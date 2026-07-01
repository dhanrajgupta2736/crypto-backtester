# Walk-Forward Validation Summary - Candidate C002

This document compiles the performance of the discovered configuration `C002-E04426` (4H timeframe, Trend Gate HH_HL, swing_window 7, contraction_waves 3, max_final_contraction 0.05, breakout Close_Above_Swing_High, risk_reward Swing_Trail, stop_buffer 0.0) across the three non-overlapping validation periods.

## Performance Table

| Fold Name        |    CAGR |   Sharpe Ratio |   Profit Factor |   Max Drawdown |   Trade Count |   Win Rate |   Expectancy (USD) |   Avg Holding Period |   Portfolio Turnover |   Fee % |   Net return % |
|:-----------------|--------:|---------------:|----------------:|---------------:|--------------:|-----------:|-------------------:|---------------------:|---------------------:|--------:|---------------:|
| Selection        |  7.5831 |       0.745972 |         3.03814 |        6.24806 |            16 |    18.75   |           -1.60293 |              40      |              3.73559 | 2.60877 |       11.8449  |
| Holdout_1        | 47.7824 |       1.92688  |        30.2415  |        7.93688 |            54 |    96.2963 |            6.73193 |              83.5556 |              4.67243 | 1.04842 |       47.6243  |
| Holdout_2        | 10.8356 |       1.1563   |       999       |        7.51208 |             1 |   100      |            4.8833  |             188      |              1.00978 | 1.81731 |        4.87867 |
| AGGREGATE / MEAN | 22.067  |       1.27638  |       344.093   |        7.23234 |            71 |    71.6821 |            3.33743 |             103.852  |              3.13927 | 1.82483 |       21.4493  |

---

## Verdict & Promotion Status
- **Final Verdict**: **REJECT**
- **Justification**: Failed validation due to: insufficient trade count (<30) in some folds.
- **Status Change**: Proceed to `VALIDATION_FAILED`.
