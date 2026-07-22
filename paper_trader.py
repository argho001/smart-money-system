"""
Paper Trading Signal Logger
Captures live signals every 5 minutes and tracks outcomes.
After 100+ trades, we calculate REAL expectancy from actual data.
"""

import json
import os
import time
import requests
from datetime import datetime

DATA_DIR = "data/paper_trades"
SNAPSHOT_URL = "http://127.0.0.1:8888/api/snapshot"
CHECK_INTERVAL = 300  # 5 minutes
OUTCOME_CHECK_DELAY = 3600  # check outcome after 1 hour

os.makedirs(DATA_DIR, exist_ok=True)

TRADES_FILE = os.path.join(DATA_DIR, "trades.jsonl")
SIGNALS_FILE = os.path.join(DATA_DIR, "signals.jsonl")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")


def get_snapshot():
    try:
        r = requests.get(SNAPSHOT_URL, timeout=10)
        return r.json()
    except:
        return None


def extract_signal(snapshot):
    """Extract actionable signal from snapshot."""
    if not snapshot:
        return None

    price = snapshot.get("price", 0)
    if price <= 0:
        return None

    signals = {
        "timestamp": datetime.now().isoformat(),
        "price": price,
        "cvd_trend": snapshot.get("cvd", {}).get("cvd_trend", ""),
        "cvd_value": snapshot.get("cvd", {}).get("cvd", 0),
        "funding_rate": snapshot.get("funding_rate", 0),
        "funding_signal": snapshot.get("funding_signal", ""),
        "imbalance": snapshot.get("imbalance", 0),
        "buying_pressure": snapshot.get("buying_pressure", 0),
        "composite": snapshot.get("composite", 0),
        "large_net": snapshot.get("large_net", 0),
        "large_trade_side": snapshot.get("large_trade_side", ""),
        "accel_signal": snapshot.get("accel_signal", ""),
        "bid_pct": snapshot.get("bid_pct", 50),
        "oi_total": snapshot.get("cross_oi", {}).get("oi_total", 0),
        "anomaly_alerts": len(snapshot.get("anomaly_alerts", [])),
        "pipeline": snapshot.get("pipeline", {}),
    }

    return signals


def determine_direction(signals):
    """Determine trade direction from multiple signals."""
    long_score = 0
    short_score = 0

    # CVD
    if "BUYING" in signals.get("cvd_trend", ""):
        long_score += 2
    elif "SELLING" in signals.get("cvd_trend", ""):
        short_score += 2

    # Composite
    comp = signals.get("composite", 0)
    if comp > 10:
        long_score += 1
    elif comp < -10:
        short_score += 1

    # Large trades
    if signals.get("large_net", 0) > 5:
        long_score += 1
    elif signals.get("large_net", 0) < -5:
        short_score += 1

    # Buying pressure
    bp = signals.get("buying_pressure", 0)
    if bp > 5:
        long_score += 1
    elif bp < -5:
        short_score += 1

    # Imbalance
    imb = signals.get("imbalance", 0)
    if imb > 5:
        long_score += 1
    elif imb < -5:
        short_score += 1

    # Acceleration
    accel = signals.get("accel_signal", "")
    if "buying" in accel.lower():
        long_score += 1
    elif "selling" in accel.lower():
        short_score += 1

    # Need at least 3 agreeing signals
    if long_score >= 3 and long_score > short_score:
        return "LONG", long_score
    elif short_score >= 3 and short_score > long_score:
        return "SHORT", short_score
    else:
        return None, 0


