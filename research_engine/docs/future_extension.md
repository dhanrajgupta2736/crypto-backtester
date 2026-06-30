# QRP Framework v2.0 — Future Extensibility Specification

This document details how the **QRP Framework v2.0** configuration system can be extended to support new asset classes, custom metrics, and future research candidates without modifying core framework code.

---

## 1. Multi-Asset Class Extension

The framework handles data ingestion through abstract **Data Adapters** defined in `framework_config.yaml`. To load a new asset class (e.g., Equities or Commodities), no changes to the backtesting engine are required. The researcher only needs to register the adapter parameters:

```yaml
# In framework_config.yaml
adapters:
  supported_asset_classes:
    - name: "equity"
      file_extension: ".csv"
      timeframe_column: "date"
      adjustments: "dividends_and_splits"
    - name: "commodity"
      file_extension: ".csv"
      timeframe_column: "timestamp"
      contracts: "continuous_roll"
```

The `DiscoveryEngine` reads this configuration and routes the database requests to the correct parser module, resolving:
* Date alignment differences (e.g. Stocks have market hours, Crypto runs 24/7).
* Adjustments (e.g., rolling stock splits, dividend distributions, or commodity futures contract rolling wicks).

---

## 2. Pluggable Metrics Engine Registry

To compute custom performance ratios, the `MetricsEngine` exposes a registry mapping metrics keys to calculation functions. If a researcher wants to introduce a new metric (e.g. Ulcer Index, Calmar Ratio, or Omega Ratio), they register the function key inside `metrics_engine.py` and call it via the candidate's YAML:

```yaml
# In candidate.yaml
validation:
  performance_gates:
    min_profit_factor: 1.15
    custom_metrics:
      - name: "calmar_ratio"
        threshold: 1.5
      - name: "omega_ratio"
        threshold: 1.2
```

The metrics loader parses these keys and evaluates them dynamically from the trade ledger, preventing hardcoded function references.

---

## 3. Extensibility for Candidate 02 and Beyond

When the quant team transitions to Candidate 02 (e.g., Mean Reversion), they execute it on the framework by creating the following:
1. **The Plugin**: `research/candidate_02_mean_reversion/code/strategy_plugin.py` exposing `StrategyPlugin(BaseStrategyPlugin)`.
2. **The Configuration**: `research/candidate_02_mean_reversion/configs/candidate.yaml` specifying parameters specific to Mean Reversion.

The framework loads Candidate 02, runs its sweeps, validates parameters, and outputs reports under `outputs/C002/` automatically. This strategy-agnostic capability ensures that the framework functions as a long-term institutional asset.
