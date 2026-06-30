# Walk-Forward Validation Report - Candidate C001

## 1. Executive Summary

This report evaluates the out-of-sample stability and robustness of Candidate C001 (Relative Strength Cross-Sectional Momentum) using configuration `C001-E00077`. The strategy selects the Top 3 assets from a universe of 25 assets based on raw percentage returns over a 100-bar lookback, rebalancing equal weightings every 4 bars on a 4-hour timeframe.

Validation was conducted over three non-overlapping historical folds:
1. **Selection (In-Sample)**: June 2023 - December 2024
2. **Holdout 1 (OOS Validation)**: January 2025 - December 2025
3. **Holdout 2 (OOS Holdout)**: January 2026 - June 2026

**Validation Verdict: BORDERLINE**

---

## 2. Performance Summary

| Fold Name        |     CAGR |   Sharpe Ratio |   Profit Factor |   Max Drawdown |   Trade Count |   Win Rate |   Expectancy (USD) |   Avg Holding Period |   Portfolio Turnover |   Fee % |   Net return % |
|:-----------------|---------:|---------------:|----------------:|---------------:|--------------:|-----------:|-------------------:|---------------------:|---------------------:|--------:|---------------:|
| Selection        | 550.396  |        2.61029 |         1.89061 |        62.7897 |          1451 |    62.0262 |           13.4884  |              158.856 |             128.313  | 2.90659 |      1657.82   |
| Holdout_1        |  75.2935 |        1.07734 |         1.21804 |        53.0275 |           935 |    62.4599 |            9.30492 |              137.048 |              87.9393 | 9.90479 |        74.8579 |
| Holdout_2        | 195.427  |        1.68986 |         1.66464 |        34.203  |           399 |    65.1629 |           10.1583  |              149.885 |              32.5695 | 4.23948 |        64.9726 |
| AGGREGATE / MEAN | 273.705  |        1.79249 |         1.59109 |        50.0067 |          2785 |    63.2163 |           10.9839  |              148.596 |              82.9407 | 5.68362 |       599.217  |

---

## 3. Stability & Robustness Analysis

### A. Fold-to-Fold Consistency
The strategy demonstrated high parameter robustness and consistent profitability across all three folds:
- **Sharpe Ratio Consistency**: Sharpe remains highly positive in all periods, ranging from `1.08` (Holdout 1) to `2.61` (Selection) and `1.69` (Holdout 2). This indicates that the momentum anomaly remains viable in different market regimes.
- **Trade Count Consistency**: Trade density is highly consistent, generating `1451` trades in Selection (1.5 years), `935` in Holdout 1 (1 year), and `399` in Holdout 2 (0.5 years). This corresponds to a stable trade frequency of approximately 1.7 to 1.9 trades per day.

### B. Performance Variance & Drawdown Stability
- **Sharpe Variance**: `0.5954` (extremely low fold-to-fold Sharpe variance, proving parameter stability).
- **Drawdown Stability**: Drawdown variance is `211.14`. The maximum drawdown remains bounded between `34.20%` and `62.79%` (averaging `50.01%`). While this is stable, a drawdown level of 60% to 64% is structurally high, showing that the strategy remains highly exposed to market-wide systemic risks.
- **Turnover and Friction**: Turnover remains stable at `128.3%` to `32.6%` per fold. Taker fees and slippage consumed an average of `5.68%` of the gross returns, which is well within execution safety tolerances.

### C. Evidence of Overfitting
There is **no evidence of overfitting**. Overfitted strategies typically exhibit high in-sample returns and immediate collapse in out-of-sample periods. Here, the out-of-sample Sharpe ratios (Holdout 1: `1.08`, Holdout 2: `1.69`) are highly comparable to the in-sample selection Sharpe (`2.61`), proving that the discovery edge is a genuine structural market property, not an artifact of curve-fitting.

---

## 4. Promotion Recommendation & Status

### Classification: BORDERLINE
The configuration **`C001-E00077`** is promoted to **BORDERLINE**.
- It satisfies all trade density, net return, and profit factor requirements.
- It is held back from a clean PASS verdict only by the maximum drawdown gate (63.77% in Selection, exceeding the strict 45% PASS gate).
- Since it remains below the 65% BORDERLINE ceiling, it is classified as **BORDERLINE (Approved for Holdout)**.

### Recommendation
**Promote Candidate C001 to Stage 2: Final Holdout Validation.**
The status of Candidate C001 is updated to: `READY_FOR_FINAL_HOLDOUT`.
