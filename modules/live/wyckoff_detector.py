"""
Wyckoff Phase Detector

The market moves in a repeating cycle:
1. ACCUMULATION — Smart money buys slowly, price ranges
2. MARKUP — Price rises (smart money already in)
3. DISTRIBUTION — Smart money sells slowly, price ranges
4. MARKDOWN — Price drops (smart money already out)

Key patterns:
- SPRING: False break below accumulation range → LONG signal
- UPTHRUST: False break above distribution range → SHORT signal
- SIGN OF STRENGTH (SOS): Strong move up after accumulation
- SIGN OF WEAKNESS (SOW): Strong move down after distribution

This detector identifies which phase we're in based on:
- Price range behavior
- Volume patterns
- Time in range
- Breakout characteristics
"""

import time
import numpy as np
from collections import deque


class WyckoffPhase:
    def __init__(self):
        # Price history (5 min candles built from ticks)
        self.price_data = deque(maxlen=3600)  # 1 hour of per-second data

        # Phase state
        self.current_phase = "UNKNOWN"
        self.phase_confidence = 0
        self.phase_start_time = 0
        self.range_high = 0
        self.range_low = 0
        self.range_mid = 0

        # Pattern detection
        self.spring_detected = False
        self.spring_time = 0
        self.upthrust_detected = False
        self.upthrust_time = 0

        # Volume analysis
        self.volume_history = deque(maxlen=3600)
        self.avg_volume = 0

        # State
        self._last_update = 0

    def update(self, price, volume=0):
        """Update with new tick data."""
        now = time.time()
        self.price_data.append({"time": now, "price": price})
        self.volume_history.append({"time": now, "volume": volume})

        # Recalculate phase every 10 seconds
        if now - self._last_update > 10:
            self._detect_phase()
            self._last_update = now

    def _detect_phase(self):
        """Detect current Wyckoff phase."""
        if len(self.price_data) < 120:  # Need at least 2 min of data
            return

        prices = [p["price"] for p in self.price_data]
        times = [p["time"] for p in self.price_data]
        now = time.time()

        # Calculate range statistics
        recent_5m = [p for p in self.price_data if p["time"] > now - 300]
        recent_15m = [p for p in self.price_data if p["time"] > now - 900]
        recent_1h = [p for p in self.price_data if p["time"] > now - 3600]

        if len(recent_5m) < 30:
            return

        prices_5m = [p["price"] for p in recent_5m]
        prices_15m = [p["price"] for p in recent_15m] if len(recent_15m) > 60 else prices_5m

        high_5m = max(prices_5m)
        low_5m = min(prices_5m)
        range_5m_pct = (high_5m - low_5m) / low_5m * 100

        high_15m = max(prices_15m)
        low_15m = min(prices_15m)
        range_15m_pct = (high_15m - low_15m) / low_15m * 100

        current_price = prices_5m[-1]

        # Volume analysis
        volumes = [v["volume"] for v in self.volume_history if v["time"] > now - 300]
        self.avg_volume = sum(volumes) / len(volumes) if volumes else 0

        # Detect phase
        phase, confidence = self._classify_phase(
            current_price, prices_5m, prices_15m,
            high_5m, low_5m, range_5m_pct,
            high_15m, low_15m, range_15m_pct,
            now
        )

        if phase != self.current_phase:
            self.current_phase = phase
            self.phase_confidence = confidence
            self.phase_start_time = now
            self.range_high = high_15m
            self.range_low = low_15m
            self.range_mid = (high_15m + low_15m) / 2

    def _classify_phase(self, price, prices_5m, prices_15m,
                        high_5m, low_5m, range_5m,
                        high_15m, low_15m, range_15m, now):
        """
        Classify the current Wyckoff phase.
        
        Accumulation: Low volatility range, volume decreasing, possible spring
        Distribution: High volatility range, volume increasing, possible upthrust
        Markup: Price trending up with increasing volume
        Markdown: Price trending down with increasing volume
        """
        confidence = 0

        # === ACCUMULATION DETECTION ===
        # Characteristics:
        # - Tight range (volatility compressed)
        # - Volume declining
        # - Price near range lows
        # - Time in range > 15 min
        if range_15m < 1.5:  # Tight range (< 1.5%)
            confidence += 2

            # Volume declining?
            early_vol = sum(v["volume"] for v in self.volume_history
                          if now - 900 < v["time"] <= now - 600)
            late_vol = sum(v["volume"] for v in self.volume_history
                         if v["time"] > now - 300)

            if early_vol > 0 and late_vol < early_vol * 0.7:
                confidence += 1  # Volume declining

            # Price in lower half of range
            mid = (high_15m + low_15m) / 2
            if price < mid:
                confidence += 1

            # Check for spring (false break below range)
            if low_5m < low_15m * 0.998 and price > low_15m:
                # Price broke below range and recovered = SPRING
                self.spring_detected = True
                self.spring_time = now
                confidence += 3
                return "SPRING", confidence

            if confidence >= 3:
                return "ACCUMULATION", confidence

        # === DISTRIBUTION DETECTION ===
        # Characteristics:
        # - Wide range (volatility expanded)
        # - Volume increasing
        # - Price near range highs
        # - Possible upthrust (false break above)
        if range_15m > 1.5:  # Wide range
            confidence += 1

            # Volume increasing?
            early_vol = sum(v["volume"] for v in self.volume_history
                          if now - 900 < v["time"] <= now - 600)
            late_vol = sum(v["volume"] for v in self.volume_history
                         if v["time"] > now - 300)

            if early_vol > 0 and late_vol > early_vol * 1.3:
                confidence += 1

            # Price in upper half of range
            mid = (high_15m + low_15m) / 2
            if price > mid:
                confidence += 1

            # Check for upthrust (false break above range)
            if high_5m > high_15m * 1.002 and price < high_15m:
                self.upthrust_detected = True
                self.upthrust_time = now
                confidence += 3
                return "UPTHRUST", confidence

            if confidence >= 3:
                return "DISTRIBUTION", confidence

        # === MARKUP DETECTION ===
        # Price making higher highs, higher lows
        if len(prices_15m) > 60:
            first_half = prices_15m[:len(prices_15m)//2]
            second_half = prices_15m[len(prices_15m)//2:]

            if min(second_half) > max(first_half) * 0.998:
                # Price moved up significantly
                return "MARKUP", 2

        # === MARKDOWN DETECTION ===
        if len(prices_15m) > 60:
            first_half = prices_15m[:len(prices_15m)//2]
            second_half = prices_15m[len(prices_15m)//2:]

            if max(second_half) < min(first_half) * 1.002:
                return "MARKDOWN", 2

        return "UNKNOWN", 0

    def get_signal(self):
        """
        Get trading signal based on Wyckoff phase.
        
        SPRING → LONG (false breakdown, accumulation complete)
        UPTHRUST → SHORT (false breakout, distribution complete)
        ACCUMULATION → Wait for spring
        DISTRIBUTION → Wait for upthrust
        MARKUP → LONG (trend following)
        MARKDOWN → SHORT (trend following)
        """
        now = time.time()

        if self.current_phase == "SPRING":
            # Spring is the strongest LONG signal
            age = now - self.spring_time
            if age < 300:  # Within 5 min of spring
                return {
                    "phase": "SPRING",
                    "direction": "LONG",
                    "confidence": "🟢 HIGH",
                    "signal": "🟢 WYCKOFF SPRING — false breakdown, accumulation complete. LONG.",
                    "age_seconds": age,
                }

        elif self.current_phase == "UPTHRUST":
            age = now - self.upthrust_time
            if age < 300:
                return {
                    "phase": "UPTHRUST",
                    "direction": "SHORT",
                    "confidence": "🟢 HIGH",
                    "signal": "🔴 WYCKOFF UPTHRUST — false breakout, distribution complete. SHORT.",
                    "age_seconds": age,
                }

        elif self.current_phase == "ACCUMULATION":
            return {
                "phase": "ACCUMULATION",
                "direction": None,
                "confidence": "🟡 MEDIUM",
                "signal": "⏳ ACCUMULATION — range forming, wait for spring",
            }

        elif self.current_phase == "DISTRIBUTION":
            return {
                "phase": "DISTRIBUTION",
                "direction": None,
                "confidence": "🟡 MEDIUM",
                "signal": "⏳ DISTRIBUTION — range forming, wait for upthrust",
            }

        elif self.current_phase == "MARKUP":
            return {
                "phase": "MARKUP",
                "direction": "LONG",
                "confidence": "🟡 MEDIUM",
                "signal": "🟢 MARKUP — trending up, look for pullback entries",
            }

        elif self.current_phase == "MARKDOWN":
            return {
                "phase": "MARKDOWN",
                "direction": "SHORT",
                "confidence": "🟡 MEDIUM",
                "signal": "🔴 MARKDOWN — trending down, look for rally entries",
            }

        return None

    def get_state(self):
        """Get current state for display."""
        signal = self.get_signal()

        return {
            "phase": self.current_phase,
            "confidence": self.phase_confidence,
            "range_high": round(self.range_high, 2),
            "range_low": round(self.range_low, 2),
            "range_mid": round(self.range_mid, 2),
            "spring_detected": self.spring_detected,
            "upthrust_detected": self.upthrust_detected,
            "signal": signal,
        }
