# Research Hypothesis — Candidate C002 Version 2

## 1. Core Hypothesis
The primary hypothesis of Version 2 is:
> *Reducing the swing detection window (from 7 bars to 3 or 5 bars) will shorten the duration and size of the consolidation patterns required to trigger a VCP signal. This will significantly increase the trade density (achieving the $\ge 30$ trade threshold per fold) without eroding the strategy's edge (Sharpe Ratio and Max Drawdown), because the structural mechanics of trend filtering (HH_HL) and swing-based risk management (Swing_Trail) will remain active to filter out poor breakouts and cap losses.*

To keep the research strictly interpretable and isolate the causal impact of this single change, all other strategy parameters are locked to the V1 optimal baseline (`C002-E04426` parameters).

---

## 2. Comparison of V1 and V2 Assumptions

### A. Unchanged Assumptions:
1. **Trend Regime Alignment**: We assume that trading VCP consolidations is only profitable in structural uptrends. The `HH_HL` trend gate remains the baseline regime filter.
2. **Pattern Complexity**: Contraction waves remain locked at exactly `3` waves, and apex tightness remains locked at `0.05` (5%).
3. **Execution, Sizing, and Buffers**: We assume transaction fees and slippage are unchanged, portfolio sizing is locked at $K = 3$, and the stop buffer is locked at `0.0`.
4. **Breakout Confirmation**: We assume that entry signals require price confirmation on a candle close above the consolidation swing high (`Close_Above_Swing_High`).
5. **Universe Coverage**: The 25-coin universe remains the baseline. No coins are blacklisted, as coin-level data is considered low-sample.

### B. Changed Assumptions:
1. **Swing Granularity**:
   * *V1 Assumption*: Swings must be defined by at least 7 bars of market structure to represent significant key levels.
   * *V2 Assumption*: Shorter structures (3 to 5 bars) define valid consolidation swings and allow the VCP pattern to identify high-quality breakouts on smaller scales.
2. **Lower Timeframe Viability**:
   * *V1 Assumption*: Timeframe analysis includes 15m, 1H, and 4H.
   * *V2 Assumption*: 15m is rejected due to excessive fee friction. Only 1H and 4H timeframes are evaluated.

---

## 3. Evidence Support from Version 1 Results

The shift in assumptions is directly supported by the findings in the V1 research cycle:

### A. Support from V1 Walk-Forward & Discovery:
* **Friction and Selection Sharpe**: V1 demonstrated that the `HH_HL` trend filter and `Swing_Trail` exit successfully managed drawdowns below `10%` across all folds while maintaining high Sharpe ratios (`1.92` in Holdout 1). This proves that the strategy's risk management engine is highly robust.
* **Trade Count Bottleneck**: The strategy failed validation solely because of low trade counts (Selection: 16, Holdout 2: 1). This indicates that the entry signal generation was the primary bottleneck. Reducing the swing window from 7 to 3 or 5 directly addresses this entry bottleneck.

### B. Support from V1 Trade Elimination Analysis:
* The V1 trade elimination study showed that:
  * Requiring 3 contraction waves instead of 2 reduced average trades by **70.7%**.
  * The `HH_HL` trend filter reduced average trades by **66.7%**.
* Since we must keep the `HH_HL` trend gate and `contraction_waves = 3` to preserve V1 baseline risk management and pattern logic, we cannot relax them. Therefore, we must relax the swing window to generate sufficient trades.

### C. Support from V1 Coin Attribution:
* The V1 coin attribution study showed that 17 out of 25 coins generated exactly 0 trades. This means that the pattern-matching rules were so strict that most coins never formed a VCP pattern that met the 7-bar swing requirements.
* Relaxing the swing window to 3 or 5 bars will allow the non-traded assets to form valid contraction patterns, broadening the active asset base and increasing overall portfolio diversification.
