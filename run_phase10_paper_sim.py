"""
Phase 10 Paper Trading Simulator
================================
Runs a strict event-driven candle-by-candle simulation on TAO Supertrend EMA200.
Partitions:
    - Backtest (In-Sample): 2024 (2024-01-03 to 2024-12-31)
    - Forward Test (Out-of-Sample): 2025 (2025-01-01 to 2025-12-31)
    - Paper Trading (Event-Driven): 2026 YTD (2026-01-01 to 2026-06-19)
Generates:
    - results/paper_trade_log.csv
    - results/paper_vs_backtest.csv
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

# Dynamic Live Fee/Slippage Schedule
ENTRY_SLIPPAGE = 0.0002
EXIT_SLIPPAGE  = 0.0002
ENTRY_FEE      = 0.00045  # Taker
EXIT_FEE_SL    = 0.00045  # Taker for SL
EXIT_FEE_TP    = 0.00015  # Maker for TP

# Standard Constant rates for VBT comparison
VBT_FEE_RATE      = 0.0005
VBT_SLIPPAGE_RATE = 0.0002

TIMEFRAME = "1H"
TIMEFRAME_DELTA = pd.Timedelta(hours=1)

# Strategy Params
ATR_PERIOD     = 10
ATR_MULTIPLIER = 3.0
EMA_LENGTH     = 200
RR_VALUE       = 3.0

# ─────────────────────────── DATA LOADING ──────────────────────────────────────
def load_symbol_timeframe(symbol: str, timeframe: str) -> pd.DataFrame | None:
    ticker_dir = os.path.join(DATA_DIR, symbol)
    if not os.path.isdir(ticker_dir):
        return None

    candidates = [
        f"{timeframe}.csv", f"{timeframe.upper()}.csv", f"{timeframe.lower()}.csv",
        f"{symbol}_{timeframe}.csv", f"{symbol}_{timeframe.upper()}.csv", f"{symbol}_{timeframe.lower()}.csv"
    ]
    filepath = next((os.path.join(ticker_dir, n) for n in candidates if os.path.exists(os.path.join(ticker_dir, n))), None)
    if filepath is None:
        for f in os.listdir(ticker_dir):
            if f.lower().endswith(f"{timeframe.lower()}.csv"):
                filepath = os.path.join(ticker_dir, f)
                break
    if filepath is None:
        return None

    try:
        df = pd.read_csv(filepath)
        col_map = {c: "timestamp" if c.lower() in ("timestamp", "date", "datetime", "ts") else c.lower() for c in df.columns}
        df.rename(columns=col_map, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.sort_values("timestamp", inplace=True)
        df.drop_duplicates(subset=["timestamp"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    except Exception as exc:
        print(f"  [ERROR] Loading: {exc}")
        return None

# ─────────────────────────── INDICATORS & SIGNALS ──────────────────────────────
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)

def calc_atr(df: pd.DataFrame, period: int) -> pd.Series:
    return true_range(df).rolling(period).mean()

def build_supertrend_signals(df, atr_period, atr_multiplier, ema_length):
    high, low, close = df["high"], df["low"], df["close"]
    signals = pd.DataFrame(
        {"long_sig": False, "short_sig": False, "stop_loss_long": np.nan, "stop_loss_short": np.nan, 
         "exit_long": False, "exit_short": False},
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

    signals["long_sig"]  = flip_up & (close > ema_filter)
    signals["short_sig"] = flip_dn & (close < ema_filter)

    lb_series = pd.Series(lowerband, index=df.index)
    ub_series = pd.Series(upperband, index=df.index)
    signals["stop_loss_long"]  = lb_series.where(lb_series < close, close * 0.99)
    signals["stop_loss_short"] = ub_series.where(ub_series > close, close * 1.01)
    signals["exit_long"]  = flip_dn
    signals["exit_short"] = flip_up
    return signals

# ─────────────────────────── VBT SIMULATION FOR BASELINES ──────────────────────
def run_vbt_backtest(df_full: pd.DataFrame, signals_full: pd.DataFrame, start_str: str, end_str: str) -> dict | None:
    start_ts = pd.Timestamp(start_str, tz="UTC")
    end_ts   = pd.Timestamp(end_str, tz="UTC")
    mask = (df_full["timestamp"] >= start_ts) & (df_full["timestamp"] <= end_ts)
    df_period = df_full.loc[mask].reset_index(drop=True)
    signals_period = signals_full.loc[mask].reset_index(drop=True)

    if len(df_period) < 30 or not (signals_period["long_sig"].any() or signals_period["short_sig"].any()):
        return None

    # VBT Inputs
    index  = df_period.index
    n      = len(df_period)
    entries       = pd.Series(False, index=index)
    short_entries = pd.Series(False, index=index)
    sl_stop       = pd.Series(np.nan, index=index)
    sl_pct_map    = {}

    sig_rows = np.where(signals_period["long_sig"] | signals_period["short_sig"])[0]
    for r in sig_rows:
        if r >= n - 1: continue
        is_long = signals_period["long_sig"].iloc[r]
        sl_price = signals_period["stop_loss_long"].iloc[r] if is_long else signals_period["stop_loss_short"].iloc[r]
        if pd.isna(sl_price) or sl_price <= 0: continue

        entry_row = r + 1
        ep = df_period["open"].iloc[entry_row]
        if ep <= 0: continue

        dist = abs(ep - sl_price)
        sl_pct = dist / ep
        if sl_pct <= 0: continue

        entry_idx = df_period.index[entry_row]
        if is_long:
            entries.iloc[entry_row] = True
        else:
            short_entries.iloc[entry_row] = True

        sl_stop.iloc[entry_row] = sl_pct
        sl_pct_map[entry_idx] = sl_pct

    tp_stop = sl_stop * RR_VALUE

    exits = signals_period["exit_long"].copy()
    short_exits = signals_period["exit_short"].copy()
    exits.iloc[-1] = True
    short_exits.iloc[-1] = True

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
            fees          = VBT_FEE_RATE,
            slippage      = VBT_SLIPPAGE_RATE,
            init_cash     = 1_000_000.0,
            accumulate    = False,
            upon_opposite_entry = OppositeEntryMode.Ignore,
            stop_exit_price     = StopExitPrice.StopMarket,
            upon_stop_exit      = StopExitMode.Close,
            freq          = TIMEFRAME_DELTA,
        )

        if pf.trades.count() == 0: return None
        trades_df = pf.trades.records_readable

        # Resizing leverage
        balance = INITIAL_BALANCE
        equity_curve = [balance]
        exit_dates = []
        sim_trades = []

        trades_sorted = trades_df.sort_values("Entry Timestamp").reset_index(drop=True)
        for _, row in trades_sorted.iterrows():
            if balance <= 0: break
            ep = float(row["Avg Entry Price"])
            v_pnl = float(row["PnL"])
            v_qty = float(row["Size"])

            sl_pct = sl_pct_map.get(row["Entry Timestamp"])
            if sl_pct is None or sl_pct <= 0: continue

            dist = ep * sl_pct
            friction = ep * (2 * VBT_FEE_RATE + 2 * VBT_SLIPPAGE_RATE)

            risk_qty = RISK_PER_TRADE / (dist + friction)
            max_qty = (balance * LEVERAGE) / ep
            qty = min(risk_qty, max_qty)

            sim_pnl = v_pnl * (qty / v_qty) if v_qty != 0 else 0.0
            balance = max(0.0, balance + sim_pnl)
            equity_curve.append(balance)

            exit_idx = row["Exit Timestamp"]
            exit_time = df_period.loc[exit_idx, "timestamp"]
            exit_dates.append(exit_time)

            sim_trades.append({"pnl": sim_pnl, "exit_date": exit_time})

        # Calculate metrics
        total_trades = len(sim_trades)
        net_profit = balance - INITIAL_BALANCE
        if total_trades == 0:
            return {"PF": 0.0, "Sharpe": 0.0, "WR": 0.0, "Net Profit": 0.0, "Max DD": 0.0, "Trades": 0, "CAGR": -100.0}

        wins = [t["pnl"] for t in sim_trades if t["pnl"] > 0]
        losses = [t["pnl"] for t in sim_trades if t["pnl"] <= 0]
        win_rate = len(wins) / total_trades * 100
        pf_val = 999.9 if sum(losses) == 0 and sum(wins) > 0 else 1.0 if sum(losses) == 0 else abs(sum(wins) / sum(losses))

        eq = pd.Series(equity_curve)
        cummax = eq.cummax()
        max_dd = float(((eq - cummax) / cummax.replace(0, 1e-9)).min() * -100)

        # Sharpe
        df_eq = pd.DataFrame({"Date": pd.to_datetime(exit_dates), "Balance": equity_curve[1:]})
        df_eq["Date"] = df_eq["Date"].dt.normalize()
        daily = df_eq.groupby("Date")["Balance"].last()
        full_idx = pd.date_range(start=daily.index.min(), end=daily.index.max(), freq="D")
        daily = daily.reindex(full_idx).ffill()
        daily_pct = daily.pct_change().dropna()
        sharpe_val = float((daily_pct.mean() / daily_pct.std()) * np.sqrt(252)) if not daily_pct.empty and daily_pct.std() != 0 else 0.0

        days = (df_period["timestamp"].max() - df_period["timestamp"].min()).total_seconds() / 86400.0
        cagr = ((balance / INITIAL_BALANCE) ** (365.25 / days) - 1.0) * 100 if days > 0 and balance > 0 else -100.0

        return {
            "PF": round(pf_val, 4),
            "Sharpe": round(sharpe_val, 4),
            "WR": round(win_rate, 2),
            "Net Profit": round(net_profit, 2),
            "Max DD": round(max_dd, 2),
            "Trades": total_trades,
            "CAGR": round(cagr, 2)
        }
    except Exception as exc:
        print(f"  [ERROR] Baseline simulation: {exc}")
        return None

# ─────────────────────────── EVENT-DRIVEN PAPER SIMULATOR ──────────────────────
def run_paper_trading_simulator(df_full: pd.DataFrame, signals_full: pd.DataFrame, start_str: str, end_str: str):
    start_ts = pd.Timestamp(start_str, tz="UTC")
    end_ts   = pd.Timestamp(end_str, tz="UTC")
    mask = (df_full["timestamp"] >= start_ts) & (df_full["timestamp"] <= end_ts)
    df_period = df_full.loc[mask].reset_index(drop=True)
    signals_period = signals_full.loc[mask].reset_index(drop=True)

    n = len(df_period)
    balance = INITIAL_BALANCE
    equity_curve = [balance]
    exit_dates = []

    # Unpack series to numpy for fast execution
    open_p  = df_period['open'].values
    high_p  = df_period['high'].values
    low_p   = df_period['low'].values
    close_p = df_period['close'].values
    ts_p    = df_period['timestamp'].values

    long_sig_p  = signals_period['long_sig'].values
    short_sig_p = signals_period['short_sig'].values
    sl_long_p   = signals_period['stop_loss_long'].values
    sl_short_p  = signals_period['stop_loss_short'].values

    native_exit_long_p = signals_period['exit_long'].values
    native_exit_short_p = signals_period['exit_short'].values

    in_trade = False
    side = 0 # 1 long, -1 short
    ep = 0.0
    sl = 0.0
    tp = 0.0
    qty = 0.0
    entry_idx = 0
    entry_ts = None
    
    trade_log = []

    for i in range(1, n):
        # 1. Handle Active Trade Exit Checks
        if in_trade:
            h, l, c = high_p[i], low_p[i], close_p[i]
            exit_triggered = False
            exit_price = 0.0
            exit_reason = ""
            exit_fee_rate = EXIT_FEE_SL
            exit_slippage = EXIT_SLIPPAGE

            if side == 1: # Long position
                if l <= sl:
                    # Stop loss triggered
                    exit_price = sl
                    exit_reason = "Stop Loss"
                    exit_triggered = True
                    exit_fee_rate = EXIT_FEE_SL
                    exit_slippage = EXIT_SLIPPAGE
                elif h >= tp:
                    # Take profit triggered (maker execution)
                    exit_price = tp
                    exit_reason = "Take Profit"
                    exit_triggered = True
                    exit_fee_rate = EXIT_FEE_TP
                    exit_slippage = 0.0 # No slippage on Maker order
                elif native_exit_long_p[i] or i == n - 1:
                    # Native indicator flip or end of period (taker execution)
                    exit_price = c
                    exit_reason = "Indicator Exit" if not (i == n - 1) else "End of Period"
                    exit_triggered = True
                    exit_fee_rate = EXIT_FEE_SL
                    exit_slippage = EXIT_SLIPPAGE

            else: # Short position
                if h >= sl:
                    # Stop loss triggered
                    exit_price = sl
                    exit_reason = "Stop Loss"
                    exit_triggered = True
                    exit_fee_rate = EXIT_FEE_SL
                    exit_slippage = EXIT_SLIPPAGE
                elif l <= tp:
                    # Take profit triggered (maker execution)
                    exit_price = tp
                    exit_reason = "Take Profit"
                    exit_triggered = True
                    exit_fee_rate = EXIT_FEE_TP
                    exit_slippage = 0.0 # No slippage on Maker order
                elif native_exit_short_p[i] or i == n - 1:
                    # Native indicator flip or end of period (taker execution)
                    exit_price = c
                    exit_reason = "Indicator Exit" if not (i == n - 1) else "End of Period"
                    exit_triggered = True
                    exit_fee_rate = EXIT_FEE_SL
                    exit_slippage = EXIT_SLIPPAGE

            if exit_triggered:
                # Calculate entry transaction cost and exit transaction cost
                # long: PnL = qty * (exit_price_with_slippage - entry_price_with_slippage) - entry_fee - exit_fee
                # short: PnL = qty * (entry_price_with_slippage - exit_price_with_slippage) - entry_fee - exit_fee
                
                real_entry = ep * (1.0 + ENTRY_SLIPPAGE) if side == 1 else ep * (1.0 - ENTRY_SLIPPAGE)
                real_exit  = exit_price * (1.0 - exit_slippage) if side == 1 else exit_price * (1.0 + exit_slippage)
                
                entry_cost = qty * real_entry
                exit_recv  = qty * real_exit
                
                entry_f_amt = qty * ep * ENTRY_FEE
                exit_f_amt  = qty * exit_price * exit_fee_rate
                
                if side == 1:
                    pnl = (exit_recv - entry_cost) - entry_f_amt - exit_f_amt
                else:
                    pnl = (entry_cost - exit_recv) - entry_f_amt - exit_f_amt
                
                balance = max(0.0, balance + pnl)
                equity_curve.append(balance)
                
                exit_ts_formatted = pd.Timestamp(ts_p[i]).strftime("%Y-%m-%d %H:%M:%S")
                exit_dates.append(ts_p[i])

                r_mult = (exit_price - ep) / abs(ep - sl) if side == 1 else (ep - exit_price) / abs(ep - sl)
                slip_amt = qty * (ep * ENTRY_SLIPPAGE + exit_price * exit_slippage)
                fee_amt = entry_f_amt + exit_f_amt
                
                trade_log.append({
                    "timestamp": exit_ts_formatted,
                    "symbol": "TAO",
                    "side": "long" if side == 1 else "short",
                    "entry": round(ep, 4),
                    "stop": round(sl, 4),
                    "target": round(tp, 4),
                    "exit": round(exit_price, 4),
                    "r_multiple": round(r_mult, 4),
                    "pnl": round(pnl, 2),
                    "fees": round(fee_amt, 4),
                    "slippage": round(slip_amt, 4),
                    "equity_before": round(balance - pnl, 2),
                    "equity_after": round(balance, 2),
                    "strategy_version": "v1.0"
                })
                
                in_trade = False
                continue

        # 2. Check for New Entries
        if not in_trade:
            # Entry signal triggered at i-1, we execute on Open of bar i
            has_long_signal  = long_sig_p[i-1]
            has_short_signal = short_sig_p[i-1]

            if has_long_signal:
                sl_price = sl_long_p[i-1]
                if not pd.isna(sl_price) and sl_price > 0:
                    ep = open_p[i]
                    if sl_price < ep:
                        # Enter Long
                        sl_pct = (ep - sl_price) / ep
                        # Risk Sizing
                        risk_qty = RISK_PER_TRADE / (ep * sl_pct + ep * 0.0014) # Friction placeholder 0.14%
                        max_qty  = (balance * LEVERAGE) / ep
                        qty = min(risk_qty, max_qty)
                        
                        sl = sl_price
                        tp = ep + (ep - sl) * RR_VALUE
                        
                        in_trade = True
                        side = 1
                        entry_idx = i
                        entry_ts = pd.Timestamp(ts_p[i]).strftime("%Y-%m-%d %H:%M:%S")
                        
            elif has_short_signal:
                sl_price = sl_short_p[i-1]
                if not pd.isna(sl_price) and sl_price > 0:
                    ep = open_p[i]
                    if sl_price > ep:
                        # Enter Short
                        sl_pct = (sl_price - ep) / ep
                        # Risk Sizing
                        risk_qty = RISK_PER_TRADE / (ep * sl_pct + ep * 0.0014)
                        max_qty  = (balance * LEVERAGE) / ep
                        qty = min(risk_qty, max_qty)
                        
                        sl = sl_price
                        tp = ep - (sl - ep) * RR_VALUE
                        
                        in_trade = True
                        side = -1
                        entry_idx = i
                        entry_ts = pd.Timestamp(ts_p[i]).strftime("%Y-%m-%d %H:%M:%S")

    # Generate Metrics from event loop results
    total_trades = len(trade_log)
    net_profit = balance - INITIAL_BALANCE

    if total_trades == 0:
        metrics = {"PF": 0.0, "Sharpe": 0.0, "WR": 0.0, "Net Profit": 0.0, "Max DD": 0.0, "Trades": 0, "CAGR": -100.0}
    else:
        wins = [t["pnl"] for t in trade_log if t["pnl"] > 0]
        losses = [t["pnl"] for t in trade_log if t["pnl"] <= 0]
        win_rate = len(wins) / total_trades * 100
        pf_val = 999.9 if sum(losses) == 0 and sum(wins) > 0 else 1.0 if sum(losses) == 0 else abs(sum(wins) / sum(losses))

        eq = pd.Series(equity_curve)
        cummax = eq.cummax()
        max_dd = float(((eq - cummax) / cummax.replace(0, 1e-9)).min() * -100)

        # Sharpe
        df_eq = pd.DataFrame({"Date": pd.to_datetime(exit_dates), "Balance": equity_curve[1:]})
        df_eq["Date"] = df_eq["Date"].dt.normalize()
        daily = df_eq.groupby("Date")["Balance"].last()
        full_idx = pd.date_range(start=daily.index.min(), end=daily.index.max(), freq="D")
        daily = daily.reindex(full_idx).ffill()
        daily_pct = daily.pct_change().dropna()
        sharpe_val = float((daily_pct.mean() / daily_pct.std()) * np.sqrt(252)) if not daily_pct.empty and daily_pct.std() != 0 else 0.0

        days = (df_period["timestamp"].max() - df_period["timestamp"].min()).total_seconds() / 86400.0
        cagr = ((balance / INITIAL_BALANCE) ** (365.25 / days) - 1.0) * 100 if days > 0 and balance > 0 else -100.0

        metrics = {
            "PF": round(pf_val, 4),
            "Sharpe": round(sharpe_val, 4),
            "WR": round(win_rate, 2),
            "Net Profit": round(net_profit, 2),
            "Max DD": round(max_dd, 2),
            "Trades": total_trades,
            "CAGR": round(cagr, 2)
        }

    return trade_log, metrics

# ─────────────────────────── MAIN ──────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 80)
    print("  PHASE 10 - PAPER TRADING SIMULATOR")
    print("  Coin: TAO | Strategy: Supertrend EMA200 | Timeframe: 1H")
    print("=" * 80)

    # 1. Load Data
    df_full = load_symbol_timeframe("TAO", TIMEFRAME)
    if df_full is None or df_full.empty:
        print("[FATAL] Failed to load TAO data.")
        return
    print(f"  Loaded TAO data: {len(df_full)} candles")

    # 2. Build signals causally on full data first to prevent warm-up boundary effects
    signals_full = build_supertrend_signals(df_full, ATR_PERIOD, ATR_MULTIPLIER, EMA_LENGTH)
    print("  Generated signals causally on entire historical dataset.")

    # Dates
    is_start, is_end     = "2024-01-03 00:00:00", "2024-12-31 23:59:59"
    oos_start, oos_end   = "2025-01-01 00:00:00", "2025-12-31 23:59:59"
    paper_start, paper_end = "2026-01-01 00:00:00", df_full["timestamp"].max().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "-" * 80)
    print("  Running Simulations for the 3 Periods...")
    print("-" * 80)

    # 1. Backtest In-Sample (2024)
    print("  Running Backtest (In-Sample: 2024)...")
    is_m = run_vbt_backtest(df_full, signals_full, is_start, is_end)
    
    # 2. Forward Test Out-of-Sample (2025)
    print("  Running Forward Test (Out-of-Sample: 2025)...")
    oos_m = run_vbt_backtest(df_full, signals_full, oos_start, oos_end)

    # 3. Paper Trading Simulator Event-Driven Loop (2026 YTD)
    print("  Running Paper Trading Event-Driven Loop (2026 YTD)...")
    trade_log, paper_m = run_paper_trading_simulator(df_full, signals_full, paper_start, paper_end)

    if is_m is None or oos_m is None or paper_m is None:
        print("[FATAL] Simulation failed to produce metrics.")
        return

    # Write trade_log to paper_trades.csv and paper_trade_log.csv for backward compatibility
    df_log = pd.DataFrame(trade_log)
    log_path = os.path.join(RESULTS_DIR, "paper_trades.csv")
    df_log.to_csv(log_path, index=False)
    df_log.to_csv(os.path.join(RESULTS_DIR, "paper_trade_log.csv"), index=False)
    print(f"\n  Saved Paper Trading trade logs -> {log_path} and paper_trade_log.csv")


    # Create Comparison Matrix
    comparison_rows = []
    metrics_list = [
        ("Profit Factor", "PF", False),
        ("Sharpe Ratio", "Sharpe", False),
        ("Win Rate %", "WR", False),
        ("Net Profit $", "Net Profit", False),
        ("Max Drawdown %", "Max DD", True), # True means lower is better (drawdown)
        ("Trade Count", "Trades", False),
        ("Annualized Return % (CAGR)", "CAGR", False)
    ]

    for label, m_key, is_dd in metrics_list:
        is_val = is_m[m_key]
        oos_val = oos_m[m_key]
        paper_val = paper_m[m_key]

        # Calculate Degradation Backtest vs. Paper
        if is_val != 0:
            if is_dd:
                deg_bp = (paper_val - is_val) / is_val * 100  # Positive means drawdown increased
            else:
                deg_bp = (is_val - paper_val) / is_val * 100  # Positive means performance dropped
        else:
            deg_bp = np.nan

        # Calculate Degradation Forward vs. Paper
        if oos_val != 0:
            if is_dd:
                deg_fp = (paper_val - oos_val) / oos_val * 100
            else:
                deg_fp = (oos_val - paper_val) / oos_val * 100
        else:
            deg_fp = np.nan

        comparison_rows.append({
            "Metric": label,
            "Backtest (2024 IS)": is_val,
            "Forward Test (2025 OOS)": oos_val,
            "Paper Trading (2026 YTD)": paper_val,
            "Degradation % (Backtest vs. Paper)": round(deg_bp, 2) if not pd.isna(deg_bp) else "N/A",
            "Degradation % (Forward vs. Paper)": round(deg_fp, 2) if not pd.isna(deg_fp) else "N/A",
        })

    df_comp = pd.DataFrame(comparison_rows)
    comp_path = os.path.join(RESULTS_DIR, "paper_vs_backtest.csv")
    df_comp.to_csv(comp_path, index=False)
    print(f"  Saved Comparison Report -> {comp_path}")

    # Display Report
    print("\n" + "=" * 100)
    print("  METRIC DEGRADATION & STABILITY REPORT (TAO SUPERTREND EMA200)")
    print("=" * 100)
    print(f"{'Metric':<30} | {'2024 Backtest':<15} | {'2025 Forward':<15} | {'2026 Paper':<12} | {'Degrad (IS vs Paper)':<20} | {'Degrad (OOS vs Paper)':<20}")
    print("-" * 125)
    for _, r in df_comp.iterrows():
        print(f"{r['Metric']:<30} | {r['Backtest (2024 IS)']:<15} | {r['Forward Test (2025 OOS)']:<15} | {r['Paper Trading (2026 YTD)']:<12} | {r['Degradation % (Backtest vs. Paper)']:<20} | {r['Degradation % (Forward vs. Paper)']:<20}")
    print("-" * 125)

    elapsed = time.time() - t0
    print(f"\n  Completed Phase 10 Simulator in {elapsed:.1f}s")

if __name__ == "__main__":
    main()
