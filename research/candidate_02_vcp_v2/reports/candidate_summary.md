# Candidate C002 Version 2 — Discovery Summary

This document summarizes the results of the Version 2 parameter sweep, which tested varying Swing Window values (`[3, 5, 7]`) across `1H` and `4H` timeframes under locked V1 baseline settings.

## Discovery Matrix Performance Table

| Experiment ID   | Timeframe   |   Swing Window |   Trade Count |   Win Rate |   Profit Factor |   Expectancy (USD) |      CAGR |   Sharpe Ratio |   Max Drawdown |     Fee % |   Quality Score | Verdict    |
|:----------------|:------------|---------------:|--------------:|-----------:|----------------:|-------------------:|----------:|---------------:|---------------:|----------:|----------------:|:-----------|
| C002_V2_E06     | 4H          |              7 |            71 |    78.8732 |       10.5852   |            4.82762 |  20.1046  |       1.29969  |        10.1037 |   1.39333 |       12.4267   | PASS       |
| C002_V2_E04     | 4H          |              3 |           151 |    74.1722 |        1.46403  |            2.9771  |   8.77326 |       0.508917 |        27.4026 |  10.1115  |        1.90282  | BORDERLINE |
| C002_V2_E01     | 1H          |              3 |           725 |    65.5172 |        1.25496  |            2.09963 |  19.7887  |       0.709678 |        33.8464 |  17.6154  |        1.89293  | BORDERLINE |
| C002_V2_E05     | 4H          |              5 |           100 |    87      |        1.4531   |            6.3521  |   6.34356 |       0.437724 |        22.4059 |   8.58723 |        1.84269  | REJECT     |
| C002_V2_E02     | 1H          |              5 |           592 |    59.6284 |        0.8114   |            1.24873 | -13.087   |      -0.335051 |        49.9975 | 150.027   |       -0.941285 | REJECT     |
| C002_V2_E03     | 1H          |              7 |           431 |    67.5174 |        0.878856 |            3.43976 |  -6.16022 |      -0.178689 |        38.9384 | 253.206   |       -1.04459  | REJECT     |

---

## Winning Variant Details
* **Timeframe**: 4H
* **Swing Window**: 7
* **Trade Count**: 71
* **Sharpe Ratio**: 1.2997
* **Profit Factor**: 10.5852
* **Max Drawdown**: 10.10%
* **Verdict**: **PASS**
