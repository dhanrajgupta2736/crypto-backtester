# QRP Framework v2.0 — Core Framework Implementation Plan

This document outlines the coding, testing, and deployment roadmap for implementing the **QRP Framework v2.0** universal research engine in Stage 3.

---

## 1. Milestone Roadmap

The implementation is divided into three sequential phases:

```text
┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
│ Phase 1: Core Systems   │ ───► │ Phase 2: Testing Suite │ ───► │ Phase 3: Integration   │
│ (Logger, Engine, ABC)  │      │ (Unit & Mock Tests)    │      │ (Candidate 01 Sweep)   │
└────────────────────────┘      └────────────────────────┘      └────────────────────────┘
```

---

## 2. Phase Details & Tasks

### Phase 1: Infrastructure and Core Engine (Target: Developer A)
Build out the core skeleton interfaces and coordinate dynamic plugin imports.
* [ ] **Task 1.1: Plugin Interface (`strategy_interface.py`)**
  * Codify the `BaseStrategyPlugin` Abstract Base Class.
  * Verify that trying to load an incomplete plugin triggers an `InterfaceValidationError`.
* [ ] **Task 1.2: Standardized Logger (`logger.py`)**
  * Implement the custom multi-handler logging class.
  * Establish file directory routing: `/outputs/C{ID}/logs/E{ID}.log`.
* [ ] **Task 1.3: Experiment Manager (`experiment_manager.py`)**
  * Write the Cartesian parameter product sweep grid generator.
  * Code the auto-manifest compiler and serial writer (`manifest.json`).
* [ ] **Task 1.4: Discovery Engine Loop (`discovery_engine.py`)**
  * Write the dynamic import loader utilizing `importlib`.
  * Establish the historical OHLCV data loader.
  * Implement the vectorized backtest execution engine applying taker/maker fees and slippage calculations.

### Phase 2: Statistical Verification & Dashboards (Target: Developer B)
* [ ] **Task 2.1: Metrics Engine (`metrics_engine.py`)**
  * Program the vectorized transaction statistics compiler.
  * Verify calculations (CAGR, Sharpe, Drawdown, Profit Factor, Expectancy) against mock trade ledger sets.
* [ ] **Task 2.2: Reporting Engine (`reporting.py`)**
  * Program automatic formatting of trade outputs and summary logs.
* [ ] **Task 2.3: Candidate Dashboard (`candidate_dashboard.py`)**
  * Write the live-dashboard JSON state writer to allow cross-candidate tracking.

### Phase 3: Testing & Quality Gates (Target: QA Engineers)
* [ ] **Task 3.1: Core Unit Tests (`tests/test_core.py`)**
  * Write unit tests for dynamic class loading, parameter sweeps, and registry writing.
* [ ] **Task 3.2: Integration Mock Runs (`tests/test_mock_plugin.py`)**
  * Construct a simple mock strategy plugin (e.g. random buy/sell) to verify end-to-end framework execution.

---

## 3. Quality Assurance & Verification Gates

Before the framework is promoted to production and used for Candidate 01 Sweeps, it must satisfy:
1. **Mock End-to-End Success**: 100 consecutive mock runs executed without a system crash.
2. **Metrics Audit**: Expected metrics (CAGR, Sharpe, Drawdown) must match hand-calculated spreadsheet metrics to 4 decimal places.
3. **Reproducibility Pass**: Repeating a specific experiment ID (`C000-E0001`) from its manifest must yield identical trade logs.
4. **Leak Test**: Multi-threaded execution must not leak file descriptors or trigger WebSocket memory growth.
