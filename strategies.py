"""Pure, unit-testable strategy logic.

Both strategies receive DataFrames of CLOSED candles only (the engine drops
the in-progress candle) with columns: ts, open, high, low, close, volume.
They return a Signal or None - they never touch the exchange.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import numpy as np

COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


@dataclass
class Signal:
    strategy_name: str
    symbol: str
    asset_class: str          # "crypto" | "stock"
    timeframe: str            # e.g., "15m", "1h", "4h"
    side: str                 # "long" | "short"
    entry_price: float
    soft_sl: float
    hard_sl: float
    tp: float
    rr: float
    confidence: str           # "High" | "Medium" | "Low"
    regime_tag: str           # "TRENDING" | "SIDEWAYS" | "VOLATILITY_COMPRESSION" | "REVERSAL_SWEEP_ZONE"
    score: float
    reason: str
    candle_ts: Optional[int] = None

    def __init__(self,
                 strategy_name: str = "",
                 symbol: str = "",
                 asset_class: str = "crypto",
                 timeframe: str = "15m",
                 side: str = "",
                 entry_price: float = 0.0,
                 soft_sl: float = 0.0,
                 hard_sl: float = 0.0,
                 tp: float = 0.0,
                 rr: float = 0.0,
                 confidence: str = "High",
                 regime_tag: str = "TRENDING",
                 score: float = 1.0,
                 reason: str = "",
                 candle_ts: Optional[int] = None,
                 # Legacy keyword fallbacks:
                 strategy: Optional[str] = None,
                 entry: Optional[float] = None,
                 stop_loss: Optional[float] = None,
                 take_profit: Optional[float] = None,
                 tf: Optional[str] = None):
        self.strategy_name = strategy if strategy is not None else strategy_name
        self.symbol = symbol
        self.asset_class = asset_class
        self.timeframe = tf if tf is not None else timeframe
        self.side = side
        self.entry_price = entry if entry is not None else entry_price
        self.soft_sl = stop_loss if stop_loss is not None else soft_sl
        self.tp = take_profit if take_profit is not None else tp
        self.confidence = confidence
        self.regime_tag = regime_tag
        self.score = score
        self.reason = reason
        self.candle_ts = candle_ts
        
        # Calculate derived metrics
        self.rr = rr if rr != 0.0 else (round(abs(self.tp - self.entry_price) / abs(self.entry_price - self.soft_sl), 2) if abs(self.entry_price - self.soft_sl) else 0.0)
        self.hard_sl = hard_sl if hard_sl != 0.0 else (self.entry_price - 2.0 * (self.entry_price - self.soft_sl))

    # Legacy properties for backward compatibility
    @property
    def strategy(self) -> str:
        return self.strategy_name

    @strategy.setter
    def strategy(self, val: str) -> None:
        self.strategy_name = val

    @property
    def entry(self) -> float:
        return self.entry_price

    @entry.setter
    def entry(self, val: float) -> None:
        self.entry_price = val

    @property
    def stop_loss(self) -> float:
        return self.soft_sl

    @stop_loss.setter
    def stop_loss(self, val: float) -> None:
        self.soft_sl = val

    @property
    def take_profit(self) -> float:
        return self.tp

    @take_profit.setter
    def take_profit(self, val: float) -> None:
        self.tp = val

    @property
    def tf(self) -> str:
        return self.timeframe

    @tf.setter
    def tf(self, val: str) -> None:
        self.timeframe = val


def to_df(ohlcv: list) -> pd.DataFrame:
    return pd.DataFrame(ohlcv, columns=COLUMNS)


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """Daily-anchored VWAP (resets at UTC midnight)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = pd.to_datetime(df["ts"], unit="ms").dt.date
    pv = (tp * df["volume"]).groupby(day).cumsum()
    vol = df["volume"].groupby(day).cumsum()
    return pv / vol


def classify_regime(symbol: str, df: pd.DataFrame, htf_high: Optional[float] = None, htf_low: Optional[float] = None) -> str:
    """Classify market regime as TRENDING, SIDEWAYS, VOLATILITY_COMPRESSION, or REVERSAL_SWEEP_ZONE."""
    if df is None or len(df) < 20:
        return "TRENDING"  # Default fallback

    high, low, close = df["high"], df["low"], df["close"]
    
    # 1. ATR 14 and ATR 100
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr14 = tr.rolling(window=14).mean()
    atr100 = tr.rolling(window=100).mean()
    if len(df) < 100:
        atr100 = tr.rolling(window=min(20, len(df))).mean()
        
    atr_ratio = (atr14 / atr100).iloc[-1]
    if pd.isna(atr_ratio):
        atr_ratio = 1.0

    # 2. Choppiness Index (CHOP) 14
    sum_tr = tr.rolling(window=14).sum()
    highest_high = high.rolling(window=14).max()
    lowest_low = low.rolling(window=14).min()
    range_diff = highest_high - lowest_low
    range_diff = range_diff.replace(0, 1e-9)
    ratio = (sum_tr / range_diff).replace(0, 1e-9)
    chop = (100 * (np.log10(ratio)) / np.log10(14)).iloc[-1]
    if pd.isna(chop) or np.isinf(chop):
        chop = 50.0

    # 3. ADX 14
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_adx = tr.rolling(window=14).mean().replace(0, 1e-9)
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(window=14).mean() / atr_adx)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(window=14).mean() / atr_adx)
    di_sum = plus_di + minus_di
    di_sum_safe = di_sum.replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / di_sum_safe
    adx = dx.rolling(window=14).mean().iloc[-1]
    if pd.isna(adx):
        adx = 20.0

    # 4. Donchian width
    donchian_high = high.rolling(window=20).max()
    donchian_low = low.rolling(window=20).min()
    donchian_width = ((donchian_high - donchian_low) / close).iloc[-1]
    if pd.isna(donchian_width):
        donchian_width = 0.02

    # Check REVERSAL_SWEEP_ZONE: near HTF boundaries and wick sweeps
    if htf_high is not None and htf_low is not None:
        last_price = close.iloc[-1]
        near_edge = (last_price >= htf_high * 0.98) or (last_price <= htf_low * 1.02)
        
        # Check if any of last 3 candles swept outside and closed inside
        recent = df.iloc[-3:]
        swept = False
        for c in recent.itertuples():
            if (c.high > htf_high and c.close < htf_high) or (c.low < htf_low and c.close > htf_low):
                swept = True
                break
        if near_edge and swept:
            return "REVERSAL_SWEEP_ZONE"

    # Check VOLATILITY_COMPRESSION
    if atr_ratio < 0.95 and donchian_width < 0.025:
        return "VOLATILITY_COMPRESSION"

    # Check SIDEWAYS
    sideways_conds = sum([adx < 20.0, chop > 61.8, atr_ratio < 0.95])
    if sideways_conds >= 2:
        return "SIDEWAYS"

    # Default/Trending
    return "TRENDING"


