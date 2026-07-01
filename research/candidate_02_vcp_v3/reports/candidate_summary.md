# Candidate C002 Version 3 — Discovery Summary

This document summarizes the results of the Version 3 parameter sweep, which tested varying Contraction Waves (`[2, 3, "adaptive"]`) across `1H` and `4H` timeframes under locked V1 baseline settings.

## Discovery Matrix Performance Table

| Experiment ID   | Timeframe   | Contraction Waves   |   Trade Count |   Win Rate |   Profit Factor |   Expectancy (USD) |    CAGR |   Sharpe Ratio |   Max Drawdown |    Fee % |   Quality Score | Verdict    |
|:----------------|:------------|:--------------------|--------------:|-----------:|----------------:|-------------------:|--------:|---------------:|---------------:|---------:|----------------:|:-----------|
| C002_V3_E05     | 4H          | 3                   |           127 |    77.9528 |         4.10075 |            4.27933 | 12.4699 |       0.7574   |        17.2163 |  2.28118 |         5.05328 | BORDERLINE |
| C002_V3_E06     | 4H          | adaptive            |           288 |    80.5556 |         2.56541 |            5.52996 | 22.9342 |       0.853116 |        18.3242 |  3.52851 |         3.6442  | BORDERLINE |
| C002_V3_E04     | 4H          | 2                   |           262 |    86.6412 |         2.05434 |            7.22948 | 16.3195 |       0.670266 |        23.2036 |  4.39403 |         2.80574 | BORDERLINE |
| C002_V3_E01     | 1H          | 2                   |          3836 |    71.0375 |         1.28183 |            3.40232 | 36.2632 |       0.828666 |        45.8274 | 13.8894  |         1.99711 | REJECT     |
| C002_V3_E03     | 1H          | adaptive            |          4340 |    74.2627 |         1.21643 |            3.55739 | 34.9114 |       0.814724 |        46.922  | 16.5857  |         1.88636 | REJECT     |
| C002_V3_E02     | 1H          | 3                   |          1106 |    75.226  |         1.16535 |            4.22263 | 11.8296 |       0.479092 |        39.5448 | 19.0816  |         1.39314 | REJECT     |

---

## Winning Variant Details
* **Timeframe**: 4H
* **Contraction Waves**: 3
* **Trade Count**: 127
* **Sharpe Ratio**: 0.7574
* **Profit Factor**: 4.1007
* **Max Drawdown**: 17.22%
* **Verdict**: **BORDERLINE**
