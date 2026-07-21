"""
Smart Money System - VPIN (Volume-Synchronized Probability of Informed Trading)
Measures order flow toxicity. When VPIN spikes, informed traders are active.
High VPIN = big move coming. Don't trade against the flow.
"""
import time
import numpy as np
from collections import deque


class VpineEngine:
    def __init__(self, n_buckets=50, bucket_size=1000):
        """
        n_buckets: number of volume buckets to use for VPIN calculation
        bucket_size: volume per bucket (in ETH)
        """
        self.n_buckets = n_buckets
        self.bucket_size = bucket_size
        self.buckets = deque(maxlen=n_buckets)
        self.current_bucket = {"buy": 0, "sell": 0, "total": 0}
        self.vpin = 0
        self.vpin_history = deque(maxlen=3600)
        self.toxicity_level = "LOW"

    def update(self, trades):
        """
        Process trades and update VPIN.
        VPIN = |buy_volume - sell_volume| / total_volume (averaged over N buckets)
        """
        if not trades:
            return

        for t in trades:
            qty = t.get("qty", 0)
            side = t.get("side", "buy")

            if side == "buy":
                self.current_bucket["buy"] += qty
            else:
                self.current_bucket["sell"] += qty
            self.current_bucket["total"] += qty

            # If bucket is full, finalize and start new one
            if self.current_bucket["total"] >= self.bucket_size:
                self._finalize_bucket()

        # Calculate VPIN
        self._calc_vpin()

    def _finalize_bucket(self):
        """Finalize current bucket and add to history"""
        self.buckets.append({
            "buy": self.current_bucket["buy"],
            "sell": self.current_bucket["sell"],
            "total": self.current_bucket["total"],
            "time": time.time(),
        })
        self.current_bucket = {"buy": 0, "sell": 0, "total": 0}

    def _calc_vpin(self):
        """
        VPIN = (1/N) * Σ|V_buy - V_sell| / V_total
        """
        if len(self.buckets) < 10:
            self.vpin = 0
            return

        sum_abs = 0
        count = 0
        for b in self.buckets:
            if b["total"] > 0:
                sum_abs += abs(b["buy"] - b["sell"]) / b["total"]
                count += 1

        if count > 0:
            self.vpin = sum_abs / count
        else:
            self.vpin = 0

        # Toxicity level
        if self.vpin > 0.6:
            self.toxicity_level = "🔴 EXTREME — informed traders active, big move imminent"
        elif self.vpin > 0.4:
            self.toxicity_level = "🟠 HIGH — significant informed flow"
        elif self.vpin > 0.25:
            self.toxicity_level = "🟡 MODERATE — some informed activity"
        else:
            self.toxicity_level = "🟢 LOW — normal retail flow"

        self.vpin_history.append({
            "time": time.time(),
            "vpin": self.vpin,
            "toxicity": self.toxicity_level,
        })

    def get_state(self):
        """Get current VPIN state"""
        # Trend
        if len(self.vpin_history) >= 60:
            recent = [h["vpin"] for h in list(self.vpin_history)[-30:]]
            older = [h["vpin"] for h in list(self.vpin_history)[-60:-30]]
            if recent and older:
                trend = "RISING" if np.mean(recent) > np.mean(older) * 1.1 else \
                        "FALLING" if np.mean(recent) < np.mean(older) * 0.9 else "STABLE"
            else:
                trend = "STABLE"
        else:
            trend = "INSUFFICIENT DATA"

        return {
            "vpin": round(self.vpin, 4),
            "vpin_pct": round(self.vpin * 100, 1),
            "toxicity": self.toxicity_level,
            "trend": trend,
            "buckets_filled": len(self.buckets),
        }