# ---------------------------------------------------------------------------
# Strategy 1 - 15-minute VWAP momentum scalp (fixed RR 1:1.5)
# ---------------------------------------------------------------------------
def vwap_momentum_scalp(symbol: str, df15: pd.DataFrame, df4h: pd.DataFrame = None, regime: str = "TRENDING", asset_class: str = "crypto") -> Optional[Signal]:
    if df15 is None or len(df15) < 30:
        return None
    
    # Sideways market suppression
    if regime == "SIDEWAYS":
        return None

    df = df15.copy()
    df["vwap"] = session_vwap(df)
    df["ema9"] = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)
    df["vol_ma10"] = df["volume"].rolling(10).mean()

    last, prev = df.iloc[-1], df.iloc[-2]
    if pd.isna(last["vol_ma10"]):
        return None
    vol_spike = last["volume"] > last["vol_ma10"]
    crossed_up = prev["ema9"] <= prev["ema21"] and last["ema9"] > last["ema21"]
    crossed_down = prev["ema9"] >= prev["ema21"] and last["ema9"] < last["ema21"]
    price = float(last["close"])

    h4_trend = None
    if df4h is not None and len(df4h) >= 50:
        df4h_copy = df4h.copy()
        df4h_copy["ema50"] = ema(df4h_copy["close"], 50)
        h4_last = df4h_copy.iloc[-1]
        h4_trend = "bullish" if h4_last["close"] > h4_last["ema50"] else "bearish"

    if price > last["vwap"] and crossed_up and vol_spike:
        if h4_trend is not None and h4_trend != "bullish":
            return None
        stop = float(df["low"].iloc[-5:].min())
        if stop >= price:
            return None
        confidence = "High" if h4_trend == "bullish" else "Medium"
        dist = price - stop
        tp = price + 1.5 * dist
        hard_sl = price - 2.0 * dist

        score = 1.0
        if regime == "TRENDING":
            score += 2.0
        if h4_trend == "bullish":
            score += 1.5
        if vol_spike:
            score += 1.0
        multiplier = 1.0 if asset_class == "crypto" else 0.6
        score *= multiplier

        return Signal(
            strategy_name="VWAP Momentum Scalp (15m)",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="15m",
            side="long",
            entry_price=price,
            soft_sl=stop,
            hard_sl=hard_sl,
            tp=tp,
            rr=1.5,
            confidence=confidence,
            regime_tag=regime,
            score=score,
            reason="price>VWAP, 9/21 EMA bull cross on 15m closed candle, volume spike, 4H trend confirmed",
            candle_ts=int(last["ts"])
        )

    if price < last["vwap"] and crossed_down and vol_spike:
        if h4_trend is not None and h4_trend != "bearish":
            return None
        stop = float(df["high"].iloc[-5:].max())
        if stop <= price:
            return None
        confidence = "High" if h4_trend == "bearish" else "Medium"
        dist = stop - price
        tp = price - 1.5 * dist
        hard_sl = price + 2.0 * dist

        score = 1.0
        if regime == "TRENDING":
            score += 2.0
        if h4_trend == "bearish":
            score += 1.5
        if vol_spike:
            score += 1.0
        multiplier = 1.0 if asset_class == "crypto" else 0.6
        score *= multiplier

        return Signal(
            strategy_name="VWAP Momentum Scalp (15m)",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="15m",
            side="short",
            entry_price=price,
            soft_sl=stop,
            hard_sl=hard_sl,
            tp=tp,
            rr=1.5,
            confidence=confidence,
            regime_tag=regime,
            score=score,
            reason="price<VWAP, 9/21 EMA bear cross on 15m closed candle, volume spike, 4H trend confirmed",
            candle_ts=int(last["ts"])
        )
    return None


# ---------------------------------------------------------------------------
# Strategy 2 - 15m/1H liquidity sweep & reversal (fixed RR 1:2.0)
# ---------------------------------------------------------------------------
def _pivots(highs: list, lows: list, n: int = 2):
    """Fractal pivot highs/lows: extreme over n bars on each side."""
    ph, pl = [], []
    for i in range(n, len(highs) - n):
        window_h = highs[i - n: i + n + 1]
        window_l = lows[i - n: i + n + 1]
        if highs[i] == max(window_h):
            ph.append((i, highs[i]))
        if lows[i] == min(window_l):
            pl.append((i, lows[i]))
    return ph, pl


def _bearish_fvg(df: pd.DataFrame, lookback: int = 5):
    """3-candle bearish Fair Value Gap: candle[i-2].low > candle[i].high."""
    start = max(len(df) - lookback, 2)
    for i in range(len(df) - 1, start - 1, -1):
        if df["low"].iloc[i - 2] > df["high"].iloc[i]:
            return float(df["high"].iloc[i]), float(df["low"].iloc[i - 2])
    return None


def _bullish_fvg(df: pd.DataFrame, lookback: int = 5):
    """3-candle bullish Fair Value Gap: candle[i-2].high < candle[i].low."""
    start = max(len(df) - lookback, 2)
    for i in range(len(df) - 1, start - 1, -1):
        if df["high"].iloc[i - 2] < df["low"].iloc[i]:
            return float(df["high"].iloc[i - 2]), float(df["low"].iloc[i])
    return None


