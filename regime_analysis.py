"""
Phase 12 - Market Regime Analysis
=================================
Analyzes TAO Supertrend EMA200 strategy performance across Bull, Bear, and Sideways regimes.
Saves metrics and plots to outputs/regime_analysis/
"""

import os
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# CONFIG
DATA_DIR    = "data"
OUTPUTS_DIR = "outputs/regime_analysis"
os.makedirs(OUTPUTS_DIR, exist_ok=True)

INITIAL_BALANCE = 1000.0
RISK_PCT        = 0.10      # 10% risk per trade (compounding)
LEVERAGE        = 5.0
FEE_RATE        = 0.0005    # 0.05 %
SLIPPAGE_RATE   = 0.0002    # 0.02 %

# Strategy parameters
ATR_PERIOD     = 10
ATR_MULTIPLIER = 3.0
EMA_LENGTH     = 200
RR_VALUE       = 3.0
TIMEFRAME      = "1H"

# ─────────────────────────── DATA & INDICATORS ─────────────────────────────────
def load_symbol_timeframe(symbol: str, timeframe: str) -> pd.DataFrame | None:
    ticker_dir = os.path.join(DATA_DIR, symbol)
    if not os.path.isdir(ticker_dir): return None
    candidates = [f"{timeframe}.csv", f"{timeframe.upper()}.csv", f"{symbol}_{timeframe}.csv"]
    filepath = next((os.path.join(ticker_dir, n) for n in candidates if os.path.exists(os.path.join(ticker_dir, n))), None)
    if filepath is None:
        for f in os.listdir(ticker_dir):
            if f.lower().endswith(f"{timeframe.lower()}.csv"):
                filepath = os.path.join(ticker_dir, f)
                break
    if filepath is None: return None

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
        print(f"Error loading data: {exc}")
        return None

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)

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
    
    def wilder_smooth(series: pd.Series, n: int) -> pd.Series:
        smoothed = np.zeros(len(series))
        smoothed[n-1] = series[:n].mean()
        for i in range(n, len(series)):
            smoothed[i] = (smoothed[i-1] * (n - 1) + series.iloc[i]) / n
        return pd.Series(smoothed, index=series.index)
        
    smoothed_tr = wilder_smooth(tr, period)
    smoothed_pdm = wilder_smooth(pd.Series(plus_dm), period)
    smoothed_mdm = wilder_smooth(pd.Series(minus_dm), period)
    
    plus_di = 100 * (smoothed_pdm / smoothed_tr)
    minus_di = 100 * (smoothed_mdm / smoothed_tr)
    
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan))
    adx = wilder_smooth(dx, period)
    return adx

# ─────────────────────────── REGIME CLASSIFIER ─────────────────────────────────
def classify_regimes(df: pd.DataFrame) -> pd.Series:
    ema200 = ema(df["close"], EMA_LENGTH)
    adx = calc_adx(df, 14)
    close = df["close"]
    
    regimes = pd.Series("Sideways", index=df.index)
    
    # Rules:
    # Bull: Close > EMA200 AND ADX > 20
    # Bear: Close < EMA200 AND ADX > 20
    # Sideways: ADX <= 20
    
    regimes.loc[(close > ema200) & (adx > 20)] = "Bull"
    regimes.loc[(close < ema200) & (adx > 20)] = "Bear"
    
    return regimes

