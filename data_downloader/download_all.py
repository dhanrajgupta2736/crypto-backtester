import ccxt
import pandas as pd
import time
import os

exchange = ccxt.binance()

SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "BNB/USDT"
]

TIMEFRAME = "1h"
LIMIT = 1000

os.makedirs("data", exist_ok=True)


def download_symbol(symbol):

    print(f"\nDownloading {symbol}")

    all_candles = []

    since = exchange.parse8601("2023-01-01T00:00:00Z")

    while True:

        candles = exchange.fetch_ohlcv(
            symbol,
            timeframe=TIMEFRAME,
            since=since,
            limit=LIMIT
        )

        if len(candles) == 0:
            break

        all_candles.extend(candles)

        since = candles[-1][0] + 1

        print(f"Downloaded {len(all_candles)} candles")

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

    filename = symbol.replace("/", "") + "_1h.csv"

    path = os.path.join("data", filename)

    df.to_csv(path, index=False)

    print(f"Saved -> {path}")
    print(f"Rows -> {len(df)}")


for symbol in SYMBOLS:
    download_symbol(symbol)

print("\nDone.")