"""
Smart Money System - Liquidity Map

Maps where price GRAVITATES based on order book walls and liquidity clusters.

Concept: Price moves toward liquidity. Big orders act as magnets.
- Large bid walls = support magnets (price bounces here)
- Large ask walls = resistance magnets (price gets rejected here)
- Thin zones = price moves fast through these (air pockets)
- Break of a wall = accelerated move to next wall

This module:
1. Scans order book for large walls
2. Identifies liquidity clusters
3. Maps price path (magnet sequence)
4. Detects thin zones (air pockets)
"""

import numpy as np
from datetime import datetime


class LiquidityMap:
    def __init__(self):
        self.map_history = []

    def analyze(self, order_book, current_price, depth_levels=100):
        """
        Build a liquidity map from order book data.

        Args:
            order_book: {"bids": [[price, qty], ...], "asks": [[price, qty], ...]}
            current_price: float
            depth_levels: how many levels to analyze

        Returns:
            {
                "walls": {support: [...], resistance: [...]},
                "magnets": [list of price magnets sorted by strength],
                "thin_zones": [price ranges with low liquidity],
                "price_path": predicted sequence of price magnets,
                "nearest_support": float,
                "nearest_resistance": float,
                "bias": str ("BULLISH" / "BEARISH" / "NEUTRAL"),
                "score": float (-100 to +100)
            }
        """
        if not order_book:
            return self._empty_map(current_price)

        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])

        # Parse into structured data
        bid_levels = self._parse_levels(bids, depth_levels)
        ask_levels = self._parse_levels(asks, depth_levels)

        # === Find Walls (large orders) ===
        support_walls = self._find_walls(bid_levels, current_price, side="bid")
        resistance_walls = self._find_walls(ask_levels, current_price, side="ask")

        # === Find Liquidity Clusters ===
        bid_clusters = self._find_clusters(bid_levels, "bid")
        ask_clusters = self._find_clusters(ask_levels, "ask")

        # === Find Thin Zones (air pockets) ===
        thin_zones = self._find_thin_zones(bid_levels, ask_levels, current_price)

        # === Build Magnet Map ===
        all_magnets = []
        for wall in support_walls:
            all_magnets.append({
                "price": wall["price"],
                "type": "support",
                "strength": wall["value"],
                "distance_pct": abs(wall["price"] - current_price) / current_price * 100
            })
        for wall in resistance_walls:
            all_magnets.append({
                "price": wall["price"],
                "type": "resistance",
                "strength": wall["value"],
                "distance_pct": abs(wall["price"] - current_price) / current_price * 100
            })

        # Sort by strength
        all_magnets.sort(key=lambda x: x["strength"], reverse=True)

        # === Predict Price Path ===
        price_path = self._predict_price_path(
            current_price, support_walls, resistance_walls, thin_zones
        )

        # === Calculate Bias ===
        bias, score = self._calculate_bias(
            bid_levels, ask_levels, support_walls, resistance_walls, current_price
        )

        # === Nearest levels ===
        nearest_support = max(
            (w["price"] for w in support_walls if w["price"] < current_price),
            default=current_price * 0.97
        )
        nearest_resistance = min(
            (w["price"] for w in resistance_walls if w["price"] > current_price),
            default=current_price * 1.03
        )

        result = {
            "current_price": round(current_price, 2),
            "walls": {
                "support": support_walls[:5],
                "resistance": resistance_walls[:5],
            },
            "magnets": all_magnets[:10],
            "thin_zones": thin_zones[:5],
            "price_path": price_path,
            "nearest_support": round(nearest_support, 2),
            "nearest_resistance": round(nearest_resistance, 2),
            "bias": bias,
            "score": round(score, 1),
            "clusters": {
                "bid": bid_clusters[:3],
                "ask": ask_clusters[:3],
            },
            "depth_analysis": {
                "bid_depth_usd": sum(l["value"] for l in bid_levels),
                "ask_depth_usd": sum(l["value"] for l in ask_levels),
                "depth_imbalance": self._depth_imbalance(bid_levels, ask_levels),
            },
            "timestamp": datetime.now().isoformat()
        }

        self.map_history.append(result)
        return result

    def _parse_levels(self, levels, max_levels):
        """Parse raw order book levels into structured data."""
        parsed = []
        for level in levels[:max_levels]:
            price = float(level[0])
            qty = float(level[1])
            value = price * qty
            parsed.append({
                "price": price,
                "qty": qty,
                "value": value,
            })
        return parsed

    def _find_walls(self, levels, current_price, side="bid", threshold_multiplier=3.0):
        """Find unusually large orders (walls)."""
        if not levels:
            return []

        # Calculate average order size
        avg_value = np.mean([l["value"] for l in levels])
        std_value = np.std([l["value"] for l in levels])

        wall_threshold = avg_value + threshold_multiplier * std_value

        walls = []
        for level in levels:
            if level["value"] > wall_threshold:
                # Check if it's a meaningful wall (not too far from price)
                distance_pct = abs(level["price"] - current_price) / current_price * 100
                if distance_pct < 15:  # Within 15%
                    walls.append({
                        "price": level["price"],
                        "qty": level["qty"],
                        "value": round(level["value"], 2),
                        "distance_pct": round(distance_pct, 2),
                        "avg_multiple": round(level["value"] / avg_value, 1),
                    })

        # Sort by value (strongest walls first)
        walls.sort(key=lambda x: x["value"], reverse=True)
        return walls

    def _find_clusters(self, levels, side):
        """Find price levels with clustered liquidity."""
        if not levels:
            return []

        # Group nearby levels
        clusters = []
        current_cluster = [levels[0]]

        for i in range(1, len(levels)):
            price_gap = abs(levels[i]["price"] - levels[i-1]["price"]) / levels[i-1]["price"]
            if price_gap < 0.003:  # Within 0.3%
                current_cluster.append(levels[i])
            else:
                if len(current_cluster) >= 3:
                    total_value = sum(l["value"] for l in current_cluster)
                    avg_price = np.mean([l["price"] for l in current_cluster])
                    clusters.append({
                        "price": round(avg_price, 2),
                        "total_value": round(total_value, 2),
                        "levels": len(current_cluster),
                    })
                current_cluster = [levels[i]]

        # Don't forget last cluster
        if len(current_cluster) >= 3:
            total_value = sum(l["value"] for l in current_cluster)
            avg_price = np.mean([l["price"] for l in current_cluster])
            clusters.append({
                "price": round(avg_price, 2),
                "total_value": round(total_value, 2),
                "levels": len(current_cluster),
            })

        clusters.sort(key=lambda x: x["total_value"], reverse=True)
        return clusters

    def _find_thin_zones(self, bid_levels, ask_levels, current_price):
        """Find price ranges with very low liquidity (air pockets)."""
        all_levels = sorted(bid_levels + ask_levels, key=lambda x: x["price"])

        if len(all_levels) < 5:
            return []

        # Calculate liquidity density per price bucket
        price_min = min(l["price"] for l in all_levels)
        price_max = max(l["price"] for l in all_levels)
        n_buckets = 20
        bucket_size = (price_max - price_min) / n_buckets if price_max > price_min else 1

        buckets = []
        for i in range(n_buckets):
            low = price_min + i * bucket_size
            high = low + bucket_size
            bucket_value = sum(
                l["value"] for l in all_levels
                if low <= l["price"] < high
            )
            buckets.append({
                "low": round(low, 2),
                "high": round(high, 2),
                "value": round(bucket_value, 2),
            })

        # Find thin zones (below average)
        avg_value = np.mean([b["value"] for b in buckets]) if buckets else 0

        thin_zones = []
        for bucket in buckets:
            if bucket["value"] < avg_value * 0.3 and bucket["low"] > current_price * 0.95 and bucket["high"] < current_price * 1.05:
                thin_zones.append({
                    "range": f"${bucket['low']:,.0f} - ${bucket['high']:,.0f}",
                    "low": bucket["low"],
                    "high": bucket["high"],
                    "liquidity": bucket["value"],
                    "description": "Price may move fast through this zone"
                })

        return thin_zones

    def _predict_price_path(self, current_price, support_walls, resistance_walls, thin_zones):
        """Predict the sequence of price levels price will visit."""
        path = [{"price": current_price, "label": "CURRENT"}]

        # Sort support walls by distance (nearest first, going down)
        nearby_supports = sorted(
            [w for w in support_walls if w["price"] < current_price],
            key=lambda x: abs(x["price"] - current_price)
        )

        # Sort resistance walls by distance (nearest first, going up)
        nearby_resistances = sorted(
            [w for w in resistance_walls if w["price"] > current_price],
            key=lambda x: abs(x["price"] - current_price)
        )

        # Build alternating path
        for i in range(max(len(nearby_supports), len(nearby_resistances))):
            if i < len(nearby_resistances):
                path.append({
                    "price": nearby_resistances[i]["price"],
                    "label": f"RESISTANCE (wall {nearby_resistances[i]['avg_multiple']:.0f}x avg)"
                })
            if i < len(nearby_supports):
                path.append({
                    "price": nearby_supports[i]["price"],
                    "label": f"SUPPORT (wall {nearby_supports[i]['avg_multiple']:.0f}x avg)"
                })

        return path[:8]

    def _calculate_bias(self, bid_levels, ask_levels, support_walls, resistance_walls, current_price):
        """Calculate overall bias from liquidity analysis."""
        score = 0

        # Factor 1: Depth imbalance (more bids = bullish)
        bid_total = sum(l["value"] for l in bid_levels)
        ask_total = sum(l["value"] for l in ask_levels)

        if bid_total + ask_total > 0:
            depth_ratio = (bid_total - ask_total) / (bid_total + ask_total)
            score += depth_ratio * 40  # ±40 points

        # Factor 2: Wall proximity (closer support = bullish, closer resistance = bearish)
        if support_walls:
            nearest_support = min(w["distance_pct"] for w in support_walls)
            score += max(0, 15 - nearest_support * 3)  # Up to +15

        if resistance_walls:
            nearest_resistance = min(w["distance_pct"] for w in resistance_walls)
            score -= max(0, 15 - nearest_resistance * 3)  # Up to -15

        # Factor 3: Wall strength (stronger support = bullish)
        if support_walls and resistance_walls:
            strongest_support = max(w["value"] for w in support_walls)
            strongest_resistance = max(w["value"] for w in resistance_walls)

            if strongest_support > strongest_resistance * 1.5:
                score += 20  # Strong support relative to resistance
            elif strongest_resistance > strongest_support * 1.5:
                score -= 20

        # Clamp
        score = max(-100, min(100, score))

        if score > 20:
            bias = "BULLISH"
        elif score < -20:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return bias, score

    def _depth_imbalance(self, bid_levels, ask_levels):
        """Calculate depth imbalance percentage."""
        bid_total = sum(l["value"] for l in bid_levels)
        ask_total = sum(l["value"] for l in ask_levels)

        if bid_total + ask_total == 0:
            return 0

        return round((bid_total - ask_total) / (bid_total + ask_total) * 100, 1)

    def _empty_map(self, price):
        return {
            "current_price": price,
            "walls": {"support": [], "resistance": []},
            "magnets": [],
            "thin_zones": [],
            "price_path": [],
            "nearest_support": price * 0.97,
            "nearest_resistance": price * 1.03,
            "bias": "NEUTRAL",
            "score": 0,
            "clusters": {"bid": [], "ask": []},
            "depth_analysis": {"bid_depth_usd": 0, "ask_depth_usd": 0, "depth_imbalance": 0},
            "timestamp": datetime.now().isoformat()
        }

    def format_map(self, result):
        """Format liquidity map for display."""
        bias_emoji = {
            "BULLISH": "🟢",
            "BEARISH": "🔴",
            "NEUTRAL": "🟡"
        }.get(result["bias"], "⚪")

        lines = [
            f"🗺️ <b>LIQUIDITY MAP</b>",
            f"",
            f"💰 <b>Current:</b> ${result['current_price']:,.2f}",
            f"{bias_emoji} <b>Bias:</b> {result['bias']} ({result['score']:+.0f})",
            f"",
            f"<b>📊 Depth:</b>",
            f"  Bid depth: ${result['depth_analysis']['bid_depth_usd']:,.0f}",
            f"  Ask depth: ${result['depth_analysis']['ask_depth_usd']:,.0f}",
            f"  Imbalance: {result['depth_analysis']['depth_imbalance']:+.1f}%",
            f"",
            f"<b>🧱 Nearest Walls:</b>",
            f"  Support: ${result['nearest_support']:,.2f}",
            f"  Resistance: ${result['nearest_resistance']:,.2f}",
        ]

        # Support walls
        if result["walls"]["support"]:
            lines.append(f"")
            lines.append(f"<b>🟢 Support Walls:</b>")
            for w in result["walls"]["support"][:3]:
                lines.append(f"  ${w['price']:,.2f} — ${w['value']:,.0f} ({w['avg_multiple']:.0f}x avg)")

        # Resistance walls
        if result["walls"]["resistance"]:
            lines.append(f"")
            lines.append(f"<b>🔴 Resistance Walls:</b>")
            for w in result["walls"]["resistance"][:3]:
                lines.append(f"  ${w['price']:,.2f} — ${w['value']:,.0f} ({w['avg_multiple']:.0f}x avg)")

        # Thin zones
        if result["thin_zones"]:
            lines.append(f"")
            lines.append(f"<b>💨 Thin Zones (price moves fast):</b>")
            for z in result["thin_zones"][:3]:
                lines.append(f"  {z['range']}")

        return "\n".join(lines)
