"""
Smart Money System - Live Configuration
"""
import os

# Binance Demo/Futures
BINANCE_DEMO_API_KEY = os.getenv("BINANCE_DEMO_API_KEY", "")
BINANCE_DEMO_API_SECRET = os.getenv("BINANCE_DEMO_API_SECRET", "")
BINANCE_FUTURES_BASE_URL = "https://demo-fapi.binance.com"
BINANCE_SPOT_BASE_URL = "https://api.binance.com"
BINANCE_WS_URL = "wss://fstream.binance.com"

# CryptoQuant
CRYPTOQUANT_API_KEY = os.getenv("CRYPTOQUANT_API_KEY", "")
CRYPTOQUANT_BASE_URL = "https://api.cryptoquant.com/v1"

# Coinglass
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY", "")
COINGLASS_BASE_URL = "https://open-api.coinglass.com/public/v2"

# Etherscan
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
