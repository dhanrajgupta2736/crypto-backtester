"""
Phase 9 Forward Test Simulator
==============================
Performs rolling forward testing on the 4 survivor configurations.
Partitions data into In-Sample (IS / Backtest) and Out-of-Sample (OOS / Forward Test) periods.
Compares performance, calculates degradation percentages, and ranks strategies by robustness.
"""

import os
import time
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

TIMEFRAME = "1H"
TIMEFRAME_DELTA = pd.Timedelta(hours=1)

# 4 Survivor configurations
CANDIDATES = [
    {
        "coin": "TRX",
        "strategy": "Donchian Breakout",
        "params": {"channel_length": 20, "stop_length": 20},
        "label": "TRX Donchian 20/20",
        "is_full_history": True
    },
    {
        "coin": "TAO",
        "strategy": "Donchian Breakout",
        "params": {"channel_length": 30, "stop_length": 20},
        "label": "TAO Donchian 30/20",
        "is_full_history": False
    },
    {
        "coin": "AVAX",
        "strategy": "Donchian Breakout",
        "params": {"channel_length": 30, "stop_length": 20},
        "label": "AVAX Donchian 30/20",
        "is_full_history": True
    },
    {
        "coin": "TAO",
        "strategy": "Supertrend EMA200",
        "params": {"atr_period": 10, "atr_multiplier": 3.0, "ema_length": 200},
        "label": "TAO Supertrend EMA200",
        "is_full_history": False
    }
]

# Date splits
IS_START_FULL  = "2023-01-01 00:00:00"
IS_END_FULL    = "2024-12-31 23:59:59"
OOS_START_FULL = "2025-01-01 00:00:00"

