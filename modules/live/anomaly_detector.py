"""
Smart Money System - Anomaly Detector
Tracks 'normal' for each metric and alerts when deviation > 2 standard deviations.
"""
import time
import json
import os
from collections import deque


class AnomalyDetector:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.history_file = os.path.join(data_dir, "anomaly_history.json")

        # Rolling windows for each metric (last 300 samples = ~5 min at 1/s)
        self.windows = {
            "trades_net": deque(maxlen=300),
            "trades_total_vol": deque(maxlen=300),
            "imbalance": deque(maxlen=300),
            "funding_rate_pct": deque(maxlen=300),
            "large_net": deque(maxlen=300),
            "liq_net": deque(maxlen=300),
            "spread_pct": deque(maxlen=300),
            "composite": deque(maxlen=300),
            "accel_10s": deque(maxlen=300),
            "buying_pressure": deque(maxlen=300),
            "whale_score": deque(maxlen=300),
        }

        self.alerts = []
        self.alert_cooldown = {}  # prevent spam
        self.anomaly_log = []

    def update(self, state):
        """Feed new state, returns list of anomaly alerts"""
        now = time.time()
        new_alerts = []

        for key in self.windows:
            val = state.get(key, 0)
            if val is not None:
                self.windows[key].append(val)

        # Need at least 30 samples to establish baseline
        if len(self.windows["trades_total_vol"]) < 30:
            return []

        # Check each metric for anomalies
        checks = [
            ("trades_net", "Trade Flow", 2.5, "std"),
            ("trades_total_vol", "Volume", 2.0, "std"),
            ("imbalance", "Order Book Imbalance", 2.5, "std"),
            ("funding_rate_pct", "Funding Rate", 2.0, "std"),
            ("large_net", "Large Trade Flow", 2.5, "std"),
            ("liq_net", "Liquidations", 2.0, "std"),
            ("spread_pct", "Spread", 3.0, "std"),
            ("composite", "Composite Score", 2.0, "std"),
            ("accel_10s", "Acceleration", 2.5, "std"),
            ("buying_pressure", "Buying Pressure", 2.0, "std"),
            ("whale_score", "Whale Activity", 2.0, "abs_threshold"),
        ]

        for metric, label, threshold, mode in checks:
            window = list(self.windows[metric])
            current = state.get(metric, 0)
            if current is None or len(window) < 10:
                continue

            if mode == "std":
                mean = sum(window) / len(window)
                variance = sum((x - mean) ** 2 for x in window) / len(window)
                std = variance ** 0.5
                if std < 0.001:
                    continue  # No variance, skip
                z_score = abs(current - mean) / std
                if z_score > threshold:
                    direction = "SPIKE UP" if current > mean else "SPIKE DOWN"
                    alert = {
                        "time": now,
                        "metric": metric,
                        "label": label,
                        "current": round(current, 4),
                        "mean": round(mean, 4),
                        "std": round(std, 4),
                        "z_score": round(z_score, 1),
                        "direction": direction,
                        "severity": "🔴 CRITICAL" if z_score > 3.5 else "🟡 ALERT",
                    }
                    if self._should_alert(metric, now):
                        new_alerts.append(alert)
                        self.anomaly_log.append(alert)

            elif mode == "abs_threshold":
                if abs(current) > 30:
                    alert = {
                        "time": now,
                        "metric": metric,
                        "label": label,
                        "current": round(current, 4),
                        "mean": 0,
                        "std": 0,
                        "z_score": 0,
                        "direction": "HIGH" if current > 0 else "LOW",
                        "severity": "🟡 ALERT",
                    }
                    if self._should_alert(metric, now):
                        new_alerts.append(alert)
                        self.anomaly_log.append(alert)

        self.alerts = new_alerts
        return new_alerts

    def _should_alert(self, metric, now):
        """Cooldown: don't alert same metric within 60 seconds"""
        last = self.alert_cooldown.get(metric, 0)
        if now - last > 60:
            self.alert_cooldown[metric] = now
            return True
        return False

    def get_recent_alerts(self, limit=10):
        """Get recent anomalies"""
        return self.anomaly_log[-limit:]

    def format_alert(self, alert):
        """Format single alert for display"""
        return (
            f"{alert['severity']} {alert['label']}: "
            f"{alert['current']} (z={alert['z_score']}, "
            f"avg={alert['mean']}, std={alert['std']}) — {alert['direction']}"
        )
