"""
===================================================================
  CRYPTO BACKTESTER  –  6-Month  |  Top 6 Coins  |  15m · 1h · 4h
===================================================================
Settings
  Portfolio   : $1 000
  Risk/trade  : $100   (position sized so losing the SL costs exactly $100)
  TP/SL       : strict (hit-on-OHLC bar, market-order simulation)
  Timeframes  : 15m, 1h, 4h
  Strategies  : VWAP Momentum Scalp, Liquidity Sweep (15m/1h),
                Liquidity Sweep (1h/4h), ATR Volume Breakout
  Lookback    : 180 days  (last 6 months of available data)
  Fees        : 0.045 % taker + 0.05 % slippage
===================================================================
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import vectorbt as vbt
from vectorbt.portfolio.enums import (
    OppositeEntryMode,
    StopEntryPrice,
    StopExitMode,
    StopExitPrice,
)

from strategies import ema, session_vwap

# ────────────────────────────── CONSTANTS ──────────────────────────────────
DATA_DIR        = Path("data")
OUT_DIR         = Path("backtest_results_6m")
OUT_DIR.mkdir(exist_ok=True)

COINS      = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT")
TIMEFRAMES = ("15m", "1h", "4h")

LOOKBACK_DAYS      = 180          # 6 months
INITIAL_CASH       = 1_000.0      # portfolio size
RISK_PER_TRADE_USD = 100.0        # strict risk per trade
MAX_NOTIONAL_USD   = INITIAL_CASH # hard cap on position notional
FEE_RATE           = 0.00045      # 0.045 % taker fee (Binance/Hyperliquid)
SLIPPAGE_RATE      = 0.0005       # 0.05 % slippage buffer

TIMEFRAME_DELTAS = {
    "15m": pd.Timedelta(minutes=15),
    "1h":  pd.Timedelta(hours=1),
    "4h":  pd.Timedelta(hours=4),
}

COIN_LABELS = {
    "BTCUSDT": "Bitcoin (BTC)",
    "ETHUSDT": "Ethereum (ETH)",
    "BNBUSDT": "BNB",
    "SOLUSDT": "Solana (SOL)",
    "XRPUSDT": "XRP",
    "ADAUSDT": "Cardano (ADA)",
}

# ────────────────────────────── DATA LOADING ────────────────────────────────
@dataclass(frozen=True)
class StrategySpec:
    name: str
    execution_tf: str
    build_setups: Callable[[dict[str, pd.DataFrame]], pd.DataFrame]


def load_frame(symbol: str, timeframe: str) -> pd.DataFrame:
    path = DATA_DIR / symbol / f"{timeframe}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing data: {path}")
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = (
        df.sort_values("timestamp")
          .drop_duplicates("timestamp")
          .reset_index(drop=True)
    )
    df["ts"] = (df["timestamp"].astype("int64") // 1_000_000).astype("int64")
    return df


def load_symbol_frames(symbol: str) -> dict[str, pd.DataFrame]:
    return {tf: load_frame(symbol, tf) for tf in TIMEFRAMES}


# ────────────────────────────── INDICATORS ──────────────────────────────────
def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat(
        [h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1
    ).max(axis=1)


def adx_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l = df["high"], df["low"]
    up   = h.diff()
    dn   = -l.diff()
    pdm  = np.where((up > dn) & (up > 0), up, 0.0)
    mdm  = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr  = true_range(df).rolling(period).mean().replace(0, 1e-9)
    pdi  = 100 * pd.Series(pdm, index=df.index).rolling(period).mean() / atr
    mdi  = 100 * pd.Series(mdm, index=df.index).rolling(period).mean() / atr
    dx   = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, 1e-9)
    return dx.rolling(period).mean()


def sideways_filter(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr        = true_range(df)
    atr_ratio = tr.rolling(14).mean() / tr.rolling(100).mean()
    sum_tr    = tr.rolling(14).sum()
    rng       = (h.rolling(14).max() - l.rolling(14).min()).replace(0, 1e-9)
    chop      = 100 * np.log10((sum_tr / rng).replace(0, 1e-9)) / np.log10(14)
    don_w     = (h.rolling(20).max() - l.rolling(20).min()) / c
    sideways  = (
        (adx_series(df) < 20.0).astype(int)
        + (chop > 61.8).astype(int)
        + (atr_ratio < 0.95).astype(int)
    ) >= 2
    compression = (atr_ratio < 0.95) & (don_w < 0.025)
    return (sideways & ~compression).fillna(False)


def asof_to(target: pd.DataFrame, source: pd.DataFrame, col: str) -> pd.Series:
    aligned = pd.merge_asof(
        target[["timestamp"]].sort_values("timestamp"),
        source[["timestamp", col]].sort_values("timestamp"),
        on="timestamp", direction="backward",
    )
    return aligned[col].reindex(target.index)


def blank_setups(primary: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {"side": "", "stop_loss": np.nan, "take_profit": np.nan},
        index=primary.index,
    )


# ────────────────────────────── SETUP BUILDERS ──────────────────────────────
def vwap_setups(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df  = frames["15m"].copy()
    s   = blank_setups(df)
    h4  = frames["4h"].copy()
    h4["ema50"]    = ema(h4["close"], 50)
    h4["h4_bull"]  = h4["close"] > h4["ema50"]
    df["h4_bull"]  = asof_to(df, h4, "h4_bull").fillna(False)
    df["vwap"]     = session_vwap(df)
    df["ema9"]     = ema(df["close"], 9)
    df["ema21"]    = ema(df["close"], 21)
    df["vol_ma10"] = df["volume"].rolling(10).mean()
    df["sw"]       = sideways_filter(df)
    vol_spike      = df["volume"] > df["vol_ma10"]
    x_up   = (df["ema9"].shift(1) <= df["ema21"].shift(1)) & (df["ema9"] > df["ema21"])
    x_down = (df["ema9"].shift(1) >= df["ema21"].shift(1)) & (df["ema9"] < df["ema21"])
    l_stop = df["low"].rolling(5).min()
    s_stop = df["high"].rolling(5).max()
    l_dist = df["close"] - l_stop
    s_dist = s_stop - df["close"]
    l_sig  = (df["close"] > df["vwap"]) & x_up   & vol_spike &  df["h4_bull"] & ~df["sw"] & (l_stop < df["close"])
    s_sig  = (df["close"] < df["vwap"]) & x_down & vol_spike & ~df["h4_bull"] & ~df["sw"] & (s_stop > df["close"])
    s.loc[l_sig, "side"]        = "long"
    s.loc[l_sig, "stop_loss"]   = l_stop[l_sig]
    s.loc[l_sig, "take_profit"] = df.loc[l_sig, "close"] + 1.5 * l_dist[l_sig]
    s.loc[s_sig, "side"]        = "short"
    s.loc[s_sig, "stop_loss"]   = s_stop[s_sig]
    s.loc[s_sig, "take_profit"] = df.loc[s_sig, "close"] - 1.5 * s_dist[s_sig]
    return s


def pivot_levels(df: pd.DataFrame):
    h = df["high"]
    l = df["low"]
    ph = h.where(h == h.rolling(5, center=True).max())
    pl = l.where(l == l.rolling(5, center=True).min())
    return ph.ffill(), pl.ffill()


def fvg_flags(df: pd.DataFrame):
    bearish = df["low"].shift(2) > df["high"]
    bullish = df["high"].shift(2) < df["low"]
    return bearish.rolling(5).max().astype(bool), bullish.rolling(5).max().astype(bool)


def ltf_sweep_setups(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = frames["15m"].copy()
    s  = blank_setups(df)
    h1 = frames["1h"].copy()
    h1["sw_hi"] = h1["high"].rolling(24).max()
    h1["sw_lo"] = h1["low"].rolling(24).min()
    df["sw_hi"] = asof_to(df, h1, "sw_hi")
    df["sw_lo"] = asof_to(df, h1, "sw_lo")
    lph, lpl   = pivot_levels(df)
    bfvg, lfvg = fvg_flags(df)
    swpt_hi = ((df["high"] > df["sw_hi"]) & (df["close"] < df["sw_hi"])).rolling(3).max().astype(bool)
    swpt_lo = ((df["low"]  < df["sw_lo"]) & (df["close"] > df["sw_lo"])).rolling(3).max().astype(bool)
    ss = df["high"].rolling(3).max()
    ls = df["low"].rolling(3).min()
    s_sig = swpt_hi & (df["close"] < lpl) & bfvg & (ss > df["close"])
    l_sig = swpt_lo & (df["close"] > lph) & lfvg & (ls < df["close"])
    s.loc[s_sig, "side"]        = "short"
    s.loc[s_sig, "stop_loss"]   = ss[s_sig]
    s.loc[s_sig, "take_profit"] = df.loc[s_sig, "close"] - 2.0 * (ss[s_sig] - df.loc[s_sig, "close"])
    s.loc[l_sig, "side"]        = "long"
    s.loc[l_sig, "stop_loss"]   = ls[l_sig]
    s.loc[l_sig, "take_profit"] = df.loc[l_sig, "close"] + 2.0 * (df.loc[l_sig, "close"] - ls[l_sig])
    return s


def htf_sweep_setups(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = frames["1h"].copy()
    s  = blank_setups(df)
    h4 = frames["4h"].copy()
    h4["sw_hi"] = h4["high"].rolling(6).max()
    h4["sw_lo"] = h4["low"].rolling(6).min()
    df["sw_hi"] = asof_to(df, h4, "sw_hi")
    df["sw_lo"] = asof_to(df, h4, "sw_lo")
    lph, lpl   = pivot_levels(df)
    bfvg, lfvg = fvg_flags(df)
    swpt_hi = ((df["high"] > df["sw_hi"]) & (df["close"] < df["sw_hi"])).rolling(3).max().astype(bool)
    swpt_lo = ((df["low"]  < df["sw_lo"]) & (df["close"] > df["sw_lo"])).rolling(3).max().astype(bool)
    ss = df["high"].rolling(3).max()
    ls = df["low"].rolling(3).min()
    s_sig = swpt_hi & (df["close"] < lpl) & bfvg & (ss > df["close"])
    l_sig = swpt_lo & (df["close"] > lph) & lfvg & (ls < df["close"])
    s.loc[s_sig, "side"]        = "short"
    s.loc[s_sig, "stop_loss"]   = ss[s_sig]
    s.loc[s_sig, "take_profit"] = df.loc[s_sig, "close"] - 2.0 * (ss[s_sig] - df.loc[s_sig, "close"])
    s.loc[l_sig, "side"]        = "long"
    s.loc[l_sig, "stop_loss"]   = ls[l_sig]
    s.loc[l_sig, "take_profit"] = df.loc[l_sig, "close"] + 2.0 * (df.loc[l_sig, "close"] - ls[l_sig])
    return s


def atr_breakout_setups(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = frames["1h"].copy()
    s  = blank_setups(df)
    tr = true_range(df)
    df["atr_r"]   = tr.rolling(14).mean() / tr.rolling(100).mean()
    df["vol20"]   = df["volume"].rolling(20).mean()
    df["adx"]     = adx_series(df)
    df["ema50"]   = ema(df["close"], 50)
    prev_dh = df["high"].shift(1).rolling(20).max()
    prev_dl = df["low"].shift(1).rolling(20).min()
    compress = df["atr_r"].rolling(5).min() < 0.95
    vol_sp   = df["volume"] > 1.25 * df["vol20"]
    adx_ok   = (df["adx"] > df["adx"].shift(1)) | (df["adx"] > 25.0)
    sw       = sideways_filter(df)
    ls = prev_dl.where(~(df["close"] - prev_dl > df["close"] * 0.1), df["low"].rolling(5).min())
    ls = ls.where(ls < df["close"], df["close"] * 0.99)
    ss = prev_dh.where(~(prev_dh - df["close"] > df["close"] * 0.1), df["high"].rolling(5).max())
    ss = ss.where(ss > df["close"], df["close"] * 1.01)
    l_sig = compress & (df["close"] > prev_dh) & vol_sp & adx_ok & (df["close"] > df["ema50"]) & ~sw
    s_sig = compress & (df["close"] < prev_dl) & vol_sp & adx_ok & (df["close"] < df["ema50"]) & ~sw
    s.loc[l_sig, "side"]        = "long"
    s.loc[l_sig, "stop_loss"]   = ls[l_sig]
    s.loc[l_sig, "take_profit"] = df.loc[l_sig, "close"] + 2.0 * (df.loc[l_sig, "close"] - ls[l_sig])
    s.loc[s_sig, "side"]        = "short"
    s.loc[s_sig, "stop_loss"]   = ss[s_sig]
    s.loc[s_sig, "take_profit"] = df.loc[s_sig, "close"] - 2.0 * (ss[s_sig] - df.loc[s_sig, "close"])
    return s


STRATEGIES = (
    StrategySpec("VWAP Momentum Scalp",    "15m", vwap_setups),
    StrategySpec("Liquidity Sweep 15m/1h", "15m", ltf_sweep_setups),
    StrategySpec("Liquidity Sweep 1h/4h",  "1h",  htf_sweep_setups),
    StrategySpec("ATR Volume Breakout",    "1h",  atr_breakout_setups),
)

# ────────────────────────────── SIZING & STOPS ──────────────────────────────
def position_size(entry_price: float, stop_loss: float) -> float:
    dist = abs(entry_price - stop_loss)
    if dist <= 0:
        return 0.0
    friction = entry_price * (2 * FEE_RATE + SLIPPAGE_RATE)
    risk_qty  = RISK_PER_TRADE_USD / (dist + friction)
    max_qty   = MAX_NOTIONAL_USD / entry_price
    return max(0.0, min(risk_qty, max_qty))


def stop_percents(
    side: str, sl: float, tp: float, ep: float
) -> tuple[float, float] | None:
    if side == "long":
        if not (sl < ep < tp):
            return None
    elif side == "short":
        if not (tp < ep < sl):
            return None
    else:
        return None
    sl_pct = abs(ep - sl) / ep
    tp_pct = abs(tp - ep) / ep
    if sl_pct <= 0 or tp_pct <= 0:
        return None
    return sl_pct, tp_pct


# ────────────────────────────── VBT PIPELINE ────────────────────────────────
def generate_vectorbt_inputs(
    frames: dict[str, pd.DataFrame],
    strategy: StrategySpec,
    start_time: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, pd.Series], list[dict]]:
    primary = frames[strategy.execution_tf].copy().reset_index(drop=True)
    setups  = strategy.build_setups(frames)
    index   = primary["timestamp"]

    entries       = pd.Series(False, index=index)
    exits         = pd.Series(False, index=index)
    short_entries = pd.Series(False, index=index)
    short_exits   = pd.Series(False, index=index)
    sl_stop       = pd.Series(np.nan, index=index)
    tp_stop       = pd.Series(np.nan, index=index)
    size          = pd.Series(np.nan, index=index)

    entry_start      = primary["timestamp"].searchsorted(start_time, side="left")
    first_signal_row = max(0, entry_start - 1)
    signal_records: list[dict] = []

    for sig_row in range(first_signal_row, len(primary) - 1):
        setup = setups.iloc[sig_row]
        side  = setup["side"]
        if side not in ("long", "short"):
            continue

        entry_row  = sig_row + 1
        entry_time = primary.at[entry_row, "timestamp"]
        if entry_time < start_time:
            continue

        ep  = float(primary.at[entry_row, "open"])
        sl  = float(setup["stop_loss"])
        tp  = float(setup["take_profit"])
        stops = stop_percents(side, sl, tp, ep)
        if stops is None:
            continue

        qty = position_size(ep, sl)
        if qty <= 0:
            continue

        sl_pct, tp_pct = stops
        if side == "long":
            entries.iloc[entry_row] = True
        else:
            short_entries.iloc[entry_row] = True

        sl_stop.iloc[entry_row] = sl_pct
        tp_stop.iloc[entry_row] = tp_pct
        size.iloc[entry_row]    = qty

        signal_records.append({
            "strategy":   strategy.name,
            "timeframe":  strategy.execution_tf,
            "entry_time": entry_time,
            "side":       side,
            "ep":  ep, "sl": sl, "tp": tp,
            "sl_pct": sl_pct, "tp_pct": tp_pct, "size": qty,
        })

    exits.iloc[-1]       = True
    short_exits.iloc[-1] = True
    order_price = primary["open"].copy()
    order_price.iloc[-1] = primary["close"].iloc[-1]

    return primary, {
        "entries": entries, "exits": exits,
        "short_entries": short_entries, "short_exits": short_exits,
        "sl_stop": sl_stop, "tp_stop": tp_stop,
        "size": size, "order_price": order_price,
    }, signal_records


def run_portfolio(
    primary: pd.DataFrame, inputs: dict[str, pd.Series], timeframe: str
) -> vbt.Portfolio:
    return vbt.Portfolio.from_signals(
        close           = primary["close"],
        entries         = inputs["entries"],
        exits           = inputs["exits"],
        short_entries   = inputs["short_entries"],
        short_exits     = inputs["short_exits"],
        size            = inputs["size"],
        size_type       = "amount",
        price           = inputs["order_price"],
        open            = primary["open"],
        high            = primary["high"],
        low             = primary["low"],
        sl_stop         = inputs["sl_stop"],
        tp_stop         = inputs["tp_stop"],
        fees            = FEE_RATE,
        slippage        = SLIPPAGE_RATE,
        init_cash       = INITIAL_CASH,
        accumulate      = False,
        upon_opposite_entry = OppositeEntryMode.Ignore,
        stop_entry_price    = StopEntryPrice.Price,
        stop_exit_price     = StopExitPrice.StopMarket,
        upon_stop_exit      = StopExitMode.Close,
        freq                = TIMEFRAME_DELTAS[timeframe],
    )


def summarize_portfolio(
    symbol: str, strategy: StrategySpec, pf: vbt.Portfolio,
    n_signals: int, start: pd.Timestamp, end: pd.Timestamp,
) -> dict:
    trades  = pf.trades.records_readable
    closed  = trades[trades["Status"] == "Closed"] if not trades.empty else trades
    wins    = int((closed["PnL"] > 0).sum()) if not closed.empty else 0
    losses  = int((closed["PnL"] <= 0).sum()) if not closed.empty else 0
    total   = wins + losses
    final   = float(pf.value().iloc[-1])
    profit  = final - INITIAL_CASH
    mdd     = float(abs(pf.max_drawdown())) * 100 if total else 0.0
    avg_win  = float(closed.loc[closed["PnL"] > 0,  "PnL"].mean()) if wins   else 0.0
    avg_loss = float(closed.loc[closed["PnL"] <= 0, "PnL"].mean()) if losses else 0.0

    return {
        "coin":              symbol,
        "coin_label":        COIN_LABELS.get(symbol, symbol),
        "strategy":          strategy.name,
        "execution_tf":      strategy.execution_tf,
        "period_start":      start.strftime("%Y-%m-%d"),
        "period_end":        end.strftime("%Y-%m-%d"),
        "signals":           n_signals,
        "trades":            total,
        "wins":              wins,
        "losses":            losses,
        "win_rate":          round(wins / total * 100, 2) if total else 0.0,
        "final_balance":     round(final, 2),
        "profit_usd":        round(profit, 2),
        "return_pct":        round(profit / INITIAL_CASH * 100, 2),
        "max_drawdown_pct":  round(mdd, 2),
        "avg_win_usd":       round(avg_win, 2),
        "avg_loss_usd":      round(avg_loss, 2),
        "profit_factor":     round(
            abs(avg_win * wins / (avg_loss * losses)) if losses and avg_loss != 0 else float("inf"), 2
        ),
    }


# ────────────────────────────── HTML REPORT ─────────────────────────────────
_GRADE_COLOR = {
    "A+": ("#00ff88", "#003322"),
    "A":  ("#22cc77", "#002211"),
    "B":  ("#66bb44", "#112200"),
    "C":  ("#ffcc00", "#221100"),
    "D":  ("#ff8844", "#220800"),
    "F":  ("#ff4444", "#220000"),
}


def grade(win_rate: float, profit: float) -> str:
    score = win_rate * 0.5 + max(0, profit / 10)
    if score >= 65:  return "A+"
    if score >= 55:  return "A"
    if score >= 45:  return "B"
    if score >= 35:  return "C"
    if score >= 25:  return "D"
    return "F"


def _spark_color(profit: float) -> str:
    return "#00ff88" if profit >= 0 else "#ff4444"


def _pct_badge(val: float, positive_good: bool = True) -> str:
    good = val >= 0 if positive_good else val <= 0
    color = "#00ff88" if good else "#ff4444"
    arrow = "▲" if val >= 0 else "▼"
    return f'<span style="color:{color};font-weight:600">{arrow} {abs(val):.2f}%</span>'


def build_html_report(results: list[dict], start_date: str, end_date: str) -> str:
    df = pd.DataFrame(results)

    # ── aggregate per strategy (across all coins) ──────────────────────────
    strat_agg = (
        df.groupby("strategy")
          .agg(
              coins=("coin", "count"),
              trades=("trades", "sum"),
              wins=("wins", "sum"),
              losses=("losses", "sum"),
              total_profit=("profit_usd", "sum"),
              avg_mdd=("max_drawdown_pct", "mean"),
          )
          .reset_index()
    )
    strat_agg["win_rate"] = np.where(
        strat_agg["trades"] > 0,
        strat_agg["wins"] / strat_agg["trades"] * 100, 0
    ).round(2)
    strat_agg["return_pct"] = (strat_agg["total_profit"] / (6 * INITIAL_CASH) * 100).round(2)

    # ── per coin aggregate ─────────────────────────────────────────────────
    coin_agg = (
        df.groupby("coin")
          .agg(
              trades=("trades", "sum"),
              wins=("wins", "sum"),
              total_profit=("profit_usd", "sum"),
              avg_mdd=("max_drawdown_pct", "mean"),
          )
          .reset_index()
    )
    coin_agg["win_rate"] = np.where(
        coin_agg["trades"] > 0,
        coin_agg["wins"] / coin_agg["trades"] * 100, 0
    ).round(2)

    # ── build table rows ────────────────────────────────────────────────────
    def row_color(profit: float) -> str:
        if profit > 0:   return "rgba(0,255,136,0.04)"
        if profit < -50: return "rgba(255,68,68,0.07)"
        return "transparent"

    table_rows = ""
    for r in sorted(results, key=lambda x: (x["coin"], x["execution_tf"], x["strategy"])):
        g = grade(r["win_rate"], r["profit_usd"])
        gc, gtxt = _GRADE_COLOR.get(g, ("#888", "#111"))
        wr_color = "#00ff88" if r["win_rate"] >= 50 else ("#ffcc00" if r["win_rate"] >= 40 else "#ff4444")
        p_color  = "#00ff88" if r["profit_usd"] >= 0 else "#ff4444"
        pf_str   = f'{r["profit_factor"]:.2f}' if r["profit_factor"] != float("inf") else "∞"
        table_rows += f"""
        <tr style="background:{row_color(r['profit_usd'])}">
          <td><span class="coin-badge">{r['coin'].replace('USDT','')}</span></td>
          <td><span class="tf-badge tf-{r['execution_tf'].replace('m','m').replace('h','h')}">{r['execution_tf']}</span></td>
          <td class="strategy-name">{r['strategy']}</td>
          <td class="num">{r['trades']}</td>
          <td class="num" style="color:{wr_color};font-weight:700">{r['win_rate']:.1f}%</td>
          <td class="num">{r['wins']} / {r['losses']}</td>
          <td class="num" style="color:{p_color};font-weight:700">${r['profit_usd']:+.2f}</td>
          <td class="num">${r['final_balance']:.2f}</td>
          <td class="num" style="color:{p_color}">{r['return_pct']:+.2f}%</td>
          <td class="num" style="color:#ff8844">{r['max_drawdown_pct']:.1f}%</td>
          <td class="num">{pf_str}</td>
          <td><span class="grade" style="background:{gc};color:{gtxt}">{g}</span></td>
        </tr>"""

    # ── strategy summary cards ──────────────────────────────────────────────
    strat_cards = ""
    for _, sr in strat_agg.iterrows():
        g  = grade(sr["win_rate"], sr["total_profit"] / 6)
        gc, gtxt = _GRADE_COLOR.get(g, ("#888","#111"))
        pc = "#00ff88" if sr["total_profit"] >= 0 else "#ff4444"
        strat_cards += f"""
        <div class="strat-card">
          <div class="strat-grade" style="background:{gc};color:{gtxt}">{g}</div>
          <div class="strat-name">{sr['strategy']}</div>
          <div class="strat-metrics">
            <div class="metric"><span class="ml">Win Rate</span><span class="mv" style="color:{'#00ff88' if sr['win_rate']>=50 else '#ffcc00'}">{sr['win_rate']:.1f}%</span></div>
            <div class="metric"><span class="ml">Trades</span><span class="mv">{sr['trades']}</span></div>
            <div class="metric"><span class="ml">Total P&L</span><span class="mv" style="color:{pc}">${sr['total_profit']:+.2f}</span></div>
            <div class="metric"><span class="ml">Avg MDD</span><span class="mv" style="color:#ff8844">{sr['avg_mdd']:.1f}%</span></div>
          </div>
        </div>"""

    # ── coin summary cards ──────────────────────────────────────────────────
    coin_cards = ""
    for _, cr in coin_agg.iterrows():
        pc = "#00ff88" if cr["total_profit"] >= 0 else "#ff4444"
        lbl = COIN_LABELS.get(cr["coin"], cr["coin"])
        short = cr["coin"].replace("USDT", "")
        coin_cards += f"""
        <div class="coin-card">
          <div class="coin-sym">{short}</div>
          <div class="coin-label">{lbl}</div>
          <div class="coin-metrics">
            <div class="metric"><span class="ml">Win Rate</span><span class="mv" style="color:{'#00ff88' if cr['win_rate']>=50 else '#ffcc00'}">{cr['win_rate']:.1f}%</span></div>
            <div class="metric"><span class="ml">Trades</span><span class="mv">{cr['trades']}</span></div>
            <div class="metric"><span class="ml">Net P&L</span><span class="mv" style="color:{pc}">${cr['total_profit']:+.2f}</span></div>
            <div class="metric"><span class="ml">Avg MDD</span><span class="mv" style="color:#ff8844">{cr['avg_mdd']:.1f}%</span></div>
          </div>
        </div>"""

    # ── global stats ───────────────────────────────────────────────────────
    total_trades  = df["trades"].sum()
    total_wins    = df["wins"].sum()
    total_profit  = df["profit_usd"].sum()
    global_wr     = (total_wins / total_trades * 100) if total_trades else 0
    best_row      = df.loc[df["profit_usd"].idxmax()]
    worst_row     = df.loc[df["profit_usd"].idxmin()]
    best_wr_row   = df.loc[df["win_rate"].idxmax()]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Crypto Backtest Report | 6-Month | Top 6 Coins</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#060d1a;--bg2:#0a1628;--bg3:#0f1f38;--bg4:#162544;
  --accent:#00c8ff;--accent2:#7b61ff;--green:#00ff88;--red:#ff4444;
  --yellow:#ffcc00;--border:rgba(255,255,255,0.07);
  --text:#e8f0fe;--muted:#7a90b0;
}}
html{{scroll-behavior:smooth}}
body{{
  font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);
  line-height:1.6;min-height:100vh;overflow-x:hidden;
}}
/* HERO */
.hero{{
  background:linear-gradient(135deg,#060d1a 0%,#0d1f3c 40%,#0a1628 100%);
  border-bottom:1px solid var(--border);padding:56px 40px 40px;
  position:relative;overflow:hidden;
}}
.hero::before{{
  content:'';position:absolute;top:-40%;left:-20%;width:80%;height:200%;
  background:radial-gradient(ellipse at center,rgba(0,200,255,0.07) 0%,transparent 60%);
  pointer-events:none;
}}
.hero::after{{
  content:'';position:absolute;top:0;right:0;width:50%;height:100%;
  background:radial-gradient(ellipse at 80% 50%,rgba(123,97,255,0.06) 0%,transparent 60%);
  pointer-events:none;
}}
.hero-inner{{max-width:1400px;margin:0 auto;position:relative;z-index:1}}
.hero-tag{{
  display:inline-flex;align-items:center;gap:8px;
  background:rgba(0,200,255,0.1);border:1px solid rgba(0,200,255,0.25);
  border-radius:100px;padding:5px 14px;font-size:11px;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--accent);font-weight:600;margin-bottom:20px;
}}
.hero-tag .dot{{
  width:6px;height:6px;border-radius:50%;background:var(--accent);
  animation:pulse 2s infinite;
}}
@keyframes pulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.4;transform:scale(0.8)}}}}
.hero h1{{
  font-size:clamp(28px,4vw,48px);font-weight:900;letter-spacing:-1px;
  background:linear-gradient(135deg,#e8f0fe 0%,#a0c4ff 50%,var(--accent) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;margin-bottom:10px;
}}
.hero-sub{{color:var(--muted);font-size:14px;margin-bottom:32px}}
.hero-meta{{
  display:flex;flex-wrap:wrap;gap:24px;
}}
.meta-item{{
  display:flex;flex-direction:column;gap:2px;
}}
.meta-label{{font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted)}}
.meta-value{{font-size:14px;font-weight:600;color:var(--text);font-family:'JetBrains Mono',monospace}}
/* MAIN CONTENT */
.container{{max-width:1400px;margin:0 auto;padding:40px}}
/* GLOBAL KPI STRIP */
.kpi-strip{{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;
  margin-bottom:40px;
}}
.kpi{{
  background:var(--bg2);border:1px solid var(--border);border-radius:16px;
  padding:20px 24px;position:relative;overflow:hidden;transition:transform .2s;
}}
.kpi:hover{{transform:translateY(-2px)}}
.kpi::before{{
  content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--accent),var(--accent2));
}}
.kpi-label{{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted);margin-bottom:8px}}
.kpi-value{{font-size:28px;font-weight:800;font-family:'JetBrains Mono',monospace;line-height:1}}
.kpi-sub{{font-size:12px;color:var(--muted);margin-top:4px}}
/* SECTION */
.section{{margin-bottom:48px}}
.section-header{{
  display:flex;align-items:center;gap:12px;margin-bottom:20px;
}}
.section-icon{{
  width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;
}}
.section-title{{font-size:18px;font-weight:700;color:var(--text)}}
.section-sub{{font-size:13px;color:var(--muted)}}
/* STRATEGY CARDS */
.strat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}
.strat-card{{
  background:var(--bg2);border:1px solid var(--border);border-radius:16px;
  padding:24px;position:relative;overflow:hidden;transition:all .25s;
}}
.strat-card:hover{{border-color:rgba(0,200,255,0.3);transform:translateY(-3px);box-shadow:0 12px 40px rgba(0,200,255,0.08)}}
.strat-grade{{
  position:absolute;top:16px;right:16px;
  width:38px;height:38px;border-radius:10px;
  display:flex;align-items:center;justify-content:center;
  font-size:14px;font-weight:900;
}}
.strat-name{{font-size:14px;font-weight:700;color:var(--text);margin-bottom:16px;padding-right:44px;line-height:1.3}}
.strat-metrics{{display:flex;flex-direction:column;gap:8px}}
.metric{{display:flex;justify-content:space-between;align-items:center}}
.ml{{font-size:12px;color:var(--muted)}}
.mv{{font-size:13px;font-weight:600;font-family:'JetBrains Mono',monospace}}
/* COIN CARDS */
.coin-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}}
.coin-card{{
  background:var(--bg2);border:1px solid var(--border);border-radius:16px;
  padding:20px;transition:all .25s;
}}
.coin-card:hover{{border-color:rgba(123,97,255,0.35);transform:translateY(-2px)}}
.coin-sym{{font-size:22px;font-weight:900;color:var(--accent);font-family:'JetBrains Mono',monospace;margin-bottom:2px}}
.coin-label{{font-size:11px;color:var(--muted);margin-bottom:14px}}
.coin-metrics{{display:flex;flex-direction:column;gap:7px}}
/* TABLE */
.table-wrap{{
  background:var(--bg2);border:1px solid var(--border);border-radius:16px;
  overflow:hidden;
}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead th{{
  background:var(--bg3);padding:13px 14px;text-align:left;
  font-size:10px;letter-spacing:1.2px;text-transform:uppercase;
  color:var(--muted);font-weight:600;white-space:nowrap;border-bottom:1px solid var(--border);
}}
tbody tr{{border-bottom:1px solid var(--border);transition:background .15s}}
tbody tr:last-child{{border-bottom:none}}
tbody tr:hover{{background:rgba(255,255,255,0.03)!important}}
tbody td{{padding:12px 14px;vertical-align:middle}}
.num{{text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px}}
.strategy-name{{font-weight:600;color:var(--text);white-space:nowrap;font-size:12px}}
/* BADGES */
.coin-badge{{
  display:inline-block;background:rgba(0,200,255,0.12);color:var(--accent);
  border:1px solid rgba(0,200,255,0.25);border-radius:6px;
  padding:2px 8px;font-size:11px;font-weight:700;font-family:'JetBrains Mono',monospace;
  white-space:nowrap;
}}
.tf-badge{{
  display:inline-block;border-radius:6px;padding:2px 8px;
  font-size:11px;font-weight:700;font-family:'JetBrains Mono',monospace;white-space:nowrap;
}}
.tf-15m{{background:rgba(255,204,0,0.12);color:#ffcc00;border:1px solid rgba(255,204,0,0.25)}}
.tf-1h{{background:rgba(123,97,255,0.12);color:#a78bfa;border:1px solid rgba(123,97,255,0.25)}}
.tf-4h{{background:rgba(0,255,136,0.12);color:#00ff88;border:1px solid rgba(0,255,136,0.25)}}
.grade{{
  display:inline-flex;align-items:center;justify-content:center;
  width:32px;height:24px;border-radius:6px;font-size:11px;font-weight:900;
}}
/* HIGHLIGHTS */
.highlights{{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;
  margin-bottom:48px;
}}
.hl-card{{
  background:var(--bg2);border:1px solid var(--border);border-radius:16px;
  padding:20px 24px;
}}
.hl-label{{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted);margin-bottom:6px}}
.hl-main{{font-size:18px;font-weight:800;color:var(--text);margin-bottom:4px}}
.hl-sub{{font-size:12px;color:var(--muted)}}
.tag-green{{color:var(--green)}}
.tag-red{{color:var(--red)}}
/* SETTINGS BOX */
.settings-grid{{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;
}}
.setting-item{{
  background:var(--bg3);border:1px solid var(--border);border-radius:12px;
  padding:14px 18px;
}}
.setting-label{{font-size:11px;color:var(--muted);margin-bottom:4px;letter-spacing:0.8px}}
.setting-value{{font-size:15px;font-weight:700;font-family:'JetBrains Mono',monospace;color:var(--accent)}}
/* FOOTER */
.footer{{
  text-align:center;padding:40px;color:var(--muted);font-size:12px;
  border-top:1px solid var(--border);
}}
/* SCROLL */
::-webkit-scrollbar{{width:6px;height:6px}}
::-webkit-scrollbar-track{{background:var(--bg)}}
::-webkit-scrollbar-thumb{{background:var(--bg4);border-radius:3px}}
/* RESPONSIVE */
@media(max-width:768px){{
  .container{{padding:20px}}
  .hero{{padding:32px 20px 28px}}
  table{{font-size:12px}}
  tbody td{{padding:10px 8px}}
  thead th{{padding:10px 8px}}
}}
/* ANIMATIONS */
@keyframes fadeUp{{from{{opacity:0;transform:translateY(20px)}}to{{opacity:1;transform:translateY(0)}}}}
.fade-up{{animation:fadeUp .5s ease forwards}}
.delay-1{{animation-delay:.1s}}
.delay-2{{animation-delay:.2s}}
.delay-3{{animation-delay:.3s}}
</style>
</head>
<body>

<!-- HERO -->
<div class="hero">
  <div class="hero-inner">
    <div class="hero-tag"><span class="dot"></span> Live Backtest Results</div>
    <h1>Crypto Strategy Backtest Report</h1>
    <div class="hero-sub">6-Month Analysis · Top 6 Coins · 15m · 1h · 4h · Strict TP/SL · $100 Risk/Trade</div>
    <div class="hero-meta">
      <div class="meta-item"><span class="meta-label">Period</span><span class="meta-value">{start_date} → {end_date}</span></div>
      <div class="meta-item"><span class="meta-label">Portfolio</span><span class="meta-value">$1,000.00</span></div>
      <div class="meta-item"><span class="meta-label">Risk / Trade</span><span class="meta-value">$100.00</span></div>
      <div class="meta-item"><span class="meta-label">Strategies</span><span class="meta-value">4 Strategies</span></div>
      <div class="meta-item"><span class="meta-label">Coins</span><span class="meta-value">BTC · ETH · BNB · SOL · XRP · ADA</span></div>
    </div>
  </div>
</div>

<div class="container">

<!-- KPI STRIP -->
<div class="kpi-strip fade-up">
  <div class="kpi">
    <div class="kpi-label">Global Win Rate</div>
    <div class="kpi-value" style="color:{'#00ff88' if global_wr>=50 else '#ffcc00'}">{global_wr:.1f}%</div>
    <div class="kpi-sub">{total_wins} wins of {total_trades} trades</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Total Trades</div>
    <div class="kpi-value" style="color:var(--accent)">{total_trades}</div>
    <div class="kpi-sub">Across all coins & strategies</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Combined Net P&L</div>
    <div class="kpi-value" style="color:{'#00ff88' if total_profit>=0 else '#ff4444'}">${total_profit:+.2f}</div>
    <div class="kpi-sub">On $1,000 portfolio × 6 coins</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Best Strategy</div>
    <div class="kpi-value" style="font-size:16px;color:var(--green)">{strat_agg.loc[strat_agg['total_profit'].idxmax(),'strategy']}</div>
    <div class="kpi-sub">${strat_agg['total_profit'].max():+.2f} combined P&amp;L</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Best Coin</div>
    <div class="kpi-value" style="font-size:16px;color:var(--green)">{coin_agg.loc[coin_agg['total_profit'].idxmax(),'coin'].replace('USDT','')}</div>
    <div class="kpi-sub">${coin_agg['total_profit'].max():+.2f} net P&amp;L</div>
  </div>
</div>

<!-- BACKTEST SETTINGS -->
<div class="section fade-up delay-1">
  <div class="section-header">
    <div class="section-icon">⚙</div>
    <div>
      <div class="section-title">Backtest Configuration</div>
      <div class="section-sub">Strict TP/SL applied on OHLC bars — no lookahead bias</div>
    </div>
  </div>
  <div class="settings-grid">
    <div class="setting-item"><div class="setting-label">Portfolio Size</div><div class="setting-value">$1,000</div></div>
    <div class="setting-item"><div class="setting-label">Risk Per Trade</div><div class="setting-value">$100</div></div>
    <div class="setting-item"><div class="setting-label">Position Mode</div><div class="setting-value">Risk-Based Sizing</div></div>
    <div class="setting-item"><div class="setting-label">Taker Fee</div><div class="setting-value">0.045%</div></div>
    <div class="setting-item"><div class="setting-label">Slippage Buffer</div><div class="setting-value">0.05%</div></div>
    <div class="setting-item"><div class="setting-label">Stop Type</div><div class="setting-value">StopMarket (Strict)</div></div>
    <div class="setting-item"><div class="setting-label">Lookback</div><div class="setting-value">180 Days</div></div>
    <div class="setting-item"><div class="setting-label">Timeframes</div><div class="setting-value">15m · 1h · 4h</div></div>
  </div>
</div>

<!-- HIGHLIGHTS -->
<div class="section fade-up delay-1">
  <div class="section-header">
    <div class="section-icon">🏆</div>
    <div>
      <div class="section-title">Top Performers</div>
      <div class="section-sub">Best and worst individual runs</div>
    </div>
  </div>
  <div class="highlights">
    <div class="hl-card">
      <div class="hl-label">🥇 Best Run (P&L)</div>
      <div class="hl-main tag-green">${best_row['profit_usd']:+.2f}  ({best_row['return_pct']:+.1f}%)</div>
      <div class="hl-sub">{best_row['coin']} · {best_row['strategy']} · {best_row['execution_tf']}</div>
    </div>
    <div class="hl-card">
      <div class="hl-label">🔴 Worst Run (P&L)</div>
      <div class="hl-main tag-red">${worst_row['profit_usd']:+.2f}  ({worst_row['return_pct']:+.1f}%)</div>
      <div class="hl-sub">{worst_row['coin']} · {worst_row['strategy']} · {worst_row['execution_tf']}</div>
    </div>
    <div class="hl-card">
      <div class="hl-label">🎯 Best Win Rate</div>
      <div class="hl-main tag-green">{best_wr_row['win_rate']:.1f}%</div>
      <div class="hl-sub">{best_wr_row['coin']} · {best_wr_row['strategy']} · {best_wr_row['execution_tf']}</div>
    </div>
    <div class="hl-card">
      <div class="hl-label">📊 Avg Profit Factor</div>
      <div class="hl-main" style="color:var(--accent)">{df.loc[df['profit_factor']!=float('inf'),'profit_factor'].mean():.2f}x</div>
      <div class="hl-sub">Win amount ÷ Loss amount (excl. ∞)</div>
    </div>
  </div>
</div>

<!-- STRATEGY SUMMARY -->
<div class="section fade-up delay-2">
  <div class="section-header">
    <div class="section-icon">📈</div>
    <div>
      <div class="section-title">Strategy Performance</div>
      <div class="section-sub">Aggregated across all 6 coins</div>
    </div>
  </div>
  <div class="strat-grid">{strat_cards}</div>
</div>

<!-- COIN SUMMARY -->
<div class="section fade-up delay-2">
  <div class="section-header">
    <div class="section-icon">🪙</div>
    <div>
      <div class="section-title">Coin Performance</div>
      <div class="section-sub">Aggregated across all strategies and timeframes</div>
    </div>
  </div>
  <div class="coin-grid">{coin_cards}</div>
</div>

<!-- MAIN TABLE -->
<div class="section fade-up delay-3">
  <div class="section-header">
    <div class="section-icon">📋</div>
    <div>
      <div class="section-title">Full Results — Every Coin × Timeframe × Strategy</div>
      <div class="section-sub">$1,000 portfolio · $100 risk/trade · strict TP/SL</div>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Coin</th><th>TF</th><th>Strategy</th><th>Trades</th>
          <th>Win Rate</th><th>W / L</th><th>Profit</th>
          <th>Final Bal.</th><th>Return %</th><th>Max DD</th>
          <th>Prof. Factor</th><th>Grade</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>
</div>

</div><!-- /container -->

<div class="footer">
  Generated by Crypto Backtester · vectorbt · {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M UTC')} ·
  All results are simulated past-data backtests — not financial advice.
</div>

</body>
</html>"""
    return html


