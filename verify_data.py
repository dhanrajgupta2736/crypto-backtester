import os
import pandas as pd

for coin in sorted(os.listdir("data")):

    coin_path = os.path.join("data", coin)

    if not os.path.isdir(coin_path):
        continue

    print(f"\n=== {coin} ===")

    for file in sorted(os.listdir(coin_path)):

        path = os.path.join(coin_path, file)

        rows = len(pd.read_csv(path))

        print(f"{file:<10} {rows}")