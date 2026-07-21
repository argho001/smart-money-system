"""
Smart Money System - CVD Engine (Cumulative Volume Delta)
Tracks cumulative net buying vs selling over time.
Detects divergences between price and CVD = institutional activity.
"""
import time
import numpy as np
from collections import deque


class CVDEngine:
    def __init__(self):
        # CVD state
        self.cvd = 0  # Running cumulative volume delta
        self.cvd_history = deque(maxlen=3600)  # 1 hour of per-second CVD values
        self.price_history = deque(maxlen=3600)

        # Divergence detection
        self.divergence = None
        self.divergence_history = deque(maxlen=100)

        # CVD rate of change
        self.cvd_roc_1m = 0
        self.cvd_roc_5m = 0
        self.cvd_roc_15m = 0

    def update(self, trades):
        """
        Process new trades and update CVD.
        trades: list of {qty, side, price, time}
        """
        if not trades:
            return

        for t in trades:
            qty = t.get("qty", 0)
            side = t.get("side", "buy")

            # Buy = positive delta, Sell = negative delta
            delta = qty if side == "buy" else -qty
            self.cvd += delta

        # Snapshot
        now = time.time()
        self.cvd_history.append({"time": now, "cvd": self.cvd})
        if trades:
            self.price_history.append({"time": now, "price": trades[-1].get("price", 0)})

        # Calculate rates of change
        self._calc_roc()

        # Check for divergence
        self._check_divergence()

    def _calc_roc(self):
        """CVD rate of change at different timeframes"""
        now = time.time()
        cvd_now = self.cvd

        for minutes, attr in [(1, "cvd_roc_1m"), (5, "cvd_roc_5m"), (15, "cvd_roc_15m")]:
            cutoff = now - (minutes * 60)
            old = None
            for snap in self.cvd_history:
                if snap["time"] >= cutoff:
                    old = snap["cvd"]
                    break
            if old is not None:
                setattr(self, attr, cvd_now - old)
            else:
                setattr(self, attr, 0)

    def _check_divergence(self):
        """
        Detect CVD-Price divergence.
        Bullish divergence: Price makes lower low, CVD makes higher low
        Bearish divergence: Price makes higher high, CVD makes lower high
        """
        if len(self.cvd_history) < 120 or len(self.price_history) < 120:
            self.divergence = None
            return

        # Get last 5 minutes of data
        now = time.time()
        recent_cutoff = now - 300  # 5 min
        older_cutoff = now - 600   # 10 min

        recent_prices = [p["price"] for p in self.price_history if p["time"] >= recent_cutoff]
        older_prices = [p["price"] for p in self.price_history if older_cutoff <= p["time"] < recent_cutoff]

        recent_cvd = [c["cvd"] for c in self.cvd_history if c["time"] >= recent_cutoff]
        older_cvd = [c["cvd"] for c in self.cvd_history if older_cutoff <= c["time"] < recent_cutoff]

        if not recent_prices or not older_prices or not recent_cvd or not older_cvd:
            self.divergence = None
            return

        # Compare highs and lows
        price_high_recent = max(recent_prices)
        price_high_older = max(older_prices)
        price_low_recent = min(recent_prices)
        price_low_older = min(older_prices)

        cvd_high_recent = max(recent_cvd)
        cvd_high_older = max(older_cvd)
        cvd_low_recent = min(recent_cvd)
        cvd_low_older = min(older_cvd)

        # Bearish divergence: price higher high, CVD lower high
        if price_high_recent > price_high_older * 1.001 and cvd_high_recent < cvd_high_older:
            self.divergence = {
                "type": "BEARISH",
                "signal": "🔴 BEARISH DIVERGENCE — price up but CVD down = institutions selling",
                "price_higher": True,
                "cvd_higher": False,
                "strength": min(abs(price_high_recent - price_high_older) / price_high_older * 100, 10),
                "time": now,
            }
            self.divergence_history.append(self.divergence)

        # Bullish divergence: price lower low, CVD higher low
        elif price_low_recent < price_low_older * 0.999 and cvd_low_recent > cvd_low_older:
            self.divergence = {
                "type": "BULLISH",
                "signal": "🟢 BULLISH DIVERGENCE — price down but CVD up = institutions buying",
                "price_higher": False,
                "cvd_higher": True,
                "strength": min(abs(price_low_older - price_low_recent) / price_low_older * 100, 10),
                "time": now,
            }
            self.divergence_history.append(self.divergence)
        else:
            self.divergence = None

    def get_state(self):
        """Get current CVD state"""
        # CVD trend
        if self.cvd_roc_5m > 100:
            trend = "🟢 STRONG BUYING"
        elif self.cvd_roc_5m > 20:
            trend = "🟢 BUYING"
        elif self.cvd_roc_5m > -20:
            trend = "⚪ NEUTRAL"
        elif self.cvd_roc_5m > -100:
            trend = "🔴 SELLING"
        else:
            trend = "🔴 STRONG SELLING"

        return {
            "cvd": round(self.cvd, 2),
            "cvd_roc_1m": round(self.cvd_roc_1m, 2),
            "cvd_roc_5m": round(self.cvd_roc_5m, 2),
            "cvd_roc_15m": round(self.cvd_roc_15m, 2),
            "cvd_trend": trend,
            "divergence": self.divergence,
            "recent_divergences": [
                {"type": d["type"], "signal": d["signal"], "strength": d["strength"]}
                for d in list(self.divergence_history)[-5:]
            ],
        }
