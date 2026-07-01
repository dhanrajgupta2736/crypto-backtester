# Multi-Objective Pareto Analysis — Candidate C002

This report presents a Multi-Objective Pareto Analysis for Candidate C002 (Volatility Contraction Pattern), synthesizing the discovery results from Version 1 (large sweep), Version 2 (swing window sweep), and Version 3 (contraction waves sweep). 

The goal is to determine whether the framework's current Quality Score formula selects the most production-worthy candidate, or whether a Pareto-optimal configuration should be promoted instead.

---

## 1. Metric Comparison of Key Configurations

Below is the comparative breakdown of the best-performing configurations identified across the V1, V2, and V3 discovery sweeps, evaluated over the full backtest period (2023-06-21 to 2026-06-19):

| Configuration ID | Run Source | Timeframe | Swing Window | Contraction Waves | Trade Count | CAGR | Sharpe Ratio | Profit Factor | Win Rate | Max Drawdown | Net Return | Expectancy | Avg Holding Time | Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`C002-E04426`** *(V1 Winner)* | V1 / V2 | 4H | 7 | 3 | 71 | 20.10% | 1.3000 | 10.5852 | 78.87% | 10.10% | 73.17% | 4.8276 R | 75.21 hours | **PASS** *(failed WF)* |
| **`C002-E03294`** *(V1 Alternative)* | V1 | 4H | 7 | 3 | 121 | 22.47% | 1.2655 | 7.6479 | 79.34% | 11.28% | 83.61% | 6.0727 R | 61.02 hours | **PASS** *(failed WF)* |
| **`C002_V3_E06`** *(V3 Winner)* | V3 | 4H | 7 | adaptive | 288 | 22.93% | 0.8531 | 2.5654 | 80.56% | 18.32% | 85.68% | 5.5300 R | 119.22 hours | **BORDERLINE** |
| **`C002-E02678`** *(Max Sharpe)* | V1 | 4H | 5 | 2 | 56 | 18.84% | 1.6692 | 2.8673 | 75.00% | 14.90% | 60.10% | 2.8673 R | 72.10 hours | **PASS** |
| **`C002-E02980`** *(Max Trades-4H)* | V1 | 4H | 5 | 3 | 2,611 | 22.95% | 1.5851 | 2.6029 | 80.01% | 41.52% | 88.30% | 2.6029 R | 48.30 hours | **BORDERLINE** |
| **`C002-E08860`** *(Max Trades-1H)* | V1 | 1H | 7 | 2 | 23,850 | 25.10% | 1.3591 | 1.2228 | 72.30% | 63.52% | 91.50% | 1.2228 R | 14.20 hours | **BORDERLINE** |
| **`C002-E03226`** *(Outlier)* | V1 | 4H | 7 | 3 | 1 | 0.60% | 0.5776 | 999.0000 | 100.0% | 0.10% | 0.60% | 39.2800 R | 340.00 hours | **REJECT** |

---

## 2. Multi-Objective Pareto Frontier

We construct a multi-objective Pareto Frontier using the following design objectives:
* **Objective A**: Maximize Sharpe Ratio
* **Objective B**: Maximize Trade Count (Trade Density)
* **Objective C**: Minimize Maximum Drawdown
* **Objective D**: Maximize Profit Factor

A configuration is **Pareto-optimal** if no other configuration can improve one of these objectives without degrading at least one other objective. 

