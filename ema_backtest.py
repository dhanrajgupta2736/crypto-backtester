import pandas as pd
import vectorbt as vbt

# Load local data
df = pd.read_csv("data/BTCUSDT_1h.csv")

close = df["close"]

# Strategy
fast_ma = vbt.MA.run(close, window=20)
slow_ma = vbt.MA.run(close, window=50)

entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)

# Backtest
pf = vbt.Portfolio.from_signals(
    close,
    entries,
    exits,
    init_cash=10000,
    fees=0.001
)

print(pf.stats())