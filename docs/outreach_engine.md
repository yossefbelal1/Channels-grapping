# Outreach Engine — Architecture & Operations Guide

## Overview

The Risk-Aware Outreach Engine adds a comprehensive safety and reliability layer
to the campaign dispatch pipeline. It ensures that outreach messages are sent
only when the target lead is qualified, the sending account is healthy, and the
overall system is operating within safe parameters.

## Architecture

```
Discovery → Normalization → Deduplication → Qualification → Risk Scoring
     ↓
Eligibility Check → Outreach Queue → Rate Limiter → Telegram Send
     ↓
Result Classification → Account Health Update → Retry / Cooldown / Stop
```

## Delivery Semantics

**At-Least-Once with Deduplication**

The system guarantees that every eligible lead will be attempted at least once.
Redis idempotency tokens (`campaign:delivered:{campaign_id}:{lead_id}`) prevent
duplicate sends within a 30-day window.

The system does **NOT** guarantee Exactly-Once delivery. In crash scenarios
between Telegram accepting a message and the application recording success,
a message may theoretically be sent twice. The reconciliation system mitigates
this by checking idempotency tokens before re-attempting.

## Account Health State Machine

```
HEALTHY ──[FloodWait >60s]──→ DEGRADED
   │                              │
   │ [3 FloodWaits/30m]          │ [FloodWait]
   ↓                              ↓
DEGRADED ──[FloodWait]───→ COOLDOWN
                                  │
                            [FloodWait]
                                  ↓
                            RESTRICTED
                                  │
                            [auth_error]
                                  ↓
                            QUARANTINED
                                  │
                            [manual]
                                  ↓
                             DISABLED
```

### Send Permission
- **HEALTHY**: Full outreach allowed
- **DEGRADED**: Outreach allowed with increased pacing
- **COOLDOWN**: No outreach until cooldown expires
- **RESTRICTED**: No outreach, extended cooldown
- **QUARANTINED**: No outreach, requires manual review
- **DISABLED**: No outreach, manually disabled

## Risk Scoring (0-100)

| Factor | Weight | Source |
|--------|--------|--------|
| Account health score | 0-30 | Redis + DB |
| Recent FloodWait events | 0-30 | flood_wait_log |
| Account failure rate | 0-25 | account_health |
| Lead quality (inverse) | 0-20 | leads.lead_score |
| Previous failures to contact | 0-20 | campaign_logs |

### Risk Levels
- **LOW** (≤25): Normal queue priority
- **MEDIUM** (≤50): Reduced priority, longer pacing
- **HIGH** (≤75): Skipped in auto-dispatch, manual review
- **CRITICAL** (>75): Halt outreach from account

## Eligibility Checks (in order)

1. Valid contact username (not empty, not bot, not system keyword)
2. Not in blacklist
3. Lead status not 'rejected'
4. Not already contacted in this campaign
5. Contact username not already messaged via another lead
6. Per-lead cooldown check
7. No permanent failure history (3+ permanent failures)
8. Risk score not HIGH or CRITICAL

## Circuit Breakers

| Trigger | Threshold | Action |
|---------|-----------|--------|
| FloodWait spike | ≥3 in 30 min | Account → COOLDOWN |
| Error spike | ≥5 consecutive | Account → DEGRADED |
| Rejection spike | ≥10 in 1 hour | Campaign → PAUSED |
| Retry explosion | ≥5 for same lead | Lead → BLOCKED |
| Connectivity loss | Any | Worker → PAUSED |

## Adaptive Throttling

Replaces fixed `sleep(random(90, 210))` with EWMA-based controller:

- Success rate ≥95% + no FloodWaits → delay × 0.9 (speed up)
- Success rate ≥80% → delay × 0.95 (gentle speed up)
- Success rate ≥50% → delay × 1.1 (slow down)
- Success rate <50% → delay × 1.5 (aggressive slow down)
- Any FloodWait → delay × 2.0, minimum 300s

Bounds: [60s, 600s]

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTREACH_ENABLED` | `true` | Global kill switch |
| `OUTREACH_DRY_RUN` | `false` | Skip actual sends |
| `OUTREACH_CANARY_SIZE` | `5` | Canary batch size |
| `OUTREACH_MAX_RETRIES` | `3` | Max retries per delivery |
| `OUTREACH_LEAD_COOLDOWN_DAYS` | `30` | Days between contacts |
| `OUTREACH_RECONCILIATION_INTERVAL` | `300` | Reconciliation cycle (seconds) |

## Emergency Procedures

### Stop all outreach
```bash
# Via API
curl -X POST http://server:8000/api/outreach/emergency/stop -H "X-API-Key: YOUR_KEY"

# Via environment
OUTREACH_ENABLED=false docker compose up -d worker_validator
```

### Resume outreach
```bash
curl -X POST http://server:8000/api/outreach/emergency/resume -H "X-API-Key: YOUR_KEY"
```

### Disable specific account
```bash
curl -X POST http://server:8000/api/outreach/account/user_session/disable -H "X-API-Key: YOUR_KEY"
```

## Dry-Run Mode

Set `OUTREACH_DRY_RUN=true` to run the full pipeline without sending messages:
- Qualification runs normally
- Risk scoring runs normally
- Account selection runs normally
- Message validation runs normally
- Decision is logged but no Telegram message is sent
- Useful for testing campaign templates before going live

## Monitoring

### Dashboard Endpoints
- `GET /api/outreach/health` — Account health states
- `GET /api/outreach/metrics` — Pipeline metrics snapshot
- `GET /api/outreach/queue` — Queue depths
- `POST /api/outreach/emergency/stop` — Emergency stop
- `POST /api/outreach/emergency/resume` — Resume

### Key Metrics
- `outreach_attempts_total` — Total send attempts
- `outreach_success_total` — Successful deliveries
- `outreach_failures_total` — Failed deliveries
- `flood_wait_total` — FloodWait events
- `flood_wait_seconds_total` — Cumulative wait time
- `retry_total` — Retry attempts
- `unknown_delivery_total` — Unknown outcome deliveries

## Database Tables

### `account_health`
Tracks Telegram account state machine for outreach risk management.

### `flood_wait_log`
Historical log of all FloodWait events for trend analysis.

### `outreach_metrics`
Historical metrics for dashboards and trend analysis.

### Modified: `campaign_logs`
New columns: `delivery_id`, `attempt_count`, `last_attempt_at`, `next_attempt_at`,
`last_error`, `risk_level`, `account_used`, `eligibility`.

### Modified: `leads`
New columns: `risk_score`, `last_contact_at`, `next_eligible_at`, `contact_cooldown_days`.
