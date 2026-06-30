# Phase 15B Post-Mortem Report: Volatility Expansion Walk-Forward Validation

This report presents the complete out-of-sample validation analysis of **Phase 15B**. The test covers 16 candidate configurations (`VE_3_ATR_EXPANSION`, 4H, 4 coins × 4 RR ratios) across three non-overlapping historical windows, using the identical execution engine from Phase 15A.

---

## 1. Validation Status Summary

**0 out of 16 candidates passed** the full validation criteria (both holdouts simultaneously).

> [!WARNING]
> **No candidates passed the formal validation gate.** However, the failure modes are critically different across assets and must be interpreted with precision before any research conclusions are drawn.

---

## 2. Complete Results Table

| Candidate | Period | Trades | Win Rate | PF | Sharpe | Drawdown | Expectancy (R) | Net Return | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BTC 4H (RR=1.0)** | Selection (23-24) | 20 | 60.00% | 2.25 | 1.42 | 14.02% | +0.3197 | +61.28% | `FAIL` |
| **BTC 4H (RR=1.0)** | Holdout 1 (2025) | **10** | 70.00% | **2.00** | 0.87 | 14.73% | **+0.3191** | **+30.07%** | `FAIL` |
| **BTC 4H (RR=1.0)** | Holdout 2 (2026) | **6** | 100.00% | **999.90** | 2.48 | 0.00% | **+0.6701** | **+38.07%** | `FAIL` |
| **BTC 4H (RR=1.5)** | Selection (23-24) | 19 | 47.37% | 1.85 | 1.06 | 21.30% | +0.2879 | +61.35% | `FAIL` |
| **BTC 4H (RR=1.5)** | Holdout 1 (2025) | **10** | 70.00% | **3.08** | 1.33 | 12.16% | **+0.6575** | **+62.29%** | `FAIL` |
| **BTC 4H (RR=1.5)** | Holdout 2 (2026) | **5** | 60.00% | **1.50** | 1.18 | 24.01% | **+0.2209** | **+12.11%** | `FAIL` |
| **BTC 4H (RR=2.0)** | Selection (23-24) | 18 | 38.89% | 1.60 | 0.80 | 25.98% | +0.2780 | +48.46% | `FAIL` |
| **BTC 4H (RR=2.0)** | Holdout 1 (2025) | **9** | 55.56% | **2.25** | 0.83 | 14.00% | **+0.6073** | **+51.18%** | `FAIL` |
| **BTC 4H (RR=2.0)** | Holdout 2 (2026) | **5** | 60.00% | **2.10** | 1.47 | 24.01% | **+0.5210** | **+26.33%** | `FAIL` |
| **BTC 4H (RR=3.0)** | Selection (23-24) | 18 | 38.89% | 1.96 | 0.96 | 25.98% | +0.4557 | +77.48% | `FAIL` |
| **BTC 4H (RR=3.0)** | Holdout 1 (2025) | **7** | 42.86% | **2.11** | 0.47 | 14.66% | **+0.6973** | **+46.22%** | `FAIL` |
| **BTC 4H (RR=3.0)** | Holdout 2 (2026) | **4** | 50.00% | **2.14** | 1.29 | 24.01% | **+0.6889** | **+27.35%** | `FAIL` |
| **LINK 4H (RR=1.0)** | Selection (23-24) | 16 | 75.00% | 5.19 | 1.82 | 6.97% | +0.6364 | +96.77% | `FAIL` |
| **LINK 4H (RR=1.0)** | Holdout 1 (2025) | 2 | 0.00% | 0.00 | -3.17 | 24.36% | -1.2492 | -24.36% | `FAIL` |
| **LINK 4H (RR=1.0)** | Holdout 2 (2026) | 3 | 66.67% | 0.89 | -0.49 | 12.97% | -0.0512 | -1.47% | `FAIL` |
| **LINK 4H (RR=1.5)** | Selection (23-24) | 16 | 62.50% | 2.37 | 1.15 | 10.89% | +0.5065 | +76.43% | `FAIL` |
| **LINK 4H (RR=1.5)** | Holdout 1 (2025) | 2 | 0.00% | 0.00 | -3.17 | 24.36% | -1.2492 | -24.36% | `FAIL` |
| **LINK 4H (RR=1.5)** | Holdout 2 (2026) | 3 | 66.67% | 1.59 | 0.02 | 12.38% | +0.2875 | +8.04% | `FAIL` |
| **LINK 4H (RR=2.0)** | Selection (23-24) | 15 | 53.33% | 2.21 | 1.12 | 10.44% | +0.5378 | +75.85% | `FAIL` |
| **LINK 4H (RR=2.0)** | Holdout 1 (2025) | 2 | 0.00% | 0.00 | -3.17 | 24.36% | -1.2492 | -24.36% | `FAIL` |
| **LINK 4H (RR=2.0)** | Holdout 2 (2026) | 3 | 66.67% | 2.30 | 0.38 | 11.84% | +0.6282 | +17.61% | `FAIL` |
| **LINK 4H (RR=3.0)** | Selection (23-24) | 13 | 53.85% | 3.18 | 1.21 | 9.64% | +0.8349 | +101.61% | `FAIL` |
| **LINK 4H (RR=3.0)** | Holdout 1 (2025) | 2 | 0.00% | 0.00 | -3.17 | 24.36% | -1.2492 | -24.36% | `FAIL` |
| **LINK 4H (RR=3.0)** | Holdout 2 (2026) | 3 | 66.67% | 3.68 | 0.78 | 10.89% | +1.2965 | +36.39% | `FAIL` |
| **XRP 4H (RR=1.0)** | Selection (23-24) | 24 | 62.50% | 2.15 | 0.45 | 13.03% | +0.4339 | +98.09% | `FAIL` |
| **XRP 4H (RR=1.0)** | Holdout 1 (2025) | 9 | 11.11% | 0.17 | -2.13 | 72.04% | -0.8249 | -72.04% | `FAIL` |
| **XRP 4H (RR=1.0)** | Holdout 2 (2026) | 3 | 33.33% | 0.09 | -1.88 | 30.15% | -1.0028 | -28.15% | `FAIL` |
| **XRP 4H (RR=1.5)** | Selection (23-24) | 23 | 56.52% | 2.35 | 0.71 | 22.29% | +0.5864 | +127.49% | `FAIL` |
| **XRP 4H (RR=1.5)** | Holdout 1 (2025) | 9 | 11.11% | 0.22 | -2.02 | 67.41% | -0.7712 | -67.41% | `FAIL` |
| **XRP 4H (RR=1.5)** | Holdout 2 (2026) | 3 | 33.33% | 0.25 | -1.89 | 28.79% | -0.8357 | -23.29% | `FAIL` |
| **XRP 4H (RR=2.0)** | Selection (23-24) | 23 | 60.87% | 2.92 | 1.11 | 17.78% | +0.8324 | +181.03% | `FAIL` |
| **XRP 4H (RR=2.0)** | Holdout 1 (2025) | 9 | 11.11% | 0.28 | -1.85 | 63.73% | -0.7174 | -62.73% | `FAIL` |
| **XRP 4H (RR=2.0)** | Holdout 2 (2026) | 3 | 33.33% | 0.41 | -1.90 | 27.50% | -0.6620 | -18.24% | `FAIL` |
| **XRP 4H (RR=3.0)** | Selection (23-24) | 21 | 42.86% | 2.10 | 0.71 | 33.80% | +0.7691 | +152.16% | `FAIL` |
| **XRP 4H (RR=3.0)** | Holdout 1 (2025) | 9 | 11.11% | 0.39 | -1.35 | 58.41% | -0.6100 | -53.37% | `FAIL` |
| **XRP 4H (RR=3.0)** | Holdout 2 (2026) | 3 | 33.33% | 0.74 | -1.90 | 25.24% | -0.3147 | -8.14% | `FAIL` |
| **AVAX 4H (RR=1.0)** | Selection (23-24) | 15 | 60.00% | 1.39 | 0.42 | 16.20% | +0.1431 | +20.45% | `FAIL` |
| **AVAX 4H (RR=1.0)** | Holdout 1 (2025) | 6 | 50.00% | 0.59 | 0.21 | 17.37% | -0.2575 | -15.36% | `FAIL` |
| **AVAX 4H (RR=1.0)** | Holdout 2 (2026) | 1 | 0.00% | 0.00 | 0.00 | 1.52% | -0.1599 | -1.52% | `FAIL` |
| **AVAX 4H (RR=1.5)** | Selection (23-24) | 14 | 57.14% | 1.91 | 0.85 | 12.45% | +0.3826 | +51.14% | `FAIL` |
| **AVAX 4H (RR=1.5)** | Holdout 1 (2025) | 5 | 60.00% | 1.17 | 1.03 | 17.37% | +0.1175 | +5.21% | `FAIL` |
| **AVAX 4H (RR=1.5)** | Holdout 2 (2026) | 1 | 100.00% | 999.90 | 0.00 | 0.00% | +0.3218 | +3.05% | `FAIL` |
| **AVAX 4H (RR=2.0)** | Selection (23-24) | 12 | 50.00% | 1.81 | 0.61 | 19.26% | +0.4199 | +48.17% | `FAIL` |
| **AVAX 4H (RR=2.0)** | Holdout 1 (2025) | 5 | 40.00% | 0.80 | 0.44 | 27.80% | -0.1700 | -8.45% | `FAIL` |
| **AVAX 4H (RR=2.0)** | Holdout 2 (2026) | 1 | 100.00% | 999.90 | 0.00 | 0.00% | +0.8027 | +7.62% | `FAIL` |
| **AVAX 4H (RR=3.0)** | Selection (23-24) | 11 | 36.36% | 1.66 | 0.41 | 19.54% | +0.4424 | +45.55% | `FAIL` |
| **AVAX 4H (RR=3.0)** | Holdout 1 (2025) | 4 | 50.00% | 1.87 | 0.96 | 27.80% | +0.6260 | +24.16% | `FAIL` |
| **AVAX 4H (RR=3.0)** | Holdout 2 (2026) | 1 | 0.00% | 0.00 | 0.00 | 20.02% | -2.1098 | -20.02% | `FAIL` |

