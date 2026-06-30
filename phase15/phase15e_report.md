# Phase 15E Report: Monte Carlo Stress Testing

**Portfolio**: BTC 4H (RR=2.0) + ETH 1H (RR=2.0) + ETH 4H (RR=2.0)
**Bootstrap Population**: 180 trades from 2023-01-01 to 2026-06-19 (3.465 years)
**Simulations**: 10,000 per risk level (50,000 total)
**Ruin Definition**: Equity drawdown > 80% at any point

---

## 1. Trade Distribution (Bootstrap Population)

| Metric | Value |
| :--- | :---: |
| Total Trades | 180 |
| Win Rate | 44.4% |
| Average R | 0.2462 |
| Median R | -0.4898 |
| Average Win (R) | 1.9124 |
| Average Loss (R) | -1.0867 |
| Trades per Year | 51.9 |

---

## 2. Monte Carlo Results by Risk Level

| Risk % | Median CAGR | 5th Pct CAGR | 95th Pct CAGR | 95% DD | 99% DD | Worst DD | Worst Streak | P(DD>20%) | P(DD>30%) | P(DD>50%) | P(Ruin) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0.5%** | 6.4% | 1.2% | 12.0% | 10.8% | 13.8% | 22.2% | 22 | 0.0% | 0.0% | 0.0% | 0.0000% |
| **1.0%** | 12.8% | 2.0% | 24.9% | 20.6% | 25.9% | 39.9% | 22 | 6.1% | 0.3% | 0.0% | 0.0000% |
| **1.5%** | 19.3% | 2.6% | 38.8% | 29.6% | 36.5% | 53.9% | 22 | 33.5% | 4.5% | 0.0% | 0.0000% |
| **2.0%** ⬅ | 25.7% | 2.8% | 53.8% | 37.8% | 45.9% | 64.8% | 22 | 65.5% | 18.8% | 0.5% | 0.0000% |
| **3.0%** | 38.1% | 2.3% | 86.7% | 51.9% | 61.3% | 79.9% | 22 | 96.3% | 60.6% | 6.7% | 0.0000% |

---

## 3. Probability Risk Map

| Risk % | P(DD>20%) | P(DD>30%) | P(DD>50%) | P(Ruin >80%) |
| :---: | :---: | :---: | :---: | :---: |
| 0.5% | ✅ 0.0% | ✅ 0.0% | ✅ 0.0% | ✅ 0.0000% |
| 1.0% | ✅ 6.1% | ✅ 0.3% | ✅ 0.0% | ✅ 0.0000% |
| 1.5% | 🟡 33.5% | ✅ 4.5% | ✅ 0.0% | ✅ 0.0000% |
| 2.0% | ⚠️ 65.5% | 🟡 18.8% | ✅ 0.5% | ✅ 0.0000% |
| 3.0% | ⚠️ 96.3% | ⚠️ 60.6% | ✅ 6.7% | ✅ 0.0000% |

---

## 4. Recommended Production Risk Level

> [!IMPORTANT]
> **Recommended: 2.0% risk per trade**
>
> Risk=2.0% is the highest level where P(DD>30%)=18.8% < 25%, P(Ruin)=0.0000% < 1%, and Median CAGR=25.7% > 10%.

### Rationale for Selection Criteria

- **P(DD > 30%) < 25%**: A 30% drawdown requires ~43% recovery. Probabilities above 25% indicate unacceptable psychological and operational risk for a real trading account.
- **P(Ruin) < 1%**: An 80% loss is operationally terminal. Any meaningful ruin probability disqualifies a risk level for production.
- **Median CAGR > 10%**: Minimum return threshold for the strategy to justify its operational complexity over passive investing.

### Key Observations

1. **Return-Risk Scaling**: Median CAGR scales from 6.4% at 0.5% risk to 38.1% at 3.0% risk. Higher risk amplifies both gains and losses non-linearly.
2. **Ruin Safety**: Risk levels up to 3.0% maintain P(Ruin) effectively at 0%. The positive expectancy of this portfolio creates a strong structural defense against ruin.
3. **Worst Losing Streak**: The Monte Carlo found worst-case losing streaks of 22 consecutive losses at 3.0% risk. At 2.0% risk, this streak would cause a ~35.9% drawdown before recovery.
4. **95% DD Envelope**: Even in 95% of all simulated paths, the portfolio at 2.0% risk stays within a 37.8% maximum drawdown. This is the realistic planning envelope for live deployment.

---

## 5. Deployment Guidance

**Start at 2.0% risk per trade.**

| Phase | Risk Level | Condition |
| :--- | :---: | :--- |
| Initial Deployment | 2.0% | Starting capital |
| After 15% Drawdown | 1.00% (halved) | Defensive mode until recovery |
| After 25% Profit | 2.50% (scale-up) | Only if equity grows >25% |

> [!NOTE]
> The Monte Carlo distribution assumes trade R-multiples remain consistent with historical observations.
> Major regime changes (e.g., prolonged low-volatility periods) could shift the distribution.
> Reassess risk level every 6 months or after 50+ trades.
