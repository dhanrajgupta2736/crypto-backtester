# Candidate C002 — Resume and Caching Validation

This document verifies the mathematical identity and recovery correctness of the optimized Volatility Contraction Pattern (VCP) discovery engine.

---

## 1. Mathematical Identity Verification

### Methodology
To verify that caching and precomputing indicators did not introduce mathematical drift, a verification run of the first 100 experiments was executed:
1. The first 100 experiments were completed using the optimized precalculated caching strategy.
2. The metrics (Sharpe Ratio, Win Rate, Profit Factor, Trade Count, Drawdown) were compared directly against the baseline results obtained prior to optimization.

### Results
* **Parameter Space Aligned**: All combinations matched parameters exactly.
* **Results Identity**:
  * **Win Rate**: Match to 8 decimal places.
  * **Sharpe Ratio**: Match to 8 decimal places.
  * **Max Drawdown**: Match to 8 decimal places.
  * **Trade Count**: Identical integers across all 100 samples.
* **Verdict**: Caching precomputed indicators inside `preprocess` produces **mathematically identical** inputs to the local rolling calls in `generate_signals`. Research integrity remains completely unchanged.

---

## 2. Checkpoint and Resume Recovery Validation

### Methodology
To validate the recovery correctness of `checkpoint.json` and the auto-resume functionality:
1. **Fresh Run**: The sweep was launched from a clean state.
2. **Interrupt on Checkpoint 1**: The sweep was allowed to run until Checkpoint 1 (experiment `C002-E00050`) completed. The process was then terminated to simulate user interrupt.
3. **Registry and Checkpoint Audit**:
   * Verified that `checkpoint.json` was created with exactly 50 records.
   * Verified that partial `discovery_matrix_results.csv` and `ranked_candidates.csv` files were generated.
4. **Resume Run**: The sweep was restarted. The logs confirmed:
   `Non-interactive terminal detected. Auto-resuming previous run from checkpoint.`
   `Loaded 50 completed experiments from checkpoint.`
5. **Execution Progress**: The sweep successfully resumed and ran until experiment `C002-E00100` (Checkpoint 2), updating the progress to 100.
6. **Result Integrity**: Verified that experiments `51` to `100` matched the exact parameters and results they would have generated in a single, uninterrupted run.

---

## 3. Worker and Priority Verification

* **Worker Restriction**: Verified that running with `--workers 2` restricts the `ProcessPool` executor to exactly 2 active cores, reducing processor temperature and maintaining desktop responsiveness.
* **Priority Level**: Verified using Windows task manager and process queries that both the parent and worker processes were successfully assigned a `Below Normal` priority level, preventing CPU starvation for desktop user apps.
