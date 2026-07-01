# Research Hypothesis — Candidate C002 Version 3

## 1. Core Hypothesis
The primary hypothesis of Version 3 is:
> *Varying the contraction wave structure from exactly 3 waves to exactly 2 waves or an adaptive wave count (2 or more waves) will significantly increase the trade density (achieving the $\ge 30$ trade threshold per fold) while preserving the strategy's expectancy and low drawdown edge. Adaptive wave counts (`contraction_waves = "adaptive"`) will outperform a fixed 2-wave or 3-wave system because it dynamically captures high-conviction 3-wave setups when they form, while falling back to 2-wave structures during less compressed market phases, maximizing trade density without sacrificing quality.*

---

## 2. Comparison of V1 and V3 Assumptions

### A. Unchanged Assumptions:
1. **Trend Regime Alignment**: We assume that trading VCP consolidations is only profitable in structural uptrends. The `HH_HL` trend gate remains the baseline regime filter.
2. **Swing Granularity**: The swing detection window is locked to `7` bars (identical to V1 baseline).
3. **Apex Tightness**: The final compression tightness is locked to `0.05` (5%).
4. **Execution, Sizing, and Buffers**: We assume transaction fees and slippage are unchanged, portfolio sizing is locked at $K = 3$, and the stop buffer is locked at `0.0`.
5. **Breakout Confirmation**: We assume that entry signals require price confirmation on a candle close above the consolidation swing high (`Close_Above_Swing_High`).
6. **Universe Coverage**: The 25-coin universe remains the baseline. No coins are blacklisted.

### B. Changed Assumptions:
1. **Pattern Wave Complexity**:
   * *V1 Assumption*: The strategy requires exactly 3 waves of contraction (control) to enter a trade.
   * *V3 Assumption*: Contraction complexity can be variable. Shorter 2-wave contractions or a dynamically adaptive wave count (2 or more waves) represent valid volatility contraction structures.
2. **Lower Timeframe Viability**:
   * *V1 Assumption*: Timeframe analysis includes 15m, 1H, and 4H.
   * *V3 Assumption*: 15m is rejected due to excessive fee friction. Only 1H and 4H timeframes are evaluated.

---

## 3. Evidence Support from Version 1 Results

The shift in assumptions is directly supported by the findings in the V1 research cycle:

### A. Support from V1 Discovery:
* In the V1 trade elimination analysis, changing from exactly 2 contraction waves to exactly 3 contraction waves reduced the average trade count from **23,989** to **7,020** (a **70.7% drop**).
* This empirical result proves that contraction waves are the single most restrictive pattern constraint. Changing this parameter directly targets the trade density bottleneck.

### B. Support from V1 Walk-Forward:
* The V1 walk-forward results showed that configuration `C002-E04426` (which used 3 contraction waves) achieved a massive Sharpe of 1.92 out-of-sample but only generated 71 trades over 3 years. This indicates that while 3 waves provide extremely high conviction and excellent risk control, it is too restrictive for walk-forward density gates. Comparing this to a 2-wave and adaptive setup is the logical next step.
* By using an adaptive setup, we can capture the high performance of 3-wave setups (Sharpe 1.30) while filling the gaps with 2-wave setups to satisfy density requirements.