# ────────────────────────────── MAIN ────────────────────────────────────────
def main() -> None:
    results: list[dict] = []
    errors:  list[str]  = []
    signal_total = 0

    global_start = None
    global_end   = None

    for symbol in COINS:
        print(f"\n{'='*60}")
        print(f"  {symbol}")
        print(f"{'='*60}")
        try:
            frames   = load_symbol_frames(symbol)
            end_time = max(f["timestamp"].iloc[-1] for f in frames.values())
            start_time = end_time - pd.Timedelta(days=LOOKBACK_DAYS)
            if global_start is None or start_time < global_start:
                global_start = start_time
            if global_end is None or end_time > global_end:
                global_end = end_time
        except FileNotFoundError as e:
            errors.append(str(e))
            print(f"  WARNING: {e}")
            continue

        for strategy in STRATEGIES:
            print(f"  >> {strategy.name:35s} [{strategy.execution_tf}]", end=" ... ", flush=True)
            try:
                primary, inputs, signals = generate_vectorbt_inputs(
                    frames, strategy, start_time
                )
                pf = run_portfolio(primary, inputs, strategy.execution_tf)
                row = summarize_portfolio(
                    symbol, strategy, pf, len(signals), start_time, end_time
                )
                results.append(row)
                signal_total += len(signals)
                wr  = row["win_rate"]
                pnl = row["profit_usd"]
                print(f"OK  trades={row['trades']:3d}  wr={wr:5.1f}%  pnl=${pnl:+.2f}")
            except Exception as exc:
                msg = f"{symbol} / {strategy.name}: {exc}"
                errors.append(msg)
                print(f"ERR  ERROR: {exc}")

    if not results:
        print("\n[!] No results — check your data files.")
        return

    df = pd.DataFrame(results)

    # ── save CSVs ─────────────────────────────────────────────────────────
    raw_path  = OUT_DIR / "all_results.csv"
    summ_path = OUT_DIR / "summary_coin_tf_strategy.csv"
    df.to_csv(raw_path,  index=False)

    summary = df[[
        "coin", "execution_tf", "strategy", "trades", "wins", "losses",
        "win_rate", "max_drawdown_pct", "profit_usd", "final_balance",
        "return_pct", "avg_win_usd", "avg_loss_usd", "profit_factor",
    ]].copy().rename(columns={
        "execution_tf":   "timeframe",
        "win_rate":       "win_rate_%",
        "max_drawdown_pct": "max_drawdown_%",
        "profit_usd":     "profit_on_$1000",
        "return_pct":     "return_%",
    }).sort_values(["coin", "timeframe", "strategy"])
    summary.to_csv(summ_path, index=False)

    # ── save HTML ─────────────────────────────────────────────────────────
    start_str = global_start.strftime("%Y-%m-%d") if global_start else "N/A"
    end_str   = global_end.strftime("%Y-%m-%d")   if global_end   else "N/A"
    html      = build_html_report(results, start_str, end_str)
    html_path = OUT_DIR / "backtest_report.html"
    html_path.write_text(html, encoding="utf-8")

    # ── print summary table ───────────────────────────────────────────────
    print(f"\n\n{'='*100}")
    print("  FULL COIN x TIMEFRAME x STRATEGY SUMMARY")
    print(f"{'='*100}")
    pd.set_option("display.max_rows", 500)
    pd.set_option("display.width", 200)
    print(summary.to_string(index=False))

    print(f"\n\n{'='*100}")
    print(f"  SAVED TO --> {OUT_DIR}/")
    print(f"     - all_results.csv")
    print(f"     - summary_coin_tf_strategy.csv")
    print(f"     - backtest_report.html  (open in browser for full visual report)")
    print(f"  Total raw signals generated: {signal_total}")
    if errors:
        print(f"\n  WARNING: {len(errors)} error(s):")
        for e in errors:
            print(f"     {e}")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    main()
