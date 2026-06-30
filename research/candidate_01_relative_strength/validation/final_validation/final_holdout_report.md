# Stage 5 Final Holdout Report - Candidate C001

## 1. Executive Summary

This report evaluates the out-of-sample performance of Candidate C001 (Relative Strength Cross-Sectional Momentum) on the **untouched Final Holdout dataset** (January 1, 2026 to June 19, 2026).

The configuration was frozen with the following parameters:
- Lookback Window ($L$): 100 bars
- Portfolio Size ($K$): Top 3 assets
- Rebalance Frequency ($R$): Every 4 bars (16 hours)
- Execution: Long Only, Equal Weighting, Taker fees (0.045%) and slippage (0.05%) applied.

**Verdict: BORDERLINE**

---

## 2. Performance Metrics Table

| Metric | Value | Threshold / Gate | Status |
| :--- | :---: | :---: | :---: |
| **CAGR** | 195.43% | > 0.00% | `PASS` |
| **Sharpe Ratio** | 1.690 | >= 1.000 | `PASS` |
| **Profit Factor** | 1.665 | >= 1.200 | `PASS` |
| **Max Drawdown** | 34.20% | <= 45.00% | `BORDERLINE` |
| **Trade Count** | 399 | >= 30 | `PASS` |
| **Win Rate** | 65.16% | N/A | `PASS` |
| **Expectancy (USD)** | 10.1583 | > 0 | `PASS` |
| **Fee % of Gross** | 4.24% | < 25.00% | `PASS` |
| **Portfolio Turnover** | 32.57% | N/A | `PASS` |
| **Net Return %** | 64.97% | > 0.00% | `PASS` |

---

## 3. Justification

The strategy successfully generated robust returns out-of-sample without showing indicators of overfitting. It qualifies for a **BORDERLINE** verdict due to its Maximum Drawdown of `34.20%` during the period, which is higher than the strict PASS limit of 45% but well below the 65% REJECT threshold.
