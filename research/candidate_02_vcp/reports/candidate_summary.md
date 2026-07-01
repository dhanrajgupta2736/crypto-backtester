# Candidate C002 — Discovery Sweep Matrix Summary

This document ranks the performance of the top 25 configurations evaluated in the Volatility Contraction Pattern (VCP) sweeps.

## Ranked Configurations (Top 25)

| Experiment ID   | Timeframe   | Trend Gate   |   Contraction Waves |   Max Final Contraction | Breakout               | Risk Reward      |   Trade Count |   Profit Factor |   Sharpe Ratio |   Max Drawdown | Verdict   |
|:----------------|:------------|:-------------|--------------------:|------------------------:|:-----------------------|:-----------------|--------------:|----------------:|---------------:|---------------:|:----------|
| C002-E03217     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | 1.5R             |             1 |        999      |       1.05054  |        7.51208 | REJECT    |
| C002-E03238     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | 1.5R             |             1 |        999      |       1.05054  |        7.51208 | REJECT    |
| C002-E03236     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | 1R               |             1 |        999      |       0.80164  |        7.51208 | REJECT    |
| C002-E03235     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | 1R               |             1 |        999      |       0.80164  |        7.51208 | REJECT    |
| C002-E03214     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | 1R               |             1 |        999      |       0.80164  |        7.51208 | REJECT    |
| C002-E03215     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | 1R               |             1 |        999      |       0.80164  |        7.51208 | REJECT    |
| C002-E03237     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | 1R               |             1 |        999      |       0.80164  |        7.51208 | REJECT    |
| C002-E03216     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | 1R               |             1 |        999      |       0.80164  |        7.51208 | REJECT    |
| C002-E03239     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | 1.5R             |             1 |        999      |       0.654947 |        8.81722 | REJECT    |
| C002-E03240     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | 1.5R             |             1 |        999      |       0.654947 |        8.81722 | REJECT    |
| C002-E03218     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | 1.5R             |             1 |        999      |       0.654947 |        8.81722 | REJECT    |
| C002-E03219     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | 1.5R             |             1 |        999      |       0.654947 |        8.81722 | REJECT    |
| C002-E03248     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | ATR_Trail        |             1 |        999      |       0.577614 |        0.095   | REJECT    |
| C002-E03226     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | ATR_Trail        |             1 |        999      |       0.577614 |        0.095   | REJECT    |
| C002-E03249     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | ATR_Trail        |             1 |        999      |       0.577614 |        0.095   | REJECT    |
| C002-E03247     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | ATR_Trail        |             1 |        999      |       0.577614 |        0.095   | REJECT    |
| C002-E03227     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | ATR_Trail        |             1 |        999      |       0.577614 |        0.095   | REJECT    |
| C002-E03228     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | ATR_Trail        |             1 |        999      |       0.577614 |        0.095   | REJECT    |
| C002-E03230     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | Swing_Trail      |             1 |        999      |       0.454903 |        7.51208 | REJECT    |
| C002-E03252     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | Swing_Trail      |             1 |        999      |       0.454903 |        7.51208 | REJECT    |
| C002-E03251     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | Swing_Trail      |             1 |        999      |       0.454903 |        7.51208 | REJECT    |
| C002-E03250     | 4H          | EMA200       |                   3 |                    0.03 | High_Break             | Swing_Trail      |             1 |        999      |       0.454903 |        7.51208 | REJECT    |
| C002-E03229     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | Swing_Trail      |             1 |        999      |       0.454903 |        7.51208 | REJECT    |
| C002-E03231     | 4H          | EMA200       |                   3 |                    0.03 | Close_Above_Swing_High | Swing_Trail      |             1 |        999      |       0.454903 |        7.51208 | REJECT    |
| C002-E04178     | 4H          | HH_HL        |                   2 |                    0.03 | Close_Above_Swing_High | 30_Bar_Time_Exit |            11 |         26.1777 |       1.09377  |       13.9465  | REJECT    |

---

## Research Synthesis Summary
* **Evaluation Period**: Approx. 3 years.
* **Min Trade Count Gates**: 225 trades (15m), 120 trades (1H), 50 trades (4H).
* **Verdict Rules**:
  * **PASS**: Sharpe Ratio $\ge 1.20$, Profit Factor $\ge 1.15$, Max Drawdown $< 30\%$, Trade Count above Pass Threshold.
  * **BORDERLINE**: Sharpe Ratio $\ge 0.50$, Max Drawdown $< 45\%$, Trade Count above Borderline Threshold.
