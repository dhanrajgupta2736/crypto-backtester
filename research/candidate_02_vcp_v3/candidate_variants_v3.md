# Candidate Variants Definition — Candidate C002 Version 3

To isolate the effect of contraction wave complexity on the VCP strategy, we define three candidate variants. The contraction waves parameter is the only experimental variable.

---

## 1. Variant Specifications

### Variant A: Exactly 2 Waves (`C002_V3_A`)
* **Primary Parameter**: `contraction_waves = 2`
* **Description**: The VCP pattern requires exactly 2 waves of alternating swing highs and swing lows to validate.
* **Target Timeframe**: Suitable for `1H` and `4H` timeframes.
* **Expected Behavior**: Higher trade frequency, as a 2-wave consolidation is easier to form than 3 waves. Potentially higher exposure to noise and false breakouts.

### Variant B: Exactly 3 Waves / Control (`C002_V3_B`)
* **Primary Parameter**: `contraction_waves = 3` (V1 Baseline Control Group)
* **Description**: The VCP pattern requires exactly 3 waves of alternating swing highs and swing lows to validate.
* **Target Timeframe**: Suitability is concentrated on the `4H` timeframe.
* **Expected Behavior**: Lowest trade frequency, high-conviction entries, and long holding periods. Serves as the baseline comparison group to measure the trade frequency expansion of Variants A and C.

### Variant C: Adaptive / 2 or More Waves (`C002_V3_C`)
* **Primary Parameter**: `contraction_waves = "adaptive"`
* **Description**: Dynamically checks for a valid 3-wave VCP pattern first. If 3 waves are valid, it triggers an entry. If not, it falls back to checking for a valid 2-wave pattern.
* **Target Timeframe**: Ideal for both `1H` and `4H` timeframes, providing a multi-scale regime response.
* **Expected Behavior**: Maximizes trade frequency by taking 2-wave patterns when 3-wave structures are unavailable, while retaining 3-wave high-conviction entries when they do form.

---

## 2. Common Configuration Matrix
All three variants share the same baseline configuration derived from Candidate C002 Version 1's best-performing configuration:

| Component | Setting / Parameter | Rationale |
| :--- | :--- | :--- |
| **Universe** | 25 assets | Preserves backtest scope consistency |
| **Trend Gate** | `HH_HL` (locked) | Provides strong risk mitigation and market regime filter |
| **Swing Window** | `7` (locked) | Identical to V1 baseline swing lookback (7 bars) |
| **Apex Tightness** | `0.05` (locked) | Identical to V1 baseline apex compression (5% limit) |
| **Breakout Trigger** | `Close_Above_Swing_High` (locked) | Best performing entry confirmation trigger in V1 |
| **Exit Method** | `Swing_Trail` (locked) | Lowers maximum drawdowns via dynamic trailing stops |
| **Stop Buffer** | `0.0` (locked) | Identical to V1 optimal baseline execution buffer |
| **Portfolio Sizing** | $K = 3$ | Standardized asset allocation limit |
| **Timeframes** | `1H` and `4H` | Evaluates multi-regime scaling |