def log_signal(signals, direction, confidence):
    """Log a signal to file."""
    entry = {
        **signals,
        "direction": direction,
        "confidence": confidence,
        "entry_price": signals["price"],
        "sl_pct": 2.0,
        "tp_pct": 6.0,  # 1:3 R:R
    }

    with open(SIGNALS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return entry


def check_outcomes():
    """Check outcomes of pending trades."""
    if not os.path.exists(SIGNALS_FILE):
        return

    # Load current price
    snap = get_snapshot()
    if not snap:
        return
    current_price = snap.get("price", 0)
    if current_price <= 0:
        return

    # Load trades file
    trades = []
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE) as f:
            trades = [json.loads(l) for l in f.readlines() if l.strip()]

    # Load pending signals
    with open(SIGNALS_FILE) as f:
        signals = [json.loads(l) for l in f.readlines() if l.strip()]

    completed_trade_ids = {t.get("signal_timestamp") for t in trades}

    for sig in signals:
        ts = sig.get("timestamp")
        if ts in completed_trade_ids:
            continue

        entry_price = sig.get("entry_price", 0)
        direction = sig.get("direction")
        if entry_price <= 0 or not direction:
            continue

        # Check if enough time has passed
        sig_time = datetime.fromisoformat(ts)
        elapsed = (datetime.now() - sig_time).total_seconds()
        if elapsed < OUTCOME_CHECK_DELAY:
            continue

        # Calculate outcome
        sl_pct = sig.get("sl_pct", 2.0)
        tp_pct = sig.get("tp_pct", 6.0)

        if direction == "LONG":
            pnl_pct = (current_price - entry_price) / entry_price * 100
            sl_price = entry_price * (1 - sl_pct / 100)
            tp_price = entry_price * (1 + tp_pct / 100)
            if current_price <= sl_price:
                result = "LOSS"
                exit_price = sl_price
            elif current_price >= tp_price:
                result = "WIN"
                exit_price = tp_price
            else:
                result = "OPEN"
                exit_price = current_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price * 100
            sl_price = entry_price * (1 + sl_pct / 100)
            tp_price = entry_price * (1 - tp_pct / 100)
            if current_price >= sl_price:
                result = "LOSS"
                exit_price = sl_price
            elif current_price <= tp_price:
                result = "WIN"
                exit_price = tp_price
            else:
                result = "OPEN"
                exit_price = current_price

        if result != "OPEN":
            trade = {
                "signal_timestamp": ts,
                "direction": direction,
                "confidence": sig.get("confidence", 0),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl_pct": round(pnl_pct, 3),
                "result": result,
                "signals": {
                    "cvd": sig.get("cvd_trend", ""),
                    "composite": sig.get("composite", 0),
                    "large_net": sig.get("large_net", 0),
                    "imbalance": sig.get("imbalance", 0),
                },
            }
            trades.append(trade)
            print(f"[TRADE] {result}: {direction} @ {entry_price:.2f} -> {exit_price:.2f} ({pnl_pct:+.2f}%)")

    # Save trades
    with open(TRADES_FILE, "w") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")

    # Update stats
    if trades:
        total = len(trades)
        wins = sum(1 for t in trades if t["result"] == "WIN")
        losses = total - wins
        win_rate = wins / total * 100
        avg_pnl = sum(t["pnl_pct"] for t in trades) / total
        gross_win = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
        gross_loss = abs(sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0))
        pf = gross_win / gross_loss if gross_loss > 0 else 99

        stats = {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "avg_pnl": round(avg_pnl, 3),
            "profit_factor": round(pf, 2),
            "expectancy_per_trade": round(avg_pnl, 3),
            "last_updated": datetime.now().isoformat(),
        }

        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2)

        print(f"\n[STATS] {total} trades | WR: {win_rate:.1f}% | PF: {pf:.2f} | Exp: {avg_pnl:+.3f}%/trade")


def run():
    print("=" * 60)
    print("PAPER TRADING SIGNAL LOGGER")
    print("=" * 60)
    print(f"Checking every {CHECK_INTERVAL}s")
    print(f"Outcome delay: {OUTCOME_CHECK_DELAY}s")
    print(f"Signals: {SIGNALS_FILE}")
    print(f"Trades: {TRADES_FILE}")
    print()

    while True:
        try:
            # Get live snapshot
            snap = get_snapshot()
            if not snap:
                print("[WARN] No snapshot, retrying in 30s...")
                time.sleep(30)
                continue

            # Extract signal
            signals = extract_signal(snap)
            if not signals:
                print("[WARN] No valid signal, retrying in 30s...")
                time.sleep(30)
                continue

            # Determine direction
            direction, confidence = determine_direction(signals)

            if direction:
                entry = log_signal(signals, direction, confidence)
                print(f"[SIGNAL] {direction} (conf: {confidence}) @ ${signals['price']:.2f}")
                print(f"  CVD: {signals['cvd_trend']}")
                print(f"  Composite: {signals['composite']:.1f}")
                print(f"  Large net: {signals['large_net']:.1f}")
                print(f"  Imbalance: {signals['imbalance']:.1f}")
            else:
                print(f"[NO SIGNAL] @ ${signals['price']:.2f} — no consensus")

            # Check outcomes of previous trades
            check_outcomes()

        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run()
