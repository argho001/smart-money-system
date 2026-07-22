"""
Smart Money System - Configuration
Reads from environment variables (Railway) or falls back to defaults.
"""
import os

# Blockchain RPC
ALCHEMY_API_KEY = os.environ.get("ALCHEMY_API_KEY", "")
ETHEREUM_WS_URL = f"wss://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}" if ALCHEMY_API_KEY else ""
ETHEREUM_HTTP_URL = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}" if ALCHEMY_API_KEY else ""

# Etherscan
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")

# Binance Demo
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
BINANCE_TESTNET = True
BINANCE_FUTURES_DEMO_URL = os.environ.get("BINANCE_FUTURES_BASE_URL", "https://demo-fapi.binance.com")
BINANCE_SPOT_URL = "https://api.binance.com"

# CryptoQuant
CRYPTOQUANT_API_KEY = os.environ.get("CRYPTOQUANT_API_KEY", "")

# Coinglass
COINGLASS_API_KEY = os.environ.get("COINGLASS_API_KEY", "")

# Telegram (optional)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Wallets
MONITORED_TOKENS = {
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": {"symbol": "WETH", "decimals": 18},
    "0xdAC17F958D2ee523a2206206994597C13D831ec7": {"symbol": "USDT", "decimals": 6},
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": {"symbol": "USDC", "decimals": 6},
}

# Database
DB_PATH = "data/smart_money.db"

# Risk Management
PORTFOLIO_VALUE_USD = 10000
MAX_RISK_PER_TRADE_PCT = 2.0
MAX_OPEN_POSITIONS = 3
MAX_DAILY_LOSS_PCT = 3.0

# Signal Settings
SIGNAL_ENTRY_THRESHOLD = 40
SIGNAL_EXIT_THRESHOLD = -15
STOP_LOSS_PCT = 3.0
TAKE_PROFIT_PCT = 6.0

SIGNAL_WEIGHTS = {
    "funding": 0.35,
    "momentum": 0.30,
    "volume": 0.20,
    "open_interest": 0.15
}

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "logs/system.log"
