# Candidate 01 Relative Strength — Signal Design Specification

## Meta Information
* **Candidate ID**: Candidate 01
* **Strategy Name**: Relative Strength (Rotation)
* **Stage**: Stage 2 — Signal Design Specification
* **Status**: Specification Finalized / Awaiting Discovery Sweeps

---

## Section 1: Market Hypothesis

The core hypothesis is that **cryptocurrency markets exhibit pronounced cross-sectional dispersion driven by sequential capital flow, liquidity rotation, and speculative herding.** 

Rather than moving in perfect synchronization, assets within the crypto universe lead or lag each other during different phases of the market cycle. When aggregate market liquidity expands, capital moves through a predictable risk-on hierarchy (typically flowing from high-liquidity majors like Bitcoin and Ethereum into high-beta altcoins). During contractions, capital flees altcoins back to majors or fiat, causing defensive or structurally stronger assets to preserve value relative to their peers.

Systematically identifying and positioning in assets that demonstrate superior price resilience (during downturns) or superior velocity (during uptrends) allows a portfolio to capture cross-sectional alpha.

---

## Section 2: Trading Philosophy

### A. Why Positions Are Entered
Positions are opened in assets exhibiting leading cross-sectional price momentum. Entering these assets is a systematic vote on institutional accumulation, momentum herding, or fundamental strength. By selecting assets at the upper tail of the cross-sectional velocity distribution, the portfolio aligns capital with the strongest ongoing capital inflows.

### B. Why Positions Are Exited
Positions are closed when the asset's price velocity decays relative to the rest of the universe. An exit indicates that capital is actively rotating out of the asset and moving elsewhere. Exiting early cuts off the trailing lag phase of rotation, preventing capital from being trapped in stagnant or declining assets.

### C. Why Capital Rotates
Capital rotates because market participants are constrained by risk limits, margin capacity, and active attention. Speculators and market makers chase yield; they extract profits from exhausted trends and redeploy them into fresh breakouts. Because aggregate capital is finite, this rotation is a zero-sum liquidity cycle. Capital rotation ensures that the portfolio systematically exits mature, decelerating trends and moves capital to accelerating leaders.

---

## Section 3: Candidate Variants

To identify the optimal mathematical representation of relative strength, Candidate 01 is structured into four research variants:

* **Variant A: Raw Percentage Return Ranking**
  Measures the simple nominal rate of return over the lookback window.
  $$M_i(t, L) = \frac{\text{Close}_i(t) - \text{Close}_i(t-L)}{\text{Close}_i(t-L)}$$
  *Characteristics*: Highly sensitive to asset beta and rapid momentum wicks.
  
* **Variant B: Volatility-Adjusted Momentum Ranking**
  Normalizes the rate of return by the historical standard deviation of daily returns over the lookback window.
  $$M_i(t, L) = \frac{\text{Mean}(R_i)}{\sigma_i(L)}$$
  *Characteristics*: Penalizes erratic, high-variance assets, prioritizing consistent, smooth trends.

* **Variant C: ATR-Normalized Momentum**
  Normalizes the price change by the Average True Range over the lookback window.
  $$M_i(t, L) = \frac{\text{Close}_i(t) - \text{Close}_i(t-L)}{\text{ATR}_{10, i}(t) \times \text{Close}_i(t-L)}$$
  *Characteristics*: Translates momentum into units of average volatility, standardizing across different asset betas.

* **Variant D: Multi-Period Momentum Ranking**
  Computes a weighted composite rank across short-term, medium-term, and long-term lookback windows.
  $$\text{Composite Rank}_i = w_1 \cdot \text{Rank}_i(L_{\text{short}}) + w_2 \cdot \text{Rank}_i(L_{\text{mid}}) + w_3 \cdot \text{Rank}_i(L_{\text{long}})$$
  *Characteristics*: Selects assets displaying short-term velocity that are also aligned with longer-term structural trends.

---

## Section 4: Ranking Window Research Space

To identify the optimal momentum frequency, the lookback parameters are mapped to a geometric research space:
* **Lookback Windows ($L$, in candles)**: `10`, `20`, `30`, `50`, `75`, `100`, `150`, `200`

*Purpose*:
* Short lookbacks ($L \in [10, 30]$) capture fast liquidity rotations but risk whipsawing in noisy ranges.
* Long lookbacks ($L \in [100, 200]$) capture structural macroeconomic trends but suffer from entry and exit lag.

---

## Section 5: Portfolio Construction Research Space

