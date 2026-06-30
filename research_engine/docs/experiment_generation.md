# QRP Framework v2.0 — Experiment Generation Specification

This document details the logic and requirements for the **Experiment Matrix Generation and Tracking** system within the **QRP Framework v2.0**.

---

## 1. Cartesian Sweep Explosion

The `ExperimentManager` converts a multi-parameter search grid into individual concrete experiment executions. The parameter space dictionary contains lists of candidate values. The manager computes the **Cartesian product** of these lists.

$$\text{Sweep Matrix} = P_1 \times P_2 \times P_3 \times \dots \times P_n$$

### Example Parameter Space:
```yaml
parameter_space:
  lookback: [10, 20]
  portfolio_size: [1, 3]
  rebalance: [1]
```

This explodes into a $2 \times 2 \times 1 = 4$ configuration matrix:
1. `{"lookback": 10, "portfolio_size": 1, "rebalance": 1}`
2. `{"lookback": 10, "portfolio_size": 3, "rebalance": 1}`
3. `{"lookback": 20, "portfolio_size": 1, "rebalance": 1}`
4. `{"lookback": 20, "portfolio_size": 3, "rebalance": 1}`

The generation process is **fully automated**. No developer or researcher edits python loops to run sweeps. They edit the `experiment_template.yaml` and the framework expands the grid automatically.

---

## 2. Immutable Experiment ID Allocation

Every generated experiment is assigned a permanent, unique identifier:

$$\text{Experiment ID} = \text{C}\{\text{Candidate ID}\} - \text{E}\{\text{Padded Experiment Index}\}$$

* **Candidate ID**: Padded to three digits (e.g. `C001`, `C002`). Represents the strategy candidate.
* **Experiment Index**: A sequentially incremented integer padded to five digits (e.g. `E00001`, `E00002`).

### ID Padded Sorting Alignment
Padding indices with zeros (e.g., `E00001` instead of `E1`) ensures that filenames, database entries, and logs sort chronologically and alphabetically across standard file explorers, terminals, and SQL queries.
* *Correct Sorting*: `C001-E00001`, `C001-E00002`, ..., `C001-E00010`
* *Incorrect Sorting (unpadded)*: `C001-E1`, `C001-E10`, `C001-E2`

---

## 3. ID Persistence Rules

To maintain institutional reproducibility:
1. **Permanent Assignment**: Once an experiment ID is assigned and executed, it is **locked**. The exact combination of parameters, universe, timeframe, and metadata is mapped to this ID in the database registry forever.
2. **No Re-use**: Even if a configuration fails, yields negative results, or is deleted from active workspace directories, its ID must **never be recycled**. 
3. **Archive Preservation**: Archived configurations moved to `archives/` retain their original IDs, keeping their directory names and metadata manifests intact.
4. **Resuming Sweep Checks**: Before executing a sweep, the configuration loader checks the `experiment_registry.db`. If a parameter configuration has already been executed under an existing ID, the loader skips it, preventing redundant backtest processing.