def liquidity_sweep_reversal(symbol: str, df1h: pd.DataFrame, df15: pd.DataFrame, regime: str = "TRENDING", asset_class: str = "crypto") -> Optional[Signal]:
    if df1h is None or df15 is None or len(df1h) < 26 or len(df15) < 30:
        return None

    # 1H structural levels over the past 24 hours
    h24 = df1h.iloc[-24:]
    swing_high = float(h24["high"].max())
    swing_low = float(h24["low"].min())

    recent = df15.iloc[-3:]
    last = df15.iloc[-1]
    price = float(last["close"])
    ph, pl = _pivots(df15["high"].tolist(), df15["low"].tolist(), n=2)

    # SHORT: sweep above 1H high + wick back inside + MSS down + bearish FVG
    swept_high = any(c.high > swing_high and c.close < swing_high for c in recent.itertuples())
    if swept_high and pl:
        minor_low = pl[-1][1]
        if price < minor_low and _bearish_fvg(df15):
            stop = float(recent["high"].max())
            if stop > price:
                dist = stop - price
                tp = price - 2.0 * dist
                hard_sl = price + 2.0 * dist

                score = 1.0
                if regime == "REVERSAL_SWEEP_ZONE":
                    score += 2.0
                vol_sma = df15["volume"].rolling(20).mean().iloc[-1]
                if not pd.isna(vol_sma) and last["volume"] > vol_sma:
                    score += 1.0
                score += 0.5
                multiplier = 1.0 if asset_class == "crypto" else 0.6
                score *= multiplier

                return Signal(
                    strategy_name="Liquidity Sweep & Reversal (15m/1H)",
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe="15m",
                    side="short",
                    entry_price=price,
                    soft_sl=stop,
                    hard_sl=hard_sl,
                    tp=tp,
                    rr=2.0,
                    confidence="High",
                    regime_tag=regime,
                    score=score,
                    reason=f"swept 1H high {swing_high:.6g}, MSS below {minor_low:.6g}, bearish FVG entry",
                    candle_ts=int(last["ts"])
                )

    # LONG: sweep below 1H low + wick back inside + MSS up + bullish FVG
    swept_low = any(c.low < swing_low and c.close > swing_low for c in recent.itertuples())
    if swept_low and ph:
        minor_high = ph[-1][1]
        if price > minor_high and _bullish_fvg(df15):
            stop = float(recent["low"].min())
            if stop < price:
                dist = price - stop
                tp = price + 2.0 * dist
                hard_sl = price - 2.0 * dist

                score = 1.0
                if regime == "REVERSAL_SWEEP_ZONE":
                    score += 2.0
                vol_sma = df15["volume"].rolling(20).mean().iloc[-1]
                if not pd.isna(vol_sma) and last["volume"] > vol_sma:
                    score += 1.0
                score += 0.5
                multiplier = 1.0 if asset_class == "crypto" else 0.6
                score *= multiplier

                return Signal(
                    strategy_name="Liquidity Sweep & Reversal (15m/1H)",
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe="15m",
                    side="long",
                    entry_price=price,
                    soft_sl=stop,
                    hard_sl=hard_sl,
                    tp=tp,
                    rr=2.0,
                    confidence="High",
                    regime_tag=regime,
                    score=score,
                    reason=f"swept 1H low {swing_low:.6g}, MSS above {minor_high:.6g}, bullish FVG entry",
                    candle_ts=int(last["ts"])
                )
    return None


def liquidity_sweep_reversal_1h_4h(symbol: str, df4h: pd.DataFrame, df1h: pd.DataFrame, regime: str = "TRENDING", asset_class: str = "crypto") -> Optional[Signal]:
    if df4h is None or df1h is None or len(df4h) < 8 or len(df1h) < 30:
        return None

    # 4H structural levels over the past 24 hours (last 6 candles of 4H)
    h24 = df4h.iloc[-6:]
    swing_high = float(h24["high"].max())
    swing_low = float(h24["low"].min())

    recent = df1h.iloc[-3:]
    last = df1h.iloc[-1]
    price = float(last["close"])
    ph, pl = _pivots(df1h["high"].tolist(), df1h["low"].tolist(), n=2)

    # SHORT: sweep above 4H high + wick back inside + MSS down + bearish FVG on 1H
    swept_high = any(c.high > swing_high and c.close < swing_high for c in recent.itertuples())
    if swept_high and pl:
        minor_low = pl[-1][1]
        if price < minor_low and _bearish_fvg(df1h):
            stop = float(recent["high"].max())
            if stop > price:
                dist = stop - price
                tp = price - 2.0 * dist
                hard_sl = price + 2.0 * dist

                score = 1.0
                if regime == "REVERSAL_SWEEP_ZONE":
                    score += 2.0
                vol_sma = df1h["volume"].rolling(20).mean().iloc[-1]
                if not pd.isna(vol_sma) and last["volume"] > vol_sma:
                    score += 1.0
                score += 0.5
                multiplier = 1.0 if asset_class == "crypto" else 0.6
                score *= multiplier

                return Signal(
                    strategy_name="Liquidity Sweep & Reversal (1H/4H)",
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe="1h",
                    side="short",
                    entry_price=price,
                    soft_sl=stop,
                    hard_sl=hard_sl,
                    tp=tp,
                    rr=2.0,
                    confidence="High",
                    regime_tag=regime,
                    score=score,
                    reason=f"swept 4H high {swing_high:.6g}, MSS below {minor_low:.6g}, bearish FVG entry on 1H",
                    candle_ts=int(last["ts"])
                )

    # LONG: sweep below 4H low + wick back inside + MSS up + bullish FVG on 1H
    swept_low = any(c.low < swing_low and c.close > swing_low for c in recent.itertuples())
    if swept_low and ph:
        minor_high = ph[-1][1]
        if price > minor_high and _bullish_fvg(df1h):
            stop = float(recent["low"].min())
            if stop < price:
                dist = price - stop
                tp = price + 2.0 * dist
                hard_sl = price - 2.0 * dist

                score = 1.0
                if regime == "REVERSAL_SWEEP_ZONE":
                    score += 2.0
                vol_sma = df1h["volume"].rolling(20).mean().iloc[-1]
                if not pd.isna(vol_sma) and last["volume"] > vol_sma:
                    score += 1.0
                score += 0.5
                multiplier = 1.0 if asset_class == "crypto" else 0.6
                score *= multiplier

                return Signal(
                    strategy_name="Liquidity Sweep & Reversal (1H/4H)",
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe="1h",
                    side="long",
                    entry_price=price,
                    soft_sl=stop,
                    hard_sl=hard_sl,
                    tp=tp,
                    rr=2.0,
                    confidence="High",
                    regime_tag=regime,
                    score=score,
                    reason=f"swept 4H low {swing_low:.6g}, MSS above {minor_high:.6g}, bullish FVG entry on 1H",
                    candle_ts=int(last["ts"])
                )
    return None


