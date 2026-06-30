# QRP Framework v2.0 — Configuration Validation Specification

This document details the validation checks and verification rules performed by the configuration validation layer of the **QRP Framework v2.0** before starting any backtesting.

---

## 1. Pre-Flight Validation Rules

To prevent waste of processing time and file storage on corrupted or mismatched configurations, the framework runs a strict **Pre-Flight Validation** check. Any warning or validation failure halts execution immediately.

```text
    [Start Sweep]
          │
          ▼
    [Schema Loader]
          │
          ▼
    [Validation Gates]
          ├─► 1. Metadata Schema Check
          ├─► 2. Timeframe Whitelist Check
          ├─► 3. Parameter Boundary Check
          ├─► 4. Portfolio Constraints Check
          ├─► 5. Path Security Verification
          └─► 6. Version Match Verification
          │
          ├─── Any Failures? ──► [HALT with ValidationError]
          │
          ▼ [All PASS]
    [Proceed to Sweep Matrix]
```

---

## 2. Validation Gate Definitions

### A. Metadata Schema Verification
Verifies that all mandatory keys exist in the configuration files.
* **MANDATORY KEYS**:
  * `candidate.metadata.id`
  * `candidate.metadata.name`
  * `candidate.plugin.module_path`
  * `candidate.universe.symbols`
  * `candidate.timeframes`
  * `experiment_sweep.parameter_space`
* **Action**: Throws `SchemaValidationError` if any key is missing or empty.

### B. Timeframe Whitelist Check
Verifies that the requested timeframes match the database availability rules.
* **Whitelisted Timeframes**: `15m`, `30m`, `1H`, `4H`, `1D`.
* **Action**: Halts with `UnsupportedTimeframeError` if a timeframe outside this list is specified.

### C. Parameter Boundary Verification
Validates that sweep values reside within reasonable financial and operational bounds (defined in `validation_rules.yaml`):
* `lookback_window`: must be between $1$ and $1000$ candles.
* `portfolio_size_k`: must be between $1$ and $50$ positions.
* `rebalance_frequency_r`: must be between $1$ and $168$ candles.
* `stop_loss_multiplier`: must be between $0.1$ and $20.0$.
* `take_profit_multiplier`: must be between $0.1$ and $999.0$.
* **Action**: Throws `OutOfBoundsParameterError` detailing the parameter and invalid value.

### D. Portfolio Constraints Check
Checks cross-sectional dimensions:
* **Rule**: Portfolio size $K$ (max active positions) must be less than or equal to the total count of symbols in the universe.
  $$K \le \text{Count}(\text{Symbols})$$
* **Action**: Throws `InvalidUniverseConstraintError` if $K > \text{Universe Size}$, preventing empty portfolio slot errors.

### E. Path Security Filters
Prevents directory traversal attacks and invalid path assignments during automated runs:
* **Rule**: Outputs must remain within the workspace boundary. File paths cannot contain parent directory markers (`..`), root paths, or absolute path sequences.
* **Action**: Throws `PathTraversalSecurityError`.

### F. Framework Version Verification
Ensures candidate configurations align with the running engine:
* **Rule**: Candidate target framework version must match `QRP Framework v2.0`.
* **Action**: Throws `FrameworkVersionMismatchError` if trying to load configs written for legacy platforms.
