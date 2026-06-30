"""
Phase 11 Stress Testing
=======================
Uses the complete trade history from results/paper_trade_log.csv (TAO Supertrend EMA200).
Performs:
    1. Monte Carlo Analysis (10,000 runs, bootstrap with replacement)
    2. Consecutive Loss Analysis (historical, expected, and simulated worst)
    3. Risk of Ruin Analysis for 1%, 2%, 5%, and 10% risk per trade
Generates:
    - results/monte_carlo.csv
    - results/risk_of_ruin.csv
    - results/losing_streak_analysis.csv
"""

import os
import time
import numpy as np
import pandas as pd

# CONFIG
RESULTS_DIR = "results"
PAPER_LOG_PATH = os.path.join(RESULTS_DIR, "paper_trades.csv")
OLD_PAPER_LOG_PATH = os.path.join(RESULTS_DIR, "paper_trade_log.csv")
MONTE_CARLO_PATH = os.path.join(RESULTS_DIR, "monte_carlo.csv")
RISK_OF_RUIN_PATH = os.path.join(RESULTS_DIR, "risk_of_ruin.csv")
LOSING_STREAK_PATH = os.path.join(RESULTS_DIR, "losing_streak_analysis.csv")

INITIAL_BALANCE = 1000.0
RUIN_THRESHOLD  = 100.0  # 90% drawdown / drop below $100
SIMULATIONS     = 10000

RISK_LEVELS = [1.0, 2.0, 5.0, 10.0]  # Risk per trade %

# ─────────────────────────── CONSECUTIVE LOSS FUNCTION ─────────────────────────
def get_longest_losing_streak(pnls):
    max_streak = 0
    current_streak = 0
    for p in pnls:
        if p <= 0:
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0
    return max_streak

