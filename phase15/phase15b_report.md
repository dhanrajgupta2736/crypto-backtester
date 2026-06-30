# Phase 15B Validation Report: Volatility Expansion Robustness Test

This report presents the out-of-sample validation of the strongest Volatility Expansion candidate strategy configurations (`VE_3_ATR_EXPANSION` at the `4H` timeframe). The analysis checks for validation across three non-overlapping historical windows:
*   **Selection Period (2023-2024)**: The in-sample discovery window.
*   **Holdout Period 1 (2025)**: Out-of-sample window (requires Trades $\ge 20$, PF $> 1.10$, Expectancy $> 0$, Net Return $> 0$).
*   **Holdout Period 2 (2026)**: Out-of-sample window (requires Trades $\ge 10$, PF $> 1.10$, Expectancy $> 0$, Net Return $> 0$).

## 1. Validation Status Summary

Out of **16** candidates evaluated, **0** passed the out-of-sample validation criteria.

> [!WARNING]
> **No candidates passed the out-of-sample validation.** All tested configurations failed to meet the validation thresholds in both holdout windows.

---

## 2. Detailed Performance Table

| Candidate | Period | Trades | Win Rate | Profit Factor | Sharpe Ratio | Max Drawdown | Expectancy (R) | Net Return | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BTC 4H (RR=1.0)** | Selection | 20 | 60.0% | 2.25 | 1.42 | 14.02% | 0.3197 | 61.28% | `FAIL` |
| **BTC 4H (RR=1.0)** | Holdout_1 | 10 | 70.0% | 2.00 | 0.87 | 14.73% | 0.3191 | 30.07% | `FAIL` |
| **BTC 4H (RR=1.0)** | Holdout_2 | 6 | 100.0% | 999.90 | 2.48 | 0.00% | 0.6701 | 38.07% | `FAIL` |
| **BTC 4H (RR=1.5)** | Selection | 19 | 47.37% | 1.85 | 1.06 | 21.30% | 0.2879 | 61.35% | `FAIL` |
| **BTC 4H (RR=1.5)** | Holdout_1 | 10 | 70.0% | 3.08 | 1.33 | 12.16% | 0.6575 | 62.29% | `FAIL` |
| **BTC 4H (RR=1.5)** | Holdout_2 | 5 | 60.0% | 1.50 | 1.18 | 24.01% | 0.2209 | 12.11% | `FAIL` |
| **BTC 4H (RR=2.0)** | Selection | 18 | 38.89% | 1.60 | 0.80 | 25.98% | 0.2780 | 48.46% | `FAIL` |
| **BTC 4H (RR=2.0)** | Holdout_1 | 9 | 55.56% | 2.25 | 0.83 | 14.00% | 0.6073 | 51.18% | `FAIL` |
| **BTC 4H (RR=2.0)** | Holdout_2 | 5 | 60.0% | 2.10 | 1.47 | 24.01% | 0.5210 | 26.33% | `FAIL` |
| **BTC 4H (RR=3.0)** | Selection | 18 | 38.89% | 1.96 | 0.96 | 25.98% | 0.4557 | 77.48% | `FAIL` |
| **BTC 4H (RR=3.0)** | Holdout_1 | 7 | 42.86% | 2.11 | 0.47 | 14.66% | 0.6973 | 46.22% | `FAIL` |
| **BTC 4H (RR=3.0)** | Holdout_2 | 4 | 50.0% | 2.14 | 1.29 | 24.01% | 0.6889 | 27.35% | `FAIL` |
| **LINK 4H (RR=1.0)** | Selection | 16 | 75.0% | 5.19 | 1.82 | 6.97% | 0.6364 | 96.77% | `FAIL` |
| **LINK 4H (RR=1.0)** | Holdout_1 | 2 | 0.0% | 0.00 | -3.17 | 24.36% | -1.2492 | -24.36% | `FAIL` |
| **LINK 4H (RR=1.0)** | Holdout_2 | 3 | 66.67% | 0.89 | -0.49 | 12.97% | -0.0512 | -1.47% | `FAIL` |
| **LINK 4H (RR=1.5)** | Selection | 16 | 62.5% | 2.37 | 1.15 | 10.89% | 0.5065 | 76.43% | `FAIL` |
| **LINK 4H (RR=1.5)** | Holdout_1 | 2 | 0.0% | 0.00 | -3.17 | 24.36% | -1.2492 | -24.36% | `FAIL` |
| **LINK 4H (RR=1.5)** | Holdout_2 | 3 | 66.67% | 1.59 | 0.02 | 12.38% | 0.2875 | 8.04% | `FAIL` |
| **LINK 4H (RR=2.0)** | Selection | 15 | 53.33% | 2.21 | 1.12 | 10.44% | 0.5378 | 75.85% | `FAIL` |
| **LINK 4H (RR=2.0)** | Holdout_1 | 2 | 0.0% | 0.00 | -3.17 | 24.36% | -1.2492 | -24.36% | `FAIL` |
| **LINK 4H (RR=2.0)** | Holdout_2 | 3 | 66.67% | 2.30 | 0.38 | 11.84% | 0.6282 | 17.61% | `FAIL` |
| **LINK 4H (RR=3.0)** | Selection | 13 | 53.85% | 3.18 | 1.21 | 9.64% | 0.8349 | 101.61% | `FAIL` |
| **LINK 4H (RR=3.0)** | Holdout_1 | 2 | 0.0% | 0.00 | -3.17 | 24.36% | -1.2492 | -24.36% | `FAIL` |
| **LINK 4H (RR=3.0)** | Holdout_2 | 3 | 66.67% | 3.68 | 0.78 | 10.89% | 1.2965 | 36.39% | `FAIL` |
| **XRP 4H (RR=1.0)** | Selection | 24 | 62.5% | 2.15 | 0.45 | 13.03% | 0.4339 | 98.09% | `FAIL` |
| **XRP 4H (RR=1.0)** | Holdout_1 | 9 | 11.11% | 0.17 | -2.13 | 72.04% | -0.8249 | -72.04% | `FAIL` |
| **XRP 4H (RR=1.0)** | Holdout_2 | 3 | 33.33% | 0.09 | -1.88 | 30.15% | -1.0028 | -28.15% | `FAIL` |
| **XRP 4H (RR=1.5)** | Selection | 23 | 56.52% | 2.35 | 0.71 | 22.29% | 0.5864 | 127.49% | `FAIL` |
| **XRP 4H (RR=1.5)** | Holdout_1 | 9 | 11.11% | 0.22 | -2.02 | 67.41% | -0.7712 | -67.41% | `FAIL` |
| **XRP 4H (RR=1.5)** | Holdout_2 | 3 | 33.33% | 0.25 | -1.89 | 28.79% | -0.8357 | -23.29% | `FAIL` |
| **XRP 4H (RR=2.0)** | Selection | 23 | 60.87% | 2.92 | 1.11 | 17.78% | 0.8324 | 181.03% | `FAIL` |
| **XRP 4H (RR=2.0)** | Holdout_1 | 9 | 11.11% | 0.28 | -1.85 | 63.73% | -0.7174 | -62.73% | `FAIL` |
| **XRP 4H (RR=2.0)** | Holdout_2 | 3 | 33.33% | 0.41 | -1.90 | 27.50% | -0.6620 | -18.24% | `FAIL` |
| **XRP 4H (RR=3.0)** | Selection | 21 | 42.86% | 2.10 | 0.71 | 33.80% | 0.7691 | 152.16% | `FAIL` |
| **XRP 4H (RR=3.0)** | Holdout_1 | 9 | 11.11% | 0.39 | -1.35 | 58.41% | -0.6100 | -53.37% | `FAIL` |
| **XRP 4H (RR=3.0)** | Holdout_2 | 3 | 33.33% | 0.74 | -1.90 | 25.24% | -0.3147 | -8.14% | `FAIL` |
| **AVAX 4H (RR=1.0)** | Selection | 15 | 60.0% | 1.39 | 0.42 | 16.20% | 0.1431 | 20.45% | `FAIL` |
| **AVAX 4H (RR=1.0)** | Holdout_1 | 6 | 50.0% | 0.59 | 0.21 | 17.37% | -0.2575 | -15.36% | `FAIL` |
| **AVAX 4H (RR=1.0)** | Holdout_2 | 1 | 0.0% | 0.00 | 0.00 | 1.52% | -0.1599 | -1.52% | `FAIL` |
| **AVAX 4H (RR=1.5)** | Selection | 14 | 57.14% | 1.91 | 0.85 | 12.45% | 0.3826 | 51.14% | `FAIL` |
| **AVAX 4H (RR=1.5)** | Holdout_1 | 5 | 60.0% | 1.17 | 1.03 | 17.37% | 0.1175 | 5.21% | `FAIL` |
| **AVAX 4H (RR=1.5)** | Holdout_2 | 1 | 100.0% | 999.90 | 0.00 | 0.00% | 0.3218 | 3.05% | `FAIL` |
| **AVAX 4H (RR=2.0)** | Selection | 12 | 50.0% | 1.81 | 0.61 | 19.26% | 0.4199 | 48.17% | `FAIL` |
| **AVAX 4H (RR=2.0)** | Holdout_1 | 5 | 40.0% | 0.80 | 0.44 | 27.80% | -0.1700 | -8.45% | `FAIL` |
| **AVAX 4H (RR=2.0)** | Holdout_2 | 1 | 100.0% | 999.90 | 0.00 | 0.00% | 0.8027 | 7.62% | `FAIL` |
| **AVAX 4H (RR=3.0)** | Selection | 11 | 36.36% | 1.66 | 0.41 | 19.54% | 0.4424 | 45.55% | `FAIL` |
| **AVAX 4H (RR=3.0)** | Holdout_1 | 4 | 50.0% | 1.87 | 0.96 | 27.80% | 0.6260 | 24.16% | `FAIL` |
| **AVAX 4H (RR=3.0)** | Holdout_2 | 1 | 0.0% | 0.00 | 0.00 | 20.02% | -2.1098 | -20.02% | `FAIL` |

