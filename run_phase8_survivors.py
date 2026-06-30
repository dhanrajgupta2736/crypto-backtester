"""
Phase 8 Survivor Extraction
===========================
Filters results/coin_detailed_sweep.csv for configurations satisfying:
    - Profit Factor >= 1.5
    - Sharpe Ratio >= 1.0
    - Max Drawdown <= 35%
    - Trades >= 30
Generates:
    - results/survivor_configs.csv (all survivors sorted)
    - results/final_candidates.csv (top 20 survivors)
"""

import os
import pandas as pd

# CONFIG
RESULTS_DIR = "results"
DETAILED_SWEEP_PATH = os.path.join(RESULTS_DIR, "coin_detailed_sweep.csv")
SURVIVOR_CONFIGS_PATH = os.path.join(RESULTS_DIR, "survivor_configs.csv")
FINAL_CANDIDATES_PATH = os.path.join(RESULTS_DIR, "final_candidates.csv")

def main():
    print("=" * 80)
    print("  PHASE 8 - SURVIVOR EXTRACTION")
    print("=" * 80)

    if not os.path.exists(DETAILED_SWEEP_PATH):
        print(f"[FATAL] Cannot find {DETAILED_SWEEP_PATH}. Run Phase 7 first.")
        return

    # 1. Load Detailed Sweep results
    df = pd.read_csv(DETAILED_SWEEP_PATH)
    print(f"  Loaded {len(df)} total configuration runs from sweep.")

    # 2. Rename columns to match requested format
    df.rename(columns={"Params": "Parameters"}, inplace=True)

    # 3. Filter configurations
    # Criteria: PF >= 1.5, Sharpe >= 1.0, Max DD <= 35.0%, Trades >= 30
    mask = (
        (df["Profit Factor"] >= 1.5) &
        (df["Sharpe Ratio"] >= 1.0) &
        (df["Max Drawdown"] <= 35.0) &
        (df["Trades"] >= 30)
    )
    df_survivors = df.loc[mask].copy()
    print(f"  Found {len(df_survivors)} configurations matching the survivor criteria.")

    # Select requested columns
    cols_to_keep = [
        "Coin", "Strategy", "Parameters", "Profit Factor", 
        "Sharpe Ratio", "Max Drawdown", "Trades", "Win Rate", "Net Profit"
    ]
    df_survivors = df_survivors[cols_to_keep]

    # 4. Sort configurations
    # 1. Profit Factor (descending)
    # 2. Sharpe Ratio (descending)
    # 3. Max Drawdown (ascending)
    df_survivors.sort_values(
        by=["Profit Factor", "Sharpe Ratio", "Max Drawdown"],
        ascending=[False, False, True],
        inplace=True
    )
    df_survivors.reset_index(drop=True, inplace=True)

    # Save all survivors
    df_survivors.to_csv(SURVIVOR_CONFIGS_PATH, index=False)
    print(f"  Saved all {len(df_survivors)} survivors to {SURVIVOR_CONFIGS_PATH}")

    # 5. Extract top 20 candidates
    df_final = df_survivors.head(20).copy()
    df_final.reset_index(drop=True, inplace=True)
    df_final.to_csv(FINAL_CANDIDATES_PATH, index=False)
    print(f"  Saved top {len(df_final)} final candidates to {FINAL_CANDIDATES_PATH}")

    # 6. Display results
    print("\n" + "=" * 80)
    print("  FINAL TOP 20 CANDIDATES FOR PAPER TRADING")
    print("=" * 80)
    print(f"{'Rank':<4} | {'Coin':<5} | {'Strategy':<18} | {'PF':<6} | {'Sharpe':<6} | {'Max DD':<7} | {'Trades':<6} | {'Params':<30}")
    print("-" * 100)
    for i, (_, row) in enumerate(df_final.iterrows(), 1):
        print(f"[{i:>2}] | {row['Coin']:<5} | {row['Strategy']:<18} | {row['Profit Factor']:<6.2f} | {row['Sharpe Ratio']:<6.2f} | {row['Max Drawdown']:>5.2f}% | {int(row['Trades']):>6} | {row['Parameters']:<30}")
    print("-" * 100)

if __name__ == "__main__":
    main()
