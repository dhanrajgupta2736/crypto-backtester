# Candidate 02 — VCP Objective Mathematical Definition

This document details the objective, deterministic mathematical formulations for each component of the Volatility Contraction Pattern (VCP). It provides a survey of alternative quantitative measures, evaluating their advantages, disadvantages, expected market behaviors, and parameter ranges.

---

## 1. Trend Detection

The VCP must only be traded in assets experiencing a strong primary uptrend. We evaluate four quantitative trend measures below.

### A. Moving Average Structure
* **Purpose**: Confirm a stacked, upward-sloping moving average structure, ensuring a classic Stage 2 uptrend.
* **Quantitative Definition**:
  $$\text{Close}(t) > \text{EMA}_1(t) > \text{EMA}_2(t) > \text{EMA}_3(t)$$
  $$\text{EMA}_3(t) > \text{EMA}_3(t-L_t)$$
  Where typical values are $\text{EMA}_1 = 50$, $\text{EMA}_2 = 150$, $\text{EMA}_3 = 200$, and $L_t = 10$ bars.
* **Advantages**: Very stable; effectively filters out assets in distribution or downtrend phases. Widely accepted benchmark.
* **Disadvantages**: Lags significantly at major market turning points, potentially delaying entry into new trends.
* **Expected Market Behavior**: Selects assets during steady, long-term accumulation phases. Avoids trading during bear markets or early range expansions.
* **Parameter Ranges**: 
  * Short EMA: $20 \le N_1 \le 50$ bars
  * Medium EMA: $50 \le N_2 \le 150$ bars
  * Long EMA: $100 \le N_3 \le 200$ bars
  * Slope lookback $L_t$: $5 \le L_t \le 20$ bars

### B. Higher Highs / Higher Lows (Swing Structure)
* **Purpose**: Confirm a structural uptrend defined by successive higher swing highs and higher swing lows.
* **Quantitative Definition**:
  Let $H_i$ and $L_i$ be the $i$-th swing high and swing low detected using a swing window $W_s$. A swing high is a bar at index $t$ where:
  $$\text{High}(t) = \max_{j \in [-W_s, W_s]} \text{High}(t+j)$$
  For the last three detected swing highs ($H_{n-2}, H_{n-1}, H_n$) and swing lows ($L_{n-2}, L_{n-1}, L_n$), we require:
  $$H_n > H_{n-1} > H_{n-2} \quad \text{and} \quad L_n > L_{n-1} > L_{n-2}$$
* **Advantages**: Matches market-structure theory exactly; not smoothed by indicators.
* **Disadvantages**: Finding swings is highly sensitive to the window parameter $W_s$. Noise in crypto can easily invalidate the strict inequality.
* **Expected Market Behavior**: Captures clean step-like trends. May reject strong, vertical trends that don't form deep enough pullbacks to register as swings.
* **Parameter Ranges**:
  * Swing Window $W_s$: $5 \le W_s \le 30$ bars

### C. Donchian Trend Midpoint
* **Purpose**: Determine the trend relative to the midpoint of the asset's trading range over a long lookback.
* **Quantitative Definition**:
  $$\text{Donchian Mid}(t, L_d) = \frac{\max_{j \in [0, L_d-1]} \text{High}(t-j) + \min_{j \in [0, L_d-1]} \text{Low}(t-j)}{2}$$
  $$\text{Close}(t) > \text{Donchian Mid}(t, L_d) \quad \text{and} \quad \text{Donchian Mid}(t, L_d) > \text{Donchian Mid}(t-1, L_d)$$
* **Advantages**: Highly responsive; less lag than a 200-period EMA.
* **Disadvantages**: Prone to whipsaw in wide, choppy ranges where the midpoint flattens.
* **Expected Market Behavior**: Enters early in emerging trends but can suffer in volatile consolidation ranges.
* **Parameter Ranges**:
  * Donchian Lookback $L_d$: $50 \le L_d \le 200$ bars

### D. Linear Regression Slope
* **Purpose**: Measure the rate of change of price over time using a least-squares regression line fit to log prices.
* **Quantitative Definition**:
  Fit the line $y = m \cdot x + c$ where $y = \ln(\text{Close}(t-j))$ and $x = -j$ for $j \in [0, L_r-1]$.
  $$\text{Slope } m > 0 \quad \text{and} \quad R^2 > \text{Threshold}$$
  Where $R^2$ is the coefficient of determination, ensuring the trend is tight and linear.
