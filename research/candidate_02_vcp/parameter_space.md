# Candidate 02 — VCP Parameter Space

This document defines the parameter space for the systematic Volatility Contraction Pattern (VCP) strategy. The parameters are divided into functional groups (Trend, Contraction, Breakout, Exit, and Portfolio) and structured for discovery sweeps.

---

## 1. Parameter Sweep Grid

| Parameter | Code Symbol | Type | Range / Options | Baseline | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Trend Filter Type** | `trend_type` | Categorical | `['EMA_Structure', 'Regression_Slope', 'None']` | `EMA_Structure` | Method used to confirm the primary Stage 2 uptrend. |
| **EMA Short Period** | `ema_short` | Integer | `[20, 50, 100]` | `50` | Fast EMA period for trend check. |
| **EMA Medium Period** | `ema_med` | Integer | `[50, 100, 150]` | `150` | Medium EMA period for trend check. |
| **EMA Long Period** | `ema_long` | Integer | `[100, 150, 200]` | `200` | Slow EMA period for trend check. |
| **Reg. Slope Period** | `reg_len` | Integer | `[30, 60, 90, 120]` | `60` | Lookback for linear regression slope. |
| **Reg. R-Squared Gate** | `reg_r2` | Float | `[0.10, 0.20, 0.30]` | `0.15` | Minimum $R^2$ to accept a regression trend. |
| **Swing Window** | `swing_window` | Integer | `[3, 5, 8, 12]` | `5` | Window radius $W_s$ for local high/low detection. |
| **Required Contractions** | `num_contractions` | Integer | `[2, 3, 4]` | `3` | Required number of contraction waves ($K$). |
| **Max Apex Tightness** | `max_tightness` | Float | `[0.02, 0.04, 0.06, 0.08]` | `0.05` | Maximum depth of the final pullback ($D_K$). |
| **Breakout Target** | `breakout_target` | Categorical | `['Pivot_High', 'Absolute_High']` | `Pivot_High` | Resistance level defining the breakout threshold. |
| **Breakout Trigger Type** | `trigger_type` | Categorical | `['High_Breach', 'Close_Breach']` | `Close_Breach` | Whether breakout is on intraday breach or close. |
| **Stop Loss Type** | `stop_type` | Categorical | `['Swing_Low', 'ATR_Stop']` | `Swing_Low` | Stop loss calculation method. |
| **Stop Buffer** | `stop_buffer` | Float | `[0.00, 0.05, 0.10]` | `0.05` | Buffer subtracted from swing low (in % or ATR). |
| **ATR SL Multiplier** | `atr_sl_mult` | Float | `[1.5, 2.0, 2.5, 3.0]` | `2.0` | Multiplier for ATR-based stop. |
| **Exit Type** | `exit_type` | Categorical | `['Fixed_RR', 'Trailing_EMA', 'No_TP']` | `Fixed_RR` | Position exit methodology. |
| **Take Profit R-Ratio** | `tp_ratio` | Float | `[1.5, 2.0, 3.0, 4.0]` | `3.0` | Fixed R:R target multiplier. |
| **Trailing EMA Period** | `trail_ema` | Integer | `[10, 15, 20, 30]` | `20` | EMA period used for trailing stop. |
| **Max Hold Duration** | `max_hold_bars` | Integer | `[10, 20, 30, 50]` | `30` | Time exit threshold in bars ($T_{\text{max}}$). |
| **Volume Filter Enable** | `volume_filter` | Boolean | `[True, False]` | `False` | Whether to enable the volume dry-up filter. |
| **Volume MA Period** | `volume_ma_len` | Integer | `[20, 50]` | `20` | Moving average length for volume. |
| **Volume Apex Threshold** | `volume_apex` | Float | `[0.5, 0.7, 0.9]` | `0.7` | Multiplier $K_v$ for volume dry-up. |

---

## 2. Discovery Sweep Boundaries

To balance completeness with computational search time, the parameter sweeps will be executed in three staged tiers during Stage 2:

```
[Tier 1: Structural Sweeps] 
Verify pattern logic and core swing sizes
   └─ (Sweep swing_window, num_contractions, max_tightness)

[Tier 2: Entry/Trend Sweeps]
Optimize filters and breakout triggers
   └─ (Sweep trend_type, breakout_target, trigger_type)

[Tier 3: Risk/Exit Sweeps]
Refine stop placements and trailing targets
   └─ (Sweep stop_type, exit_type, tp_ratio, trail_ema)
```

### A. Tier 1: Pattern Logic Sweeps (288 iterations)
Focuses on finding the optimal structural definition of the contraction pattern itself, holding exits and trends constant.
* Timeframes: `4H` primarily, then `1H`.
* Trend: Fixed to `EMA_Structure` (50/150/200).
* Exits: Fixed to `Swing_Low` stop with a `Fixed_RR` (3R) target.

### B. Tier 2: Filtering Sweeps (144 iterations)
Evaluates which trend filter and breakout trigger combination minimizes false breakouts (whipsaws) while preserving trade density.
* Input: Optimal pattern structures from Tier 1.
* Output: Selected trend and breakout configuration.

### C. Tier 3: Exit Optimization (240 iterations)
Sweeps different exit types and multipliers to identify the highest Sharpe ratio and lowest drawdown configurations.
* Input: Best entries and trends from Tier 1 & 2.
* Output: Complete final configurations promoted to Walk-Forward testing.
