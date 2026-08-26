# Channels-grapping: Comprehensive Architecture Audit & Production Hardening Plan

**Audit Timestamp:** 2026-08-26 (Round 2 Verified)  
**Repository:** [yossefbelal1/Channels-grapping](https://github.com/yossefbelal1/Channels-grapping)  
**Status:** Enterprise Production Hardened — All P0/P1/P2 Gaps Resolved & Regression Tested  

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
| **Graph Expander** | `graph_expander.py` | Traverses the ecosystem graph by fetching historical posts from qualified channels and extracting forwarded links and @mentions with message watermark (`min_id`). | `graph_expander_session` |
| **Web Scraper** | `web_scraper.py` | Scrapes external Telegram catalog websites (TelegramChannels.me, TGStat, etc.) for new Arabic channels. | None (HTTP only) |
| **Seed Intake** | `seed_intake_worker.py` | Bridges external systems (AutoTele, manual databases) by polling `seed_channels` table and routing seeds to priority queues with atomic Lua deduplication. | None (DB + Redis) |
| **Validator** | `validator.py` | Central processing engine: pops links from Redis queues, fetches full Telegram metadata, classifies Arabic ratio & Forex business models, extracts contact info, updates graph & DB, runs Auto-Joiner & Campaign Dispatcher. | `validator_session` + `user_session` (@tamerads1) |
| **Campaign Worker** | `campaign_worker.py` / `validator.py` | Delivers direct outreach messages and 3-photo albums to channel owners/admins with rate limiting, `FOR UPDATE SKIP LOCKED` claiming, and follow-up loops. | `user_session` |
| **Dashboard** | `dashboard.py` | FastAPI web service providing full CRM UI, analytics endpoints, network graph visualization, and campaign controls with API key security. | None (DB + Redis) |

---

## 3. Delivery Guarantees & Correctness Model

### Outreach Delivery Model:
- **At-Least-Once Dispatch with Distributed Deduplication Protection:**
  Because Telegram API calls and PostgreSQL transactions cannot execute in a single distributed 2PC transaction, outreach messages are protected against duplicate sends via a dual-layer strategy:
  1. Transactional database claiming via `SELECT ... FOR UPDATE OF cl SKIP LOCKED` transitions row to `status = 'processing'`.
  2. Redis delivery token `campaign:delivered:{campaign_id}:{lead_id}` recorded with 30-day TTL upon successful dispatch.
  3. If a worker process crashes between Telegram dispatch and database commit, the recovering worker reads the Redis token, identifies that the external delivery already succeeded, and immediately marks the database record as `sent` without re-dispatching to Telegram.

### Rate Limiter Fail-Safe Model:
- **Fail-Closed Protection:**
  If Redis or the Lua rate limiter is temporarily unavailable or errors, the rate limiter strictly returns `False` (Fail-Closed) to prevent unchecked Telegram API calls from causing carrier or platform bans.

### Seed Queue Reliability Model:
- **Atomic Dedup & Enqueue via Redis Lua:**
  Seed intake evaluates membership in `seen_channels` and pushes to `queue:high`/`queue:normal` in a single atomic Lua script. If Redis fails, the seed remains un-marked in PostgreSQL and is safely retried on subsequent poll cycles without being prematurely recorded in `seen_channels`.

---

## 4. Verification Test Matrix (43 Tests Total)

1. **Dashboard & API Security:**
   - Import & typing integrity
   - Production API key requirement (HTTP 500 on missing key in production)
   - Unauthorized access rejection (HTTP 401 on invalid key)
   - Strict canonical path containment against directory traversal (`../`, absolute paths outside `/app/media/`)
2. **Rate Limiting & Locking:**
   - Fail-closed error handling
   - Sliding-window cleanup and sequence increment
   - Multi-worker concurrent session lock contention (20 workers -> exactly 1 winner)
   - Compare-and-delete atomic lock release
3. **Queue & Campaign Concurrency:**
   - Atomic seed enqueue Lua execution
   - Zero seed loss upon Redis connection failures
   - 20-worker concurrent row claim simulation (`FOR UPDATE SKIP LOCKED`)
   - Crash-window delivery idempotency recovery
4. **NLP & Scoring:**
   - Arabic character ratio calculations across Arabic, English, and mixed texts
   - Multi-tier lead score classification (Tier 1, Tier 2, Tier 3, Unqualified)
5. **Link & Contact Extraction:**
   - Public, private (+), joinchat parsing
   - Bot & junk keyword filtering
   - Website, email, phone/WhatsApp, and admin contact extraction
