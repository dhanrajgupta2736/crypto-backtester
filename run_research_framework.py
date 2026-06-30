import os
import sys
import concurrent.futures
import numpy as np
import pandas as pd
import vectorbt as vbt
from vectorbt.portfolio.enums import OppositeEntryMode, StopExitMode, StopExitPrice
from tqdm import tqdm

# Force UTF-8 output so box-drawing / special chars don't crash on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
DATA_DIR    = "data"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

# Sizing & Costs
INITIAL_BALANCE = 1000.0
RISK_PER_TRADE  = 100.0
LEVERAGE        = 5.0
FEE_RATE        = 0.0005   # 0.05 %
SLIPPAGE_RATE   = 0.0002   # 0.02 %

TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]
STRATEGIES = ["Volatility_Expansion", "Session_ORB", "Funding_Contrarian", "HTF_Pullback"]
RR_VALUES  = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]

def get_slippage_rate(symbol):
    sym = symbol.upper()
    if sym in ['BTC', 'ETH']:
        return 0.0002
    elif sym in ['AVAX', 'DOT', 'XRP', 'DOGE', 'RENDER']:
        return 0.0005
    else:
        return 0.0008

def get_exit_fee_rate(direction, ep, exit_price, sl_pct, rr):
    tp_pct = sl_pct * rr
    if direction == 'Long' or direction == 1.0 or direction == 1:
        tp_price = ep * (1.0 + tp_pct)
        if exit_price >= tp_price - 1e-6:
            return 0.00015  # Maker fee (take profit)
        else:
            return 0.00045  # Taker fee (stop loss or regular exit)
    else:  # Short
        tp_price = ep * (1.0 - tp_pct)
        if exit_price <= tp_price + 1e-6:
            return 0.00015  # Maker fee (take profit)
        else:
            return 0.00045  # Taker fee (stop loss or regular exit)

def load_funding_history(symbol):
    path = os.path.join(DATA_DIR, symbol, f"{symbol}_funding.csv")
    if os.path.exists(path):
        try:
            fdf = pd.read_csv(path)
            fdf['timestamp'] = pd.to_datetime(fdf['timestamp'], utc=True, format='mixed')
            fdf.sort_values(by='timestamp', inplace=True)
            return fdf
        except Exception as e:
            print(f"Error parsing funding history for {symbol}: {e}")
    return pd.DataFrame(columns=['timestamp', 'funding_rate'])

TIMEFRAME_DELTAS = {
    "5m":  pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h":  pd.Timedelta(hours=1),
    "4h":  pd.Timedelta(hours=4),
    "1d":  pd.Timedelta(days=1),
}

# ═══════════════════════════════════════════════════════════════════════════════
#  NON-OVERLAPPING DATE PERIODS
#  The original 6 overlapping ranges are replaced by 3 strictly contiguous
#  periods that share no candles.  "Last 30/60/180 days" are dropped as
#  separate rows — they were subsets of 2025-2026 and caused the same lucky
#  candle stretch to appear as multiple rows of "independent" evidence.
# ═══════════════════════════════════════════════════════════════════════════════
SELECTION_PERIOD = {
    "name":  "SELECTION_2023_2024",
    "label": "Selection  (2023-01-01 to 2024-12-31, 24 months)",
    "start": pd.Timestamp("2023-01-01 00:00:00", tz="UTC"),
    "end":   pd.Timestamp("2024-12-31 23:59:59", tz="UTC"),
}
HOLDOUT_1_PERIOD = {
    "name":  "HOLDOUT1_2025",
    "label": "Holdout-1  (2025-01-01 to 2025-12-31, 12 months)",
    "start": pd.Timestamp("2025-01-01 00:00:00", tz="UTC"),
    "end":   pd.Timestamp("2025-12-31 23:59:59", tz="UTC"),
}
HOLDOUT_2_PERIOD = {
    "name":  "HOLDOUT2_2026",
    "label": "Holdout-2  (2026-01-01 to 2026-06-19, ~6 months, most recent)",
    "start": pd.Timestamp("2026-01-01 00:00:00", tz="UTC"),
    "end":   pd.Timestamp("2026-06-19 23:59:59", tz="UTC"),
}

# ═══════════════════════════════════════════════════════════════════════════════
#  METHODOLOGY SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════
MIN_TRADES_REQUIRED       = 50   # floor applied in EVERY period; results below are excluded
TOP_N_CANDIDATES_PER_COIN = 50   # best selection combos per coin forwarded to holdout

# Qualification gates — a combo MUST clear ALL of these in BOTH holdout periods.
# PF 0.9 still loses money after fees; 1.1 is the minimum real-edge threshold.
HOLDOUT_MIN_NET_PROFIT    =  0.0   # Net Profit must be > 0
HOLDOUT_MIN_PROFIT_FACTOR =  1.1   # Profit Factor >= 1.1
HOLDOUT_MIN_SHARPE        =  0.0   # Sharpe Ratio  >= 0

# Combo identity columns (used for joining across phases)
COMBO_KEYS = ['Coin', 'Strategy', 'Timeframe', 'RR Value']

