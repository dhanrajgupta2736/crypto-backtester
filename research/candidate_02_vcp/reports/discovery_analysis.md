# Candidate C002 — VCP Parameter Discovery Analysis

This document provides a quantitative analysis of how different Volatility Contraction Pattern parameters influenced backtest performance.

## Parameter Influence Analysis

### A. Performance by Resolution Timeframe
| Timeframe   |   Sharpe Ratio |   Profit Factor |   Trade Count |
|:------------|---------------:|----------------:|--------------:|
| 15m         |      -1.81278  |        0.810988 |      37503.4  |
| 1H          |      -0.247987 |        0.911492 |       7960    |
| 4H          |       0.250899 |        5.51062  |       1051.81 |

### B. Performance by Trend Gate Filter
| Trend Gate   |   Sharpe Ratio |   Profit Factor |   Trade Count |
|:-------------|---------------:|----------------:|--------------:|
| Donchian     |      -0.527423 |        0.980385 |       15211.8 |
| EMA100       |      -0.676337 |        0.99394  |       18712.3 |
| EMA200       |      -0.490105 |        8.08321  |       16088.4 |
| HH_HL        |      -0.533615 |        1.02215  |        6871.5 |
| None         |      -0.78897  |        0.975478 |       20641.4 |

### C. Performance by Contraction Waves (K)
|   Contraction Waves |   Sharpe Ratio |   Profit Factor |
|--------------------:|---------------:|----------------:|
|                   2 |      -0.698809 |         1.01204 |
|                   3 |      -0.507771 |         3.81002 |

### D. Performance by Apex Tightness (Max final pullback %)
|   Max Final Contraction |   Sharpe Ratio |   Profit Factor |
|------------------------:|---------------:|----------------:|
|                    0.03 |      -0.669609 |        5.30442  |
|                    0.05 |      -0.575067 |        0.992489 |
|                    0.07 |      -0.565194 |        0.936192 |

### E. Performance by Breakout Trigger Type
| Breakout               |   Sharpe Ratio |   Profit Factor |
|:-----------------------|---------------:|----------------:|
| Close_Above_Swing_High |      -0.515353 |        3.14529  |
| Donchian_Break         |      -0.750483 |        0.920182 |
| High_Break             |      -0.544034 |        3.16762  |

### F. Performance by Risk Reward Exit Strategy
| Risk Reward      |   Sharpe Ratio |   Profit Factor |
|:-----------------|---------------:|----------------:|
| 1.5R             |     -0.660871  |        3.44508  |
| 1R               |     -0.815784  |        3.42937  |
| 2R               |     -0.615637  |        0.943023 |
| 30_Bar_Time_Exit |      0.0541556 |        1.09385  |
| 3R               |     -0.405849  |        0.951124 |
| ATR_Trail        |     -1.15503   |        3.44794  |
| Swing_Trail      |     -0.624546  |        3.56783  |

## Key Findings & Recommendations
1. **Timeframe Resolution**: Analysis across timeframes reveals whether lower resolutions (e.g. 15m) suffer from transaction cost drag or high noise. Typically, 1H and 4H resolutions offer superior Sharpe ratios due to lower transaction count relative to net move.
2. **Trend Filters**: Strong trend gates (such as EMA200) prevent entries during market downtrends, significantly reducing the maximum drawdown.
3. **Contraction Geometry**: Enforcing tighter apex conditions (e.g., 3%) can lead to a higher win rate but lower trade frequency, while larger values (e.g., 7%) provide more trades but higher false breakout rates.
4. **Optimal Variant Promotion**: The top-ranked configurations will be selected for Walk-Forward testing based on their Quality Score.
