# Quantitative Trading Literature Review & Candidate C003 Selection

This document contains a literature review of 10 well-known quantitative trading approaches suitable for cryptocurrency markets, compares them inside a ranking matrix, and recommends the strategy for **Candidate C003**.

---

## 1. Literature Review of 10 Quantitative Approaches

### Approach 1: Trend Following / Moving Average Crossover (e.g. MACD, Supertrend, Dual EMA)
- **Core Market Inefficiency**: Price persistence (momentum) driven by persistent capital flows, news propagation lags, and behavioral herd dynamics.
- **Expected Trade Frequency**: Low to Medium (1-10 trades per month per asset, depending on lookback).
- **Regime Robustness**: High in persistent trending markets; suffers severe whipsaws and capital decay in sideways/ranging/mean-reverting markets.
- **Risk Characteristics**: Positively skewed returns (long tails of large gains), low win rate (30-40%), and large peak-to-trough drawdowns during regime transitions.
- **Advantages**: Simple, highly robust, captures tail gains, easily scalable.
- **Weaknesses**: High drawdown duration, low win rate, vulnerable to prolonged horizontal ranges.
- **Suitability for Long-Only**: High (benefiting from major bull cycles).
- **Risk of Overfitting**: Low (few parameters like lookback periods).
- **Expected Compatibility**: High (core to our trend filters).

### Approach 2: Mean Reversion / Oscillator Overbought-Oversold (e.g. Bollinger Bands, RSI)
- **Core Market Inefficiency**: Temporary liquidity/buying exhaustion causing price overextension and subsequent reversion to a rolling mean (price elasticity).
- **Expected Trade Frequency**: Medium to High (20-80 trades per month).
- **Regime Robustness**: Excellent in horizontal range regimes; suffers severe "falling knife" losses in strong, directional trend regimes.
- **Risk Characteristics**: Negatively skewed returns (high win rate but large tail losses), subject to stop-runs during breakouts.
- **Advantages**: High win rate, frequent trades, provides steady return streams in quiet markets.
- **Weaknesses**: Vulnerable to strong breakouts (lacks protection in runaway trends), high turnover costs.
- **Suitability for Long-Only**: Medium (long entry on oversold extremes is viable but requires a strict stop-loss).
- **Risk of Overfitting**: Medium (requires tuning thresholds and lookbacks).
- **Expected Compatibility**: High.

### Approach 3: Perpetual Funding Rate Arbitrage / Basis Trading (Spot-Perp Cash & Carry)
- **Core Market Inefficiency**: Supply-demand imbalances for leverage on perp exchanges, leading to persistent funding rate premiums/discounts.
- **Expected Trade Frequency**: Low (typically held for weeks or months).
- **Regime Robustness**: High (delta-neutral yield extraction across bull and bear markets).
- **Risk Characteristics**: Extremely low market risk, but high operational/liquidation risk on leverage legs during anomalous squeeze events.
- **Advantages**: Highly consistent, delta-neutral yield, low drawdowns.
- **Weaknesses**: Requires shorting (non-compatible with long-only), capital intensive, yield decays when capital floods the arb space.
- **Suitability for Long-Only**: Low (cannot be executed without shorting perp futures).
- **Risk of Overfitting**: Extremely Low.
- **Expected Compatibility**: Low.

### Approach 4: Market Making / Order Book Imbalance (HFT Inventory Skew)
- **Core Market Inefficiency**: Bid-ask spread capture and short-term inventory imbalances (microstructure edge).
- **Expected Trade Frequency**: Extremely High (thousands of trades per day).
- **Regime Robustness**: Low (vulnerable to toxic order flow and adverse selection during market panics).
- **Risk Characteristics**: Inventory accumulation risk during one-sided trends, highly dependent on latency.
- **Advantages**: Steady tick-level yield, low exposure time.
- **Weaknesses**: Extremely high execution dependency, low-latency infrastructure required, high exchange fee drag.
- **Suitability for Long-Only**: Low (strictly bi-directional/delta-neutral quoting).
- **Risk of Overfitting**: High.
- **Expected Compatibility**: Extremely Low (requires tick L2/L3 order book data).

### Approach 5: Volume Profile / Value Area / Support & Resistance (Auction Market Theory)
- **Core Market Inefficiency**: Price distribution centers around historical high-volume nodes (fair value) and reacts/rejects at low-volume areas (value area edges).
- **Expected Trade Frequency**: Medium (10-30 trades per month).
- **Regime Robustness**: High (value areas act as structural support/resistance across regimes).
- **Risk Characteristics**: False breakouts at value area boundaries, slippage at liquidity voids.
- **Advantages**: Anchored on actual volume transacted rather than time-based charts, high structural logic.
- **Weaknesses**: Complex calculation, level identification can be subjective/overfit to historical tick data.
- **Suitability for Long-Only**: High (buying at high-volume nodes or value area low).
- **Risk of Overfitting**: Medium to High.
- **Expected Compatibility**: Medium (requires volume profile processing).

### Approach 6: Machine Learning classification on Lag-Return Features
- **Core Market Inefficiency**: Complex, non-linear dependencies between past features (price, volatility, funding) and near-term price direction.
- **Expected Trade Frequency**: High (daily or hourly predictions).
- **Regime Robustness**: Low (models rapidly degrade when market regimes shift from training data distributions).
- **Risk Characteristics**: Model drift, high tail risk during anomalous macro events.
- **Advantages**: Adapts to complex feature interactions.
- **Weaknesses**: Lack of interpretability, high overfitting risk, black-box execution.
- **Suitability for Long-Only**: Medium.
- **Risk of Overfitting**: Extremely High.
- **Expected Compatibility**: Medium.

