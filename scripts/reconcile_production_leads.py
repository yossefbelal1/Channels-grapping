"""
scripts/reconcile_production_leads.py — Production Data Reconciliation & Priority Re-Ranking

Executes directly on the VPS against real production PostgreSQL:
1. Evaluates all pending campaign leads using the Commercial Inference Engine.
2. Updates leads table with outreach_priority, commercial_fit_score, likely_services.
3. Synchronizes priority values into campaign_logs.
4. Outputs the REAL Top-50 ranked pending recipients.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.outreach.priority_engine import OutreachPriorityEngine
from app.outreach.constants import OutreachPriority

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reconciliation")


class DbPost:
    def __init__(self, text, date):
        self.text = text or ""
        self.date = date


def main():
    print("=" * 80)
    print("LEADHUNTER PRODUCTION DATA RECONCILIATION & RE-RANKING")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    db_host = os.getenv("DB_HOST", "postgres")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "leadhunter_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASSWORD", "leadhunter_pass")

    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_pass
    )
    conn.autocommit = False

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Fetch active campaign
        cur.execute("SELECT id, message_text, created_at FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1;")
        camp = cur.fetchone()
        if not camp:
            print("ERROR: No active campaign found in database!")
            return
        campaign_id = str(camp['id'])
        print(f"\n[1] Active Campaign: {campaign_id}")
        print(f"    Created: {camp['created_at']}")
        print(f"    Message: {camp['message_text'][:80]}...\n")

        # 2. Fetch all unique leads that are pending in this campaign
        cur.execute("""
            SELECT DISTINCT l.id, l.channel_username, l.description, l.member_count,
                   l.contact_username, COALESCE(l.forex_intent_score, 0) as forex_intent_score,
                   COALESCE(l.lead_score, 0) as lead_score
            FROM campaign_logs cl
            JOIN leads l ON cl.lead_id = l.id
            WHERE cl.campaign_id = %s AND cl.status = 'pending';
        """, (campaign_id,))
        pending_leads = cur.fetchall()
        total_pending = len(pending_leads)
        print(f"[2] Evaluating {total_pending} pending campaign leads...")

        evaluated_count = 0
        tier_counts = {OutreachPriority.P0: 0, OutreachPriority.P1: 0, OutreachPriority.P2: 0, OutreachPriority.P3: 0, OutreachPriority.P4: 0}

        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(days=1)
        seven_days_ago = now - timedelta(days=7)

        for lead in pending_leads:
            lead_id = lead['id']
            ch_user = lead['channel_username'] or ""
            desc = lead['description'] or ""
            subs = lead['member_count'] or 0
            contact = lead['contact_username'] or ""
            forex_score = lead['forex_intent_score'] or 0

            # Fetch recent posts from channel_posts
            cur.execute("""
                SELECT message_text, timestamp
                FROM channel_posts
                WHERE channel_username = %s
                ORDER BY timestamp DESC
                LIMIT 25;
            """, (ch_user,))
            post_rows = cur.fetchall()

            messages = []
            posts_24h = 0
            posts_7d = 0
            for pr in post_rows:
                ptxt = pr['message_text'] or ""
                pts = pr['timestamp']
                if pts and pts.tzinfo is None:
                    pts = pts.replace(tzinfo=timezone.utc)
                if pts:
                    if pts >= one_day_ago:
                        posts_24h += 1
                    if pts >= seven_days_ago:
                        posts_7d += 1
                messages.append(DbPost(ptxt, pts))

            contacts_dict = {"contact_username": contact, "source": "bio_official"} if contact else {}

            # Run Commercial Fit Inference & Priority Evaluation
            eval_res = OutreachPriorityEngine.evaluate_priority(
                title=ch_user,
                description=desc,
                recent_messages=messages,
                contacts_dict=contacts_dict,
                forex_relevance_score=forex_score,
                member_count=subs,
                posts_24h=posts_24h,
                posts_7d=posts_7d
            )

            tier = eval_res['priority']
            score = eval_res['priority_score']
            reason = eval_res['reason']
            comm_fit = eval_res['commercial_fit_score']
            bm_score = eval_res['business_model_score']
            op_score = eval_res['operational_complexity_score']
            likely_services = eval_res['likely_services']
            evidence_json = json.dumps(eval_res['evidence'])
            freshest_date = eval_res.get('freshest_commercial_date')

            tier_counts[tier] = tier_counts.get(tier, 0) + 1

            # Update leads table
            cur.execute("""
                UPDATE leads
                SET outreach_priority = %s,
                    outreach_priority_score = %s,
                    outreach_priority_reason = %s,
                    outreach_priority_updated_at = NOW(),
                    commercial_fit_score = %s,
                    business_model_score = %s,
                    operational_complexity_score = %s,
                    likely_services = %s,
                    commercial_evidence = %s::jsonb,
                    commercial_last_seen = %s
                WHERE id = %s;
            """, (
                tier, score, reason,
                comm_fit, bm_score, op_score,
                likely_services, evidence_json, freshest_date,
                lead_id
            ))
            evaluated_count += 1

        conn.commit()
        print(f"    Evaluated and updated {evaluated_count} leads in database.")
        print(f"    Tier distribution in leads: {tier_counts}\n")

        # 3. Synchronize campaign_logs
        print("[3] Synchronizing priority intelligence into campaign_logs...")
        cur.execute("""
            UPDATE campaign_logs cl
            SET priority = l.outreach_priority,
                priority_score = l.outreach_priority_score,
                priority_reason = l.outreach_priority_reason,
                commercial_fit_score = l.commercial_fit_score,
                likely_services = l.likely_services,
                intent_evidence = l.commercial_evidence
            FROM leads l
            WHERE cl.lead_id = l.id
              AND cl.campaign_id = %s
              AND cl.status = 'pending';
        """, (campaign_id,))
        synced_count = cur.rowcount
        conn.commit()
        print(f"    Synchronized {synced_count} pending campaign_logs rows.\n")

        # 4. Query and print the ACTUAL Real Top 50 Pending Recipients
        print("=" * 80)
        print("REAL PRODUCTION TOP 50 PENDING RECIPIENTS (CLAIM ORDER)")
        print("=" * 80)
        cur.execute("""
            SELECT cl.id as log_id, l.channel_username, l.contact_username, l.member_count,
                   COALESCE(l.outreach_priority, cl.priority, 'P3') as priority,
                   COALESCE(l.outreach_priority_score, cl.priority_score, 25) as priority_score,
                   COALESCE(l.commercial_fit_score, cl.commercial_fit_score, 0) as comm_fit,
                   COALESCE(l.business_model_score, 0) as bm_score,
                   COALESCE(l.likely_services, '{}') as likely_services,
                   SUBSTRING(COALESCE(l.outreach_priority_reason, ''), 1, 90) as reason
            FROM campaign_logs cl
            JOIN campaigns c ON cl.campaign_id = c.id
            JOIN leads l ON cl.lead_id = l.id
            WHERE cl.campaign_id = %s AND cl.status = 'pending'
            ORDER BY
                CASE COALESCE(l.outreach_priority, cl.priority, 'P3')
                    WHEN 'P0' THEN 0
                    WHEN 'P1' THEN 1
                    WHEN 'P2' THEN 2
                    WHEN 'P3' THEN 3
                    WHEN 'P4' THEN 4
                    ELSE 5
                END ASC,
                COALESCE(l.outreach_priority_score, cl.priority_score, 25) DESC,
                COALESCE(l.commercial_last_seen, l.intent_detected_at) DESC NULLS LAST,
                cl.attempt_count ASC,
                c.created_at ASC
            LIMIT 50;
        """, (campaign_id,))
        top50 = cur.fetchall()

        print(f"{'#':<3} | {'Channel':<24} | {'Contact':<20} | {'Subs':<7} | {'Tier':<4} | {'Score':<5} | {'Fit':<4} | {'BM':<4} | {'Services':<24}")
        print("-" * 115)
        for idx, row in enumerate(top50, 1):
            ch = (row['channel_username'] or 'none')[:24]
            cu = (row['contact_username'] or 'none')[:20]
            subs = row['member_count'] or 0
            tier = row['priority']
            score = row['priority_score']
            fit = row['comm_fit']
            bm = row['bm_score']
            svcs = ",".join(row['likely_services'][:2])[:24]
            print(f"{idx:<3} | @{ch:<23} | @{cu:<19} | {subs:<7} | {tier:<4} | {score:<5} | {fit:<4} | {bm:<4} | {svcs:<24}")

        print("\n" + "=" * 80)
        print("CAMPAIGN LOG SUMMARY BY TIER:")
        cur.execute("""
            SELECT COALESCE(priority, 'P3') as tier, count(*) as count
            FROM campaign_logs
            WHERE campaign_id = %s AND status = 'pending'
            GROUP BY priority
            ORDER BY 
                CASE priority
                    WHEN 'P0' THEN 0
                    WHEN 'P1' THEN 1
                    WHEN 'P2' THEN 2
                    WHEN 'P3' THEN 3
                    WHEN 'P4' THEN 4
                    ELSE 5
                END;
        """, (campaign_id,))
        tier_summary = cur.fetchall()
        for ts in tier_summary:
            print(f"    Tier {ts['tier']:<4}: {ts['count']:>5} pending recipients")
        print("=" * 80)

    conn.close()


if __name__ == "__main__":
    main()