# ---------------------------------------------------------------------------
# Strategy 3 - ATR Volume Breakout (fixed RR 1:2.0)
# ---------------------------------------------------------------------------
def atr_volume_breakout(symbol: str, df1h: pd.DataFrame, regime: str = "TRENDING", asset_class: str = "crypto") -> Optional[Signal]:
    if df1h is None or len(df1h) < 30:
        return None

    # Don't trade breakout in sideways markets
    if regime == "SIDEWAYS":
        return None

    df = df1h.copy()
    high, low, close, volume = df["high"], df["low"], df["close"], df["volume"]

    # TR, ATR 14, ATR 100
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    df["atr_short"] = tr.rolling(window=14).mean()
    df["atr_long"] = tr.rolling(window=100).mean()
    if len(df) < 100:
        df["atr_long"] = tr.rolling(window=min(20, len(df))).mean()
    df["atr_ratio"] = df["atr_short"] / df["atr_long"]

    # Compression criteria
    recent_compression = df["atr_ratio"].iloc[-5:].min() < 0.95 or regime == "VOLATILITY_COMPRESSION"

    # Donchian channel excluding last closed candle
    prev_donchian_high = high.iloc[-21:-1].max()
    prev_donchian_low = low.iloc[-21:-1].min()

    # Volume SMA 20
    df["vol_sma20"] = volume.rolling(window=20).mean()

    # ADX 14
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_adx = tr.rolling(window=14).mean().replace(0, 1e-9)
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(window=14).mean() / atr_adx)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(window=14).mean() / atr_adx)
    di_sum = plus_di + minus_di
    di_sum_safe = di_sum.replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / di_sum_safe
    df["adx"] = dx.rolling(window=14).mean()

    df["ema50"] = ema(close, 50)

    last, prev = df.iloc[-1], df.iloc[-2]
    if pd.isna(last["vol_sma20"]) or pd.isna(last["adx"]):
        return None

    price = float(last["close"])
    vol_spike = last["volume"] > 1.25 * last["vol_sma20"]
    adx_rising = last["adx"] > prev["adx"]
    adx_high = last["adx"] > 25.0
    adx_ok = adx_rising or adx_high

    if recent_compression and price > prev_donchian_high and vol_spike and adx_ok:
        if not pd.isna(last["ema50"]) and price < last["ema50"]:
            return None
        stop = float(prev_donchian_low)
        if price - stop > price * 0.1:
            stop = float(df["low"].iloc[-5:].min())
        if stop >= price:
            stop = price * 0.99
            
        dist = price - stop
        tp = price + 2.0 * dist
        hard_sl = price - 2.0 * dist
        confidence = "High" if adx_rising and price > last["ema50"] else "Medium"

        score = 1.0
        if regime in ["VOLATILITY_COMPRESSION", "TRENDING"]:
            score += 2.0
        if price > last["ema50"]:
            score += 1.5
        if vol_spike:
            score += 1.0
        score += 0.5
        multiplier = 1.0 if asset_class == "crypto" else 0.6
        score *= multiplier

        return Signal(
            strategy_name="ATR Volume Breakout (1H)",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="1h",
            side="long",
            entry_price=price,
            soft_sl=stop,
            hard_sl=hard_sl,
            tp=tp,
            rr=2.0,
            confidence=confidence,
            regime_tag=regime,
            score=score,
            reason=f"compression breakout above Donchian high {prev_donchian_high:.6g} on volume spike",
            candle_ts=int(last["ts"])
        )

    if recent_compression and price < prev_donchian_low and vol_spike and adx_ok:
        if not pd.isna(last["ema50"]) and price > last["ema50"]:
            return None
        stop = float(prev_donchian_high)
        if stop - price > price * 0.1:
            stop = float(df["high"].iloc[-5:].max())
        if stop <= price:
            stop = price * 1.01
            
        dist = stop - price
        tp = price - 2.0 * dist
        hard_sl = price + 2.0 * dist
        confidence = "High" if adx_rising and price < last["ema50"] else "Medium"

        score = 1.0
        if regime in ["VOLATILITY_COMPRESSION", "TRENDING"]:
            score += 2.0
        if price < last["ema50"]:
            score += 1.5
        if vol_spike:
            score += 1.0
        score += 0.5
        multiplier = 1.0 if asset_class == "crypto" else 0.6
        score *= multiplier

        return Signal(
            strategy_name="ATR Volume Breakout (1H)",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="1h",
            side="short",
            entry_price=price,
            soft_sl=stop,
            hard_sl=hard_sl,
            tp=tp,
            rr=2.0,
            confidence=confidence,
            regime_tag=regime,
            score=score,
            reason=f"compression breakdown below Donchian low {prev_donchian_low:.6g} on volume spike",
            candle_ts=int(last["ts"])
        )
    return None


# ---------------------------------------------------------------------------
# Signal Routing & Priority Ranking
# ---------------------------------------------------------------------------
def get_best_signal(symbol: str, frames: dict[str, pd.DataFrame], asset_class: str) -> Optional[Signal]:
    if "15m" not in frames or "1h" not in frames or "4h" not in frames:
        return None

    df15 = frames["15m"]
    df1h = frames["1h"]
    df4h = frames["4h"]

    h24 = df1h.iloc[-24:] if len(df1h) >= 24 else df1h
    swing_high = float(h24["high"].max()) if len(h24) > 0 else None
    swing_low = float(h24["low"].min()) if len(h24) > 0 else None

    # Determine regime on 15m (which is the execution timeframe for VWAP and Sweeps)
    regime = classify_regime(symbol, df15, swing_high, swing_low)

    signals = []

    # 1. Evaluate Liquidity Sweep Reversal (1H/4H)
    sig_sweep_htf = liquidity_sweep_reversal_1h_4h(symbol, df4h, df1h, regime=regime, asset_class=asset_class)
    if sig_sweep_htf:
        signals.append(sig_sweep_htf)

    # 2. Evaluate Liquidity Sweep Reversal (15m/1H)
    sig_sweep_ltf = liquidity_sweep_reversal(symbol, df1h, df15, regime=regime, asset_class=asset_class)
    if sig_sweep_ltf:
        signals.append(sig_sweep_ltf)

    # 3. Evaluate ATR Volume Breakout (1H)
    sig_breakout = atr_volume_breakout(symbol, df1h, regime=regime, asset_class=asset_class)
    if sig_breakout:
        signals.append(sig_breakout)

    # 4. Evaluate VWAP Momentum Scalp (15m)
    sig_vwap = vwap_momentum_scalp(symbol, df15, df4h, regime=regime, asset_class=asset_class)
    if sig_vwap:
        signals.append(sig_vwap)

    if not signals:
        return None

    # Ranking logic
    def get_priority(sig: Signal) -> int:
        if "Liquidity Sweep" in sig.strategy_name:
            return 4 if sig.confidence == "High" else 1
        if "ATR Volume Breakout" in sig.strategy_name:
            return 3 if sig.confidence == "High" else 1
        if "VWAP Momentum" in sig.strategy_name:
            return 2 if sig.confidence == "High" else 1
        return 1

    signals.sort(key=lambda s: (get_priority(s), s.score), reverse=True)
    return signals[0]


