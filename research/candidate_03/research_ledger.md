# Candidate C003: Research Ledger

**Strategy Name**: Session Open Range Breakout (SORB)
**Candidate ID**: C003
**Research Phase**: Phase 1 — Research Only
**Created**: 2026-07-01
**Status**: `RESEARCH`

---

## Current Status

| Field | Value |
| :--- | :--- |
| Current Stage | Stage 0 — Research & Specification |
| Current Status | `RESEARCH` |
| Last Updated | 2026-07-01 |
| Author | QRP Research |

---

## Phase Definitions

| Phase | Name | Gate Criteria |
| :--- | :--- | :--- |
| **Phase 0** | Research & Specification | Documents complete, hypothesis locked |
| **Phase 1** | Discovery Sweep | Sharpe ≥ 0.8, DrawDown ≤ 35%, Trades ≥ 50 |
| **Phase 2** | Walk-Forward Validation | OOS Sharpe ≥ 0.7, Trades ≥ 30 in both holdouts |
| **Phase 3** | Final Validation | Monte Carlo ruin ≤ 10%, correlation with C001 < 0.4 |
| **Phase 4** | Paper Trading | Live forward test, minimum 30 days |
| **Phase 5** | Production | Capital allocation approved by QRP committee |

---

## Key Documents

| Document | Path | Status |
| :--- | :--- | :--- |
| Literature Review | `research/candidate_03/reports/literature_review.md` | ✅ Complete |
| Objective Definition | `research/candidate_03/objective_definition.md` | ✅ Complete |
| Research Hypothesis | `research/candidate_03/research_hypothesis.md` | ✅ Complete |
| Parameter Space | `research/candidate_03/parameter_space.md` | ✅ Complete |
| Candidate Variants | `research/candidate_03/candidate_variants.md` | ✅ Complete |
| Strategy Code | `research/candidate_03/code/` | 🔲 Pending (Phase 1) |
| Discovery Config | `research/candidate_03/configs/` | 🔲 Pending (Phase 1) |
| Discovery Results | `research/candidate_03/outputs/` | 🔲 Pending (Phase 1) |
| Discovery Analysis | `research/candidate_03/reports/discovery_analysis.md` | 🔲 Pending (Phase 1) |
| Walk-Forward Results | `research/candidate_03/reports/walk_forward_report.md` | 🔲 Pending (Phase 2) |

---

## Key Assumptions

1. **Session Volume is Measurable**: Intraday session volumes can be calculated from standard 15m OHLCV data using the sum of volumes within the Open Range window.
2. **Sessions are Fixed**: London open is consistently 07:00 UTC and New York open is 13:00 UTC. No Daylight Saving Time adjustments are required since crypto markets are UTC-based.
3. **Asset Participation**: All 25 assets in our fixed universe participate meaningfully at London and New York opens (they all have sufficient liquidity at these hours).
4. **Fee Model Unchanged**: Taker fees 0.045%, slippage 0.05% — identical to C001 and C002 for comparability.
5. **No Look-Ahead Bias**: Open Range boundaries are computed using only candles that are fully closed before the breakout trigger candle opens.

---

## Locked Hypotheses

| # | Hypothesis | Status |
| :--- | :--- | :--- |
| H1 | Long entry above Open Range High at session open produces positive expectancy net of fees | 🔒 Locked |
| H2 | Volume filter improves the Sharpe Ratio of H1 trades | 🔒 Locked |
| H3 | Trend filter (EMA50) further improves Sharpe and reduces drawdown | 🔒 Locked |
| H0 | Null hypothesis: breakout is indistinguishable from random walk | 🔒 Locked |

---

## Outstanding Questions

1. How do crypto exchange maintenance windows (typically 00:00–01:00 UTC on weekends) affect the London session data continuity?
2. Do high-impact macro events (FOMC, CPI releases) cause disproportionate false SORB breakouts that should be filtered?
3. Does the optimal Open Range width vary significantly by asset volatility regime (e.g., BTC vs. altcoins)?
4. Can session-level volume data be accurately aggregated from the existing data infrastructure (15m OHLCV) without additional data feeds?

---

## Research Log

| Date | Stage | Action | Decision / Notes |
| :--- | :--- | :--- | :--- |
| 2026-07-01 | Phase 0: Research | Literature review completed | 10 approaches evaluated; SORB ranked #1. Selected as C003. |
| 2026-07-01 | Phase 0: Research | All specification documents created | `objective_definition.md`, `research_hypothesis.md`, `parameter_space.md`, `candidate_variants.md` completed. |
| 2026-07-01 | Phase 0: Research | Hypothesis locked | H1, H2, H3 formally locked. No modifications without ledger entry. |
| | Phase 1: Discovery | Discovery Sweep | _Pending implementation approval_ |

---

## Decisions Requiring Approval Before Phase 1

Before any implementation code is written, the following must be confirmed:

1. ✅ Hypothesis and parameter space approved by researcher.
2. ⬜ Confirm the research engine supports intraday session time filtering (07:00 UTC, 13:00 UTC).
3. ⬜ Confirm 15m OHLCV data is available and clean for all 25 assets in the universe.
4. ⬜ Approve the Discovery Sweep grid (432 configurations baseline sweep).
5. ⬜ Confirm fee model is unchanged from C001 and C002.
