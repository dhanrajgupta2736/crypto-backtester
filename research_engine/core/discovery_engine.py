"""Discovery Engine Orchestrator.

Loads datasets, dynamic plugins, generates sweep paths, executes backtesting loops,
applies fees/slippage friction, and routes outputs.
"""

import importlib.util
from pathlib import Path
import sys
from typing import List, Dict, Union
import pandas as pd
import numpy as np
import yaml

from research_engine.core.strategy_interface import BaseStrategyPlugin, InterfaceValidationError


class DiscoveryEngine:
    """The central orchestration engine of the QRP Framework v2.0."""

    def __init__(self, config_path: Union[str, Path] = None) -> None:
        """Initialize the Discovery Engine with framework configs."""
        self.configs: dict = {}
        self.active_plugin: BaseStrategyPlugin = None
        self._load_configs(config_path)

    def _load_configs(self, config_path: Union[str, Path] = None) -> None:
        """Load internal settings and fee templates from configs/framework_config.yaml."""
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent / "configs" / "framework_config.yaml"
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.configs = yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load framework config: {e}")
            self.configs = {
                "execution": {
                    "initial_capital": 10000.0,
                    "costs": {
                        "default_taker_fee": 0.00045,
                        "default_maker_fee": 0.00015,
                        "default_slippage": 0.0005
                    }
                }
            }

    def load_dataset(self, symbols: List[str], timeframe: str) -> Dict[str, pd.DataFrame]:
        """Load historical bar database for specified symbols and timeframe.
        
        Args:
            symbols (list): List of asset symbols (str).
            timeframe (str): Resampling resolution (e.g. '1H').
            
        Returns:
            dict: Map of asset symbols to historical DataFrames.
        """
        universe = {}
        data_root = Path(self.configs.get("paths", {}).get("historical_data_dir", "./data"))
        
        for sym in symbols:
            ticker_dir = data_root / sym
            if not ticker_dir.is_dir():
                continue
                
            possible_names = [
                f"{sym}_{timeframe}.csv",
                f"{sym}_{timeframe.upper()}.csv",
                f"{sym}_{timeframe.lower()}.csv",
            ]
            
            filepath = None
            for name in possible_names:
                path = ticker_dir / name
                if path.exists():
                    filepath = path
                    break
            
            if not filepath:
                continue
                
            try:
                df = pd.read_csv(filepath)
                # Standardize column naming
                date_col = None
                for col in df.columns:
                    if col.lower() in ['date', 'timestamp', 'time']:
                        date_col = col
                        break
                
                if date_col:
                    df.rename(columns={date_col: 'timestamp'}, inplace=True)
                    
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                df.set_index('timestamp', inplace=True)
                df = df[~df.index.duplicated(keep='first')]
                df.sort_index(inplace=True)
                
                # Standardize values
                col_map = {}
                for col in df.columns:
                    if col.lower() in ['open', 'high', 'low', 'close', 'volume']:
                        col_map[col] = col.lower()
                df.rename(columns=col_map, inplace=True)
                
                df = df[['open', 'high', 'low', 'close', 'volume']]
                # Ensure float data types
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                
                universe[sym] = df
            except Exception as e:
                print(f"Error loading {sym}: {e}")
                
        return universe

    def load_plugin(self, candidate_id: str) -> BaseStrategyPlugin:
        """Dynamically import and instantiate the candidate strategy plugin.
        
        Args:
            candidate_id (str): The ID of the strategy folder (e.g. 'candidate_01_relative_strength').
            
        Returns:
            BaseStrategyPlugin: An instantiated strategy plugin object.
            
        Raises:
            InterfaceValidationError: If the plugin violates the BaseStrategyPlugin contract.
        """
        yaml_path = Path("research") / candidate_id / "configs" / "candidate.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"Candidate configuration not found: {yaml_path}")
            
        with open(yaml_path, "r", encoding="utf-8") as f:
            candidate_config = yaml.safe_load(f)
            
        plugin_config = candidate_config.get("candidate", {}).get("plugin", {})
        module_path = plugin_config.get("module_path")
        class_name = plugin_config.get("class_name", "StrategyPlugin")
        
        abs_module_path = Path(module_path).resolve()
        if not abs_module_path.exists():
            raise FileNotFoundError(f"Strategy plugin file not found: {abs_module_path}")
            
        spec = importlib.util.spec_from_file_location("strategy_plugin_module", abs_module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["strategy_plugin_module"] = module
        spec.loader.exec_module(module)
        
        if not hasattr(module, class_name):
            raise InterfaceValidationError(f"Class {class_name} not found in plugin module.")
            
        strategy_class = getattr(module, class_name)
        plugin_instance = strategy_class()
        
        if not isinstance(plugin_instance, BaseStrategyPlugin):
            raise InterfaceValidationError("Plugin class does not inherit from BaseStrategyPlugin")
            
        self.active_plugin = plugin_instance
        return plugin_instance

    def simulate_backtest(self, universe_data: dict, parameters: dict) -> Dict[str, Union[pd.DataFrame, pd.Series, str, int, float]]:
        """Run portfolio backtest simulation with safety validations and early termination guards.
        
        Args:
            universe_data (dict): Dict mapping asset symbols to preprocessed signal DataFrames.
            parameters (dict): The parameter configuration dictionary for this run.
            
        Returns:
            dict: Contains 'status', 'termination_reason', 'last_processed_candle',
                  'trade_ledger', 'equity_curve', and other performance metrics.
        """
        initial_capital = self.configs.get("execution", {}).get("initial_capital", 10000.0)
        costs = self.configs.get("execution", {}).get("costs", {})
        taker_fee_rate = costs.get("default_taker_fee", 0.00045)
        slippage_rate = costs.get("default_slippage", 0.0005)
        
        k = parameters.get("portfolio_size_k", 3)
        
        symbols = list(universe_data.keys())
        first_sym = symbols[0]
        timestamps = universe_data[first_sym].index
        
        close_dict = {}
        signal_dict = {}
        for sym in symbols:
            close_dict[sym] = universe_data[sym]['close']
            signal_dict[sym] = universe_data[sym]['signal']
            
        close_df = pd.DataFrame(close_dict)
        signal_df = pd.DataFrame(signal_dict)
        
        cash = initial_capital
        positions = {sym: 0.0 for sym in symbols}
        equity_history = []
        trades = []
        active_trades = {}
        
        status = "COMPLETED"
        termination_reason = "N/A"
        last_processed_candle = "N/A"
        
        rebalance_starts = parameters.get("lookback_window", 50)
        
        for idx in range(len(timestamps)):
            t = timestamps[idx]
            last_processed_candle = str(t)
            close_prices = close_df.loc[t]
            
            # Update Portfolio Value
            current_asset_value = sum(positions[sym] * close_prices[sym] for sym in symbols)
            portfolio_value = cash + current_asset_value
            
            # Accounting Check: NaN or Infinite
            if np.isnan(portfolio_value) or np.isinf(portfolio_value):
                status = "FAILED"
                termination_reason = "NaN or Infinite portfolio equity detected."
                equity_history.append((t, 0.0))
                # Close out active trades at last known price
                for sym, trade_record in list(active_trades.items()):
                    trade_record["exit_timestamp"] = t
                    trade_record["exit_price"] = close_prices[sym]
                    trade_record["exit_reason"] = "ACCOUNTING_FAILURE"
                    trades.append(trade_record)
                active_trades.clear()
                break
                
            # Accounting Check: Negative cash (with small tolerance)
            if cash < -0.01:
                status = "FAILED"
                termination_reason = f"Negative cash balance detected: {cash} USD."
                equity_history.append((t, portfolio_value))
                # Close out active trades
                for sym, trade_record in list(active_trades.items()):
                    qty_sold = positions[sym]
                    exec_price = close_prices[sym] * (1.0 - slippage_rate)
                    fee = qty_sold * close_prices[sym] * taker_fee_rate
                    slippage_cost = qty_sold * close_prices[sym] * slippage_rate
                    trade_record["exit_timestamp"] = t
                    trade_record["exit_price"] = close_prices[sym]
                    trade_record["fees_paid"] += fee
                    trade_record["slippage_paid"] += slippage_cost
                    trade_record["pnl_nominal"] = (qty_sold * close_prices[sym]) - (trade_record["qty"] * trade_record["entry_price"]) - trade_record["fees_paid"] - trade_record["slippage_paid"]
                    trade_record["pnl_r"] = (trade_record["pnl_nominal"] / (trade_record["qty"] * trade_record["entry_price"])) * 100.0
                    trade_record["exit_reason"] = "ACCOUNTING_FAILURE"
                    trades.append(trade_record)
                active_trades.clear()
                break

            # Equity Safety Guard
            if portfolio_value <= 0:
                status = "TERMINATED"
                termination_reason = "Portfolio equity reached zero or negative."
                equity_history.append((t, portfolio_value))
                # Liquidate all remaining open positions immediately
                for sym, trade_record in list(active_trades.items()):
                    qty_sold = positions[sym]
                    exec_price = close_prices[sym] * (1.0 - slippage_rate)
                    fee = qty_sold * close_prices[sym] * taker_fee_rate
                    slippage_cost = qty_sold * close_prices[sym] * slippage_rate
                    trade_record["exit_timestamp"] = t
                    trade_record["exit_price"] = close_prices[sym]
                    trade_record["fees_paid"] += fee
                    trade_record["slippage_paid"] += slippage_cost
                    trade_record["pnl_nominal"] = (qty_sold * close_prices[sym]) - (trade_record["qty"] * trade_record["entry_price"]) - trade_record["fees_paid"] - trade_record["slippage_paid"]
                    trade_record["pnl_r"] = (trade_record["pnl_nominal"] / (trade_record["qty"] * trade_record["entry_price"])) * 100.0
                    trade_record["exit_reason"] = "LIQUIDATION"
                    trades.append(trade_record)
                active_trades.clear()
                break

            # If clean, append to equity curve
            equity_history.append((t, portfolio_value))
            
            # Skip rebalancing before warm-up lookback
            if idx < rebalance_starts:
                continue
                
            # Skip rebalancing if not on frequency schedule R
            rebalance_freq = parameters.get("rebalance_frequency_r", 1)
            if (idx - rebalance_starts) % rebalance_freq != 0:
                continue
                
            # Current signals
            signals = signal_df.loc[t]
            target_symbols = [sym for sym in symbols if signals[sym] == 1.0]
            target_symbols = target_symbols[:k]
            
            currently_held = [sym for sym in symbols if positions[sym] > 0.0]
            
            # A. Sells / Liquidations
            for sym in currently_held:
                if sym not in target_symbols:
                    qty_sold = positions[sym]
                    if qty_sold <= 0:
                        continue
                    exec_price = close_prices[sym] * (1.0 - slippage_rate)
                    nominal_value = qty_sold * close_prices[sym]
                    fee = nominal_value * taker_fee_rate
                    slippage_cost = nominal_value * slippage_rate
                    cash_received = qty_sold * exec_price - fee
                    
                    cash += cash_received
                    positions[sym] = 0.0
                    
                    trade_record = active_trades.pop(sym)
                    trade_record["exit_timestamp"] = t
                    trade_record["exit_price"] = close_prices[sym]
                    trade_record["fees_paid"] += fee
                    trade_record["slippage_paid"] += slippage_cost
                    entry_val = trade_record["qty"] * trade_record["entry_price"]
                    exit_val = qty_sold * close_prices[sym]
                    trade_record["pnl_nominal"] = exit_val - entry_val - trade_record["fees_paid"] - trade_record["slippage_paid"]
                    trade_record["pnl_r"] = (trade_record["pnl_nominal"] / entry_val) * 100.0
                    trades.append(trade_record)
            
            # B. Equal Weight Rebalancing
            active_targets_count = len(target_symbols)
            if active_targets_count > 0:
                target_value = portfolio_value / active_targets_count
            else:
                target_value = 0.0
                
            # Perform position reductions
            for sym in target_symbols:
                if positions[sym] > 0.0:
                    if close_prices[sym] <= 0:
                        continue
                    current_val = positions[sym] * close_prices[sym]
                    if current_val > target_value:
                        excess_val = current_val - target_value
                        qty_sold = excess_val / close_prices[sym]
                        if qty_sold <= 0:
                            continue
                        exec_price = close_prices[sym] * (1.0 - slippage_rate)
                        fee = excess_val * taker_fee_rate
                        slippage_cost = excess_val * slippage_rate
                        cash_received = qty_sold * exec_price - fee
                        
                        cash += cash_received
                        positions[sym] -= qty_sold
                        
                        if sym in active_trades:
                            # Log the partial exit portion as a completed trade record
                            partial_trade = active_trades[sym].copy()
                            partial_trade["qty"] = qty_sold
                            partial_trade["exit_timestamp"] = t
                            partial_trade["exit_price"] = close_prices[sym]
                            partial_trade["fees_paid"] = fee
                            partial_trade["slippage_paid"] = slippage_cost
                            
                            entry_val = qty_sold * partial_trade["entry_price"]
                            exit_val = qty_sold * close_prices[sym]
                            partial_trade["pnl_nominal"] = exit_val - entry_val - fee - slippage_cost
                            partial_trade["pnl_r"] = (partial_trade["pnl_nominal"] / entry_val) * 100.0 if entry_val > 0 else 0.0
                            partial_trade["exit_reason"] = "REBALANCE_REDUCTION"
                            partial_trade["trade_id"] = f"{active_trades[sym]['trade_id']}-P"
                            
                            trades.append(partial_trade)
                            
                            # Decrease remaining quantity in active tracking
                            active_trades[sym]["qty"] = max(0.0, active_trades[sym]["qty"] - qty_sold)
            
            # Perform buys/increases
            for sym in target_symbols:
                if close_prices[sym] <= 0:
                    continue
                current_val = positions[sym] * close_prices[sym]
                if current_val < target_value:
                    if portfolio_value <= 0:
                        continue
                    
                    deficit_val = target_value - current_val
                    if deficit_val <= 0:
                        continue
                        
                    q = deficit_val / (close_prices[sym] * (1.0 + slippage_rate + taker_fee_rate))
                    if q <= 0:
                        continue
                        
                    nominal_cost = q * close_prices[sym]
                    fee = nominal_cost * taker_fee_rate
                    slippage_cost = nominal_cost * slippage_rate
                    cash_spent = nominal_cost * (1.0 + slippage_rate) + fee
                    
                    # Prevent execution if cash spent would exceed available cash
                    if cash_spent > cash:
                        cash_spent = cash
                        q = cash_spent / (close_prices[sym] * (1.0 + slippage_rate + taker_fee_rate))
                        if q <= 0:
                            continue
                        nominal_cost = q * close_prices[sym]
                        fee = nominal_cost * taker_fee_rate
                        slippage_cost = nominal_cost * slippage_rate
                        
                    cash -= cash_spent
                    positions[sym] += q
                    
                    if sym not in active_trades:
                        active_trades[sym] = {
                            "trade_id": f"T-{len(trades) + len(active_trades) + 1:05d}",
                            "asset": sym,
                            "direction": "LONG",
                            "entry_timestamp": t,
                            "entry_price": close_prices[sym],
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
                        active_trades[sym]["fees_paid"] += fee
                        active_trades[sym]["slippage_paid"] += slippage_cost
                        prev_qty = active_trades[sym]["qty"]
                        prev_price = active_trades[sym]["entry_price"]
                        new_qty = prev_qty + q
                        blended_price = (prev_qty * prev_price + q * close_prices[sym]) / new_qty
                        active_trades[sym]["qty"] = new_qty
                        active_trades[sym]["entry_price"] = blended_price

        # If completed normally
        if status == "COMPLETED":
            end_time = timestamps[-1]
            final_prices = close_df.loc[end_time]
            for sym, trade_record in list(active_trades.items()):
                qty_sold = positions[sym]
                exec_price = final_prices[sym] * (1.0 - slippage_rate)
                nominal_value = qty_sold * final_prices[sym]
                fee = nominal_value * taker_fee_rate
                slippage_cost = nominal_value * slippage_rate
                
                trade_record["exit_timestamp"] = end_time
                trade_record["exit_price"] = final_prices[sym]
                trade_record["fees_paid"] += fee
                trade_record["slippage_paid"] += slippage_cost
                
                entry_val = trade_record["qty"] * trade_record["entry_price"]
                exit_val = qty_sold * final_prices[sym]
                trade_record["pnl_nominal"] = exit_val - entry_val - trade_record["fees_paid"] - trade_record["slippage_paid"]
                trade_record["pnl_r"] = (trade_record["pnl_nominal"] / entry_val) * 100.0
                
                trades.append(trade_record)
                
        trade_ledger = pd.DataFrame(trades)
        if trade_ledger.empty:
            trade_ledger = pd.DataFrame(columns=[
                'trade_id', 'asset', 'direction', 'entry_timestamp', 'entry_price',
                'qty', 'exit_timestamp', 'exit_price', 'exit_reason', 'pnl_nominal',
                'pnl_r', 'fees_paid', 'slippage_paid'
            ])
            
        eq_dates, eq_vals = zip(*equity_history)
        equity_curve = pd.Series(eq_vals, index=eq_dates, name="portfolio_equity")
        
        number_of_rebalances = max(0, len(equity_history) - rebalance_starts)
        
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
