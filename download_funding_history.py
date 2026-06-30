import os
import time
import requests
import pandas as pd

CRYPTO_TICKERS = [
    "BTC", "XRP", "ETH", "ADA", "SOL", "BNB", "DOGE", "TRX", "HYPE", "ZEC",
    "LINK", "HBAR", "LTC", "SUI", "NEAR", "AVAX", "TAO", "WLD", "UNI", "ONDO",
    "AAVE", "RENDER", "ENA", "INJ", "DOT"
]

DATA_DIR = "data"
API_URL = "https://api.hyperliquid.xyz/info"

def download_funding_rate(coin):
    print(f"Downloading historical funding history for {coin}...")
    start_time = 1672531200000 # Jan 1, 2023 UTC
    end_time = int(time.time() * 1000)
    
    all_records = []
    
    while start_time < end_time:
        payload = {
            "type": "fundingHistory",
            "coin": coin,
            "startTime": start_time
        }
        try:
            r = requests.post(API_URL, json=payload, timeout=10)
            if r.status_code == 429:
                print(f"    Rate limited (429) for {coin}, sleeping 5s and retrying...")
                time.sleep(5.0)
                continue
            elif r.status_code != 200:
                print(f"    Error from API for {coin}: status code {r.status_code}")
                break
                
            data = r.json()
            if not data or not isinstance(data, list):
                break
                
            records = []
            for item in data:
                t = int(item['time'])
                rate = float(item['fundingRate'])
                records.append({
                    "timestamp": pd.to_datetime(t, unit='ms', utc=True),
                    "funding_rate": rate
                })
            
            last_ts = int(data[-1]['time'])
            all_records.extend(records)
            
            if len(data) < 500 or last_ts <= start_time:
                break
                
            start_time = last_ts + 1
            time.sleep(0.05) # Rate limit protection
            
        except Exception as e:
            print(f"    Exception downloading {coin}: {e}")
            time.sleep(1.0)
            continue
            
    if not all_records:
        print(f"    No funding rate records found for {coin}.")
        return 0
        
    df = pd.DataFrame(all_records)
    df.drop_duplicates(subset=['timestamp'], inplace=True)
    df.sort_values(by='timestamp', inplace=True)
    
    coin_dir = os.path.join(DATA_DIR, coin)
    os.makedirs(coin_dir, exist_ok=True)
    filepath = os.path.join(coin_dir, f"{coin}_funding.csv")
    df.to_csv(filepath, index=False)
    print(f"    Saved {len(df)} records to {filepath}")
    return len(df)

def main():
    print("=" * 72)
    print("  HYPERLIQUID HISTORICAL FUNDING RATE DOWNLOADER")
    print("=" * 72)
    total_saved = 0
    for coin in CRYPTO_TICKERS:
        cnt = download_funding_rate(coin)
        total_saved += cnt
        time.sleep(0.1)
    print("=" * 72)
    print(f"Funding rate download completed. Saved {total_saved} total records.")
    print("=" * 72)

if __name__ == "__main__":
    main()