The research sweeps will evaluate the following portfolio boundaries:
* **Portfolio Size ($K$, number of concurrent assets)**: `1`, `2`, `3`, `5`
* **Asset Allocation Weighting**:
  * **Equal Weighting**: Active capital is divided equally ($1/K$) among selected assets.
  * **Risk-Based Weighting (Postponed)**: Sizing positions inversely proportional to their rolling volatility (ATR) to equalize risk contributions. (Scheduled for future optimization, not Discovery).
* **Maximum Concurrent Positions**: Hard capped at $K$.
* **Trading Direction**: **Long Only**.
* **Long/Short Postponement Justification**: Long/Short execution (buying strength, shorting weakness) is postponed to Version 2 of Candidate 01 due to:
  1. *Funding Rate Friction*: Shorting mid-cap altcoins during bull regimes incurs high funding fee costs.
  2. *Asymmetric Risk Profiles*: Altcoins possess right-skewed tail distributions. Shorting laggards during market recoveries introduces catastrophic short-squeeze risk.
  3. *Regime Simplicity*: A long-only structure allows clean integration with market-wide cash filters.

---

## Section 6: Rebalance Research Space

The rebalance frequency ($R$) defines how often the asset universe is re-ranked and capital is redistributed:
* **Frequencies**: Every candle ($1R$), every 2 candles ($2R$), every 4 candles ($4R$), or daily ($24R$ for the 1H timeframe).

### Trade-Off Matrix
| Frequency | Expected Advantages | Expected Disadvantages |
| :--- | :--- | :--- |
| **Every Candle ($1R$)** | * Maximizes responsiveness.<br>* Instantly exits decaying assets. | * High turnover fees ($0.045\%$ taker).<br>* Increased slippage impact.<br>* Frequent whipsawing. |
| **Multi-Candle ($2R$ / $4R$)** | * Filters out micro-noise.<br>* Reduces transaction fees. | * Introduces execution lag.<br>* May delay exits during market flush events. |
| **Daily ($24R$)** | * Minimizes trading friction.<br>* Aligns with daily fund rebalancing. | * Ineffective for short timeframes (e.g., 15m).<br>* Exposes portfolio to intraday drawdowns. |

---

## Section 7: Exit Research Space

All research exits are strictly objective, rule-based, and lack human discretion:
1. **Rank Decay Exit (Relative Rank)**:
   A position is closed if its relative strength rank falls below $K$ (e.g. out of the top 3) or drops below a buffer threshold $E$ (where $E > K$, such as exiting only when it falls below Top 5).
2. **Fixed ATR Stop Loss**:
   $$\text{Stop Loss Price} = \text{Entry Price} - (M_{\text{SL}} \times \text{ATR}_{10})$$
   Protects capital against idiosyncratic asset crashes.
3. **Fixed Take Profit (Risk-to-Reward)**:
   $$\text{Take Profit Price} = \text{Entry Price} + (M_{\text{TP}} \times \text{ATR}_{10})$$
   Executes maker limit orders at fixed risk-to-reward boundaries (e.g., 1:2 or 1:3).
4. **Time-Based Exit (Holding Period)**:
   Positions are closed after a fixed number of candles ($H$ bars) if neither the ATR Stop nor the Rank Decay has triggered, preventing capital stagnation.

---

## Section 8: Parameters To Keep Constant

To isolate the strategy's core alpha and reduce dimensionality during sweeps, the following parameters remain constant:
1. **Universe of Assets**: Frozen at the specified 25 crypto assets. (Prevents survivorship and selection bias).
2. **Execution Cost Adjustments**: Taker fee rate at $0.045\%$, Maker fee rate at $0.015\%$, and Taker Slippage penalty at $0.05\%$. (Ensures realistic trading friction).
3. **Maximum Leverage**: Capped at $5\text{x}$ isolated margin. (Enforces consistent capital scaling).
4. **Timeframes**: Only `15m`, `1H`, and `4H` candles will be compiled.

---

## Section 9: Parameters To Explore

The active parameter grid for the Discovery sweep contains:
1. **Lookback Window ($L$)**: $[10, 20, 30, 50, 75, 100, 150, 200]$
2. **Portfolio Size / Max Positions ($K$)**: $[1, 2, 3, 5]$
3. **Rebalance Frequency ($R$)**: $[1, 2, 4]$ (and $24$ for 1H/4H timeframes)
4. **Stop Loss Multiplier ($M_{\text{SL}}$)**: $[2.0, 3.0, 4.0]$
5. **Take Profit Multiplier ($M_{\text{TP}}$)**: $[2.0, 3.0, \text{None}]$
6. **Exit Rank Decay Gate ($E$)**: $[K, K+1, K+2]$

---

## Section 10: Hypothesis Lock

