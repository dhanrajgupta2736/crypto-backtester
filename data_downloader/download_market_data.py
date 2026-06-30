import ccxt
import pandas as pd
import os
import time
from datetime import datetime, timedelta

exchange = ccxt.binance({
    "enableRateLimit": True
})

COINS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "BNB/USDT"
]

TIMEFRAMES = {
    "5m": 90,
    "15m": 180,
    "1h": 1460,
    "4h": 1460,
    "1d": 4000
}

LIMIT = 1000


def download_symbol(symbol, timeframe, days):

    print(f"\nDownloading {symbol} {timeframe}")

    since = exchange.parse8601(
        (
            datetime.utcnow()
            - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    all_candles = []

    while True:

        candles = exchange.fetch_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            limit=LIMIT
        )

        if len(candles) == 0:
            break

        all_candles.extend(candles)

        since = candles[-1][0] + 1

        print(
            f"{symbol} {timeframe}: "
            f"{len(all_candles)} candles"
        )

        if len(candles) < LIMIT:
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

    coin_folder = symbol.replace("/", "")

    save_dir = os.path.join(
        "data",
        coin_folder
    )

    os.makedirs(
        save_dir,
        exist_ok=True
    )

    file_path = os.path.join(
        save_dir,
        f"{timeframe}.csv"
    )

    df.to_csv(
        file_path,
        index=False
    )

    print(
        f"Saved: {file_path}"
    )

    print(
        f"Rows: {len(df)}"
    )


for coin in COINS:

    for timeframe, days in TIMEFRAMES.items():

        try:

            download_symbol(
                coin,
                timeframe,
                days
            )

        except Exception as e:

            print(
                f"ERROR {coin} {timeframe}: {e}"
            )

print("\nDONE")