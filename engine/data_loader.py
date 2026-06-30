import pandas as pd


def load_data(symbol):

    path = f"data/{symbol}_1h.csv"

    df = pd.read_csv(path)

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    return df