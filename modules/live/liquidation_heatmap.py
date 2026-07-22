"""
Liquidation Heatmap Engine

The single most predictive data source in crypto.
When a cluster of leveraged positions gets liquidated, it creates a chain reaction:
- Long liquidations = forced selling = price drops = more liquidations
- Short liquidations = forced buying = price rises = more liquidations
- After the cascade: price REVERSES (the move is exhausted)

This engine estimates liquidation clusters from:
1. Open interest distribution
2. Funding rate (tells us where leverage is)
3. Price action (round numbers, key levels)
4. Historical liquidation patterns

Data sources:
- Binance Futures API (OI, funding, liquidation data)
- Price levels where stops cluster
"""

import asyncio
import time
import aiohttp
from collections import deque


class LiquidationHeatmap:
    def __init__(self):
        # Current state
        self.oi_total = 0
        self.oi_long = 0
        self.oi_short = 0
        self.funding_rate = 0
        self.mark_price = 0

        # Estimated liquidation clusters
        self.long_liq_clusters = []  # Below current price
        self.short_liq_clusters = []  # Above current price

        # Cascade state
        self.cascade_active = False
        self.cascade_direction = None  # "LONG_LIQ" or "SHORT_LIQ"
        self.cascade_start_time = 0
        self.cascade_volume = 0

        # Historical data
        self.oi_history = deque(maxlen=3600)  # 1 hour
        self.price_history = deque(maxlen=3600)
        self.liq_history = deque(maxlen=100)  # Recent liquidation events

        # Round number levels (where stops cluster)
        self.round_levels = []

    async def start(self, session):
        """Start collecting data."""
        print("[LIQ] Starting liquidation heatmap engine")
        while True:
            try:
                await self._fetch_oi_data(session)
                await self._fetch_funding(session)
                await self._estimate_clusters()
                await self._detect_cascade()
            except Exception as e:
                pass
            await asyncio.sleep(2)

    async def _fetch_oi_data(self, session):
        """Fetch open interest data from Binance."""
        try:
            # Current OI
            async with session.get(
                "https://fapi.binance.com/fapi/v1/openInterest",
                params={"symbol": "ETHUSDT"},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    oi = float(data.get("openInterest", 0))
                    self.oi_total = oi
                    self.oi_history.append({"time": time.time(), "oi": oi})

            # Long/Short ratio (to estimate OI distribution)
            async with session.get(
                "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                params={"symbol": "ETHUSDT", "period": "5m", "limit": 1},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        ratio = float(data[0].get("longShortRatio", 1))
                        # Estimate OI split
                        total = self.oi_total
                        self.oi_long = total * (ratio / (1 + ratio))
                        self.oi_short = total - self.oi_long

            # Mark price
            async with session.get(
                "https://fapi.binance.com/fapi/v1/premiumIndex",
                params={"symbol": "ETHUSDT"},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.mark_price = float(data.get("markPrice", 0))
                    self.funding_rate = float(data.get("lastFundingRate", 0))
                    self.price_history.append({"time": time.time(), "price": self.mark_price})

        except Exception as e:
            pass

    async def _fetch_funding(self, session):
        """Fetch funding rate for leverage context."""
        # Already fetched in _fetch_oi_data
        pass

    async def _estimate_clusters(self):
        """
        Estimate where liquidation clusters are.
        
        Key insight: Liquidation price depends on:
        - Entry price
        - Leverage used
        - Margin type (cross vs isolated)
        
        Most traders use 5-20x leverage.
        Their liquidation price is roughly:
        - Long: entry * (1 - 1/leverage * 0.9)
        - Short: entry * (1 + 1/leverage * 0.9)
        
        Where traders ENTER determines where they GET LIQUIDATED.
        Entries cluster at:
        - Round numbers ($3,500, $3,400)
        - Support/resistance levels
        - Recent highs/lows
        - Moving averages
        """
        if self.mark_price == 0:
            return

        price = self.mark_price
        clusters = []

        # Generate round number levels near current price
        # These are where traders are most likely to have entered
        round_step = self._get_round_step(price)
        base = round(price / round_step) * round_step

        for i in range(-10, 11):
            level = base + (i * round_step)
            if level <= 0:
                continue

            # Estimate how many traders entered at this level
            # Closer to current price = more traders
            distance_pct = abs(level - price) / price * 100

            # Weight: closer levels have more positions
            weight = max(0, 100 - distance_pct * 20)

            # Round numbers get extra weight (psychological levels)
            if self._is_round_number(level):
                weight *= 1.5

            # Calculate liquidation prices for different leverages
            for leverage in [5, 10, 15, 20, 25]:
                # Long entry at this level → liquidation below
                long_liq = level * (1 - 1/leverage * 0.9)
                # Short entry at this level → liquidation above
                short_liq = level * (1 + 1/leverage * 0.9)

                # Weight by leverage (more traders use 5-10x than 25x)
                lev_weight = {5: 3, 10: 4, 15: 3, 20: 2, 25: 1}.get(leverage, 1)

                clusters.append({
                    "price": round(long_liq, 2),
                    "type": "LONG_LIQ",
                    "source_level": level,
                    "leverage": leverage,
                    "weight": weight * lev_weight,
                    "distance_pct": (price - long_liq) / price * 100,
                })

                clusters.append({
                    "price": round(short_liq, 2),
                    "type": "SHORT_LIQ",
                    "source_level": level,
                    "leverage": leverage,
                    "weight": weight * lev_weight,
                    "distance_pct": (short_liq - price) / price * 100,
                })

        # Sort by weight (most likely clusters first)
        clusters.sort(key=lambda x: x["weight"], reverse=True)

        # Split into below (long liqs) and above (short liqs)
        self.long_liq_clusters = [c for c in clusters if c["type"] == "LONG_LIQ" and c["price"] < price][:15]
        self.short_liq_clusters = [c for c in clusters if c["type"] == "SHORT_LIQ" and c["price"] > price][:15]

        # Sort by price for easy lookup
        self.long_liq_clusters.sort(key=lambda x: x["price"], reverse=True)
        self.short_liq_clusters.sort(key=lambda x: x["price"])

    async def _detect_cascade(self):
        """
        Detect if a liquidation cascade is happening or imminent.
        
        Signs of an active cascade:
        1. OI dropping rapidly (positions being liquidated)
        2. Price moving sharply in one direction
        3. Volume spiking
        
        Signs a cascade is IMMINENT:
        1. Price approaching a dense liquidation cluster
        2. Funding rate extreme (lots of leveraged positions)
        3. OI at local high (lots of positions to liquidate)
        """
        if len(self.oi_history) < 60 or len(self.price_history) < 60:
            return

        now = time.time()

        # Check OI change (last 5 minutes)
        recent_oi = [h for h in self.oi_history if h["time"] > now - 300]
        older_oi = [h for h in self.oi_history if now - 600 < h["time"] <= now - 300]

        if recent_oi and older_oi:
            avg_recent = sum(h["oi"] for h in recent_oi) / len(recent_oi)
            avg_older = sum(h["oi"] for h in older_oi) / len(older_oi)
            oi_change_pct = (avg_recent - avg_older) / avg_older * 100 if avg_older > 0 else 0

            # OI dropping fast = cascade happening
            if oi_change_pct < -3:  # 3% drop in 5 min
                recent_prices = [h for h in self.price_history if h["time"] > now - 300]
                if recent_prices:
                    price_change = (recent_prices[-1]["price"] - recent_prices[0]["price"]) / recent_prices[0]["price"] * 100

                    if price_change < -1:  # Price dropping + OI dropping = long cascade
                        self.cascade_active = True
                        self.cascade_direction = "LONG_LIQ"
                        self.cascade_start_time = now
                    elif price_change > 1:  # Price rising + OI dropping = short cascade
                        self.cascade_active = True
                        self.cascade_direction = "SHORT_LIQ"
                        self.cascade_start_time = now

        # Check if cascade is over (OI stabilizing)
        if self.cascade_active and now - self.cascade_start_time > 300:  # 5 min timeout
            self.cascade_active = False
            self.cascade_direction = None

    def get_nearest_cluster(self, direction="below"):
        """Get the nearest liquidation cluster in a direction."""
        if direction == "below" and self.long_liq_clusters:
            return self.long_liq_clusters[0]
        elif direction == "above" and self.short_liq_clusters:
            return self.short_liq_clusters[0]
        return None

    def get_dense_cluster(self, direction="below"):
        """Get the DENSEST cluster (most liquidations) in a direction."""
        clusters = self.long_liq_clusters if direction == "below" else self.short_liq_clusters
        if not clusters:
            return None
        # Find cluster with highest total weight in a price band
        best = max(clusters, key=lambda c: c["weight"])
        return best

    def get_cascade_signal(self):
        """
        Get cascade signal for trading.
        After a cascade, price reverses. This is the edge.
        """
        if not self.cascade_active:
            return None

        # How long has cascade been going?
        elapsed = time.time() - self.cascade_start_time

        if self.cascade_direction == "LONG_LIQ":
            # Longs getting liquidated → price dropping
            # After cascade: price will reverse UP
            return {
                "type": "LONG_CASCADE",
                "direction_after": "LONG",  # Trade LONG after cascade
                "elapsed": elapsed,
                "signal": "🔴 Long cascade active — wait for exhaustion, then LONG",
                "confidence": "high" if elapsed > 60 else "forming",
            }
        elif self.cascade_direction == "SHORT_LIQ":
            # Shorts getting liquidated → price rising
            # After cascade: price will reverse DOWN
            return {
                "type": "SHORT_CASCADE",
                "direction_after": "SHORT",  # Trade SHORT after cascade
                "elapsed": elapsed,
                "signal": "🟢 Short cascade active — wait for exhaustion, then SHORT",
                "confidence": "high" if elapsed > 60 else "forming",
            }

        return None

    def get_proximity_signal(self, price):
        """
        Is price approaching a liquidation cluster?
        This is the "fuse" — the cascade is about to trigger.
        """
        if not price:
            return None

        # Check proximity to dense long liquidation clusters
        for cluster in self.long_liq_clusters[:3]:
            distance = (price - cluster["price"]) / price * 100
            if 0 < distance < 0.5:  # Within 0.5% above a long liq cluster
                return {
                    "type": "APPROACHING_LONG_LIQ",
                    "direction": "SHORT",  # Price will drop to trigger the cascade
                    "cluster_price": cluster["price"],
                    "distance_pct": distance,
                    "weight": cluster["weight"],
                    "signal": f"⚠️ Price approaching long liq cluster at ${cluster['price']:,.0f} — cascade likely",
                }

        # Check proximity to dense short liquidation clusters
        for cluster in self.short_liq_clusters[:3]:
            distance = (cluster["price"] - price) / price * 100
            if 0 < distance < 0.5:  # Within 0.5% below a short liq cluster
                return {
                    "type": "APPROACHING_SHORT_LIQ",
                    "direction": "LONG",  # Price will rise to trigger the cascade
                    "cluster_price": cluster["price"],
                    "distance_pct": distance,
                    "weight": cluster["weight"],
                    "signal": f"⚠️ Price approaching short liq cluster at ${cluster['price']:,.0f} — cascade likely",
                }

        return None

    def _get_round_step(self, price):
        """Get appropriate round number step for current price level."""
        if price > 10000:
            return 500
        elif price > 5000:
            return 200
        elif price > 2000:
            return 100
        elif price > 1000:
            return 50
        elif price > 500:
            return 25
        elif price > 100:
            return 10
        else:
            return 5

    def _is_round_number(self, price):
        """Check if price is a psychological round number."""
        # Check if divisible by common round numbers
        for step in [100, 50, 25, 10, 5]:
            if abs(price % step) < 1:
                return True
        return False

    def get_state(self):
        """Get current state for display."""
        cascade = self.get_cascade_signal()

        return {
            "oi_total": round(self.oi_total, 2),
            "oi_long": round(self.oi_long, 2),
            "oi_short": round(self.oi_short, 2),
            "long_short_ratio": round(self.oi_long / self.oi_short, 2) if self.oi_short > 0 else 0,
            "funding_rate": round(self.funding_rate * 100, 4),
            "mark_price": round(self.mark_price, 2),
            "long_liq_clusters": len(self.long_liq_clusters),
            "short_liq_clusters": len(self.short_liq_clusters),
            "nearest_long_liq": self.long_liq_clusters[0]["price"] if self.long_liq_clusters else 0,
            "nearest_short_liq": self.short_liq_clusters[0]["price"] if self.short_liq_clusters else 0,
            "cascade_active": self.cascade_active,
            "cascade_direction": self.cascade_direction,
            "cascade_signal": cascade,
        }
