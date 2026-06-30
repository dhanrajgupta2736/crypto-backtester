# Walk-Forward Validation Summary - Candidate C001

This document compiles the performance of the discovered configuration `C001-E00077` (4H timeframe, Lookback 100, K=3, R=4) across the three non-overlapping validation periods.

## Performance Table

| Fold Name        |     CAGR |   Sharpe Ratio |   Profit Factor |   Max Drawdown |   Trade Count |   Win Rate |   Expectancy (USD) |   Avg Holding Period |   Portfolio Turnover |   Fee % |   Net return % |
|:-----------------|---------:|---------------:|----------------:|---------------:|--------------:|-----------:|-------------------:|---------------------:|---------------------:|--------:|---------------:|
| Selection        | 550.396  |        2.61029 |         1.89061 |        62.7897 |          1451 |    62.0262 |           13.4884  |              158.856 |             128.313  | 2.90659 |      1657.82   |
| Holdout_1        |  75.2935 |        1.07734 |         1.21804 |        53.0275 |           935 |    62.4599 |            9.30492 |              137.048 |              87.9393 | 9.90479 |        74.8579 |
| Holdout_2        | 195.427  |        1.68986 |         1.66464 |        34.203  |           399 |    65.1629 |           10.1583  |              149.885 |              32.5695 | 4.23948 |        64.9726 |
| AGGREGATE / MEAN | 273.705  |        1.79249 |         1.59109 |        50.0067 |          2785 |    63.2163 |           10.9839  |              148.596 |              82.9407 | 5.68362 |       599.217  |

---

## Verdict & Promotion Status
- **Final Verdict**: **BORDERLINE**
- **Justification**: Profitable and viable across all folds, but maximum drawdowns exceeded 45% safety gate (remained under 65%).
- **Status Change**: Proceed to `READY_FOR_FINAL_HOLDOUT`.
