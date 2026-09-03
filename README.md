# Channels-grapping: Production Telegram Arabic Forex Discovery & Graph Intelligence Engine

A production-grade, distributed intelligence and graph analysis platform specialized in discovering, validating, scoring, and continuous crawling of Arabic Forex, Gold (XAUUSD), SMC/ICT, and trading communities across Telegram.

---

## 🌟 Core Architectural Features

1. **Maximized Realistic Coverage (No Subscriber-Count Bias)**:
   - Discovers and scores channels from small (100–500 subscribers) to large (500K+).
   - Small active channels with real trade signals receive a dedicated `new_channel_score` bonus.
2. **Multi-Source Discovery Engine**:
   - Telegram Global Message Search (`messages.searchGlobal`) with pagination and offset checkpoints.
   - Telegram Hashtag Post Search (`channels.searchPosts`).
   - Similar Channel Recommendations (`channels.getChannelRecommendations`).
   - Multi-Edge Directed Graph Crawling (`mention`, `forwarded_from`, `promoted`, `linked`, `recommended`).
   - Forward Origin Analysis (`fwd_from`) to reveal parent signal syndication networks.
   - Pluggable Web Search Engine (Google, Bing, DuckDuckGo, Telegram Directories).
3. **Arabic NLP & 9-Family Trading Taxonomy**:
   - Arabic text normalization (Alif variants, Yaa/Alif Maqsura, Taa Marbuta, Tashkeel diacritics, Tatweel).
   - Controlled query mutations and deduplication.
   - Comprehensive trading taxonomy (Forex, Gold, SMC/ICT, Scalping, Signals, Brokers, Prop Firms, Commercial Services, Crypto).
4. **13-Dimension Scoring Matrix with Evidence Persistence**:
   - `forex_score`, `arabic_score`, `trading_score`, `signal_score`, `gold_score`, `activity_score`, `growth_score`, `commercial_score`, `contact_score`, `legitimacy_score`, `discovery_score`, `freshness_score`, `new_channel_score` -> `final_score` + `tier` (`Tier_A`, `Tier_B`, `Tier_C`, `Tier_D`).
   - Evidence dictionary detailing exact keyword hits and growth metrics.
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
- [`OPERATIONS.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/OPERATIONS.md) — Production operations and runbook.
- [`TESTING.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/TESTING.md) — Automated testing guide.
- [`MANUAL_VERIFICATION.md`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/MANUAL_VERIFICATION.md) — Real Telegram verification procedure.
