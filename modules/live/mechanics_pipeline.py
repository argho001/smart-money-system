"""
Market Mechanics Pipeline v5

Built on HOW THE MARKET ACTUALLY WORKS, not lagging indicators.

The market is a liquidity-seeking machine. Price goes where the orders are.
Big players accumulate using TWAP/VWAP, create false breakouts to trap retail,
and liquidation cascades drive the biggest moves.

SIGNALS (based on actual market mechanics):
1. Liquidity Sweep — Stop hunt + reversal (most reliable signal)
2. Wyckoff Spring/Upthrust — False breakout patterns
3. Liquidation Cascade — After cascade, price reverses
4. Liquidation Proximity — Price approaching cascade target
5. Funding Extreme + Liq Cluster — Crowd wrong AND about to get liquidated
6. BTC Leading — BTC moves first, ETH follows

FILTERS:
- Session quality (don't trade during dead hours)
- BTC agreement (don't fight BTC)
- Trend direction (trade with the trend)
"""

import time


class MechanicsPipeline:
    def __init__(self):
        self.last_signal = None
        self.last_signal_time = 0
        self.cooldown = 300  # 5 min between signals

        # Signal history for win rate tracking
        self.signal_history = []

    def evaluate(self, state, atr_engine, btc_engine=None, session_filter=None,
                 liq_heatmap=None, sweep_detector=None, wyckoff=None):
        """
        Evaluate market mechanics for trading signals.
        """
        now = time.time()
        price = state.get("price", 0)
        if price == 0:
            return self._empty("No price data")

        checkpoints = []

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 1: SESSION QUALITY
        # Don't trade during dead hours
        # ═══════════════════════════════════════════════════════
        session_info = session_filter.get_session() if session_filter else None
        session_quality = session_info.get("quality_raw", "medium") if session_info else "medium"

        if session_quality == "high":
            checkpoints.append({
                "name": "SESSION",
                "status": "PASS",
                "detail": f"🟢 {session_info['session']} session — high quality",
                "score": 1,
                "direction": None,
                "type": "filter",
            })
        elif session_quality == "low":
            checkpoints.append({
                "name": "SESSION",
                "status": "BLOCK",
                "detail": f"🔴 {session_info.get('session', '?')} session — low quality, avoid",
                "score": -2,
                "direction": None,
                "type": "filter",
            })
        else:
            checkpoints.append({
                "name": "SESSION",
                "status": "NEUTRAL",
                "detail": f"⚪ {session_info.get('session', '?')} session — medium quality",
                "score": 0,
                "direction": None,
                "type": "filter",
            })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 2: BTC CORRELATION
        # BTC leads, ETH follows
        # ═══════════════════════════════════════════════════════
        if btc_engine:
            mtf = state.get("mtf", {})
            mtf_5m = mtf.get("5m", {})
            eth_buy_pct = mtf_5m.get("buy_pct", 50)
            eth_change = (eth_buy_pct - 50) / 50 * 0.5
            btc_ctx = btc_engine.get_btc_context(eth_change)

            if btc_ctx["agreement"] == "AGREE":
                checkpoints.append({
                    "name": "BTC",
                    "status": "PASS",
                    "detail": f"🟢 {btc_ctx['detail']}",
                    "score": 2,
                    "direction": btc_ctx["btc_direction"],
                    "type": "filter",
                })
            elif btc_ctx["agreement"] == "DISAGREE":
                checkpoints.append({
                    "name": "BTC",
                    "status": "BLOCK",
                    "detail": f"🔴 {btc_ctx['detail']}",
                    "score": -2,
                    "direction": None,
                    "type": "filter",
                })
            else:
                checkpoints.append({
                    "name": "BTC",
                    "status": "NEUTRAL",
                    "detail": f"⚪ {btc_ctx['detail']}",
                    "score": 0,
                    "direction": None,
                    "type": "filter",
                })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 3: LIQUIDITY SWEEP
        # The most reliable reversal signal
        # ═══════════════════════════════════════════════════════
        if sweep_detector:
            # Update sweep detector with current levels
            support = state.get("support_levels", [])
            resistance = state.get("resistance_levels", [])
            sweep_detector.update(price, support_levels=support, resistance_levels=resistance)

            sweep = sweep_detector.detect_sweep()
            if sweep:
                checkpoints.append({
                    "name": "SWEEP",
                    "status": "PASS",
                    "detail": sweep["signal"],
                    "score": 4 if sweep["confidence"] == "🟢 HIGH" else 3,
                    "direction": sweep["direction"],
                    "type": "mechanic",
                    "weight": "heavy",
                })
            else:
                checkpoints.append({
                    "name": "SWEEP",
                    "status": "NEUTRAL",
                    "detail": "⚪ No sweep detected",
                    "score": 0,
                    "direction": None,
                    "type": "mechanic",
                })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 4: WYCKOFF PHASE
        # Accumulation/Distribution/Spring/Upthrust
        # ═══════════════════════════════════════════════════════
        if wyckoff:
            wyckoff.update(price)
            wyckoff_signal = wyckoff.get_signal()

            if wyckoff_signal and wyckoff_signal.get("direction"):
                phase = wyckoff_signal["phase"]
                if phase in ("SPRING", "UPTHRUST"):
                    checkpoints.append({
                        "name": "WYCKOFF",
                        "status": "PASS",
                        "detail": wyckoff_signal["signal"],
                        "score": 4 if phase == "SPRING" else 3,
                        "direction": wyckoff_signal["direction"],
                        "type": "mechanic",
                        "weight": "heavy",
                    })
                elif phase in ("MARKUP", "MARKDOWN"):
                    checkpoints.append({
                        "name": "WYCKOFF",
                        "status": "WEAK",
                        "detail": wyckoff_signal["signal"],
                        "score": 1,
                        "direction": wyckoff_signal["direction"],
                        "type": "mechanic",
                        "weight": "medium",
                    })
                else:
                    checkpoints.append({
                        "name": "WYCKOFF",
                        "status": "NEUTRAL",
                        "detail": wyckoff_signal["signal"],
                        "score": 0,
                        "direction": None,
                        "type": "mechanic",
                    })
            else:
                checkpoints.append({
                    "name": "WYCKOFF",
                    "status": "NEUTRAL",
                    "detail": f"⚪ Phase: {wyckoff.current_phase}",
                    "score": 0,
                    "direction": None,
                    "type": "mechanic",
                })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 5: LIQUIDATION CASCADE
        # After cascade, price reverses
        # ═══════════════════════════════════════════════════════
        if liq_heatmap:
            cascade = liq_heatmap.get_cascade_signal()
            proximity = liq_heatmap.get_proximity_signal(price)

            if cascade:
                checkpoints.append({
                    "name": "CASCADE",
                    "status": "PASS",
                    "detail": cascade["signal"],
                    "score": 5 if cascade["confidence"] == "high" else 3,
                    "direction": cascade["direction_after"],
                    "type": "mechanic",
                    "weight": "heavy",
                })
            elif proximity:
                checkpoints.append({
                    "name": "CASCADE",
                    "status": "WEAK",
                    "detail": proximity["signal"],
                    "score": 2,
                    "direction": proximity["direction"],
                    "type": "mechanic",
                    "weight": "medium",
                })
            else:
                checkpoints.append({
                    "name": "CASCADE",
                    "status": "NEUTRAL",
                    "detail": "⚪ No cascade active",
                    "score": 0,
                    "direction": None,
                    "type": "mechanic",
                })

        # ═══════════════════════════════════════════════════════
        # CHECKPOINT 6: FUNDING EXTREME + LIQUIDATION CONFLUENCE
        # Crowd wrong AND about to get liquidated
        # ═══════════════════════════════════════════════════════
        funding = state.get("funding_rate_pct", 0)

        if liq_heatmap:
            liq_state = liq_heatmap.get_state()
            nearest_long_liq = liq_state.get("nearest_long_liq", 0)
            nearest_short_liq = liq_state.get("nearest_short_liq", 0)

            # Funding extreme long + long liq cluster nearby = SHORT
            if funding > 0.06 and nearest_long_liq > 0:
                distance = (price - nearest_long_liq) / price * 100
                if distance < 1.0:  # Within 1%
                    checkpoints.append({
                        "name": "FUNDING+LIQ",
                        "status": "PASS",
                        "detail": f"🔴 Extreme long funding ({funding:+.3f}%) + long liq at ${nearest_long_liq:,.0f} ({distance:.2f}% away) — cascade coming",
                        "score": 3,
                        "direction": "SHORT",
                        "type": "mechanic",
                        "weight": "heavy",
                    })
                else:
                    checkpoints.append({
                        "name": "FUNDING+LIQ",
                        "status": "WEAK",
                        "detail": f"🟡 Extreme funding ({funding:+.3f}%) but liq cluster far ({distance:.1f}%)",
                        "score": 1,
                        "direction": "SHORT",
                        "type": "mechanic",
                        "weight": "light",
                    })
            elif funding < -0.03 and nearest_short_liq > 0:
                distance = (nearest_short_liq - price) / price * 100
                if distance < 1.0:
                    checkpoints.append({
                        "name": "FUNDING+LIQ",
                        "status": "PASS",
                        "detail": f"🟢 Extreme short funding ({funding:+.3f}%) + short liq at ${nearest_short_liq:,.0f} ({distance:.2f}% away) — cascade coming",
                        "score": 3,
                        "direction": "LONG",
                        "type": "mechanic",
                        "weight": "heavy",
                    })
                else:
                    checkpoints.append({
                        "name": "FUNDING+LIQ",
                        "status": "WEAK",
                        "detail": f"🟡 Negative funding ({funding:+.3f}%) but liq cluster far ({distance:.1f}%)",
                        "score": 1,
                        "direction": "LONG",
                        "type": "mechanic",
                        "weight": "light",
                    })
            else:
                checkpoints.append({
                    "name": "FUNDING+LIQ",
                    "status": "NEUTRAL",
                    "detail": f"⚪ Funding neutral ({funding:+.3f}%)",
                    "score": 0,
                    "direction": None,
                    "type": "mechanic",
                })

        # ═══════════════════════════════════════════════════════
        # SCORING — Weighted, not hard blocks
        # ═══════════════════════════════════════════════════════
        total_score = sum(cp["score"] for cp in checkpoints)
        passed = sum(1 for cp in checkpoints if cp["status"] == "PASS")

        # Direction from mechanic signals (not filters)
        mechanic_cps = [cp for cp in checkpoints if cp["type"] == "mechanic"]
        long_score = sum(cp["score"] for cp in mechanic_cps if cp["direction"] == "LONG")
        short_score = sum(cp["score"] for cp in mechanic_cps if cp["direction"] == "SHORT")

        if long_score > short_score and long_score >= 3:
            direction = "LONG"
        elif short_score > long_score and short_score >= 3:
            direction = "SHORT"
        else:
            direction = None

        # Check blocks
        session_blocked = any(cp["name"] == "SESSION" and cp["status"] == "BLOCK" for cp in checkpoints)
        btc_blocked = any(cp["name"] == "BTC" and cp["status"] == "BLOCK" for cp in checkpoints)

        # Weighted scoring: need enough conviction
        # Minimum 4 points from mechanic signals to trade
        can_signal = (
            direction
            and not session_blocked
            and not btc_blocked
            and long_score + short_score >= 4
            and (now - self.last_signal_time > self.cooldown)
        )

        if can_signal and atr_engine:
            signal = self._build_signal(state, direction, checkpoints, atr_engine)
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

        # Stage
        if session_blocked:
            stage = "🛑 SESSION BLOCKED"
        elif btc_blocked:
            stage = "🛑 BTC DISAGREES"
        elif not direction:
            stage = "⏳ WAITING — no mechanic signal"
        elif long_score + short_score < 4:
            stage = f"🔍 WEAK — score {long_score + short_score}/4 needed"
        elif not ready:
            stage = "⏳ COOLDOWN"
        else:
            stage = "🟢 SIGNAL READY — market mechanics aligned"

        return {
            "stage": stage,
            "direction": direction,
            "total_score": total_score,
            "passed": passed,
            "long_score": long_score,
            "short_score": short_score,
            "checkpoints": checkpoints,
            "ready": ready,
            "signal": signal,
        }

    def _build_signal(self, state, direction, checkpoints, atr_engine):
        """Build trade signal using ATR-based levels."""
        price = state.get("price", 0)
        if price == 0:
            return None

        # ATR-based levels
        levels = atr_engine.get_levels(price, direction, sl_mult=1.5, tp_mult=2.5)
        if not levels:
            return None

        # Reject bad R:R
        if levels["rr"] < 1.5:
            return None

        reasons = [cp["detail"] for cp in checkpoints if cp["direction"] == direction and cp["score"] > 0]

        return {
            "time": time.time(),
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
            "reasons": reasons,
            "trail_distance": round(atr_engine.get_trail_distance(1.0), 2),
            "checkpoints_passed": sum(1 for cp in checkpoints if cp["status"] == "PASS"),
        }

    def _empty(self, reason):
        return {
            "stage": f"⏳ {reason}",
            "direction": None,
            "total_score": 0,
            "passed": 0,
            "long_score": 0,
            "short_score": 0,
            "checkpoints": [],
            "ready": False,
            "signal": None,
        }

    def format_signal(self, signal):
        """Format signal for Telegram."""
        if not signal:
            return None

        dir_emoji = "🟢" if signal["direction"] == "LONG" else "🔴"

        lines = [
            f"{dir_emoji} <b>MECHANICS {signal['direction']}</b> {dir_emoji}",
            f"",
            f"<b>Entry:</b> ${signal['entry']:,.2f}",
            f"<b>Stop Loss:</b> ${signal['stop_loss']:,.2f} ({signal['sl_pct']:.1f}%)",
            f"<b>Target:</b> ${signal['target']:,.2f} ({signal['tp_pct']:.1f}%)",
            f"<b>R:R:</b> 1:{signal['rr']}",
            f"<b>ATR:</b> ${signal['atr']:.2f}",
            f"",
            f"<b>Why:</b>",
        ]
        for r in signal.get("reasons", []):
            lines.append(f"  • {r}")

        if signal.get("trail_distance"):
            lines.append(f"")
            lines.append(f"<b>Trail:</b> ${signal['trail_distance']:.2f} (activates at 1R)")

        return "\n".join(lines)
