# Candidate C002 — Checkpoint & Recovery Specification

This document details the architecture, file schemas, recovery rules, and interrupt handling for the Candidate C002 sweep checkpoint system.

---

## 1. Directory and File Layout

* **Checkpoint Location**: `research_engine/outputs/checkpoint.json`
* **Lifecycle**:
  * Created at the end of the first 50 experiments.
  * Updated every **50 completed experiments** thereafter.
  * Updated **instantly** when `Ctrl+C` is intercepted.
  * **Auto-deleted** upon successful completion of all 17,010 experiments in the grid.

---

## 2. Checkpoint JSON Schema

The checkpoint file stores the raw list of completed experiment records inside a flat list:

```json
{
  "results_list": [
    {
      "Experiment ID": "C002-E00001",
      "Timeframe": "4H",
      "Trend Gate": "None",
      "Swing Window": 3,
      "Contraction Waves": 2,
      "Max Final Contraction": 0.03,
      "Breakout": "Close_Above_Swing_High",
      "Risk Reward": "1R",
      "Stop Buffer": 0.0,
      "Status": "COMPLETED",
      "Termination Reason": "N/A",
      "Trade Count": 1391,
      "Win Rate": 72.18,
      "Profit Factor": 1.12,
      "Expectancy (USD)": 2.51,
      "CAGR": 18.25,
      "Sharpe Ratio": 0.61,
      "Max Drawdown": 38.12,
      ...
    }
  ]
}
```

---

## 3. Resume and Skip Logic

Upon startup, the sweep runner checks if `checkpoint.json` exists:
1. **Interactive Prompt**: If stdin is a TTY terminal, it queries the researcher:
   `Previous VCP sweep checkpoint detected. Resume previous run? [Y/N] (Default: Y):`
2. **Non-Interactive Default**: If stdin is not a TTY (such as running inside an IDE subagent or automated background tasks), it auto-resumes for safety.
3. **Combination Filtering**:
   * It loads the completed records list from `checkpoint.json`.
   * For each record, it constructs a unique tuple key:
     `key = (Timeframe, Trend Gate, Swing Window, Contraction Waves, Max Final Contraction, Breakout, Risk Reward, Stop Buffer)`
   * It filters the full grid combinations list, keeping only those combinations whose tuple key is **not** present in the completed set.
   * `global_index` is initialized to the number of completed combinations, ensuring correct experiment ID alignment (e.g. if 50 completed, the next ID is `C002-E00051`).

---

## 4. Graceful SIGINT Interruption (Ctrl+C)

To prevent progress loss between checkpoint intervals, a SIGINT signal handler is wrapped around the execution loop:
1. Hitting `Ctrl+C` raises a `KeyboardInterrupt` in the main sweep process.
2. The program cancels all queued futures in the executor.
3. Any currently running backtests in child workers are abandoned.
4. The main thread immediately:
   * Flushes the memory registry buffers to `experiment_registry.json`.
   * Invokes `save_checkpoint()`, dumping all completed results to `checkpoint.json` and writing partial `discovery_matrix_results.csv` and `ranked_candidates.csv`.
   * Updates the dashboard status to `INTERRUPTED`.
   * Exits cleanly.
