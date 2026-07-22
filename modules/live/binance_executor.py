"""
Binance Futures Demo Executor
Handles: open positions, close positions, set SL/TP, track P&L
Uses Binance Futures TESTNET/DEMO API
"""

import time
import hmac
import hashlib
import json
import requests
from urllib.parse import urlencode
from datetime import datetime


class BinanceExecutor:
    def __init__(self, api_key, api_secret, base_url="https://demo-fapi.binance.com"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": self.api_key
        })
        self.symbol = "ETHUSDT"
        self.leverage = 5  # default leverage
        self.margin_type = "CROSSED"

    def _sign(self, params):
        """Sign request with HMAC SHA256."""
        query = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _request(self, method, endpoint, params=None, signed=False):
        """Make API request."""
        url = f"{self.base_url}{endpoint}"
        if params is None:
            params = {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params = self._sign(params)

        try:
            if method == "GET":
                r = self.session.get(url, params=params, timeout=10)
            elif method == "POST":
                r = self.session.post(url, params=params, timeout=10)
            elif method == "DELETE":
                r = self.session.delete(url, params=params, timeout=10)
            else:
                return None

            if r.status_code == 200:
                return r.json()
            else:
                print(f"[BINANCE] Error {r.status_code}: {r.text[:200]}")
                return {"error": r.text, "status": r.status_code}
        except Exception as e:
            print(f"[BINANCE] Request error: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════════
    # ACCOUNT
    # ═══════════════════════════════════════════════

    def get_balance(self):
        """Get futures account balance."""
        data = self._request("GET", "/fapi/v2/balance", signed=True)
        if isinstance(data, list):
            for asset in data:
                if asset.get("asset") == "USDT":
                    return {
                        "balance": float(asset.get("balance", 0)),
                        "available": float(asset.get("availableBalance", 0)),
                        "unrealized_pnl": float(asset.get("crossUnPnl", 0)),
                    }
        return {"balance": 0, "available": 0, "unrealized_pnl": 0, "error": data}

    def get_positions(self):
        """Get all open positions."""
        data = self._request("GET", "/fapi/v2/positionRisk", signed=True)
        positions = []
        if isinstance(data, list):
            for pos in data:
                amt = float(pos.get("positionAmt", 0))
                if amt != 0:
                    positions.append({
                        "symbol": pos.get("symbol"),
                        "side": "LONG" if amt > 0 else "SHORT",
                        "amount": abs(amt),
                        "entry_price": float(pos.get("entryPrice", 0)),
                        "mark_price": float(pos.get("markPrice", 0)),
                        "unrealized_pnl": float(pos.get("unRealizedProfit", 0)),
                        "leverage": int(pos.get("leverage", 1)),
                        "margin_type": pos.get("marginType"),
                        "liquidation_price": float(pos.get("liquidationPrice", 0)),
                        "notional": abs(float(pos.get("notional", 0))),
                    })
        return positions

    def get_open_orders(self):
        """Get all open orders."""
        data = self._request("GET", "/fapi/v1/openOrders",
                             {"symbol": self.symbol}, signed=True)
        if isinstance(data, list):
            return [{
                "order_id": o.get("orderId"),
                "side": o.get("side"),
                "type": o.get("type"),
                "price": float(o.get("price", 0)),
                "stop_price": float(o.get("stopPrice", 0)),
                "quantity": float(o.get("origQty", 0)),
                "status": o.get("status"),
                "reduce_only": o.get("reduceOnly", False),
            } for o in data]
        return []

    # ═══════════════════════════════════════════════
    # SETUP
    # ═══════════════════════════════════════════════

    def set_leverage(self, leverage=None):
        """Set leverage for the symbol."""
        lev = leverage or self.leverage
        result = self._request("POST", "/fapi/v1/leverage", {
            "symbol": self.symbol,
            "leverage": lev,
        }, signed=True)
        print(f"[BINANCE] Leverage set to {lev}x: {result}")
        return result

    def set_margin_type(self, margin_type="CROSSED"):
        """Set margin type (CROSSED or ISOLATED)."""
        result = self._request("POST", "/fapi/v1/marginType", {
            "symbol": self.symbol,
            "marginType": margin_type,
        }, signed=True)
        # Binance returns -4046 if already set, that's fine
        if isinstance(result, dict) and result.get("code") == -4046:
            print(f"[BINANCE] Margin type already {margin_type}")
        else:
            print(f"[BINANCE] Margin type set to {margin_type}: {result}")
        return result

    # ═══════════════════════════════════════════════
    # TRADE EXECUTION
    # ═══════════════════════════════════════════════

    def open_position(self, direction, quantity=None, usdt_amount=None):
        """
        Open a position.
        direction: "LONG" or "SHORT"
        quantity: exact ETH amount (or)
        usdt_amount: USDT to use (auto-calculates quantity)
        """
        side = "BUY" if direction == "LONG" else "SELL"

        # Get current price for quantity calculation
        if usdt_amount and not quantity:
            ticker = self._request("GET", "/fapi/v1/ticker/price",
                                   {"symbol": self.symbol})
            if ticker and "price" in ticker:
                price = float(ticker["price"])
                # quantity = usdt_amount * leverage / price
                quantity = round(usdt_amount * self.leverage / price, 3)
            else:
                return {"error": "Could not get price"}

        if not quantity or quantity <= 0:
            return {"error": "Invalid quantity"}

        # Place market order
        result = self._request("POST", "/fapi/v1/order", {
            "symbol": self.symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
        }, signed=True)

        if isinstance(result, dict) and "orderId" in result:
            print(f"[BINANCE] OPENED {direction} {quantity} ETH @ market")
            return {
                "success": True,
                "order_id": result["orderId"],
                "direction": direction,
                "quantity": quantity,
                "side": side,
                "time": datetime.now().isoformat(),
            }
        else:
            print(f"[BINANCE] OPEN FAILED: {result}")
            return {"error": result}

    def close_position(self, direction, quantity=None):
        """Close a position (or partial)."""
        # Opposite side to close
        side = "SELL" if direction == "LONG" else "BUY"

        if not quantity:
            # Close full position
            positions = self.get_positions()
            for pos in positions:
                if pos["symbol"] == self.symbol and pos["side"] == direction:
                    quantity = pos["amount"]
                    break

        if not quantity or quantity <= 0:
            return {"error": "No position to close"}

        result = self._request("POST", "/fapi/v1/order", {
            "symbol": self.symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
            "reduceOnly": "true",
        }, signed=True)

        if isinstance(result, dict) and "orderId" in result:
            print(f"[BINANCE] CLOSED {direction} {quantity} ETH @ market")
            return {
                "success": True,
                "order_id": result["orderId"],
                "direction": direction,
                "quantity": quantity,
                "time": datetime.now().isoformat(),
            }
        else:
            print(f"[BINANCE] CLOSE FAILED: {result}")
            return {"error": result}

    def close_all(self):
        """Close all open positions."""
        results = []
        positions = self.get_positions()
        for pos in positions:
            if pos["symbol"] == self.symbol:
                r = self.close_position(pos["side"], pos["amount"])
                results.append(r)
        return results

    # ═══════════════════════════════════════════════
    # SL/TP ORDERS
    # ═══════════════════════════════════════════════

    def set_stop_loss(self, direction, stop_price, quantity=None):
        """Place a stop-loss order."""
        # SL for LONG = SELL, SL for SHORT = BUY
        side = "SELL" if direction == "LONG" else "BUY"

        if not quantity:
            positions = self.get_positions()
            for pos in positions:
                if pos["symbol"] == self.symbol and pos["side"] == direction:
                    quantity = pos["amount"]
                    break

        if not quantity:
            return {"error": "No position found"}

        # Cancel existing SL orders first
        self._cancel_orders_by_type("STOP_MARKET")

        result = self._request("POST", "/fapi/v1/order", {
            "symbol": self.symbol,
            "side": side,
            "type": "STOP_MARKET",
            "stopPrice": round(stop_price, 2),
            "quantity": quantity,
            "reduceOnly": "true",
            "workingType": "MARK_PRICE",
        }, signed=True)

        if isinstance(result, dict) and "orderId" in result:
            print(f"[BINANCE] SL set @ ${stop_price:.2f}")
            return {"success": True, "stop_price": stop_price, "order_id": result["orderId"]}
        return {"error": result}

    def set_take_profit(self, direction, tp_price, quantity=None):
        """Place a take-profit order."""
        side = "SELL" if direction == "LONG" else "BUY"

        if not quantity:
            positions = self.get_positions()
            for pos in positions:
                if pos["symbol"] == self.symbol and pos["side"] == direction:
                    quantity = pos["amount"]
                    break

        if not quantity:
            return {"error": "No position found"}

        # Cancel existing TP orders first
        self._cancel_orders_by_type("TAKE_PROFIT_MARKET")

        result = self._request("POST", "/fapi/v1/order", {
            "symbol": self.symbol,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": round(tp_price, 2),
            "quantity": quantity,
            "reduceOnly": "true",
            "workingType": "MARK_PRICE",
        }, signed=True)

        if isinstance(result, dict) and "orderId" in result:
            print(f"[BINANCE] TP set @ ${tp_price:.2f}")
            return {"success": True, "take_profit": tp_price, "order_id": result["orderId"]}
        return {"error": result}

    def _cancel_orders_by_type(self, order_type):
        """Cancel all orders of a given type."""
        orders = self.get_open_orders()
        for order in orders:
            if order["type"] == order_type:
                self._request("DELETE", "/fapi/v1/order", {
                    "symbol": self.symbol,
                    "orderId": order["order_id"],
                }, signed=True)

    def cancel_all_orders(self):
        """Cancel all open orders."""
        result = self._request("DELETE", "/fapi/v1/allOpenOrders", {
            "symbol": self.symbol,
        }, signed=True)
        print(f"[BINANCE] Cancelled all orders: {result}")
        return result

    # ═══════════════════════════════════════════════
    # TRADE HISTORY
    # ═══════════════════════════════════════════════

    def get_trade_history(self, limit=50):
        """Get recent trades."""
        data = self._request("GET", "/fapi/v1/userTrades", {
            "symbol": self.symbol,
            "limit": limit,
        }, signed=True)
        trades = []
        if isinstance(data, list):
            for t in data:
                trades.append({
                    "id": t.get("id"),
                    "order_id": t.get("orderId"),
                    "side": t.get("side"),
                    "price": float(t.get("price", 0)),
                    "quantity": float(t.get("qty", 0)),
                    "realized_pnl": float(t.get("realizedPnl", 0)),
                    "commission": float(t.get("commission", 0)),
                    "time": datetime.fromtimestamp(t.get("time", 0) / 1000).isoformat(),
                })
        return trades

    def get_income_history(self, limit=50):
        """Get income history (PnL, funding, etc)."""
        data = self._request("GET", "/fapi/v1/income", {
            "symbol": self.symbol,
            "limit": limit,
        }, signed=True)
        income = []
        if isinstance(data, list):
            for i in data:
                income.append({
                    "type": i.get("incomeType"),
                    "amount": float(i.get("income", 0)),
                    "asset": i.get("asset"),
                    "time": datetime.fromtimestamp(i.get("time", 0) / 1000).isoformat(),
                })
        return income

    # ═══════════════════════════════════════════════
    # CONVENIENCE
    # ═══════════════════════════════════════════════

    def execute_signal(self, direction, sl_price, tp_price, usdt_amount=100):
        """
        Full trade execution: open position only.
        SL/TP handled by monitor thread (Binance demo doesn't support stop orders).
        """
        # 1. Set leverage
        self.set_leverage()

        # 2. Open position
        result = self.open_position(direction, usdt_amount=usdt_amount)
        if not result.get("success"):
            return result

        return {
            "success": True,
            "direction": direction,
            "quantity": result.get("quantity"),
            "sl": sl_price,
            "tp": tp_price,
            "time": datetime.now().isoformat(),
            "note": "SL/TP monitored by software (Binance demo limitation)",
        }

    def get_full_status(self):
        """Get complete account + position status."""
        balance = self.get_balance()
        positions = self.get_positions()
        orders = self.get_open_orders()

        return {
            "balance": balance,
            "positions": positions,
            "orders": orders,
            "leverage": self.leverage,
            "symbol": self.symbol,
            "timestamp": datetime.now().isoformat(),
        }