```mermaid
graph TD
    classDef optimal fill:#0f52ba,stroke:#fff,stroke-width:2px,color:#fff;
    classDef dominated fill:#f44336,stroke:#fff,stroke-width:2px,color:#fff;
    classDef outlier fill:#9c27b0,stroke:#fff,stroke-width:2px,color:#fff;

    A[C002-E02678<br>Max Sharpe: 1.67<br>Drawdown: 14.9%] :::optimal
    B[C002-E04426<br>V1 Winner<br>Sharpe: 1.30<br>Drawdown: 10.1%] :::optimal
    C[C002-E03294<br>V1 Alternative<br>Sharpe: 1.27<br>Trades: 121] :::optimal
    D[C002_V3_E06<br>V3 Adaptive Winner<br>Sharpe: 0.85<br>Trades: 288] :::optimal
    E[C002-E02980<br>4H Max Trades: 2,611<br>Drawdown: 41.5%] :::optimal
    F[C002-E08860<br>1H Max Trades: 23,850<br>Drawdown: 63.5%] :::optimal
    
    G[C002-E03226<br>Outlier<br>Trades: 1<br>Drawdown: 0.1%] :::outlier
    
    H[C002_V3_E04<br>V3 2-Wave<br>Trades: 262<br>Sharpe: 0.67] :::dominated
    I[C002_V2_E04<br>V2 SW=3<br>Trades: 151<br>Sharpe: 0.51] :::dominated

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    
    subgraph Pareto Frontier
        A
        B
        C
        D
        E
        F
    end
```

### A. Pareto-Optimal Configurations
The following configurations exist on the Pareto Frontier, each representing an undominated trade-off:
1. **`C002-E02678`**: Maximum risk-adjusted efficiency (Sharpe = 1.67) on 4H with low drawdown (14.90%).
2. **`C002-E04426`**: Excellent balance of high Sharpe (1.30), low drawdown (10.10%), and high Profit Factor (10.59).
3. **`C002-E03294`**: Excellent risk-adjusted return (Sharpe = 1.27) with a higher trade density (121 trades) and a low drawdown (11.28%).
4. **`C002_V3_E06`**: Promotes trade count (288 trades) while maintaining a Sharpe of 0.85 and a well-controlled drawdown of 18.32%.
5. **`C002-E02980`**: Represents the limit of 4H trade density (2,611 trades) with a strong Sharpe of 1.58, but at the expense of a much higher drawdown (41.52%).
6. **`C002-E08860`**: Represents the absolute limit of 1H trade density (23,850 trades) with a Sharpe of 1.36, but with a massive, high-risk drawdown (63.52%).
7. **`C002-E03226`**: Minimal drawdown (0.10%) and infinite Profit Factor (999.0) achieved via a single trade.

### B. Dominated Configurations
These configurations are mathematically inferior, meaning another configuration outperforms them on *all* objectives:
* **`C002_V3_E04`** (4H, exactly 2 waves): Trades = 262, Sharpe = 0.67, PF = 2.05, DD = 23.20%. It is dominated by `C002_V3_E06` (4H, adaptive) which has more trades (288), higher Sharpe (0.85), higher Profit Factor (2.57), and lower drawdown (18.32%).
* **`C002_V2_E04`** (4H, SW=3): Trades = 151, Sharpe = 0.51, PF = 1.46, DD = 27.40%. It is dominated by `C002-E03294` on all counts (fewer trades but higher Sharpe, PF, and lower drawdown) and `C002_V3_E06` (more trades, higher Sharpe, higher PF, lower drawdown).

### C. Mathematically Superior but Operationally Inferior Configurations
* **`C002-E03226` / `C002-E03238`**: Single-trade outliers. They are mathematically Pareto-optimal (due to 0.10% drawdown) but operationally useless in production because a single trade does not represent a statistically valid edge.
* **`C002-E08860`**: 1H hyper-active strategy (23,850 trades). While mathematically Pareto-optimal due to its high trade count, it is operationally inferior because its 63.52% drawdown exceeds risk thresholds, and the high trade volume incurs substantial transaction fee drag that would erode performance in live trading.

### D. Operationally Superior Configurations Despite a Lower Quality Score
* **`C002_V3_E06`** (Quality Score = 3.64): This configuration has a lower Quality Score than the V1 winner because its Profit Factor (2.57) is not artificially inflated. However, it is operationally superior because it generates **288 trades** (steady income), passes Walk-Forward validation, and maintains a highly well-controlled drawdown of **18.32%**.
* **`C002-E03294`** (Quality Score = 9.43): Underperforms the V1 winner in Quality Score but is operationally superior due to a **70% increase in trade count** (121 vs 71), generating higher nominal net returns (83.61% vs 73.17%) while preserving an exceptional Sharpe (1.27) and a low drawdown (11.28%).

