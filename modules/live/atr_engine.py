"""
ATR Engine — Volatility-Adaptive Stop Loss & Take Profit

Instead of fixed 1% SL, use Average True Range to adapt to current volatility.
- Calm market → tighter SL (less risk per trade)
- Volatile market → wider SL (avoid noise stops)
"""

import time
from collections import deque


class ATREngine:
    def __init__(self, period=14):
        self.period = period
        self.trues = deque(maxlen=period * 3)  # Keep extra for safety
        self.atr = 0
        self.atr_pct = 0  # ATR as % of price
        self.price_history = deque(maxlen=100)

    def update(self, price, high=None, low=None):
        """
        Update ATR with new price data.
        If high/low not provided, uses price as all three (tick-based approximation).
        """
        if high is None:
            high = price
        if low is None:
            low = price

        self.price_history.append({"time": time.time(), "price": price, "high": high, "low": low})

        if len(self.price_history) < 2:
            return

        prev = self.price_history[-2]
        prev_close = prev["price"]

        # True Range = max of:
        # 1. High - Low
        # 2. |High - Prev Close|
        # 3. |Low - Prev Close|
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        true_range = max(tr1, tr2, tr3)

        self.trues.append(true_range)

        # Calculate ATR (simple moving average of true ranges)
        if len(self.trues) >= self.period:
            recent = list(self.trues)[-self.period:]
            self.atr = sum(recent) / len(recent)
            self.atr_pct = (self.atr / price * 100) if price > 0 else 0

    def get_sl_distance(self, multiplier=1.5):
        """
        Get stop loss distance based on ATR.
        multiplier: how many ATRs for SL (1.5 = 1.5x ATR)
        
        Returns absolute price distance.
        """
        if self.atr == 0:
            return 0
        return self.atr * multiplier

    def get_sl_pct(self, price, multiplier=1.5):
        """Get SL as percentage of price."""
        if price == 0 or self.atr == 0:
            return 1.5  # Fallback 1.5%
        sl_dist = self.atr * multiplier
        return (sl_dist / price) * 100

    def get_levels(self, price, direction, sl_mult=1.5, tp_mult=2.5):
        """
        Calculate SL and TP levels based on ATR.
        
        Args:
            price: current price
            direction: "LONG" or "SHORT"
            sl_mult: SL = this many ATRs from entry
            tp_mult: TP = this many ATRs from entry
        
        Returns:
            dict with entry, sl, tp, risk, reward, rr, sl_pct, tp_pct
        """
        if self.atr == 0 or price == 0:
            return None

        sl_dist = self.atr * sl_mult
        tp_dist = self.atr * tp_mult

        if direction == "LONG":
            sl = price - sl_dist
            tp = price + tp_dist
        else:
            sl = price + sl_dist
            tp = price - tp_dist

        risk = abs(price - sl)
        reward = abs(tp - price)
        rr = reward / risk if risk > 0 else 0

        return {
            "entry": round(price, 2),
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "risk": round(risk, 2),
            "reward": round(reward, 2),
            "rr": round(rr, 2),
            "sl_pct": round(risk / price * 100, 2),
            "tp_pct": round(reward / price * 100, 2),
            "atr": round(self.atr, 2),
            "atr_pct": round(self.atr_pct, 3),
            "sl_mult": sl_mult,
            "tp_mult": tp_mult,
        }

    def get_trail_distance(self, multiplier=1.0):
        """
        Get trailing stop distance.
        Tighter than initial SL — locks in profit as price moves.
        """
        if self.atr == 0:
            return 0
        return self.atr * multiplier

    def get_state(self):
        """Get current ATR state for display."""
        if self.atr == 0:
            return {"atr": 0, "atr_pct": 0, "volatility": "NO DATA"}

        if self.atr_pct < 0.3:
            vol = "🟢 LOW"
        elif self.atr_pct < 0.8:
            vol = "🟡 NORMAL"
        elif self.atr_pct < 1.5:
            vol = "🟠 HIGH"
        else:
            vol = "🔴 EXTREME"

        return {
            "atr": round(self.atr, 2),
            "atr_pct": round(self.atr_pct, 3),
            "volatility": vol,
            "period": self.period,
            "samples": len(self.trues),
        }