### Approach 7: Volatility Breakout (Session Open Range Breakout - SORB)
- **Core Market Inefficiency**: Intraday price expansion triggered by regional session opens (liquidity injection) leading to directional continuation.
- **Expected Trade Frequency**: Medium (15-40 trades per month per asset).
- **Regime Robustness**: High (volatility expands during high-volume openings regardless of secular market cycles).
- **Risk Characteristics**: Whipsaws during low-volatility sessions or false breakout drives.
- **Advantages**: Highly symmetric (easy to short), simple, clear boundary levels, low overfitting risk.
- **Weaknesses**: High dependence on execution quality and spread/fees.
- **Suitability for Long-Only**: High (long breakout trigger).
- **Risk of Overfitting**: Low (simple range breakout rules).
- **Expected Compatibility**: High (fits standard candle-based backtesting).

### Approach 8: Statistical Arbitrage / Pairs Trading (e.g. ETH/BTC Cointegration)
- **Core Market Inefficiency**: Temporary divergence of cointegrated asset prices from their long-term equilibrium relationship.
- **Expected Trade Frequency**: Medium (5-20 trades per month).
- **Regime Robustness**: High, but cointegration relationships can permanently break.
- **Risk Characteristics**: Risk of permanent divergence (e.g. one asset goes bankrupt or breaks relationship).
- **Advantages**: Beta-neutral, isolates relative value.
- **Weaknesses**: Requires shorting (long one, short another), or if long-only relative rotation, it becomes similar to Relative Strength.
- **Suitability for Long-Only**: Low to Medium.
- **Risk of Overfitting**: Medium.
- **Expected Compatibility**: Medium.

### Approach 9: Intraday Funding Rate Drift / Momentum
- **Core Market Inefficiency**: Price drifts leading up to and immediately following perp funding rate payments (arbitrageurs adjusting positions).
- **Expected Trade Frequency**: Medium to High (aligned to 4H or 8H funding hours).
- **Regime Robustness**: Medium.
- **Risk Characteristics**: Dependent on leverage demand cycles, fee drag.
- **Advantages**: Aligned to a predictable chronological schedule.
- **Weaknesses**: High fee turnover, decay of the premium.
- **Suitability for Long-Only**: Medium (buy before high-funding hours).
- **Risk of Overfitting**: Medium.
- **Expected Compatibility**: High.

### Approach 10: Calendar Anomalies / Intraday Seasonality (Time-of-day / Day-of-week)
- **Core Market Inefficiency**: Recurring patterns of buying/selling pressure associated with calendar time (e.g. weekend liquidity drop, London open directional drives, end-of-month flows).
- **Expected Trade Frequency**: Medium.
- **Regime Robustness**: Medium.
- **Risk Characteristics**: Decay of seasonality patterns.
- **Advantages**: Clear, zero-parameter timing signals.
- **Weaknesses**: Low statistical significance in short historical windows, highly affected by macro regime shifts.
- **Suitability for Long-Only**: High.
- **Risk of Overfitting**: Low to Medium.
- **Expected Compatibility**: High.

---

## 2. Comparison Matrix

| Approach | Statistical Robustness | Trade Frequency | Regime Robustness | Overfitting Risk | Long-Only Suitability | Framework Compatibility | **Rank** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Trend Following** | High | Low-Med | Medium | Low | High | High | **3** |
| **2. Mean Reversion** | Med-High | Medium | Medium | Medium | Med-High | High | **4** |
| **3. Basis Arbitrage** | High | Low | High | Low | Low | Low | **9** |
| **4. Market Making** | Medium | High | Low | High | Low | Low | **10** |
| **5. Volume Profile** | Medium | Medium | High | Medium | High | Medium | **6** |
| **6. Machine Learning**| Low | Medium | Low | High | Medium | Medium | **8** |
| **7. Volatility Breakout (SORB)** | **High** | **Medium** | **High** | **Low** | **High** | **High** | **1** |
| **8. Pairs Trading** | Medium | Medium | Medium | Medium | Low-Med | Medium | **7** |
| **9. Funding Drift** | Medium | Med-High | Medium | Medium | Medium | High | **5** |
| **10. Calendar/Seasonality**| Medium | Medium | Medium | Low-Med | High | High | **2** |

---

## 3. Recommendation: Session Open Range Breakout (SORB)

We recommend **Session Open Range Breakout (SORB) with Trend-Volume Filters** as Candidate C003.

### Rationale:
1. **Statistical Robustness**: Exploits institutional and market-making order flow injected at London (07:00 UTC) and New York (13:00 UTC) session opens. These openings consistently represent local maxima in intraday volume and volatility.
2. **Symmetry & Extensibility**: The breakout mechanism is inherently symmetric. Validating a long-only version (C003) translates directly into a short-only counterpart (C003-S).
3. **Simple & Explainable**: Entry is defined by clear horizontal boundaries (High/Low of the first 60 minutes of the session).
4. **Differentiation**: 
   - C001 (Relative Strength) is a cross-sectional trend-following system with a multi-day holding period.
   - C002 (VCP) is a multi-week volatility compression breakout system.
   - C003 (SORB) is an intraday session breakout system with short holding times (typically exited at the session or daily close).