---

## 3. Analysis & Key Takeaways

### BTC Candidates Performance
*   **RR=1.0**:
    *   *Selection (23-24)*: 20 trades | PF: 2.25 | Net Return: 61.28%
    *   *Holdout 1 (2025)*: 10 trades | PF: 2.00 | Net Return: 30.07%
    *   *Holdout 2 (2026)*: 6 trades | PF: 999.90 | Net Return: 38.07%
    *   *Failure Reason*: H1 Trades (10) < 20, H2 Trades (6) < 10
*   **RR=1.5**:
    *   *Selection (23-24)*: 19 trades | PF: 1.85 | Net Return: 61.35%
    *   *Holdout 1 (2025)*: 10 trades | PF: 3.08 | Net Return: 62.29%
    *   *Holdout 2 (2026)*: 5 trades | PF: 1.50 | Net Return: 12.11%
    *   *Failure Reason*: H1 Trades (10) < 20, H2 Trades (5) < 10
*   **RR=2.0**:
    *   *Selection (23-24)*: 18 trades | PF: 1.60 | Net Return: 48.46%
    *   *Holdout 1 (2025)*: 9 trades | PF: 2.25 | Net Return: 51.18%
    *   *Holdout 2 (2026)*: 5 trades | PF: 2.10 | Net Return: 26.33%
    *   *Failure Reason*: H1 Trades (9) < 20, H2 Trades (5) < 10
