# Strategy Specification: TAO Supertrend EMA200
**Version**: v1.0  
**Status**: Approved for Paper Trading / Pre-Live Validation  
**Target Market**: Hyperliquid Perpetual Swaps (Perps)  
**Target Asset**: TAO (Bittensor)  
**Base Timeframe**: 1H (Hourly Candles)  

---

## 1. Mathematical Definitions & Logic

### A. Core Indicators
1.  **Exponential Moving Average (EMA200)**:
    $$\text{EMA}_t = \text{Close}_t \times \left(\frac{2}{N+1}\right) + \text{EMA}_{t-1} \times \left(1 - \frac{2}{N+1}\right)$$
    where $N = 200$. Calculates on closed candles to determine trend regime.
    
2.  **Average True Range (ATR10)**:
    $$\text{TR}_t = \max \left( \text{High}_t - \text{Low}_t, \, |\text{High}_t - \text{Close}_{t-1}|, \, |\text{Low}_t - \text{Close}_{t-1}| \right)$$
    $$\text{ATR}_t = \frac{1}{10} \sum_{i=0}^{9} \text{TR}_{t-i}$$
    Used for band volatility sizing and stop distance.

### B. Supertrend Bands
For ATR Period $P = 10$ and Multiplier $M = 3.0$:
1.  **Basic Bands**:
    $$\text{Basic Upper}_t = \left(\frac{\text{High}_t + \text{Low}_t}{2}\right) + M \times \text{ATR}_t$$
    $$\text{Basic Lower}_t = \left(\frac{\text{High}_t + \text{Low}_t}{2}\right) - M \times \text{ATR}_t$$
    
2.  **Final Bands**:
    $$\text{Final Upper}_t = \begin{cases} 
      \text{Basic Upper}_t & \text{if } \text{Basic Upper}_t < \text{Final Upper}_{t-1} \text{ or } \text{Close}_{t-1} > \text{Final Upper}_{t-1} \\
      \text{Final Upper}_{t-1} & \text{otherwise}
    \end{cases}$$
    
    $$\text{Final Lower}_t = \begin{cases} 
      \text{Basic Lower}_t & \text{if } \text{Basic Lower}_t > \text{Final Lower}_{t-1} \text{ or } \text{Close}_{t-1} < \text{Final Lower}_{t-1} \\
      \text{Final Lower}_{t-1} & \text{otherwise}
    \end{cases}$$

3.  **Supertrend Direction (Uptrend / Downtrend)**:
    $$\text{Uptrend}_t = \begin{cases}
      \text{True} & \text{if } \text{Close}_t > \text{Final Upper}_{t-1} \\
      \text{False} & \text{if } \text{Close}_t < \text{Final Lower}_{t-1} \\
      \text{Uptrend}_{t-1} & \text{otherwise}
    \end{cases}$$

### C. Entry Rules
A trade signal is generated ONLY on the close of candle $t$, and executes at the open of candle $t+1$:
*   **Long Entry**: 
    $$\text{Long Signal}_t = \text{Uptrend}_t \land (\neg \text{Uptrend}_{t-1}) \land (\text{Close}_t > \text{EMA}_{200, t})$$
*   **Short Entry**:
    $$\text{Short Signal}_t = (\neg \text{Uptrend}_t) \land \text{Uptrend}_{t-1} \land (\text{Close}_t < \text{EMA}_{200, t})$$

### D. Exit Rules
*   **Stop Loss (SL)**: Set at the band boundary value of the entry candle:
    *   *Long Entry*: $\text{SL}_0 = \text{Final Lower}_t$
    *   *Short Entry*: $\text{SL}_0 = \text{Final Upper}_t$
*   **Take Profit (TP)**: Set at a fixed 1:3 Risk-to-Reward ratio based on stop distance:
    *   *Long Entry*: $\text{TP}_0 = \text{Entry} + 3.0 \times (\text{Entry} - \text{SL}_0)$
    *   *Short Entry*: $\text{TP}_0 = \text{Entry} - 3.0 \times (\text{SL}_0 - \text{Entry})$
*   **Indicator Exit**: Exit immediately if trend direction flips:
    *   *Exit Long*: $\text{Uptrend}_t = \text{False}$ (short flip)
    *   *Exit Short*: $\text{Uptrend}_t = \text{True}$ (long flip)