# ─────────────────────────── STRATEGY SIMULATION ───────────────────────────────
def run_continuous_strategy(df: pd.DataFrame):
    high, low, close = df["high"], df["low"], df["close"]
    
    # Calculate indicators
    ema_filter = ema(close, EMA_LENGTH)
    tr = true_range(df)
    atr = tr.rolling(ATR_PERIOD).mean()
    hl2 = (high + low) / 2
    atr_val = atr.values
    close_val = close.values
    hl2_val = hl2.values
    n = len(df)
    
    # Supertrend
    upperband = np.zeros(n)
    lowerband = np.zeros(n)
    in_uptrend = np.ones(n, dtype=bool)
    
    for i in range(1, n):
        if np.isnan(atr_val[i]):
            upperband[i] = hl2_val[i]
            lowerband[i] = hl2_val[i]
            continue
        basic_ub = hl2_val[i] + ATR_MULTIPLIER * atr_val[i]
        basic_lb = hl2_val[i] - ATR_MULTIPLIER * atr_val[i]
        upperband[i] = basic_ub if (basic_ub < upperband[i-1] or close_val[i-1] > upperband[i-1]) else upperband[i-1]
        lowerband[i] = basic_lb if (basic_lb > lowerband[i-1] or close_val[i-1] < lowerband[i-1]) else lowerband[i-1]
        if close_val[i] > upperband[i-1]: in_uptrend[i] = True
        elif close_val[i] < lowerband[i-1]: in_uptrend[i] = False
        else: in_uptrend[i] = in_uptrend[i-1]
        
    uptrend = pd.Series(in_uptrend, index=df.index)
    flip_up = uptrend & (~uptrend.shift(1).fillna(True))
    flip_dn = (~uptrend) & uptrend.shift(1).fillna(False)
    
    long_sig = flip_up & (close > ema_filter)
    short_sig = flip_dn & (close < ema_filter)
    
    lb_series = pd.Series(lowerband, index=df.index)
    ub_series = pd.Series(upperband, index=df.index)
    
    sl_long = lb_series.where(lb_series < close, close * 0.99)
    sl_short = ub_series.where(ub_series > close, close * 1.01)
    
    # Event loop to extract trade ledger
    trades = []
    in_trade = False
    side = 0
    ep = 0.0
    sl = 0.0
    tp = 0.0
    entry_idx = 0
    entry_ts = None
    
    for i in range(1, n):
        if in_trade:
            h, l, c = high_p[i], low_p[i], close_p[i]
            exit_triggered = False
            exit_price = 0.0
            
            if side == 1:
                if l <= sl:
                    exit_price = sl
                    exit_triggered = True
                elif h >= tp:
                    exit_price = tp
                    exit_triggered = True
                elif flip_dn.iloc[i] or i == n - 1:
                    exit_price = c
                    exit_triggered = True
            else:
                if h >= sl:
                    exit_price = sl
                    exit_triggered = True
                elif l <= tp:
                    exit_price = tp
                    exit_triggered = True
                elif flip_up.iloc[i] or i == n - 1:
                    exit_price = c
                    exit_triggered = True
                    
            if exit_triggered:
                # Add trade record
                trades.append({
                    "entry_idx": entry_idx,
                    "entry_ts": entry_ts,
                    "exit_idx": i,
                    "exit_ts": df["timestamp"].iloc[i],
                    "direction": "long" if side == 1 else "short",
                    "entry_price": ep,
                    "exit_price": exit_price,
                    "sl_pct": abs(ep - sl) / ep
                })
                in_trade = False
                continue
                
        if not in_trade:
            # We trigger signal on i-1, enter on Open of bar i
            high_p, low_p, close_p = high.values, low.values, close.values
            if long_sig.iloc[i-1]:
                sl_val = sl_long.iloc[i-1]
                if not pd.isna(sl_val) and sl_val > 0 and sl_val < open_p[i]:
                    ep = open_p[i]
                    sl = sl_val
                    tp = ep + (ep - sl) * RR_VALUE
                    side = 1
                    in_trade = True
                    entry_idx = i
                    entry_ts = df["timestamp"].iloc[i]
            elif short_sig.iloc[i-1]:
                sl_val = sl_short.iloc[i-1]
                if not pd.isna(sl_val) and sl_val > 0 and sl_val > open_p[i]:
                    ep = open_p[i]
                    sl = sl_val
                    tp = ep - (sl - ep) * RR_VALUE
                    side = -1
                    in_trade = True
                    entry_idx = i
                    entry_ts = df["timestamp"].iloc[i]
                    
    return trades