*   **RR=3.0**:
    *   *Selection (23-24)*: 18 trades | PF: 1.96 | Net Return: 77.48%
    *   *Holdout 1 (2025)*: 7 trades | PF: 2.11 | Net Return: 46.22%
    *   *Holdout 2 (2026)*: 4 trades | PF: 2.14 | Net Return: 27.35%
    *   *Failure Reason*: H1 Trades (7) < 20, H2 Trades (4) < 10

### LINK Candidates Performance
*   **RR=1.0**:
    *   *Selection (23-24)*: 16 trades | PF: 5.19 | Net Return: 96.77%
    *   *Holdout 1 (2025)*: 2 trades | PF: 0.00 | Net Return: -24.36%
    *   *Holdout 2 (2026)*: 3 trades | PF: 0.89 | Net Return: -1.47%
    *   *Failure Reason*: H1 Trades (2) < 20, H1 PF (0.00) <= 1.10, H1 Expectancy (-1.249) <= 0, H1 Return (-24.36%) <= 0, H2 Trades (3) < 10, H2 PF (0.89) <= 1.10, H2 Expectancy (-0.0512) <= 0, H2 Return (-1.47%) <= 0
*   **RR=1.5**:
    *   *Selection (23-24)*: 16 trades | PF: 2.37 | Net Return: 76.43%
    *   *Holdout 1 (2025)*: 2 trades | PF: 0.00 | Net Return: -24.36%
    *   *Holdout 2 (2026)*: 3 trades | PF: 1.59 | Net Return: 8.04%
    *   *Failure Reason*: H1 Trades (2) < 20, H1 PF (0.00) <= 1.10, H1 Expectancy (-1.249) <= 0, H1 Return (-24.36%) <= 0, H2 Trades (3) < 10