* **Advantages**: Mathematically elegant; provides a direct measure of trend strength and linear consistency.
* **Disadvantages**: Highly sensitive to the lookback window $L_r$. A single large bar can skew the slope.
* **Expected Market Behavior**: Smoothly ranks and selects the most linear, persistent trends.
* **Parameter Ranges**:
  * Regression Window $L_r$: $30 \le L_r \le 120$ bars
  * $R^2$ threshold: $0.1 \le R^2 \le 0.5$

---

## 2. Volatility Contraction

The defining feature of a VCP is the reduction in price volatility from left to right. We evaluate three metrics.

### A. Swing Range Contraction (Primary Candidate)
* **Purpose**: Measure the percentage depth of successive consolidation pullbacks to ensure they are shrinking.
* **Quantitative Definition**:
  Let $C_1, C_2, \dots, C_K$ be the contraction waves within a consolidation structure, where $K$ is the number of contractions ($K \ge 2$, typically $2$ to $4$).
  For each contraction wave $i$, the depth $D_i$ is calculated from the local swing high $SH_i$ to the subsequent local swing low $SL_i$:
  $$D_i = \frac{SH_i - SL_i}{SH_i}$$
  To confirm volatility contraction, we require:
  $$D_i < D_{i-1} \quad \text{for all } i \in [2, K]$$
  Additionally, the final contraction depth $D_K$ must be tight:
  $$D_K \le D_{\text{max\_tight}}$$
  Where $D_{\text{max\_tight}}$ is a parameter (e.g., $5\%$).
* **Advantages**: Directly measures the physical shape of the VCP (the classic "waves"). Highly intuitive and structurally meaningful.
* **Disadvantages**: Algorithmically complex to identify and align historical swing points deterministically in code.
* **Expected Market Behavior**: Identifies textbook coil patterns where supply is steadily locked up.
* **Parameter Ranges**:
  * Number of contractions $K$: $2 \le K \le 4$
  * Max tight depth $D_{\text{max\_tight}}$: $1\% \le D_{\text{max\_tight}} \le 8\%$

### B. ATR Ratio Contraction
* **Purpose**: Measure contraction by comparing short-term ATR to long-term ATR.
* **Quantitative Definition**:
  $$\text{ATR Ratio}(t) = \frac{\text{ATR}(t, L_{\text{short}})}{\text{ATR}(t, L_{\text{long}})}$$
  $$\text{ATR Ratio}(t) < \text{Threshold}_{\text{ratio}} \quad \text{and} \quad \text{Slope}(\text{ATR Ratio}, L_{\text{slope}}) < 0$$
* **Advantages**: Easy to implement; continuous indicator that avoids complex swing-detection logic.
* **Disadvantages**: Does not guarantee that price is consolidating near overhead resistance; it only measures volatility contraction, which can also occur during a drift downward.
* **Expected Market Behavior**: Identifies periods of quiet compression.
* **Parameter Ranges**:
  * Short ATR $L_{\text{short}}$: $5 \le L_{\text{short}} \le 14$ bars
  * Long ATR $L_{\text{long}}$: $20 \le L_{\text{long}} \le 100$ bars
  * Threshold Ratio: $0.4 \le \text{Threshold}_{\text{ratio}} \le 0.7$

### C. Rolling Volatility Bandwidth
* **Purpose**: Measure the width of Bollinger Bands normalized by price, showing historical squeeze states.
* **Quantitative Definition**:
  $$\text{Bandwidth}(t) = \frac{\text{Upper Band}(t, L_b) - \text{Lower Band}(t, L_b)}{\text{SMA}(t, L_b)}$$
  $$\text{Bandwidth}(t) = \min_{j \in [0, L_{\text{lookback}}-1]} \text{Bandwidth}(t-j)$$
