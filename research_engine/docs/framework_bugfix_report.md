# QRP Framework Safety Patch v2.0.1 — Bug Fix Report

This document reports the identification, analysis, and correction of execution and logging anomalies in the QRP Framework Discovery Engine.

---

## 1. Identified Defects & Root Causes

### A. The Negative Equity Sizing Defect
* **Description**: If a strategy's capital is severely eroded, the engine does not stop simulation. If portfolio value drops below zero, target allocations ($E_t / K$) become negative, resulting in negative position sizes (effectively shorting assets).
* **Root Cause**: The rebalancing loop in `discovery_engine.py` lacked equity validation wicks or checks.
* **Correction**: 
  - Added an **Equity Safety Guard** at the top of the main loop. If `portfolio_value <= 0`, the engine immediately liquidates open positions, marks the status as `TERMINATED`, documents the reason ("Portfolio equity reached zero or negative"), and exits the simulation chronological loop.

### B. The Trade Ledger Quantity Matching Defect
* **Description**: In Sprint 1.5, the trade log reported a total net PnL of **$-316,231.21$** on a starting capital of **$10,000$**, which is a physical impossibility for cash-only accounts.
* **Root Cause**: During position size reductions (partial exits), the quantity in `active_trades` was not adjusted. At final liquidation, `pnl_nominal = exit_val (remaining qty) - entry_val (maximum qty)`, resulting in an artificially inflated loss calculation for every trade.
* **Correction**:
  - Implemented **Partial Exit Matching** in `discovery_engine.py`. When a position reduction occurs, the partial portion is logged as a separate completed trade record, and the active trade's remaining quantity is correctly reduced.

---

## 2. Implemented Safeguards

### A. Position Size & Quantity Validation
Before placing any buy/sell adjustments:
- Assert that `close_prices[sym] > 0` (prevents division by zero).
- Assert that `q > 0` (prevents zero or negative sizing).
- Check that cash spent does not exceed cash available. If so, adjust `q` dynamically to the remaining cash, leaving cash at exactly `0.0`.

### B. Accounting Validation Checks
- Checked for `np.isnan(portfolio_value)` or `np.isinf(portfolio_value)`. If triggered, abort with `FAILED` status and log the error.
- Verified cash balances: abort if `cash < -0.01` with an `ACCOUNTING_FAILURE` exit tag on open trades.

---

## 3. Status Propagation & Error Codes
Status codes are now structured and propagated to the Candidate Dashboard, Experiment Registry, and central Research Ledger:
- `RUNNING`: Simulation active.
- `COMPLETED`: Simulation completed all historical timestamps.
- `TERMINATED`: Simulation halted by safety guards (equity <= 0).
- `FAILED`: Critical NaN/inf accounting error or execution failure.
- `INVALID_CONFIGURATION`: Pre-flight parameters check failed.
