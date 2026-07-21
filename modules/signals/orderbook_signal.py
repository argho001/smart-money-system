"""
Smart Money System - Order Book Signal
Fetches real-time order book data from Binance.
Analyzes bid/ask imbalance to determine buying vs selling pressure.

Logic:
- More bids than asks = buying pressure = bullish
- More asks than bids = selling pressure = bearish
- Large orders (walls) indicate institutional positioning
"""

import aiohttp
import asyncio
from datetime import datetime

BINANCE_API = "https://api.binance.com"

class OrderBookSignal:
    def __init__(self):
        self.symbols = ["ETHUSDT", "BTCUSDT"]
        self.base_url = BINANCE_API
    
    async def get_order_book(self, symbol, limit=100):
        """Get order book from Binance (no API key needed)"""
        url = f"{self.base_url}/api/v3/depth?symbol={symbol}&limit={limit}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    print(f"[ORDERBOOK] Error fetching {symbol}: {resp.status}")
                    return None
    
    async def get_ticker(self, symbol):
        """Get current price"""
        url = f"{self.base_url}/api/v3/ticker/price?symbol={symbol}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get("price", 0))
        return 0
    
    async def get_24h_stats(self, symbol):
        """Get 24h trading statistics"""
        url = f"{self.base_url}/api/v3/ticker/24hr?symbol={symbol}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
        return {}
    
    def analyze_order_book(self, order_book, current_price):
        """
        Analyze order book for signals.
        Returns: {bid_volume, ask_volume, imbalance, score, large_orders}
        """
        if not order_book:
            return {"score": 0, "reason": "No data"}
        
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])
        
        # Calculate total volume within 1% of price
        price_range = current_price * 0.01  # 1%
        lower_bound = current_price - price_range
        upper_bound = current_price + price_range
        
        bid_volume = 0
        ask_volume = 0
        large_bid_orders = []
        large_ask_orders = []
        
        for bid in bids:
            bid_price = float(bid[0])
            bid_qty = float(bid[1])
            bid_value = bid_price * bid_qty
            
            if bid_price >= lower_bound:
                bid_volume += bid_value
                
                # Large order detection (>$100K)
                if bid_value > 100000:
                    large_bid_orders.append({
                        "price": bid_price,
                        "qty": bid_qty,
                        "value": bid_value
                    })
        
        for ask in asks:
            ask_price = float(ask[0])
            ask_qty = float(ask[1])
            ask_value = ask_price * ask_qty
            
            if ask_price <= upper_bound:
                ask_volume += ask_value
                
                # Large order detection (>$100K)
                if ask_value > 100000:
                    large_ask_orders.append({
                        "price": ask_price,
                        "qty": ask_qty,
                        "value": ask_value
                    })
        
        # Calculate imbalance
        total_volume = bid_volume + ask_volume
        if total_volume > 0:
            bid_pct = (bid_volume / total_volume) * 100
            ask_pct = (ask_volume / total_volume) * 100
            imbalance = bid_pct - ask_pct  # Positive = more buying
        else:
            bid_pct = 50
            ask_pct = 50
            imbalance = 0
        
        # Score: -100 to +100
        # Positive imbalance = more bids = bullish
        # Negative imbalance = more asks = bearish
        
        if imbalance > 30:
            score = 80
            reason = f"Strong buying pressure: {bid_pct:.0f}% bids vs {ask_pct:.0f}% asks"
        elif imbalance > 15:
            score = 50
            reason = f"Buying pressure: {bid_pct:.0f}% bids vs {ask_pct:.0f}% asks"
        elif imbalance > 5:
            score = 20
            reason = f"Slight buying pressure: {bid_pct:.0f}% bids vs {ask_pct:.0f}% asks"
        elif imbalance > -5:
            score = 0
            reason = f"Balanced: {bid_pct:.0f}% bids vs {ask_pct:.0f}% asks"
        elif imbalance > -15:
            score = -20
            reason = f"Slight selling pressure: {ask_pct:.0f}% asks vs {bid_pct:.0f}% bids"
        elif imbalance > -30:
            score = -50
            reason = f"Selling pressure: {ask_pct:.0f}% asks vs {bid_pct:.0f}% bids"
        else:
            score = -80
            reason = f"Strong selling pressure: {ask_pct:.0f}% asks vs {bid_pct:.0f}% bids"
        
        return {
            "score": score,
            "reason": reason,
            "bid_volume": bid_volume,
            "ask_volume": ask_volume,
            "bid_pct": bid_pct,
            "ask_pct": ask_pct,
            "imbalance": imbalance,
            "large_bid_orders": len(large_bid_orders),
            "large_ask_orders": len(large_ask_orders),
            "large_bid_total": sum(o["value"] for o in large_bid_orders),
            "large_ask_total": sum(o["value"] for o in large_ask_orders)
        }
    
    async def run(self):
        """Run order book analysis for all symbols"""
        results = {}
        
        for symbol in self.symbols:
            print(f"[ORDERBOOK] Fetching {symbol}...")
            
            # Get current price
            price = await self.get_ticker(symbol)
            
            # Get order book
            order_book = await self.get_order_book(symbol, limit=100)
            
            # Get 24h stats
            stats = await self.get_24h_stats(symbol)
            
            if order_book and price > 0:
                analysis = self.analyze_order_book(order_book, price)
                
                results[symbol] = {
                    "price": price,
                    "volume_24h": float(stats.get("quoteVolume", 0)),
                    "price_change_24h": float(stats.get("priceChangePercent", 0)),
                    "analysis": analysis
                }
                
                print(f"[ORDERBOOK] {symbol}: ${price:,.2f}")
                print(f"  Bid volume: ${analysis['bid_volume']:,.0f}")
                print(f"  Ask volume: ${analysis['ask_volume']:,.0f}")
                print(f"  Imbalance: {analysis['imbalance']:+.1f}%")
                print(f"  Score: {analysis['score']:+d}")
                print(f"  Signal: {analysis['reason']}")
            
            await asyncio.sleep(0.5)  # Rate limit
        
        return results


async def test_orderbook():
    """Test the order book signal"""
    print("=" * 50)
    print("Order Book Signal - Test")
    print("=" * 50)
    
    signal = OrderBookSignal()
    results = await signal.run()
    
    print(f"\nResults: {results}")
    return results


if __name__ == "__main__":
    asyncio.run(test_orderbook())