*   **RR=2.0**:
    *   *Selection (23-24)*: 15 trades | PF: 2.21 | Net Return: 75.85%
    *   *Holdout 1 (2025)*: 2 trades | PF: 0.00 | Net Return: -24.36%
    *   *Holdout 2 (2026)*: 3 trades | PF: 2.30 | Net Return: 17.61%
    *   *Failure Reason*: H1 Trades (2) < 20, H1 PF (0.00) <= 1.10, H1 Expectancy (-1.249) <= 0, H1 Return (-24.36%) <= 0, H2 Trades (3) < 10
*   **RR=3.0**:
    *   *Selection (23-24)*: 13 trades | PF: 3.18 | Net Return: 101.61%
    *   *Holdout 1 (2025)*: 2 trades | PF: 0.00 | Net Return: -24.36%
    *   *Holdout 2 (2026)*: 3 trades | PF: 3.68 | Net Return: 36.39%
    *   *Failure Reason*: H1 Trades (2) < 20, H1 PF (0.00) <= 1.10, H1 Expectancy (-1.249) <= 0, H1 Return (-24.36%) <= 0, H2 Trades (3) < 10

### XRP Candidates Performance
*   **RR=1.0**:
    *   *Selection (23-24)*: 24 trades | PF: 2.15 | Net Return: 98.09%
    *   *Holdout 1 (2025)*: 9 trades | PF: 0.17 | Net Return: -72.04%
    *   *Holdout 2 (2026)*: 3 trades | PF: 0.09 | Net Return: -28.15%
    *   *Failure Reason*: H1 Trades (9) < 20, H1 PF (0.17) <= 1.10, H1 Expectancy (-0.8249) <= 0, H1 Return (-72.04%) <= 0, H2 Trades (3) < 10, H2 PF (0.09) <= 1.10, H2 Expectancy (-1.003) <= 0, H2 Return (-28.15%) <= 0
*   **RR=1.5**:
    *   *Selection (23-24)*: 23 trades | PF: 2.35 | Net Return: 127.49%
    *   *Holdout 1 (2025)*: 9 trades | PF: 0.22 | Net Return: -67.41%
    *   *Holdout 2 (2026)*: 3 trades | PF: 0.25 | Net Return: -23.29%
    *   *Failure Reason*: H1 Trades (9) < 20, H1 PF (0.22) <= 1.10, H1 Expectancy (-0.7712) <= 0, H1 Return (-67.41%) <= 0, H2 Trades (3) < 10, H2 PF (0.25) <= 1.10, H2 Expectancy (-0.8357) <= 0, H2 Return (-23.29%) <= 0
*   **RR=2.0**:
    *   *Selection (23-24)*: 23 trades | PF: 2.92 | Net Return: 181.03%
    *   *Holdout 1 (2025)*: 9 trades | PF: 0.28 | Net Return: -62.73%
    *   *Holdout 2 (2026)*: 3 trades | PF: 0.41 | Net Return: -18.24%
    *   *Failure Reason*: H1 Trades (9) < 20, H1 PF (0.28) <= 1.10, H1 Expectancy (-0.7174) <= 0, H1 Return (-62.73%) <= 0, H2 Trades (3) < 10, H2 PF (0.41) <= 1.10, H2 Expectancy (-0.662) <= 0, H2 Return (-18.24%) <= 0