class MarketStateFilter:
    """
    Production-grade market state classifier and breakout tracking system.
    Wraps around an existing EMA strategy to suppress whipsaws and delay entries.
    """
    def __init__(self, chop_period: int = 14, adx_period: int = 14, atr_period: int = 14):
        self.chop_period = chop_period
        self.adx_period = adx_period
        self.atr_period = atr_period
        self.states = {}

    def get_state(self, symbol: str) -> dict:
        if symbol not in self.states:
            self.states[symbol] = {
                "in_consolidation": False,
                "breakout_watch": False,
                "watch_direction": None,      # "long" | "short"
                "resistance": 0.0,
                "support": 0.0,
                "candle_ts": None
            }
        return self.states[symbol]

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        high, low, close, volume = df["high"], df["low"], df["close"], df["volume"]
        
        # --- 1. Average True Range (ATR) & ATR Ratio ---
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        df["atr_short"] = tr.rolling(window=self.atr_period).mean()
        df["atr_long"] = tr.rolling(window=100).mean()
        df["atr_ratio"] = df["atr_short"] / df["atr_long"]
        
        # --- 2. Choppiness Index (CHOP) ---
        sum_tr = tr.rolling(window=self.chop_period).sum()
        highest_high = high.rolling(window=self.chop_period).max()
        lowest_low = low.rolling(window=self.chop_period).min()
        range_diff = highest_high - lowest_low
        range_diff = range_diff.replace(0, 1e-9)
        ratio = (sum_tr / range_diff).replace(0, 1e-9)
        df["chop"] = 100 * (np.log10(ratio)) / np.log10(self.chop_period)
        
        # --- 3. ADX (Average Directional Index) ---
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        atr_adx = tr.rolling(window=self.adx_period).mean().replace(0, 1e-9)
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(window=self.adx_period).mean() / atr_adx)
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(window=self.adx_period).mean() / atr_adx)
        di_sum = plus_di + minus_di
        di_sum_safe = di_sum.replace(0, 1e-9)
        dx = 100 * (plus_di - minus_di).abs() / di_sum_safe
        df["adx"] = dx.rolling(window=self.adx_period).mean()
        
        # --- 4. Volume MA ---
        df["vol_ma20"] = volume.rolling(window=20).mean()
        
        # --- 5. Donchian Channels ---
        df["donchian_high"] = high.rolling(window=20).max()
        df["donchian_low"] = low.rolling(window=20).min()
        return df

    def evaluate_market_state(self, symbol: str, df: pd.DataFrame) -> tuple[bool, float, float]:
        if len(df) < 100:
            return False, 0.0, 0.0
        last = df.iloc[-1]
        adx_val = last["adx"] if not pd.isna(last["adx"]) else 25.0
        chop_val = last["chop"] if not pd.isna(last["chop"]) else 50.0
        atr_ratio_val = last["atr_ratio"] if not pd.isna(last["atr_ratio"]) else 1.0
        
        low_trend = adx_val < 20.0
        high_chop = chop_val > 61.8
        compressed_vol = atr_ratio_val < 0.95
        is_sideways = sum([low_trend, high_chop, compressed_vol]) >= 2
        
        resistance = float(last["donchian_high"]) if not pd.isna(last["donchian_high"]) else float(last["close"])
        support = float(last["donchian_low"]) if not pd.isna(last["donchian_low"]) else float(last["close"])
        return is_sideways, resistance, support

    def process_signal(self, symbol: str, df: pd.DataFrame, ema_signal: Optional[dict]) -> Optional[dict]:
        state = self.get_state(symbol)
        df_indicators = self.calculate_indicators(df)
        last = df_indicators.iloc[-1]
        close_price = float(last["close"])
        volume = float(last["volume"])
        vol_ma = float(last["vol_ma20"])
        
        is_sideways, resistance, support = self.evaluate_market_state(symbol, df_indicators)
        state["in_consolidation"] = is_sideways
        
        if state["breakout_watch"]:
            vol_confirmed = True
            if not pd.isna(vol_ma) and vol_ma > 0:
                vol_confirmed = volume > 1.25 * vol_ma
            
            if state["watch_direction"] == "long":
                if close_price > state["resistance"] and vol_confirmed:
                    ret_val = {
                        "side": "long",
                        "entry": close_price,
                        "stop_loss": state["support"],
                        "reason": f"Sideways range breakout long (resistance: {state['resistance']:.6g}) on high volume."
                    }
                    self.reset_watch(symbol)
                    return ret_val
            elif state["watch_direction"] == "short":
                if close_price < state["support"] and vol_confirmed:
                    ret_val = {
                        "side": "short",
                        "entry": close_price,
                        "stop_loss": state["resistance"],
                        "reason": f"Sideways range breakdown short (support: {state['support']:.6g}) on high volume."
                    }
                    self.reset_watch(symbol)
                    return ret_val
            
            if ema_signal and ema_signal["side"] != state["watch_direction"]:
                self.reset_watch(symbol)
                
        if ema_signal:
            if is_sideways:
                state["breakout_watch"] = True
                state["watch_direction"] = ema_signal["side"]
                state["resistance"] = resistance
                state["support"] = support
                state["candle_ts"] = ema_signal.get("candle_ts")
                return None
            else:
                return ema_signal
        return None

    def reset_watch(self, symbol: str):
        state = self.get_state(symbol)
        state["breakout_watch"] = False
        state["watch_direction"] = None
        state["resistance"] = 0.0
        state["support"] = 0.0
        state["candle_ts"] = None


