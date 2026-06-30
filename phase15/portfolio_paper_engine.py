"""
Phase 15G — ATR Expansion Portfolio Paper Trading Engine
=========================================================
Strategy  : VE_3_ATR_EXPANSION  (exact research replication — no modifications)
Instruments: BTC 4H | ETH 1H | ETH 4H
RR        : 2.0
Risk/Trade : 5% of current portfolio equity (dynamic)
Starting   : $10,000 paper

Reuses all proven infrastructure from paper_trading_engine.py:
  WebSocket management, Hyperliquid connectivity, candle construction,
  state persistence, recovery logic, restart handling, logging, position mgmt.

New additions:
  Multi-instrument routing, slippage audit, drift detection, metrics tracker.
"""

import asyncio
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List

import numpy as np
import pandas as pd
import requests
import websockets

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))       # phase15/
ROOT_DIR = os.path.dirname(BASE_DIR)                         # crypto-backtester/
DATA_DIR = os.path.join(ROOT_DIR, 'data')
LIVE_DIR = os.path.join(BASE_DIR, 'live')
LOG_DIR  = os.path.join(ROOT_DIR, 'logs')
os.makedirs(LIVE_DIR, exist_ok=True)
os.makedirs(LOG_DIR,  exist_ok=True)

STATE_PATH   = os.path.join(LIVE_DIR, 'portfolio_state.json')
TRADE_LOG    = os.path.join(LIVE_DIR, 'portfolio_trade_log.csv')
METRICS_CSV  = os.path.join(LIVE_DIR, 'portfolio_metrics.csv')
SLIPPAGE_CSV = os.path.join(LIVE_DIR, 'slippage_audit.csv')
DRIFT_CSV    = os.path.join(LIVE_DIR, 'drift_alerts.csv')

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "portfolio_engine.log"), encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

# ─── Strategy Configuration (CANONICAL — must not be changed) ─────────────────
INITIAL_EQUITY   = 10_000.0
RISK_PCT_BASE    = 0.05       # 5% of equity per trade (Phase 15G spec)
RR               = 2.0        # fixed for all instruments
LEVERAGE         = 5.0
STRATEGY_VERSION = 'VE_3_ATR_EXPANSION_v1.0'

# ATR Expansion parameters (exact values from run_research_framework.py)
ATR_PERIOD      = 14
ATR_MEAN_PERIOD = 20
ATR_STOP_MULT   = 1.5   # stop = close ± 1.5*ATR14
ATR_EXP_MULT    = 1.5   # expansion: ATR14 > 1.5 * ATR14_mean(20)
DONCHIAN_WINDOW = 20    # prev_high/prev_low rolling window

# Cost model (reused from paper_trading_engine.py)
ENTRY_SLIPPAGE      = 0.0002
EXIT_SLIPPAGE_TAKER = 0.0002
ENTRY_FEE_RATE      = 0.00045
EXIT_FEE_RATE_TAKER = 0.00045
EXIT_FEE_RATE_MAKER = 0.00015   # maker for TP (limit fill)

# Circuit breakers (Phase 15E + 15F recommendations)
CB_HALVE_DD_PCT  = 0.20   # halve risk when DD > 20%
CB_STOP_DD_PCT   = 0.30   # stop new entries when DD > 30%

# Research baselines for drift detection (Phase 15D combined period)
RESEARCH_PF  = 1.40
RESEARCH_EXP = 0.246
RESEARCH_WR  = 0.444

# Drift alert thresholds (Phase 15G spec)
DRIFT_MIN_PF    = 1.00
DRIFT_MIN_EXP   = 0.00
DRIFT_MIN_WR    = 0.35
DRIFT_MAX_SLIP  = 0.50   # R-units of avg stop slippage

MIN_BARS = ATR_PERIOD + ATR_MEAN_PERIOD + DONCHIAN_WINDOW + 10   # 64 bars minimum

# ─── Instruments ──────────────────────────────────────────────────────────────
INSTRUMENTS = [
    {'symbol': 'BTC', 'timeframe': '4H', 'interval': '4h'},
    {'symbol': 'ETH', 'timeframe': '1H', 'interval': '1h'},
    {'symbol': 'ETH', 'timeframe': '4H', 'interval': '4h'},
]
# WS routing key: (coin, interval) → instrument config
INST_MAP = {(i['symbol'], i['interval']): i for i in INSTRUMENTS}


