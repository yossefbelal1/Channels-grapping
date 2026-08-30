"""
tests/test_real_postgres_integration.py — Real PostgreSQL Concurrency & Connection Pooling Integration Tests

Exercises actual PostgreSQL server transactions using:
1. SELECT ... FOR UPDATE SKIP LOCKED across 10+ concurrent real database connections.
2. Concurrent multi-row claims across 10+ threads.
3. Connection pool acquisition, reuse, and context management without socket destruction.

Runs automatically against PostgreSQL service in CI or local development.
"""

import os
import uuid
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from app.core import config
from app.core.db import PooledConnectionWrapper


def get_real_pg_conn():
    """Attempts to create a physical connection to PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", "leadhunter_test_db" if "leadhunter_test_db" in os.environ.get("DB_NAME", "") else "leadhunter_db"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "testpassword" if "leadhunter_test_db" in os.environ.get("DB_NAME", "") else ""),
            connect_timeout=3
        )
        return conn
    except Exception:
        return None


class TestRealPostgresIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Check if real PostgreSQL server is reachable."""
        cls.conn = get_real_pg_conn()
        if cls.conn is None:
            cls.is_available = False
            return

        cls.is_available = True
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            # Ensure schema tables exist for testing
            cur.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    channel_username VARCHAR(255) UNIQUE NOT NULL,
                    contact_username VARCHAR(255),
                    is_group BOOLEAN DEFAULT FALSE,
                    status VARCHAR(20) DEFAULT 'new'
                );
                CREATE TABLE IF NOT EXISTS campaigns (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    message_text TEXT NOT NULL,
                    media_path VARCHAR(255),
                    status VARCHAR(20) DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS campaign_logs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
                    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
                    status VARCHAR(20) DEFAULT 'pending',
                    error_message TEXT,
                    sent_at TIMESTAMP,
                    delivery_id UUID DEFAULT gen_random_uuid(),
                    attempt_count INT DEFAULT 0,
                    last_attempt_at TIMESTAMP,
                    next_attempt_at TIMESTAMP,
                    risk_level VARCHAR(20),
                    account_used VARCHAR(100),
                    eligibility VARCHAR(20)
                );
            """)

    @classmethod
    def tearDownClass(cls):
        if cls.conn:
            cls.conn.close()

    def setUp(self):
        if not self.is_available:
            self.skipTest("Real PostgreSQL server is not reachable. Skipping real PostgreSQL integration test.")

    def test_single_row_concurrent_claim_skip_locked(self):
        """
        P0 Concurrency Gate: 15 concurrent physical PostgreSQL connections race
        to claim the SAME pending campaign_log row via 'SELECT ... FOR UPDATE OF cl SKIP LOCKED'.
        
        Guarantees:
        - Exactly ONE worker acquires the row lock and updates status to 'processing'.
        - Exactly 14 workers receive empty result (row skipped without blocking or waiting).
        - Zero duplicate claims, zero deadlocks.
        """
        # 1. Create dedicated test campaign and lead
        campaign_id = str(uuid.uuid4())
        lead_id = str(uuid.uuid4())
        log_id = str(uuid.uuid4())
        test_username = f"test_chan_{uuid.uuid4().hex[:8]}"

        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO campaigns (id, message_text, status) VALUES (%s, %s, 'active')",
                        (campaign_id, "Test concurrency pitch"))
            cur.execute("INSERT INTO leads (id, channel_username, contact_username, status) VALUES (%s, %s, %s, 'new')",
                        (lead_id, test_username, f"admin_{test_username}"))
            cur.execute("INSERT INTO campaign_logs (id, campaign_id, lead_id, status) VALUES (%s, %s, %s, 'pending')",
                        (log_id, campaign_id, lead_id))

        successful_claims = []
        barrier = threading.Barrier(15)

        def worker_claim_task(worker_id):
            conn = get_real_pg_conn()
            if not conn:
                return None
            try:
                # Synchronize all threads at barrier before firing
                barrier.wait(timeout=5)
                
                # Execute EXACT production claim query
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT cl.id as log_id, cl.campaign_id, cl.lead_id, c.message_text,
                               l.contact_username, l.channel_username
                        FROM campaign_logs cl
                        JOIN campaigns c ON cl.campaign_id = c.id
                        JOIN leads l ON cl.lead_id = l.id
                        WHERE cl.id = %s AND cl.status = 'pending'
                        FOR UPDATE OF cl SKIP LOCKED
                    """, (log_id,))
                    claimed_row = cur.fetchone()
                    if claimed_row:
                        # Claimed -> update to processing and commit
                        cur.execute("UPDATE campaign_logs SET status = 'processing' WHERE id = %s", (log_id,))
                        conn.commit()
                        return worker_id
                    else:
                        conn.rollback()
                        return None
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(worker_claim_task, i) for i in range(15)]
            for f in as_completed(futures):
                res = f.result()
                if res is not None:
                    successful_claims.append(res)

        # Assertions on real database state
        self.assertEqual(len(successful_claims), 1,
                         f"Exactly ONE worker must claim the locked row. Claimants: {successful_claims}")

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT status FROM campaign_logs WHERE id = %s", (log_id,))
            final_status = cur.fetchone()["status"]
            self.assertEqual(final_status, "processing")

    def test_multi_row_concurrent_claims_skip_locked(self):
        """
        P0 Concurrency Gate: 10 concurrent connections race for 3 pending rows.
        
        Guarantees:
        - Exactly 3 distinct workers claim exactly 1 row each.
        - Remaining 7 workers get None.
        - Zero duplicate claims across any row.
        """
        campaign_id = str(uuid.uuid4())
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO campaigns (id, message_text, status) VALUES (%s, %s, 'active')",
                        (campaign_id, "Multi-row concurrency pitch"))

        log_ids = []
        for i in range(3):
            lead_id = str(uuid.uuid4())
            lid = str(uuid.uuid4())
            log_ids.append(lid)
            u = f"multi_chan_{uuid.uuid4().hex[:8]}"
            with self.conn.cursor() as cur:
                cur.execute("INSERT INTO leads (id, channel_username, contact_username, status) VALUES (%s, %s, %s, 'new')",
                            (lead_id, u, f"admin_{u}"))
                cur.execute("INSERT INTO campaign_logs (id, campaign_id, lead_id, status) VALUES (%s, %s, %s, 'pending')",
                            (lid, campaign_id, lead_id))

        claimed_rows_by_worker = {}
        lock = threading.Lock()
        barrier = threading.Barrier(10)

        def worker_claim_multi(worker_id):
            conn = get_real_pg_conn()
            if not conn:
                return
            try:
                barrier.wait(timeout=5)
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT cl.id as log_id, cl.campaign_id, cl.lead_id
                        FROM campaign_logs cl
                        WHERE cl.campaign_id = %s AND cl.status = 'pending'
                        LIMIT 1
                        FOR UPDATE OF cl SKIP LOCKED
                    """, (campaign_id,))
                    row = cur.fetchone()
                    if row:
                        claimed_id = row["log_id"]
                        cur.execute("UPDATE campaign_logs SET status = 'processing' WHERE id = %s", (claimed_id,))
                        conn.commit()
                        with lock:
                            claimed_rows_by_worker[worker_id] = claimed_id
                    else:
                        conn.rollback()
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker_claim_multi, i) for i in range(10)]
            for f in as_completed(futures):
                f.result()

        # Exactly 3 workers claimed 1 distinct row each
        self.assertEqual(len(claimed_rows_by_worker), 3,
                         f"Exactly 3 rows were available, got claims: {claimed_rows_by_worker}")
        claimed_log_ids = list(claimed_rows_by_worker.values())
        self.assertEqual(len(set(claimed_log_ids)), 3, "All claimed row IDs must be unique (no duplicate claims).")

    def test_pooled_connection_wrapper_real_pool(self):
        """
        Verify that PooledConnectionWrapper returns real PostgreSQL connection
        to pool without closing the underlying socket.
        """
        pool = ThreadedConnectionPool(
            minconn=2,
            maxconn=5,
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", "leadhunter_test_db" if "leadhunter_test_db" in os.environ.get("DB_NAME", "") else "leadhunter_db"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "testpassword" if "leadhunter_test_db" in os.environ.get("DB_NAME", "") else "")
        )

        try:
            # 1. Acquire wrapper and test query
            raw_conn = pool.getconn()
            wrapper = PooledConnectionWrapper(raw_conn, pool)
            with wrapper.cursor() as cur:
                cur.execute("SELECT 1 AS num")
                res = cur.fetchone()
                self.assertEqual(res[0], 1)

            # 2. Close wrapper (returns to pool)
            wrapper.close()

            # 3. Connection is still alive and re-usable from pool
            raw_conn2 = pool.getconn()
            self.assertFalse(raw_conn2.closed, "Underlying connection socket must remain open in pool.")
            with raw_conn2.cursor() as cur:
                cur.execute("SELECT 2 AS num")
                self.assertEqual(cur.fetchone()[0], 2)
            pool.putconn(raw_conn2)
        finally:
            pool.closeall()


if __name__ == '__main__':
    unittest.main()
