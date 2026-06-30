import pandas as pd

from strategies.ema import ema_strategy
from engine.backtester import run_backtest

COINS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "BNBUSDT"
]

fast_windows = [10, 20, 30, 40]
slow_windows = [50, 100, 150, 200]

results = []

for fast in fast_windows:

    for slow in slow_windows:

        if fast >= slow:
            continue

        total_return = 0
        total_drawdown = 0

        coin_results = []

        for coin in COINS:

            df = pd.read_csv(f"data/{coin}_1h.csv")

            close = df["close"]

            entries, exits = ema_strategy(
                close,
                fast=fast,
                slow=slow
            )

            result = run_backtest(
                close,
                entries,
                exits
            )

            total_return += result["return_pct"]
            total_drawdown += result["max_dd"]

            coin_results.append(result["return_pct"])

        avg_return = total_return / len(COINS)
        avg_drawdown = total_drawdown / len(COINS)

        score = avg_return / avg_drawdown

        results.append({
            "fast": fast,
            "slow": slow,
            "avg_return": round(avg_return, 2),
            "avg_drawdown": round(avg_drawdown, 2),
            "score": round(score, 3)
        })

results = sorted(
    results,
    key=lambda x: x["score"],
    reverse=True
)

for row in results:
    print(row)