"""
Smart Money System - Signal Pipeline v3
Redesigned based on backtest findings:
- OHLCV indicators don't work
- Real-time order flow (CVD, OI, orderbook, large trades) is the edge
- Fewer, stronger checkpoints > many weak ones
- Each checkpoint must have CLEAR directional value
"""
import time


class SignalPipeline:
    def __init__(self):
        self.last_signal = None
        self.last_signal_time = 0
        self.cooldown = 180  # 3 min between signals

    def evaluate(self, state):
        """
        5 core checkpoints — each one is a real-time order flow metric.
        No OHLCV indicators. No lagging signals.
        """
        now = time.time()
        price = state.get("price", 0)
        if price == 0:
            return self._empty()

        checkpoints = []

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 1: CVD — WHO is in control (buyers or sellers)
        # ═══════════════════════════════════════════════════════
        cvd = state.get("cvd", {})
        cvd_5m = cvd.get("cvd_roc_5m", 0)
        cvd_15m = cvd.get("cvd_roc_15m", 0)

        # Strong signal: both 5m and 15m agree
        if cvd_5m > 100 and cvd_15m > 50:
            cp = {"name": "CVD", "status": "PASS", "detail": f"🟢 Strong buying ({cvd_5m:+.0f}/{cvd_15m:+.0f})", "score": 3, "direction": "LONG"}
        elif cvd_5m < -100 and cvd_15m < -50:
            cp = {"name": "CVD", "status": "PASS", "detail": f"🔴 Strong selling ({cvd_5m:+.0f}/{cvd_15m:+.0f})", "score": -3, "direction": "SHORT"}
        elif cvd_5m > 50:
            cp = {"name": "CVD", "status": "WEAK", "detail": f"🟢 Buying ({cvd_5m:+.0f})", "score": 1, "direction": "LONG"}
        elif cvd_5m < -50:
            cp = {"name": "CVD", "status": "WEAK", "detail": f"🔴 Selling ({cvd_5m:+.0f})", "score": -1, "direction": "SHORT"}
        else:
            cp = {"name": "CVD", "status": "NEUTRAL", "detail": f"Neutral ({cvd_5m:+.0f})", "score": 0, "direction": None}
        checkpoints.append(cp)

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 2: LARGE TRADES — What whales are doing
        # ═══════════════════════════════════════════════════════
        large_net = state.get("large_net", 0)
        large_buy_count = state.get("large_buy_count", 0)
        large_sell_count = state.get("large_sell_count", 0)
        largest = state.get("largest_trade", 0)

        # Strong: significant net flow + multiple trades
        if large_net > 20 and large_buy_count >= 3:
            cp = {"name": "WHALES", "status": "PASS", "detail": f"🟢 Whales buying ({large_net:+.1f} ETH, {large_buy_count} trades)", "score": 2, "direction": "LONG"}
        elif large_net < -20 and large_sell_count >= 3:
            cp = {"name": "WHALES", "status": "PASS", "detail": f"🔴 Whales selling ({large_net:+.1f} ETH, {large_sell_count} trades)", "score": -2, "direction": "SHORT"}
        elif large_net > 5:
            cp = {"name": "WHALES", "status": "WEAK", "detail": f"🟢 Light buying ({large_net:+.1f} ETH)", "score": 1, "direction": "LONG"}
        elif large_net < -5:
            cp = {"name": "WHALES", "status": "WEAK", "detail": f"🔴 Light selling ({large_net:+.1f} ETH)", "score": -1, "direction": "SHORT"}
        else:
            cp = {"name": "WHALES", "status": "NEUTRAL", "detail": f"No whale flow ({large_net:+.1f} ETH)", "score": 0, "direction": None}
        checkpoints.append(cp)

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 3: ORDER BOOK — Real supply/demand
        # ═══════════════════════════════════════════════════════
        imbalance = state.get("imbalance", 0)
        bid_pct = state.get("bid_pct", 50)
        ask_pct = state.get("ask_pct", 50)

        if imbalance > 8:
            cp = {"name": "ORDERBOOK", "status": "PASS", "detail": f"🟢 Buy wall heavy ({bid_pct:.0f}% bids)", "score": 2, "direction": "LONG"}
        elif imbalance < -8:
            cp = {"name": "ORDERBOOK", "status": "PASS", "detail": f"🔴 Sell wall heavy ({ask_pct:.0f}% asks)", "score": -2, "direction": "SHORT"}
        elif imbalance > 3:
            cp = {"name": "ORDERBOOK", "status": "WEAK", "detail": f"🟢 Slight buy bias ({bid_pct:.0f}%)", "score": 1, "direction": "LONG"}
        elif imbalance < -3:
            cp = {"name": "ORDERBOOK", "status": "WEAK", "detail": f"🔴 Slight sell bias ({ask_pct:.0f}%)", "score": -1, "direction": "SHORT"}
        else:
            cp = {"name": "ORDERBOOK", "status": "NEUTRAL", "detail": f"Balanced ({imbalance:+.1f}%)", "score": 0, "direction": None}
        checkpoints.append(cp)

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 4: OI + FUNDING — Where leverage is building
        # ═══════════════════════════════════════════════════════
        oi = state.get("oi_delta", {})
        oi_signal = oi.get("signal", "")
        funding = state.get("funding_rate_pct", 0)
        cross_oi = state.get("cross_oi", {})

        oi_score = 0
        oi_details = []

        # OI signal
        if "NEW LONGS" in oi_signal:
            oi_score += 2
            oi_details.append("new longs opening")
        elif "NEW SHORTS" in oi_signal:
            oi_score -= 2
            oi_details.append("new shorts opening")
        elif "SHORT COVERING" in oi_signal:
            oi_score += 1
            oi_details.append("shorts covering")
        elif "LONG CLOSING" in oi_signal:
            oi_score -= 1
            oi_details.append("longs closing")

        # Funding contrarian: extreme funding = crowd is wrong
        if funding > 0.03:
            oi_score -= 1
            oi_details.append(f"high funding ({funding:.3f}%) = crowd long")
        elif funding < -0.01:
            oi_score += 1
            oi_details.append(f"negative funding ({funding:.3f}%) = crowd short")

        if oi_score >= 2:
            cp = {"name": "LEVERAGE", "status": "PASS", "detail": f"🟢 {', '.join(oi_details)}", "score": 2, "direction": "LONG"}
        elif oi_score <= -2:
            cp = {"name": "LEVERAGE", "status": "PASS", "detail": f"🔴 {', '.join(oi_details)}", "score": -2, "direction": "SHORT"}
        elif oi_score > 0:
            cp = {"name": "LEVERAGE", "status": "WEAK", "detail": f"🟢 {', '.join(oi_details)}", "score": 1, "direction": "LONG"}
        elif oi_score < 0:
            cp = {"name": "LEVERAGE", "status": "WEAK", "detail": f"🔴 {', '.join(oi_details)}", "score": -1, "direction": "SHORT"}
        else:
            cp = {"name": "LEVERAGE", "status": "NEUTRAL", "detail": f"Neutral ({', '.join(oi_details) or 'no signal'})", "score": 0, "direction": None}
        checkpoints.append(cp)

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 5: MOMENTUM — Is the move accelerating
        # ═══════════════════════════════════════════════════════
        accel_10s = state.get("accel_10s", 0)
        accel_30s = state.get("accel_30s", 0)

        # Both must agree for strong signal
        if accel_10s > 50 and accel_30s > 100:
            cp = {"name": "MOMENTUM", "status": "PASS", "detail": f"🟢 Accelerating buying ({accel_10s:+.0f}/{accel_30s:+.0f})", "score": 2, "direction": "LONG"}
        elif accel_10s < -50 and accel_30s < -100:
            cp = {"name": "MOMENTUM", "status": "PASS", "detail": f"🔴 Accelerating selling ({accel_10s:+.0f}/{accel_30s:+.0f})", "score": -2, "direction": "SHORT"}
        elif accel_10s > 20:
            cp = {"name": "MOMENTUM", "status": "WEAK", "detail": f"🟢 Buying ({accel_10s:+.0f})", "score": 1, "direction": "LONG"}
        elif accel_10s < -20:
            cp = {"name": "MOMENTUM", "status": "WEAK", "detail": f"🔴 Selling ({accel_10s:+.0f})", "score": -1, "direction": "SHORT"}
        else:
            cp = {"name": "MOMENTUM", "status": "NEUTRAL", "detail": f"Flat ({accel_10s:+.0f})", "score": 0, "direction": None}
        checkpoints.append(cp)

        # ═══════════════════════════════════════════════════════
        # SCORING — Simple, transparent
        # ═══════════════════════════════════════════════════════
        total_score = sum(cp["score"] for cp in checkpoints)
        passed = sum(1 for cp in checkpoints if cp["status"] == "PASS")
        weak = sum(1 for cp in checkpoints if cp["status"] == "WEAK")

        # Direction: majority of checkpoints must agree
        long_cps = sum(1 for cp in checkpoints if cp["direction"] == "LONG")
        short_cps = sum(1 for cp in checkpoints if cp["direction"] == "SHORT")

        if long_cps >= 3 and long_cps > short_cps:
            direction = "LONG"
        elif short_cps >= 3 and short_cps > long_cps:
            direction = "SHORT"
        else:
            direction = None

        # Danger: VPIN or conflicting signals
        vpin = state.get("vpin", {})
        vpin_pct = vpin.get("vpin_pct", 0)
        danger = vpin_pct > 50

        # Build setups
        long_setup = self._build_setup(state, "LONG", checkpoints)
        short_setup = self._build_setup(state, "SHORT", checkpoints)

        # Signal readiness
        if direction and not danger and (passed >= 2 or (passed >= 1 and weak >= 2)) and (now - self.last_signal_time > self.cooldown):
            ready = True
            signal = self._build_signal(state, direction, total_score, checkpoints)
            self.last_signal = signal
            self.last_signal_time = now
        else:
            ready = False
            signal = None

        # Stage
        if danger:
            stage = "🛑 BLOCKED — toxic flow detected"
        elif not direction:
            stage = "⏳ WAITING — no consensus (need 3+ agreeing)"
        elif passed < 2:
            stage = f"🔍 WEAK — only {passed} strong signals"
        elif not ready:
            stage = "⏳ COOLDOWN"
        else:
            stage = "🟢 SIGNAL READY"

        return {
            "stage": stage,
            "direction": direction,
            "total_score": total_score,
            "passed": passed,
            "weak": weak,
            "long_cps": long_cps,
            "short_cps": short_cps,
            "checkpoints": checkpoints,
            "ready": ready,
            "signal": signal,
            "long_setup": long_setup,
            "short_setup": short_setup,
        }

    def _build_setup(self, state, direction, checkpoints):
        """Build entry/stop/target using REAL liquidity structure."""
        price = state.get("price", 0)
        if price == 0:
            return None

        # === GET REAL LEVELS ===
        support = state.get("support_levels", [])
        resistance = state.get("resistance_levels", [])
        vah = state.get("vol_profile_vah", 0)
        val = state.get("vol_profile_val", 0)
        poc = state.get("vol_profile_poc", 0)
        liq = state.get("liq_clusters", {})
        liq_above = liq.get("clusters_above", [])
        liq_below = liq.get("clusters_below", [])

        # === CALCULATE VOLATILITY (spread-based) ===
        bid = state.get("optimal_bid", 0)
        ask = state.get("optimal_ask", 0)
        spread_pct = ((ask - bid) / price * 100) if price > 0 and ask > bid else 0.1
        # Minimum SL distance = max(1%, 3x spread) to avoid noise stops
        min_sl_pct = max(1.0, spread_pct * 3)

        if direction == "LONG":
            entry = price

            # ═══ STOP LOSS ═══
            # Find the strongest support level that's at least min_sl_pct away
            stop = None
            stop_source = "fixed"

            # 1. Try orderbook support (pick strongest level beyond min distance)
            valid_supports = [s for s in support if (price - s["price"]) / price * 100 >= min_sl_pct]
            if valid_supports:
                # Pick the one with highest strength (most liquidity)
                best = max(valid_supports, key=lambda s: s.get("strength", 0))
                stop = best["price"] * 0.998  # 0.2% buffer below
                stop_source = "orderbook"

            # 2. Try liquidation clusters below
            if not stop and liq_below:
                for lb in sorted(liq_below, key=lambda x: x.get("liq_usd", 0), reverse=True):
                    lb_price = lb.get("price", 0)
                    if lb_price > 0 and (price - lb_price) / price * 100 >= min_sl_pct:
                        stop = lb_price * 0.998
                        stop_source = "liquidation"
                        break

            # 3. Fallback: fixed % based on volatility
            if not stop:
                stop = price * (1 - min_sl_pct / 100)
                stop_source = "fixed"

            # ═══ TAKE PROFIT ═══
            # Find the nearest liquidity target above
            target = None
            tp_source = "fixed"
            sl_dist = stop - entry if stop else entry * 0.01
            min_tp_dist = sl_dist * 2  # TP must be at least 2x SL distance

            # 1. Try liquidation clusters above (price magnets)
            if liq_above:
                for la in sorted(liq_above, key=lambda x: x.get("liq_usd", 0), reverse=True):
                    la_price = la.get("price", 0)
                    if la_price - entry >= min_tp_dist:
                        target = la_price
                        tp_source = "liquidation"
                        break

            # 2. Try orderbook resistance (must be far enough)
            if not target and resistance:
                for r in sorted(resistance, key=lambda x: x["price"]):
                    if r["price"] - entry >= min_tp_dist:
                        target = r["price"]
                        tp_source = "orderbook"
                        break

            # 3. Fallback: 3x SL distance
            if not target:
                target = entry + sl_dist * 3
                tp_source = "calculated"

            score = sum(cp["score"] for cp in checkpoints if cp["score"] > 0)
            supporting = [cp["detail"] for cp in checkpoints if cp["direction"] == "LONG"]

        else:  # SHORT
            entry = price

            # ═══ STOP LOSS ═══
            stop = None
            stop_source = "fixed"

            # 1. Try orderbook resistance
            valid_resistances = [r for r in resistance if (r["price"] - price) / price * 100 >= min_sl_pct]
            if valid_resistances:
                best = max(valid_resistances, key=lambda r: r.get("strength", 0))
                stop = best["price"] * 1.002  # 0.2% buffer above
                stop_source = "orderbook"

            # 2. Try liquidation clusters above
            if not stop and liq_above:
                for la in sorted(liq_above, key=lambda x: x.get("liq_usd", 0), reverse=True):
                    la_price = la.get("price", 0)
                    if la_price > 0 and (la_price - price) / price * 100 >= min_sl_pct:
                        stop = la_price * 1.002
                        stop_source = "liquidation"
                        break

            # 3. Fallback
            if not stop:
                stop = price * (1 + min_sl_pct / 100)
                stop_source = "fixed"

            # ═══ TAKE PROFIT ═══
            target = None
            tp_source = "fixed"
            sl_dist = stop - entry if stop else entry * 0.01
            min_tp_dist = sl_dist * 2  # TP must be at least 2x SL distance

            # 1. Try liquidation clusters below
            if liq_below:
                for lb in sorted(liq_below, key=lambda x: x.get("liq_usd", 0), reverse=True):
                    lb_price = lb.get("price", 0)
                    if entry - lb_price >= min_tp_dist:
                        target = lb_price
                        tp_source = "liquidation"
                        break

            # 2. Try orderbook support (must be far enough)
            if not target and support:
                for s in sorted(support, key=lambda x: x["price"], reverse=True):
                    if entry - s["price"] >= min_tp_dist:
                        target = s["price"]
                        tp_source = "orderbook"
                        break

            # 3. Fallback: 3x SL distance
            if not target:
                target = entry - sl_dist * 3
                tp_source = "calculated"

            score = abs(sum(cp["score"] for cp in checkpoints if cp["score"] < 0))
            supporting = [cp["detail"] for cp in checkpoints if cp["direction"] == "SHORT"]

        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0

        # Reject if R:R < 2
        if rr < 2.0:
            return None

        sl_pct = risk / entry * 100
        tp_pct = reward / entry * 100

        return {
            "direction": direction,
            "entry": round(entry, 2),
            "stop_loss": round(stop, 2),
            "target": round(target, 2),
            "risk": round(risk, 2),
            "reward": round(reward, 2),
            "rr": round(rr, 1),
            "sl_pct": round(sl_pct, 2),
            "tp_pct": round(tp_pct, 2),
            "score": score,
            "supporting": supporting,
            "supporting_count": len(supporting),
            "stop_source": stop_source,
            "tp_source": tp_source,
            "min_sl_used": round(min_sl_pct, 2),
        }

    def _build_signal(self, state, direction, score, checkpoints):
        """Build trade signal using the same smart logic as _build_setup."""
        setup = self._build_setup(state, direction, checkpoints)
        if not setup:
            return None

        reasons = [cp["detail"] for cp in checkpoints if cp["status"] in ["PASS", "WEAK"] and cp["direction"] == direction]

        return {
            "time": time.time(),
            "direction": direction,
            "score": score,
            "entry": setup["entry"],
            "stop_loss": setup["stop_loss"],
            "target": setup["target"],
            "risk": setup["risk"],
            "reward": setup["reward"],
            "rr": setup["rr"],
            "reasons": reasons,
            "stop_source": setup.get("stop_source", "atr"),
            "tp_source": setup.get("tp_source", "atr"),
            "checkpoints_passed": sum(1 for cp in checkpoints if cp["status"] == "PASS"),
        }

    def _empty(self):
        return {
            "stage": "⏳ INITIALIZING",
            "direction": None,
            "total_score": 0,
            "passed": 0,
            "weak": 0,
            "checkpoints": [],
            "ready": False,
            "signal": None,
        }
