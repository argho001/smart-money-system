"""
Smart Money System — Live Dashboard v5 (Simplified)
Only uses signals proven in backtest:
1. Liquidity sweep (support/resistance break + recovery)
2. Wyckoff spring/upthrust (false breakouts)
3. Funding extreme (crowd is wrong)
4. ATR-based SL/TP
5. BTC correlation filter
6. Session filter
"""
import asyncio
import json
import os
import sys
import time as time_mod
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, render_template, jsonify, request
from flask_sock import Sock
import aiohttp

# Only the engines we actually use
from modules.live.live_engine import LiveDataEngine
from modules.live.atr_engine import ATREngine
from modules.live.btc_correlation import BTCCorrelation
from modules.live.session_filter import SessionFilter
from modules.live.liquidation_heatmap import LiquidationHeatmap
from modules.live.liquidity_sweep import LiquiditySweepDetector
from modules.live.wyckoff_detector import WyckoffPhase
from modules.live.realtime_enhancer import RealtimeEnhancer

app = Flask(__name__)
sock = Sock(app)

# Core engines (only what backtest uses + real-time enhancer)
engine = LiveDataEngine()
atr = ATREngine(period=14)
btc_corr = BTCCorrelation()
session_filter = SessionFilter()
liq_heatmap = LiquidationHeatmap()
sweep_detector = LiquiditySweepDetector()
wyckoff = WyckoffPhase()
enhancer = RealtimeEnhancer()

# Trade manager (loaded if Binance keys exist)
trade_mgr = None
try:
    from config import settings
    if hasattr(settings, 'BINANCE_API_KEY') and settings.BINANCE_API_KEY:
        from modules.live.trade_manager import TradeManager
        trade_mgr = TradeManager(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
            base_url=getattr(settings, 'BINANCE_FUTURES_DEMO_URL', 'https://demo-fapi.binance.com'),
            config={"usdt_per_trade": 100, "leverage": 5, "auto_trade": False, "cooldown": 300, "risk_pct": 2.0}
        )
        print("[TRADE] Binance executor connected")
    else:
        print("[TRADE] No Binance keys — execution disabled")
except Exception as e:
    print(f"[TRADE] Init failed: {e}")

enhanced_state = {}
_engine_ready = False
_last_signal_time = 0
SIGNAL_COOLDOWN = 300  # 5 min between signals