# ═══════════════════════════════════════════════════════════════════════════════
#  5 NEW COST-AWARE STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

SLIPPAGE_MAP = {
    'BTC':    0.0002, 'ETH': 0.0002,
    'AVAX':   0.0005, 'DOT': 0.0005, 'XRP': 0.0005, 'DOGE': 0.0005, 'RENDER': 0.0005,
    'WLD':    0.0008, 'ZEC': 0.0008, 'AAVE': 0.0008
}

TAKER_FEE = 0.00045   # 0.045%
MAKER_FEE = 0.00015   # 0.015%
FUNDING_RATE = 0.0001 # 0.01% per hour

def volatility_expansion_momentum(symbol: str, df: pd.DataFrame, asset_class: str = "crypto", mode: Optional[str] = None) -> Optional[Signal]:
    """1. Volatility Expansion Momentum strategy with built-in Cost Gate."""
    if mode not in ['VE_1_BB_SQUEEZE', 'VE_2_KELTNER_SQUEEZE', 'VE_3_ATR_EXPANSION']:
        raise ValueError(f"Volatility Expansion strategy requires mode to be 'VE_1_BB_SQUEEZE', 'VE_2_KELTNER_SQUEEZE', or 'VE_3_ATR_EXPANSION'. Got: {mode}")

    if df is None or len(df) < 100:
        return None
        
    high, low, close = df["high"], df["low"], df["close"]
    
    # Calculate ATR 14
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=14).mean()
    last_atr = float(atr.iloc[-1])
    
    last = df.iloc[-1]
    last_close = float(last["close"])
    timeframe = "15m"  # default execution tf
    
    long_sig = False
    short_sig = False
    
    if mode == 'VE_1_BB_SQUEEZE':
        mid = close.rolling(20).mean()
        std = close.rolling(20).std()
        upper = mid + 2 * std
        lower = mid - 2 * std
        bb_width = (upper - lower) / mid
        bb_width_p20 = bb_width.rolling(100).quantile(0.20)
        
        last_squeeze = float(bb_width.iloc[-1]) < float(bb_width_p20.iloc[-1])
        long_sig = last_squeeze and (last_close > float(upper.iloc[-1]))
        short_sig = last_squeeze and (last_close < float(lower.iloc[-1]))

    elif mode == 'VE_2_KELTNER_SQUEEZE':
        mid_bb = close.rolling(20).mean()
        std_bb = close.rolling(20).std()
        upper_bb = mid_bb + 2 * std_bb
        lower_bb = mid_bb - 2 * std_bb

        atr20 = tr.rolling(20).mean()
        mid_kc = close.ewm(span=20, adjust=False).mean()
        upper_kc = mid_kc + 1.5 * atr20
        lower_kc = mid_kc - 1.5 * atr20

        last_squeeze = (float(upper_bb.iloc[-1]) < float(upper_kc.iloc[-1])) and (float(lower_bb.iloc[-1]) > float(lower_kc.iloc[-1]))
        long_sig = last_squeeze and (last_close > float(upper_bb.iloc[-1]))
        short_sig = last_squeeze and (last_close < float(lower_bb.iloc[-1]))

    elif mode == 'VE_3_ATR_EXPANSION':
        atr14_mean = atr.rolling(20).mean()
        atr_expanded = last_atr > 1.5 * float(atr14_mean.iloc[-1])
        prev_high = high.shift(1).rolling(20).max()
        prev_low = low.shift(1).rolling(20).min()

        long_sig = atr_expanded and (last_close > float(prev_high.iloc[-1]))
        short_sig = atr_expanded and (last_close < float(prev_low.iloc[-1]))

    if long_sig:
        stop = last_close - 1.5 * last_atr
        tp = last_close + 3.0 * last_atr
        return Signal(
            strategy_name="Volatility Expansion Momentum",
            symbol=symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            side="long",
            entry_price=last_close,
            soft_sl=stop,
            tp=tp,
            rr=2.0,
            confidence="High",
            regime_tag="VOLATILITY_EXPANSION",
            score=1.5,
            reason=f"Volatility Expansion Mode {mode} Long: Close {last_close:.6g}, ATR: {last_atr:.4g}",
            candle_ts=int(last["ts"])
        )
        
    if short_sig:
        stop = last_close + 1.5 * last_atr
        tp = last_close - 3.0 * last_atr
        return Signal(
            strategy_name="Volatility Expansion Momentum",
            symbol=symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            side="short",
            entry_price=last_close,
            soft_sl=stop,
            tp=tp,
            rr=2.0,
            confidence="High",
            regime_tag="VOLATILITY_EXPANSION",
            score=1.5,
            reason=f"Volatility Expansion Mode {mode} Short: Close {last_close:.6g}, ATR: {last_atr:.4g}",
            candle_ts=int(last["ts"])
        )
        
    return None