# ─────────────────────────── MAIN ──────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 80)
    print("  PHASE 11 - RISK STRESS TESTING (TAO SUPERTREND EMA200)")
    print("=" * 80)

    log_path = PAPER_LOG_PATH
    if not os.path.exists(log_path):
        log_path = OLD_PAPER_LOG_PATH
        
    if not os.path.exists(log_path):
        print(f"[FATAL] Cannot find {PAPER_LOG_PATH} or {OLD_PAPER_LOG_PATH}. Run Phase 10 first.")
        return

    # 1. Load trade history
    df_trades = pd.read_csv(log_path)
    total_trades = len(df_trades)
    print(f"  Loaded {total_trades} historical trades from {log_path}.")


    # Extract PnLs and R-multiples with fallback to old column names
    if "pnl" in df_trades.columns:
        pnls = df_trades["pnl"].values
    elif "Trade PnL" in df_trades.columns:
        pnls = df_trades["Trade PnL"].values
    else:
        raise KeyError("Could not find PnL column in trade log.")

    if "r_multiple" in df_trades.columns:
        r_multiples = df_trades["r_multiple"].values
    else:
        r_multiples = pnls / 100.0


    # 2. Consecutive Loss Analysis
    hist_streak = get_longest_losing_streak(pnls)
    
    # Shuffle sequences to find expected and worst streaks
    shuffled_streaks = []
    np.random.seed(42)
    for _ in range(SIMULATIONS):
        shuffled = np.random.permutation(pnls)
        shuffled_streaks.append(get_longest_losing_streak(shuffled))
        
    expected_streak = np.mean(shuffled_streaks)
    worst_sim_streak = np.max(shuffled_streaks)
    
    wins = np.sum(pnls > 0)
    losses = np.sum(pnls <= 0)
    win_rate = (wins / total_trades) * 100
    loss_rate = (losses / total_trades) * 100

    df_streak = pd.DataFrame([{
        "Win Rate %": round(win_rate, 2),
        "Loss Rate %": round(loss_rate, 2),
        "Historical Longest Losing Streak": hist_streak,
        "Expected Longest Losing Streak (Shuffle Mean)": round(expected_streak, 2),
        "Worst Simulated Losing Streak (Shuffle Max)": worst_sim_streak
    }])
    df_streak.to_csv(LOSING_STREAK_PATH, index=False)
    print(f"  Saved losing streak analysis -> {LOSING_STREAK_PATH}")

    # 3. Monte Carlo & Risk of Ruin Analysis
    ruin_results = []
    percentile_rows = []

    for risk in RISK_LEVELS:
        final_balances = []
        max_drawdowns = []
        ruined_count = 0
        dd_30_count = 0
        dd_50_count = 0

        # Run 10,000 simulations
        for _ in range(SIMULATIONS):
            # Bootstrap trades with replacement
            drawn_indices = np.random.randint(0, total_trades, size=total_trades)
            drawn_r = r_multiples[drawn_indices]

            balance = INITIAL_BALANCE
            equity_curve = [balance]
            is_ruined = False

            for r in drawn_r:
                if is_ruined:
                    equity_curve.append(balance)
                    continue

                # Position size is sized relative to current balance B
                # Return PnL = B * Risk% * R_multiple
                pct_return = r * (risk / 100.0)
                balance = max(0.0, balance * (1.0 + pct_return))
                equity_curve.append(balance)

                # Check ruin
                if balance <= RUIN_THRESHOLD:
                    is_ruined = True
                    ruined_count += 1
                    balance = RUIN_THRESHOLD

            final_balances.append(balance)

            # Drawdown check
            eq = pd.Series(equity_curve)
            cummax = eq.cummax()
            dd = (eq - cummax) / cummax.replace(0, 1e-9) * -100
            m_dd = float(dd.max())
            max_drawdowns.append(m_dd)

            if m_dd >= 30.0:
                dd_30_count += 1
            if m_dd >= 50.0:
                dd_50_count += 1

        final_balances = np.array(final_balances)
        max_drawdowns = np.array(max_drawdowns)

        # Probabilities
        prob_ruin = (ruined_count / SIMULATIONS) * 100
        prob_dd30 = (dd_30_count / SIMULATIONS) * 100
        prob_dd50 = (dd_50_count / SIMULATIONS) * 100

        avg_final = np.mean(final_balances)
        med_final = np.median(final_balances)

        ruin_results.append({
            "Risk Per Trade %": f"{risk}%",
            "Probability of 30% DD %": round(prob_dd30, 2),
            "Probability of 50% DD %": round(prob_dd50, 2),
            "Probability of Ruin %": round(prob_ruin, 2),
            "Expected Final Balance $": round(avg_final, 2),
            "Median Final Balance $": round(med_final, 2)
        })

        # Track percentiles for monte_carlo.csv
        p_pcts = [10, 25, 50, 75, 90]
        for p in p_pcts:
            percentile_rows.append({
                "Risk Per Trade": f"{risk}%",
                "Metric": "Final Balance",
                "Percentile": f"{p}th",
                "Value": round(np.percentile(final_balances, p), 2)
            })
            percentile_rows.append({
                "Risk Per Trade": f"{risk}%",
                "Metric": "Max Drawdown",
                "Percentile": f"{p}th",
                "Value": round(np.percentile(max_drawdowns, p), 2)
            })

    # Save outputs
    df_ruin = pd.DataFrame(ruin_results)
    df_ruin.to_csv(RISK_OF_RUIN_PATH, index=False)
    print(f"  Saved risk of ruin results -> {RISK_OF_RUIN_PATH}")

    df_percentiles = pd.DataFrame(percentile_rows)
    df_percentiles.to_csv(MONTE_CARLO_PATH, index=False)
    print(f"  Saved Monte Carlo percentiles -> {MONTE_CARLO_PATH}")

    # Determine Safe Risk Recommendation
    # Recommendation criteria: Ruin probability = 0.0% and DD 30% probability < 15%
    safe_risk = "1%"
    for row in ruin_results:
        risk_val = row["Risk Per Trade %"]
        p_ruin = row["Probability of Ruin %"]
        p_dd30 = row["Probability of 30% DD %"]
        if p_ruin == 0.0 and p_dd30 <= 15.0:
            safe_risk = risk_val

    # Print summary
    print("\n" + "=" * 80)
    print("  CONSECUTIVE LOSS ANALYSIS SUMMARY")
    print("=" * 80)
    print(f"  Win Rate: {win_rate:.2f}% | Loss Rate: {loss_rate:.2f}%")
    print(f"  Longest Historical Losing Streak:          {hist_streak} losses")
    print(f"  Expected Longest Losing Streak (Average):  {expected_streak:.2f} losses")
    print(f"  Worst Simulated Losing Streak:            {worst_sim_streak} losses")

    print("\n" + "=" * 80)
    print("  RISK OF RUIN & DRAWDOWN PROBABILITIES")
    print("=" * 80)
    print(f"{'Risk %':<8} | {'Prob 30% DD':<12} | {'Prob 50% DD':<12} | {'Prob Ruin':<10} | {'Expected Balance':<18} | {'Median Balance':<15}")
    print("-" * 88)
    for _, row in df_ruin.iterrows():
        print(f"{row['Risk Per Trade %']:<8} | {row['Probability of 30% DD %']:>10.2f}% | {row['Probability of 50% DD %']:>10.2f}% | {row['Probability of Ruin %']:>8.2f}% | ${row['Expected Final Balance $']:>16.2f} | ${row['Median Final Balance $']:>13.2f}")
    print("-" * 88)
    print(f"\n  [RECOMMENDATION] Safe Risk Per Trade for live deployment: {safe_risk}")
    print(f"  *Criteria: Ruin probability = 0% and Probability of 30% drawdown <= 15%.")

    elapsed = time.time() - t0
    print(f"\n  Completed stress testing in {elapsed:.1f}s")

if __name__ == "__main__":
    main()
