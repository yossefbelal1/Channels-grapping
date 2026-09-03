# Architecture & System Design — Telegram Arabic Forex Discovery & Graph Intelligence Engine

## 1. System Overview

The **Channels-grapping** engine is a production-grade distributed intelligence pipeline specifically designed to discover, validate, score, map, and continuously crawl Arabic Forex, Trading, Gold (XAUUSD), SMC/ICT, and Prop Firm channels and communities across Telegram.

```
                                  [ DISCOVERY LAYER ]
┌─────────────────────────┬─────────────────────────┬─────────────────────────┬─────────────────────────┐
│  Telegram Global Search │   Global Post Search    │ Channel Recommendations │  Multi-Edge Graph Crawl │
│ (messages.searchGlobal) │  (channels.searchPosts) │ (getChannelRecommendations) │(Mentions, Forwards, Ads)│
└────────────┬────────────┴────────────┬────────────┴────────────┬────────────┴────────────┬────────────┘
             │                         │                         │                         │
┌────────────┴─────────────────────────┴─────────────────────────┴─────────────────────────┴────────────┐
│                             External Web Scraper (Pluggable Search Engines)                           │
│                                Seed Intake Worker (AutoTele, Manual, API)                             │
└──────────────────────────────────────────────┬────────────────────────────────────────────────────────┘
                                               │
                                               ▼
                              [ UNIFIED CANDIDATE QUEUE & DEDUPE ]
                             (Redis Priority Queues + Provenance Tracking)
                                               │
                                               ▼
                                 [ STAGE 1: CHEAP VALIDATION ]
                             (Metadata, Title, Username, Public Status)
                                               │
                                               ▼
                              [ ARABIC NLP & FOREX TAXONOMY SCORER ]
                        (Arabic Normalization, Keyword Mutation, Intent Rules)
                                               │
                                               ▼
                                  [ STAGE 2: DEEP VALIDATION ]
                      (Message Content Sampling, Contacts Extraction, Forwards)
                                               │
                                               ▼
                              [ MULTI-DIMENSIONAL SCORING ENGINE ]
                   (Forex, Gold, Arabic, Signal, Activity, Growth, Small/New Tiering)
                                               │
                                               ▼
                                   [ MULTI-EDGE GRAPH ENGINE ]
                     (Channel Edges, Forward Origins, Network Centrality)
                                               │
                                               ▼
                                  [ POSTGRESQL SOURCE OF TRUTH ]
                   (Channels, Snapshots, Contacts, Edges, Search Hits, Crawl Jobs)
                                               │
                                               ▼
                                 [ DYNAMIC PRIORITY SCHEDULER ]
                         (HOT / WARM / COLD / DORMANT Recrawl Cycles)
```

---

## 2. Core Subsystems & Components

### 2.1 Discovery Layer (`app/discovery/`, `scavenger.py`, `web_scraper.py`)
- **Global Message Search**: Uses Telethon `messages.SearchGlobalRequest` to find channels by message contents.
- **Hashtag Post Search**: Uses Telethon `channels.SearchPostsRequest` to track live trading hashtags.
- **Similar Channel Recommendations**: Uses `channels.GetChannelRecommendationsRequest` on top-tier validated channels.
- **Search Checkpoint Manager (`app/discovery/checkpoint.py`)**: Stores pagination offset states in Redis and PostgreSQL to allow interrupted search queries to resume without duplicate calls.
- **Provenance Manager (`app/discovery/provenance.py`)**: Normalizes usernames, tracks multi-source origins (`discovered_by`), and accumulates discovery counts.

### 2.2 Arabic NLP & Taxonomy Intelligence (`app/discovery/arabic_normalizer.py`, `app/discovery/taxonomy.py`)
- **Arabic Normalizer**: Strips Tashkeel diacritics and Tatweel; unifies Alif variants (`ا, أ, إ, آ, ٱ` -> `ا`), Yaa/Alif Maqsura (`ي, ى, ئ` -> `ي`), and Taa Marbuta.
- **Hierarchical Taxonomy**: Categorizes keywords across 9 families (Forex, Gold/XAUUSD, SMC/ICT, Trading Styles, Signals, Brokers, Prop Firms, Commercial Services, Arabic Crypto).

### 2.3 Multi-Dimensional Scoring Engine (`app/scoring/`)
Calculates 13 independent dimensions with zero subscriber-count bias:
1. `forex_score`: Density and frequency of Forex currency terms.
2. `arabic_score`: Character-level Arabic ratio and dialect phrases.
3. `trading_score`: Technical analysis, chart patterns, and indicators.
4. `signal_score`: Actionable trade setups (buy/sell limits, SL, TP, pips).
5. `gold_score`: Gold and XAUUSD specialization.
6. `activity_score`: Real-time post frequency in 24h, 7d, and 30d.
7. `growth_score`: Member growth rate tracked across snapshots.
8. `commercial_score`: VIP access, account management, copy trading, and subscriptions.
9. `contact_score`: Resolved owner, admin, WhatsApp, and website contacts.
10. `legitimacy_score`: Anti-spam and anti-casino filter.
11. `discovery_score`: Multi-source confidence boost.
12. `freshness_score`: Recency of the most recent channel post.
13. `new_channel_score`: Active bonus boost for small (100–500 members) and newly launched active channels.

### 2.4 Multi-Edge Graph & Forward Analyzer (`app/graph/`, `graph_expander.py`)
- **Multi-Edge Model**: Explicit relationship edges (`mention`, `forwarded_from`, `promoted`, `linked`, `recommended`) with confidence and evidence.
- **Forward Analyzer**: Extracts `message.fwd_from` origin headers to identify root signal providers and syndicated channel networks.

### 2.5 Activity Intelligence & Dynamic Crawl Scheduler (`app/scheduler/`)
Classifies channels into 4 tiers:
- **`HOT`** (>= 5 posts/day) -> Recrawled every 6 hours.
- **`WARM`** (1–4 posts/day) -> Recrawled every 24 hours.
- **`COLD`** (< 1 post/week) -> Recrawled every 7 days.
- **`DORMANT`** (no activity > 30 days) -> Recrawled every 30 days.

---

## 3. Database Schema Topology

```
 leads (Canonical Channel Record)
   ├── id (UUID, PK)
   ├── channel_username (VARCHAR, UNIQUE)
   ├── lead_score, tier, activity_class
   ├── 13 scoring dimension columns
   ├── owner_username, admin_username
   └── next_crawl_at, discovery_count, discovered_by

 channel_edges (Multi-Edge Directed Graph)
   ├── id (UUID, PK)
   ├── source_channel_id (FK -> leads.id)
   ├── target_channel_id (FK -> leads.id)
   ├── relation_type (mention, forwarded_from, promoted, linked, recommended)
   ├── confidence, occurrence_count, evidence
   └── CONSTRAINT uq_channel_edge UNIQUE(source, target, relation_type)

 channel_contacts (Structured Contact Directory)
   ├── id (UUID, PK)
   ├── channel_id (FK -> leads.id)
   ├── contact_type (owner, admin, support, whatsapp, website, email, linktree, social)
   └── value, confidence, source

 channel_snapshots (Time-Series Metric History)
   ├── channel_id (FK -> leads.id)
   ├── member_count, post_count, posts_24h, posts_7d, posts_30d
   └── recorded_at (TIMESTAMP)

 discovery_checkpoints (Resumable Search Pagination)
   ├── search_type, query_key
   ├── last_offset_id, last_offset_rate, page_number, total_yield, status
   └── updated_at
```
