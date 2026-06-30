import ccxt
import pandas as pd
import os

exchange = ccxt.binance()

symbol = "BTC/USDT"
timeframe = "1h"

ohlcv = exchange.fetch_ohlcv(
    symbol=symbol,
    timeframe=timeframe,
    limit=1000
)

df = pd.DataFrame(
    ohlcv,
    columns=[
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]
)

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    unit="ms"
)

os.makedirs("data", exist_ok=True)

df.to_csv(
    "data/BTCUSDT_1h.csv",
    index=False
)

print(df.head())
print()
print(f"Rows downloaded: {len(df)}")