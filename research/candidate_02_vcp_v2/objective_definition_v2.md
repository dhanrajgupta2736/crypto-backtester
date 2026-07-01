# Objective Definition — Candidate C002 Version 2

## 1. Background & V1 Failure Analysis
Candidate C002 Version 1 (Volatility Contraction Pattern) successfully demonstrated a strong mathematical edge during Walk-Forward Validation, achieving positive out-of-sample Sharpe ratios in all periods (Selection: `0.7460`, Holdout 1: `1.9269`, Holdout 2: `1.1563`) and extremely low maximum drawdowns (averaging `7.23%`). 

However, Version 1 was **rejected** (`VALIDATION_FAILED`) due to failing the strict trade density gate of **$\ge 30$ trades per fold**. The trade counts were highly skewed and insufficient:
* **Selection (1.5 years)**: 16 trades (Failed)
* **Holdout 1 (1.0 year)**: 54 trades (Passed)
* **Holdout 2 (0.5 years)**: 1 trade (Failed)

The high selectivity was caused by the combination of a strict 3-wave VCP consolidation requirement, an apex tightness threshold of $\le 5\%$, and a slow swing detection window of `7` bars.

---

## 2. Version 2 Objective
The primary objective of Version 2 is to **systematically increase trade frequency (density) across all validation folds while preserving the positive expectancy and low drawdown profile discovered in Version 1**.

### Key Targets:
* **Trade Density**: $\ge 30$ trades in every fold (Selection, Holdout 1, Holdout 2) on the 4H timeframe, and $\ge 60$ trades in every fold on the 1H timeframe.
* **Sharpe Ratio**: $\ge 1.0$ in selection (in-sample) and $\ge 0.8$ in out-of-sample folds.
* **Max Drawdown**: $\le 15\%$ on standalone assets and $\le 30\%$ on the portfolio level.
* **Win Rate**: $\ge 40\%$.
* **Profit Factor**: $\ge 1.20$.

---

## 3. Scope of Constraints & Settings

### Unchanged from Version 1:
* **Universe**: Same 25-coin universe (no blacklisting).
* **Framework**: Same universal configuration and validation rules.
* **Backtesting Engine**: Same execution simulator and transaction cost assumptions (taker fees & slippage).
* **Validation Periods**: Same non-overlapping folds:
  * Selection: 2023-06-21 to 2024-12-31
  * Holdout 1: 2025-01-01 to 2025-12-31
  * Holdout 2: 2026-01-01 to 2026-06-19

### Modified in Version 2:
* **Timeframes**: Only `1H` and `4H` (excluding `15m` to avoid high transaction fee drag on lower timeframes).
* **Single Major Research Dimension Change**: Relaxing the **Swing Detection** window (`swing_window` parameter) from a fixed `7` bars to a compact range of `[3, 5, 7]` bars to allow shorter-duration swings to build contraction patterns.
