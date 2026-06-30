# QRP Framework v2.0 — Configuration Architecture Specification

This document presents the architectural design of the **Universal Configuration & Experiment System** for the **Quantitative Research Platform (QRP) Framework v2.0**.

---

## 1. Configuration-Driven Research Philosophy

To build an institutional-grade, scalable backtesting platform, the platform must remain **completely configuration-driven**. Strategy researchers must be able to specify new candidates, asset universes, timeframes, parameters, rebalancing rules, and validation criteria entirely through declarative YAML files.

```text
                     ┌──────────────────────────────────┐
                     │     Declarative YAML Files       │
                     │  (candidate, sweep, validation)  │
                     └──────────────────────────────────┘
                                      │
                                      ▼
                      ┌────────────────────────────────┐
                      │    Configuration Loader        │
                      │ (Reads YAML, Validates Schema) │
                      └────────────────────────────────┘
                                      │
                                      ▼
                       ┌──────────────────────────────┐
                       │      Discovery Engine        │
                       │ (Executes Strategy Skeletons)│
                       └──────────────────────────────┘
```

The framework enforces a total separation of concerns:
* **Framework Core Code**: Strategy-agnostic modules that execute backtests, calculate metrics, and output reports. Never modified for new strategies.
* **Strategy Plugin Code**: Implements the mathematical signal functions and metadata definitions. Inherits from `BaseStrategyPlugin`.
* **Configuration Layer (YAML)**: Maps parameters, universes, and sweep spaces.

Adding a new strategy candidate to the platform requires **zero changes** to the core framework code, requiring only a new plugin file and a corresponding configuration file.

---

## 2. Component Layout & Responsibilities

The configuration system resides inside `research_engine/configs/` and is processed by the core engine components:

```mermaid
graph TD
    A[configs/candidate_template.yaml] --> Loader[Core Configuration Loader]
    B[configs/experiment_template.yaml] --> Loader
    C[configs/validation_rules.yaml] --> Loader
    
    Loader -->|Schema Check & Logic Gates| Val[Validation Layer]
    Val -->|Clean Config Map| Matrix[Experiment Matrix Generator]
    Matrix -->|C{ID}-E{ID} Permutations| DE[Discovery Engine]
```

* **Configuration Loader (`discovery_engine.py` / `configs`)**:
  Reads raw YAML configurations and parses them into standardized dictionary mappings.
* **Validation Layer (`discovery_engine.py` / `validation_rules.yaml`)**:
  Asserts that parameters fall within valid constraints (e.g. timeframe is supported, lookback values are positive, portfolio size $K$ does not exceed the asset list).
* **Matrix Generator (`experiment_manager.py`)**:
  Explodes parameter grids into individual experiment runs, allocating permanent experiment IDs.

---

## 3. Dynamic Ingest and Execution Sequence

When a discovery sweep is initiated, the engine performs the following processing steps:

```
  Step 1: Configuration Ingest
  Loader parses 'framework_config.yaml', 'candidate.yaml', and 'experiment.yaml'.
  
  Step 2: Pre-Flight Validation
  Validation Layer checks schemas and parameter boundaries. 
  If verification fails, execution HALTS immediately with detailed errors.
  
  Step 3: Sweep Explosion
  ExperimentManager builds the Cartesian product of the parameter lists,
  allocating padded IDs (e.g. C001-E0001, C001-E0002) and writing reproducibility manifests.
  
  Step 4: Execution Routing
  DiscoveryEngine dynamically imports the StrategyPlugin class indicated in the configuration,
  running backtests for each parameter mapping.
```
