# Candidate 02 — VCP Strategy Variants

This document outlines the candidate strategy variants for the Volatility Contraction Pattern (VCP) research. It compares their logical structures and concludes with the recommended Version 1 hypothesis for implementation.

---

## 1. Candidate Strategy Variants

We define four distinct variants of the VCP strategy, ranging from pure price-action structures to continuous indicator approximations.

### Variant 1: Pure Swing VCP (Structure-Focused)
* **Description**: A pure price-action strategy that detects swing highs and lows to track the physical contraction of consolidation pullbacks. It uses no mathematical indicators except a basic trend filter.
* **Rules**:
  1. **Trend**: $\text{Close}(t) > \text{EMA}_{200}(t)$.
  2. **Contraction**: Detect $K$ successive swing points using window $W_s$. Pullback depths must decrease: $D_K < D_{K-1} < \dots < D_1$.
  3. **Volume**: Ignored (de-prioritized).
  4. **Breakout**: Close price closes above the highest swing high of the consolidation.
  5. **Stop Loss**: Set immediately below the swing low of the final contraction wave ($SL_K$).
  6. **Exit**: Fixed Risk-Reward target ($3\text{R}$) or time exit after $30$ bars.
* **Advantages**: Strictly faithful to the core geometric VCP concept. Very tight stops resulting in highly asymmetric R:R.
* **Disadvantages**: Algorithmically complex to identify and track swing structures robustly in historical backtests.

### Variant 2: ATR Rolling VCP (Indicator Approximation)
* **Description**: Approximates the volatility contraction pattern using continuous indicators, eliminating the need for complex swing-point tracking.
* **Rules**:
  1. **Trend**: $\text{Close}(t) > \text{EMA}_{200}(t)$.
  2. **Contraction**: Short-term/Long-term ATR ratio falls below a squeeze threshold: $\text{ATR}_{5}/\text{ATR}_{50} < 0.5$, and the price range over the last $20$ bars is in the bottom $10\%$ of historical ranges.
  3. **Breakout**: Close price breaks above the 20-bar Donchian channel high.
  4. **Stop Loss**: Entry price minus $2.0 \times \text{ATR}_{14}$.
  5. **Exit**: Trailing stop using the 20-period EMA.
* **Advantages**: Extremely simple to write, compile, and execute in any standard backtesting engine. No swing logic required.
* **Disadvantages**: Does not verify the asymmetric, decreasing step-like structure of pullbacks. It cannot differentiate between a flat consolidation and a structural contraction.

### Variant 3: Volume-Filtered Swing VCP
* **Description**: Enhances Variant 1 by adding strict volume constraints to verify supply dry-up during consolidation and institutional participation on the breakout.
* **Rules**:
  1. **Trend**: Same as Variant 1.
  2. **Contraction**: Same as Variant 1.
  3. **Volume Contraction**: The average volume of the last $3$ bars of the final contraction wave must be $< 0.6 \times \text{MA}_V(20)$.
  4. **Breakout**: Close price breaks above the swing high of the final contraction, with breakout bar volume $> 1.5 \times \text{MA}_V(20)$.
  5. **Stop Loss & Exit**: Same as Variant 1.
* **Advantages**: Reduces false breakout rate by filtering out quiet drift breakouts and distribution structures.
* **Disadvantages**: Significantly reduces trade density, potentially failing the minimum trade count gates on 4H timeframes. Sensitive to exchange-specific volume data.

### Variant 4: Regime-Filtered VCP
* **Description**: Integrates Variant 1 with an external market-wide regime filter (e.g., Bitcoin's trend state) to disable trading when the broader market is in a downtrend.
* **Rules**:
  1. **Regime Gate**: Only enter VCP long trades if $\text{Close}_{\text{BTC}} > \text{EMA}_{200,\text{BTC}}$.
  2. **Trend / Contraction / Breakout**: Same as Variant 1.
  3. **Stop Loss & Exit**: Same as Variant 1.
* **Advantages**: Protects capital during macro crypto liquidations where high correlation causes all altcoin breakouts to fail.
* **Disadvantages**: Introduces lookback and parameter dependency on an external asset (BTC), increasing model complexity.

---

## 2. Final Section: Version 1 Recommendation

We recommend **Variant 1 (Pure Swing VCP with Simple Exits)** as the Version 1 hypothesis for discovery.

### Rationale
Version 1 must minimize complexity while remaining structurally faithful to the VCP concept. 
* **Faithfulness**: Using actual swing depth contraction (Variant 1) is essential to test the true VCP hypothesis. Indicator approximations (Variant 2) lose the core geometric concept.
* **Simplicity**: Deferring volume filters (Variant 3) and BTC regime gates (Variant 4) keeps the design clean and reduces the parameter search space. Volume dry-up and BTC regime filters can be layered on in subsequent iterations as optimization filters if the baseline edge is established.
* **Risk Control**: A simple swing-low stop combined with a fixed risk-reward target provides a transparent, easy-to-evaluate baseline expectancy.

### Version 1 Mathematical Specification

A long trade is triggered at the open of bar $t+1$ if the following conditions are met at the close of bar $t$:

#### 1. Trend Filter
$$\text{Close}(t) > \text{EMA}_{200}(t)$$

#### 2. Consolidation & Swing Identification
Within a lookback window of the last $N_{\text{vcp}} = 60$ bars, we identify the local swing highs and swing lows using a swing radius of $W_s = 5$ bars:
* A swing high occurs at bar $j$ if $\text{High}(j) = \max_{k \in [j-W_s, j+W_s]} \text{High}(k)$.
* A swing low occurs at bar $j$ if $\text{Low}(j) = \min_{k \in [j-W_s, j+W_s]} \text{Low}(k)$.

#### 3. Contraction Criteria
The consolidation must contain exactly **two contraction waves** ($K = 2$):
* **Wave 1**: Pullback from Swing High 1 ($SH_1$) to Swing Low 1 ($SL_1$).
* **Wave 2**: Pullback from Swing High 2 ($SH_2$) to Swing Low 2 ($SL_2$).

We calculate pullback depths $D_1$ and $D_2$:
$$D_1 = \frac{SH_1 - SL_1}{SH_1}$$
$$D_2 = \frac{SH_2 - SL_2}{SH_2}$$

The contraction is valid if:
$$D_2 < D_1 \quad \text{(Contraction)}$$
$$D_2 \le 0.05 \quad \text{(Apex Tightness Gate)}$$

#### 4. Breakout Trigger
A breakout occurs on bar $t$ if the close breaches the highest high of the final contraction wave ($SH_2$):
$$\text{Close}(t) > SH_2 \quad \text{and} \quad \text{Close}(t-1) \le SH_2$$

#### 5. Entry
Execute a **Market Order** at the open of bar $t+1$.

#### 6. Position Management
* **Stop Loss**: Placed at entry minus the distance to the final swing low ($SL_2$) plus a small buffer:
  $$\text{Stop Loss} = SL_2 \times (1 - \epsilon) \quad \text{where } \epsilon = 0.05\%$$
* **Take Profit**: Fixed $3\text{R}$ target:
  $$\text{Take Profit} = \text{Entry} + 3.0 \times (\text{Entry} - \text{Stop Loss})$$
* **Time Exit**: If neither Stop Loss nor Take Profit is hit within $T_{\text{max}} = 30$ bars, exit at market on the close of the 30th bar.
