# Discovery Engine & Taxonomy Guide — Channels-grapping

## 1. Multi-Source Discovery Strategy

The discovery subsystem operates across complementary channels to ensure zero blind spots in mapping the Arabic Forex Telegram ecosystem:

| Discovery Source | Technical Implementation | Discovery Focus |
|---|---|---|
| **Global Message Search** | Telethon `messages.SearchGlobalRequest` | Searches inside post content for specific strategy terms and signals. |
| **Hashtag Post Search** | Telethon `channels.SearchPostsRequest` | Tracks trending hashtags like `#ذهب`, `#فوركس`, `#XAUUSD`, `#SMC`. |
| **Similar Channel Recs** | Telethon `channels.GetChannelRecommendationsRequest` | Expands directly from verified high-tier trading channels. |
| **Multi-Edge Graph Crawl** | Message parsing (`t.me/` links, `@mentions`, ad exchange) | Traverses promotional and partner channel networks. |
| **Forward Origin Graph** | `message.fwd_from` origin header inspection | Unmasks root signal providers and syndication networks. |
| **Pluggable Web Scraper** | Google, Bing, DuckDuckGo, Telegram Directories | Indexes channels from external public web and trading blogs. |

---

## 2. Phase 1: Telegram Search Discovery Architecture

### A. Telegram Global Message Search (`app/discovery/telegram_global_search.py`)
- **API Call**: Telethon `messages.SearchGlobalRequest` (via `TelegramManager.search_global_messages`).
- **Content-Based Discovery**: Discovers channels based on trade setups inside post bodies (e.g. `XAUUSD BUY 2450 SL 2440 TP 2475`) even when channel titles contain no trading keywords (e.g. *"The Market Room"*).
- **Pagination & Checkpoints**: Checkpoints are stored atomically in Redis and persisted in PostgreSQL `discovery_checkpoints`. Resumes automatically across restarts using `offset_id`, `offset_rate`, and `page_number`.
- **Candidate Extraction**: Extracts `channel_id`, `username`, `title`, `matched_message_id`, `message_date`, and `post_text_preview`.

### B. Telegram Global Post Search (`app/discovery/telegram_post_search.py`)
- **API Call**: Telethon `channels.SearchPostsRequest` (via `TelegramManager.search_posts`).
- **Hashtag & Query Discovery**: Targets Arabic & English trading hashtags: `#ذهب`, `#فوركس`, `#تداول`, `#توصيات`, `#XAUUSD`, `#SMC`, `#ICT`, `#scalping`.
- **Graceful Fallback**: Detects unsupported or restricted post search requests and automatically falls back to `messages.searchGlobal` without interrupting workers or triggering retry storms.

### C. Shared Candidate Pipeline & Multi-Source Provenance
Both search engines feed the exact same downstream pipeline:
```
Telegram Global Search / Post Search
                ↓
    Extract Channel Candidates
                ↓
    Canonical Channel Resolution (@username / channel_id)
                ↓
    Multi-Source Deduplication (seen_channels & ProvenanceManager)
                ↓
    Redis Candidate Queue (queue:normal / queue:high)
                ↓
    Stage 1 Cheap Validation & Stage 2 Deep Scoring
```
- **Provenance Attributes**: Every candidate stores `source_type` (`telegram_global_search` / `telegram_search_posts`), `keyword`, `matched_message_id`, `discovery_count`, `first_seen_at`, and `last_seen_at`.

---

## 3. Arabic Keyword Taxonomy

The system organizes search queries into 9 distinct hierarchical categories defined in `app/discovery/taxonomy.py`:

```
KEYWORD_TAXONOMY
├── FOREX (Currency trading, technical analysis, lots, spreads, pips)
├── GOLD_XAUUSD (Gold signals, scalping, ounce pricing, yellow metal)
├── SMC_ICT (Smart money concepts, order blocks, FVG, liquidity sweeps)
├── TRADING_STYLES (Scalping, day trading, swing trading, indicators)
├── SIGNALS (Buy/Sell setups, targets, stop loss, profit taking)
├── BROKERS_PLATFORMS (MT4, MT5, Exness, XM, IC Markets, Islamic accounts)
├── PROP_FIRMS (Funded accounts, FTMO, FundedNext, evaluation challenges)
├── COMMERCIAL_SERVICES (VIP groups, account management, copy trading, IB)
└── CRYPTO_ARABIC (Binance, USDT, crypto futures, P2P exchange)
```

---

## 4. Arabic NLP Normalization & Query Mutation

Arabic Telegram channels frequently use various spellings, dialect markers, and decorative characters (diacritics and Tatweel). `app/discovery/arabic_normalizer.py` handles this with:

1. **Character Normalization**:
   - `[أ, إ, آ, ٱ] -> ا`
   - `[ى, ئ] -> ي`
   - `ة -> ه`
2. **Diacritics Removal**: Tanwin, Fathah, Dammah, Kasrah, Shaddah, Sukun (`[\u064B-\u0652\u0670]`).
3. **Tatweel Removal**: Kashida decorative letter elongations (`\u0640`).
4. **Controlled Query Variants**: Generates high-yield search variations (e.g. adding/removing `الـ`, combining with `XAUUSD` or `VIP`) to maximize recall without query explosion.

---

## 5. Small Channel & New Channel Prioritization

Traditional scrapers discard channels with few subscribers. In contrast, this engine applies:
- **Zero Minimum Subscriber Filter**: Channels with 100–500 subscribers are retained and evaluated purely on signal density and content quality.
- **Niche Signal Boost**: Active small channels with verified Forex/Gold setups receive up to `+50` bonus points on `new_channel_score`.
- **New Channel Boost**: Channels created within the last 30–90 days receive an automatic recency boost to accelerate discovery of high-growth newcomers.
