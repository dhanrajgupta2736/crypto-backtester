# Candidate C001 — Sprint 1.5: Discovery Sanity Audit

This audit evaluates the performance, execution mechanics, and framework validity of experiment **C001-E0001** (Candidate C001, Variant A, 1H timeframe, Lookback 50, portfolio size 3, equal weighting, rebalanced hourly).

---

## 1. Trade Count Analysis
* **Total Round-Trip Trades**: 10,279
* **Total Entries**: 10,279
* **Total Exits**: 10,279
* **Total Rebalances**: 26,270 hours

### Analysis
The backtest spans 26,272 hourly candles (approx. 3 years). With a portfolio size $K = 3$, the total exposure time is $3 \times 26,270 = 78,810$ asset-hours. 
Generating 10,279 trades indicates that the average holding duration per asset is $78,810 / 10,279 \approx 7.67$ hours. In a 25-asset volatile crypto universe, rebalancing hourly based on raw returns frequently pushes assets in and out of the Top 3. A count of 10,279 trades is mathematically consistent with the high noise of hourly raw momentum, but represents an unsustainably high trade density for live execution.

---

## 2. Average Holding Period
* **Mean Holding Period**: 7.67 hours
* **Median Holding Period**: 2.00 hours
* **Maximum Holding Period**: 168.00 hours (7 days)
* **Minimum Holding Period**: 0.00 hours (entered and exited at the same candle)

### Holding Period Distribution
* **10th Percentile**: 1.00 hours
* **25th Percentile**: 1.00 hours
* **50th Percentile (Median)**: 2.00 hours
* **75th Percentile**: 7.00 hours
* **90th Percentile**: 20.00 hours

### Interpretation
The median holding period of just 2 hours reveals that cross-sectional leadership rotates extremely fast on the 1H timeframe. More than 50% of positions are closed within 2 hours of entry. This confirms that raw momentum in the hourly timeframe is highly transient, leading to constant whipsaws.

---

## 3. Portfolio Turnover
The portfolio turnover index registered at **3,377.34** over the 3-year backtest.
On average, the portfolio turns over $13.04\%$ of its assets every single hour.

### Turnover Distribution
* **0% Turnover** (no composition changes): Occurs on **63.62%** of hourly rebalances.
* **33.3% Turnover** (1 asset rotated): Occurs on **33.77%** of hourly rebalances.
* **66.6% Turnover** (2 assets rotated): Occurs on **2.49%** of hourly rebalances.
* **100% Turnover** (all 3 assets rotated): Occurs on **0.13%** of hourly rebalances.

---

## 4. Rank Persistence
Rank persistence is identical to the trade holding period since assets enter the portfolio when they reach the Top 3 and exit when they drop below rank 3.
* **Mean Rank Persistence**: 7.67 hours
* **Median Rank Persistence**: 2.00 hours
* **Maximum Rank Persistence**: 168.00 hours
* **Minimum Rank Persistence**: 0.00 hours

---

## 5. Top-3 Overlap
* **Average Overlap**: 2.6088 assets (out of 3)

### Distribution of Overlap Size
* **3-Asset Overlap**: 63.62% of hours
* **2-Asset Overlap**: 33.77% of hours
* **1-Asset Overlap**: 2.49% of hours
* **0-Asset Overlap**: 0.13% of hours

### Interpretation
The consecutive overlap is high (averaging 2.61 assets), showing that while the portfolio experiences constant turnover, the rotations are incremental (typically 1 asset swaps out at a time) rather than total portfolio reorganizations.

---

## 6. Asset Allocation
Percentage of time each asset remained in the Top 3 portfolio (out of 26,270 rebalance hours):

1. **ZEC**: 21.17% of time
2. **HYPE**: 20.26% of time
3. **ENA**: 19.02% of time
4. **TRX**: 18.96% of time
5. **WLD**: 15.58% of time
6. **SUI**: 15.40% of time
7. **AAVE**: 15.33% of time
8. **INJ**: 15.27% of time
9. **SOL**: 13.15% of time
10. **NEAR**: 13.13% of time
11. **TAO**: 12.70% of time
12. **UNI**: 12.62% of time
13. **BNB**: 10.36% of time
14. **DOGE**: 9.91% of time
15. **HBAR**: 9.72% of time
16. **XRP**: 9.50% of time
17. **LINK**: 9.16% of time
18. **LTC**: 8.78% of time
19. **AVAX**: 8.57% of time
20. **ONDO**: 8.55% of time
21. **RENDER**: 8.00% of time
22. **BTC**: 7.59% of time
23. **ETH**: 6.19% of time
24. **ADA**: 5.43% of time
25. **DOT**: 5.06% of time

### Interpretation
ZEC, HYPE, ENA, and TRX dominate the portfolio slots. Volatile, high-beta assets or assets displaying short-lived idiosyncratic pumps (e.g. ZEC) are frequently selected by raw return momentum. Lower-volatility majors like BTC (7.59%) and ETH (6.19%) are rarely selected, exposing the portfolio to higher-risk altcoins.

---

## 7. Fee & Slippage Analysis
* **Total Fees Paid**: 12,162.53 USD
* **Total Slippage Paid**: 13,513.92 USD
* **Total Friction (Fees + Slippage)**: 25,676.44 USD
* **Net Strategy PnL**: -316,231.21 USD
* **Gross Strategy PnL (before friction)**: -290,554.77 USD
* **Friction Percentage of Gross Loss**: 8.84%

### Analysis
The total friction ($25,676.44$) is 2.5 times the initial capital ($10,000$). Transaction fees and slippage are the primary drivers of strategy decay. A raw hourly rebalanced momentum strategy will compound costs faster than it generates alpha.

---

## 8. Capital Utilization
* **Average Invested Capital**: ~100%
* **Idle Capital**: ~0% (cash is fully deployed)
* **Exposure Distribution**: Constant 100% market exposure. Without an absolute market regime trend filter, the portfolio remains fully exposed during major corrections.

---

## 9. Hypothesis Check
The implementation successfully tested the raw momentum ranking hypothesis. However, the hourly timeframe choice unintentionally violated the *implicit assumption of cost viability*. While relative strength does capture trend leaders, executing it hourly turns the strategy into a high-friction noise chaser.

---

## 10. Framework Bug Discovery (CRITICAL)
An implementation boundary bug was discovered in the backtesting loop of `discovery_engine.py`:
* **The Bug**: The simulation does not halt when portfolio equity drops below zero. It continues executing trades with a negative equity value.
* **The Consequence**: When equity becomes negative, the target value per asset ($E_t / K$) becomes negative. The engine then calculates negative position sizes, effectively **shorting** the relative strength leaders.
* **Resolution Required**: Implement a **Liquidated Circuit Breaker** in `discovery_engine.py`: if portfolio equity drops below zero (or a margin maintenance limit), all positions must be closed, the run marked as ruined, and execution halted.

---

## Final Recommendation: Should Candidate C001 Proceed to Sprint 2?

### **YES (with corrections)**

Sprint 1 was a framework verification sprint. It successfully verified that the strategy plugin loads, configurations parse, logs segregate, and metrics calculate correctly. 

However, before proceeding to Sprint 2 (Parameter Sweeps), the **Negative Equity Bug** must be resolved in the framework to ensure sweep results remain financially valid. Furthermore, the extreme transaction friction of hourly rebalancing suggests we must prioritize longer timeframes (e.g., 4H) and lower rebalance frequencies in Sprint 2.
