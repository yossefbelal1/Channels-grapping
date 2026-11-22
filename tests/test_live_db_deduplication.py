import os
import unittest
import psycopg2
from psycopg2.extras import RealDictCursor

class TestDatabaseDeduplicationLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_host = os.getenv("DB_HOST", os.getenv("POSTGRES_HOST", "postgres"))
        db_port = int(os.getenv("DB_PORT", os.getenv("POSTGRES_PORT", 5432)))
        db_name = os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "leadhunter_db"))
        db_user = os.getenv("DB_USER", os.getenv("POSTGRES_USER", "postgres"))
        db_pass = os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
        cls.conn = psycopg2.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_zero_overlap_between_pending_and_already_sent_contacts(self):
        """Invariant 1: No contact currently pending/approved was ever sent a message previously."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) as contact,
                    cl.id as pending_log_id,
                    l.channel_username as pending_channel
                FROM campaign_logs cl
                JOIN leads l ON cl.lead_id = l.id
                WHERE cl.status IN ('pending', 'pending_review', 'approved', 'processing')
                  AND l.contact_username IS NOT NULL AND l.contact_username != ''
                  AND LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) IN (
                      SELECT DISTINCT LOWER(TRIM(LEADING '@' FROM TRIM(l_sent.contact_username)))
                      FROM campaign_logs cl_sent
                      JOIN leads l_sent ON cl_sent.lead_id = l_sent.id
                      WHERE cl_sent.status = 'sent' AND l_sent.contact_username IS NOT NULL AND l_sent.contact_username != ''
                  );
            """)
            overlap = cur.fetchall()
            self.assertEqual(len(overlap), 0, f"Found {len(overlap)} pending logs for contacts already sent: {overlap[:5]}")

    def test_zero_duplicate_contacts_within_pending_and_approved_queue(self):
        """Invariant 2: Every contact in the pending/approved queue appears exactly ONCE."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) as contact,
                    count(cl.id) as cnt,
                    array_agg(l.channel_username) as channels
                FROM campaign_logs cl
                JOIN leads l ON cl.lead_id = l.id
                WHERE cl.status IN ('pending', 'pending_review', 'approved', 'processing')
                  AND l.contact_username IS NOT NULL AND l.contact_username != ''
                GROUP BY LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username)))
                HAVING count(cl.id) > 1;
            """)
            dupes = cur.fetchall()
            self.assertEqual(len(dupes), 0, f"Found {len(dupes)} duplicate contacts in pending queue: {dupes[:5]}")

    def test_redis_messaged_contacts_set_matches_sent_db_contacts(self):
        """Invariant 3: Redis set outreach:messaged_contacts contains all unique contacts sent in DB."""
        import redis
        r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username)))) as sent_count
                FROM campaign_logs cl
                JOIN leads l ON cl.lead_id = l.id
                WHERE cl.status = 'sent' AND l.contact_username IS NOT NULL AND l.contact_username != '';
            """)
            db_sent_count = cur.fetchone()['sent_count']
            redis_sent_count = r.scard("outreach:messaged_contacts")
            self.assertGreaterEqual(redis_sent_count, db_sent_count)


if __name__ == "__main__":
    unittest.main()