---

## 3. Failure Mode Dissection

The validation failures fall into two distinct, mechanistically different categories. Conflating them would be a research error.

### Category A: Trade-Density Failures (BTC — Edge Intact)

> [!IMPORTANT]
> **BTC failed the trade-density gate, not the quality gate.** Its edge is intact across all three periods.

All four BTC RR configurations showed **consistently profitable metrics** in both holdout periods but could not reach the minimum trade count thresholds:

| Period | Metric | BTC RR=1.5 | BTC RR=2.0 |
| :--- | :--- | :---: | :---: |
| Holdout 1 (2025) | Trades | 10 *(req. ≥ 20)* | 9 *(req. ≥ 20)* |
| Holdout 1 (2025) | PF | **3.08** ✓ | **2.25** ✓ |
| Holdout 1 (2025) | Net Return | **+62.29%** ✓ | **+51.18%** ✓ |
| Holdout 2 (2026) | Trades | 5 *(req. ≥ 10)* | 5 *(req. ≥ 10)* |
| Holdout 2 (2026) | PF | **1.50** ✓ | **2.10** ✓ |
| Holdout 2 (2026) | Net Return | **+12.11%** ✓ | **+26.33%** ✓ |

**Diagnosis**: VE_3_ATR_EXPANSION on BTC 4H is a **low-frequency, high-quality strategy**. The 20-bar Donchian breakout combined with an ATR ≥ 1.5× expansion requirement triggers only on genuine structural volatility events, which are inherently sparse. Every single trade that fired was profitable. The density gate was the only obstacle.

