"""
app/core/redis_client.py — Redis Connection Provider
"""

import redis
from app.core import config

_redis_conn = None


def get_redis_client() -> redis.Redis:
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            password=config.REDIS_PASSWORD,
            decode_responses=True
        )
    return _redis_conn
