"""
Smart Money System - Config Loader
Loads settings and wallet watchlist.
"""

import json
import os

# Load settings
from config.settings import *

# Load wallets from JSON
WALLETS_FILE = os.path.join(os.path.dirname(__file__), "wallets.json")

def load_wallets():
    """Load wallet watchlist from wallets.json"""
    with open(WALLETS_FILE, "r") as f:
        data = json.load(f)
    return data["wallets"]

def get_wallet_category(address):
    """Get wallet category by address"""
    wallets = load_wallets()
    addr_lower = address.lower()
    for addr, info in wallets.items():
        if addr.lower() == addr_lower:
            return info["category"]
    return "unknown"

def get_wallet_label(address):
    """Get wallet label by address"""
    wallets = load_wallets()
    addr_lower = address.lower()
    for addr, info in wallets.items():
        if addr.lower() == addr_lower:
            return info["label"]
    return "Unknown"

def get_wallet_priority(address):
    """Get wallet priority by address"""
    wallets = load_wallets()
    addr_lower = address.lower()
    for addr, info in wallets.items():
        if addr.lower() == addr_lower:
            return info.get("priority", "low")
    return "low"

def get_tracked_addresses():
    """Get list of all tracked addresses (lowercase)"""
    wallets = load_wallets()
    return [addr.lower() for addr in wallets.keys()]
