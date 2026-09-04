import os
import sys
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

from fastapi import FastAPI, Query, HTTPException, Security, Depends, Request
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import uvicorn
from dotenv import load_dotenv
import redis

from app.core.db import get_db_connection, get_db_cursor
from app.core import config
from app.outreach.metrics import OutreachMetrics
from app.outreach.emergency import is_outreach_enabled, emergency_stop, emergency_resume, disable_account, enable_account
from app.outreach.account_health import AccountHealthManager
from app.outreach.circuit_breaker import CircuitBreaker
from app.outreach.backpressure import BackpressureManager
from app.repositories.campaign_repository import CampaignRepository

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

load_dotenv()

app = FastAPI(title="LeadHunter CRM Dashboard")

# ── Dashboard Security ────────────────────────────────────────────────────────
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_dashboard_auth(
    header_key: Optional[Union[str, Request]] = Security(API_KEY_HEADER),
):
    """
    Authenticates mutating and sensitive API requests strictly via the 'X-API-Key' HTTP header.
    Configured via DASHBOARD_API_KEY.
    Query parameters (e.g. ?api_key=...) are strictly rejected.
    In production environments, missing or invalid key is strictly rejected.
    """
    required_key = os.getenv("DASHBOARD_API_KEY", "").strip()
    is_production = os.getenv("ENVIRONMENT", "").lower() == "production"

    if is_production and not required_key:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: DASHBOARD_API_KEY must be configured in production."
        )

    if not required_key:
        return True  # Local development fallback when no key is set and not production

    actual_key = None
    if isinstance(header_key, str):
        actual_key = header_key
    elif hasattr(header_key, "headers"):
        actual_key = header_key.headers.get("X-API-Key") or header_key.headers.get("x-api-key")

    if not actual_key or actual_key.strip() != required_key:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing API key. Provide via 'X-API-Key' HTTP header only."
        )
    return True


def sanitize_media_path(media_input: Optional[str]) -> Optional[str]:
    """
    Validates and resolves media paths safely using canonical Path resolution.
    Rejects directory traversal (e.g. '../', symlinks outside media directory).
    """
    if not media_input:
        return None

    paths = []
    if media_input.startswith('[') and media_input.endswith(']'):
        try:
            paths = json.loads(media_input)
        except Exception:
            paths = [media_input]
    elif ',' in media_input:
        paths = [p.strip() for p in media_input.split(',') if p.strip()]
    else:
        paths = [media_input.strip()]

    # Canonical base directory for media
    base_media_dir = Path(os.getenv("ALLOWED_MEDIA_DIR", "media")).resolve()
    # Create media directory if it doesn't exist yet
    base_media_dir.mkdir(parents=True, exist_ok=True)

    sanitized = []
    for p in paths:
        path_obj = Path(p.strip())
        # Resolve full canonical path
        try:
            resolved = (base_media_dir / path_obj).resolve() if not path_obj.is_absolute() else path_obj.resolve()
            # Strict path containment verification
            resolved.relative_to(base_media_dir)
        except (ValueError, RuntimeError):
            raise HTTPException(
                status_code=400,
                detail=f"Security Alert: Media path '{p}' is outside allowed media directory ('{base_media_dir}')."
            )
        sanitized.append(str(resolved))

    return ",".join(sanitized) if len(sanitized) > 1 else (sanitized[0] if sanitized else None)


class CampaignRequest(BaseModel):
    message_text: str
    media_path: Optional[str] = None
    selected_lead_ids: List[str]


@app.post("/api/campaigns/start", dependencies=[Depends(verify_dashboard_auth)])
def start_campaign(req: CampaignRequest):
    try:
        # Sanitize media path against traversal
        safe_media_path = sanitize_media_path(req.media_path)
        campaign_id, inserted_logs = CampaignRepository.create_campaign(
            message_text=req.message_text,
            media_path=safe_media_path,
            selected_lead_ids=req.selected_lead_ids
        )
        logging.info(f"Outreach Campaign started: ID {campaign_id} with {inserted_logs} recipient leads.")
        return {
            "success": True,
            "campaign_id": campaign_id,
            "queued_leads_count": inserted_logs
        }
    except Exception as e:
        logging.error(f"Error starting campaign: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/campaigns", dependencies=[Depends(verify_dashboard_auth)])
def get_campaigns():
    try:
        # 0. Auto-enqueue any unqueued eligible leads into active campaign with priority
        active_camp = CampaignRepository.get_active_campaign()
        if active_camp:
            CampaignRepository.auto_enqueue_eligible_leads(active_camp['id'])

        # 1. Fetch campaigns with priority tiers and 50 granular priority-ordered logs
        campaigns, logs = CampaignRepository.get_campaign_summaries()
        return {
            "success": True,
            "campaigns": campaigns,
            "logs": logs
        }
    except Exception as e:
        logging.error(f"Error fetching campaigns: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/campaigns/{campaign_id}/rerank", dependencies=[Depends(verify_dashboard_auth)])
def rerank_campaign(campaign_id: str):
    try:
        res = CampaignRepository.rerank_campaign_recipients(campaign_id)
        logging.info(f"Campaign {campaign_id} reranked: {res}")
        return {
            "success": True,
            "campaign_id": campaign_id,
            "reranked_count": res.get("updated", 0),
            "tier_counts": res.get("tier_counts", {})
        }
    except Exception as e:
        logging.error(f"Error reranking campaign {campaign_id}: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/leads", dependencies=[Depends(verify_dashboard_auth)])
def get_leads(
    min_score: int = Query(None, alias="minScore"),
    has_vip: bool = Query(None, alias="hasVip"),
    has_ac_mgmt: bool = Query(None, alias="hasAcMgmt"),
    has_website: bool = Query(None, alias="hasWebsite"),
    has_whatsapp: bool = Query(None, alias="hasWhatsapp"),
    arabic_only: bool = Query(None, alias="arabicOnly")
):
    try:
        with get_db_cursor(commit_on_success=False) as cur:
            # Build query dynamically
            # Only show genuinely qualified leads: must have score>=10, real member count, and not be a dummy/broken record
            query = """SELECT * FROM leads WHERE status = 'new' AND last_scan IS NOT NULL
                AND lead_score >= 10
                AND member_count > 0
                AND (description IS NULL OR description NOT LIKE 'Blacklisted entity%%')
                AND (description IS NULL OR description NOT LIKE 'Entity does not exist%%')"""
            params = []
            
            if min_score is not None:
                query += " AND lead_score >= %s"
                params.append(min_score)
            if has_vip:
                query += " AND vip = TRUE"
            if has_ac_mgmt:
                query += " AND account_management = TRUE"
            if has_website:
                query += " AND website IS NOT NULL AND website != ''"
            if has_whatsapp:
                query += " AND whatsapp IS NOT NULL AND whatsapp != ''"
            if arabic_only:
                query += " AND language = 'Arabic'"
                
            query += " ORDER BY lead_score DESC"
            
            cur.execute(query, params)
            leads = cur.fetchall()
            
            # Get count of blacklist and total posts for stats
            cur.execute("SELECT COUNT(*) as count FROM blacklist")
            blacklist_count = cur.fetchone()["count"]
            
            cur.execute("SELECT COUNT(*) as count FROM channel_posts")
            posts_count = cur.fetchone()["count"]
            
        return {
            "success": True,
            "leads": leads,
            "stats": {
                "total_leads": len(leads),
                "blacklist_count": blacklist_count,
                "posts_count": posts_count
            }
        }
    except Exception as e:
        logging.error(f"Error fetching leads: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/leaderboards", dependencies=[Depends(verify_dashboard_auth)])
def get_leaderboards():
    try:
        with get_db_cursor(commit_on_success=False) as cur:
            # 1. Top VIP Sellers
            cur.execute("""
                SELECT channel_username, lead_score, tier, member_count 
                FROM leads 
                WHERE vip = TRUE AND status != 'rejected' 
                ORDER BY lead_score DESC, member_count DESC 
                LIMIT 10
            """)
            top_vip = cur.fetchall()
            
            # 2. Top Account Managers
            cur.execute("""
                SELECT channel_username, lead_score, tier, member_count 
                FROM leads 
                WHERE account_management = TRUE AND status != 'rejected' 
                ORDER BY lead_score DESC, member_count DESC 
                LIMIT 10
            """)
            top_ac_mgmt = cur.fetchall()
            
            # 3. Top Copy Trading Providers
            cur.execute("""
                SELECT channel_username, lead_score, tier, member_count 
                FROM leads 
                WHERE copy_trading = TRUE AND status != 'rejected' 
                ORDER BY lead_score DESC, member_count DESC 
                LIMIT 10
            """)
            top_copy = cur.fetchall()
            
            # 4. Top Funded Account Providers
            cur.execute("""
                SELECT channel_username, lead_score, tier, member_count 
                FROM leads 
                WHERE funded_accounts = TRUE AND status != 'rejected' 
                ORDER BY lead_score DESC, member_count DESC 
                LIMIT 10
            """)
            top_funded = cur.fetchall()
            
            # 5. Most Connected Channels
            cur.execute("""
                SELECT l.channel_username, 
                       ((SELECT COUNT(*) FROM channel_graph WHERE source_channel_id = l.id) + 
                        (SELECT COUNT(*) FROM channel_graph WHERE target_channel_id = l.id)) as connection_count,
                       l.lead_score, l.tier
                FROM leads l
                WHERE l.status != 'rejected'
                ORDER BY connection_count DESC, l.lead_score DESC
                LIMIT 10;
            """)
            most_connected = cur.fetchall()
            
            # 6. Most Advertised Channels
            cur.execute("""
                SELECT l.channel_username, COUNT(cg.target_channel_id) as ad_count, l.lead_score, l.tier
                FROM leads l
                JOIN channel_graph cg ON l.id = cg.target_channel_id
                WHERE l.status != 'rejected'
                GROUP BY l.channel_username, l.lead_score, l.tier
                ORDER BY ad_count DESC, l.lead_score DESC
                LIMIT 10;
            """)
            most_advertised = cur.fetchall()
            
            # 7. Highest Lead Score
            cur.execute("""
                SELECT channel_username, lead_score, tier, member_count 
                FROM leads 
                WHERE status != 'rejected' 
                ORDER BY lead_score DESC, member_count DESC 
                LIMIT 10
            """)
            highest_score = cur.fetchall()
            
            # 8. Fastest Growing Channels
            # Growth tracked by new graph connections in last 30 days, fallback to member_count
            cur.execute("""
                SELECT l.channel_username, COALESCE(growth.cnt, 0) as growth_count, l.lead_score, l.tier, l.member_count
                FROM leads l
                LEFT JOIN (
                    SELECT source_channel_id, COUNT(*) as cnt 
                    FROM channel_graph 
                    WHERE created_at >= NOW() - INTERVAL '30 days' 
                    GROUP BY source_channel_id
                ) growth ON l.id = growth.source_channel_id
                WHERE l.status != 'rejected'
                ORDER BY growth_count DESC, l.member_count DESC
                LIMIT 10;
            """)
            fastest_growing = cur.fetchall()
            
            # 9. Highest Marketplace Score
            cur.execute("""
                SELECT channel_username, marketplace_score, lead_score, tier 
                FROM leads 
                WHERE is_group = TRUE AND status != 'rejected' 
                ORDER BY marketplace_score DESC, lead_score DESC 
                LIMIT 10
            """)
            highest_marketplace = cur.fetchall()
            
        return {
            "success": True,
            "top_vip": top_vip,
            "top_ac_mgmt": top_ac_mgmt,
            "top_copy": top_copy,
            "top_funded": top_funded,
            "most_connected": most_connected,
            "most_advertised": most_advertised,
            "highest_score": highest_score,
            "fastest_growing": fastest_growing,
            "highest_marketplace": highest_marketplace
        }
    except Exception as e:
        logging.error(f"Error fetching leaderboards: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/group_metrics", dependencies=[Depends(verify_dashboard_auth)])
def get_group_metrics():
    try:
        with get_db_cursor(commit_on_success=False) as cur:
            cur.execute("""
                SELECT l.channel_username as group_username, gm.messages_scanned, gm.mentions_count, 
                       gm.telegram_links_count, gm.advertisements_count, gm.marketplace_score, 
                       gm.last_scan, l.member_count
                FROM group_metrics gm
                JOIN leads l ON gm.group_id = l.id
                WHERE l.status != 'rejected'
                ORDER BY gm.marketplace_score DESC, gm.last_scan DESC
                LIMIT 50
            """)
            metrics = cur.fetchall()
        return {"success": True, "metrics": metrics}
    except Exception as e:
        logging.error(f"Error fetching group metrics: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/discovery_stats", dependencies=[Depends(verify_dashboard_auth)])
