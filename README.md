# Channels-grapping: Production Telegram Arabic Forex Discovery & Graph Intelligence Engine

A production-grade, distributed intelligence and graph analysis platform specialized in discovering, validating, scoring, and continuous crawling of Arabic Forex, Gold (XAUUSD), SMC/ICT, and trading communities across Telegram.

* **Global Content Discovery**: Exhaustive continuous scanning across Telegram global search, public post search, and contact directories.
* **Multi-Edge Graph Intelligence (Phase 2)**: Advanced traversal of channel relationships including Similar Channel Recommendations, forward origin detection, mentions, and promotions.
* **Unified Candidate Pipeline**: Atomic deduplication and provenance tracking across all discovery vectors.
* **Arabic Taxonomy**: Multi-variant linguistic normalization for the Forex, Gold, and Crypto markets.

---

## 🌟 Core Architectural Features

1. **Maximized Realistic Coverage (No Subscriber-Count Bias)**:
   - Discovers and scores channels from ~400 subscribers to 2,000,000+.
   - Subscriber count has **0% weight** — pure neutrality across all sizes.
   - Small active channels with real trade signals receive a dedicated `new_channel_score` bonus.
2. **Multi-Source Discovery Engine**:
   - Telegram Global Message Search (`messages.searchGlobal`) with pagination and offset checkpoints.
   - Telegram Hashtag + Text Post Search (`channels.searchPosts`).
   - Similar Channel Recommendations (`channels.getChannelRecommendations`).
   - Multi-Edge Directed Graph Crawling (`mention`, `forwarded_from`, `promoted`, `linked`, `recommended`).
   - Forward Origin Analysis (`fwd_from`) to reveal parent signal syndication networks.
   - Pluggable Web Search Engine (Google, Bing, DuckDuckGo, Telegram Directories).
3. **Arabic NLP & 9-Family Trading Taxonomy**:
   - Arabic text normalization (Alif variants, Yaa/Alif Maqsura, Taa Marbuta, Tashkeel diacritics, Tatweel).
   - Controlled query mutations and deduplication.
   - Comprehensive trading taxonomy (Forex, Gold, SMC/ICT, Scalping, Signals, Brokers, Prop Firms, Commercial Services, Crypto).
4. **12+ Dimension Channel Intelligence & Smart Ranking (Phase 3)**:
   - `forex_score` (28%), `gold_score` (14%), `signal_score` (14%), `trading_score` (10%), `arabic_score` (10%), `new_channel_score` (8%), `activity_score` (5%), `freshness_score` (5%), `growth_score` (5%), `discovery_score` (4%), `commercial_score` (3%), `contact_score` (2%) → `final_score` + `tier` + `classification`.
   - Per-post recurrence analysis, zero-trading damping, structured JSONB evidence persistence.
   - Four-tier classification: `HIGH_CONFIDENCE_FOREX`, `LIKELY_FOREX`, `POSSIBLE_FOREX`, `LOW_CONFIDENCE`.
5. **Dynamic Activity & Priority Scheduler**:
   - Categorizes channels into `HOT` (6h), `WARM` (24h), `COLD` (7d), and `DORMANT` (30d).
   - Automated priority injection into Redis queues.
6. **Robust Hardened Infrastructure**:
   - PostgreSQL schema v5 with zero-leak connection pooling.
   - Redis sliding-window Lua rate limiter and atomic session locking.
   - Prometheus-compatible `/metrics` observability endpoint on Dashboard.

---

## 🚀 Quick Start & Local Execution

### 1. Start Infrastructure with Docker
```bash
docker-compose up -d redis postgres
```

### 2. Apply Migrations
```bash
psql -U postgres -d leadhunter_db -f schema.sql
psql -U postgres -d leadhunter_db -f migrate_v5_graph_engine.sql
psql -U postgres -d leadhunter_db -f migrate_v6_channel_intelligence.sql
```

### 3. Run Automated Tests
```bash
python -m pytest tests/ -v
```

### 4. Run Benchmark Suite
```bash
python scripts/benchmark_pipeline.py
```

### 5. Launch Workers & Dashboard
```bash
# Terminal 1: Validator CRM
python validator.py

# Terminal 2: Multi-Source Scavenger
python scavenger.py

# Terminal 3: Multi-Edge Graph Expander
python graph_expander.py

# Terminal 4: Web Scraper
python web_scraper.py

# Terminal 5: CRM Dashboard
python dashboard.py
```

---

## 📖 Comprehensive Documentation
- [`ARCHITECTURE.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/ARCHITECTURE.md) — System design and data models.
- [`DISCOVERY.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/DISCOVERY.md) — Multi-source discovery strategies and Arabic taxonomy.
- [`SCORING.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/SCORING.md) — Channel Intelligence scoring dimensions, weights, classification, and policies.
- [`GRAPH.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/GRAPH.md) — Graph expansion engine and edge types.
- [`OPERATIONS.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/OPERATIONS.md) — Production operations and runbook.
- [`TESTING.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/TESTING.md) — Automated testing guide.
- [`MANUAL_VERIFICATION.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/MANUAL_VERIFICATION.md) — Real Telegram verification procedure.
