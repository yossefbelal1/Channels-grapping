"""
scripts/benchmark_exchange_network.py — Comprehensive Exchange Network Engine Benchmark & Reranking

Executes the complete Exchange Network Intelligence pipeline:
1. Detects Exchange Hubs and Cross-Promotion Clusters in channel_edges
2. Loads sampled posts from channel_posts to detect real historical promotion and exchange evidence
3. Calculates Exchange Affinity, Sweet Spot Size, and Network Value across all leads
4. Re-evaluates and synchronizes Outreach Priority (P0, P1, etc.) for mutual network growth
5. Harvests unvalidated peer channel targets from graph edges into seed_channels
6. Generates the comprehensive 10-Metric Before vs After Quantitative Benchmark Report
"""

import os
import sys
import json
import logging
from datetime import datetime
from collections import defaultdict
from typing import Dict, Any, List

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import get_db_connection
from app.discovery.exchange_analyzer import ExchangeAffinityAnalyzer
from app.graph.exchange_graph_engine import ExchangeGraphEngine
from app.outreach.priority_engine import OutreachPriorityEngine
from app.learning.gold_admin_pattern_profiler import GoldAdminPatternProfiler

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("benchmark")


def run_benchmark():
    conn = get_db_connection()
    cur = conn.cursor()

    print("\n" + "="*80)
    print("🚀 EXECUTING EXCHANGE NETWORK INTELLIGENCE PIPELINE & BENCHMARK")
    print("="*80 + "\n")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 1: Capture Baseline (Before) Metrics
    # ──────────────────────────────────────────────────────────────────────────
    logger.info("Capturing Baseline Metrics (Before)...")
    cur.execute("""
        SELECT 
            COUNT(*) as total_leads,
            COUNT(CASE WHEN status != 'rejected' THEN 1 END) as active_leads,
            COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_leads,
            COUNT(CASE WHEN COALESCE(forex_score, forex_intent_score, 0) >= 30 THEN 1 END) as forex_relevant,
            COUNT(CASE WHEN member_count BETWEEN 1000 AND 35000 THEN 1 END) as small_medium_channels,
            COUNT(CASE WHEN contact_username IS NOT NULL AND contact_username != '' THEN 1 END) as with_contact,
            COUNT(CASE WHEN is_exchange_hub = TRUE THEN 1 END) as exchange_hubs,
            COUNT(CASE WHEN is_exchange_seed = TRUE THEN 1 END) as exchange_seeds,
            COUNT(CASE WHEN exchange_affinity_score >= 30 THEN 1 END) as with_exchange_affinity,
            COUNT(CASE WHEN cluster_id IS NOT NULL THEN 1 END) as in_clusters,
            COUNT(CASE WHEN discovery_method = 'graph' OR discovery_source = 'graph' THEN 1 END) as graph_yield
        FROM leads;
    """)
    before_leads = cur.fetchone()

    cur.execute("""
        SELECT 
            COUNT(*) as total_recipients,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P0' THEN 1 END) as p0_count,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P1' THEN 1 END) as p1_count,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P2' THEN 1 END) as p2_count,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P3' THEN 1 END) as p3_count,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P4' THEN 1 END) as p4_count,
            COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_count,
            COUNT(CASE WHEN status IN ('pending', 'pending_review') THEN 1 END) as pending_review_count
        FROM campaign_logs;
    """)
    before_campaign = cur.fetchone()

    # ──────────────────────────────────────────────────────────────────────────
    # Step 2: Run Active Graph Mining (Hubs & Clusters)
    # ──────────────────────────────────────────────────────────────────────────
    logger.info("Running Graph Engine: Detecting Exchange Hubs & Cross-Promotion Clusters...")
    graph_engine = ExchangeGraphEngine(db_conn=conn)
    hubs = graph_engine.detect_and_tag_exchange_hubs(min_degree=3)
    hub_ids = {h["channel_id"] for h in hubs}
    clusters = graph_engine.detect_cross_promotion_clusters()
    harvested = graph_engine.harvest_unvalidated_graph_targets(limit=200)
    logger.info(f"Detected {len(hubs)} Exchange Hubs, {clusters['clusters_count']} Mutual Clusters, Harvested {harvested} targets.")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 2.5: Load Sampled Messages from channel_posts for Post Analysis
    # ──────────────────────────────────────────────────────────────────────────
    logger.info("Loading sampled posts from channel_posts for post analysis...")
    cur.execute("""
        SELECT channel_username, message_text
        FROM (
            SELECT channel_username, message_text,
                   ROW_NUMBER() OVER (PARTITION BY channel_username ORDER BY timestamp DESC) as rn
            FROM channel_posts
            WHERE message_text IS NOT NULL AND LENGTH(message_text) > 10
        ) sub
        WHERE rn <= 20;
    """)
    post_rows = cur.fetchall() or []
    channel_posts_map = defaultdict(list)
    for pr in post_rows:
        u = (pr["channel_username"] or "").lower().strip()
        txt = pr["message_text"] or ""
        if u and txt:
            channel_posts_map[u].append(txt)
    logger.info(f"Loaded posts for {len(channel_posts_map)} distinct channels.")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 3: Run Exchange Affinity & Prioritization across all active leads
    # ──────────────────────────────────────────────────────────────────────────
    logger.info("Computing Exchange Affinity & Sweet Spot Prioritization across leads...")
    cur.execute("""
        SELECT l.id, l.channel_username, l.title, l.description, l.member_count,
               l.contact_username, COALESCE(l.forex_score, l.forex_intent_score, 0) as forex_score,
               l.posts_24h, l.posts_7d,
               COALESCE(ce_in.in_cnt, 0) as in_degree,
               COALESCE(ce_out.out_cnt, 0) as out_degree,
               COALESCE(ce_rel.rel_types, ARRAY[]::varchar[]) as rel_types
        FROM leads l
        LEFT JOIN (
            SELECT target_channel_id, COUNT(*) as in_cnt 
            FROM channel_edges GROUP BY target_channel_id
        ) ce_in ON l.id = ce_in.target_channel_id
        LEFT JOIN (
            SELECT source_channel_id, COUNT(*) as out_cnt 
            FROM channel_edges GROUP BY source_channel_id
        ) ce_out ON l.id = ce_out.source_channel_id
        LEFT JOIN (
            SELECT source_channel_id, ARRAY_AGG(DISTINCT relation_type) as rel_types 
            FROM channel_edges GROUP BY source_channel_id
        ) ce_rel ON l.id = ce_rel.source_channel_id
        WHERE l.status != 'rejected';
    """)
    leads_to_process = cur.fetchall() or []
    logger.info(f"Processing {len(leads_to_process)} leads...")

    batch_updates = []
    p0_count = 0
    p1_count = 0
    seeds_count = 0

    for row in leads_to_process:
        lid = str(row["id"])
        uname = (row["channel_username"] or "").lower().strip()
        title = row["title"] or ""
        desc = row["description"] or ""
        mcount = row["member_count"] or 0
        cuser = row["contact_username"]
        fscore = row["forex_score"] or 0
        p24 = row["posts_24h"] or 0
        p7d = row["posts_7d"] or 0
        in_deg = row["in_degree"] or 0
        out_deg = row["out_degree"] or 0
        rels = set(row["rel_types"] or [])

        # Get sampled posts if available
        msgs = channel_posts_map.get(uname, [])

        # Evaluate Exchange Network Priority
        eval_res = OutreachPriorityEngine.evaluate_priority(
            title=title,
            description=desc,
            recent_messages=msgs,
            contacts_dict={"contact_username": cuser, "source": "bio_admin"} if cuser else {},
            forex_relevance_score=fscore,
            member_count=mcount,
            posts_24h=p24,
            posts_7d=p7d,
            in_degree=in_deg,
            out_degree=out_deg,
            relation_types=rels
        )

        p_tier = eval_res["priority"]
        p_score = eval_res["priority_score"]
        p_reason = eval_res["reason"]
        ex_aff = eval_res["exchange_affinity_score"]
        net_val = eval_res["network_value_score"]
        grow_op = eval_res["growth_openness_score"]
        is_seed = eval_res["is_exchange_seed"]
        is_hub = eval_res["is_exchange_hub"] or (lid in hub_ids)
        ex_ev = json.dumps(eval_res["exchange_evidence"])

        if p_tier == "P0":
            p0_count += 1
        elif p_tier == "P1":
            p1_count += 1
        if is_seed:
            seeds_count += 1

        batch_updates.append((
            p_tier, p_score, p_reason, ex_aff, net_val, grow_op, is_seed, is_hub, ex_ev, lid
        ))

    # Batch update leads
    logger.info("Persisting evaluation results into PostgreSQL...")
    cur.executemany("""
        UPDATE leads
        SET outreach_priority = %s,
            outreach_priority_score = %s,
            outreach_priority_reason = %s,
            outreach_priority_updated_at = NOW(),
            exchange_affinity_score = %s,
            network_value_score = %s,
            growth_openness_score = %s,
            is_exchange_seed = %s,
            is_exchange_hub = %s,
            exchange_evidence = %s::jsonb
        WHERE id = %s;
    """, batch_updates)
    conn.commit()

    # ──────────────────────────────────────────────────────────────────────────
    # Step 4: Synchronize Campaign Logs (Active Campaign)
    # ──────────────────────────────────────────────────────────────────────────
    logger.info("Synchronizing Campaign Pipeline Priorities...")
    cur.execute("SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1;")
    camp_row = cur.fetchone()
    if camp_row:
        camp_id = str(camp_row["id"])
        cur.execute("""
            UPDATE campaign_logs cl
            SET priority = l.outreach_priority,
                priority_score = l.outreach_priority_score,
                priority_reason = l.outreach_priority_reason,
                intent_evidence = l.exchange_evidence
            FROM leads l
            WHERE cl.lead_id = l.id
              AND cl.campaign_id = %s
              AND cl.status IN ('pending', 'pending_review', 'approved');
        """, (camp_id,))
        conn.commit()
        logger.info(f"Synchronized campaign {camp_id} logs with latest network priority.")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 5: Capture Final (After) Metrics
    # ──────────────────────────────────────────────────────────────────────────
    logger.info("Capturing After Metrics...")
    cur.execute("""
        SELECT 
            COUNT(*) as total_leads,
            COUNT(CASE WHEN status != 'rejected' THEN 1 END) as active_leads,
            COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_leads,
            COUNT(CASE WHEN COALESCE(forex_score, forex_intent_score, 0) >= 30 THEN 1 END) as forex_relevant,
            COUNT(CASE WHEN member_count BETWEEN 1000 AND 35000 THEN 1 END) as small_medium_channels,
            COUNT(CASE WHEN contact_username IS NOT NULL AND contact_username != '' THEN 1 END) as with_contact,
            COUNT(CASE WHEN is_exchange_hub = TRUE THEN 1 END) as exchange_hubs,
            COUNT(CASE WHEN is_exchange_seed = TRUE THEN 1 END) as exchange_seeds,
            COUNT(CASE WHEN exchange_affinity_score >= 30 THEN 1 END) as with_exchange_affinity,
            COUNT(CASE WHEN cluster_id IS NOT NULL THEN 1 END) as in_clusters,
            COUNT(CASE WHEN discovery_method = 'graph' OR discovery_source = 'graph' THEN 1 END) as graph_yield
        FROM leads;
    """)
    after_leads = cur.fetchone()

    cur.execute("""
        SELECT 
            COUNT(*) as total_recipients,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P0' THEN 1 END) as p0_count,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P1' THEN 1 END) as p1_count,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P2' THEN 1 END) as p2_count,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P3' THEN 1 END) as p3_count,
            COUNT(CASE WHEN COALESCE(priority, 'P3') = 'P4' THEN 1 END) as p4_count,
            COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_count,
            COUNT(CASE WHEN status IN ('pending', 'pending_review') THEN 1 END) as pending_review_count
        FROM campaign_logs;
    """)
    after_campaign = cur.fetchone()

    # ──────────────────────────────────────────────────────────────────────────
    # Step 6: Print Comprehensive 10-Metric Report
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("📊 10-METRIC BEFORE VS AFTER QUANTITATIVE BENCHMARK REPORT")
    print("="*80)
    
    report_rows = [
        ("1. Total Forex/Trading Channels Discovered", before_leads["forex_relevant"], after_leads["forex_relevant"]),
        ("2. Small & Medium Channels (1k-35k members)", before_leads["small_medium_channels"], after_leads["small_medium_channels"]),
        ("3. Active Leads Qualified vs Rejected Noise", f"{before_leads['active_leads']} active / {before_leads['rejected_leads']} rej", f"{after_leads['active_leads']} active / {after_leads['rejected_leads']} rej"),
        ("4. Channels with Verified Exchange Evidence", before_leads["with_exchange_affinity"], after_leads["with_exchange_affinity"]),
        ("5. Channels in Promotion/Mutual Clusters", before_leads["in_clusters"], after_leads["in_clusters"]),
        ("6. Active Exchange Hubs Discovered", before_leads["exchange_hubs"], after_leads["exchange_hubs"]),
        ("7. Unique Graph Expansion Yield (Channels)", before_leads["graph_yield"], after_leads["graph_yield"]),
        ("8. Exchange Network Seeds (is_exchange_seed)", before_leads["exchange_seeds"], after_leads["exchange_seeds"]),
        ("9. Channels with Verified Human Contact", before_leads["with_contact"], after_leads["with_contact"]),
        ("10. Campaign P0 Leads (Prime Exchange Partners)", before_campaign["p0_count"], after_campaign["p0_count"]),
        ("11. Campaign P1 Leads (High-Value Exchange Nodes)", before_campaign["p1_count"], after_campaign["p1_count"]),
    ]

    print(f"{'Metric':<48} | {'Before':<15} | {'After':<15}")
    print("-" * 84)
    for name, b_val, a_val in report_rows:
        print(f"{name:<48} | {str(b_val):<15} | {str(a_val):<15}")
    print("-" * 84)
    print(f"Total Campaign Approved Leads Ready for Outreach: {after_campaign['approved_count']}")
    print(f"Total Campaign Pending Leads Awaiting Review:     {after_campaign['pending_review_count']}")
    print("="*80 + "\n")

    conn.close()


if __name__ == "__main__":
    run_benchmark()
