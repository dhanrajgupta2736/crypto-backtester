import os
import time
import ccxt
import pandas as pd

def get_hype_data(timeframe):
    # Connect to Hyperliquid DEX
    exchange = ccxt.hyperliquid()
    
    # Map to CCXT timeframe string
    ccxt_tf = {'5m': '5m', '15m': '15m', '1H': '1h', '4H': '4h', '1D': '1d'}[timeframe]
    
    primary_symbol = 'HYPE/USDC'
    fallback_symbol = 'HYPE/USDT'
    limit = 5000
    
    try:
        exchange.load_markets()
    except Exception as e:
        print(f"Error loading Hyperliquid markets: {e}")
        return None
        
    # Determine symbol to use
    symbol = None
    if primary_symbol in exchange.markets:
        symbol = primary_symbol
    elif fallback_symbol in exchange.markets:
        print(f"HYPE/USDC not found. Using fallback HYPE/USDT.")
        symbol = fallback_symbol
    else:
        print("Neither HYPE/USDC nor HYPE/USDT is listed on Hyperliquid exchange.")
        return None
        
    try:
        print(f"Fetching {symbol} {timeframe} data (limit={limit})...")
        candles = exchange.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=limit)
        if not candles:
            print(f"No candles returned for {symbol} {timeframe}.")
            return None
            
        df = pd.DataFrame(candles, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        
        # Convert timestamp to YYYY-MM-DD HH:MM:SS format
        df['Date'] = pd.to_datetime(df['Date'], unit='ms').dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Clean and sort
        df.drop_duplicates(subset=['Date'], inplace=True)
        df.sort_values(by='Date', inplace=True)
        
        return df
    except Exception as e:
        print(f"Error fetching HYPE {timeframe}: {e}")
        return None

def main():
    data_dir = os.path.join("data", "HYPE")
    os.makedirs(data_dir, exist_ok=True)
    
    timeframes = ["5m", "15m", "1H", "4H", "1D"]
    successful_downloads = []
    
    print("=== DOWNLOADING HYPE HISTORICAL DATA ===")
    
    for tf in timeframes:
        filename = f"HYPE_{tf}.csv"
        filepath = os.path.join(data_dir, filename)
        
        df = get_hype_data(tf)
        if df is not None and not df.empty:
            df.to_csv(filepath, index=False)
            print(f"Downloaded HYPE_{tf}.csv [OK]")
            successful_downloads.append(filepath)
        else:
            print(f"Failed or empty data for HYPE {tf}")
            
    print("\n=== DOWNLOAD SUMMARY ===")
    total_files = len(successful_downloads)
    total_size_bytes = sum(os.path.getsize(f) for f in successful_downloads if os.path.exists(f))
    total_size_mb = total_size_bytes / (1024 * 1024)
    
    print(f"Total files downloaded: {total_files}")
    print(f"Approximate total size: {total_size_mb:.2f} MB")
    
    print("\nFiles in data/HYPE/ directory:")
    if os.path.exists(data_dir):
        for file in sorted(os.listdir(data_dir)):
            path = os.path.join(data_dir, file)
            size_kb = os.path.getsize(path) / 1024
            rows = len(pd.read_csv(path)) if path.endswith('.csv') else 0
            print(f"  {file:<15} | Rows: {rows:<6} | Size: {size_kb:.2f} KB")
            
    print("\nNotice: HYPE: Only ~5000 candles available for 5m/15m/1H/4H (launched Nov 2024). 1D has full history.")
    print("All HYPE data downloaded successfully!")

if __name__ == "__main__":
    main()
