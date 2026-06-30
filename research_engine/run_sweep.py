"""Discovery Sweep Matrix Runner.

Executes 81 backtesting experiments across multiple timeframes, lookbacks,
portfolio sizes, and frequencies, logging metrics and compiling reports.
"""

import os
from pathlib import Path
import sys
import datetime
import itertools
import pandas as pd
import numpy as np
import yaml

# Add workspace directory to python path
workspace_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_dir))

from research_engine.core.discovery_engine import DiscoveryEngine
from research_engine.core.experiment_manager import ExperimentManager
from research_engine.core.metrics_engine import MetricsEngine
from research_engine.core.reporting import ReportingEngine
from research_engine.core.logger import CustomLogger
from research_engine.core.experiment_registry import ExperimentRegistry
from research_engine.core.candidate_dashboard import CandidateDashboard


from concurrent.futures import ProcessPoolExecutor, as_completed

def run_single_backtest_worker(combo_info):
    tf, lookback, k, r, preprocessed_data, symbols, framework_config_path, candidate_id = combo_info
    import sys
    from pathlib import Path
    workspace_dir = Path(__file__).resolve().parent.parent
    if str(workspace_dir) not in sys.path:
        sys.path.insert(0, str(workspace_dir))

    from research_engine.core.discovery_engine import DiscoveryEngine
    from research_engine.core.metrics_engine import MetricsEngine
    import pandas as pd
    import numpy as np

    engine = DiscoveryEngine(config_path=framework_config_path)
    plugin = engine.load_plugin(candidate_id)
    metrics_engine = MetricsEngine()

    params = {
        "lookback_window": lookback,
        "portfolio_size_k": k,
        "rebalance_frequency_r": r
    }

    signaled_data = plugin.generate_signals(preprocessed_data, params)
    results = engine.simulate_backtest(signaled_data, params)

    trade_ledger = results["trade_ledger"]
    equity_curve = results["equity_curve"]
    num_rebalances = results["number_of_rebalances"]
    total_volume = results["total_volume_traded"]
    avg_port_val = results["average_portfolio_value"]

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

    avg_overlap = 0.0
    if not trade_ledger.empty and len(trade_ledger) > 1:
        try:
            holdings_dict = {}
            for _, row in trade_ledger.iterrows():
                entry = pd.to_datetime(row['entry_timestamp'])
                exit = pd.to_datetime(row['exit_timestamp'])
                symbol = row['asset']
                freq_code = '15min' if tf == '15m' else ('4h' if tf == '4H' else '1h')
                dr = pd.date_range(entry.round(freq_code), exit.round(freq_code), freq=freq_code)
                for dt in dr:
                    if dt not in holdings_dict:
                        holdings_dict[dt] = set()
                    holdings_dict[dt].add(symbol)
            ts_list = sorted(list(holdings_dict.keys()))
            overlaps = []
            for i in range(1, len(ts_list)):
                overlaps.append(len(holdings_dict[ts_list[i-1]].intersection(holdings_dict[ts_list[i]])))
            avg_overlap = np.mean(overlaps) if overlaps else 0.0
        except Exception:
            pass

    concentration = 1.0 / k

    run_record = {
        "Timeframe": tf,
        "Lookback": lookback,
        "Portfolio Size K": k,
        "Rebalance Freq R": r,
        "Status": results["status"],
        "Termination Reason": results["termination_reason"],
        "Trade Count": metrics["trade_count"],
        "Win Rate": metrics["win_rate"],
        "Profit Factor": metrics["profit_factor"],
        "Expectancy (USD)": metrics["expectancy_r"],
        "CAGR": metrics["cagr"],
        "Sharpe Ratio": metrics["sharpe_ratio"],
        "Max Drawdown": metrics["max_drawdown"]["drawdown_pct"],
        "Avg Holding Period": metrics["avg_holding_period_hours"],
        "Portfolio Turnover": metrics["portfolio_turnover"],
        "Rank Persistence": metrics["avg_holding_period_hours"],
        "Average Overlap": avg_overlap,
        "Concentration Index": concentration,
        "Gross Fees": gross_fees,
        "Gross Slippage": gross_slippage,
        "Fee % of Gross PnL": fee_pct
    }

    manifest = {
        "parameters": params,
        "timeframe": tf,
        "universe": symbols,
        "termination_status": results["status"],
        "termination_reason": results["termination_reason"]
    }

    return run_record, manifest, metrics


