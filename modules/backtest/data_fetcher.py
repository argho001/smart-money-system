"""
Smart Money System - Historical Data Fetcher
Fetches historical OHLCV data from Binance for backtesting.
"""

import aiohttp
import json
import os
from datetime import datetime, timedelta

BINANCE_API = "https://api.binance.com"
DATA_DIR = "data/candles"

class DataFetcher:
    def __init__(self):
        self.base_url = BINANCE_API
        os.makedirs(DATA_DIR, exist_ok=True)
    
    async def fetch_candles(self, symbol, interval, start_time, end_time, limit=1000):
        """
        Fetch OHLCV candles from Binance.
        
        Args:
            symbol: e.g., "ETHUSDT"
            interval: e.g., "1h", "4h", "1d"
            start_time: datetime
            end_time: datetime
            limit: max candles per request (1000)
        
        Returns: list of candles
        """
        url = f"{self.base_url}/api/v3/klines"
        
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        all_candles = []
        current_start = start_ms
        
        while current_start < end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current_start,
                "endTime": end_ms,
                "limit": limit
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if not data:
                            break
                        
                        all_candles.extend(data)
                        
                        # Move start to after last candle
                        last_close_time = data[-1][6]  # Close time
                        current_start = last_close_time + 1
                        
                        # Rate limiting
                        await asyncio.sleep(0.2)
                    else:
                        print(f"[DATA] Error fetching {symbol}: {resp.status}")
                        break
        
        return all_candles
    
    def parse_candles(self, raw_candles):
        """
        Parse raw Binance candle data into clean format.
        
        Binance format: [open_time, open, high, low, close, volume, close_time, ...]
        """
        candles = []
        for c in raw_candles:
            candles.append({
                "timestamp": datetime.fromtimestamp(c[0] / 1000),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
                "close_time": datetime.fromtimestamp(c[6] / 1000),
                "quote_volume": float(c[7]),
                "trades": int(c[8]),
                "taker_buy_volume": float(c[9]),
                "taker_buy_quote_volume": float(c[10])
            })
        return candles
    
    async def get_historical_data(self, symbol, interval, days_back):
        """
        Get historical data with caching.
        
        Args:
            symbol: e.g., "ETHUSDT"
            interval: e.g., "1h", "4h", "1d"
            days_back: number of days of history
        
        Returns: list of parsed candles
        """
        # Check cache
        cache_file = os.path.join(DATA_DIR, f"{symbol}_{interval}_{days_back}d.json")
        
        if os.path.exists(cache_file):
            # Check if cache is fresh (less than 1 hour old)
            cache_age = datetime.now().timestamp() - os.path.getmtime(cache_file)
            if cache_age < 3600:
                print(f"[DATA] Loading from cache: {cache_file}")
                with open(cache_file, "r") as f:
                    data = json.load(f)
                return [self._dict_to_candle(d) for d in data]
        
        # Fetch fresh data
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days_back)
        
        print(f"[DATA] Fetching {symbol} {interval} data for {days_back} days...")
        raw = await self.fetch_candles(symbol, interval, start_time, end_time)
        candles = self.parse_candles(raw)
        
        print(f"[DATA] Got {len(candles)} candles")
        
        # Save to cache
        cache_data = [self._candle_to_dict(c) for c in candles]
        with open(cache_file, "w") as f:
            json.dump(cache_data, f, indent=2, default=str)
        
        return candles
    
    def _candle_to_dict(self, candle):
        """Convert candle to serializable dict"""
        return {
            "timestamp": candle["timestamp"].isoformat(),
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "volume": candle["volume"],
            "quote_volume": candle["quote_volume"],
            "trades": candle["trades"]
        }
    
    def _dict_to_candle(self, d):
        """Convert dict back to candle"""
        return {
            "timestamp": datetime.fromisoformat(d["timestamp"]),
            "open": d["open"],
            "high": d["high"],
            "low": d["low"],
            "close": d["close"],
            "volume": d["volume"],
            "quote_volume": d.get("quote_volume", 0),
            "trades": d.get("trades", 0)
        }


# Need asyncio for the async functions
import asyncio


async def test_data_fetcher():
    """Test the data fetcher"""
    print("=" * 50)
    print("Historical Data Fetcher - Test")
    print("=" * 50)
    
    fetcher = DataFetcher()
    
    # Fetch 30 days of ETH 1h candles
    candles = await fetcher.get_historical_data("ETHUSDT", "1h", 30)
    
    print(f"\nGot {len(candles)} candles")
    print(f"First: {candles[0]['timestamp']} - ${candles[0]['close']:,.2f}")
    print(f"Last: {candles[-1]['timestamp']} - ${candles[-1]['close']:,.2f}")
    
    # Calculate basic stats
    closes = [c["close"] for c in candles]
    high = max(closes)
    low = min(closes)
    change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100
    
    print(f"\n30-day Stats:")
    print(f"  High: ${high:,.2f}")
    print(f"  Low: ${low:,.2f}")
    print(f"  Change: {change_pct:+.2f}%")
    
    return candles


if __name__ == "__main__":
    asyncio.run(test_data_fetcher())
