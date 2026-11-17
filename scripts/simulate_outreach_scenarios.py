#!/usr/bin/env python3
"""
scripts/simulate_outreach_scenarios.py

Comprehensive Outreach Simulation Engine:
Audits all 2,836 pending leads in PostgreSQL, evaluates them with the exact production
eligibility & deduplication rules, and runs multi-scenario stochastic simulations.
"""

import os
import sys
import json
import random
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "leadhunter_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "leadhunter_pass")

SYSTEM_KEYWORDS = {
    'addlist', 'everyone', 'share', 'joinchat', 'setlanguage',
    'proxy', 'socks', 'c', 's', 'm', 'i', '4030', 'help', 'support'
}


def main():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Fetch Blacklist
    cur.execute("SELECT lower(entity_username_or_link) as item FROM blacklist;")
    blacklist_set = {row['item'].lstrip('@').strip() for row in cur.fetchall()}

    # 2. Fetch Already Sent Contacts (Across all campaigns)
    cur.execute("""
        SELECT DISTINCT lower(l.contact_username) as contact
        FROM campaign_logs cl
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.status = 'sent' AND l.contact_username IS NOT NULL AND l.contact_username != '';
    """)
    already_sent_contacts = {row['contact'].lstrip('@').strip() for row in cur.fetchall()}

    # 3. Fetch All Pending/Approved Leads in active campaign
    cur.execute("""
        SELECT cl.id as log_id, cl.campaign_id, cl.lead_id, cl.status,
               COALESCE(l.outreach_priority, cl.priority, 'P3') as priority,
               COALESCE(l.outreach_priority_score, cl.priority_score, 25) as priority_score,
               l.contact_username, l.channel_username, l.title, l.status as lead_status,
               l.lead_score, l.commercial_fit_score
        FROM campaign_logs cl
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.status IN ('pending_review', 'approved')
        ORDER BY 
            CASE COALESCE(l.outreach_priority, cl.priority, 'P3')
                WHEN 'P0' THEN 0
                WHEN 'P1' THEN 1
                WHEN 'P2' THEN 2
                WHEN 'P3' THEN 3
                WHEN 'P4' THEN 4
                ELSE 5
            END ASC,
            COALESCE(l.outreach_priority_score, cl.priority_score, 25) DESC;
    """)
    all_pending = cur.fetchall()
    total_count = len(all_pending)

    print("\n" + "=" * 80)
    print(f"📊 LIVE AUDIT: {total_count} PENDING LEADS IN QUEUE")
    print("=" * 80)

    # 4. Rigorous Eligibility & Deduplication Pass (Simulating Exact Production Order)
    seen_contacts_in_batch = set()
    eligible_by_prio = defaultdict(list)
    skipped_by_prio = defaultdict(list)
    skip_reasons_counter = defaultdict(int)

    for row in all_pending:
        prio = row['priority']
        raw_contact = (row['contact_username'] or '').strip()
        clean_contact = raw_contact.lstrip('@').strip().lower()

        # Rule 1: Missing Contact
        if not clean_contact or len(clean_contact) < 3:
            skipped_by_prio[prio].append(row)
            skip_reasons_counter['NO_CONTACT'] += 1
            continue

        # Rule 2: System Keyword
        if clean_contact in SYSTEM_KEYWORDS:
            skipped_by_prio[prio].append(row)
            skip_reasons_counter['SYSTEM_KEYWORD'] += 1
            continue

        # Rule 3: Bot
        if clean_contact.endswith('bot') or clean_contact.endswith('_bot'):
            skipped_by_prio[prio].append(row)
            skip_reasons_counter['IS_BOT'] += 1
            continue

        # Rule 4: Blacklist
        if clean_contact in blacklist_set:
            skipped_by_prio[prio].append(row)
            skip_reasons_counter['BLACKLISTED'] += 1
            continue

        # Rule 5: Rejected Lead Status
        if row['lead_status'] == 'rejected':
            skipped_by_prio[prio].append(row)
            skip_reasons_counter['LEAD_REJECTED'] += 1
            continue

        # Rule 6: Already Contacted in Past Campaigns
        if clean_contact in already_sent_contacts:
            skipped_by_prio[prio].append(row)
            skip_reasons_counter['ALREADY_SENT_PAST'] += 1
            continue

        # Rule 7: Duplicate within Current Queue (Same contact across multiple channels)
        if clean_contact in seen_contacts_in_batch:
            skipped_by_prio[prio].append(row)
            skip_reasons_counter['DUPLICATE_IN_QUEUE'] += 1
            continue

        # Passed all rules -> ELIGIBLE
        seen_contacts_in_batch.add(clean_contact)
        eligible_by_prio[prio].append(row)

    # Breakdown Table
    print(f"\n{'Priority':<10} | {'Total In DB':<12} | {'Eligible (Sendable)':<20} | {'Skipped (Filtered)':<20} | {'Quality Ratio':<15}")
    print("-" * 85)
    
    total_eligible = 0
    total_skipped = 0

    for p in ['P0', 'P1', 'P2', 'P3', 'P4']:
        e_cnt = len(eligible_by_prio[p])
        s_cnt = len(skipped_by_prio[p])
        tot = e_cnt + s_cnt
        if tot == 0:
            continue
        total_eligible += e_cnt
        total_skipped += s_cnt
        ratio = (e_cnt / tot) * 100
        print(f"{p:<10} | {tot:<12} | {e_cnt:<20} | {s_cnt:<20} | {ratio:.1f}%")

    print("-" * 85)
    print(f"{'TOTAL':<10} | {total_count:<12} | {total_eligible:<20} | {total_skipped:<20} | {(total_eligible/total_count)*100:.1f}%\n")

    print("🔎 Filter / Skip Breakdown Reasons across the 2,830 leads:")
    for reason, cnt in sorted(skip_reasons_counter.items(), key=lambda x: x[1], reverse=True):
        print(f"   • {reason:<25}: {cnt:>5} leads")

    # 5. Stochastic Monte Carlo Simulation (1,000 Runs per Scenario)
    print("\n" + "=" * 80)
    print("🎲 STOCHASTIC MONTE CARLO SIMULATION (1,000 RUNS)")
    print("=" * 80)

    # Scenarios Definition
    # Scenario 1: Realistic Baseline (Target: 17.5/day [15-20], Jitter: 75-150s, 1 cooldown/mo)
    # Scenario 2: High Throttle (Target: 20/day, Jitter: 75-120s, 0 cooldown)
    # Scenario 3: Conservative (Target: 14/day [12-16], Jitter: 90-180s, 2 cooldowns/mo)
    # Scenario 4: Multi-Account (2 accounts = 35/day)
    # Scenario 5: Multi-Account (3 accounts = 52.5/day)

    scenarios = [
        {"name": "1. Realistic Baseline (1 الحساب الحالي - معدل آمن 17.5/يوم)", "min_cap": 15, "max_cap": 20, "cooldown_prob": 0.04, "cooldown_days": 1, "accounts": 1},
        {"name": "2. Nominal Maximum (1 حساب - الحد الأقصى الآمن 20/يوم)", "min_cap": 18, "max_cap": 20, "cooldown_prob": 0.01, "cooldown_days": 1, "accounts": 1},
        {"name": "3. Conservative Caution (1 حساب - وضع شديد التحفظ 14/يوم)", "min_cap": 12, "max_cap": 16, "cooldown_prob": 0.08, "cooldown_days": 1.5, "accounts": 1},
        {"name": "4. Dual Accounts (2 حسابات إرسال = 35/يوم)", "min_cap": 30, "max_cap": 40, "cooldown_prob": 0.03, "cooldown_days": 1, "accounts": 2},
        {"name": "5. Trio Accounts (3 حسابات إرسال = 52.5/يوم)", "min_cap": 45, "max_cap": 60, "cooldown_prob": 0.03, "cooldown_days": 1, "accounts": 3},
    ]

    for sc in scenarios:
        print(f"\n▶ {sc['name']}:")
        
        # We simulate the exact queue order: P0 leads, then P1, then P2, then P3, then P4
        target_counts = {
            'P0': len(eligible_by_prio['P0']),
            'P1': len(eligible_by_prio['P1']),
            'P2': len(eligible_by_prio['P2']),
            'P3': len(eligible_by_prio['P3']),
            'TOTAL': total_eligible
        }

        # Run 1000 simulations
        days_to_p0 = []
        days_to_p1 = []
        days_to_p2 = []
        days_to_total = []

        for _ in range(1000):
            current_day = 0
            sent_total = 0
            p0_done_day = None
            p1_done_day = None
            p2_done_day = None
            
            p0_cum = target_counts['P0']
            p1_cum = p0_cum + target_counts['P1']
            p2_cum = p1_cum + target_counts['P2']
            total_target = target_counts['TOTAL']

            while sent_total < total_target:
                current_day += 1
                
                # Check for Telegram transient cooldown / flood wait event
                if random.random() < sc['cooldown_prob']:
                    current_day += sc['cooldown_days']
                    continue

                # Normal day sends
                daily_sends = random.randint(sc['min_cap'], sc['max_cap'])
                sent_total += daily_sends

                if sent_total >= p0_cum and p0_done_day is None:
                    p0_done_day = current_day
                if sent_total >= p1_cum and p1_done_day is None:
                    p1_done_day = current_day
                if sent_total >= p2_cum and p2_done_day is None:
                    p2_done_day = current_day

            days_to_p0.append(p0_done_day or current_day)
            days_to_p1.append(p1_done_day or current_day)
            days_to_p2.append(p2_done_day or current_day)
            days_to_total.append(current_day)

        avg_p0 = sum(days_to_p0) / len(days_to_p0)
        avg_p1 = sum(days_to_p1) / len(days_to_p1)
        avg_p2 = sum(days_to_p2) / len(days_to_p2)
        avg_tot = sum(days_to_total) / len(days_to_total)

        p95_p0 = sorted(days_to_p0)[int(len(days_to_p0) * 0.95)]
        p95_p1 = sorted(days_to_p1)[int(len(days_to_p1) * 0.95)]
        p95_p2 = sorted(days_to_p2)[int(len(days_to_p2) * 0.95)]
        p95_tot = sorted(days_to_total)[int(len(days_to_total) * 0.95)]

        print(f"   • P0 ({target_counts['P0']} عميل)           : متوسط {avg_p0:.1f} يوم  (أقصى حد 95% ثقة: {p95_p0} يوم)")
        print(f"   • P0 + P1 ({target_counts['P0']+target_counts['P1']} عميل)     : متوسط {avg_p1:.1f} يوم  (أقصى حد 95% ثقة: {p95_p1} يوم)")
        print(f"   • P0 + P1 + P2 ({target_counts['P0']+target_counts['P1']+target_counts['P2']} عميل): متوسط {avg_p2:.1f} يوم  (أقصى حد 95% ثقة: {p95_p2} يوم)")
        print(f"   • كامل القائمة ({total_eligible} عميل)    : متوسط {avg_tot:.1f} يوم  (أقصى حد 95% ثقة: {p95_tot} يوم)")

    # 6. Active Sending Time & Resource Jitter Calculation
    print("\n" + "=" * 80)
    print("⏱️ PACING & DAILY TIME EXPENDITURE PER MESSAGE")
    print("=" * 80)
    # Jitter is between 75s and 150s (mean 112.5s)
    mean_jitter = 112.5
    daily_sends = 17.5
    active_sending_seconds = daily_sends * mean_jitter
    active_sending_minutes = active_sending_seconds / 60
    
    print(f" • متوسط الفاصل الزمني بين الرسائل (Jitter): {mean_jitter:.1f} ثانية (~1 دقيقة و 52 ثانية)")
    print(f" • وقت الإرسال الفعلي في اليوم الواحد (Active Time): {active_sending_minutes:.1f} دقيقة فقط من أصل 24 ساعة!")
    print(f" • وقت راحة الحساب اليومي (Resting Time): {24 - (active_sending_minutes/60):.1f} ساعة في اليوم")
    print(" • النتيجة: الحساب يقضي 98% من اليوم في حالة خمول طبيعي تام، مما يجعل السلوك يبدو بشرياً 100% لخوارزميات تيليجرام.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
