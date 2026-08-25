# Channels-grapping: Comprehensive Architecture Audit & Production Hardening Plan

**Audit Timestamp:** 2026-08-26  
**Repository:** [yossefbelal1/Channels-grapping](https://github.com/yossefbelal1/Channels-grapping)  
**Status:** Baseline Documented — Pre-Refactoring Audit  

---

## 1. Current Architecture Overview

Channels-grapping is an autonomous Arabic Forex & Crypto business intelligence, channel discovery, lead qualification, and outreach delivery platform.

```
                      ┌─────────────────────────────────┐
                      │    External Ingestion & Seeds    │
                      │  (AutoTele / Web / Manual Seeds) │
                      └──────────────┬──────────────────┘
                                     │ INSERT seed_channels
                                     ▼
                       ┌───────────────────────────┐
                       │    seed_intake_worker     │
                       └─────────────┬─────────────┘
                                     │
    ┌────────────────────────────────┼────────────────────────────────┐
    ▼                                ▼                                ▼
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│     scavenger.py     │   │       radar.py       │   │  graph_expander.py   │
│  (Keyword Discovery) │   │ (Live Group Listener)│   │ (Post Links Crawler) │
└──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘
           │                          │                          │
           └──────────────────────────┼──────────────────────────┘
                                      │ RPUSH (JSON payload)
                                      ▼
                      ┌───────────────────────────────┐
                      │ Redis Priority Queues         │
                      │ • queue:critical              │
                      │ • queue:high                  │
                      │ • queue:normal                │
                      └───────────────┬───────────────┘
                                      │ BLPOP / LPOP
                                      ▼
                      ┌───────────────────────────────┐
                      │         validator.py          │
                      │  • Channel & Entity Analysis  │
                      │  • Arabic NLP & Forex Intent  │
                      │  • Contact/Admin Extraction   │
                      │  • Marketplace Group Scoring  │
                      │  • Auto-Joiner & Live Dialogs │
                      │  • Campaign & Follow-up Loops │
                      └───────────────┬───────────────┘
                                      │
           ┌──────────────────────────┴──────────────────────────┐
           ▼                                                     ▼
┌──────────────────────────────┐              ┌──────────────────────────────┐
│  PostgreSQL (leadhunter_db)  │              │    dashboard.py (FastAPI)    │
│  • leads & group_metrics     │◄─────────────┤  • CRM Leads & Leaderboards  │
│  • channel_graph & posts     │              │  • Campaign Ingestion API    │
│  • campaigns & campaign_logs │              │  • Realtime Metrics & Stats  │
└──────────────────────────────┘              └──────────────────────────────┘
```

---

## 2. Worker Responsibilities

| Worker / Module | Script / Service | Primary Responsibility | Telegram Session |
|---|---|---|---|
| **Scavenger** | `scavenger.py` | Searches Telegram global directory for curated Arabic Forex/Crypto keywords, extracts channel/group usernames, pushes to validation queue. | `scavenger_session` |
| **Radar** | `radar.py` | Joins/listens to top active Arabic marketplace groups, captures realtime forwarded messages and promo links. | `radar_session` |
| **Graph Expander** | `graph_expander.py` | Traverses the ecosystem graph by fetching historical posts from qualified channels and extracting forwarded links and @mentions. | `graph_expander_session` |
| **Web Scraper** | `web_scraper.py` | Scrapes external Telegram catalog websites (TelegramChannels.me, TGStat, etc.) for new Arabic channels. | None (HTTP only) |
| **Seed Intake** | `seed_intake_worker.py` | Bridges external systems (AutoTele, manual databases) by polling `seed_channels` table and routing seeds to priority queues. | None (DB + Redis) |
| **Validator** | `validator.py` | Central processing engine: pops links from Redis queues, fetches full Telegram metadata, classifies Arabic ratio & Forex business models, extracts contact info, updates graph & DB, runs Auto-Joiner & Campaign Dispatcher. | `validator_session` + `user_session` (@tamerads1) |
| **Campaign Worker** | `campaign_worker.py` / `validator.py` | Delivers direct outreach messages and 3-photo albums to channel owners/admins with rate limiting and follow-up loops. | `user_session` |
| **Dashboard** | `dashboard.py` | FastAPI web service providing full CRM UI, analytics endpoints, network graph visualization, and campaign controls. | None (DB + Redis) |

---

## 3. Data Flow

1. **Discovery:**
   - Producers (`scavenger.py`, `radar.py`, `graph_expander.py`, `web_scraper.py`, `seed_intake_worker.py`) discover raw candidate links.
   - Producer checks Redis set `seen_channels` for deduplication.
   - If not seen, registers in `seen_channels` and pushes JSON payload to `queue:critical`, `queue:high`, or `queue:normal`.
2. **Ingestion & Validation:**
   - `validator.py` pops candidate from the highest non-empty priority queue.
   - Checks cooldown / blacklist in Redis & PostgreSQL.
   - Fetches entity metadata via Telethon through `TelegramManager` (or falls back to web preview `t.me/s/...` if restricted).
   - Classifies language (Arabic ratio), Forex commercial offerings (VIP, Account Management, Copy Trading, Prop Firms), and extracts direct contact username.
   - Stores/updates `leads`, `group_metrics`, `channel_keywords`, `channel_graph`, and `channel_posts`.
3. **Outreach & Campaigns:**
   - New qualified leads with contact usernames are enqueued into active `campaign_logs`.
   - `campaign_dispatcher_loop` sends initial pitch message with 3-photo album (max 12/day, with human break jitter).
   - `followup_dispatcher_loop` monitors unanswered leads after 4 days, inspects live chat history to strictly exclude any contact who replied, and delivers follow-up album (max 8/day).

---

## 4. Redis Key Registry & Usage

| Key Pattern | Type | Usage / Purpose |
|---|---|---|
| `seen_channels` | SET | Global deduplication set for all discovered links/usernames. |
| `queue:critical` | LIST | Critical priority validation queue (rescan scheduler, immediate requests). |
| `queue:high` | LIST | High priority validation queue (AutoTele, Graph expander, group broadcasts). |
| `queue:normal` | LIST | Standard priority validation queue (Scavenger keywords, web scraping). |
| `lock:session:{session_name}` | STRING | Distributed lock preventing concurrent SQLite access on the same Telethon session. |
| `health:{session_name}:score` | STRING | Dynamic account health score (0 to 100). |
| `health:{session_name}:banned` | STRING | Flag set to "1" if session received permanent ban/deactivation. |
| `health:{session_name}:rate_limited_until` | STRING | Timestamp until which the session is in global Telegram FloodWait cooldown. |
| `health:user_session:dm_rate_limited_until` | STRING | Cooldown timestamp for new DM creation on user outreach account. |
| `health:user_session:followup_rate_limited_until`| STRING | Cooldown timestamp for follow-up DMs (isolated from new DMs). |
| `health:user_session:join_rate_limited_until` | STRING | Cooldown timestamp for channel joins (isolated from DMs). |
| `limit:{session_name}:requests_hour` | STRING | Sliding 1-hour request counter for rate limiting. |
| `campaign_sent_today:YYYY-MM-DD` | STRING | Counter of outreach messages sent today (cap: 12). |
| `campaign_followup_sent_today:YYYY-MM-DD` | STRING | Counter of follow-up messages sent today (cap: 8). |
| `priority:keywords` | ZSET | Frequency/quality scored keywords for adaptive search ordering. |

---

## 5. PostgreSQL Schema & Database Usage

- **`leads`**: Master table for channels and groups (metadata, lead_score, tier, contact_username, arabic_ratio, business flags).
- **`group_metrics`**: Specialized analytics for marketplace groups (messages_scanned, mentions_count, links_count, advertisements_count, marketplace_score).
- **`channel_graph`**: Directed graph edges between source channels and target channels/mentions.
- **`channel_keywords`**: Keyword frequency occurrences per channel.
- **`channel_posts`**: Range-partitioned table by month (`channel_posts_YYYY_MM`) for historical message texts.
- **`seed_channels`**: Ingestion staging table for external seeds from AutoTele.
- **`blacklist`**: Blacklisted usernames and domains.
- **`campaigns` & `campaign_logs`**: Outreach campaigns definition, message copies, media paths, delivery states, and follow-up tracking.

---

## 6. Telegram Session Flow & Locking Audit

### Existing Flaws Identified:
1. **Unsafe Startup Lock Deletion:**
   In `tg_manager.py:start_all()`, the code blindly deleted `lock:session:{primary_session}` without checking if another active container held the lock.
2. **Non-Atomic Lock Release:**
   Lock release in `tg_manager.py` did a `GET` followed by `DELETE`. If ownership expired between get and delete, it could delete a lock acquired by another worker.
3. **Lock Ownership Identifier:**
   Current `lock_value` was generated per process instance, but lacked structured host/process identification and atomic Lua compare-and-delete.

---

## 7. Existing Rate Limiting & Failover Behavior

### Existing Flaws Identified:
1. **Non-Atomic Rate Limiting:**
   `check_request_limit()` did `GET` then `INCR` in a pipeline without Lua script atomicity. Multiple concurrent async tasks could read below threshold simultaneously and exceed the rate limit.
2. **Comment vs Implementation Discrepancy:**
   Docstring claimed 800 requests/hour while code hardcoded `count >= 300`.
3. **Recursive Failover Call Stack:**
   In `tg_manager.py:execute_request()`, error recovery and session failover called `self.execute_request()` recursively, risking stack overflow on extended failovers.

---

## 8. Queue & Concurrency Correctness Audit

### Existing Flaws Identified:
1. **Seed Intake Crash Safety (`seed_intake_worker.py`):**
   Seeds were marked `processed = TRUE` *before* pushing to Redis `queue:high`. If Redis crashed or disconnected, the seed was permanently lost from the pipeline.
2. **Campaign Worker Concurrent Claiming Race Condition:**
   `campaign_worker.py` and `validator.py` did `SELECT ... WHERE status = 'pending' LIMIT 1` without `FOR UPDATE SKIP LOCKED`. If two campaign workers run concurrently, both will claim and dispatch to the exact same recipient.
3. **Campaign Idempotency:**
   No unique delivery token or deduplication guard existed if a worker crashed after `client.send_message` but before `UPDATE campaign_logs SET status = 'sent'`.

---

## 9. Security & Validation Audit

### Existing Flaws Identified:
1. **Dashboard Authentication:**
   Dashboard endpoints (`/api/campaigns/start`, etc.) had no authentication layer.
2. **Media Path Traversal:**
   `start_campaign` accepted arbitrary `media_path` strings without validating that the path is restricted within `/app/media/`.

---

## 10. Phased Implementation Roadmap

- **Phase 1:** Baseline verification & test runner setup.
- **Phase 2 (P0 - Critical Correctness):**
  - Robust distributed locking (`SET ... NX EX` with host+pid+uuid owner, atomic Lua release, lock renewal heartbeat, removal of startup deletion).
  - Centralized atomic token bucket / sliding window rate limiter in Redis via Lua.
  - Granular FloodWait classification (transient backoff vs score reduction vs quarantine).
  - Bounded iterative retry loop replacing recursive failovers.
  - Crash-safe Seed Intake state machine (durable processing transition).
  - Concurrency-safe campaign row claiming (`FOR UPDATE SKIP LOCKED` + `processing` state).
  - Delivery idempotency key (`campaign_id:lead_id`).
  - Dashboard API key / token auth & media path validation.
- **Phase 3 (P1 - Performance & Async):**
  - PostgreSQL connection pooling (`ThreadedConnectionPool` / async connection management).
  - Non-blocking async Redis & HTTP client.
  - Incremental post scanning in `graph_expander.py` using `min_id` watermark.
  - Queue backpressure throttle for producers.
- **Phase 4 (P1 - Code Architecture):**
  - Modular package extraction for `app/validator/` and `app/dashboard/` while retaining backward-compatible top-level wrappers (`validator.py`, `dashboard.py`).
  - Repository layer for clean database separation.
  - Reorganize one-off / migration / diagnostic scripts into `scripts/`.
- **Phase 5 (P3 - Testing):**
  - Deterministic unit & concurrency test suite with Telegram mocks.
- **Phase 6 (P3 - Observability & Metrics):**
  - Structured logging with context + lightweight Prometheus-compatible metrics endpoint.
  - Container healthchecks.
- **Phase 7 (CI/CD & Hardening):**
  - Pinned requirements lockfile, GitHub Actions workflow with lint, security scans (`pip-audit`), and Docker build.
