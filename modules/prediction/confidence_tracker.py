"""
Smart Money System - Confidence Tracker

Tracks prediction accuracy over time and auto-calibrates confidence.

How it works:
1. Records every prediction (direction, magnitude, timeframe)
2. Tracks actual outcomes
3. Calculates accuracy metrics per regime, per signal strength, etc.
4. Adjusts future confidence based on historical performance

This is the SELF-IMPROVEMENT loop — the system learns from its mistakes.
"""

import json
import os
import numpy as np
from datetime import datetime, timedelta


class ConfidenceTracker:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.predictions_file = os.path.join(data_dir, "predictions.json")
        self.accuracy_file = os.path.join(data_dir, "accuracy_stats.json")
        os.makedirs(data_dir, exist_ok=True)

        self.predictions = self._load_predictions()
        self.accuracy_stats = self._load_accuracy()

    def record_prediction(self, prediction):
        """
        Record a prediction for future verification.

        Args:
            prediction: {
                "direction": "UP" / "DOWN",
                "expected_move_pct": float,
                "expected_timeframe_days": float,
                "confidence": float,
                "regime": str,
                "signal_score": float,
                "current_price": float,
                "targets": dict,
            }
        """
        record = {
            "id": len(self.predictions) + 1,
            "timestamp": datetime.now().isoformat(),
            "direction": prediction.get("direction", "UNKNOWN"),
            "expected_move_pct": prediction.get("expected_move_pct", 0),
            "expected_timeframe_days": prediction.get("expected_timeframe_days", 7),
            "confidence": prediction.get("confidence", 0.5),
            "regime": prediction.get("regime", "UNKNOWN"),
            "signal_score": prediction.get("signal_score", 0),
            "current_price": prediction.get("current_price", 0),
            "targets": prediction.get("targets", {}),
            "verified": False,
            "actual_outcome": None,
        }

        self.predictions.append(record)
        self._save_predictions()
        return record

    def verify_predictions(self, current_price, candles=None):
        """
        Check pending predictions against actual price movement.

        Args:
            current_price: current ETH price
            candles: optional candle data for detailed verification

        Returns: list of newly verified predictions
        """
        verified = []
        now = datetime.now()

        for pred in self.predictions:
            if pred["verified"]:
                continue

            pred_time = datetime.fromisoformat(pred["timestamp"])
            timeframe_days = pred["expected_timeframe_days"]
            deadline = pred_time + timedelta(days=timeframe_days * 1.5)  # 150% of expected time

            # Only verify if deadline has passed
            if now < deadline:
                continue

            entry_price = pred["current_price"]
            if entry_price == 0:
                continue

            # Calculate actual outcome
            actual_change_pct = (current_price - entry_price) / entry_price * 100

            # Was direction correct?
            expected_dir = pred["direction"]
            if expected_dir == "UP":
                direction_correct = actual_change_pct > 0
            elif expected_dir == "DOWN":
                direction_correct = actual_change_pct < 0
            else:
                direction_correct = None

            # Was magnitude within target?
            expected_pct = pred["expected_move_pct"]
            magnitude_error = abs(abs(actual_change_pct) - expected_pct)

            # Did price reach 1-sigma target?
            target_1s = pred["targets"].get("1sigma", {}).get("price", 0)
            if target_1s > 0 and expected_dir == "UP":
                hit_1sigma = current_price >= target_1s
            elif target_1s > 0 and expected_dir == "DOWN":
                hit_1sigma = current_price <= target_1s
            else:
                hit_1sigma = None

            pred["verified"] = True
            pred["actual_outcome"] = {
                "actual_change_pct": round(actual_change_pct, 2),
                "direction_correct": direction_correct,
                "magnitude_error": round(magnitude_error, 2),
                "hit_1sigma": hit_1sigma,
                "price_at_verification": current_price,
                "verified_at": now.isoformat(),
            }

            verified.append(pred)

        if verified:
            self._save_predictions()
            self._update_accuracy_stats()

        return verified

    def get_accuracy_stats(self):
        """Get comprehensive accuracy statistics."""
        verified = [p for p in self.predictions if p["verified"]]

        if not verified:
            return {
                "total_predictions": len(self.predictions),
                "verified": 0,
                "message": "No verified predictions yet"
            }

        # Overall metrics
        direction_correct = sum(
            1 for p in verified
            if p["actual_outcome"]["direction_correct"]
        )
        direction_total = sum(
            1 for p in verified
            if p["actual_outcome"]["direction_correct"] is not None
        )

        hit_1sigma = sum(
            1 for p in verified
            if p["actual_outcome"].get("hit_1sigma")
        )

        # Per-regime accuracy
        regime_accuracy = {}
        for regime in ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE", "ACCUMULATION", "DISTRIBUTION"]:
            regime_preds = [p for p in verified if p["regime"] == regime]
            if regime_preds:
                correct = sum(1 for p in regime_preds if p["actual_outcome"]["direction_correct"])
                total = sum(1 for p in regime_preds if p["actual_outcome"]["direction_correct"] is not None)
                regime_accuracy[regime] = {
                    "correct": correct,
                    "total": total,
                    "accuracy": round(correct / total, 2) if total > 0 else 0
                }

        # Per-confidence-level accuracy
        confidence_buckets = {"low": [], "medium": [], "high": []}
        for p in verified:
            conf = p["confidence"]
            if conf >= 0.7:
                confidence_buckets["high"].append(p)
            elif conf >= 0.4:
                confidence_buckets["medium"].append(p)
            else:
                confidence_buckets["low"].append(p)

        confidence_accuracy = {}
        for level, preds in confidence_buckets.items():
            if preds:
                correct = sum(1 for p in preds if p["actual_outcome"]["direction_correct"])
                total = sum(1 for p in preds if p["actual_outcome"]["direction_correct"] is not None)
                confidence_accuracy[level] = {
                    "correct": correct,
                    "total": total,
                    "accuracy": round(correct / total, 2) if total > 0 else 0
                }

        # Magnitude accuracy
        magnitude_errors = [
            p["actual_outcome"]["magnitude_error"]
            for p in verified
            if p["actual_outcome"]["magnitude_error"] is not None
        ]

        # Recent performance (last 10 predictions)
        recent = verified[-10:]
        recent_correct = sum(1 for p in recent if p["actual_outcome"]["direction_correct"])
        recent_total = sum(1 for p in recent if p["actual_outcome"]["direction_correct"] is not None)

        return {
            "total_predictions": len(self.predictions),
            "verified": len(verified),
            "direction_accuracy": {
                "correct": direction_correct,
                "total": direction_total,
                "rate": round(direction_correct / direction_total, 2) if direction_total > 0 else 0
            },
            "1sigma_hit_rate": round(hit_1sigma / len(verified), 2) if verified else 0,
            "avg_magnitude_error": round(np.mean(magnitude_errors), 2) if magnitude_errors else 0,
            "regime_accuracy": regime_accuracy,
            "confidence_accuracy": confidence_accuracy,
            "recent_accuracy": round(recent_correct / recent_total, 2) if recent_total > 0 else 0,
            "timestamp": datetime.now().isoformat()
        }

    def get_calibrated_confidence(self, raw_confidence, regime, signal_score):
        """
        Adjust confidence based on historical accuracy.

        If the system has been accurate for a given regime/confidence level,
        boost confidence. If inaccurate, reduce it.
        """
        stats = self.get_accuracy_stats()

        if stats.get("verified", 0) < 5:
            return raw_confidence  # Not enough data to calibrate

        # Regime adjustment
        regime_acc = stats.get("regime_accuracy", {}).get(regime, {})
        regime_rate = regime_acc.get("accuracy", 0.5)
        regime_adjustment = (regime_rate - 0.5) * 0.4  # ±20% adjustment

        # Confidence level adjustment
        if raw_confidence >= 0.7:
            conf_level = "high"
        elif raw_confidence >= 0.4:
            conf_level = "medium"
        else:
            conf_level = "low"

        conf_acc = stats.get("confidence_accuracy", {}).get(conf_level, {})
        conf_rate = conf_acc.get("accuracy", 0.5)
        conf_adjustment = (conf_rate - 0.5) * 0.3  # ±15% adjustment

        # Recent trend adjustment
        recent_rate = stats.get("recent_accuracy", 0.5)
        recent_adjustment = (recent_rate - 0.5) * 0.2  # ±10% adjustment

        # Apply adjustments
        calibrated = raw_confidence + regime_adjustment + conf_adjustment + recent_adjustment
        calibrated = max(0.1, min(0.95, calibrated))

        return round(calibrated, 2)

    def _update_accuracy_stats(self):
        """Update stored accuracy statistics."""
        self.accuracy_stats = self.get_accuracy_stats()
        self._save_accuracy()

    def _load_predictions(self):
        if os.path.exists(self.predictions_file):
            try:
                with open(self.predictions_file, "r") as f:
                    return json.load(f)
            except:
                pass
        return []

    def _save_predictions(self):
        with open(self.predictions_file, "w") as f:
            json.dump(self.predictions, f, indent=2, default=str)

    def _load_accuracy(self):
        if os.path.exists(self.accuracy_file):
            try:
                with open(self.accuracy_file, "r") as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_accuracy(self):
        with open(self.accuracy_file, "w") as f:
            json.dump(self.accuracy_stats, f, indent=2, default=str)

    def format_accuracy(self):
        """Format accuracy report for display."""
        stats = self.get_accuracy_stats()

        if stats.get("verified", 0) == 0:
            return (
                f"📊 <b>CONFIDENCE TRACKER</b>\n\n"
                f"Total predictions: {stats['total_predictions']}\n"
                f"Verified: 0\n\n"
                f"⏳ Not enough data yet. Predictions will be verified "
                f"after their timeframes expire."
            )

        da = stats["direction_accuracy"]
        lines = [
            f"📊 <b>CONFIDENCE TRACKER</b>",
            f"",
            f"<b>Overall Accuracy:</b>",
            f"  Direction: {da['correct']}/{da['total']} ({da['rate']:.0%})",
            f"  1σ Hit Rate: {stats['1sigma_hit_rate']:.0%}",
            f"  Avg Magnitude Error: {stats['avg_magnitude_error']:.1f}%",
            f"  Recent (last 10): {stats['recent_accuracy']:.0%}",
            f"",
            f"<b>By Regime:</b>",
        ]

        for regime, acc in stats.get("regime_accuracy", {}).items():
            if acc["total"] > 0:
                lines.append(f"  {regime}: {acc['correct']}/{acc['total']} ({acc['accuracy']:.0%})")

        lines.append(f"")
        lines.append(f"<b>By Confidence Level:</b>")
        for level, acc in stats.get("confidence_accuracy", {}).items():
            if acc["total"] > 0:
                lines.append(f"  {level}: {acc['correct']}/{acc['total']} ({acc['accuracy']:.0%})")

        return "\n".join(lines)