# ─────────────────────────── COMPUTE PORTFOLIO METRICS ─────────────────────────
def simulate_trade_subset(trades_list, df_full):
    # Compounding leverage simulation
    balance = INITIAL_BALANCE
    equity_curve = [balance]
    exit_dates = []
    processed_trades = []
    
    for t in trades_list:
        if balance <= 0: break
        
        ep = t["entry_price"]
        sl_pct = t["sl_pct"]
        friction = ep * (2 * FEE_RATE + 2 * SLIPPAGE_RATE)
        
        risk_amt = balance * RISK_PCT
        risk_qty = risk_amt / (ep * sl_pct + friction)
        max_qty  = (balance * LEVERAGE) / ep
        qty      = min(risk_qty, max_qty)
        
        raw_pnl = qty * (t["exit_price"] - ep) if t["direction"] == "long" else qty * (ep - t["exit_price"])
        actual_pnl = raw_pnl - (qty * friction)
        
        balance = max(0.0, balance + actual_pnl)
        equity_curve.append(balance)
        exit_dates.append(t["exit_ts"])
        
        processed_trades.append({
            "pnl": actual_pnl,
            "r_multiple": actual_pnl / risk_amt if risk_amt > 0 else 0.0
        })
        
    return processed_trades, balance, equity_curve, exit_dates

