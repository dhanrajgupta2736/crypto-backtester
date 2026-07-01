"""Candidate C002 Volatility Contraction Pattern (VCP) Strategy Plugin.

Implements a deterministic mathematical VCP breakout strategy with trend gating,
pullback contraction waves, and custom stop/exit logic. Supports exactly 2, exactly 3,
and adaptive (2 or more) contraction waves.
"""

import pandas as pd
import numpy as np
from research_engine.core.strategy_interface import BaseStrategyPlugin


def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)


class StrategyPlugin(BaseStrategyPlugin):
    """Strategy Plugin for Candidate C002 (Volatility Contraction Pattern) V3."""

    def __init__(self):
        super().__init__()
        self.all_trades_info = []

    @property
    def metadata(self) -> dict:
        return {
            "candidate_id": "C002_V3",
            "name": "Volatility Contraction Pattern V3",
            "version": "0.3",
            "author": "Quant Team",
            "description": "Volatility Contraction Pattern (VCP) strategy V3 "
                           "with adaptive wave counts (2 or more contraction waves)."
        }

    @property
    def parameter_space(self) -> dict:
        return {
            "trend_gate": ["None", "EMA100", "EMA200", "HH_HL", "Donchian"],
            "swing_window": [3, 5, 7],
            "contraction_waves": [2, 3, "adaptive"],
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
            
            aligned_df['ema100'] = aligned_df['close'].ewm(span=100, adjust=False).mean()
            aligned_df['ema200'] = aligned_df['close'].ewm(span=200, adjust=False).mean()
            
            rolling_max_50 = aligned_df['high'].rolling(50).max()
            rolling_min_50 = aligned_df['low'].rolling(50).min()
            aligned_df['donchian_mid'] = (rolling_max_50 + rolling_min_50) / 2.0
            
            aligned_df['donchian_high_20'] = aligned_df['high'].rolling(20).max().shift(1)
            
            tr = true_range(aligned_df)
            aligned_df['atr14'] = tr.rolling(14).mean()
            
            for w in [3, 5, 7]:
                aligned_df[f'is_sh_{w}'] = (aligned_df['high'] == aligned_df['high'].rolling(2 * w + 1, center=True).max())
                aligned_df[f'is_sl_{w}'] = (aligned_df['low'] == aligned_df['low'].rolling(2 * w + 1, center=True).min())
            
            aligned_universe[symbol] = aligned_df

        return aligned_universe

    def generate_signals(self, universe_data: dict, parameters: dict) -> dict:
        """Core VCP signal generation logic supporting adaptive wave structures."""
        if not universe_data:
            return universe_data

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

        if tf == "15m":
            min_d1_limit = 0.015
            min_dK_limit = 0.003
        elif tf == "1H":
            min_d1_limit = 0.030
            min_dK_limit = 0.005
        else:
            min_d1_limit = 0.050
            min_dK_limit = 0.008

        trend_type = parameters.get("trend_gate", "None")
        W_s = parameters.get("swing_window", 5)
        K = parameters.get("contraction_waves", 3)  # Can be 2, 3, or "adaptive"
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

            position = 0
            entry_price = 0.0
            stop_loss = 0.0
            take_profit = None
            bars_held = 0
            trailing_stop_val = 0.0
            
            entry_idx = 0
            pattern_idx_sh1 = 0
            pattern_max_SH = 0.0
            last_entered_sl_idx = -1

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
                    if sh_ptr < 2 or sl_ptr < 2:
                        continue

                    if sh_ptr == last_sh_ptr and sl_ptr == last_sl_ptr:
                        if not pattern_valid or (t - cached_idx_sh1 > 150):
                            continue
                    else:
                        last_sh_ptr = sh_ptr
                        last_sl_ptr = sl_ptr

                        # Support adaptive waves
                        is_3_wave_valid = False
                        is_2_wave_valid = False
                        
                        # 1. Try 3-wave check
                        if K == 3 or K == "adaptive":
                            if sh_ptr >= 3 and sl_ptr >= 3:
                                idx_sh1_3 = sh_indices[sh_ptr - 3]
                                idx_sh2_3 = sh_indices[sh_ptr - 2]
                                idx_sh3_3 = sh_indices[sh_ptr - 1]
                                idx_sl1_3 = sl_indices[sl_ptr - 3]
                                idx_sl2_3 = sl_indices[sl_ptr - 2]
                                idx_sl3_3 = sl_indices[sl_ptr - 1]
                                if (idx_sh1_3 < idx_sl1_3 < idx_sh2_3 < idx_sl2_3 < idx_sh3_3 < idx_sl3_3) and (t - idx_sh1_3 <= 150):
                                    SH1_3, SL1_3 = high_arr[idx_sh1_3], low_arr[idx_sl1_3]
                                    SH2_3, SL2_3 = high_arr[idx_sh2_3], low_arr[idx_sl2_3]
                                    SH3_3, SL3_3 = high_arr[idx_sh3_3], low_arr[idx_sl3_3]
                                    if SH1_3 > 0 and SH2_3 > 0 and SH3_3 > 0:
                                        D1_3 = (SH1_3 - SL1_3) / SH1_3
                                        D2_3 = (SH2_3 - SL2_3) / SH2_3
                                        D3_3 = (SH3_3 - SL3_3) / SH3_3
                                        if (D1_3 >= min_d1_limit) and (D3_3 >= min_dK_limit) and (D3_3 < D2_3 < D1_3) and (D3_3 <= max_final_contraction):
                                            is_3_wave_valid = True
                                            max_SH_3 = max(SH1_3, SH2_3, SH3_3)
                                            stop_loss_base_3 = SL3_3
                                            stop_loss_base_idx_3 = idx_sl3_3
                                            trend_hh_hl_3 = (high_arr[idx_sh3_3] > high_arr[idx_sh2_3]) and (low_arr[idx_sl3_3] > low_arr[idx_sl2_3])
                                            idx_sh1_used_3 = idx_sh1_3

                        # 2. Try 2-wave check (if not 3-wave valid and (K==2 or K=="adaptive"))
                        if (K == 2 or (K == "adaptive" and not is_3_wave_valid)):
                            if sh_ptr >= 2 and sl_ptr >= 2:
                                idx_sh1_2 = sh_indices[sh_ptr - 2]
                                idx_sh2_2 = sh_indices[sh_ptr - 1]
                                idx_sl1_2 = sl_indices[sl_ptr - 2]
                                idx_sl2_2 = sl_indices[sl_ptr - 1]
                                if (idx_sh1_2 < idx_sl1_2 < idx_sh2_2 < idx_sl2_2) and (t - idx_sh1_2 <= 150):
                                    SH1_2, SL1_2 = high_arr[idx_sh1_2], low_arr[idx_sl1_2]
                                    SH2_2, SL2_2 = high_arr[idx_sh2_2], low_arr[idx_sl2_2]
                                    if SH1_2 > 0 and SH2_2 > 0:
                                        D1_2 = (SH1_2 - SL1_2) / SH1_2
                                        D2_2 = (SH2_2 - SL2_2) / SH2_2
                                        if (D1_2 >= min_d1_limit) and (D2_2 >= min_dK_limit) and (D2_2 < D1_2) and (D2_2 <= max_final_contraction):
                                            is_2_wave_valid = True
                                            max_SH_2 = max(SH1_2, SH2_2)
                                            stop_loss_base_2 = SL2_2
                                            stop_loss_base_idx_2 = idx_sl2_2
                                            trend_hh_hl_2 = (high_arr[idx_sh2_2] > high_arr[idx_sh1_2]) and (low_arr[idx_sl2_2] > low_arr[idx_sl1_2])
                                            idx_sh1_used_2 = idx_sh1_2

                        # Set pattern variables depending on which path succeeded
                        if is_3_wave_valid:
                            pattern_valid = True
                            max_SH = max_SH_3
                            stop_loss_base = stop_loss_base_3
                            stop_loss_base_idx = stop_loss_base_idx_3
                            trend_hh_hl = trend_hh_hl_3
                            cached_idx_sh1 = idx_sh1_used_3
                        elif is_2_wave_valid:
                            pattern_valid = True
                            max_SH = max_SH_2
                            stop_loss_base = stop_loss_base_2
                            stop_loss_base_idx = stop_loss_base_idx_2
                            trend_hh_hl = trend_hh_hl_2
                            cached_idx_sh1 = idx_sh1_used_2
                        else:
                            pattern_valid = False
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

                    stop_loss_val = stop_loss_base * (1.0 - stop_buffer)
                    if close_arr[t] <= stop_loss_val:
                        continue

                    position = 1
                    entry_price = close_arr[t]
                    stop_loss = stop_loss_val
                    entry_idx = t
                    bars_held = 0
                    pattern_idx_sh1 = cached_idx_sh1
                    pattern_max_SH = max_SH

                    if risk_reward == "1R":
                        take_profit = entry_price + 1.0 * (entry_price - stop_loss)
                    elif risk_reward == "1.5R":
                        take_profit = entry_price + 1.5 * (entry_price - stop_loss)
                    elif risk_reward == "2R":
                        take_profit = entry_price + 2.0 * (entry_price - stop_loss)
                    elif risk_reward == "3R":
                        take_profit = entry_price + 3.0 * (entry_price - stop_loss)
                    else:
                        take_profit = None

                    trailing_stop_val = stop_loss
                    signal_arr[t] = 1.0

                elif position == 1:
                    bars_held += 1
                    signal_arr[t] = 1.0

                    # Exit logic check
                    exit_reason = None
                    current_price = close_arr[t]
                    current_high = high_arr[t]
                    current_low = low_arr[t]

                    # 1. Stop Loss check
                    if current_low <= trailing_stop_val:
                        exit_reason = "STOP_LOSS"
                        exit_price = trailing_stop_val
                    # 2. Take Profit check (fixed R-multiple)
                    elif take_profit is not None and current_high >= take_profit:
                        exit_reason = "TAKE_PROFIT"
                        exit_price = take_profit
                    # 3. Trailing exits
                    elif risk_reward == "ATR_Trail":
                        trail_mult = 3.0
                        atr_val = atr14_arr[t]
                        new_trail = current_price - trail_mult * atr_val
                        if new_trail > trailing_stop_val:
                            trailing_stop_val = new_trail
                        
                        if current_low <= trailing_stop_val:
                            exit_reason = "ATR_TRAIL"
                            exit_price = trailing_stop_val
                    elif risk_reward == "Swing_Trail":
                        # Trail by latest swing low index
                        sl_ptr_curr = sl_ptrs[t]
                        if sl_ptr_curr > 0:
                            curr_sl_idx = sl_indices[sl_ptr_curr - 1]
                            if curr_sl_idx > entry_idx:
                                new_trail = low_arr[curr_sl_idx]
                                if new_trail > trailing_stop_val:
                                    trailing_stop_val = new_trail
                        
                        if current_low <= trailing_stop_val:
                            exit_reason = "SWING_TRAIL"
                            exit_price = trailing_stop_val
                    # 4. Time exit (30 bars)
                    elif risk_reward == "30_Bar_Time_Exit" and bars_held >= 30:
                        exit_reason = "TIME_EXIT"
                        exit_price = current_price

                    if exit_reason is not None:
                        # Record trade details
                        trade_info = {
                            "trade_id": len(self.all_trades_info) + 1,
                            "symbol": symbol,
                            "entry_idx": entry_idx,
                            "exit_idx": t,
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "exit_reason": exit_reason,
                            "pattern_sh1": pattern_idx_sh1,
                            "pattern_max_SH": pattern_max_SH
                        }
                        self.all_trades_info.append(trade_info)
                        
                        position = 0
                        last_entered_sl_idx = stop_loss_base_idx
                        signal_arr[t] = 0.0

            df['signal'] = signal_arr

        return universe_data

    def get_custom_metrics(self) -> dict:
        """Expose list of processed trade detail maps for downstream verification audits."""
        return {
            "all_trades_info": self.all_trades_info
        }