def get_discovery_stats():
    try:
        with get_db_cursor(commit_on_success=False) as cur:
            # 1. Top Arabic Keywords (Phase 7 & Phase 8)
            cur.execute("""
                SELECT discovery_source as keyword, COUNT(*) as discovered_channels, COUNT(*) FILTER (WHERE lead_score >= 50) as high_quality_leads,
                       CASE WHEN COUNT(*) > 0 THEN CAST((COUNT(*) FILTER (WHERE lead_score >= 50) * 100.0 / COUNT(*)) AS INT) ELSE 0 END as quality_score
                FROM leads
                WHERE is_group = FALSE AND discovery_method = 'telegram_search' AND (language = 'Arabic' OR arabic_score >= 40)
                GROUP BY discovery_source
                ORDER BY discovered_channels DESC, quality_score DESC
                LIMIT 20
            """)
            top_keywords = cur.fetchall()
            
            # 2. Top Arabic Discovery Sources (Phase 7)
            cur.execute("""
                SELECT discovery_source as source_name, 
                       CASE WHEN discovery_method = 'telegram_search' THEN 'keyword' ELSE 'group' END as source_type,
                       MAX(discovery_source) as keyword,
                       COUNT(*) as discovered_channels,
                       COUNT(*) FILTER (WHERE lead_score >= 50) as high_quality_leads,
                       CASE WHEN COUNT(*) > 0 THEN CAST((COUNT(*) FILTER (WHERE lead_score >= 50) * 100.0 / COUNT(*)) AS INT) ELSE 0 END as quality_score,
                       MAX(discovered_at) as last_discovery
                FROM leads
                WHERE is_group = FALSE AND (language = 'Arabic' OR arabic_score >= 40)
                GROUP BY discovery_source, discovery_method
                ORDER BY discovered_channels DESC
                LIMIT 20
            """)
            top_sources = cur.fetchall()
            for r in top_sources:
                if r.get('last_discovery'):
                    r['last_discovery'] = r['last_discovery'].isoformat()
            
            # 3. Top Arabic Marketplace Groups (Phase 7: ordered by Arabic channels discovered)
            cur.execute("""
                SELECT l.channel_username as group_username, l.marketplace_score, l.member_count,
                       0 as messages_scanned,
                       (SELECT COUNT(*) FROM channel_graph cg JOIN leads l2 ON cg.target_channel_id = l2.id WHERE cg.source_channel_id = l.id AND (l2.language = 'Arabic' OR l2.arabic_score >= 40)) as advertisements_count
                FROM leads l
                WHERE l.is_group = TRUE AND l.status != 'rejected'
                ORDER BY advertisements_count DESC, l.marketplace_score DESC, l.member_count DESC
                LIMIT 20
            """)
            top_marketplace_groups = cur.fetchall()
            
            # 4. Arabic Channels Discovered Per Day (last 14 days)
            cur.execute("""
                SELECT DATE(discovered_at) as date, COUNT(*) as count
                FROM leads
                WHERE is_group = FALSE AND (language = 'Arabic' OR arabic_score >= 40)
                GROUP BY DATE(discovered_at)
                ORDER BY DATE(discovered_at) DESC
                LIMIT 14
            """)
            discovered_per_day = cur.fetchall()
            for r in discovered_per_day:
                r['date'] = str(r['date'])
                
            # 5. Arabic High Quality Leads Per Day (last 14 days)
            cur.execute("""
                SELECT DATE(discovered_at) as date, COUNT(*) as count
                FROM leads
                WHERE is_group = FALSE AND lead_score >= 50 AND (language = 'Arabic' OR arabic_score >= 40)
                GROUP BY DATE(discovered_at)
                ORDER BY DATE(discovered_at) DESC
                LIMIT 14
            """)
            hq_leads_per_day = cur.fetchall()
            for r in hq_leads_per_day:
                r['date'] = str(r['date'])
                
            # 6. Arabic Discovery Rate (Phase 7)
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE language = 'Arabic' OR arabic_score >= 40) as arabic_count,
                    CASE 
                        WHEN COUNT(*) > 0 THEN CAST((COUNT(*) FILTER (WHERE language = 'Arabic' OR arabic_score >= 40) * 100.0 / COUNT(*)) AS INT)
                        ELSE 0
                    END as overall_rate
                FROM leads
                WHERE is_group = FALSE
            """)
            arabic_rate_stats = cur.fetchone()
            
            # Arabic discovery rate per day
            cur.execute("""
                SELECT 
                    DATE(discovered_at) as date,
                    CASE 
                        WHEN COUNT(*) > 0 THEN CAST((COUNT(*) FILTER (WHERE language = 'Arabic' OR arabic_score >= 40) * 100.0 / COUNT(*)) AS INT)
                        ELSE 0
                    END as rate
                FROM leads
                WHERE is_group = FALSE
                GROUP BY DATE(discovered_at)
                ORDER BY DATE(discovered_at) DESC
                LIMIT 14
            """)
            arabic_rate_per_day = cur.fetchall()
            for r in arabic_rate_per_day:
                r['date'] = str(r['date'])
            
        return {
            "success": True,
            "top_keywords": top_keywords,
            "top_sources": top_sources,
            "top_marketplace_groups": top_marketplace_groups,
            "discovered_per_day": discovered_per_day,
            "hq_leads_per_day": hq_leads_per_day,
            "arabic_rate_stats": arabic_rate_stats,
            "arabic_rate_per_day": arabic_rate_per_day
        }
    except Exception as e:
        logging.error(f"Error fetching discovery stats: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/quality_stats", dependencies=[Depends(verify_dashboard_auth)])
def get_quality_stats():
    """PHASE 7 — Lead Quality Dashboard: funnel, categories, score distribution, rejections."""
    try:
        with get_db_cursor(commit_on_success=False) as cur:
            # 1. Lead Conversion Funnel
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE is_group = FALSE) as total_discovered,
                    COUNT(*) FILTER (WHERE is_group = FALSE AND lead_score IS NOT NULL AND lead_score > 0) as total_validated,
                    COUNT(*) FILTER (WHERE is_group = FALSE AND status = 'new' AND lead_score >= 10 AND member_count > 0) as qualified_leads,
                    COUNT(*) FILTER (WHERE is_group = FALSE AND status = 'contacted') as partners
                FROM leads
            """)
            funnel = cur.fetchone()

            # 2. Forex Category Breakdown
            cur.execute("""
                SELECT
                    COALESCE(forex_category, 'unknown') as category,
                    COUNT(*) as count,
                    ROUND(AVG(lead_score)) as avg_score,
                    ROUND(AVG(forex_intent_score)) as avg_forex_intent
                FROM leads
                WHERE is_group = FALSE AND status = 'new' AND lead_score > 0
                GROUP BY forex_category
                ORDER BY count DESC
            """)
            categories = cur.fetchall()

            # 3. Score Distribution
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE lead_score >= 90) as tier_s,
                    COUNT(*) FILTER (WHERE lead_score >= 75 AND lead_score < 90) as tier_a,
                    COUNT(*) FILTER (WHERE lead_score >= 50 AND lead_score < 75) as tier_b,
                    COUNT(*) FILTER (WHERE lead_score >= 25 AND lead_score < 50) as tier_c,
                    COUNT(*) FILTER (WHERE lead_score > 0 AND lead_score < 25) as tier_d,
                    ROUND(AVG(lead_score)) as avg_lead_score,
                    ROUND(AVG(forex_intent_score)) as avg_forex_intent,
                    ROUND(AVG(arabic_score)) as avg_arabic_score
                FROM leads
                WHERE is_group = FALSE AND lead_score > 0
            """)
            score_dist = cur.fetchone()

            # 4. Rejection Reasons
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'rejected' AND arabic_score < 50) as rejected_low_arabic,
                    COUNT(*) FILTER (WHERE status = 'rejected' AND (lead_score < 50 OR forex_intent_score < 30)) as rejected_low_score,
                    COUNT(*) as total_rejected
                FROM leads
                WHERE is_group = FALSE AND status = 'rejected'
            """)
            rejections = cur.fetchone()

            # 5. Blacklist reasons breakdown
            cur.execute("""
                SELECT reason, COUNT(*) as count
                FROM blacklist
                GROUP BY reason
                ORDER BY count DESC
            """)
            blacklist_reasons = cur.fetchall()

            # 6. Top Forex Intent Score leads
            cur.execute("""
                SELECT channel_username, lead_score, forex_intent_score, arabic_score,
                       forex_category, tier, member_count
                FROM leads
                WHERE is_group = FALSE AND status = 'new' AND forex_intent_score > 0
                ORDER BY forex_intent_score DESC, lead_score DESC
                LIMIT 10
            """)
            top_forex_intent = cur.fetchall()

        return {
            "success": True,
            "funnel": funnel,
            "categories": categories,
            "score_dist": score_dist,
            "rejections": rejections,
            "blacklist_reasons": blacklist_reasons,
            "top_forex_intent": top_forex_intent
        }
    except Exception as e:
        logging.error(f"Error fetching quality stats: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/graph/stats", dependencies=[Depends(verify_dashboard_auth)])
def get_graph_stats():
    """
    Exposes graph analytics: Most Mentioned, Most Connected, Fastest Growing, and Top Networks.
    """
    try:
        with get_db_cursor(commit_on_success=False) as cur:
            # 1. Most Mentioned Channels
            query_mentioned = """
            SELECT l.channel_username, COUNT(cg.target_channel_id) as mention_count, l.lead_score, l.tier
            FROM leads l
            JOIN channel_graph cg ON l.id = cg.target_channel_id
            GROUP BY l.channel_username, l.lead_score, l.tier
            ORDER BY mention_count DESC
            LIMIT 10;
            """
            cur.execute(query_mentioned)
            most_mentioned = cur.fetchall()
            
            # 2. Most Connected Channels (Degree Centrality)
            query_connected = """
            SELECT l.channel_username, 
                   ((SELECT COUNT(*) FROM channel_graph WHERE source_channel_id = l.id) + 
                    (SELECT COUNT(*) FROM channel_graph WHERE target_channel_id = l.id)) as connection_count,
                   l.lead_score, l.tier
            FROM leads l
            ORDER BY connection_count DESC
            LIMIT 10;
            """
            cur.execute(query_connected)
            most_connected = cur.fetchall()
            
            # 3. Fastest Growing Discovery Sources
            query_growing = """
            SELECT l.channel_username, COUNT(cg.target_channel_id) as new_discoveries_count, l.lead_score, l.tier
            FROM leads l
            JOIN channel_graph cg ON l.id = cg.source_channel_id
            WHERE cg.created_at >= NOW() - INTERVAL '7 days'
            GROUP BY l.channel_username, l.lead_score, l.tier
            ORDER BY new_discoveries_count DESC
            LIMIT 10;
            """
            cur.execute(query_growing)
            fastest_growing = cur.fetchall()
            
            # 4. Top Forex Networks (Edges list)
            query_networks = """
            SELECT l_source.channel_username as source, l_target.channel_username as target, cg.discovery_method
            FROM channel_graph cg
            JOIN leads l_source ON cg.source_channel_id = l_source.id
            JOIN leads l_target ON cg.target_channel_id = l_target.id
            ORDER BY cg.created_at DESC
            LIMIT 15;
            """
            cur.execute(query_networks)
            top_networks = cur.fetchall()
            
        return {
            "success": True,
            "most_mentioned": most_mentioned,
            "most_connected": most_connected,
            "fastest_growing": fastest_growing,
            "top_networks": top_networks
        }
    except Exception as e:
        logging.error(f"Error fetching graph stats: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/graph/network", dependencies=[Depends(verify_dashboard_auth)])
