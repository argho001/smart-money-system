"""
Smart Money System - Live Dashboard Server v3
All engines integrated: CVD, OI Delta, Liquidation Clusters, VPIN, Cross-exchange OI.
"""
import asyncio
import json
import os
import sys
import time as time_mod
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, render_template, jsonify
from flask_sock import Sock
from modules.live.live_engine import LiveDataEngine
from modules.live.anomaly_detector import AnomalyDetector
from modules.live.outcome_tracker import OutcomeTracker
from modules.live.entry_exit_engine import EntryExitEngine
from modules.live.signal_pipeline import SignalPipeline
from modules.live.signal_pipeline_v2 import SignalPipelineV2
from modules.live.cvd_engine import CVDEngine
from modules.live.oi_delta import OIDeltaTracker
from modules.live.liquidation_clusters import LiquidationClusters
from modules.live.vpin_engine import VpineEngine
from modules.live.cross_exchange_oi import CrossExchangeOI

app = Flask(__name__)
sock = Sock(app)

# All engines
engine = LiveDataEngine()
anomaly = AnomalyDetector()
outcome = OutcomeTracker()
entry_exit = EntryExitEngine()
pipeline = SignalPipeline()
pipeline_v2 = SignalPipelineV2()
cvd = CVDEngine()
oi_delta = OIDeltaTracker()
liq_clusters = LiquidationClusters()
vpin = VpineEngine()
cross_oi = CrossExchangeOI()

enhanced_state = {}
_oi_fetch_counter = 0


def enhance_state(state):
    """Add all enhanced data to state"""
    global enhanced_state, _oi_fetch_counter

    # CVD — update from trade buffer
    trades = list(engine._last_trades)[-100:]  # Last 100 trades
    cvd.update(trades)
    state["cvd"] = cvd.get_state()

    # Liquidation clusters — update from order book
    bids = []
    asks = []
    # Reconstruct order book from state
    for l in state.get("support_levels", []):
        bids.append([str(l["price"]), str(l.get("strength", 1))])
    for l in state.get("resistance_levels", []):
        asks.append([str(l["price"]), str(l.get("strength", 1))])
    liq_clusters.update(state.get("price", 0), bids, asks, state.get("funding_rate", 0))
    state["liq_clusters"] = liq_clusters.get_state(state.get("price", 0))

    # VPIN — update from trades
    vpin.update(trades)
    state["vpin"] = vpin.get_state()

    # Anomaly detection
    alerts = anomaly.update(state)
    state["anomaly_alerts"] = [
        {"severity": a["severity"], "label": a["label"], "current": a["current"],
         "z_score": a["z_score"], "direction": a["direction"]}
        for a in alerts
    ]

    # Outcome tracking
    outcome.log_state(state)
    outcome.check_outcomes(state.get("price", 0))
    outlook = outcome.get_current_setup_outlook(state)
    state["setup_outlook"] = outlook

    # Entry/Exit signal
    signal = entry_exit.evaluate(state, outlook)
    if signal:
        state["trade_signal"] = signal
    elif entry_exit.last_signal and time_mod.time() - entry_exit.last_signal_time < 600:
        state["trade_signal"] = entry_exit.last_signal
    else:
        state["trade_signal"] = None

    # Signal Pipeline (v1 for backward compat)
    state["pipeline"] = pipeline.evaluate(state)

    # Signal Pipeline v2 (proven signals only)
    # We need candle data — fetch from engine's cached data
    try:
        import json, os
        candle_file = "data/candles/ETHUSDT_1m_90d.json"
        c1m = []
        if os.path.exists(candle_file):
            with open(candle_file) as f:
                raw = json.load(f)
                c1m = [{"close": c["close"], "high": c["high"], "low": c["low"], "volume": c["volume"]} for c in raw[-3600:]]

        candle_file_5m = "data/candles/ETHUSDT_5m_90d.json"
        c5m = []
        if os.path.exists(candle_file_5m):
            with open(candle_file_5m) as f:
                raw = json.load(f)
                c5m = [{"close": c["close"], "high": c["high"], "low": c["low"], "volume": c["volume"]} for c in raw[-200:]]

        candle_file_15m = "data/candles/ETHUSDT_15m_90d.json"
        c15m = []
        if os.path.exists(candle_file_15m):
            with open(candle_file_15m) as f:
                raw = json.load(f)
                c15m = [{"close": c["close"], "high": c["high"], "low": c["low"], "volume": c["volume"]} for c in raw[-200:]]

        candle_file_1h = "data/candles/ETHUSDT_1h_90d.json"
        c1h = []
        if os.path.exists(candle_file_1h):
            with open(candle_file_1h) as f:
                raw = json.load(f)
                c1h = [{"close": c["close"], "high": c["high"], "low": c["low"], "volume": c["volume"]} for c in raw[-200:]]

        if c1m:
            state["pipeline_v2"] = pipeline_v2.evaluate(c1m, c5m, c15m, c1h)
        else:
            state["pipeline_v2"] = pipeline_v2._empty("No candle data")
    except Exception as e:
        state["pipeline_v2"] = pipeline_v2._empty(str(e))

    enhanced_state = state
    return state


@app.route("/")
def index():
    return render_template("live.html")


@app.route("/api/snapshot")
def api_snapshot():
    return jsonify(enhanced_state or engine.get_snapshot())


@app.route("/api/alerts")
def api_alerts():
    return jsonify(anomaly.get_recent_alerts(20))


@app.route("/api/outcomes")
def api_outcomes():
    return jsonify(outcome.get_setup_stats())


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
    """Start all engines"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_all():
        # Start main engine with enhancement callback
        engine.on_update(lambda s: enhance_state(s))

        # Start OI and cross-exchange polling in parallel
        async def oi_loop():
            global _oi_fetch_counter
            session = __import__("aiohttp").ClientSession()
            while True:
                try:
                    await oi_delta.fetch(session)
                    await cross_oi.fetch(session)

                    # Merge OI data into enhanced state
                    oi_state = oi_delta.get_signal(enhanced_state.get("price", 0))
                    enhanced_state["oi_delta"] = oi_state
                    enhanced_state["cross_oi"] = cross_oi.get_state()
                except:
                    pass
                await asyncio.sleep(5)

        # Run both
        await asyncio.gather(
            engine.start(),
            oi_loop(),
        )

    loop.run_until_complete(run_all())


if __name__ == "__main__":
    import threading

    print("=" * 60)
    print("SMART MONEY — LIVE TERMINAL v3")
    print("=" * 60)
    print("Components:")
    print("  ✅ Live data engine")
    print("  ✅ CVD (Cumulative Volume Delta)")
    print("  ✅ OI Delta tracker")
    print("  ✅ Liquidation clusters")
    print("  ✅ VPIN (toxic flow)")
    print("  ✅ Cross-exchange OI rotation")
    print("  ✅ Anomaly detector")
    print("  ✅ Outcome tracker")
    print("  ✅ Entry/exit engine")
    print("Starting...")

    engine_thread = threading.Thread(target=start_engine, daemon=True)
    engine_thread.start()

    time_mod.sleep(3)
    print(f"\nDashboard: http://localhost:8888")
    print("=" * 60)

    app.run(host="0.0.0.0", port=8888, debug=False, threaded=True)
