"""
app/core/db.py — Thread-safe PostgreSQL Connection Pool & Context Manager
"""

import logging
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from app.core import config

_pool = None


def get_db_pool():
    global _pool
    if _pool is None or _pool.closed:
        _pool = pool.ThreadedConnectionPool(
            minconn=config.DB_POOL_MIN,
            maxconn=config.DB_POOL_MAX,
            host=config.DB_HOST,
            port=config.DB_PORT,
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            cursor_factory=RealDictCursor
        )
        logging.info(f"Initialized PostgreSQL ThreadedConnectionPool ({config.DB_POOL_MIN}-{config.DB_POOL_MAX} conns).")
    return _pool


def get_raw_connection():
    """Returns a standalone psycopg2 connection (e.g. for long-running dedicated worker sessions)."""
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        cursor_factory=RealDictCursor
    )


@contextmanager
def get_db_connection():
    """
    Context manager for acquiring and returning a connection from the pool.
    Auto-commits on normal exit and auto-rollbacks on exception.
    """
    p = get_db_pool()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


@contextmanager
def get_db_cursor(commit_on_success: bool = True):
    """
    Context manager for acquiring a connection & cursor from the pool in a single with block.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