* **Advantages**: Standardized metric (Bollinger Band Squeeze). Captures multi-bar volatility compression.
* **Disadvantages**: Does not verify the asymmetric, decreasing step-like structure of the VCP pullbacks.
* **Expected Market Behavior**: Selects assets experiencing extreme compression.
* **Parameter Ranges**:
  * Bandwidth Period $L_b$: $20 \le L_b \le 50$ bars
  * Lookback window $L_{\text{lookback}}$: $5 \le L_{\text{lookback}} \le 20$ bars

---

## 3. Volume Contraction

* **Purpose**: Verify that transaction volume shrinks as price consolidates, indicating that sell pressure is exhausted before the breakout.
* **Quantitative Definition**:
  Let $\text{MA}_V(t, L_v)$ be the simple moving average of volume:
  $$\text{MA}_V(t, L_v) = \frac{1}{L_v} \sum_{j=0}^{L_v-1} \text{Volume}(t-j)$$
  Volume contraction is confirmed if the volume at the apex (final contraction wave $C_K$) is significantly below average:
  $$\text{Volume}(t) < K_v \cdot \text{MA}_V(t, L_v)$$
  Where $K_v \in [0.4, 0.8]$ is the volume contraction multiplier.
* **Advantages**: Confirms the absence of active sellers, lowering the probability of a false breakout.
* **Disadvantages**: Volume in crypto can be highly fragmented across exchanges, subject to wash trading, or quiet due to time-of-day effects rather than structural pattern dynamics.
* **Expected Market Behavior**: Filters out consolidations that have high participation (which are prone to distribution) in favor of quiet, accumulated bases.
* **Version 1 Recommendation**: **Defer to Version 2 / Keep Optional**. Including strict volume filters in Version 1 will severely restrict trade count and introduce noise due to exchange volume fragmentation. Price contraction is the primary requirement; volume contraction should be analyzed as an optimization filter later.

---

## 4. Breakout Trigger

The breakout trigger defines the precise price level and condition that signals the start of the price expansion phase.

### A. Highest Close / Highest High (Structure Breakout)
* **Purpose**: Enter when the price closes above the absolute maximum resistance level established by the entire VCP consolidation structure.
* **Quantitative Definition**:
  Let $L_{\text{vcp}}$ be the total duration of the consolidation structure.
  $$\text{Resistance Level} = \max_{j \in [1, L_{\text{vcp}}]} \text{High}(t-j)$$
  $$\text{Close}(t) > \text{Resistance Level}$$
* **Advantages**: Cleanest definition; ensures that all overhead resistance from the pattern has been cleared.
* **Disadvantages**: Can result in a late entry with a wide stop if the breakout bar is exceptionally large.
* **Expected Market Behavior**: Captures high-momentum runs. Avoids early fakeouts inside the pattern.
* **Parameter Ranges**:
  * Consolidation Lookback $L_{\text{vcp}}$: $20 \le L_{\text{vcp}} \le 120$ bars

### B. Pivot Breakout (Swing High Breakout - Primary Candidate)
* **Purpose**: Enter when the price breaches the resistance of the *most recent* consolidation wave (the "cheat pivot").
* **Quantitative Definition**:
  Let $SH_K$ be the swing high of the final contraction wave $C_K$.
  $$\text{Close}(t) > SH_K$$
* **Advantages**: Allows entry much closer to the apex, reducing the distance to the stop loss and increasing the Risk-to-Reward ratio (cheat entry).
* **Disadvantages**: Higher probability of whipsaw, as the price is still inside the larger consolidation range.
* **Expected Market Behavior**: Enters early in the breakout sequence. High win expectancy in strong markets; higher failure rate in choppy markets.
* **Parameter Ranges**:
  * Final Swing High index: Detected via local swing algorithms ($W_s \in [3, 10]$).

---

## 5. Exits & Stop Loss

Managing risk is critical because VCP setups rely on tight risk definition at entry.

### A. Swing Low Stop (Primary Candidate)
* **Purpose**: Place the stop loss at the structural invalidation level of the pattern (the lowest price of the most recent consolidation wave).
* **Quantitative Definition**:
  Let $SL_K$ be the swing low of the final contraction wave $C_K$ (or the lowest low of the last $N_{sl}$ bars before entry).
  $$\text{Stop Loss Price} = SL_K - \epsilon$$
  Where $\epsilon$ is a small buffer (e.g., $0.05\%$, or $0.1 \times \text{ATR}_{14}$) to avoid tick-level stop-outs.