def session_open_range_breakout(symbol: str, df: pd.DataFrame, asset_class: str = "crypto") -> Optional[Signal]:
    """2. Session Open Range Breakout strategy with session-trade limits and range width validation."""
    if df is None or len(df) < 50:
        return None
        
    last_candle = df.iloc[-1]
    last_ts = pd.to_datetime(last_candle['ts'], unit='ms', utc=True)
    
    # Identify session (00:00 or 12:00 UTC)
    sess_hour = 0 if last_ts.hour < 12 else 12
    sess_start_dt = last_ts.replace(hour=sess_hour, minute=0, second=0, microsecond=0)
    
    # Get candles for current session
    df_ts = pd.to_datetime(df['ts'], unit='ms', utc=True)
    session_mask = (df_ts >= sess_start_dt) & (df_ts <= last_ts)
    df_sess = df[session_mask]
    
    if len(df_sess) == 0:
        return None
        
    # Range definition is the first hour
    range_end_dt = sess_start_dt + pd.Timedelta(hours=1)
    df_range = df_sess[pd.to_datetime(df_sess['ts'], unit='ms', utc=True) < range_end_dt]
    
    if df_range.empty:
        return None
        
    range_high = float(df_range['high'].max())
    range_low = float(df_range['low'].min())
    
    # Sane range width check (between 0.2% and 3.0%)
    range_width_pct = (range_high - range_low) / range_low
    if range_width_pct < 0.002 or range_width_pct > 0.03:
        return None
        
    current_time = last_ts
    if current_time < range_end_dt:
        return None
        
    # Check if a breakout already occurred on previous candles in this session
    df_trade_phase_prev = df_sess[
        (pd.to_datetime(df_sess['ts'], unit='ms', utc=True) >= range_end_dt) &
        (pd.to_datetime(df_sess['ts'], unit='ms', utc=True) < current_time)
    ]
    
    already_traded = False
    for row in df_trade_phase_prev.itertuples():
        if row.close > range_high or row.close < range_low:
            already_traded = True
            break
            
    if already_traded:
        return None
        
    close_val = float(last_candle['close'])
    
    # Calculate ATR 14
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_val = float(tr.rolling(14).mean().iloc[-1])
    
    if close_val > range_high:
        stop = range_low
        stop = max(stop, close_val - 2.0 * atr_val)
        stop = min(stop, close_val - 0.5 * atr_val)
        tp = close_val + 2.0 * (close_val - stop)
        return Signal(
            strategy_name="Session Open Range Breakout",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="15m",
            side="long",
            entry_price=close_val,
            soft_sl=stop,
            tp=tp,
            rr=2.0,
            confidence="Medium",
            regime_tag="TRENDING",
            score=1.2,
            reason=f"Session range breakout above {range_high:.6g}",
            candle_ts=int(last_candle["ts"])
        )
        
    if close_val < range_low:
        stop = range_high
        stop = min(stop, close_val + 2.0 * atr_val)
        stop = max(stop, close_val + 0.5 * atr_val)
        tp = close_val - 2.0 * (stop - close_val)
        return Signal(
            strategy_name="Session Open Range Breakout",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="15m",
            side="short",
            entry_price=close_val,
            soft_sl=stop,
            tp=tp,
            rr=2.0,
            confidence="Medium",
            regime_tag="TRENDING",
            score=1.2,
            reason=f"Session range breakdown below {range_low:.6g}",
            candle_ts=int(last_candle["ts"])
        )
        
    return None

def mean_reversion_statistical_extreme(symbol: str, df: pd.DataFrame, asset_class: str = "crypto", mode: Optional[str] = None) -> Optional[Signal]:
    """3. Mean Reversion Statistical Extreme strategy with BB breakout and RSI divergence."""
    if mode not in ['RSI', 'BB', 'RSI_BB']:
        raise ValueError(f"Mean Reversion strategy requires mode to be 'RSI', 'BB', or 'RSI_BB'. Got: {mode}")

    if df is None or len(df) < 30:
        return None
        
    close, high, low = df["close"], df["high"], df["low"]
    
    # Bollinger Bands (20, 2)
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    
    # RSI 14
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean().replace(0, 1e-9)
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    last = df.iloc[-1]
    last_close = float(last["close"])
    last_rsi = float(rsi.iloc[-1])
    last_upper = float(upper.iloc[-1])
    last_lower = float(lower.iloc[-1])
    
    # ATR 14
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    
    # Calculate ADX 14 for RSI_BB mode
    last_adx = 0.0
    if mode == 'RSI_BB':
        up_move = high.diff()
        down_move = -low.diff()
        pdm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        mdm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        atr_adx = tr.rolling(window=14).mean().replace(0, 1e-9)
        plus_di = 100 * (pd.Series(pdm, index=df.index).rolling(window=14).mean() / atr_adx)
        minus_di = 100 * (pd.Series(mdm, index=df.index).rolling(window=14).mean() / atr_adx)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
        adx = dx.rolling(window=14).mean()
        last_adx = float(adx.iloc[-1])
    
    # Long Entry condition
    long_entry = False
    if mode == 'RSI':
        long_entry = last_rsi < 25
    elif mode == 'BB':
        long_entry = last_close < last_lower
    elif mode == 'RSI_BB':
        long_entry = (last_rsi < 30) and (last_close < last_lower) and (last_adx < 20)

    if long_entry:
        stop = last_close - 1.5 * atr
        tp = last_close + 1.5 * (last_close - stop)
        return Signal(
            strategy_name="Mean Reversion Statistical Extreme",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="15m",
            side="long",
            entry_price=last_close,
            soft_sl=stop,
            tp=tp,
            rr=1.5,
            confidence="Medium",
            regime_tag="REVERSAL_SWEEP_ZONE",
            score=1.3,
            reason=f"Mode {mode} Long: Close {last_close:.6g}, RSI: {last_rsi:.2f}, Lower BB: {last_lower:.6g}, ADX: {last_adx:.2f}",
            candle_ts=int(last["ts"])
        )
        
    # Short Entry condition
    short_entry = False
    if mode == 'RSI':
        short_entry = last_rsi > 75
    elif mode == 'BB':
        short_entry = last_close > last_upper
    elif mode == 'RSI_BB':
        short_entry = (last_rsi > 70) and (last_close > last_upper) and (last_adx < 20)

    if short_entry:
        stop = last_close + 1.5 * atr
        tp = last_close - 1.5 * (stop - last_close)
        return Signal(
            strategy_name="Mean Reversion Statistical Extreme",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="15m",
            side="short",
            entry_price=last_close,
            soft_sl=stop,
            tp=tp,
            rr=1.5,
            confidence="Medium",
            regime_tag="REVERSAL_SWEEP_ZONE",
            score=1.3,
            reason=f"Mode {mode} Short: Close {last_close:.6g}, RSI: {last_rsi:.2f}, Upper BB: {last_upper:.6g}",
            candle_ts=int(last["ts"])
        )
        
    return None

