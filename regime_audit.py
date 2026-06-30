"""
Regime Audit Diagnostics
========================
Performs trade-level attribution and transition analysis to audit Phase 12.
"""

import os
import numpy as np
import pandas as pd

# CONFIG
DATA_DIR = "data"
INITIAL_BALANCE = 1000.0
RISK_PCT = 0.10
LEVERAGE = 5.0
FEE_RATE = 0.0005
SLIPPAGE_RATE = 0.0002

ATR_PERIOD = 10
ATR_MULTIPLIER = 3.0
EMA_LENGTH = 200
RR_VALUE = 3.0
TIMEFRAME = "1H"

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

def classify_regimes(df: pd.DataFrame) -> pd.Series:
    ema200 = ema(df["close"], EMA_LENGTH)
    adx = calc_adx(df, 14)
    close = df["close"]
    regimes = pd.Series("Sideways", index=df.index)
    regimes.loc[(close > ema200) & (adx > 20)] = "Bull"
    regimes.loc[(close < ema200) & (adx > 20)] = "Bear"
    return regimes

def run_continuous_backtest(df: pd.DataFrame):
    high, low, close = df["high"], df["low"], df["close"]
    open_p = df["open"].values
    
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
    
    # Single continuous account simulation
    balance = INITIAL_BALANCE
    equity_curve = [balance]
    exit_dates = []
    
    trades = []
    in_trade = False
    side = 0
    ep = 0.0
    sl = 0.0
    tp = 0.0
    qty = 0.0
    entry_idx = 0
    entry_ts = None
    
    # Pre-calculated arrays for speed
    high_p = high.values
    low_p = low.values
    close_p = close.values
    ts_p = df["timestamp"].tolist()
    
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
                # Compound sizing based on CURRENT balance
                sl_pct = abs(ep - sl) / ep
                friction = ep * (2 * FEE_RATE + 2 * SLIPPAGE_RATE)
                
                # Check locked risk
                risk_amt = balance * RISK_PCT
                risk_qty = risk_amt / (ep * sl_pct + friction)
                max_qty = (balance * LEVERAGE) / ep
                qty = min(risk_qty, max_qty)
                
                raw_pnl = qty * (exit_price - ep) if side == 1 else qty * (ep - exit_price)
                net_pnl = raw_pnl - (qty * friction)
                
                balance = max(0.0, balance + net_pnl)
                equity_curve.append(balance)
                exit_dates.append(ts_p[i])
                
                trades.append({
                    "entry_idx": entry_idx,
                    "entry_ts": entry_ts,
                    "exit_idx": i,
                    "exit_ts": ts_p[i],
                    "direction": "long" if side == 1 else "short",
                    "entry_price": ep,
                    "exit_price": exit_price,
                    "sl_pct": sl_pct,
                    "pnl": net_pnl,
                    "r_multiple": net_pnl / risk_amt if risk_amt > 0 else 0.0
                })
                in_trade = False
                continue
                
        if not in_trade:
            if long_sig.iloc[i-1]:
                sl_val = sl_long.iloc[i-1]
                if not pd.isna(sl_val) and sl_val > 0 and sl_val < open_p[i]:
                    ep = open_p[i]
                    sl = sl_val
                    tp = ep + (ep - sl) * RR_VALUE
                    side = 1
                    in_trade = True
                    entry_idx = i
                    entry_ts = ts_p[i]
            elif short_sig.iloc[i-1]:
                sl_val = sl_short.iloc[i-1]
                if not pd.isna(sl_val) and sl_val > 0 and sl_val > open_p[i]:
                    ep = open_p[i]
                    sl = sl_val
                    tp = ep - (sl - ep) * RR_VALUE
                    side = -1
                    in_trade = True
                    entry_idx = i
                    entry_ts = ts_p[i]
                    
    return trades, equity_curve, exit_dates

def main():
    ticker_dir = os.path.join(DATA_DIR, "TAO")
    candidates = ["1H.csv", "1H.CSV", "TAO_1H.csv"]
    filepath = next((os.path.join(ticker_dir, n) for n in candidates if os.path.exists(os.path.join(ticker_dir, n))), None)
    if filepath is None:
        for f in os.listdir(ticker_dir):
            if f.lower().endswith("1h.csv"):
                filepath = os.path.join(ticker_dir, f)
                break
                
    df = pd.read_csv(filepath)
    col_map = {c: "timestamp" if c.lower() in ("timestamp", "date", "datetime", "ts") else c.lower() for c in df.columns}
    df.rename(columns=col_map, inplace=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.sort_values("timestamp", inplace=True)
    df.drop_duplicates(subset=["timestamp"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    # Classify regimes
    regimes = classify_regimes(df)
    df["regime"] = regimes
    
    # Run continuous backtest
    trades, equity_curve, exit_dates = run_continuous_backtest(df)
    
    # 1. Analyse Cross-Regime Trades
    cross_regime_count = 0
    cross_regime_pnl = 0.0
    
    for t in trades:
        entry_ts = t["entry_ts"]
        exit_ts = t["exit_ts"]
        
        reg_entry = df.loc[df["timestamp"] == entry_ts, "regime"].values[0]
        reg_exit = df.loc[df["timestamp"] == exit_ts, "regime"].values[0]
        
        t["regime_entry"] = reg_entry
        t["regime_exit"] = reg_exit
        
        if reg_entry != reg_exit:
            cross_regime_count += 1
            cross_regime_pnl += t["pnl"]
            
    print(f"Total Trades: {len(trades)}")
    print(f"Cross-Regime Trades (Open in one, close in another): {cross_regime_count} ({cross_regime_count/len(trades)*100:.2f}%)")
    print(f"PnL contribution of Cross-Regime trades: ${cross_regime_pnl:.2f}")
    
    # 2. Trade-Level Attribution (Sum of raw Dollar PnL generated in continuous run)
    pnl_by_regime = {"Bull": 0.0, "Bear": 0.0, "Sideways": 0.0}
    r_mult_by_regime = {"Bull": [], "Bear": [], "Sideways": []}
    win_by_regime = {"Bull": 0, "Bear": 0, "Sideways": 0}
    loss_by_regime = {"Bull": 0, "Bear": 0, "Sideways": 0}
    
    for t in trades:
        reg = t["regime_entry"]
        pnl_by_regime[reg] += t["pnl"]
        r_mult_by_regime[reg].append(t["r_multiple"])
        if t["pnl"] > 0:
            win_by_regime[reg] += 1
        else:
            loss_by_regime[reg] += 1
            
    print("\nTrade-Level PnL Attribution (From Single Continuous Run):")
    total_continuous_pnl = sum(t["pnl"] for t in trades)
    print(f"  Total Strategy PnL: ${total_continuous_pnl:.2f}")
    
    for reg in ["Bull", "Bear", "Sideways"]:
        pnl = pnl_by_regime[reg]
        pct = (pnl / total_continuous_pnl * 100) if total_continuous_pnl > 0 else 0.0
        avg_r = np.mean(r_mult_by_regime[reg]) if len(r_mult_by_regime[reg]) > 0 else 0.0
        wr = (win_by_regime[reg] / (win_by_regime[reg] + loss_by_regime[reg]) * 100) if (win_by_regime[reg] + loss_by_regime[reg]) > 0 else 0.0
        print(f"    {reg:<8} : Net PnL = ${pnl:>10.2f} ({pct:>6.2f}%) | Trades = {len(r_mult_by_regime[reg]):>3} | Win Rate = {wr:>5.2f}% | Avg R = {avg_r:>6.4f}")

if __name__ == "__main__":
    main()
