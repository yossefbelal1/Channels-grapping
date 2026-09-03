# Discovery Engine & Taxonomy Guide — Channels-grapping

## 1. Multi-Source Discovery Strategy

The discovery subsystem operates across 6 complementary channels to ensure zero blind spots in mapping the Arabic Forex Telegram ecosystem:

| Discovery Source | Technical Implementation | Discovery Focus |
|---|---|---|
| **Global Message Search** | Telethon `messages.SearchGlobalRequest` | Searches inside post content for specific strategy terms and signals. |
| **Hashtag Post Search** | Telethon `channels.SearchPostsRequest` | Tracks trending hashtags like `#ذهب`, `#فوركس`, `#XAUUSD`, `#SMC`. |
| **Similar Channel Recs** | Telethon `channels.GetChannelRecommendationsRequest` | Expands directly from verified high-tier trading channels. |
| **Multi-Edge Graph Crawl** | Message parsing (`t.me/` links, `@mentions`, ad exchange) | Traverses promotional and partner channel networks. |
| **Forward Origin Graph** | `message.fwd_from` origin header inspection | Unmasks root signal providers and syndication networks. |
| **Pluggable Web Scraper** | Google, Bing, DuckDuckGo, Telegram Directories | Indexes channels from external public web and trading blogs. |

---

## 2. Arabic Keyword Taxonomy

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

## 3. Arabic NLP Normalization & Query Mutation

Arabic Telegram channels frequently use various spellings, dialect markers, and decorative characters (diacritics and Tatweel). `app/discovery/arabic_normalizer.py` handles this with:

1. **Character Normalization**:
   - `[أ, إ, آ, ٱ] -> ا`
   - `[ى, ئ] -> ي`
   - `ة -> ه`
2. **Diacritics Removal**: Tanwin, Fathah, Dammah, Kasrah, Shaddah, Sukun (`[\u064B-\u0652\u0670]`).
3. **Tatweel Removal**: Kashida decorative letter elongations (`\u0640`).
4. **Controlled Query Variants**: Generates high-yield search variations (e.g. adding/removing `الـ`, combining with `XAUUSD` or `VIP`) to maximize recall without query explosion.

---

## 4. Small Channel & New Channel Prioritization

Traditional scrapers discard channels with few subscribers. In contrast, this engine applies:
- **Zero Minimum Subscriber Filter**: Channels with 100–500 subscribers are retained and evaluated purely on signal density and content quality.
- **Niche Signal Boost**: Active small channels with verified Forex/Gold setups receive up to `+50` bonus points on `new_channel_score`.
- **New Channel Boost**: Channels created within the last 30–90 days receive an automatic recency boost to accelerate discovery of high-growth newcomers.
