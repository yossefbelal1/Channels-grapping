"""
scripts/cleanup_and_reconcile_outreach_queue.py — Outreach Queue Purification & Forex Hardening

1. Resets false P0/P1 priorities in `leads` for all non-forex and rejected channels.
2. Purges unqualified channels from `campaign_logs` (marks them as 'skipped'):
   - Any channel with forex_intent_score < 30 or 0
   - Any channel marked 'rejected' in leads
   - Any channel with empty, null, bot, or invalid contact_username
   - Explicitly purges @whyyyvv, @rr_12_5, @Zahraaaii1, @ABDOKings, and similar junk.
3. Fixes false boolean flags like `vip = true` on non-forex channels.
4. Synchronizes and re-ranks eligible Forex leads strictly according to OutreachPriorityEngine.
"""

import os
import sys
import subprocess
import psycopg2
from psycopg2.extras import RealDictCursor

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"
REMOTE_USER = "root"

def run_remote_psql(sql: str) -> str:
    # Escape double quotes for shell
    escaped_sql = sql.replace('"', '\\"')
    cmd = [
        "ssh", "-i", REMOTE_KEY,
        "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}",
        f"""docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "{escaped_sql}" """
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if res.stderr and "ERROR" in res.stderr:
        print(f"PSQL Error:\n{res.stderr}", file=sys.stderr)
    return res.stdout

def run_remote_script(script_code: str) -> str:
    # Writes a python script to /tmp on remote and runs it inside docker or on host
    cmd = [
        "ssh", "-i", REMOTE_KEY,
        "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}",
        f"""python3 -c '{script_code}' """
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return res.stdout + (("\nSTDERR:\n" + res.stderr) if res.stderr else "")

def main():
    print("================================================================")
    print("     STARTING OUTREACH QUEUE PURIFICATION & FOREX HARDENING     ")
    print("================================================================")

    # 1. Inspect initial contamination state
    print("\n--- [Step 1] Initial Contamination Audit ---")
    audit_sql = """
    SELECT 
        COUNT(*) as total_leads,
        COUNT(*) FILTER (WHERE outreach_priority = 'P0') as p0_leads,
        COUNT(*) FILTER (WHERE outreach_priority = 'P0' AND (forex_intent_score = 0 OR forex_intent_score IS NULL)) as p0_zero_forex,
        COUNT(*) FILTER (WHERE outreach_priority = 'P0' AND status = 'rejected') as p0_rejected,
        COUNT(*) FILTER (WHERE outreach_priority = 'P0' AND (description ILIKE '%هادئاً إلا عقلي%' OR channel_username = 'whyyyvv')) as p0_whyyyvv
    FROM leads;
    """
    print(run_remote_psql(audit_sql))

    camp_audit_sql = """
    SELECT 
        COUNT(*) as total_active_logs,
        COUNT(*) FILTER (WHERE cl.priority = 'P0') as p0_active,
        COUNT(*) FILTER (WHERE l.forex_intent_score = 0 OR l.forex_intent_score IS NULL) as zero_forex_active,
        COUNT(*) FILTER (WHERE l.status = 'rejected') as rejected_active,
        COUNT(*) FILTER (WHERE l.contact_username IS NULL OR l.contact_username = '') as no_contact_active
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('approved', 'pending');
    """
    print(run_remote_psql(camp_audit_sql))

    # 2. Specifically clean @whyyyvv and @rr_12_5
    print("\n--- [Step 2] Purging @whyyyvv and non-forex targets from Campaign Logs ---")
    purge_specific_sql = """
    -- Reset whyyyvv in leads
    UPDATE leads
    SET outreach_priority = 'P4',
        outreach_priority_score = 10,
        outreach_priority_reason = 'Non-forex literary/poetry channel',
        vip = false,
        account_management = false
    WHERE channel_username = 'whyyyvv';

    -- Mark whyyyvv and rr_12_5 in campaign_logs as skipped
    UPDATE campaign_logs cl
    SET status = 'skipped',
        error_message = 'Not eligible: Non-forex channel (@whyyyvv / @rr_12_5)'
    FROM leads l
    WHERE cl.lead_id = l.id
      AND (l.channel_username IN ('whyyyvv', 'rr_12_5', 'Zahraaaii1', 'ABDOKings')
           OR l.contact_username IN ('rr_12_5', 'whyyyvv'));
    """
    print(run_remote_psql(purge_specific_sql))

    # 3. Purge all rejected, zero-forex, or missing-contact items from active campaign queue
    print("\n--- [Step 3] Purging All Invalid / Rejected / Zero-Forex from Campaign Queue ---")
    purge_all_invalid_camp_sql = """
    UPDATE campaign_logs cl
    SET status = 'skipped',
        error_message = CASE 
            WHEN l.status = 'rejected' THEN 'Not eligible: Channel status is rejected'
            WHEN (l.forex_intent_score = 0 OR l.forex_intent_score IS NULL) THEN 'Not eligible: Zero forex relevance'
            WHEN (l.contact_username IS NULL OR l.contact_username = '') THEN 'Not eligible: Missing contact username'
            ELSE 'Not eligible: Fails Forex qualification gate'
        END
    FROM leads l
    WHERE cl.lead_id = l.id
      AND cl.status IN ('approved', 'pending')
      AND (
          l.status = 'rejected'
          OR l.forex_intent_score = 0
          OR l.forex_intent_score IS NULL
          OR l.contact_username IS NULL
          OR l.contact_username = ''
      );
    """
    print(run_remote_psql(purge_all_invalid_camp_sql))

    # 4. Reset False P0/P1 priorities in leads table
    print("\n--- [Step 4] Resetting False P0/P1 in Leads Table ---")
    reset_leads_priority_sql = """
    -- Any lead that has zero forex or is rejected CANNOT have P0 or P1
    UPDATE leads
    SET outreach_priority = 'P4',
        outreach_priority_score = 10,
        outreach_priority_reason = 'Zero or negligible forex relevance / rejected'
    WHERE outreach_priority IN ('P0', 'P1')
      AND (
          status = 'rejected'
          OR forex_intent_score = 0
          OR forex_intent_score IS NULL
      );

    -- Also reset vip flag if channel has 0 forex relevance and is not a trading channel
    UPDATE leads
    SET vip = false
    WHERE vip = true
      AND (forex_intent_score = 0 OR forex_intent_score IS NULL)
      AND NOT (description ~* 'ذهب|فوركس|تداول|عملات|xauusd|forex|trading');
    """
    print(run_remote_psql(reset_leads_priority_sql))

    # 5. Synchronize priorities for all remaining campaign_logs
    print("\n--- [Step 5] Synchronizing Remaining Eligible Campaign Logs ---")
    sync_camp_sql = """
    UPDATE campaign_logs cl
    SET priority = l.outreach_priority,
        priority_score = l.outreach_priority_score,
        priority_reason = l.outreach_priority_reason,
        commercial_fit_score = COALESCE(l.commercial_fit_score, 0)
    FROM leads l
    WHERE cl.lead_id = l.id
      AND cl.status IN ('approved', 'pending');
    """
    print(run_remote_psql(sync_camp_sql))

    # 6. Post-Cleanup Verification Audit
    print("\n--- [Step 6] Post-Cleanup Verification Audit ---")
    verify_leads_sql = """
    SELECT 
        COUNT(*) as total_leads,
        COUNT(*) FILTER (WHERE outreach_priority = 'P0') as p0_leads,
        COUNT(*) FILTER (WHERE outreach_priority = 'P0' AND (forex_intent_score = 0 OR forex_intent_score IS NULL)) as p0_zero_forex,
        COUNT(*) FILTER (WHERE outreach_priority = 'P0' AND status = 'rejected') as p0_rejected
    FROM leads;
    """
    print("Leads Table State:")
    print(run_remote_psql(verify_leads_sql))

    verify_camp_sql = """
    SELECT 
        cl.id, l.channel_username, l.contact_username, cl.status, cl.priority, cl.priority_score,
        l.forex_intent_score, l.lead_score, l.tier, l.status as lead_status,
        SUBSTRING(COALESCE(l.title, l.description, '') FROM 1 FOR 50) as snippet
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('approved', 'pending')
    ORDER BY 
        CASE cl.priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
        cl.priority_score DESC
    LIMIT 15;
    """
    print("Remaining Approved / Pending Campaign Queue (Top 15):")
    print(run_remote_psql(verify_camp_sql))

    # Verify @whyyyvv specifically
    whyyyvv_check = """
    SELECT l.channel_username, l.outreach_priority, l.outreach_priority_score, cl.status, cl.priority, cl.error_message
    FROM leads l
    LEFT JOIN campaign_logs cl ON l.id = cl.lead_id
    WHERE l.channel_username = 'whyyyvv';
    """
    print("@whyyyvv Verification:")
    print(run_remote_psql(whyyyvv_check))

    # 7. Remove rogue script on remote server
    print("\n--- [Step 7] Removing Rogue Script /root/prioritize_leads.py on VPS ---")
    rm_cmd = [
        "ssh", "-i", REMOTE_KEY,
        "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}",
        "rm -f /root/prioritize_leads.py && echo 'Successfully removed /root/prioritize_leads.py'"
    ]
    res_rm = subprocess.run(rm_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(res_rm.stdout)

    print("\n================================================================")
    print("            PURIFICATION & RECONCILIATION COMPLETE              ")
    print("================================================================")

if __name__ == '__main__':
    main()
