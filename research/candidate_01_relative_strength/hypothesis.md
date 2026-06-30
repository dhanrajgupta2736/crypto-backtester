# Candidate 01 Relative Strength — Market Hypothesis

This document defines the underlying economic and behavioral hypothesis for the Relative Strength strategy family.

---

## 1. Market Hypothesis

The core hypothesis is that **cryptocurrency markets exhibit pronounced cross-sectional dispersion driven by sequential capital flow, liquidity rotation, and speculative herding.** 

Rather than moving in perfect synchronization, assets within the crypto universe lead or lag each other during different phases of the market cycle. When aggregate market liquidity expands, capital moves through a predictable risk-on hierarchy (typically flowing from high-liquidity majors like Bitcoin and Ethereum into high-beta altcoins). During contractions, capital flees altcoins back to majors or fiat, causing defensive or structurally stronger assets to preserve value relative to their peers.

Systematically identifying and positioning in assets that demonstrate superior price resilience (during downturns) or superior velocity (during uptrends) allows a portfolio to capture cross-sectional alpha.

---

## 2. Why the Edge Could Exist

The relative strength edge exists due to three structural market inefficiencies:

1. **Information Asymmetry and Delayed Price Discovery**: Information does not diffuse instantly across all crypto assets. Major fundamental developments (e.g., mainnet upgrades, major partnerships, regulatory approvals) create localized value shifts that take days or weeks for the broader retail and institutional market to fully price in, creating persistent lead-lag effects.
2. **Behavioral Herding and Attention Scarcity**: Attention is a scarce commodity in retail-dominated markets. Retail traders exhibit strong feedback-loop behavior, gravitationally moving toward assets that are already displaying high relative strength (visible on exchange "top gainer" leaderboards, social media, and news outlets). This attention clustering drives self-reinforcing buying pressure that pushes prices beyond short-term equilibrium.
3. **Liquidity Rotation Trajectories**: Large institutional allocators or market makers cannot move size into low-liquidity altcoins instantly without market impact. Consequently, capital deployment is staged over days and weeks, creating sustained, directional buying pressure in selected assets while others remain stagnant.

---

## 3. Why the Edge May Persist

We expect this edge to persist due to the following structural properties of the crypto market:

* **Retail-Dominant Speculative Flow**: Unlike mature equity markets, cryptocurrency trading is heavily driven by retail sentiment, high leverage, and momentum-seeking behavior. These participants are structurally prone to chasing performance and calling tops prematurely (shorting strong assets), which fuels short-squeeze expansions.
* **Persistent Fundamental Dispersion**: The utility, adoption, regulatory risk, and tokenomics of the 25 assets in our universe are highly heterogeneous. Stable, cash-flow-generative, or high-adoption protocols will naturally exhibit stronger baseline support during market drawdowns than purely speculative assets, maintaining a structural cross-sectional spread.
* **Capital Constraints & Mandate Limits**: Quant funds, VCs, and index products have strict mandate constraints (e.g., rebalancing schedules, asset whitelists). The mechanical nature of these capital flows creates repeatable patterns in relative asset performance.

---

## 4. Expected Market Behaviour

* **Expansion Regimes (Bull Market)**: During broad market rallies, relative strength leaders will experience rapid, compounding price appreciation. The strategy should capture the "high-beta" tail of the asset distribution as liquidity rotates aggressively.
* **Contraction Regimes (Bear Market)**: During major downturns, relative strength leaders (often majors or assets with strong fundamental backstops) will decline significantly less than the broader altcoin market. By holding these relative outperformers (or moving flat if absolute thresholds are breached), the strategy minimizes capital drawdowns.
* **Regime Transitions**: Transitions from bull to bear (or vice-versa) will trigger shifts in cross-sectional leadership, leading to orderly rebalancing signals as capital moves to defensive assets.

---

## 5. Expected Weaknesses & Failure Modes

* **Correlation Convergence (Flash Crashes)**: During sudden, macro-driven deleveraging events (e.g., BTC flash crashes, liquidations of massive derivative positions), cross-sectional dispersion collapses. Asset correlations shift rapidly toward 1.0, and all assets sell off indiscriminately. In these scenarios, relative strength leaders offer no protection and may experience high drawdowns.
* **Mean-Reverting (Chop) Regimes**: In rangebound markets characterized by low volatility and lack of directional capital flow, leadership rotations are erratic and short-lived. The strategy will suffer from high transaction costs and slippage as it repeatedly buys assets at local tops only for them to mean-revert.
* **Speed of Rotation vs. Rebalance Frequency**: If the market rotates its leadership faster than the rebalancing frequency of the strategy (e.g., capital jumps from asset to asset every few hours while the strategy rebalances daily), the strategy will systematically lag the trend, buying the top of the rotated asset and missing the start of the next leader.
