from __future__ import annotations

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


DATA_DIR = Path("data")
RESULTS_FILE = Path("top6_tp_sl_backtest_results.csv")
SUMMARY_FILE = Path("top6_tp_sl_backtest_summary.csv")
MY_SUMMARY_FILE = Path("top6_coin_timeframe_strategy_summary.csv")

COINS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT")
TIMEFRAMES = ("15m", "1h", "4h")

LOOKBACK_DAYS = 30
INITIAL_CASH = 1000.0
POSITION_MODE = "risk"  # "risk" uses $ risk per SL; "all_cash" uses full available cash.
RISK_PER_TRADE_USD = 100.0
MAX_NOTIONAL_USD = INITIAL_CASH
FEE_RATE = 0.00045
SLIPPAGE_RATE = 0.0005

TIMEFRAME_DELTAS = {
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
}


@dataclass(frozen=True)
class StrategySpec:
    name: str
    execution_tf: str
    build_setups: Callable[[dict[str, pd.DataFrame]], pd.DataFrame]


def load_frame(symbol: str, timeframe: str) -> pd.DataFrame:
    path = DATA_DIR / symbol / f"{timeframe}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing data file: {path}")

    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    df["ts"] = (df["timestamp"].astype("int64") // 1_000_000).astype("int64")
    return df


def load_symbol_frames(symbol: str) -> dict[str, pd.DataFrame]:
    return {timeframe: load_frame(symbol, timeframe) for timeframe in TIMEFRAMES}


def true_range(df: pd.DataFrame) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    return pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_adx = true_range(df).rolling(period).mean().replace(0, 1e-9)
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr_adx)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr_adx)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    return dx.rolling(period).mean()


def sideways_filter(df: pd.DataFrame) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = true_range(df)

    atr_ratio = tr.rolling(14).mean() / tr.rolling(100).mean()
    sum_tr = tr.rolling(14).sum()
    range_diff = (high.rolling(14).max() - low.rolling(14).min()).replace(0, 1e-9)
    chop = 100 * np.log10((sum_tr / range_diff).replace(0, 1e-9)) / np.log10(14)
    donchian_width = (high.rolling(20).max() - low.rolling(20).min()) / close

    sideways = (
        (adx(df) < 20.0).astype(int)
        + (chop > 61.8).astype(int)
        + (atr_ratio < 0.95).astype(int)
    ) >= 2
    compression = (atr_ratio < 0.95) & (donchian_width < 0.025)
    return (sideways & ~compression).fillna(False)


def asof_to(target: pd.DataFrame, source: pd.DataFrame, column: str) -> pd.Series:
    aligned = pd.merge_asof(
        target[["timestamp"]].sort_values("timestamp"),
        source[["timestamp", column]].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )
    return aligned[column].reindex(target.index)


def blank_setups(primary: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "side": "",
            "stop_loss": np.nan,
            "take_profit": np.nan,
        },
        index=primary.index,
    )


def vwap_setups(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = frames["15m"].copy()
    setups = blank_setups(df)

    h4 = frames["4h"].copy()
    h4["ema50"] = ema(h4["close"], 50)
    h4["h4_bullish"] = h4["close"] > h4["ema50"]
    df["h4_bullish"] = asof_to(df, h4, "h4_bullish").fillna(False)

    df["vwap"] = session_vwap(df)
    df["ema9"] = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)
    df["vol_ma10"] = df["volume"].rolling(10).mean()
    df["sideways"] = sideways_filter(df)

    vol_spike = df["volume"] > df["vol_ma10"]
    crossed_up = (df["ema9"].shift(1) <= df["ema21"].shift(1)) & (df["ema9"] > df["ema21"])
    crossed_down = (df["ema9"].shift(1) >= df["ema21"].shift(1)) & (df["ema9"] < df["ema21"])

    long_stop = df["low"].rolling(5).min()
    short_stop = df["high"].rolling(5).max()
    long_dist = df["close"] - long_stop
    short_dist = short_stop - df["close"]

    long_signal = (
        (df["close"] > df["vwap"])
        & crossed_up
        & vol_spike
        & df["h4_bullish"]
        & ~df["sideways"]
        & (long_stop < df["close"])
    )
    short_signal = (
        (df["close"] < df["vwap"])
        & crossed_down
        & vol_spike
        & ~df["h4_bullish"]
        & ~df["sideways"]
        & (short_stop > df["close"])
    )

    setups.loc[long_signal, "side"] = "long"
    setups.loc[long_signal, "stop_loss"] = long_stop[long_signal]
    setups.loc[long_signal, "take_profit"] = df.loc[long_signal, "close"] + 1.5 * long_dist[long_signal]

    setups.loc[short_signal, "side"] = "short"
    setups.loc[short_signal, "stop_loss"] = short_stop[short_signal]
    setups.loc[short_signal, "take_profit"] = df.loc[short_signal, "close"] - 1.5 * short_dist[short_signal]
    return setups