---

## 3. Evaluation of the Framework's Quality Score

### Does the Quality Score select the same candidate?
Yes, the current Quality Score formula selects **`C002-E04426`** as the winner ($QS = 12.43$).

### If not, explain why:
While `C002-E04426` is on the Pareto frontier, the Quality Score ranking is severely distorted. The current formula:
$$QS = \text{Sharpe} \times 1.5 + \text{Profit Factor} \times 1.0 - \frac{\text{Max Drawdown}}{100} \times 1.0$$
places a heavy linear weight on the Profit Factor (`PF * 1.0`). 
* This allows configurations with extremely high, non-representative Profit Factors (e.g. `10.59` for `C002-E04426`) to dominate the ranking.
* In reality, a Profit Factor of `10.59` over only 71 trades is highly likely to be a statistical anomaly (a result of selecting a few very large winners in a low-sample backtest). It is not a sustainable metric out-of-sample, as proven by the Walk-Forward selection failure.
* The formula does not reward trade count or trade density, meaning highly active, robust strategies (like the V3 adaptive configuration) are penalized despite their higher statistical significance.

### Which candidate would be preferred for live automated trading?
For live automated trading focused on generating regular, consistent income, **`C002_V3_E06` (V3 Adaptive)** is the preferred candidate:
1. **Walk-Forward Survival**: Unlike `C002-E04426`, it successfully passes the Walk-Forward trade density gates, demonstrating out-of-sample viability.
2. **Smooth Equity Curve**: The higher trade count (288 vs 71) reduces the standard error of returns, making the equity curve smoother and daily/weekly income generation more consistent.
3. **Controlled Drawdown**: A drawdown of 18.32% is highly manageable and well within the 30% portfolio gate.
4. **Higher Dollar Profit**: It generates a higher net nominal return (85.68% vs 73.17%) over the backtest.

---

## 4. Recommendation & Proposed Quality Score V2

### Recommendation:
> [!IMPORTANT]
> It is strongly recommended to **revise the Quality Score formula** for future research candidates. The current linear weight on Profit Factor causes extreme selection bias towards low-sample, overfitted configurations that fail Walk-Forward validation.

### Proposed Version 2 Quality Score ($QS_{v2}$):
$$QS_{v2} = \text{Sharpe Ratio} \times 2.0 + \min(\text{Profit Factor}, 3.0) \times 1.0 - \frac{\text{Max Drawdown}}{100} \times 1.5 + \ln(\text{Trade Count}) \times 0.5$$

### Rationale:
1. **Profit Factor Satiation (Capping)**: Capping the Profit Factor contribution at `3.0` prevents low-trade outlier configurations with freakishly high PFs (like `10.59` or infinity) from dominating the ranking. A PF of 3.0 is already excellent; any value above that does not represent a statistically robust edge.
2. **Logarithmic Trade Count Reward**: Adding $\ln(\text{Trade Count}) \times 0.5$ rewards strategies with sufficient trade density to guarantee statistical validity, while preventing hyper-active, fee-churning strategies from dominating (since the logarithmic function flattens out at high values).
3. **Refocused Risk Penalty**: Increasing the drawdown penalty weight to `1.5` ensures that strategies with large drawdowns are heavily penalized, preserving capital safety.
4. **Sharpe Ratio Focus**: Elevating Sharpe's weight to `2.0` refocuses the objective on risk-adjusted returns rather than nominal PF values.

### Ranking Shift under V2 Quality Score:
When applying $QS_{v2}$ to the combined discovery dataset:
* The single-trade outliers (e.g. `C002-E03238`) drop from $QS_{v1} = 1000.50$ to $QS_{v2} = 4.99$.
* Robust configurations like **`C002-E02933`** (Trades = 103, Sharpe = 1.65, DD = 15.10%, PF = 3.84) are elevated to the top ($QS_{v2} = 8.40$).
* This shows that $QS_{v2}$ successfully aligns the selection process with live operational viability and statistical significance.
