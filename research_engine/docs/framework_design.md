# QRP Framework v2.0 — Framework Design Document

This document details the software design, class structures, configuration schemas, and interaction flows for the **Quantitative Research Platform (QRP) Framework v2.0**.

---

## 1. Modular Interface Hierarchy

The framework is organized as a collection of core classes that interact using defined data contracts. 

```mermaid
classDiagram
    class BaseStrategyPlugin {
        <<Abstract>>
        +metadata: dict
        +parameter_space: dict
        +preprocess(data) DataFrame
        +generate_signals(data, parameters) DataFrame
    }

    class DiscoveryEngine {
        +configs: dict
        +active_plugin: BaseStrategyPlugin
        +load_dataset(asset, timeframe) DataFrame
        +load_plugin(candidate_id) BaseStrategyPlugin
        +run_sweep(candidate_id, timeframe_list) list
    }

    class ExperimentManager {
        +candidate_id: str
        +framework_version: str
        +assign_experiment_id() str
        +generate_sweep_matrix(param_space) list
        +create_manifest(exp_id, params) dict
    }

    class MetricsEngine {
        +calculate_metrics(ledger) dict
        +cagr(returns) float
        +sharpe_ratio(returns) float
        +max_drawdown(equity) float
        +expectancy(ledger) float
    }

    class ReportingEngine {
        +generate_markdown_report(metadata, metrics) str
        +save_performance_csv(ledger, filepath) void
    }

    class ExperimentRegistry {
        +registry_db_path: str
        +register_experiment(metadata) void
        +query_experiments(query) list
    }

    DiscoveryEngine --> BaseStrategyPlugin : dynamic import
    DiscoveryEngine --> ExperimentManager : allocates and tracks
    DiscoveryEngine --> MetricsEngine : trade evaluation
    DiscoveryEngine --> ReportingEngine : compiles outputs
    ExperimentManager --> ExperimentRegistry : writes tracking entries
```

---

## 2. Interaction Dynamics

The execution flow of a discovery parameter sweep is fully automated, passing data structures between the components chronologically:

```mermaid
sequenceDiagram
    autonumber
    actor Researcher
    participant DE as DiscoveryEngine
    participant EM as ExperimentManager
    participant Plugin as StrategyPlugin
    participant ME as MetricsEngine
    participant RE as ReportingEngine
    participant Reg as ExperimentRegistry

    Researcher->>DE: Run Sweep (Candidate ID, Timeframes)
    DE->>Plugin: Import and Instantiate Plugin
    Plugin-->>DE: Return Metadata & Parameter Space
    DE->>EM: Request Sweep Matrix (Parameter Space)
    EM->>EM: Build Cartesian Product of Parameters
    EM-->>DE: Return Experiment List (IDs and Param Dicts)
    
    loop For Every Experiment Configuration
        DE->>DE: Load Historical Dataset (OHLCV)
        DE->>Plugin: Preprocess Data
        Plugin-->>DE: Cleaned DataFrame
        DE->>Plugin: Generate Signals (Data, Param Dict)
        Plugin-->>DE: Signals DataFrame (Buy/Sell gates)
        DE->>DE: Run Backtest Simulation Loop (Applying fees & slippage)
        DE-->>DE: Generate Raw Trade Ledger
        DE->>ME: Calculate Performance (Trade Ledger)
        ME-->>DE: Return Performance Metrics Dict
        DE->>RE: Compile Report & Outputs
        RE-->>DE: Save Manifest, CSV, Report files
        DE->>Reg: Register Experiment (ID, Metadata, Key Metrics)
    end
    
    DE-->>Researcher: Execution Complete (Console summary & dashboard updated)
```

---

## 3. Class Design & Module Specifications

### A. `discovery_engine.py` (Core Coordinator)
* **Functionality**: Loads datasets, loads strategy plugins dynamically, runs the sweep loop, handles asynchronous worker pools (multiprocessing per experiment configuration).
* **Key Functions**:
  * `load_dataset(asset: str, timeframe: str) -> pd.DataFrame`
  * `load_plugin(candidate_id: str) -> BaseStrategyPlugin`
  * `run_backtest(data: pd.DataFrame, params: dict) -> pd.DataFrame` (returns trade ledger)

### B. `experiment_manager.py` (Registry and ID manager)
* **Functionality**: Allocates unique IDs, builds parameter sweeping configurations, compiles reproducibility manifests.
* **Key Functions**:
  * `assign_experiment_id() -> str`
  * `generate_sweep_matrix(param_space: dict) -> List[dict]`
  * `create_manifest(exp_id: str, params: dict, git_hash: str) -> dict`

### C. `metrics_engine.py` (Statistical compiler)
* **Functionality**: Accepts standardized transaction logs and returns performance statistics.
* **Key Functions**:
  * `calculate_metrics(ledger: pd.DataFrame) -> dict`
  * `calculate_cagr(daily_returns: pd.Series) -> float`
  * `calculate_sharpe(daily_returns: pd.Series) -> float`
  * `calculate_drawdown(equity_curve: pd.Series) -> dict` (max drawdown, duration, recovery date)

### D. `reporting.py` (Output formatting)
* **Functionality**: Saves backtesting logs and outputs to disk, compiles final report summaries.
* **Key Functions**:
  * `write_markdown_report(exp_dir: Path, manifest: dict, metrics: dict) -> Path`
  * `export_trades_csv(exp_dir: Path, ledger: pd.DataFrame) -> Path`

### E. `logger.py` (Execution Tracing)
* **Functionality**: Custom class maintaining segregated logging handlers.
* **Key Functions**:
  * `get_experiment_logger(candidate_id: str, exp_id: str) -> logging.Logger`

---

## 4. Configuration Schemas

The central framework run settings are governed by a YAML schema (`research_engine/configs/runner.yaml`):

```yaml
framework:
  version: "QRP Framework v2.0"
  log_level: "INFO"
  max_workers: 4                 # Multiprocessing CPU allocation

data:
  root_dir: "./data"             # Path to historical databases
  asset_class: "crypto"          # Asset class adapter to load
  default_timeframes: ["15m", "1H", "4H"]

backtest:
  initial_capital: 10000.0       # Standardized baseline capital
  costs:
    taker_fee: 0.00045           # 0.045% Taker fee rate
    maker_fee: 0.00015           # 0.015% Maker fee rate
    slippage_rate: 0.0005        # 0.05% Slippage buffer
  leverage:
    max_cap: 5                   # Max isolated leverage cap

paths:
  outputs_dir: "./research_engine/outputs"
  archives_dir: "./research_engine/archives"
```

---

## 5. Standardized Data Structures

### A. Input Bar Structure (Pandas DataFrame)
Standardized index: `timestamp` (UTC datetime64)
Columns:
* `open` (float)
* `high` (float)
* `low` (float)
* `close` (float)
* `volume` (float)

### B. Output Trade Ledger Structure (Pandas DataFrame)
Columns:
* `trade_id` (str)
* `asset` (str)
* `direction` (str: `LONG` / `SHORT`)
* `entry_timestamp` (datetime)
* `entry_price` (float)
* `qty` (float)
* `exit_timestamp` (datetime)
* `exit_price` (float)
* `exit_reason` (str: `RANK_DECAY`, `STOP_LOSS`, `TAKE_PROFIT`, `TIME_EXIT`)
* `pnl_nominal` (float)
* `pnl_r` (float: PnL measured in units of initial risk)
* `fees_paid` (float)
* `slippage_paid` (float)
