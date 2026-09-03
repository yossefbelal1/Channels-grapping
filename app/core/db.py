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


class PooledConnectionWrapper:
    """
    Transparent wrapper around a pooled connection.
    Ensures that calling conn.close() returns the connection to the pool
    rather than closing the physical underlying socket.
    """

    def __init__(self, conn, pool_instance):
        self._conn = conn
        self._pool = pool_instance

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            try:
                self._conn.rollback()
            except Exception:
                pass
        else:
            try:
                self._conn.commit()
            except Exception:
                pass
        self.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if self._conn is not None and self._pool is not None:
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass
            self._conn = None


def get_db_connection():
    """
    Acquires a connection from the ThreadedConnectionPool.
    Calling conn.close() on the returned connection safely returns it to the pool.
    """
    p = get_db_pool()
    raw_conn = p.getconn()
    return PooledConnectionWrapper(raw_conn, p)


def get_raw_connection():
    """Returns a standalone dedicated connection for long-running unpooled sessions."""
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        cursor_factory=RealDictCursor
    )


@contextmanager
def get_db_cursor(commit_on_success: bool = True):
    """
    Context manager for acquiring a pooled connection & cursor in a single with block.
    Guarantees immediate and safe return of connection to pool.
    """
    conn = get_db_connection()
    cur = None
    try:
        cur = conn.cursor()
        yield cur
        if commit_on_success:
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()