*   **RR=3.0**:
    *   *Selection (23-24)*: 21 trades | PF: 2.10 | Net Return: 152.16%
    *   *Holdout 1 (2025)*: 9 trades | PF: 0.39 | Net Return: -53.37%
    *   *Holdout 2 (2026)*: 3 trades | PF: 0.74 | Net Return: -8.14%
    *   *Failure Reason*: H1 Trades (9) < 20, H1 PF (0.39) <= 1.10, H1 Expectancy (-0.61) <= 0, H1 Return (-53.37%) <= 0, H2 Trades (3) < 10, H2 PF (0.74) <= 1.10, H2 Expectancy (-0.3147) <= 0, H2 Return (-8.14%) <= 0

### AVAX Candidates Performance
*   **RR=1.0**:
    *   *Selection (23-24)*: 15 trades | PF: 1.39 | Net Return: 20.45%
    *   *Holdout 1 (2025)*: 6 trades | PF: 0.59 | Net Return: -15.36%
    *   *Holdout 2 (2026)*: 1 trades | PF: 0.00 | Net Return: -1.52%
    *   *Failure Reason*: H1 Trades (6) < 20, H1 PF (0.59) <= 1.10, H1 Expectancy (-0.2575) <= 0, H1 Return (-15.36%) <= 0, H2 Trades (1) < 10, H2 PF (0.00) <= 1.10, H2 Expectancy (-0.1599) <= 0, H2 Return (-1.52%) <= 0
*   **RR=1.5**:
    *   *Selection (23-24)*: 14 trades | PF: 1.91 | Net Return: 51.14%
    *   *Holdout 1 (2025)*: 5 trades | PF: 1.17 | Net Return: 5.21%
    *   *Holdout 2 (2026)*: 1 trades | PF: 999.90 | Net Return: 3.05%
    *   *Failure Reason*: H1 Trades (5) < 20, H2 Trades (1) < 10
*   **RR=2.0**:
    *   *Selection (23-24)*: 12 trades | PF: 1.81 | Net Return: 48.17%
    *   *Holdout 1 (2025)*: 5 trades | PF: 0.80 | Net Return: -8.45%
    *   *Holdout 2 (2026)*: 1 trades | PF: 999.90 | Net Return: 7.62%
    *   *Failure Reason*: H1 Trades (5) < 20, H1 PF (0.80) <= 1.10, H1 Expectancy (-0.17) <= 0, H1 Return (-8.45%) <= 0, H2 Trades (1) < 10
*   **RR=3.0**:
    *   *Selection (23-24)*: 11 trades | PF: 1.66 | Net Return: 45.55%
    *   *Holdout 1 (2025)*: 4 trades | PF: 1.87 | Net Return: 24.16%
    *   *Holdout 2 (2026)*: 1 trades | PF: 0.00 | Net Return: -20.02%
    *   *Failure Reason*: H1 Trades (4) < 20, H2 Trades (1) < 10, H2 PF (0.00) <= 1.10, H2 Expectancy (-2.11) <= 0, H2 Return (-20.02%) <= 0

## 4. Synthesis & Recommendations

### Did ATR Expansion Prove Robust?
No, **all** configurations failed the out-of-sample validation checks. While the strategy was highly profitable in-sample (23-24), its edge completely decayed or did not maintain the required trade density / profitability in 2025 and 2026. This indicates that the discovery results were likely an artifact of the specific trending regime of 2023-2024 (bull market and structural expansion) and did not hold up under different market regimes (e.g. 2025 range or 2026 correction).

### Recommendations for Next Phase:
1.  **If there are passing candidates**: Focus parameter sweeps and trailing-stop optimizations solely on those configurations that passed.
2.  **If no candidates passed**: Investigate whether macro filters (such as volume filters or trend direction filters) can reduce false breakouts, or explore regime-aware execution models.
