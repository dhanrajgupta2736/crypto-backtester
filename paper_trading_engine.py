import asyncio
import json
import logging
import os
import random
import time
import math
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
import websockets

# Suppress pandas downcasting warnings
pd.set_option('future.no_silent_downcasting', True)

# Configure Logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/engine.log"),
        logging.StreamHandler()
    ]
)

# Configuration & Constants
COIN = "TAO"
INTERVAL = "1H"
CSV_PATH = os.path.join("data", "TAO", "TAO_1H.csv")
STATE_PATH = os.path.join("results", "engine_state.json")
LOG_PATH = os.path.join("results", "live_trades.csv")

# Fee & Slippage Schedule
ENTRY_SLIPPAGE = 0.0002  # 0.02%
EXIT_SLIPPAGE_TAKER = 0.0002  # 0.02%
ENTRY_FEE_RATE = 0.00045  # 0.045% Taker
EXIT_FEE_RATE_TAKER = 0.00045  # 0.045% Taker
EXIT_FEE_RATE_MAKER = 0.00015  # 0.015% Maker

# Risk Sizing
RISK_PER_TRADE_PCT = 0.02  # 2%
LEVERAGE = 5.0

# Indicators Config
EMA_LENGTH = 200
ATR_PERIOD = 10
ATR_MULTIPLIER = 3.0
RR_VALUE = 3.0

