from app.core.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

cur.execute("""
    UPDATE leads 
    SET title = %s,
        contact_username = 'G0ld_c',
        admin_username = 'G0ld_c',
        lead_score = 100,
        forex_intent_score = 100,
        tier = 'Tier_A',
        last_scan = NOW()
    WHERE channel_username ILIKE '%%almaalforex%%';
""", ('🏆 أكاديمية الخبراء | خبراء تداول الذهب',))

cur.execute("""
    INSERT INTO campaign_logs (id, campaign_id, lead_id, status, priority, priority_score, priority_reason, commercial_fit_score)
    SELECT gen_random_uuid(), '30d91eeb-b306-4674-a3a7-5249a9e9096f', id, 'approved', 'P0', 100, 'Pinned Admin Contact Verified: @G0ld_c', 100
    FROM leads WHERE channel_username ILIKE '%%almaalforex%%'
    ON CONFLICT DO NOTHING;
""")

conn.commit()
print("Successfully updated almaalforex with title and @G0ld_c contact")
conn.close()
