"""
Phase 4 Walk-Forward Validation (V2)
=====================================
Validates strategy configurations from phase3_top50.csv across three
independent time periods to identify consistently profitable strategies.

Dynamic Period Selection:
- If coin data starts <= 2023-01-01:
    Training: 2023, Validation: 2024, Test: 2025
- If coin data starts > 2023-01-01:
    Training: 2024, Validation: 2025, Test: 2026 YTD

Survival Criteria (ALL THREE periods must pass):
    Profit Factor  >= 1.3
    Sharpe Ratio   >= 1.0
    Max Drawdown   <= 30.0 %
    Trades         >= 30

Outputs:
    results/walk_forward_results_v2.csv
    results/walk_forward_survivors_v2.csv
    results/walk_forward_failures_v2.csv
"""

import os
import time
import math
import numpy as np
import pandas as pd
import vectorbt as vbt
from vectorbt.portfolio.enums import OppositeEntryMode, StopExitMode, StopExitPrice

# ─────────────────────────── CONFIG ────────────────────────────────────────────
DATA_DIR    = "data"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

INITIAL_BALANCE = 1_000.0
RISK_PER_TRADE  = 100.0
LEVERAGE        = 5.0
FEE_RATE        = 0.0005   # 0.05 %
SLIPPAGE_RATE   = 0.0002   # 0.02 %

# Phase 4 scope
P4_COINS      = {"TRX", "TAO", "WLD", "ZEC", "XRP"}
P4_STRATEGIES = {"Donchian Breakout", "Turtle Trading", "Supertrend EMA200"}
P4_TIMEFRAME  = "1H"

# Walk-forward period definitions
PERIODS_FULL_HISTORY = {
    "Training":   ("2023-01-01", "2023-12-31 23:59:59"),
    "Validation": ("2024-01-01", "2024-12-31 23:59:59"),
    "Test":       ("2025-01-01", "2025-12-31 23:59:59"),
}

PERIODS_SHORT_HISTORY = {
    "Training":   ("2024-01-01", "2024-12-31 23:59:59"),
    "Validation": ("2025-01-01", "2025-12-31 23:59:59"),
    "Test":       ("2026-01-01", "2026-12-31 23:59:59"),
}

# Survival thresholds
MIN_PROFIT_FACTOR = 1.3
MIN_SHARPE        = 1.0
MAX_DRAWDOWN      = 30.0
MIN_TRADES        = 30

TIMEFRAME_DELTA = pd.Timedelta(hours=1)