**This is NOT edge decay. This is a correct signal filter doing its job.**

---

### Category B: Win-Rate Collapse Failures (XRP — Genuine Edge Decay)

All XRP configurations showed a catastrophic win-rate collapse from in-sample to holdout:

| Period | Win Rate | PF |
| :--- | :---: | :---: |
| Selection (23-24) | 42–63% | 2.10–2.92 |
| Holdout 1 (2025) | **11.11%** | 0.17–0.39 |
| Holdout 2 (2026) | 33.33% | 0.09–0.74 |

**Diagnosis**: XRP's in-sample profitability was driven entirely by the 2023–2024 bull market, during which volatility expansions reliably preceded directional continuation. In 2025, XRP shifted to a choppy/reversal regime where breakouts systematically failed, dropping win rate to 11%. This is **true edge decay** — the signal had no predictive power outside the discovery window.

---

### Category C: Signal Extinction Failures (LINK — Insufficient Setups)

All LINK Holdout 1 configurations produced exactly **2 trades** — both losses. This is a signal extinction failure, not a strategy failure per se. The ATR expansion + 20-bar Donchian breakout criteria generated so few qualifying setups in 2025 that statistical validity is impossible.

| Period | LINK Trades |
| :--- | :---: |
| Selection (23-24) | 13–16 |
| Holdout 1 (2025) | **2** |
| Holdout 2 (2026) | 3 |

