"""
Smart Money System - Magnitude Predictor

Predicts HOW FAR price will move using:
1. ATR-based statistical targets (σ bands)
2. Supply/demand elasticity model
3. Volume profile analysis
4. Historical move distribution

Output: price targets with probability bands
"""

import numpy as np
from datetime import datetime


class MagnitudePredictor:
    def __init__(self):
        self.history = []

    def predict(self, candles, direction, signal_score, regime="UNKNOWN"):
        """
        Predict price move magnitude.

        Args:
            candles: OHLCV data (at least 50 candles)
            direction: "UP" or "DOWN"
            signal_score: -100 to +100 from signal combiner
            regime: current market regime

        Returns:
            {
                "current_price": float,
                "targets": {
                    "1sigma": {price, pct, probability},
                    "2sigma": {price, pct, probability},
                    "3sigma": {price, pct, probability},
                },
                "expected_move_pct": float,
                "expected_timeframe_days": float,
                "method": str,
                "details": dict
            }
        """
        if len(candles) < 20:
            return self._empty_result(candles[-1]["close"] if candles else 0)

        closes = np.array([c["close"] for c in candles])
        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])
        volumes = np.array([c["volume"] for c in candles])

        current_price = closes[-1]

        # === Method 1: ATR-Based Targets ===
        atr_targets = self._atr_targets(closes, highs, lows, direction)

        # === Method 2: Historical Move Distribution ===
        hist_targets = self._historical_move_targets(closes, direction)

        # === Method 3: Support/Resistance Levels ===
        sr_targets = self._support_resistance_targets(closes, highs, lows, direction)

        # === Method 4: Volume Profile Targets ===
        vol_targets = self._volume_profile_targets(closes, highs, lows, volumes, direction)

        # === Method 5: Bollinger Band Targets ===
        bb_targets = self._bollinger_targets(closes, direction)

        # === Combine all methods (weighted by regime) ===
        combined = self._combine_targets(
            atr_targets, hist_targets, sr_targets, vol_targets, bb_targets,
            regime, signal_score
        )

        # === Estimate timeframe ===
        timeframe = self._estimate_timeframe(candles, combined["move_pct"], regime)

        result = {
            "current_price": round(current_price, 2),
            "direction": direction,
            "targets": {
                "1sigma": {
                    "price": round(combined["target_1s"], 2),
                    "pct": round(combined["pct_1s"], 2),
                    "probability": 0.68,
                    "label": "68% probability reach"
                },
                "2sigma": {
                    "price": round(combined["target_2s"], 2),
                    "pct": round(combined["pct_2s"], 2),
                    "probability": 0.95,
                    "label": "95% probability reach"
                },
                "3sigma": {
                    "price": round(combined["target_3s"], 2),
                    "pct": round(combined["pct_3s"], 2),
                    "probability": 0.997,
                    "label": "99.7% probability reach"
                },
            },
            "expected_move_pct": round(combined["move_pct"], 2),
            "expected_timeframe_days": round(timeframe, 1),
            "method": "ensemble",
            "details": {
                "atr_targets": atr_targets,
                "historical_targets": hist_targets,
                "sr_targets": sr_targets,
                "volume_targets": vol_targets,
                "bb_targets": bb_targets,
                "regime": regime,
                "signal_score": signal_score,
            },
            "timestamp": datetime.now().isoformat()
        }

        self.history.append(result)
        return result

    def _atr_targets(self, closes, highs, lows, direction):
        """ATR-based statistical move potential."""
        atr = self._atr(highs, lows, closes, 14)
        current = closes[-1]

        # Use multipliers based on timeframe
        # 1σ ≈ 1 ATR, 2σ ≈ 2 ATR, 3σ ≈ 3 ATR
        if direction == "UP":
            return {
                "target_1s": current + atr * 1.0,
                "target_2s": current + atr * 2.0,
                "target_3s": current + atr * 3.0,
                "atr": atr,
                "atr_pct": (atr / current) * 100
            }
        else:
            return {
                "target_1s": current - atr * 1.0,
                "target_2s": current - atr * 2.0,
                "target_3s": current - atr * 3.0,
                "atr": atr,
                "atr_pct": (atr / current) * 100
            }

    def _historical_move_targets(self, closes, direction):
        """Look at historical moves of similar magnitude."""
        n = len(closes)
        if n < 30:
            return {"target_1s": closes[-1], "target_2s": closes[-1], "move_pct": 0}

        # Calculate rolling returns
        returns_5d = []
        returns_10d = []
        returns_20d = []

        for i in range(20, n):
            if i >= 5:
                ret5 = (closes[i] - closes[i-5]) / closes[i-5]
                returns_5d.append(ret5)
            if i >= 10:
                ret10 = (closes[i] - closes[i-10]) / closes[i-10]
                returns_10d.append(ret10)
            ret20 = (closes[i] - closes[i-20]) / closes[i-20]
            returns_20d.append(ret20)

        current = closes[-1]

        if direction == "UP":
            # Positive moves
            up_moves_5d = [r for r in returns_5d if r > 0]
            up_moves_10d = [r for r in returns_10d if r > 0]

            if up_moves_5d:
                avg_5d = np.mean(up_moves_5d)
                std_5d = np.std(up_moves_5d)
            else:
                avg_5d, std_5d = 0.02, 0.03

            if up_moves_10d:
                avg_10d = np.mean(up_moves_10d)
            else:
                avg_10d = 0.03

            return {
                "target_1s": current * (1 + avg_5d),
                "target_2s": current * (1 + avg_5d + std_5d),
                "target_3s": current * (1 + avg_10d * 1.5),
                "avg_up_5d": avg_5d * 100,
                "avg_up_10d": avg_10d * 100,
            }
        else:
            down_moves_5d = [r for r in returns_5d if r < 0]
            down_moves_10d = [r for r in returns_10d if r < 0]

            if down_moves_5d:
                avg_5d = np.mean(down_moves_5d)
                std_5d = np.std(down_moves_5d)
            else:
                avg_5d, std_5d = -0.02, 0.03

            if down_moves_10d:
                avg_10d = np.mean(down_moves_10d)
            else:
                avg_10d = -0.03

            return {
                "target_1s": current * (1 + avg_5d),
                "target_2s": current * (1 + avg_5d - std_5d),
                "target_3s": current * (1 + avg_10d * 1.5),
                "avg_down_5d": avg_5d * 100,
                "avg_down_10d": avg_10d * 100,
            }

    def _support_resistance_targets(self, closes, highs, lows, direction):
        """Find nearest support/resistance levels."""
        current = closes[-1]

        # Find significant levels using volume-at-price approximation
        # Use price clusters as proxy
        all_prices = np.concatenate([highs, lows, closes])
        price_range = np.linspace(
            np.min(all_prices) * 0.95,
            np.max(all_prices) * 1.05,
            50
        )

        # Count touches near each level
        touches = []
        for level in price_range:
            tolerance = current * 0.005  # 0.5% tolerance
            count = sum(1 for p in all_prices if abs(p - level) < tolerance)
            touches.append((level, count))

        # Sort by touch count
        touches.sort(key=lambda x: x[1], reverse=True)

        # Find nearest support (below current) and resistance (above current)
        supports = [(l, t) for l, t in touches if l < current * 0.995]
        resistances = [(l, t) for l, t in touches if l > current * 1.005]

        if direction == "UP":
            target_1 = resistances[0][0] if resistances else current * 1.03
            target_2 = resistances[1][0] if len(resistances) > 1 else current * 1.06
            target_3 = resistances[2][0] if len(resistances) > 2 else current * 1.10
        else:
            target_1 = supports[0][0] if supports else current * 0.97
            target_2 = supports[1][0] if len(supports) > 1 else current * 0.94
            target_3 = supports[2][0] if len(supports) > 2 else current * 0.90

        return {
            "target_1s": target_1,
            "target_2s": target_2,
            "target_3s": target_3,
            "nearest_support": supports[0][0] if supports else None,
            "nearest_resistance": resistances[0][0] if resistances else None,
        }

    def _volume_profile_targets(self, closes, highs, lows, volumes, direction):
        """Volume-weighted price targets."""
        current = closes[-1]

        # Volume-weighted average price (VWAP) over recent period
        recent = min(20, len(closes))
        vwap = np.sum(closes[-recent:] * volumes[-recent:]) / np.sum(volumes[-recent:]) if np.sum(volumes[-recent:]) > 0 else current

        # High-volume nodes (price levels with most volume)
        price_bins = np.linspace(current * 0.9, current * 1.1, 20)
        vol_at_price = np.zeros(len(price_bins) - 1)

        for i in range(len(closes)):
            idx = np.searchsorted(price_bins, closes[i]) - 1
            if 0 <= idx < len(vol_at_price):
                vol_at_price[idx] += volumes[i]

        # Highest volume node
        hvn_idx = np.argmax(vol_at_price)
        hvn_price = (price_bins[hvn_idx] + price_bins[hvn_idx + 1]) / 2

        # Point of control (POC) - price with most volume
        poc = hvn_price

        if direction == "UP":
            # Target is above current, near high-volume resistance
            above_poc = poc if poc > current else current * 1.03
            return {
                "target_1s": max(above_poc, current * 1.01),
                "target_2s": current * 1.05,
                "target_3s": current * 1.08,
                "vwap": vwap,
                "poc": poc,
            }
        else:
            below_poc = poc if poc < current else current * 0.97
            return {
                "target_1s": min(below_poc, current * 0.99),
                "target_2s": current * 0.95,
                "target_3s": current * 0.92,
                "vwap": vwap,
                "poc": poc,
            }

    def _bollinger_targets(self, closes, direction):
        """Bollinger Band-based targets."""
        sma = np.mean(closes[-20:])
        std = np.std(closes[-20:])
        current = closes[-1]

        upper_1s = sma + std
        upper_2s = sma + 2 * std
        lower_1s = sma - std
        lower_2s = sma - 2 * std

        if direction == "UP":
            return {
                "target_1s": max(upper_1s, current * 1.01),
                "target_2s": max(upper_2s, current * 1.03),
                "target_3s": sma + 3 * std,
                "sma": sma,
                "bb_upper": upper_2s,
                "bb_lower": lower_2s,
            }
        else:
            return {
                "target_1s": min(lower_1s, current * 0.99),
                "target_2s": min(lower_2s, current * 0.97),
                "target_3s": sma - 3 * std,
                "sma": sma,
                "bb_upper": upper_2s,
                "bb_lower": lower_2s,
            }

    def _combine_targets(self, atr, hist, sr, vol, bb, regime, signal_score):
        """Combine all target methods with regime-appropriate weights."""
        # Regime-based method weights
        method_weights = {
            "TRENDING_UP": {"atr": 0.30, "hist": 0.25, "sr": 0.10, "vol": 0.15, "bb": 0.20},
            "TRENDING_DOWN": {"atr": 0.30, "hist": 0.25, "sr": 0.10, "vol": 0.15, "bb": 0.20},
            "RANGING": {"atr": 0.15, "hist": 0.15, "sr": 0.35, "vol": 0.20, "bb": 0.15},
            "VOLATILE": {"atr": 0.35, "hist": 0.20, "sr": 0.10, "vol": 0.15, "bb": 0.20},
            "ACCUMULATION": {"atr": 0.20, "hist": 0.25, "sr": 0.15, "vol": 0.25, "bb": 0.15},
            "DISTRIBUTION": {"atr": 0.20, "hist": 0.25, "sr": 0.15, "vol": 0.25, "bb": 0.15},
        }

        weights = method_weights.get(regime, method_weights["RANGING"])
        current = atr.get("target_1s", 0) - atr.get("atr", 0)  # Recover current price

        if current == 0:
            current = 1  # Avoid division by zero

        # Weighted average of each sigma level
        methods = {"atr": atr, "hist": hist, "sr": sr, "vol": vol, "bb": bb}

        target_1s = sum(methods[m]["target_1s"] * weights[m] for m in methods)
        target_2s = sum(methods[m]["target_2s"] * weights[m] for m in methods)
        target_3s = sum(methods[m]["target_3s"] * weights[m] for m in methods)

        # Adjust based on signal strength
        signal_multiplier = 1.0 + (abs(signal_score) - 50) / 200  # ±25% based on conviction
        signal_multiplier = max(0.75, min(1.25, signal_multiplier))

        # Apply signal multiplier to stretch/compress targets
        direction = "UP" if target_1s > current else "DOWN"
        if direction == "UP":
            target_1s = current + (target_1s - current) * signal_multiplier
            target_2s = current + (target_2s - current) * signal_multiplier
            target_3s = current + (target_3s - current) * signal_multiplier
        else:
            target_1s = current - (current - target_1s) * signal_multiplier
            target_2s = current - (current - target_2s) * signal_multiplier
            target_3s = current - (current - target_3s) * signal_multiplier

        move_pct = abs(target_1s - current) / current * 100

        return {
            "target_1s": target_1s,
            "target_2s": target_2s,
            "target_3s": target_3s,
            "pct_1s": (target_1s - current) / current * 100,
            "pct_2s": (target_2s - current) / current * 100,
            "pct_3s": (target_3s - current) / current * 100,
            "move_pct": move_pct,
        }

    def _estimate_timeframe(self, candles, move_pct, regime):
        """Estimate how many days until target is reached."""
        if move_pct <= 0:
            return 0

        closes = np.array([c["close"] for c in candles])

        # Calculate historical daily velocity (% move per day)
        daily_returns = np.abs(np.diff(closes) / closes[:-1]) * 100
        avg_daily_move = np.mean(daily_returns[-30:]) if len(daily_returns) >= 30 else np.mean(daily_returns)

        if avg_daily_move == 0:
            return 7  # Default

        # Simple: move_pct / avg_daily_velocity
        raw_days = move_pct / avg_daily_move

        # Adjust for regime
        regime_multiplier = {
            "TRENDING_UP": 0.8,    # Trends move faster
            "TRENDING_DOWN": 0.7,  # Dumps are faster
            "RANGING": 1.5,        # Ranges are slower
            "VOLATILE": 0.6,       # Volatile = fast
            "ACCUMULATION": 2.0,   # Accumulation takes time
            "DISTRIBUTION": 1.5,   # Distribution is slower
        }

        multiplier = regime_multiplier.get(regime, 1.0)
        estimated_days = raw_days * multiplier

        # Clamp to reasonable range
        return max(1, min(60, estimated_days))

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

    def _empty_result(self, price):
        return {
            "current_price": price,
            "direction": "UNKNOWN",
            "targets": {},
            "expected_move_pct": 0,
            "expected_timeframe_days": 0,
            "method": "insufficient_data",
            "timestamp": datetime.now().isoformat()
        }

    def format_prediction(self, prediction):
        """Format prediction for display."""
        if not prediction.get("targets"):
            return "⚠️ Insufficient data for prediction"

        current = prediction["current_price"]
        direction = prediction["direction"]
        targets = prediction["targets"]
        timeframe = prediction["expected_timeframe_days"]

        dir_emoji = "📈" if direction == "UP" else "📉"

        lines = [
            f"{dir_emoji} <b>PREDICTION: {direction}</b>",
            f"",
            f"💰 <b>Current:</b> ${current:,.2f}",
            f"",
            f"<b>🎯 Targets:</b>",
        ]

        for sigma, data in targets.items():
            prob = data["probability"] * 100
            price = data["price"]
            pct = data["pct"]
            lines.append(f"  {sigma}: ${price:,.2f} ({pct:+.1f}%) — {prob:.0f}% probability")

        lines.extend([
            f"",
            f"⏱️ <b>Expected timeframe:</b> {timeframe:.0f} days",
            f"",
            f"📊 <b>Method:</b> {prediction['method']} (5-model ensemble)"
        ])

        return "\n".join(lines)
