# Coin Attribution Analysis — Candidate C002 Version 1

This document presents the per-coin performance attribution analysis for Candidate C002 (Volatility Contraction Pattern) using the selected configuration `C002-E04426` on the 4H timeframe. The analysis is evaluated over the full backtest period (2023-06-21 to 2026-06-19).

---

## 1. Per-Coin Performance Metrics

Below is the complete statistical breakdown of all 25 assets in the trade universe, ranked from best to worst by net profit contribution:

| asset   |   Trade Count | Win Rate   | Net Profit   | Expectancy   |   Profit Factor |   Sharpe Ratio | Max Drawdown   | Avg Holding Time   | Classification   |
|:--------|--------------:|:-----------|:-------------|:-------------|----------------:|---------------:|:---------------|:-------------------|:-----------------|
| XRP     |             1 | 100.00%    | $4,363.81    | 39.2812 R    |          999    |         0.5776 | 0.00%          | 340.0h             | STRONG           |
| DOGE    |             9 | 44.44%     | $2,281.72    | 1.3304 R     |           11.73 |         0.6389 | 7.11%          | 64.4h              | STRONG           |
| RENDER  |            17 | 100.00%    | $766.88      | 9.2055 R     |          999    |         0.7951 | 0.00%          | 71.3h              | STRONG           |
| SUI     |            19 | 94.74%     | $201.14      | 4.9531 R     |          999    |         0.6161 | 0.00%          | 85.9h              | NEUTRAL          |
| ADA     |            16 | 100.00%    | $87.78       | 4.6708 R     |          999    |         0.6665 | 0.00%          | 81.2h              | NEUTRAL          |
| ETH     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| AAVE    |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| BNB     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| AVAX    |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| ONDO    |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| NEAR    |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| ENA     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| HBAR    |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| LINK    |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| LTC     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| INJ     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| HYPE    |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| WLD     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| UNI     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| TAO     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| SOL     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| ZEC     |             0 | 0.00%      | $0.00        | 0.0000 R     |            1    |         0      | 0.00%          | 0.0h               | NEUTRAL          |
| BTC     |             1 | 0.00%      | $-65.48      | -0.3939 R    |            0    |        -0.5776 | 1.96%          | 56.0h              | WEAK             |
| TRX     |             1 | 0.00%      | $-213.63     | -1.0919 R    |            0    |        -0.5776 | 6.41%          | 28.0h              | WEAK             |
| DOT     |             7 | 0.00%      | $-327.40     | -4.6205 R    |            0    |        -0.5848 | 9.82%          | 27.4h              | REJECT           |

---

## 2. Coin Classification Definition

We classify every coin in the universe into one of four categories based on trade frequency and profit contributions:

1. **STRONG**: Consistently profitable, with positive standalone Sharpe ratios and high profit factors ($\ge 2.0$).
2. **NEUTRAL**: Profitable but either small/marginal returns, or did not trigger any trades during the 3-year period (representing zero drag on capital).
3. **WEAK**: Unprofitable with very low trade counts ($\le 2$ trades), representing low-sample noise.
4. **REJECT**: Structurally unprofitable over multiple trades ($\ge 3$ trades), representing a persistent drag on portfolio equity.

### Group Breakdown:

* **STRONG (3 coins)**: `XRP`, `DOGE`, `RENDER`.
* **NEUTRAL (19 coins)**: `SUI`, `ADA`, and the 17 non-traded coins (`ETH`, `AAVE`, `BNB`, `AVAX`, `ONDO`, `NEAR`, `ENA`, `HBAR`, `LINK`, `LTC`, `INJ`, `HYPE`, `WLD`, `UNI`, `TAO`, `SOL`, `ZEC`).
* **WEAK (2 coins)**: `BTC`, `TRX`.
* **REJECT (1 coins)**: `DOT`.

---

## 3. Portfolio Drag Analysis

* **High Selectivity**: Due to the highly restrictive VCP parameters of `C002-E04426` (3 waves, 5% apex tightness, and a `HH_HL` trend filter), **17 out of 25 assets generated exactly 0 trades** over the 3-year backtest. These non-traded assets represent $0.00 in returns and 0% drawdown contribution, causing zero drag.
* **Underperforming Assets**:
  * **`DOT` (REJECT)**: The single worst performer. It generated 7 trades with a **0% win rate**, resulting in a loss of **-$327.40** and a standalone max drawdown of **9.82%**. This coin represents a structural drag on the VCP breakout strategy.
  * **`TRX` (WEAK)**: Generated 1 trade with a **0% win rate**, losing **-$213.63** with a drawdown of **6.41%**.
  * **`BTC` (WEAK)**: Generated 1 trade, losing **-$65.48**.
* **Impact of Removing Drag**:
  * Cumulative net profit of all coins: **$7,094.81**
  * Sum of profitable coins: **$7,701.33**
  * Sum of unprofitable coins: **$-606.52**
  * Excluding the underperforming coins (`DOT`, `TRX`, and `BTC`) would increase the net portfolio profit from **$7,094.81** to **$7,701.33**, representing an **8.55% increase in total profits** while completely eliminating unprofitable asset risk.

---

## 4. Firm Recommendations

### Recommended Action: Remove specific coins

We recommend **removing specific underperforming coins (`DOT`, `TRX`, and `BTC`)** from the active trading universe of Candidate C002.

#### Rationale:
1. **Direct Profit Improvement**: Eliminating these three coins increases the backtest net profit by **+$606.52** (an **8.55% improvement**).
2. **Universe Split is Sub-optimal**: We evaluated splitting the universe into *Large Caps vs Altcoins*. However, this is not justified by the data:
   * **Large Caps** contain both top performers (`XRP` +$4,363.81, `DOGE` +$2,281.72, `ADA` +$87.78) and drag (`BTC` -$65.48).
   * **Altcoins** contain top performers (`RENDER` +$766.88, `SUI` +$201.14) and drag (`DOT` -$327.40, `TRX` -$213.63).
   * Splitting by market cap would arbitrarily eliminate high-performing assets from one of the groups. Removing specific assets based on attribution metrics is far more targeted and effective.
3. **Keep Non-Traded Assets**: The 17 coins that generated 0 trades should remain in the universe config as `NEUTRAL`. Because they do not trigger trades under strict trend and contraction gates, they cause zero capital drag during low-opportunity periods but remain available if strong VCP consolidations develop in the future.