class EngineState:
    def __init__(self):
        self.balance = 10000.0  # Default starting paper equity
        self.position = None    # None or dict
        self.daily_start_equity = 10000.0
        self.daily_start_date = ""
        self.consecutive_losses = 0
        self.last_signal_ts = None
        self.is_paused = False
        self.pause_reason = ""
        self.websocket_connected = False
        self.last_price = 0.0
        self.last_candle_ts = None
        self.indicators = {}

    def to_dict(self):
        return {
            "balance": self.balance,
            "position": self.position,
            "daily_start_equity": self.daily_start_equity,
            "daily_start_date": self.daily_start_date,
            "consecutive_losses": self.consecutive_losses,
            "last_signal_ts": self.last_signal_ts,
            "is_paused": self.is_paused,
            "pause_reason": self.pause_reason,
            "websocket_connected": self.websocket_connected,
            "last_price": self.last_price,
            "last_candle_ts": self.last_candle_ts,
            "indicators": self.indicators
        }

    def from_dict(self, d):
        self.balance = d.get("balance", 10000.0)
        self.position = d.get("position", None)
        self.daily_start_equity = d.get("daily_start_equity", 10000.0)
        self.daily_start_date = d.get("daily_start_date", "")
        self.consecutive_losses = d.get("consecutive_losses", 0)
        self.last_signal_ts = d.get("last_signal_ts", None)
        self.is_paused = d.get("is_paused", False)
        self.pause_reason = d.get("pause_reason", "")
        self.websocket_connected = d.get("websocket_connected", False)
        self.last_price = d.get("last_price", 0.0)
        self.last_candle_ts = d.get("last_candle_ts", None)
        self.indicators = d.get("indicators", {})

    def save(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        try:
            with open(STATE_PATH, "w") as f:
                json.dump(self.to_dict(), f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save state file: {e}")

    def load(self):
        if os.path.exists(STATE_PATH):
            try:
                with open(STATE_PATH, "r") as f:
                    d = json.load(f)
                    self.from_dict(d)
                logging.info(f"Loaded existing state. Balance: ${self.balance:.2f}, Position: {self.position}")
            except Exception as e:
                logging.error(f"Failed to load state file: {e}")

# Global Engine State
state = EngineState()

# Indicator Calculation Functions
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def true_range(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    return pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    high, low, close = df["high"], df["low"], df["close"]
    
    # EMA200
    df["ema200"] = ema(close, EMA_LENGTH)
    
    # ATR 10
    tr = true_range(df)
    df["atr"] = tr.rolling(window=ATR_PERIOD).mean()
    
    hl2 = (high + low) / 2
    atr_val = df["atr"].values
    close_val = close.values
    hl2_val = hl2.values
    n = len(df)
    
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
        
        # Band calculations
        upperband[i] = basic_ub if (basic_ub < upperband[i-1] or close_val[i-1] > upperband[i-1]) else upperband[i-1]
        lowerband[i] = basic_lb if (basic_lb > lowerband[i-1] or close_val[i-1] < lowerband[i-1]) else lowerband[i-1]
        
        # Trend detection
        if close_val[i] > upperband[i-1]:
            in_uptrend[i] = True
        elif close_val[i] < lowerband[i-1]:
            in_uptrend[i] = False
        else:
            in_uptrend[i] = in_uptrend[i-1]
            
    df["upperband"] = upperband
    df["lowerband"] = lowerband
    df["uptrend"] = in_uptrend
    
    # Trend change flips
    df["flip_up"] = df["uptrend"] & (~df["uptrend"].shift(1).fillna(True))
    df["flip_dn"] = (~df["uptrend"]) & df["uptrend"].shift(1).fillna(False)
    
    # Signals
    df["long_sig"] = df["flip_up"] & (close > df["ema200"])
    df["short_sig"] = df["flip_dn"] & (close < df["ema200"])
    
    # Stop Losses
    df["stop_loss_long"] = df["lowerband"].where(df["lowerband"] < close, close * 0.99)
    df["stop_loss_short"] = df["upperband"].where(df["upperband"] > close, close * 1.01)
    
    df["exit_long"] = df["flip_dn"]
    df["exit_short"] = df["flip_up"]
    
    return df

# Hyperliquid HTTP Backfill
def fetch_recent_candles(start_time_ms: int) -> list:
    url = "https://api.hyperliquid.xyz/info"
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": COIN,
            "interval": "1h",
            "startTime": start_time_ms + 1000,
            "endTime": int(time.time() * 1000)
        }
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Failed to fetch recent candles from REST: {e}")
    return []

# DataFrame Loading & Warm-up
def load_and_backfill_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    logging.info(f"Loading historical data from {CSV_PATH}...")
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Missing historical database at {CSV_PATH}")
        
    df = pd.read_csv(CSV_PATH)
    # Convert 'Date' string to milliseconds timestamp
    df["timestamp"] = pd.to_datetime(df["Date"], utc=True).astype(int) // 10**6
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
    })
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    
    # Identify gaps and backfill using REST API
    last_ts = int(df["timestamp"].max())
    logging.info(f"Last CSV candle: {df['Date'].iloc[-1] if 'Date' in df.columns else datetime.fromtimestamp(last_ts/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    df_backfilled = pd.DataFrame()
    recent_candles = fetch_recent_candles(last_ts)
    if recent_candles:
        logging.info(f"Backfilled {len(recent_candles)} candles from REST API.")
        backfilled_rows = []
        for c in recent_candles:
            backfilled_rows.append({
                "timestamp": int(c["t"]),
                "open": float(c["o"]),
                "high": float(c["h"]),
                "low": float(c["l"]),
                "close": float(c["c"]),
                "volume": float(c["v"])
            })
        df_backfilled = pd.DataFrame(backfilled_rows)
        # Drop duplicates and sort
        df = pd.concat([df, df_backfilled], ignore_index=True)
        df.drop_duplicates(subset=["timestamp"], inplace=True)
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # Save backfilled rows to CSV to maintain integrity
        with open(CSV_PATH, "a") as f:
            for c in recent_candles:
                dt_str = datetime.fromtimestamp(c["t"]/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{dt_str},{c['o']},{c['h']},{c['l']},{c['c']},{c['v']}\n")
    else:
        logging.info("No gaps found to backfill.")
        
    return df, df_backfilled

# Journals
def write_trade_journal(record: dict):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    header = "timestamp,symbol,side,entry,stop,target,exit,r_multiple,pnl,fees,slippage,equity_before,equity_after,strategy_version\n"
    file_exists = os.path.exists(LOG_PATH)
    
    # Check if empty
    if file_exists and os.path.getsize(LOG_PATH) == 0:
        file_exists = False
        
    try:
        with open(LOG_PATH, "a") as f:
            if not file_exists:
                f.write(header)
            row = (
                f"{record['timestamp']},{record['symbol']},{record['side']},"
                f"{record['entry']:.4f},{record['stop']:.4f},{record['target']:.4f},"
                f"{record['exit']:.4f},{record['r_multiple']:.4f},{record['pnl']:.2f},"
                f"{record['fees']:.4f},{record['slippage']:.4f},"
                f"{record['equity_before']:.2f},{record['equity_after']:.2f},"
                f"{record.get('strategy_version', 'v1.0')}\n"
            )
            f.write(row)
        logging.info(f"Journaled trade exit: {record['side'].upper()} PnL: ${record['pnl']:.2f}")

    except Exception as e:
        logging.error(f"Failed to write trade journal: {e}")

# Risk & Order Sizing Engine
def calculate_position_size(ep: float, sl: float, equity: float) -> tuple:
    """
    Returns (position_size_qty, stop_distance, expected_risk_amt)
    Size = Risk_Amt / (dist + friction)
    """
    risk_amt = equity * RISK_PER_TRADE_PCT
    dist = abs(ep - sl)
    
    # Friction: 0.045% Taker entry fee + 0.02% entry slippage + 0.045% Taker exit fee + 0.02% exit slippage = 0.13% total
    friction_per_unit = ep * (ENTRY_FEE_RATE + ENTRY_SLIPPAGE + EXIT_FEE_RATE_TAKER + EXIT_SLIPPAGE_TAKER)
    
    qty = risk_amt / (dist + friction_per_unit)
    
    # Cap size at maximum leverage
    max_qty = (equity * LEVERAGE) / ep
    if qty > max_qty:
        qty = max_qty
        logging.warning(f"Position size capped by max leverage of {LEVERAGE}x (requested: {qty:.4f}, max: {max_qty:.4f})")
        
    return round(qty, 4), dist, risk_amt

# Safety Guards
def check_safety_guards(entry_ts: int, side: str, entry_price: float, sl: float) -> str | None:
    """Returns reject reason string if blocked, else None"""
    if state.is_paused:
        return f"Trading is currently PAUSED: {state.pause_reason}"
        
    if state.position is not None:
        return "Position limit exceeded (Max 1 open position)"
        
    # Check Daily Drawdown
    current_utc_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.daily_start_date != current_utc_date:
        state.daily_start_date = current_utc_date
        state.daily_start_equity = state.balance
        state.save()
        logging.info(f"New trading day. Reset daily start equity to: ${state.daily_start_equity:.2f}")
        
    equity = state.balance
    drawdown_pct = (state.daily_start_equity - equity) / state.daily_start_equity * 100
    if drawdown_pct >= 5.0:
        state.is_paused = True
        state.pause_reason = f"Daily drawdown limit exceeded ({drawdown_pct:.2f}%)"
        state.save()
        return f"Daily Drawdown Guard activated: {state.pause_reason}"
        
    # Check Consecutive Losses
    if state.consecutive_losses >= 5:
        state.is_paused = True
        state.pause_reason = "5 consecutive losses reached"
        state.save()
        return f"Consecutive Losses Guard activated: {state.pause_reason}"
        
    # Check Duplicate Signal
    if state.last_signal_ts == entry_ts:
        return f"Duplicate signal protection activated for candle timestamp {entry_ts}"
        
    return None

# Broker Order Simulator
def execute_paper_entry(side: str, entry_price: float, sl: float, candle_ts: int):
    # Calculate position size
    qty, dist, risk_amt = calculate_position_size(entry_price, sl, state.balance)
    if qty <= 0:
        logging.error("Calculated size is <= 0. Skipping entry.")
        return
        
    # Simulated execution with slippage
    actual_entry = entry_price * (1.0 + ENTRY_SLIPPAGE) if side == "long" else entry_price * (1.0 - ENTRY_SLIPPAGE)
    slippage_cost = qty * abs(actual_entry - entry_price)
    fee_amt = qty * entry_price * ENTRY_FEE_RATE
    
    # Profit target (1:3 risk reward based on stop distance)
    tp = actual_entry + 3.0 * dist if side == "long" else actual_entry - 3.0 * dist
    
    state.position = {
        "side": side,
        "entry": actual_entry,
        "sl": sl,
        "tp": tp,
        "qty": qty,
        "entry_ts": candle_ts,
        "entry_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "initial_sl": sl,
        "moved_to_be": False,
        "expected_fill": entry_price,
        "entry_fee": fee_amt,
        "entry_slippage": slippage_cost
    }
    
    state.last_signal_ts = candle_ts
    state.save()
    
    logging.info(
        f"Executed paper entry: {side.upper()} at {actual_entry:.4f} (expected: {entry_price:.4f}), "
        f"Qty: {qty}, SL: {sl:.4f}, TP: {tp:.4f}, Est Fee: ${fee_amt:.4f}, Est Slippage: ${slippage_cost:.4f}"
    )

def execute_paper_exit(exit_price: float, exit_reason: str, exit_time_ms: int):
    if state.position is None:
        return
        
    pos = state.position
    side = pos["side"]
    qty = pos["qty"]
    ep = pos["entry"]
    initial_sl = pos["initial_sl"]
    
    # Calculate exit slippage and fees based on execution type
    if exit_reason == "Take Profit":
        # Maker fill
        actual_exit = exit_price
        exit_slippage = 0.0
        exit_fee = qty * exit_price * EXIT_FEE_RATE_MAKER
    else:
        # Taker fill (Stop Loss, indicator flip, or manual exit)
        actual_exit = exit_price * (1.0 - EXIT_SLIPPAGE_TAKER) if side == "long" else exit_price * (1.0 + EXIT_SLIPPAGE_TAKER)
        exit_slippage = qty * abs(actual_exit - exit_price)
        exit_fee = qty * exit_price * EXIT_FEE_RATE_TAKER
        
    # Calculate trade PnL
    entry_value = qty * ep
    exit_value = qty * actual_exit
    
    # Net PnL = (exit_val - entry_val) - entry_fees - exit_fees
    if side == "long":
        trade_pnl = (exit_value - entry_value) - pos["entry_fee"] - exit_fee
    else:
        trade_pnl = (entry_value - exit_value) - pos["entry_fee"] - exit_fee
        
    total_fees = pos["entry_fee"] + exit_fee
    total_slippage = pos["entry_slippage"] + exit_slippage
    
    equity_before = state.balance
    state.balance = max(0.0, state.balance + trade_pnl)
    equity_after = state.balance
    
    # Consecutive losses check
    if trade_pnl <= 0:
        state.consecutive_losses += 1
    else:
        state.consecutive_losses = 0
        
    # Calculate R-multiple based on initial planned risk
    initial_risk = pos["entry_fee"] + pos["entry_slippage"] + qty * abs(ep - initial_sl)
    r_multiple = trade_pnl / initial_risk if initial_risk > 0 else 0.0
    
    # Log trade details to journal
    exit_date_str = datetime.fromtimestamp(exit_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "timestamp": exit_date_str,
        "symbol": COIN,
        "side": side,
        "entry": ep,
        "stop": pos["sl"],
        "target": pos["tp"],
        "exit": actual_exit,
        "r_multiple": r_multiple,
        "pnl": trade_pnl,
        "fees": total_fees,
        "slippage": total_slippage,
        "equity_before": equity_before,
        "equity_after": equity_after
    }
    write_trade_journal(record)
    
    logging.info(
        f"Closed paper position ({exit_reason}): {side.upper()} exit price: {actual_exit:.4f} (expected: {exit_price:.4f}), "
        f"Net PnL: ${trade_pnl:.2f}, R-multiple: {r_multiple:.2f}, Balance: ${state.balance:.2f}"
    )
    
    # Clear position and save state
    state.position = None
    state.save()
    
    # Re-evaluate safety guards post-trade
    check_guards_post_trade()

def check_guards_post_trade():
    equity = state.balance
    current_utc_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.daily_start_date == current_utc_date:
        drawdown_pct = (state.daily_start_equity - equity) / state.daily_start_equity * 100
        if drawdown_pct >= 5.0:
            state.is_paused = True
            state.pause_reason = f"Daily drawdown limit exceeded ({drawdown_pct:.2f}%)"
            logging.error(f"Daily drawdown limit exceeded post-trade. Trading PAUSED.")
            
    if state.consecutive_losses >= 5:
        state.is_paused = True
        state.pause_reason = "5 consecutive losses reached"
        logging.error("5 consecutive losses reached. Trading PAUSED.")
        
    state.save()

# Main Event Handlers
async def handle_candle_update(candle_dict: dict, df: pd.DataFrame) -> pd.DataFrame:
    t = int(candle_dict["t"])
    o = float(candle_dict["o"])
    h = float(candle_dict["h"])
    l = float(candle_dict["l"])
    c = float(candle_dict["c"])
    v = float(candle_dict["v"])
    
    # If it's a new hourly candle
    if state.last_candle_ts is None or t > state.last_candle_ts:
        if state.last_candle_ts is not None:
            # We had an in-progress candle. Retrieve finalized values from REST if possible, fallback to in-memory
            rest_candles = fetch_recent_candles(state.last_candle_ts - 1000)
            finalized_candle = None
            if rest_candles:
                for rc in rest_candles:
                    if int(rc["t"]) == state.last_candle_ts:
                        finalized_candle = {
                            "timestamp": state.last_candle_ts,
                            "open": float(rc["o"]),
                            "high": float(rc["h"]),
                            "low": float(rc["l"]),
                            "close": float(rc["c"]),
                            "volume": float(rc["v"])
                        }
                        logging.info(f"Retrieved exchange-finalized closed candle for timestamp {state.last_candle_ts} from REST API.")
                        break
            
            if finalized_candle is None:
                # Fallback to in-memory in-progress values if REST fails
                finalized_candle = {
                    "timestamp": state.last_candle_ts,
                    "open": float(state.indicators.get("open")),
                    "high": float(state.indicators.get("high")),
                    "low": float(state.indicators.get("low")),
                    "close": float(state.indicators.get("close")),
                    "volume": float(state.indicators.get("volume"))
                }
                logging.info(f"REST candle snapshot query returned no match. Using in-memory fallback closed candle for timestamp {state.last_candle_ts}.")
            
            new_closed_row = finalized_candle
            logging.info(f"Hourly candle closed. Open time: {datetime.fromtimestamp(state.last_candle_ts/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} Close price: {new_closed_row['close']}")
            
            # Append to memory DataFrame and save to CSV
            df_new_row = pd.DataFrame([new_closed_row])
            df = pd.concat([df, df_new_row], ignore_index=True)
            df.drop_duplicates(subset=["timestamp"], inplace=True)
            df.sort_values("timestamp", inplace=True)
            df.reset_index(drop=True, inplace=True)
            
            with open(CSV_PATH, "a") as f:
                dt_str = datetime.fromtimestamp(state.last_candle_ts/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{dt_str},{new_closed_row['open']},{new_closed_row['high']},{new_closed_row['low']},{new_closed_row['close']},{new_closed_row['volume']}\n")
                
            # Recalculate indicators
            df = calculate_indicators(df)
            last_row = df.iloc[-1]
            
            # Extract latest indicators
            state.indicators = {
                "open": o, "high": h, "low": l, "close": c, "volume": v,
                "ema200": float(last_row["ema200"]),
                "atr": float(last_row["atr"]),
                "upperband": float(last_row["upperband"]),
                "lowerband": float(last_row["lowerband"]),
                "uptrend": bool(last_row["uptrend"])
            }
            
            # Check exit flip signals on newly closed candle
            if state.position is not None:
                pos_side = state.position["side"]
                if pos_side == "long" and last_row["exit_long"]:
                    logging.info("Indicator Exit flip signal triggered for LONG position.")
                    execute_paper_exit(c, "Indicator Exit", t)
                elif pos_side == "short" and last_row["exit_short"]:
                    logging.info("Indicator Exit flip signal triggered for SHORT position.")
                    execute_paper_exit(c, "Indicator Exit", t)
            
            # Check entry signals on newly closed candle (execute on the open of the current bar)
            if state.position is None:
                if last_row["long_sig"]:
                    reject_reason = check_safety_guards(state.last_candle_ts, "long", o, last_row["stop_loss_long"])
                    if reject_reason:
                        logging.warning(f"Long entry signal rejected: {reject_reason}")
                    else:
                        execute_paper_entry("long", o, last_row["stop_loss_long"], state.last_candle_ts)
                elif last_row["short_sig"]:
                    reject_reason = check_safety_guards(state.last_candle_ts, "short", o, last_row["stop_loss_short"])
                    if reject_reason:
                        logging.warning(f"Short entry signal rejected: {reject_reason}")
                    else:
                        execute_paper_entry("short", o, last_row["stop_loss_short"], state.last_candle_ts)
                        
        state.last_candle_ts = t
        
    # Update real-time state for the in-progress candle
    state.indicators["open"] = o
    state.indicators["high"] = max(state.indicators.get("high", h), h)
    state.indicators["low"] = min(state.indicators.get("low", l), l)
    state.indicators["close"] = c
    state.indicators["volume"] = v
    state.save()
    return df

def handle_price_update(current_price: float, timestamp_ms: int):
    state.last_price = current_price
    if state.position is None:
        state.save()
        return
        
    pos = state.position
    side = pos["side"]
    sl = pos["sl"]
    tp = pos["tp"]
    entry = pos["entry"]
    initial_sl = pos["initial_sl"]
    
    # 1. Check Break-Even Trailing (Move Stop to Entry when price hits 1R profit)
    if not pos.get("moved_to_be", False):
        dist = abs(entry - initial_sl)
        if side == "long" and current_price >= entry + dist:
            pos["sl"] = entry
            pos["moved_to_be"] = True
            logging.info(f"Break-even trailing stop triggered for LONG position. SL moved to entry ({entry:.4f})")
            state.save()
        elif side == "short" and current_price <= entry - dist:
            pos["sl"] = entry
            pos["moved_to_be"] = True
            logging.info(f"Break-even trailing stop triggered for SHORT position. SL moved to entry ({entry:.4f})")
            state.save()
            
    # 2. Check SL / TP triggers
    if side == "long":
        if current_price <= sl:
            logging.info(f"Stop Loss hit for LONG position. Price: {current_price:.4f} <= SL: {sl:.4f}")
            execute_paper_exit(sl, "Stop Loss", timestamp_ms)
        elif current_price >= tp:
            logging.info(f"Take Profit hit for LONG position. Price: {current_price:.4f} >= TP: {tp:.4f}")
            execute_paper_exit(tp, "Take Profit", timestamp_ms)
    else: # short
        if current_price >= sl:
            logging.info(f"Stop Loss hit for SHORT position. Price: {current_price:.4f} >= SL: {sl:.4f}")
            execute_paper_exit(sl, "Stop Loss", timestamp_ms)
        elif current_price <= tp:
            logging.info(f"Take Profit hit for SHORT position. Price: {current_price:.4f} <= TP: {tp:.4f}")
            execute_paper_exit(tp, "Take Profit", timestamp_ms)
            
    state.save()

async def ping_loop(websocket):
    while True:
        try:
            await asyncio.sleep(30)
            if websocket.state == websockets.State.OPEN:
                await websocket.send(json.dumps({"method": "ping"}))
                logging.info("heartbeat_sent")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Error sending WebSocket ping: {e}")
            break

def recover_offline_trades(df_backfilled: pd.DataFrame):
    if state.position is None or df_backfilled.empty:
        return
        
    logging.info("Checking for stop-loss or take-profit hits during engine downtime...")
    pos = state.position
    side = pos["side"]
    sl = pos["sl"]
    tp = pos["tp"]
    
    df_sorted = df_backfilled.sort_values("timestamp").reset_index(drop=True)
    
    for idx, row in df_sorted.iterrows():
        ts_ms = int(row["timestamp"])
        h = float(row["high"])
        l = float(row["low"])
        
        # Check Break-Even trigger
        if not pos.get("moved_to_be", False):
            dist = abs(pos["entry"] - pos["initial_sl"])
            if side == "long" and h >= pos["entry"] + dist:
                pos["sl"] = pos["entry"]
                pos["moved_to_be"] = True
                sl = pos["entry"] # Update local SL check value
                logging.info(f"Downtime recovery: Break-even trailing stop triggered. SL moved to entry ({pos['entry']:.4f})")
                state.save()
            elif side == "short" and l <= pos["entry"] - dist:
                pos["sl"] = pos["entry"]
                pos["moved_to_be"] = True
                sl = pos["entry"] # Update local SL check value
                logging.info(f"Downtime recovery: Break-even trailing stop triggered. SL moved to entry ({pos['entry']:.4f})")
                state.save()
                
        if side == "long":
            if l <= sl:
                logging.info(f"Downtime recovery: Stop Loss hit at candle {ts_ms}. Price: {l} <= SL: {sl}")
                execute_paper_exit(sl, "Stop Loss (Downtime Recovery)", ts_ms)
                break
            elif h >= tp:
                logging.info(f"Downtime recovery: Take Profit hit at candle {ts_ms}. Price: {h} >= TP: {tp}")
                execute_paper_exit(tp, "Take Profit (Downtime Recovery)", ts_ms)
                break
        else: # short
            if h >= sl:
                logging.info(f"Downtime recovery: Stop Loss hit at candle {ts_ms}. Price: {h} >= SL: {sl}")
                execute_paper_exit(sl, "Stop Loss (Downtime Recovery)", ts_ms)
                break
            elif l <= tp:
                logging.info(f"Downtime recovery: Take Profit hit at candle {ts_ms}. Price: {l} <= TP: {tp}")
                execute_paper_exit(tp, "Take Profit (Downtime Recovery)", ts_ms)
                break

async def main():
    state.load()
    
    # 1. Warm-up history + backfill gaps
    df, df_backfilled = load_and_backfill_data()
    
    # 2. Check for offline trades stopped out or target hit during downtime
    recover_offline_trades(df_backfilled)
    
    # 3. Calculate indicators
    df = calculate_indicators(df)
    
    # Prime initial indicator values in state
    last_row = df.iloc[-1]
    state.indicators = {
        "open": float(last_row["open"]),
        "high": float(last_row["high"]),
        "low": float(last_row["low"]),
        "close": float(last_row["close"]),
        "volume": float(last_row["volume"]),
        "ema200": float(last_row["ema200"]),
        "atr": float(last_row["atr"]),
        "upperband": float(last_row["upperband"]),
        "lowerband": float(last_row["lowerband"]),
        "uptrend": bool(last_row["uptrend"])
    }
    state.last_candle_ts = int(last_row["timestamp"])
    state.save()
    
    # Connect Loop
    backoff = 1
    while True:
        try:
            logging.info("reconnect_attempt (Connecting to Hyperliquid WebSocket API...)")
            async with websockets.connect("wss://api.hyperliquid.xyz/ws") as ws:
                state.websocket_connected = True
                state.save()
                backoff = 1
                logging.info("WebSocket connected successfully!")
                
                # Subscribe to candle
                await ws.send(json.dumps({
                    "method": "subscribe",
                    "subscription": {"type": "candle", "coin": COIN, "interval": "1h"}
                }))
                
                # Subscribe to trades
                await ws.send(json.dumps({
                    "method": "subscribe",
                    "subscription": {"type": "trades", "coin": COIN}
                }))
                logging.info(f"Subscribed to {COIN} 1h candle and trades feeds.")
                
                # Start ping heartbeat
                ping_task = asyncio.create_task(ping_loop(ws))
                
                # WS Message Loop
                async for message in ws:
                    msg = json.loads(message)
                    channel = msg.get("channel")
                    
                    if channel == "pong":
                        logging.info("heartbeat_received")
                    elif channel == "candle":
                        candle_data = msg.get("data")
                        if isinstance(candle_data, list):
                            for c in candle_data:
                                if c.get("s") == COIN and c.get("i") == "1h":
                                    df = await handle_candle_update(c, df)
                        elif isinstance(candle_data, dict):
                            if candle_data.get("s") == COIN and candle_data.get("i") == "1h":
                                df = await handle_candle_update(candle_data, df)
                                
                    elif channel == "trades":
                        trade_data = msg.get("data")
                        if isinstance(trade_data, list) and len(trade_data) > 0:
                            # Use the last trade in the list as the latest price
                            latest_trade = trade_data[-1]
                            px = float(latest_trade["px"])
                            time_ms = int(latest_trade["time"])
                            handle_price_update(px, time_ms)
                            
                # Cancel ping task if message loop finishes
                ping_task.cancel()
                
        except Exception as e:
            state.websocket_connected = False
            state.save()
            logging.error(f"WebSocket error: {e}. Reconnecting in {backoff:.1f}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60) + random.uniform(0, 1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Engine stopped by user.")
