# Candidate C003: Research Hypothesis

**Strategy Name**: Session Open Range Breakout (SORB)
**Candidate ID**: C003
**Research Phase**: Phase 1 — Research Only
**Created**: 2026-07-01
**Status**: `HYPOTHESIS_DEFINED`

---

## 1. Primary Hypothesis

> **H1**: In cryptocurrency perpetual futures markets, a long position entered when price breaches the upper boundary of the first 60-minute candle range of the London (07:00 UTC) or New York (13:00 UTC) session open will produce statistically significant positive returns over the next 4–8 hours, net of trading fees and slippage.

This hypothesis asserts that institutional order flow injected at session opens creates a measurable and tradable price expansion that persists long enough to capture meaningful profit.

---

## 2. Secondary Hypothesis (Volume Confirmation)

> **H2**: The positive returns in H1 are significantly improved when the session's first candle has above-average volume relative to a 20-session lookback, confirming the presence of genuine institutional participation rather than thin-market noise.

This tests whether volume filtering removes low-conviction breakouts that historically fail.

---

## 3. Tertiary Hypothesis (Trend Alignment)

> **H3**: The SORB edge is strongest when the asset is in a structural uptrend, defined as the closing price above its 50-period EMA on the session timeframe. Taking SORB longs only in trending assets improves the Sharpe ratio and reduces maximum drawdown compared to an unconditional SORB.

This tests whether macro trend alignment acts as a quality filter.

---

## 4. Null Hypothesis

> **H0**: Price breakouts above the Open Range boundary at session opens in cryptocurrency perpetual markets are statistically indistinguishable from random walk, producing no positive expectancy net of fees.

The research must reject H0 to justify advancement to Walk-Forward Validation.

---

## 5. Statistical Validation Framework

The hypothesis will be tested under the following framework:

### 5.1 Independence of Observations
Each session open is treated as a new, independent experiment. Assets in the universe are tested independently and then combined across assets to measure portfolio-level expectancy.

### 5.2 Minimum Sample Size
- Minimum 100 completed trades per configuration per holdout period.
- Minimum 200 completed trades in the Discovery period.

### 5.3 Significance Test
- Bootstrapped p-value of trade returns < 0.05 (one-tailed, testing for positive mean return).
- Sharpe Ratio > 0.8 after 1000-sample Monte Carlo permutation test (null: random entry at same time of day with random direction).

### 5.4 Anti-Overfitting Validation
- Walk-Forward validation with 2 non-overlapping Out-of-Sample holdout windows.
- Monte Carlo simulation with 500+ iterations of randomised entry permutations to establish a t-statistic for the edge.

---

## 6. Key Causal Mechanisms

### 6.1 Institutional Order Flow Injection
At major session opens, institutional desks receive new mandates (macro data releases, Asia-Europe handover, US pre-market signals) and execute algorithmic orders in large size. This concentrated buying pressure in thin liquidity produces rapid, persistent directional expansion.

### 6.2 Stop Hunt and Continuation
Market makers identify and clear pending stop orders above the session open range before initiating the directional leg. This creates the "false break and continuation" pattern seen frequently in forex and crypto sessions.

### 6.3 Systematic Algorithm Alignment
Trend-following CTAs and stat-arb systems monitor session opens as a time-anchored trigger. Their simultaneous execution creates self-reinforcing price expansion once the range is cleared.

### 6.4 Perpetual Funding Incentive
During highly positive funding rate environments, longs pay shorts continuously. At session opens, market makers reduce short exposure, removing resistance and enabling cleaner breakout moves in the upward direction.

---

## 7. Expected Failure Modes

| Failure Mode | Description | Mitigation |
| :--- | :--- | :--- |
| Chop regime whipsaw | Range expansion fails; price collapses back through the open range | ATR-based minimum range width filter |
| News-driven false breakout | Macro news spike creates a brief breakout that immediately reverses | Avoid entries within 5 minutes of scheduled high-impact news (optional extension) |
| Low-volume session | Insufficient participation; range extends but fails to sustain | Volume filter (H2) |
| Fee erosion on frequent small wins | High trade frequency + small per-trade gains consumed by fees | Minimum range/ATR ratio on entry threshold |
| Structural bear market | Downtrend reversal of long positions into session opens | Trend filter (H3); drawdown controls |

---

## 8. Relationship to Existing Candidates

| Candidate | Timeframe | Holding Period | Core Mechanism | Correlation Expectation |
| :--- | :---: | :---: | :--- | :---: |
| C001 — Relative Strength | 4H | 1–5 days | Cross-sectional trend ranking | Low (< 0.4) |
| C002 — VCP | 4H | 1–4 weeks | Chart pattern contraction breakout | Low (< 0.35) |
| **C003 — SORB** | 15m / 1H | 4–8 hours | Session open range breakout | — |

C003 is operationally independent of both C001 and C002:
- C001 enters based on 4H ranking cycles; C003 enters based on intraday session timing.
- C002 enters based on multi-week chart structures; C003 entries are reset every session.
- C003's intraday holding period means its trade outcomes will be largely uncorrelated with C001's and C002's multi-day returns.

---

## 9. Hypothesis Locking Statement

This hypothesis is **LOCKED** for research phase. No modifications to the primary hypothesis may be made after this document is committed without a formal research ledger entry documenting the decision and its rationale.
