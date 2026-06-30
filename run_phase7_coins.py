"""
Phase 7 Coin Selection Research
===============================
Runs a parameter sweep (9 configurations) across 25 crypto assets on the 1H timeframe.
Computes Best/Average/Worst metrics, Pass Count, and a custom Coin Robustness Score.
Generates:
    - results/coin_rankings.csv (ranked by Robustness Score)
    - results/elite_coins.csv (PF >= 1.4, Sharpe >= 1.2, DD <= 35%)
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

COINS = [
    "BTC", "ETH", "XRP", "ADA", "SOL", "BNB", "DOGE", "TRX", "HYPE", "ZEC",
    "LINK", "HBAR", "LTC", "SUI", "NEAR", "AVAX", "TAO", "WLD", "UNI", "ONDO",
    "AAVE", "RENDER", "ENA", "INJ", "DOT"
]

# 9 strategy configurations
CONFIGS = [
    # Donchian Breakout (channel_length, stop_length=20)
    {"strategy": "Donchian Breakout", "params": {"channel_length": 20, "stop_length": 20}, "label": "Donchian 20"},
    {"strategy": "Donchian Breakout", "params": {"channel_length": 30, "stop_length": 20}, "label": "Donchian 30"},
    {"strategy": "Donchian Breakout", "params": {"channel_length": 50, "stop_length": 20}, "label": "Donchian 50"},
    
    # Turtle Trading (breakout_length, exit_length)
    {"strategy": "Turtle Trading", "params": {"breakout_length": 20, "exit_length": 10}, "label": "Turtle 20/10"},
    {"strategy": "Turtle Trading", "params": {"breakout_length": 30, "exit_length": 15}, "label": "Turtle 30/15"},
    {"strategy": "Turtle Trading", "params": {"breakout_length": 55, "exit_length": 20}, "label": "Turtle 55/20"},
    
    # Supertrend EMA200 (atr_period, atr_multiplier, ema_length=200)
    {"strategy": "Supertrend EMA200", "params": {"atr_period": 10, "atr_multiplier": 2.0, "ema_length": 200}, "label": "Supertrend ATR10x2"},
    {"strategy": "Supertrend EMA200", "params": {"atr_period": 10, "atr_multiplier": 3.0, "ema_length": 200}, "label": "Supertrend ATR10x3"},
    {"strategy": "Supertrend EMA200", "params": {"atr_period": 14, "atr_multiplier": 3.0, "ema_length": 200}, "label": "Supertrend ATR14x3"},
]

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
        # Fallback to scanning directory for any file ending with timeframe
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
def build_turtle_signals(df, breakout_length, exit_length):
    high, low, close = df["high"], df["low"], df["close"]
    signals = pd.DataFrame(
        {"side": "", "stop_loss": np.nan, "exit_long": False, "exit_short": False},
        index=df.index,
    )
    if len(df) < max(breakout_length, exit_length, 20):
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

# ─────────────────────────── BACKTEST RUNNER ───────────────────────────────────
def run_backtest(df: pd.DataFrame, config: dict, rr: float) -> dict | None:
    strategy = config["strategy"]
    params = config["params"]

    if strategy == "Turtle Trading":
        signals = build_turtle_signals(df, params["breakout_length"], params["exit_length"])
    elif strategy == "Donchian Breakout":
        signals = build_donchian_signals(df, params["channel_length"], params["stop_length"])
    elif strategy == "Supertrend EMA200":
        signals = build_supertrend_signals(df, params["atr_period"], params["atr_multiplier"], params["ema_length"])
    else:
        return None

    if signals["side"].eq("").all():
        return None

    entries, short_entries, exits, short_exits, sl_stop, tp_stop, sl_pct_map = build_vbt_inputs(
        df, signals, rr
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
def main():
    t0 = time.time()
    print("=" * 80)
    print("  PHASE 7 - COIN SELECTION RESEARCH")
    print("  Parameter Sweep: 9 Configurations | 25 Coins | 1H Timeframe | RR 1:3")
    print("=" * 80)

    # 1. Load Data
    raw_data = {}
    for coin in COINS:
        df = load_symbol_timeframe(coin, TIMEFRAME)
        if df is not None and not df.empty:
            raw_data[coin] = df
            print(f"  Loaded {coin:<6} | {len(df):>6} candles | {df['timestamp'].min().strftime('%Y-%m-%d')} to {df['timestamp'].max().strftime('%Y-%m-%d')}")
        else:
            print(f"  [WARN] Failed to load {coin}")

    print("\n" + "-" * 80)
    print(f"  Running simulations across {len(raw_data)} coins...")
    print("-" * 80)

    coin_results = []
    detailed_rows = []

    for coin, df in raw_data.items():
        pfs = []
        sharpes = []
        dds = []
        pass_count = 0
        
        print(f"  Processing {coin}...", end="", flush=True)
        coin_t0 = time.time()

        for config in CONFIGS:
            res = run_backtest(df, config, 3.0)
            if res is None:
                # 0 trades placeholder
                res = {
                    "Net Profit": 0.0, "Profit Factor": 0.0, "Sharpe Ratio": 0.0, 
                    "Max Drawdown": 0.0, "Win Rate": 0.0, "Trades": 0
                }

            pf = res["Profit Factor"]
            sr = res["Sharpe Ratio"]
            dd = res["Max Drawdown"]
            tr = res["Trades"]

            pfs.append(pf)
            sharpes.append(sr)
            dds.append(dd)

            # Check if this config passes robustness thresholds
            # Thresholds: PF >= 1.3, Sharpe >= 1.0, Max DD <= 35%, Trades >= 30
            is_pass = (pf >= 1.3) and (sr >= 1.0) and (dd <= 35.0) and (tr >= 30)
            if is_pass:
                pass_count += 1

            detailed_rows.append({
                "Coin": coin,
                "Strategy": config["strategy"],
                "Label": config["label"],
                "Params": str(config["params"]),
                "Net Profit": res["Net Profit"],
                "Profit Factor": pf,
                "Sharpe Ratio": sr,
                "Max Drawdown": dd,
                "Trades": tr,
                "Win Rate": res["Win Rate"],
                "Passed": is_pass
            })

        # Calculate aggregations
        best_pf = max(pfs)
        avg_pf = np.mean(pfs)
        worst_pf = min(pfs)

        best_sr = max(sharpes)
        avg_sr = np.mean(sharpes)

        best_dd = min(dds) # Lowest drawdown is "best"
        avg_dd = np.mean(dds)

        # Robustness Score Formula
        # (Pass Count * 10) + (Avg Sharpe * 5) + (Avg PF * 5) - (Avg DD * 0.2)
        robustness_score = (pass_count * 10.0) + (avg_sr * 5.0) + (avg_pf * 5.0) - (avg_dd * 0.2)

        coin_results.append({
            "Coin": coin,
            "Robustness Score": round(robustness_score, 4),
            "Pass Count": pass_count,
            "Best PF": round(best_pf, 4),
            "Average PF": round(avg_pf, 4),
            "Worst PF": round(worst_pf, 4),
            "Best Sharpe": round(best_sr, 4),
            "Average Sharpe": round(avg_sr, 4),
            "Best DD": round(best_dd, 2),
            "Average DD": round(avg_dd, 2)
        })
        
        print(f" done in {time.time() - coin_t0:.1f}s | Score: {robustness_score:.2f} | Passes: {pass_count}/9")

    # 2. Save Rankings
    df_rankings = pd.DataFrame(coin_results)
    df_rankings.sort_values(by="Robustness Score", ascending=False, inplace=True)
    df_rankings.reset_index(drop=True, inplace=True)
    
    rankings_path = os.path.join(RESULTS_DIR, "coin_rankings.csv")
    df_rankings.to_csv(rankings_path, index=False)
    print(f"\n  Saved coin rankings -> {rankings_path}")

    # 3. Save Detailed Results (for reference or diagnostics)
    df_detailed = pd.DataFrame(detailed_rows)
    detailed_path = os.path.join(RESULTS_DIR, "coin_detailed_sweep.csv")
    df_detailed.to_csv(detailed_path, index=False)
    print(f"  Saved detailed parameter sweep -> {detailed_path}")

    # 4. Save Elite Coins
    # Elite criteria: PF >= 1.4, Sharpe >= 1.2, DD <= 35% on average across configurations
    # Wait, let's verify if the user meant filtering by Average metrics or Best metrics.
    # We will filter based on the Average metrics to select truly robust elite coins.
    df_elite = df_rankings[
        (df_rankings["Average PF"] >= 1.4) & 
        (df_rankings["Average Sharpe"] >= 1.2) & 
        (df_rankings["Average DD"] <= 35.0)
    ].copy()
    
    elite_path = os.path.join(RESULTS_DIR, "elite_coins.csv")
    df_elite.to_csv(elite_path, index=False)
    print(f"  Saved elite coins (Strict criteria) -> {elite_path}")

    # 5. Display Summary
    print("\n" + "=" * 80)
    print("  COIN ROBUSTNESS SUMMARY")
    print("=" * 80)
    print(f"{'Coin':<6} | {'Score':<8} | {'Passes':<6} | {'Avg PF':<8} | {'Avg Sharpe':<10} | {'Avg DD':<8}")
    print("-" * 80)
    for _, row in df_rankings.iterrows():
        print(f"{row['Coin']:<6} | {row['Robustness Score']:<8.2f} | {int(row['Pass Count']):>2}/9   | {row['Average PF']:<8.2f} | {row['Average Sharpe']:<10.2f} | {row['Average DD']:<8.2f}%")

    print("\n" + "=" * 80)
    print(f"  TOP 10 ROBUST COINS")
    print("=" * 80)
    for i, (_, row) in enumerate(df_rankings.head(10).iterrows(), 1):
        print(f"[{i:>2}] {row['Coin']:<5} | Score: {row['Robustness Score']:>6.2f} | Passes: {int(row['Pass Count'])}/9 | Avg Sharpe: {row['Average Sharpe']:>5.2f} | Avg DD: {row['Average DD']:>5.2f}%")

    print("\n" + "=" * 80)
    print(f"  WORST 10 COINS")
    print("=" * 80)
    for i, (_, row) in enumerate(df_rankings.tail(10).iterrows(), 1):
        print(f"[{i:>2}] {row['Coin']:<5} | Score: {row['Robustness Score']:>6.2f} | Passes: {int(row['Pass Count'])}/9 | Avg Sharpe: {row['Average Sharpe']:>5.2f} | Avg DD: {row['Average DD']:>5.2f}%")

    # If df_elite is empty, show a note, otherwise display them
    print("\n" + "=" * 80)
    print(f"  ELITE COINS (Avg PF >= 1.4, Avg Sharpe >= 1.2, Avg DD <= 35%)")
    print("=" * 80)
    if df_elite.empty:
        print("  No coins met the strict Average Elite criteria.")
        # Let's show coins meeting the criteria on their *Best* configuration as a backup or reference
        df_best_elite = df_rankings[
            (df_rankings["Best PF"] >= 1.4) & 
            (df_rankings["Best Sharpe"] >= 1.2) & 
            (df_rankings["Best DD"] <= 35.0)
        ].copy()
        if not df_best_elite.empty:
            print("\n  Reference: Coins meeting Elite criteria on their BEST configuration:")
            for i, (_, row) in enumerate(df_best_elite.iterrows(), 1):
                print(f"  - {row['Coin']}: Best PF = {row['Best PF']:.2f}, Best Sharpe = {row['Best Sharpe']:.2f}, Best DD = {row['Best DD']:.2f}%")
    else:
        for i, (_, row) in enumerate(df_elite.iterrows(), 1):
            print(f"[{i:>2}] {row['Coin']:<5} | Score: {row['Robustness Score']:>6.2f} | Avg PF: {row['Average PF']:.2f} | Avg Sharpe: {row['Average Sharpe']:.2f} | Avg DD: {row['Average DD']:.2f}%")

    elapsed = time.time() - t0
    print(f"\n  Completed all simulations in {elapsed/60:.1f} minutes.")

if __name__ == "__main__":
    main()