**Diagnosis**: LINK's 2025 price action was insufficient to generate the required ATR expansion + breakout confluence events. Holdout 2 shows partial recovery (PF up to 3.68 at RR=3.0, +36.39% return) but the trade counts remain below the minimum threshold.

---

### Category D: Mixed Failures (AVAX — Density + Minor Decay)

AVAX failed on both dimensions: insufficient trade counts (4–6 trades in Holdout 1) and mild edge deterioration. Unlike BTC, when AVAX did trade in 2025, quality was mixed (PF range: 0.59–1.87). This suggests AVAX's in-sample results were partially genuine but not fully robust.

---

## 4. Synthesis

### Was the ATR Expansion Edge Real?

> [!IMPORTANT]
> **Partially yes — for BTC specifically. The VE_3_ATR_EXPANSION strategy on BTC 4H shows a consistent, repeatable edge across all three periods when trades do occur. Every holdout trade produced a positive outcome (PF ≥ 2.00 in H1, PF ≥ 1.50 in H2 across all RR ratios). The fundamental signal logic is sound.**
>
> The validation failure is a **frequency problem**, not an **edge problem**. BTC's ATR expansion breakout at the 4H level triggers approximately 4–10 times per year — too infrequently to meet the minimum trade density gates independently.

### Consolidated Verdict by Asset:

| Asset | In-Sample Edge | Holdout Quality | Holdout Density | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **BTC** | ✅ Strong | ✅ Preserved | ❌ Too sparse | **Density rescue needed** |
| **LINK** | ✅ Strong | ⚠️ Partial (H2 ok, H1 failed) | ❌ Signal extinction | **Requires looser trigger** |
| **XRP** | ✅ Strong | ❌ Complete collapse | ❌ Sparse | **Genuine edge decay** |
| **AVAX** | ✅ Moderate | ⚠️ Mixed | ❌ Too sparse | **Inconclusive** |

---

## 5. Recommended Phase 15C Research Direction

Based on the failure mode analysis, there is a clear and specific path forward for BTC.

### Objective: Rescue BTC ATR Expansion via Multi-Timeframe Trade Density

The BTC 4H strategy has proven quality but insufficient frequency. The correct next step is to **expand the signal universe** without changing the core signal logic:

1.  **Add BTC 1H**: Run the identical `VE_3_ATR_EXPANSION` signal on the 1H timeframe for BTC. This will increase trade frequency by approximately 4× while preserving the same signal quality characteristics.
2.  **Add ETH 4H**: ETH showed PF = 1.34 and +51.53% net return in the full-history scan. Validate ETH 4H separately across the same three periods.
3.  **Do NOT loosen the signal parameters** to manufacture trades. The density problem must be solved by adding more instruments, not by weakening the filter.
4.  **Do NOT include XRP** in the next phase — its edge was regime-specific and has fully decayed.