---

## 2. Risk & Position Management

*   **Risk Per Trade**: **2%** of account equity, dynamically compounded.
*   **Friction Sizing Formulation**:
    $$\text{Unit Risk} = \text{Stop Distance} + \text{Friction Cost}$$
    $$\text{Friction Cost} = \text{Entry Price} \times (\text{Entry Fee} + \text{Entry Slippage} + \text{Exit Fee} + \text{Exit Slippage})$$
    $$\text{Quantity (Qty)} = \frac{\text{Equity} \times 0.02}{\text{Unit Risk}}$$
*   **Maximum Leverage**: Capped at **5x leverage** ($5.0 \times \text{Equity}$). Position size is truncated if the required capital exceeds this threshold.
*   **Break-Even Rule**: When the trade reaches **1R profit** (unrealized PnL equals initial planned risk), the Stop Loss is immediately moved to the actual entry fill price.
*   **Maximum Open Positions**: Capped at **1 concurrent open position** on TAO.

---

## 3. Execution Assumptions

To simulate realistic market friction, the paper broker applies the following schedules:
*   **Taker Fee Rate**: **0.045%** (assumed on Market Entry, Stop Loss exits, and Indicator Exit flips).
*   **Maker Fee Rate**: **0.015%** (assumed on Take Profit limit order executions).
*   **Slippage Penalty**:
    *   *Taker Execution*: **0.02%** (entry price adjusted higher for longs/lower for shorts; stop and indicator exit prices adjusted unfavorably).
    *   *Maker Execution*: **0.00%** (Take Profit limit orders are filled exactly at the target price).
*   **Funding Rates**: Funding payments are assumed to net to zero in the historical baseline, but real-time paper engine updates execute based on the spot/perp index mark price updates.

---

## 4. Historical Validation Results (Phase 1–12 Summary)

The strategy was evaluated using a strict multi-stage quantitative pipeline:
1.  **In-Sample Backtest (2024)**: Validated core trend-following logic and parameter convergence.
2.  **Out-of-Sample Forward Test (2025)**: Validated that metrics did not collapse under unseen market regimes.
3.  **Monte Carlo Stress Testing**: Executed 10,000 randomized permutations of the trade ledger to confirm risk of ruin (30% and 50% drawdowns) remains under safe parameters for live deployment.
4.  **Market Regime Analysis**: Classified TAO's historical price actions into Bull (trending), Bear (trending), and Sideways (range-bound). Discovered counter-intuitive strategy robustness during range-bound consolidation phases due to survival of noise wicks under 3 ATR stop distances.

### Research Baseline Metrics (2026 YTD Benchmarks)
*   **Profit Factor (PF)**: 1.79
*   **Win Rate**: 40.74%
*   **Sharpe Ratio**: 1.96
*   **Maximum Drawdown**: 21.94%
*   **Losing Streak Statistics**: Max consecutive losses observed: 6.

---

## 5. Deployment & Safety Requirements

*   **WebSocket Heartbeat Monitoring**: The WebSocket client sends a `{"method": "ping"}` packet every 30 seconds. The process restarts the socket handler if a connection drop is detected.
*   **Automatic Restart Recovery**:
    *   Load state variables (`results/engine_state.json`) containing balance, positions, and streak logs.
    *   Query REST API `candleSnapshot` to download any candles missed during downtime.
    *   Run retroactive check to check if active position's SL, TP, or BE was breached during the downtime, executing exits chronologically.
*   **Daily Drawdown Circuit Breaker**: If the daily net loss exceeds **5.0%** of the starting UTC day equity, trading is paused immediately, any active position is liquidated via market exit, and new entries are blocked.
*   **Consecutive Losses Circuit Breaker**: If the strategy registers **5 consecutive losing trades**, the engine pauses trading, requiring a manual audit before restarting.
*   **Duplicate Signal Protection**: Tracks `last_signal_ts` in state files to prevent multiple entries on the same hourly candle.

---

## 6. Change Control

Any modification to this specification requires:
1.  **New Version Number**: Incrementing version (e.g. `v1.1` or `v2.0`).
2.  **New Backtest**: Full simulation on historical TAO database.
3.  **New Validation Cycle**: Validation tests and validation reports verifying no performance degradation before deployment to paper/live production environments.
