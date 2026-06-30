import pandas as pd

from strategies.ema import ema_strategy
from engine.backtester import run_backtest

df = pd.read_csv("data/BTCUSDT_1h.csv")

close = df["close"]

fast_windows = [10, 20, 30, 40]
slow_windows = [50, 100, 150, 200]

results = []

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

        results.append({
            "fast": fast,
            "slow": slow,
            **result
        })

results = sorted(
    results,
    key=lambda x: x["return_pct"],
    reverse=True
)

for row in results:
    print(row)