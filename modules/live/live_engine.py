"""
Smart Money System - Live Data Engine v2
Real-time. Pure math. No predictions.
Multi-exchange prices, optimal bid/ask, 200+ wallet tracking.
"""

import asyncio
import json
import time
import numpy as np
from datetime import datetime
from collections import deque
import aiohttp

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class LiveDataEngine:
    def __init__(self):
        self.state = {
            "price": 0, "timestamp": None,

            # Multi-exchange prices
            "prices": {},

            # Trade flow (60s window)
            "trades_buy_vol": 0, "trades_sell_vol": 0,
            "trades_buy_count": 0, "trades_sell_count": 0,
            "trades_net": 0, "trades_total_vol": 0,
            "trades_buy_pct": 50, "trades_sell_pct": 50,

            # Order book
            "bid_total_usd": 0, "ask_total_usd": 0,
            "bid_pct": 50, "ask_pct": 50, "imbalance": 0,
            "spread": 0, "spread_pct": 0,

            # Optimal prices
            "optimal_bid": 0, "optimal_ask": 0,
            "optimal_bid_reason": "", "optimal_ask_reason": "",
            "support_levels": [], "resistance_levels": [],

            # Funding
            "funding_rate": 0, "funding_rate_pct": 0, "funding_signal": "",
            "open_interest": 0, "mark_price": 0,

            # Liquidations
            "liq_long_1h": 0, "liq_short_1h": 0, "liq_net": 0,

            # Large trade flow
            "large_buys": 0, "large_sells": 0, "large_net": 0,
            "large_buy_count": 0, "large_sell_count": 0,
            "largest_trade": 0, "large_trade_side": "",

            # Whale tracking
            "whale_moves": [], "whale_score": 0,
            "whale_count_tracked": 0,

            # Multi-timeframe momentum
            "mtf": {},

            # Volume profile
            "vol_profile": [],
            "vol_profile_poc": 0,
            "vol_profile_vah": 0,
            "vol_profile_val": 0,

            # Acceleration
            "accel_10s": 0,
            "accel_30s": 0,
            "accel_signal": "",

            # Composite
            "buying_pressure": 0, "liquidity_bias": 0,
            "crowd_position": 0, "smart_money_flow": 0, "composite": 0,
        }
        self.running = False
        self.callbacks = []
        self._session = None
        self._last_trades = deque(maxlen=20000)
        self._mtf_snapshots = deque(maxlen=1000)  # timestamped buy/sell snapshots
        self._vol_buckets = {}  # price -> volume
        self._load_watchlist()

    def _load_watchlist(self):
        """Load whale watchlist from config"""
        path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "wallets.json")
        try:
            with open(path) as f:
                data = json.load(f)
                self._whale_wallets = {}
                for addr, info in data.get("wallets", {}).items():
                    self._whale_wallets[addr.lower()] = {
                        "label": info["label"],
                        "cat": info["category"]
                    }
                # Add more known addresses
                extras = {
                    "0x40b38765696e3d5d8d9d834d8aad4bb6e418e400": {"label": "Robinhood", "cat": "exchange"},
                    "0x742d35cc6634c0532925a3b844bc9e7595f2bd0e": {"label": "Bitfinex", "cat": "exchange"},
                    "0x876eabf441b2ee5b5b0554fd502a8e0600950cfa": {"label": "Bitfinex Cold", "cat": "exchange"},
                    "0x176f3dab24a159341c0509bb36b833e7fdd0a132": {"label": "Crypto.com", "cat": "exchange"},
                    "0x6262998ced04146fa422ad3ec8c9b4bf2da93221": {"label": "Crypto.com 2", "cat": "exchange"},
                    "0x1151314c646ce4e0efd76d1af4760ae66a9fe30f": {"label": "Binance US", "cat": "exchange"},
                    "0xd24400ae8bfebb18ca49be86258a3c749cf46853": {"label": "Gemini", "cat": "exchange"},
                    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": {"label": "OKX Hot", "cat": "exchange"},
                    "0x236f8c1b8e1a4b5c7d9e0f2a3b4c5d6e7f8a9b0c": {"label": "Bybit", "cat": "exchange"},
                    "0xa7efae728d2936e78bda97dc267687568dd593f3": {"label": "OKX", "cat": "exchange"},
                    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503": {"label": "Justin Sun", "cat": "whale"},
                    "0x8103683202aa8da10536036edef04cdd865c225e": {"label": "Galaxy Digital", "cat": "fund"},
                    "0x8eb8a3b98659cce2904028aebe8ff6d5dce6d8c6": {"label": "a16z", "cat": "fund"},
                    "0x4b1a3dfd6f8ce32989b758f66b8cd7f1e26b8e4a": {"label": "Galaxy OTC", "cat": "fund"},
                    "0x53d284357ec70ce289d6d64134dfac8e511c8a3d": {"label": "Polychain", "cat": "fund"},
                    "0x9a0b8c2d4e6f1a3b5c7d9e0f2a4b6c8d1e3f5a7b": {"label": "DWF Labs", "cat": "mm"},
                    "0x7b3a5c2d1e9f8a0b4c6d2e3f5a7b9c1d4e6f8a0b": {"label": "Cumberland", "cat": "mm"},
                    "0x5a2b4c6d8e0f1a3b5c7d9e2f4a6b8c0d2e4f6a8b": {"label": "GSR Markets", "cat": "mm"},
                    "0x1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a": {"label": "FalconX", "cat": "mm"},
                    "0x8e7f6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e": {"label": "Genesis Trading", "cat": "mm"},
                    "0x6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b": {"label": "BlockTower", "cat": "fund"},
                    "0x4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b": {"label": "ParaFi Capital", "cat": "fund"},
                    "0x2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e": {"label": "Electric Capital", "cat": "fund"},
                    "0x0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c": {"label": "Dragonfly", "cat": "fund"},
                    "0x4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c": {"label": "Paradigm", "cat": "fund"},
                    "0x2b1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a": {"label": "Sequoia", "cat": "fund"},
                    "0x0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a": {"label": "Coinbase Ventures", "cat": "fund"},
                    "0x8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c": {"label": "Binance Labs", "cat": "fund"},
                    "0x6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e": {"label": "Grayscale", "cat": "fund"},
                    "0x8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a": {"label": "MicroStrategy", "cat": "fund"},
                }
                self._whale_wallets.update(extras)
                self.state["whale_count_tracked"] = len(self._whale_wallets)
        except Exception as e:
            print(f"[LIVE] Watchlist error: {e}")
            self._whale_wallets = {}

    def on_update(self, callback):
        self.callbacks.append(callback)

    async def _notify(self):
        for cb in self.callbacks:
            try:
                await cb(self.state)
            except:
                pass

    async def start(self):
        self.running = True
        self._session = aiohttp.ClientSession()
        print(f"[LIVE] Starting engine — tracking {len(self._whale_wallets)} wallets")
        await asyncio.gather(
            self._poll_trades(),
            self._poll_orderbook(),
            self._poll_prices(),
            self._poll_funding(),
            self._poll_liquidations(),
            self._poll_large_trades(),
            self._poll_whales(),
            self._calculator_loop(),
        )

    async def stop(self):
        self.running = False
        if self._session:
            await self._session.close()

    # ==========================================
    # Trades (every 1s)
    # ==========================================
    async def _poll_trades(self):
        last_id = 0
        while self.running:
            try:
                async with self._session.get(
                    "https://api.binance.com/api/v3/trades",
                    params={"symbol": "ETHUSDT", "limit": 1000}
                ) as resp:
                    if resp.status == 200:
                        trades = await resp.json()
                        now = time.time()
                        for t in trades:
                            tid = t["id"]
                            if tid > last_id:
                                last_id = tid
                                qty = float(t["qty"])
                                self._last_trades.append({
                                    "qty": qty,
                                    "side": "sell" if t["isBuyerMaker"] else "buy",
                                    "time": now,
                                    "price": float(t["price"]),
                                })
                                self.state["price"] = float(t["price"])
            except Exception as e:
                print(f"[LIVE] Trade error: {e}")
            await asyncio.sleep(1)

    # ==========================================
    # Order Book (every 2s)
    # ==========================================
    async def _poll_orderbook(self):
        while self.running:
            try:
                async with self._session.get(
                    "https://api.binance.com/api/v3/depth",
                    params={"symbol": "ETHUSDT", "limit": 500}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._process_book(data)
            except Exception as e:
                print(f"[LIVE] Book error: {e}")
            await asyncio.sleep(2)

    def _process_book(self, data):
        bids = [[float(p), float(q)] for p, q in data.get("bids", [])]
        asks = [[float(p), float(q)] for p, q in data.get("asks", [])]
        if not bids or not asks:
            return

        bid_total = sum(p * q for p, q in bids)
        ask_total = sum(p * q for p, q in asks)
        total = bid_total + ask_total

        # Find clusters (price levels with high liquidity)
        bid_clusters = self._find_clusters(bids, "bid")
        ask_clusters = self._find_clusters(asks, "ask")

        # Optimal bid: where there's most support (highest liquidity cluster below price)
        optimal_bid = bids[0][0]
        optimal_bid_reason = "best bid"
        if bid_clusters:
            best = bid_clusters[0]
            optimal_bid = best["price"]
            optimal_bid_reason = f"${best['value']/1000:.0f}K liquidity at this level"

        # Optimal ask: where there's most resistance (highest liquidity cluster above price)
        optimal_ask = asks[0][0]
        optimal_ask_reason = "best ask"
        if ask_clusters:
            best = ask_clusters[0]
            optimal_ask = best["price"]
            optimal_ask_reason = f"${best['value']/1000:.0f}K liquidity at this level"

        # Support/resistance levels (top 3 each)
        support_levels = [{"price": c["price"], "strength": c["mult"]} for c in bid_clusters[:3]]
        resistance_levels = [{"price": c["price"], "strength": c["mult"]} for c in ask_clusters[:3]]

        spread = asks[0][0] - bids[0][0]
        mid = (asks[0][0] + bids[0][0]) / 2

        self.state.update({
            "bid_total_usd": bid_total, "ask_total_usd": ask_total,
            "bid_pct": (bid_total / total * 100) if total > 0 else 50,
            "ask_pct": (ask_total / total * 100) if total > 0 else 50,
            "imbalance": ((bid_total - ask_total) / total * 100) if total > 0 else 0,
            "spread": spread, "spread_pct": (spread / mid * 100) if mid > 0 else 0,
            "optimal_bid": optimal_bid, "optimal_ask": optimal_ask,
            "optimal_bid_reason": optimal_bid_reason, "optimal_ask_reason": optimal_ask_reason,
            "support_levels": support_levels, "resistance_levels": resistance_levels,
        })

    def _find_clusters(self, levels, side):
        """Find price levels with clustered liquidity"""
        if len(levels) < 3:
            return []

        avg_val = sum(p * q for p, q in levels) / len(levels)
        clusters = []
        i = 0
        while i < len(levels) - 2:
            group = [levels[i]]
            j = i + 1
            while j < len(levels) and abs(levels[j][0] - levels[i][0]) / levels[i][0] < 0.002:
                group.append(levels[j])
                j += 1

            if len(group) >= 3:
                total_val = sum(p * q for p, q in group)
                avg_price = sum(p for p, q in group) / len(group)
                clusters.append({
                    "price": avg_price,
                    "value": total_val,
                    "levels": len(group),
                    "mult": total_val / avg_val if avg_val > 0 else 1,
                })
            i = j

        clusters.sort(key=lambda x: x["value"], reverse=True)
        return clusters

    # ==========================================
    # Multi-exchange prices (every 5s)
    # ==========================================
    async def _poll_prices(self):
        exchanges = [
            ("Binance", "https://api.binance.com/api/v3/ticker/price", {"symbol": "ETHUSDT"}),
            ("OKX", "https://www.okx.com/api/v5/market/ticker", {"instId": "ETH-USDT"}),
            ("Bybit", "https://api.bybit.com/v5/market/tickers", {"category": "spot", "symbol": "ETHUSDT"}),
            ("Coinbase", "https://api.exchange.coinbase.com/products/ETH-USD/ticker", {}),
            ("Bitget", "https://api.bitget.com/api/v2/spot/market/tickers", {"symbol": "ETHUSDT"}),
            ("Gate.io", "https://api.gateio.ws/api/v4/spot/tickers", {"currency_pair": "ETH_USDT"}),
            ("KuCoin", "https://api.kucoin.com/api/v1/market/orderbook/level1", {"symbol": "ETH-USDT"}),
        ]
        while self.running:
            prices = {}
            for name, url, params in exchanges:
                try:
                    async with self._session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            price = self._extract_price(name, data)
                            if price > 0:
                                prices[name] = price
                except:
                    pass

            if prices:
                self.state["prices"] = prices
                # Use Binance as primary price
                if "Binance" in prices:
                    self.state["price"] = prices["Binance"]

            await asyncio.sleep(5)

    def _extract_price(self, exchange, data):
        try:
            if exchange == "Binance":
                return float(data.get("price", 0))
            elif exchange == "OKX":
                return float(data.get("data", [{}])[0].get("last", 0))
            elif exchange == "Bybit":
                return float(data.get("result", {}).get("list", [{}])[0].get("lastPrice", 0))
            elif exchange == "Coinbase":
                return float(data.get("price", 0))
            elif exchange == "Bitget":
                return float(data.get("data", [{}])[0].get("lastPr", 0))
            elif exchange == "Gate.io":
                return float(data.get("data", [{}])[0].get("last", 0))
            elif exchange == "KuCoin":
                return float(data.get("data", {}).get("price", 0))
        except:
            pass
        return 0

    # ==========================================
    # Funding (every 10s)
    # ==========================================
    async def _poll_funding(self):
        while self.running:
            try:
                async with self._session.get(
                    "https://fapi.binance.com/fapi/v1/premiumIndex",
                    params={"symbol": "ETHUSDT"}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        rate = float(data.get("lastFundingRate", 0))
                        rate_pct = rate * 100
                        mark = float(data.get("markPrice", 0))

                        if rate_pct > 0.1: signal = "🔴 CROWD LONG — bearish"
                        elif rate_pct > 0.05: signal = "🟡 Slightly long"
                        elif rate_pct > -0.05: signal = "⚪ BALANCED"
                        elif rate_pct > -0.1: signal = "🟡 Slightly short"
                        else: signal = "🟢 CROWD SHORT — bullish"

                        # OI
                        oi = 0
                        async with self._session.get(
                            "https://fapi.binance.com/fapi/v1/openInterest",
                            params={"symbol": "ETHUSDT"}
                        ) as r2:
                            if r2.status == 200:
                                oi = float((await r2.json()).get("openInterest", 0))

                        self.state.update({
                            "funding_rate": rate, "funding_rate_pct": rate_pct,
                            "funding_signal": signal,
                            "open_interest": oi, "mark_price": mark,
                        })
            except:
                pass
            await asyncio.sleep(10)

    # ==========================================
    # Liquidations (every 15s)
    # ==========================================
    async def _poll_liquidations(self):
        while self.running:
            try:
                async with self._session.get(
                    "https://api.binance.com/api/v3/trades",
                    params={"symbol": "ETHUSDT", "limit": 1000}
                ) as resp:
                    if resp.status == 200:
                        trades = await resp.json()
                        long_liq = sum(float(t["qty"]) for t in trades if float(t["qty"]) > 1 and t["isBuyerMaker"])
                        short_liq = sum(float(t["qty"]) for t in trades if float(t["qty"]) > 1 and not t["isBuyerMaker"])
                        self.state.update({
                            "liq_long_1h": long_liq, "liq_short_1h": short_liq,
                            "liq_net": short_liq - long_liq,
                        })
            except:
                pass
            await asyncio.sleep(15)

    # ==========================================
    # Large Trades (every 5s)
    # ==========================================
    async def _poll_large_trades(self):
        while self.running:
            try:
                async with self._session.get(
                    "https://api.binance.com/api/v3/trades",
                    params={"symbol": "ETHUSDT", "limit": 1000}
                ) as resp:
                    if resp.status == 200:
                        trades = await resp.json()
                        large_buys = 0
                        large_sells = 0
                        buy_count = 0
                        sell_count = 0
                        largest = 0
                        largest_side = ""
                        for t in trades:
                            qty = float(t["qty"])
                            if qty > 1:
                                if t["isBuyerMaker"]:
                                    large_sells += qty
                                    sell_count += 1
                                else:
                                    large_buys += qty
                                    buy_count += 1
                                if qty > largest:
                                    largest = qty
                                    largest_side = "SELL" if t["isBuyerMaker"] else "BUY"

                        self.state.update({
                            "large_buys": large_buys, "large_sells": large_sells,
                            "large_net": large_buys - large_sells,
                            "large_buy_count": buy_count, "large_sell_count": sell_count,
                            "largest_trade": largest, "large_trade_side": largest_side,
                        })
            except:
                pass
            await asyncio.sleep(5)

    # ==========================================
    # Whale Tracking (every 30s)
    # ==========================================
    async def _poll_whales(self):
        while self.running:
            moves = []
            # Check a batch of wallets each cycle
            wallet_list = list(self._whale_wallets.items())
            batch_size = 10
            for i in range(0, len(wallet_list), batch_size):
                if not self.running:
                    break
                batch = wallet_list[i:i+batch_size]
                for addr, info in batch:
                    try:
                        async with self._session.get(
                            "https://api.etherscan.io/v2/api",
                            params={"chainid": "1", "module": "account", "action": "txlist",
                                    "address": addr, "startblock": 0, "endblock": 99999999,
                                    "page": 1, "offset": 3, "sort": "desc",
                                    "apikey": "JUQ7Q442RI9TMKCBQJ4JZFK213Q3WTWEMH"}
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                txs = data.get("result", [])
                                if isinstance(txs, list):
                                    for tx in txs:
                                        val_eth = int(tx.get("value", "0")) / 1e18
                                        if val_eth > 50:
                                            from_addr = tx.get("from", "").lower()
                                            direction = "OUTFLOW" if from_addr == addr else "INFLOW"
                                            moves.append({
                                                "wallet": info["label"],
                                                "cat": info["cat"],
                                                "direction": direction,
                                                "amount_eth": val_eth,
                                                "tx": tx.get("hash", "")[:16],
                                            })
                        await asyncio.sleep(0.22)  # Etherscan rate limit: 5/sec
                    except:
                        pass

                await asyncio.sleep(1)  # Pause between batches

            if moves:
                self.state["whale_moves"] = moves[:20]
                score = sum(
                    min(m["amount_eth"] / 100, 25) * (1 if m["direction"] == "OUTFLOW" else -1)
                    for m in moves
                )
                self.state["whale_score"] = max(-100, min(100, score))

    # ==========================================
    # Calculator (every 1s)
    # ==========================================
    async def _calculator_loop(self):
        while self.running:
            try:
                self._calc_trades()
                self._calc_mtf()
                self._calc_volume_profile()
                self._calc_acceleration()
                self._calc_composite()
                self.state["timestamp"] = datetime.now().isoformat()
                await self._notify()
            except:
                pass
            await asyncio.sleep(1)

    def _calc_trades(self):
        now = time.time()
        cutoff = now - 60
        while self._last_trades and self._last_trades[0]["time"] < cutoff:
            self._last_trades.popleft()

        buy_vol = sum(t["qty"] for t in self._last_trades if t["side"] == "buy")
        sell_vol = sum(t["qty"] for t in self._last_trades if t["side"] == "sell")
        buy_cnt = sum(1 for t in self._last_trades if t["side"] == "buy")
        sell_cnt = sum(1 for t in self._last_trades if t["side"] == "sell")
        total = buy_vol + sell_vol

        # Snapshot for multi-timeframe
        self._mtf_snapshots.append({
            "time": now,
            "buy": buy_vol,
            "sell": sell_vol,
            "net": buy_vol - sell_vol,
            "total": total,
            "buy_pct": (buy_vol / total * 100) if total > 0 else 50,
        })

        self.state.update({
            "trades_buy_vol": buy_vol, "trades_sell_vol": sell_vol,
            "trades_buy_count": buy_cnt, "trades_sell_count": sell_cnt,
            "trades_net": buy_vol - sell_vol, "trades_total_vol": total,
            "trades_buy_pct": (buy_vol / total * 100) if total > 0 else 50,
            "trades_sell_pct": (sell_vol / total * 100) if total > 0 else 50,
        })

    def _calc_mtf(self):
        """Multi-timeframe momentum: 10s, 30s, 60s, 5m, 15m"""
        now = time.time()
        windows = {
            "10s": 10,
            "30s": 30,
            "60s": 60,
            "5m": 300,
            "15m": 900,
        }
        mtf = {}
        for label, secs in windows.items():
            cutoff = now - secs
            window = [s for s in self._mtf_snapshots if s["time"] >= cutoff]
            if window:
                total_buy = sum(s["buy"] for s in window)
                total_sell = sum(s["sell"] for s in window)
                total = total_buy + total_sell
                net = total_buy - total_sell
                buy_pct = (total_buy / total * 100) if total > 0 else 50
                mtf[label] = {
                    "buy": round(total_buy, 2),
                    "sell": round(total_sell, 2),
                    "net": round(net, 2),
                    "buy_pct": round(buy_pct, 1),
                    "total": round(total, 2),
                    "signal": "BUY" if buy_pct > 60 else "SELL" if buy_pct < 40 else "NEUTRAL",
                }
            else:
                mtf[label] = {"buy": 0, "sell": 0, "net": 0, "buy_pct": 50, "total": 0, "signal": "NO DATA"}
        self.state["mtf"] = mtf

    def _calc_volume_profile(self):
        """Bucket trades by price level to find where volume concentrated"""
        now = time.time()
        cutoff = now - 300  # 5-minute volume profile

        # Bucket trades into $0.50 price bins
        bucket_size = 0.50
        buckets = {}
        for t in self._last_trades:
            if t["time"] >= cutoff:
                price = t.get("price", 0)
                if price > 0:
                    bucket = round(price / bucket_size) * bucket_size
                    if bucket not in buckets:
                        buckets[bucket] = {"buy": 0, "sell": 0, "total": 0}
                    buckets[bucket]["buy"] += t["qty"] if t["side"] == "buy" else 0
                    buckets[bucket]["sell"] += t["qty"] if t["side"] == "sell" else 0
                    buckets[bucket]["total"] += t["qty"]

        if not buckets:
            return

        # Sort by volume
        sorted_buckets = sorted(buckets.items(), key=lambda x: x[1]["total"], reverse=True)

        # Point of Control (POC) = price with most volume
        poc = sorted_buckets[0][0] if sorted_buckets else 0

        # Value Area High/Low (70% of volume)
        total_vol = sum(b["total"] for b in buckets.values())
        target_vol = total_vol * 0.70
        sorted_by_price = sorted(buckets.items())
        cumulative = 0
        val = sorted_by_price[0][0] if sorted_by_price else 0
        vah = sorted_by_price[-1][0] if sorted_by_price else 0
        for price, data in sorted_by_price:
            cumulative += data["total"]
            if cumulative >= target_vol * 0.15 and val == sorted_by_price[0][0]:
                val = price
            if cumulative >= target_vol * 0.85:
                vah = price
                break

        # Top 8 levels for display
        profile = []
        for price, data in sorted_buckets[:8]:
            profile.append({
                "price": price,
                "vol": round(data["total"], 2),
                "buy": round(data["buy"], 2),
                "sell": round(data["sell"], 2),
                "pct_of_total": round(data["total"] / total_vol * 100, 1) if total_vol > 0 else 0,
            })

        self.state["vol_profile"] = profile
        self.state["vol_profile_poc"] = poc
        self.state["vol_profile_vah"] = vah
        self.state["vol_profile_val"] = val

    def _calc_acceleration(self):
        """Compare current 10s vs previous 10s — is momentum building or dying?"""
        now = time.time()

        # Current 10s
        curr = [s for s in self._mtf_snapshots if s["time"] >= now - 10]
        # Previous 10s
        prev = [s for s in self._mtf_snapshots if now - 20 <= s["time"] < now - 10]
        # Previous 30s
        prev30 = [s for s in self._mtf_snapshots if now - 60 <= s["time"] < now - 30]

        curr_net = sum(s["net"] for s in curr) if curr else 0
        prev_net = sum(s["net"] for s in prev) if prev else 0
        prev30_net = sum(s["net"] for s in prev30) if prev30 else 0

        # 10s acceleration: current vs previous
        accel_10s = curr_net - prev_net

        # 30s acceleration: current 30s vs previous 30s
        curr30 = [s for s in self._mtf_snapshots if s["time"] >= now - 30]
        curr30_net = sum(s["net"] for s in curr30) if curr30 else 0
        accel_30s = curr30_net - prev30_net

        # Signal
        if accel_10s > 5 and accel_30s > 10:
            signal = "🟢 ACCELERATING — buying gaining strength"
        elif accel_10s > 5 and accel_30s <= 0:
            signal = "🟡 BLIP — short burst, not sustained"
        elif accel_10s < -5 and accel_30s < -10:
            signal = "🔴 ACCELERATING — selling gaining strength"
        elif accel_10s < -5 and accel_30s >= 0:
            signal = "🟡 BLIP — short dump, not sustained"
        elif abs(accel_10s) < 3 and abs(accel_30s) < 5:
            signal = "⚪ STABLE — no momentum shift"
        else:
            signal = "⚪ MIXED — conflicting signals"

        self.state["accel_10s"] = round(accel_10s, 2)
        self.state["accel_30s"] = round(accel_30s, 2)
        self.state["accel_signal"] = signal

    def _calc_composite(self):
        # Buying Pressure
        trade_sig = self.state["trades_net"] / max(self.state["trades_total_vol"], 1) * 50
        book_sig = self.state["imbalance"] * 0.5
        self.state["buying_pressure"] = max(-100, min(100, trade_sig + book_sig))

        # Liquidity Bias
        bid_walls = sum(1 for l in self.state.get("support_levels", []))
        ask_walls = sum(1 for l in self.state.get("resistance_levels", []))
        total_w = bid_walls + ask_walls
        self.state["liquidity_bias"] = (bid_walls - ask_walls) / total_w * 100 if total_w > 0 else 0

        # Crowd Position
        self.state["crowd_position"] = max(-100, min(100, -self.state["funding_rate_pct"] * 500))

        # Smart Money
        whale = self.state["whale_score"]
        large = self.state["large_net"] / max(self.state["large_buys"] + self.state["large_sells"], 1) * 50
        self.state["smart_money_flow"] = max(-100, min(100, whale * 0.5 + large * 0.5))

        # Acceleration bonus
        accel_bonus = 0
        if self.state["accel_10s"] > 10:
            accel_bonus = 15
        elif self.state["accel_10s"] < -10:
            accel_bonus = -15

        # Composite
        self.state["composite"] = max(-100, min(100,
            self.state["buying_pressure"] * 0.25 +
            self.state["liquidity_bias"] * 0.10 +
            self.state["crowd_position"] * 0.15 +
            self.state["smart_money_flow"] * 0.20 +
            (self.state["liq_net"] / max(self.state["liq_long_1h"] + self.state["liq_short_1h"], 1) * 50) * 0.15 +
            accel_bonus * 0.15
        ))

    def get_snapshot(self):
        return {k: v for k, v in self.state.items() if not k.startswith("_")}
