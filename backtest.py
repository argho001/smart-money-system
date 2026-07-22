"""
Market Mechanics Backtest v5

Tests the core strategy signals against historical ETH data:
1. Liquidity sweep (support/resistance break + recovery)
2. Wyckoff spring/upthrust (false breakouts)
3. Funding extreme (crowd is wrong)
4. ATR-based SL/TP

Run: python3 backtest.py
Output: Trade-by-trade log with win rate, R:R, and P&L
"""

import asyncio
import aiohttp
import numpy as np
from datetime import datetime, timezone
import json
import os


class BacktestEngine:
    def __init__(self):
        self.trades = []
        self.signals = []  # All signals (including ones not taken)
        self.current_trade = None

        # ATR
        self.atr_period = 14
        self.atr = 0

        # Support/resistance levels
        self.support_levels = []
        self.resistance_levels = []

        # Stats
        self.total_signals = 0
        self.trades_taken = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0
        self.max_drawdown = 0
        self.peak_balance = 10000
        self.last_trade_time = None
        self.trade_cooldown = 6  # 6 candles = 30 min cooldown between trades

    async def run(self, days=30):
        """Run backtest over N days of historical data."""
        print("=" * 70)
        print("MARKET MECHANICS BACKTEST v5")
        print("=" * 70)
        print(f"Period: {days} days")
        print(f"Strategy: Liquidity Sweep + Wyckoff + Funding + ATR")
        print("=" * 70)

        # Fetch data
        print("\n[1/3] Fetching historical data...")
        candles = await self.fetch_candles("ETHUSDT", "5m", days)
        funding_data = await self.fetch_funding("ETHUSDT", days)
        btc_candles = await self.fetch_candles("BTCUSDT", "5m", days)

        if not candles:
            print("ERROR: No candle data fetched")
            return

        print(f"  ✅ {len(candles)} ETH candles ({candles[0]['time']} → {candles[-1]['time']})")
        print(f"  ✅ {len(funding_data)} funding rate entries")
        print(f"  ✅ {len(btc_candles)} BTC candles")

        # Build funding lookup (nearest 8h)
        funding_map = self._build_funding_map(funding_data)

        # Run simulation
        print("\n[2/3] Running simulation...")
        balance = 10000
        risk_pct = 2.0
        leverage = 5

        for i in range(self.atr_period + 100, len(candles)):
            candle = candles[i]
            price = candle["close"]
            high = candle["high"]
            low = candle["low"]
            volume = candle["volume"]
            ts = candle["time"]

            # Update ATR
            self._update_atr(candles, i)

            # Update support/resistance
            self._update_levels(candles, i)

            # Get funding rate
            funding = self._get_funding(funding_map, ts)

            # Get BTC context
            btc_change_5m = 0
            if i < len(btc_candles):
                btc_now = btc_candles[i]["close"]
                btc_prev = btc_candles[max(0, i-1)]["close"]
                btc_change_5m = (btc_now - btc_prev) / btc_prev * 100 if btc_prev > 0 else 0

            # Check if we have an open trade
            if self.current_trade:
                self._check_exit(price, high, low, ts)
                continue

            # Detect signals
            signal = self._detect_signal(price, high, low, volume, funding, btc_change_5m, ts, candles, i)

            if signal:
                self.total_signals += 1
                self.signals.append(signal)

                # Take trade if signal is strong enough + cooldown
                cooldown_ok = True
                if self.last_trade_time:
                    candles_since = i - self.last_trade_time
                    if candles_since < self.trade_cooldown:
                        cooldown_ok = False

                if signal["score"] >= 6 and cooldown_ok:
                    self._open_trade(signal, price, balance, risk_pct, leverage, ts)
                    self.last_trade_time = i

        # Close any remaining trade
        if self.current_trade:
            self._force_close(candles[-1]["close"], candles[-1]["time"])

        # Print results
        self._print_results()

    def _detect_signal(self, price, high, low, volume, funding, btc_change, ts, candles, i):
        """
        Detect trading signals based on market mechanics.
        Returns signal dict or None.
        """
        score = 0
        direction = None
        reasons = []

        # ═══ SIGNAL 1: LIQUIDITY SWEEP ═══
        # Price breaks below support, recovers above it
        sweep = self._detect_sweep(price, high, low, candles, i)
        if sweep:
            score += 4
            direction = sweep["direction"]
            reasons.append(sweep["reason"])

        # ═══ SIGNAL 2: WYCKOFF SPRING/UPTHRUST ═══
        wyckoff = self._detect_wyckoff(price, high, low, candles, i)
        if wyckoff:
            score += 3
            if not direction:
                direction = wyckoff["direction"]
            reasons.append(wyckoff["reason"])

        # ═══ SIGNAL 3: FUNDING EXTREME ═══
        if funding is not None:
            if funding > 0.06:  # Extreme long → SHORT
                score += 2
                if not direction:
                    direction = "SHORT"
                reasons.append(f"Extreme long funding ({funding:+.4f}%)")
            elif funding < -0.02:  # Extreme short → LONG
                score += 2
                if not direction:
                    direction = "LONG"
                reasons.append(f"Extreme short funding ({funding:+.4f}%)")

        # ═══ SIGNAL 4: BTC AGREEMENT ═══
        if direction == "LONG" and btc_change > 0.1:
            score += 1
            reasons.append(f"BTC confirming ({btc_change:+.2f}%)")
        elif direction == "SHORT" and btc_change < -0.1:
            score += 1
            reasons.append(f"BTC confirming ({btc_change:+.2f}%)")
        elif direction and ((direction == "LONG" and btc_change < -0.3) or
                           (direction == "SHORT" and btc_change > 0.3)):
            score -= 2  # BTC disagrees — reduce confidence
            reasons.append(f"⚠️ BTC diverges ({btc_change:+.2f}%)")

        # ═══ SESSION FILTER ═══
        hour = ts.hour if hasattr(ts, 'hour') else 0
        if 14 <= hour <= 21:  # US session
            score += 1
            reasons.append("US session (high quality)")
        elif 0 <= hour < 8:  # Asia session
            score -= 1
            reasons.append("Asia session (low quality)")

        if score >= 4 and direction:
            return {
                "time": ts,
                "direction": direction,
                "score": score,
                "price": price,
                "reasons": reasons,
                "atr": self.atr,
            }

        return None

    def _detect_sweep(self, price, high, low, candles, i):
        """
        Detect liquidity sweep: price breaks a level then recovers.
        
        Support sweep: price was above support, broke below, recovered above
        Resistance sweep: price was below resistance, broke above, fell below
        """
        if len(self.support_levels) < 2:
            return None

        # Check last 6 candles (30 min) for sweep pattern
        lookback = min(6, i)
        recent = candles[i-lookback:i+1]

        # Support sweep
        for level in self.support_levels[-5:]:
            level_price = level["price"]

            # Find if price broke below this level in recent candles
            broke_below = False
            recovered = False
            break_low = level_price

            for c in recent:
                if c["low"] < level_price * 0.998:  # Broke below by 0.2%
                    broke_below = True
                    break_low = min(break_low, c["low"])

            # Check if current price is above the level
            if broke_below and price > level_price:
                depth_pct = (level_price - break_low) / level_price * 100
                if 0.1 < depth_pct < 2.0:  # Reasonable sweep depth
                    return {
                        "type": "SUPPORT_SWEEP",
                        "direction": "LONG",
                        "level": level_price,
                        "depth_pct": depth_pct,
                        "reason": f"Support sweep at ${level_price:,.0f} (depth {depth_pct:.2f}%)",
                    }

        # Resistance sweep
        for level in self.resistance_levels[-5:]:
            level_price = level["price"]

            broke_above = False
            break_high = level_price

            for c in recent:
                if c["high"] > level_price * 1.002:
                    broke_above = True
                    break_high = max(break_high, c["high"])

            if broke_above and price < level_price:
                depth_pct = (break_high - level_price) / level_price * 100
                if 0.1 < depth_pct < 2.0:
                    return {
                        "type": "RESISTANCE_SWEEP",
                        "direction": "SHORT",
                        "level": level_price,
                        "depth_pct": depth_pct,
                        "reason": f"Resistance sweep at ${level_price:,.0f} (depth {depth_pct:.2f}%)",
                    }

        return None

    def _detect_wyckoff(self, price, high, low, candles, i):
        """
        Detect Wyckoff spring/upthrust.
        
        Spring: Price in range, breaks below range, recovers back into range
        Upthrust: Price in range, breaks above range, falls back into range
        """
        if i < 60:
            return None

        # Get range of last 60 candles (5 hours)
        range_candles = candles[i-60:i]
        range_high = max(c["high"] for c in range_candles)
        range_low = min(c["low"] for c in range_candles)
        range_pct = (range_high - range_low) / range_low * 100

        # Need a reasonable range (0.5% - 3%)
        if range_pct < 0.5 or range_pct > 3.0:
            return None

        # Check last 6 candles for break
        recent = candles[i-6:i+1]

        # Spring: break below range low, recover
        for c in recent:
            if c["low"] < range_low * 0.998 and price > range_low:
                return {
                    "type": "SPRING",
                    "direction": "LONG",
                    "reason": f"Wyckoff Spring — broke below ${range_low:,.0f}, recovered",
                }

        # Upthrust: break above range high, fall back
        for c in recent:
            if c["high"] > range_high * 1.002 and price < range_high:
                return {
                    "type": "UPTHRUST",
                    "direction": "SHORT",
                    "reason": f"Wyckoff Upthrust — broke above ${range_high:,.0f}, rejected",
                }

        return None

    def _update_atr(self, candles, i):
        """Calculate ATR from candles."""
        if i < self.atr_period + 1:
            return

        true_ranges = []
        for j in range(i - self.atr_period, i):
            tr1 = candles[j]["high"] - candles[j]["low"]
            tr2 = abs(candles[j]["high"] - candles[j-1]["close"])
            tr3 = abs(candles[j]["low"] - candles[j-1]["close"])
            true_ranges.append(max(tr1, tr2, tr3))

        self.atr = sum(true_ranges) / len(true_ranges) if true_ranges else 0

    def _update_levels(self, candles, i):
        """Update support/resistance from recent price action."""
        if i < 100:
            return

        # Use swing highs/lows from last 200 candles
        lookback = min(200, i)
        recent = candles[i-lookback:i]

        # Find swing lows (support)
        self.support_levels = []
        for j in range(2, len(recent) - 2):
            if (recent[j]["low"] < recent[j-1]["low"] and
                recent[j]["low"] < recent[j-2]["low"] and
                recent[j]["low"] < recent[j+1]["low"] and
                recent[j]["low"] < recent[j+2]["low"]):
                self.support_levels.append({
                    "price": recent[j]["low"],
                    "strength": 1,
                })

        # Find swing highs (resistance)
        self.resistance_levels = []
        for j in range(2, len(recent) - 2):
            if (recent[j]["high"] > recent[j-1]["high"] and
                recent[j]["high"] > recent[j-2]["high"] and
                recent[j]["high"] > recent[j+1]["high"] and
                recent[j]["high"] > recent[j+2]["high"]):
                self.resistance_levels.append({
                    "price": recent[j]["high"],
                    "strength": 1,
                })

        # Sort and keep top levels
        self.support_levels.sort(key=lambda x: x["price"])
        self.resistance_levels.sort(key=lambda x: x["price"])

    def _open_trade(self, signal, price, balance, risk_pct, leverage, ts):
        """Open a new trade."""
        direction = signal["direction"]
        atr = signal["atr"]

        if atr == 0:
            return

        # ATR-based SL/TP
        sl_dist = atr * 1.5
        tp_dist = atr * 2.5

        if direction == "LONG":
            sl = price - sl_dist
            tp = price + tp_dist
        else:
            sl = price + sl_dist
            tp = price - tp_dist

        risk = abs(price - sl)
        reward = abs(tp - price)
        rr = reward / risk if risk > 0 else 0

        if rr < 1.5:
            return

        # Position sizing
        risk_amount = balance * (risk_pct / 100)
        sl_pct = risk / price
        margin = risk_amount / sl_pct / leverage
        margin = min(margin, balance * 0.9)

        self.current_trade = {
            "direction": direction,
            "entry": price,
            "sl": sl,
            "tp": tp,
            "margin": margin,
            "rr": rr,
            "atr": atr,
            "time": ts,
            "score": signal["score"],
            "reasons": signal["reasons"],
        }
        self.trades_taken += 1

    def _check_exit(self, price, high, low, ts):
        """Check if current trade should be closed."""
        if not self.current_trade:
            return

        trade = self.current_trade
        direction = trade["direction"]

        hit_sl = False
        hit_tp = False

        if direction == "LONG":
            if low <= trade["sl"]:
                hit_sl = True
            elif high >= trade["tp"]:
                hit_tp = True
        else:
            if high >= trade["sl"]:
                hit_sl = True
            elif low <= trade["tp"]:
                hit_tp = True

        if hit_sl:
            self._close_trade(trade["sl"], "SL", ts)
        elif hit_tp:
            self._close_trade(trade["tp"], "TP", ts)

    def _force_close(self, price, ts):
        """Force close at current price."""
        if self.current_trade:
            self._close_trade(price, "FORCED", ts)

    def _close_trade(self, exit_price, result, ts):
        """Close trade and record result."""
        trade = self.current_trade
        direction = trade["direction"]
        entry = trade["entry"]

        if direction == "LONG":
            pnl_pct = (exit_price - entry) / entry * 100
        else:
            pnl_pct = (entry - exit_price) / entry * 100

        # Apply leverage
        leveraged_pnl = pnl_pct * 5  # 5x leverage
        pnl_usd = trade["margin"] * (leveraged_pnl / 100)

        if result == "TP":
            self.wins += 1
        elif result == "SL":
            self.losses += 1
        else:
            # Forced close — count as win if profitable
            if pnl_pct > 0:
                self.wins += 1
            else:
                self.losses += 1

        self.total_pnl += pnl_usd
        self.peak_balance = max(self.peak_balance, 10000 + self.total_pnl)
        drawdown = (self.peak_balance - (10000 + self.total_pnl)) / self.peak_balance * 100
        self.max_drawdown = max(self.max_drawdown, drawdown)

        self.trades.append({
            "time": str(ts),
            "direction": direction,
            "entry": round(entry, 2),
            "exit": round(exit_price, 2),
            "sl": round(trade["sl"], 2),
            "tp": round(trade["tp"], 2),
            "rr": trade["rr"],
            "result": result,
            "pnl_pct": round(pnl_pct, 3),
            "pnl_usd": round(pnl_usd, 2),
            "score": trade["score"],
            "reasons": trade["reasons"],
        })

        self.current_trade = None

    async def fetch_candles(self, symbol, interval, days):
        """Fetch historical candles from Binance."""
        candles = []
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)

        async with aiohttp.ClientSession() as session:
            while start_time < end_time:
                try:
                    async with session.get(
                        "https://api.binance.com/api/v3/klines",
                        params={
                            "symbol": symbol,
                            "interval": interval,
                            "startTime": start_time,
                            "limit": 1000,
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not data:
                                break
                            for k in data:
                                candles.append({
                                    "time": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                                    "open": float(k[1]),
                                    "high": float(k[2]),
                                    "low": float(k[3]),
                                    "close": float(k[4]),
                                    "volume": float(k[5]),
                                })
                            start_time = data[-1][0] + 1
                        else:
                            print(f"  ⚠️ API error {resp.status}")
                            break
                except Exception as e:
                    print(f"  ⚠️ Fetch error: {e}")
                    break
                await asyncio.sleep(0.1)  # Rate limit

        return candles

    async def fetch_funding(self, symbol, days):
        """Fetch historical funding rates from Binance."""
        funding = []
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)

        async with aiohttp.ClientSession() as session:
            while start_time < end_time:
                try:
                    async with session.get(
                        "https://fapi.binance.com/fapi/v1/fundingRate",
                        params={
                            "symbol": symbol,
                            "startTime": start_time,
                            "limit": 1000,
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not data:
                                break
                            for f in data:
                                funding.append({
                                    "time": datetime.fromtimestamp(f["fundingTime"] / 1000, tz=timezone.utc),
                                    "rate": float(f["fundingRate"]),
                                })
                            start_time = data[-1]["fundingTime"] + 1
                        else:
                            break
                except:
                    break
                await asyncio.sleep(0.1)

        return funding

    def _build_funding_map(self, funding_data):
        """Build time-indexed funding map."""
        return {f["time"]: f["rate"] for f in funding_data}

    def _get_funding(self, funding_map, ts):
        """Get nearest funding rate for timestamp."""
        if not funding_map:
            return None

        # Find nearest funding time (within 8 hours)
        nearest = min(funding_map.keys(), key=lambda t: abs((t - ts).total_seconds()))
        diff = abs((nearest - ts).total_seconds())

        if diff < 8 * 3600:  # Within 8 hours
            return funding_map[nearest] * 100  # Convert to percentage

        return None

    def _print_results(self):
        """Print backtest results."""
        total = self.wins + self.losses
        win_rate = (self.wins / total * 100) if total > 0 else 0
        avg_win = 0
        avg_loss = 0

        winning_trades = [t for t in self.trades if t["result"] == "TP"]
        losing_trades = [t for t in self.trades if t["result"] == "SL"]

        if winning_trades:
            avg_win = sum(t["pnl_pct"] for t in winning_trades) / len(winning_trades)
        if losing_trades:
            avg_loss = sum(t["pnl_pct"] for t in losing_trades) / len(losing_trades)

        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

        print("\n" + "=" * 70)
        print("BACKTEST RESULTS")
        print("=" * 70)
        print(f"\n📊 Performance:")
        print(f"  Total Signals:     {self.total_signals}")
        print(f"  Trades Taken:      {total}")
        print(f"  Wins:              {self.wins}")
        print(f"  Losses:            {self.losses}")
        print(f"  Win Rate:          {win_rate:.1f}%")
        print(f"  Avg Win:           {avg_win:+.2f}%")
        print(f"  Avg Loss:          {avg_loss:+.2f}%")
        print(f"  Expectancy:        {expectancy:+.3f}% per trade")
        print(f"\n💰 P&L:")
        print(f"  Starting Balance:  $10,000")
        print(f"  Final Balance:     ${10000 + self.total_pnl:,.2f}")
        print(f"  Total P&L:         ${self.total_pnl:+,.2f}")
        print(f"  Max Drawdown:      {self.max_drawdown:.1f}%")
        print(f"\n📋 Trade Log:")
        print(f"  {'Time':<22} {'Dir':<6} {'Entry':<10} {'Exit':<10} {'SL':<10} {'TP':<10} {'R:R':<5} {'Result':<6} {'PnL':<8}")
        print(f"  {'-'*22} {'-'*6} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*5} {'-'*6} {'-'*8}")

        for t in self.trades[-50:]:  # Show last 50 trades
            result_emoji = "✅" if t["result"] == "TP" else "❌" if t["result"] == "SL" else "⏹️"
            print(f"  {str(t['time'])[:22]:<22} {t['direction']:<6} ${t['entry']:<9} ${t['exit']:<9} ${t['sl']:<9} ${t['tp']:<9} 1:{t['rr']:<3} {result_emoji} {t['pnl_pct']:+.2f}%")

        # Save to file
        os.makedirs("data/backtest", exist_ok=True)
        with open("data/backtest/results.json", "w") as f:
            json.dump({
                "total_signals": self.total_signals,
                "trades_taken": total,
                "wins": self.wins,
                "losses": self.losses,
                "win_rate": round(win_rate, 1),
                "avg_win": round(avg_win, 3),
                "avg_loss": round(avg_loss, 3),
                "expectancy": round(expectancy, 4),
                "total_pnl": round(self.total_pnl, 2),
                "max_drawdown": round(self.max_drawdown, 1),
                "trades": self.trades,
            }, f, indent=2, default=str)

        print(f"\n💾 Full results saved to data/backtest/results.json")
        print("=" * 70)


if __name__ == "__main__":
    engine = BacktestEngine()
    asyncio.run(engine.run(days=30))