IS_START_SHORT  = "2024-01-01 00:00:00"
IS_END_SHORT    = "2025-12-31 23:59:59"
OOS_START_SHORT = "2026-01-01 00:00:00"

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
        for f in os.listdir(ticker_dir):
            if f.lower().endswith(f"{timeframe.lower()}.csv"):
                filepath = os.path.join(ticker_dir, f)
                break

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
                return None

        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.sort_values("timestamp", inplace=True)
        df.drop_duplicates(subset=["timestamp"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    except Exception as exc:
        print(f"  [ERROR] Loading {symbol}: {exc}")
        return None

# ─────────────────────────── INDICATORS ────────────────────────────────────────
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat(
        [h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1
    ).max(axis=1)

def calc_atr(df: pd.DataFrame, period: int) -> pd.Series:
    return true_range(df).rolling(period).mean()

# ─────────────────────────── SIGNAL BUILDERS ───────────────────────────────────
def build_donchian_signals(df, channel_length, stop_length):
    high, low, close = df["high"], df["low"], df["close"]
    signals = pd.DataFrame(
        {"side": "", "stop_loss": np.nan, "exit_long": False, "exit_short": False},
        index=df.index,
    )
    if len(df) < max(channel_length, stop_length, 20):
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
    if len(df) < max(ema_length, atr_period, 20):
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
def build_vbt_inputs(df, signals, rr):
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

    tp_stop = sl_stop * rr

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

def calculate_cagr(final_balance, initial_balance, start_date, end_date):
    days = (end_date - start_date).total_seconds() / 86400.0
    if days <= 0 or final_balance <= 0:
        return -100.0
    return float(((final_balance / initial_balance) ** (365.25 / days) - 1.0) * 100)

def compute_metrics(sim_trades, final_balance, equity_curve, exit_dates, start_date, end_date):
    total_trades = len(sim_trades)
    net_profit   = final_balance - INITIAL_BALANCE
    cagr = calculate_cagr(final_balance, INITIAL_BALANCE, start_date, end_date)

    if total_trades == 0:
        return {
            "Net Profit":    0.0,
            "Profit Factor": 0.0,
            "Sharpe Ratio":  0.0,
            "Max Drawdown":  0.0,
            "Win Rate":      0.0,
            "Trades":        0,
            "CAGR":          -100.0
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
        "CAGR":          round(cagr, 2)
    }

# ─────────────────────────── BACKTEST PERIOD RUNNER ────────────────────────────
def run_period_backtest(df_full: pd.DataFrame, config: dict, start_str: str, end_str: str) -> dict | None:
    # 1. Generate signals on full dataframe to prevent boundary effects
    strategy = config["strategy"]
    params = config["params"]

    if strategy == "Donchian Breakout":
        signals_full = build_donchian_signals(df_full, params["channel_length"], params["stop_length"])
    elif strategy == "Supertrend EMA200":
        signals_full = build_supertrend_signals(df_full, params["atr_period"], params["atr_multiplier"], params["ema_length"])
    else:
        return None

    # 2. Slice both df and signals to the requested period
    start_ts = pd.Timestamp(start_str, tz="UTC")
    end_ts   = pd.Timestamp(end_str, tz="UTC")

    mask = (df_full["timestamp"] >= start_ts) & (df_full["timestamp"] <= end_ts)
    df_period = df_full.loc[mask].reset_index(drop=True)
    signals_period = signals_full.loc[mask].reset_index(drop=True)

    if len(df_period) < 30 or signals_period["side"].eq("").all():
        return None

    # 3. Build VBT inputs and run backtest
    entries, short_entries, exits, short_exits, sl_stop, tp_stop, sl_pct_map = build_vbt_inputs(
        df_period, signals_period, 3.0 # Fixed 1:3 RR
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
            tp_stop       = tp_stop,
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

        return compute_metrics(
            sim_trades, final_balance, equity_curve, exit_dates, 
            df_period["timestamp"].min(), df_period["timestamp"].max()
        )
    except Exception as exc:
        print(f"  [ERROR] Running period simulation: {exc}")
        return None

# ─────────────────────────── MAIN ──────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 80)
    print("  PHASE 9 - FORWARD TEST SIMULATOR")
    print("=" * 80)

    # 1. Load Data
    raw_data = {}
    needed_coins = set(c["coin"] for c in CANDIDATES)
    for coin in needed_coins:
        df = load_symbol_timeframe(coin, TIMEFRAME)
        if df is not None and not df.empty:
            raw_data[coin] = df
            print(f"  Loaded {coin} data: {len(df)} candles")
        else:
            print(f"  [FATAL] Failed to load {coin}")
            return

    forward_test_results = []
    degradation_results = []

    print("\n" + "-" * 80)
    print("  Simulating In-Sample and Out-of-Sample slices...")
    print("-" * 80)

    for cand in CANDIDATES:
        coin = cand["coin"]
        label = cand["label"]
        df_full = raw_data[coin]

        # Define split strings based on history type
        if cand["is_full_history"]:
            is_start, is_end, oos_start = IS_START_FULL, IS_END_FULL, OOS_START_FULL
        else:
            is_start, is_end, oos_start = IS_START_SHORT, IS_END_SHORT, OOS_START_SHORT

        oos_end = df_full["timestamp"].max().strftime("%Y-%m-%d %H:%M:%S")

        print(f"  Running: {label}")
        print(f"    In-Sample:  {is_start} to {is_end}")
        print(f"    Out-of-Sample: {oos_start} to {oos_end}")

        # Run In-Sample
        is_metrics = run_period_backtest(df_full, cand, is_start, is_end)
        # Run Out-of-Sample (Forward Test)
        oos_metrics = run_period_backtest(df_full, cand, oos_start, oos_end)

        if is_metrics is None or oos_metrics is None:
            print(f"    [WARN] Failed to get metrics for {label}")
            continue

        # Log details to forward_test_results
        for period, m in [("In-Sample", is_metrics), ("Out-of-Sample", oos_metrics)]:
            forward_test_results.append({
                "Configuration": label,
                "Period": period,
                "Profit Factor": m["Profit Factor"],
                "Sharpe Ratio": m["Sharpe Ratio"],
                "Max Drawdown": m["Max Drawdown"],
                "Net Profit": m["Net Profit"],
                "Trades": m["Trades"],
                "CAGR": m["CAGR"],
                "Win Rate": m["Win Rate"]
            })

        # Calculate Degradation
        # Degradation % = (IS - OOS) / IS * 100
        # If IS is negative or zero, we report NaN or raw difference
        is_pf = is_metrics["Profit Factor"]
        oos_pf = oos_metrics["Profit Factor"]
        pf_deg = ((is_pf - oos_pf) / is_pf * 100) if is_pf > 0 else np.nan

        is_sr = is_metrics["Sharpe Ratio"]
        oos_sr = oos_metrics["Sharpe Ratio"]
        sr_deg = ((is_sr - oos_sr) / is_sr * 100) if is_sr > 0 else np.nan

        # CAGR degradation handles duration difference fairly
        is_cagr = is_metrics["CAGR"]
        oos_cagr = oos_metrics["CAGR"]
        # If IS CAGR is positive, standard % change, if negative, standard change
        if is_cagr > 0:
            cagr_deg = (is_cagr - oos_cagr) / is_cagr * 100
        else:
            cagr_deg = is_cagr - oos_cagr # Raw difference

        raw_profit_deg = ((is_metrics["Net Profit"] - oos_metrics["Net Profit"]) / is_metrics["Net Profit"] * 100) if is_metrics["Net Profit"] > 0 else np.nan

        # We will rank by Out-of-Sample Sharpe and lowest average degradation
        degradation_results.append({
            "Configuration": label,
            "In-Sample PF": is_pf,
            "Out-of-Sample PF": oos_pf,
            "PF Degradation %": round(pf_deg, 2) if not pd.isna(pf_deg) else "N/A",
            
            "In-Sample Sharpe": is_sr,
            "Out-of-Sample Sharpe": oos_sr,
            "Sharpe Degradation %": round(sr_deg, 2) if not pd.isna(sr_deg) else "N/A",
            
            "In-Sample CAGR": is_cagr,
            "Out-of-Sample CAGR": oos_cagr,
            "CAGR Degradation %": round(cagr_deg, 2) if not pd.isna(cagr_deg) else "N/A",

            "In-Sample Profit": is_metrics["Net Profit"],
            "Out-of-Sample Profit": oos_metrics["Net Profit"],
            "Profit Degradation %": round(raw_profit_deg, 2) if not pd.isna(raw_profit_deg) else "N/A",

            "IS Trades": is_metrics["Trades"],
            "OOS Trades": oos_metrics["Trades"]
        })

    # Save forward_test.csv
    df_ft = pd.DataFrame(forward_test_results)
    ft_path = os.path.join(RESULTS_DIR, "forward_test.csv")
    df_ft.to_csv(ft_path, index=False)
    print(f"\n  Saved forward test detailed metrics -> {ft_path}")

    # Save degradation_report.csv
    df_deg = pd.DataFrame(degradation_results)
    
    # Sort degradation report:
    # A config is robust if it has strong OOS performance and low degradation.
    # We rank by:
    # 1. Out-of-Sample Sharpe Ratio (descending)
    # 2. Out-of-Sample PF (descending)
    df_deg.sort_values(by="Out-of-Sample Sharpe", ascending=False, inplace=True)
    df_deg.reset_index(drop=True, inplace=True)
    df_deg.index = df_deg.index + 1
    df_deg.index.name = "Robustness Rank"
    
    deg_path = os.path.join(RESULTS_DIR, "degradation_report.csv")
    df_deg.to_csv(deg_path)
    print(f"  Saved degradation report -> {deg_path}")

    # Display console comparison
    print("\n" + "=" * 100)
    print("  FORWARD TEST COMPARISON & DEGRADATION REPORT")
    print("=" * 100)
    for rank, row in df_deg.iterrows():
        print(f"Rank [{rank}] | {row['Configuration']}")
        print(f"  Profit Factor: In-Sample = {row['In-Sample PF']:.2f} | Out-of-Sample = {row['Out-of-Sample PF']:.2f} | Degradation = {row['PF Degradation %']}%")
        print(f"  Sharpe Ratio:  In-Sample = {row['In-Sample Sharpe']:.2f} | Out-of-Sample = {row['Out-of-Sample Sharpe']:.2f} | Degradation = {row['Sharpe Degradation %']}%")
        print(f"  CAGR (Annual): In-Sample = {row['In-Sample CAGR']:.2f}% | Out-of-Sample = {row['Out-of-Sample CAGR']:.2f}% | Degradation = {row['CAGR Degradation %']}%")
        print(f"  Trades:        In-Sample = {row['IS Trades']} | Out-of-Sample = {row['OOS Trades']}")
        print("-" * 100)

    elapsed = time.time() - t0
    print(f"\n  Completed forward testing simulator in {elapsed:.1f}s")

if __name__ == "__main__":
    main()