The following technical filters, indicators, and rules are **systematically excluded** from Candidate 01 during the Discovery phase:
* **No Trend-Following Moving Averages** (e.g., EMA200, SMA50)
* **No Bound Oscillators** (e.g., RSI, Stochastic, CCI)
* **No Volatility Channel Bands** (e.g., Bollinger Bands, Keltner Channels)
* **No Absolute Volume Filters** (e.g., volume spikes, OBV)
* **No Trend Strength Indicators** (e.g., ADX)
* **No Discretionary or Chart Pattern Logic** (e.g., Support/Resistance, Head & Shoulders)
* **No Multi-Indicator Stacking**

If any of these filters are required to pass future validation stages, they will be specified under **Candidate 01 Version 2**.

---

## Section 11: Research Matrix

The initial experimental sweep covers the cross-product of variants, timeframes, and lookbacks. Status is set to `NOT STARTED`.

| Exp ID | Variant | Timeframe | Lookback ($L$) | Portfolio Size ($K$) | Rebalance ($R$) | Exit Logic | Status |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **EXP-01** | Variant A | 1H | 20 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-02** | Variant A | 1H | 50 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-03** | Variant A | 4H | 20 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-04** | Variant A | 4H | 50 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-05** | Variant B | 1H | 20 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-06** | Variant B | 1H | 50 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-07** | Variant B | 4H | 20 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-08** | Variant B | 4H | 50 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-09** | Variant C | 1H | 20 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-10** | Variant C | 1H | 50 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-11** | Variant C | 4H | 20 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-12** | Variant C | 4H | 50 | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-13** | Variant D | 1H | Multi | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-14** | Variant D | 4H | Multi | 3 | 1 bar | Rank Decay + 3 ATR Stop | `NOT STARTED` |
| **EXP-15** | Variant B | 15m | 30 | 5 | 4 bars | Rank Decay + 2 ATR Stop | `NOT STARTED` |

*(This represents the initial baseline sweep matrix. Further permutations will be generated dynamically during the sweep phase).*

---

## Section 12: Risks

* **Research Risk (Data Snooping)**: Selecting lookback parameters that perform exceptionally well in-sample (2023-2024) but collapse during out-of-sample periods (2025-2026).
* **Implementation Risk (State Recovery)**: Inability of the paper broker or production engine to maintain rebalance structures, token balances, and target weights across system restarts.
* **Statistical Risk (Sample Size)**: Running 4H configurations results in fewer trades, reducing statistical confidence in the expectancy and profit factor calculations.
* **Operational Risk (Funding Rates & Liquidity)**: Relative strength leaders are often highly volatile mid-caps. The portfolio could face large slippage wicks during execution, or get stuck paying high funding rates.
* **Curve-Fitting Risk (Over-Optimization)**: Tuning $K$, $L$, and $R$ simultaneously to fit a specific bull market regime, leading to high drawdowns during subsequent regime flips.

---

## Section 13: Success Criteria

### A. Success Metrics (Discovery Stage)
To pass the Discovery stage and proceed to Walk-Forward Analysis, a candidate configuration must meet:
1. **Trade Count Requirements**:
   * `15m`: $\ge 225$ trades in-sample.
   * `1H`: $\ge 120$ trades in-sample.
   * `4H`: $\ge 50$ trades in-sample.
2. **Performance Expectations**:
   * **Profit Factor**: $\ge 1.15$
   * **Expectancy**: $\ge 0.1\text{R}$ per trade
   * **Net Return**: Positive return after transaction fee adjustments.
3. **Statistical Robustness**:
   * Drawdown profile must not exhibit structural decay over the period.

### B. Classification Thresholds
* **PASS**: Meets all success metrics in-sample and out-of-sample.
* **BORDERLINE**: Positive net returns, but Profit Factor is between $1.0$ and $1.15$ or trade count is slightly below threshold.
* **WATCHLIST**: Expectancy is positive, but performance depends on a specific market regime (e.g. bull only).
* **REJECT**: Negative expectancy, failed trade thresholds, or high risk of ruin.

---

## Candidate 01 Hypothesis Lock

The following assumptions are frozen for Candidate 01:
1. **No indicators are stacked on signals** (including EMA, RSI, Bollinger, ADX, Volume).
2. **The universe consists strictly of the 25 specified crypto assets**.
3. **Trading direction is long-only**.
4. **Execution occurs strictly on close of candle $t$, matching open of candle $t+1$**.
5. **No discretionary rules or chart pattern recognition are applied**.

Any change to these frozen assumptions requires the formal creation of **Candidate 01 Version 2**.
