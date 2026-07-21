"""
Smart Money System - Outcome Tracker
Logs every market state and tracks what happened after.
Calculates win rates for specific setups.
"""
import time
import json
import os
from datetime import datetime


class OutcomeTracker:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.log_file = os.path.join(data_dir, "outcomes.jsonl")
        self.setups_file = os.path.join(data_dir, "setup_stats.json")

        self.pending = []  # States waiting for outcome
        self.setup_stats = self._load_stats()

    def log_state(self, state):
        """Log current state for future outcome tracking"""
        entry = {
            "time": time.time(),
            "timestamp": datetime.now().isoformat(),
            "price": state.get("price", 0),
            "composite": state.get("composite", 0),
            "buying_pressure": state.get("buying_pressure", 0),
            "accel_10s": state.get("accel_10s", 0),
            "accel_30s": state.get("accel_30s", 0),
            "whale_score": state.get("whale_score", 0),
            "funding_rate_pct": state.get("funding_rate_pct", 0),
            "imbalance": state.get("imbalance", 0),
            "large_net": state.get("large_net", 0),
            "liq_net": state.get("liq_net", 0),
            "trades_net": state.get("trades_net", 0),
            "trades_buy_pct": state.get("trades_buy_pct", 50),
            "vol_profile_poc": state.get("vol_profile_poc", 0),
            # Setup classification
            "setup": self._classify_setup(state),
            "resolved": False,
            "outcome_1h": None,
            "outcome_4h": None,
            "outcome_24h": None,
        }

        self.pending.append(entry)

        # Log to file
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except:
            pass

    def check_outcomes(self, current_price):
        """Check pending entries and record outcomes"""
        now = time.time()
        resolved = []

        for entry in self.pending:
            if entry["resolved"]:
                continue

            elapsed = now - entry["time"]
            price = entry["price"]
            if price == 0:
                continue

            change_pct = (current_price - price) / price * 100

            if elapsed >= 3600 and entry["outcome_1h"] is None:
                entry["outcome_1h"] = round(change_pct, 2)
            if elapsed >= 14400 and entry["outcome_4h"] is None:
                entry["outcome_4h"] = round(change_pct, 2)
            if elapsed >= 86400 and entry["outcome_24h"] is None:
                entry["outcome_24h"] = round(change_pct, 2)
                entry["resolved"] = True
                resolved.append(entry)
                self._update_stats(entry)

        # Keep only unresolved + last 1000 resolved
        self.pending = [e for e in self.pending if not e["resolved"]][-5000:]

        return resolved

    def _classify_setup(self, state):
        """Classify the current market state into a setup type"""
        composite = state.get("composite", 0)
        accel = state.get("accel_10s", 0)
        whale = state.get("whale_score", 0)
        buying = state.get("buying_pressure", 0)
        liq = state.get("liq_net", 0)

        tags = []

        # Direction
        if composite > 30:
            tags.append("STRONG_BUY")
        elif composite > 15:
            tags.append("BUY")
        elif composite < -30:
            tags.append("STRONG_SELL")
        elif composite < -15:
            tags.append("SELL")
        else:
            tags.append("NEUTRAL")

        # Momentum
        if accel > 10:
            tags.append("ACCELERATING")
        elif accel < -10:
            tags.append("DECELERATING")

        # Whale
        if whale > 20:
            tags.append("WHALE_BUYING")
        elif whale < -20:
            tags.append("WHALE_SELLING")

        # Liquidation
        if liq > 5:
            tags.append("SHORTS_LIQ")
        elif liq < -5:
            tags.append("LONGS_LIQ")

        return "_".join(tags)

    def _update_stats(self, entry):
        """Update setup statistics after resolution"""
        setup = entry["setup"]
        if setup not in self.setup_stats:
            self.setup_stats[setup] = {
                "count": 0,
                "wins_1h": 0, "losses_1h": 0,
                "wins_4h": 0, "losses_4h": 0,
                "wins_24h": 0, "losses_24h": 0,
                "avg_return_1h": 0, "avg_return_4h": 0, "avg_return_24h": 0,
            }

        stats = self.setup_stats[setup]
        stats["count"] += 1

        for period, key in [("1h", "1h"), ("4h", "4h"), ("24h", "24h")]:
            outcome = entry.get(f"outcome_{period}")
            if outcome is not None:
                if outcome > 0:
                    stats[f"wins_{key}"] += 1
                else:
                    stats[f"losses_{key}"] += 1
                # Running average
                n = stats[f"wins_{key}"] + stats[f"losses_{key}"]
                stats[f"avg_return_{key}"] = round(
                    (stats[f"avg_return_{key}"] * (n - 1) + outcome) / n, 2
                )

        self._save_stats()

    def get_setup_stats(self, setup=None):
        """Get statistics for a specific setup or all setups"""
        if setup:
            return self.setup_stats.get(setup, None)
        return self.setup_stats

    def get_current_setup_outlook(self, state):
        """Get historical performance of current setup"""
        setup = self._classify_setup(state)
        stats = self.setup_stats.get(setup, None)

        if not stats or stats["count"] < 3:
            return {
                "setup": setup,
                "has_data": False,
                "message": f"Setup '{setup}' has {stats['count'] if stats else 0} historical samples — need more data"
            }

        total_4h = stats["wins_4h"] + stats["losses_4h"]
        win_rate_4h = (stats["wins_4h"] / total_4h * 100) if total_4h > 0 else 0

        return {
            "setup": setup,
            "has_data": True,
            "count": stats["count"],
            "win_rate_1h": round(stats["wins_1h"] / max(stats["wins_1h"] + stats["losses_1h"], 1) * 100, 0),
            "win_rate_4h": round(win_rate_4h, 0),
            "win_rate_24h": round(stats["wins_24h"] / max(stats["wins_24h"] + stats["losses_24h"], 1) * 100, 0),
            "avg_return_1h": stats["avg_return_1h"],
            "avg_return_4h": stats["avg_return_4h"],
            "avg_return_24h": stats["avg_return_24h"],
        }

    def _load_stats(self):
        if os.path.exists(self.setups_file):
            try:
                with open(self.setups_file) as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_stats(self):
        try:
            with open(self.setups_file, "w") as f:
                json.dump(self.setup_stats, f, indent=2)
        except:
            pass