def get_graph_network():
    """
    Returns full node-link structure for rendering force-directed network graphs.
    """
    try:
        with get_db_cursor(commit_on_success=False) as cur:
            # Select active nodes
            cur.execute("SELECT id, channel_username, lead_score, tier FROM leads WHERE status != 'rejected'")
            nodes = cur.fetchall()
            
            # Select edges
            cur.execute("SELECT source_channel_id as source, target_channel_id as target, discovery_method FROM channel_graph")
            edges = cur.fetchall()
            
        return {
            "success": True,
            "nodes": nodes,
            "edges": edges
        }
    except Exception as e:
        logging.error(f"Error fetching network structure: {e}")
        return {"success": False, "error": str(e)}


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    html_content = """
    <!DOCTYPE html>
    <html lang="en" class="h-full bg-slate-950">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>LeadHunter CRM - Arabic Forex Discovery Portal</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Outfit', sans-serif;
            }
            .glassmorphism {
                background: rgba(15, 23, 42, 0.45);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            .glassmorphism-input {
                background: rgba(15, 23, 42, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            .glassmorphism-input:focus {
                border-color: rgba(99, 102, 241, 0.6);
                outline: none;
                box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
            }
            ::-webkit-scrollbar {
                width: 6px;
                height: 6px;
            }
            ::-webkit-scrollbar-track {
                background: rgba(15, 23, 42, 0.8);
            }
            ::-webkit-scrollbar-thumb {
                background: rgba(99, 102, 241, 0.4);
                border-radius: 4px;
            }
            ::-webkit-scrollbar-thumb:hover {
                background: rgba(99, 102, 241, 0.6);
            }
        </style>
    </head>
    <body class="h-full text-slate-100 flex flex-col antialiased">
        
        <!-- Header -->
        <header class="w-full py-5 px-8 flex justify-between items-center border-b border-slate-900 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
            <div class="flex items-center space-x-3">
                <div class="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                    <svg class="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
                    </svg>
                </div>
                <div>
                    <h1 class="text-xl font-bold tracking-tight bg-gradient-to-r from-indigo-200 via-slate-100 to-indigo-200 bg-clip-text text-transparent">LeadHunter CRM</h1>
                    <p class="text-xs text-slate-500">Stealth Arabic Forex Lead Intelligence Portal</p>
                </div>
            </div>
            <div class="flex items-center space-x-6">
                <!-- Navigation Tabs -->
                <nav class="flex space-x-2 bg-slate-900/60 p-1 rounded-xl border border-slate-800/40">
                    <button onclick="switchTab('leads')" id="tab-leads-btn" class="px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-500 text-white transition">Leads Grid</button>
                    <button onclick="switchTab('campaigns')" id="tab-campaigns-btn" class="px-4 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition">📢 Campaigns & Logs</button>
                    <button onclick="switchTab('graph')" id="tab-graph-btn" class="px-4 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition">Graph Network</button>
                    <button onclick="switchTab('leaderboards')" id="tab-leaderboards-btn" class="px-4 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition">CRM Leaderboards</button>
                    <button onclick="switchTab('group-metrics')" id="tab-group-metrics-btn" class="px-4 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition">Group Metrics</button>
                    <button onclick="switchTab('discovery')" id="tab-discovery-btn" class="px-4 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition">Discovery Analytics</button>
                    <button onclick="switchTab('quality')" id="tab-quality-btn" class="px-4 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition">&#127919; Lead Quality</button>
                </nav>
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <span class="h-2 w-2 rounded-full bg-emerald-400 mr-2 animate-pulse"></span>
                    Validator Workers Online
                </span>
            </div>
        </header>

        <!-- Main Body -->
        <main class="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-8">
            
            <!-- Metrics Row -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <!-- Card 1 -->
                <div class="glassmorphism p-6 rounded-2xl flex items-center space-x-4 shadow-xl">
                    <div class="h-12 w-12 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center border border-indigo-500/20">
                        <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
                        </svg>
                    </div>
                    <div>
                        <p class="text-xs text-slate-400 font-medium uppercase tracking-wider">Active Verified Leads</p>
                        <h3 id="stat-leads" class="text-2xl font-bold mt-1 text-white">-</h3>
                    </div>
                </div>
                <!-- Card 2 -->
                <div class="glassmorphism p-6 rounded-2xl flex items-center space-x-4 shadow-xl">
                    <div class="h-12 w-12 rounded-lg bg-rose-500/10 text-rose-400 flex items-center justify-center border border-rose-500/20">
                        <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"></path>
                        </svg>
                    </div>
                    <div>
                        <p class="text-xs text-slate-400 font-medium uppercase tracking-wider">Blacklisted Entities</p>
                        <h3 id="stat-blacklist" class="text-2xl font-bold mt-1 text-white">-</h3>
                    </div>
                </div>
                <!-- Card 3 -->
                <div class="glassmorphism p-6 rounded-2xl flex items-center space-x-4 shadow-xl">
                    <div class="h-12 w-12 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center border border-amber-500/20">
                        <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                        </svg>
                    </div>
                    <div>
                        <p class="text-xs text-slate-400 font-medium uppercase tracking-wider">Scanned Ad Messages</p>
                        <h3 id="stat-posts" class="text-2xl font-bold mt-1 text-white">-</h3>
                    </div>
                </div>
            </div>

            <!-- Leads Tab Section -->
            <div id="tab-leads" class="space-y-8">
                <!-- Filters Section -->
                <div class="glassmorphism p-6 rounded-2xl shadow-xl space-y-4">
                    <h4 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Discover Filters</h4>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <!-- Column 1: Range -->
                        <div class="space-y-2">
                            <label class="text-xs text-slate-400 flex justify-between font-medium">
                                <span>Minimum Lead Score</span>
                                <span id="score-val" class="text-indigo-400 font-semibold">10</span>
                            </label>
                            <input type="range" id="min-score" min="10" max="100" value="10" step="5" class="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500">
                        </div>
                        <!-- Column 2: Toggles -->
                        <div class="flex flex-wrap gap-4 items-center h-full">
                            <label class="flex items-center space-x-2 text-xs font-medium cursor-pointer text-slate-300">
                                <input type="checkbox" id="has-vip" class="h-4 w-4 bg-slate-900 border-slate-700 rounded text-indigo-600 accent-indigo-500">
                                <span>Has VIP/Premium</span>
                            </label>
                            <label class="flex items-center space-x-2 text-xs font-medium cursor-pointer text-slate-300">
                                <input type="checkbox" id="has-ac-mgmt" class="h-4 w-4 bg-slate-900 border-slate-700 rounded text-indigo-600 accent-indigo-500">
                                <span>Has Account Management</span>
                            </label>
                            <label class="flex items-center space-x-2 text-xs font-medium cursor-pointer text-slate-300">
                                <input type="checkbox" id="arabic-only" checked class="h-4 w-4 bg-slate-900 border-slate-700 rounded text-indigo-600 accent-indigo-500">
                                <span>Arabic Niche Only</span>
                            </label>
                        </div>
                        <!-- Column 3: Toggles 2 -->
                        <div class="flex flex-wrap gap-4 items-center h-full">
                            <label class="flex items-center space-x-2 text-xs font-medium cursor-pointer text-slate-300">
                                <input type="checkbox" id="has-website" class="h-4 w-4 bg-slate-900 border-slate-700 rounded text-indigo-600 accent-indigo-500">
                                <span>Has Website Link</span>
                            </label>
                            <label class="flex items-center space-x-2 text-xs font-medium cursor-pointer text-slate-300">
                                <input type="checkbox" id="has-whatsapp" class="h-4 w-4 bg-slate-900 border-slate-700 rounded text-indigo-600 accent-indigo-500">
                                <span>Has WhatsApp Contact</span>
                            </label>
                        </div>
                    </div>
                </div>

                <!-- Campaign Creator Panel -->
                <div class="glassmorphism p-6 rounded-2xl shadow-xl space-y-4">
                    <h4 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Campaign Dispatcher Panel</h4>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <!-- Message Text area -->
                        <div class="space-y-2">
                            <label class="text-xs text-slate-400 font-medium">Outreach Message Text</label>
                            <textarea id="campaign-message" rows="4" placeholder="Type your sales outreach message here... (e.g. Hello, we would like to offer account management services...)" class="w-full p-3 rounded-xl glassmorphism-input text-slate-200 text-xs resize-none"></textarea>
                        </div>
                        <!-- Optional Media & Start -->
                        <div class="flex flex-col justify-between space-y-4">
                            <div class="space-y-2">
                                <label class="text-xs text-slate-400 font-medium">Optional Media Attachments (Path or Filename on Server)</label>
                                <input type="text" id="campaign-media" placeholder="e.g. /app/media/promo.jpg (leave blank for text-only)" class="w-full p-2.5 rounded-xl glassmorphism-input text-slate-200 text-xs">
                            </div>
                            <div class="flex items-center justify-between pt-2">
                                <span class="text-xs text-slate-400 font-semibold text-indigo-400" id="selected-count-msg">0 channel(s) selected</span>
                                <button onclick="startCampaign()" class="px-6 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 transition text-xs font-semibold rounded-xl text-white shadow-lg shadow-indigo-500/20 flex items-center space-x-2">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
                                    </svg>
                                    <span>Start Sending Campaign</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Leads Spreadsheet Table -->
                <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                    <div class="px-6 py-4 border-b border-slate-900 flex justify-between items-center bg-slate-950/20">
                        <h3 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Leads List</h3>
                        <button onclick="fetchLeads()" class="px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 transition text-xs font-medium rounded-lg text-white shadow-lg shadow-indigo-500/10">
                            Refresh Grid
                        </button>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="bg-slate-900/60 border-b border-slate-900 text-slate-400 font-medium">
                                    <th class="px-6 py-4 text-center select-all-col w-[50px]"><input type="checkbox" id="select-all-leads" onclick="toggleSelectAll(this)" class="h-4 w-4 bg-slate-900 border-slate-700 rounded text-indigo-600 accent-indigo-500 cursor-pointer"></th>
                                    <th class="px-6 py-4">Lead Username</th>
                                    <th class="px-6 py-4">Members</th>
                                    <th class="px-6 py-4 text-center">Score</th>
                                    <th class="px-6 py-4 text-center">Tier</th>
                                    <th class="px-6 py-4 text-center">Language (Ratio)</th>
                                    <th class="px-6 py-4 text-center">VIP</th>
                                    <th class="px-6 py-4 text-center">Subscription</th>
                                    <th class="px-6 py-4 text-center">Ac. Mgmt</th>
                                    <th class="px-6 py-4 text-center">Copy Trading</th>
                                    <th class="px-6 py-4">Website</th>
                                    <th class="px-6 py-4">WhatsApp</th>
                                    <th class="px-6 py-4">Contact</th>
                                    <th class="px-6 py-4">Last Activity</th>
                                </tr>
                            </thead>
                            <tbody id="leads-body" class="divide-y divide-slate-900/40 text-slate-300">
                                <tr>
                                    <td colspan="14" class="px-6 py-8 text-center text-slate-500">Loading leads data...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Campaigns Tab Section -->
            <div id="tab-campaigns" class="space-y-8 hidden">
                <!-- Campaigns Summary -->
                <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                    <div class="px-6 py-4 border-b border-slate-900 flex justify-between items-center bg-slate-950/20">
                        <h3 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Outreach Campaigns History</h3>
                        <button onclick="fetchCampaigns()" class="px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 transition text-xs font-medium rounded-lg text-white shadow-lg shadow-indigo-500/10">
                            Refresh Campaigns
                        </button>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="bg-slate-900/60 border-b border-slate-900 text-slate-400 font-medium">
                                    <th class="px-5 py-4">Campaign ID</th>
                                    <th class="px-5 py-4">Created At</th>
                                    <th class="px-5 py-4">Message Snippet</th>
                                    <th class="px-4 py-4 text-center">Recipients</th>
                                    <th class="px-4 py-4 text-center font-semibold text-emerald-400">Sent</th>
                                    <th class="px-4 py-4 text-center font-semibold text-cyan-400">Follow-ups</th>
                                    <th class="px-4 py-4 text-center font-semibold text-teal-400">Replied</th>
                                    <th class="px-4 py-4 text-center font-semibold text-rose-400">Failed</th>
                                    <th class="px-4 py-4 text-center font-semibold text-purple-400">Skipped</th>
                                    <th class="px-4 py-4 text-center font-semibold text-amber-400">Pending</th>
                                    <th class="px-4 py-4 text-center">Status</th>
                                </tr>
                            </thead>
                            <tbody id="campaigns-body" class="divide-y divide-slate-900/40 text-slate-300">
                                <tr>
                                    <td colspan="9" class="px-6 py-8 text-center text-slate-500">Loading campaign summaries...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Latest Logs -->
                <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                    <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                        <h3 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Granular Message Logs (Latest 50 attempts)</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="bg-slate-900/60 border-b border-slate-900 text-slate-400 font-medium">
                                    <th class="px-6 py-4">Target Channel</th>
                                    <th class="px-6 py-4">Outreach Contact</th>
                                    <th class="px-6 py-4">Message Preview</th>
                                    <th class="px-6 py-4 text-center">Sent At</th>
                                    <th class="px-6 py-4 text-center">Status</th>
                                    <th class="px-6 py-4">Error / Detail</th>
                                </tr>
                            </thead>
                            <tbody id="campaign-logs-body" class="divide-y divide-slate-900/40 text-slate-300">
                                <tr>
                                    <td colspan="6" class="px-6 py-8 text-center text-slate-500">Loading detailed logs...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Graph Analytics Tab Section -->
            <div id="tab-graph" class="space-y-8 hidden">
                <!-- Interactive Graph Diagram -->
                <div class="glassmorphism p-6 rounded-2xl shadow-xl space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-900/40 pb-4">
                        <div>
                            <h4 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Force-Directed Channel Graph Map</h4>
                            <p class="text-xs text-slate-500">Interactive live relationship crawl tree. Drag nodes to explore connections.</p>
                        </div>
                        <button onclick="initNetworkGraph()" class="px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 transition text-xs font-medium rounded-lg text-white shadow-lg shadow-indigo-500/10">
                            Reset Layout
                        </button>
                    </div>
                    <div class="relative w-full h-[500px] rounded-xl overflow-hidden bg-slate-950/60 border border-slate-900">
                        <canvas id="network-canvas" class="w-full h-full block cursor-grab active:cursor-grabbing"></canvas>
                        <!-- Graph tooltip -->
                        <div id="graph-tooltip" class="absolute pointer-events-none p-3 bg-slate-950/90 border border-slate-800 rounded-lg text-xs font-medium text-slate-300 opacity-0 transition-opacity duration-150 shadow-xl max-w-[200px]"></div>
                    </div>
                </div>

                <!-- Stats Columns -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <!-- Col 1: Most Mentioned -->
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Most Mentioned Channels</h4>
                        </div>
                        <div class="p-4 overflow-y-auto max-h-[300px]">
                            <ul id="list-mentioned" class="space-y-3 text-xs">
                                <li class="text-center text-slate-500">Querying mentions...</li>
                            </ul>
                        </div>
                    </div>
                    <!-- Col 2: Most Connected -->
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Most Connected (Degree Centrality)</h4>
                        </div>
                        <div class="p-4 overflow-y-auto max-h-[300px]">
                            <ul id="list-connected" class="space-y-3 text-xs">
                                <li class="text-center text-slate-500">Querying connections...</li>
                            </ul>
                        </div>
                    </div>
                    <!-- Col 3: Fastest Growing Sources -->
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Fastest Growing Discovery Sources</h4>
                        </div>
                        <div class="p-4 overflow-y-auto max-h-[300px]">
                            <ul id="list-growing" class="space-y-3 text-xs">
                                <li class="text-center text-slate-500">Querying growth...</li>
                            </ul>
                        </div>
                    </div>
                </div>

                <!-- Top Forex Network Edges -->
                <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                    <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                        <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Active Discovery Relationships (Latest Mentions)</h4>
                    </div>
                    <div class="p-6">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4" id="list-relationships">
                            <div class="text-slate-500 text-xs">Loading relationship details...</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- CRM Leaderboards Tab Section -->
            <div id="tab-leaderboards" class="space-y-8 hidden">
                <div class="glassmorphism p-6 rounded-2xl shadow-xl flex justify-between items-center bg-slate-950/20">
                    <div>
                        <h4 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Autonomous CRM Leaderboards</h4>
                        <p class="text-xs text-slate-500">Top high-value leads categorized by business model, network connectivity, and scoring tier.</p>
                    </div>
                    <button onclick="fetchLeaderboards()" class="px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 transition text-xs font-medium rounded-lg text-white shadow-lg shadow-indigo-500/10">
                        Refresh Leaderboards
                    </button>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <!-- Column 1: High-Value Services -->
                    <div class="space-y-6">
                        <!-- Card 1: Top VIP Sellers -->
                        <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                            <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20 flex items-center space-x-2">
                                <div class="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                                </div>
                                <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Top VIP Sellers</h4>
                            </div>
                            <div class="p-4">
                                <ul id="list-vip-sellers" class="space-y-2 text-xs animate-fade-in">
                                    <li class="text-center text-slate-500">Loading...</li>
                                </ul>
                            </div>
                        </div>

                        <!-- Card 2: Top Account Managers -->
                        <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                            <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20 flex items-center space-x-2">
                                <div class="p-1.5 rounded-lg bg-pink-500/10 text-pink-400 border border-pink-500/20">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                </div>
                                <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Top Account Managers</h4>
                            </div>
                            <div class="p-4">
                                <ul id="list-ac-managers" class="space-y-2 text-xs">
                                    <li class="text-center text-slate-500">Loading...</li>
                                </ul>
                            </div>
                        </div>

                        <!-- Card 3: Top Copy Trading Providers -->
                        <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                            <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20 flex items-center space-x-2">
                                <div class="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"></path></svg>
                                </div>
                                <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Top Copy Trading</h4>
                            </div>
                            <div class="p-4">
                                <ul id="list-copy-trading" class="space-y-2 text-xs">
                                    <li class="text-center text-slate-500">Loading...</li>
                                </ul>
                            </div>
                        </div>
                    </div>

                    <!-- Column 2: Ecosystem Network -->
                    <div class="space-y-6">
                        <!-- Card 4: Top Funded Account Providers -->
                        <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                            <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20 flex items-center space-x-2">
                                <div class="p-1.5 rounded-lg bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path></svg>
                                </div>
                                <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Top Funded Account Providers</h4>
                            </div>
                            <div class="p-4">
                                <ul id="list-funded-providers" class="space-y-2 text-xs">
                                    <li class="text-center text-slate-500">Loading...</li>
                                </ul>
                            </div>
                        </div>

                        <!-- Card 5: Most Connected Channels -->
                        <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                            <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20 flex items-center space-x-2">
                                <div class="p-1.5 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                                </div>
                                <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Most Connected Channels</h4>
                            </div>
                            <div class="p-4">
                                <ul id="list-most-connected" class="space-y-2 text-xs">
                                    <li class="text-center text-slate-500">Loading...</li>
                                </ul>
                            </div>
                        </div>

                        <!-- Card 6: Most Advertised Channels -->
                        <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                            <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20 flex items-center space-x-2">
                                <div class="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"></path></svg>
                                </div>
                                <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Most Advertised Channels</h4>
                            </div>
                            <div class="p-4">
                                <ul id="list-most-advertised" class="space-y-2 text-xs">
                                    <li class="text-center text-slate-500">Loading...</li>
                                </ul>
                            </div>
                        </div>
                    </div>

                    <!-- Column 3: Lead Growth & Scoring -->
                    <div class="space-y-6">
                        <!-- Card 7: Highest Lead Score -->
                        <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                            <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20 flex items-center space-x-2">
                                <div class="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"></path></svg>
                                </div>
                                <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Highest Lead Score</h4>
                            </div>
                            <div class="p-4">
                                <ul id="list-highest-score" class="space-y-2 text-xs">
                                    <li class="text-center text-slate-500">Loading...</li>
                                </ul>
                            </div>
                        </div>

                        <!-- Card 8: Fastest Growing Channels -->
                        <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                            <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20 flex items-center space-x-2">
                                <div class="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path></svg>
                                </div>
                                <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Fastest Growing Channels</h4>
                            </div>
                            <div class="p-4">
                                <ul id="list-fastest-growing" class="space-y-2 text-xs">
                                    <li class="text-center text-slate-500">Loading...</li>
                                </ul>
                            </div>
                        </div>

                        <!-- Card 9: Highest Marketplace Score -->
                        <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                            <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20 flex items-center space-x-2">
                                <div class="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                                </div>
                                <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-300">Highest Marketplace Score</h4>
                            </div>
                            <div class="p-4">
                                <ul id="list-highest-marketplace" class="space-y-2 text-xs">
                                    <li class="text-center text-slate-500">Loading...</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Group Metrics Tab Section -->
            <div id="tab-group-metrics" class="space-y-8 hidden">
                <div class="glassmorphism p-6 rounded-2xl shadow-xl flex justify-between items-center bg-slate-950/20">
                    <div>
                        <h4 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Marketplace Group Metrics</h4>
                        <p class="text-xs text-slate-500">Autonomous detection and scoring of marketplace groups based on advertising and link densities.</p>
                    </div>
                    <button onclick="fetchGroupMetrics()" class="px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 transition text-xs font-medium rounded-lg text-white shadow-lg shadow-indigo-500/10">
                        Refresh Metrics
                    </button>
                </div>

                <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                    <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                        <h3 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Top Marketplace Groups (Top 50 Only)</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="bg-slate-900/60 border-b border-slate-900 text-slate-400 font-medium">
                                    <th class="px-6 py-4">Group Name</th>
                                    <th class="px-6 py-4 text-center">Members</th>
                                    <th class="px-6 py-4 text-center">Marketplace Score</th>
                                    <th class="px-6 py-4 text-center">Mentions</th>
                                    <th class="px-6 py-4 text-center">Links</th>
                                    <th class="px-6 py-4 text-center">Advertisements</th>
                                    <th class="px-6 py-4 text-center">Last Scan</th>
                                </tr>
                            </thead>
                            <tbody id="group-metrics-body" class="divide-y divide-slate-900/40 text-slate-300">
                                <tr>
                                    <td colspan="7" class="px-6 py-8 text-center text-slate-500">Loading group metrics...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Discovery Analytics Tab Section -->
            <div id="tab-discovery" class="space-y-8 hidden">
                <div class="glassmorphism p-6 rounded-2xl shadow-xl flex justify-between items-center bg-slate-950/20">
                    <div>
                        <h4 class="text-sm font-semibold uppercase tracking-wider text-slate-400">Discovery Engine Optimization Analytics</h4>
                        <p class="text-xs text-slate-500">Real-time statistics of the Arabic Forex pipeline, tracking keyword yields, source performance, and discovery velocity.</p>
                    </div>
                    <button onclick="fetchDiscoveryStats()" class="px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 transition text-xs font-medium rounded-lg text-white shadow-lg shadow-indigo-500/10">
                        Refresh Statistics
                    </button>
                </div>

                <!-- Metrics Row -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <!-- Overall Arabic Discovery Rate Card -->
                    <div class="glassmorphism p-6 rounded-2xl flex items-center space-x-4 shadow-xl border-l-4 border-l-emerald-500">
                        <div class="h-12 w-12 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center border border-emerald-500/20">
                            <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 002 2h1.5A2.5 2.5 0 0019 9.5V8a2 2 0 00-2-2h-3.17M12 21a9 9 0 100-18 9 9 0 000 18z"></path>
                            </svg>
                        </div>
                        <div>
                            <p class="text-xs text-slate-400 font-medium uppercase tracking-wider">Arabic Discovery Rate</p>
                            <h3 id="stat-arabic-rate" class="text-2xl font-bold mt-1 text-white">-</h3>
                            <p id="stat-arabic-counts" class="text-[10px] text-slate-500 font-medium mt-0.5">-</p>
                        </div>
                    </div>

                    <!-- Daily Discovered Card -->
                    <div class="glassmorphism p-6 rounded-2xl flex items-center space-x-4 shadow-xl border-l-4 border-l-indigo-500">
                        <div class="h-12 w-12 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center border border-indigo-500/20">
                            <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                            </svg>
                        </div>
                        <div>
                            <p class="text-xs text-slate-400 font-medium uppercase tracking-wider">Arabic Channels Found Today</p>
                            <h3 id="stat-discovered-today" class="text-2xl font-bold mt-1 text-white">-</h3>
                            <p id="stat-discovered-total" class="text-[10px] text-slate-500 font-medium mt-0.5">-</p>
                        </div>
                    </div>

                    <!-- Quality Ratio Card -->
                    <div class="glassmorphism p-6 rounded-2xl flex items-center space-x-4 shadow-xl border-l-4 border-l-purple-500">
                        <div class="h-12 w-12 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center border border-purple-500/20">
                            <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"></path>
                            </svg>
                        </div>
                        <div>
                            <p class="text-xs text-slate-400 font-medium uppercase tracking-wider">High Quality Arabic Leads</p>
                            <h3 id="stat-hq-leads" class="text-2xl font-bold mt-1 text-white">-</h3>
                            <p id="stat-hq-ratio" class="text-[10px] text-slate-500 font-medium mt-0.5">-</p>
                        </div>
                    </div>
                </div>

                <!-- Leaderboards Grid -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Top Keywords Yield -->
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Top Arabic Discovery Keywords</h4>
                        </div>
                        <div class="overflow-x-auto p-2">
                            <table class="w-full text-left border-collapse text-xs">
                                <thead>
                                    <tr class="border-b border-slate-900 text-slate-400 font-medium bg-slate-900/20">
                                        <th class="px-4 py-2">Keyword</th>
                                        <th class="px-4 py-2 text-center">Arabic Discovered</th>
                                        <th class="px-4 py-2 text-center">HQ Leads</th>
                                        <th class="px-4 py-2 text-center">Yield Score</th>
                                    </tr>
                                </thead>
                                <tbody id="discovery-keywords-body" class="divide-y divide-slate-900/40 text-slate-300">
                                    <tr>
                                        <td colspan="4" class="px-4 py-4 text-center text-slate-500">No keyword yield recorded yet.</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Top Discovery Sources -->
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Top Arabic Discovery Sources</h4>
                        </div>
                        <div class="overflow-x-auto p-2">
                            <table class="w-full text-left border-collapse text-xs">
                                <thead>
                                    <tr class="border-b border-slate-900 text-slate-400 font-medium bg-slate-900/20">
                                        <th class="px-4 py-2">Source</th>
                                        <th class="px-4 py-2 text-center">Type</th>
                                        <th class="px-4 py-2 text-center">Keyword</th>
                                        <th class="px-4 py-2 text-center">Discovered</th>
                                        <th class="px-4 py-2 text-center">Yield %</th>
                                    </tr>
                                </thead>
                                <tbody id="discovery-sources-body" class="divide-y divide-slate-900/40 text-slate-300">
                                    <tr>
                                        <td colspan="5" class="px-4 py-4 text-center text-slate-500">No discovery sources recorded yet.</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Top Discovery Marketplace Groups -->
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Top Arabic Marketplace Groups</h4>
                        </div>
                        <div class="overflow-x-auto p-2">
                            <table class="w-full text-left border-collapse text-xs">
                                <thead>
                                    <tr class="border-b border-slate-900 text-slate-400 font-medium bg-slate-900/20">
                                        <th class="px-4 py-2">Group Username</th>
                                        <th class="px-4 py-2 text-center">Members</th>
                                        <th class="px-4 py-2 text-center">Marketplace Score</th>
                                        <th class="px-4 py-2 text-center">Arabic Channels Found</th>
                                    </tr>
                                </thead>
                                <tbody id="discovery-marketplace-body" class="divide-y divide-slate-900/40 text-slate-300">
                                    <tr>
                                        <td colspan="4" class="px-4 py-4 text-center text-slate-500">No marketplace groups metrics found.</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Daily Velocity Statistics -->
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden flex flex-col">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Daily Discovery Yield & Velocity (Last 14 Days)</h4>
                        </div>
                        <div class="overflow-x-auto p-2">
                            <table class="w-full text-left border-collapse text-xs">
                                <thead>
                                    <tr class="border-b border-slate-900 text-slate-400 font-medium bg-slate-900/20">
                                        <th class="px-4 py-2">Date</th>
                                        <th class="px-4 py-2 text-center">Discovered</th>
                                        <th class="px-4 py-2 text-center">HQ Leads</th>
                                        <th class="px-4 py-2 text-center">Arabic Rate</th>
                                    </tr>
                                </thead>
                                <tbody id="discovery-daily-body" class="divide-y divide-slate-900/40 text-slate-300">
                                    <tr>
                                        <td colspan="4" class="px-4 py-4 text-center text-slate-500">No daily discovery logs found.</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Lead Quality Tab Section -->
            <div id="tab-quality" class="space-y-8 hidden">
                <div class="glassmorphism p-6 rounded-2xl shadow-xl flex justify-between items-center bg-slate-950/20">
                    <div>
                        <h4 class="text-sm font-semibold uppercase tracking-wider text-slate-400">&#127919; Lead Quality Intelligence Dashboard</h4>
                        <p class="text-xs text-slate-500">Forex Intent Score, Arabic Score, Lead Gate analysis, conversion funnel and category breakdown.</p>
                    </div>
                    <button onclick="fetchQualityStats()" class="px-4 py-1.5 bg-amber-500 hover:bg-amber-600 transition text-xs font-medium rounded-lg text-white shadow-lg shadow-amber-500/10">Refresh Quality Stats</button>
                </div>

                <!-- Funnel Row -->
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div class="glassmorphism p-5 rounded-2xl text-center border-l-4 border-l-blue-500">
                        <p class="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Discovered</p>
                        <h3 id="funnel-discovered" class="text-3xl font-bold text-white">-</h3>
                        <p class="text-[10px] text-slate-500 mt-1">Total Channels Found</p>
                    </div>
                    <div class="glassmorphism p-5 rounded-2xl text-center border-l-4 border-l-indigo-500">
                        <p class="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Validated</p>
                        <h3 id="funnel-validated" class="text-3xl font-bold text-white">-</h3>
                        <p class="text-[10px] text-slate-500 mt-1">Scored by Engine</p>
                    </div>
                    <div class="glassmorphism p-5 rounded-2xl text-center border-l-4 border-l-emerald-500">
                        <p class="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Qualified Leads</p>
                        <h3 id="funnel-leads" class="text-3xl font-bold text-emerald-400">-</h3>
                        <p class="text-[10px] text-slate-500 mt-1">Score&#8805;70 &amp; Forex&#8805;60</p>
                    </div>
                    <div class="glassmorphism p-5 rounded-2xl text-center border-l-4 border-l-amber-500">
                        <p class="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Partners</p>
                        <h3 id="funnel-partners" class="text-3xl font-bold text-amber-400">-</h3>
                        <p class="text-[10px] text-slate-500 mt-1">Contacted</p>
                    </div>
                </div>

                <!-- Score Averages -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="glassmorphism p-5 rounded-2xl flex items-center space-x-4 border-l-4 border-l-purple-500">
                        <div class="h-10 w-10 rounded-lg bg-purple-500/10 flex items-center justify-center text-purple-400 text-lg">&#129504;</div>
                        <div>
                            <p class="text-[10px] text-slate-400 uppercase">Avg Forex Intent Score</p>
                            <h3 id="avg-forex-intent" class="text-xl font-bold text-white">-</h3>
                        </div>
                    </div>
                    <div class="glassmorphism p-5 rounded-2xl flex items-center space-x-4 border-l-4 border-l-green-500">
                        <div class="h-10 w-10 rounded-lg bg-green-500/10 flex items-center justify-center text-green-400 text-lg">&#127760;</div>
                        <div>
                            <p class="text-[10px] text-slate-400 uppercase">Avg Arabic Score</p>
                            <h3 id="avg-arabic" class="text-xl font-bold text-white">-</h3>
                        </div>
                    </div>
                    <div class="glassmorphism p-5 rounded-2xl flex items-center space-x-4 border-l-4 border-l-cyan-500">
                        <div class="h-10 w-10 rounded-lg bg-cyan-500/10 flex items-center justify-center text-cyan-400 text-lg">&#11088;</div>
                        <div>
                            <p class="text-[10px] text-slate-400 uppercase">Avg Lead Score</p>
                            <h3 id="avg-lead-score" class="text-xl font-bold text-white">-</h3>
                        </div>
                    </div>
                </div>

                <!-- Categories + Top Intent -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Forex Category Breakdown -->
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">&#128202; Forex Category Breakdown</h4>
                        </div>
                        <div class="overflow-x-auto p-2">
                            <table class="w-full text-left border-collapse text-xs">
                                <thead>
                                    <tr class="border-b border-slate-900 text-slate-400 font-medium bg-slate-900/20">
                                        <th class="px-4 py-2">Category</th>
                                        <th class="px-4 py-2 text-center">Leads</th>
                                        <th class="px-4 py-2 text-center">Avg Score</th>
                                        <th class="px-4 py-2 text-center">Avg Forex Intent</th>
                                    </tr>
                                </thead>
                                <tbody id="quality-categories-body" class="divide-y divide-slate-900/40 text-slate-300">
                                    <tr><td colspan="4" class="px-4 py-4 text-center text-slate-500">Loading...</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Top Forex Intent Leads -->
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">&#129351; Top Forex Intent Leads</h4>
                        </div>
                        <div class="overflow-x-auto p-2">
                            <table class="w-full text-left border-collapse text-xs">
                                <thead>
                                    <tr class="border-b border-slate-900 text-slate-400 font-medium bg-slate-900/20">
                                        <th class="px-4 py-2">Channel</th>
                                        <th class="px-4 py-2 text-center">Forex Intent</th>
                                        <th class="px-4 py-2 text-center">Arabic</th>
                                        <th class="px-4 py-2 text-center">Score</th>
                                        <th class="px-4 py-2 text-center">Category</th>
                                    </tr>
                                </thead>
                                <tbody id="quality-top-intent-body" class="divide-y divide-slate-900/40 text-slate-300">
                                    <tr><td colspan="5" class="px-4 py-4 text-center text-slate-500">Loading...</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Rejections + Blacklist -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div class="glassmorphism p-6 rounded-2xl shadow-xl">
                        <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">&#10060; Rejection Analysis</h4>
                        <div class="space-y-3" id="quality-rejections">
                            <p class="text-slate-500 text-xs">Loading...</p>
                        </div>
                    </div>
                    <div class="glassmorphism rounded-2xl shadow-xl overflow-hidden">
                        <div class="px-6 py-4 border-b border-slate-900 bg-slate-950/20">
                            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">&#128683; Blacklist Reasons</h4>
                        </div>
                        <div class="overflow-x-auto p-2">
                            <table class="w-full text-left border-collapse text-xs">
                                <thead>
                                    <tr class="border-b border-slate-900 text-slate-400 font-medium bg-slate-900/20">
                                        <th class="px-4 py-2">Reason</th>
                                        <th class="px-4 py-2 text-center">Count</th>
                                    </tr>
                                </thead>
                                <tbody id="quality-blacklist-body" class="divide-y divide-slate-900/40 text-slate-300">
                                    <tr><td colspan="2" class="px-4 py-4 text-center text-slate-500">Loading...</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

        </main>

        <footer class="w-full py-6 text-center border-t border-slate-950 bg-slate-950 text-xs text-slate-500 font-medium">
            &copy; 2026 LeadHunter Inc. All Rights Reserved. Stealth AI CRM Platform.
        </footer>

        <script>
            // Tabs switching
            function switchTab(tabId) {
                const leadsTab = document.getElementById('tab-leads');
                const campaignsTab = document.getElementById('tab-campaigns');
                const graphTab = document.getElementById('tab-graph');
                const leaderboardsTab = document.getElementById('tab-leaderboards');
                const groupMetricsTab = document.getElementById('tab-group-metrics');
                const discoveryTab = document.getElementById('tab-discovery');
                const qualityTab = document.getElementById('tab-quality');
                const leadsBtn = document.getElementById('tab-leads-btn');
                const campaignsBtn = document.getElementById('tab-campaigns-btn');
                const graphBtn = document.getElementById('tab-graph-btn');
                const leaderboardsBtn = document.getElementById('tab-leaderboards-btn');
                const groupMetricsBtn = document.getElementById('tab-group-metrics-btn');
                const discoveryBtn = document.getElementById('tab-discovery-btn');
                const qualityBtn = document.getElementById('tab-quality-btn');

                [leadsTab, campaignsTab, graphTab, leaderboardsTab, groupMetricsTab, discoveryTab, qualityTab].forEach(t => t && t.classList.add('hidden'));
                const inactiveClass = "px-4 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition";
                const activeClass = "px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-500 text-white transition";
                [leadsBtn, campaignsBtn, graphBtn, leaderboardsBtn, groupMetricsBtn, discoveryBtn, qualityBtn].forEach(b => b && (b.className = inactiveClass));

                if (tabId === 'leads') {
                    leadsTab.classList.remove('hidden');
                    leadsBtn.className = "px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-500 text-white transition";
                    fetchLeads();
                } else if (tabId === 'campaigns') {
                    campaignsTab.classList.remove('hidden');
                    campaignsBtn.className = activeClass;
                    fetchCampaigns();
                } else if (tabId === 'graph') {
                    graphTab.classList.remove('hidden');
                    graphBtn.className = "px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-500 text-white transition";
                    fetchGraphStats();
                    initNetworkGraph();
                } else if (tabId === 'leaderboards') {
                    leaderboardsTab.classList.remove('hidden');
                    leaderboardsBtn.className = "px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-500 text-white transition";
                    fetchLeaderboards();
                } else if (tabId === 'group-metrics') {
                    groupMetricsTab.classList.remove('hidden');
                    groupMetricsBtn.className = "px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-500 text-white transition";
                    fetchGroupMetrics();
                } else if (tabId === 'discovery') {
                    discoveryTab.classList.remove('hidden');
                    discoveryBtn.className = activeClass;
                    fetchDiscoveryStats();
                } else if (tabId === 'quality') {
                    qualityTab.classList.remove('hidden');
                    qualityBtn.className = activeClass;
                    fetchQualityStats();
                }
            }

            // Elements
            const minScoreInput = document.getElementById('min-score');
            const scoreVal = document.getElementById('score-val');
            const hasVipCheckbox = document.getElementById('has-vip');
            const hasAcMgmtCheckbox = document.getElementById('has-ac-mgmt');
            const arabicOnlyCheckbox = document.getElementById('arabic-only');
            const hasWebsiteCheckbox = document.getElementById('has-website');
            const hasWhatsappCheckbox = document.getElementById('has-whatsapp');
            const leadsBody = document.getElementById('leads-body');
            
            const statLeads = document.getElementById('stat-leads');
            const statBlacklist = document.getElementById('stat-blacklist');
            const statPosts = document.getElementById('stat-posts');

            // Event Listeners
            minScoreInput.addEventListener('input', (e) => {
                scoreVal.innerText = e.target.value;
                fetchLeads();
            });
            hasVipCheckbox.addEventListener('change', fetchLeads);
            hasAcMgmtCheckbox.addEventListener('change', fetchLeads);
            arabicOnlyCheckbox.addEventListener('change', fetchLeads);
            hasWebsiteCheckbox.addEventListener('change', fetchLeads);
            hasWhatsappCheckbox.addEventListener('change', fetchLeads);

            // Fetch Data
            function fetchLeads() {
                const minScore = minScoreInput.value;
                const hasVip = hasVipCheckbox.checked;
                const hasAcMgmt = hasAcMgmtCheckbox.checked;
                const arabicOnly = arabicOnlyCheckbox.checked;
                const hasWebsite = hasWebsiteCheckbox.checked;
                const hasWhatsapp = hasWhatsappCheckbox.checked;

                let url = `/api/leads?minScore=${minScore}`;
                if (hasVip) url += `&hasVip=true`;
                if (hasAcMgmt) url += `&hasAcMgmt=true`;
                if (arabicOnly) url += `&arabicOnly=true`;
                if (hasWebsite) url += `&hasWebsite=true`;
                if (hasWhatsapp) url += `&hasWhatsapp=true`;

                leadsBody.innerHTML = `
                    <tr>
                        <td colspan="13" class="px-6 py-8 text-center text-slate-500">Querying databases...</td>
                    </tr>
                `;

                fetch(url)
                    .then(res => res.json())
                    .then(data => {
                        if (!data.success) {
                            leadsBody.innerHTML = `
                                <tr>
                                    <td colspan="13" class="px-6 py-8 text-center text-rose-500 font-medium">Error: ${data.error}</td>
                                </tr>
                            `;
                            return;
                        }

                        // Populate Stats
                        statLeads.innerText = data.stats.total_leads;
                        statBlacklist.innerText = data.stats.blacklist_count;
                        statPosts.innerText = data.stats.posts_count;

                        if (data.leads.length === 0) {
                            leadsBody.innerHTML = `
                                <tr>
                                    <td colspan="13" class="px-6 py-8 text-center text-slate-500">No leads found matching current filters.</td>
                                </tr>
                            `;
                            return;
                        }

                        // Populate Table
                        leadsBody.innerHTML = "";
                        data.leads.forEach(lead => {
                            const vipBadge = lead.vip 
                                ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">VIP</span>' 
                                : '<span class="text-slate-600">-</span>';
                            
                            const subBadge = lead.subscription 
                                ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20">Active</span>' 
                                : '<span class="text-slate-600">-</span>';
                            
                            const acBadge = lead.account_management 
                                ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-pink-500/10 text-pink-400 border border-pink-500/20">Yes</span>' 
                                : '<span class="text-slate-600">-</span>';
                                
                            const copyBadge = lead.copy_trading 
                                ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">Yes</span>' 
                                : '<span class="text-slate-600">-</span>';

                            let scoreClass = "text-slate-400";
                            if (lead.lead_score >= 75) scoreClass = "text-emerald-400 font-bold";
                            else if (lead.lead_score >= 50) scoreClass = "text-indigo-400 font-semibold";
                            else if (lead.lead_score >= 25) scoreClass = "text-amber-400";

                            let tierClass = "bg-slate-900 text-slate-400 border-slate-800";
                            if (lead.tier === "Tier_A") tierClass = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
                            else if (lead.tier === "Tier_B") tierClass = "bg-indigo-500/10 text-indigo-400 border-indigo-500/20";
                            else if (lead.tier === "Tier_C") tierClass = "bg-amber-500/10 text-amber-400 border-amber-500/20";
                            else if (lead.tier === "Tier_D") tierClass = "bg-rose-500/10 text-rose-400 border-rose-500/20";

                            const websiteLink = lead.website 
                                ? `<a href="${lead.website}" target="_blank" class="text-indigo-400 hover:text-indigo-300 underline font-medium truncate max-w-[140px] block">${lead.website.replace(/^https?:\/\/(www\.)?/, '')}</a>` 
                                : '<span class="text-slate-600">None</span>';

                            const whatsappLink = lead.whatsapp 
                                ? `<a href="https://wa.me/${lead.whatsapp.replace('+', '')}" target="_blank" class="text-emerald-400 hover:text-emerald-300 font-medium">${lead.whatsapp}</a>` 
                                : '<span class="text-slate-600">None</span>';

                            const contactLink = lead.contact_username 
                                ? `<a href="https://t.me/${lead.contact_username}" target="_blank" class="text-indigo-400 hover:text-indigo-300 font-medium">@${lead.contact_username}</a>` 
                                : '<span class="text-slate-600">None</span>';

                            let activityStr = "Unknown";
                            if (lead.last_activity) {
                                const actDate = new Date(lead.last_activity);
                                activityStr = actDate.toLocaleDateString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
                            }

                            const langBadge = lead.language === "Arabic"
                                ? `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Arabic (${lead.arabic_ratio}%)</span>`
                                : `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-400 border border-slate-800">Other (${lead.arabic_ratio || 0}%)</span>`;

                            const row = `
                                <tr class="hover:bg-slate-900/20 transition duration-150">
                                    <td class="px-6 py-4 text-center">
                                        <input type="checkbox" name="lead-select" value="${lead.id}" onchange="updateSelectedCount()" class="h-4 w-4 bg-slate-900 border-slate-700 rounded text-indigo-600 accent-indigo-500 cursor-pointer">
                                    </td>
                                    <td class="px-6 py-4 font-semibold text-slate-100">
                                        <a href="https://t.me/${lead.channel_username}" target="_blank" class="hover:underline text-indigo-300 flex items-center">
                                            @${lead.channel_username}
                                            <svg class="h-3 w-3 ml-1 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>
                                        </a>
                                    </td>
                                    <td class="px-6 py-4 font-medium">${lead.member_count.toLocaleString()}</td>
                                    <td class="px-6 py-4 text-center font-semibold ${scoreClass}">${lead.lead_score}</td>
                                    <td class="px-6 py-4 text-center">
                                        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${tierClass}">${lead.tier.replace('_', ' ')}</span>
                                    </td>
                                    <td class="px-6 py-4 text-center">${langBadge}</td>
                                    <td class="px-6 py-4 text-center">${vipBadge}</td>
                                    <td class="px-6 py-4 text-center">${subBadge}</td>
                                    <td class="px-6 py-4 text-center">${acBadge}</td>
                                    <td class="px-6 py-4 text-center">${copyBadge}</td>
                                    <td class="px-6 py-4 truncate">${websiteLink}</td>
                                    <td class="px-6 py-4">${whatsappLink}</td>
                                    <td class="px-6 py-4">${contactLink}</td>
                                    <td class="px-6 py-4 text-slate-400 font-medium">${activityStr}</td>
                                </tr>
                            `;
                            leadsBody.insertAdjacentHTML('beforeend', row);
                        });
                        // Reset Select All
                        document.getElementById('select-all-leads').checked = false;
                        updateSelectedCount();
                    });
            }

            // Toggle select all leads
            function toggleSelectAll(master) {
                const checkboxes = document.getElementsByName('lead-select');
                checkboxes.forEach(cb => cb.checked = master.checked);
                updateSelectedCount();
            }

            // Update selected channels counter
            function updateSelectedCount() {
                const checkboxes = document.getElementsByName('lead-select');
                const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
                document.getElementById('selected-count-msg').innerText = `${checkedCount} channel(s) selected`;
            }

            // Fire POST start campaign request
            function startCampaign() {
                const messageText = document.getElementById('campaign-message').value.trim();
                const mediaPath = document.getElementById('campaign-media').value.trim();
                const checkboxes = document.getElementsByName('lead-select');
                const selectedIds = Array.from(checkboxes).filter(cb => cb.checked).map(cb => cb.value);

                if (!messageText) {
                    alert("Please type a sales outreach message first!");
                    return;
                }
                if (selectedIds.length === 0) {
                    alert("Please select at least one channel from the table below!");
                    return;
                }

                if (!confirm(`Are you sure you want to start this outreach campaign to ${selectedIds.length} channel owners?`)) {
                    return;
                }

                const payload = {
                    message_text: messageText,
                    media_path: mediaPath || null,
                    selected_lead_ids: selectedIds
                };

                fetch('/api/campaigns/start', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        alert(`Campaign dispatched successfully! Queued ${data.queued_leads_count} message dispatches.`);
                        document.getElementById('campaign-message').value = "";
                        document.getElementById('campaign-media').value = "";
                        // Refresh grid to reflect status changes when worker processes them
                        fetchLeads();
                    } else {
                        alert(`Error starting campaign: ${data.error}`);
                    }
                })
                .catch(err => {
                    console.error("Campaign start error:", err);
                    alert("Failed to communicate with API server.");
                });
            }

            // Fetch Graph Stats
            function fetchGraphStats() {
                const listMentioned = document.getElementById('list-mentioned');
                const listConnected = document.getElementById('list-connected');
                const listGrowing = document.getElementById('list-growing');
                const listRelationships = document.getElementById('list-relationships');

                fetch('/api/graph/stats')
                    .then(res => res.json())
                    .then(data => {
                        if (!data.success) {
                            return;
                        }

                        // Most Mentioned
                        listMentioned.innerHTML = "";
                        data.most_mentioned.forEach((item, idx) => {
                            listMentioned.insertAdjacentHTML('beforeend', `
                                <li class="flex justify-between items-center p-2 rounded bg-slate-900/40 border border-slate-900/60">
                                    <span class="font-medium text-slate-200">#${idx+1} @${item.channel_username}</span>
                                    <span class="px-2 py-0.5 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-full font-semibold">${item.mention_count} ads</span>
                                </li>
                            `);
                        });

                        // Most Connected
                        listConnected.innerHTML = "";
                        data.most_connected.forEach((item, idx) => {
                            listConnected.insertAdjacentHTML('beforeend', `
                                <li class="flex justify-between items-center p-2 rounded bg-slate-900/40 border border-slate-900/60">
                                    <span class="font-medium text-slate-200">#${idx+1} @${item.channel_username}</span>
                                    <span class="px-2 py-0.5 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded-full font-semibold">${item.connection_count} deg</span>
                                </li>
                            `);
                        });

                        // Fastest Growing
                        listGrowing.innerHTML = "";
                        data.fastest_growing.forEach((item, idx) => {
                            listGrowing.insertAdjacentHTML('beforeend', `
                                <li class="flex justify-between items-center p-2 rounded bg-slate-900/40 border border-slate-900/60">
                                    <span class="font-medium text-slate-200">#${idx+1} @${item.channel_username}</span>
                                    <span class="px-2 py-0.5 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-full font-semibold">+${item.new_discoveries_count} new</span>
                                </li>
                            `);
                        });

                        // Active Discovery Relationships
                        listRelationships.innerHTML = "";
                        if (data.top_networks.length === 0) {
                            listRelationships.innerHTML = '<div class="text-slate-500 text-xs col-span-2 text-center py-4">No crawl connections recorded yet. Run crawling validator loops to populate.</div>';
                        }
                        data.top_networks.forEach(item => {
                            listRelationships.insertAdjacentHTML('beforeend', `
                                <div class="flex justify-between items-center p-3 rounded-xl bg-slate-900/40 border border-slate-900/60 text-xs">
                                    <div class="flex items-center space-x-2">
                                        <span class="text-slate-300 font-semibold">@${item.source}</span>
                                        <svg class="h-3.5 w-3.5 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg>
                                        <span class="text-indigo-300 font-semibold">@${item.target}</span>
                                    </div>
                                    <span class="text-[10px] uppercase font-bold text-slate-500 tracking-wider">${item.discovery_method.replace('_', ' ')}</span>
                                </div>
                            `);
                        });
                    });
            }

            // Interactive force-directed network graph code
            let graphAnimationId = null;
            function initNetworkGraph() {
                if (graphAnimationId) {
                    cancelAnimationFrame(graphAnimationId);
                }

                const canvas = document.getElementById('network-canvas');
                const ctx = canvas.getContext('2d');
                const tooltip = document.getElementById('graph-tooltip');
                
                // Adjust size for retina displays
                const width = canvas.parentElement.clientWidth;
                const height = canvas.parentElement.clientHeight;
                canvas.width = width;
                canvas.height = height;

                fetch('/api/graph/network')
                    .then(res => res.json())
                    .then(data => {
                        if (!data.success || data.nodes.length === 0) {
                            ctx.fillStyle = '#64748b';
                            ctx.font = '14px Outfit';
                            ctx.textAlign = 'center';
                            ctx.fillText("Insufficient graph data. Run validators to generate discovery nodes.", width / 2, height / 2);
                            return;
                        }

                        // Map database nodes and edges to layout objects
                        const nodes = data.nodes.map(n => ({
                            id: n.id,
                            label: n.channel_username,
                            score: n.lead_score,
                            tier: n.tier,
                            x: Math.random() * width,
                            y: Math.random() * height,
                            vx: 0,
                            vy: 0,
                            radius: 8 + (n.lead_score / 15)
                        }));

                        const edges = data.edges.map(e => {
                            const sourceNode = nodes.find(n => n.id === e.source);
                            const targetNode = nodes.find(n => n.id === e.target);
                            return { source: sourceNode, target: targetNode, type: e.discovery_method };
                        }).filter(e => e.source && e.target);

                        let draggedNode = null;
                        let hoveredNode = null;

                        // Physics parameters
                        const kRepulsion = 1200;  // Repelling force coefficient
                        const kAttraction = 0.05; // Link spring stiffness
                        const gravity = 0.02;     // Pull to center
                        const friction = 0.9;     // Velocity damping

                        // Mouse coordinates
                        let mouseX = 0;
                        let mouseY = 0;

                        // Canvas events
                        canvas.addEventListener('mousedown', (e) => {
                            const rect = canvas.getBoundingClientRect();
                            const x = e.clientX - rect.left;
                            const y = e.clientY - rect.top;
                            
                            // Find clicked node
                            draggedNode = nodes.find(n => {
                                const dx = n.x - x;
                                const dy = n.y - y;
                                return Math.sqrt(dx*dx + dy*dy) < n.radius + 10;
                            });
                        });

                        canvas.addEventListener('mousemove', (e) => {
                            const rect = canvas.getBoundingClientRect();
                            mouseX = e.clientX - rect.left;
                            mouseY = e.clientY - rect.top;

                            if (draggedNode) {
                                draggedNode.x = mouseX;
                                draggedNode.y = mouseY;
                                draggedNode.vx = 0;
                                draggedNode.vy = 0;
                            }

                            // Hover check
                            hoveredNode = nodes.find(n => {
                                const dx = n.x - mouseX;
                                const dy = n.y - mouseY;
                                return Math.sqrt(dx*dx + dy*dy) < n.radius + 10;
                            });

                            if (hoveredNode) {
                                tooltip.style.opacity = 1;
                                tooltip.style.left = `${e.clientX - rect.left + 20}px`;
                                tooltip.style.top = `${e.clientY - rect.top - 20}px`;
                                tooltip.innerHTML = `
                                    <div class="font-bold text-white mb-1">@${hoveredNode.label}</div>
                                    <div>Score: <span class="font-semibold text-indigo-400">${hoveredNode.score}</span></div>
                                    <div>Tier: <span class="font-semibold text-purple-400">${hoveredNode.tier}</span></div>
                                `;
                            } else {
                                tooltip.style.opacity = 0;
                            }
                        });

                        canvas.addEventListener('mouseup', () => {
                            draggedNode = null;
                        });

                        // Loop tick
                        function tick() {
                            // 1. Calculate repulsion forces (every node pairs)
                            for (let i = 0; i < nodes.length; i++) {
                                for (let j = i + 1; j < nodes.length; j++) {
                                    const n1 = nodes[i];
                                    const n2 = nodes[j];
                                    const dx = n2.x - n1.x;
                                    const dy = n2.y - n1.y;
                                    const dist = Math.sqrt(dx*dx + dy*dy) || 1;
                                    
                                    // Coulomb repelling force
                                    const force = kRepulsion / (dist * dist);
                                    const fx = (dx / dist) * force;
                                    const fy = (dy / dist) * force;

                                    if (n1 !== draggedNode) {
                                        n1.vx -= fx;
                                        n1.vy -= fy;
                                    }
                                    if (n2 !== draggedNode) {
                                        n2.vx += fx;
                                        n2.vy += fy;
                                    }
                                }
                            }

                            // 2. Calculate attraction forces (Hooke spring on edges)
                            edges.forEach(edge => {
                                const n1 = edge.source;
                                const n2 = edge.target;
                                const dx = n2.x - n1.x;
                                const dy = n2.y - n1.y;
                                const dist = Math.sqrt(dx*dx + dy*dy) || 1;

                                const force = (dist - 100) * kAttraction;
                                const fx = (dx / dist) * force;
                                const fy = (dy / dist) * force;

                                if (n1 !== draggedNode) {
                                    n1.vx += fx;
                                    n1.vy += fy;
                                }
                                if (n2 !== draggedNode) {
                                    n2.vx -= fx;
                                    n2.vy -= fy;
                                }
                            });

                            // 3. Central gravity and update position
                            nodes.forEach(n => {
                                if (n !== draggedNode) {
                                    const dx = width / 2 - n.x;
                                    const dy = height / 2 - n.y;
                                    n.vx += dx * gravity;
                                    n.vy += dy * gravity;

                                    // Apply friction
                                    n.vx *= friction;
                                    n.vy *= friction;

                                    n.x += n.vx;
                                    n.y += n.vy;

                                    // Bounds limits
                                    n.x = Math.max(n.radius, Math.min(width - n.radius, n.x));
                                    n.y = Math.max(n.radius, Math.min(height - n.radius, n.y));
                                }
                            });

                            // 4. Render Canvas
                            ctx.clearRect(0, 0, width, height);

                            // Draw Edges
                            ctx.strokeStyle = 'rgba(99, 102, 241, 0.15)';
                            ctx.lineWidth = 1.5;
                            edges.forEach(e => {
                                ctx.beginPath();
                                ctx.moveTo(e.source.x, e.source.y);
                                ctx.lineTo(e.target.x, e.target.y);
                                ctx.stroke();
                            });

                            // Draw Nodes
                            nodes.forEach(n => {
                                const isHovered = (n === hoveredNode);
                                
                                // Draw glow if hovered or high score
                                if (isHovered || n.score >= 70) {
                                    ctx.shadowBlur = 15;
                                    ctx.shadowColor = n.score >= 70 ? 'rgba(16, 185, 129, 0.4)' : 'rgba(99, 102, 241, 0.4)';
                                } else {
                                    ctx.shadowBlur = 0;
                                }

                                // Decide color
                                let fillStyle = '#64748b'; // Slate (Default)
                                if (n.tier === "Tier_A") fillStyle = '#10b981'; // Emerald (Tier_A)
                                else if (n.tier === "Tier_B") fillStyle = '#6366f1'; // Indigo (Tier_B)
                                else if (n.tier === "Tier_C") fillStyle = '#f59e0b'; // Amber (Tier_C)
                                else if (n.tier === "Tier_D") fillStyle = '#ef4444'; // Red (Tier_D)

                                ctx.fillStyle = fillStyle;
                                ctx.beginPath();
                                ctx.arc(n.x, n.y, n.radius, 0, 2 * Math.PI);
                                ctx.fill();

                                // Draw ring border
                                ctx.shadowBlur = 0; // reset shadow
                                ctx.strokeStyle = isHovered ? '#ffffff' : 'rgba(255,255,255,0.15)';
                                ctx.lineWidth = isHovered ? 2 : 1;
                                ctx.stroke();

                                // Text label
                                if (isHovered || nodes.length < 20 || n.score >= 70) {
                                    ctx.fillStyle = isHovered ? '#ffffff' : '#94a3b8';
                                    ctx.font = isHovered ? 'bold 11px Outfit' : '10px Outfit';
                                    ctx.textAlign = 'center';
                                    ctx.fillText(`@${n.label}`, n.x, n.y - n.radius - 6);
                                }
                            });

                            graphAnimationId = requestAnimationFrame(tick);
                        }

                        tick();
                    })
                    .catch(err => {
                        ctx.fillStyle = '#ef4444';
                        ctx.font = '14px Outfit';
                        ctx.textAlign = 'center';
                        ctx.fillText(`Error connecting to network API: ${err.message}`, width / 2, height / 2);
                    });
            }

            // Fetch Leaderboards
            function fetchLeaderboards() {
                const endpoints = [
                    { id: 'list-vip-sellers', key: 'top_vip', metric: 'score' },
                    { id: 'list-ac-managers', key: 'top_ac_mgmt', metric: 'score' },
                    { id: 'list-copy-trading', key: 'top_copy', metric: 'score' },
                    { id: 'list-funded-providers', key: 'top_funded', metric: 'score' },
                    { id: 'list-most-connected', key: 'most_connected', metric: 'connections' },
                    { id: 'list-most-advertised', key: 'most_advertised', metric: 'ads' },
                    { id: 'list-highest-score', key: 'highest_score', metric: 'score' },
                    { id: 'list-fastest-growing', key: 'fastest_growing', metric: 'growth' },
                    { id: 'list-highest-marketplace', key: 'highest_marketplace', metric: 'marketplace' }
                ];

                endpoints.forEach(ep => {
                    const el = document.getElementById(ep.id);
                    if (el) {
                        el.innerHTML = '<li class="text-center text-slate-500 py-4">Querying database...</li>';
                    }
                });

                fetch('/api/leaderboards')
                    .then(res => res.json())
                    .then(data => {
                        if (!data.success) {
                            endpoints.forEach(ep => {
                                const el = document.getElementById(ep.id);
                                if (el) {
                                    el.innerHTML = `<li class="text-center text-rose-500 py-4">Error loading data</li>`;
                                }
                            });
                            return;
                        }

                        endpoints.forEach(ep => {
                            const el = document.getElementById(ep.id);
                            if (!el) return;
                            el.innerHTML = "";

                            const items = data[ep.key] || [];
                            if (items.length === 0) {
                                el.innerHTML = '<li class="text-center text-slate-500 py-4">No data available</li>';
                                return;
                            }

                            items.forEach((item, idx) => {
                                let badgeHtml = "";
                                if (ep.metric === 'score') {
                                    let scoreClass = "bg-slate-800 text-slate-400";
                                    if (item.lead_score >= 75) scoreClass = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
                                    else if (item.lead_score >= 50) scoreClass = "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
                                    else if (item.lead_score >= 25) scoreClass = "bg-amber-500/10 text-amber-400 border border-amber-500/20";
                                    
                                    badgeHtml = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold ${scoreClass}">Score: ${item.lead_score}</span>`;
                                } else if (ep.metric === 'connections') {
                                    badgeHtml = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">${item.connection_count} connected</span>`;
                                } else if (ep.metric === 'ads') {
                                    badgeHtml = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-pink-500/10 text-pink-400 border border-pink-500/20">${item.ad_count} ads</span>`;
                                } else if (ep.metric === 'growth') {
                                    badgeHtml = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">+${item.growth_count} grow</span>`;
                                } else if (ep.metric === 'marketplace') {
                                    badgeHtml = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">Market: ${item.marketplace_score}</span>`;
                                }

                                el.insertAdjacentHTML('beforeend', `
                                    <li class="flex justify-between items-center p-2 rounded bg-slate-900/40 border border-slate-900/60 hover:bg-slate-900/80 transition duration-150">
                                        <div class="flex items-center space-x-2 min-w-0">
                                            <span class="font-bold text-slate-500">#${idx+1}</span>
                                            <a href="https://t.me/${item.channel_username}" target="_blank" class="font-semibold text-indigo-300 hover:text-indigo-200 hover:underline truncate">
                                                @${item.channel_username}
                                            </a>
                                        </div>
                                        <div class="flex items-center space-x-2 shrink-0">
                                            ${badgeHtml}
                                        </div>
                                    </li>
                                `);
                            });
                        });
                    })
                    .catch(err => {
                        endpoints.forEach(ep => {
                            const el = document.getElementById(ep.id);
                            if (el) {
                                el.innerHTML = `<li class="text-center text-rose-500 py-4">Error: ${err.message}</li>`;
                            }
                        });
                    });
            }

            // Fetch Group Metrics
            function fetchGroupMetrics() {
                const body = document.getElementById('group-metrics-body');
                if (!body) return;
                
                body.innerHTML = `
                    <tr>
                        <td colspan="7" class="px-6 py-8 text-center text-slate-500">Querying database...</td>
                    </tr>
                `;
                
                fetch('/api/group_metrics')
                    .then(res => res.json())
                    .then(data => {
                        if (!data.success) {
                            body.innerHTML = `
                                <tr>
                                    <td colspan="7" class="px-6 py-8 text-center text-rose-500 font-medium">Error: ${data.error}</td>
                                </tr>
                            `;
                            return;
                        }
                        
                        if (data.metrics.length === 0) {
                            body.innerHTML = `
                                <tr>
                                    <td colspan="7" class="px-6 py-8 text-center text-slate-500">No marketplace groups metrics found. Run radar loops to generate.</td>
                                </tr>
                            `;
                            return;
                        }
                        
                        body.innerHTML = "";
                        data.metrics.forEach(row => {
                            let scoreClass = "text-slate-400";
                            if (row.marketplace_score >= 75) scoreClass = "text-emerald-400 font-bold";
                            else if (row.marketplace_score >= 50) scoreClass = "text-indigo-400 font-semibold";
                            else if (row.marketplace_score >= 25) scoreClass = "text-amber-400";
                            
                            let dateStr = "Just now";
                            if (row.last_scan) {
                                const d = new Date(row.last_scan);
                                dateStr = d.toLocaleDateString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
                            }
                            
                            const groupLink = row.group_username.startsWith('group_')
                                ? `<span class="text-slate-400">${row.group_username}</span>`
                                : `<a href="https://t.me/${row.group_username}" target="_blank" class="hover:underline text-indigo-300 font-medium flex items-center">
                                    @${row.group_username}
                                    <svg class="h-3 w-3 ml-1 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>
                                   </a>`;
                                   
                            const membersCount = row.member_count ? row.member_count.toLocaleString() : "0";
                                   
                            const html = `
                                <tr class="hover:bg-slate-900/20 transition duration-150">
                                    <td class="px-6 py-4 font-semibold text-slate-100">${groupLink}</td>
                                    <td class="px-6 py-4 text-center font-medium">${membersCount}</td>
                                    <td class="px-6 py-4 text-center font-bold ${scoreClass}">${row.marketplace_score}%</td>
                                    <td class="px-6 py-4 text-center font-medium">${row.mentions_count}</td>
                                    <td class="px-6 py-4 text-center font-medium">${row.telegram_links_count}</td>
                                    <td class="px-6 py-4 text-center font-medium">${row.advertisements_count}</td>
                                    <td class="px-6 py-4 text-center text-slate-400">${dateStr}</td>
                                </tr>
                            `;
                            body.insertAdjacentHTML('beforeend', html);
                        });
                    })
                    .catch(err => {
                        body.innerHTML = `
                            <tr>
                                <td colspan="7" class="px-6 py-8 text-center text-rose-500 font-medium">Error connecting to database API: ${err.message}</td>
                            </tr>
                        `;
                    });
            }

            function fetchDiscoveryStats() {
                fetch('/api/discovery_stats')
                    .then(res => res.json())
                    .then(data => {
                        if (!data.success) {
                            return;
                        }

                        // 1. Update stats cards
                        const rateStats = data.arabic_rate_stats || { total: 0, arabic_count: 0, overall_rate: 0 };
                        document.getElementById('stat-arabic-rate').innerText = `${rateStats.overall_rate}%`;
                        document.getElementById('stat-arabic-counts').innerText = `${rateStats.arabic_count} of ${rateStats.total} total channels`;

                        // Discovered today vs total
                        let todayDiscovered = 0;
                        if (data.discovered_per_day && data.discovered_per_day.length > 0) {
                            const todayStr = new Date().toISOString().split('T')[0];
                            const todayItem = data.discovered_per_day.find(item => item.date === todayStr);
                            if (todayItem) {
                                todayDiscovered = todayItem.count;
                            } else {
                                todayDiscovered = data.discovered_per_day[0].count; // Fallback to latest day
                            }
                        }
                        document.getElementById('stat-discovered-today').innerText = todayDiscovered;
                        document.getElementById('stat-discovered-total').innerText = `Across ${data.discovered_per_day.length} active logging days`;

                        // High Quality stats
                        let totalHQ = 0;
                        data.top_sources.forEach(item => {
                            totalHQ += item.high_quality_leads;
                        });
                        document.getElementById('stat-hq-leads').innerText = totalHQ;
                        const hqPercent = rateStats.total > 0 ? Math.round(totalHQ * 100 / rateStats.total) : 0;
                        document.getElementById('stat-hq-ratio').innerText = `${hqPercent}% of total verified leads`;

                        // 2. Populate Keywords table
                        const keywordsBody = document.getElementById('discovery-keywords-body');
                        keywordsBody.innerHTML = "";
                        if (data.top_keywords.length === 0) {
                            keywordsBody.innerHTML = `<tr><td colspan="4" class="px-4 py-4 text-center text-slate-500">No keyword yields recorded.</td></tr>`;
                        } else {
                            data.top_keywords.forEach(item => {
                                keywordsBody.insertAdjacentHTML('beforeend', `
                                    <tr class="hover:bg-slate-900/20 transition duration-150">
                                        <td class="px-4 py-2.5 font-semibold text-indigo-300 font-mono">${item.keyword}</td>
                                        <td class="px-4 py-2.5 text-center font-medium">${item.discovered_channels}</td>
                                        <td class="px-4 py-2.5 text-center font-medium text-purple-400">${item.high_quality_leads}</td>
                                        <td class="px-4 py-2.5 text-center font-bold text-emerald-400">${item.quality_score}%</td>
                                    </tr>
                                `);
                            });
                        }

                        // 3. Populate Sources table
                        const sourcesBody = document.getElementById('discovery-sources-body');
                        sourcesBody.innerHTML = "";
                        if (data.top_sources.length === 0) {
                            sourcesBody.innerHTML = `<tr><td colspan="5" class="px-4 py-4 text-center text-slate-500">No sources tracked.</td></tr>`;
                        } else {
                            data.top_sources.forEach(item => {
                                const typeBadge = item.source_type === 'keyword' 
                                    ? '<span class="px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">Keyword</span>'
                                    : item.source_type === 'group'
                                        ? '<span class="px-1.5 py-0.5 rounded bg-pink-500/10 text-pink-400 border border-pink-500/20">Group</span>'
                                        : '<span class="px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">Channel</span>';
                                
                                const displayName = item.source_type === 'keyword' 
                                    ? `<span class="font-semibold text-slate-200 font-mono">${item.source_name}</span>`
                                    : `<a href="https://t.me/${item.source_name}" target="_blank" class="hover:underline text-indigo-300 font-semibold">@${item.source_name}</a>`;
                                
                                sourcesBody.insertAdjacentHTML('beforeend', `
                                    <tr class="hover:bg-slate-900/20 transition duration-150">
                                        <td class="px-4 py-2.5 font-semibold text-slate-100">${displayName}</td>
                                        <td class="px-4 py-2.5 text-center">${typeBadge}</td>
                                        <td class="px-4 py-2.5 text-center font-medium text-slate-400 font-mono">${item.keyword || '-'}</td>
                                        <td class="px-4 py-2.5 text-center font-medium">${item.discovered_channels}</td>
                                        <td class="px-4 py-2.5 text-center font-bold text-emerald-400">${item.quality_score}%</td>
                                    </tr>
                                `);
                            });
                        }

                        // 4. Populate Marketplace Groups table
                        const mktBody = document.getElementById('discovery-marketplace-body');
                        mktBody.innerHTML = "";
                        if (data.top_marketplace_groups.length === 0) {
                            mktBody.innerHTML = `<tr><td colspan="4" class="px-4 py-4 text-center text-slate-500">No marketplace groups.</td></tr>`;
                        } else {
                            data.top_marketplace_groups.forEach(item => {
                                const groupLink = item.group_username.startsWith('group_')
                                    ? `<span class="text-slate-400">${item.group_username}</span>`
                                    : `<a href="https://t.me/${item.group_username}" target="_blank" class="hover:underline text-indigo-300 font-semibold">@${item.group_username}</a>`;
                                
                                let scoreClass = "text-slate-400";
                                if (item.marketplace_score >= 75) scoreClass = "text-emerald-400 font-bold";
                                else if (item.marketplace_score >= 50) scoreClass = "text-indigo-400 font-semibold";
                                else if (item.marketplace_score >= 25) scoreClass = "text-amber-400";

                                mktBody.insertAdjacentHTML('beforeend', `
                                    <tr class="hover:bg-slate-900/20 transition duration-150">
                                        <td class="px-4 py-2.5 font-semibold text-slate-100">${groupLink}</td>
                                        <td class="px-4 py-2.5 text-center font-medium">${item.member_count ? item.member_count.toLocaleString() : '0'}</td>
                                        <td class="px-4 py-2.5 text-center font-bold ${scoreClass}">${item.marketplace_score}%</td>
                                        <td class="px-4 py-2.5 text-center font-medium">${item.advertisements_count}</td>
                                    </tr>
                                `);
                            });
                        }

                        // 5. Populate Daily Velocity table
                        const dailyBody = document.getElementById('discovery-daily-body');
                        dailyBody.innerHTML = "";
                        if (data.discovered_per_day.length === 0) {
                            dailyBody.innerHTML = `<tr><td colspan="4" class="px-4 py-4 text-center text-slate-500">No daily logs.</td></tr>`;
                        } else {
                            const dateMap = {};
                            data.discovered_per_day.forEach(item => {
                                dateMap[item.date] = { date: item.date, discovered: item.count, hq: 0, rate: 0 };
                            });
                            data.hq_leads_per_day.forEach(item => {
                                if (dateMap[item.date]) {
                                    dateMap[item.date].hq = item.count;
                                }
                            });
                            data.arabic_rate_per_day.forEach(item => {
                                if (dateMap[item.date]) {
                                    dateMap[item.date].rate = item.rate;
                                }
                            });

                            const sortedDates = Object.keys(dateMap).sort().reverse();
                            sortedDates.forEach(dStr => {
                                const item = dateMap[dStr];
                                const dateObj = new Date(item.date);
                                const formattedDate = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });

                                dailyBody.insertAdjacentHTML('beforeend', `
                                    <tr class="hover:bg-slate-900/20 transition duration-150">
                                        <td class="px-4 py-2.5 font-semibold text-slate-300">${formattedDate}</td>
                                        <td class="px-4 py-2.5 text-center font-medium">${item.discovered}</td>
                                        <td class="px-4 py-2.5 text-center font-medium text-purple-400">${item.hq}</td>
                                        <td class="px-4 py-2.5 text-center font-bold text-emerald-400">${item.rate}%</td>
                                    </tr>
                                `);
                            });
                        }
                    });
            }

            function fetchQualityStats() {
                fetch('/api/quality_stats')
                    .then(r => r.json())
                    .then(data => {
                        if (!data.success) return;

                        // Funnel
                        const f = data.funnel || {};
                        document.getElementById('funnel-discovered').textContent = f.total_discovered ?? '-';
                        document.getElementById('funnel-validated').textContent = f.total_validated ?? '-';
                        document.getElementById('funnel-leads').textContent = f.qualified_leads ?? '-';
                        document.getElementById('funnel-partners').textContent = f.partners ?? '-';

                        // Score averages
                        const sd = data.score_dist || {};
                        document.getElementById('avg-forex-intent').textContent = sd.avg_forex_intent != null ? sd.avg_forex_intent + '/100' : '-';
                        document.getElementById('avg-arabic').textContent = sd.avg_arabic_score != null ? sd.avg_arabic_score + '/100' : '-';
                        document.getElementById('avg-lead-score').textContent = sd.avg_lead_score != null ? sd.avg_lead_score + '/100' : '-';

                        // Categories
                        const catBody = document.getElementById('quality-categories-body');
                        const catColors = {gold_signals:'text-yellow-400', forex_signals:'text-blue-400', vip_services:'text-purple-400', account_management:'text-emerald-400', copy_trading:'text-cyan-400', funded_accounts:'text-orange-400', trading_education:'text-pink-400', unknown:'text-slate-400'};
                        catBody.innerHTML = (data.categories && data.categories.length > 0)
                            ? data.categories.map(c => `<tr class="hover:bg-slate-900/30"><td class="px-4 py-2 font-medium ${catColors[c.category]||'text-slate-300'}">${c.category.replace(/_/g,' ').toUpperCase()}</td><td class="px-4 py-2 text-center">${c.count}</td><td class="px-4 py-2 text-center">${c.avg_score??'-'}</td><td class="px-4 py-2 text-center">${c.avg_forex_intent??'-'}</td></tr>`).join('')
                            : '<tr><td colspan="4" class="px-4 py-4 text-center text-slate-500">No qualified leads yet. Check back after discovery runs.</td></tr>';

                        // Top Forex Intent leads
                        const intentBody = document.getElementById('quality-top-intent-body');
                        intentBody.innerHTML = (data.top_forex_intent && data.top_forex_intent.length > 0)
                            ? data.top_forex_intent.map(l => `<tr class="hover:bg-slate-900/30"><td class="px-4 py-2 font-medium text-indigo-300"><a href="https://t.me/${l.channel_username}" target="_blank">@${l.channel_username}</a></td><td class="px-4 py-2 text-center font-bold text-purple-400">${l.forex_intent_score}</td><td class="px-4 py-2 text-center">${l.arabic_score}</td><td class="px-4 py-2 text-center font-bold text-emerald-400">${l.lead_score}</td><td class="px-4 py-2 text-center text-xs">${(l.forex_category||'unknown').replace(/_/g,' ')}</td></tr>`).join('')
                            : '<tr><td colspan="5" class="px-4 py-4 text-center text-slate-500">No leads passed the gate yet.</td></tr>';

                        // Rejections
                        const r = data.rejections || {};
                        document.getElementById('quality-rejections').innerHTML = `
                            <div class="flex justify-between items-center p-3 bg-slate-900/40 rounded-xl">
                                <span class="text-slate-300">Total Rejected</span>
                                <span class="font-bold text-rose-400">${r.total_rejected??0}</span>
                            </div>
                            <div class="flex justify-between items-center p-3 bg-slate-900/40 rounded-xl">
                                <span class="text-slate-300">Low Arabic Score (&lt;50)</span>
                                <span class="font-bold text-orange-400">${r.rejected_low_arabic??0}</span>
                            </div>
                            <div class="flex justify-between items-center p-3 bg-slate-900/40 rounded-xl">
                                <span class="text-slate-300">Below Lead Gate (Score&lt;70 or Forex&lt;60)</span>
                                <span class="font-bold text-yellow-400">${r.rejected_low_score??0}</span>
                            </div>`;

                        // Blacklist
                        const blBody = document.getElementById('quality-blacklist-body');
                        blBody.innerHTML = (data.blacklist_reasons && data.blacklist_reasons.length > 0)
                            ? data.blacklist_reasons.map(b => `<tr class="hover:bg-slate-900/30"><td class="px-4 py-2 text-slate-300">${b.reason}</td><td class="px-4 py-2 text-center font-bold text-rose-400">${b.count}</td></tr>`).join('')
                            : '<tr><td colspan="2" class="px-4 py-4 text-center text-slate-500">No blacklisted channels yet.</td></tr>';
                    })
                    .catch(e => console.error('Quality stats error:', e));
            }

            // Fetch campaigns history and granular dispatch logs
            function fetchCampaigns() {
                const campaignsBody = document.getElementById('campaigns-body');
                const logsBody = document.getElementById('campaign-logs-body');

                campaignsBody.innerHTML = `<tr><td colspan="11" class="px-6 py-8 text-center text-slate-500">Querying database campaigns...</td></tr>`;
                logsBody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-slate-500">Querying database logs...</td></tr>`;

                fetch('/api/campaigns')
                    .then(res => res.json())
                    .then(data => {
                        if (!data.success) {
                            campaignsBody.innerHTML = `<tr><td colspan="11" class="px-6 py-8 text-center text-rose-500">Error: ${data.error}</td></tr>`;
                            logsBody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-rose-500">Error: ${data.error}</td></tr>`;
                            return;
                        }

                        // 1. Populate Campaigns Summary Table
                        campaignsBody.innerHTML = "";
                        if (data.campaigns.length === 0) {
                            campaignsBody.innerHTML = `<tr><td colspan="11" class="px-6 py-8 text-center text-slate-500">No campaigns launched yet. Use the selector above to schedule one.</td></tr>`;
                        } else {
                            data.campaigns.forEach(c => {
                                const createdDate = new Date(c.created_at);
                                const dateStr = createdDate.toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
                                const preview = c.message_text.length > 60 ? c.message_text.substring(0, 60) + "..." : c.message_text;
                                
                                let statusClass = "text-slate-400";
                                if (c.status === "active") statusClass = "text-indigo-400 font-semibold animate-pulse";
                                else if (c.status === "completed") statusClass = "text-emerald-400 font-semibold";

                                const followupBadge = c.followup_enabled ? `<span class="text-cyan-400 font-bold">${c.followup_sent_count || 0}</span> <span class="text-slate-500 text-[10px]">(${c.followup_ready_count || 0} ready)</span>` : `<span class="text-slate-600">Off</span>`;
                                const repliedBadge = `<span class="text-teal-400 font-bold">${c.replied_count || 0}</span>`;
                                
                                const p0Count = c.p0_pending_count || 0;
                                const p1Count = c.p1_pending_count || 0;
                                const p2Count = c.p2_pending_count || 0;
                                const p3Count = c.p3_pending_count || 0;
                                const priorityPills = `<div class="flex items-center justify-center gap-1 mt-1 text-[9px]">
                                    <span class="px-1 py-0.5 rounded bg-rose-500/20 text-rose-300 font-bold" title="P0 Immediate">P0:${p0Count}</span>
                                    <span class="px-1 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold" title="P1 Very High">P1:${p1Count}</span>
                                    <span class="px-1 py-0.5 rounded bg-blue-500/20 text-blue-300" title="P2 High">P2:${p2Count}</span>
                                    <span class="px-1 py-0.5 rounded bg-slate-700 text-slate-300" title="P3 Normal">P3:${p3Count}</span>
                                </div>`;
                                const rerankBtn = `<button onclick="rerankCampaign('${c.id}')" class="mt-1 block mx-auto text-[10px] text-indigo-400 hover:text-indigo-300 underline font-medium">Re-rank</button>`;

                                campaignsBody.insertAdjacentHTML('beforeend', `
                                    <tr class="hover:bg-slate-900/20 transition duration-150">
                                        <td class="px-5 py-4 font-mono font-semibold text-indigo-400 text-xs">${c.id.substring(0, 8)}...</td>
                                        <td class="px-5 py-4 text-slate-400">${dateStr}</td>
                                        <td class="px-5 py-4 font-medium text-slate-200" title="${c.message_text}">${preview}</td>
                                        <td class="px-4 py-4 text-center font-bold text-slate-300">${c.total_recipients}</td>
                                        <td class="px-4 py-4 text-center font-bold text-emerald-400">${c.sent_count}</td>
                                        <td class="px-4 py-4 text-center">${followupBadge}</td>
                                        <td class="px-4 py-4 text-center">${repliedBadge}</td>
                                        <td class="px-4 py-4 text-center font-bold text-rose-400">${c.failed_count}</td>
                                        <td class="px-4 py-4 text-center font-bold text-purple-400">${c.skipped_count || 0}</td>
                                        <td class="px-4 py-4 text-center font-bold text-amber-400">${c.pending_count} ${priorityPills} ${rerankBtn}</td>
                                        <td class="px-4 py-4 text-center ${statusClass}">${c.status.toUpperCase()}</td>
                                    </tr>
                                `);
                            });
                        }

                        // 2. Populate Granular Message Logs Table
                        logsBody.innerHTML = "";
                        if (data.logs.length === 0) {
                            logsBody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-slate-500">No logs generated yet. Wait for Campaign worker to pull messages.</td></tr>`;
                        } else {
                            data.logs.forEach(l => {
                                const preview = l.message_text.length > 50 ? l.message_text.substring(0, 50) + "..." : l.message_text;
                                
                                let sentStr = "Pending";
                                if (l.sent_at) {
                                    const sentDate = new Date(l.sent_at);
                                    sentStr = sentDate.toLocaleTimeString(undefined, {hour: '2-digit', minute: '2-digit', second: '2-digit'});
                                }

                                const prio = l.priority || 'P3';
                                const score = l.priority_score !== undefined ? l.priority_score : 25;
                                let prioBadge = `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-300">${prio} (${score})</span>`;
                                if (prio === 'P0') prioBadge = `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/30 text-rose-300 border border-rose-500/40">${prio} (${score})</span>`;
                                else if (prio === 'P1') prioBadge = `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">${prio} (${score})</span>`;
                                else if (prio === 'P2') prioBadge = `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">${prio} (${score})</span>`;

                                let statusBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">Pending</span>`;
                                if (l.status === 'sent') {
                                    statusBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Sent</span>`;
                                } else if (l.status === 'failed') {
                                    statusBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">Failed</span>`;
                                } else if (l.status === 'skipped') {
                                    statusBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">Skipped (Dup)</span>`;
                                }

                                const detailText = l.error_message 
                                    ? `<span class="text-rose-400 font-medium font-mono text-[10px] break-all">${l.error_message}</span>` 
                                    : `<span class="text-slate-500">Delivered successfully</span>`;

                                logsBody.insertAdjacentHTML('beforeend', `
                                    <tr class="hover:bg-slate-900/20 transition duration-150">
                                        <td class="px-6 py-4 font-semibold text-slate-300">
                                            <div class="flex items-center gap-2">
                                                ${prioBadge}
                                                <a href="https://t.me/${l.channel_username}" target="_blank" class="hover:underline">@${l.channel_username}</a>
                                            </div>
                                        </td>
                                        <td class="px-6 py-4 font-medium text-slate-400">
                                            ${l.contact_username ? `<a href="https://t.me/${l.contact_username}" target="_blank" class="text-indigo-400 hover:underline">@${l.contact_username}</a>` : '<span class="text-slate-600">No Outward Contact</span>'}
                                        </td>
                                        <td class="px-6 py-4 text-slate-300" title="${l.message_text}">${preview}</td>
                                        <td class="px-6 py-4 text-center text-slate-400">${sentStr}</td>
                                        <td class="px-6 py-4 text-center">${statusBadge}</td>
                                        <td class="px-6 py-4 max-w-[200px] truncate">${detailText}</td>
                                    </tr>
                                `);
                            });
                        }
                    })
                    .catch(e => {
                        console.error('Fetch campaigns logs error:', e);
                        campaignsBody.innerHTML = `<tr><td colspan="8" class="px-6 py-8 text-center text-rose-500">API connection error</td></tr>`;
                        logsBody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-rose-500">API connection error</td></tr>`;
                    });
            }

            window.rerankCampaign = function(campaignId) {
                if (!confirm('Re-rank pending recipients based on commercial fit and service need inference?')) return;
                fetch('/api/campaigns/' + campaignId + '/rerank', { method: 'POST' })
                    .then(r => r.json())
                    .then(d => {
                        if (d.success) {
                            alert('Successfully re-ranked ' + d.reranked_count + ' recipients!');
                            fetchCampaigns();
                        } else {
                            alert('Re-ranking error: ' + d.error);
                        }
                    })
                    .catch(e => alert('Network error: ' + e));
            };

            // Initial Load
            fetchLeads();
            fetchLeaderboards();
            fetchGroupMetrics();
            fetchDiscoveryStats();
            fetchCampaigns();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

# ── Outreach Engine API Endpoints ─────────────────────────────────────────

@app.get("/api/outreach/health", dependencies=[Depends(verify_dashboard_auth)])
async def get_outreach_health():
    """Get account health states and outreach status."""
    try:
        redis_conn = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'),
                                 port=int(os.getenv('REDIS_PORT', 6379)),
                                 db=int(os.getenv('REDIS_DB', 0)),
                                 decode_responses=True)
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get account health from DB
        cur.execute("SELECT * FROM account_health ORDER BY health_score DESC")
        accounts = cur.fetchall()
        
        # Get global outreach status
        outreach_enabled = is_outreach_enabled(redis_conn)
        
        conn.close()
        return {
            "outreach_enabled": outreach_enabled,
            "accounts": [dict(a) for a in accounts] if accounts else [],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/outreach/metrics", dependencies=[Depends(verify_dashboard_auth)])
async def get_outreach_metrics():
    """Get outreach pipeline metrics snapshot."""
    try:
        redis_conn = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'),
                                 port=int(os.getenv('REDIS_PORT', 6379)),
                                 db=int(os.getenv('REDIS_DB', 0)),
                                 decode_responses=True)
        metrics = OutreachMetrics(redis_conn)
        return metrics.get_dashboard_snapshot()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/outreach/queue", dependencies=[Depends(verify_dashboard_auth)])
async def get_outreach_queue():
    """Get outreach queue depths."""
    try:
        redis_conn = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'),
                                 port=int(os.getenv('REDIS_PORT', 6379)),
                                 db=int(os.getenv('REDIS_DB', 0)),
                                 decode_responses=True)
        depths = {}
        for queue_name in ['outreach:high', 'outreach:normal', 'outreach:low']:
            depths[queue_name] = redis_conn.llen(queue_name) or 0
        depths['total'] = sum(depths.values())
        return depths
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/outreach/emergency/stop", dependencies=[Depends(verify_dashboard_auth)])
async def api_emergency_stop():
    """Trigger emergency outreach stop."""
    try:
        redis_conn = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'),
                                 port=int(os.getenv('REDIS_PORT', 6379)),
                                 db=int(os.getenv('REDIS_DB', 0)),
                                 decode_responses=True)
        emergency_stop(redis_conn)
        return {"success": True, "message": "Outreach emergency stop activated"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/outreach/emergency/resume", dependencies=[Depends(verify_dashboard_auth)])
async def api_emergency_resume():
    """Resume outreach after emergency stop."""
    try:
        redis_conn = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'),
                                 port=int(os.getenv('REDIS_PORT', 6379)),
                                 db=int(os.getenv('REDIS_DB', 0)),
                                 decode_responses=True)
        emergency_resume(redis_conn)
        return {"success": True, "message": "Outreach resumed"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/metrics")
async def get_prometheus_metrics():
    """Prometheus-compatible plain text metrics endpoint."""
    lines = []
    try:
        redis_conn = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 0)),
            decode_responses=True
        )
        
        # 1. Queue Depths
        for q in ['queue:critical', 'queue:high', 'queue:normal', 'queue:low', 'queue:dead_letter', 'outreach:high', 'outreach:normal', 'outreach:low', 'recommendations:queue']:
            depth = redis_conn.llen(q) or 0
            lines.append(f'lead_queue_depth{{queue="{q}"}} {depth}')
        
        # 2. Seen Channels Count
        seen_count = redis_conn.scard('seen_channels') or 0
        lines.append(f'lead_seen_channels_total {seen_count}')

        # 3. Account pool health metrics
        for acc_key in redis_conn.keys("health:*:score"):
            acc_name = acc_key.split(":")[1] if isinstance(acc_key, str) else acc_key.decode().split(":")[1]
            score_val = redis_conn.get(acc_key) or 100
            lines.append(f'lead_account_health_score{{account="{acc_name}"}} {score_val}')
    except Exception as re_err:
        lines.append(f'# redis_metrics_error: {re_err}')

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total leads
        cur.execute("SELECT COUNT(*) as total FROM leads")
        total_leads = cur.fetchone()['total']
        lines.append(f'lead_channels_total {total_leads}')
        
        # Leads by Tier
        cur.execute("SELECT tier, COUNT(*) as count FROM leads GROUP BY tier")
        for row in cur.fetchall():
            tier_name = row['tier'] or 'unclassified'
            lines.append(f'lead_channels_by_tier{{tier="{tier_name}"}} {row["count"]}')
        
        # Total Graph Edges
        cur.execute("SELECT COUNT(*) as total FROM channel_edges")
        total_edges = cur.fetchone()['total']
        lines.append(f'lead_graph_edges_total {total_edges}')
        
        # Total Snapshots
        cur.execute("SELECT COUNT(*) as total FROM channel_snapshots")
        total_snaps = cur.fetchone()['total']
        lines.append(f'lead_snapshots_total {total_snaps}')

        # Crawl Jobs
        cur.execute("SELECT status, COUNT(*) as count FROM crawl_jobs GROUP BY status")
        for row in cur.fetchall():
            lines.append(f'lead_crawl_jobs_total{{status="{row["status"]}"}} {row["count"]}')
        
        conn.close()
    except Exception as db_err:
        lines.append(f'# db_metrics_error: {db_err}')

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.get("/health")
@app.get("/api/health")
async def get_system_health():
    """
    Public system-wide health and readiness probe endpoint (PART V).
    Inspects PostgreSQL, Redis, Queue depths, DLQ, and Account pool status.
    """
    import time
    from fastapi.responses import JSONResponse

    health_data = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "database": {"status": "unknown"},
            "redis": {"status": "unknown"},
            "queues": {},
            "account_pool": {}
        }
    }
    is_healthy = True

    # 1. Database Check
    t0 = time.time()
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        conn.close()
        db_latency_ms = round((time.time() - t0) * 1000, 2)
        health_data["components"]["database"] = {
            "status": "healthy",
            "latency_ms": db_latency_ms
        }
    except Exception as db_e:
        is_healthy = False
        health_data["components"]["database"] = {
            "status": "unhealthy",
            "error": str(db_e)
        }

    # 2. Redis & Queue Check
    t0 = time.time()
    try:
        redis_conn = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 0)),
            decode_responses=True,
            socket_timeout=2.0
        )
        redis_conn.ping()
        redis_latency_ms = round((time.time() - t0) * 1000, 2)
        
        # Check Queues
        queues_checked = {}
        for q in ['queue:critical', 'queue:high', 'queue:normal', 'queue:low', 'queue:dead_letter']:
            queues_checked[q] = redis_conn.llen(q) or 0

        health_data["components"]["redis"] = {
            "status": "healthy",
            "latency_ms": redis_latency_ms
        }
        health_data["components"]["queues"] = queues_checked

        # Check Account Pool
        account_statuses = {}
        for state_key in redis_conn.keys("account:pool:*:state"):
            s_name = state_key.split(":")[2]
            state_val = redis_conn.get(state_key)
            account_statuses[s_name] = state_val
        health_data["components"]["account_pool"] = account_statuses or {"status": "no_active_sessions_tracked"}

    except Exception as redis_e:
        is_healthy = False
        health_data["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(redis_e)
        }

    if not is_healthy:
        health_data["status"] = "unhealthy"
        return JSONResponse(status_code=503, content=health_data)

    # Check for degraded queue backpressure
    dlq_depth = health_data["components"]["queues"].get("queue:dead_letter", 0)
    if dlq_depth > 100:
        health_data["status"] = "degraded"
        health_data["warning"] = f"Dead letter queue contains {dlq_depth} poisoned jobs."

    return JSONResponse(status_code=200, content=health_data)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("dashboard:app", host="0.0.0.0", port=port, log_level="info")
