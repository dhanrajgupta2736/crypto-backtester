# Candidate C003: Parameter Space

**Strategy Name**: Session Open Range Breakout (SORB)
**Candidate ID**: C003
**Research Phase**: Phase 1 — Research Only
**Created**: 2026-07-01
**Status**: `PARAMETER_SPACE_DEFINED`

---

## Overview

The parameter space defines every configurable input dimension of the SORB strategy. Each dimension is assigned a **scan range** for the Discovery Sweep and a **locked baseline** for reference.

The parameter space is deliberately kept narrow and orthogonal to minimise combinatorial explosion and overfitting risk.

---

## Dimension 1: Session Definition

| Parameter | Description | Scan Range | Baseline |
| :--- | :--- | :--- | :--- |
| `session` | The market session to trade | `['london', 'newyork', 'both']` | `'newyork'` |
| `session_open_hour_utc` | UTC hour when the session opens | Fixed: London = 7, NY = 13 | 13 |
| `open_range_minutes` | Length of the Open Range window in minutes | `[30, 60, 90]` | 60 |

**Total Dimension 1 Combinations**: 9 (3 sessions × 3 range widths)

---

## Dimension 2: Timeframe

| Parameter | Description | Scan Range | Baseline |
| :--- | :--- | :--- | :--- |
| `timeframe` | Candle granularity for entries and exits | `['15m', '1H']` | `'15m'` |

**Note**: The Open Range is always defined by summing candles within the first `open_range_minutes` of the session. A 15m timeframe uses 4 candles for a 60-minute window; 1H uses 1 candle.

---

## Dimension 3: Breakout Threshold

| Parameter | Description | Scan Range | Baseline |
| :--- | :--- | :--- | :--- |
| `breakout_buffer_atr` | Multiplier of ATR(14) added to range high before entry triggers | `[0.0, 0.1, 0.2, 0.3]` | 0.1 |

Adding a small ATR buffer prevents entry on micro-breakouts that are simply noise within the spread, requiring genuine momentum.

---

## Dimension 4: ATR Period (for buffer and stop calculation)

| Parameter | Description | Scan Range | Baseline |
| :--- | :--- | :--- | :--- |
| `atr_period` | Lookback for ATR calculation | `[10, 14, 20]` | 14 |

---

## Dimension 5: Stop-Loss

| Parameter | Description | Scan Range | Baseline |
| :--- | :--- | :--- | :--- |
| `stop_mode` | How the stop is determined | `['range_low', 'atr_stop']` | `'range_low'` |
| `atr_stop_multiplier` | ATR multiplier when stop_mode = 'atr_stop' | `[1.0, 1.5, 2.0]` | 1.5 |

- `range_low`: Stop is placed at the low of the Open Range (the baseline, natural stop).
- `atr_stop`: Stop is placed at `entry_price - N × ATR(14)` below entry.

---

## Dimension 6: Take-Profit / Exit Rule

| Parameter | Description | Scan Range | Baseline |
| :--- | :--- | :--- | :--- |
| `exit_mode` | Exit trigger mechanism | `['session_close', 'atr_target', 'fixed_rr']` | `'session_close'` |
| `atr_target_multiplier` | Risk multiple for ATR take-profit | `[2.0, 3.0, 4.0]` | 2.0 |
| `fixed_rr` | Fixed Risk:Reward ratio (applied if exit_mode = 'fixed_rr') | `[2.0, 3.0]` | 2.0 |

- `session_close`: Exit at the close of the active session window (e.g. 4H window after NY open).
- `atr_target`: Exit when price gains `N × ATR(14)` from entry.
- `fixed_rr`: Exit when reward equals `N × initial_risk`.

---

## Dimension 7: Volume Filter (Hypothesis H2)

| Parameter | Description | Scan Range | Baseline |
| :--- | :--- | :--- | :--- |
| `volume_filter` | Whether to require above-average session open volume | `[True, False]` | False |
| `volume_lookback` | Sessions used to compute average volume | `[10, 20]` | 20 |
| `volume_threshold_pct` | Minimum percentile of session volume required | `[50, 75]` | 50 |

---

## Dimension 8: Trend Filter (Hypothesis H3)

| Parameter | Description | Scan Range | Baseline |
| :--- | :--- | :--- | :--- |
| `trend_filter` | Whether to require structural uptrend alignment | `[True, False]` | False |
| `trend_ema_period` | EMA period used for trend definition | `[50, 100, 200]` | 50 |

---

## Full Combinatorial Count (Discovery Sweep)

| Dimension | Options |
| :--- | :---: |
| Session × Range Width | 9 |
| Timeframe | 2 |
| Breakout Buffer | 4 |
| ATR Period | 3 |
| Stop Mode × Multiplier | 5 (2 + 3) |
| Exit Mode × Multiplier | 7 (1 + 3 + 2) |
| Volume Filter | 5 (off + 4 combos) |
| Trend Filter | 7 (off + 6 combos) |

**Maximum combinatorial space**: ~9 × 2 × 4 × 3 × 5 × 7 × 5 × 7 = **79,380 configurations**

### Practical Sweep Strategy
For the initial Discovery Sweep, we will fix low-interaction dimensions to their baseline values and scan the highest-impact dimensions independently:

**Priority Scan Grid (Phase 2 Discovery)**:
- Session × Open Range Width: 9 combinations
- Timeframe: 2 values
- Breakout Buffer: 4 values
- Stop Mode: 2 values
- Exit Mode: 3 values

**Estimated Initial Sweep**: 9 × 2 × 4 × 2 × 3 = **432 configurations** (manageable baseline)

Volume filter and trend filter are added as orthogonal top-N refinement passes after the baseline sweep.

---

## Parameter Locking Rules

1. **No parameter may be added after the Discovery Sweep begins** without a formal ledger entry.
2. **No parameter may be tuned toward known in-sample results** — all scan ranges are defined before any backtests are run.
3. **Winner selection is performed by Sharpe Ratio + Trade Count minimum gate**, not by maximising any single metric.

---

## Banned Parameters (Overfitting Prevention)

The following indicator families are **banned** during the Discovery Sweep:
- RSI / Stochastic / MACD
- Bollinger Bands
- ADX / DI+/DI-
- On-Balance Volume (OBV)
- VWAP (as a filter — acceptable as a future extension in later phases)

These can be introduced as refinement filters only after the core SORB edge is independently validated.
