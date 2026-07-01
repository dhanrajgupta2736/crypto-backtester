# Candidate C003: Objective Definition

**Strategy Name**: Session Open Range Breakout (SORB)
**Candidate ID**: C003
**Research Phase**: Phase 1 — Research Only
**Created**: 2026-07-01
**Status**: `RESEARCH`

---

## 1. Research Objective

Discover a statistically robust, long-only intraday market inefficiency anchored to major session opens (London and New York) in the cryptocurrency perpetual futures market.

The objective is to determine whether directional price expansions generated during the first 60 minutes of a session open can be systematically captured with a long breakout entry rule and provide risk-adjusted returns that are uncorrelated with C001 and C002.

---

## 2. Target Inefficiency

### Economic Hypothesis
Regional equity, commodity, and FX session opens generate predictable surges in institutional order flow and market-maker re-hedging activity. In cryptocurrency perpetual markets, this manifests as:

1. **Volume spikes** at the London open (07:00 UTC) and New York open (13:00 UTC).
2. **Directional expansion** above or below the prior session's establishing range (Open Range = first 60 minutes of session).
3. **Continuation bias** following the breakout, driven by systematic execution algorithms, stop-runs, and momentum-chasing capital.

### Why This Works in Crypto
- Crypto markets operate 24/7, meaning session transitions produce identifiable volume regimes rather than price gaps.
- Institutional crypto desks (market makers, hedge funds) re-balance at session opens, creating predictable directional drives.
- The perpetual funding rate mechanism creates additional incentive for directional positioning at liquid intervals.

---

## 3. Performance Targets

| Metric | Target (Discovery) | Target (Walk-Forward) |
| :--- | :---: | :---: |
| Annualized Sharpe Ratio | ≥ 0.8 | ≥ 0.7 |
| Maximum Drawdown | ≤ 35% | ≤ 40% |
| Annual Return | ≥ 25% | ≥ 20% |
| Win Rate | ≥ 45% | ≥ 42% |
| Profit Factor | ≥ 1.4 | ≥ 1.3 |
| Minimum Trade Count (per period) | ≥ 50 | ≥ 30 |

---

## 4. Constraints

| Constraint | Value |
| :--- | :--- |
| Trade Direction | Long-Only |
| Asset Universe | Fixed 25 crypto perpetuals |
| Execution | Next-candle open (closed-candle signal) |
| Fee Model | Taker 0.045%, Slippage 0.05% (same as C001/C002) |
| Short Selling | Forbidden in C003 (reserved for C003-S) |
| Indicator Stacking | Forbidden during Discovery Phase |
| Max Holding Period | 1 session (approximately 4-8H) |

---

## 5. Success Criteria for Phase Promotion

| Gate | Requirement |
| :--- | :--- |
| Discovery | ≥ 1 configuration passing Sharpe ≥ 0.8, Drawdown ≤ 35%, Trade Count ≥ 50 |
| Walk-Forward | OOS Sharpe ≥ 0.7 in both Holdout windows, Trade Count ≥ 30 |
| Final Validation | Monte Carlo ruin probability ≤ 10%, daily correlation with C001 < 0.4 |

---

## 6. Diversification Objective

C003 must be designed so its daily return stream has a **Pearson correlation of ≤ 0.40** with C001 (4H Relative Strength) and C002 (4H VCP) — confirming it provides meaningful diversification in a future combined portfolio.

---

## 7. Out-of-Scope for This Phase

- No trading code.
- No backtesting execution.
- No live or paper trading.
- No short version (C003-S) — reserved for future phase.
