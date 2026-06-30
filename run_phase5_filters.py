"""
Phase 5 Filter Research
=======================
Tests specific market filters against baseline breakout/trend strategies
to evaluate their effectiveness at reducing drawdown.

Filters:
1. ADX > 25
2. Trend (Close vs EMA200)
3. Volatility (ATR14 > ATR50)
4. Volume (Volume > SMA20)
5. Combined (ADX + Trend + ATR)
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

# Phase 5 scope
P5_COINS      = {"TAO", "ZEC", "TRX"}
P5_STRATEGIES = {"Donchian Breakout", "Turtle Trading", "Supertrend EMA200"}
P5_TIMEFRAME  = "1H"
P5_RR_VALUES  = {2.5, 3.0}

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

        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.sort_values("timestamp", inplace=True)
        df.drop_duplicates(subset=["timestamp"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    except Exception as exc:
        return None

# ─────────────────────────── INDICATORS ────────────────────────────────────────
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()

def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat(
        [h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1
    ).max(axis=1)

def calc_atr(df: pd.DataFrame, period: int) -> pd.Series:
    return true_range(df).rolling(period).mean()

def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    tr = true_range(df)
    
    # Wilder's Smoothing
    def wilder_smooth(series: pd.Series, n: int) -> pd.Series:
        smoothed = np.zeros(len(series))
        # Initial SMA for first value
        smoothed[n-1] = series[:n].sum()
        for i in range(n, len(series)):
            smoothed[i] = smoothed[i-1] - (smoothed[i-1] / n) + series.iloc[i]
        return pd.Series(smoothed, index=series.index)
        
    smoothed_tr = wilder_smooth(tr, period)
    smoothed_pdm = wilder_smooth(pd.Series(plus_dm), period)
    smoothed_mdm = wilder_smooth(pd.Series(minus_dm), period)
    
    plus_di = 100 * (smoothed_pdm / smoothed_tr)
    minus_di = 100 * (smoothed_mdm / smoothed_tr)
    
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan))
    adx = wilder_smooth(dx, period)
    return adx

# ─────────────────────────── SIGNAL BUILDERS ───────────────────────────────────
def build_base_signals(df, strategy, params):
    high, low, close = df["high"], df["low"], df["close"]
    signals = pd.DataFrame(
        {"long_sig": False, "short_sig": False, "stop_loss_long": np.nan, "stop_loss_short": np.nan, 
         "exit_long": False, "exit_short": False},
        index=df.index,
    )

    if strategy == "Turtle Trading":
        breakout_length = params["breakout_length"]
        exit_length = params["exit_length"]
        
        atr20 = calc_atr(df, 20)
        entry_upper = high.shift(1).rolling(breakout_length).max()
        entry_lower = low.shift(1).rolling(breakout_length).min()
        exit_lower  = low.shift(1).rolling(exit_length).min()
        exit_upper  = high.shift(1).rolling(exit_length).max()

        signals["long_sig"]  = close > entry_upper
        signals["short_sig"] = close < entry_lower

        signals["stop_loss_long"]  = (close - 2 * atr20).where(lambda s: s < close, close * 0.99)
        signals["stop_loss_short"] = (close + 2 * atr20).where(lambda s: s > close, close * 1.01)
        
        signals["exit_long"]  = close < exit_lower
        signals["exit_short"] = close > exit_upper

    elif strategy == "Donchian Breakout":
        channel_length = params["channel_length"]
        stop_length = params["stop_length"]
        
        upper_channel = high.shift(1).rolling(channel_length).max()
        lower_channel = low.shift(1).rolling(channel_length).min()
        l_stop = low.shift(1).rolling(stop_length).min()
        s_stop = high.shift(1).rolling(stop_length).max()

        signals["long_sig"]  = close > upper_channel
        signals["short_sig"] = close < lower_channel

        signals["stop_loss_long"]  = l_stop.where(l_stop < close, close * 0.99)
        signals["stop_loss_short"] = s_stop.where(s_stop > close, close * 1.01)

    elif strategy == "Supertrend EMA200":
        atr_period = params["atr_period"]
        atr_multiplier = params["atr_multiplier"]
        ema_length = params["ema_length"]
        
        ema_filter = ema(close, ema_length)
        atr = calc_atr(df, atr_period)

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

    return signals

def build_filter_conditions(df):
    adx14 = calc_adx(df, 14)
    ema200 = ema(df["close"], 200)
    atr14 = calc_atr(df, 14)
    atr50 = calc_atr(df, 50)
    vol20 = sma(df["volume"], 20)
    
    conds = {}
    conds["Unfiltered"] = {
        "long": pd.Series(True, index=df.index),
        "short": pd.Series(True, index=df.index)
    }
    
    # ADX Filter
    adx_mask = adx14 > 25
    conds["ADX Filter"] = {
        "long": adx_mask,
        "short": adx_mask
    }
    
    # Trend Filter
    conds["EMA200 Trend Filter"] = {
        "long": df["close"] > ema200,
        "short": df["close"] < ema200
    }
    
    # ATR Volatility Filter
    atr_mask = atr14 > atr50
    conds["ATR Volatility Filter"] = {
        "long": atr_mask,
        "short": atr_mask
    }
    
    # Volume Filter
    vol_mask = df["volume"] > vol20
    conds["Volume Filter"] = {
        "long": vol_mask,
        "short": vol_mask
    }
    
    # Combined Filter (ADX + Trend + ATR)
    conds["Combined Filter"] = {
        "long": adx_mask & (df["close"] > ema200) & atr_mask,
        "short": adx_mask & (df["close"] < ema200) & atr_mask
    }
    
    return conds

# ─────────────────────────── VBT & LEVERAGE SIM ──────────────────────────────
def build_vbt_inputs(df, signals, cond_long, cond_short, rr):
    index  = df.index
    n      = len(df)

    entries       = pd.Series(False, index=index)
    short_entries = pd.Series(False, index=index)
    sl_stop       = pd.Series(np.nan, index=index)
    tp_stop       = pd.Series(np.nan, index=index)
    sl_pct_map    = {}
    
    # Combine base signals with filters
    final_long_sig = signals["long_sig"] & cond_long
    final_short_sig = signals["short_sig"] & cond_short

    # Identify rows where a valid entry exists
    sig_rows = np.where(final_long_sig | final_short_sig)[0]
    
    for r in sig_rows:
        if r >= n - 1:
            continue
            
        is_long = final_long_sig.iloc[r]
        side = "long" if is_long else "short"
        sl_price = signals["stop_loss_long"].iloc[r] if is_long else signals["stop_loss_short"].iloc[r]
        
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
        tp_stop.iloc[entry_row]       = sl_pct * rr

    exits       = signals["exit_long"].copy()
    short_exits = signals["exit_short"].copy()

    # Force close at end of period
    exits.iloc[-1]       = True
    short_exits.iloc[-1] = True

    return entries, short_entries, exits, short_exits, sl_stop, tp_stop, sl_pct_map

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
        direction  = row["Direction"]

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
            "direction":   direction,
            "entry_price": ep,
            "exit_price":  exit_price,
            "qty":         qty,
            "exit_date":   exit_time,
        })

    return sim_trades, balance, equity_curve, exit_dates

def compute_metrics(sim_trades, final_balance, equity_curve, exit_dates):
    total_trades = len(sim_trades)
    net_profit   = final_balance - INITIAL_BALANCE

    if total_trades == 0:
        return {"Net Profit": 0.0, "Profit Factor": 0.0, "Sharpe Ratio": 0.0, "Max Drawdown": 0.0, "Win Rate": 0.0, "Trades": 0}

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
        "Net Profit":    round(net_profit, 2),
        "Profit Factor": round(profit_factor, 4),
        "Sharpe Ratio":  round(_daily_sharpe(equity_curve, exit_dates), 4),
        "Max Drawdown":  round(max_dd, 2),
        "Win Rate":      round(win_rate, 2),
        "Trades":        total_trades,
    }

def run_backtest_with_filter(df, signals, cond_long, cond_short, rr):
    entries, short_entries, exits, short_exits, sl_stop, tp_stop, sl_pct_map = build_vbt_inputs(
        df, signals, cond_long, cond_short, rr
    )

    if not entries.any() and not short_entries.any():
        return None

    order_price = df["open"].copy()
    order_price.iloc[-1] = df["close"].iloc[-1]

    try:
        pf = vbt.Portfolio.from_signals(
            close         = df["close"],
            entries       = entries,
            exits         = exits,
            short_entries = short_entries,
            short_exits   = short_exits,
            size          = 1.0,
            size_type     = "amount",
            price         = order_price,
            open          = df["open"],
            high          = df["high"],
            low           = df["low"],
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
            trades_df, sl_pct_map, df
        )
        return compute_metrics(sim_trades, final_balance, equity_curve, exit_dates)
    except Exception as exc:
        return None

# ─────────────────────────── MAIN ──────────────────────────────────────────────
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

def load_candidates(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Strategy"] = df["Strategy"].str.strip()
    
    # Apply user filters
    df["RR Float"] = df["RR Value"].apply(lambda x: float(x.split(":")[1]) if ":" in str(x) else float(x))
    
    mask = (
        df["Coin"].isin(P5_COINS)
        & df["Strategy"].isin(P5_STRATEGIES)
        & (df["Timeframe"] == P5_TIMEFRAME)
        & (df["RR Float"].isin(P5_RR_VALUES))
    )
    df = df.loc[mask].reset_index(drop=True)
    df = df.drop_duplicates(subset=["Coin", "Strategy", "Parameters", "RR Value"]).reset_index(drop=True)
    return df

def main():
    t0 = time.time()
    top50_path = os.path.join(RESULTS_DIR, "phase3_top50.csv")
    if not os.path.exists(top50_path):
        print(f"[FATAL] Cannot find {top50_path}.")
        return

    print("\n" + "="*70)
    print("  PHASE 5  -  FILTER RESEARCH")
    print("="*70)

    candidates = load_candidates(top50_path)
    if candidates.empty:
        print("[FATAL] No candidates matched Phase 5 filters.")
        return

    needed_coins = sorted(candidates["Coin"].unique())
    raw_data = {}

    for coin in needed_coins:
        df = load_symbol_timeframe(coin, P5_TIMEFRAME)
        if df is not None and not df.empty:
            raw_data[coin] = df
            print(f"  Loaded {coin}: {len(df)} bars")

    print(f"\n  Running filters on {len(candidates)} configurations ...\n")
    all_results = []
    total = len(candidates)

    filter_names = [
        "Unfiltered", "ADX Filter", "EMA200 Trend Filter", 
        "ATR Volatility Filter", "Volume Filter", "Combined Filter"
    ]

    for i, (_, row) in enumerate(candidates.iterrows(), 1):
        coin     = row["Coin"]
        strategy = row["Strategy"]
        rr       = row["RR Float"]
        params   = extract_params(row, strategy)
        param_str = row["Parameters"]

        if coin not in raw_data:
            continue

        df = raw_data[coin]
        print(f"  [{i:>2}/{total}] {coin} | {strategy} | RR 1:{rr} | {param_str}")
        
        # Build base signals
        signals = build_base_signals(df, strategy, params)
        
        # Build filter conditions
        conds = build_filter_conditions(df)
        
        config_runs = {}
        unfiltered_metrics = None
        
        for fname in filter_names:
            c_long = conds[fname]["long"]
            c_short = conds[fname]["short"]
            
            m = run_backtest_with_filter(df, signals, c_long, c_short, rr)
            if m is None:
                m = {"Net Profit": 0.0, "Profit Factor": 0.0, "Sharpe Ratio": 0.0, "Max Drawdown": 0.0, "Win Rate": 0.0, "Trades": 0}
                
            config_runs[fname] = m
            
            if fname == "Unfiltered":
                unfiltered_metrics = m

        # Compare and compile results
        for fname in filter_names:
            m = config_runs[fname]
            
            if fname == "Unfiltered" or unfiltered_metrics["Trades"] == 0:
                dd_red = 0.0
                pf_chg = 0.0
                tr_red = 0.0
            else:
                u_dd = unfiltered_metrics["Max Drawdown"]
                f_dd = m["Max Drawdown"]
                dd_red = ((u_dd - f_dd) / u_dd * 100) if u_dd > 0 else 0.0
                
                u_pf = unfiltered_metrics["Profit Factor"]
                f_pf = m["Profit Factor"]
                pf_chg = ((f_pf - u_pf) / u_pf * 100) if u_pf > 0 else 0.0
                
                u_tr = unfiltered_metrics["Trades"]
                f_tr = m["Trades"]
                tr_red = ((u_tr - f_tr) / u_tr * 100) if u_tr > 0 else 0.0

            all_results.append({
                "Coin": coin,
                "Strategy": strategy,
                "RR Value": f"1:{rr}",
                "Parameters": param_str,
                "Filter Name": fname,
                "Final Balance": round(1000.0 + m["Net Profit"], 2),
                "Net Profit": m["Net Profit"],
                "Profit Factor": m["Profit Factor"],
                "Sharpe Ratio": m["Sharpe Ratio"],
                "Max Drawdown": m["Max Drawdown"],
                "Win Rate": m["Win Rate"],
                "Trades": m["Trades"],
                "Drawdown Reduction %": round(dd_red, 2),
                "Profit Factor Change %": round(pf_chg, 2),
                "Trade Count Reduction %": round(tr_red, 2),
            })

    if not all_results:
        return

    df_out = pd.DataFrame(all_results)
    out_path = os.path.join(RESULTS_DIR, "filter_comparison.csv")
    df_out.to_csv(out_path, index=False)
    
    print(f"\n  Saved {len(df_out)} evaluation rows -> {out_path}")
    
    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    print(f"  Completed in {mins}m {secs}s")

if __name__ == "__main__":
    main()
