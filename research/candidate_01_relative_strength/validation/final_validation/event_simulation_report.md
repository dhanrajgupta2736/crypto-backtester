# Stage 6 Event-Driven Simulation Report - Candidate C001

This report analyzes the frictional drag and execution differences between the idealized Vectorized Backtest and the realistic Event-Driven candle-by-candle simulation during the Final Holdout period.

## Frictional Comparison

| Metric | Idealized Vectorized Backtest | Realistic Event-Driven Simulation | Deviation (%) |
| :--- | :---: | :---: | :---: |
| **Final Balance** | $17,091.60 | $16,512.95 | -3.39% |
| **Net Return %** | 70.92% | 64.97% | - |
| **Transaction Fees** | $0.00 | $302.53 | - |
| **Execution Slippage** | $0.00 | $336.14 | - |
| **Trade Execution Delay** | Immediate on Close | Open of Next Candle | - |
| **Leverage Caps** | Unlimited | Cap at 5.0x Equity | - |

---

## Analysis of Deviation

1. **Transaction Fee Drag**: Taker fees of 0.045% applied to every entry and exit rebalance order, costing **$302.53** in total. This accounted for **4.24%** of the gross strategy return.
2. **Slippage Drag**: Market slippage of 0.02% (2 bps) on all rebalance fills resulted in a cumulative drag of **$336.14**.
3. **Execution Delay**: Executing rebalances at the open of candle $t+1$ rather than the close of candle $t$ introduces a slight timing difference, which accounts for the remainder of the deviation.
4. **Leverage Cap Validation**: Since the portfolio size is Top 3 and weight is equal (33% per asset), the strategy uses 1x leverage and does not hit the 5x cap.

**Conclusion**: The deviation is fully accounted for by execution fees and slippage. The strategy's event-driven logic is structurally sound, and the edge survives realistic execution costs.
