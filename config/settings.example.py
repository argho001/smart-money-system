"""
Smart Money System - Configuration Template
Copy this to settings.py and fill in your API keys.
NEVER commit settings.py with real keys!
"""

# ============================================
# BLOCKCHAIN RPC
# ============================================
# Get your key: https://www.alchemy.com/
ALCHEMY_API_KEY = "YOUR_ALCHEMY_KEY"
ETHEREUM_WS_URL = f"wss://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
ETHEREUM_HTTP_URL = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"

# Backup: Infura
INFURA_API_KEY = "YOUR_INFURA_KEY"

# Etherscan (free: 5 calls/sec)
# Get your key: https://etherscan.io/
ETHERSCAN_API_KEY = "YOUR_ETHERSCAN_KEY"

# ============================================
# EXCHANGE API
# ============================================
# Testnet: https://testnet.binance.vision/ (paper trading)
# Real: https://www.binance.com/ (live trading, later)
BINANCE_API_KEY = "YOUR_BINANCE_API_KEY"
BINANCE_API_SECRET = "YOUR_BINANCE_API_SECRET"
BINANCE_TESTNET = True  # True = demo (fake money), False = real

# Binance endpoints
BINANCE_FUTURES_DEMO_URL = "https://demo-fapi.binance.com"
BINANCE_SPOT_URL = "https://api.binance.com"
BINANCE_TESTNET_URL = "https://testnet.binance.vision"

# ============================================
# WALLET WATCHLIST
# ============================================
# See wallets.json for the full list
# Add wallets via: python scripts/add_wallet.py

# ============================================
# TOKENS TO MONITOR
# ============================================
MONITORED_TOKENS = {
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": {"symbol": "WETH", "decimals": 18},
    "0xdAC17F958D2ee523a2206206994597C13D831ec7": {"symbol": "USDT", "decimals": 6},
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": {"symbol": "USDC", "decimals": 6},
    "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599": {"symbol": "WBTC", "decimals": 8},
    "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0": {"symbol": "wstETH", "decimals": 18},
    "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84": {"symbol": "stETH", "decimals": 18},
}

# ============================================
# DATABASE
# ============================================
DB_PATH = "data/smart_money.db"

# ============================================
# ALERTS
# ============================================
# Get Telegram bot: Message @BotFather on Telegram
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"

# Alert thresholds
ALERT_MIN_VALUE_USD = 10000  # Only alert for transfers > $10K
ALERT_COOLDOWN_SECONDS = 60  # Don't repeat same alert within 60s

# ============================================
# RISK MANAGEMENT
# ============================================
PORTFOLIO_VALUE_USD = 10000
MAX_RISK_PER_TRADE_PCT = 1.0  # 1% risk per trade
MAX_OPEN_POSITIONS = 3
MAX_DAILY_LOSS_PCT = 3.0

# ============================================
# SIGNAL SETTINGS
# ============================================
SIGNAL_ENTRY_THRESHOLD = 40  # Only trade on high conviction
SIGNAL_EXIT_THRESHOLD = -15
STOP_LOSS_PCT = 3.0
TAKE_PROFIT_PCT = 6.0

# Signal weights (must sum to 1.0)
SIGNAL_WEIGHTS = {
    "funding": 0.35,
    "momentum": 0.30,
    "volume": 0.20,
    "open_interest": 0.15
}

# ============================================
# LOGGING
# ============================================
LOG_LEVEL = "INFO"
LOG_FILE = "logs/system.log"
