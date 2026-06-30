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

all_results = []

for coin in COINS:

    print(f"\nTesting {coin}")

    df = pd.read_csv(f"data/{coin}_1h.csv")

    close = df["close"]

    best_result = None

    for fast in fast_windows:

        for slow in slow_windows:

            if fast >= slow:
                continue

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

            row = {
                "coin": coin,
                "fast": fast,
                "slow": slow,
                **result
            }

            all_results.append(row)

            if (
                best_result is None
                or row["return_pct"] > best_result["return_pct"]
            ):
                best_result = row

    print("BEST:", best_result)

results_df = pd.DataFrame(all_results)

results_df.to_csv(
    "optimization_results.csv",
    index=False
)

print("\nSaved optimization_results.csv")