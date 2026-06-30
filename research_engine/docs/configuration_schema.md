# QRP Framework v2.0 — Configuration Schema Reference

This document serves as the schema reference sheet for the YAML configuration dictionaries loaded by the **QRP Framework v2.0**.

---

## 1. Candidate Configuration Schema Reference

Loaded from candidate files (e.g. `research/candidate_{id}/configs/candidate.yaml`).

| Section | Parameter Key | Data Type | Constraint / Option | Description |
| :--- | :--- | :--- | :--- | :--- |
| **candidate.metadata** | `id` | string | Padded (e.g. `"C001"`) | Candidate strategy index code. |
| | `name` | string | Non-empty | Descriptive strategy family name. |
| | `version` | string | Semantic Versioning | Strategy logic revision level. |
| | `research_version` | string | e.g. `"v1.0"` | Phase identification string. |
| | `author` | string | Non-empty | Author / researcher credit. |
| | `description` | string | Non-empty | Summary of the strategy hypothesis. |
| **candidate.plugin** | `module_path` | string | Valid path within workspace | Python filepath to strategy script. |
| | `class_name` | string | Non-empty | Target strategy class name inside script. |
| **candidate.universe** | `asset_class` | string | `crypto`, `equity`, `commodity` | Target asset class adapter choice. |
| | `symbols` | list of strings | Non-empty list | Symbols array to load and parse. |
| **candidate.timeframes**| `timeframes` | list of strings | `15m`, `30m`, `1H`, `4H`, `1D` | Target timeframe resolutions. |
| **candidate.portfolio**| `max_active_positions`| integer | $\ge 1$ and $\le$ Universe Size | Position capacity slot limit ($K$). |
| | `capital_allocation` | string | `EQUAL`, `RISK_PARITY` | Capital distribution methodology. |
| | `trading_direction` | string | `LONG_ONLY`, `SHORT_ONLY`, `LONG_SHORT` | Restricts transaction orders. |
| **candidate.rebalance**| `frequency_bars` | integer | $\ge 1$ | Rebalancing interval in candles ($R$). |
| | `trigger_type` | string | `SCHEDULED`, `THRESHOLD_DISPERSION` | Rule category for rebalancing runs. |
| **candidate.exits** | `rank_decay_exit` | boolean | `true`, `false` | Enable liquidation on ranking drop. |
| | `rank_decay_threshold`| integer | $\ge 1$ | Rank below which assets exit portfolio. |
| | `stop_loss.type` | string | `ATR_MULTIPLE`, `PERCENTAGE`, `NONE` | Stop-loss calculation model. |
| | `stop_loss.multiplier`| float | $\ge 0.1$ | ATR multiplier factor for stop limits. |
| | `take_profit.type` | string | `ATR_MULTIPLE`, `PERCENTAGE`, `NONE` | Take-profit calculation model. |
| | `take_profit.multiplier`| float | $\ge 0.1$ | ATR multiplier factor for profit targets. |
| **candidate.validation**| `min_trades` | map | Key: timeframe, Value: integer | Gate threshold trade count. |
| | `performance_gates` | map | Sharpe, PF, Expectancy thresholds | Qualification requirements. |

---

## 2. Experiment Sweep Configuration Schema Reference

Loaded from sweep configurations.

| Section | Parameter Key | Data Type | Constraint / Option | Description |
| :--- | :--- | :--- | :--- | :--- |
| **experiment_sweep** | `candidate_id` | string | Must match registered Candidate ID | Targets candidate folder. |
| | `timestamp` | string | ISO 8601 Timestamp | Generation timestamp metadata. |
| **experiment_sweep.parameter_space** | `lookback_window` | list of integers | Values $\ge 1$ | Ranges of lookback bars to test. |
| | `portfolio_size_k` | list of integers | Values $\ge 1$ | Positions limits ($K$) to sweep. |
| | `rebalance_frequency_r`| list of integers | Values $\ge 1$ | Rebalance frequencies ($R$) to test. |
| | `stop_loss_multiplier` | list of floats | Values $\ge 0.1$ | Stop loss bounds to sweep. |
| | `take_profit_multiplier`| list of floats | Values $\ge 0.1$ | Take profit bounds to sweep. |
| | `exit_rank_decay_threshold`| list of integers | Values $\ge 1$ | Decay limits to sweep. |

---

## 3. Global Framework Configuration Schema Reference

Loaded from `research_engine/configs/framework_config.yaml`.

* **engine**: General performance configurations, multithreading cores (`max_workers`), and log levels (`INFO`, `WARNING`, `ERROR`, `SUCCESS`).
* **execution**: Backtesting engine default parameters, cost profiles (default maker/taker fees, default slippage), and margin requirements.
* **paths**: Centralized file path configurations for historical data, outputs, archives, registries, and dashboards.
* **adapters**: Declares support for asset resolution maps (OHLCV columns, extensions).