def enhance_state(state):
    """Process live state and generate signals using backtested logic."""
    global enhanced_state, _last_signal_time

    price = state.get("price", 0)
    if price == 0:
        return state

    # Update ATR
    atr.update(price)

    # Update BTC correlation
    btc_corr.update_eth_price(price)

    # Update Wyckoff
    wyckoff.update(price)

    # Update liquidity sweep
    support = state.get("support_levels", [])
    resistance = state.get("resistance_levels", [])
    sweep_detector.update(price, support_levels=support, resistance_levels=resistance)

    # ═══════════════════════════════════════════════════════════
    # SIGNAL DETECTION — Same logic as backtest
    # ═══════════════════════════════════════════════════════════
    score = 0
    direction = None
    reasons = []

    # Signal 1: Liquidity Sweep
    sweep = sweep_detector.detect_sweep()
    if sweep:
        score += 4
        direction = sweep["direction"]
        reasons.append(sweep["signal"])

    # Signal 2: Wyckoff Spring/Upthrust
    wyckoff_signal = wyckoff.get_signal()
    if wyckoff_signal and wyckoff_signal.get("direction"):
        phase = wyckoff_signal["phase"]
        if phase in ("SPRING", "UPTHRUST"):
            score += 3
            if not direction:
                direction = wyckoff_signal["direction"]
            reasons.append(wyckoff_signal["signal"])

    # Signal 3: Funding Extreme
    funding = state.get("funding_rate_pct", 0)
    if funding > 0.06:
        score += 2
        if not direction:
            direction = "SHORT"
        reasons.append(f"Extreme long funding ({funding:+.4f}%)")
    elif funding < -0.02:
        score += 2
        if not direction:
            direction = "LONG"
        reasons.append(f"Extreme short funding ({funding:+.4f}%)")

    # Filter: BTC Correlation
    mtf = state.get("mtf", {})
    mtf_5m = mtf.get("5m", {})
    eth_buy_pct = mtf_5m.get("buy_pct", 50)
    eth_change = (eth_buy_pct - 50) / 50 * 0.5
    btc_ctx = btc_corr.get_btc_context(eth_change)

    if direction == "LONG" and btc_ctx.get("btc_change_5m", 0) > 0.1:
        score += 1
        reasons.append(f"BTC confirming ({btc_ctx['btc_change_5m']:+.2f}%)")
    elif direction == "SHORT" and btc_ctx.get("btc_change_5m", 0) < -0.1:
        score += 1
        reasons.append(f"BTC confirming ({btc_ctx['btc_change_5m']:+.2f}%)")
    elif direction and ((direction == "LONG" and btc_ctx.get("btc_change_5m", 0) < -0.3) or
                        (direction == "SHORT" and btc_ctx.get("btc_change_5m", 0) > 0.3)):
        score -= 2
        reasons.append(f"⚠️ BTC diverges ({btc_ctx['btc_change_5m']:+.2f}%)")

    # Filter: Session
    session_info = session_filter.get_session()
    session_quality = session_info.get("quality_raw", "medium")
    if session_quality == "high":
        score += 1
        reasons.append("US session (high quality)")
    elif session_quality == "low":
        score -= 1
        reasons.append(f"{session_info.get('session', '?')} session (low quality)")

    # ═══════════════════════════════════════════════════════════
    # BUILD SIGNAL (if score >= 6 and cooldown passed)
    # ═══════════════════════════════════════════════════════════
    signal = None
    now = time_mod.time()

    if direction and score >= 6 and (now - _last_signal_time > SIGNAL_COOLDOWN):
        # Build base signal
        base_signal = {
            "time": now,
            "direction": direction,
            "score": score,
            "reasons": reasons,
        }

        # ═══ REAL-TIME ENHANCEMENT (additive only) ═══
        # Check if real-time data suggests skipping
        if enhancer.should_skip(base_signal, state):
            signal = None
            stage = "🛑 REALTIME SKIP — OI/crowd contradiction"
        else:
            # Enhance signal with real-time data
            enhanced = enhancer.evaluate_signal(base_signal, state)
            final_score = enhanced.get("score", score)
            final_reasons = enhanced.get("reasons", reasons)

            levels = atr.get_levels(price, direction, sl_mult=1.5, tp_mult=2.5)
            if levels and levels["rr"] >= 1.5:
                signal = {
                    "time": now,
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
                    "trail_distance": round(atr.get_trail_distance(1.0), 2),
                    "score": final_score,
                    "reasons": final_reasons,
                    "realtime_boost": enhanced.get("confidence_boost", 0),
                }
                _last_signal_time = now

    # Build stage text
    if not direction:
        stage = "⏳ WAITING — no signal"
    elif score < 6:
        stage = f"🔍 WEAK — score {score}/6 needed"
    elif signal:
        stage = "🟢 SIGNAL READY"
    else:
        stage = "⏳ COOLDOWN"

    # Package everything for dashboard
    state["signal"] = {
        "stage": stage,
        "direction": direction,
        "score": score,
        "ready": signal is not None,
        "signal": signal,
    }

    # Wyckoff state
    state["wyckoff"] = wyckoff.get_state()

    # Liquidity sweep state
    state["sweep"] = sweep_detector.get_state()

    # Liquidation heatmap
    state["liquidation"] = liq_heatmap.get_state()

    # BTC context
    state["btc"] = btc_corr.get_state()

    # Session
    state["session"] = session_info

    # ATR
    state["atr"] = atr.get_state()

    # Real-time enhancer
    state["realtime"] = enhancer.get_state()

    # Trade status
    if trade_mgr:
        state["trade_status"] = trade_mgr.get_formatted_status()
        if trade_mgr.auto_trade and signal:
            has_position = any(
                pos["symbol"] == trade_mgr.executor.symbol
                for pos in trade_mgr.executor.get_positions()
            )
            if not has_position:
                trade_mgr.process_signal({"ready": True, "signal": signal})

    enhanced_state = state
    return state


@app.route("/")
def index():
    return render_template("live.html")


@app.route("/api/snapshot")
def api_snapshot():
    if enhanced_state:
        return jsonify(enhanced_state)
    snap = engine.get_snapshot()
    snap["_engine_ready"] = _engine_ready
    return jsonify(snap)


@app.route("/api/trade/status")
def api_trade_status():
    if trade_mgr:
        return jsonify(trade_mgr.get_formatted_status())
    return jsonify({"error": "Not connected"})


