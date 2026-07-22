"""
Trade Manager
Connects signal pipeline → Binance executor
Auto-executes trades, tracks positions, calculates P&L
"""

import json
import os
import time
import threading
from datetime import datetime
from modules.live.binance_executor import BinanceExecutor


class TradeManager:
    def __init__(self, api_key, api_secret, base_url, config=None):
        self.executor = BinanceExecutor(api_key, api_secret, base_url)
        self.config = config or {}
        self.usdt_per_trade = self.config.get("usdt_per_trade", 100)
        self.leverage = self.config.get("leverage", 5)
        self.auto_trade = self.config.get("auto_trade", False)
        self.cooldown = self.config.get("cooldown", 300)  # 5 min

        self.last_trade_time = 0
        self.trade_log = []
        self.stats = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0,
            "open_positions": 0,
        }

        # Active SL/TP tracking
        self.active_stops = {}  # {direction: {"sl": price, "tp": price, "entry": price}}

        # Setup
        self.executor.leverage = self.leverage
        self.executor.set_leverage()
        self.executor.set_margin_type("CROSSED")

        # Start monitor thread
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._monitor_positions, daemon=True)
        self._monitor_thread.start()
        print("[TRADE_MGR] SL/TP monitor started")

        # Load trade history
        self._load_history()

    def _load_history(self):
        """Start fresh — count from now, not from old Binance history."""
        self.stats = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0,
            "open_positions": 0,
        }

    def process_signal(self, pipeline_result):
        """
        Process a signal from the pipeline.
        RULE: Can only open when NO position exists.
        Once in a trade → ignore all signals until SL/TP resolves.
        """
        if not pipeline_result or not pipeline_result.get("ready"):
            return None

        signal = pipeline_result.get("signal")
        if not signal:
            return None

        direction = signal.get("direction")
        sl = signal.get("stop_loss")
        tp = signal.get("target")
        entry = signal.get("entry", 0)

        if not all([direction, sl, tp, entry]):
            return None

        # === CHECK: Is there already an open position? ===
        # If YES → do nothing. Let SL/TP decide.
        positions = self.executor.get_positions()
        for pos in positions:
            if pos["symbol"] == self.executor.symbol:
                return {
                    "status": "blocked",
                    "message": f"Already in {pos['side']} position. Waiting for SL/TP.",
                    "open_position": pos["side"],
                }

        # Check cooldown
        now = time.time()
        if now - self.last_trade_time < self.cooldown:
            return {"status": "cooldown", "message": "Too soon since last trade"}

        # === RISK-BASED POSITION SIZING ===
        balance_info = self.executor.get_balance()
        balance = balance_info.get("available", 1000)
        risk_pct = self.config.get("risk_pct", 2.0)
        risk_amount = balance * (risk_pct / 100)
        sl_distance_pct = abs(entry - sl) / entry
        usdt_amount = risk_amount / sl_distance_pct / self.leverage if sl_distance_pct > 0 else self.usdt_per_trade
        usdt_amount = min(usdt_amount, balance * 0.9)
        usdt_amount = max(usdt_amount, 10)

        trade_info = {
            "signal": signal,
            "direction": direction,
            "sl": sl,
            "tp": tp,
            "entry": entry,
            "rr": signal.get("rr"),
            "score": signal.get("score"),
            "reasons": signal.get("reasons", []),
            "time": datetime.now().isoformat(),
            "auto_executed": False,
            "risk_pct": risk_pct,
            "risk_amount": round(risk_amount, 2),
            "usdt_amount": round(usdt_amount, 2),
        }

        if self.auto_trade:
            # Execute
            result = self.executor.execute_signal(direction, sl, tp, usdt_amount)
            trade_info["execution"] = result
            trade_info["auto_executed"] = result.get("success", False)
            self.last_trade_time = now

            if result.get("success"):
                self.stats["total_trades"] += 1
                self.stats["open_positions"] += 1
                # Register SL/TP for monitoring with trailing stop
                trail_dist = signal.get("trail_distance", 0)
                self._register_stop(direction, sl, tp, entry, trail_distance=trail_dist)
                print(f"[TRADE] OPENED {direction} @ ${entry:.2f} | SL ${sl:.2f} | TP ${tp:.2f} | ${usdt_amount:.0f} margin")

        self.trade_log.append(trade_info)
        self._save_log()
        return trade_info

    def close_position(self, direction=None):
        """Close position(s) and update stats."""
        if direction:
            positions = self.executor.get_positions()
            for pos in positions:
                if pos["symbol"] == self.executor.symbol and pos["side"] == direction:
                    entry = pos["entry_price"]
                    current = pos["mark_price"]
                    result = self.executor.close_position(direction)
                    # Update stats
                    if direction == "LONG":
                        pnl_pct = (current - entry) / entry * 100
                    else:
                        pnl_pct = (entry - current) / entry * 100
                    self.stats["total_trades"] += 1
                    if pnl_pct > 0:
                        self.stats["wins"] += 1
                    else:
                        self.stats["losses"] += 1
                    self.stats["open_positions"] = max(0, self.stats["open_positions"] - 1)
                    self._remove_stop(direction)
                    # Log
                    self.trade_log.append({
                        "time": datetime.now().isoformat(),
                        "direction": direction,
                        "entry": entry,
                        "exit": current,
                        "result": "WIN" if pnl_pct > 0 else "LOSS",
                        "pnl_pct": round(pnl_pct, 3),
                        "auto_executed": False,
                        "manual_close": True,
                    })
                    self._save_log()
                    return result
            return {"error": "No position found"}
        else:
            # Close all
            results = []
            positions = self.executor.get_positions()
            for pos in positions:
                if pos["symbol"] == self.executor.symbol:
                    entry = pos["entry_price"]
                    current = pos["mark_price"]
                    d = pos["side"]
                    result = self.executor.close_position(d)
                    if d == "LONG":
                        pnl_pct = (current - entry) / entry * 100
                    else:
                        pnl_pct = (entry - current) / entry * 100
                    self.stats["total_trades"] += 1
                    if pnl_pct > 0:
                        self.stats["wins"] += 1
                    else:
                        self.stats["losses"] += 1
                    self._remove_stop(d)
                    self.trade_log.append({
                        "time": datetime.now().isoformat(),
                        "direction": d,
                        "entry": entry,
                        "exit": current,
                        "result": "WIN" if pnl_pct > 0 else "LOSS",
                        "pnl_pct": round(pnl_pct, 3),
                        "auto_executed": False,
                        "manual_close": True,
                    })
                    results.append(result)
            self.stats["open_positions"] = 0
            self._save_log()
            return results

    def get_status(self):
        """Get full trading status."""
        # Refresh positions
        positions = self.executor.get_positions()
        balance = self.executor.get_balance()
        orders = self.executor.get_open_orders()

        # Update stats
        self.stats["open_positions"] = len([p for p in positions if p["symbol"] == self.executor.symbol])

        # Calculate unrealized P&L
        unrealized = sum(p["unrealized_pnl"] for p in positions if p["symbol"] == self.executor.symbol)

        return {
            "balance": balance,
            "positions": [p for p in positions if p["symbol"] == self.executor.symbol],
            "orders": [o for o in orders],
            "stats": self.stats,
            "unrealized_pnl": unrealized,
            "total_pnl": self.stats["total_pnl"] + unrealized,
            "leverage": self.leverage,
            "auto_trade": self.auto_trade,
            "usdt_per_trade": self.usdt_per_trade,
            "last_trade_time": self.last_trade_time,
            "recent_trades": self.trade_log[-10:],
        }

    def toggle_auto_trade(self, enabled=None):
        """Toggle auto-trading on/off."""
        if enabled is not None:
            self.auto_trade = enabled
        else:
            self.auto_trade = not self.auto_trade
        print(f"[TRADE_MGR] Auto-trade: {'ON' if self.auto_trade else 'OFF'}")
        return self.auto_trade

    def set_leverage(self, leverage):
        """Change leverage."""
        self.leverage = leverage
        self.executor.leverage = leverage
        self.executor.set_leverage()

    def set_amount(self, usdt):
        """Change USDT per trade."""
        self.usdt_per_trade = usdt
        print(f"[TRADE_MGR] USDT per trade: ${usdt}")

    def _save_log(self):
        """Save trade log to file."""
        os.makedirs("data/trades", exist_ok=True)
        with open("data/trades/trade_log.json", "w") as f:
            json.dump(self.trade_log, f, indent=2, default=str)

    def _register_stop(self, direction, sl, tp, entry, trail_distance=0):
        """Register SL/TP for monitoring. trail_distance > 0 enables trailing stop."""
        self.active_stops[direction] = {
            "sl": sl,
            "tp": tp,
            "entry": entry,
            "time": time.time(),
            "trail_distance": trail_distance,
            "trail_active": False,
            "best_price": entry,  # Track best price for trailing
            "original_sl": sl,
        }
        trail_str = f" | Trail: ${trail_distance:.2f}" if trail_distance else ""
        print(f"[MONITOR] Registered {direction} SL=${sl:.2f} TP=${tp:.2f}{trail_str}")

    def _remove_stop(self, direction):
        """Remove SL/TP tracking."""
        if direction in self.active_stops:
            del self.active_stops[direction]

    def _monitor_positions(self):
        """
        Background thread: monitors open positions and closes when SL/TP hit.
        Binance demo doesn't support stop orders, so we do it in software.
        """
        import requests as req
        print("[MONITOR] SL/TP monitor thread running")
        while self._monitor_running:
            try:
                if not self.active_stops:
                    time.sleep(1)
                    continue

                # Get current price
                try:
                    r = req.get(f"{self.executor.base_url}/fapi/v1/ticker/price",
                                params={"symbol": self.executor.symbol}, timeout=5)
                    if r.status_code == 200:
                        current_price = float(r.json()["price"])
                    else:
                        time.sleep(1)
                        continue
                except:
                    time.sleep(1)
                    continue

                # Check each tracked position
                to_close = []
                for direction, stop in list(self.active_stops.items()):
                    sl = stop["sl"]
                    tp = stop["tp"]
                    trail_dist = stop.get("trail_distance", 0)
                    trail_active = stop.get("trail_active", False)
                    best_price = stop.get("best_price", stop["entry"])

                    hit_sl = False
                    hit_tp = False

                    # Update best price for trailing
                    if direction == "LONG":
                        if current_price > best_price:
                            stop["best_price"] = current_price
                            best_price = current_price
                    else:
                        if current_price < best_price:
                            stop["best_price"] = current_price
                            best_price = current_price

                    # Activate trailing stop when 1R profit reached
                    if trail_dist > 0 and not trail_active:
                        entry = stop["entry"]
                        original_sl = stop.get("original_sl", sl)
                        risk = abs(entry - original_sl)
                        if direction == "LONG" and current_price >= entry + risk:
                            stop["trail_active"] = True
                            trail_active = True
                            new_sl = current_price - trail_dist
                            if new_sl > sl:
                                stop["sl"] = new_sl
                                sl = new_sl
                            print(f"[MONITOR] TRAILING activated for {direction} @ ${current_price:.2f} — new SL ${sl:.2f}")
                        elif direction == "SHORT" and current_price <= entry - risk:
                            stop["trail_active"] = True
                            trail_active = True
                            new_sl = current_price + trail_dist
                            if new_sl < sl:
                                stop["sl"] = new_sl
                                sl = new_sl
                            print(f"[MONITOR] TRAILING activated for {direction} @ ${current_price:.2f} — new SL ${sl:.2f}")

                    # Update trailing SL (move in profit direction)
                    if trail_active and trail_dist > 0:
                        if direction == "LONG":
                            new_sl = best_price - trail_dist
                            if new_sl > sl:
                                stop["sl"] = new_sl
                                sl = new_sl
                        else:
                            new_sl = best_price + trail_dist
                            if new_sl < sl:
                                stop["sl"] = new_sl
                                sl = new_sl

                    # Check SL/TP hits
                    if direction == "LONG":
                        if current_price <= sl:
                            hit_sl = True
                        elif current_price >= tp:
                            hit_tp = True
                    else:  # SHORT
                        if current_price >= sl:
                            hit_sl = True
                        elif current_price <= tp:
                            hit_tp = True

                    if hit_sl or hit_tp:
                        result_type = "SL" if hit_sl else "TP"
                        trail_note = " (trailing)" if trail_active and hit_sl else ""
                        print(f"[MONITOR] {result_type} HIT{trail_note} for {direction} @ ${current_price:.2f} (target was ${sl if hit_sl else tp:.2f})")
                        to_close.append((direction, result_type, current_price))

                # Close positions that hit SL/TP
                for direction, result_type, price in to_close:
                    close_result = self.executor.close_position(direction)
                    if isinstance(close_result, dict) and close_result.get("success"):
                        # Update stats
                        stop = self.active_stops.get(direction, {})
                        entry = stop.get("entry", price)
                        if direction == "LONG":
                            pnl_pct = (price - entry) / entry * 100
                        else:
                            pnl_pct = (entry - price) / entry * 100

                        if result_type == "TP":
                            self.stats["wins"] += 1
                        else:
                            self.stats["losses"] += 1

                        self.stats["open_positions"] = max(0, self.stats["open_positions"] - 1)

                        # Log the trade
                        log_entry = {
                            "time": datetime.now().isoformat(),
                            "direction": direction,
                            "entry": entry,
                            "exit": price,
                            "result": result_type,
                            "pnl_pct": round(pnl_pct, 3),
                            "auto_executed": True,
                        }
                        self.trade_log.append(log_entry)
                        self._save_log()
                        print(f"[MONITOR] Closed {direction} {result_type} @ ${price:.2f} PnL: {pnl_pct:+.2f}%")

                    self._remove_stop(direction)

            except Exception as e:
                print(f"[MONITOR] Error: {e}")

            time.sleep(1)  # Check every 1 second

    def register_manual_stop(self, direction, sl, tp, entry, trail_distance=0):
        """Register SL/TP for manually opened positions."""
        self._register_stop(direction, sl, tp, entry, trail_distance=trail_distance)

    def get_formatted_status(self):
        """Get status formatted for dashboard display."""
        status = self.get_status()

        # Format for display
        return {
            "balance": round(status["balance"].get("balance", 0), 2),
            "available": round(status["balance"].get("available", 0), 2),
            "unrealized_pnl": round(status["unrealized_pnl"], 2),
            "total_pnl": round(status["total_pnl"], 2),
            "positions": [{
                "side": p["side"],
                "amount": p["amount"],
                "entry": round(p["entry_price"], 2),
                "mark": round(p["mark_price"], 2),
                "pnl": round(p["unrealized_pnl"], 2),
                "pnl_pct": round(p["unrealized_pnl"] / (p["notional"] / p["leverage"]) * 100, 2) if p["notional"] > 0 else 0,
                "liq": round(p["liquidation_price"], 2),
                "lev": p["leverage"],
            } for p in status["positions"]],
            "orders": status["orders"],
            "stats": status["stats"],
            "auto_trade": status["auto_trade"],
            "leverage": status["leverage"],
            "usdt_per_trade": status["usdt_per_trade"],
            "recent_trades": status["recent_trades"],
        }
