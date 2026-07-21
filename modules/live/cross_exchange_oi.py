"""
Smart Money System - Cross-Exchange OI Rotation
Tracks OI across multiple exchanges to detect money rotation.
"""
import time
import aiohttp
from collections import deque


class CrossExchangeOI:
    def __init__(self):
        self.exchanges = {
            "Binance": "https://fapi.binance.com/fapi/v1/openInterest",
            "Bybit": "https://api.bybit.com/v5/market/open-interest",
            "OKX": "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history",
        }
        self.oi_data = {}
        self.oi_history = deque(maxlen=300)

    async def fetch(self, session):
        """Fetch OI from multiple exchanges"""
        now = time.time()

        # Binance
        try:
            async with session.get(
                self.exchanges["Binance"],
                params={"symbol": "ETHUSDT"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.oi_data["Binance"] = float(data.get("openInterest", 0))
        except:
            pass

        # Bybit
        try:
            async with session.get(
                self.exchanges["Bybit"],
                params={"category": "linear", "symbol": "ETHUSDT", "intervalTime": "5min", "limit": 1}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get("result", {}).get("list", [])
                    if result:
                        self.oi_data["Bybit"] = float(result[0].get("openInterest", 0))
        except:
            pass

        # OKX
        try:
            async with session.get(
                self.exchanges["OKX"],
                params={"instId": "ETH-USDT-SWAP", "period": "5m"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get("data", [])
                    if result:
                        self.oi_data["OKX"] = float(result[0][1]) if len(result[0]) > 1 else 0
        except:
            pass

        if self.oi_data:
            self.oi_history.append({
                "time": now,
                "data": dict(self.oi_data),
            })

    def get_rotation(self):
        """
        Detect if OI is rotating between exchanges.
        Rising on one + falling on another = money moving.
        """
        if len(self.oi_history) < 12:  # Need at least 1 minute of data
            return {"rotation": None, "data": self.oi_data}

        recent = self.oi_history[-1]
        older = self.oi_history[-12]  # ~1 minute ago

        changes = {}
        for exchange in self.oi_data:
            if exchange in recent["data"] and exchange in older["data"]:
                curr = recent["data"][exchange]
                prev = older["data"][exchange]
                if prev > 0:
                    changes[exchange] = {
                        "current": curr,
                        "previous": prev,
                        "delta": curr - prev,
                        "delta_pct": (curr - prev) / prev * 100,
                    }

        # Detect rotation
        rising = {k: v for k, v in changes.items() if v["delta_pct"] > 0.5}
        falling = {k: v for k, v in changes.items() if v["delta_pct"] < -0.5}

        rotation = None
        if rising and falling:
            rotation = {
                "type": "ROTATION",
                "from": list(falling.keys()),
                "to": list(rising.keys()),
                "signal": f"🔄 OI rotating from {', '.join(falling.keys())} to {', '.join(rising.keys())}",
            }
        elif len(rising) >= 2:
            rotation = {
                "type": "ALL_RISING",
                "exchanges": list(rising.keys()),
                "signal": "🟢 OI rising across exchanges — new money entering",
            }
        elif len(falling) >= 2:
            rotation = {
                "type": "ALL_FALLING",
                "exchanges": list(falling.keys()),
                "signal": "🔴 OI falling across exchanges — money leaving",
            }

        return {
            "rotation": rotation,
            "changes": changes,
            "data": self.oi_data,
        }

    def get_state(self):
        """Get current state"""
        rotation = self.get_rotation()
        return {
            "oi_by_exchange": {k: round(v, 2) for k, v in self.oi_data.items()},
            "oi_total": round(sum(self.oi_data.values()), 2),
            "rotation": rotation.get("rotation"),
            "changes": rotation.get("changes", {}),
        }