def calculate_metrics_for_regime(trades_list, df_full, start_date, end_date):
    total_trades = len(trades_list)
    days = (end_date - start_date).total_seconds() / 86400.0
    
    if total_trades == 0:
        return {
            "Total Return %": 0.0, "CAGR %": 0.0, "Profit Factor": 0.0,
            "Win Rate %": 0.0, "Average R-multiple": 0.0, "Max Drawdown %": 0.0,
            "Sharpe Ratio": 0.0, "Trades": 0, "Final Balance $": INITIAL_BALANCE,
            "Equity Curve": [INITIAL_BALANCE], "Exit Dates": [start_date]
        }
        
    p_trades, final_bal, eq_curve, exit_dates = simulate_trade_subset(trades_list, df_full)
    
    wins = [t["pnl"] for t in p_trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in p_trades if t["pnl"] <= 0]
    win_rate = (len(wins) / total_trades) * 100
    
    sum_wins = sum(wins)
    sum_losses = sum(losses)
    pf = 999.9 if sum_losses == 0 and sum_wins > 0 else 1.0 if sum_losses == 0 else abs(sum_wins / sum_losses)
    
    avg_r = np.mean([t["r_multiple"] for t in p_trades])
    total_return = ((final_bal - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
    cagr = ((final_bal / INITIAL_BALANCE) ** (365.25 / days) - 1.0) * 100 if final_bal > 0 else -100.0
    
    # Drawdown
    eq_series = pd.Series(eq_curve)
    cummax = eq_series.cummax()
    dd = (eq_series - cummax) / cummax.replace(0, 1e-9) * -100
    max_dd = float(dd.max())
    
    # Sharpe
    df_eq = pd.DataFrame({"Date": pd.to_datetime(exit_dates), "Balance": eq_curve[1:]})
    df_eq["Date"] = df_eq["Date"].dt.normalize()
    daily = df_eq.groupby("Date")["Balance"].last()
    full_idx = pd.date_range(start=start_date.normalize(), end=end_date.normalize(), freq="D")
    daily = daily.reindex(full_idx).ffill()
    daily_pct = daily.pct_change().dropna()
    sharpe = float((daily_pct.mean() / daily_pct.std()) * np.sqrt(252)) if not daily_pct.empty and daily_pct.std() != 0 else 0.0
    
    return {
        "Total Return %": round(total_return, 2),
        "CAGR %": round(cagr, 2),
        "Profit Factor": round(pf, 4),
        "Win Rate %": round(win_rate, 2),
        "Average R-multiple": round(avg_r, 4),
        "Max Drawdown %": round(max_dd, 2),
        "Sharpe Ratio": round(sharpe, 4),
        "Trades": total_trades,
        "Final Balance $": round(final_bal, 2),
        "Equity Curve": eq_curve,
        "Exit Dates": exit_dates
    }

# ─────────────────────────── MAIN ──────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 80)
    print("  PHASE 12 - MARKET REGIME ANALYSIS")
    print("=" * 80)
    
    # Load TAO data
    df = load_symbol_timeframe("TAO", TIMEFRAME)
    if df is None or df.empty:
        print("[FATAL] Could not load TAO data.")
        return
        
    print(f"  Loaded TAO: {len(df)} candles")
    start_date = df["timestamp"].min()
    end_date = df["timestamp"].max()
    
    # Classify Regimes
    regimes = classify_regimes(df)
    df["regime"] = regimes
    
    # Summarize Regime Durations
    counts = regimes.value_counts()
    total_hours = len(regimes)
    summary_rows = []
    print("\n  Regime Distribution Summary:")
    for reg in ["Bull", "Bear", "Sideways"]:
        cnt = counts.get(reg, 0)
        pct = (cnt / total_hours) * 100
        print(f"    {reg:<8} : {cnt:>5} hours | {pct:>5.2f}%")
        summary_rows.append({
            "Regime": reg,
            "Duration (Hours)": cnt,
            "Duration %": round(pct, 2)
        })
        
    df_summary = pd.DataFrame(summary_rows)
    summary_path = os.path.join(OUTPUTS_DIR, "regime_summary.csv")
    df_summary.to_csv(summary_path, index=False)
    print(f"  Saved regime summary -> {summary_path}")
    
    # Open prices array for strategy simulation
    global open_p
    open_p = df['open'].values
    
    # Run strategy continuously to extract trade ledger
    print("\n  Executing Supertrend EMA200 strategy continuously...")
    trades = run_continuous_strategy(df)
    print(f"    Executed {len(trades)} trades in total history.")
    
    # Allocate trades to entry regimes
    trades_by_regime = {"Bull": [], "Bear": [], "Sideways": []}
    for t in trades:
        entry_ts = t["entry_ts"]
        # Find active regime at trade entry timestamp
        reg_active = df.loc[df["timestamp"] == entry_ts, "regime"].values[0]
        trades_by_regime[reg_active].append(t)
        
    print("\n  Trades allocated by entry regime:")
    for reg, t_list in trades_by_regime.items():
        print(f"    {reg:<8} : {len(t_list):>3} trades")
        
    # Calculate metrics for each regime slice
    results = {}
    metrics_rows = []
    
    for reg in ["Bull", "Bear", "Sideways"]:
        t_list = trades_by_regime[reg]
        metrics = calculate_metrics_for_regime(t_list, df, start_date, end_date)
        results[reg] = metrics
        
        metrics_rows.append({
            "Regime": reg,
            "Total Return %": metrics["Total Return %"],
            "CAGR %": metrics["CAGR %"],
            "Profit Factor": metrics["Profit Factor"],
            "Win Rate %": metrics["Win Rate %"],
            "Average R-multiple": metrics["Average R-multiple"],
            "Max Drawdown %": metrics["Max Drawdown %"],
            "Sharpe Ratio": metrics["Sharpe Ratio"],
            "Trades": metrics["Trades"],
            "Final Balance $": metrics["Final Balance $"]
        })
        
    df_metrics = pd.DataFrame(metrics_rows)
    metrics_path = os.path.join(OUTPUTS_DIR, "regime_metrics.csv")
    df_metrics.to_csv(metrics_path, index=False)
    print(f"  Saved regime performance metrics -> {metrics_path}")
    
    # Display comparison table
    print("\n" + "=" * 100)
    print("  PERFORMANCE METRICS BY MARKET REGIME")
    print("=" * 100)
    print(f"{'Regime':<10} | {'Return %':<10} | {'CAGR %':<8} | {'PF':<8} | {'Win Rate %':<10} | {'Avg R-mult':<10} | {'Max DD %':<10} | {'Sharpe':<8} | {'Trades':<6}")
    print("-" * 100)
    for r in metrics_rows:
        print(f"{r['Regime']:<10} | {r['Total Return %']:>9.2f}% | {r['CAGR %']:>7.2f}% | {r['Profit Factor']:>8.4f} | {r['Win Rate %']:>9.2f}% | {r['Average R-multiple']:>10.4f} | {r['Max Drawdown %']:>9.2f}% | {r['Sharpe Ratio']:>8.4f} | {r['Trades']:>6}")
    print("-" * 100)
    
    # ─────────────────────────── PLOTTING CHARTS ────────────────────────────────
    print("\n  Generating visualization charts...")
    
    # 1. Equity Curves Plot
    plt.figure(figsize=(12, 6))
    colors = {"Bull": "#2ca02c", "Bear": "#d62728", "Sideways": "#1f77b4"}
    
    for reg in ["Bull", "Bear", "Sideways"]:
        m = results[reg]
        eq = m["Equity Curve"]
        dates = [start_date] + m["Exit Dates"]
        
        # Build timeline
        ts_eq = pd.Series(eq, index=pd.to_datetime(dates))
        ts_eq = ts_eq.resample("D").last().ffill()
        
        # Reindex to full date range
        full_range = pd.date_range(start=start_date.normalize(), end=end_date.normalize(), freq="D")
        ts_eq = ts_eq.reindex(full_range).ffill().fillna(INITIAL_BALANCE)
        
        plt.plot(ts_eq.index, ts_eq.values, label=f"{reg} Regime (Return: {m['Total Return %']}%)", color=colors[reg], lw=2)
        
    plt.title("TAO Supertrend EMA200 Equity Curves by Market Regime", fontsize=14, fontweight="bold")
    plt.xlabel("Date", fontsize=12)
    plt.ylabel("Account Balance ($)", fontsize=12)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend(loc="upper left")
    plt.tight_layout()
    
    curves_path = os.path.join(OUTPUTS_DIR, "equity_curves.png")
    plt.savefig(curves_path, dpi=150)
    plt.close()
    print(f"    Saved equity curves chart -> {curves_path}")
    
    # 2. Drawdowns Plot
    plt.figure(figsize=(12, 6))
    for reg in ["Bull", "Bear", "Sideways"]:
        m = results[reg]
        eq = m["Equity Curve"]
        dates = [start_date] + m["Exit Dates"]
        
        ts_eq = pd.Series(eq, index=pd.to_datetime(dates)).resample("D").last().ffill()
        full_range = pd.date_range(start=start_date.normalize(), end=end_date.normalize(), freq="D")
        ts_eq = ts_eq.reindex(full_range).ffill().fillna(INITIAL_BALANCE)
        
        cummax = ts_eq.cummax()
        dd = (ts_eq - cummax) / cummax * 100
        
        plt.plot(dd.index, dd.values, label=f"{reg} Regime (Max DD: {m['Max Drawdown %']}%)", color=colors[reg], lw=1.5)
        
    plt.title("Historical Drawdown Profiles by Market Regime", fontsize=14, fontweight="bold")
    plt.xlabel("Date", fontsize=12)
    plt.ylabel("Drawdown %", fontsize=12)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend(loc="lower left")
    plt.tight_layout()
    
    dd_path = os.path.join(OUTPUTS_DIR, "drawdown_curves.png")
    plt.savefig(dd_path, dpi=150)
    plt.close()
    print(f"    Saved drawdown curves chart -> {dd_path}")
    
    # Print completion
    elapsed = time.time() - t0
    print(f"\n  Completed regime analysis in {elapsed:.1f}s")

if __name__ == "__main__":
    main()