def pivot_levels(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    high = df["high"]
    low = df["low"]
    pivot_high = high.where(high == high.rolling(5, center=True).max())
    pivot_low = low.where(low == low.rolling(5, center=True).min())
    return pivot_high.ffill(), pivot_low.ffill()


def fvg_flags(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    bearish = df["low"].shift(2) > df["high"]
    bullish = df["high"].shift(2) < df["low"]
    return bearish.rolling(5).max().astype(bool), bullish.rolling(5).max().astype(bool)


def ltf_sweep_setups(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = frames["15m"].copy()
    setups = blank_setups(df)

    h1 = frames["1h"].copy()
    h1["swing_high"] = h1["high"].rolling(24).max()
    h1["swing_low"] = h1["low"].rolling(24).min()
    df["swing_high"] = asof_to(df, h1, "swing_high")
    df["swing_low"] = asof_to(df, h1, "swing_low")

    last_pivot_high, last_pivot_low = pivot_levels(df)
    bearish_fvg, bullish_fvg = fvg_flags(df)

    swept_high = ((df["high"] > df["swing_high"]) & (df["close"] < df["swing_high"])).rolling(3).max().astype(bool)
    swept_low = ((df["low"] < df["swing_low"]) & (df["close"] > df["swing_low"])).rolling(3).max().astype(bool)

    short_stop = df["high"].rolling(3).max()
    long_stop = df["low"].rolling(3).min()
    short_signal = swept_high & (df["close"] < last_pivot_low) & bearish_fvg & (short_stop > df["close"])
    long_signal = swept_low & (df["close"] > last_pivot_high) & bullish_fvg & (long_stop < df["close"])

    setups.loc[short_signal, "side"] = "short"
    setups.loc[short_signal, "stop_loss"] = short_stop[short_signal]
    setups.loc[short_signal, "take_profit"] = df.loc[short_signal, "close"] - 2.0 * (short_stop[short_signal] - df.loc[short_signal, "close"])

    setups.loc[long_signal, "side"] = "long"
    setups.loc[long_signal, "stop_loss"] = long_stop[long_signal]
    setups.loc[long_signal, "take_profit"] = df.loc[long_signal, "close"] + 2.0 * (df.loc[long_signal, "close"] - long_stop[long_signal])
    return setups


def htf_sweep_setups(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = frames["1h"].copy()
    setups = blank_setups(df)

    h4 = frames["4h"].copy()
    h4["swing_high"] = h4["high"].rolling(6).max()
    h4["swing_low"] = h4["low"].rolling(6).min()
    df["swing_high"] = asof_to(df, h4, "swing_high")
    df["swing_low"] = asof_to(df, h4, "swing_low")

    last_pivot_high, last_pivot_low = pivot_levels(df)
    bearish_fvg, bullish_fvg = fvg_flags(df)

    swept_high = ((df["high"] > df["swing_high"]) & (df["close"] < df["swing_high"])).rolling(3).max().astype(bool)
    swept_low = ((df["low"] < df["swing_low"]) & (df["close"] > df["swing_low"])).rolling(3).max().astype(bool)

    short_stop = df["high"].rolling(3).max()
    long_stop = df["low"].rolling(3).min()
    short_signal = swept_high & (df["close"] < last_pivot_low) & bearish_fvg & (short_stop > df["close"])
    long_signal = swept_low & (df["close"] > last_pivot_high) & bullish_fvg & (long_stop < df["close"])

    setups.loc[short_signal, "side"] = "short"
    setups.loc[short_signal, "stop_loss"] = short_stop[short_signal]
    setups.loc[short_signal, "take_profit"] = df.loc[short_signal, "close"] - 2.0 * (short_stop[short_signal] - df.loc[short_signal, "close"])

    setups.loc[long_signal, "side"] = "long"
    setups.loc[long_signal, "stop_loss"] = long_stop[long_signal]
    setups.loc[long_signal, "take_profit"] = df.loc[long_signal, "close"] + 2.0 * (df.loc[long_signal, "close"] - long_stop[long_signal])
    return setups


def atr_breakout_setups(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = frames["1h"].copy()
    setups = blank_setups(df)

    tr = true_range(df)
    df["atr_ratio"] = tr.rolling(14).mean() / tr.rolling(100).mean()
    df["vol_sma20"] = df["volume"].rolling(20).mean()
    df["adx"] = adx(df)
    df["ema50"] = ema(df["close"], 50)

    prev_donchian_high = df["high"].shift(1).rolling(20).max()
    prev_donchian_low = df["low"].shift(1).rolling(20).min()
    recent_compression = df["atr_ratio"].rolling(5).min() < 0.95
    vol_spike = df["volume"] > 1.25 * df["vol_sma20"]
    adx_ok = (df["adx"] > df["adx"].shift(1)) | (df["adx"] > 25.0)
    sideways = sideways_filter(df)

    long_stop = prev_donchian_low.where(
        ~(df["close"] - prev_donchian_low > df["close"] * 0.1),
        df["low"].rolling(5).min(),
    )
    long_stop = long_stop.where(long_stop < df["close"], df["close"] * 0.99)

    short_stop = prev_donchian_high.where(
        ~(prev_donchian_high - df["close"] > df["close"] * 0.1),
        df["high"].rolling(5).max(),
    )
    short_stop = short_stop.where(short_stop > df["close"], df["close"] * 1.01)

    long_signal = (
        recent_compression
        & (df["close"] > prev_donchian_high)
        & vol_spike
        & adx_ok
        & (df["close"] > df["ema50"])
        & ~sideways
    )
    short_signal = (
        recent_compression
        & (df["close"] < prev_donchian_low)
        & vol_spike
        & adx_ok
        & (df["close"] < df["ema50"])
        & ~sideways
    )

    setups.loc[long_signal, "side"] = "long"
    setups.loc[long_signal, "stop_loss"] = long_stop[long_signal]
    setups.loc[long_signal, "take_profit"] = df.loc[long_signal, "close"] + 2.0 * (df.loc[long_signal, "close"] - long_stop[long_signal])

    setups.loc[short_signal, "side"] = "short"
    setups.loc[short_signal, "stop_loss"] = short_stop[short_signal]
    setups.loc[short_signal, "take_profit"] = df.loc[short_signal, "close"] - 2.0 * (short_stop[short_signal] - df.loc[short_signal, "close"])
    return setups


STRATEGIES = (
    StrategySpec("VWAP Momentum Scalp", "15m", vwap_setups),
    StrategySpec("Liquidity Sweep 15m/1h", "15m", ltf_sweep_setups),
    StrategySpec("Liquidity Sweep 1h/4h", "1h", htf_sweep_setups),
    StrategySpec("ATR Volume Breakout", "1h", atr_breakout_setups),
)


def position_size(entry_price: float, stop_loss: float) -> float:
    if POSITION_MODE == "all_cash":
        return np.inf

    distance = abs(entry_price - stop_loss)
    if distance <= 0:
        return 0.0

    friction = entry_price * (2 * FEE_RATE + SLIPPAGE_RATE)
    risk_sized_qty = RISK_PER_TRADE_USD / (distance + friction)
    max_cash_qty = MAX_NOTIONAL_USD / entry_price
    return max(0.0, min(risk_sized_qty, max_cash_qty))


def stop_percents(side: str, stop_loss: float, take_profit: float, entry_price: float) -> tuple[float, float] | None:
    if side == "long":
        if not (stop_loss < entry_price < take_profit):
            return None
    elif side == "short":
        if not (take_profit < entry_price < stop_loss):
            return None
    else:
        return None

    sl_stop = abs(entry_price - stop_loss) / entry_price
    tp_stop = abs(take_profit - entry_price) / entry_price
    if sl_stop <= 0 or tp_stop <= 0:
        return None
    return sl_stop, tp_stop


def generate_vectorbt_inputs(
    frames: dict[str, pd.DataFrame],
    strategy: StrategySpec,
    start_time: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, pd.Series], list[dict]]:
    primary = frames[strategy.execution_tf].copy().reset_index(drop=True)
    setups = strategy.build_setups(frames)
    index = primary["timestamp"]

    entries = pd.Series(False, index=index)
    exits = pd.Series(False, index=index)
    short_entries = pd.Series(False, index=index)
    short_exits = pd.Series(False, index=index)
    sl_stop = pd.Series(np.nan, index=index)
    tp_stop = pd.Series(np.nan, index=index)
    size = pd.Series(np.nan, index=index)

    entry_start = primary["timestamp"].searchsorted(start_time, side="left")
    first_signal_row = max(0, entry_start - 1)
    signal_records: list[dict] = []

    for signal_row in range(first_signal_row, len(primary) - 1):
        setup = setups.iloc[signal_row]
        side = setup["side"]
        if side not in ("long", "short"):
            continue

        entry_row = signal_row + 1
        entry_time = primary.at[entry_row, "timestamp"]
        if entry_time < start_time:
            continue

        entry_price = float(primary.at[entry_row, "open"])
        stop_loss = float(setup["stop_loss"])
        take_profit = float(setup["take_profit"])
        stops = stop_percents(side, stop_loss, take_profit, entry_price)
        if stops is None:
            continue

        qty = position_size(entry_price, stop_loss)
        if qty <= 0:
            continue

        sl_pct, tp_pct = stops
        if side == "long":
            entries.iloc[entry_row] = True
        else:
            short_entries.iloc[entry_row] = True

        sl_stop.iloc[entry_row] = sl_pct
        tp_stop.iloc[entry_row] = tp_pct
        size.iloc[entry_row] = qty

        signal_records.append(
            {
                "strategy": strategy.name,
                "timeframe": strategy.execution_tf,
                "signal_time": primary.at[signal_row, "timestamp"],
                "entry_time": entry_time,
                "side": side,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "sl_pct": sl_pct,
                "tp_pct": tp_pct,
                "size": qty,
            }
        )

    exits.iloc[-1] = True
    short_exits.iloc[-1] = True

    order_price = primary["open"].copy()
    order_price.iloc[-1] = primary["close"].iloc[-1]
    inputs = {
        "entries": entries,
        "exits": exits,
        "short_entries": short_entries,
        "short_exits": short_exits,
        "sl_stop": sl_stop,
        "tp_stop": tp_stop,
        "size": size,
        "order_price": order_price,
    }
    return primary, inputs, signal_records


def run_portfolio(
    primary: pd.DataFrame,
    inputs: dict[str, pd.Series],
    timeframe: str,
) -> vbt.Portfolio:
    return vbt.Portfolio.from_signals(
        close=primary["close"],
        entries=inputs["entries"],
        exits=inputs["exits"],
        short_entries=inputs["short_entries"],
        short_exits=inputs["short_exits"],
        size=inputs["size"],
        size_type="amount",
        price=inputs["order_price"],
        open=primary["open"],
        high=primary["high"],
        low=primary["low"],
        sl_stop=inputs["sl_stop"],
        tp_stop=inputs["tp_stop"],
        fees=FEE_RATE,
        slippage=SLIPPAGE_RATE,
        init_cash=INITIAL_CASH,
        accumulate=False,
        upon_opposite_entry=OppositeEntryMode.Ignore,
        stop_entry_price=StopEntryPrice.Price,
        stop_exit_price=StopExitPrice.StopMarket,
        upon_stop_exit=StopExitMode.Close,
        freq=TIMEFRAME_DELTAS[timeframe],
    )


def summarize_portfolio(
    symbol: str,
    strategy: StrategySpec,
    pf: vbt.Portfolio,
    signal_count: int,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
) -> dict:
    trades = pf.trades.records_readable
    closed = trades[trades["Status"] == "Closed"] if not trades.empty else trades
    wins = int((closed["PnL"] > 0).sum()) if not closed.empty else 0
    losses = int((closed["PnL"] <= 0).sum()) if not closed.empty else 0
    total_trades = int(len(closed))
    final_balance = float(pf.value().iloc[-1])
    profit = final_balance - INITIAL_CASH
    max_drawdown = float(abs(pf.max_drawdown())) * 100 if total_trades else 0.0

    return {
        "symbol": symbol,
        "strategy": strategy.name,
        "timeframe": strategy.execution_tf,
        "start": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "signals": signal_count,
        "trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round((wins / total_trades * 100) if total_trades else 0.0, 2),
        "final_balance": round(final_balance, 2),
        "profit_usd": round(profit, 2),
        "return_pct": round((profit / INITIAL_CASH) * 100, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
    }


def build_summary(results: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        results.groupby(["strategy", "timeframe"], as_index=False)
        .agg(
            portfolios=("symbol", "count"),
            trades=("trades", "sum"),
            wins=("wins", "sum"),
            losses=("losses", "sum"),
            profit_usd=("profit_usd", "sum"),
            final_balance=("final_balance", "sum"),
            max_drawdown_pct=("max_drawdown_pct", "mean"),
        )
    )
    grouped["initial_cash"] = grouped["portfolios"] * INITIAL_CASH
    grouped["win_rate_pct"] = np.where(
        grouped["trades"] > 0,
        grouped["wins"] / grouped["trades"] * 100,
        0.0,
    )
    grouped["return_pct"] = grouped["profit_usd"] / grouped["initial_cash"] * 100
    return grouped[
        [
            "strategy",
            "timeframe",
            "portfolios",
            "trades",
            "wins",
            "losses",
            "win_rate_pct",
            "initial_cash",
            "final_balance",
            "profit_usd",
            "return_pct",
            "max_drawdown_pct",
        ]
    ].round(2)


def build_coin_timeframe_strategy_summary(results: pd.DataFrame) -> pd.DataFrame:
    summary = results[
        [
            "symbol",
            "timeframe",
            "strategy",
            "trades",
            "wins",
            "losses",
            "win_rate_pct",
            "max_drawdown_pct",
            "profit_usd",
            "final_balance",
            "return_pct",
        ]
    ].copy()
    summary = summary.rename(
        columns={
            "symbol": "coin",
            "win_rate_pct": "win_rate",
            "max_drawdown_pct": "max_drawdown",
            "profit_usd": "total_profit_on_1000",
            "return_pct": "return_on_1000_pct",
        }
    )
    return summary.sort_values(["coin", "timeframe", "strategy"]).round(2)


def main() -> None:
    results = []
    signal_total = 0

    for symbol in COINS:
        print(f"Loading {symbol}")
        frames = load_symbol_frames(symbol)
        end_time = max(frame["timestamp"].iloc[-1] for frame in frames.values())
        start_time = end_time - pd.Timedelta(days=LOOKBACK_DAYS)

        for strategy in STRATEGIES:
            print(f"  Backtesting {strategy.name} ({strategy.execution_tf})")
            primary, inputs, signal_records = generate_vectorbt_inputs(
                frames,
                strategy,
                start_time,
            )
            pf = run_portfolio(primary, inputs, strategy.execution_tf)
            results.append(
                summarize_portfolio(
                    symbol,
                    strategy,
                    pf,
                    len(signal_records),
                    start_time,
                    end_time,
                )
            )
            signal_total += len(signal_records)

    results_df = pd.DataFrame(results)
    summary_df = build_summary(results_df)
    my_summary_df = build_coin_timeframe_strategy_summary(results_df)

    results_df.to_csv(RESULTS_FILE, index=False)
    summary_df.to_csv(SUMMARY_FILE, index=False)
    my_summary_df.to_csv(MY_SUMMARY_FILE, index=False)

    print("\nDetailed results")
    print(results_df.to_string(index=False))

    print("\nSummary by strategy")
    print(summary_df.to_string(index=False))

    print("\nCoin/timeframe/strategy summary")
    print(my_summary_df.to_string(index=False))

    print(f"\nSaved detailed results to {RESULTS_FILE}")
    print(f"Saved summary results to {SUMMARY_FILE}")
    print(f"Saved coin/timeframe/strategy summary to {MY_SUMMARY_FILE}")
    print(f"Generated {signal_total} raw entry signals")


if __name__ == "__main__":
    main()