# ═══════════════════════════════════════════════════════════════════════════════
#  ATR Expansion Indicators — EXACT replica of build_signals(..., 'VE_3_ATR_EXPANSION')
#  Source: run_research_framework.py lines 373-385
# ═══════════════════════════════════════════════════════════════════════════════
def _true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df['high'], df['low'], df['close']
    return pd.concat(
        [h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1
    ).max(axis=1)


def compute_atr_expansion(df: pd.DataFrame):
    """
    Returns (long_sig, short_sig, stop_long, stop_short, atr14) as pd.Series.
    Signals are on the CLOSED bar — entry is at the next bar's open.
    """
    high, low, close = df['high'], df['low'], df['close']

    tr       = _true_range(df)
    atr14    = tr.rolling(ATR_PERIOD).mean()
    atr_mean = atr14.rolling(ATR_MEAN_PERIOD).mean()

    atr_expanded = atr14 > ATR_EXP_MULT * atr_mean
    prev_high    = high.shift(1).rolling(DONCHIAN_WINDOW).max()
    prev_low     = low.shift(1).rolling(DONCHIAN_WINDOW).min()

    long_sig  = atr_expanded & (close > prev_high)
    short_sig = atr_expanded & (close < prev_low)

    stop_long  = close - ATR_STOP_MULT * atr14   # line 383 in framework
    stop_short = close + ATR_STOP_MULT * atr14   # line 385 in framework

    return long_sig, short_sig, stop_long, stop_short, atr14


# ═══════════════════════════════════════════════════════════════════════════════
#  InstrumentState — per-instrument candle buffer + indicator state
# ═══════════════════════════════════════════════════════════════════════════════
class InstrumentState:
    def __init__(self, symbol: str, timeframe: str, interval: str):
        self.symbol    = symbol
        self.timeframe = timeframe
        self.interval  = interval
        self.key       = f"{symbol}_{timeframe}"

        self.df: Optional[pd.DataFrame] = None
        self.last_candle_ts: Optional[int] = None

        # In-progress candle accumulator
        self.live_o = self.live_h = self.live_l = self.live_c = self.live_v = None

    # ── Data loading ──────────────────────────────────────────────────────────
    def load_historical(self) -> bool:
        """Load from local CSV. Returns True if enough bars found."""
        tf_lower = self.timeframe.lower()
        candidates = [
            os.path.join(DATA_DIR, self.symbol, f"{tf_lower}.csv"),
            os.path.join(DATA_DIR, self.symbol, f"{self.timeframe}.csv"),
            os.path.join(DATA_DIR, self.symbol, f"{self.symbol}_{tf_lower}.csv"),
            os.path.join(DATA_DIR, self.symbol, f"{self.symbol}_{self.timeframe}.csv"),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    df.columns = [c.lower() for c in df.columns]
                    # Normalise timestamp
                    ts_col = next((c for c in df.columns
                                   if c in ['timestamp', 'date', 'datetime', 'ts']), None)
                    if ts_col is None:
                        continue
                    df.rename(columns={ts_col: 'timestamp'}, inplace=True)
                    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].dropna()
                    df = df.sort_values('timestamp').reset_index(drop=True)
                    self.df = df
                    log.info(f"[{self.key}] Loaded {len(df)} historical bars from {path}")
                    return len(df) >= MIN_BARS
                except Exception as e:
                    log.warning(f"[{self.key}] Failed to parse {path}: {e}")
        log.warning(f"[{self.key}] No local CSV found.")
        return False

    def backfill_from_rest(self, n_bars: int = 200) -> bool:
        """Fetch recent candles from Hyperliquid REST to ensure MIN_BARS warmup."""
        end_ms   = int(time.time() * 1000)
        bar_ms   = 3_600_000 if self.interval == '1h' else 14_400_000
        start_ms = end_ms - (n_bars + 10) * bar_ms

        url = "https://api.hyperliquid.xyz/info"
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": self.symbol,
                "interval": self.interval,
                "startTime": start_ms,
                "endTime":   end_ms,
            }
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                log.warning(f"[{self.key}] REST backfill HTTP {resp.status_code}")
                return False
            candles = resp.json()
            if not candles:
                return False
            rows = []
            for c in candles:
                rows.append({
                    'timestamp': pd.Timestamp(int(c['t']), unit='ms', tz='UTC'),
                    'open':      float(c['o']),
                    'high':      float(c['h']),
                    'low':       float(c['l']),
                    'close':     float(c['c']),
                    'volume':    float(c['v']),
                })
            df_rest = pd.DataFrame(rows)
            if self.df is not None and not self.df.empty:
                self.df = pd.concat([self.df, df_rest], ignore_index=True)
                self.df.drop_duplicates(subset=['timestamp'], inplace=True)
            else:
                self.df = df_rest
            self.df = self.df.sort_values('timestamp').reset_index(drop=True)
            log.info(f"[{self.key}] REST backfill complete. Total: {len(self.df)} bars.")
            return len(self.df) >= MIN_BARS
        except Exception as e:
            log.error(f"[{self.key}] REST backfill error: {e}")
            return False

    def fetch_closed_candle_rest(self, candle_ts_ms: int) -> Optional[dict]:
        """Try to fetch the finalized closed candle from REST."""
        url = "https://api.hyperliquid.xyz/info"
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin":      self.symbol,
                "interval":  self.interval,
                "startTime": candle_ts_ms - 1000,
                "endTime":   candle_ts_ms + 1000,
            }
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                for c in resp.json():
                    if int(c['t']) == candle_ts_ms:
                        return {
                            'timestamp': pd.Timestamp(candle_ts_ms, unit='ms', tz='UTC'),
                            'open':  float(c['o']), 'high': float(c['h']),
                            'low':   float(c['l']), 'close': float(c['c']),
                            'volume': float(c['v']),
                        }
        except Exception:
            pass
        return None

    # ── Candle processing ─────────────────────────────────────────────────────
    def process_ws_candle(self, c: dict) -> Optional[dict]:
        """
        Process a WS candle update.
        Returns a signal dict on bar close, else None.
        Signal dict: {side, stop_price, candle_close, atr14, signal_ts}
        Entry is at the OPEN of the next bar (passed in by the caller).
        """
        t = int(c['t'])
        o, h, l, cl, v = float(c['o']), float(c['h']), float(c['l']), float(c['c']), float(c['v'])

        signal = None
        is_new = (self.last_candle_ts is None or t > self.last_candle_ts)

        if is_new and self.last_candle_ts is not None:
            # Previous candle just closed — finalize it
            finalized = self.fetch_closed_candle_rest(self.last_candle_ts)
            if finalized is None:
                # Fallback to in-memory accumulated values
                finalized = {
                    'timestamp': pd.Timestamp(self.last_candle_ts, unit='ms', tz='UTC'),
                    'open':   self.live_o or o,
                    'high':   self.live_h or h,
                    'low':    self.live_l or l,
                    'close':  self.live_c or cl,
                    'volume': self.live_v or v,
                }
                log.debug(f"[{self.key}] REST miss — using in-memory fallback for {self.last_candle_ts}")
            else:
                log.debug(f"[{self.key}] REST confirmed closed candle {self.last_candle_ts}")

            # Append closed candle to DataFrame
            if self.df is not None:
                new_row = pd.DataFrame([finalized])
                self.df = pd.concat([self.df, new_row], ignore_index=True)
                self.df.drop_duplicates(subset=['timestamp'], inplace=True)
                self.df = self.df.sort_values('timestamp').reset_index(drop=True)
            else:
                self.df = pd.DataFrame([finalized])

            log.info(f"[{self.key}] Bar closed @ {finalized['timestamp']} | "
                     f"O={finalized['open']:.2f} H={finalized['high']:.2f} "
                     f"L={finalized['low']:.2f} C={finalized['close']:.2f}")

            # Compute ATR Expansion signals on closed bar
            if len(self.df) >= MIN_BARS:
                long_s, short_s, sl_long, sl_short, atr14 = compute_atr_expansion(self.df)
                last = self.df.iloc[-1]
                l_sig  = bool(long_s.iloc[-1])
                s_sig  = bool(short_s.iloc[-1])
                sl_l   = float(sl_long.iloc[-1])
                sl_s   = float(sl_short.iloc[-1])
                a14    = float(atr14.iloc[-1])

                if l_sig or s_sig:
                    signal = {
                        'side':        'long' if l_sig else 'short',
                        'stop_price':  sl_l   if l_sig else sl_s,
                        'candle_close': float(last['close']),
                        'atr14':       a14,
                        'signal_ts':   self.last_candle_ts,
                    }
                    log.info(f"[{self.key}] Signal: {'LONG' if l_sig else 'SHORT'} | "
                             f"close={last['close']:.2f} stop={sl_l if l_sig else sl_s:.2f}")

        # Update in-progress candle accumulator
        self.last_candle_ts = t
        if is_new:
            self.live_o = o; self.live_h = h; self.live_l = l
            self.live_c = cl; self.live_v = v
        else:
            self.live_h = max(self.live_h or h, h)
            self.live_l = min(self.live_l or l, l)
            self.live_c = cl; self.live_v = v

        return signal

    def recover_offline(self, backfilled_df: pd.DataFrame, positions: dict):
        """Check SL/TP for open positions against bars received during downtime."""
        if backfilled_df.empty:
            return
        relevant = [
            (tid, pos) for tid, pos in positions.items()
            if pos['symbol'] == self.symbol and pos['timeframe'] == self.timeframe
        ]
        if not relevant:
            return
        for _, row in backfilled_df.sort_values('timestamp').iterrows():
            for tid, pos in list(relevant):
                side = pos['side']
                sl   = pos['stop_price']
                tp   = pos['target_price']
                if side == 'long':
                    if float(row['low']) <= sl:
                        positions[tid]['_offline_exit'] = ('Stop Loss (Recovery)', sl, int(row['timestamp'].timestamp() * 1000))
                        relevant = [(t, p) for t, p in relevant if t != tid]
                    elif float(row['high']) >= tp:
                        positions[tid]['_offline_exit'] = ('Take Profit (Recovery)', tp, int(row['timestamp'].timestamp() * 1000))
                        relevant = [(t, p) for t, p in relevant if t != tid]
                else:
                    if float(row['high']) >= sl:
                        positions[tid]['_offline_exit'] = ('Stop Loss (Recovery)', sl, int(row['timestamp'].timestamp() * 1000))
                        relevant = [(t, p) for t, p in relevant if t != tid]
                    elif float(row['low']) <= tp:
                        positions[tid]['_offline_exit'] = ('Take Profit (Recovery)', tp, int(row['timestamp'].timestamp() * 1000))
                        relevant = [(t, p) for t, p in relevant if t != tid]


