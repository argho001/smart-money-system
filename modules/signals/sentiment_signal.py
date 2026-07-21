"""
Smart Money System - Sentiment Signal
Fetches the Crypto Fear & Greed Index.

Logic:
- Extreme Fear (0-25) = buying opportunity (contrarian)
- Fear (25-45) = slightly bullish
- Neutral (45-55) = no signal
- Greed (55-75) = slightly bearish
- Extreme Greed (75-100) = selling opportunity (contrarian)

Source: https://api.alternative.me/fng/
"""

import aiohttp
import asyncio
from datetime import datetime

FEAR_GREED_API = "https://api.alternative.me/fng/"

class SentimentSignal:
    def __init__(self):
        self.api_url = FEAR_GREED_API
    
    async def get_fear_greed(self, limit=7):
        """Get Fear & Greed Index (last N days)"""
        url = f"{self.api_url}?limit={limit}&format=json"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                else:
                    print(f"[SENTIMENT] Error fetching Fear & Greed: {resp.status}")
        return []
    
    def analyze_sentiment(self, fng_data):
        """
        Analyze Fear & Greed data for signals.
        Returns: {score, reason, details}
        """
        if not fng_data:
            return {"score": 0, "reason": "No data"}
        
        # Current value
        current = fng_data[0]
        current_value = int(current.get("value", 50))
        current_label = current.get("value_classification", "Neutral")
        
        details = {
            "current_value": current_value,
            "current_label": current_label,
            "timestamp": current.get("timestamp", "")
        }
        
        # Historical trend
        if len(fng_data) > 1:
            values = [int(d.get("value", 50)) for d in fng_data]
            avg_value = sum(values) / len(values)
            details["avg_7d"] = avg_value
            details["trend"] = "improving" if current_value > avg_value else "worsening"
            
            # Volatility
            if len(values) > 2:
                details["volatility"] = max(values) - min(values)
        
        # Score calculation (CONTRARIAN)
        # Extreme Fear = BUY signal (contrarian)
        # Extreme Greed = SELL signal (contrarian)
        
        if current_value <= 15:
            score = 90
            reason = f"EXTREME FEAR ({current_value}) = STRONG BUY (contrarian)"
        elif current_value <= 25:
            score = 60
            reason = f"Extreme Fear ({current_value}) = BUY opportunity"
        elif current_value <= 35:
            score = 35
            reason = f"Fear ({current_value}) = slight bullish"
        elif current_value <= 45:
            score = 15
            reason = f"Slight Fear ({current_value}) = neutral-bullish"
        elif current_value <= 55:
            score = 0
            reason = f"Neutral ({current_value}) = no signal"
        elif current_value <= 65:
            score = -15
            reason = f"Slight Greed ({current_value}) = neutral-bearish"
        elif current_value <= 75:
            score = -35
            reason = f"Greed ({current_value}) = slight bearish"
        elif current_value <= 85:
            score = -60
            reason = f"Extreme Greed ({current_value}) = SELL opportunity"
        else:
            score = -90
            reason = f"EXTREME GREED ({current_value}) = STRONG SELL (contrarian)"
        
        return {
            "score": score,
            "reason": reason,
            "details": details
        }
    
    async def run(self):
        """Run sentiment analysis"""
        print("[SENTIMENT] Fetching Fear & Greed Index...")
        
        fng_data = await self.get_fear_greed(limit=7)
        
        if fng_data:
            analysis = self.analyze_sentiment(fng_data)
            
            print(f"[SENTIMENT] Fear & Greed Index: {analysis['details']['current_value']}")
            print(f"  Label: {analysis['details']['current_label']}")
            print(f"  Score: {analysis['score']:+d}")
            print(f"  Signal: {analysis['reason']}")
            
            if "avg_7d" in analysis["details"]:
                print(f"  7-day avg: {analysis['details']['avg_7d']:.0f}")
                print(f"  Trend: {analysis['details']['trend']}")
            
            return {
                "signal": "sentiment",
                "analysis": analysis,
                "raw_data": fng_data[:3],  # Last 3 days
                "timestamp": datetime.now().isoformat()
            }
        
        return {"signal": "sentiment", "analysis": {"score": 0, "reason": "No data"}}


async def test_sentiment():
    """Test the sentiment signal"""
    print("=" * 50)
    print("Sentiment Signal - Test")
    print("=" * 50)
    
    signal = SentimentSignal()
    result = await signal.run()
    
    print(f"\nResult: {result}")
    return result


if __name__ == "__main__":
    asyncio.run(test_sentiment())
