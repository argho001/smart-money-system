"""
Session Filter — Time-of-Day Trading Quality

Not all hours are equal in crypto:
- US session (14:00-21:00 UTC) = biggest moves, most volume
- EU session (08:00-14:00 UTC) = sets direction
- Asia session (00:00-08:00 UTC) = range-bound, low volume
- Dead zone (21:00-00:00 UTC) = reversals, thin liquidity

Trading during low-liquidity hours = getting faked out by noise.
Trading during high-volume hours = real moves with follow-through.
"""

import time
from datetime import datetime, timezone


class SessionFilter:
    def __init__(self):
        # Session definitions (UTC hours)
        self.sessions = {
            "ASIA": {"start": 0, "end": 8, "quality": "low", "volatility": 0.6},
            "EU": {"start": 8, "end": 14, "quality": "medium", "volatility": 0.8},
            "US": {"start": 14, "end": 21, "quality": "high", "volatility": 1.0},
            "DEAD": {"start": 21, "end": 24, "quality": "low", "volatility": 0.5},
        }

        # Days of week (0=Monday, 6=Sunday)
        self.day_quality = {
            0: "medium",  # Monday — slow start
            1: "high",    # Tuesday
            2: "high",    # Wednesday
            3: "high",    # Thursday
            4: "medium",  # Friday — positions close
            5: "low",     # Saturday
            6: "low",     # Sunday
        }

    def get_session(self):
        """Get current trading session and quality."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        weekday = now.weekday()

        # Determine session
        current_session = "DEAD"
        for name, info in self.sessions.items():
            if info["start"] <= hour < info["end"]:
                current_session = name
                break

        session_info = self.sessions[current_session]
        day_quality = self.day_quality.get(weekday, "medium")

        # Overall quality score (0-100)
        quality_scores = {"high": 80, "medium": 50, "low": 20}
        session_score = quality_scores[session_info["quality"]]
        day_score = quality_scores[day_quality]
        overall_score = (session_score * 0.7 + day_score * 0.3)

        # Should we trade?
        should_trade = overall_score >= 50

        # Confidence multiplier
        if overall_score >= 70:
            confidence_mult = 1.0  # Full confidence
            quality_label = "🟢 HIGH"
        elif overall_score >= 50:
            confidence_mult = 0.7  # Reduced confidence
            quality_label = "🟡 MEDIUM"
        else:
            confidence_mult = 0.3  # Very low confidence
            quality_label = "🔴 LOW"

        # Session-specific notes
        notes = []
        if current_session == "ASIA":
            notes.append("Low volume — moves may not sustain")
            notes.append("Range-bound — tighter stops recommended")
        elif current_session == "EU":
            notes.append("Setting daily direction — watch for breakouts")
        elif current_session == "US":
            notes.append("Highest volume — moves have follow-through")
            notes.append("Best time for trend trades")
        elif current_session == "DEAD":
            notes.append("Thin liquidity — high slippage risk")
            notes.append("Reversals common — be cautious")

        if weekday >= 5:
            notes.append("Weekend — reduced institutional activity")

        return {
            "session": current_session,
            "quality": quality_label,
            "quality_raw": session_info["quality"],
            "day_quality": day_quality,
            "overall_score": round(overall_score, 0),
            "confidence_mult": round(confidence_mult, 2),
            "should_trade": should_trade,
            "volatility_mult": session_info["volatility"],
            "notes": notes,
            "hour_utc": hour,
            "weekday": weekday,
        }

    def get_sl_multiplier(self):
        """
        Get SL multiplier based on session.
        Low-liquidity hours need wider SL (more noise).
        """
        session = self.get_session()
        # Wider SL during low liquidity
        if session["quality_raw"] == "low":
            return 1.5  # 50% wider SL
        elif session["quality_raw"] == "medium":
            return 1.2  # 20% wider SL
        else:
            return 1.0  # Normal SL

    def format_session(self, session_info=None):
        """Format session info for display."""
        if not session_info:
            session_info = self.get_session()

        lines = [
            f"🕐 Session: {session_info['session']} ({session_info['quality']})",
            f"   Score: {session_info['overall_score']}/100",
            f"   Confidence: {session_info['confidence_mult']}x",
        ]
        for note in session_info.get("notes", []):
            lines.append(f"   • {note}")

        return "\n".join(lines)
