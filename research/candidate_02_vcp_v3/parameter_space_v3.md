# Parameter Space Definition — Candidate C002 Version 3

## 1. Parameter Grid Selection
To maintain strict scientific interpretability and isolate the causal impact of the contraction wave complexity, all other parameters are locked to the V1 optimal baseline configuration (`C002-E04426`).

### Locked Parameters (V1 Baseline):
* **Trend Filter (`trend_gate`)**: `"HH_HL"`
* **Swing Window (`swing_window`)**: `7` bars
* **Apex Tightness (`max_final_contraction`)**: `0.05` (5% final compression limit)
* **Breakout Confirmation (`breakout`)**: `"Close_Above_Swing_High"`
* **Exit Logic (`risk_reward`)**: `"Swing_Trail"`
* **Stop Buffer (`stop_buffer`)**: `0.0`
* **Portfolio Sizing ($K$)**: `3` (Maximum concurrent positions)

### Experimental Variable:
* **Contraction Waves (`contraction_waves`)**: `[2, 3, "adaptive"]` (3 values - **The Only Experimental Variable**)
* **Timeframes**: `["1H", "4H"]` (2 values)

---

## 2. Search Space Complexity
The total configuration count is:
$$\text{Total Experiments} = 2 \text{ (timeframes)} \times 3 \text{ (waves)} = 6 \text{ configurations}$$

This represents a **99.96% reduction** from V1's 17,010-experiment sweep. It allows for an exact, isolated comparison of the relationship between contraction wave structure, trade density, and out-of-sample performance.

---

## 3. Projected Compute & AWS Estimates

### Local Execution (7 Workers):
* **Estimated Runtime**: **~1.5 seconds** (using Python multiprocessing).

### AWS Compute Requirements (AWS EC2):
* **Recommended Instance**: `t3.micro` or `t3.small` (1-2 vCPUs) is more than sufficient.
* **Estimated AWS Runtime**:
  * On `t3.micro` (1 worker): ~5 seconds.
  * On `t3.small` (2 workers): ~3 seconds.
* **AWS Compute Cost**: $0.00 (negligible).