def funding_rate_contrarian(symbol: str, df: pd.DataFrame, funding_df: pd.DataFrame, asset_class: str = "crypto") -> Optional[Signal]:
    """4. Funding Rate Contrarian strategy trading extreme funding deciles to collect carry."""
    if df is None or len(df) < 30 or funding_df is None or funding_df.empty:
        return None
        
    last_candle = df.iloc[-1]
    last_ts = pd.to_datetime(last_candle['ts'], unit='ms', utc=True)
    
    # Find matching funding rate
    mask = (funding_df['timestamp'] <= last_ts)
    if not mask.any():
        return None
        
    recent_funding = funding_df[mask].iloc[-1]
    current_funding_rate = float(recent_funding['funding_rate'])
    
    # Calculate deciles over history prior to this candle
    past_funding = funding_df[funding_df['timestamp'] <= last_ts]['funding_rate']
    if len(past_funding) < 100:
        return None
        
    p10 = past_funding.quantile(0.10)
    p90 = past_funding.quantile(0.90)
    
    last_close = float(last_candle['close'])
    
    # ATR 14
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    
    if current_funding_rate <= p10:
        # Long entry (funding highly negative)
        stop = last_close - 2.0 * atr
        tp = last_close + 3.0 * atr
        return Signal(
            strategy_name="Funding Rate Contrarian",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="1h",
            side="long",
            entry_price=last_close,
            soft_sl=stop,
            tp=tp,
            rr=1.5,
            confidence="High",
            regime_tag="TRENDING",
            score=1.5,
            reason=f"Funding rate ({current_funding_rate:.6f}) <= bottom decile ({p10:.6f})",
            candle_ts=int(last_candle["ts"])
        )
        
    if current_funding_rate >= p90:
        # Short entry (funding highly positive)
        stop = last_close + 2.0 * atr
        tp = last_close - 3.0 * atr
        return Signal(
            strategy_name="Funding Rate Contrarian",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="1h",
            side="short",
            entry_price=last_close,
            soft_sl=stop,
            tp=tp,
            rr=1.5,
            confidence="High",
            regime_tag="TRENDING",
            score=1.5,
            reason=f"Funding rate ({current_funding_rate:.6f}) >= top decile ({p90:.6f})",
            candle_ts=int(last_candle["ts"])
        )
        
    return None

def htf_trend_ltf_pullback(symbol: str, df_ltf: pd.DataFrame, df_htf: pd.DataFrame, asset_class: str = "crypto") -> Optional[Signal]:
    """5. Higher Timeframe Trend, Lower Timeframe Pullback strategy."""
    if df_ltf is None or len(df_ltf) < 30 or df_htf is None or len(df_htf) < 50:
        return None
        
    close_htf = df_htf["close"]
    ema50_htf = ema(close_htf, 50)
    
    # ADX 14 on HTF
    high_htf, low_htf = df_htf["high"], df_htf["low"]
    tr1 = high_htf - low_htf
    tr2 = (high_htf - close_htf.shift(1)).abs()
    tr3 = (low_htf - close_htf.shift(1)).abs()
    tr_htf = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    up_htf = high_htf.diff()
    dn_htf = -low_htf.diff()
    pdm_htf = np.where((up_htf > dn_htf) & (up_htf > 0), up_htf, 0.0)
    mdm_htf = np.where((dn_htf > up_htf) & (dn_htf > 0), dn_htf, 0.0)
    atr_adx = tr_htf.rolling(window=14).mean().replace(0, 1e-9)
    pdi_htf = 100 * pd.Series(pdm_htf).rolling(window=14).mean() / atr_adx
    mdi_htf = 100 * pd.Series(mdm_htf).rolling(window=14).mean() / atr_adx
    dx_htf = 100 * (pdi_htf - mdi_htf).abs() / (pdi_htf + mdi_htf).replace(0, 1e-9)
    adx_htf = dx_htf.rolling(window=14).mean()
    
    last_candle_ltf = df_ltf.iloc[-1]
    last_ltf_ts = pd.to_datetime(last_candle_ltf['ts'], unit='ms', utc=True)
    
    # Find aligned HTF candle
    df_htf_ts = pd.to_datetime(df_htf['ts'], unit='ms', utc=True)
    mask = (df_htf_ts <= last_ltf_ts)
    if not mask.any():
        return None
        
    aligned_htf_row_idx = df_htf[mask].index[-1]
    
    last_ema50 = ema50_htf.loc[aligned_htf_row_idx]
    prev_ema50 = ema50_htf.loc[aligned_htf_row_idx - 1] if aligned_htf_row_idx > 0 else last_ema50
    last_adx = adx_htf.loc[aligned_htf_row_idx]
    
    htf_bullish = (last_ema50 > prev_ema50) and (last_adx > 20.0)
    htf_bearish = (last_ema50 < prev_ema50) and (last_adx > 20.0)
    
    if not (htf_bullish or htf_bearish):
        return None
        
    close_ltf = df_ltf["close"]
    ema20_ltf = ema(close_ltf, 20)
    
    last_close_ltf = float(last_candle_ltf["close"])
    last_ema20_ltf = float(ema20_ltf.iloc[-1])
    prev_close_ltf = float(df_ltf["close"].iloc[-2])
    prev_ema20_ltf = float(ema20_ltf.iloc[-2])
    
    long_trigger = (prev_close_ltf <= prev_ema20_ltf) and (last_close_ltf > last_ema20_ltf)
    short_trigger = (prev_close_ltf >= prev_ema20_ltf) and (last_close_ltf < last_ema20_ltf)
    
    high_ltf, low_ltf = df_ltf["high"], df_ltf["low"]
    tr1_l = high_ltf - low_ltf
    tr2_l = (high_ltf - close_ltf.shift(1)).abs()
    tr3_l = (low_ltf - close_ltf.shift(1)).abs()
    tr_ltf = pd.concat([tr1_l, tr2_l, tr3_l], axis=1).max(axis=1)
    atr_ltf = float(tr_ltf.rolling(14).mean().iloc[-1])
    
    if htf_bullish and long_trigger:
        stop = last_close_ltf - 1.5 * atr_ltf
        tp = last_close_ltf + 3.0 * atr_ltf
        return Signal(
            strategy_name="HTF Trend LTF Pullback",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="15m",
            side="long",
            entry_price=last_close_ltf,
            soft_sl=stop,
            tp=tp,
            rr=2.0,
            confidence="High",
            regime_tag="TRENDING",
            score=1.5,
            reason=f"HTF Bullish Trend (ADX: {last_adx:.2f}) + LTF Pullback EMA20",
            candle_ts=int(last_candle_ltf["ts"])
        )
        
    if htf_bearish and short_trigger:
        stop = last_close_ltf + 1.5 * atr_ltf
        tp = last_close_ltf - 3.0 * atr_ltf
        return Signal(
            strategy_name="HTF Trend LTF Pullback",
            symbol=symbol,
            asset_class=asset_class,
            timeframe="15m",
            side="short",
            entry_price=last_close_ltf,
            soft_sl=stop,
            tp=tp,
            rr=2.0,
            confidence="High",
            regime_tag="TRENDING",
            score=1.5,
            reason=f"HTF Bearish Trend (ADX: {last_adx:.2f}) + LTF Pullback EMA20",
            candle_ts=int(last_candle_ltf["ts"])
        )
        
    return None
