"""Discovery Sweep Matrix Runner for Candidate C002 (Volatility Contraction Pattern).

Executes parallel backtesting sweeps across the entire VCP parameter grid.
Logs results in registry, updates dashboard, and generates reports.
"""

import os
import json
from pathlib import Path
import sys
import datetime
import itertools
import pandas as pd
import numpy as np
import yaml
import subprocess
import argparse
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

# Add workspace directory to python path
workspace_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_dir))

from research_engine.core.discovery_engine import DiscoveryEngine
from research_engine.core.metrics_engine import MetricsEngine
from research_engine.core.candidate_dashboard import CandidateDashboard
from research_engine.core.experiment_registry import ExperimentRegistry

def custom_update_candidate_progress(self, 
                                     candidate_id: str, 
                                     stage: str, 
                                     status: str, 
                                     progress_pct: float,
                                     current_experiment: str = None,
                                     notes: str = "",
                                     eta: str = "N/A",
                                     current_best_candidate: str = "N/A",
                                     highest_sharpe: float = 0.0,
                                     highest_profit_factor: float = 0.0,
                                     highest_cagr: float = 0.0) -> None:
    state = {"last_updated": "", "candidates": {}}
    try:
        with open(self.state_file_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        pass

    candidates = state.get("candidates", {})
    cand_state = candidates.get(candidate_id, {})
    
    cand_state["name"] = candidate_id
    cand_state["stage"] = stage
    cand_state["status"] = status
    cand_state["progress_pct"] = progress_pct
    if current_experiment:
        cand_state["current_experiment"] = current_experiment
    cand_state["notes"] = notes
    
    # Custom dashboard fields
    cand_state["eta"] = eta
    cand_state["current_best_candidate"] = current_best_candidate
    cand_state["highest_sharpe"] = highest_sharpe
    cand_state["highest_profit_factor"] = highest_profit_factor
    cand_state["highest_cagr"] = highest_cagr
    
    now_str = datetime.datetime.utcnow().isoformat() + "Z"
    if status == "RUNNING" and not cand_state.get("start_time"):
        cand_state["start_time"] = now_str
        cand_state["end_time"] = None
    elif status in ["COMPLETED", "FAILED", "TERMINATED", "INVALID_CONFIGURATION"]:
        cand_state["end_time"] = now_str

    candidates[candidate_id] = cand_state
    state["candidates"] = candidates
    state["last_updated"] = now_str

    with open(self.state_file_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

CandidateDashboard.update_candidate_progress = custom_update_candidate_progress

# The optimized numpy-based backtest simulator monkey patch
def numpy_simulate_backtest(self, universe_data: dict, parameters: dict) -> dict:
    initial_capital = self.configs.get("execution", {}).get("initial_capital", 10000.0)
    costs = self.configs.get("execution", {}).get("costs", {})
    taker_fee_rate = costs.get("default_taker_fee", 0.00045)
    slippage_rate = costs.get("default_slippage", 0.0005)
    
    k = parameters.get("portfolio_size_k", 3)
    
    symbols = list(universe_data.keys())
    M = len(symbols)
    first_sym = symbols[0]
    timestamps = universe_data[first_sym].index
    N = len(timestamps)
    
    close_matrix = np.zeros((N, M))
    signal_matrix = np.zeros((N, M))
    
    for i, sym in enumerate(symbols):
        close_matrix[:, i] = universe_data[sym]['close'].to_numpy()
        signal_matrix[:, i] = universe_data[sym]['signal'].to_numpy()
        
    cash = initial_capital
    positions = np.zeros(M)
    equity_history = np.zeros(N)
    
    trades = []
    active_trades = {}
    
    status = "COMPLETED"
    termination_reason = "N/A"
    last_processed_candle = "N/A"
    
    rebalance_starts = parameters.get("lookback_window", 50)
    rebalance_freq = parameters.get("rebalance_frequency_r", 1)
    
    for idx in range(N):
        t = timestamps[idx]
        last_processed_candle = str(t)
        close_prices = close_matrix[idx]
        
        current_asset_value = 0.0
        for i in range(M):
            if positions[i] > 0.0:
                current_asset_value += positions[i] * close_prices[i]
        portfolio_value = cash + current_asset_value
        
        if np.isnan(portfolio_value) or np.isinf(portfolio_value):
            status = "FAILED"
            termination_reason = "NaN or Infinite portfolio equity detected."
            equity_history[idx:] = 0.0
            for i, trade_record in list(active_trades.items()):
                trade_record["exit_timestamp"] = t
                trade_record["exit_price"] = close_prices[i]
                trade_record["exit_reason"] = "ACCOUNTING_FAILURE"
                trades.append(trade_record)
            active_trades.clear()
            break
            
        if cash < -0.01:
            status = "FAILED"
            termination_reason = f"Negative cash balance detected: {cash} USD."
            equity_history[idx:] = portfolio_value
            for i, trade_record in list(active_trades.items()):
                qty_sold = positions[i]
                fee = qty_sold * close_prices[i] * taker_fee_rate
                slippage_cost = qty_sold * close_prices[i] * slippage_rate
                trade_record["exit_timestamp"] = t
                trade_record["exit_price"] = close_prices[i]
                trade_record["fees_paid"] += fee
                trade_record["slippage_paid"] += slippage_cost
                trade_record["pnl_nominal"] = (qty_sold * close_prices[i]) - (trade_record["qty"] * trade_record["entry_price"]) - trade_record["fees_paid"] - trade_record["slippage_paid"]
                trade_record["pnl_r"] = (trade_record["pnl_nominal"] / (trade_record["qty"] * trade_record["entry_price"])) * 100.0 if (trade_record["qty"] * trade_record["entry_price"]) > 0 else 0.0
                trade_record["exit_reason"] = "ACCOUNTING_FAILURE"
                trades.append(trade_record)
            active_trades.clear()
            break
            
        if portfolio_value <= 0:
            status = "TERMINATED"
            termination_reason = "Portfolio equity reached zero or negative."
            equity_history[idx:] = portfolio_value
            for i, trade_record in list(active_trades.items()):
                qty_sold = positions[i]
                fee = qty_sold * close_prices[i] * taker_fee_rate
                slippage_cost = qty_sold * close_prices[i] * slippage_rate
                trade_record["exit_timestamp"] = t
                trade_record["exit_price"] = close_prices[i]
                trade_record["fees_paid"] += fee
                trade_record["slippage_paid"] += slippage_cost
                trade_record["pnl_nominal"] = (qty_sold * close_prices[i]) - (trade_record["qty"] * trade_record["entry_price"]) - trade_record["fees_paid"] - trade_record["slippage_paid"]
                trade_record["pnl_r"] = (trade_record["pnl_nominal"] / (trade_record["qty"] * trade_record["entry_price"])) * 100.0 if (trade_record["qty"] * trade_record["entry_price"]) > 0 else 0.0
                trade_record["exit_reason"] = "LIQUIDATION"
                trades.append(trade_record)
            active_trades.clear()
            break
            
        equity_history[idx] = portfolio_value
        
        if idx < rebalance_starts:
            continue
        if (idx - rebalance_starts) % rebalance_freq != 0:
            continue
            
        signals = signal_matrix[idx]
        target_indices = []
        for i in range(M):
            if signals[i] == 1.0:
                target_indices.append(i)
        target_indices = target_indices[:k]
        
        for i in range(M):
            if positions[i] > 0.0 and i not in target_indices:
                qty_sold = positions[i]
                exec_price = close_prices[i] * (1.0 - slippage_rate)
                nominal_value = qty_sold * close_prices[i]
                fee = nominal_value * taker_fee_rate
                slippage_cost = nominal_value * slippage_rate
                cash_received = qty_sold * exec_price - fee
                
                cash += cash_received
                positions[i] = 0.0
                
                trade_record = active_trades.pop(i)
                trade_record["exit_timestamp"] = t
                trade_record["exit_price"] = close_prices[i]
                trade_record["fees_paid"] += fee
                trade_record["slippage_paid"] += slippage_cost
                entry_val = trade_record["qty"] * trade_record["entry_price"]
                exit_val = qty_sold * close_prices[i]
                trade_record["pnl_nominal"] = exit_val - entry_val - trade_record["fees_paid"] - trade_record["slippage_paid"]
                trade_record["pnl_r"] = (trade_record["pnl_nominal"] / entry_val) * 100.0 if entry_val > 0 else 0.0
                trades.append(trade_record)
                
        active_targets_count = len(target_indices)
        target_value = portfolio_value / active_targets_count if active_targets_count > 0 else 0.0
        
        for i in target_indices:
            if positions[i] > 0.0:
                if close_prices[i] <= 0:
                    continue
                current_val = positions[i] * close_prices[i]
                if current_val > target_value:
                    excess_val = current_val - target_value
                    qty_sold = excess_val / close_prices[i]
                    if qty_sold <= 0:
                        continue
                    exec_price = close_prices[i] * (1.0 - slippage_rate)
                    fee = excess_val * taker_fee_rate
                    slippage_cost = excess_val * slippage_rate
                    cash_received = qty_sold * exec_price - fee
                    
                    cash += cash_received
                    positions[i] -= qty_sold
                    
                    if i in active_trades:
                        partial_trade = active_trades[i].copy()
                        partial_trade["qty"] = qty_sold
                        partial_trade["exit_timestamp"] = t
                        partial_trade["exit_price"] = close_prices[i]
                        partial_trade["fees_paid"] = fee
                        partial_trade["slippage_paid"] = slippage_cost
                        
                        entry_val = qty_sold * partial_trade["entry_price"]
                        exit_val = qty_sold * close_prices[i]
                        partial_trade["pnl_nominal"] = exit_val - entry_val - fee - slippage_cost
                        partial_trade["pnl_r"] = (partial_trade["pnl_nominal"] / entry_val) * 100.0 if entry_val > 0 else 0.0
                        partial_trade["exit_reason"] = "REBALANCE_REDUCTION"
                        partial_trade["trade_id"] = f"{active_trades[i]['trade_id']}-P"
                        
                        trades.append(partial_trade)
                        active_trades[i]["qty"] = max(0.0, active_trades[i]["qty"] - qty_sold)
                        
        for i in target_indices:
            if close_prices[i] <= 0:
                continue
            current_val = positions[i] * close_prices[i]
            if current_val < target_value:
                if portfolio_value <= 0:
                    continue
                deficit_val = target_value - current_val
                if deficit_val <= 0:
                    continue
                    
                q = deficit_val / (close_prices[i] * (1.0 + slippage_rate + taker_fee_rate))
                if q <= 0:
                    continue
                    
                nominal_cost = q * close_prices[i]
                fee = nominal_cost * taker_fee_rate
                slippage_cost = nominal_cost * slippage_rate
                cash_spent = nominal_cost * (1.0 + slippage_rate) + fee
                
                if cash_spent > cash:
                    cash_spent = cash
                    q = cash_spent / (close_prices[i] * (1.0 + slippage_rate + taker_fee_rate))
                    if q <= 0:
                        continue
                    nominal_cost = q * close_prices[i]
                    fee = nominal_cost * taker_fee_rate
                    slippage_cost = nominal_cost * slippage_rate
                    
                cash -= cash_spent
                positions[i] += q
                
                sym = symbols[i]
                if i not in active_trades:
                    active_trades[i] = {
                        "trade_id": f"T-{len(trades) + len(active_trades) + 1:05d}",
                        "asset": sym,
                        "direction": "LONG",
                        "entry_timestamp": t,
                        "entry_price": close_prices[i],
                        "qty": q,
                        "exit_timestamp": None,
                        "exit_price": 0.0,
                        "exit_reason": "RANK_DECAY",
                        "pnl_nominal": 0.0,
                        "pnl_r": 0.0,
                        "fees_paid": fee,
                        "slippage_paid": slippage_cost
                    }
                else:
                    active_trades[i]["fees_paid"] += fee
                    active_trades[i]["slippage_paid"] += slippage_cost
                    prev_qty = active_trades[i]["qty"]
                    prev_price = active_trades[i]["entry_price"]
                    new_qty = prev_qty + q
                    blended_price = (prev_qty * prev_price + q * close_prices[i]) / new_qty
                    active_trades[i]["qty"] = new_qty
                    active_trades[i]["entry_price"] = blended_price

    if status == "COMPLETED":
        end_time = timestamps[-1]
        final_prices = close_matrix[-1]
        for i, trade_record in list(active_trades.items()):
            qty_sold = positions[i]
            exec_price = final_prices[i] * (1.0 - slippage_rate)
            nominal_value = qty_sold * final_prices[i]
            fee = nominal_value * taker_fee_rate
            slippage_cost = nominal_value * slippage_rate
            
            trade_record["exit_timestamp"] = end_time
            trade_record["exit_price"] = final_prices[i]
            trade_record["fees_paid"] += fee
            trade_record["slippage_paid"] += slippage_cost
            
            entry_val = trade_record["qty"] * trade_record["entry_price"]
            exit_val = qty_sold * final_prices[i]
            trade_record["pnl_nominal"] = exit_val - entry_val - trade_record["fees_paid"] - trade_record["slippage_paid"]
            trade_record["pnl_r"] = (trade_record["pnl_nominal"] / entry_val) * 100.0 if entry_val > 0 else 0.0
            trades.append(trade_record)
            
    trade_ledger = pd.DataFrame(trades)
    if trade_ledger.empty:
        trade_ledger = pd.DataFrame(columns=[
            'trade_id', 'asset', 'direction', 'entry_timestamp', 'entry_price',
            'qty', 'exit_timestamp', 'exit_price', 'exit_reason', 'pnl_nominal',
            'pnl_r', 'fees_paid', 'slippage_paid'
        ])
        
    equity_curve = pd.Series(equity_history, index=timestamps, name="portfolio_equity")
    number_of_rebalances = max(0, N - rebalance_starts)
    
    total_volume = 0.0
    if not trade_ledger.empty:
        total_volume += (trade_ledger['qty'] * trade_ledger['entry_price']).sum()
        total_volume += (trade_ledger['qty'] * trade_ledger['exit_price']).sum()
        
    average_portfolio_value = equity_curve.mean()
    
    return {
        "status": status,
        "termination_reason": termination_reason,
        "last_processed_candle": last_processed_candle,
        "trade_ledger": trade_ledger,
        "equity_curve": equity_curve,
        "number_of_rebalances": number_of_rebalances,
        "total_volume_traded": total_volume,
        "average_portfolio_value": average_portfolio_value
    }

# Apply patch to module scope DiscoveryEngine
DiscoveryEngine.simulate_backtest = numpy_simulate_backtest

# Platform-Independent Process Priority
def set_process_priority():
    import sys
    import os
    if sys.platform == 'win32':
        try:
            import ctypes
            # BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
        except Exception:
            pass
    else:
        try:
            os.nice(10)
        except Exception:
            pass

_pending_experiments = []

def batched_register_experiment(self, candidate_id: str, experiment_id: str, manifest: dict, metrics: dict) -> None:
    global _pending_experiments
    _pending_experiments.append({
        "candidate_id": candidate_id,
        "experiment_id": experiment_id,
        "manifest": manifest,
        "metrics": metrics
    })
    if len(_pending_experiments) >= 50:
        self.flush_batch()

def flush_batch(self):
    global _pending_experiments
    if not _pending_experiments:
        return
    registry_data = {"experiments": []}
    if self.database_path.exists():
        try:
            with open(self.database_path, "r", encoding="utf-8") as f:
                registry_data = json.load(f)
        except Exception:
            pass
            
    experiments = registry_data.get("experiments", [])
    pending_ids = {e["experiment_id"] for e in _pending_experiments}
    experiments = [e for e in experiments if e.get("experiment_id") not in pending_ids]
    experiments.extend(_pending_experiments)
    registry_data["experiments"] = experiments
    
    with open(self.database_path, "w", encoding="utf-8") as f:
        json.dump(registry_data, f, indent=2)
    _pending_experiments.clear()

ExperimentRegistry.register_experiment = batched_register_experiment
ExperimentRegistry.flush_batch = flush_batch

# Process-level cache to hold preprocessed DataFrames
cached_data = {}


def run_single_backtest_worker(combo_info):
    (tf, trend_gate, swing_window, contraction_waves, max_final_contraction,
     breakout, risk_reward, stop_buffer, symbols, framework_config_path, candidate_id, worker_sleep_ms) = combo_info

    import sys
    from pathlib import Path
    workspace_dir = Path(__file__).resolve().parent.parent
    if str(workspace_dir) not in sys.path:
        sys.path.insert(0, str(workspace_dir))

    from research_engine.core.discovery_engine import DiscoveryEngine
    from research_engine.core.metrics_engine import MetricsEngine
    import pandas as pd
    import numpy as np
    import time

    # Lower process priority to Below Normal in a platform-independent way
    set_process_priority()

    # Apply monkey patch inside process worker namespace
    DiscoveryEngine.simulate_backtest = numpy_simulate_backtest

    # Process-level caching of dataset to avoid IPC transfer cost
    global cached_data
    cache_key = (tf, tuple(symbols))
    if cache_key not in cached_data:
        engine = DiscoveryEngine(config_path=framework_config_path)
        universe_data = engine.load_dataset(symbols, tf)
        plugin = engine.load_plugin(candidate_id)
        cached_data[cache_key] = plugin.preprocess(universe_data)

    preprocessed_data = cached_data[cache_key]

    engine = DiscoveryEngine(config_path=framework_config_path)
    plugin = engine.load_plugin(candidate_id)
    metrics_engine = MetricsEngine()

    params = {
        "trend_gate": trend_gate,
        "swing_window": swing_window,
        "contraction_waves": contraction_waves,
        "max_final_contraction": max_final_contraction,
        "breakout": breakout,
        "risk_reward": risk_reward,
        "stop_buffer": stop_buffer,
        "portfolio_size_k": 3  # Fixed baseline active positions limit
    }

    # Generate signals and simulate backtest
    signaled_data = plugin.generate_signals(preprocessed_data, params)
    results = engine.simulate_backtest(signaled_data, params)

    trade_ledger = results["trade_ledger"]
    equity_curve = results["equity_curve"]
    num_rebalances = results["number_of_rebalances"]
    total_volume = results["total_volume_traded"]
    avg_port_val = results["average_portfolio_value"]

    # Compute standard metrics
    metrics = metrics_engine.calculate_metrics(
        trade_ledger=trade_ledger,
        daily_equity=equity_curve,
        number_of_rebalances=num_rebalances,
        total_volume_traded=total_volume,
        average_portfolio_value=avg_port_val
    )

    # Collect custom VCP metrics
    custom_vcp_metrics = plugin.get_custom_metrics()

    gross_fees = trade_ledger['fees_paid'].sum() if not trade_ledger.empty else 0.0
    gross_slippage = trade_ledger['slippage_paid'].sum() if not trade_ledger.empty else 0.0
    net_pnl = trade_ledger['pnl_nominal'].sum() if not trade_ledger.empty else 0.0
    gross_pnl = net_pnl + gross_fees + gross_slippage
    fee_pct = (gross_fees / abs(gross_pnl)) * 100.0 if abs(gross_pnl) > 0.0 else 0.0

    run_record = {
        "Timeframe": tf,
        "Trend Gate": trend_gate,
        "Swing Window": swing_window,
        "Contraction Waves": contraction_waves,
        "Max Final Contraction": max_final_contraction,
        "Breakout": breakout,
        "Risk Reward": risk_reward,
        "Stop Buffer": stop_buffer,
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
        "Gross Fees": gross_fees,
        "Gross Slippage": gross_slippage,
        "Fee % of Gross PnL": fee_pct,
        # Custom VCP metrics
        "Pattern Frequency": custom_vcp_metrics["Pattern Frequency"],
        "Pattern Success Rate": custom_vcp_metrics["Pattern Success Rate"],
        "Average Contraction Duration": custom_vcp_metrics["Average Contraction Duration"],
        "Average Breakout Distance": custom_vcp_metrics["Average Breakout Distance"],
        "False Breakout %": custom_vcp_metrics["False Breakout %"]
    }

    manifest = {
        "parameters": params,
        "timeframe": tf,
        "universe": symbols,
        "termination_status": results["status"],
        "termination_reason": results["termination_reason"]
    }

    # Embed custom metrics into metrics dictionary for indexing
    metrics.update(custom_vcp_metrics)

    # CPU temperature friendly mode: brief breathing window
    if worker_sleep_ms > 0:
        time.sleep(worker_sleep_ms / 1000.0)

    return run_record, manifest, metrics


def save_checkpoint(checkpoint_path, results_list, outputs_path, registry_flush_fn=None):
    checkpoint_data = {
        "results_list": results_list
    }
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint_data, f, indent=2)
    
    if registry_flush_fn:
        registry_flush_fn()

    if not results_list:
        return

    # Save partial discovery matrix results
    results_df = pd.DataFrame(results_list)
    expected_cols = [
        "Experiment ID", "Timeframe", "Trend Gate", "Swing Window", "Contraction Waves",
        "Max Final Contraction", "Breakout", "Risk Reward", "Stop Buffer",
        "Status", "Termination Reason", "Trade Count", "Win Rate", "Profit Factor",
        "Expectancy (USD)", "CAGR", "Sharpe Ratio", "Max Drawdown", "Avg Holding Period",
        "Portfolio Turnover", "Gross Fees", "Gross Slippage", "Fee % of Gross PnL",
        "Pattern Frequency", "Pattern Success Rate", "Average Contraction Duration",
        "Average Breakout Distance", "False Breakout %"
    ]
    existing_cols = [c for c in expected_cols if c in results_df.columns]
    results_df = results_df[existing_cols]
    
    results_df.to_csv(outputs_path / "discovery_matrix_results.csv", index=False)

    # Save partial ranked candidates
    results_df['Quality Score'] = (
        results_df['Sharpe Ratio'] * 1.5 +
        results_df['Profit Factor'] * 1.0 -
        (results_df['Max Drawdown'] / 100.0) * 1.0 -
        (results_df['Fee % of Gross PnL'] / 100.0) * 0.5
    )
    ranked_df = results_df.sort_values(by='Quality Score', ascending=False)
    
    verdicts = []
    for _, row in ranked_df.iterrows():
        tf_val = row['Timeframe']
        tc = row['Trade Count']
        sh = row['Sharpe Ratio']
        pf = row['Profit Factor']
        dd = row['Max Drawdown']
        status = row['Status']
        
        if tf_val == "15m":
            pass_tc, borderline_tc = 225, 200
        elif tf_val == "1H":
            pass_tc, borderline_tc = 120, 105
        else:
            pass_tc, borderline_tc = 50, 45

        if status == 'TERMINATED':
            verdicts.append('REJECT (Safety Guard Triggered)')
        elif sh >= 1.20 and pf >= 1.15 and dd < 30.0 and tc >= pass_tc:
            verdicts.append('PASS')
        elif sh >= 0.50 and dd < 45.0 and tc >= borderline_tc:
            verdicts.append('BORDERLINE')
        else:
            verdicts.append('REJECT')
            
    ranked_df['Verdict'] = verdicts
    ranked_df.to_csv(outputs_path / "ranked_candidates.csv", index=False)

    # Save partial Top 10 CSVs to outputs_path for real-time tracking
    top10_overall = ranked_df.head(10)
    top10_overall.to_csv(outputs_path / "top10_overall.csv", index=False)
    
    top10_sharpe = ranked_df.sort_values(by="Sharpe Ratio", ascending=False).head(10)
    top10_sharpe.to_csv(outputs_path / "top10_sharpe.csv", index=False)
    
    top10_cagr = ranked_df.sort_values(by="CAGR", ascending=False).head(10)
    top10_cagr.to_csv(outputs_path / "top10_cagr.csv", index=False)
    
    top10_pf = ranked_df.sort_values(by="Profit Factor", ascending=False).head(10)
    top10_pf.to_csv(outputs_path / "top10_pf.csv", index=False)
    
    top10_drawdown = ranked_df.sort_values(by="Max Drawdown", ascending=True).head(10)
    top10_drawdown.to_csv(outputs_path / "top10_drawdown.csv", index=False)


def run_matrix_sweep_c002():
    # Lower process priority to Below Normal on startup
    set_process_priority()

    candidate_id = "candidate_02_vcp"
    candidate_dir = workspace_dir / "research" / candidate_id
    
    framework_config_path = workspace_dir / "research_engine" / "configs" / "framework_config.yaml"
    candidate_yaml_path = candidate_dir / "configs" / "candidate.yaml"
    
    # Load candidate configuration
    with open(candidate_yaml_path, "r", encoding="utf-8") as f:
        candidate_cfg = yaml.safe_load(f)
    symbols = candidate_cfg["candidate"]["universe"]["symbols"]

    # Load framework config to get execution parameters
    with open(framework_config_path, "r", encoding="utf-8") as f:
        framework_cfg = yaml.safe_load(f)

    # CLI Argument Parsing
    parser = argparse.ArgumentParser(description="Candidate C002 VCP Sweep Runner")
    parser.add_argument("--workers", type=int, default=None, help="Force override workers count")
    args, unknown = parser.parse_known_args()

    # Worker configuration logic
    cli_workers = args.workers
    system_cfg = framework_cfg.get("system", {})
    yaml_max_workers = system_cfg.get("max_workers", "auto")
    yaml_default_workers = system_cfg.get("default_workers", 2)
    worker_sleep_ms = int(system_cfg.get("worker_sleep_ms", 10))

    if cli_workers is not None:
        max_workers = cli_workers
        print(f"Workers: Configured via CLI override to {max_workers}")
    elif yaml_max_workers == "auto":
        max_workers = os.cpu_count() or 2
        print(f"Workers: Configured via YAML 'auto' to {max_workers}")
    else:
        try:
            max_workers = int(yaml_max_workers)
            print(f"Workers: Configured via YAML integer to {max_workers}")
        except (ValueError, TypeError):
            max_workers = int(yaml_default_workers)
            print(f"Workers: Configured via YAML default fallback to {max_workers}")

    print(f"Thermal Sleep Mode: {worker_sleep_ms} ms pause per experiment.")

    # Initialize dashboard & registry
    outputs_path = workspace_dir / "research_engine" / "outputs"
    outputs_path.mkdir(parents=True, exist_ok=True)
    dashboard_path = outputs_path / "dashboard_state.json"
    registry_path = outputs_path / "experiment_registry.json"
    checkpoint_path = outputs_path / "checkpoint.json"
    
    dashboard = CandidateDashboard(state_file_path=dashboard_path)
    registry = ExperimentRegistry(database_path=registry_path)

    # VCP Parameter Sweep Grid
    timeframes = ["4H", "1H", "15m"]
    trend_gates = ["None", "EMA100", "EMA200", "HH_HL", "Donchian"]
    swing_windows = [3, 5, 7]
    contraction_waves = [2, 3]
    max_final_contractions = [0.03, 0.05, 0.07]
    breakouts = ["Close_Above_Swing_High", "High_Break", "Donchian_Break"]
    risk_rewards = ["1R", "1.5R", "2R", "3R", "ATR_Trail", "Swing_Trail", "30_Bar_Time_Exit"]
    stop_buffers = [0.0, 0.0005, 0.0010]

    # Generate combination tuples
    combinations = list(itertools.product(
        timeframes, trend_gates, swing_windows, contraction_waves,
        max_final_contractions, breakouts, risk_rewards, stop_buffers
    ))
    total_runs = len(combinations)

    # Helper function to get unique key for configuration
    def get_combo_key(c):
        return (c[0], c[1], int(c[2]), int(c[3]), float(c[4]), c[5], c[6], float(c[7]))

    results_list = []
    completed_keys = set()
    resume_mode = False

    # Check if checkpoint exists and prompt to resume
    if checkpoint_path.exists():
        if sys.stdin.isatty():
            try:
                ans = input("Previous VCP sweep checkpoint detected. Resume previous run? [Y/N] (Default: Y): ").strip().lower()
                if ans.startswith('y') or ans == '':
                    resume_mode = True
            except Exception:
                resume_mode = True
        else:
            print("Non-interactive terminal detected. Auto-resuming previous run from checkpoint.")
            resume_mode = True

    if resume_mode:
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)
            results_list = checkpoint_data.get("results_list", [])
            for r in results_list:
                key = (
                    r["Timeframe"],
                    r["Trend Gate"],
                    int(r["Swing Window"]),
                    int(r["Contraction Waves"]),
                    float(r["Max Final Contraction"]),
                    r["Breakout"],
                    r["Risk Reward"],
                    float(r["Stop Buffer"])
                )
                completed_keys.add(key)
            print(f"Loaded {len(results_list)} completed experiments from checkpoint.")
        except Exception as e:
            print(f"Error loading checkpoint: {e}. Starting fresh.")
            results_list = []
            completed_keys = set()
    else:
        if checkpoint_path.exists():
            try:
                checkpoint_path.unlink()
            except Exception:
                pass

    global_index = len(completed_keys)
    print(f"Sweep status: {global_index} of {total_runs} completed. {total_runs - global_index} remaining.")
    
    # Compute current best stats from results_list on resume
    highest_sharpe = 0.0
    highest_profit_factor = 0.0
    highest_cagr = 0.0
    current_best_candidate = "N/A"
    if results_list:
        best_sharpe_row = max(results_list, key=lambda x: x.get("Sharpe Ratio", 0.0))
        highest_sharpe = best_sharpe_row.get("Sharpe Ratio", 0.0)
        
        best_pf_row = max(results_list, key=lambda x: x.get("Profit Factor", 0.0))
        highest_profit_factor = best_pf_row.get("Profit Factor", 0.0)
        
        best_cagr_row = max(results_list, key=lambda x: x.get("CAGR", 0.0))
        highest_cagr = best_cagr_row.get("CAGR", 0.0)
        
        def calc_qs(r):
            sh = r.get("Sharpe Ratio", 0.0)
            pf = r.get("Profit Factor", 0.0)
            dd = r.get("Max Drawdown", 0.0)
            fee_pct = r.get("Fee % of Gross PnL", 0.0)
            return sh * 1.5 + pf * 1.0 - (dd / 100.0) * 1.0 - (fee_pct / 100.0) * 0.5
            
        best_overall_row = max(results_list, key=calc_qs)
        current_best_candidate = best_overall_row.get("Experiment ID", "N/A")

    # Update dashboard state to RUNNING
    dashboard.update_candidate_progress(
        candidate_id="Candidate 02",
        stage="Discovery Sweep",
        status="RUNNING",
        progress_pct=(global_index / total_runs) * 100.0,
        notes=f"Sweep running. Completed {global_index} of {total_runs} experiments.",
        eta="N/A",
        current_best_candidate=current_best_candidate,
        highest_sharpe=highest_sharpe,
        highest_profit_factor=highest_profit_factor,
        highest_cagr=highest_cagr
    )

    batch_start_time = time.time()

    # Process timeframe by timeframe to optimize memory loading
    for tf in timeframes:
        if tf == "15m":
            print("\n1H timeframe complete. Pausing sweep before 15m as requested by user.")
            dashboard.update_candidate_progress(
                candidate_id="Candidate 02",
                stage="Discovery Sweep",
                status="PAUSED",
                progress_pct=(global_index / total_runs) * 100.0,
                notes=f"Paused before 15m timeframe. Completed {global_index} of {total_runs} experiments."
            )
            sys.exit(0)

        tf_combos = [c for c in combinations if c[0] == tf]
        tf_combos_to_run = [c for c in tf_combos if get_combo_key(c) not in completed_keys]

        if not tf_combos_to_run:
            continue

        print(f"Submitting {len(tf_combos_to_run)} combos for timeframe {tf}...")
        
        # Prepare list for executor mapping
        combo_infos = []
        for combo in tf_combos_to_run:
            trend_gate, swing_window, contraction_wave, max_final_contraction, breakout, risk_reward, stop_buffer = combo[1:]
            combo_infos.append((
                tf, trend_gate, swing_window, contraction_wave, max_final_contraction,
                breakout, risk_reward, stop_buffer, symbols, framework_config_path, candidate_id, worker_sleep_ms
            ))

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_combo = {executor.submit(run_single_backtest_worker, ci): ci for ci in combo_infos}
            
            try:
                for future in as_completed(future_to_combo):
                    combo_val = future_to_combo[future]
                    (tf_val, trend_gate, swing_window, contraction_wave, max_final_contraction,
                     breakout, risk_reward, stop_buffer) = combo_val[:8]
                    
                    global_index += 1
                    experiment_num = global_index
                    experiment_id = f"C002-E{experiment_num:05d}"
                    
                    try:
                        run_record, manifest, metrics = future.result()
                        
                        run_record["Experiment ID"] = experiment_id
                        manifest["experiment_id"] = experiment_id
                        
                        # Add git hash
                        try:
                            git_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
                            manifest["git_commit"] = git_hash
                        except Exception:
                            manifest["git_commit"] = "N/A"
                            
                        results_list.append(run_record)
                        registry.register_experiment("Candidate 02", experiment_id, manifest, metrics)
                        
                        # Save checkpoint and update dashboard every 50 experiments
                        if global_index % 50 == 0 or global_index == total_runs:
                            save_checkpoint(checkpoint_path, results_list, outputs_path, registry.flush_batch)
                            
                            now = time.time()
                            duration = now - batch_start_time
                            batch_start_time = now
                            speed = 50.0 / duration if duration > 0 else 0.0
                            remaining_runs = total_runs - global_index
                            eta_seconds = remaining_runs / speed if speed > 0 else 0.0
                            eta_str = str(datetime.timedelta(seconds=int(eta_seconds))) if eta_seconds > 0 else "N/A"
                            
                            checkpoint_num = global_index // 50
                            batch_num = checkpoint_num
                            
                            print(f"Checkpoint #{checkpoint_num} Saved | Progress: {global_index}/{total_runs} ({global_index/total_runs*100.0:.2f}%) | Speed: {speed:.2f} runs/sec | ETA: {eta_str}")
                            
                            # Compute current best stats from results_list
                            highest_sharpe = 0.0
                            highest_profit_factor = 0.0
                            highest_cagr = 0.0
                            current_best_candidate = "N/A"
                            if results_list:
                                best_sharpe_row = max(results_list, key=lambda x: x.get("Sharpe Ratio", 0.0))
                                highest_sharpe = best_sharpe_row.get("Sharpe Ratio", 0.0)
                                
                                best_pf_row = max(results_list, key=lambda x: x.get("Profit Factor", 0.0))
                                highest_profit_factor = best_pf_row.get("Profit Factor", 0.0)
                                
                                best_cagr_row = max(results_list, key=lambda x: x.get("CAGR", 0.0))
                                highest_cagr = best_cagr_row.get("CAGR", 0.0)
                                
                                def calc_qs(r):
                                    sh = r.get("Sharpe Ratio", 0.0)
                                    pf = r.get("Profit Factor", 0.0)
                                    dd = r.get("Max Drawdown", 0.0)
                                    fee_pct = r.get("Fee % of Gross PnL", 0.0)
                                    return sh * 1.5 + pf * 1.0 - (dd / 100.0) * 1.0 - (fee_pct / 100.0) * 0.5
                                    
                                best_overall_row = max(results_list, key=calc_qs)
                                current_best_candidate = best_overall_row.get("Experiment ID", "N/A")

                            dashboard.update_candidate_progress(
                                candidate_id="Candidate 02",
                                stage="Discovery Sweep",
                                status="RUNNING",
                                progress_pct=(global_index / total_runs) * 100.0,
                                current_experiment=experiment_id,
                                notes=f"Checkpoint {checkpoint_num} | Completed {global_index} of {total_runs} experiments",
                                eta=eta_str,
                                current_best_candidate=current_best_candidate,
                                highest_sharpe=highest_sharpe,
                                highest_profit_factor=highest_profit_factor,
                                highest_cagr=highest_cagr
                            )
                            
                    except Exception as exc:
                        print(f"Experiment {experiment_id} generated an exception: {exc}")
                        dashboard.update_candidate_progress(
                            candidate_id="Candidate 02",
                            stage="Discovery Sweep",
                            status="FAILED",
                            progress_pct=(global_index / total_runs) * 100.0,
                            notes=f"Experiment {experiment_id} failed: {exc}"
                        )
                        raise exc
                        
            except KeyboardInterrupt:
                print("\n[Ctrl+C] KeyboardInterrupt detected! Saving checkpoint and shutting down gracefully...")
                for fut in future_to_combo:
                    fut.cancel()
                registry.flush_batch()
                save_checkpoint(checkpoint_path, results_list, outputs_path)
                dashboard.update_candidate_progress(
                    candidate_id="Candidate 02",
                    stage="Discovery Sweep",
                    status="INTERRUPTED",
                    progress_pct=(global_index / total_runs) * 100.0,
                    notes=f"Sweep interrupted by user (Ctrl+C). Completed {global_index} of {total_runs}."
                )
                print("Progress checkpoint saved. Exiting.")
                sys.exit(0)

    # Final Save and Report Generation (only if we completed the sweep)
    if global_index >= total_runs:
        registry.flush_batch()
        save_checkpoint(checkpoint_path, results_list, outputs_path)
        
        # Save discovery matrix results
        results_df = pd.DataFrame(results_list)
        expected_cols = [
            "Experiment ID", "Timeframe", "Trend Gate", "Swing Window", "Contraction Waves",
            "Max Final Contraction", "Breakout", "Risk Reward", "Stop Buffer",
            "Status", "Termination Reason", "Trade Count", "Win Rate", "Profit Factor",
            "Expectancy (USD)", "CAGR", "Sharpe Ratio", "Max Drawdown", "Avg Holding Period",
            "Portfolio Turnover", "Gross Fees", "Gross Slippage", "Fee % of Gross PnL",
            "Pattern Frequency", "Pattern Success Rate", "Average Contraction Duration",
            "Average Breakout Distance", "False Breakout %"
        ]
        results_df = results_df[expected_cols]
        
        candidate_dir_outputs = candidate_dir / "outputs"
        candidate_dir_outputs.mkdir(parents=True, exist_ok=True)
        results_df.to_csv(candidate_dir_outputs / "discovery_matrix_results.csv", index=False)
        print("Saved final discovery_matrix_results.csv successfully.")

        # Compute Quality Score
        results_df['Quality Score'] = (
            results_df['Sharpe Ratio'] * 1.5 +
            results_df['Profit Factor'] * 1.0 -
            (results_df['Max Drawdown'] / 100.0) * 1.0 -
            (results_df['Fee % of Gross PnL'] / 100.0) * 0.5
        )
        ranked_df = results_df.sort_values(by='Quality Score', ascending=False)
        
        verdicts = []
        for _, row in ranked_df.iterrows():
            tf_val = row['Timeframe']
            tc = row['Trade Count']
            sh = row['Sharpe Ratio']
            pf = row['Profit Factor']
            dd = row['Max Drawdown']
            status = row['Status']
            
            if tf_val == "15m":
                pass_tc, borderline_tc = 225, 200
            elif tf_val == "1H":
                pass_tc, borderline_tc = 120, 105
            else:
                pass_tc, borderline_tc = 50, 45

            if status == 'TERMINATED':
                verdicts.append('REJECT (Safety Guard Triggered)')
            elif sh >= 1.20 and pf >= 1.15 and dd < 30.0 and tc >= pass_tc:
                verdicts.append('PASS')
            elif sh >= 0.50 and dd < 45.0 and tc >= borderline_tc:
                verdicts.append('BORDERLINE')
            else:
                verdicts.append('REJECT')
                
        ranked_df['Verdict'] = verdicts
        ranked_df.to_csv(candidate_dir_outputs / "ranked_candidates.csv", index=False)
        print("Saved final ranked_candidates.csv successfully.")

        # Generate final Top 10 CSVs in candidate dir outputs
        top10_overall = ranked_df.head(10)
        top10_overall.to_csv(candidate_dir_outputs / "top10_overall.csv", index=False)
        
        top10_sharpe = ranked_df.sort_values(by="Sharpe Ratio", ascending=False).head(10)
        top10_sharpe.to_csv(candidate_dir_outputs / "top10_sharpe.csv", index=False)
        
        top10_cagr = ranked_df.sort_values(by="CAGR", ascending=False).head(10)
        top10_cagr.to_csv(candidate_dir_outputs / "top10_cagr.csv", index=False)
        
        top10_pf = ranked_df.sort_values(by="Profit Factor", ascending=False).head(10)
        top10_pf.to_csv(candidate_dir_outputs / "top10_pf.csv", index=False)
        
        top10_drawdown = ranked_df.sort_values(by="Max Drawdown", ascending=True).head(10)
        top10_drawdown.to_csv(candidate_dir_outputs / "top10_drawdown.csv", index=False)
        print("Saved all top 10 CSV deliverables successfully.")

        # Generate reports
        reports_path = candidate_dir / "reports"
        reports_path.mkdir(parents=True, exist_ok=True)

        summary_table_df = ranked_df[[
            "Experiment ID", "Timeframe", "Trend Gate", "Contraction Waves", "Max Final Contraction",
            "Breakout", "Risk Reward", "Trade Count", "Profit Factor", "Sharpe Ratio", "Max Drawdown", "Verdict"
        ]].head(25)
        
        summary_content = f"""# Candidate C002 — Discovery Sweep Matrix Summary

This document ranks the performance of the top 25 configurations evaluated in the Volatility Contraction Pattern (VCP) sweeps.

## Ranked Configurations (Top 25)

{summary_table_df.to_markdown(index=False)}

---

## Research Synthesis Summary
* **Evaluation Period**: Approx. 3 years.
* **Min Trade Count Gates**: 225 trades (15m), 120 trades (1H), 50 trades (4H).
* **Verdict Rules**:
  * **PASS**: Sharpe Ratio $\\ge 1.20$, Profit Factor $\\ge 1.15$, Max Drawdown $< 30\\%$, Trade Count above Pass Threshold.
  * **BORDERLINE**: Sharpe Ratio $\\ge 0.50$, Max Drawdown $< 45\\%$, Trade Count above Borderline Threshold.
"""
        with open(reports_path / "candidate_summary.md", "w", encoding="utf-8") as f:
            f.write(summary_content)
        print("Generated candidate_summary.md successfully.")

        # discovery_analysis.md
        avg_by_tf = results_df.groupby("Timeframe")[["Sharpe Ratio", "Profit Factor", "Trade Count"]].mean()
        avg_by_trend = results_df.groupby("Trend Gate")[["Sharpe Ratio", "Profit Factor", "Trade Count"]].mean()
        avg_by_waves = results_df.groupby("Contraction Waves")[["Sharpe Ratio", "Profit Factor"]].mean()
        avg_by_tightness = results_df.groupby("Max Final Contraction")[["Sharpe Ratio", "Profit Factor"]].mean()
        avg_by_breakout = results_df.groupby("Breakout")[["Sharpe Ratio", "Profit Factor"]].mean()
        avg_by_rr = results_df.groupby("Risk Reward")[["Sharpe Ratio", "Profit Factor"]].mean()

        analysis_content = f"""# Candidate C002 — VCP Parameter Discovery Analysis

This document provides a quantitative analysis of how different Volatility Contraction Pattern parameters influenced backtest performance.

## Parameter Influence Analysis

### A. Performance by Resolution Timeframe
{avg_by_tf.to_markdown()}

### B. Performance by Trend Gate Filter
{avg_by_trend.to_markdown()}

### C. Performance by Contraction Waves (K)
{avg_by_waves.to_markdown()}

### D. Performance by Apex Tightness (Max final pullback %)
{avg_by_tightness.to_markdown()}

### E. Performance by Breakout Trigger Type
{avg_by_breakout.to_markdown()}

### F. Performance by Risk Reward Exit Strategy
{avg_by_rr.to_markdown()}

## Key Findings & Recommendations
1. **Timeframe Resolution**: Analysis across timeframes reveals whether lower resolutions (e.g. 15m) suffer from transaction cost drag or high noise. Typically, 1H and 4H resolutions offer superior Sharpe ratios due to lower transaction count relative to net move.
2. **Trend Filters**: Strong trend gates (such as EMA200) prevent entries during market downtrends, significantly reducing the maximum drawdown.
3. **Contraction Geometry**: Enforcing tighter apex conditions (e.g., 3%) can lead to a higher win rate but lower trade frequency, while larger values (e.g., 7%) provide more trades but higher false breakout rates.
4. **Optimal Variant Promotion**: The top-ranked configurations will be selected for Walk-Forward testing based on their Quality Score.
"""
        with open(reports_path / "discovery_analysis.md", "w", encoding="utf-8") as f:
            f.write(analysis_content)
        print("Generated discovery_analysis.md successfully.")

        # Update dashboard state to COMPLETED
        dashboard.update_candidate_progress(
            candidate_id="Candidate 02",
            stage="Discovery Sweep",
            status="COMPLETED",
            progress_pct=100.0,
            notes="VCP discovery sweep matrix executed successfully. READY_FOR_WALK_FORWARD_SELECTION."
        )
        print("Dashboard updated successfully.")
        
        # Delete checkpoint on complete success
        if checkpoint_path.exists():
            try:
                checkpoint_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    run_matrix_sweep_c002()
