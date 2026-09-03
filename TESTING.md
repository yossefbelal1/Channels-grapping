# Testing Guide & Quality Assurance — Channels-grapping

## 1. Test Suite Overview

The test suite covers unit tests, regression tests, failure injection tests, and full end-to-end simulated discovery pipelines across all modules.

| Test File | Focus Area |
|---|---|
| `test_arabic_normalizer.py` | Arabic character normalization, Tashkeel/Tatweel stripping, query mutations. |
| `test_taxonomy.py` | Hierarchical keyword mapping and text classification across 9 categories. |
| `test_scoring_dimensions.py` | 13 scoring dimensions, small channel priority, new channel boost, anti-spam. |
| `test_graph_edges.py` | Multi-edge relationships (`mention`, `forwarded_from`, `promoted`, `linked`), upserts. |
| `test_forward_analyzer.py` | Forward origin header extraction and channel syndication summaries. |
| `test_activity_scheduler.py` | Channel activity classification (`HOT`/`WARM`/`COLD`/`DORMANT`) and scheduling. |
| `test_candidate_provenance.py` | Canonical handle resolution, multi-source provenance, and deduplication. |
| `test_contact_extractor_v2.py` | Structured contact parsing (owner, admin, WhatsApp, website, social links). |
| `test_e2e_discovery_pipeline.py` | Simulated end-to-end pipeline from search signal to CRM lead persistence. |
| `test_rate_limiter_regression.py` | Atomic sliding-window Lua rate limiter correctness. |
| `test_session_lock.py` | Distributed session locking and atomic release Lua scripts. |
| `test_outreach_*.py` | Risk scoring, adaptive throttling, circuit breakers, eligibility, and reconciliation. |

---

## 2. Running Automated Tests

Run the complete test suite:
```bash
python -m pytest tests/ -v
```

Run specific test modules:
```bash
# Test Arabic NLP & Taxonomy
python -m pytest tests/test_arabic_normalizer.py tests/test_taxonomy.py -v

# Test Multi-Dimensional Scoring Engine
python -m pytest tests/test_scoring_dimensions.py -v

# Test Graph Engine & Forward Analyzer
python -m pytest tests/test_graph_edges.py tests/test_forward_analyzer.py -v

# Test End-to-End Discovery Pipeline
python -m pytest tests/test_e2e_discovery_pipeline.py -v
```
