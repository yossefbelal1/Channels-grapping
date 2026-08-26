"""
tests/test_db_pooling_verification.py — Verification tests for ThreadedConnectionPool and PooledConnectionWrapper
"""

import unittest
from unittest.mock import MagicMock, patch
from app.core.db import PooledConnectionWrapper, get_db_cursor


class TestDbPoolingVerification(unittest.TestCase):

    def test_pooled_connection_wrapper_close_returns_to_pool(self):
        """P1-A Verification: Closing a pooled connection returns it to the pool instead of closing the socket."""
        mock_raw_conn = MagicMock()
        mock_pool = MagicMock()

        wrapper = PooledConnectionWrapper(mock_raw_conn, mock_pool)

        # Call close()
        wrapper.close()

        # pool.putconn must be called with raw connection
        mock_pool.putconn.assert_called_once_with(mock_raw_conn)
        # raw connection socket close() MUST NOT be called directly
        mock_raw_conn.close.assert_not_called()

    def test_pooled_connection_context_manager_commits_and_returns(self):
        """P1-A Verification: Using 'with' block commits transaction and returns connection to pool on exit."""
        mock_raw_conn = MagicMock()
        mock_pool = MagicMock()

        wrapper = PooledConnectionWrapper(mock_raw_conn, mock_pool)

        with wrapper as conn:
            self.assertEqual(conn, mock_raw_conn)

        # On normal exit: commit was called, and returned to pool
        mock_raw_conn.commit.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_raw_conn)

    def test_pooled_connection_context_manager_rollbacks_on_exception(self):
        """P1-A Verification: Exception inside 'with' block triggers rollback and still returns connection to pool."""
        mock_raw_conn = MagicMock()
        mock_pool = MagicMock()

        wrapper = PooledConnectionWrapper(mock_raw_conn, mock_pool)

        with self.assertRaises(ValueError):
            with wrapper as conn:
                raise ValueError("Simulated DB query error")

        mock_raw_conn.rollback.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_raw_conn)


if __name__ == '__main__':
    unittest.main()
