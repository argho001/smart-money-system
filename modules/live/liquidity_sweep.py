"""
Liquidity Sweep Detector

The most reliable reversal signal in trading.

A liquidity sweep is when price briefly breaks a key level to trigger clustered
stop losses, then reverses. This is NOT manipulation — it's the market
mechanically seeking available liquidity.

Detection:
1. Price breaks below support (or above resistance)
2. Volume spikes (stops being triggered)
3. Price reverses back above support (or below resistance) within a few candles
4. → Enter in the reversal direction

This is the signal that catches the "spring" and "upthrust" in Wyckoff terms.
"""

import time
from collections import deque


class LiquiditySweepDetector:
    def __init__(self):
        # Price and volume history
        self.price_history = deque(maxlen=600)  # 10 min of per-second data
        self.volume_history = deque(maxlen=600)

        # Key levels (support/resistance)
        self.support_levels = []
        self.resistance_levels = []

        # Sweep state
        self.last_sweep = None
        self.sweep_history = deque(maxlen=50)

        # Tracking
        self._last_price = 0
        self._sweep_cooldown = 120  # 2 min between sweep signals
        self._last_sweep_time = 0

    def update(self, price, volume=0, support_levels=None, resistance_levels=None):
        """Update with new price data."""
        now = time.time()
        self.price_history.append({"time": now, "price": price})
        self.volume_history.append({"time": now, "volume": volume})

        if support_levels is not None:
            self.support_levels = support_levels
        if resistance_levels is not None:
            self.resistance_levels = resistance_levels

        self._last_price = price

    def detect_sweep(self):
        """
        Detect a liquidity sweep.
        
        Returns sweep signal if detected, None otherwise.
        """
        now = time.time()
        price = self._last_price

        if price == 0 or len(self.price_history) < 30:
            return None

        # Cooldown check
        if now - self._last_sweep_time < self._sweep_cooldown:
            return None

        # Check each support level for sweep
        for level in self.support_levels:
            sweep = self._check_support_sweep(price, level)
            if sweep:
                self._last_sweep_time = now
                self.last_sweep = sweep
                self.sweep_history.append(sweep)
                return sweep

        # Check each resistance level for sweep
        for level in self.resistance_levels:
            sweep = self._check_resistance_sweep(price, level)
            if sweep:
                self._last_sweep_time = now
                self.last_sweep = sweep
                self.sweep_history.append(sweep)
                return sweep

        return None

    def _check_support_sweep(self, current_price, level):
        """
        Check for a support sweep (Wyckoff Spring).
        
        Pattern:
        1. Price was above support
        2. Price broke below support (the sweep)
        3. Price recovered back above support (the reversal)
        4. This happened in the last 1-5 minutes
        """
        level_price = level["price"]
        buffer = level_price * 0.001  # 0.1% buffer

        # Look at recent price history (last 5 minutes)
        now = time.time()
        recent = [p for p in self.price_history if p["time"] > now - 300]

        if len(recent) < 10:
            return None

        # Find the lowest point in recent history
        min_price = min(p["price"] for p in recent)
        min_time = min(p["time"] for p in recent if p["price"] == min_price)

        # Check if price swept below support
        if min_price > level_price - buffer:
            return None  # Didn't break below

        # Check if price recovered above support
        if current_price < level_price:
            return None  # Still below

        # Check timing — sweep should be recent (within 3 min)
        if now - min_time > 180:
            return None

        # Check volume spike at sweep time
        volume_spike = self._check_volume_spike(min_time)

        # Calculate sweep depth (how far below support)
        sweep_depth_pct = (level_price - min_price) / level_price * 100

        # Valid sweep: broke below, recovered, happened recently
        return {
            "type": "SUPPORT_SWEEP",
            "direction": "LONG",  # Bounce after sweep = LONG
            "level_price": round(level_price, 2),
            "sweep_low": round(min_price, 2),
            "sweep_depth_pct": round(sweep_depth_pct, 3),
            "current_price": round(current_price, 2),
            "volume_spike": volume_spike,
            "time": now,
            "age_seconds": round(now - min_time, 0),
            "confidence": self._calc_sweep_confidence(sweep_depth_pct, volume_spike, level),
            "signal": f"🟢 SUPPORT SWEEP — price swept ${level_price:,.0f} by {sweep_depth_pct:.2f}%, recovered. LONG.",
        }

    def _check_resistance_sweep(self, current_price, level):
        """
        Check for a resistance sweep (Wyckoff Upthrust).
        
        Pattern:
        1. Price was below resistance
        2. Price broke above resistance (the sweep)
        3. Price fell back below resistance (the reversal)
        4. This happened in the last 1-5 minutes
        """
        level_price = level["price"]
        buffer = level_price * 0.001

        now = time.time()
        recent = [p for p in self.price_history if p["time"] > now - 300]

        if len(recent) < 10:
            return None

        # Find the highest point in recent history
        max_price = max(p["price"] for p in recent)
        max_time = max(p["time"] for p in recent if p["price"] == max_price)

        # Check if price swept above resistance
        if max_price < level_price + buffer:
            return None

        # Check if price fell back below resistance
        if current_price > level_price:
            return None

        # Check timing
        if now - max_time > 180:
            return None

        volume_spike = self._check_volume_spike(max_time)
        sweep_depth_pct = (max_price - level_price) / level_price * 100

        return {
            "type": "RESISTANCE_SWEEP",
            "direction": "SHORT",  # Rejection after sweep = SHORT
            "level_price": round(level_price, 2),
            "sweep_high": round(max_price, 2),
            "sweep_depth_pct": round(sweep_depth_pct, 3),
            "current_price": round(current_price, 2),
            "volume_spike": volume_spike,
            "time": now,
            "age_seconds": round(now - max_time, 0),
            "confidence": self._calc_sweep_confidence(sweep_depth_pct, volume_spike, level),
            "signal": f"🔴 RESISTANCE SWEEP — price swept ${level_price:,.0f} by {sweep_depth_pct:.2f}%, rejected. SHORT.",
        }

    def _check_volume_spike(self, sweep_time):
        """Check if there was a volume spike at the sweep time."""
        if len(self.volume_history) < 60:
            return False

        # Compare volume at sweep time vs average
        sweep_volumes = [
            v["volume"] for v in self.volume_history
            if abs(v["time"] - sweep_time) < 10  # Within 10 seconds of sweep
        ]

        avg_volume = sum(v["volume"] for v in list(self.volume_history)[-60:]) / 60

        if not sweep_volumes or avg_volume == 0:
            return False

        sweep_avg = sum(sweep_volumes) / len(sweep_volumes)
        return sweep_avg > avg_volume * 2  # 2x average volume = spike

    def _calc_sweep_confidence(self, depth_pct, volume_spike, level):
        """Calculate confidence in the sweep signal."""
        score = 0

        # Deeper sweep = more stops triggered = stronger reversal
        if depth_pct > 0.5:
            score += 3
        elif depth_pct > 0.3:
            score += 2
        elif depth_pct > 0.1:
            score += 1

        # Volume spike confirms stops were hit
        if volume_spike:
            score += 2

        # Level strength
        strength = level.get("strength", 1)
        if strength > 3:
            score += 2
        elif strength > 2:
            score += 1

        if score >= 5:
            return "🟢 HIGH"
        elif score >= 3:
            return "🟡 MEDIUM"
        else:
            return "🔴 LOW"

    def get_state(self):
        """Get current state for display."""
        return {
            "last_sweep": self.last_sweep,
            "sweep_count": len(self.sweep_history),
            "recent_sweeps": [
                {"type": s["type"], "direction": s["direction"], "depth": s["sweep_depth_pct"], "age": s["age_seconds"]}
                for s in list(self.sweep_history)[-5:]
            ],
        }
