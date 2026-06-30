import os
import time
from datetime import datetime, timedelta
import ccxt
import pandas as pd
import yfinance as yf

# Configuration
CRYPTO_TICKERS = [
    "BTC", "XRP", "ETH", "ADA", "SOL", "BNB", "DOGE", "TRX", "HYPE", "ZEC",
    "LINK", "HBAR", "LTC", "SUI", "NEAR", "AVAX", "TAO", "WLD", "UNI", "ONDO",
    "AAVE", "RENDER", "ENA", "INJ", "DOT"
]

STOCK_TICKERS = [
    "AAPL", "COIN", "NVDA", "GOOGL", "MSFT", "AMZN", "HOOD", "TSLA", "META", "INTC"
]

TIMEFRAMES = ["5m", "15m", "1H", "4H", "1D"]

# Initialize exchanges
exchange = ccxt.binance({
    "enableRateLimit": True,
    "timeout": 30000,
})

def get_crypto_data(ticker, timeframe, start_dt, end_dt):
    symbol = f"{ticker}/USDT"
    
    # Map to CCXT timeframe string
    ccxt_tf = {'5m': '5m', '15m': '15m', '1H': '1h', '4H': '4h', '1D': '1d'}[timeframe]
    
    since = exchange.parse8601(start_dt.strftime('%Y-%m-%dT%H:%M:%SZ'))
    end_ts = int(end_dt.timestamp() * 1000)
    
    all_candles = []
    limit = 1000
    
    while since < end_ts:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe=ccxt_tf, since=since, limit=limit)
            if not candles:
                break
            
            last_ts = candles[-1][0]
            all_candles.extend(candles)
            
            if last_ts >= end_ts or len(candles) < limit:
                break
                
            since = last_ts + 1
            # Extra sleep to respect API rate limits and avoid ban
            time.sleep(0.1)
        except ccxt.DDoSProtection as e:
            print(f"Rate limit hit for {symbol} {timeframe}. Sleeping for 60s...")
            time.sleep(60)
            continue
        except ccxt.RequestTimeout as e:
            print(f"Timeout for {symbol} {timeframe}. Retrying...")
            time.sleep(5)
            continue
        except Exception as e:
            print(f"Error fetching {symbol} {timeframe}: {e}")
            break
            
    if not all_candles:
        return None
        
    df = pd.DataFrame(all_candles, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
    
    # Filter only required range
    df = df[df['Date'] <= end_ts]
    
    # Format date to YYYY-MM-DD HH:MM:SS
    df['Date'] = pd.to_datetime(df['Date'], unit='ms').dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Clean and sort
    df.drop_duplicates(subset=['Date'], inplace=True)
    df.sort_values(by='Date', inplace=True)
    
    return df

def get_stock_data(ticker, timeframe, start_dt, end_dt):
    # Map to yfinance interval
    yf_tf = {'5m': '5m', '15m': '15m', '1H': '1h', '4H': '4h', '1D': '1d'}[timeframe]
    t = yf.Ticker(ticker)
    
    try:
        # yfinance limits lookback for smaller intervals
        if timeframe in ['5m', '15m']:
            df = t.history(period='59d', interval=yf_tf)
        elif timeframe in ['1H', '4H']:
            df = t.history(period='720d', interval=yf_tf)
        else:
            # 1D - full 3 years
            start_str = start_dt.strftime('%Y-%m-%d')
            end_str = end_dt.strftime('%Y-%m-%d')
            df = t.history(start=start_str, end=end_str, interval=yf_tf)
            
        if df.empty:
            return None
            
        # Standardize columns and reset index
        df = df.copy()
        df.index.name = None
        df['Date'] = pd.to_datetime(df.index).tz_localize(None).strftime('%Y-%m-%d %H:%M:%S')
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        
        # Clean and sort
        df.drop_duplicates(subset=['Date'], inplace=True)
        df.sort_values(by='Date', inplace=True)
        
        return df
    except Exception as e:
        print(f"Error fetching stock {ticker} {timeframe}: {e}")
        return None

def main():
    # Setup directories
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    # Dates
    # June 19, 2026 is today
    end_dt = datetime(2026, 6, 19, 23, 59, 59)
    start_dt = end_dt - timedelta(days=3 * 365) # Approx 3 years
    
    print(f"Historical Data Downloader started.")
    print(f"Start Date: {start_dt.strftime('%Y-%m-%d')}")
    print(f"End Date: {end_dt.strftime('%Y-%m-%d')}\n")
    
    # Load markets for CCXT
    print("Loading Binance markets...")
    try:
        exchange.load_markets()
        print("Binance markets loaded successfully.\n")
    except Exception as e:
        print(f"CRITICAL: Failed to load markets: {e}")
        return
        
    successful_downloads = []
    
    # 1. Download Crypto
    print("=== DOWNLOADING CRYPTO DATA ===")
    for ticker in CRYPTO_TICKERS:
        ticker_dir = os.path.join(data_dir, ticker)
        os.makedirs(ticker_dir, exist_ok=True)
        
        # Check if HYPE is on Binance
        if ticker == "HYPE" and f"HYPE/USDT" not in exchange.markets:
            print(f"Skipping {ticker}: Not listed on Binance.\n")
            continue
            
        for tf in TIMEFRAMES:
            filename = f"{ticker}_{tf}.csv"
            filepath = os.path.join(ticker_dir, filename)
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                print(f"File {filename} already exists. Skipping...")
                successful_downloads.append(filepath)
                continue
                
            df = get_crypto_data(ticker, tf, start_dt, end_dt)
            if df is not None and not df.empty:
                df.to_csv(filepath, index=False)
                print(f"Downloaded {filename} [OK]")
                successful_downloads.append(filepath)
            else:
                print(f"Failed or empty data for {ticker} {tf}")
        print() # Spacer per ticker
        
    # 2. Download Stocks
    print("=== DOWNLOADING STOCK DATA ===")
    for ticker in STOCK_TICKERS:
        ticker_dir = os.path.join(data_dir, ticker)
        os.makedirs(ticker_dir, exist_ok=True)
        
        for tf in TIMEFRAMES:
            filename = f"{ticker}_{tf}.csv"
            filepath = os.path.join(ticker_dir, filename)
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                print(f"File {filename} already exists. Skipping...")
                successful_downloads.append(filepath)
                continue
                
            df = get_stock_data(ticker, tf, start_dt, end_dt)
            if df is not None and not df.empty:
                df.to_csv(filepath, index=False)
                print(f"Downloaded {filename} [OK]")
                successful_downloads.append(filepath)
            else:
                print(f"Failed or empty data for {ticker} {tf}")
        print() # Spacer per ticker
        
    # Stats calculation
    total_files = len(successful_downloads)
    total_size_bytes = 0
    for filepath in successful_downloads:
        if os.path.exists(filepath):
            total_size_bytes += os.path.getsize(filepath)
            
    total_size_mb = total_size_bytes / (1024 * 1024)
    
    print("=== DOWNLOAD SUMMARY ===")
    print(f"Total files downloaded: {total_files}")
    print(f"Approximate total size: {total_size_mb:.2f} MB")
    
    # Verify all expected files
    print("\nFiles in data directory:")
    for ticker in sorted(os.listdir(data_dir)):
        t_dir = os.path.join(data_dir, ticker)
        if os.path.isdir(t_dir):
            files = sorted(os.listdir(t_dir))
            if files:
                print(f"  {ticker}/: {', '.join(files)}")
                
    print("\nAll data downloaded and organized successfully!")

if __name__ == "__main__":
    main()
