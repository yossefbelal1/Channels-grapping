from app.core.db import get_db_connection

conn = get_db_connection()
with conn.cursor() as cur:
    cur.execute("""
        UPDATE leads
        SET title = %s,
            contact_username = 'KSA_Trader11',
            admin_username = 'KSA_Trader11',
            forex_intent_score = 90,
            lead_score = 80,
            tier = 'Tier_B',
            entity_type = 'channel',
            status = 'new',
            discovered_at = NOW(),
            last_scan = NOW()
        WHERE channel_username ILIKE '%%ABOSALEM2003%%';
    """, ('سعودي للتداول 🇸🇦',))

    cur.execute("""
        UPDATE leads
        SET entity_type = 'user',
            outreach_priority_reason = 'user_account'
        WHERE channel_username ILIKE '%%ksa_trader11%%';
    """)

    cur.execute("""
        INSERT INTO campaign_logs (id, campaign_id, lead_id, status, priority, priority_score, priority_reason, commercial_fit_score)
        SELECT gen_random_uuid(), '30d91eeb-b306-4674-a3a7-5249a9e9096f', id, 'approved', 'P1', 90, 'Pinned Contact Verified: @KSA_Trader11', 90
        FROM leads WHERE channel_username ILIKE '%%ABOSALEM2003%%'
        ON CONFLICT DO NOTHING;
    """)

conn.commit()
conn.close()
print("ABOSALEM2003 & ksa_trader11 updated cleanly")
