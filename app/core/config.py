"""
app/core/config.py — Central Application Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL Database Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "leadhunter_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Telegram / Rate Limiting Defaults
TELEGRAM_MAX_REQUESTS_PER_HOUR = int(os.getenv("TELEGRAM_MAX_REQUESTS_PER_HOUR", "300"))
SESSION_LOCK_TTL = int(os.getenv("TELEGRAM_SESSION_LOCK_TTL", "60"))
LOCK_HEARTBEAT_INTERVAL = int(os.getenv("TELEGRAM_LOCK_HEARTBEAT_INTERVAL", "15"))

# Dashboard Security
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")
ALLOWED_MEDIA_DIR = os.getenv("ALLOWED_MEDIA_DIR", "/app/media")