# ─────────────────────────── DATA LOADING ──────────────────────────────────────
def load_symbol_timeframe(symbol: str, timeframe: str) -> pd.DataFrame | None:
    ticker_dir = os.path.join(DATA_DIR, symbol)
    if not os.path.isdir(ticker_dir):
        return None

    candidates = [
        f"{timeframe}.csv",
        f"{timeframe.upper()}.csv",
        f"{timeframe.lower()}.csv",
        f"{symbol}_{timeframe}.csv",
        f"{symbol}_{timeframe.upper()}.csv",
        f"{symbol}_{timeframe.lower()}.csv",
    ]
    filepath = next(
        (os.path.join(ticker_dir, n) for n in candidates
         if os.path.exists(os.path.join(ticker_dir, n))),
        None,
    )
    if filepath is None:
        return None

    try:
        df = pd.read_csv(filepath)
        col_map = {}
        for col in df.columns:
            lc = col.lower()
            if lc in ("timestamp", "date", "datetime", "ts"):
                col_map[col] = "timestamp"
            elif lc in ("open", "high", "low", "close", "volume"):
                col_map[col] = lc
        df.rename(columns=col_map, inplace=True)

        for req in ("timestamp", "open", "high", "low", "close", "volume"):
            if req not in df.columns:
                print(f"  [WARN] {symbol}/{timeframe} missing column '{req}'")
                return None

        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.sort_values("timestamp", inplace=True)
        df.drop_duplicates(subset=["timestamp"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    except Exception as exc:
        print(f"  [ERROR] loading {symbol} {timeframe}: {exc}")
        return None

def slice_period(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    lo = pd.Timestamp(start, tz="UTC")
    hi = pd.Timestamp(end,   tz="UTC")
    mask = (df["timestamp"] >= lo) & (df["timestamp"] <= hi)
    return df.loc[mask].reset_index(drop=True)

# ─────────────────────────── INDICATORS ────────────────────────────────────────
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat(
        [h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1
    ).max(axis=1)

# ─────────────────────────── SIGNAL BUILDERS ───────────────────────────────────
def build_turtle_signals(df, breakout_length, exit_length):
    high, low, close = df["high"], df["low"], df["close"]
    signals = pd.DataFrame(
        {"side": "", "stop_loss": np.nan, "exit_long": False, "exit_short": False},
        index=df.index,
    )

    min_len = max(breakout_length, exit_length, 20)
    if len(df) < min_len:
        return signals

    tr    = true_range(df)
    atr20 = tr.rolling(20).mean()

    entry_upper = high.shift(1).rolling(breakout_length).max()
    entry_lower = low.shift(1).rolling(breakout_length).min()
    exit_lower  = low.shift(1).rolling(exit_length).min()
    exit_upper  = high.shift(1).rolling(exit_length).max()

    long_sig  = close > entry_upper
    short_sig = close < entry_lower

    l_stop = (close - 2 * atr20).where(lambda s: s < close, close * 0.99)
    s_stop = (close + 2 * atr20).where(lambda s: s > close, close * 1.01)

    signals.loc[long_sig,  "side"]      = "long"
    signals.loc[long_sig,  "stop_loss"] = l_stop
    signals.loc[short_sig, "side"]      = "short"
    signals.loc[short_sig, "stop_loss"] = s_stop
    signals["exit_long"]  = close < exit_lower
    signals["exit_short"] = close > exit_upper
    return signals

def build_donchian_signals(df, channel_length, stop_length):
    high, low, close = df["high"], df["low"], df["close"]
    signals = pd.DataFrame(
        {"side": "", "stop_loss": np.nan, "exit_long": False, "exit_short": False},
        index=df.index,
    )

    min_len = max(channel_length, stop_length, 20)
    if len(df) < min_len:
        return signals

    upper_channel = high.shift(1).rolling(channel_length).max()
    lower_channel = low.shift(1).rolling(channel_length).min()
    l_stop = low.shift(1).rolling(stop_length).min()
    s_stop = high.shift(1).rolling(stop_length).max()

    l_stop = l_stop.where(l_stop < close, close * 0.99)
    s_stop = s_stop.where(s_stop > close, close * 1.01)

    long_sig  = close > upper_channel
    short_sig = close < lower_channel

    signals.loc[long_sig,  "side"]      = "long"
    signals.loc[long_sig,  "stop_loss"] = l_stop
    signals.loc[short_sig, "side"]      = "short"
    signals.loc[short_sig, "stop_loss"] = s_stop
    return signals

def build_supertrend_signals(df, atr_period, atr_multiplier, ema_length):
    high, low, close = df["high"], df["low"], df["close"]
    signals = pd.DataFrame(
        {"side": "", "stop_loss": np.nan, "exit_long": False, "exit_short": False},
        index=df.index,
    )

    min_len = max(ema_length, atr_period, 20)
    if len(df) < min_len:
        return signals

    ema_filter = ema(close, ema_length)
    tr  = true_range(df)
    atr = tr.rolling(atr_period).mean()

    hl2       = (high + low) / 2
    atr_val   = atr.values
    close_val = close.values
    hl2_val   = hl2.values
    n         = len(df)

    upperband   = np.zeros(n)
    lowerband   = np.zeros(n)
    in_uptrend  = np.ones(n, dtype=bool)

    for i in range(1, n):
        if np.isnan(atr_val[i]):
            upperband[i] = hl2_val[i]
            lowerband[i] = hl2_val[i]
            continue

        basic_ub = hl2_val[i] + atr_multiplier * atr_val[i]
        basic_lb = hl2_val[i] - atr_multiplier * atr_val[i]

        upperband[i] = basic_ub if (basic_ub < upperband[i-1] or close_val[i-1] > upperband[i-1]) else upperband[i-1]
        lowerband[i] = basic_lb if (basic_lb > lowerband[i-1] or close_val[i-1] < lowerband[i-1]) else lowerband[i-1]

        if   close_val[i] > upperband[i-1]: in_uptrend[i] = True
        elif close_val[i] < lowerband[i-1]: in_uptrend[i] = False
        else:                               in_uptrend[i] = in_uptrend[i-1]

    uptrend   = pd.Series(in_uptrend, index=df.index)
    flip_up   = uptrend  & (~uptrend.shift(1).fillna(True))
    flip_dn   = (~uptrend) & uptrend.shift(1).fillna(False)

    long_sig  = flip_up & (close > ema_filter)
    short_sig = flip_dn & (close < ema_filter)

    lb_series = pd.Series(lowerband, index=df.index)
    ub_series = pd.Series(upperband, index=df.index)
    l_stop = lb_series.where(lb_series < close, close * 0.99)
    s_stop = ub_series.where(ub_series > close, close * 1.01)

    signals.loc[long_sig,  "side"]      = "long"
    signals.loc[long_sig,  "stop_loss"] = l_stop
    signals.loc[short_sig, "side"]      = "short"
    signals.loc[short_sig, "stop_loss"] = s_stop
    return signals

# ─────────────────────────── VBT INPUT BUILDER ─────────────────────────────────
def build_vbt_inputs(df, signals, rr_values):
    index  = df.index
    n      = len(df)

    entries       = pd.Series(False, index=index)
    short_entries = pd.Series(False, index=index)
    sl_stop       = pd.Series(np.nan, index=index)
    sl_pct_map    = {}

    sig_rows = np.where(signals["side"] != "")[0]
    for r in sig_rows:
        if r >= n - 1:
            continue
        side     = signals["side"].iloc[r]
        sl_price = signals["stop_loss"].iloc[r]
        if pd.isna(sl_price) or sl_price <= 0:
            continue

        entry_row = r + 1
        ep        = df["open"].iloc[entry_row]
        if ep <= 0:
            continue

        dist   = abs(ep - sl_price)
        sl_pct = dist / ep
        if sl_pct <= 0:
            continue

        entry_idx = df.index[entry_row]
        if side == "long":
            entries.iloc[entry_row]       = True
        else:
            short_entries.iloc[entry_row] = True

        sl_stop.iloc[entry_row]       = sl_pct
        sl_pct_map[entry_idx]         = sl_pct

    tp_stop = pd.DataFrame(index=index)
    for rr in rr_values:
        tp_stop[rr] = sl_stop * rr

    exits       = signals["exit_long"].copy()  if "exit_long"  in signals.columns else pd.Series(False, index=index)
    short_exits = signals["exit_short"].copy() if "exit_short" in signals.columns else pd.Series(False, index=index)

    # Force close at end of period
    exits.iloc[-1]       = True
    short_exits.iloc[-1] = True

    return entries, short_entries, exits, short_exits, sl_stop, tp_stop, sl_pct_map

# ─────────────────────────── LEVERAGE SIMULATOR ────────────────────────────────
def _daily_sharpe(equity_curve, exit_dates):
    if len(exit_dates) < 2:
        return 0.0
    df_eq = pd.DataFrame({"Date": pd.to_datetime(exit_dates), "Balance": equity_curve[1:]})
    df_eq["Date"] = df_eq["Date"].dt.normalize()
    daily = df_eq.groupby("Date")["Balance"].last()

    full_idx = pd.date_range(start=daily.index.min(), end=daily.index.max(), freq="D")
    daily = daily.reindex(full_idx).ffill()

    daily_pct = daily.pct_change().dropna()
    if daily_pct.empty or daily_pct.std() == 0:
        return 0.0
    return float((daily_pct.mean() / daily_pct.std()) * np.sqrt(252))

def simulate_portfolio_leverage(trades_df, sl_pct_map, df_slice):
    balance     = INITIAL_BALANCE
    equity_curve = [balance]
    exit_dates  = []
    sim_trades  = []

    if trades_df.empty:
        return sim_trades, balance, equity_curve, exit_dates

    trades_sorted = trades_df.sort_values("Entry Timestamp").reset_index(drop=True)

    for _, row in trades_sorted.iterrows():
        if balance <= 0:
            break

        ep         = float(row["Avg Entry Price"])
        exit_price = float(row["Avg Exit Price"])
        vbt_qty    = float(row["Size"])
        vbt_pnl    = float(row["PnL"])

        sl_pct = sl_pct_map.get(row["Entry Timestamp"])
        if sl_pct is None or sl_pct <= 0:
            continue

        dist     = ep * sl_pct
        friction = ep * (2 * FEE_RATE + 2 * SLIPPAGE_RATE)

        risk_qty = RISK_PER_TRADE / (dist + friction)
        max_qty  = (balance * LEVERAGE) / ep
        qty      = min(risk_qty, max_qty)

        sim_pnl  = vbt_pnl * (qty / vbt_qty) if vbt_qty != 0 else 0.0
        balance  = max(0.0, balance + sim_pnl)
        equity_curve.append(balance)

        exit_idx  = row["Exit Timestamp"]
        exit_time = df_slice.loc[exit_idx, "timestamp"]
        exit_dates.append(exit_time)

        sim_trades.append({
            "pnl":         sim_pnl,
            "direction":   row["Direction"],
            "entry_price": ep,
            "exit_price":  exit_price,
            "qty":         qty,
            "exit_date":   exit_time,
        })

        if balance <= 0:
            break

    return sim_trades, balance, equity_curve, exit_dates

def compute_metrics(sim_trades, final_balance, equity_curve, exit_dates):
    total_trades = len(sim_trades)
    net_profit   = final_balance - INITIAL_BALANCE

    if total_trades == 0:
        return {
            "Net Profit":    0.0,
            "Profit Factor": 0.0,
            "Sharpe Ratio":  0.0,
            "Max Drawdown":  0.0,
            "Win Rate":      0.0,
            "Trades":        0,
        }

    wins   = [t["pnl"] for t in sim_trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in sim_trades if t["pnl"] <= 0]

    win_rate     = len(wins) / total_trades * 100
    sum_wins     = sum(wins)
    sum_losses   = sum(losses)
    profit_factor = (
        999.9 if sum_losses == 0 and sum_wins > 0
        else 1.0 if sum_losses == 0
        else abs(sum_wins / sum_losses)
    )

    eq = pd.Series(equity_curve)
    cummax = eq.cummax()
    max_dd = float(((eq - cummax) / cummax.replace(0, 1e-9)).min() * -100)

    return {
        "Net Profit":    round(net_profit,   2),
        "Profit Factor": round(profit_factor, 4),
        "Sharpe Ratio":  round(_daily_sharpe(equity_curve, exit_dates), 4),
        "Max Drawdown":  round(max_dd,        2),
        "Win Rate":      round(win_rate,       2),
        "Trades":        total_trades,
    }

# ─────────────────────────── SINGLE PERIOD BACKTEST ────────────────────────────
def run_period_backtest(df_period: pd.DataFrame, strategy: str, params: dict, rr: float) -> dict:
    """Run one strategy/params/rr combination on a single period slice."""
    if df_period is None or len(df_period) < 50:
        return None

    if strategy == "Turtle Trading":
        signals = build_turtle_signals(df_period, params["breakout_length"], params["exit_length"])
    elif strategy == "Donchian Breakout":
        signals = build_donchian_signals(df_period, params["channel_length"], params["stop_length"])
    elif strategy == "Supertrend EMA200":
        signals = build_supertrend_signals(df_period, params["atr_period"], params["atr_multiplier"], params["ema_length"])
    else:
        return None

    if signals["side"].eq("").all():
        return None

    entries, short_entries, exits, short_exits, sl_stop, tp_stop, sl_pct_map = build_vbt_inputs(
        df_period, signals, [rr]
    )

    if not entries.any() and not short_entries.any():
        return None

    order_price = df_period["open"].copy()
    order_price.iloc[-1] = df_period["close"].iloc[-1]

    try:
        pf = vbt.Portfolio.from_signals(
            close         = df_period["close"],
            entries       = entries,
            exits         = exits,
            short_entries = short_entries,
            short_exits   = short_exits,
            size          = 1.0,
            size_type     = "amount",
            price         = order_price,
            open          = df_period["open"],
            high          = df_period["high"],
            low           = df_period["low"],
            sl_stop       = sl_stop,
            tp_stop       = tp_stop[rr],
            fees          = FEE_RATE,
            slippage      = SLIPPAGE_RATE,
            init_cash     = 1_000_000.0,
            accumulate    = False,
            upon_opposite_entry = OppositeEntryMode.Ignore,
            stop_exit_price     = StopExitPrice.StopMarket,
            upon_stop_exit      = StopExitMode.Close,
            freq          = TIMEFRAME_DELTA,
        )

        if pf.trades.count() == 0:
            return None

        trades_df = pf.trades.records_readable
        sim_trades, final_balance, equity_curve, exit_dates = simulate_portfolio_leverage(
            trades_df, sl_pct_map, df_period
        )

        return compute_metrics(sim_trades, final_balance, equity_curve, exit_dates)
    except Exception as exc:
        return None

# ─────────────────────────── CANDIDATE EXTRACTION ──────────────────────────────
def extract_params(row: pd.Series, strategy: str) -> dict:
    p = {}
    if strategy == "Turtle Trading":
        p["breakout_length"] = int(row["breakout_length"])
        p["exit_length"]     = int(row["exit_length"])
    elif strategy == "Donchian Breakout":
        p["channel_length"] = int(row["channel_length"])
        p["stop_length"]    = int(row["stop_length"])
    elif strategy == "Supertrend EMA200":
        p["atr_period"]     = int(row["atr_period"])
        p["atr_multiplier"] = float(row["atr_multiplier"])
        p["ema_length"]     = int(row["ema_length"])
    return p

def rr_value_to_float(rr_str: str) -> float:
    try:
        return float(rr_str.split(":")[1])
    except Exception:
        return float(rr_str)

def load_candidates(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Strategy"] = df["Strategy"].str.strip()
    mask = (
        df["Coin"].isin(P4_COINS)
        & df["Strategy"].isin(P4_STRATEGIES)
        & (df["Timeframe"] == P4_TIMEFRAME)
    )
    df = df.loc[mask].reset_index(drop=True)
    df["RR Float"] = df["RR Value"].apply(rr_value_to_float)
    df = df.drop_duplicates(subset=["Coin", "Strategy", "Parameters", "RR Value"]).reset_index(drop=True)
    return df

# ─────────────────────────── MAIN ──────────────────────────────────────────────
def main():
    t0 = time.time()
    top50_path = os.path.join(RESULTS_DIR, "phase3_top50.csv")
    if not os.path.exists(top50_path):
        print(f"[FATAL] Cannot find {top50_path}.")
        return

    print("\n" + "="*70)
    print("  PHASE 4  -  WALK-FORWARD VALIDATION (V2)")
    print("="*70)

    candidates = load_candidates(top50_path)
    if candidates.empty:
        print("[FATAL] No candidates matched Phase 4 filters.")
        return

    needed_coins = sorted(candidates["Coin"].unique())
    raw_data: dict[str, pd.DataFrame] = {}
    coin_periods: dict[str, dict] = {}

    for coin in needed_coins:
        df = load_symbol_timeframe(coin, P4_TIMEFRAME)
        if df is None or df.empty:
            continue
            
        raw_data[coin] = df
        ts_min = df["timestamp"].min()
        
        # Check start date
        if ts_min <= pd.Timestamp("2023-01-01", tz="UTC"):
            coin_periods[coin] = PERIODS_FULL_HISTORY
            print(f"  {coin}: Full History -> Training 2023, Val 2024, Test 2025")
        else:
            coin_periods[coin] = PERIODS_SHORT_HISTORY
            print(f"  {coin}: Short History ({ts_min.strftime('%Y-%m-%d')}) -> Training 2024, Val 2025, Test 2026")

    print(f"\n  Running walk-forward on {len(candidates)} configurations ...\n")
    all_period_rows = []
    total = len(candidates)

    for i, (_, row) in enumerate(candidates.iterrows(), 1):
        coin     = row["Coin"]
        strategy = row["Strategy"]
        rr       = row["RR Float"]
        params   = extract_params(row, strategy)
        param_str = row["Parameters"]

        if coin not in raw_data:
            continue

        df_full = raw_data[coin]
        periods = coin_periods[coin]
        pct = i / total * 100
        print(f"  [{i:>3}/{total}] {pct:5.1f}%  {coin:4s}  {strategy:20s}  RR=1:{rr}  params={param_str}")

        for period_name, (start, end) in periods.items():
            df_period = slice_period(df_full, start, end)

            if df_period.empty or len(df_period) < 50:
                m = {
                    "Net Profit": np.nan, "Profit Factor": np.nan,
                    "Sharpe Ratio": np.nan, "Max Drawdown": np.nan,
                    "Win Rate": np.nan, "Trades": 0,
                }
            else:
                m = run_period_backtest(df_period, strategy, params, rr)
                if m is None:
                    m = {
                        "Net Profit": np.nan, "Profit Factor": np.nan,
                        "Sharpe Ratio": np.nan, "Max Drawdown": np.nan,
                        "Win Rate": np.nan, "Trades": 0,
                    }

            all_period_rows.append({
                "Coin":           coin,
                "Strategy":       strategy,
                "Timeframe":      P4_TIMEFRAME,
                "RR Value":       f"1:{rr}",
                "Parameters":     param_str,
                "Period":         period_name,
                "Period Start":   start,
                "Period End":     end,
                "Profit Factor":  m["Profit Factor"],
                "Sharpe Ratio":   m["Sharpe Ratio"],
                "Max Drawdown":   m["Max Drawdown"],
                "Net Profit":     m["Net Profit"],
                "Win Rate":       m["Win Rate"],
                "Trades":         m["Trades"],
            })

    if not all_period_rows:
        return

    df_results = pd.DataFrame(all_period_rows)
    wf_path = os.path.join(RESULTS_DIR, "walk_forward_results_v2.csv")
    df_results.to_csv(wf_path, index=False)
    print(f"\n  Saved {len(df_results)} period-level rows -> {wf_path}")

    # ── Apply survival criteria & failure tracking ──────────────────────────────
    config_keys = ["Coin", "Strategy", "Timeframe", "RR Value", "Parameters"]
    survivor_rows = []
    failure_rows = []

    for key, grp in df_results.groupby(config_keys):
        grp = grp.set_index("Period")
        coin, strategy, tf, rr_val, param_str = key
        
        passed_all = True
        period_metrics = {}
        failure_reasons = []

        # We need Training, Validation, Test in order
        for period in ["Training", "Validation", "Test"]:
            if period not in grp.index:
                passed_all = False
                failure_reasons.append(f"{period}: Missing Data")
                continue
                
            r = grp.loc[period]
            pf = r["Profit Factor"]
            sr = r["Sharpe Ratio"]
            dd = r["Max Drawdown"]
            tr = r["Trades"]
            
            period_metrics[period] = {
                "pf": pf, "sr": sr, "dd": dd, "np": r["Net Profit"], "tr": tr, "wr": r["Win Rate"]
            }

            if pd.isna(tr) or tr < MIN_TRADES:
                failure_reasons.append(f"{period}: Low Trades ({tr})")
                passed_all = False
            if pd.isna(pf) or pf < MIN_PROFIT_FACTOR:
                failure_reasons.append(f"{period}: Low PF ({pf})")
                passed_all = False
            if pd.isna(sr) or sr < MIN_SHARPE:
                failure_reasons.append(f"{period}: Low Sharpe ({sr})")
                passed_all = False
            if pd.isna(dd) or dd > MAX_DRAWDOWN:
                failure_reasons.append(f"{period}: High Drawdown ({dd}%)")
                passed_all = False

        if passed_all:
            # Survivor
            pf_vals = [period_metrics[p]["pf"] for p in ["Training", "Validation", "Test"]]
            sr_vals = [period_metrics[p]["sr"] for p in ["Training", "Validation", "Test"]]
            dd_vals = [period_metrics[p]["dd"] for p in ["Training", "Validation", "Test"]]
            np_vals = [period_metrics[p]["np"] for p in ["Training", "Validation", "Test"]]

            survivor_rows.append({
                "Coin":            coin,
                "Strategy":        strategy,
                "Timeframe":       tf,
                "RR Value":        rr_val,
                "Parameters":      param_str,
                "Train PF":        round(period_metrics["Training"]["pf"],   4),
                "Val PF":          round(period_metrics["Validation"]["pf"],  4),
                "Test PF":         round(period_metrics["Test"]["pf"],        4),
                "Train Sharpe":    round(period_metrics["Training"]["sr"],   4),
                "Val Sharpe":      round(period_metrics["Validation"]["sr"],  4),
                "Test Sharpe":     round(period_metrics["Test"]["sr"],        4),
                "Train DD":        round(period_metrics["Training"]["dd"],   2),
                "Val DD":          round(period_metrics["Validation"]["dd"],  2),
                "Test DD":         round(period_metrics["Test"]["dd"],        2),
                "Train NP":        round(period_metrics["Training"]["np"],   2),
                "Val NP":          round(period_metrics["Validation"]["np"],  2),
                "Test NP":         round(period_metrics["Test"]["np"],        2),
                "Train Trades":    period_metrics["Training"]["tr"],
                "Val Trades":      period_metrics["Validation"]["tr"],
                "Test Trades":     period_metrics["Test"]["tr"],
                "Avg PF":          round(np.mean(pf_vals),  4),
                "Avg Sharpe":      round(np.mean(sr_vals),  4),
                "Std Sharpe":      round(np.std(sr_vals, ddof=0), 4),
                "Avg Drawdown":    round(np.mean(dd_vals),  2),
                "Avg Net Profit":  round(np.mean(np_vals),  2),
            })
        else:
            # Failed
            failure_rows.append({
                "Coin": coin,
                "Strategy": strategy,
                "RR Value": rr_val,
                "Parameters": param_str,
                "Failure Reasons": " | ".join(failure_reasons)
            })

    # Save Failures
    if failure_rows:
        df_failures = pd.DataFrame(failure_rows)
        fail_path = os.path.join(RESULTS_DIR, "walk_forward_failures_v2.csv")
        df_failures.to_csv(fail_path, index=False)
        print(f"  Saved {len(df_failures)} failed configurations -> {fail_path}")

    # Save Survivors
    print(f"\n  Survivors found: {len(survivor_rows)}")
    if survivor_rows:
        df_survivors = pd.DataFrame(survivor_rows)
        df_survivors.sort_values(by=["Std Sharpe", "Avg Net Profit"], ascending=[True, False], inplace=True)
        df_survivors.reset_index(drop=True, inplace=True)
        df_survivors.index = df_survivors.index + 1
        df_survivors.index.name = "Rank"

        surv_path = os.path.join(RESULTS_DIR, "walk_forward_survivors_v2.csv")
        df_survivors.to_csv(surv_path)
        print(f"  Saved {len(df_survivors)} survivors -> {surv_path}")

        top20 = df_survivors.head(20)
        print("\n" + "="*80)
        print("  ALL SURVIVORS (ranked by consistency)")
        print("="*80)
        for rank, (_, r) in enumerate(df_survivors.iterrows(), 1):
            print(f"[{rank}] {r['Coin']} | {r['Strategy']} | {r['RR Value']} | {r['Parameters']}")
            print(f"      Avg PF: {r['Avg PF']:.2f} | Avg Sharpe: {r['Avg Sharpe']:.2f} | Std Sharpe: {r['Std Sharpe']:.2f} | Avg NP: {r['Avg Net Profit']:.2f}")
    else:
        print("\n  No survivors passed all three periods.")
        pd.DataFrame().to_csv(os.path.join(RESULTS_DIR, "walk_forward_survivors_v2.csv"), index=False)

    # Print summary of failures
    print("\n" + "="*80)
    print("  FAILURE SUMMARY (Top 10 most common failure reasons)")
    print("="*80)
    if failure_rows:
        all_reasons = []
        for row in failure_rows:
            all_reasons.extend(row["Failure Reasons"].split(" | "))
        
        reason_counts = pd.Series(all_reasons).value_counts().head(10)
        for reason, count in reason_counts.items():
            # Clean up the output slightly for readability
            clean_reason = reason.split("(")[0].strip()
            print(f"  {count:>3} occurrences : {clean_reason}")
    else:
        print("  No failures!")

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    print(f"\n  Completed in {mins}m {secs}s")

if __name__ == "__main__":
    main()
