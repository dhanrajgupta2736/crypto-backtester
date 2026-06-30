import ccxt
import pandas as pd
import os
import time
from datetime import datetime, timedelta

exchange = ccxt.binance({
    "enableRateLimit": True
})

symbol = "ETH/USDT"
timeframe = "5m"
days = 90
limit = 1000

since = exchange.parse8601(
    (
        datetime.utcnow()
        - timedelta(days=days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
)

all_candles = []

while True:

    candles = exchange.fetch_ohlcv(
        symbol,
        timeframe,
        since,
        limit
    )

    if len(candles) == 0:
        break

    all_candles.extend(candles)

    since = candles[-1][0] + 1

    print(f"Downloaded {len(all_candles)} candles")

    if len(candles) < limit:
        break

    time.sleep(exchange.rateLimit / 1000)

df = pd.DataFrame(
    all_candles,
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

os.makedirs(
    "data/ETHUSDT",
    exist_ok=True
)

df.to_csv(
    "data/ETHUSDT/5m.csv",
    index=False
)

print("\nSaved ETHUSDT 5m")
print("Rows:", len(df))