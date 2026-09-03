# Manual Real-Telegram Smoke Test & Verification Runbook

This guide provides step-by-step instructions for performing manual, real-world smoke tests on a live Telegram account without exposing sensitive production credentials in the repository.

---

## 1. Prerequisites & Environment Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Configure credentials in `.env`:
   ```ini
   TELEGRAM_API_ID=your_api_id
   TELEGRAM_API_HASH=your_api_hash
   TELEGRAM_PHONE=+your_phone_number
   SESSION_NAME=user_session
   REDIS_HOST=localhost
   REDIS_PORT=6379
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=leadhunter_db
   DB_USER=postgres
   DB_PASSWORD=your_password
   ```
3. Start Redis and PostgreSQL instances:
   ```bash
   docker-compose up -d redis postgres
   ```
4. Apply database schema migrations:
   ```bash
   psql -U postgres -d leadhunter_db -f schema.sql
   psql -U postgres -d leadhunter_db -f migrate_v5_graph_engine.sql
   ```

---

## 2. Step-by-Step Live Verification Procedures

### Step A: Global Content-Based Message Search
Verify that channels publishing Forex signals in their posts (even with non-Forex titles) are discovered.

```bash
python -c "
import asyncio
from tg_manager import TelegramManager

async def test_search():
    tg = TelegramManager()
    res = await tg.search_global_messages(query='XAUUSD BUY')
    print(f'Found {len(res.messages)} messages and {len(res.chats)} channels.')
    for c in res.chats[:5]:
        print(f' - @{getattr(c, \"username\", \"none\")}: {c.title}')

asyncio.run(test_search())
"
```
**Expected Outcome**: Returns a list of public Telegram channels where posts mention `XAUUSD BUY`.

---

### Step B: Hashtag Post Search (`channels.searchPosts`)
Verify hashtag tracking for Arabic trading terms:

```bash
python -c "
import asyncio
from tg_manager import TelegramManager

async def test_hashtags():
    tg = TelegramManager()
    res = await tg.search_posts(hashtag='ذهب')
    print(f'Found {len(res.messages)} posts for hashtag #ذهب.')

asyncio.run(test_hashtags())
"
```
**Expected Outcome**: Finds posts tagged with `#ذهب` and extracts origin channel entities.

---

### Step C: Similar Channel Recommendations Expansion
Verify graph expansion from top-tier trading hubs:

```bash
python -c "
import asyncio
from tg_manager import TelegramManager

async def test_recs():
    tg = TelegramManager()
    res = await tg.get_channel_recommendations(channel_peer='ForexArabic')
    print(f'Recommended channels: {len(res.chats)}')
    for c in res.chats:
        print(f' -> @{getattr(c, \"username\", \"none\")}: {c.title}')

asyncio.run(test_recs())
"
```
**Expected Outcome**: Discovers structurally and semantically related trading channels recommended by Telegram.

---

### Step D: Multi-Edge Graph & Forward Origin Analysis
Verify forward header inspection:

```bash
python -c "
import asyncio
from tg_manager import TelegramManager
from app.graph.forward_analyzer import ForwardAnalyzer

async def test_forwards():
    tg = TelegramManager()
    client = list(tg.clients.values())[0]
    msgs = await client.get_messages('ForexArabic', limit=30)
    summary = ForwardAnalyzer.summarize_forwards(msgs)
    print('Forward summary:', summary)

asyncio.run(test_forwards())
"
```
**Expected Outcome**: Extracts `fwd_from` origin channels and computes channel syndication ratios.

---

### Step E: Small & New Channel Prioritization Verification
Verify that channels with 100–500 subscribers are retained and scored with high priority:

```bash
python -c "
from app.scoring.engine import LeadScoringEngine
from datetime import datetime, timezone, timedelta

scores = LeadScoringEngine.evaluate_stage_2(
    title='نادي الذهب الخاص',
    description='صفقات سكالبينج يومية XAUUSD. للتواصل: @GoldTrader',
    recent_posts=['صفقة شراء ذهب 2650 الهدف 2680'],
    member_count=250, # Small niche channel
    has_contact=True,
    creation_date=datetime.now(timezone.utc) - timedelta(days=15)
)

print(f'Final Score: {scores.final_score} | Tier: {scores.tier} | NewChannelScore: {scores.new_channel_score}')
assert scores.final_score >= 50
assert scores.tier in ['Tier_A', 'Tier_B', 'Tier_C']
print('PASS: Small channel was successfully retained and boosted!')
"
```
**Expected Outcome**: High tier assignment (`Tier_A` / `Tier_B`) despite low member count.

---

## 3. Known Telegram API Limitations & Mitigation Strategy

1. **`FloodWaitError`**:
   - *Limitation*: Exceeding request frequency results in temporary Telegram cooldowns.
   - *Mitigation*: Sliding-window Lua rate limiting (max 300 req/hr per session) with automatic failover to alternative accounts in `tg_manager.py`.
2. **`GetChannelRecommendationsRequest` Limit**:
   - *Limitation*: Telegram limits recommendation requests to a small batch per channel.
   - *Mitigation*: Triggered only for qualified `Tier_A` and `Tier_B` channels via `recommendations:queue`.
3. **Restricted Search Queries**:
   - *Limitation*: Certain hashtags may return empty sets if regional restrictions apply.
   - *Mitigation*: Fallback to `messages.searchGlobal` using normalized keyword variants generated by `arabic_normalizer.py`.
