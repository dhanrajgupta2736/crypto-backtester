import pandas as pd

from strategies.ema import ema_strategy
from engine.backtester import run_backtest

# ======================
# LOAD DATA
# ======================

df = pd.read_csv("data/BTCUSDT_1h.csv")

df["timestamp"] = pd.to_datetime(df["timestamp"])

# ======================
# TRAIN PERIOD
# ======================

train = df[
    (df["timestamp"] >= "2023-01-01")
    & (df["timestamp"] < "2025-01-01")
]

# ======================
# TEST PERIOD
# ======================

test = df[
    (df["timestamp"] >= "2025-01-01")
]

# ======================
# OPTIMIZE ON TRAIN DATA
# ======================

fast_windows = [10, 20, 30, 40]
slow_windows = [50, 100, 150, 200]

best_result = None

for fast in fast_windows:

    for slow in slow_windows:

        if fast >= slow:
            continue

        entries, exits = ema_strategy(
            train["close"],
            fast,
            slow
        )

        result = run_backtest(
            train["close"],
            entries,
            exits
        )

        row = {
            "fast": fast,
            "slow": slow,
            **result
        }

        if (
            best_result is None
            or row["return_pct"] > best_result["return_pct"]
        ):
            best_result = row

print("\nBEST TRAIN RESULT")
print(best_result)

# ======================
# TEST USING BEST EMA
# ======================

entries, exits = ema_strategy(
    test["close"],
    best_result["fast"],
    best_result["slow"]
)

test_result = run_backtest(
    test["close"],
    entries,
    exits
)

print("\nOUT OF SAMPLE TEST")
print(test_result)