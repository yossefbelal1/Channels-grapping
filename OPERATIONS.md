# Operations & Runbook Guide — Channels-grapping

## 1. Running the System Locally and in Production

### 1.1 Prerequisites
- Python 3.10+
- PostgreSQL 14+ with `pgcrypto` or `uuid-ossp`
- Redis 7+
- Valid Telegram Sessions (`user_session.session`, `scavenger_session.session`, etc.)

### 1.2 Database Migrations
Apply all migrations in order:
```bash
psql -U postgres -d leadhunter_db -f schema.sql
psql -U postgres -d leadhunter_db -f migrate_v3_graph_engine.sql
psql -U postgres -d leadhunter_db -f migrate_v4_outreach_engine.sql
psql -U postgres -d leadhunter_db -f migrate_v5_graph_engine.sql
```

### 1.3 Running Workers with Docker Compose
```bash
docker-compose up -d --build
```

To run individual workers locally for development:
```bash
# Terminal 1: Lead Validator & CRM Processor
python validator.py

# Terminal 2: Multi-Source Scavenger
python scavenger.py

# Terminal 3: Multi-Edge Graph Expander
python graph_expander.py

# Terminal 4: Web Scraper
python web_scraper.py

# Terminal 5: Seed Intake Worker
python seed_intake_worker.py

# Terminal 6: FastAPI Dashboard
python dashboard.py
```

---

## 2. Redis Queue & Key Topology

| Queue / Key | Purpose |
|---|---|
| `queue:critical` | P0 urgent crawl jobs and high-priority cross-promoted channels. |
| `queue:high` | Graph discoveries, similar channel recommendations, and top signals. |
| `queue:normal` | Global search and web search discoveries. |
| `queue:low` | Periodic re-validation of COOLDOWN / DORMANT channels. |
| `recommendations:queue` | High-scoring Tier A/B channels waiting for similar channel expansion. |
| `seen_channels` | Redis Set containing all previously seen canonical channel URLs. |
| `checkpoint:*` | Pagination offsets for search queries. |
| `provenance:sources:*` | Multi-source provenance set per channel handle. |
| `health:*:score` | Telegram session health scores (0–100). |
| `lock:session:*` | Distributed locks preventing duplicate concurrent session logins. |

---

## 3. Account Health & FloodWait Handling

- **Health Scores**: Each Telegram account starts at 100 points.
- **FloodWait Classification**:
  - `Wait <= 60s`: Handled transparently with asynchronous jitter delay; health score drops by 5.
  - `Wait > 60s`: Account automatically placed in COOLDOWN; health score drops by 15.
  - `Auth / Key Errors`: Account immediately quarantined to prevent session bans.
- **Failover**: `TelegramManager.execute_request` automatically rotates to the healthiest available session if the active session is rate-limited.
