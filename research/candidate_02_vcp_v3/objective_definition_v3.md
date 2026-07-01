# Objective Definition — Candidate C002 Version 3

## 1. Background & V2 Summary
Candidate C002 Version 2 evaluated the **Swing Detection Window** as the primary experimental variable. While reducing the swing window (from 7 to 3 or 5) successfully increased trade frequency (e.g. from 71 to 151 trades on 4H), it resulted in severe performance decay (4H Sharpe dropped from 1.30 to 0.44 or 0.51). 

Therefore, Version 2 was archived, and we create Version 3.

---

## 2. Version 3 Objective
The primary objective of Version 3 is to **increase trade frequency while preserving the low drawdown and positive expectancy discovered in Version 1 by evaluating Contraction Wave structures as the sole experimental variable**.

We aim to compare:
1. **Exactly 2 contraction waves**: Maximizes pattern density by requiring fewer consolidation waves.
2. **Exactly 3 contraction waves (control)**: The V1 baseline, providing high conviction but low trade count.
3. **2 or more contraction waves (adaptive)**: Dynamically checks for 3-wave consolidations first, and falls back to 2-wave consolidations if a 3-wave pattern is not present.

---

## 3. Scope of Constraints & Settings

### Unchanged from V1 (Locked Baseline):
* **Universe**: Same 25-coin universe.
* **Framework**: Same universal configuration and validation rules.
* **Backtesting Engine**: Same execution simulator and transaction cost assumptions.
* **Trend Filter (`trend_gate`)**: Locked to `"HH_HL"`.
* **Swing Window (`swing_window`)**: Locked to `7` bars.
* **Apex Tightness (`max_final_contraction`)**: Locked to `0.05` (5%).
* **Breakout Confirmation (`breakout`)**: Locked to `"Close_Above_Swing_High"`.
* **Exit Logic (`risk_reward`)**: Locked to `"Swing_Trail"`.
* **Stop Buffer (`stop_buffer`)**: Locked to `0.0`.
* **Portfolio Sizing ($K$)**: Locked to `3`.

### Modified in Version 3:
* **Timeframes**: Only `1H` and `4H` (excluding `15m` to avoid high transaction fee drag on lower timeframes).
* **Single Major Research Dimension Change**: The **Contraction Waves** parameter (`contraction_waves` varied as `[2, 3, "adaptive"]`).
