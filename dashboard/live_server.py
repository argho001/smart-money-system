"""
Smart Money System - Live Dashboard Server v4
Trading terminal: signals + execution + tracking
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
from modules.live.live_engine import LiveDataEngine
from modules.live.anomaly_detector import AnomalyDetector
from modules.live.outcome_tracker import OutcomeTracker
from modules.live.entry_exit_engine import EntryExitEngine
from modules.live.signal_pipeline import SignalPipeline
from modules.live.contrarian_pipeline import ContrarianPipeline
from modules.live.atr_engine import ATREngine
from modules.live.cvd_engine import CVDEngine
from modules.live.oi_delta import OIDeltaTracker
from modules.live.liquidation_clusters import LiquidationClusters
from modules.live.vpin_engine import VpineEngine
from modules.live.cross_exchange_oi import CrossExchangeOI

app = Flask(__name__)
sock = Sock(app)

# Core engines
engine = LiveDataEngine()
anomaly = AnomalyDetector()
outcome = OutcomeTracker()
entry_exit = EntryExitEngine()
pipeline = SignalPipeline()
contrarian = ContrarianPipeline()
atr = ATREngine(period=14)
cvd = CVDEngine()
oi_delta = OIDeltaTracker()
liq_clusters = LiquidationClusters()
vpin = VpineEngine()
cross_oi = CrossExchangeOI()

# Trade Manager
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
_oi_fetch_counter = 0
_engine_ready = False


def enhance_state(state):
    global enhanced_state, _oi_fetch_counter

    # Update ATR with current price
    price = state.get("price", 0)
    if price > 0:
        atr.update(price)

    # CVD
    trades = list(engine._last_trades)[-100:]
    cvd.update(trades)
    state["cvd"] = cvd.get_state()

    # Liquidation clusters
    bids, asks = [], []
    for l in state.get("support_levels", []):
        bids.append([str(l["price"]), str(l.get("strength", 1))])
    for l in state.get("resistance_levels", []):
        asks.append([str(l["price"]), str(l.get("strength", 1))])
    liq_clusters.update(state.get("price", 0), bids, asks, state.get("funding_rate", 0))
    state["liq_clusters"] = liq_clusters.get_state(state.get("price", 0))

    # VPIN
    vpin.update(trades)
    state["vpin"] = vpin.get_state()

    # Anomaly
    alerts = anomaly.update(state)
    state["anomaly_alerts"] = [
        {"severity": a["severity"], "label": a["label"], "current": a["current"],
         "z_score": a["z_score"], "direction": a["direction"]} for a in alerts
    ]

    # Outcome
    outcome.log_state(state)
    outcome.check_outcomes(state.get("price", 0))
    outlook = outcome.get_current_setup_outlook(state)
    state["setup_outlook"] = outlook

    # Entry/Exit
    signal = entry_exit.evaluate(state, outlook)
    if signal:
        state["trade_signal"] = signal
    elif entry_exit.last_signal and time_mod.time() - entry_exit.last_signal_time < 600:
        state["trade_signal"] = entry_exit.last_signal
    else:
        state["trade_signal"] = None

    # Pipeline v3 (legacy — still available)
    state["pipeline"] = pipeline.evaluate(state)

    # Contrarian Pipeline v4 (new — primary signal)
    state["contrarian"] = contrarian.evaluate(state, atr)

    # ATR state
    state["atr"] = atr.get_state()

    # Trade status
    if trade_mgr:
        state["trade_status"] = trade_mgr.get_formatted_status()
        # Auto-execute with CONTRARIAN signals (not legacy pipeline)
        contrarian_signal = state.get("contrarian", {})
        if trade_mgr.auto_trade and contrarian_signal.get("ready"):
            # Check if there's already an open position
            has_position = False
            for pos in trade_mgr.executor.get_positions():
                if pos["symbol"] == trade_mgr.executor.symbol:
                    has_position = True
                    break
            if not has_position:
                trade_mgr.process_signal(contrarian_signal)
            else:
                pass

    enhanced_state = state
    return state


@app.route("/")
def index():
    return render_template("live.html")


@app.route("/api/snapshot")
def api_snapshot():
    # Always return 200 for Railway healthcheck, even if engine isn't ready
    if enhanced_state:
        return jsonify(enhanced_state)
    # Return default snapshot so healthcheck passes
    snap = engine.get_snapshot()
    snap["_engine_ready"] = _engine_ready
    return jsonify(snap)


@app.route("/api/alerts")
def api_alerts():
    return jsonify(anomaly.get_recent_alerts(20))


@app.route("/api/outcomes")
def api_outcomes():
    return jsonify(outcome.get_setup_stats())


# ═══════════════════════════════════════════
# TRADE API
# ═══════════════════════════════════════════

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
        # Register SL/TP for monitoring
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

        async def oi_loop():
            global _oi_fetch_counter
            session = aiohttp.ClientSession()
            try:
                while True:
                    try:
                        await oi_delta.fetch(session)
                        await cross_oi.fetch(session)
                        oi_state = oi_delta.get_signal(enhanced_state.get("price", 0))
                        enhanced_state["oi_delta"] = oi_state
                        enhanced_state["cross_oi"] = cross_oi.get_state()
                    except Exception as e:
                        print(f"[OI] Error: {e}")
                    await asyncio.sleep(5)
            finally:
                await session.close()

        _engine_ready = True
        print("[ENGINE] Ready")
        await asyncio.gather(engine.start(), oi_loop())

    try:
        loop.run_until_complete(run_all())
    except Exception as e:
        print(f"[ENGINE] Fatal error: {e}")
        _engine_ready = False




@app.route("/api/export")
def api_export():
    """Export all trade data for analysis."""
    import os
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
if __name__ == "__main__":
    import threading

    print("=" * 60)
    print("SMART MONEY — LIVE TERMINAL v4")
    print("=" * 60)
    print("Components:")
    print("  ✅ Live data engine")
    print("  ✅ CVD (Cumulative Volume Delta)")
    print("  ✅ OI Delta tracker")
    print("  ✅ Liquidation clusters")
    print("  ✅ Cross-exchange OI rotation")
    print("  ✅ Anomaly detector")
    print("  ✅ Signal Pipeline v3 (5 checkpoints)")
    print(f"  {'✅' if trade_mgr else '❌'} Trade executor {'(' + str(trade_mgr.leverage) + 'x leverage)' if trade_mgr else ''}")
    print(f"  {'✅' if trade_mgr else '❌'} Auto-trade {'ON' if trade_mgr and trade_mgr.auto_trade else 'OFF'}")
    print("Starting...")

    engine_thread = threading.Thread(target=start_engine, daemon=True)
    engine_thread.start()

    print(f"\nDashboard: http://localhost:{os.environ.get('PORT', 8888)}")
    print("=" * 60)

    # Railway sets PORT env var — use it, fallback to 8888
    port = int(os.environ.get("PORT", 8888))
    print(f"Listening on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)