* **Advantages**: Directly tied to the structure. If the price breaks below the final contraction low, the VCP is structurally invalidated. This yields very tight stops.
* **Disadvantages**: In highly volatile assets, a tight structural stop can easily be triggered by transient noise before the breakout proceeds.
* **Expected Market Behavior**: Results in highly asymmetric trades. Many small, quick losses balanced by large trend wins.
* **Parameter Ranges**:
  * Lookback for low $N_{sl}$: $5 \le N_{sl} \le 20$ bars
  * Volatility buffer: $0 \le \epsilon \le 0.5 \times \text{ATR}_{14}$

### B. ATR Stop
* **Purpose**: Define a risk boundary based on rolling volatility, independent of specific chart structure.
* **Quantitative Definition**:
  $$\text{Stop Loss Price} = \text{Entry Price} - M_{\text{SL}} \cdot \text{ATR}_{14}(t)$$
* **Advantages**: Adaptable to the asset's current volatility regime; guaranteed to handle high-volatility assets by widening the stop.
* **Disadvantages**: Not structurally meaningful; may place the stop in the middle of a contraction wave, resulting in premature exit of a valid pattern.
* **Expected Market Behavior**: Normalizes risk across different assets.
* **Parameter Ranges**:
  * ATR Multiplier $M_{\text{SL}}$: $1.5 \le M_{\text{SL}} \le 3.5$

### C. Fixed Risk-Reward (R:R) Profit Target
* **Purpose**: Take profit at a fixed multiple of the initial risk.
* **Quantitative Definition**:
  $$\text{Risk (R)} = \text{Entry Price} - \text{Stop Loss Price}$$
  $$\text{Take Profit Price} = \text{Entry Price} + M_{\text{TP}} \cdot \text{Risk}$$
* **Advantages**: Simple to execute; locks in profits at key mathematical targets.
* **Disadvantages**: Cuts off outlier trends early, which are necessary to offset small losses in breakout strategies.
* **Parameter Ranges**:
  * Target Multiplier $M_{\text{TP}}$: $1.5 \le M_{\text{TP}} \le 4.0$

### D. Trailing Stop (EMA or Parabolic SAR)
* **Purpose**: Trail the stop loss behind a moving average to capture large trend extensions.
* **Quantitative Definition**:
  $$\text{Stop Loss}(t) = \max(\text{Stop Loss}(t-1), \text{EMA}_{\text{trail}}(t))$$
* **Advantages**: Allows the strategy to capture massive, open-ended trends.
* **Disadvantages**: Gives back a significant portion of profits during sharp reversals.
* **Parameter Ranges**:
  * Trail EMA: $10 \le N_{\text{trail}} \le 30$ bars

### E. Time Exit
* **Purpose**: Exit trades that fail to expand within a certain timeframe, releasing capital.
* **Quantitative Definition**:
  Exit position at market if trade duration exceeds $T_{\text{max}}$ bars and target has not been met.
* **Advantages**: Improves capital efficiency and reduces exposure to rangebound chop.
* **Disadvantages**: May cut off a slow-developing but ultimately successful breakout.
* **Parameter Ranges**:
  * Max hold time $T_{\text{max}}$: $10 \le T_{\text{max}} \le 50$ bars

---

## 6. Invalidations

Deterministic rules to discard patterns before entry, or abort trades immediately post-entry.

### A. Pattern Invalidation (Pre-Entry)
1. **Time Limit**: If the consolidation duration exceeds $L_{\text{max\_vcp}}$ bars without a breakout, the pattern is discarded.
2. **Depth Breach**: If the price drops below the swing low of the *first* contraction wave ($SL_1$), the consolidation structure is broken, and the pattern tracker is reset.
3. **Volatility Expansion**: If a subsequent contraction depth is greater than the previous one ($D_i > D_{i-1}$), the contraction sequence is broken, and the pattern tracker is reset.

### B. Trade Invalidation (Failed Breakout / Post-Entry)
1. **Failed Breakout (Whipsaw)**: If the breakout bar closes below the pivot level (or if the subsequent candle closes back inside the consolidation range), the breakout is flagged as false. The position may be exited immediately at the market close of that bar to minimize damage.
