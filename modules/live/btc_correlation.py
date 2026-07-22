"""
BTC Correlation Engine

ETH doesn't move alone. BTC leads, ETH follows with 1.2-1.5x leverage.
This engine tracks BTC alongside ETH to provide context for ETH signals.

Key insight: When BTC and ETH signals agree → high confidence.
When they disagree → don't trade.
"""

import asyncio
import time
import aiohttp
from collections import deque


class BTCCorrelation:
    def __init__(self):
        # BTC state
        self.btc_price = 0
        self.btc_price_5m_ago = 0
        self.btc_price_15m_ago = 0
        self.btc_change_5m = 0
        self.btc_change_15m = 0
        self.btc_momentum = "NEUTRAL"

        # BTC CVD approximation (from trades)
        self.btc_cvd = 0
        self.btc_cvd_roc_5m = 0
        self.btc_cvd_history = deque(maxlen=3600)
        self.btc_trade_history = deque(maxlen=5000)

        # ETH/BTC ratio
        self.eth_btc_ratio = 0
        self.eth_btc_ratio_5m_ago = 0
        self.eth_btc_change = 0  # Is ETH outperforming or underperforming BTC?

        # Correlation state
        self.correlation = "NEUTRAL"  # AGREE, DISAGREE, NEUTRAL
        self.correlation_detail = ""

        # Price history for tracking
        self.btc_price_history = deque(maxlen=3600)  # 1 hour of per-second prices

        self._session = None

    async def start(self):
        """Start BTC data collection."""
        self._session = aiohttp.ClientSession()
        print("[BTC] Starting BTC correlation engine")

        await asyncio.gather(
            self._poll_btc_price(),
            self._poll_btc_trades(),
            self._calc_loop(),
        )

    async def _poll_btc_price(self):
        """Poll BTC price every second."""
        while True:
            try:
                async with self._session.get(
                    "https://api.binance.com/api/v3/ticker/price",
                    params={"symbol": "BTCUSDT"},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.btc_price = float(data["price"])
                        self.btc_price_history.append({
                            "time": time.time(),
                            "price": self.btc_price
                        })
            except Exception as e:
                pass
            await asyncio.sleep(1)

    async def _poll_btc_trades(self):
        """Poll BTC trades for CVD calculation."""
        last_id = 0
        while True:
            try:
                async with self._session.get(
                    "https://api.binance.com/api/v3/trades",
                    params={"symbol": "BTCUSDT", "limit": 1000},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        trades = await resp.json()
                        now = time.time()
                        for t in trades:
                            tid = t["id"]
                            if tid > last_id:
                                last_id = tid
                                qty = float(t["qty"])
                                side = "sell" if t["isBuyerMaker"] else "buy"
                                delta = qty if side == "buy" else -qty
                                self.btc_cvd += delta
                                self.btc_trade_history.append({
                                    "time": now,
                                    "qty": qty,
                                    "side": side,
                                    "delta": delta,
                                })
                                self.btc_cvd_history.append({
                                    "time": now,
                                    "cvd": self.btc_cvd,
                                })
            except:
                pass
            await asyncio.sleep(2)

    async def _calc_loop(self):
        """Calculate derived metrics every second."""
        while True:
            try:
                self._calc_momentum()
                self._calc_eth_btc_ratio()
                self._calc_correlation()
            except:
                pass
            await asyncio.sleep(1)

    def _calc_momentum(self):
        """Calculate BTC momentum at multiple timeframes."""
        now = time.time()
        current = self.btc_price

        if current == 0:
            return

        # 5m momentum
        cutoff_5m = now - 300
        old_5m = None
        for p in self.btc_price_history:
            if p["time"] >= cutoff_5m:
                old_5m = p["price"]
                break
        if old_5m and old_5m > 0:
            self.btc_price_5m_ago = old_5m
            self.btc_change_5m = (current - old_5m) / old_5m * 100

        # 15m momentum
        cutoff_15m = now - 900
        old_15m = None
        for p in self.btc_price_history:
            if p["time"] >= cutoff_15m:
                old_15m = p["price"]
                break
        if old_15m and old_15m > 0:
            self.btc_price_15m_ago = old_15m
            self.btc_change_15m = (current - old_15m) / old_15m * 100

        # CVD ROC
        cvd_now = self.btc_cvd
        for snap in self.btc_cvd_history:
            if snap["time"] >= cutoff_5m:
                self.btc_cvd_roc_5m = cvd_now - snap["cvd"]
                break

        # Momentum classification
        if self.btc_change_5m > 0.3 and self.btc_change_15m > 0.5:
            self.btc_momentum = "🟢 STRONG UP"
        elif self.btc_change_5m > 0.15:
            self.btc_momentum = "🟢 UP"
        elif self.btc_change_5m < -0.3 and self.btc_change_15m < -0.5:
            self.btc_momentum = "🔴 STRONG DOWN"
        elif self.btc_change_5m < -0.15:
            self.btc_momentum = "🔴 DOWN"
        else:
            self.btc_momentum = "⚪ NEUTRAL"

    def _calc_eth_btc_ratio(self):
        """Track if ETH is outperforming or underperforming BTC."""
        # This needs ETH price — we'll get it from the state passed in
        # For now, track the ratio change
        pass

    def update_eth_price(self, eth_price):
        """Called from live server with current ETH price."""
        if self.btc_price > 0 and eth_price > 0:
            ratio = eth_price / self.btc_price
            if self.eth_btc_ratio > 0:
                self.eth_btc_change = (ratio - self.eth_btc_ratio) / self.eth_btc_ratio * 100
            self.eth_btc_ratio_5m_ago = self.eth_btc_ratio if self.eth_btc_ratio > 0 else ratio
            self.eth_btc_ratio = ratio

    def _calc_correlation(self):
        """Determine if BTC and ETH are moving together."""
        if self.btc_change_5m == 0:
            self.correlation = "NEUTRAL"
            self.correlation_detail = "No BTC movement"
            return

        # We need ETH change — this will be set by the pipeline
        # For now, use the ETH/BTC ratio as proxy
        if abs(self.btc_change_5m) < 0.1:
            self.correlation = "NEUTRAL"
            self.correlation_detail = f"BTC flat ({self.btc_change_5m:+.3f}%)"
            return

    def get_btc_context(self, eth_change_5m=0):
        """
        Get BTC context for an ETH signal.
        Returns context dict that helps decide whether to take the trade.
        """
        btc_dir = "LONG" if self.btc_change_5m > 0.15 else "SHORT" if self.btc_change_5m < -0.15 else "NEUTRAL"
        eth_dir = "LONG" if eth_change_5m > 0.15 else "SHORT" if eth_change_5m < -0.15 else "NEUTRAL"

        # Agreement check
        if btc_dir == eth_dir and btc_dir != "NEUTRAL":
            agreement = "AGREE"
            confidence_boost = 2
            detail = f"✅ BTC and ETH both {btc_dir} — high confidence"
        elif btc_dir == "NEUTRAL":
            agreement = "NEUTRAL"
            confidence_boost = 0
            detail = f"⚪ BTC neutral — ETH signal standalone"
        elif eth_dir == "NEUTRAL":
            agreement = "NEUTRAL"
            confidence_boost = 0
            detail = f"⚪ ETH neutral — no clear direction"
        elif btc_dir != eth_dir:
            agreement = "DISAGREE"
            confidence_boost = -3
            detail = f"⚠️ BTC {btc_dir} but ETH {eth_dir} — divergence, risky"
        else:
            agreement = "NEUTRAL"
            confidence_boost = 0
            detail = f"⚪ No clear correlation"

        # ETH/BTC ratio context
        ratio_context = ""
        if abs(self.eth_btc_change) > 0.5:
            if self.eth_btc_change > 0:
                ratio_context = f"ETH outperforming BTC ({self.eth_btc_change:+.2f}%) — ETH strength"
            else:
                ratio_context = f"ETH underperforming BTC ({self.eth_btc_change:+.2f}%) — ETH weakness"

        return {
            "btc_price": round(self.btc_price, 2),
            "btc_change_5m": round(self.btc_change_5m, 3),
            "btc_change_15m": round(self.btc_change_15m, 3),
            "btc_momentum": self.btc_momentum,
            "btc_cvd_roc_5m": round(self.btc_cvd_roc_5m, 2),
            "btc_direction": btc_dir,
            "eth_btc_ratio": round(self.eth_btc_ratio, 6),
            "eth_btc_change": round(self.eth_btc_change, 3),
            "agreement": agreement,
            "confidence_boost": confidence_boost,
            "detail": detail,
            "ratio_context": ratio_context,
        }

    def get_state(self):
        """Get current BTC state for display."""
        return {
            "btc_price": round(self.btc_price, 2),
            "btc_change_5m": round(self.btc_change_5m, 3),
            "btc_change_15m": round(self.btc_change_15m, 3),
            "btc_momentum": self.btc_momentum,
            "btc_cvd_roc_5m": round(self.btc_cvd_roc_5m, 2),
            "eth_btc_ratio": round(self.eth_btc_ratio, 6),
            "eth_btc_change": round(self.eth_btc_change, 3),
            "correlation": self.correlation,
        }