# Result column order for CSV output
RESULT_COLS = [
    'Coin', 'Strategy', 'Timeframe', 'RR Value',
    'Final Balance', 'Net Profit', 'Profit Factor', 'Sharpe Ratio',
    'Expectancy', 'Max Drawdown', 'Win Rate', 'Average Win',
    'Average Loss', 'Number of Trades', 'RUINED',
]


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════
def load_symbol_timeframe(symbol, timeframe):
    ticker_dir = os.path.join(DATA_DIR, symbol)
    if not os.path.isdir(ticker_dir):
        return None

    possible_names = [
        f"{timeframe}.csv",
        f"{timeframe.upper()}.csv",
        f"{timeframe.lower()}.csv",
        f"{symbol}_{timeframe}.csv",
        f"{symbol}_{timeframe.upper()}.csv",
        f"{symbol}_{timeframe.lower()}.csv",
    ]

    filepath = None
    for name in possible_names:
        path = os.path.join(ticker_dir, name)
        if os.path.exists(path):
            filepath = path
            break

    if not filepath:
        return None

    try:
        df = pd.read_csv(filepath)
        col_mapping = {}
        for col in df.columns:
            lc = col.lower()
            if lc in ['timestamp', 'date', 'datetime', 'ts']:
                col_mapping[col] = 'timestamp'
            elif lc == 'open':
                col_mapping[col] = 'open'
            elif lc == 'high':
                col_mapping[col] = 'high'
            elif lc == 'low':
                col_mapping[col] = 'low'
            elif lc == 'close':
                col_mapping[col] = 'close'
            elif lc == 'volume':
                col_mapping[col] = 'volume'

        df.rename(columns=col_mapping, inplace=True)

        required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for req in required:
            if req not in df.columns:
                return None

        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df.sort_values(by='timestamp', inplace=True)
        df.drop_duplicates(subset=['timestamp'], inplace=True)
        df.reset_index(drop=True, inplace=True)
        df['ts'] = (df['timestamp'].astype('int64') // 10**6).astype('int64')
        return df
    except Exception as e:
        print(f"Error loading {symbol} {timeframe}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  INDICATOR HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


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


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    tp    = (df["high"] + df["low"] + df["close"]) / 3
    dates = df["timestamp"].dt.date
    pv    = (tp * df["volume"]).groupby(dates).cumsum()
    vol   = df["volume"].groupby(dates).cumsum().replace(0, 1e-9)
    return pv / vol


# ═══════════════════════════════════════════════════════════════════════════════
#  SIGNAL GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════
def build_signals(df, strategy_name, symbol=None, tf=None, mode=None):
    high, low, close, volume = df['high'], df['low'], df['close'], df['volume']

    signals = pd.DataFrame(index=df.index)
    signals['side']      = ''
    signals['stop_loss'] = np.nan

    if len(df) < 50:
        return signals

    if strategy_name == 'EMA_Cross':
        ema9   = ema(close, 9)
        ema21  = ema(close, 21)
        ema200 = ema(close, 200)

        x_up = (ema9.shift(1) <= ema21.shift(1)) & (ema9 > ema21)
        x_dn = (ema9.shift(1) >= ema21.shift(1)) & (ema9 < ema21)

        long_sig  = x_up
        short_sig = x_dn

        if len(df) >= 200:
            long_sig  = long_sig  & (close > ema200)
            short_sig = short_sig & (close < ema200)

        l_stop = low.rolling(5).min()
        s_stop = high.rolling(5).max()

        signals.loc[long_sig,  'side']      = 'long'
        signals.loc[long_sig,  'stop_loss'] = l_stop
        signals.loc[short_sig, 'side']      = 'short'
        signals.loc[short_sig, 'stop_loss'] = s_stop

    elif strategy_name == 'VWAP_Momentum':
        vwap      = calculate_vwap(df)
        ema9      = ema(close, 9)
        ema21     = ema(close, 21)
        vol_ma10  = volume.rolling(10).mean()
        vol_spike = volume > vol_ma10

        x_up = (ema9.shift(1) <= ema21.shift(1)) & (ema9 > ema21)
        x_dn = (ema9.shift(1) >= ema21.shift(1)) & (ema9 < ema21)

        long_sig  = (close > vwap) & x_up & vol_spike
        short_sig = (close < vwap) & x_dn & vol_spike

        l_stop = low.rolling(5).min()
        s_stop = high.rolling(5).max()

        signals.loc[long_sig,  'side']      = 'long'
        signals.loc[long_sig,  'stop_loss'] = l_stop
        signals.loc[short_sig, 'side']      = 'short'
        signals.loc[short_sig, 'stop_loss'] = s_stop

    elif strategy_name == 'Liquidity_Sweep':
        sw_hi = high.shift(1).rolling(24).max()
        sw_lo = low.shift(1).rolling(24).min()

        swept_hi   = (high > sw_hi) & (close < sw_hi)
        swept_lo   = (low  < sw_lo) & (close > sw_lo)
        swept_hi_3 = swept_hi.rolling(3).max().astype(bool)
        swept_lo_3 = swept_lo.rolling(3).max().astype(bool)

        lph = high.shift(1).rolling(5).max()
        lpl = low.shift(1).rolling(5).min()

        bearish_fvg = (low.shift(2)  > high).rolling(5).max().astype(bool)
        bullish_fvg = (high.shift(2) < low).rolling(5).max().astype(bool)

        long_sig  = swept_lo_3 & (close > lph) & bullish_fvg
        short_sig = swept_hi_3 & (close < lpl) & bearish_fvg

        l_stop = low.rolling(3).min()
        s_stop = high.rolling(3).max()

        signals.loc[long_sig,  'side']      = 'long'
        signals.loc[long_sig,  'stop_loss'] = l_stop
        signals.loc[short_sig, 'side']      = 'short'
        signals.loc[short_sig, 'stop_loss'] = s_stop

    elif strategy_name == 'ATR_Breakout':
        tr        = true_range(df)
        atr14     = tr.rolling(14).mean()
        atr100    = tr.rolling(100).mean()
        atr_ratio = atr14 / atr100

        compress  = atr_ratio.rolling(5).min() < 0.95
        prev_dh   = high.shift(1).rolling(20).max()
        prev_dl   = low.shift(1).rolling(20).min()
        vol_sma20 = volume.rolling(20).mean()
        vol_spike = volume > 1.25 * vol_sma20

        adx    = adx_series(df)
        adx_ok = (adx > adx.shift(1)) | (adx > 25.0)
        ema50  = ema(close, 50)

        long_sig  = compress & (close > prev_dh) & vol_spike & adx_ok & (close > ema50)
        short_sig = compress & (close < prev_dl) & vol_spike & adx_ok & (close < ema50)

        l_stop_fallback = low.rolling(5).min()
        s_stop_fallback = high.rolling(5).max()

        l_stop = prev_dl.where(~(close - prev_dl > close * 0.1), l_stop_fallback)
        l_stop = l_stop.where(l_stop < close, close * 0.99)
        s_stop = prev_dh.where(~(prev_dh - close > close * 0.1), s_stop_fallback)
        s_stop = s_stop.where(s_stop > close, close * 1.01)

        signals.loc[long_sig,  'side']      = 'long'
        signals.loc[long_sig,  'stop_loss'] = l_stop
        signals.loc[short_sig, 'side']      = 'short'
        signals.loc[short_sig, 'stop_loss'] = s_stop

    elif strategy_name == 'Volatility_Expansion':
        if mode not in ['VE_1_BB_SQUEEZE', 'VE_2_KELTNER_SQUEEZE', 'VE_3_ATR_EXPANSION']:
            raise ValueError(f"Volatility_Expansion strategy requires mode to be 'VE_1_BB_SQUEEZE', 'VE_2_KELTNER_SQUEEZE', or 'VE_3_ATR_EXPANSION'. Got: {mode}")

        tr = true_range(df)
        atr14 = tr.rolling(14).mean()

        if mode == 'VE_1_BB_SQUEEZE':
            mid = close.rolling(20).mean()
            std = close.rolling(20).std()
            upper = mid + 2 * std
            lower = mid - 2 * std
            bb_width = (upper - lower) / mid
            bb_width_p20 = bb_width.rolling(100).quantile(0.20)
            squeeze = bb_width < bb_width_p20

            long_sig = squeeze & (close > upper)
            short_sig = squeeze & (close < lower)

        elif mode == 'VE_2_KELTNER_SQUEEZE':
            mid_bb = close.rolling(20).mean()
            std_bb = close.rolling(20).std()
            upper_bb = mid_bb + 2 * std_bb
            lower_bb = mid_bb - 2 * std_bb

            atr20 = tr.rolling(20).mean()
            mid_kc = close.ewm(span=20, adjust=False).mean()
            upper_kc = mid_kc + 1.5 * atr20
            lower_kc = mid_kc - 1.5 * atr20

            squeeze = (upper_bb < upper_kc) & (lower_bb > lower_kc)
            long_sig = squeeze & (close > upper_bb)
            short_sig = squeeze & (close < lower_bb)

        elif mode == 'VE_3_ATR_EXPANSION':
            atr14_mean = atr14.rolling(20).mean()
            atr_expanded = atr14 > 1.5 * atr14_mean
            prev_high = high.shift(1).rolling(20).max()
            prev_low = low.shift(1).rolling(20).min()

            long_sig = atr_expanded & (close > prev_high)
            short_sig = atr_expanded & (close < prev_low)

        signals.loc[long_sig, 'side'] = 'long'
        signals.loc[long_sig, 'stop_loss'] = close - 1.5 * atr14
        signals.loc[short_sig, 'side'] = 'short'
        signals.loc[short_sig, 'stop_loss'] = close + 1.5 * atr14

    elif strategy_name == 'Session_ORB':
        hours = df['timestamp'].dt.hour
        sess_id = df['timestamp'].dt.strftime('%Y-%m-%d_') + np.where(hours < 12, '00', '12')
        sess_start = pd.to_datetime(df['timestamp'].dt.date).dt.tz_localize('UTC') + pd.to_timedelta(np.where(hours < 12, 0, 12), unit='h')
        
        is_range_def = df['timestamp'] < sess_start + pd.Timedelta(hours=1)
        range_highs = df['high'].where(is_range_def).groupby(sess_id).transform('max')
        range_lows = df['low'].where(is_range_def).groupby(sess_id).transform('min')
        
        range_width_pct = (range_highs - range_lows) / range_lows
        valid_range = (range_width_pct >= 0.002) & (range_width_pct <= 0.03)
        
        is_trade_phase = df['timestamp'] >= sess_start + pd.Timedelta(hours=1)
        
        is_breakout_long = is_trade_phase & valid_range & (close > range_highs)
        is_breakout_short = is_trade_phase & valid_range & (close < range_lows)
        any_breakout = is_breakout_long | is_breakout_short
        
        breakout_rank = any_breakout.groupby(sess_id).cumsum()
        
        long_sig = is_breakout_long & (breakout_rank == 1)
        short_sig = is_breakout_short & (breakout_rank == 1)
        
        tr = true_range(df)
        atr = tr.rolling(14).mean()
        
        l_stop = range_lows
        l_stop = np.maximum(l_stop, close - 2.0 * atr)
        l_stop = np.minimum(l_stop, close - 0.5 * atr)
        
        s_stop = range_highs
        s_stop = np.minimum(s_stop, close + 2.0 * atr)
        s_stop = np.maximum(s_stop, close + 0.5 * atr)
        
        signals.loc[long_sig, 'side'] = 'long'
        signals.loc[long_sig, 'stop_loss'] = l_stop
        signals.loc[short_sig, 'side'] = 'short'
        signals.loc[short_sig, 'stop_loss'] = s_stop

    elif strategy_name == 'Mean_Reversion':
        if mode not in ['RSI', 'BB', 'RSI_BB']:
            raise ValueError(f"Mean_Reversion strategy requires mode to be 'RSI', 'BB', or 'RSI_BB'. Got: {mode}")

        mid = close.rolling(20).mean()
        std = close.rolling(20).std()
        upper = mid + 2 * std
        lower = mid - 2 * std
        
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean().replace(0, 1e-9)
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        tr = true_range(df)
        atr = tr.rolling(14).mean()
        
        if mode == 'RSI':
            long_sig = rsi < 25
            short_sig = rsi > 75
        elif mode == 'BB':
            long_sig = close < lower
            short_sig = close > upper
        elif mode == 'RSI_BB':
            adx = adx_series(df, 14)
            long_sig = (rsi < 30) & (close < lower) & (adx < 20)
            short_sig = (rsi > 70) & (close > upper) & (adx < 20)
        
        signals.loc[long_sig, 'side'] = 'long'
        signals.loc[long_sig, 'stop_loss'] = close - 1.5 * atr
        signals.loc[short_sig, 'side'] = 'short'
        signals.loc[short_sig, 'stop_loss'] = close + 1.5 * atr

    elif strategy_name == 'Funding_Contrarian':
        if symbol:
            funding_df = load_funding_history(symbol)
        else:
            funding_df = pd.DataFrame()
            
        if funding_df is not None and not funding_df.empty:
            funding_df = funding_df.sort_values('timestamp').copy()
            # Calculate rolling percentiles on funding_df to avoid lookahead bias
            funding_df['p10'] = funding_df['funding_rate'].rolling(720, min_periods=100).quantile(0.10)
            funding_df['p90'] = funding_df['funding_rate'].rolling(720, min_periods=100).quantile(0.90)
            
            # Merge onto df
            df_merged = pd.merge_asof(
                df.sort_values('timestamp'),
                funding_df[['timestamp', 'funding_rate', 'p10', 'p90']],
                on='timestamp',
                direction='backward'
            )
            f_rate = df_merged['funding_rate']
            f_p10 = df_merged['p10']
            f_p90 = df_merged['p90']
        else:
            f_rate = pd.Series(0.0, index=df.index)
            f_p10 = pd.Series(np.nan, index=df.index)
            f_p90 = pd.Series(np.nan, index=df.index)
            
        long_sig = (f_rate <= f_p10) & f_p10.notna()
        short_sig = (f_rate >= f_p90) & f_p90.notna()
        
        tr = true_range(df)
        atr = tr.rolling(14).mean()
        
        signals.loc[long_sig, 'side'] = 'long'
        signals.loc[long_sig, 'stop_loss'] = close - 2.0 * atr
        signals.loc[short_sig, 'side'] = 'short'
        signals.loc[short_sig, 'stop_loss'] = close + 2.0 * atr

    elif strategy_name == 'HTF_Pullback':
        LTF_TO_HTF = {
            '5m': '15m',
            '15m': '1h',
            '1h': '4h',
            '4h': '1d'
        }
        htf = LTF_TO_HTF.get(tf) if tf else None
        if htf and symbol:
            df_htf = load_symbol_timeframe(symbol, htf)
            if df_htf is not None and not df_htf.empty:
                ema50_htf = ema(df_htf['close'], 50)
                adx_htf = adx_series(df_htf, 14)
                
                htf_bullish = (ema50_htf > ema50_htf.shift(1)) & (adx_htf > 20.0)
                htf_bearish = (ema50_htf < ema50_htf.shift(1)) & (adx_htf > 20.0)
                
                # Add indicators to df_htf and shift timestamps to avoid lookahead bias
                df_htf = df_htf.copy()
                df_htf['htf_bullish'] = htf_bullish
                df_htf['htf_bearish'] = htf_bearish
                df_htf['available_time'] = df_htf['timestamp'] + TIMEFRAME_DELTAS[htf]
                
                # Merge onto df
                df_sorted = df.sort_values('timestamp').copy()
                df_htf_sorted = df_htf.sort_values('available_time').copy()
                
                df_merged = pd.merge_asof(
                    df_sorted, df_htf_sorted[['available_time', 'htf_bullish', 'htf_bearish']],
                    left_on='timestamp',
                    right_on='available_time',
                    direction='backward'
                )
                
                h_bullish = df_merged['htf_bullish'].fillna(False)
                h_bearish = df_merged['htf_bearish'].fillna(False)
            else:
                h_bullish = pd.Series(False, index=df.index)
                h_bearish = pd.Series(False, index=df.index)
        else:
            h_bullish = pd.Series(False, index=df.index)
            h_bearish = pd.Series(False, index=df.index)
            
        ema20_ltf = ema(close, 20)
        tr = true_range(df)
        atr = tr.rolling(14).mean()
        
        long_trigger = (close.shift(1) <= ema20_ltf.shift(1)) & (close > ema20_ltf)
        short_trigger = (close.shift(1) >= ema20_ltf.shift(1)) & (close < ema20_ltf)
        
        long_sig = h_bullish & long_trigger
        short_sig = h_bearish & short_trigger
        
        signals.loc[long_sig, 'side'] = 'long'
        signals.loc[long_sig, 'stop_loss'] = close - 1.5 * atr
        signals.loc[short_sig, 'side'] = 'short'
        signals.loc[short_sig, 'stop_loss'] = close + 1.5 * atr

    return signals


def build_vbt_signals(df_slice, signals_slice, rr_values):
    index = df_slice.index
    n     = len(df_slice)

    entries       = pd.Series(False,   index=index)
    short_entries = pd.Series(False,   index=index)
    sl_stop       = pd.Series(np.nan,  index=index)

    sig_rows   = np.where(signals_slice['side'] != '')[0]
    sl_pct_map = {}

    for r in sig_rows:
        if r >= n - 1:
            continue
        side     = signals_slice['side'].iloc[r]
        sl_price = signals_slice['stop_loss'].iloc[r]
        if pd.isna(sl_price) or sl_price <= 0:
            continue

        entry_row = r + 1
        ep        = df_slice['open'].iloc[entry_row]
        if ep <= 0:
            continue

        dist   = abs(ep - sl_price)
        sl_pct = dist / ep
        if sl_pct <= 0:
            continue

        entry_idx = df_slice.index[entry_row]
        if side == 'long':
            entries.iloc[entry_row] = True
        else:
            short_entries.iloc[entry_row] = True

        sl_stop.iloc[entry_row]    = sl_pct
        sl_pct_map[entry_idx]      = sl_pct

    # tp_stop DataFrame — one column per RR value requested
    tp_stop = pd.DataFrame(index=index)
    for rr in rr_values:
        tp_stop[rr] = sl_stop * rr

    return entries, short_entries, sl_stop, tp_stop, sl_pct_map


# ═══════════════════════════════════════════════════════════════════════════════
#  PORTFOLIO SIMULATION & METRICS
# ═══════════════════════════════════════════════════════════════════════════════
def calculate_daily_sharpe(equity_curve, exit_dates):
    if len(exit_dates) < 2:
        return 0.0

    df_eq = pd.DataFrame({'Date': pd.to_datetime(exit_dates), 'Balance': equity_curve[1:]})
    df_eq['Date'] = df_eq['Date'].dt.normalize()
    daily = df_eq.groupby('Date')['Balance'].last()

    if len(daily) < 2:
        return 0.0

    full_idx   = pd.date_range(start=daily.index.min(), end=daily.index.max(), freq='D')
    daily      = daily.reindex(full_idx).ffill()
    daily_pct  = daily.pct_change().dropna()

    if daily_pct.empty or daily_pct.std() == 0:
        return 0.0

    return (daily_pct.mean() / daily_pct.std()) * np.sqrt(252)


def simulate_portfolio_leverage(trades_df, sl_pct_map, df_slice, symbol, rr, funding_df):
    balance      = INITIAL_BALANCE
    equity_curve = [balance]
    exit_dates   = []
    sim_trades   = []
    ruined       = False

    if trades_df.empty:
        return sim_trades, balance, equity_curve, exit_dates, ruined

    CRYPTO_TICKERS = {
        "BTC", "XRP", "ETH", "ADA", "SOL", "BNB", "DOGE", "TRX", "HYPE", "ZEC",
        "LINK", "HBAR", "LTC", "SUI", "NEAR", "AVAX", "TAO", "WLD", "UNI", "ONDO",
        "AAVE", "RENDER", "ENA", "INJ", "DOT"
    }

    trades_sorted = trades_df.sort_values(by='Entry Timestamp').reset_index(drop=True)
    is_crypto = symbol.upper() in CRYPTO_TICKERS
    slippage_rate = get_slippage_rate(symbol) if is_crypto else 0.0002

    for _, row in trades_sorted.iterrows():
        if balance <= 0:
            ruined = True
            break

        ep         = float(row['Avg Entry Price'])
        exit_price = float(row['Avg Exit Price'])
        vbt_qty    = float(row['Size'])

        sl_pct = sl_pct_map.get(row['Entry Timestamp'])
        if sl_pct is None or sl_pct <= 0:
            continue

        direction = row['Direction']
        
        # Sizing and fee calculation based on asset class
        if is_crypto:
            exit_fee_rate = get_exit_fee_rate(direction, ep, exit_price, sl_pct, rr)
            sizing_friction = ep * (0.00045 + 0.00045 + 2 * slippage_rate)
        else:
            exit_fee_rate = 0.0005
            sizing_friction = ep * (0.0005 + 0.0005 + 2 * 0.0002)

        dist     = ep * sl_pct
        risk_qty = RISK_PER_TRADE / (dist + sizing_friction)
        max_qty  = (balance * LEVERAGE) / ep
        
        # RUIN CHECK — halt before entering this trade
        if max_qty < 0.3 * risk_qty:
            ruined = True
            break

        qty      = min(risk_qty, max_qty)

        # Net Profit/Loss calculation
        if direction == 'Long' or direction == 1.0 or direction == 1:
            gross_pnl = (exit_price - ep) * qty
            funding_multiplier = -1.0
        else:
            gross_pnl = (ep - exit_price) * qty
            funding_multiplier = 1.0

        # Fees and Slippage
        if is_crypto:
            entry_fee = qty * ep * 0.00045
            exit_fee = qty * exit_price * exit_fee_rate
            entry_slippage = qty * ep * slippage_rate
            if exit_fee_rate == 0.00015:  # Maker limit exit (TP)
                exit_slippage = 0.0
            else:  # Taker market exit (SL or time close)
                exit_slippage = qty * exit_price * slippage_rate
        else:
            entry_fee = qty * ep * 0.0005
            exit_fee = qty * exit_price * 0.0005
            entry_slippage = qty * ep * 0.0002
            exit_slippage = qty * exit_price * 0.0002
            
        # Funding rate carry P&L (only for crypto)
        funding_pnl = 0.0
        entry_idx = row['Entry Timestamp']
        exit_idx = row['Exit Timestamp']
        entry_time = df_slice.loc[entry_idx, 'timestamp']
        exit_time = df_slice.loc[exit_idx, 'timestamp']

        if is_crypto:
            if funding_df is not None and not funding_df.empty:
                # Find funding records settled during the trade
                mask = (funding_df['timestamp'] > entry_time) & (funding_df['timestamp'] <= exit_time)
                sum_funding = funding_df.loc[mask, 'funding_rate'].sum()
                funding_pnl = funding_multiplier * qty * ep * sum_funding
            else:
                # Default fallback funding rate if missing (0.01% per hour)
                duration_hours = (exit_time - entry_time).total_seconds() / 3600.0
                sum_funding = duration_hours * 0.0001
                funding_pnl = funding_multiplier * qty * ep * sum_funding

        # Net PnL of this trade
        net_trade_pnl = gross_pnl - entry_fee - exit_fee - entry_slippage - exit_slippage + funding_pnl
        balance += net_trade_pnl
        balance  = max(0.0, balance)

        equity_curve.append(balance)
        exit_dates.append(exit_time)

        duration_hours = (exit_time - entry_time).total_seconds() / 3600.0
        initial_risk = qty * (ep * sl_pct)
        r_mult = net_trade_pnl / initial_risk if initial_risk > 0 else 0.0

        sim_trades.append({
            'pnl':         net_trade_pnl,
            'direction':   direction,
            'entry_price': ep,
            'exit_price':  exit_price,
            'qty':         qty,
            'exit_date':   exit_time,
            'r_multiple':  r_mult,
            'duration_hours': duration_hours,
        })

        if balance <= 0:
            ruined = True
            break

    return sim_trades, balance, equity_curve, exit_dates, ruined


def compute_metrics(sim_trades, final_balance, initial_balance, equity_curve, exit_dates):
    net_profit   = final_balance - initial_balance
    total_trades = len(sim_trades)

    if total_trades == 0:
        return {
            'Final Balance':   final_balance,
            'Net Profit':      net_profit,
            'Profit Factor':   0.0,
            'Sharpe Ratio':    0.0,
            'Expectancy':      0.0,
            'Max Drawdown':    0.0,
            'Win Rate':        0.0,
            'Average Win':     0.0,
            'Average Loss':    0.0,
            'Number of Trades': 0,
        }

    wins   = [t['pnl'] for t in sim_trades if t['pnl'] > 0]
    losses = [t['pnl'] for t in sim_trades if t['pnl'] <= 0]

    win_rate  = len(wins) / total_trades * 100
    avg_win   = np.mean(wins)   if wins   else 0.0
    avg_loss  = np.mean(losses) if losses else 0.0

    sum_wins   = sum(wins)
    sum_losses = sum(losses)
    if sum_losses == 0:
        profit_factor = 999.9 if sum_wins > 0 else 1.0
    else:
        profit_factor = abs(sum_wins / sum_losses)

    expectancy = (win_rate / 100.0 * avg_win) + ((100 - win_rate) / 100.0 * avg_loss)

    eq_series  = pd.Series(equity_curve)
    cummax     = eq_series.cummax()
    drawdown   = (eq_series - cummax) / cummax.replace(0, 1e-9)
    max_dd     = abs(drawdown.min()) * 100

    daily_sharpe = calculate_daily_sharpe(equity_curve, exit_dates)

    return {
        'Final Balance':    round(final_balance,  2),
        'Net Profit':       round(net_profit,      2),
        'Profit Factor':    round(profit_factor,   2),
        'Sharpe Ratio':     round(daily_sharpe,    2),
        'Expectancy':       round(expectancy,      2),
        'Max Drawdown':     round(max_dd,          2),
        'Win Rate':         round(win_rate,        2),
        'Average Win':      round(avg_win,         2),
        'Average Loss':     round(avg_loss,        2),
        'Number of Trades': total_trades,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  SINGLE-PERIOD PROCESSOR
#  Replaces the old process_symbol_timeframe() which looped over all 6 ranges.
#  Now each call targets exactly one time period, with an optional filter on
#  which (strategy, rr) combos to run (used in holdout phases to avoid testing
#  combos that were not selected).
# ═══════════════════════════════════════════════════════════════════════════════
def process_symbol_timeframe_period(symbol, tf, start_dt, end_dt, allowed_combos=None):
    """
    Run backtests for one (symbol, timeframe) pair over a single date window.

    Parameters
    ----------
    allowed_combos : set of (strategy_name: str, rr: float) | None
        If None  → run all strategy/RR combos (selection phase).
        If set   → run only the listed combos (holdout phases, saves compute).

    Returns
    -------
    list of result dicts (one per qualifying combo)
    """
    df = load_symbol_timeframe(symbol, tf)
    if df is None or df.empty:
        return []

    # ── Build signals on FULL history so indicator warm-up is complete ──────
    strat_signals = {s: build_signals(df, s, symbol, tf) for s in STRATEGIES}

    # ── Slice to the requested period (keep original index for VBT) ──────────
    mask     = (df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)
    df_slice = df[mask]

    if len(df_slice) < 50:
        return []

    results = []

    for strat in STRATEGIES:
        signals_slice = strat_signals[strat][mask]

        if signals_slice['side'].eq('').all():
            continue

        # Determine which RR values to run for this strategy
        if allowed_combos is not None:
            rr_to_run = [rr for rr in RR_VALUES if (strat, rr) in allowed_combos]
            if not rr_to_run:
                continue
        else:
            rr_to_run = list(RR_VALUES)

        if strat == 'Mean_Reversion':
            rr_to_run = [rr for rr in rr_to_run if rr in [1.5, 2.0]]
            if not rr_to_run:
                continue

        try:
            entries_s, short_entries_s, sl_stop_s, tp_stop_all, sl_pct_map = build_vbt_signals(
                df_slice, signals_slice, rr_to_run
            )

            if not entries_s.any() and not short_entries_s.any():
                continue

            exits_s         = pd.Series(False, index=df_slice.index)
            exits_s.iloc[-1] = True
            short_exits_s   = pd.Series(False, index=df_slice.index)
            short_exits_s.iloc[-1] = True

            order_price          = df_slice['open'].copy()
            order_price.iloc[-1] = df_slice['close'].iloc[-1]

            # Only pass the columns VBT needs to simulate
            tp_stop_df = tp_stop_all[rr_to_run]

            pf = vbt.Portfolio.from_signals(
                close          = df_slice['close'],
                entries        = entries_s,
                exits          = exits_s,
                short_entries  = short_entries_s,
                short_exits    = short_exits_s,
                size           = 1.0,
                size_type      = "amount",
                price          = order_price,
                open           = df_slice['open'],
                high           = df_slice['high'],
                low            = df_slice['low'],
                sl_stop        = sl_stop_s,
                tp_stop        = tp_stop_df,
                fees           = FEE_RATE,
                slippage       = SLIPPAGE_RATE,
                init_cash      = 1_000_000.0,
                accumulate     = False,
                upon_opposite_entry = OppositeEntryMode.Ignore,
                stop_exit_price     = StopExitPrice.StopMarket,
                upon_stop_exit      = StopExitMode.Close,
                freq           = TIMEFRAME_DELTAS[tf],
            )

            for rr in rr_to_run:
                try:
                    # Multi-column portfolio: index by RR.
                    # If only 1 RR was run, VBT still produces a 1-col portfolio;
                    # pf[rr] is still valid but we fall back to pf if it raises.
                    try:
                        sub_pf = pf[rr]
                    except Exception:
                        sub_pf = pf   # single-column fallback

                    if sub_pf.trades.count() == 0:
                        continue

                    trades_df = sub_pf.trades.records_readable
                    
                    # Load historical funding rate
                    funding_df = load_funding_history(symbol)
                    
                    sim_trades, final_bal, equity_curve, exit_dates, ruined = simulate_portfolio_leverage(
                        trades_df, sl_pct_map, df_slice, symbol, rr, funding_df
                    )

                    m = compute_metrics(sim_trades, final_bal, INITIAL_BALANCE, equity_curve, exit_dates)
                    m.update({
                        'Coin':      symbol,
                        'Strategy':  strat,
                        'Timeframe': tf,
                        'RR Value':  f"1:{rr}",
                        '_rr_raw':   rr,      # internal float, stripped before CSV save
                        'RUINED':    ruined,
                    })
                    results.append(m)
                except Exception:
                    pass

        except Exception:
            pass

    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  SCORING & UTILITY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def compute_combined_score_per_coin(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add 'Combined Score' column (0-100) using percentile ranks computed
    *within each coin's own result pool*, not globally.
    This prevents a BTC result from crowding out an ETH result just because
    BTC happened to have a better absolute PF that quarter.

    Weights  (identical to original formula):
      30 % Profit Factor rank
      30 % Sharpe Ratio rank
      20 % Net Profit rank
      20 % Max Drawdown rank  (lower DD → higher rank, so we negate)
    """
    df = df.copy()
    df['Combined Score'] = 0.0

    for coin, grp in df.groupby('Coin'):
        score = (
            grp['Profit Factor'].rank(pct=True)             * 30.0 +
            grp['Sharpe Ratio'].fillna(0).rank(pct=True)    * 30.0 +
            grp['Net Profit'].rank(pct=True)                * 20.0 +
            (-grp['Max Drawdown']).rank(pct=True)           * 20.0
        ).round(2)
        df.loc[grp.index, 'Combined Score'] = score.values

    return df


def _gate_pass(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows that pass ALL holdout qualification gates."""
    if df.empty:
        return df
    ruined_mask = df['RUINED'] == False if 'RUINED' in df.columns else True
    return df[
        (df['Number of Trades'] >= MIN_TRADES_REQUIRED)     &
        (df['Net Profit']        > HOLDOUT_MIN_NET_PROFIT)  &
        (df['Profit Factor']    >= HOLDOUT_MIN_PROFIT_FACTOR) &
        (df['Sharpe Ratio']     >= HOLDOUT_MIN_SHARPE) &
        ruined_mask
    ].copy()


def _combo_keyset(df: pd.DataFrame) -> set:
    """Convert COMBO_KEYS columns to a set of tuples for fast intersection."""
    if df.empty:
        return set()
    return set(zip(*[df[c] for c in COMBO_KEYS]))


def _filter_by_keys(df: pd.DataFrame, keys: set) -> pd.DataFrame:
    """Keep only rows whose COMBO_KEYS tuple is in *keys*."""
    if df.empty or not keys:
        return df.iloc[0:0].copy()
    mask = pd.Series(
        [tuple(row[c] for c in COMBO_KEYS) for _, row in df.iterrows()],
        index=df.index
    ).isin(keys)
    return df[mask].copy()


def _save_csv(df: pd.DataFrame, filename: str, verbose: bool = True):
    path = os.path.join(RESULTS_DIR, filename)
    df.to_csv(path, index=False)
    if verbose:
        print(f"    -> {filename}  ({len(df):,} rows)  saved to {path}")


def _run_phase(phase_label, tasks, start_dt, end_dt, allowed_map, max_workers):
    """Helper: run process_symbol_timeframe_period in parallel for a list of tasks."""
    raw = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                process_symbol_timeframe_period,
                sym, tf, start_dt, end_dt,
                allowed_map.get((sym, tf)) if allowed_map else None
            ): (sym, tf)
            for sym, tf in tasks
        }
        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc=phase_label,
        ):
            sym, tf = futures[future]
            try:
                res = future.result()
                if res:
                    raw.extend(res)
            except Exception as e:
                print(f"    ERROR {sym} {tf}: {e}")
    return raw


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN FLOW
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    symbols = sorted([
        d for d in os.listdir(DATA_DIR)
        if os.path.isdir(os.path.join(DATA_DIR, d))
    ])
    # Keep only the folders that aren't raw USDT-suffixed duplicates
    symbols = [s for s in symbols if not s.endswith('USDT') or s == 'HYPE']

    max_workers = os.cpu_count()
    all_tasks   = [(sym, tf) for sym in symbols for tf in TIMEFRAMES]

    print("=" * 72)
    print("  CRYPTO BACKTESTER - OUT-OF-SAMPLE VALIDATION FRAMEWORK")
    print("=" * 72)
    print(f"  Symbols   : {len(symbols)}  ({', '.join(symbols)})")
    print(f"  Timeframes: {TIMEFRAMES}")
    print(f"  Strategies: {STRATEGIES}")
    print(f"  RR Values : {RR_VALUES}")
    print()
    print("  PERIODS (non-overlapping, no candle counted twice):")
    print(f"    {SELECTION_PERIOD['label']}")
    print(f"    {HOLDOUT_1_PERIOD['label']}")
    print(f"    {HOLDOUT_2_PERIOD['label']}")
    print()
    print(f"  Min trades required (every period) : {MIN_TRADES_REQUIRED}")
    print(f"  Top-N candidates per coin          : {TOP_N_CANDIDATES_PER_COIN}")
    print(f"  Holdout qualification gates        :")
    print(f"    Net Profit    > {HOLDOUT_MIN_NET_PROFIT}")
    print(f"    Profit Factor >= {HOLDOUT_MIN_PROFIT_FACTOR}")
    print(f"    Sharpe Ratio  >= {HOLDOUT_MIN_SHARPE}")
    print(f"    Trades        >= {MIN_TRADES_REQUIRED}")
    print(f"    (ALL gates must hold in BOTH holdout periods)")
    print("=" * 72)

    # ───────────────────────────────────────────────────────────────────────────
    # PHASE 1 — SELECTION (2023–2024)
    # Run all combos; results that don't reach MIN_TRADES_REQUIRED are excluded
    # before scoring.  Top-N per coin are forwarded to holdout.
    # ───────────────────────────────────────────────────────────────────────────
    print(f"\n[PHASE 1] SELECTION  ({SELECTION_PERIOD['label']})")
    print(f"  Tasks: {len(all_tasks)} symbol×timeframe pairs\n")

    raw_sel = _run_phase(
        "Selection", all_tasks,
        SELECTION_PERIOD['start'], SELECTION_PERIOD['end'],
        allowed_map=None,    # run everything
        max_workers=max_workers,
    )

    if not raw_sel:
        print("\nFATAL: Zero selection results generated. Check data directory.")
        return

    df_sel_all = pd.DataFrame(raw_sel)

    # Apply trade-count floor and exclude ruined combos
    df_sel_eligible = df_sel_all[
        (df_sel_all['Number of Trades'] >= MIN_TRADES_REQUIRED) &
        (df_sel_all['RUINED'] == False)
    ].copy()

    print(f"\n  Raw results              : {len(df_sel_all):,}")
    print(f"  After ≥{MIN_TRADES_REQUIRED} trades and RUINED=False filter: {len(df_sel_eligible):,}")

    if df_sel_eligible.empty:
        print("\nFATAL: No selection results pass the minimum trade count and RUINED=False check. Aborting.")
        return

    # Score per coin, take top N
    df_sel_scored = compute_combined_score_per_coin(df_sel_eligible)
    df_sel_top = (
        df_sel_scored
        .groupby('Coin', group_keys=False)
        .apply(lambda x: x.nlargest(TOP_N_CANDIDATES_PER_COIN, 'Combined Score'))
        .reset_index(drop=True)
    )

    n_candidates = len(df_sel_top)
    print(f"  Top-{TOP_N_CANDIDATES_PER_COIN} per coin forwarded    : {n_candidates:,}")

    # Save selection_results_v3.csv  (top candidates only)
    sel_save_cols = [c for c in RESULT_COLS + ['Combined Score'] if c in df_sel_top.columns]
    df_sel_save   = df_sel_top[sel_save_cols].sort_values(
        ['Coin', 'Combined Score'], ascending=[True, False]
    )
    print()
    _save_csv(df_sel_save, "selection_results_v3.csv")

    # Build per-(coin,tf) allowed-combo maps for holdout phases
    allowed_map: dict = {}
    for _, row in df_sel_top.iterrows():
        key = (row['Coin'], row['Timeframe'])
        allowed_map.setdefault(key, set()).add((row['Strategy'], row['_rr_raw']))

    h_tasks = list(allowed_map.keys())

    # ───────────────────────────────────────────────────────────────────────────
    # PHASE 2A — HOLDOUT-1 (2025)
    # Run only the selected candidates; all others are ignored.
    # ───────────────────────────────────────────────────────────────────────────
    print(f"\n[PHASE 2A] HOLDOUT-1  ({HOLDOUT_1_PERIOD['label']})")
    print(f"  Tasks: {len(h_tasks)} coin×timeframe pairs "
          f"(only top-{TOP_N_CANDIDATES_PER_COIN} combos per coin)\n")

    raw_h1 = _run_phase(
        "Holdout-1", h_tasks,
        HOLDOUT_1_PERIOD['start'], HOLDOUT_1_PERIOD['end'],
        allowed_map=allowed_map,
        max_workers=max_workers,
    )

    df_h1 = pd.DataFrame(raw_h1) if raw_h1 else pd.DataFrame(columns=RESULT_COLS)
    h1_save = df_h1[[c for c in RESULT_COLS if c in df_h1.columns]] if not df_h1.empty else df_h1
    print()
    _save_csv(h1_save, "holdout1_results_v3.csv")

    # ───────────────────────────────────────────────────────────────────────────
    # PHASE 2B — HOLDOUT-2 (2026 YTD)
    # Same candidate set as holdout-1.
    # ───────────────────────────────────────────────────────────────────────────
    print(f"\n[PHASE 2B] HOLDOUT-2  ({HOLDOUT_2_PERIOD['label']})")
    print(f"  Tasks: {len(h_tasks)} coin×timeframe pairs\n")

    raw_h2 = _run_phase(
        "Holdout-2", h_tasks,
        HOLDOUT_2_PERIOD['start'], HOLDOUT_2_PERIOD['end'],
        allowed_map=allowed_map,
        max_workers=max_workers,
    )

    df_h2 = pd.DataFrame(raw_h2) if raw_h2 else pd.DataFrame(columns=RESULT_COLS)
    h2_save = df_h2[[c for c in RESULT_COLS if c in df_h2.columns]] if not df_h2.empty else df_h2
    print()
    _save_csv(h2_save, "holdout2_results_v3.csv")

    # ───────────────────────────────────────────────────────────────────────────
    # PHASE 3 — QUALIFICATION
    # A combo qualifies iff it clears ALL gates in BOTH holdout periods.
    # ───────────────────────────────────────────────────────────────────────────
    print(f"\n[PHASE 3] QUALIFICATION")

    h1_pass = _gate_pass(df_h1)
    h2_pass = _gate_pass(df_h2)

    print(f"  Holdout-1 rows passing gates : {len(h1_pass):,} / {len(df_h1):,}")
    print(f"  Holdout-2 rows passing gates : {len(h2_pass):,} / {len(df_h2):,}")

    qualified_keys = _combo_keyset(h1_pass) & _combo_keyset(h2_pass)

    print(f"  Combos passing BOTH holdouts : {len(qualified_keys):,}")

    # ── Build side-by-side qualified_results.csv ──────────────────────────────
    SIDE_COLS = ['Net Profit', 'Profit Factor', 'Sharpe Ratio',
                 'Win Rate', 'Number of Trades', 'Max Drawdown']

    def _prefix(df, tag):
        """Keep combo keys + side metrics, rename metrics with prefix."""
        keep = COMBO_KEYS + [c for c in SIDE_COLS if c in df.columns]
        sub  = df[keep].copy()
        sub.rename(columns={c: f"{tag}_{c}" for c in SIDE_COLS if c in df.columns}, inplace=True)
        return sub

    if qualified_keys:
        sel_q = _filter_by_keys(df_sel_top, qualified_keys)
        h1_q  = _filter_by_keys(h1_pass,    qualified_keys)
        h2_q  = _filter_by_keys(h2_pass,    qualified_keys)

        df_qualified = (
            _prefix(sel_q, "SEL")
            .merge(_prefix(h1_q, "H1"), on=COMBO_KEYS, how='inner')
            .merge(_prefix(h2_q, "H2"), on=COMBO_KEYS, how='inner')
        )

        # Sort by H2 Sharpe descending — most recent period, most informative
        if 'H2_Sharpe Ratio' in df_qualified.columns:
            df_qualified.sort_values('H2_Sharpe Ratio', ascending=False, inplace=True)

        df_qualified.reset_index(drop=True, inplace=True)
    else:
        df_qualified = pd.DataFrame(columns=COMBO_KEYS)

    print()
    _save_csv(df_qualified, "qualified_results_v3.csv")

    # ───────────────────────────────────────────────────────────────────────────
    # SUMMARY REPORT
    # ───────────────────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("  VALIDATION FUNNEL SUMMARY")
    print("=" * 72)
    print(f"  Selection combos (≥{MIN_TRADES_REQUIRED} trades)       : {len(df_sel_eligible):>7,}")
    print(f"  Top-{TOP_N_CANDIDATES_PER_COIN} candidates forwarded         : {n_candidates:>7,}")
    print(f"  Holdout-1 results produced       : {len(df_h1):>7,}")
    print(f"  Holdout-1 passing ALL gates      : {len(h1_pass):>7,}")
    print(f"  Holdout-2 results produced       : {len(df_h2):>7,}")
    print(f"  Holdout-2 passing ALL gates      : {len(h2_pass):>7,}")
    print(f"  ----------------------------------------------")
    print(f"  QUALIFIED (both holdouts, all gates) : {len(qualified_keys):>4,}")
    print("=" * 72)

    if len(qualified_keys) == 0:
        print()
        print("  [!] ZERO combos qualified.")
        print("      This is a valid and important finding.")
        print("      No (Strategy, Timeframe, RR) combination demonstrated")
        print("      consistent out-of-sample performance across both holdout")
        print("      periods under the required minimum bars/profitability.")
        print("      Do NOT trade any combo from selection_results.csv.")
        print("      Thresholds were NOT loosened to force a result.")
    else:
        print(f"\n  [OK] {len(qualified_keys)} combo(s) survived the full funnel.")
        print("       Side-by-side metrics (SEL = selection, H1 = holdout-1, H2 = holdout-2):\n")
        pd.set_option('display.max_columns', 30)
        pd.set_option('display.width', 160)
        pd.set_option('display.float_format', '{:.2f}'.format)
        print(df_qualified.to_string(index=False))

    print()
    print("  Output files (results/):")
    print("    selection_results_v3.csv   — top candidates from selection period")
    print("    holdout1_results_v3.csv    — holdout-1 results for those candidates")
    print("    holdout2_results_v3.csv    — holdout-2 results for those candidates")
    print("    qualified_results_v3.csv   — combos passing ALL gates in BOTH holdouts")
    print("    all_results.csv         — (unchanged — previous run, kept for reference)")
    print("    top_results.csv         — (unchanged — previous run, kept for reference)")
    print()


if __name__ == "__main__":
    main()