@app.route("/api/trade/open", methods=["POST"])
def api_trade_open():
    if not trade_mgr:
        return jsonify({"error": "Not connected"}), 400
    data = request.json or {}
    direction = data.get("direction", "LONG")
    sl = data.get("sl", 0)
    tp = data.get("tp", 0)
    usdt = data.get("usdt", trade_mgr.usdt_per_trade)
    result = trade_mgr.executor.execute_signal(direction, sl, tp, usdt)
    if result.get("success") and sl and tp:
        trade_mgr.register_manual_stop(direction, sl, tp, data.get("entry", 0))
    return jsonify(result)


@app.route("/api/trade/close", methods=["POST"])
def api_trade_close():
    if not trade_mgr:
        return jsonify({"error": "Not connected"}), 400
    data = request.json or {}
    direction = data.get("direction")
    result = trade_mgr.close_position(direction)
    return jsonify(result)


@app.route("/api/trade/close-all", methods=["POST"])
def api_trade_close_all():
    if not trade_mgr:
        return jsonify({"error": "Not connected"}), 400
    result = trade_mgr.close_position()
    return jsonify(result)


@app.route("/api/trade/auto", methods=["POST"])
def api_trade_auto():
    if not trade_mgr:
        return jsonify({"error": "Not connected"}), 400
    data = request.json or {}
    enabled = data.get("enabled", not trade_mgr.auto_trade)
    trade_mgr.toggle_auto_trade(enabled)
    return jsonify({"auto_trade": trade_mgr.auto_trade})


@app.route("/api/trade/leverage", methods=["POST"])
def api_trade_leverage():
    if not trade_mgr:
        return jsonify({"error": "Not connected"}), 400
    data = request.json or {}
    lev = data.get("leverage", 5)
    trade_mgr.set_leverage(lev)
    return jsonify({"leverage": lev})


@app.route("/api/trade/amount", methods=["POST"])
def api_trade_amount():
    if not trade_mgr:
        return jsonify({"error": "Not connected"}), 400
    data = request.json or {}
    usdt = data.get("usdt", 100)
    trade_mgr.set_amount(usdt)
    return jsonify({"usdt_per_trade": usdt})


@app.route("/api/export")
def api_export():
    data = {
        "exported_at": datetime.now().isoformat(),
        "trade_log": [],
        "paper_signals": [],
        "stats": {},
    }
    try:
        with open("data/trades/trade_log.json") as f:
            data["trade_log"] = json.load(f)
    except:
        pass
    try:
        with open("data/paper_trades/signals.jsonl") as f:
            data["paper_signals"] = [json.loads(l) for l in f if l.strip()]
    except:
        pass
    if trade_mgr:
        data["stats"] = trade_mgr.get_formatted_status()
    return jsonify(data)


@sock.route("/ws")
def ws_handler(ws):
    loop = asyncio.new_event_loop()

    async def send_updates():
        while True:
            try:
                snap = dict(enhanced_state) if enhanced_state else engine.get_snapshot()
                ws.send(json.dumps(snap))
                await asyncio.sleep(0.5)
            except:
                break

    loop.run_until_complete(send_updates())


def start_engine():
    global _engine_ready
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_all():
        global _engine_ready
        engine.on_update(lambda s: enhance_state(s))

        async def liq_loop():
            session = aiohttp.ClientSession()
            try:
                await liq_heatmap.start(session)
            finally:
                await session.close()

        _engine_ready = True
        print("[ENGINE] Ready")
        await asyncio.gather(engine.start(), liq_loop(), btc_corr.start(), enhancer.start(aiohttp.ClientSession()))

    try:
        loop.run_until_complete(run_all())
    except Exception as e:
        print(f"[ENGINE] Fatal error: {e}")
        _engine_ready = False


if __name__ == "__main__":
    import threading

    print("=" * 60)
    print("SMART MONEY — MARKET MECHANICS v5")
    print("=" * 60)
    print("Signals (proven in backtest):")
    print("  ✅ Liquidity sweep (stop hunt + reversal)")
    print("  ✅ Wyckoff spring/upthrust (false breakouts)")
    print("  ✅ Funding extreme (crowd is wrong)")
    print("  ✅ ATR-based SL/TP")
    print("  ✅ BTC correlation filter")
    print("  ✅ Session filter")
    print(f"  {'✅' if trade_mgr else '❌'} Trade executor")
    print("Starting...")

    engine_thread = threading.Thread(target=start_engine, daemon=True)
    engine_thread.start()

    port = int(os.environ.get("PORT", 8888))
    print(f"\nDashboard: http://localhost:{port}")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
