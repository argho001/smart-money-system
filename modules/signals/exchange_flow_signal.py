"""
Smart Money System - Exchange Flow Signal
Tracks overall ETH flowing in/out of exchanges.
Uses Etherscan API to monitor exchange wallets.

Logic:
- Large inflow to exchanges = bearish (people preparing to sell)
- Large outflow from exchanges = bullish (people withdrawing to hold)
- Uses aggregate data from known exchange wallets
"""

import aiohttp
import asyncio
from datetime import datetime, timedelta
from config import ETHERSCAN_API_KEY

# Major exchange wallets (Ethereum)
EXCHANGE_WALLETS = {
    # Binance
    "0x28C6c06298d514Db089934071355E5743bf21d60": "Binance",
    "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549": "Binance Cold",
    "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d": "Binance 16",
    # Coinbase
    "0x503828976D22510aad0201ac7EC88293211D23Da": "Coinbase",
    "0xcd531ae9efcce479654c4926dec5f6209531ca7b": "Coinbase Prime 1",
    "0xceb69f6342ece283b2f5c9088ff249b5d0ae66ea": "Coinbase Prime 2",
    # Others
    "0xA7efae728D2936E78Bda97dC267687568Dd593f3": "OKX",
    "0x267Be1C1D684F78Cb4f6a176c4911b741e4Ffdc0": "Kraken",
}

class ExchangeFlowSignal:
    def __init__(self):
        self.api_key = ETHERSCAN_API_KEY
        self.base_url = "https://api.etherscan.io/api"
        self.flow_history = []  # Track flows over time
    
    async def get_eth_balance(self, address):
        """Get current ETH balance for an address"""
        url = f"{self.base_url}?module=account&action=balance&address={address}&tag=latest&apikey={self.api_key}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data.get("status") == "1":
                    return int(data["result"]) / 1e18
        return 0
    
    async def get_recent_transfers(self, address, start_block=0):
        """Get recent internal transactions for an address"""
        url = (f"{self.base_url}?module=account&action=txlistinternal"
               f"&address={address}&startblock={start_block}"
               f"&endblock=99999999&sort=desc&apikey={self.api_key}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data.get("status") == "1":
                    return data.get("result", [])[:50]  # Last 50
        return []
    
    async def get_token_transfers(self, address):
        """Get recent ERC-20 token transfers"""
        url = (f"{self.base_url}?module=account&action=tokentx"
               f"&address={address}&sort=desc"
               f"&apikey={self.api_key}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data.get("status") == "1":
                    return data.get("result", [])[:50]
        return []
    
    async def calculate_exchange_flows(self):
        """
        Calculate net ETH flow across all exchange wallets.
        Returns: {total_inflow, total_outflow, net_flow, score}
        """
        total_inflow = 0
        total_outflow = 0
        details = []
        
        # Rate limiting: Etherscan free = 5 calls/sec
        # We have 8 wallets, need to be careful
        for address, name in EXCHANGE_WALLETS.items():
            try:
                # Get balance (1 call per wallet)
                balance = await self.get_eth_balance(address)
                details.append({"wallet": name, "balance": balance})
                
                # Small delay for rate limiting
                await asyncio.sleep(0.25)
                
            except Exception as e:
                print(f"[FLOW] Error getting {name} balance: {e}")
                continue
        
        # For now, use balance changes as proxy for flow
        # In full version, we'd compare with previous snapshot
        
        return {
            "wallets": details,
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_exchange_balance_snapshot(self):
        """Take a snapshot of all exchange balances"""
        snapshot = {}
        
        for address, name in EXCHANGE_WALLETS.items():
            try:
                balance = await self.get_eth_balance(address)
                snapshot[name] = {
                    "address": address,
                    "balance": balance,
                    "timestamp": datetime.now().isoformat()
                }
                await asyncio.sleep(0.25)  # Rate limit
            except Exception as e:
                print(f"[FLOW] Error: {name}: {e}")
                snapshot[name] = {"address": address, "balance": 0, "error": str(e)}
        
        return snapshot
    
    def calculate_flow_score(self, current_snapshot, previous_snapshot):
        """
        Calculate flow score from two balance snapshots.
        Returns score from -100 (very bearish) to +100 (very bullish)
        """
        if not previous_snapshot:
            return 0, "No previous data", {}
        
        total_change = 0
        details = []
        
        for name in current_snapshot:
            if name in previous_snapshot:
                curr = current_snapshot[name].get("balance", 0)
                prev = previous_snapshot[name].get("balance", 0)
                
                if prev > 0:
                    change = curr - prev
                    change_pct = (change / prev) * 100
                    total_change += change
                    
                    if abs(change) > 0.1:  # Only significant changes
                        direction = "inflow" if change > 0 else "outflow"
                        details.append({
                            "wallet": name,
                            "change": change,
                            "change_pct": change_pct,
                            "direction": direction
                        })
        
        # Score calculation
        # Positive change = inflow (bearish) = negative score
        # Negative change = outflow (bullish) = positive score
        
        if total_change > 1000:
            score = -80  # Massive inflow = very bearish
            reason = f"MASSIVE inflow: {total_change:,.0f} ETH to exchanges"
        elif total_change > 100:
            score = -50  # Large inflow = bearish
            reason = f"Large inflow: {total_change:,.0f} ETH to exchanges"
        elif total_change > 10:
            score = -20  # Moderate inflow
            reason = f"Moderate inflow: {total_change:,.1f} ETH to exchanges"
        elif total_change > -10:
            score = 0  # Neutral
            reason = "Balanced flow"
        elif total_change > -100:
            score = 20  # Moderate outflow
            reason = f"Moderate outflow: {abs(total_change):,.1f} ETH from exchanges"
        elif total_change > -1000:
            score = 50  # Large outflow = bullish
            reason = f"Large outflow: {abs(total_change):,.0f} ETH from exchanges"
        else:
            score = 80  # Massive outflow = very bullish
            reason = f"MASSIVE outflow: {abs(total_change):,.0f} ETH from exchanges"
        
        return score, reason, details
    
    async def run(self):
        """Run the exchange flow analysis"""
        print("[FLOW] Taking exchange balance snapshot...")
        snapshot = await self.get_exchange_balance_snapshot()
        
        total_eth = sum(s.get("balance", 0) for s in snapshot.values())
        
        result = {
            "signal": "exchange_flow",
            "total_exchange_eth": total_eth,
            "snapshot": snapshot,
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"[FLOW] Total ETH on tracked exchanges: {total_eth:,.2f}")
        for name, data in snapshot.items():
            bal = data.get("balance", 0)
            print(f"  {name}: {bal:,.2f} ETH")
        
        return result


async def test_exchange_flow():
    """Test the exchange flow signal"""
    print("=" * 50)
    print("Exchange Flow Signal - Test")
    print("=" * 50)
    
    signal = ExchangeFlowSignal()
    result = await signal.run()
    
    print(f"\nResult: {result}")
    return result


if __name__ == "__main__":
    asyncio.run(test_exchange_flow())
