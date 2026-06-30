# Phase 14A Post-Mortem Report: Mean Reversion Discovery Scan

This report presents a quantitative post-mortem analysis of the Phase 14A.1 Mean Reversion Discovery Scan. The scan evaluated **252 combinations** across 3 modes, 7 coins, 3 timeframes, and 4 risk-reward ratios (RR) using the full historical dataset (2023-01-01 to 2026-06-19) under realistic fee, slippage, and funding rate assumptions.

---

## 1. Summary of Qualified Systems ($\ge 100$ Trades)

Out of 252 configurations evaluated, only **19 systems** achieved $\ge 100$ trades, demonstrating sufficient trade density for statistical validation. All other 233 runs failed to reach this threshold, primarily due to the strictness of canonical signal thresholds on the hourly and 4-hour timeframes, or low trade counts on the 15m timeframe under execution constraints.

### Qualified Systems Sorted by Profit Factor (PF)
The table below lists all 19 qualified systems, sorted in descending order of Profit Factor:

| Mode | Coin | Timeframe | RR | Trades | Profit Factor | Expectancy (R) | Sharpe Ratio | Net Return (%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **RSI_BB** | ETH | 4H | 3.0 | 191 | **1.04** | **+0.0270** | **+0.39** | **+52.52%** |
| RSI | ETH | 1H | 3.0 | 186 | 0.97 | -0.0422 | +0.40 | -33.34% |
| BB | BNB | 1H | 3.0 | 148 | 0.94 | -0.0974 | +0.18 | -40.46% |
| BB | ETH | 4H | 3.0 | 140 | 0.93 | -0.0565 | -0.41 | -82.95% |
| RSI_BB | ETH | 4H | 2.0 | 147 | 0.92 | -0.0451 | +0.10 | -78.09% |
| BB | ETH | 4H | 1.5 | 125 | 0.91 | -0.0478 | -0.25 | -74.56% |
| RSI | ETH | 4H | 3.0 | 121 | 0.91 | -0.0661 | -0.09 | -85.28% |
| RSI | SOL | 1H | 3.0 | 120 | 0.90 | -0.0235 | +0.28 | -74.61% |
| BB | SOL | 1H | 2.0 | 116 | 0.90 | -0.1531 | -0.68 | -70.06% |
| BB | AVAX | 1H | 3.0 | 114 | 0.90 | -0.1260 | -0.24 | -68.46% |
| BB | ETH | 4H | 2.0 | 105 | 0.90 | -0.0346 | -0.16 | -71.07% |
| RSI_BB | AVAX | 4H | 3.0 | 115 | 0.89 | -0.0709 | -0.22 | -91.02% |
| RSI_BB | BNB | 1H | 3.0 | 100 | 0.88 | -0.1238 | -0.73 | -52.60% |
| RSI_BB | AVAX | 1H | 3.0 | 105 | 0.88 | -0.1611 | -1.01 | -89.17% |
| RSI_BB | AVAX | 1H | 2.0 | 109 | 0.87 | -0.1941 | -0.72 | -69.42% |
| RSI_BB | AVAX | 4H | 1.5 | 100 | 0.86 | -0.1169 | -0.44 | -87.61% |
| RSI_BB | ETH | 4H | 1.5 | 102 | 0.84 | -0.1293 | -0.43 | -96.23% |
| BB | ETH | 4H | 1.0 | 107 | 0.82 | -0.1373 | -1.35 | -89.32% |
| RSI_BB | BNB | 4H | 1.0 | 106 | 0.81 | -0.2007 | -0.36 | -85.22% |

---

## 2. Mode-Specific Rankings

### A. RSI Mode
Only **3 configurations** qualified. All finished with negative expectancy and net returns, though Sharpe remained positive for some configurations due to lower volatility in equity drawdown.

| Coin | Timeframe | RR | Trades | Profit Factor | Expectancy (R) | Sharpe Ratio | Net Return (%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| ETH | 1H | 3.0 | 186 | **0.97** | **-0.0422** | **+0.40** | **-33.34%** |
| ETH | 4H | 3.0 | 121 | 0.91 | -0.0661 | -0.09 | -85.28% |
| SOL | 1H | 3.0 | 120 | 0.90 | -0.0235 | +0.28 | -74.61% |

### B. Bollinger Bands (BB) Mode
Qualified **7 configurations**. All resulted in net capital loss.

| Coin | Timeframe | RR | Trades | Profit Factor | Expectancy (R) | Sharpe Ratio | Net Return (%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| BNB | 1H | 3.0 | 148 | **0.94** | **-0.0974** | **+0.18** | **-40.46%** |
| ETH | 4H | 3.0 | 140 | 0.93 | -0.0565 | -0.41 | -82.95% |
| ETH | 4H | 1.5 | 125 | 0.91 | -0.0478 | -0.25 | -74.56% |
| SOL | 1H | 2.0 | 116 | 0.90 | -0.1531 | -0.68 | -70.06% |
| ETH | 4H | 2.0 | 105 | 0.90 | -0.0346 | -0.16 | -71.07% |
| AVAX | 1H | 3.0 | 114 | 0.90 | -0.1260 | -0.24 | -68.46% |
| ETH | 4H | 1.0 | 107 | 0.82 | -0.1373 | -1.35 | -89.32% |

### C. RSI + Bollinger Bands (RSI_BB) Mode
Qualified **9 configurations**. Contains the **only profitable run** of the entire scan.

| Coin | Timeframe | RR | Trades | Profit Factor | Expectancy (R) | Sharpe Ratio | Net Return (%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| ETH | 4H | 3.0 | 191 | **1.04** | **+0.0270** | **+0.39** | **+52.52%** |
| ETH | 4H | 2.0 | 147 | 0.92 | -0.0451 | +0.10 | -78.09% |
| AVAX | 4H | 3.0 | 115 | 0.89 | -0.0709 | -0.22 | -91.02% |
| AVAX | 1H | 3.0 | 105 | 0.88 | -0.1611 | -1.01 | -89.17% |
| BNB | 1H | 3.0 | 100 | 0.88 | -0.1238 | -0.73 | -52.60% |
| AVAX | 1H | 2.0 | 109 | 0.87 | -0.1941 | -0.72 | -69.42% |
| AVAX | 4H | 1.5 | 100 | 0.86 | -0.1169 | -0.44 | -87.61% |
| ETH | 4H | 1.5 | 102 | 0.84 | -0.1293 | -0.43 | -96.23% |
| BNB | 4H | 1.0 | 106 | 0.81 | -0.2007 | -0.36 | -85.22% |

---

## 3. Concentration Analysis

The scan results reveal heavy performance and density concentration across the variables:

*   **Coin Concentration**: Highly concentrated in **ETH** (9 of the 19 qualified runs) and **AVAX** (5 of 19). BTC, LINK, and XRP produced zero qualified runs. Highly liquid and medium-to-high volatility assets allow sufficient consolidation loops, whereas BTC was too clean (few consolidation wicks), and LINK/XRP trades collapsed.
*   **Timeframe Concentration**: Strictly concentrated in the **1H** (8 runs) and **4H** (11 runs) timeframes. The **15m timeframe generated zero qualified runs** due to rapid stop-outs from transaction cost drag and spread friction, preventing positions from breathing.
*   **Risk-Reward (RR) Concentration**: Survival and profitability metrics are positively correlated with higher Risk-Reward ratios:
    - **RR=1.0**: 2 runs (Mean PF = 0.815)
    - **RR=1.5**: 3 runs (Mean PF = 0.870)
    - **RR=2.0**: 4 runs (Mean PF = 0.898)
    - **RR=3.0**: 10 runs (Mean PF = 0.924)
    Higher RRs are crucial to offset taker fee and slippage overhead on losing trades.

### Component Leaders
*   **Best Coin Overall**: **ETH** (Mean PF = 0.9156, contains the only profitable qualified system).
*   **Best Timeframe Overall**: **1H** (Mean PF = 0.9050, slightly outperforming 4H's 0.8936 average).
*   **Best Risk-Reward Overall**: **3.0** (Mean PF = 0.9240, accounting for 10 of the 19 qualified setups).
*   **Best Strategy Mode Overall**: **RSI** (Mean PF = 0.9267, and the only mode to hold a positive mean Sharpe ratio of +0.1967).

---

## 4. Aggregate Qualified Performance

Averages calculated across all 19 qualified configurations:

*   **Average Profit Factor**: **0.8984**
*   **Average Sharpe Ratio**: **-0.3021**
*   **Average Win Rate**: **33.38%**
*   **Average Expectancy**: **-0.0947 R**

---

## 5. Synthesis: Did Mean Reversion Demonstrate a Real Edge?

> [!CAUTION]
> **No. Canonical mean reversion did not demonstrate a statistically meaningful edge.**
> 
> Only **1 out of 252 backtests** achieved profitability (`RSI_BB ETH 4H RR=3.0`, PF=1.04). The remaining 99.6% of configurations failed to generate a net profit. 
> 
> Across all qualified runs, the average Profit Factor (0.8984), average Sharpe Ratio (-0.3021), and average expectancy (-0.0947 R) are negative. Taker fee drag (0.05% per entry/stop-out), slippage, and cumulative hourly funding rate carry completely eroded the theoretical mean reversion edge. Without active regime filtering or trend alignment, canonical mean reversion is mathematically unprofitable.

---

## 6. Recommended Phase 14A.2 Research Direction

Based on the quantitative findings, we must reject blind counter-trend mean reversion. However, the concentration data indicates that **RSI breakouts/boundaries on ETH 1H/4H timeframes using wide Risk-Reward profiles (3.0R) survive best**. 

### Recommendation: "Trend-Regime Filtered RSI Reversion with ATR-Volatility Entry Bands"

Instead of sweeping arbitrary parameters, Phase 14A.2 must implement and validate the following structural rules:
1.  **Trend-Alignment Filter**: Restrict RSI entries to the direction of the macro trend (e.g. only buy RSI oversold when price is above the 200-period Hourly EMA; only sell RSI overbought when price is below the 200 Hourly EMA).
2.  **Regime Locking**: Integrate the existing Choppiness Index (CHOP) or ADX indicators. Disable mean reversion during trending regimes (ADX > 25) and restrict trading exclusively to sideways/consolidation environments (ADX < 20).
3.  **Dynamic Entry Bands**: Rather than fixed RSI boundaries (<30/>70), scale the entry trigger band dynamically using the rolling ATR (e.g., price must overshoot a moving average by $\ge 2.0 \times \text{ATR}(14)$ to trigger a reversion entry).
4.  **High Risk-Reward (3.0R+) Target**: Focus exclusively on 3.0R configurations, as the data proves low RR setups (1.0R - 1.5R) cannot recover from fee and slippage friction.
