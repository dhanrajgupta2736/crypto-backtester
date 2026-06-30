import pandas as pd

from strategies import (
    vwap_momentum_scalp
)

from engine.signal_backtester import (
    simulate_trade
)

START_BALANCE = 1000

balance = START_BALANCE

wins = 0
losses = 0

# Load Data

df15 = pd.read_csv(
    "data/BTCUSDT/15m.csv"
)

df4h = pd.read_csv(
    "data/BTCUSDT/4h.csv"
)

# Convert timestamps

df15["ts"] = pd.to_datetime(
    df15["timestamp"]
).astype("int64") // 10**6

df4h["ts"] = pd.to_datetime(
    df4h["timestamp"]
).astype("int64") // 10**6

# Walk Forward

trade_open_until = 0

for i in range(50, len(df15) - 20):

    if i < trade_open_until:
        continue

    current_15m = df15.iloc[:i].copy()

    current_time = current_15m.iloc[-1]["ts"]

    current_4h = df4h[
        df4h["ts"] <= current_time
    ].copy()

    signal = vwap_momentum_scalp(
        "BTCUSDT",
        current_15m,
        current_4h
    )

    if signal is None:
        continue

    future = df15.iloc[
        i + 1 : i + 20
    ]

    result, pnl_pct = simulate_trade(
    signal,
    future
)
    trade_open_until = i + 20

    if result == "win":

        wins += 1

        balance *= 1.015

    elif result == "loss":

        losses += 1

        balance *= 0.99

total_trades = wins + losses

win_rate = (
    wins / total_trades * 100
    if total_trades
    else 0
)

print("\nRESULTS")

print(
    f"Initial Balance: ${START_BALANCE}"
)

print(
    f"Final Balance: ${balance:.2f}"
)

print(
    f"Profit: ${balance - START_BALANCE:.2f}"
)

print(
    f"Trades: {total_trades}"
)

print(
    f"Wins: {wins}"
)

print(
    f"Losses: {losses}"
)

print(
    f"Win Rate: {win_rate:.2f}%"
)