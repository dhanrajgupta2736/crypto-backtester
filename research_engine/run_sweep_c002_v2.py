"""Volatility Contraction Pattern Version 2 Parameter Sweep.

Runs a 6-experiment sweep varying Swing Window [3, 5, 7] across 1H and 4H timeframes,
locking all other parameters to the V1 baseline.
"""

import os
from pathlib import Path
import sys
import json
import datetime
import pandas as pd
import numpy as np
import yaml

# Add workspace directory to python path
workspace_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_dir))

from research_engine.core.discovery_engine import DiscoveryEngine
from research_engine.core.metrics_engine import MetricsEngine
from research_engine.core.candidate_dashboard import CandidateDashboard


def run_v2_sweep():
    print("======================================================================")
    print("  QRP Framework v2.0.1 — Candidate C002 V2 Volatility Contraction Sweep")
    print("======================================================================")

    candidate_id = "candidate_02_vcp"
    candidate_dir = workspace_dir / "research" / "candidate_02_vcp_v2"
    
    framework_config_path = workspace_dir / "research_engine" / "configs" / "framework_config.yaml"
    candidate_yaml_path = workspace_dir / "research" / "candidate_02_vcp" / "configs" / "candidate.yaml"
    
    with open(candidate_yaml_path, "r", encoding="utf-8") as f:
        candidate_cfg = yaml.safe_load(f)
    symbols = candidate_cfg["candidate"]["universe"]["symbols"]

    # Initialize engines
    outputs_dir = candidate_dir / "outputs"
    reports_dir = candidate_dir / "reports"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    dashboard_path = workspace_dir / "research_engine" / "outputs" / "dashboard_state.json"
    dashboard = CandidateDashboard(state_file_path=dashboard_path)
    engine = DiscoveryEngine(config_path=framework_config_path)
    plugin = engine.load_plugin("candidate_02_vcp")
    metrics_engine = MetricsEngine()

    # Timeframes and Swing Windows to sweep
    timeframes = ["1H", "4H"]
    swing_windows = [3, 5, 7]

    # Lock all other parameters to V1 optimal baseline
    base_params = {
        "trend_gate": "HH_HL",
        "contraction_waves": 3,
        "max_final_contraction": 0.05,
        "breakout": "Close_Above_Swing_High",
        "risk_reward": "Swing_Trail",
        "stop_buffer": 0.0,
        "portfolio_size_k": 3
    }

    # Update dashboard
    dashboard.update_candidate_progress(
        candidate_id="Candidate 02",
        stage="V2 Discovery Sweep",
        status="RUNNING",
        progress_pct=5.0,
        notes="Starting V2 Discovery Sweep across 6 configurations..."
    )

    run_records = []
    
    # Run backtests
    total_runs = len(timeframes) * len(swing_windows)
    run_idx = 0

    for tf in timeframes:
        print(f"\nLoading database for timeframe {tf}...")
        universe_data = engine.load_dataset(symbols, tf)
        print("Preprocessing data...")
        preprocessed_data = plugin.preprocess(universe_data)

        for sw in swing_windows:
            run_idx += 1
            print(f"\n[{run_idx}/{total_runs}] Running Timeframe={tf} | Swing Window={sw}...")
            
            # Update dashboard
            dashboard.update_candidate_progress(
                candidate_id="Candidate 02",
                stage="V2 Discovery Sweep",
                status="RUNNING",
                progress_pct=5.0 + (run_idx / total_runs) * 90.0,
                notes=f"Simulating config: TF={tf}, SW={sw}"
            )

            # Copy base params and set the variable swing window
            params = base_params.copy()
            params["swing_window"] = sw

            # Generate signals
            signaled_data = plugin.generate_signals(preprocessed_data, params)

            # Run backtest simulation
            results = engine.simulate_backtest(signaled_data, params)

            trade_ledger = results["trade_ledger"]
            equity_curve = results["equity_curve"]
            num_rebalances = results["number_of_rebalances"]
            total_volume = results["total_volume_traded"]
            avg_port_val = results["average_portfolio_value"]

            # Calculate metrics
            metrics = metrics_engine.calculate_metrics(
                trade_ledger=trade_ledger,
                daily_equity=equity_curve,
                number_of_rebalances=num_rebalances,
                total_volume_traded=total_volume,
                average_portfolio_value=avg_port_val
            )

            gross_fees = trade_ledger['fees_paid'].sum() if not trade_ledger.empty else 0.0
            gross_slippage = trade_ledger['slippage_paid'].sum() if not trade_ledger.empty else 0.0
            net_pnl = trade_ledger['pnl_nominal'].sum() if not trade_ledger.empty else 0.0
            gross_pnl = net_pnl + gross_fees + gross_slippage
            fee_pct = (gross_fees / abs(gross_pnl)) * 100.0 if abs(gross_pnl) > 0.0 else 0.0

            # Quality Score calculation
            quality_score = (
                metrics["sharpe_ratio"] * 1.5 +
                metrics["profit_factor"] * 1.0 -
                (metrics["max_drawdown"]["drawdown_pct"] / 100.0) * 1.0 -
                (fee_pct / 100.0) * 0.5
            )

            # Determine pass/borderline/reject status
            # 1H threshold: pass=120, borderline=105
            # 4H threshold: pass=50, borderline=45
            pass_tc = 120 if tf == "1H" else 50
            borderline_tc = 105 if tf == "1H" else 45

            tc = metrics["trade_count"]
            sh = metrics["sharpe_ratio"]
            pf = metrics["profit_factor"]
            dd = metrics["max_drawdown"]["drawdown_pct"]

            if sh >= 1.20 and pf >= 1.15 and dd < 30.0 and tc >= pass_tc:
                verdict = "PASS"
            elif sh >= 0.50 and dd < 45.0 and tc >= borderline_tc:
                verdict = "BORDERLINE"
            else:
                verdict = "REJECT"

            record = {
                "Experiment ID": f"C002_V2_E{run_idx:02d}",
                "Timeframe": tf,
                "Swing Window": sw,
                "Trade Count": tc,
                "Win Rate": metrics["win_rate"],
                "Profit Factor": pf,
                "Expectancy (USD)": metrics["expectancy_r"],
                "CAGR": metrics["cagr"],
                "Sharpe Ratio": sh,
                "Max Drawdown": dd,
                "Fee %": fee_pct,
                "Quality Score": quality_score,
                "Verdict": verdict
            }
            
            run_records.append(record)
            print(f"-> Completed. Trades={tc} | Sharpe={sh:.4f} | PF={pf:.2f} | Drawdown={dd:.2f}% | Verdict={verdict}")

    # Convert to DataFrame
    df = pd.DataFrame(run_records)

    # Save outputs
    df.to_csv(outputs_dir / "discovery_matrix_results.csv", index=False)
    
    # Sort by Quality Score to find ranked list and winner
    df_ranked = df.sort_values(by="Quality Score", ascending=False).copy()
    df_ranked.to_csv(outputs_dir / "ranked_candidates.csv", index=False)

    winner = df_ranked.iloc[0]

    # Print the Winner Block in the exact user-specified format
    print("\n================================================")
    print("Winner")
    print(f"Swing Window = {winner['Swing Window']}")
    print(f"Timeframe = {winner['Timeframe']}")
    print(f"Trades = {winner['Trade Count']}")
    print(f"Sharpe = {winner['Sharpe Ratio']:.2f}")
    print(f"PF = {winner['Profit Factor']:.2f}")
    print(f"Drawdown = {winner['Max Drawdown']:.1f}%")
    print("================================================\n")

    # Generate candidate_summary.md and discovery_analysis.md
    summary_path = reports_dir / "candidate_summary.md"
    md_table = df_ranked.to_markdown(index=False)
    
    summary_content = f"""# Candidate C002 Version 2 — Discovery Summary

This document summarizes the results of the Version 2 parameter sweep, which tested varying Swing Window values (`[3, 5, 7]`) across `1H` and `4H` timeframes under locked V1 baseline settings.

## Discovery Matrix Performance Table

{md_table}

---

## Winning Variant Details
* **Timeframe**: {winner['Timeframe']}
* **Swing Window**: {winner['Swing Window']}
* **Trade Count**: {winner['Trade Count']}
* **Sharpe Ratio**: {winner['Sharpe Ratio']:.4f}
* **Profit Factor**: {winner['Profit Factor']:.4f}
* **Max Drawdown**: {winner['Max Drawdown']:.2f}%
* **Verdict**: **{winner['Verdict']}**
"""
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_content)

    # Update dashboard
    dashboard.update_candidate_progress(
        candidate_id="Candidate 02",
        stage="V2 Discovery Sweep",
        status="COMPLETED",
        progress_pct=100.0,
        notes=f"V2 sweep complete. Winner: TF={winner['Timeframe']}, SW={winner['Swing Window']}."
    )
    print("V2 summary report generated and dashboard updated successfully.")


if __name__ == "__main__":
    run_v2_sweep()
