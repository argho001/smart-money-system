"""
Smart Money System - Liquidation Level Clusters
Calculates where liquidation levels are clustered based on leverage and price.
Price tends to move toward these clusters to trigger liquidations.
"""
import time
import numpy as np
from collections import deque


class LiquidationClusters:
    def __init__(self):
        self.clusters = []
        self.price_history = deque(maxlen=7200)  # 2 hours
        self.oi_by_level = {}  # Estimated OI at each price level

    def update(self, price, order_book_bids, order_book_asks, funding_rate):
        """
        Estimate liquidation clusters based on:
        - Order book liquidity (proxy for position sizes)
        - Price levels where stops are likely placed
        - Funding rate (indicates leverage direction)
        """
        self.price_history.append({"time": time.time(), "price": price})

        if not order_book_bids or not order_book_asks:
            return

        clusters = []

        # Estimate liquidation levels for common leverage ratios
        leverages = [5, 10, 20, 50, 100]

        for lev in leverages:
            # Long liquidation = price drops by 1/lev from entry
            # Short liquidation = price rises by 1/lev from entry
            liq_pct = 100 / lev

            # Estimate where longs would be liquidated (below current price)
            long_liq_price = price * (1 - liq_pct / 100)
            # Estimate where shorts would be liquidated (above current price)
            short_liq_price = price * (1 + liq_pct / 100)

            # Count how much order book liquidity is near these levels
            long_liq_liquidity = sum(
                float(b[1]) * float(b[0])
                for b in order_book_bids
                if abs(float(b[0]) - long_liq_price) / long_liq_price < 0.005
            )

            short_liq_liquidity = sum(
                float(a[1]) * float(a[0])
                for a in order_book_asks
                if abs(float(a[0]) - short_liq_price) / short_liq_price < 0.005
            )

            # Estimate liquidation volume based on OI proxy
            # More liquidity near a level = more positions = more liquidations
            long_liq_est = long_liq_liquidity * (lev / 10)  # Scale by leverage
            short_liq_est = short_liq_liquidity * (lev / 10)

            if long_liq_est > 10000:  # Only significant clusters
                clusters.append({
                    "price": round(long_liq_price, 2),
                    "side": "LONG",
                    "leverage": lev,
                    "estimated_liq_usd": round(long_liq_est, 0),
                    "distance_pct": round(-liq_pct, 2),
                })

            if short_liq_est > 10000:
                clusters.append({
                    "price": round(short_liq_price, 2),
                    "side": "SHORT",
                    "leverage": lev,
                    "estimated_liq_usd": round(short_liq_est, 0),
                    "distance_pct": round(liq_pct, 2),
                })

        # Sort by estimated liquidation volume
        clusters.sort(key=lambda x: x["estimated_liq_usd"], reverse=True)

        # Add magnet score (how likely price moves toward this cluster)
        for c in clusters:
            # Closer clusters are stronger magnets
            distance = abs(c["price"] - price) / price * 100
            c["magnet_score"] = round(c["estimated_liq_usd"] / max(distance, 0.1), 0)

        # Sort by magnet score
        clusters.sort(key=lambda x: x["magnet_score"], reverse=True)

        self.clusters = clusters[:20]  # Top 20 clusters

    def get_targets(self, price, direction):
        """
        Get liquidation-based price targets.
        Price tends to move toward liquidation clusters.
        """
        if not self.clusters:
            return {"targets": [], "next_target": None}

        if direction == "UP":
            # Look for short liquidation clusters above price
            targets = [c for c in self.clusters if c["side"] == "SHORT" and c["price"] > price]
        else:
            # Look for long liquidation clusters below price
            targets = [c for c in self.clusters if c["side"] == "LONG" and c["price"] < price]

        targets.sort(key=lambda x: x["magnet_score"], reverse=True)

        return {
            "targets": targets[:5],
            "next_target": targets[0] if targets else None,
            "total_liq_above": sum(c["estimated_liq_usd"] for c in self.clusters if c["side"] == "SHORT" and c["price"] > price),
            "total_liq_below": sum(c["estimated_liq_usd"] for c in self.clusters if c["side"] == "LONG" and c["price"] < price),
        }

    def get_state(self, price):
        """Get current liquidation cluster state"""
        above = [c for c in self.clusters if c["price"] > price][:5]
        below = [c for c in self.clusters if c["price"] < price][:5]

        total_above = sum(c["estimated_liq_usd"] for c in self.clusters if c["price"] > price)
        total_below = sum(c["estimated_liq_usd"] for c in self.clusters if c["price"] < price)

        # Bias: price moves toward bigger liquidation pool
        if total_above > total_below * 1.5:
            bias = "🔴 MORE SHORTS ABOVE — price likely pumps to liquidate them"
            bias_score = 20
        elif total_below > total_above * 1.5:
            bias = "🟢 MORE LONGS BELOW — price likely dumps to liquidate them"
            bias_score = -20
        else:
            bias = "⚪ BALANCED liquidation levels"
            bias_score = 0

        return {
            "clusters_above": [
                {"price": c["price"], "side": c["side"], "lev": c["leverage"],
                 "liq_usd": c["estimated_liq_usd"], "magnet": c["magnet_score"]}
                for c in above
            ],
            "clusters_below": [
                {"price": c["price"], "side": c["side"], "lev": c["leverage"],
                 "liq_usd": c["estimated_liq_usd"], "magnet": c["magnet_score"]}
                for c in below
            ],
            "total_liq_above": round(total_above, 0),
            "total_liq_below": round(total_below, 0),
            "bias": bias,
            "bias_score": bias_score,
        }
