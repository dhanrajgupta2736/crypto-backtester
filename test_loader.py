from engine.data_loader import load_data

df = load_data("BTCUSDT")

print(df.head())

print()

print("Rows:", len(df))