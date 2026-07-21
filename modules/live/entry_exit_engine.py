"""
Smart Money System - Entry/Exit Engine
Generates specific trade recommendations based on all signals.
No predictions. Math-based levels from order book + volume profile.
"""
import time


class EntryExitEngine:
    def __init__(self):
        self.last_signal = None
        self.last_signal_time = 0
        self.signal_cooldown = 300  # 5 min between signals

    def evaluate(self, state, setup_outlook):
        """
        Evaluate current state and generate trade recommendation.
        Returns None if no actionable signal, or a trade dict.
        """
        now = time.time()
        composite = state.get("composite", 0)
        accel = state.get("accel_10s", 0)
        accel_30s = state.get("accel_30s", 0)
        whale = state.get("whale_score", 0)
        buying = state.get("buying_pressure", 0)
        imbalance = state.get("imbalance", 0)
        liq = state.get("liq_net", 0)
        price = state.get("price", 0)
        poc = state.get("vol_profile_poc", 0)
        support = state.get("support_levels", [])
        resistance = state.get("resistance_levels", [])
        large_net = state.get("large_net", 0)
        funding = state.get("funding_rate_pct", 0)

        if price == 0:
            return None

        # === SIGNAL SCORING ===
        score = 0
        reasons = []

        # Composite direction
        if composite > 30:
            score += 3
            reasons.append(f"Composite strongly bullish ({composite:+.0f})")
        elif composite > 15:
            score += 1
            reasons.append(f"Composite bullish ({composite:+.0f})")
        elif composite < -30:
            score -= 3
            reasons.append(f"Composite strongly bearish ({composite:+.0f})")
        elif composite < -15:
            score -= 1
            reasons.append(f"Composite bearish ({composite:+.0f})")

        # Acceleration
        if accel > 10 and accel_30s > 20:
            score += 2
            reasons.append(f"Momentum ACCELERATING ({accel:+.0f}/{accel_30s:+.0f})")
        elif accel < -10 and accel_30s < -20:
            score -= 2
            reasons.append(f"Momentum DECELERATING ({accel:+.0f}/{accel_30s:+.0f})")

        # Whale activity
        if whale > 25:
            score += 2
            reasons.append(f"Whales accumulating ({whale:+.0f})")
        elif whale < -25:
            score -= 2
            reasons.append(f"Whales distributing ({whale:+.0f})")

        # Large trade flow
        if large_net > 10:
            score += 1
            reasons.append(f"Large trades net buying ({large_net:+.1f} ETH)")
        elif large_net < -10:
            score -= 1
            reasons.append(f"Large trades net selling ({large_net:+.1f} ETH)")

        # Funding contrarian
        if funding < -0.05:
            score += 1
            reasons.append(f"Funding negative = crowd short = bullish ({funding:+.4f}%)")
        elif funding > 0.1:
            score -= 1
            reasons.append(f"Funding extreme long = bearish ({funding:+.4f}%)")

        # Liquidation cascade
        if liq > 10:
            score += 1
            reasons.append(f"Shorts getting liquidated ({liq:+.1f} ETH)")
        elif liq < -10:
            score -= 1
            reasons.append(f"Longs getting liquidated ({liq:+.1f} ETH)")

        # Order book imbalance
        if imbalance > 15:
            score += 1
            reasons.append(f"Order book bullish ({imbalance:+.1f}%)")
        elif imbalance < -15:
            score -= 1
            reasons.append(f"Order book bearish ({imbalance:+.1f}%)")

        # === SIGNAL GENERATION ===
        # Need score >= 5 for long, <= -5 for short
        if abs(score) < 5:
            return None

        # Cooldown check
        if now - self.last_signal_time < self.signal_cooldown:
            return None

        direction = "LONG" if score > 0 else "SHORT"

        # === CALCULATE LEVELS ===
        # Entry: current price
        entry = price

        # Stop loss: below nearest support (for long) or above nearest resistance (for short)
        if direction == "LONG":
            if support:
                stop = support[0]["price"] - (price * 0.002)  # 0.2% below support
            else:
                stop = price * 0.985  # 1.5% default stop
            # Target: nearest resistance or POC-based
            if resistance:
                target = resistance[0]["price"]
            elif poc > price:
                target = poc + (price - poc) * 0.5
            else:
                target = price * 1.03  # 3% default target
        else:
            if resistance:
                stop = resistance[0]["price"] + (price * 0.002)
            else:
                stop = price * 1.015
            if support:
                target = support[0]["price"]
            elif poc < price:
                target = poc - (poc - price) * 0.5
            else:
                target = price * 0.97

        # Risk/Reward
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0

        # Don't take bad R:R trades
        if rr < 1.5:
            return None

        # Historical win rate
        win_rate = setup_outlook.get("win_rate_4h", 0) if setup_outlook.get("has_data") else 0
        sample_size = setup_outlook.get("count", 0) if setup_outlook.get("has_data") else 0

        # Confidence
        if abs(score) >= 8 and rr >= 2.0 and win_rate >= 60:
            confidence = "🟢 HIGH"
        elif abs(score) >= 6 and rr >= 1.5:
            confidence = "🟡 MEDIUM"
        else:
            confidence = "🔴 LOW"

        signal = {
            "time": time.time(),
            "direction": direction,
            "score": score,
            "confidence": confidence,
            "entry": round(entry, 2),
            "stop_loss": round(stop, 2),
            "target": round(target, 2),
            "risk": round(risk, 2),
            "reward": round(reward, 2),
            "rr": round(rr, 1),
            "reasons": reasons,
            "setup": setup_outlook.get("setup", "UNKNOWN"),
            "historical_win_rate": win_rate,
            "historical_samples": sample_size,
        }

        self.last_signal = signal
        self.last_signal_time = now
        return signal

    def format_signal(self, signal):
        """Format signal for display"""
        if not signal:
            return None

        dir_emoji = "🟢" if signal["direction"] == "LONG" else "🔴"

        lines = [
            f"{dir_emoji} <b>{signal['direction']} SIGNAL</b> {dir_emoji}",
            f"",
            f"<b>Score:</b> {signal['score']:+d}/10",
            f"<b>Confidence:</b> {signal['confidence']}",
            f"",
            f"<b>Entry:</b> ${signal['entry']:,.2f}",
            f"<b>Stop Loss:</b> ${signal['stop_loss']:,.2f} (risk: ${signal['risk']:,.2f})",
            f"<b>Target:</b> ${signal['target']:,.2f} (reward: ${signal['reward']:,.2f})",
            f"<b>R:R:</b> 1:{signal['rr']}",
        ]

        if signal["historical_win_rate"] > 0:
            lines.extend([
                f"",
                f"<b>Historical:</b> {signal['historical_win_rate']:.0f}% win rate ({signal['historical_samples']} samples)",
            ])

        lines.extend([
            f"",
            f"<b>Reasons:</b>",
        ])
        for r in signal["reasons"]:
            lines.append(f"  • {r}")

        return "\n".join(lines)
