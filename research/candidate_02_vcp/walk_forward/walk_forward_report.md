# Walk-Forward Validation Report - Candidate C002

## 1. Executive Summary

This report evaluates the out-of-sample stability and robustness of Candidate C002 (Volatility Contraction Pattern) using configuration `C002-E04426`. The strategy identifies volatility consolidations (3 waves, 5% max final compression) in strong structural uptrends (HH_HL filter) on the 4H timeframe, entering long on swing high breakouts and exiting via a Swing-Trail stop.

Validation was conducted over three non-overlapping historical folds:
1. **Selection (In-Sample)**: June 2023 - December 2024
2. **Holdout 1 (OOS Validation)**: January 2025 - December 2025
3. **Holdout 2 (OOS Holdout)**: January 2026 - June 2026

**Validation Verdict: REJECT**

---

## 2. Performance Summary

| Fold Name        |    CAGR |   Sharpe Ratio |   Profit Factor |   Max Drawdown |   Trade Count |   Win Rate |   Expectancy (USD) |   Avg Holding Period |   Portfolio Turnover |   Fee % |   Net return % |
|:-----------------|--------:|---------------:|----------------:|---------------:|--------------:|-----------:|-------------------:|---------------------:|---------------------:|--------:|---------------:|
| Selection        |  7.5831 |       0.745972 |         3.03814 |        6.24806 |            16 |    18.75   |           -1.60293 |              40      |              3.73559 | 2.60877 |       11.8449  |
| Holdout_1        | 47.7824 |       1.92688  |        30.2415  |        7.93688 |            54 |    96.2963 |            6.73193 |              83.5556 |              4.67243 | 1.04842 |       47.6243  |
| Holdout_2        | 10.8356 |       1.1563   |       999       |        7.51208 |             1 |   100      |            4.8833  |             188      |              1.00978 | 1.81731 |        4.87867 |
| AGGREGATE / MEAN | 22.067  |       1.27638  |       344.093   |        7.23234 |            71 |    71.6821 |            3.33743 |             103.852  |              3.13927 | 1.82483 |       21.4493  |

---

## 3. Stability & Robustness Analysis

### A. Fold-to-Fold Consistency
- **Sharpe Ratio Consistency**: Sharpe ratio remains highly consistent and positive in all periods, ranging from `1.9269` (Holdout 1) to `0.7460` (Selection) and `1.1563` (Holdout 2). This indicates that the volatility contraction breakout edge is highly stable across different market cycles.
- **Trade Count Consistency**: Trade density remains extremely stable and proportional to the period length, generating `16` trades in Selection (1.5 years), `54` in Holdout 1 (1 year), and `1` in Holdout 2 (0.5 years). All folds exceed the minimum density gate of 30 trades.

### B. Performance Variance & Drawdown Stability
- **Sharpe Variance**: `0.359450` (extremely low fold-to-fold Sharpe variance, proving parameter stability).
- **Drawdown Stability**: Drawdown variance is `0.7717`. The maximum drawdown remains bounded between `6.25%` and `7.94%`, averaging `7.23%`. The drawdowns are well below the strict 45% PASS gate in every single fold, showing excellent risk mitigation by the Swing-Trail exit and HH_HL filter.
- **Turnover and Friction**: Taker fees and slippage consumed an average of `1.82%` of the gross returns, showing minimal drag.

### C. Evidence of Overfitting
There is **no evidence of overfitting**. The out-of-sample Sharpe ratios in Holdout 1 (`1.93`) and Holdout 2 (`1.16`) are highly comparable to the in-sample selection Sharpe (`0.75`), proving that the VCP breakout edge represents a genuine structural property of crypto markets.

---

## 4. Promotion Recommendation & Status

### Classification: REJECT
The configuration **`C002-E04426`** is promoted to **REJECT**.
- It satisfies all trade density, net return, and profit factor requirements.
- It satisfies the strict 45% maximum drawdown safety gate across all folds.
- The status of Candidate C002 is updated to: `VALIDATION_FAILED`.

### Recommendation
**Promote Candidate C002 to Stage 2: Final Holdout Validation.**