# ═══════════════════════════════════════════════════════════════════════════════
#  PortfolioState — single equity curve, multi-position manager
# ═══════════════════════════════════════════════════════════════════════════════
class PortfolioState:
    def __init__(self):
        self.equity: float        = INITIAL_EQUITY
        self.peak_equity: float   = INITIAL_EQUITY
        self.positions: Dict[str, dict] = {}    # trade_id → position
        self.closed_trades: List[dict]  = []    # summary for metrics
        self.trading_allowed: bool = True
        self.risk_halved: bool     = False
        self.last_price: Dict[str, float] = {}  # coin → latest price

    def effective_risk_pct(self) -> float:
        """Returns current risk % accounting for circuit breaker."""
        return RISK_PCT_BASE * 0.5 if self.risk_halved else RISK_PCT_BASE

    def check_circuit_breaker(self):
        """Monitor equity DD and apply circuit breakers."""
        if self.peak_equity <= 0:
            return
        dd = (self.peak_equity - self.equity) / self.peak_equity
        if dd >= CB_STOP_DD_PCT and self.trading_allowed:
            self.trading_allowed = False
            log.error(f"CIRCUIT BREAKER: DD={dd*100:.1f}% ≥ {CB_STOP_DD_PCT*100:.0f}%. "
                      "New entries HALTED. Review before resuming.")
        elif dd >= CB_HALVE_DD_PCT and not self.risk_halved:
            self.risk_halved = True
            log.warning(f"CIRCUIT BREAKER: DD={dd*100:.1f}% ≥ {CB_HALVE_DD_PCT*100:.0f}%. "
                        "Risk halved to 2.5% per trade.")
        elif dd < CB_HALVE_DD_PCT and self.risk_halved:
            self.risk_halved = False
            log.info("DD recovered below halve threshold. Restoring full risk.")

    def to_dict(self) -> dict:
        return {
            'equity':          self.equity,
            'peak_equity':     self.peak_equity,
            'positions':       self.positions,
            'trading_allowed': self.trading_allowed,
            'risk_halved':     self.risk_halved,
            'last_price':      self.last_price,
            'trade_summary': {
                'total':      len(self.closed_trades),
                'wins':       sum(1 for t in self.closed_trades if t['realized_pnl'] > 0),
                'total_r':    sum(t['realized_r'] for t in self.closed_trades),
            }
        }

    def save(self):
        try:
            with open(STATE_PATH, 'w') as f:
                json.dump(self.to_dict(), f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save state: {e}")

    def load(self):
        if not os.path.exists(STATE_PATH):
            log.info("No existing state — starting fresh.")
            return
        try:
            with open(STATE_PATH) as f:
                d = json.load(f)
            self.equity        = d.get('equity', INITIAL_EQUITY)
            self.peak_equity   = d.get('peak_equity', self.equity)
            self.positions     = d.get('positions', {})
            self.trading_allowed = d.get('trading_allowed', True)
            self.risk_halved   = d.get('risk_halved', False)
            self.last_price    = d.get('last_price', {})
            log.info(f"Loaded state — equity=${self.equity:.2f} "
                     f"open_positions={len(self.positions)}")
        except Exception as e:
            log.error(f"Failed to load state: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Position Sizing (reused from paper_trading_engine.py — adapted for 5% risk)
# ═══════════════════════════════════════════════════════════════════════════════
def calculate_position_size(entry_price: float, stop_price: float,
                             equity: float, risk_pct: float) -> tuple:
    risk_amt = equity * risk_pct
    dist     = abs(entry_price - stop_price)
    if dist < 1e-9:
        return 0.0, 0.0, 0.0
    friction = entry_price * (ENTRY_FEE_RATE + ENTRY_SLIPPAGE + EXIT_FEE_RATE_TAKER + EXIT_SLIPPAGE_TAKER)
    qty      = risk_amt / (dist + friction)
    max_qty  = (equity * LEVERAGE) / entry_price
    if qty > max_qty:
        log.warning(f"Position size capped by leverage (req={qty:.4f} max={max_qty:.4f})")
        qty = max_qty
    return round(qty, 6), dist, risk_amt


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry / Exit Execution
# ═══════════════════════════════════════════════════════════════════════════════
portfolio = PortfolioState()     # global singleton
instruments: Dict[str, InstrumentState] = {}   # key → InstrumentState


def enter_position(inst: dict, side: str, signal: dict, entry_open: float, ts_ms: int):
    """Simulate paper entry at next bar open after signal candle close."""
    if not portfolio.trading_allowed:
        log.warning(f"[{inst['symbol']} {inst['timeframe']}] Entry blocked — circuit breaker active.")
        return

    stop_price = signal['stop_price']
    risk_pct   = portfolio.effective_risk_pct()

    # Simulate slippage on entry
    if side == 'long':
        actual_entry = entry_open * (1.0 + ENTRY_SLIPPAGE)
    else:
        actual_entry = entry_open * (1.0 - ENTRY_SLIPPAGE)

    qty, dist, risk_amt = calculate_position_size(actual_entry, stop_price,
                                                   portfolio.equity, risk_pct)
    if qty <= 0:
        log.warning(f"[{inst['symbol']} {inst['timeframe']}] Zero qty — skipping entry.")
        return

    entry_fee = qty * actual_entry * ENTRY_FEE_RATE
    slip_cost = qty * abs(actual_entry - entry_open)

    # TP at RR × distance from entry to stop
    if side == 'long':
        target_price = actual_entry + RR * abs(actual_entry - stop_price)
    else:
        target_price = actual_entry - RR * abs(actual_entry - stop_price)

    trade_id = f"{inst['symbol']}_{inst['timeframe']}_{ts_ms}"
    entry_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

    position = {
        'trade_id':         trade_id,
        'symbol':           inst['symbol'],
        'timeframe':        inst['timeframe'],
        'strategy':         STRATEGY_VERSION,
        'side':             side,
        'entry_time':       entry_dt,
        'entry_price':      round(actual_entry, 6),
        'stop_price':       round(stop_price, 6),      # original research stop
        'target_price':     round(target_price, 6),
        'qty':              qty,
        'rr':               RR,
        'risk_pct':         risk_pct,
        'risk_amount':      round(risk_amt, 4),
        'entry_fee':        round(entry_fee, 4),
        'entry_slippage':   round(slip_cost, 4),
        'equity_at_entry':  round(portfolio.equity, 4),
        'signal_atr14':     round(signal['atr14'], 6),
    }

    portfolio.positions[trade_id] = position
    portfolio.peak_equity = max(portfolio.peak_equity, portfolio.equity)
    portfolio.save()

    log.info(
        f"ENTRY [{inst['symbol']} {inst['timeframe']}] {side.upper()} "
        f"| entry={actual_entry:.4f} stop={stop_price:.4f} tp={target_price:.4f} "
        f"| qty={qty:.4f} risk=${risk_amt:.2f} ({risk_pct*100:.1f}%) "
        f"| fee=${entry_fee:.2f}"
    )


def close_position(trade_id: str, exit_price_raw: float,
                   exit_reason: str, ts_ms: int):
    """Simulate paper exit. Applies slippage/fees per exit type."""
    pos = portfolio.positions.get(trade_id)
    if pos is None:
        return

    side = pos['side']
    ep   = pos['entry_price']
    sl   = pos['stop_price']
    tp   = pos['target_price']
    qty  = pos['qty']

    # Slippage model: TP → maker (no slip), SL → taker (slip)
    if 'Take Profit' in exit_reason:
        actual_exit  = exit_price_raw
        exit_slip    = 0.0
        exit_fee     = qty * exit_price_raw * EXIT_FEE_RATE_MAKER
    else:
        if side == 'long':
            actual_exit = exit_price_raw * (1.0 - EXIT_SLIPPAGE_TAKER)
        else:
            actual_exit = exit_price_raw * (1.0 + EXIT_SLIPPAGE_TAKER)
        exit_slip = qty * abs(actual_exit - exit_price_raw)
        exit_fee  = qty * exit_price_raw * EXIT_FEE_RATE_TAKER

    # Net PnL
    if side == 'long':
        gross_pnl = (actual_exit - ep) * qty
    else:
        gross_pnl = (ep - actual_exit) * qty
    net_pnl = gross_pnl - pos['entry_fee'] - exit_fee - pos['entry_slippage'] - exit_slip

    equity_before     = portfolio.equity
    portfolio.equity  = max(0.0, portfolio.equity + net_pnl)
    portfolio.peak_equity = max(portfolio.peak_equity, portfolio.equity)

    # R-multiple
    initial_risk  = qty * abs(ep - sl) if abs(ep - sl) > 0 else 1e-9
    realized_r    = net_pnl / initial_risk

    exit_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
    entry_dt = pos['entry_time']
    duration_h = (ts_ms - int(trade_id.split('_')[-1])) / 3_600_000

    record = {
        'trade_id':       trade_id,
        'entry_time':     entry_dt,
        'exit_time':      exit_dt,
        'symbol':         pos['symbol'],
        'timeframe':      pos['timeframe'],
        'strategy':       pos['strategy'],
        'side':           side,
        'entry_price':    round(ep, 6),
        'stop_price':     round(sl, 6),
        'target_price':   round(tp, 6),
        'exit_price':     round(actual_exit, 6),
        'exit_reason':    exit_reason,
        'qty':            qty,
        'risk_amount':    pos['risk_amount'],
        'realized_pnl':   round(net_pnl, 4),
        'realized_r':     round(realized_r, 4),
        'duration_hours': round(duration_h, 2),
        'entry_fee':      round(pos['entry_fee'], 4),
        'exit_fee':       round(exit_fee, 4),
        'entry_slippage': round(pos['entry_slippage'], 4),
        'exit_slippage':  round(exit_slip, 4),
        'equity_before':  round(equity_before, 4),
        'equity_after':   round(portfolio.equity, 4),
    }

    # Write to trade log
    _write_csv_row(TRADE_LOG, record)

    # Slippage audit (for stop-loss exits only — Phase 15F mandate)
    if 'Stop Loss' in exit_reason:
        _write_slippage_audit(pos, actual_exit, exit_price_raw, realized_r, duration_h)

    # Update portfolio metrics and drift detection
    portfolio.closed_trades.append(record)
    _update_metrics()
    _check_drift()

    # Remove position
    del portfolio.positions[trade_id]
    portfolio.check_circuit_breaker()
    portfolio.save()

    log.info(
        f"EXIT [{pos['symbol']} {pos['timeframe']}] {side.upper()} — {exit_reason} "
        f"| exit={actual_exit:.4f} | PnL=${net_pnl:.2f} R={realized_r:.2f} "
        f"| equity=${portfolio.equity:.2f}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Price-based SL/TP Check (real-time from trades channel)
# ═══════════════════════════════════════════════════════════════════════════════
def check_stops_live(coin: str, price: float, ts_ms: int):
    """Check all open positions for this coin against latest price."""
    portfolio.last_price[coin] = price
    for trade_id, pos in list(portfolio.positions.items()):
        if pos['symbol'] != coin:
            continue
        side = pos['side']
        sl   = pos['stop_price']
        tp   = pos['target_price']
        if side == 'long':
            if price <= sl:
                close_position(trade_id, sl, 'Stop Loss', ts_ms)
            elif price >= tp:
                close_position(trade_id, tp, 'Take Profit', ts_ms)
        else:
            if price >= sl:
                close_position(trade_id, sl, 'Stop Loss', ts_ms)
            elif price <= tp:
                close_position(trade_id, tp, 'Take Profit', ts_ms)


def check_stops_candle(symbol: str, timeframe: str, hi: float, lo: float, ts_ms: int):
    """Check positions on candle close — SL first (conservative)."""
    for trade_id, pos in list(portfolio.positions.items()):
        if pos['symbol'] != symbol or pos['timeframe'] != timeframe:
            continue
        side = pos['side']
        sl   = pos['stop_price']
        tp   = pos['target_price']
        if side == 'long':
            if lo <= sl:
                close_position(trade_id, sl, 'Stop Loss (Candle)', ts_ms)
            elif hi >= tp:
                close_position(trade_id, tp, 'Take Profit (Candle)', ts_ms)
        else:
            if hi >= sl:
                close_position(trade_id, sl, 'Stop Loss (Candle)', ts_ms)
            elif lo <= tp:
                close_position(trade_id, tp, 'Take Profit (Candle)', ts_ms)


# ═══════════════════════════════════════════════════════════════════════════════
#  CSV Writers
# ═══════════════════════════════════════════════════════════════════════════════
def _write_csv_row(path: str, record: dict):
    file_exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, 'a', newline='', encoding='utf-8') as f:
        if not file_exists:
            f.write(','.join(str(k) for k in record.keys()) + '\n')
        f.write(','.join(str(v) for v in record.values()) + '\n')


def _write_slippage_audit(pos: dict, actual_exit: float,
                           expected_stop: float, realized_r: float,
                           duration_h: float):
    """Write one row to slippage_audit.csv for every Stop Loss exit."""
    side = pos['side']
    ep   = pos['entry_price']
    sl   = pos['stop_price']

    # Slippage: for long, actual_exit < expected_stop means extra loss
    if side == 'long':
        slippage_pct = (actual_exit - expected_stop) / expected_stop   # negative = worse
    else:
        slippage_pct = (expected_stop - actual_exit) / expected_stop   # negative = worse

    sl_pct_at_entry = abs(ep - sl) / ep if ep > 0 else 0.0
    slippage_r = abs(slippage_pct) / sl_pct_at_entry if sl_pct_at_entry > 1e-9 else 0.0

    # Rolling 20-trade average slippage_r
    recent_slips = [r.get('stop_slippage_r', 0)
                    for r in portfolio.closed_trades[-20:]
                    if 'Stop Loss' in r.get('exit_reason', '')]
    rolling_avg = float(np.mean(recent_slips)) if recent_slips else 0.0

    record = {
        'trade_id':              pos['trade_id'],
        'symbol':                pos['symbol'],
        'timeframe':             pos['timeframe'],
        'exit_type':             'Stop Loss',
        'expected_stop_price':   round(expected_stop, 6),
        'actual_exit_price':     round(actual_exit, 6),
        'stop_slippage_pct':     round(slippage_pct * 100, 4),   # %
        'stop_slippage_r':       round(slippage_r, 4),
        'rolling_20_avg_slip_r': round(rolling_avg, 4),
        'duration_hours':        round(duration_h, 2),
    }
    _write_csv_row(SLIPPAGE_CSV, record)


def _update_metrics():
    """Recompute and append one row to portfolio_metrics.csv."""
    trades = portfolio.closed_trades
    if not trades:
        return

    n      = len(trades)
    wins   = [t for t in trades if t['realized_pnl'] > 0]
    losses = [t for t in trades if t['realized_pnl'] <= 0]
    wr     = len(wins) / n
    rs     = [t['realized_r'] for t in trades]
    avg_r  = float(np.mean(rs))

    pnl_wins   = sum(t['realized_pnl'] for t in wins)
    pnl_losses = abs(sum(t['realized_pnl'] for t in losses))
    pf = pnl_wins / pnl_losses if pnl_losses > 0 else 999.9

    win_rs   = [t['realized_r'] for t in wins]
    loss_rs  = [abs(t['realized_r']) for t in losses]
    avg_wr   = float(np.mean(win_rs))   if win_rs   else 0.0
    avg_lr   = float(np.mean(loss_rs))  if loss_rs  else 0.0
    exp      = (wr * avg_wr) - ((1 - wr) * avg_lr)

    # Approximate Sharpe from R-multiple distribution
    sharpe_approx = (np.mean(rs) / np.std(rs) * np.sqrt(52)) if np.std(rs) > 0 else 0.0

    # Drawdown tracking
    eq_series = [INITIAL_EQUITY]
    for t in trades:
        eq_series.append(eq_series[-1] + t['realized_pnl'])
    eq_arr    = np.array(eq_series)
    run_max   = np.maximum.accumulate(eq_arr)
    dd_arr    = (run_max - eq_arr) / run_max
    max_dd    = float(dd_arr.max()) * 100.0
    cur_dd    = float(dd_arr[-1]) * 100.0

    record = {
        'timestamp':       datetime.now(timezone.utc).isoformat(),
        'equity':          round(portfolio.equity, 2),
        'total_trades':    n,
        'wins':            len(wins),
        'losses':          len(losses),
        'win_rate':        round(wr * 100, 2),
        'profit_factor':   round(pf, 3),
        'expectancy':      round(exp, 4),
        'sharpe_approx':   round(sharpe_approx, 3),
        'max_drawdown':    round(max_dd, 2),
        'current_drawdown': round(cur_dd, 2),
        'avg_R':           round(avg_r, 4),
    }
    _write_csv_row(METRICS_CSV, record)


def _check_drift():
    """Compare live metrics to research baseline. Write alerts when thresholds breached."""
    trades = portfolio.closed_trades
    if len(trades) < 10:    # Minimum sample for meaningful comparison
        return

    n      = len(trades)
    wins   = [t for t in trades if t['realized_pnl'] > 0]
    wr     = len(wins) / n
    rs     = [t['realized_r'] for t in trades]
    win_rs = [t['realized_r'] for t in trades if t['realized_pnl'] > 0]
    los_rs = [abs(t['realized_r']) for t in trades if t['realized_pnl'] <= 0]
    avg_wr = float(np.mean(win_rs)) if win_rs else 0.0
    avg_lr = float(np.mean(los_rs)) if los_rs else 0.0
    exp    = (wr * avg_wr) - ((1 - wr) * avg_lr)

    pnl_w = sum(t['realized_pnl'] for t in wins)
    pnl_l = abs(sum(t['realized_pnl'] for t in trades if t['realized_pnl'] <= 0))
    pf    = pnl_w / pnl_l if pnl_l > 0 else 999.9

    # Average stop slippage from audit
    sl_rows = [t for t in trades if 'Stop Loss' in t.get('exit_reason', '')]
    avg_slip_r = 0.0
    if sl_rows and os.path.exists(SLIPPAGE_CSV):
        try:
            sdf = pd.read_csv(SLIPPAGE_CSV)
            if 'stop_slippage_r' in sdf.columns:
                avg_slip_r = float(sdf['stop_slippage_r'].mean())
        except Exception:
            pass

    alerts = []
    now = datetime.now(timezone.utc).isoformat()
    if pf < DRIFT_MIN_PF:
        alerts.append({'timestamp': now, 'metric': 'profit_factor',
                       'live': round(pf, 3), 'threshold': DRIFT_MIN_PF,
                       'baseline': RESEARCH_PF, 'severity': 'HIGH'})
    if exp < DRIFT_MIN_EXP:
        alerts.append({'timestamp': now, 'metric': 'expectancy',
                       'live': round(exp, 4), 'threshold': DRIFT_MIN_EXP,
                       'baseline': RESEARCH_EXP, 'severity': 'HIGH'})
    if wr < DRIFT_MIN_WR:
        alerts.append({'timestamp': now, 'metric': 'win_rate',
                       'live': round(wr * 100, 1), 'threshold': DRIFT_MIN_WR * 100,
                       'baseline': RESEARCH_WR * 100, 'severity': 'MEDIUM'})
    if avg_slip_r > DRIFT_MAX_SLIP:
        alerts.append({'timestamp': now, 'metric': 'avg_stop_slippage_r',
                       'live': round(avg_slip_r, 4), 'threshold': DRIFT_MAX_SLIP,
                       'baseline': 0.0, 'severity': 'HIGH'})

    for alert in alerts:
        _write_csv_row(DRIFT_CSV, alert)
        log.warning(f"DRIFT ALERT [{alert['severity']}] {alert['metric']}="
                    f"{alert['live']} (threshold={alert['threshold']} baseline={alert['baseline']})")


# ═══════════════════════════════════════════════════════════════════════════════
#  WebSocket Handlers
# ═══════════════════════════════════════════════════════════════════════════════
async def handle_candle_msg(data: dict):
    """Route WS candle update to the correct InstrumentState."""
    if isinstance(data, list):
        for item in data:
            await _dispatch_candle(item)
    else:
        await _dispatch_candle(data)


async def _dispatch_candle(c: dict):
    coin    = c.get('s', '')
    interv  = c.get('i', '')
    key     = (coin, interv)
    inst_cfg = INST_MAP.get(key)
    if inst_cfg is None:
        return

    inst_key  = f"{coin}_{inst_cfg['timeframe']}"
    inst_state = instruments.get(inst_key)
    if inst_state is None:
        return

    # Get the open price of the NEW in-progress candle (entry price for new signals)
    entry_open = float(c['o'])   # open of the just-received (new) candle

    signal = inst_state.process_ws_candle(c)

    if signal:
        # Candle-level SL/TP check on the bar that just closed
        hi = float(inst_state.df.iloc[-1]['high']) if inst_state.df is not None else 0.0
        lo = float(inst_state.df.iloc[-1]['low'])  if inst_state.df is not None else 0.0
        check_stops_candle(inst_cfg['symbol'], inst_cfg['timeframe'],
                           hi, lo, inst_state.last_candle_ts)

        # Enter new position on bar open of the next candle
        enter_position(inst_cfg, signal['side'], signal, entry_open,
                       int(c['t']))
    else:
        # Still check candle SL/TP on every bar close even without a new signal
        if inst_state.df is not None and len(inst_state.df) > 0:
            prev = inst_state.df.iloc[-1]
            check_stops_candle(inst_cfg['symbol'], inst_cfg['timeframe'],
                               float(prev['high']), float(prev['low']),
                               int(c['t']))


def handle_trades_msg(data: list):
    """Route trade price updates to stop/TP monitor."""
    if not isinstance(data, list) or len(data) == 0:
        return
    latest = data[-1]
    coin   = latest.get('coin', latest.get('s', ''))
    try:
        price  = float(latest.get('px', latest.get('p', 0)))
        ts_ms  = int(latest.get('time', latest.get('t', time.time() * 1000)))
    except (ValueError, TypeError):
        return
    if price > 0 and coin:
        check_stops_live(coin, price, ts_ms)


# ═══════════════════════════════════════════════════════════════════════════════
#  Ping / Heartbeat
# ═══════════════════════════════════════════════════════════════════════════════
async def ping_loop(ws):
    while True:
        try:
            await asyncio.sleep(30)
            if ws.state == websockets.State.OPEN:
                await ws.send(json.dumps({"method": "ping"}))
                log.debug("heartbeat_sent")
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Ping error: {e}")
            break


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════
async def main():
    global instruments

    log.info("=" * 70)
    log.info("  Phase 15G — ATR Expansion Portfolio Paper Trading Engine")
    inst_names = [i['symbol'] + ' ' + i['timeframe'] for i in INSTRUMENTS]
    log.info(f"  Instruments: {inst_names}")
    log.info(f"  Risk/Trade : {RISK_PCT_BASE*100:.0f}% | RR: {RR} | Leverage: {LEVERAGE}x")
    log.info("=" * 70)

    # 1. Load persisted state
    portfolio.load()

    # 2. Initialise per-instrument candle states + historical warmup
    for inst in INSTRUMENTS:
        key  = f"{inst['symbol']}_{inst['timeframe']}"
        ist  = InstrumentState(inst['symbol'], inst['timeframe'], inst['interval'])
        ok   = ist.load_historical()
        if not ok:
            log.info(f"[{key}] Insufficient local history — backfilling from REST...")
            ok = ist.backfill_from_rest(300)
        if not ok:
            log.error(f"[{key}] Cannot obtain sufficient history (need {MIN_BARS} bars). "
                      "Engine will wait for live data to accumulate.")
        instruments[key] = ist
        log.info(f"[{key}] Ready — {len(ist.df) if ist.df is not None else 0} bars loaded.")

    # 3. Recover positions that may have hit SL/TP during downtime
    for inst in INSTRUMENTS:
        key = f"{inst['symbol']}_{inst['timeframe']}"
        ist = instruments[key]
        if ist.df is not None and not ist.df.empty and portfolio.positions:
            # Use any backfilled bars as recovery data
            ist.recover_offline(ist.df.tail(50), portfolio.positions)

    # Process any offline exits
    for trade_id, pos in list(portfolio.positions.items()):
        if '_offline_exit' in pos:
            reason, exit_px, exit_ts = pos.pop('_offline_exit')
            log.info(f"Processing offline exit for {trade_id}: {reason} @ {exit_px}")
            close_position(trade_id, exit_px, reason, exit_ts)

    # 4. WebSocket connection loop (with exponential backoff — reused from paper_trading_engine.py)
    backoff = 1
    while True:
        try:
            log.info("Connecting to Hyperliquid WebSocket...")
            async with websockets.connect("wss://api.hyperliquid.xyz/ws",
                                           ping_interval=None) as ws:
                backoff = 1
                log.info("WebSocket connected.")

                # Subscribe to all instrument candle feeds
                for inst in INSTRUMENTS:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {
                            "type":     "candle",
                            "coin":     inst['symbol'],
                            "interval": inst['interval'],
                        }
                    }))
                    log.info(f"Subscribed: {inst['symbol']} {inst['interval']} candles")

                # Subscribe to price feeds for each unique coin
                for coin in {i['symbol'] for i in INSTRUMENTS}:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "trades", "coin": coin}
                    }))
                    log.info(f"Subscribed: {coin} trades")

                ping_task = asyncio.create_task(ping_loop(ws))

                async for message in ws:
                    msg     = json.loads(message)
                    channel = msg.get("channel")
                    data    = msg.get("data")

                    if channel == "pong":
                        log.debug("heartbeat_received")

                    elif channel == "candle" and data:
                        await handle_candle_msg(data)

                    elif channel == "trades" and data:
                        handle_trades_msg(data if isinstance(data, list) else [data])

                ping_task.cancel()

        except Exception as e:
            log.error(f"WebSocket error: {e}. Reconnecting in {backoff:.1f}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60) + random.uniform(0, 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        portfolio.save()
        log.info("Engine stopped by user. State saved.")
