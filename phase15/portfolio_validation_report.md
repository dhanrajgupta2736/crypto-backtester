# Phase 15D Portfolio Validation Report

**Strategy**: `VE_3_ATR_EXPANSION`
**Portfolio**: BTC 4H (RR=2.0) + ETH 1H (RR=2.0) + ETH 4H (RR=2.0)
**Risk per Trade**: 2% of current portfolio equity (dynamic)
**Simultaneous Positions**: Allowed
**Periods**: Selection 2023-2024 | Holdout 1 (2025) | Holdout 2 (2026)

---

## 1. Portfolio Performance by Period

| Period | Trades | Win Rate | PF | Sharpe | Expectancy | CAGR | Max DD | Ulcer Index | Risk of Ruin | Avg Concurrent |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Selection | 96 | 39.58% | 1.11 | 0.44 | 0.0978 | 6.81% | 28.22% | 11.6147 | 0.0055% | 0.70 |
| Holdout_1 | 48 | 50.0% | 1.49 | 0.99 | 0.3685 | 36.11% | 17.64% | 6.4798 | 0.0000% | 0.65 |
| Holdout_2 | 36 | 50.0% | 1.88 | 1.81 | 0.4789 | 88.54% | 9.51% | 4.3560 | 0.0000% | 0.83 |

## 2. Success Criteria

- [x] H1 PF > 1.20
- [x] H1 Expectancy > 0
- [x] H1 Net Return > 0
- [x] H2 PF > 1.20
- [x] H2 Expectancy > 0
- [x] H2 Net Return > 0

> [!IMPORTANT]
> **PORTFOLIO PASSED** — All success criteria met. The ATR Expansion family
> demonstrates robust, deployable edge as a real multi-instrument portfolio.

---

## 3. Instrument Contribution by Period

### Selection

| Instrument | Trades | Win Rate |
| :--- | :---: | :---: |
| BTC 4H | 18 | 38.9% |
| ETH 1H | 64 | 40.6% |
| ETH 4H | 14 | 35.7% |

### Holdout_1

| Instrument | Trades | Win Rate |
| :--- | :---: | :---: |
| BTC 4H | 9 | 55.6% |
| ETH 1H | 32 | 50.0% |
| ETH 4H | 7 | 42.9% |

### Holdout_2

| Instrument | Trades | Win Rate |
| :--- | :---: | :---: |
| BTC 4H | 5 | 60.0% |
| ETH 1H | 25 | 48.0% |
| ETH 4H | 6 | 50.0% |

---

## 4. Key Observations

### Risk of Ruin Interpretation
Risk of Ruin is computed using the classical formula:
```
RoR = ((1 - edge) / (1 + edge))^N
where edge = win_rate * avg_win_R - loss_rate * avg_loss_R
      N    = 1 / risk_pct = 50 units of risk in the starting bankroll
```
Values < 5% are considered acceptable for live deployment.

### Ulcer Index Interpretation
Ulcer Index weights prolonged drawdowns more severely than Max Drawdown.
Values < 5 indicate low stress on the account; values > 15 indicate high prolonged pain.

### Average Concurrent Positions
Indicates how many positions were open simultaneously on average.
Higher values increase correlated-loss risk during adverse regimes.

### Dynamic Sizing Note
Each trade is sized at 2% of equity AT THE TIME OF THE PREVIOUS EXIT.
A winning run compounds gains; a losing run reduces exposure naturally.
This is the most realistic sizing model for live portfolio deployment.
