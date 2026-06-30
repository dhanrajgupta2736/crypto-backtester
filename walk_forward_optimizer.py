import pandas as pd

from strategies.ema import ema_strategy
from engine.backtester import run_backtest

# ======================
# LOAD DATA
# ======================

df = pd.read_csv("data/BTCUSDT_1h.csv")

df["timestamp"] = pd.to_datetime(df["timestamp"])

train = df[
    (df["timestamp"] >= "2023-01-01")
    & (df["timestamp"] < "2025-01-01")
]

test = df[
    (df["timestamp"] >= "2025-01-01")
]

fast_windows = [10, 20, 30, 40]
slow_windows = [50, 100, 150, 200]

results = []

for fast in fast_windows:

    for slow in slow_windows:

        if fast >= slow:
            continue

        # TRAIN

        entries, exits = ema_strategy(
            train["close"],
            fast,
            slow
        )

        train_result = run_backtest(
            train["close"],
            entries,
            exits
        )

        # TEST

        entries, exits = ema_strategy(
            test["close"],
            fast,
            slow
        )

        test_result = run_backtest(
            test["close"],
            entries,
            exits
        )

        results.append({
            "fast": fast,
            "slow": slow,

            "train_return":
                train_result["return_pct"],

            "test_return":
                test_result["return_pct"],

            "train_dd":
                train_result["max_dd"],

            "test_dd":
                test_result["max_dd"],

            "test_win_rate":
                test_result["win_rate"]
        })

results = sorted(
    results,
    key=lambda x: x["test_return"],
    reverse=True
)

print("\nTOP WALK-FORWARD RESULTS\n")

for row in results:
    print(row)