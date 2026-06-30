import pandas as pd

from strategies.ema import ema_strategy
from engine.backtester import run_backtest

df = pd.read_csv("data/BTCUSDT_1h.csv")

close = df["close"]

entries, exits = ema_strategy(
    close,
    fast=20,
    slow=50
)

result = run_backtest(
    close,
    entries,
    exits
)

print(result)