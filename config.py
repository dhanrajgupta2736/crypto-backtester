"""Central configuration.

All secrets come from environment variables loaded from .env - never
hardcode credentials. Risk constants are intentionally hardcoded per the
capital-management specification and must not be user-editable at runtime.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
STATE_DIR = BASE_DIR / "state"
STATE_DIR.mkdir(exist_ok=True)
ACTIVE_STOPS_FILE = STATE_DIR / "active_stops.json"
DB_FILE = STATE_DIR / "trading.db"



class Settings:
    """Runtime settings + hardcoded risk rules."""

    # ---- Risk & capital management (CRITICAL - hardcoded by design) ----
    INITIAL_CAPITAL_USD: float = 120.0
    MAX_RISK_PER_TRADE_USD: float = 10.0   # absolute max loss per trade
    DAILY_TARGET_USD: float = 10.0         # circuit breaker trips at >= $10 net
    DAILY_MAX_LOSS_USD: float = 10.0       # circuit breaker trips at <= -$10 net
    LEVERAGE: int = 5
    MARGIN_MODE: str = "isolated"

    # ---- Universe & Whitelist ----
    WHITELIST_ONLY: bool = True
    AUTO_UNIVERSE: bool = False
    ENABLE_CRYPTO: bool = True
    ENABLE_STOCKS: bool = True
    MAX_ACTIVE_SYMBOLS: int = 8
    MAX_TOTAL_CONCURRENT_TRADES: int = 2
    MAX_CONCURRENT_TRADES_PER_SYMBOL: int = 1

    CRYPTO_WHITELIST = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK"]
    STOCK_WHITELIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META"]

    # ---- Asset Class Rules ----
    STOCK_RISK_MULTIPLIER: float = 0.6
    CRYPTO_RISK_MULTIPLIER: float = 1.0

    # ---- Execution cost assumptions (shrink size so loss never > $10) ----
    TAKER_FEE_RATE: float = 0.00045        # Hyperliquid taker fee 0.045 %
    SLIPPAGE_RATE: float = 0.0005          # conservative 0.05 % slippage buffer

    # ---- Scanner ----
    TOP_N_PAIRS: int = 50
    SCAN_INTERVAL_SECONDS: int = 7         # within the required 5-10 s window
    TIMEFRAMES = ("15m", "1h", "4h")
    CANDLE_LIMIT: int = 120
    MIN_CONFIDENCE: str = "High"
    MIN_STOP_DISTANCE_PCT: float = 0.005   # 0.5% minimum stop distance to prevent high-friction losses
    USE_SOFT_SL: bool = False              # Use hard stop loss on exchange by default

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        """(Re)load secrets from .env. Called after the config modal saves."""
        load_dotenv(ENV_FILE, override=True)
        # Hyperliquid auth: API key = wallet address, secret = private key
        self.api_key: str = os.getenv("HYPERLIQUID_API_KEY", "").strip()
        self.secret_key: str = os.getenv("HYPERLIQUID_SECRET_KEY", "").strip()
        self.testnet: bool = os.getenv("TESTNET", "true").strip().lower() == "true"
        try:
            self.MIN_STOP_DISTANCE_PCT = float(os.getenv("MIN_STOP_DISTANCE_PCT", "0.005").strip())
        except ValueError:
            self.MIN_STOP_DISTANCE_PCT = 0.005
        self.USE_SOFT_SL = os.getenv("USE_SOFT_SL", "false").strip().lower() == "true"

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.secret_key)


settings = Settings()
