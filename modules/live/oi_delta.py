"""
Smart Money System - Open Interest Delta Tracker
Tracks CHANGE in open interest, not just absolute value.
OI change + price direction = market structure signal.
"""
import time
import aiohttp
from collections import deque


class OIDeltaTracker:
    def __init__(self):
        self.oi_current = 0
        self.oi_previous = 0
        self.oi_delta = 0
        self.oi_delta_pct = 0
        self.oi_history = deque(maxlen=3600)  # 1 hour
        self.price_at_oi = 0

    async def fetch(self, session):
        """Fetch OI from Binance Futures"""
        try:
            async with session.get(
                "https://fapi.binance.com/fapi/v1/openInterest",
                params={"symbol": "ETHUSDT"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    oi = float(data.get("openInterest", 0))

                    self.oi_previous = self.oi_current
                    self.oi_current = oi
                    self.oi_delta = oi - self.oi_previous if self.oi_previous > 0 else 0
                    self.oi_delta_pct = (self.oi_delta / self.oi_previous * 100) if self.oi_previous > 0 else 0

                    self.oi_history.append({
                        "time": time.time(),
                        "oi": oi,
                        "delta": self.oi_delta,
                        "delta_pct": self.oi_delta_pct,
                    })
        except:
            pass

    def get_signal(self, price):
        """
        Interpret OI delta + price direction.
        Returns signal dict.
        """
        price_change = 0
        if self.price_at_oi > 0:
            price_change = (price - self.price_at_oi) / self.price_at_oi * 100
        self.price_at_oi = price

        # OI delta interpretation
        oi_rising = self.oi_delta > 0
        price_rising = price_change > 0

        if oi_rising and price_rising:
            # New longs entering = bullish
            signal = "🟢 NEW LONGS — bullish momentum"
            bias = 20
        elif oi_rising and not price_rising:
            # New shorts entering = bearish
            signal = "🔴 NEW SHORTS — bearish momentum"
            bias = -20
        elif not oi_rising and price_rising:
            # Short covering = weak bullish
            signal = "🟡 SHORT COVERING — weak bullish"
            bias = 10
        elif not oi_rising and not price_rising:
            # Long liquidation = bearish
            signal = "🔴 LONG LIQUIDATION — bearish"
            bias = -15
        else:
            signal = "⚪ NEUTRAL"
            bias = 0

        # OI surge detection
        surge = False
        if len(self.oi_history) >= 60:
            recent_avg = sum(h["oi"] for h in list(self.oi_history)[-60:]) / 60
            if self.oi_current > recent_avg * 1.1:  # 10% above average
                surge = True
                signal += " ⚠️ OI SURGE — unusual activity"

        return {
            "oi": round(self.oi_current, 2),
            "oi_delta": round(self.oi_delta, 2),
            "oi_delta_pct": round(self.oi_delta_pct, 4),
            "price_change": round(price_change, 4),
            "signal": signal,
            "bias": bias,
            "surge": surge,
        }
