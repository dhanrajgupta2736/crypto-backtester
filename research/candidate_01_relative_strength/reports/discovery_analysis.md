# Candidate C001 — Sprint 2: Discovery Matrix Analysis

This document synthesizes the findings from the structured parameter sweep (81 experiments) evaluating the Cross-Sectional Momentum (Relative Strength) hypothesis.

---

## 1. Key Statistics & Overview

The parameter sweep was executed over three dimensions across a three-year historical database (June 2023 - June 2026) using the frozen QRP Framework v2.0.1:
- **Timeframes**: 15m, 1H, 4H
- **Lookbacks ($L$)**: 20, 50, 100 bars
- **Portfolio Size ($K$)**: Top 1, Top 3, Top 5 assets
- **Rebalance Frequency ($R$)**: Every 1, 2, 4 candles

### Grouped Summary Table

| Dimension | Group | Average Sharpe | Average Max Drawdown | Average Trade Count | Average Fee % of Gross PnL |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Timeframe** | 15m | -5.81 | 99.99% | 105,764 | 728.54% |
| | 1H | -0.16 | 94.15% | 25,866 | 67.68% |
| | 4H | +1.43 | 78.08% | 6,251 | 15.84% |
| **Lookback ($L$)** | 20 | -2.97 | 93.33% | 50,673 | 442.60% |
| | 50 | -1.27 | 90.84% | 45,181 | 198.90% |
| | 100 | -0.31 | 88.05% | 42,027 | 170.57% |
| **Portfolio size ($K$)**| K=1 | -0.65 | 94.81% | 5,721 | 217.76% |
| | K=3 | -1.73 | 89.41% | 50,109 | 189.04% |
| | K=5 | -2.17 | 88.00% | 82,051 | 405.26% |
| **Rebalance Freq ($R$)**| R=1 | -2.63 | 92.06% | 75,667 | 446.01% |
| | R=2 | -1.41 | 90.95% | 40,343 | 174.79% |
| | R=4 | -0.51 | 89.21% | 21,871 | 191.27% |

---

## 2. Answers to Research Questions

### 1. Does the hypothesis appear viable?
**Yes, but strictly under specific parameter constraints.**
The relative strength cross-sectional momentum hypothesis demonstrates substantial viability on the **4H timeframe** (yielding an average Sharpe Ratio of +1.43). However, it is **completely non-viable on the 15m timeframe** and **borderline/unviable on the 1H timeframe** under raw percentage return ranking. This is due to severe whipsaw losses and high transaction cost drag.

### 2. Which parameter has the largest impact?
**Timeframe** has the largest impact on performance.
- Moving from 15m to 4H changes the average Sharpe Ratio from **-5.81** to **+1.43** (an improvement of 7.24 Sharpe units).
- **Lookback length ($L$)** also has a significant impact; longer lookbacks ($L=100$) are much more robust, filtering out high-frequency noise and reducing false breakouts.

### 3. Does reducing rebalance frequency reduce transaction costs meaningfully?
**Yes, dramatically.**
Increasing the rebalance interval $R$ from 1 bar to 4 bars reduces the average trade count by **71.1%** (from 75,667 trades to 21,871 trades). In the 4H timeframe with Lookback 100 and K=3, moving from $R=1$ (`C001-E00079`) to $R=4$ (`C001-E00077`) reduces the trade count from **10,546** to **2,877** (a 72.7% reduction) and cuts the fee percentage of gross PnL from **9.64%** to **5.81%**.

### 4. Which timeframe appears most promising?
The **4H timeframe** is the only promising timeframe.
- The 4H configurations achieve positive Sharpe Ratios (averaging +1.43, with top configurations around **1.69 to 2.04**).
- The 15m timeframe is a complete failure (Sharpe < -0.89) due to transaction fee drag exceeding 130% of gross PnL.
- The 1H timeframe is unprofitable or marginal (Sharpe < 1.0) with significant drawdowns.

### 5. Which configurations qualify for Walk-Forward validation?
None of the configurations qualify for a direct **PASS** verdict because all of them experienced maximum drawdowns exceeding the strict 45% gate (the best configurations had drawdowns between 60% and 90% due to the long-only altcoin exposure during market-wide bear phases).
However, **two configurations** qualify under the **BORDERLINE** promotion rules and are approved for Walk-Forward selection:
1. **`C001-E00077` (4H, Lookback 100, K=3, R=4)**: Sharpe `1.937`, Profit Factor `1.439`, CAGR `267.6%`, Max Drawdown `63.77%`, Fee % `5.81%`, Trade Count `2,877`.
2. **`C001-E00082` (4H, Lookback 100, K=5, R=1)**: Sharpe `1.714`, Profit Factor `1.235`, CAGR `171.9%`, Max Drawdown `60.17%`, Fee % `14.58%`, Trade Count `17,331`.

### 6. Which configurations should be rejected?
**All 79 other configurations must be rejected.**
- **All 15m configurations** (C001-E00002 to C001-E00028) must be rejected due to negative expectancy, extreme turnover, and high fee drag (fees up to 559% of gross returns).
- **All 1H configurations** (C001-E00029 to C001-E00055) must be rejected because they fail to meet the performance gates (Sharpe < 1.0, Profit Factor < 1.15, drawdowns > 80%).
- **4H configurations with short lookbacks ($L=20$ or $L=50$) or $K=1$** must be rejected. The $K=1$ configurations (e.g. `C001-E00075`) generated the highest raw Sharpe (2.04) and CAGR (625%) but suffered drawdowns > 83-90% due to lack of diversification.

### 7. Which qualify as BORDERLINE?
The following two configurations qualify as BORDERLINE:
- **`C001-E00077` (4H, Lookback 100, K=3, R=4)**
- **`C001-E00082` (4H, Lookback 100, K=5, R=1)**
These configurations are held back from direct promotion only by their Max Drawdown (63.77% and 60.17%, exceeding the 45% safety gate). However, their high Sharpe Ratios (1.94 and 1.71) and strong profit factors make them excellent candidates for Stage 3 Walk-Forward optimization and filtration.

### 8. Are there patterns suggesting Candidate C001 Version 2 should explore volatility-adjusted ranking?
**Yes, very strongly.**
- The raw percentage return ranking selects high-beta altcoins during market rallies, which results in extreme concentration in highly correlated assets. When the market turns, these assets suffer synchronized drawdowns, leading to the **60% to 90% portfolio drawdowns** seen across all 4H configurations.
- Volatility-adjusted ranking (e.g., Volatility-Normalized Return or Sharpe-like ratio) would penalize assets with erratic, high-volatility spikes and reward consistent, steady trends.
- Sizing positions inversely to their volatility (risk parity) rather than equal weighting would further dampen the portfolio drawdown.
- Version 2 should introduce an **Absolute Market Regime Trend Gate** (e.g., shutting off entries if BTC is below its EMA200) to protect the portfolio from systemic market drawdowns.

---

## 3. Recommended Next Steps

1. **Promote the BORDERLINE Configurations to Walk-Forward validation**:
   Specifically target **`C001-E00077`** as the lead candidate, given its low execution cost drag (5.81% of gross returns) and stable metrics.
2. **Design Candidate C001 Version 2**:
   Incorporate:
   - Volatility-Normalized Return (VNR) ranking.
   - An absolute market regime gate (moving average filter on BTC/ETH).
   - ATR-based trailing exits or hard stop losses.
