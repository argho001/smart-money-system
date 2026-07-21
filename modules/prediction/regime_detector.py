"""
Smart Money System - Market Regime Detector

Determines the CURRENT market state so we apply the right prediction model.

Regimes:
- TRENDING_UP:    High momentum, expanding volume, higher highs
- TRENDING_DOWN:  Negative momentum, expanding volume, lower lows
- RANGING:        Low volatility, mean-reverting, tight range
- VOLATILE:       High ATR, erratic moves, no clear direction
- ACCUMULATION:   Low volume, tight range, whale buying (pre-pump)
- DISTRIBUTION:   High volume at resistance, whale selling (pre-dump)

Each regime gets different prediction weights and strategies.
"""

import numpy as np
from datetime import datetime


class RegimeDetector:
    def __init__(self):
        self.regime_history = []

    def detect(self, candles, lookback=50):
        """
        Detect current market regime from OHLCV data.

        Args:
            candles: list of {open, high, low, close, volume} dicts
            lookback: how many candles to analyze

        Returns:
            {
                "regime": str,
                "confidence": float (0-1),
                "sub_signals": dict,
                "description": str
            }
        """
        if len(candles) < lookback:
            return {
                "regime": "UNKNOWN",
                "confidence": 0,
                "sub_signals": {},
                "description": "Not enough data"
            }

        recent = candles[-lookback:]
        closes = np.array([c["close"] for c in recent])
        highs = np.array([c["high"] for c in recent])
        lows = np.array([c["low"] for c in recent])
        volumes = np.array([c["volume"] for c in recent])

        # === Signal 1: Trend Direction (ADX-like) ===
        trend_score, trend_desc = self._measure_trend(closes, highs, lows)

        # === Signal 2: Volatility Regime ===
        vol_score, vol_desc = self._measure_volatility(closes, highs, lows)

        # === Signal 3: Volume Behavior ===
        vol_behavior, vol_beh_desc = self._measure_volume_behavior(volumes, closes)

        # === Signal 4: Price Structure ===
        structure_score, struct_desc = self._measure_structure(highs, lows, closes)

        # === Signal 5: Range vs Trend ===
        range_score, range_desc = self._measure_range_efficiency(closes)

        # === Combine signals into regime ===
        sub_signals = {
            "trend": {"score": trend_score, "desc": trend_desc},
            "volatility": {"score": vol_score, "desc": vol_desc},
            "volume_behavior": {"score": vol_behavior, "desc": vol_beh_desc},
            "structure": {"score": structure_score, "desc": struct_desc},
            "range_efficiency": {"score": range_score, "desc": range_desc},
        }

        regime, confidence = self._classify_regime(
            trend_score, vol_score, vol_behavior, structure_score, range_score
        )

        # Detect accumulation/distribution (special cases)
        if regime == "RANGING" and vol_behavior < -0.3:
            # Low volume + tight range + whale activity → accumulation
            regime = "ACCUMULATION"
            confidence = min(confidence + 0.1, 1.0)
        elif regime == "RANGING" and vol_behavior > 0.5 and structure_score < -0.3:
            # High volume at resistance → distribution
            regime = "DISTRIBUTION"
            confidence = min(confidence + 0.1, 1.0)

        descriptions = {
            "TRENDING_UP": "📈 Strong uptrend — momentum strategies work. Look for pullback entries.",
            "TRENDING_DOWN": "📉 Strong downtrend — short rallies, don't catch falling knives.",
            "RANGING": "↔️ Range-bound — mean-reversion works. Buy support, sell resistance.",
            "VOLATILE": "🌪️ High volatility — reduce size, widen stops, wait for clarity.",
            "ACCUMULATION": "🐋 Accumulation detected — smart money quietly buying. Watch for breakout.",
            "DISTRIBUTION": "📤 Distribution detected — smart money selling into strength. Watch for breakdown.",
            "UNKNOWN": "❓ Insufficient data to determine regime."
        }

        result = {
            "regime": regime,
            "confidence": round(confidence, 2),
            "sub_signals": sub_signals,
            "description": descriptions.get(regime, "Unknown regime"),
            "timestamp": datetime.now().isoformat()
        }

        self.regime_history.append(result)
        return result

    def _measure_trend(self, closes, highs, lows):
        """Measure trend strength using directional movement."""
        n = len(closes)

        # +DM / -DM (Directional Movement)
        plus_dm = []
        minus_dm = []
        true_range = []

        for i in range(1, n):
            high_diff = highs[i] - highs[i-1]
            low_diff = lows[i-1] - lows[i]

            plus_dm.append(max(high_diff, 0) if high_diff > low_diff else 0)
            minus_dm.append(max(low_diff, 0) if low_diff > high_diff else 0)

            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_range.append(tr)

        # Smoothed using 14-period EMA-like
        period = min(14, len(plus_dm))
        smooth_plus = self._ema(plus_dm, period)
        smooth_minus = self._ema(minus_dm, period)
        smooth_tr = self._ema(true_range, period)

        if smooth_tr == 0:
            return 0, "No movement"

        # ADX calculation
        plus_di = (smooth_plus / smooth_tr) * 100
        minus_di = (smooth_minus / smooth_tr) * 100
        dx = abs(plus_di - minus_di) / (plus_di + minus_di + 0.001) * 100

        # Trend score: -1 (strong down) to +1 (strong up)
        if plus_di + minus_di == 0:
            return 0, "Flat"

        trend_direction = (plus_di - minus_di) / (plus_di + minus_di)
        trend_strength = min(dx / 50, 1.0)  # Normalize ADX to 0-1

        score = trend_direction * trend_strength

        if score > 0.5:
            desc = f"Strong uptrend (+DI={plus_di:.0f}, -DI={minus_di:.0f})"
        elif score > 0.2:
            desc = f"Mild uptrend (+DI={plus_di:.0f}, -DI={minus_di:.0f})"
        elif score > -0.2:
            desc = f"No clear trend (ADX={dx:.0f})"
        elif score > -0.5:
            desc = f"Mild downtrend (+DI={plus_di:.0f}, -DI={minus_di:.0f})"
        else:
            desc = f"Strong downtrend (+DI={plus_di:.0f}, -DI={minus_di:.0f})"

        return score, desc

    def _measure_volatility(self, closes, highs, lows):
        """Measure volatility regime using ATR and Bollinger Band width."""
        # ATR
        atr = self._atr(highs, lows, closes, period=14)
        current_price = closes[-1]
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0

        # Bollinger Band Width
        sma = np.mean(closes[-20:])
        std = np.std(closes[-20:])
        bb_width = (2 * std / sma) * 100 if sma > 0 else 0

        # Historical ATR percentile
        atr_values = []
        for i in range(14, len(closes)):
            a = self._atr(highs[:i+1], lows[:i+1], closes[:i+1], 14)
            atr_values.append(a)

        if atr_values:
            percentile = sum(1 for v in atr_values if v < atr) / len(atr_values)
        else:
            percentile = 0.5

        # Score: -1 (very low vol) to +1 (very high vol)
        # We use percentile, not absolute value
        score = (percentile - 0.5) * 2  # Remap 0-1 to -1 to +1

        if atr_pct > 5:
            desc = f"Extreme volatility (ATR={atr_pct:.1f}%, BB width={bb_width:.1f}%)"
        elif atr_pct > 3:
            desc = f"High volatility (ATR={atr_pct:.1f}%, {percentile:.0%}ile)"
        elif atr_pct > 1.5:
            desc = f"Normal volatility (ATR={atr_pct:.1f}%, {percentile:.0%}ile)"
        else:
            desc = f"Low volatility (ATR={atr_pct:.1f}%, {percentile:.0%}ile)"

        return score, desc

    def _measure_volume_behavior(self, volumes, closes):
        """Analyze volume trends relative to price."""
        n = len(volumes)
        if n < 20:
            return 0, "Insufficient volume data"

        # Compare recent volume to average
        recent_vol = np.mean(volumes[-10:])
        avg_vol = np.mean(volumes[-50:]) if n >= 50 else np.mean(vol/vol if vol > 0 else 0 for vol in volumes[-20:])

        if avg_vol == 0:
            return 0, "No volume data"

        vol_ratio = recent_vol / avg_vol

        # Volume trend (is volume increasing or decreasing?)
        vol_sma_short = np.mean(volumes[-5:])
        vol_sma_long = np.mean(volumes[-20:])
        vol_trend = (vol_sma_short - vol_sma_long) / vol_sma_long if vol_sma_long > 0 else 0

        # Price-volume correlation
        if len(closes) >= 10:
            price_changes = np.diff(closes[-11:])
            vol_changes = np.diff(volumes[-11:])
            if np.std(price_changes) > 0 and np.std(vol_changes) > 0:
                correlation = np.corrcoef(price_changes, vol_changes)[0, 1]
            else:
                correlation = 0
        else:
            correlation = 0

        # Score: volume expanding (positive) or contracting (negative)
        score = (vol_ratio - 1.0) * 0.5 + vol_trend * 0.5
        score = max(-1, min(1, score))

        if vol_ratio > 1.5 and correlation > 0.3:
            desc = f"Volume expanding with price (ratio={vol_ratio:.1f}x, corr={correlation:.2f})"
        elif vol_ratio > 1.5 and correlation < -0.3:
            desc = f"High volume divergence (ratio={vol_ratio:.1f}x, corr={correlation:.2f})"
        elif vol_ratio < 0.5:
            desc = f"Volume drying up (ratio={vol_ratio:.1f}x) — possible accumulation"
        else:
            desc = f"Normal volume (ratio={vol_ratio:.1f}x, trend={vol_trend:+.2f})"

        return score, desc

    def _measure_structure(self, highs, lows, closes):
        """Analyze price structure: higher highs/lows or lower highs/lows."""
        n = len(closes)
        if n < 20:
            return 0, "Insufficient data"

        # Find swing highs and lows (simple method)
        swing_highs = []
        swing_lows = []

        for i in range(2, n-2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
               highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                swing_highs.append((i, highs[i]))
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
               lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                swing_lows.append((i, lows[i]))

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return 0, "Not enough swing points"

        # Check for higher highs / higher lows (bullish)
        recent_highs = swing_highs[-3:]
        recent_lows = swing_lows[-3:]

        higher_highs = sum(1 for i in range(1, len(recent_highs)) if recent_highs[i][1] > recent_highs[i-1][1])
        higher_lows = sum(1 for i in range(1, len(recent_lows)) if recent_lows[i][1] > recent_lows[i-1][1])
        lower_highs = sum(1 for i in range(1, len(recent_highs)) if recent_highs[i][1] < recent_highs[i-1][1])
        lower_lows = sum(1 for i in range(1, len(recent_lows)) if recent_lows[i][1] < recent_lows[i-1][1])

        bullish = higher_highs + higher_lows
        bearish = lower_highs + lower_lows

        score = (bullish - bearish) / 4.0  # Normalize to -1 to +1

        if score > 0.5:
            desc = f"Bullish structure (HH/HL: {higher_highs}/{higher_lows})"
        elif score > 0:
            desc = f"Slightly bullish (HH/HL: {higher_highs}/{higher_lows})"
        elif score > -0.5:
            desc = f"Slightly bearish (LH/LL: {lower_highs}/{lower_lows})"
        else:
            desc = f"Bearish structure (LH/LL: {lower_highs}/{lower_lows})"

        return score, desc

    def _measure_range_efficiency(self, closes):
        """Measure how efficiently price moves (trending vs choppy)."""
        n = len(closes)
        if n < 20:
            return 0, "Insufficient data"

        # Efficiency Ratio: net move / sum of absolute moves
        net_move = abs(closes[-1] - closes[0])
        sum_moves = sum(abs(closes[i] - closes[i-1]) for i in range(1, n))

        if sum_moves == 0:
            return 0, "No movement"

        efficiency = net_move / sum_moves

        # High efficiency = trending, low = ranging/choppy
        score = (efficiency - 0.3) * 2.5  # Remap around 0.3 midpoint
        score = max(-1, min(1, score))

        if efficiency > 0.6:
            desc = f"Highly efficient move ({efficiency:.2f}) — strong trend"
        elif efficiency > 0.3:
            desc = f"Moderate efficiency ({efficiency:.2f}) — some trend"
        elif efficiency > 0.15:
            desc = f"Low efficiency ({efficiency:.2f}) — choppy/ranging"
        else:
            desc = f"Very choppy ({efficiency:.2f}) — noise dominated"

        return score, desc

    def _classify_regime(self, trend, volatility, volume, structure, efficiency):
        """Classify regime from sub-signals."""
        # Strong trend signals
        if trend > 0.3 and efficiency > 0.2:
            return "TRENDING_UP", min(0.5 + abs(trend) * 0.4, 0.95)
        elif trend < -0.3 and efficiency > 0.2:
            return "TRENDING_DOWN", min(0.5 + abs(trend) * 0.4, 0.95)

        # High volatility
        if volatility > 0.5:
            return "VOLATILE", min(0.4 + volatility * 0.4, 0.9)

        # Range-bound
        if abs(trend) < 0.2 and efficiency < 0.25:
            return "RANGING", min(0.5 + (1 - efficiency) * 0.3, 0.85)

        # Mild trend
        if trend > 0.15:
            return "TRENDING_UP", 0.45
        elif trend < -0.15:
            return "TRENDING_DOWN", 0.45

        return "RANGING", 0.4

    def _ema(self, data, period):
        """Simple EMA approximation."""
        if not data:
            return 0
        multiplier = 2 / (period + 1)
        ema = data[0]
        for val in data[1:]:
            ema = (val - ema) * multiplier + ema
        return ema

    def _atr(self, highs, lows, closes, period=14):
        """Calculate Average True Range."""
        if len(highs) < period + 1:
            period = len(highs) - 1
        if period < 1:
            return 0

        trs = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            trs.append(tr)

        return np.mean(trs[-period:]) if trs else 0

    def get_regime_weights(self, regime):
        """
        Get signal weights appropriate for the current regime.
        Different regimes favor different prediction approaches.
        """
        weights = {
            "TRENDING_UP": {
                "momentum": 0.35,
                "fundamentals": 0.25,
                "liquidity": 0.15,
                "mean_reversion": 0.05,
                "orderbook": 0.20,
            },
            "TRENDING_DOWN": {
                "momentum": 0.35,
                "fundamentals": 0.20,
                "liquidity": 0.15,
                "mean_reversion": 0.05,
                "orderbook": 0.25,
            },
            "RANGING": {
                "momentum": 0.10,
                "fundamentals": 0.15,
                "liquidity": 0.25,
                "mean_reversion": 0.35,
                "orderbook": 0.15,
            },
            "VOLATILE": {
                "momentum": 0.15,
                "fundamentals": 0.30,
                "liquidity": 0.25,
                "mean_reversion": 0.10,
                "orderbook": 0.20,
            },
            "ACCUMULATION": {
                "momentum": 0.15,
                "fundamentals": 0.35,
                "liquidity": 0.25,
                "mean_reversion": 0.05,
                "orderbook": 0.20,
            },
            "DISTRIBUTION": {
                "momentum": 0.20,
                "fundamentals": 0.30,
                "liquidity": 0.25,
                "mean_reversion": 0.05,
                "orderbook": 0.20,
            },
        }
        return weights.get(regime, weights["RANGING"])
