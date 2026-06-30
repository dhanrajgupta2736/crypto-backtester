"""
Phase 6 Exit Research
=======================
Tests 12 distinct exit methodologies to isolate whether severe drawdowns
are structurally tied to the entries or rigid Fixed RR exits.
"""

import os
import time
import math
import numpy as np
import pandas as pd
from numba import njit

# ─────────────────────────── CONFIG ────────────────────────────────────────────
DATA_DIR    = "data"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

INITIAL_BALANCE = 1_000.0
RISK_PER_TRADE  = 100.0
LEVERAGE        = 5.0
FEE_RATE        = 0.0005   # 0.05 %
SLIPPAGE_RATE   = 0.0002   # 0.02 %

P6_COINS      = {"TAO", "ZEC", "TRX"}
P6_STRATEGIES = {"Donchian Breakout", "Turtle Trading", "Supertrend EMA200"}
P6_TIMEFRAME  = "1H"

# ─────────────────────────── DATA & INDICATORS ───────────────────────────────
def load_symbol_timeframe(symbol: str, timeframe: str) -> pd.DataFrame | None:
    ticker_dir = os.path.join(DATA_DIR, symbol)
    if not os.path.isdir(ticker_dir): return None
    candidates = [f"{timeframe}.csv", f"{timeframe.upper()}.csv", f"{symbol}_{timeframe}.csv"]
    filepath = next((os.path.join(ticker_dir, n) for n in candidates if os.path.exists(os.path.join(ticker_dir, n))), None)
    if not filepath:
        # Check all files
        for f in os.listdir(ticker_dir):
            if f.lower().endswith(f"{timeframe.lower()}.csv"):
                filepath = os.path.join(ticker_dir, f)
                break
    if not filepath: return None

    try:
        df = pd.read_csv(filepath)
        col_map = {c: "timestamp" if c.lower() in ("timestamp", "date", "datetime") else c.lower() for c in df.columns}
        df.rename(columns=col_map, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.sort_values("timestamp", inplace=True)
        df.drop_duplicates(subset=["timestamp"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    except:
        return None

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)

def calc_atr(df: pd.DataFrame, period: int) -> pd.Series:
    return true_range(df).rolling(period).mean()

# ─────────────────────────── SIGNAL BUILDERS ───────────────────────────────────
def build_base_signals(df, strategy, params):
    high, low, close = df["high"], df["low"], df["close"]
    signals = pd.DataFrame(
        {"long_sig": False, "short_sig": False, "stop_loss_long": np.nan, "stop_loss_short": np.nan, 
         "native_exit_long": False, "native_exit_short": False},
        index=df.index,
    )

    if strategy == "Turtle Trading":
        bl, el = params["breakout_length"], params["exit_length"]
        atr20 = calc_atr(df, 20)
        entry_upper = high.shift(1).rolling(bl).max()
        entry_lower = low.shift(1).rolling(bl).min()
        exit_lower  = low.shift(1).rolling(el).min()
        exit_upper  = high.shift(1).rolling(el).max()

        signals["long_sig"]  = close > entry_upper
        signals["short_sig"] = close < entry_lower
        signals["stop_loss_long"]  = (close - 2 * atr20).where(lambda s: s < close, close * 0.99)
        signals["stop_loss_short"] = (close + 2 * atr20).where(lambda s: s > close, close * 1.01)
        signals["native_exit_long"]  = close < exit_lower
        signals["native_exit_short"] = close > exit_upper

    elif strategy == "Donchian Breakout":
        cl, sl = params["channel_length"], params["stop_length"]
        upper_channel = high.shift(1).rolling(cl).max()
        lower_channel = low.shift(1).rolling(cl).min()
        l_stop = low.shift(1).rolling(sl).min()
        s_stop = high.shift(1).rolling(sl).max()

        signals["long_sig"]  = close > upper_channel
        signals["short_sig"] = close < lower_channel
        signals["stop_loss_long"]  = l_stop.where(l_stop < close, close * 0.99)
        signals["stop_loss_short"] = s_stop.where(s_stop > close, close * 1.01)
        # Donchian native exit: closing beyond opposite side of entry channel (usually halfway or shorter channel, here we use the stop channel as exit)
        signals["native_exit_long"]  = close < l_stop
        signals["native_exit_short"] = close > s_stop

    elif strategy == "Supertrend EMA200":
        ap, am, el = params["atr_period"], params["atr_multiplier"], params["ema_length"]
        ema_filter = ema(close, el)
        atr = calc_atr(df, ap)
        hl2 = (high + low) / 2
        atr_val, close_val, hl2_val = atr.values, close.values, hl2.values
        n = len(df)
        upperband, lowerband, in_uptrend = np.zeros(n), np.zeros(n), np.ones(n, dtype=bool)

        for i in range(1, n):
            if np.isnan(atr_val[i]):
                upperband[i] = lowerband[i] = hl2_val[i]
                continue
            basic_ub = hl2_val[i] + am * atr_val[i]
            basic_lb = hl2_val[i] - am * atr_val[i]
            upperband[i] = basic_ub if (basic_ub < upperband[i-1] or close_val[i-1] > upperband[i-1]) else upperband[i-1]
            lowerband[i] = basic_lb if (basic_lb > lowerband[i-1] or close_val[i-1] < lowerband[i-1]) else lowerband[i-1]
            if   close_val[i] > upperband[i-1]: in_uptrend[i] = True
            elif close_val[i] < lowerband[i-1]: in_uptrend[i] = False
            else:                               in_uptrend[i] = in_uptrend[i-1]

        uptrend = pd.Series(in_uptrend, index=df.index)
        flip_up = uptrend & (~uptrend.shift(1).fillna(True))
        flip_dn = (~uptrend) & uptrend.shift(1).fillna(False)

        signals["long_sig"]  = flip_up & (close > ema_filter)
        signals["short_sig"] = flip_dn & (close < ema_filter)
        lb_series = pd.Series(lowerband, index=df.index)
        ub_series = pd.Series(upperband, index=df.index)
        signals["stop_loss_long"]  = lb_series.where(lb_series < close, close * 0.99)
        signals["stop_loss_short"] = ub_series.where(ub_series > close, close * 1.01)
        signals["native_exit_long"]  = flip_dn
        signals["native_exit_short"] = flip_up

    return signals

# ─────────────────────────── CUSTOM FAST TRADE SIMULATOR ───────────────────
def simulate_trade_loop(df, signals, atr14, atr22, exit_type):
    # Unpack series to numpy for fast looping
    open_p  = df['open'].values
    high_p  = df['high'].values
    low_p   = df['low'].values
    close_p = df['close'].values
    
    entries = signals['long_sig'].values
    shorts  = signals['short_sig'].values
    sl_l    = signals['stop_loss_long'].values
    sl_s    = signals['stop_loss_short'].values
    nx_l    = signals['native_exit_long'].values
    nx_s    = signals['native_exit_short'].values
    
    atr14_v = atr14.values
    atr22_v = atr22.values
    
    trades = []
    in_trade = False
    side = 0 # 1 long, -1 short
    ep = 0.0
    initial_sl = 0.0
    sl = 0.0
    tp = 0.0
    hh = 0.0
    ll = 0.0
    entry_idx = 0
    
    # Parse exit properties
    is_fixed = "Fixed RR" in exit_type
    rr_val = 0.0
    if is_fixed:
        rr_val = float(exit_type.split(":")[-1])
        
    is_atr = "ATR Trailing" in exit_type
    atr_mult = 0.0
    if is_atr: atr_mult = float(exit_type.split("(")[1].split(" ")[0])
    
    is_chand = "Chandelier" in exit_type
    chand_mult = 0.0
    if is_chand: chand_mult = float(exit_type.split("(")[1].split(" ")[0])
    
    is_native = "Native" in exit_type
    
    is_be = "Break-Even" in exit_type
    be_native = "Native" in exit_type and is_be
    be_fixed  = "1:3" in exit_type and is_be
    
    for i in range(1, len(df)):
        if in_trade:
            h, l, c = high_p[i], low_p[i], close_p[i]
            
            # Update trackers
            if h > hh: hh = h
            if l < ll: ll = l
            
            # Dynamic Stop adjustments
            if is_atr:
                if side == 1:
                    trail = c - atr_mult * atr14_v[i]
                    if trail > sl: sl = trail
                else:
                    trail = c + atr_mult * atr14_v[i]
                    if trail < sl: sl = trail
            
            elif is_chand:
                if side == 1:
                    trail = hh - chand_mult * atr22_v[i]
                    if trail > sl: sl = trail
                else:
                    trail = ll + chand_mult * atr22_v[i]
                    if trail < sl: sl = trail
                    
            elif is_be:
                r_dist = abs(ep - initial_sl)
                if side == 1 and h >= ep + r_dist:
                    if sl < ep: sl = ep
                elif side == -1 and l <= ep - r_dist:
                    if sl > ep: sl = ep

            # Intra-bar exit checks
            exit_price = 0.0
            triggered = False
            
            if side == 1:
                if l <= sl:
                    exit_price = sl
                    triggered = True
                elif (is_fixed or be_fixed) and h >= tp:
                    exit_price = tp
                    triggered = True
                elif (is_native or be_native) and nx_l[i]:
                    exit_price = c
                    triggered = True
            else:
                if h >= sl:
                    exit_price = sl
                    triggered = True
                elif (is_fixed or be_fixed) and l <= tp:
                    exit_price = tp
                    triggered = True
                elif (is_native or be_native) and nx_s[i]:
                    exit_price = c
                    triggered = True
                    
            if triggered:
                pnl = (exit_price - ep)/ep if side == 1 else (ep - exit_price)/ep
                sl_pct = abs(ep - initial_sl)/ep
                trades.append({
                    "entry_price": ep,
                    "exit_price": exit_price,
                    "direction": "long" if side == 1 else "short",
                    "pnl_pct": pnl,
                    "initial_sl_pct": sl_pct,
                    "exit_date": df['timestamp'].iloc[i]
                })
                in_trade = False
                continue
                
        # Check entries
        if not in_trade:
            if entries[i-1]:
                if pd.isna(sl_l[i-1]) or sl_l[i-1] <= 0: continue
                ep = open_p[i]
                initial_sl = sl_l[i-1]
                if initial_sl >= ep: continue # Invalid
                
                in_trade = True
                side = 1
                sl = initial_sl
                hh = high_p[i]
                ll = low_p[i]
                entry_idx = i
                
                if is_fixed: tp = ep + (ep - sl) * rr_val
                elif be_fixed: tp = ep + (ep - sl) * 3.0
                
            elif shorts[i-1]:
                if pd.isna(sl_s[i-1]) or sl_s[i-1] <= 0: continue
                ep = open_p[i]
                initial_sl = sl_s[i-1]
                if initial_sl <= ep: continue # Invalid
                
                in_trade = True
                side = -1
                sl = initial_sl
                hh = high_p[i]
                ll = low_p[i]
                entry_idx = i
                
                if is_fixed: tp = ep - (sl - ep) * rr_val
                elif be_fixed: tp = ep - (sl - ep) * 3.0

    return trades

def _daily_sharpe(equity_curve, exit_dates):
    if len(exit_dates) < 2: return 0.0
    df_eq = pd.DataFrame({"Date": pd.to_datetime(exit_dates), "Balance": equity_curve[1:]})
    df_eq["Date"] = df_eq["Date"].dt.normalize()
    daily = df_eq.groupby("Date")["Balance"].last()
    full_idx = pd.date_range(start=daily.index.min(), end=daily.index.max(), freq="D")
    daily = daily.reindex(full_idx).ffill()
    daily_pct = daily.pct_change().dropna()
    if daily_pct.empty or daily_pct.std() == 0: return 0.0
    return float((daily_pct.mean() / daily_pct.std()) * np.sqrt(252))

def apply_leverage_sizing(trades_list):
    balance = INITIAL_BALANCE
    equity_curve = [balance]
    exit_dates = []
    processed_trades = []
    
    for t in trades_list:
        if balance <= 0: break
        
        ep = t["entry_price"]
        dist_pct = t["initial_sl_pct"]
        friction_pct = (2 * FEE_RATE + 2 * SLIPPAGE_RATE)
        
        # Sizing
        risk_qty = RISK_PER_TRADE / (ep * dist_pct + ep * friction_pct)
        max_qty  = (balance * LEVERAGE) / ep
        qty      = min(risk_qty, max_qty)
        
        raw_pnl = t["pnl_pct"] * ep * qty
        actual_pnl = raw_pnl - (qty * ep * friction_pct)
        
        balance = max(0.0, balance + actual_pnl)
        equity_curve.append(balance)
        exit_dates.append(t["exit_date"])
        
        new_t = t.copy()
        new_t["actual_pnl"] = actual_pnl
        processed_trades.append(new_t)
        
    return processed_trades, balance, equity_curve, exit_dates

def compute_metrics(trades_list, final_balance, equity_curve, exit_dates):
    total_trades = len(trades_list)
    net_profit = final_balance - INITIAL_BALANCE
    if total_trades == 0:
        return {"Net Profit": 0.0, "Profit Factor": 0.0, "Sharpe Ratio": 0.0, "Max Drawdown": 0.0, "Win Rate": 0.0, "Trades": 0}

    wins   = [t["actual_pnl"] for t in trades_list if t["actual_pnl"] > 0]
    losses = [t["actual_pnl"] for t in trades_list if t["actual_pnl"] <= 0]

    win_rate = len(wins) / total_trades * 100
    sum_wins = sum(wins)
    sum_losses = sum(losses)
    pf = 999.9 if sum_losses == 0 and sum_wins > 0 else 1.0 if sum_losses == 0 else abs(sum_wins / sum_losses)

    eq = pd.Series(equity_curve)
    cummax = eq.cummax()
    max_dd = float(((eq - cummax) / cummax.replace(0, 1e-9)).min() * -100)

    return {
        "Net Profit": round(net_profit, 2),
        "Profit Factor": round(pf, 4),
        "Sharpe Ratio": round(_daily_sharpe(equity_curve, exit_dates), 4),
        "Max Drawdown": round(max_dd, 2),
        "Win Rate": round(win_rate, 2),
        "Trades": total_trades,
    }

# ─────────────────────────── MAIN ──────────────────────────────────────────────
def extract_params(row, strategy):
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

def main():
    t0 = time.time()
    top50_path = os.path.join(RESULTS_DIR, "phase3_top50.csv")
    
    df_top = pd.read_csv(top50_path)
    mask = (df_top["Coin"].isin(P6_COINS)) & (df_top["Strategy"].isin(P6_STRATEGIES)) & (df_top["Timeframe"] == P6_TIMEFRAME)
    candidates = df_top.loc[mask].drop_duplicates(subset=["Coin", "Strategy", "Parameters"]).reset_index(drop=True)
    
    needed_coins = candidates["Coin"].unique()
    raw_data = {c: load_symbol_timeframe(c, P6_TIMEFRAME) for c in needed_coins}
    
    exit_types = [
        "Fixed RR 1:2",
        "Fixed RR 1:2.5",
        "Fixed RR 1:3",
        "ATR Trailing Stop (2 ATR)",
        "ATR Trailing Stop (3 ATR)",
        "ATR Trailing Stop (4 ATR)",
        "Chandelier Exit (2 ATR)",
        "Chandelier Exit (3 ATR)",
        "Chandelier Exit (4 ATR)",
        "Native Indicator Exit",
        "Break-Even Native",
        "Break-Even Fixed RR 1:3"
    ]
    
    all_results = []
    
    print(f"\n==========================================")
    print(f"  PHASE 6 - EXIT RESEARCH ({len(candidates)} configs)")
    print(f"==========================================")
    
    for i, row in candidates.iterrows():
        coin, strategy, param_str = row["Coin"], row["Strategy"], row["Parameters"]
        df = raw_data[coin]
        if df is None: continue
        
        print(f"[{i+1}/{len(candidates)}] {coin} | {strategy} | {param_str}")
        
        params = extract_params(row, strategy)
        signals = build_base_signals(df, strategy, params)
        
        atr14 = calc_atr(df, 14)
        atr22 = calc_atr(df, 22)
        
        baseline_metrics = None
        config_runs = {}
        
        # Run all exits
        for et in exit_types:
            trades = simulate_trade_loop(df, signals, atr14, atr22, et)
            p_trades, bal, eq, dts = apply_leverage_sizing(trades)
            m = compute_metrics(p_trades, bal, eq, dts)
            config_runs[et] = m
            if et == "Fixed RR 1:2.5":
                baseline_metrics = m
                
        # Compile relative changes
        for et in exit_types:
            m = config_runs[et]
            
            pf_chg = m["Profit Factor"] - baseline_metrics["Profit Factor"]
            dd_chg = m["Max Drawdown"] - baseline_metrics["Max Drawdown"]
            np_chg = m["Net Profit"] - baseline_metrics["Net Profit"]
            
            all_results.append({
                "Coin": coin,
                "Strategy": strategy,
                "Parameters": param_str,
                "Exit Type": et,
                "Net Profit": m["Net Profit"],
                "Max Drawdown": m["Max Drawdown"],
                "Profit Factor": m["Profit Factor"],
                "Sharpe Ratio": m["Sharpe Ratio"],
                "Trades": m["Trades"],
                "Win Rate": m["Win Rate"],
                "Drawdown Change": round(dd_chg, 2),
                "Profit Factor Change": round(pf_chg, 4),
                "Net Profit Change": round(np_chg, 2)
            })

    # Save outputs
    df_out = pd.DataFrame(all_results)
    df_out.to_csv(os.path.join(RESULTS_DIR, "exit_comparison.csv"), index=False)
    
    # Rankings
    rankings = df_out.groupby("Exit Type").agg({
        "Max Drawdown": "mean",
        "Profit Factor": "mean",
        "Sharpe Ratio": "mean",
        "Net Profit": "mean",
        "Drawdown Change": "mean"
    }).round(2).reset_index()
    
    # Sort by lowest average drawdown
    rankings.sort_values("Max Drawdown", inplace=True)
    rankings.to_csv(os.path.join(RESULTS_DIR, "exit_rankings.csv"), index=False)
    
    print("\n[SUCCESS] Completed in {:.1f}s".format(time.time() - t0))

if __name__ == "__main__":
    main()
