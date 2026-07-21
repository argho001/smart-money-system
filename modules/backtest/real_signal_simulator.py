"""
Smart Money System - Real Signal Simulator
Uses actual market data (funding, order book, sentiment) for backtesting.
Not just price patterns — real money flow signals.
"""

import numpy as np
import aiohttp
import json
import os
from datetime import datetime, timedelta

BINANCE_API = "https://api.binance.com"
BINANCE_FUTURES_API = "https://fapi.binance.com"
FEAR_GREED_API = "https://api.alternative.me/fng/"

class RealSignalSimulator:
    def __init__(self):
        self.signal_cache = {}
    
    async def fetch_funding_history(self, symbol, days_back):
        """Fetch historical funding rates from Binance Futures"""
        url = f"{BINANCE_FUTURES_API}/fapi/v1/fundingRate"
        
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days_back)).timestamp() * 1000)
        
        all_rates = []
        current_start = start_time
        
        async with aiohttp.ClientSession() as session:
            while current_start < end_time:
                params = {
                    "symbol": symbol,
                    "startTime": current_start,
                    "endTime": end_time,
                    "limit": 1000
                }
                
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if not data:
                            break
                        all_rates.extend(data)
                        current_start = int(data[-1]["fundingTime"]) + 1
                    else:
                        break
                
                await asyncio.sleep(0.2)
        
        return all_rates
    
    async def fetch_fear_greed_history(self, days_back):
        """Fetch historical Fear & Greed data"""
        url = f"{FEAR_GREED_API}?limit={days_back}&format=json"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
        return []
    
    async def fetch_liquidation_data(self, symbol, days_back):
        """Fetch open interest history as proxy for liquidation risk"""
        url = f"{BINANCE_FUTURES_API}/futures/data/openInterestHist"
        
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days_back)).timestamp() * 1000)
        
        params = {
            "symbol": symbol,
            "period": "4h",
            "startTime": start_time,
            "endTime": end_time,
            "limit": 500
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
        return []
    
    async def prepare_signals(self, candles, symbol="ETHUSDT", days_back=90):
        """
        Prepare all signal data aligned with candle timestamps.
        Returns dict of signal arrays aligned with candles.
        """
        print("[SIGNALS] Fetching historical data...")
        
        # 1. Funding rates (every 8 hours on Binance)
        print("[SIGNALS] Fetching funding rates...")
        funding_data = await self.fetch_funding_history(symbol, days_back)
        print(f"[SIGNALS] Got {len(funding_data)} funding records")
        
        # 2. Fear & Greed (daily)
        print("[SIGNALS] Fetching Fear & Greed...")
        fng_data = await self.fetch_fear_greed_history(days_back)
        print(f"[SIGNALS] Got {len(fng_data)} FNG records")
        
        # 3. Open Interest
        print("[SIGNALS] Fetching Open Interest...")
        oi_data = await self.fetch_liquidation_data(symbol, days_back)
        print(f"[SIGNALS] Got {len(oi_data)} OI records")
        
        # Align signals with candles
        signals = []
        
        for i, candle in enumerate(candles):
            timestamp = candle["timestamp"]
            price = candle["close"]
            
            # --- Funding Rate Signal ---
            funding_score = self._calc_funding_signal(funding_data, timestamp)
            
            # --- Sentiment Signal ---
            sentiment_score = self._calc_sentiment_signal(fng_data, timestamp)
            
            # --- Open Interest Signal ---
            oi_score = self._calc_oi_signal(oi_data, timestamp, candles, i)
            
            # --- Volume Signal (from candles) ---
            volume_score = self._calc_volume_signal(candles, i)
            
            # --- Price Momentum (simple) ---
            momentum_score = self._calc_momentum_signal(candles, i)
            
            # Weighted composite
            weights = {
                "funding": 0.25,
                "sentiment": 0.20,
                "open_interest": 0.20,
                "volume": 0.15,
                "momentum": 0.20
            }
            
            composite = (
                funding_score * weights["funding"] +
                sentiment_score * weights["sentiment"] +
                oi_score * weights["open_interest"] +
                volume_score * weights["volume"] +
                momentum_score * weights["momentum"]
            )
            
            composite = max(-100, min(100, composite))
            
            # Decision
            if composite > 40:
                signal = "STRONG_BUY"
            elif composite > 15:
                signal = "BUY"
            elif composite > -15:
                signal = "HOLD"
            elif composite > -40:
                signal = "SELL"
            else:
                signal = "STRONG_SELL"
            
            signals.append({
                "timestamp": timestamp,
                "price": price,
                "score": round(composite, 1),
                "signal": signal,
                "components": {
                    "funding": round(funding_score, 1),
                    "sentiment": round(sentiment_score, 1),
                    "open_interest": round(oi_score, 1),
                    "volume": round(volume_score, 1),
                    "momentum": round(momentum_score, 1)
                }
            })
        
        return signals
    
    def _calc_funding_signal(self, funding_data, timestamp):
        """
        Funding rate signal.
        Positive funding = crowd is long = BEARISH (contrarian)
        Negative funding = crowd is short = BULLISH (contrarian)
        """
        # Find closest funding rate to this timestamp
        ts_ms = int(timestamp.timestamp() * 1000) if isinstance(timestamp, datetime) else timestamp
        
        closest = None
        min_diff = float('inf')
        
        for f in funding_data:
            diff = abs(int(f["fundingTime"]) - ts_ms)
            if diff < min_diff:
                min_diff = diff
                closest = f
        
        if not closest:
            return 0
        
        rate = float(closest["fundingRate"])
        rate_pct = rate * 100
        
        # Contrarian: positive funding = bearish, negative = bullish
        # Scale: -0.1% to +0.1% maps to +100 to -100
        score = -rate_pct * 1000
        return max(-100, min(100, score))
    
    def _calc_sentiment_signal(self, fng_data, timestamp):
        """
        Sentiment signal from Fear & Greed Index.
        Extreme Fear = BUY (contrarian)
        Extreme Greed = SELL (contrarian)
        """
        if not fng_data:
            return 0
        
        # Find closest FNG to this date
        if isinstance(timestamp, datetime):
            date_str = timestamp.strftime("%d-%m-%Y")
        else:
            date_str = timestamp
        
        closest = None
        for fng in fng_data:
            if fng.get("timestamp"):
                fng_date = datetime.fromtimestamp(int(fng["timestamp"])).strftime("%d-%m-%Y")
                if fng_date == date_str:
                    closest = fng
                    break
        
        if not closest:
            # Use most recent
            closest = fng_data[0]
        
        value = int(closest.get("value", 50))
        
        # Contrarian: fear = buy, greed = sell
        # 0-100 maps to +100 (extreme fear) to -100 (extreme greed)
        score = (50 - value) * 2
        return max(-100, min(100, score))
    
    def _calc_oi_signal(self, oi_data, timestamp, candles, index):
        """
        Open Interest signal.
        Rising OI + rising price = trend continuation (bullish)
        Rising OI + falling price = short buildup (bearish)
        Falling OI = position closing (reversal likely)
        """
        if not oi_data or index < 5:
            return 0
        
        # Find OI values around this time
        ts_ms = int(timestamp.timestamp() * 1000) if isinstance(timestamp, datetime) else timestamp
        
        current_oi = None
        prev_oi = None
        
        for i, oi in enumerate(oi_data):
            oi_time = int(oi["timestamp"])
            if abs(oi_time - ts_ms) < 4 * 3600 * 1000:  # Within 4 hours
                current_oi = float(oi["sumOpenInterestValue"])
                if i > 0:
                    prev_oi = float(oi_data[i-1]["sumOpenInterestValue"])
                break
        
        if not current_oi or not prev_oi:
            return 0
        
        # OI change
        oi_change_pct = ((current_oi - prev_oi) / prev_oi) * 100
        
        # Price change
        if index > 0:
            price_change = ((candles[index]["close"] - candles[index-1]["close"]) / candles[index-1]["close"]) * 100
        else:
            price_change = 0
        
        # Rising OI + rising price = bullish
        # Rising OI + falling price = bearish (shorts building)
        # Falling OI = neutral (positions closing)
        
        if oi_change_pct > 2:
            if price_change > 0:
                score = 50  # Long buildup
            else:
                score = -50  # Short buildup
        elif oi_change_pct < -2:
            score = 0  # Position closing, neutral
        else:
            score = price_change * 10  # Follow price
        
        return max(-100, min(100, score))
    
    def _calc_volume_signal(self, candles, index):
        """
        Volume signal.
        High volume confirms the move.
        Low volume = weak move.
        """
        if index < 20:
            return 0
        
        volumes = [c["volume"] for c in candles[index-20:index+1]]
        avg_volume = np.mean(volumes[:-1])
        current_volume = volumes[-1]
        
        if avg_volume == 0:
            return 0
        
        volume_ratio = current_volume / avg_volume
        
        # Price direction
        price_change = ((candles[index]["close"] - candles[index-1]["close"]) / candles[index-1]["close"]) * 100
        
        # High volume confirms direction
        if volume_ratio > 2.0:
            score = price_change * 15
        elif volume_ratio > 1.5:
            score = price_change * 10
        elif volume_ratio < 0.5:
            score = 0  # Low volume = ignore
        else:
            score = price_change * 5
        
        return max(-100, min(100, score))
    
    def _calc_momentum_signal(self, candles, index):
        """
        Simple momentum signal.
        Uses rate of change over different periods.
        """
        if index < 20:
            return 0
        
        # 3-period momentum
        if index >= 3:
            mom_3 = ((candles[index]["close"] - candles[index-3]["close"]) / candles[index-3]["close"]) * 100
        else:
            mom_3 = 0
        
        # 10-period momentum
        if index >= 10:
            mom_10 = ((candles[index]["close"] - candles[index-10]["close"]) / candles[index-10]["close"]) * 100
        else:
            mom_10 = 0
        
        # Combined momentum
        score = (mom_3 * 60 + mom_10 * 40) if index >= 10 else mom_3 * 100
        
        return max(-100, min(100, score))


import asyncio


async def test_real_signals():
    """Test the real signal simulator"""
    from modules.backtest.data_fetcher import DataFetcher
    
    print("=" * 60)
    print("REAL SIGNAL SIMULATOR - Test")
    print("=" * 60)
    
    fetcher = DataFetcher()
    candles = await fetcher.get_historical_data("ETHUSDT", "4h", 30)
    
    simulator = RealSignalSimulator()
    signals = await simulator.prepare_signals(candles, "ETHUSDT", 30)
    
    print(f"\nGenerated {len(signals)} signals")
    print(f"\nLast 10 signals:")
    for s in signals[-10:]:
        print(f"  {s['signal']:12s} ({s['score']:+6.1f}) @ ${s['price']:,.2f} | "
              f"F:{s['components']['funding']:+5.1f} S:{s['components']['sentiment']:+5.1f} "
              f"OI:{s['components']['open_interest']:+5.1f} V:{s['components']['volume']:+5.1f} "
              f"M:{s['components']['momentum']:+5.1f}")
    
    return signals


if __name__ == "__main__":
    asyncio.run(test_real_signals())
