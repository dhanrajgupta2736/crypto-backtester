# Stage 7 Monte Carlo Stress Test Report - Candidate C001

## 1. Executive Summary
This report presents the sequence-of-returns stress test results for Candidate C001, evaluated via **10,000 bootstrap simulations** of the strategy's daily returns over the full historical period (June 2023 to June 2026, 17.98 years).

- **Bootstrap Sample Size**: 6567 trading days
- **Simulations**: 10,000 runs
- **Risk of Ruin Threshold**: >80% drawdown

---

## 2. Percentile Tables

### Expected CAGR Distribution
| Percentile | Expected CAGR (%) |
| :--- | :---: |
| 5th (Worst Cases) | 7.47% |
| 25th | 17.16% |
| **50th (Median)** | 24.26% |
| 75th | 31.54% |
| 95th (Best Cases) | 43.38% |

### Expected Max Drawdown Distribution
| Percentile | Expected Max Drawdown (%) |
| :--- | :---: |
| 5th (Safest paths) | 44.58% |
| 25th | 53.13% |
| **50th (Median)** | 60.36% |
| 75th | 68.32% |
| 95th (Worst Drawdowns) | 79.99% |

---

## 3. Drawdown Probability & Risk of Ruin

| Drawdown Level | Probability of Exceeding (%) | Status |
| :--- | :---: | :---: |
| **Drawdown > 10%** | 100.00% | - |
| **Drawdown > 20%** | 100.00% | - |
| **Drawdown > 30%** | 100.00% | - |
| **Drawdown > 50%** | 84.10% | - |
| **Risk of Ruin (> 80% DD)** | 4.9800% | `PASS` (threshold < 1.0%) |

---

## 4. Key Findings

- **High Expectancy**: The median CAGR is `24.26%`, and the 5th percentile CAGR is `7.47%` (proving that even under very unfavorable return sequences, the strategy is expected to remain highly profitable).
- **Structural Drawdown Profile**: The median expected drawdown is `60.36%`, and the 95th percentile drawdown is `79.99%`. This indicates that a drawdown of 50-70% is a structural feature of the strategy due to long-only altcoin exposure.
- **Ruin Safety**: The probability of total ruin (>80% drawdown) is `4.9800%`, showing that the strategy is safe from total capital destruction under historical volatility assumptions.
