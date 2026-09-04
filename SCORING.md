# Scoring Engine — Channel Intelligence & Smart Ranking

## Core Principle

> **Subscriber count and activity are ranking/context signals, NOT hard qualification filters.**

The product goal is to discover and retain **Arabic Forex/Trading channels across the full size range** — from ~400 members to 2,000,000+ members.

A channel is **never rejected** merely because:
- It has few subscribers
- It has many subscribers
- It is currently low activity
- It posts infrequently
- It has not posted very recently

The **main qualification signal** is actual **Forex/Trading relevance** supported by evidence.

---

## Architecture Overview

```
Channel Candidate
      ↓
 Stage 1: Cheap Validation (metadata only)
      ↓
 Stage 2: Deep Multi-Dimensional Scoring
      ↓
 Classification + Tier Assignment
      ↓
 Evidence Persistence (PostgreSQL JSONB)
```

### Module Layout

| Module | Purpose |
|--------|---------|
| [`dimensions.py`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/app/scoring/dimensions.py) | `ScoringDimensions` dataclass + `calculate_all_dimensions()` — all scoring logic |
| [`engine.py`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/app/scoring/engine.py) | `LeadScoringEngine` with Stage 1 / Stage 2 evaluation + DB persistence |
| [`growth_analyzer.py`](file:///c:/Users/NV%20LAP/Downloads/Phone%20Link/Channels-grapping/app/scoring/growth_analyzer.py) | `GrowthAnalyzer` — observable member-count growth from historical snapshots |

---

## Scoring Dimensions (12+)

Every channel is evaluated across 12+ dimensions. Each dimension produces a score from **0 to 100**.

### Primary Trading Relevance Dimensions

| Dimension | Weight | Description |
|-----------|--------|-------------|
| `forex_score` | **28%** | Forex intent — currency pairs (`EURUSD`, `GBPUSD`, etc.), trading vocabulary, taxonomy matches. Per-post recurrence analysis prevents single-keyword false positives. |
| `gold_score` | **14%** | Gold/XAUUSD intent — gold-specific terms, `XAUUSD`, `ذهب` (Arabic for gold). Breadth + recurrence across posts. |
| `signal_score` | **14%** | Trading signals — `BUY`, `SELL`, `SL`, `TP`, `شراء`, `بيع`, `هدف`, `ستوب`. Detects structured trade setups. |
| `trading_score` | **10%** | Trading methodology — scalping, day trading, swing trading, SMC/ICT concepts, order blocks, FVG, liquidity sweeps. |
| `arabic_score` | **10%** | Arabic language presence — character ratio + Arabic Forex vocabulary hits. Mixed Arabic/English channels are supported. |

### Context & Metadata Dimensions

| Dimension | Weight | Description |
|-----------|--------|-------------|
| `new_channel_score` | **8%** | Recency bonus for newly created or newly discovered small channels with Forex/Gold/Signal relevance. |
| `activity_score` | **5%** | Posting velocity — posts per 24h/7d/30d. **Ranking signal only, never a gate.** Minimum baseline: 5. |
| `freshness_score` | **5%** | Time since last post. Channels that posted within 24h score 100; older channels score lower but are **never rejected**. |
| `growth_score` | **5%** | Observable member-count growth from historical snapshots. Neutral baseline (50) when unobserved. |
| `discovery_score` | **4%** | How many independent discovery sources found this channel. Multi-source channels score higher. |
| `commercial_score` | **3%** | VIP groups, account management, copy trading, prop firms, IB programs. Context for commercial Forex services. |
| `contact_score` | **2%** | Owner/admin contacts, WhatsApp, websites. Context signal; absence does not penalize. |

### Zero-Weight Metadata

| Field | Weight | Description |
|-------|--------|-------------|
| `member_count` | **0%** | Stored as metadata. **Zero direct weight.** Pure neutrality across 400 to 2,000,000 members. |

### Anti-Spam / Legitimacy

| Dimension | Role |
|-----------|------|
| `legitimacy_score` | Starts at 100, decremented by 35 for each spam phrase detected (`casino`, `كازينو`, `قمار`, `betting`, etc.). Applied as a multiplier to the final score. |

### Confidence Assessment

| Dimension | Role |
|-----------|------|
| `confidence_score` | How much evidence was available for the assessment. Based on: number of posts analyzed, Forex recurrence across posts, bio-level intent, and discovery source count. |

---

## Weighted Composite Formula

```
weighted_sum = (
    forex_score   × 0.28  +
    gold_score    × 0.14  +
    signal_score  × 0.14  +
    trading_score × 0.10  +
    arabic_score  × 0.10  +
    activity_score × 0.05 +
    freshness_score × 0.05 +
    growth_score  × 0.05  +
    discovery_score × 0.04 +
    commercial_score × 0.03 +
    contact_score × 0.02  +
    new_channel_score × 0.08
)

final_score = weighted_sum × (legitimacy_score / 100)
```

### Zero-Trading-Intent Damping

If a channel has **zero** Forex, Gold, Signal, or Trading intent (all relevant scores = 0 and no taxonomy matches), the `final_score` is **capped at 15** regardless of Arabic or activity scores. This prevents non-trading Arabic channels from receiving inflated scores.

---

## Classification System

Every channel receives one of four classifications based on its dimension scores:

| Classification | Criteria |
|----------------|----------|
| **HIGH_CONFIDENCE_FOREX** | `forex_score ≥ 60` AND `final_score ≥ 50` AND `arabic_score ≥ 15` |
| **LIKELY_FOREX** | `forex_score ≥ 35` OR `gold_score ≥ 40` OR `signal_score ≥ 40`, AND `final_score ≥ 35` |
| **POSSIBLE_FOREX** | Any trading dimension ≥ 15–20, AND `final_score ≥ 20` |
| **LOW_CONFIDENCE** | Insufficient evidence of Forex/Trading relevance |

---

## Tier Assignment

| Tier | Score Range | Typical Profile |
|------|-------------|-----------------|
| **Tier_A** | 75–100 | Active Arabic Forex channel with strong signal density, multiple currency pairs, recurring trade setups |
| **Tier_B** | 55–74 | Forex-relevant channel with moderate signal or gold/SMC focus |
| **Tier_C** | 35–54 | Likely or possible Forex channel with some trading indicators |
| **Tier_D** | 0–34 | Low evidence of Forex/Trading relevance |

---

## Per-Post Recurrence Analysis

A critical anti-false-positive mechanism. The scoring engine does **not** rely solely on aggregate keyword counts across all text. Instead, it tracks:

- `posts_with_forex` — how many distinct posts contain Forex terms or currency pairs
- `posts_with_signals` — how many distinct posts contain trade signal patterns (BUY/SELL/SL/TP)
- `posts_with_gold` — how many distinct posts mention gold/XAUUSD

### Isolated Single-Keyword Detection

If a channel has ≥5 recent posts but only **1 distinct Forex term** appearing in only **1 post** and **nothing in the bio**, it's flagged as `is_isolated_single_keyword` and the `forex_score` is capped at 15. This prevents a single casual mention of "trading" from inflating the score.

---

## Subscriber Count Policy

> **Subscriber count has 0% weight in the scoring formula.**

| Scenario | Behavior |
|----------|----------|
| Channel with 400 members posting daily Forex signals | ✅ Retained, scored on Forex relevance |
| Channel with 2,000,000 members posting Forex analysis | ✅ Retained, scored on Forex relevance |
| Channel with 50 members but genuine trade setups | ✅ Retained based on Forex relevance |
| Channel with 500,000 members but zero trading content | ❌ Low score due to zero trading intent damping |

---

## Activity Policy

> **Activity is a 5% ranking signal, never a gate.**

| Scenario | `activity_score` | Retained? |
|----------|------------------|-----------|
| 10+ posts per day | 80–100 | ✅ Yes |
| 1 post per day | 30–40 | ✅ Yes |
| 1 post per week | 10–20 | ✅ Yes |
| No posts in 30 days | 5 (baseline) | ✅ Yes, if Forex relevance exists |

The `activity_score` minimum is **5** (never 0), ensuring that even dormant channels with strong Forex relevance are retained.

---

## Growth Policy

Growth is measured from **observed historical snapshots** stored in `channel_snapshots`.

| Growth Scenario | `growth_score` |
|-----------------|----------------|
| ≥50% growth in ≤30 days | 95 |
| ≥25% growth in ≤14 days | 90 |
| ≥10% growth | 75 |
| Gentle positive growth | 50–70 |
| No observed snapshots (unobserved) | 0 (No artificial growth implied) |
| Minor decline (≤5%) | 45 |
| Sharp decline (>5%) | 10–50 |

---

## Freshness Policy

| Last Post Age | `freshness_score` |
|---------------|-------------------|
| ≤24 hours | 100 |
| ≤3 days | 80 |
| ≤7 days | 60 |
| ≤14 days | 45 |
| ≤30 days | 30 |
| >30 days | 15 |
| Unknown (using post count fallback) | 35–90 |

Boundary tolerance of 0.5 hours is applied (e.g., 24.5h, 72.5h) to avoid boundary-condition scoring issues.

---

## Evidence Persistence

Every scored channel has a JSONB `scoring_evidence` field persisted to PostgreSQL with full transparency:

```json
{
  "forex_terms_matched": ["فوركس", "تداول"],
  "currency_pairs_matched": ["xauusd", "eurusd"],
  "gold_terms_matched": ["ذهب"],
  "signals_terms_matched": ["شراء", "هدف"],
  "trading_styles_matched": [],
  "smc_ict_matched": [],
  "commercial_terms_matched": [],
  "arabic_character_ratio": 0.72,
  "arabic_vocabulary_hits": ["فوركس", "تداول", "ذهب", "توصيات"],
  "posts_analyzed": 20,
  "posts_with_forex": 12,
  "posts_with_signals": 8,
  "posts_with_gold": 6,
  "is_isolated_single_keyword": false,
  "member_count": 3200,
  "activity_metrics": {
    "posts_24h": 5,
    "posts_7d": 25,
    "posts_30d": 80,
    "avg_posts_per_day": 2.7
  },
  "freshness_hours": 2.3,
  "growth_analysis": {
    "status": "OBSERVED",
    "snapshot_count": 3,
    "member_count_t0": 2800,
    "member_count_t1": 3200,
    "growth_percentage": 14.29,
    "growth_score": 75
  },
  "discovery_sources": ["telegram_global_search", "graph_expansion"],
  "spam_penalties": [],
  "classification_reason": "Classified as HIGH_CONFIDENCE_FOREX with Forex=72, Arabic=85, Final=68"
}
```

---

## Database Schema (Phase 3 Additions)

### `leads` Table — New Columns

| Column | Type | Description |
|--------|------|-------------|
| `freshness_score` | `INT` | Freshness dimension score |
| `confidence_score` | `INT` | Evidence depth confidence |
| `classification` | `VARCHAR(50)` | `HIGH_CONFIDENCE_FOREX`, `LIKELY_FOREX`, `POSSIBLE_FOREX`, `LOW_CONFIDENCE` |
| `scoring_evidence` | `JSONB` | Full structured evidence dictionary |

### `channel_snapshots` Table — New Columns

| Column | Type | Description |
|--------|------|-------------|
| `lead_score` | `INT` | Composite score at snapshot time |
| `forex_score` | `INT` | Forex dimension at snapshot time |
| `activity_score` | `INT` | Activity dimension at snapshot time |
| `scores` | `JSONB` | All dimensions at snapshot time |

### Migration

Apply via:
```sql
psql -U postgres -d leadhunter_db -f migrate_v6_channel_intelligence.sql
```

---

## Arabic NLP Integration

The scoring engine uses the Arabic NLP pipeline from `app/discovery/arabic_normalizer.py`:

- **Character normalization**: `[أ, إ, آ, ٱ] → ا`, `[ى, ئ] → ي`, `ة → ه`
- **Diacritics removal**: Tanwin, Fathah, Dammah, etc.
- **Tatweel removal**: Kashida elongations

### Arabic Forex Vocabulary

The following Arabic terms are recognized as Forex-specific vocabulary (contributing to `arabic_score` when found alongside Arabic character ratio):

| Arabic | English |
|--------|---------|
| فوركس | Forex |
| تداول | Trading |
| ذهب / الذهب | Gold |
| عملات | Currencies |
| توصيات | Recommendations/Signals |
| تحليل | Analysis |
| صفقة / صفقات | Trade(s) |
| شراء / بيع | Buy / Sell |
| هدف | Target |
| وقف الخسارة | Stop Loss |
| ستوب | Stop |
| لوت / بيب / نقطة | Lot / Pip / Point |
| رافعة مالية | Leverage |
| سبريد | Spread |
| حساب ممول | Funded Account |
| إدارة محافظ | Portfolio Management |
| نسخ صفقات | Copy Trading |

---

## Testing

The scoring engine is validated with 19+ test scenarios covering:

1. Strong Arabic Forex channel (HIGH_CONFIDENCE, Tier_A/B)
2. Gold-specific XAUUSD channel
3. Signals-focused channel
4. Mixed Arabic/English channel
5. Low activity but relevant channel (must NOT be rejected)
6. Meme/entertainment channel (zero-trading damping)
7. Very small channel with Forex relevance (new_channel_score bonus)
8. Large channel with Forex relevance (no subscriber-count ceiling)
9. Growth detection from snapshots
10. Freshness boundary thresholds
11. Commercial/prop firm context
12. Multi-source discovery boost
13. Spam/casino penalty
14. Isolated single-keyword false positive prevention
15. New channel recency bonus
16. Pure English trading channel (lower Arabic score)
17. Crypto-focused channel
18. Full scenario end-to-end fixture

Run tests:
```bash
python -m pytest tests/test_phase3_channel_intelligence.py -v
```
