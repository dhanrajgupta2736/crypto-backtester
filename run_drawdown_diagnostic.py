"""
Drawdown Diagnostic Report
==========================
Analyzes the walk-forward validation results to identify the source of
drawdown failures (Coin, Strategy, RR, or Timeframe).
"""

import os
import pandas as pd
import numpy as np

RESULTS_DIR = "results"
INPUT_CSV = os.path.join(RESULTS_DIR, "walk_forward_results_v2.csv")

# Thresholds used in Phase 4
MIN_PF = 1.3
MIN_SHARPE = 1.0
MAX_DD = 30.0
MIN_TRADES = 30

def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: {INPUT_CSV} not found.")
        return

    df = pd.read_csv(INPUT_CSV)
    
    # ---------------------------------------------------------
    # 1. DRAWDOWN ANALYSIS
    # ---------------------------------------------------------
    # Pivot the data to get Training, Validation, and Test drawdowns as columns
    dd_pivot = df.pivot_table(
        index=["Coin", "Strategy", "Timeframe", "RR Value", "Parameters"],
        columns="Period",
        values="Max Drawdown",
        aggfunc="first"
    ).reset_index()

    # Ensure all period columns exist
    for p in ["Training", "Validation", "Test"]:
        if p not in dd_pivot.columns:
            dd_pivot[p] = np.nan

    dd_pivot["Average Drawdown"] = dd_pivot[["Training", "Validation", "Test"]].mean(axis=1)
    dd_pivot["Worst Drawdown"] = dd_pivot[["Training", "Validation", "Test"]].max(axis=1)
    
    # Rename columns for output
    dd_pivot.rename(columns={
        "Training": "Training Drawdown",
        "Validation": "Validation Drawdown",
        "Test": "Test Drawdown"
    }, inplace=True)

    # Sort by Average Drawdown ascending
    dd_pivot.sort_values("Average Drawdown", ascending=True, inplace=True)
    
    # Drop Parameters column as per request to group by Coin, Strategy, Timeframe, RR
    # Wait, the prompt says "For every: Coin, Strategy, Timeframe, RR".
    # Since there might be multiple parameter sets per Strategy/RR combo, 
    # we should group by these 4 and average the results, or keep parameters.
    # The prompt specifically says "For every: Coin, Strategy, Timeframe, RR".
    # Let's aggregate at that level instead of the raw parameter level to give a high-level view.
    
    agg_df = df.groupby(["Coin", "Strategy", "Timeframe", "RR Value", "Period"])["Max Drawdown"].mean().reset_index()
    agg_pivot = agg_df.pivot_table(
        index=["Coin", "Strategy", "Timeframe", "RR Value"],
        columns="Period",
        values="Max Drawdown",
        aggfunc="mean"
    ).reset_index()
    
    for p in ["Training", "Validation", "Test"]:
        if p not in agg_pivot.columns:
            agg_pivot[p] = np.nan

    agg_pivot["Average Drawdown"] = agg_pivot[["Training", "Validation", "Test"]].mean(axis=1)
    # The prompt asks for "Worst Drawdown". We can take the max over the averages, or the max across all configs.
    # Let's take the max across the periods for that grouping.
    agg_pivot["Worst Drawdown"] = agg_pivot[["Training", "Validation", "Test"]].max(axis=1)
    
    agg_pivot.rename(columns={
        "Training": "Training Drawdown",
        "Validation": "Validation Drawdown",
        "Test": "Test Drawdown"
    }, inplace=True)

    # Reorder columns
    cols = ["Coin", "Strategy", "Timeframe", "RR Value", 
            "Average Drawdown", "Worst Drawdown", 
            "Training Drawdown", "Validation Drawdown", "Test Drawdown"]
    agg_pivot = agg_pivot[cols]
    agg_pivot.sort_values("Average Drawdown", ascending=True, inplace=True)
    
    out_dd = os.path.join(RESULTS_DIR, "drawdown_analysis.csv")
    agg_pivot.to_csv(out_dd, index=False)
    print(f"Saved {len(agg_pivot)} rows to {out_dd}")


    # ---------------------------------------------------------
    # 2. COIN STABILITY
    # ---------------------------------------------------------
    # Evaluate if each row passed the period-level criteria
    df["Passed"] = (
        (df["Profit Factor"] >= MIN_PF) &
        (df["Sharpe Ratio"] >= MIN_SHARPE) &
        (df["Max Drawdown"] <= MAX_DD) &
        (df["Trades"] >= MIN_TRADES)
    )

    coin_group = df.groupby("Coin")
    
    coin_stability = pd.DataFrame({
        "Average Profit Factor": coin_group["Profit Factor"].mean(),
        "Average Drawdown": coin_group["Max Drawdown"].mean(),
        "Average Sharpe": coin_group["Sharpe Ratio"].mean(),
        "Pass Rate": coin_group["Passed"].mean() * 100.0  # as percentage
    }).reset_index()

    # Sort by Pass Rate desc, Average Drawdown asc
    coin_stability.sort_values(by=["Pass Rate", "Average Drawdown"], ascending=[False, True], inplace=True)
    
    out_coin = os.path.join(RESULTS_DIR, "coin_stability.csv")
    coin_stability.to_csv(out_coin, index=False)
    print(f"Saved {len(coin_stability)} rows to {out_coin}")

    print("\n--- COIN STABILITY SUMMARY ---")
    for _, r in coin_stability.iterrows():
        print(f"{r['Coin']:4s} | Pass Rate: {r['Pass Rate']:5.1f}% | Avg DD: {r['Average Drawdown']:5.1f}% | Avg PF: {r['Average Profit Factor']:5.2f} | Avg Sharpe: {r['Average Sharpe']:5.2f}")


if __name__ == "__main__":
    main()