def run_matrix_sweep():
    candidate_id = "candidate_01_relative_strength"
    candidate_dir = workspace_dir / "research" / candidate_id
    
    framework_config_path = workspace_dir / "research_engine" / "configs" / "framework_config.yaml"
    candidate_yaml_path = candidate_dir / "configs" / "candidate.yaml"
    
    # Load candidate YAML
    with open(candidate_yaml_path, "r", encoding="utf-8") as f:
        candidate_cfg = yaml.safe_load(f)
    symbols = candidate_cfg["candidate"]["universe"]["symbols"]

    # Load framework config to get max_workers
    with open(framework_config_path, "r", encoding="utf-8") as f:
        framework_cfg = yaml.safe_load(f)
    max_workers = framework_cfg.get("engine", {}).get("max_workers", 4)

    # Initialize frameworks
    outputs_dir = workspace_dir / "research_engine" / "outputs"
    dashboard_path = outputs_dir / "dashboard_state.json"
    registry_path = outputs_dir / "experiment_registry.json"
    
    dashboard = CandidateDashboard(state_file_path=dashboard_path)
    registry = ExperimentRegistry(database_path=registry_path)
    engine = DiscoveryEngine(config_path=framework_config_path)
    
    # Parameter grid definition
    timeframes = ["15m", "1H", "4H"]
    lookbacks = [20, 50, 100]
    portfolio_sizes = [1, 3, 5]
    rebalance_freqs = [1, 2, 4]
    
    # Calculate combinations
    combinations = list(itertools.product(timeframes, lookbacks, portfolio_sizes, rebalance_freqs))
    total_runs = len(combinations)
    print(f"Starting Parameter Sweep: {total_runs} total experiments with {max_workers} parallel workers.")
    
    results_list = []
    
    # Update dashboard initial
    dashboard.update_candidate_progress(
        candidate_id="Candidate 01",
        stage="Discovery Sweep",
        status="RUNNING",
        progress_pct=0.0,
        notes="Starting parallel sweep execution"
    )

    global_index = 0
    # Process timeframe by timeframe to avoid loading all data into memory at once
    for tf in timeframes:
        print(f"Loading database for timeframe {tf}...")
        universe_data = engine.load_dataset(symbols, tf)
        plugin = engine.load_plugin(candidate_id)
        preprocessed_data = plugin.preprocess(universe_data)
        
        # Filter combinations for this timeframe
        tf_combos = [c for c in combinations if c[0] == tf]
        
        # Prepare combo info lists
        combo_infos = []
        for combo in tf_combos:
            tf_val, lookback, k, r = combo
            combo_infos.append((tf_val, lookback, k, r, preprocessed_data, symbols, framework_config_path, candidate_id))
            
        print(f"Submitting {len(tf_combos)} experiments for timeframe {tf} to ProcessPoolExecutor...")
        
        # Run in parallel
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Map combinations to futures
            future_to_combo = {executor.submit(run_single_backtest_worker, ci): ci for ci in combo_infos}
            
            for future in as_completed(future_to_combo):
                combo_val = future_to_combo[future]
                tf_val, lookback, k, r = combo_val[0], combo_val[1], combo_val[2], combo_val[3]
                
                experiment_num = global_index + 2  # C001-E00002 onwards
                experiment_id = f"C001-E{experiment_num:05d}"
                global_index += 1
                
                try:
                    run_record, manifest, metrics = future.result()
                    
                    # Add experiment ID to record and manifest
                    run_record["Experiment ID"] = experiment_id
                    manifest["experiment_id"] = experiment_id
                    
                    print(f"Completed [{global_index}/{total_runs}]: ID={experiment_id} | TF={tf_val} | L={lookback} | K={k} | R={r} | Sharpe={metrics['sharpe_ratio']:.4f}")
                    
                    # Update dashboard
                    dashboard.update_candidate_progress(
                        candidate_id="Candidate 01",
                        stage="Discovery Sweep",
                        status="RUNNING",
                        progress_pct=(global_index / total_runs) * 100.0,
                        current_experiment=experiment_id,
                        notes=f"Completed TF={tf_val}, L={lookback}, K={k}, R={r}"
                    )
                    
                    results_list.append(run_record)
                    
                    # Register experiment index record
                    # Add Git Commit info to manifest if possible
                    import subprocess
                    try:
                        git_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
                        manifest["git_commit"] = git_hash
                    except Exception:
                        manifest["git_commit"] = "N/A"
                        
                    registry.register_experiment("Candidate 01", experiment_id, manifest, metrics)
                    
                except Exception as exc:
                    print(f"Experiment {experiment_id} generated an exception: {exc}")
                    dashboard.update_candidate_progress(
                        candidate_id="Candidate 01",
                        stage="Discovery Sweep",
                        status="FAILED",
                        progress_pct=(global_index / total_runs) * 100.0,
                        notes=f"Experiment {experiment_id} failed: {exc}"
                    )
                    raise exc

    # 2. Save Outputs
    results_df = pd.DataFrame(results_list)
    # Ensure columns order matches expected
    expected_cols = [
        "Experiment ID", "Timeframe", "Lookback", "Portfolio Size K", "Rebalance Freq R",
        "Status", "Termination Reason", "Trade Count", "Win Rate", "Profit Factor",
        "Expectancy (USD)", "CAGR", "Sharpe Ratio", "Max Drawdown", "Avg Holding Period",
        "Portfolio Turnover", "Rank Persistence", "Average Overlap", "Concentration Index",
        "Gross Fees", "Gross Slippage", "Fee % of Gross PnL"
    ]
    # Reorder columns to ensure exact match
    results_df = results_df[expected_cols]
    
    outputs_path = candidate_dir / "outputs"
    outputs_path.mkdir(parents=True, exist_ok=True)
    
    results_df.to_csv(outputs_path / "discovery_matrix_results.csv", index=False)
    print("Saved discovery_matrix_results.csv successfully.")
    
    # 3. Candidate Sorter (Research Quality Ranking Score)
    results_df['Quality Score'] = (
        results_df['Sharpe Ratio'] * 1.5 +
        results_df['Profit Factor'] * 1.0 -
        (results_df['Max Drawdown'] / 100.0) * 1.0 -
        (results_df['Fee % of Gross PnL'] / 100.0) * 0.5
    )
    
    # Rank configurations
    ranked_df = results_df.sort_values(by='Quality Score', ascending=False)
    
    # Determine Verdicts
    verdicts = []
    for _, row in ranked_df.iterrows():
        sh = row['Sharpe Ratio']
        pf = row['Profit Factor']
        dd = row['Max Drawdown']
        tc = row['Trade Count']
        status = row['Status']
        
        if status == 'TERMINATED':
            verdicts.append('REJECT (Safety Guard Triggered)')
        elif sh > 0.05 and pf > 1.01 and dd < 45.0 and tc >= 40:
            verdicts.append('PASS (Qualifies for Walk-Forward)')
        elif sh >= -0.25 and dd < 65.0 and tc >= 20:
            verdicts.append('BORDERLINE')
        else:
            verdicts.append('REJECT')
            
    ranked_df['Verdict'] = verdicts
    ranked_df.to_csv(outputs_path / "ranked_candidates.csv", index=False)
    print("Saved ranked_candidates.csv successfully.")
    
    # 4. Generate candidate_summary.md
    summary_path = candidate_dir / "reports" / "candidate_summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Select subset for reporting
    table_df = ranked_df[[
        "Experiment ID", "Timeframe", "Lookback", "Portfolio Size K", "Rebalance Freq R",
        "Trade Count", "Profit Factor", "CAGR", "Max Drawdown", "Portfolio Turnover", "Fee % of Gross PnL", "Verdict"
    ]].head(25)
    
    # Convert to markdown table
    md_table = table_df.to_markdown(index=False)
    
    summary_content = f"""# Candidate C001 — Discovery Sweep Matrix Summary

This document ranks the performance of the 81 configurations evaluated in Candidate C001 Discovery Matrix sweeps.

## Ranked Configurations (Top 25)

{md_table}

---

## Research Synthesis Summary
- **Evaluation Period**: Approx. 3 years (June 2023 - June 2026).
- **Metric Definitions**:
  - *Sharpe Ratio*: Risk-adjusted return resampled daily.
  - *Fee %*: Gross fees paid divided by gross strategy PnL.
  - *Quality Score Sort*: Sorts configurations by Sharpe stability and low execution drag rather than simple return magnitude.
"""
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_content)
        
    print("Generated candidate_summary.md successfully.")
    
    # Update dashboard state to COMPLETED
    dashboard.update_candidate_progress(
        candidate_id="Candidate 01",
        stage="Discovery Sweep",
        status="COMPLETED",
        progress_pct=100.0,
        notes="Sprint 2 discovery sweep matrix executed successfully. READY FOR WALK-FORWARD SELECTION."
    )
    print("Dashboard updated successfully.")


if __name__ == "__main__":
    run_matrix_sweep()
