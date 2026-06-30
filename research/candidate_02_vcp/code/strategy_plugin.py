"""Candidate C002 Volatility Contraction Pattern (VCP) Strategy Plugin.

Implements a deterministic mathematical VCP breakout strategy with trend gating,
pullback contraction waves, and custom stop/exit logic.
"""

import pandas as pd
import numpy as np
from research_engine.core.strategy_interface import BaseStrategyPlugin


def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)


class StrategyPlugin(BaseStrategyPlugin):
    """Strategy Plugin for Candidate C002 (Volatility Contraction Pattern)."""

    def __init__(self):
        super().__init__()
        self.all_trades_info = []

    @property
    def metadata(self) -> dict:
        return {
            "candidate_id": "C002",
            "name": "Volatility Contraction Pattern",
            "version": "0.1",
            "author": "Quant Team",
            "description": "Systematic Volatility Contraction Pattern (VCP) strategy "
                           "with deterministic swing contraction, trend filters, and exits."
        }

    @property
    def parameter_space(self) -> dict:
        return {
            "trend_gate": ["None", "EMA100", "EMA200", "HH_HL", "Donchian"],
            "swing_window": [3, 5, 7],
            "contraction_waves": [2, 3],
            "max_final_contraction": [0.03, 0.05, 0.07],
            "breakout": ["Close_Above_Swing_High", "High_Break", "Donchian_Break"],
            "risk_reward": ["1R", "1.5R", "2R", "3R", "ATR_Trail", "Swing_Trail", "30_Bar_Time_Exit"],
            "stop_buffer": [0.0, 0.0005, 0.0010]
        }

    def preprocess(self, universe_data: dict) -> dict:
        """Align all asset timestamps and fill any data gaps to ensure uniform cross-sections."""
        if not universe_data:
            return universe_data

        close_dict = {}
        for symbol, df in universe_data.items():
            close_dict[symbol] = df['close']
        
        close_df = pd.DataFrame(close_dict)
        close_df = close_df.ffill().bfill()

        aligned_universe = {}
        for symbol, df in universe_data.items():
            aligned_df = df.reindex(close_df.index)
            aligned_df['close'] = close_df[symbol]
            aligned_df = aligned_df.ffill().bfill()
            
            # Precompute reusable calculations once and cache them in columns
            aligned_df['ema100'] = aligned_df['close'].ewm(span=100, adjust=False).mean()
            aligned_df['ema200'] = aligned_df['close'].ewm(span=200, adjust=False).mean()
            
            # Donchian midpoint (50-bar)
            rolling_max_50 = aligned_df['high'].rolling(50).max()
            rolling_min_50 = aligned_df['low'].rolling(50).min()
            aligned_df['donchian_mid'] = (rolling_max_50 + rolling_min_50) / 2.0
            
            # Donchian channel 20-bar high (for breakout, shifted 1)
            aligned_df['donchian_high_20'] = aligned_df['high'].rolling(20).max().shift(1)
            
            # ATR 14
            tr = true_range(aligned_df)
            aligned_df['atr14'] = tr.rolling(14).mean()
            
            # Swing points for windows [3, 5, 7]
            for w in [3, 5, 7]:
                aligned_df[f'is_sh_{w}'] = (aligned_df['high'] == aligned_df['high'].rolling(2 * w + 1, center=True).max())
                aligned_df[f'is_sl_{w}'] = (aligned_df['low'] == aligned_df['low'].rolling(2 * w + 1, center=True).min())
            
            aligned_universe[symbol] = aligned_df

        return aligned_universe


    def generate_signals(self, universe_data: dict, parameters: dict) -> dict:
        """Core VCP signal generation logic. Runs a fast path-dependent simulation for each asset."""
        if not universe_data:
            return universe_data

        # Infer timeframe from index frequency
        first_df = next(iter(universe_data.values()))
        if len(first_df) > 1:
            diff = first_df.index[1] - first_df.index[0]
            minutes = diff.total_seconds() / 60.0
            if minutes <= 16.0:
                tf = "15m"
            elif minutes <= 61.0:
                tf = "1H"
            else:
                tf = "4H"
        else:
            tf = "1H"

        # Timeframe-adaptive minimum wave depths
        if tf == "15m":
            min_d1_limit = 0.015  # 1.5% min depth for Wave 1
            min_dK_limit = 0.003  # 0.3% min depth for Wave K
        elif tf == "1H":
            min_d1_limit = 0.030  # 3.0% min depth for Wave 1
            min_dK_limit = 0.005  # 0.5% min depth for Wave K
        else:  # 4H
            min_d1_limit = 0.050  # 5.0% min depth for Wave 1
            min_dK_limit = 0.008  # 0.8% min depth for Wave K

        trend_type = parameters.get("trend_gate", "None")
        W_s = parameters.get("swing_window", 5)
        K = parameters.get("contraction_waves", 2)
        max_final_contraction = parameters.get("max_final_contraction", 0.05)
        breakout_type = parameters.get("breakout", "Close_Above_Swing_High")
        risk_reward = parameters.get("risk_reward", "2R")
        stop_buffer = parameters.get("stop_buffer", 0.0005)

        self.all_trades_info = []

        for symbol, df in universe_data.items():
            n = len(df)
            if n < 100:
                df['signal'] = 0.0
                continue

            # Retrieve cached precalculated indicators from columns
            close_arr = df['close'].to_numpy()
            high_arr = df['high'].to_numpy()
            low_arr = df['low'].to_numpy()

            ema100_arr = df['ema100'].to_numpy()
            ema200_arr = df['ema200'].to_numpy()
            donchian_mid_arr = df['donchian_mid'].to_numpy()
            donchian_high_20 = df['donchian_high_20'].to_numpy()
            atr14_arr = df['atr14'].to_numpy()

            is_sh = df[f'is_sh_{W_s}'].to_numpy()
            is_sl = df[f'is_sl_{W_s}'].to_numpy()

            sh_indices = np.where(is_sh)[0]
            sl_indices = np.where(is_sl)[0]

            sh_ptrs = np.searchsorted(sh_indices, np.arange(n) - W_s, side='right')
            sl_ptrs = np.searchsorted(sl_indices, np.arange(n) - W_s, side='right')

            signal_arr = np.zeros(n)

            # State machine variables
            position = 0
            entry_price = 0.0
            stop_loss = 0.0
            take_profit = None
            bars_held = 0
            trailing_stop_val = 0.0
            
            # Pattern tracking temporary variables
            entry_idx = 0
            pattern_idx_sh1 = 0
            pattern_max_SH = 0.0
            last_entered_sl_idx = -1

            # Caching variables
            last_sh_ptr = -1
            last_sl_ptr = -1
            pattern_valid = False
            max_SH = 0.0
            stop_loss_base = 0.0
            stop_loss_base_idx = -1
            trend_hh_hl = False
            cached_idx_sh1 = -1

            for t in range(20, n):
                sh_ptr = sh_ptrs[t]
                sl_ptr = sl_ptrs[t]

                if position == 0:
                    # Look for pattern setup
                    if sh_ptr < K or sl_ptr < K:
                        continue

                    # If pointers haven't changed, reuse checks (except pattern width)
                    if sh_ptr == last_sh_ptr and sl_ptr == last_sl_ptr:
                        if not pattern_valid or (t - cached_idx_sh1 > 150):
                            continue
                    else:
                        last_sh_ptr = sh_ptr
                        last_sl_ptr = sl_ptr

                        # Extract latest swing indices
                        if K == 2:
                            idx_sh1 = sh_indices[sh_ptr - 2]
                            idx_sh2 = sh_indices[sh_ptr - 1]
                            idx_sl1 = sl_indices[sl_ptr - 2]
                            idx_sl2 = sl_indices[sl_ptr - 1]
                            chronological = (idx_sh1 < idx_sl1 < idx_sh2 < idx_sl2)
                        else:  # K == 3
                            idx_sh1 = sh_indices[sh_ptr - 3]
                            idx_sh2 = sh_indices[sh_ptr - 2]
                            idx_sh3 = sh_indices[sh_ptr - 1]
                            idx_sl1 = sl_indices[sl_ptr - 3]
                            idx_sl2 = sl_indices[sl_ptr - 2]
                            idx_sl3 = sl_indices[sl_ptr - 1]
                            chronological = (idx_sh1 < idx_sl1 < idx_sh2 < idx_sl2 < idx_sh3 < idx_sl3)

                        cached_idx_sh1 = idx_sh1

                        if not chronological:
                            pattern_valid = False
                            continue

                        # Maximum width check: entire pattern must fit within 150 bars
                        if t - idx_sh1 > 150:
                            pattern_valid = False
                            continue

                        # Depth calculation and contraction check
                        if K == 2:
                            SH1, SL1 = high_arr[idx_sh1], low_arr[idx_sl1]
                            SH2, SL2 = high_arr[idx_sh2], low_arr[idx_sl2]
                            if SH1 <= 0 or SH2 <= 0:
                                pattern_valid = False
                                continue
                            D1 = (SH1 - SL1) / SH1
                            D2 = (SH2 - SL2) / SH2
                            
                            pattern_valid = (D1 >= min_d1_limit) and (D2 >= min_dK_limit) and (D2 < D1) and (D2 <= max_final_contraction)
                            max_SH = max(SH1, SH2)
                            stop_loss_base = SL2
                            stop_loss_base_idx = idx_sl2
                            trend_hh_hl = (high_arr[idx_sh2] > high_arr[idx_sh1]) and (low_arr[idx_sl2] > low_arr[idx_sl1])
                        else:  # K == 3
                            SH1, SL1 = high_arr[idx_sh1], low_arr[idx_sl1]
                            SH2, SL2 = high_arr[idx_sh2], low_arr[idx_sl2]
                            SH3, SL3 = high_arr[idx_sh3], low_arr[idx_sl3]
                            if SH1 <= 0 or SH2 <= 0 or SH3 <= 0:
                                pattern_valid = False
                                continue
                            D1 = (SH1 - SL1) / SH1
                            D2 = (SH2 - SL2) / SH2
                            D3 = (SH3 - SL3) / SH3
                            
                            pattern_valid = (D1 >= min_d1_limit) and (D3 >= min_dK_limit) and (D3 < D2 < D1) and (D3 <= max_final_contraction)
                            max_SH = max(SH1, SH2, SH3)
                            stop_loss_base = SL3
                            stop_loss_base_idx = idx_sl3
                            trend_hh_hl = (high_arr[idx_sh3] > high_arr[idx_sh2]) and (low_arr[idx_sl3] > low_arr[idx_sl2])

                        if not pattern_valid:
                            continue

                    if stop_loss_base_idx <= last_entered_sl_idx:
                        continue

                    # Trend Gate check
                    trend_ok = False
                    if trend_type == "None":
                        trend_ok = True
                    elif trend_type == "EMA100":
                        trend_ok = (close_arr[t] > ema100_arr[t])
                    elif trend_type == "EMA200":
                        trend_ok = (close_arr[t] > ema200_arr[t])
                    elif trend_type == "HH_HL":
                        trend_ok = trend_hh_hl
                    elif trend_type == "Donchian":
                        trend_ok = (close_arr[t] > donchian_mid_arr[t]) and (donchian_mid_arr[t] > donchian_mid_arr[t-1])

                    if not trend_ok:
                        continue

                    # Breakout check
                    breakout_triggered = False
                    if breakout_type == "Close_Above_Swing_High":
                        breakout_triggered = (close_arr[t] > max_SH) and (close_arr[t-1] <= max_SH)
                    elif breakout_type == "High_Break":
                        breakout_triggered = (high_arr[t] > max_SH) and (high_arr[t-1] <= max_SH)
                    elif breakout_type == "Donchian_Break":
                        if not pd.isna(donchian_high_20[t]):
                            breakout_triggered = (close_arr[t] > donchian_high_20[t])

                    if not breakout_triggered:
                        continue

                    # Entry execution
                    stop_loss_val = stop_loss_base * (1.0 - stop_buffer)
                    if close_arr[t] <= stop_loss_val:
                        continue  # Avoid negative/zero risk trades

                    position = 1
                    entry_price = close_arr[t]
                    stop_loss = stop_loss_val
                    bars_held = 0
                    last_entered_sl_idx = stop_loss_base_idx
                    
                    # Calculate fixed targets
                    risk = entry_price - stop_loss
                    if risk_reward == "1R":
                        take_profit = entry_price + 1.0 * risk
                    elif risk_reward == "1.5R":
                        take_profit = entry_price + 1.5 * risk
                    elif risk_reward == "2R":
                        take_profit = entry_price + 2.0 * risk
                    elif risk_reward == "3R":
                        take_profit = entry_price + 3.0 * risk
                    else:
                        take_profit = None

                    trailing_stop_val = stop_loss
                    entry_idx = t
                    pattern_idx_sh1 = idx_sh1
                    pattern_max_SH = max_SH

                    signal_arr[t] = 1.0

                elif position == 1:
                    bars_held += 1
                    signal_arr[t] = 1.0

                    # Exit condition evaluation
                    exit_triggered = False

                    # 1. Stop Loss check
                    if low_arr[t] <= stop_loss:
                        exit_triggered = True

                    # 2. Take Profit check
                    if not exit_triggered and take_profit is not None:
                        if high_arr[t] >= take_profit:
                            exit_triggered = True

                    # 3. ATR Trail check
                    if not exit_triggered and risk_reward == "ATR_Trail":
                        if not pd.isna(atr14_arr[t]):
                            trailing_stop_val = max(trailing_stop_val, high_arr[t] - 2.5 * atr14_arr[t])
                        if low_arr[t] <= trailing_stop_val:
                            exit_triggered = True

                    # 4. Swing Trail check
                    if not exit_triggered and risk_reward == "Swing_Trail":
                        lowest_10 = np.min(low_arr[max(0, t - 9):t + 1])
                        trailing_stop_val = max(trailing_stop_val, lowest_10)
                        if low_arr[t] <= trailing_stop_val:
                            exit_triggered = True

                    # 5. Time Exit check
                    if not exit_triggered and (risk_reward == "30-Bar Time Exit" or bars_held >= 300):
                        # hard cap of 300 bars just to prevent infinite trade lock
                        if bars_held >= 30:
                            exit_triggered = True

                    if exit_triggered:
                        position = 0
                        signal_arr[t] = 0.0
                        
                        # Record completed trade metrics
                        exit_val = close_arr[t]
                        is_win = (exit_val > entry_price)
                        is_false_breakout = (exit_val < entry_price)

                        self.all_trades_info.append({
                            "symbol": symbol,
                            "entry_idx": entry_idx,
                            "exit_idx": t,
                            "contraction_duration": entry_idx - pattern_idx_sh1,
                            "breakout_distance": ((entry_price - pattern_max_SH) / pattern_max_SH * 100.0) if pattern_max_SH > 0 else 0.0,
                            "is_win": is_win,
                            "is_false_breakout": is_false_breakout
                        })

            df['signal'] = signal_arr

        return universe_data

    def get_custom_metrics(self) -> dict:
        """Aggregate custom performance metrics from the simulated trades."""
        if not self.all_trades_info:
            return {
                "Pattern Frequency": 0.0,
                "Pattern Success Rate": 0.0,
                "Average Contraction Duration": 0.0,
                "Average Breakout Distance": 0.0,
                "False Breakout %": 0.0
            }

        total_trades = len(self.all_trades_info)
        win_trades = sum(1 for tr in self.all_trades_info if tr['is_win'])
        false_breakouts = sum(1 for tr in self.all_trades_info if tr['is_false_breakout'])

        pattern_freq = total_trades
        success_rate = (win_trades / total_trades * 100.0)
        avg_duration = np.mean([tr['contraction_duration'] for tr in self.all_trades_info])
        avg_distance = np.mean([tr['breakout_distance'] for tr in self.all_trades_info])
        false_breakout_pct = (false_breakouts / total_trades * 100.0)

        return {
            "Pattern Frequency": float(pattern_freq),
            "Pattern Success Rate": float(success_rate),
            "Average Contraction Duration": float(avg_duration),
            "Average Breakout Distance": float(avg_distance),
            "False Breakout %": float(false_breakout_pct)
        }
