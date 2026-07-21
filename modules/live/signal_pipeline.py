"""
Smart Money System - Signal Pipeline
Shows EXACTLY what conditions are met and what's missing before a signal fires.
Each checkpoint must pass before the next is evaluated.
"""
import time


class SignalPipeline:
    def __init__(self):
        self.last_signal = None
        self.last_signal_time = 0
        self.cooldown = 300  # 5 min between signals

    def evaluate(self, state):
        """
        Evaluate all checkpoints in order.
        Returns: {stage, checkpoints[], ready, signal}
        """
        now = time.time()
        price = state.get("price", 0)
        if price == 0:
            return self._empty()

        # === CHECKPOINT 1: DIRECTION ===
        # CVD must show clear direction
        cvd = state.get("cvd", {})
        cvd_5m = cvd.get("cvd_roc_5m", 0)
        cvd_trend = cvd.get("cvd_trend", "")

        if cvd_5m > 50:
            cp1 = {"name": "DIRECTION", "status": "PASS", "detail": f"CVD bullish ({cvd_5m:+.0f} in 5m)", "score": 2}
        elif cvd_5m < -50:
            cp1 = {"name": "DIRECTION", "status": "PASS", "detail": f"CVD bearish ({cvd_5m:+.0f} in 5m)", "score": -2}
        elif cvd_5m > 20:
            cp1 = {"name": "DIRECTION", "status": "WEAK", "detail": f"CVD slightly bullish ({cvd_5m:+.0f})", "score": 1}
        elif cvd_5m < -20:
            cp1 = {"name": "DIRECTION", "status": "WEAK", "detail": f"CVD slightly bearish ({cvd_5m:+.0f})", "score": -1}
        else:
            cp1 = {"name": "DIRECTION", "status": "FAIL", "detail": f"CVD neutral ({cvd_5m:+.0f})", "score": 0}

        # === CHECKPOINT 2: DIVERGENCE ===
        # CVD-Price divergence is the strongest signal
        div = cvd.get("divergence")
        if div:
            if div["type"] == "BULLISH":
                cp2 = {"name": "DIVERGENCE", "status": "PASS", "detail": "🟢 Bullish divergence detected", "score": 3}
            else:
                cp2 = {"name": "DIVERGENCE", "status": "PASS", "detail": "🔴 Bearish divergence detected", "score": -3}
        else:
            cp2 = {"name": "DIVERGENCE", "status": "NONE", "detail": "No divergence", "score": 0}

        # === CHECKPOINT 3: TOXICITY ===
        # VPIN must not be too high (informed traders = don't trade against them)
        vpin = state.get("vpin", {})
        vpin_pct = vpin.get("vpin_pct", 0)

        if vpin_pct > 50:
            cp3 = {"name": "TOXICITY", "status": "DANGER", "detail": f"VPIN {vpin_pct:.0f}% — informed traders active, careful", "score": 0}
        elif vpin_pct > 30:
            cp3 = {"name": "TOXICITY", "status": "WARN", "detail": f"VPIN {vpin_pct:.0f}% — some informed flow", "score": 0}
        else:
            cp3 = {"name": "TOXICITY", "status": "CLEAR", "detail": f"VPIN {vpin_pct:.0f}% — normal flow", "score": 0}

        # === CHECKPOINT 4: MOMENTUM ===
        # Acceleration must confirm direction
        accel = state.get("accel_10s", 0)
        accel_30s = state.get("accel_30s", 0)

        if accel > 10 and accel_30s > 20:
            cp4 = {"name": "MOMENTUM", "status": "PASS", "detail": f"Accelerating ({accel:+.0f}/{accel_30s:+.0f})", "score": 2}
        elif accel < -10 and accel_30s < -20:
            cp4 = {"name": "MOMENTUM", "status": "PASS", "detail": f"Decelerating ({accel:+.0f}/{accel_30s:+.0f})", "score": -2}
        elif abs(accel) < 5:
            cp4 = {"name": "MOMENTUM", "status": "FLAT", "detail": f"No momentum ({accel:+.0f})", "score": 0}
        else:
            cp4 = {"name": "MOMENTUM", "status": "WEAK", "detail": f"Weak momentum ({accel:+.0f})", "score": 1 if accel > 0 else -1}

        # === CHECKPOINT 5: INSTITUTIONAL ===
        # Whale + OI must align
        whale = state.get("whale_score", 0)
        oi = state.get("oi_delta", {})
        oi_signal = oi.get("signal", "")

        inst_score = 0
        inst_details = []
        if whale > 20:
            inst_score += 1
            inst_details.append("whales buying")
        elif whale < -20:
            inst_score -= 1
            inst_details.append("whales selling")

        if "NEW LONGS" in oi_signal:
            inst_score += 1
            inst_details.append("new longs")
        elif "NEW SHORTS" in oi_signal:
            inst_score -= 1
            inst_details.append("new shorts")
        elif "SHORT COVERING" in oi_signal:
            inst_score += 0.5
            inst_details.append("short covering")

        if inst_score >= 1:
            cp5 = {"name": "INSTITUTIONAL", "status": "PASS", "detail": f"Institutional buying ({', '.join(inst_details)})", "score": 2}
        elif inst_score <= -1:
            cp5 = {"name": "INSTITUTIONAL", "status": "PASS", "detail": f"Institutional selling ({', '.join(inst_details)})", "score": -2}
        else:
            cp5 = {"name": "INSTITUTIONAL", "status": "NEUTRAL", "detail": f"No clear institutional signal ({', '.join(inst_details) or 'mixed'})", "score": 0}

        # === CHECKPOINT 6: LIQUIDITY TARGET ===
        # Must have a clear liquidation target
        liq = state.get("liq_clusters", {})
        liq_above = liq.get("total_liq_above", 0)
        liq_below = liq.get("total_liq_below", 0)

        if liq_above > liq_below * 1.5:
            cp6 = {"name": "LIQ TARGET", "status": "PASS", "detail": f"${liq_above/1000:.0f}K liq above — price targets up", "score": 1}
        elif liq_below > liq_above * 1.5:
            cp6 = {"name": "LIQ TARGET", "status": "PASS", "detail": f"${liq_below/1000:.0f}K liq below — price targets down", "score": -1}
        else:
            cp6 = {"name": "LIQ TARGET", "status": "NEUTRAL", "detail": "Balanced liquidation levels", "score": 0}

        # === CHECKPOINT 7: ORDER BOOK ===
        # Must confirm direction
        imbalance = state.get("imbalance", 0)

        if imbalance > 10:
            cp7 = {"name": "ORDER BOOK", "status": "PASS", "detail": f"Bullish ({imbalance:+.1f}%)", "score": 1}
        elif imbalance < -10:
            cp7 = {"name": "ORDER BOOK", "status": "PASS", "detail": f"Bearish ({imbalance:+.1f}%)", "score": -1}
        else:
            cp7 = {"name": "ORDER BOOK", "status": "NEUTRAL", "detail": f"Balanced ({imbalance:+.1f}%)", "score": 0}

        # === CHECKPOINT 8: MULTI-TIMEFRAME ===
        # Must show consistent direction across timeframes
        mtf = state.get("mtf", {})
        mtf_aligned = 0
        mtf_total = 0
        for label, data in mtf.items():
            if data.get("total", 0) > 0:
                mtf_total += 1
                if data.get("buy_pct", 50) > 60:
                    mtf_aligned += 1
                elif data.get("buy_pct", 50) < 40:
                    mtf_aligned -= 1

        if mtf_aligned >= 3:
            cp8 = {"name": "MTF ALIGN", "status": "PASS", "detail": f"{abs(mtf_aligned)}/{mtf_total} timeframes bullish", "score": 2}
        elif mtf_aligned <= -3:
            cp8 = {"name": "MTF ALIGN", "status": "PASS", "detail": f"{abs(mtf_aligned)}/{mtf_total} timeframes bearish", "score": -2}
        elif abs(mtf_aligned) >= 2:
            cp8 = {"name": "MTF ALIGN", "status": "WEAK", "detail": f"{abs(mtf_aligned)}/{mtf_total} timeframes aligned", "score": 1 if mtf_aligned > 0 else -1}
        else:
            cp8 = {"name": "MTF ALIGN", "status": "FAIL", "detail": f"Timeframes conflicting ({mtf_aligned}/{mtf_total})", "score": 0}

        # === CALCULATE TOTAL SCORE ===
        checkpoints = [cp1, cp2, cp3, cp4, cp5, cp6, cp7, cp8]
        total_score = sum(cp["score"] for cp in checkpoints)
        passed = sum(1 for cp in checkpoints if cp["status"] == "PASS")
        failed = sum(1 for cp in checkpoints if cp["status"] == "FAIL")
        danger = any(cp["status"] == "DANGER" for cp in checkpoints)

        # Count bullish vs bearish checkpoints
        bullish_cps = sum(1 for cp in checkpoints if cp["score"] > 0)
        bearish_cps = sum(1 for cp in checkpoints if cp["score"] < 0)

        # Direction
        if total_score >= 3:
            direction = "LONG"
        elif total_score <= -3:
            direction = "SHORT"
        else:
            direction = None

        # Build BOTH potential setups
        long_setup = self._build_setup(state, "LONG", checkpoints)
        short_setup = self._build_setup(state, "SHORT", checkpoints)

        # Signal readiness
        if direction and not danger and passed >= 3 and (now - self.last_signal_time > self.cooldown):
            ready = True
            signal = self._build_signal(state, direction, total_score, checkpoints)
            self.last_signal = signal
            self.last_signal_time = now
        else:
            ready = False
            signal = None

        # Stage description
        if danger:
            stage = "🛑 BLOCKED — informed traders active"
        elif not direction:
            stage = "⏳ WAITING — no clear direction yet"
        elif passed < 3:
            stage = f"🔍 FORMING — {passed}/8 checkpoints passed"
        elif not ready:
            stage = "⏳ COOLDOWN — waiting between signals"
        else:
            stage = "🟢 SIGNAL READY"

        return {
            "stage": stage,
            "direction": direction,
            "total_score": total_score,
            "passed": passed,
            "failed": failed,
            "bullish_cps": bullish_cps,
            "bearish_cps": bearish_cps,
            "checkpoints": checkpoints,
            "ready": ready,
            "signal": signal,
            "long_setup": long_setup,
            "short_setup": short_setup,
        }

    def _build_setup(self, state, direction, checkpoints):
        """Build a potential setup for LONG or SHORT (always calculated)"""
        price = state.get("price", 0)
        support = state.get("support_levels", [])
        resistance = state.get("resistance_levels", [])
        vah = state.get("vol_profile_vah", 0)
        val = state.get("vol_profile_val", 0)

        if price == 0:
            return None

        # Use percentage-based stops (1.5% stop, 3% target) for better R:R
        if direction == "LONG":
            entry = price
            # Stop: below support if available, otherwise1.5% below
            if support and support[0]["price"] < price * 0.99:
                stop = support[0]["price"] - price * 0.002
            else:
                stop = price * 0.985  # 1.5% stop
            # Target: resistance or 3% above
            if resistance and resistance[0]["price"] > price * 1.01:
                target = resistance[0]["price"]
            elif vah > price * 1.01:
                target = vah
            else:
                target = price * 1.03  # 3% target
            # Score: sum of positive checkpoint scores
            score = sum(cp["score"] for cp in checkpoints if cp["score"] > 0)
            supporting = [cp["detail"] for cp in checkpoints if cp["score"] > 0]
        else:
            entry = price
            # Stop: above resistance if available, otherwise1.5% above
            if resistance and resistance[0]["price"] > price * 1.01:
                stop = resistance[0]["price"] + price * 0.002
            else:
                stop = price * 1.015  # 1.5% stop
            # Target: support or 3% below
            if support and support[0]["price"] < price * 0.99:
                target = support[0]["price"]
            elif val < price * 0.99:
                target = val
            else:
                target = price * 0.97  # 3% target
            # Score: sum of negative checkpoint scores (absolute)
            score = abs(sum(cp["score"] for cp in checkpoints if cp["score"] < 0))
            supporting = [cp["detail"] for cp in checkpoints if cp["score"] < 0]

        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0

        return {
            "direction": direction,
            "entry": round(entry, 2),
            "stop_loss": round(stop, 2),
            "target": round(target, 2),
            "risk": round(risk, 2),
            "reward": round(reward, 2),
            "rr": round(rr, 1),
            "score": score,
            "supporting": supporting,
            "supporting_count": len(supporting),
        }

    def _build_signal(self, state, direction, score, checkpoints):
        """Build trade signal with entry/stop/target"""
        price = state.get("price", 0)
        support = state.get("support_levels", [])
        resistance = state.get("resistance_levels", [])
        vah = state.get("vol_profile_vah", 0)
        val = state.get("vol_profile_val", 0)

        if direction == "LONG":
            entry = price
            if support and support[0]["price"] < price * 0.99:
                stop = support[0]["price"] - price * 0.002
            else:
                stop = price * 0.985
            if resistance and resistance[0]["price"] > price * 1.01:
                target = resistance[0]["price"]
            elif vah > price * 1.01:
                target = vah
            else:
                target = price * 1.03
        else:
            entry = price
            if resistance and resistance[0]["price"] > price * 1.01:
                stop = resistance[0]["price"] + price * 0.002
            else:
                stop = price * 1.015
            if support and support[0]["price"] < price * 0.99:
                target = support[0]["price"]
            elif val < price * 0.99:
                target = val
            else:
                target = price * 0.97

        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0

        if rr < 1.0:
            return None

        reasons = [cp["detail"] for cp in checkpoints if cp["status"] == "PASS"]

        return {
            "time": time.time(),
            "direction": direction,
            "score": score,
            "entry": round(entry, 2),
            "stop_loss": round(stop, 2),
            "target": round(target, 2),
            "risk": round(risk, 2),
            "reward": round(reward, 2),
            "rr": round(rr, 1),
            "reasons": reasons,
            "checkpoints_passed": sum(1 for cp in checkpoints if cp["status"] == "PASS"),
        }

    def _empty(self):
        return {
            "stage": "⏳ INITIALIZING",
            "direction": None,
            "total_score": 0,
            "passed": 0,
            "failed": 0,
            "checkpoints": [],
            "ready": False,
            "signal": None,
        }
