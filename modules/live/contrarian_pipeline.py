"""
Contrarian Signal Pipeline v4

CORE PHILOSOPHY: Trade AGAINST the crowd, not with it.
- When everyone is buying → look for short opportunities
- When everyone is selling → look for long opportunities
- Enter at LEVELS (POC, VAL, VAH, liquidation clusters), not at market
- Use CVD divergence as primary signal (predicts reversals)
- Use ATR for volatility-adaptive SL/TP

SIGNALS (all contrarian):
1. CVD Divergence — price vs volume delta divergence (predictive)
2. Extreme Funding — crowd is all-in one direction (fade them)
3. Whale Exhaustion — large trades drying up after a move (reversal coming)
4. Level Reaction — price at key level + any contrarian signal = entry
5. Momentum Exhaustion — acceleration dying after strong move
"""

import time
from collections import deque


class ContrarianPipeline:
    def __init__(self):
        self.last_signal = None
        self.last_signal_time = 0
        self.cooldown = 600  # 10 min between signals (quality over quantity)

        # Track recent signals for win rate estimation
        self.signal_history = deque(maxlen=100)

    def evaluate(self, state, atr_engine):
        """
        Evaluate contrarian signals.
        Returns signal dict or None.
        """
        now = time.time()
        price = state.get("price", 0)
        if price == 0:
            return self._empty("No price data")

        checkpoints = []

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 0: HIGHER TIMEFRAME TREND FILTER
        # Only trade in the direction of the 15m+ trend
        # Fading WITH the trend = high probability
        # Fading AGAINST the trend = getting run over
        # ═══════════════════════════════════════════════════════
        mtf = state.get("mtf", {})
        mtf_15m = mtf.get("15m", {})
        mtf_5m = mtf.get("5m", {})
        
        # Use 15m trend as primary filter
        trend_direction = None
        trend_score = 0
        
        buy_pct_15m = mtf_15m.get("buy_pct", 50)
        buy_pct_5m = mtf_5m.get("buy_pct", 50)
        
        # Strong trend: both 5m and 15m agree
        if buy_pct_15m > 58 and buy_pct_5m > 55:
            trend_direction = "LONG"
            trend_score = 3
            checkpoints.append({
                "name": "TREND",
                "status": "PASS",
                "detail": f"🟢 Uptrend — 15m {buy_pct_15m:.0f}% buy, 5m {buy_pct_5m:.0f}% buy",
                "score": 3,
                "direction": "LONG",
                "type": "trend",
                "weight": "heavy",
            })
        elif buy_pct_15m < 42 and buy_pct_5m < 45:
            trend_direction = "SHORT"
            trend_score = 3
            checkpoints.append({
                "name": "TREND",
                "status": "PASS",
                "detail": f"🔴 Downtrend — 15m {buy_pct_15m:.0f}% buy, 5m {buy_pct_5m:.0f}% buy",
                "score": 3,
                "direction": "SHORT",
                "type": "trend",
                "weight": "heavy",
            })
        elif buy_pct_15m > 55:
            trend_direction = "LONG"
            trend_score = 1
            checkpoints.append({
                "name": "TREND",
                "status": "WEAK",
                "detail": f"🟡 Mild uptrend — 15m {buy_pct_15m:.0f}% buy",
                "score": 1,
                "direction": "LONG",
                "type": "trend",
                "weight": "medium",
            })
        elif buy_pct_15m < 45:
            trend_direction = "SHORT"
            trend_score = 1
            checkpoints.append({
                "name": "TREND",
                "status": "WEAK",
                "detail": f"🟡 Mild downtrend — 15m {buy_pct_15m:.0f}% buy",
                "score": 1,
                "direction": "SHORT",
                "type": "trend",
                "weight": "medium",
            })
        else:
            checkpoints.append({
                "name": "TREND",
                "status": "NEUTRAL",
                "detail": f"⚪ No clear trend — 15m {buy_pct_15m:.0f}% buy",
                "score": 0,
                "direction": None,
                "type": "trend",
            })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 1: CVD DIVERGENCE — The best predictive signal
        # When price makes new high but CVD doesn't = institutions selling
        # When price makes new low but CVD doesn't = institutions buying
        # ═══════════════════════════════════════════════════════
        cvd = state.get("cvd", {})
        divergence = cvd.get("divergence")
        cvd_roc_5m = cvd.get("cvd_roc_5m", 0)
        cvd_roc_15m = cvd.get("cvd_roc_15m", 0)

        if divergence:
            if divergence["type"] == "BEARISH":
                # Price up, CVD down → institutions distributing → SHORT
                checkpoints.append({
                    "name": "CVD DIV",
                    "status": "PASS",
                    "detail": f"🔴 Bearish divergence — institutions selling into strength",
                    "score": 4,
                    "direction": "SHORT",
                    "type": "contrarian",
                    "weight": "heavy",
                })
            elif divergence["type"] == "BULLISH":
                # Price down, CVD up → institutions accumulating → LONG
                checkpoints.append({
                    "name": "CVD DIV",
                    "status": "PASS",
                    "detail": f"🟢 Bullish divergence — institutions buying into weakness",
                    "score": 4,
                    "direction": "LONG",
                    "type": "contrarian",
                    "weight": "heavy",
                })
        else:
            # No divergence — check CVD trend for exhaustion
            # Strong CVD one way but price not following = exhaustion
            if cvd_roc_5m > 200 and cvd_roc_15m > 500:
                # Massive buying but check if price is stalling
                accel = state.get("accel_10s", 0)
                if accel < 10:  # CVD strong but momentum dying
                    checkpoints.append({
                        "name": "CVD DIV",
                        "status": "WEAK",
                        "detail": f"🟡 Buying exhaustion — CVD strong ({cvd_roc_5m:+.0f}) but momentum dying ({accel:+.0f})",
                        "score": 2,
                        "direction": "SHORT",
                        "type": "contrarian",
                        "weight": "medium",
                    })
                else:
                    checkpoints.append({
                        "name": "CVD DIV",
                        "status": "NEUTRAL",
                        "detail": f"⚪ CVD buying ({cvd_roc_5m:+.0f}) — no divergence yet",
                        "score": 0,
                        "direction": None,
                    })
            elif cvd_roc_5m < -200 and cvd_roc_15m < -500:
                accel = state.get("accel_10s", 0)
                if accel > -10:  # CVD weak but momentum dying
                    checkpoints.append({
                        "name": "CVD DIV",
                        "status": "WEAK",
                        "detail": f"🟡 Selling exhaustion — CVD weak ({cvd_roc_5m:+.0f}) but momentum dying ({accel:+.0f})",
                        "score": 2,
                        "direction": "LONG",
                        "type": "contrarian",
                        "weight": "medium",
                    })
                else:
                    checkpoints.append({
                        "name": "CVD DIV",
                        "status": "NEUTRAL",
                        "detail": f"⚪ CVD selling ({cvd_roc_5m:+.0f}) — no divergence yet",
                        "score": 0,
                        "direction": None,
                    })
            else:
                checkpoints.append({
                    "name": "CVD DIV",
                    "status": "NEUTRAL",
                    "detail": f"⚪ No CVD divergence ({cvd_roc_5m:+.0f})",
                    "score": 0,
                    "direction": None,
                })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 2: EXTREME FUNDING — Crowd is all-in
        # When funding is extremely positive = crowd is long → SHORT
        # When funding is extremely negative = crowd is short → LONG
        # ═══════════════════════════════════════════════════════
        funding = state.get("funding_rate_pct", 0)

        if funding > 0.08:
            # Crowd heavily long → fade them
            checkpoints.append({
                "name": "FUNDING",
                "status": "PASS",
                "detail": f"🔴 Extreme long funding ({funding:+.4f}%) — crowd all-in long, fade them",
                "score": 3,
                "direction": "SHORT",
                "type": "contrarian",
                "weight": "heavy",
            })
        elif funding > 0.04:
            checkpoints.append({
                "name": "FUNDING",
                "status": "WEAK",
                "detail": f"🟡 Elevated funding ({funding:+.4f}%) — crowd leaning long",
                "score": 1,
                "direction": "SHORT",
                "type": "contrarian",
                "weight": "light",
            })
        elif funding < -0.04:
            # Crowd heavily short → fade them
            checkpoints.append({
                "name": "FUNDING",
                "status": "PASS",
                "detail": f"🟢 Extreme short funding ({funding:+.4f}%) — crowd all-in short, fade them",
                "score": 3,
                "direction": "LONG",
                "type": "contrarian",
                "weight": "heavy",
            })
        elif funding < -0.02:
            checkpoints.append({
                "name": "FUNDING",
                "status": "WEAK",
                "detail": f"🟡 Negative funding ({funding:+.4f}%) — crowd leaning short",
                "score": 1,
                "direction": "LONG",
                "type": "contrarian",
                "weight": "light",
            })
        else:
            checkpoints.append({
                "name": "FUNDING",
                "status": "NEUTRAL",
                "detail": f"⚪ Neutral funding ({funding:+.4f}%) — no crowd bias",
                "score": 0,
                "direction": None,
            })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 3: WHALE EXHAUSTION — Large trades drying up
        # After a big move, if whale activity drops = move is done
        # ═══════════════════════════════════════════════════════
        large_net = state.get("large_net", 0)
        large_buy_count = state.get("large_buy_count", 0)
        large_sell_count = state.get("large_sell_count", 0)
        whale_score = state.get("whale_score", 0)

        # Contra-whale: if whales were buying but now net flow is reversing
        if large_net < -15 and large_sell_count >= 3 and whale_score > 15:
            # Whales were accumulating, now distributing → SHORT
            checkpoints.append({
                "name": "WHALES",
                "status": "PASS",
                "detail": f"🔴 Whale distribution — {large_sell_count} sells ({large_net:+.1f} ETH) after accumulation",
                "score": 3,
                "direction": "SHORT",
                "type": "contrarian",
                "weight": "heavy",
            })
        elif large_net > 15 and large_buy_count >= 3 and whale_score < -15:
            # Whales were distributing, now accumulating → LONG
            checkpoints.append({
                "name": "WHALES",
                "status": "PASS",
                "detail": f"🟢 Whale accumulation — {large_buy_count} buys ({large_net:+.1f} ETH) after distribution",
                "score": 3,
                "direction": "LONG",
                "type": "contrarian",
                "weight": "heavy",
            })
        elif large_net > 20 and large_buy_count >= 5:
            # Strong buying but check if it's exhaustion
            accel = state.get("accel_10s", 0)
            if accel < 5:
                checkpoints.append({
                    "name": "WHALES",
                    "status": "WEAK",
                    "detail": f"🟡 Whale buying exhaustion — {large_buy_count} buys but momentum dying",
                    "score": 1,
                    "direction": "SHORT",
                    "type": "contrarian",
                    "weight": "medium",
                })
            else:
                checkpoints.append({
                    "name": "WHALES",
                    "status": "NEUTRAL",
                    "detail": f"⚪ Whale buying ({large_net:+.1f} ETH) — still active",
                    "score": 0,
                    "direction": None,
                })
        elif large_net < -20 and large_sell_count >= 5:
            accel = state.get("accel_10s", 0)
            if accel > -5:
                checkpoints.append({
                    "name": "WHALES",
                    "status": "WEAK",
                    "detail": f"🟡 Whale selling exhaustion — {large_sell_count} sells but momentum dying",
                    "score": 1,
                    "direction": "LONG",
                    "type": "contrarian",
                    "weight": "medium",
                })
            else:
                checkpoints.append({
                    "name": "WHALES",
                    "status": "NEUTRAL",
                    "detail": f"⚪ Whale selling ({large_net:+.1f} ETH) — still active",
                    "score": 0,
                    "direction": None,
                })
        else:
            checkpoints.append({
                "name": "WHALES",
                "status": "NEUTRAL",
                "detail": f"⚪ No whale exhaustion ({large_net:+.1f} ETH)",
                "score": 0,
                "direction": None,
            })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 4: LEVEL PROXIMITY — Is price at a key level?
        # Trade at levels, not at random prices
        # ═══════════════════════════════════════════════════════
        poc = state.get("vol_profile_poc", 0)
        val = state.get("vol_profile_val", 0)
        vah = state.get("vol_profile_vah", 0)
        support = state.get("support_levels", [])
        resistance = state.get("resistance_levels", [])

        level_info = self._check_level_proximity(price, poc, val, vah, support, resistance)

        if level_info["at_level"]:
            if level_info["direction"] == "LONG":
                checkpoints.append({
                    "name": "LEVEL",
                    "status": "PASS",
                    "detail": f"🟢 At support level {level_info['level_name']} (${level_info['level_price']:,.0f}) — bounce zone",
                    "score": 2,
                    "direction": "LONG",
                    "type": "level",
                    "weight": "medium",
                    "level": level_info,
                })
            elif level_info["direction"] == "SHORT":
                checkpoints.append({
                    "name": "LEVEL",
                    "status": "PASS",
                    "detail": f"🔴 At resistance level {level_info['level_name']} (${level_info['level_price']:,.0f}) — rejection zone",
                    "score": 2,
                    "direction": "SHORT",
                    "type": "level",
                    "weight": "medium",
                    "level": level_info,
                })
        else:
            checkpoints.append({
                "name": "LEVEL",
                "status": "NEUTRAL",
                "detail": f"⚪ Not at key level (nearest: ${level_info.get('nearest_price', 0):,.0f} {level_info.get('nearest_name', '')})",
                "score": 0,
                "direction": None,
            })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 5: MOMENTUM EXHAUSTION — Is the move dying?
        # Strong move + decelerating = reversal imminent
        # ═══════════════════════════════════════════════════════
        accel_10s = state.get("accel_10s", 0)
        accel_30s = state.get("accel_30s", 0)
        buying_pressure = state.get("buying_pressure", 0)

        # Exhaustion: strong one-way pressure + deceleration
        if buying_pressure > 40 and accel_10s < -20 and accel_30s < 30:
            # Was buying hard, now decelerating → SHORT
            checkpoints.append({
                "name": "MOMENTUM",
                "status": "PASS",
                "detail": f"🔴 Buying exhaustion — pressure {buying_pressure:+.0f} but decelerating ({accel_10s:+.0f})",
                "score": 2,
                "direction": "SHORT",
                "type": "contrarian",
                "weight": "medium",
            })
        elif buying_pressure < -40 and accel_10s > 20 and accel_30s > -30:
            # Was selling hard, now decelerating → LONG
            checkpoints.append({
                "name": "MOMENTUM",
                "status": "PASS",
                "detail": f"🟢 Selling exhaustion — pressure {buying_pressure:+.0f} but decelerating ({accel_10s:+.0f})",
                "score": 2,
                "direction": "LONG",
                "type": "contrarian",
                "weight": "medium",
            })
        elif abs(accel_10s) < 10 and abs(accel_30s) < 20:
            checkpoints.append({
                "name": "MOMENTUM",
                "status": "NEUTRAL",
                "detail": f"⚪ Stable momentum ({accel_10s:+.0f}/{accel_30s:+.0f})",
                "score": 0,
                "direction": None,
            })
        else:
            checkpoints.append({
                "name": "MOMENTUM",
                "status": "NEUTRAL",
                "detail": f"⚪ Momentum ({accel_10s:+.0f}/{accel_30s:+.0f}) — no exhaustion",
                "score": 0,
                "direction": None,
            })

        # ═══════════════════════════════════════════════════════
        # SCORING — Contrarian + Trend Filter
        # ═══════════════════════════════════════════════════════
        total_score = sum(cp["score"] for cp in checkpoints)
        passed = sum(1 for cp in checkpoints if cp["status"] == "PASS")

        # Direction: need at least 1 heavy contrarian signal + 1 level
        heavy_signals = [cp for cp in checkpoints if cp.get("weight") == "heavy" and cp["score"] > 0]
        level_signal = any(cp.get("type") == "level" and cp["score"] > 0 for cp in checkpoints)
        contrarian_passed = sum(1 for cp in checkpoints if cp.get("type") == "contrarian" and cp["status"] == "PASS")
        trend_cp = next((cp for cp in checkpoints if cp.get("type") == "trend"), None)
        trend_dir = trend_cp["direction"] if trend_cp else None

        # Determine direction from contrarian signals
        long_score = sum(cp["score"] for cp in checkpoints if cp["direction"] == "LONG" and cp["score"] > 0)
        short_score = sum(cp["score"] for cp in checkpoints if cp["direction"] == "SHORT" and cp["score"] > 0)

        if long_score > short_score and long_score >= 4:
            raw_direction = "LONG"
        elif short_score > long_score and short_score >= 4:
            raw_direction = "SHORT"
        else:
            raw_direction = None

        # ═══ TREND FILTER ═══
        # Only trade WITH the trend. If contrarian signal opposes trend → block it.
        # Exception: if trend is NEUTRAL (no clear direction), allow both.
        direction = None
        trend_blocked = False
        
        if raw_direction and trend_dir:
            if raw_direction == trend_dir:
                # Contrarian signal aligns with trend → proceed
                direction = raw_direction
            else:
                # Contrarian signal opposes trend → BLOCK
                trend_blocked = True
                direction = None
        elif raw_direction and trend_dir is None:
            # No clear trend → allow contrarian signal (but lower confidence)
            direction = raw_direction
        else:
            direction = raw_direction

        # ═══════════════════════════════════════════════════════
        # SIGNAL GENERATION
        # ═══════════════════════════════════════════════════════
        # Need: direction WITH trend + at least 1 contrarian PASS + at level OR 2 contrarian PASS
        can_signal = (
            direction
            and not trend_blocked
            and (contrarian_passed >= 2 or (contrarian_passed >= 1 and level_signal))
            and (now - self.last_signal_time > self.cooldown)
        )

        if can_signal and atr_engine:
            signal = self._build_signal(state, direction, total_score, checkpoints, atr_engine)
            if signal:
                self.last_signal = signal
                self.last_signal_time = now
                ready = True
            else:
                ready = False
                signal = None
        else:
            ready = False
            signal = None

        # Build setups for both directions
        long_setup = self._build_setup(state, "LONG", checkpoints, atr_engine) if atr_engine else None
        short_setup = self._build_setup(state, "SHORT", checkpoints, atr_engine) if atr_engine else None

        # Stage
        if trend_blocked:
            stage = f"🛑 TREND BLOCKED — contrarian {raw_direction} but trend is {trend_dir}"
        elif not direction:
            stage = "⏳ WAITING — no contrarian signal"
        elif contrarian_passed == 0:
            stage = "🔍 SCANNING — need contrarian confirmation"
        elif contrarian_passed >= 1 and level_signal:
            stage = "🟢 AT LEVEL + CONTRARIAN + TREND — best setup"
        elif contrarian_passed >= 2:
            stage = "🟢 MULTIPLE CONTRARIANS + TREND — strong setup"
        elif not ready:
            stage = "⏳ COOLDOWN"
        else:
            stage = "🔍 FORMING"

        return {
            "stage": stage,
            "direction": direction,
            "total_score": total_score,
            "passed": passed,
            "contrarian_passed": contrarian_passed,
            "level_signal": level_signal,
            "checkpoints": checkpoints,
            "ready": ready,
            "signal": signal,
            "long_setup": long_setup,
            "short_setup": short_setup,
        }

    def _check_level_proximity(self, price, poc, val, vah, support, resistance):
        """
        Check if price is near a key level.
        Returns info about nearest level and whether we're 'at' it.
        """
        threshold_pct = 0.3  # Within 0.3% = "at level"

        levels = []

        # Volume profile levels
        if poc > 0:
            dist = abs(price - poc) / price * 100
            levels.append({"name": "POC", "price": poc, "dist_pct": dist, "type": "neutral"})
        if val > 0:
            dist = abs(price - val) / price * 100
            levels.append({"name": "VAL", "price": val, "dist_pct": dist, "type": "support"})
        if vah > 0:
            dist = abs(price - vah) / price * 100
            levels.append({"name": "VAH", "price": vah, "dist_pct": dist, "type": "resistance"})

        # Orderbook levels
        for s in support[:2]:
            dist = abs(price - s["price"]) / price * 100
            levels.append({"name": f"Support", "price": s["price"], "dist_pct": dist, "type": "support", "strength": s.get("strength", 1)})
        for r in resistance[:2]:
            dist = abs(price - r["price"]) / price * 100
            levels.append({"name": f"Resistance", "price": r["price"], "dist_pct": dist, "type": "resistance", "strength": r.get("strength", 1)})

        if not levels:
            return {"at_level": False, "nearest_name": "none", "nearest_price": 0}

        # Sort by distance
        levels.sort(key=lambda x: x["dist_pct"])
        nearest = levels[0]

        # Check if at level
        at_level = nearest["dist_pct"] <= threshold_pct

        # Direction based on level type
        if at_level:
            if nearest["type"] == "support":
                direction = "LONG"  # Bounce off support
            elif nearest["type"] == "resistance":
                direction = "SHORT"  # Rejection at resistance
            elif nearest["type"] == "neutral":
                # POC — could go either way, check momentum
                direction = None
            else:
                direction = None
        else:
            direction = None

        return {
            "at_level": at_level,
            "level_name": nearest["name"],
            "level_price": nearest["price"],
            "level_type": nearest["type"],
            "dist_pct": nearest["dist_pct"],
            "direction": direction,
            "nearest_name": nearest["name"],
            "nearest_price": nearest["price"],
            "all_levels": [{"name": l["name"], "price": l["price"], "dist": l["dist_pct"]} for l in levels[:5]],
        }

    def _build_setup(self, state, direction, checkpoints, atr_engine):
        """Build entry/SL/TP using ATR + level awareness."""
        price = state.get("price", 0)
        if price == 0 or not atr_engine:
            return None

        # Get ATR-based levels
        levels = atr_engine.get_levels(price, direction, sl_mult=1.5, tp_mult=2.5)
        if not levels:
            return None

        # If we have a level signal, refine SL to use the level
        level_cp = next((cp for cp in checkpoints if cp.get("type") == "level" and cp.get("level")), None)
        if level_cp:
            level_info = level_cp["level"]
            level_price = level_info.get("level_price", 0)

            if direction == "LONG" and level_info.get("level_type") in ("support", "neutral"):
                # Move SL below the support level
                level_sl = level_price - atr_engine.get_sl_distance(0.5)
                if level_sl < levels["sl"]:
                    levels["sl"] = round(level_sl, 2)
                    levels["risk"] = round(abs(price - level_sl), 2)
                    levels["rr"] = round(levels["reward"] / levels["risk"], 2) if levels["risk"] > 0 else 0
                    levels["sl_source"] = "level"
            elif direction == "SHORT" and level_info.get("level_type") in ("resistance", "neutral"):
                level_sl = level_price + atr_engine.get_sl_distance(0.5)
                if level_sl > levels["sl"]:
                    levels["sl"] = round(level_sl, 2)
                    levels["risk"] = round(abs(level_sl - price), 2)
                    levels["rr"] = round(levels["reward"] / levels["risk"], 2) if levels["risk"] > 0 else 0
                    levels["sl_source"] = "level"

        # Reject bad R:R
        if levels["rr"] < 1.5:
            return None

        score = sum(cp["score"] for cp in checkpoints if cp["direction"] == direction and cp["score"] > 0)
        supporting = [cp["detail"] for cp in checkpoints if cp["direction"] == direction and cp["score"] > 0]

        return {
            "direction": direction,
            "entry": levels["entry"],
            "stop_loss": levels["sl"],
            "target": levels["tp"],
            "risk": levels["risk"],
            "reward": levels["reward"],
            "rr": levels["rr"],
            "sl_pct": levels["sl_pct"],
            "tp_pct": levels["tp_pct"],
            "atr": levels["atr"],
            "atr_pct": levels["atr_pct"],
            "score": score,
            "supporting": supporting,
            "supporting_count": len(supporting),
            "sl_source": levels.get("sl_source", "atr"),
            "tp_source": "atr",
            "trail_distance": round(atr_engine.get_trail_distance(1.0), 2),
        }

    def _build_signal(self, state, direction, total_score, checkpoints, atr_engine):
        """Build the actual trade signal."""
        setup = self._build_setup(state, direction, checkpoints, atr_engine)
        if not setup:
            return None

        reasons = [cp["detail"] for cp in checkpoints if cp["direction"] == direction and cp["score"] > 0]

        return {
            "time": time.time(),
            "direction": direction,
            "score": total_score,
            "entry": setup["entry"],
            "stop_loss": setup["stop_loss"],
            "target": setup["target"],
            "risk": setup["risk"],
            "reward": setup["reward"],
            "rr": setup["rr"],
            "sl_pct": setup["sl_pct"],
            "tp_pct": setup["tp_pct"],
            "atr": setup["atr"],
            "reasons": reasons,
            "stop_source": setup.get("sl_source", "atr"),
            "tp_source": setup.get("tp_source", "atr"),
            "trail_distance": setup.get("trail_distance", 0),
            "checkpoints_passed": sum(1 for cp in checkpoints if cp["status"] == "PASS"),
            "contrarian_signals": sum(1 for cp in checkpoints if cp.get("type") == "contrarian" and cp["status"] == "PASS"),
            "at_level": any(cp.get("type") == "level" and cp["score"] > 0 for cp in checkpoints),
        }

    def _empty(self, reason):
        return {
            "stage": f"⏳ {reason}",
            "direction": None,
            "total_score": 0,
            "passed": 0,
            "contrarian_passed": 0,
            "level_signal": False,
            "checkpoints": [],
            "ready": False,
            "signal": None,
            "long_setup": None,
            "short_setup": None,
        }

    def format_signal(self, signal):
        """Format signal for Telegram."""
        if not signal:
            return None

        dir_emoji = "🟢" if signal["direction"] == "LONG" else "🔴"

        lines = [
            f"{dir_emoji} <b>CONTRARIAN {signal['direction']}</b> {dir_emoji}",
            f"",
            f"<b>Entry:</b> ${signal['entry']:,.2f}",
            f"<b>Stop Loss:</b> ${signal['stop_loss']:,.2f} ({signal['sl_pct']:.1f}%)",
            f"<b>Target:</b> ${signal['target']:,.2f} ({signal['tp_pct']:.1f}%)",
            f"<b>R:R:</b> 1:{signal['rr']}",
            f"<b>ATR:</b> ${signal['atr']:.2f}",
            f"",
            f"<b>Signals:</b>",
        ]
        for r in signal.get("reasons", []):
            lines.append(f"  • {r}")

        if signal.get("trail_distance"):
            lines.append(f"")
            lines.append(f"<b>Trail Stop:</b> ${signal['trail_distance']:.2f} (activates at 1R profit)")

        return "\n".join(lines)
