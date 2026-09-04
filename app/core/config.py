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
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "5"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "50"))

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

# Outreach Engine Configuration
OUTREACH_ENABLED = os.getenv("OUTREACH_ENABLED", "true").lower() == "true"
OUTREACH_DRY_RUN = os.getenv("OUTREACH_DRY_RUN", "false").lower() == "true"
OUTREACH_CANARY_SIZE = int(os.getenv("OUTREACH_CANARY_SIZE", "5"))
OUTREACH_MAX_RETRIES = int(os.getenv("OUTREACH_MAX_RETRIES", "3"))
OUTREACH_LEAD_COOLDOWN_DAYS = int(os.getenv("OUTREACH_LEAD_COOLDOWN_DAYS", "30"))
OUTREACH_RECONCILIATION_INTERVAL = int(os.getenv("OUTREACH_RECONCILIATION_INTERVAL", "300"))

# v7 Dynamic Scheduler & Crawl Knobs
CRAWL_INTERVAL_HOT_HOURS = int(os.getenv("CRAWL_INTERVAL_HOT_HOURS", "4"))
CRAWL_INTERVAL_WARM_HOURS = int(os.getenv("CRAWL_INTERVAL_WARM_HOURS", "18"))
CRAWL_INTERVAL_NORMAL_DAYS = int(os.getenv("CRAWL_INTERVAL_NORMAL_DAYS", "3"))
CRAWL_INTERVAL_COLD_DAYS = int(os.getenv("CRAWL_INTERVAL_COLD_DAYS", "10"))
CRAWL_INTERVAL_DORMANT_DAYS = int(os.getenv("CRAWL_INTERVAL_DORMANT_DAYS", "30"))
MIN_CRAWL_INTERVAL_MINUTES = int(os.getenv("MIN_CRAWL_INTERVAL_MINUTES", "120"))
MAX_CRAWL_INTERVAL_MINUTES = int(os.getenv("MAX_CRAWL_INTERVAL_MINUTES", "43200"))

# v7 Scan Depth Post Budgets
SCAN_DEPTH_DEEP_POSTS = int(os.getenv("SCAN_DEPTH_DEEP_POSTS", "150"))
SCAN_DEPTH_STANDARD_POSTS = int(os.getenv("SCAN_DEPTH_STANDARD_POSTS", "40"))
SCAN_DEPTH_LIGHT_POSTS = int(os.getenv("SCAN_DEPTH_LIGHT_POSTS", "15"))

# v7 Centralized Retry & Backpressure Knobs
TG_MAX_RETRIES = int(os.getenv("TG_MAX_RETRIES", "3"))
TG_RETRY_BASE_BACKOFF = float(os.getenv("TG_RETRY_BASE_BACKOFF", "1.5"))
TG_RETRY_MAX_BACKOFF = float(os.getenv("TG_RETRY_MAX_BACKOFF", "30.0"))
DLQ_NAME = os.getenv("DLQ_NAME", "queue:dead_letter")
BACKPRESSURE_VALIDATION_THRESHOLD = int(os.getenv("BACKPRESSURE_VALIDATION_THRESHOLD", "3000"))
BACKPRESSURE_CRAWL_THRESHOLD = int(os.getenv("BACKPRESSURE_CRAWL_THRESHOLD", "1500"))
