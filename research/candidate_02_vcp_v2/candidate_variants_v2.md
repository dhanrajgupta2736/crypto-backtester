# Candidate Variants Definition — Candidate C002 Version 2

To isolate the effect of the swing window on the VCP strategy, we define three candidate variants. The swing detection window is the only experimental variable.

---

## 1. Variant Specifications

### Variant A: Fast Swing Detection (`C002_V2_A`)
* **Primary Parameter**: `swing_window = 3`
* **Description**: Swing highs and swing lows are identified using a short 3-candle lookback. This allows the contraction logic to identify very brief consolidations.
* **Target Timeframe**: Ideal for the `1H` timeframe, where market structure shifts rapidly.
* **Expected Behavior**: Highest trade frequency, shorter trade duration, and faster entry signals. Potentially exposed to more market noise and false breakouts.

### Variant B: Medium Swing Detection (`C002_V2_B`)
* **Primary Parameter**: `swing_window = 5`
* **Description**: Swing highs and swing lows are identified using a 5-candle lookback. This balances noise filtering with responsiveness.
* **Target Timeframe**: Serves as a crossover model suitable for both `1H` and `4H` timeframes.
* **Expected Behavior**: Moderate trade frequency. Filters out minor intraday noise while entering trades faster than the V1 baseline.

### Variant C: Slow Swing Detection / V1 Control (`C002_V2_C`)
* **Primary Parameter**: `swing_window = 7` (Control Group)
* **Description**: Swing highs and swing lows are identified using a 7-candle lookback, matching the baseline locked in Version 1.
* **Target Timeframe**: Primarily suited for `4H` timeframe.
* **Expected Behavior**: Lowest trade frequency, high-conviction entries, and long holding periods. Serves as the baseline comparison group to measure the trade frequency expansion of Variants A and B.

---

## 2. Common Configuration Matrix
All three variants share the same baseline configuration derived from Candidate C002 Version 1's best-performing configuration:

| Component | Setting / Parameter | Rationale |
| :--- | :--- | :--- |
| **Universe** | 25 assets | Preserves backtest scope consistency |
| **Trend Gate** | `HH_HL` (locked) | Provides strong risk mitigation and market regime filter |
| **Contraction Waves** | `3` (locked) | Identical to V1 baseline wave complexity |
| **Apex Tightness** | `0.05` (locked) | Identical to V1 baseline apex compression (5% limit) |
| **Breakout Trigger** | `Close_Above_Swing_High` (locked) | Best performing entry confirmation trigger in V1 |
| **Exit Method** | `Swing_Trail` (locked) | Lowers maximum drawdowns via dynamic trailing stops |
| **Stop Buffer** | `0.0` (locked) | Identical to V1 optimal baseline execution buffer |
| **Portfolio Sizing** | $K = 3$ | Standardized asset allocation limit |
| **Timeframes** | `1H` and `4H` | Evaluates multi-regime scaling |
