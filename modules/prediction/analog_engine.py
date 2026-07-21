"""
Smart Money System - Historical Analog Engine

Finds historical periods that look like RIGHT NOW and measures what happened next.

How it works:
1. Capture a "fingerprint" of current conditions (volatility, trend, volume, funding, etc.)
2. Search historical data for similar fingerprints
3. Measure what price did after each analog
4. Report the aggregate: "When conditions looked like this, price did X"
"""

import numpy as np
import json
import os
from datetime import datetime


class AnalogEngine:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.analog_history = []
        self.fingerprint_cache = {}

    def find_analogs(self, candles, current_fingerprint, min_similarity=0.7, max_analogs=10):
        """
        Find historical periods similar to current conditions.

        Args:
            candles: full OHLCV history
            current_fingerprint: dict of current conditions
            min_similarity: minimum similarity score (0-1)
            max_analogs: max number of analogs to return

        Returns:
            {
                "analogs": list of {date, similarity, outcome_5d, outcome_10d, outcome_20d},
                "summary": {avg_5d, avg_10d, avg_20d, win_rate, direction_consensus},
                "current_fingerprint": dict
            }
        """
        if len(candles) < 60:
            return {"analogs": [], "summary": {}, "current_fingerprint": current_fingerprint}

        # Build fingerprints for all historical windows
        window_size = 30  # 30-candle fingerprint
        analogs = []

        for i in range(window_size, len(candles) - 20):
            window = candles[i - window_size:i]
            hist_fingerprint = self._build_fingerprint(window)

            similarity = self._calculate_similarity(current_fingerprint, hist_fingerprint)

            if similarity >= min_similarity:
                # Measure outcome: what happened after this period?
                outcome = self._measure_outcome(candles, i)

                analogs.append({
                    "index": i,
                    "date": candles[i]["timestamp"].isoformat() if hasattr(candles[i]["timestamp"], 'isoformat') else str(candles[i]["timestamp"]),
                    "price_at_time": candles[i]["close"],
                    "similarity": round(similarity, 3),
                    "outcome_5d": outcome.get("5d", 0),
                    "outcome_10d": outcome.get("10d", 0),
                    "outcome_20d": outcome.get("20d", 0),
                    "outcome_direction": outcome.get("direction", "unknown"),
                    "fingerprint": hist_fingerprint,
                })

        # Sort by similarity, take top N
        analogs.sort(key=lambda x: x["similarity"], reverse=True)
        analogs = analogs[:max_analogs]

        # Calculate summary
        summary = self._summarize_analogs(analogs)

        result = {
            "analogs": analogs,
            "summary": summary,
            "current_fingerprint": current_fingerprint,
            "total_candidates": len([a for a in analogs if a["similarity"] >= min_similarity]),
            "timestamp": datetime.now().isoformat()
        }

        self.analog_history.append(result)
        return result

    def _build_fingerprint(self, candles):
        """Build a numerical fingerprint of a candle period."""
        closes = np.array([c["close"] for c in candles])
        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])
        volumes = np.array([c["volume"] for c in candles])

        # Trend: total return
        total_return = (closes[-1] - closes[0]) / closes[0]

        # Volatility: ATR as % of price
        atr = self._atr(highs, lows, closes, 14)
        atr_pct = atr / closes[-1] if closes[-1] > 0 else 0

        # Volume trend
        vol_early = np.mean(volumes[:len(volumes)//2])
        vol_late = np.mean(volumes[len(volumes)//2:])
        vol_trend = (vol_late - vol_early) / vol_early if vol_early > 0 else 0

        # Momentum (rate of change)
        roc_5 = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else 0
        roc_10 = (closes[-1] - closes[-11]) / closes[-11] if len(closes) >= 11 else 0

        # Efficiency ratio
        net_move = abs(closes[-1] - closes[0])
        sum_moves = sum(abs(closes[i] - closes[i-1]) for i in range(1, len(closes)))
        efficiency = net_move / sum_moves if sum_moves > 0 else 0

        # Volatility of volatility (vol clustering)
        daily_returns = np.abs(np.diff(closes) / closes[:-1])
        vol_of_vol = np.std(daily_returns) / np.mean(daily_returns) if np.mean(daily_returns) > 0 else 0

        # Price position in range (0 = at low, 1 = at high)
        price_range = np.max(highs) - np.min(lows)
        price_position = (closes[-1] - np.min(lows)) / price_range if price_range > 0 else 0.5

        return {
            "total_return": round(total_return, 4),
            "atr_pct": round(atr_pct, 4),
            "vol_trend": round(vol_trend, 4),
            "roc_5": round(roc_5, 4),
            "roc_10": round(roc_10, 4),
            "efficiency": round(efficiency, 4),
            "vol_of_vol": round(vol_of_vol, 4),
            "price_position": round(price_position, 4),
            "avg_volume": round(np.mean(volumes), 2),
            "volume_std": round(np.std(volumes), 2),
        }

    def _calculate_similarity(self, fp1, fp2):
        """Calculate similarity between two fingerprints (0 to 1)."""
        # Weighted Euclidean distance, normalized
        weights = {
            "total_return": 2.0,    # Most important
            "atr_pct": 1.5,         # Volatility matters
            "efficiency": 1.5,      # Trend efficiency
            "roc_5": 1.8,           # Short-term momentum
            "roc_10": 1.2,          # Medium-term momentum
            "vol_trend": 1.0,       # Volume behavior
            "price_position": 1.0,  # Where in range
            "vol_of_vol": 0.5,      # Less important
        }

        total_weight = 0
        weighted_distance = 0

        for key, weight in weights.items():
            if key in fp1 and key in fp2:
                # Normalize by typical range for each metric
                scale = self._get_scale(key)
                diff = abs(fp1[key] - fp2[key]) / scale
                weighted_distance += weight * diff ** 2
                total_weight += weight

        if total_weight == 0:
            return 0

        # Convert distance to similarity (0-1)
        avg_distance = np.sqrt(weighted_distance / total_weight)
        similarity = max(0, 1 - avg_distance)

        return similarity

    def _get_scale(self, key):
        """Get typical scale for normalization."""
        scales = {
            "total_return": 0.15,   # 15% is a big move
            "atr_pct": 0.05,        # 5% ATR is high
            "efficiency": 0.5,      # 0-1 range
            "roc_5": 0.10,          # 10% in 5 candles
            "roc_10": 0.15,         # 15% in 10 candles
            "vol_trend": 1.0,       # -1 to +1 range
            "price_position": 1.0,  # 0-1 range
            "vol_of_vol": 2.0,      # Can be high
        }
        return scales.get(key, 1.0)

    def _measure_outcome(self, candles, start_idx):
        """Measure what happened after a given point."""
        outcomes = {}

        for days, label in [(5, "5d"), (10, "10d"), (20, "20d")]:
            end_idx = start_idx + days
            if end_idx < len(candles):
                start_price = candles[start_idx]["close"]
                end_price = candles[end_idx]["close"]
                change = (end_price - start_price) / start_price
                outcomes[label] = round(change * 100, 2)
            else:
                outcomes[label] = None

        # Determine direction
        if outcomes.get("10d") is not None:
            if outcomes["10d"] > 2:
                outcomes["direction"] = "UP"
            elif outcomes["10d"] < -2:
                outcomes["direction"] = "DOWN"
            else:
                outcomes["direction"] = "FLAT"
        else:
            outcomes["direction"] = "unknown"

        return outcomes

    def _summarize_analogs(self, analogs):
        """Summarize analog outcomes."""
        if not analogs:
            return {
                "avg_5d": 0, "avg_10d": 0, "avg_20d": 0,
                "win_rate": 0, "direction_consensus": "NONE",
                "sample_size": 0
            }

        valid_5d = [a["outcome_5d"] for a in analogs if a["outcome_5d"] is not None]
        valid_10d = [a["outcome_10d"] for a in analogs if a["outcome_10d"] is not None]
        valid_20d = [a["outcome_20d"] for a in analogs if a["outcome_20d"] is not None]

        avg_5d = np.mean(valid_5d) if valid_5d else 0
        avg_10d = np.mean(valid_10d) if valid_10d else 0
        avg_20d = np.mean(valid_20d) if valid_20d else 0

        # Win rate (positive 10d return)
        win_rate = sum(1 for v in valid_10d if v > 0) / len(valid_10d) if valid_10d else 0

        # Direction consensus
        up_count = sum(1 for a in analogs if a.get("outcome_direction") == "UP")
        down_count = sum(1 for a in analogs if a.get("outcome_direction") == "DOWN")
        total = up_count + down_count

        if total == 0:
            consensus = "NONE"
        elif up_count / total > 0.65:
            consensus = "BULLISH"
        elif down_count / total > 0.65:
            consensus = "BEARISH"
        else:
            consensus = "MIXED"

        return {
            "avg_5d": round(avg_5d, 2),
            "avg_10d": round(avg_10d, 2),
            "avg_20d": round(avg_20d, 2),
            "win_rate": round(win_rate, 2),
            "direction_consensus": consensus,
            "up_count": up_count,
            "down_count": down_count,
            "sample_size": len(analogs),
        }

    def format_analogs(self, result):
        """Format analog results for display."""
        if not result.get("analogs"):
            return "⚠️ No historical analogs found"

        summary = result["summary"]
        analogs = result["analogs"]

        consensus_emoji = {
            "BULLISH": "🟢",
            "BEARISH": "🔴",
            "MIXED": "🟡",
            "NONE": "⚪"
        }.get(summary["direction_consensus"], "⚪")

        lines = [
            f"🔍 <b>HISTORICAL ANALOGS</b>",
            f"",
            f"{consensus_emoji} <b>Consensus:</b> {summary['direction_consensus']}",
            f"📊 <b>Sample size:</b> {summary['sample_size']} similar periods",
            f"🎯 <b>Win rate:</b> {summary['win_rate']:.0%}",
            f"",
            f"<b>📈 Average outcome after similar conditions:</b>",
            f"  5 days: {summary['avg_5d']:+.1f}%",
            f"  10 days: {summary['avg_10d']:+.1f}%",
            f"  20 days: {summary['avg_20d']:+.1f}%",
            f"",
            f"<b>🔎 Top analogs:</b>",
        ]

        for i, analog in enumerate(analogs[:5]):
            outcome = analog.get("outcome_10d", "N/A")
            if outcome != "N/A":
                outcome_str = f"{outcome:+.1f}%"
            else:
                outcome_str = "N/A"
            lines.append(
                f"  {i+1}. {analog['date'][:10]} — "
                f"similarity: {analog['similarity']:.0%} — "
                f"10d outcome: {outcome_str}"
            )

        return "\n".join(lines)

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

    def build_current_fingerprint(self, candles, extra_signals=None):
        """
        Build fingerprint for current conditions.
        Can merge candle-based fingerprint with external signals.
        """
        if len(candles) < 30:
            return {}

        window = candles[-30:]
        fp = self._build_fingerprint(window)

        # Merge extra signals if provided (funding, sentiment, etc.)
        if extra_signals:
            fp["funding_rate"] = extra_signals.get("funding_rate", 0)
            fp["sentiment_score"] = extra_signals.get("sentiment_score", 0)
            fp["whale_score"] = extra_signals.get("whale_score", 0)
            fp["orderbook_imbalance"] = extra_signals.get("orderbook_imbalance", 0)

        return fp
