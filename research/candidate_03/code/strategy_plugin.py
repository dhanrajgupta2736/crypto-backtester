"""Candidate C003 — Session Open Range Breakout (SORB) Strategy Plugin.

QRP Framework v2.0 Strategy Plugin Interface.

Implements long-only SORB signals anchored to London (07:00 UTC) and New York
(13:00 UTC) session opens. Supports all exit modes from the approved Discovery
Matrix: session_close, atr_trail, swing_trail, and fixed_rr.

No look-ahead bias: all signals are computed on fully-closed candles.
Entry is executed at the open of the bar immediately following the signal bar.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

# Ensure workspace root is on path when loaded dynamically by the engine
_workspace_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from research_engine.core.strategy_interface import BaseStrategyPlugin


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LONDON_OPEN_HOUR = 7    # 07:00 UTC
NEWYORK_OPEN_HOUR = 13  # 13:00 UTC
SESSION_DURATION_HOURS = 4  # maximum hold window per session

TAKER_FEE = 0.00045
SLIPPAGE = 0.0005
TOTAL_FRICTION = TAKER_FEE + SLIPPAGE  # per leg


# ---------------------------------------------------------------------------
# ATR helper
# ---------------------------------------------------------------------------

def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range (Wilder's smoothing) without look-ahead bias."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder's smoothing: first value = simple mean, subsequent = EMA-style
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return atr


# ---------------------------------------------------------------------------
# Signal generation helpers
# ---------------------------------------------------------------------------

_or_cache: dict = {}
_atr_cache: dict = {}
_ema_cache: dict = {}


def _session_hours_for(session: str) -> List[int]:
    """Return UTC open hours for the specified session string."""
    if session == "london":
        return [LONDON_OPEN_HOUR]
    if session == "newyork":
        return [NEWYORK_OPEN_HOUR]
    if session == "both":
        return [LONDON_OPEN_HOUR, NEWYORK_OPEN_HOUR]
    raise ValueError(f"Unknown session: {session}")


def _session_close_hour_for(open_hour: int) -> int:
    """Return UTC close hour for a given session open hour."""
    return open_hour + SESSION_DURATION_HOURS


def _compute_open_range(
    df: pd.DataFrame,
    timeframe: str,
    session_open_hour: int,
    open_range_minutes: int,
) -> pd.DataFrame:
    """Compute session open range (high/low) for each session occurrence.

    Returns a DataFrame indexed by date with columns:
        or_high, or_low, or_complete_time (UTC timestamp when range is confirmed)
    """
    cache_key = (id(df), timeframe, session_open_hour, open_range_minutes)
    if cache_key in _or_cache:
        return _or_cache[cache_key]

    # Determine how many bars form the open range
    if timeframe == "15m":
        bars_in_range = open_range_minutes // 15
    elif timeframe == "1H":
        bars_in_range = open_range_minutes // 60
    else:
        bars_in_range = 1

    bars_in_range = max(1, bars_in_range)

    rows = []
    dates = df.index.normalize().unique()
    range_delta = pd.Timedelta(minutes=open_range_minutes)

    for date in dates:
        # Locate bars in [open_hour, open_hour + range_minutes)
        session_start = pd.Timestamp(
            year=date.year, month=date.month, day=date.day,
            hour=session_open_hour, tz="UTC"
        )
        session_end = session_start + range_delta

        # Slice df using loc, which is O(log N) and extremely fast
        # Since it is a sorted DatetimeIndex, this is extremely efficient.
        # Slices are inclusive in pandas loc, so we slice up to session_end - 1 second
        # to ensure session_end is exclusive.
        range_bars = df.loc[session_start : session_end - pd.Timedelta(seconds=1)]

        if len(range_bars) < bars_in_range:
            continue  # Incomplete range — skip this session

        or_high = range_bars["high"].max()
        or_low = range_bars["low"].min()
        or_complete_time = range_bars.index[-1]  # last bar of the open range

        rows.append(
            {
                "date": date.date(),
                "session_open_hour": session_open_hour,
                "or_high": or_high,
                "or_low": or_low,
                "or_complete_time": or_complete_time,
            }
        )

    if not rows:
        res = pd.DataFrame(columns=["date", "session_open_hour", "or_high", "or_low", "or_complete_time"])
        _or_cache[cache_key] = res
        return res

    res = pd.DataFrame(rows)
    _or_cache[cache_key] = res
    return res


def _compute_swing_lows(df: pd.DataFrame, window: int = 3) -> pd.Series:
    """Identify pivot swing lows (local minima) for trailing stop."""
    lows = df["low"]
    is_swing_low = pd.Series(False, index=df.index)
    for i in range(window, len(lows) - window):
        centre = lows.iloc[i]
        if centre == lows.iloc[i - window : i + window + 1].min():
            is_swing_low.iloc[i] = True
    return is_swing_low


# ---------------------------------------------------------------------------
# SORB Backtest Core — per-asset, single-parameter-set
# ---------------------------------------------------------------------------

def _run_sorb_backtest_single_asset(
    df: pd.DataFrame,
    params: dict,
    initial_capital: float = 10_000.0,
) -> List[dict]:
    """Execute SORB intraday backtest for one asset with one parameter set.

    Returns a list of completed trade records.
    """
    session = params["session"]
    timeframe = params["timeframe"]
    open_range_minutes = params["open_range_minutes"]
    breakout_buffer_atr = params["breakout_buffer_atr"]
    stop_mode = params["stop_mode"]
    atr_stop_multiplier = params.get("atr_stop_multiplier", 1.5)
    exit_mode = params["exit_mode"]
    fixed_rr = params.get("fixed_rr", 2.0)
    trend_filter = params["trend_filter"]
    trend_ema_period = params.get("trend_ema_period", 50)
    atr_period = params.get("atr_period", 14)

    if df.empty or len(df) < 50:
        return []

    # Pre-compute ATR and EMA columns with caching to avoid IPC and computation overhead
    global _atr_cache, _ema_cache
    atr_key = (id(df), atr_period)
    if atr_key in _atr_cache:
        atr_series = _atr_cache[atr_key]
    else:
        atr_series = _compute_atr(df, period=atr_period)
        _atr_cache[atr_key] = atr_series

    _ema_span = trend_ema_period if isinstance(trend_ema_period, int) and trend_ema_period > 0 else 50
    ema_key = (id(df), _ema_span)
    if ema_key in _ema_cache:
        ema_series = _ema_cache[ema_key]
    else:
        ema_series = df["close"].ewm(span=_ema_span, adjust=False).mean()
        _ema_cache[ema_key] = ema_series

    df_close = df["close"].to_numpy()
    df_open = df["open"].to_numpy()
    df_high = df["high"].to_numpy()
    df_low = df["low"].to_numpy()
    df_times = df.index.to_numpy()

    session_hours = _session_hours_for(session)
    trades = []

    # Track open positions keyed by session open hour to prevent re-entry
    # within the same session day
    active_session_keys = set()  # (date, open_hour)

    for open_hour in session_hours:
        or_table = _compute_open_range(df, timeframe, open_hour, open_range_minutes)
        if or_table.empty:
            continue

        close_hour = _session_close_hour_for(open_hour)

        # Convert columns to numpy arrays for super fast iteration
        or_highs = or_table["or_high"].to_numpy()
        or_lows = or_table["or_low"].to_numpy()
        or_dates = or_table["date"].to_numpy()
        or_complete_times = or_table["or_complete_time"].to_numpy()

        for idx in range(len(or_table)):
            date = or_dates[idx]
            or_high = or_highs[idx]
            or_low = or_lows[idx]
            or_complete_time = or_complete_times[idx]

            session_key = (date, open_hour)
            if session_key in active_session_keys:
                continue  # Already traded this session

            # Ensure target timezone matches df.index timezone
            tz = df.index.tz
            ts_complete = pd.Timestamp(or_complete_time)
            if ts_complete.tz != tz:
                if tz is None:
                    ts_complete = ts_complete.tz_localize(None)
                else:
                    if ts_complete.tz is None:
                        ts_complete = ts_complete.tz_localize("UTC").tz_convert(tz)
                    else:
                        ts_complete = ts_complete.tz_convert(tz)

            session_window_end = pd.Timestamp(
                year=ts_complete.year,
                month=ts_complete.month,
                day=ts_complete.day,
                hour=close_hour,
                tz=tz,
            )

            # Find slice boundaries using DatetimeIndex.searchsorted
            complete_idx = df.index.searchsorted(ts_complete)
            end_idx = df.index.searchsorted(session_window_end, side="right")



            if complete_idx + 1 >= end_idx:
                continue

            post_close = df_close[complete_idx + 1 : end_idx]
            post_open = df_open[complete_idx + 1 : end_idx]
            post_high = df_high[complete_idx + 1 : end_idx]
            post_low = df_low[complete_idx + 1 : end_idx]
            post_times = df_times[complete_idx + 1 : end_idx]

            # Breakout buffer: add ATR fraction to the range high
            buffer_value = 0.0
            if breakout_buffer_atr > 0.0:
                atr_at_range_end = atr_series.get(ts_complete, np.nan)
                if not np.isnan(atr_at_range_end) and atr_at_range_end > 0:
                    buffer_value = breakout_buffer_atr * atr_at_range_end

            entry_trigger = or_high + buffer_value

            # Trend filter check at OR completion time
            if trend_filter != "off":
                ema_val = ema_series.get(ts_complete, np.nan)
                close_at_or = df_close[complete_idx] if complete_idx < len(df_close) else np.nan
                if np.isnan(ema_val) or np.isnan(close_at_or):
                    continue
                if close_at_or <= ema_val:
                    continue  # Price below EMA — skip session


            entry_price = None
            entry_bar_idx = None
            entry_time = None

            # Scan post-range bars for breakout entry (signal = close exceeds entry trigger)
            trigger_hits = np.where(post_close > entry_trigger)[0]
            if len(trigger_hits) > 0:
                hit_idx = trigger_hits[0]
                # Entry is at the open of the next bar (hit_idx + 1)
                if hit_idx + 1 < len(post_close):
                    entry_price = post_open[hit_idx + 1] * (1.0 + SLIPPAGE)
                    entry_bar_idx = hit_idx + 1
                    entry_time = post_times[hit_idx + 1]

            if entry_price is None:
                continue  # No breakout fired this session

            active_session_keys.add(session_key)

            # Determine initial stop loss
            ts_entry_time = pd.Timestamp(entry_time)
            atr_at_entry = atr_series.get(ts_entry_time, np.nan)
            if np.isnan(atr_at_entry) or atr_at_entry <= 0:
                atr_at_entry = (entry_price * 0.015)  # fallback 1.5% of price

            if stop_mode == "range_low":
                stop_price = or_low
            else:  # atr_stop
                stop_price = entry_price - (atr_stop_multiplier * atr_at_entry)

            initial_risk = entry_price - stop_price
            if initial_risk <= 0:
                continue  # Degenerate setup — range low above entry

            # Determine take-profit (for fixed_rr and atr_trail modes)
            if exit_mode == "fixed_rr":
                take_profit = entry_price + (fixed_rr * initial_risk)
            else:
                take_profit = None

            # Simulate from entry bar to session close
            exit_price = None
            exit_reason = "SESSION_CLOSE"
            exit_time = entry_time

            # ATR trail state
            atr_trail_stop = stop_price  # starts at initial stop
            # Swing trail state: last confirmed swing low price
            last_swing_low = stop_price

            for hi in range(entry_bar_idx, len(post_close)):
                bar_ts = post_times[hi]
                bar_low = post_low[hi]
                bar_high = post_high[hi]
                bar_close = post_close[hi]

                # --- Stop hit check ---
                current_stop = atr_trail_stop if exit_mode == "atr_trail" else (
                    last_swing_low if exit_mode == "swing_trail" else stop_price
                )
                if bar_low <= current_stop:
                    exit_price = current_stop * (1.0 - SLIPPAGE)
                    exit_reason = "STOP_LOSS"
                    exit_time = bar_ts
                    break

                # --- Take profit check ---
                if exit_mode == "fixed_rr" and take_profit is not None:
                    if bar_high >= take_profit:
                        exit_price = take_profit * (1.0 - SLIPPAGE)
                        exit_reason = "TAKE_PROFIT_RR"
                        exit_time = bar_ts
                        break

                # --- ATR Trail ---
                if exit_mode == "atr_trail":
                    ts_val = pd.Timestamp(bar_ts)
                    atr_now = atr_series.get(ts_val, atr_at_entry)
                    new_trail = bar_close - (atr_stop_multiplier * atr_now)
                    if new_trail > atr_trail_stop:
                        atr_trail_stop = new_trail

                # --- Swing Trail ---
                if exit_mode == "swing_trail":
                    if hi >= entry_bar_idx + 2:
                        if post_low[hi - 2] < post_low[hi - 1] and post_low[hi - 2] < bar_low:
                            candidate_stop = post_low[hi - 2]
                            if candidate_stop > last_swing_low:
                                last_swing_low = candidate_stop

            # If loop completes without exit, exit at session close
            if exit_price is None:
                exit_price = post_close[-1] * (1.0 - SLIPPAGE)
                exit_reason = "SESSION_CLOSE"
                exit_time = post_times[-1]

            exit_time = pd.Timestamp(exit_time)


            # --- PnL Calculation ---
            # Assume 1 unit of notional per trade (normalised for metrics)
            notional = 1_000.0  # USD per trade allocation
            qty = notional / entry_price

            gross_pnl = qty * (exit_price - entry_price)
            entry_fee = notional * TAKER_FEE
            exit_fee = qty * exit_price * TAKER_FEE
            total_fees = entry_fee + exit_fee
            total_slippage = notional * SLIPPAGE + qty * exit_price * SLIPPAGE

            net_pnl = gross_pnl - total_fees - total_slippage
            risk_usd = notional * (initial_risk / entry_price)
            pnl_r = (net_pnl / risk_usd) if risk_usd > 0 else 0.0

            trades.append(
                {
                    "trade_id": f"C003-{entry_time}",
                    "asset": "UNKNOWN",  # filled in by caller
                    "direction": "LONG",
                    "session": session,
                    "open_hour": open_hour,
                    "entry_timestamp": entry_time,
                    "entry_price": entry_price,
                    "qty": qty,
                    "stop_price": stop_price,
                    "take_profit": take_profit,
                    "exit_timestamp": exit_time,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "pnl_nominal": round(net_pnl, 6),
                    "pnl_r": round(pnl_r, 4),
                    "fees_paid": round(total_fees, 6),
                    "slippage_paid": round(total_slippage, 6),
                    "initial_risk_usd": round(risk_usd, 4),
                }
            )

    return trades


# ---------------------------------------------------------------------------
# BaseStrategyPlugin Implementation
# ---------------------------------------------------------------------------

class StrategyPlugin(BaseStrategyPlugin):
    """C003 Session Open Range Breakout (SORB) strategy plugin.

    Implements the BaseStrategyPlugin interface for the QRP Framework v2.0
    Discovery Engine. Signal generation and backtest simulation are self-
    contained within this plugin to support the SORB intraday logic that
    does not map cleanly to the engine's bar-by-bar portfolio rebalancing model.
    """

    # ----------------------------------------------------------------
    # Interface contract
    # ----------------------------------------------------------------

    @property
    def metadata(self) -> dict:
        return {
            "candidate_id": "C003",
            "name": "Session Open Range Breakout (SORB)",
            "version": "1.0.0",
            "author": "Quant Team",
            "description": (
                "Long-only intraday strategy that enters on breakouts above the session "
                "open range high. Supports London and New York sessions, multiple "
                "exit mechanisms, and trend filters."
            ),
        }

    @property
    def parameter_space(self) -> dict:
        """Full approved Discovery Matrix parameter space for C003.

        Structural pruning constraints are enforced in run_sweep_c003.py when
        building the experiment grid, not here — this property returns the raw
        value lists for each dimension.
        """
        return {
            "timeframe": ["15m", "1H"],
            "session": ["london", "newyork", "both"],
            "open_range_minutes": [30, 60, 90],
            "breakout_buffer_atr": [0.0, 0.1, 0.2],
            "stop_mode": ["range_low", "atr_stop"],
            "atr_stop_multiplier": [1.5],          # locked to baseline in v1
            "atr_period": [14],                    # locked to baseline in v1
            "exit_mode": ["session_close", "atr_trail", "swing_trail", "fixed_rr"],
            "fixed_rr": [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
            "trend_filter": ["off", "ema50", "ema100", "ema200"],
        }

    def preprocess(self, universe_data: dict) -> dict:
        """Minimal preprocessing: ensure UTC timezone and sort index.

        The engine already normalises timestamps; we do a defensive pass here.
        """
        processed = {}
        for sym, df in universe_data.items():
            df = df.copy()
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index, utc=True)
            elif df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            df.sort_index(inplace=True)
            df = df[~df.index.duplicated(keep="first")]
            processed[sym] = df
        return processed

    def generate_signals(self, universe_data: dict, parameters: dict) -> dict:
        """Generate SORB entry signals (does not execute trades).

        For the C003 SORB plugin, the engine's built-in simulate_backtest
        is NOT used because SORB is intraday and session-scoped, which is
        incompatible with the portfolio rebalancing model. Instead, this
        method attaches a 'signal' column (0/1) for dashboard/progress display
        only. Full trade simulation is performed via run_sorb_universe_backtest().

        The 'signal' column here = 1 when a breakout condition is met on bar t
        (entry at t+1 open). This allows the framework dashboard to show signal
        frequency while the actual PnL is computed in the sweep runner.
        """
        session = parameters.get("session", "newyork")
        timeframe = parameters.get("timeframe", "15m")
        open_range_minutes = parameters.get("open_range_minutes", 60)
        breakout_buffer_atr = parameters.get("breakout_buffer_atr", 0.1)
        atr_period = parameters.get("atr_period", 14)
        trend_filter = parameters.get("trend_filter", "off")
        trend_ema_period_map = {"ema50": 50, "ema100": 100, "ema200": 200}
        trend_ema_period = trend_ema_period_map.get(trend_filter, 50)

        session_hours = _session_hours_for(session)

        result = {}
        for sym, df in universe_data.items():
            if df.empty or len(df) < 50:
                out = df.copy()
                out["signal"] = 0
                result[sym] = out
                continue

            atr_series = _compute_atr(df, period=atr_period)
            _ema_span = trend_ema_period if isinstance(trend_ema_period, (int, float)) and trend_ema_period > 0 else 50
            ema_series = df["close"].ewm(span=_ema_span, adjust=False).mean()

            signal = pd.Series(0, index=df.index, dtype=float)

            for open_hour in session_hours:
                or_table = _compute_open_range(df, timeframe, open_hour, open_range_minutes)
                if or_table.empty:
                    continue

                for _, or_row in or_table.iterrows():
                    or_high = or_row["or_high"]
                    or_complete_time = or_row["or_complete_time"]

                    # Breakout buffer
                    buffer_value = 0.0
                    if breakout_buffer_atr > 0.0:
                        atr_val = atr_series.get(or_complete_time, np.nan)
                        if not np.isnan(atr_val) and atr_val > 0:
                            buffer_value = breakout_buffer_atr * atr_val

                    entry_trigger = or_high + buffer_value

                    # Trend filter
                    if trend_filter != "off":
                        ema_val = ema_series.get(or_complete_time, np.nan)
                        close_val = df["close"].get(or_complete_time, np.nan)
                        if np.isnan(ema_val) or np.isnan(close_val) or close_val <= ema_val:
                            continue

                    close_hour = _session_close_hour_for(open_hour)
                    session_window_end = or_complete_time + pd.Timedelta(
                        hours=SESSION_DURATION_HOURS
                    )

                    post_range = df.loc[or_complete_time + pd.Timedelta(seconds=1) : session_window_end]

                    for bar_ts, bar in post_range.iterrows():
                        if bar["close"] > entry_trigger:
                            if bar_ts in signal.index:
                                signal.loc[bar_ts] = 1
                            break  # Only one entry per session

            out = df.copy()
            out["signal"] = signal
            result[sym] = out

        return result

    # ----------------------------------------------------------------
    # Self-contained SORB backtest (used by the sweep runner directly)
    # ----------------------------------------------------------------

    def run_sorb_universe_backtest(
        self,
        universe_data: dict,
        parameters: dict,
        initial_capital: float = 10_000.0,
    ) -> dict:
        """Run the full SORB intraday backtest across the entire universe.

        This method bypasses the engine's portfolio rebalancing model and
        instead simulates each session breakout independently, then aggregates
        trade-level results to produce portfolio equity.

        Args:
            universe_data: Dict mapping symbol -> preprocessed OHLCV DataFrame.
            parameters: Parameter dict from the experiment grid.
            initial_capital: Starting capital in USD.

        Returns:
            Dict with keys: trade_ledger, equity_curve, number_of_rebalances,
                            total_volume_traded, average_portfolio_value.
        """
        all_trades = []
        for sym, df in universe_data.items():
            asset_trades = _run_sorb_backtest_single_asset(df, parameters, initial_capital)
            for t in asset_trades:
                t["asset"] = sym
            all_trades.extend(asset_trades)

        if not all_trades:
            trade_ledger = pd.DataFrame(
                columns=[
                    "trade_id", "asset", "direction", "session", "open_hour",
                    "entry_timestamp", "entry_price", "qty",
                    "stop_price", "take_profit",
                    "exit_timestamp", "exit_price", "exit_reason",
                    "pnl_nominal", "pnl_r", "fees_paid", "slippage_paid",
                    "initial_risk_usd",
                ]
            )
        else:
            trade_ledger = pd.DataFrame(all_trades)
            trade_ledger.sort_values("entry_timestamp", inplace=True)
            trade_ledger.reset_index(drop=True, inplace=True)

        # Build equity curve from sequential trade PnL
        equity = initial_capital
        equity_points = []

        if not trade_ledger.empty:
            for _, row in trade_ledger.iterrows():
                equity += row["pnl_nominal"]
                equity_points.append((pd.Timestamp(row["exit_timestamp"]), equity))

        if equity_points:
            eq_dates, eq_vals = zip(*equity_points)
            equity_curve = pd.Series(eq_vals, index=eq_dates, name="portfolio_equity")
        else:
            # Flat equity curve covering the data range
            first_sym = next(iter(universe_data))
            idx = universe_data[first_sym].index
            equity_curve = pd.Series(initial_capital, index=idx, name="portfolio_equity")

        total_volume = 0.0
        if not trade_ledger.empty:
            total_volume += (trade_ledger["qty"] * trade_ledger["entry_price"]).sum()
            total_volume += (trade_ledger["qty"] * trade_ledger["exit_price"]).sum()

        average_portfolio_value = equity_curve.mean()
        number_of_rebalances = len(trade_ledger)

        return {
            "status": "COMPLETED",
            "termination_reason": "N/A",
            "last_processed_candle": str(equity_curve.index[-1]) if not equity_curve.empty else "N/A",
            "trade_ledger": trade_ledger,
            "equity_curve": equity_curve,
            "number_of_rebalances": number_of_rebalances,
            "total_volume_traded": total_volume,
            "average_portfolio_value": average_portfolio_value,
        }
