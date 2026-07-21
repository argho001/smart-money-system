"""
Smart Money System - Funding Rate Signal
Fetches funding rates from Binance Futures.

Logic:
- Positive funding = longs pay shorts = crowd is long = bearish (crowded trade)
- Negative funding = shorts pay longs = crowd is short = bullish (crowded trade)
- Extreme funding rates (>0.1% or <-0.1%) = reversal likely
"""

import aiohttp
import asyncio
from datetime import datetime

BINANCE_FUTURES_API = "https://fapi.binance.com"

class FundingRateSignal:
    def __init__(self):
        self.symbols = ["ETHUSDT", "BTCUSDT"]
        self.base_url = BINANCE_FUTURES_API
    
    async def get_funding_rate(self, symbol):
        """Get current funding rate for a symbol"""
        url = f"{self.base_url}/fapi/v1/premiumIndex?symbol={symbol}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    print(f"[FUNDING] Error fetching {symbol}: {resp.status}")
                    return None
    
    async def get_funding_rate_history(self, symbol, limit=10):
        """Get historical funding rates"""
        url = f"{self.base_url}/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
        return []
    
    async def get_open_interest(self, symbol):
        """Get current open interest"""
        url = f"{self.base_url}/fapi/v1/openInterest?symbol={symbol}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
        return {}
    
    def analyze_funding_rate(self, funding_data, history=None):
        """
        Analyze funding rate for signals.
        Returns: {score, reason, details}
        """
        if not funding_data:
            return {"score": 0, "reason": "No data"}
        
        # Current funding rate
        current_rate = float(funding_data.get("lastFundingRate", 0))
        rate_pct = current_rate * 100  # Convert to percentage
        
        # Mark price
        mark_price = float(funding_data.get("markPrice", 0))
        
        # Analysis
        details = {
            "current_rate": current_rate,
            "rate_pct": rate_pct,
            "mark_price": mark_price
        }
        
        # Historical trend
        if history:
            rates = [float(h.get("fundingRate", 0)) for h in history]
            avg_rate = sum(rates) / len(rates) if rates else 0
            details["avg_rate_10h"] = avg_rate
            details["rate_trend"] = "increasing" if current_rate > avg_rate else "decreasing"
        
        # Score calculation
        # Positive funding = longs pay shorts = crowd is long = BEARISH
        # Negative funding = shorts pay longs = crowd is short = BULLISH
        
        if rate_pct > 0.15:
            score = -80
            reason = f"EXTREME positive funding ({rate_pct:+.4f}%) = crowd very long = BEARISH"
        elif rate_pct > 0.1:
            score = -50
            reason = f"High positive funding ({rate_pct:+.4f}%) = crowd is long = bearish"
        elif rate_pct > 0.05:
            score = -25
            reason = f"Moderate positive funding ({rate_pct:+.4f}%) = slightly bearish"
        elif rate_pct > -0.05:
            score = 0
            reason = f"Neutral funding ({rate_pct:+.4f}%) = balanced"
        elif rate_pct > -0.1:
            score = 25
            reason = f"Moderate negative funding ({rate_pct:+.4f}%) = slightly bullish"
        elif rate_pct > -0.15:
            score = 50
            reason = f"Negative funding ({rate_pct:+.4f}%) = crowd is short = bullish"
        else:
            score = 80
            reason = f"EXTREME negative funding ({rate_pct:+.4f}%) = crowd very short = BULLISH"
        
        return {
            "score": score,
            "reason": reason,
            "details": details
        }
    
    async def run(self):
        """Run funding rate analysis for all symbols"""
        results = {}
        
        for symbol in self.symbols:
            print(f"[FUNDING] Fetching {symbol}...")
            
            # Get current funding rate
            funding = await self.get_funding_rate(symbol)
            
            # Get history
            history = await self.get_funding_rate_history(symbol, limit=10)
            
            # Get open interest
            oi = await self.get_open_interest(symbol)
            
            if funding:
                analysis = self.analyze_funding_rate(funding, history)
                
                results[symbol] = {
                    "analysis": analysis,
                    "open_interest": float(oi.get("openInterest", 0)),
                    "timestamp": datetime.now().isoformat()
                }
                
                rate_pct = analysis["details"]["rate_pct"]
                print(f"[FUNDING] {symbol}: {rate_pct:+.4f}%")
                print(f"  Score: {analysis['score']:+d}")
                print(f"  Signal: {analysis['reason']}")
                
                if oi:
                    print(f"  Open Interest: {float(oi.get('openInterest', 0)):,.0f} contracts")
            
            await asyncio.sleep(0.5)
        
        return results


async def test_funding():
    """Test the funding rate signal"""
    print("=" * 50)
    print("Funding Rate Signal - Test")
    print("=" * 50)
    
    signal = FundingRateSignal()
    results = await signal.run()
    
    print(f"\nResults: {results}")
    return results


if __name__ == "__main__":
    asyncio.run(test_funding())
