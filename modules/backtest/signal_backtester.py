"""
Smart Money System - Signal Backtester
Runs the8-checkpoint signal pipeline against historical data.
Proves whether the system works or not.
"""
import asyncio
import json
import os
import sys
import time
import numpy as np
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.backtest.data_fetcher import DataFetcher


class SignalBacktester:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.fetcher = DataFetcher()
        self.results = []

    async def run(self, symbol="ETHUSDT", days=90, check_interval=300):
        """
        Run backtest.
        check_interval: seconds between checks (300 = 5 min)
        """
        print("=" * 60)
        print("SIGNAL PIPELINE BACKTEST")
        print("=" * 60)
        print(f"Symbol: {symbol}")
        print(f"Period: {days} days")
        print(f"Check interval: {check_interval}s ({check_interval//60} min)")
        print()

        # Fetch data
        print("[1/3] Fetching historical data...")
        candles_1m = await self.fetcher.get_historical_data(symbol, "1m", days)
        candles_5m = await self.fetcher.get_historical_data(symbol, "5m", days)
        candles_15m = await self.fetcher.get_historical_data(symbol, "15m", days)
        candles_1h = await self.fetcher.get_historical_data(symbol, "1h", days)

        print(f"  1m: {len(candles_1m)} candles")
        print(f"  5m: {len(candles_5m)} candles")
        print(f"  15m: {len(candles_15m)} candles")
        print(f"  1h: {len(candles_1h)} candles")

        if len(candles_1m) < 1000:
            print("ERROR: Not enough data")
            return None

        # Build CVD from 1m candles
        print("[2/3] Building CVD and indicators...")
        cvd_data = self._build_cvd(candles_1m)
        oi_data = self._build_oi_proxy(candles_1m)

        # Run simulation
        print("[3/3] Running simulation...")
        results = self._simulate(candles_1m, candles_5m, candles_15m, candles_1h,
                                  cvd_data, oi_data, check_interval)

        # Analyze results
        analysis = self._analyze(results)

        # Print report
        self._print_report(analysis)

        # Save
        with open(os.path.join(self.data_dir, "backtest_results.json"), "w") as f:
            json.dump(analysis, f, indent=2, default=str)

        return analysis

    def _build_cvd(self, candles):
        """Build CVD from1m candles (approximate using close vs open)"""
        cvd = 0
        cvd_history = []
        for c in candles:
            # Approximate delta: if close > open, buying dominated
            delta = (c["close"] - c["open"]) / c["open"] * c["volume"]
            cvd += delta
            cvd_history.append({
                "time": c["timestamp"],
                "cvd": cvd,
                "delta": delta,
                "price": c["close"],
            })
        return cvd_history

    def _build_oi_proxy(self, candles):
        """Build OI proxy from volume * price action"""
        oi_history = []
        for i, c in enumerate(candles):
            # OI proxy: volume weighted by absolute price change
            # Rising volume + rising price = new longs
            # Rising volume + falling price = new shorts
            price_change = (c["close"] - c["open"]) / c["open"]
            oi_proxy = c["volume"] * abs(price_change)
            oi_history.append({
                "time": c["timestamp"],
                "oi": oi_proxy,
                "delta": price_change,
            })
        return oi_history

    def _simulate(self, c1m, c5m, c15m, c1h, cvd_data, oi_data, interval):
        """Run signal pipeline at each interval"""
        results = []
        check_points = list(range(500, len(c1m) - 1440, interval // 60))  # Skip first500, leave 24h for outcome

        total = len(check_points)
        print(f"  Checking {total} points...")

        for idx, i in enumerate(check_points):
            if idx % 100 == 0:
                print(f"  Progress: {idx}/{total} ({idx/total*100:.0f}%)")

            price = c1m[i]["close"]
            timestamp = c1m[i]["timestamp"]

            # Calculate all checkpoints
            checkpoints = self._evaluate_checkpoints(c1m, c5m, c15m, c1h, cvd_data, oi_data, i)

            # Calculate score
            total_score = sum(cp["score"] for cp in checkpoints)
            passed = sum(1 for cp in checkpoints if cp["status"] == "PASS")
            bullish_cps = sum(1 for cp in checkpoints if cp["score"] > 0)
            bearish_cps = sum(1 for cp in checkpoints if cp["score"] < 0)

            # Direction
            if total_score >= 3:
                direction = "LONG"
            elif total_score <= -3:
                direction = "SHORT"
            else:
                direction = None

            # Check outcome at 1h, 4h, 24h
            outcome = self._check_outcome(c1m, i, direction)

            if direction and passed >= 3:
                results.append({
                    "index": i,
                    "timestamp": str(timestamp),
                    "price": price,
                    "direction": direction,
                    "score": total_score,
                    "passed": passed,
                    "bullish_cps": bullish_cps,
                    "bearish_cps": bearish_cps,
                    "checkpoints": checkpoints,
                    "outcome_1h": outcome["1h"],
                    "outcome_4h": outcome["4h"],
                    "outcome_24h": outcome["24h"],
                    "correct_1h": outcome["correct_1h"],
                    "correct_4h": outcome["correct_4h"],
                    "correct_24h": outcome["correct_24h"],
                })

        self.results = results
        return results

    def _evaluate_checkpoints(self, c1m, c5m, c15m, c1h, cvd_data, oi_data, idx):
        """Evaluate all8 checkpoints at a given index"""
        price = c1m[idx]["close"]
        cps = []

        # 1. DIRECTION (CVD 5m change)
        if idx >= 300:
            cvd_now = cvd_data[idx]["cvd"]
            cvd_5m_ago = cvd_data[idx - 300]["cvd"]
            cvd_5m = cvd_now - cvd_5m_ago
            if cvd_5m > 50:
                cps.append({"name": "DIRECTION", "status": "PASS", "score": 2})
            elif cvd_5m < -50:
                cps.append({"name": "DIRECTION", "status": "PASS", "score": -2})
            elif cvd_5m > 20:
                cps.append({"name": "DIRECTION", "status": "WEAK", "score": 1})
            elif cvd_5m < -20:
                cps.append({"name": "DIRECTION", "status": "WEAK", "score": -1})
            else:
                cps.append({"name": "DIRECTION", "status": "FAIL", "score": 0})
        else:
            cps.append({"name": "DIRECTION", "status": "FAIL", "score": 0})

        # 2. DIVERGENCE (price vs CVD)
        if idx >= 600:
            price_5m_ago = c1m[idx - 300]["close"]
            price_now = c1m[idx]["close"]
            cvd_5m_ago = cvd_data[idx - 300]["cvd"]
            cvd_now = cvd_data[idx]["cvd"]

            # Bullish divergence: price down, CVD up
            if price_now < price_5m_ago * 0.998 and cvd_now > cvd_5m_ago:
                cps.append({"name": "DIVERGENCE", "status": "PASS", "score": 3})
            # Bearish divergence: price up, CVD down
            elif price_now > price_5m_ago * 1.002 and cvd_now < cvd_5m_ago:
                cps.append({"name": "DIVERGENCE", "status": "PASS", "score": -3})
            else:
                cps.append({"name": "DIVERGENCE", "status": "NONE", "score": 0})
        else:
            cps.append({"name": "DIVERGENCE", "status": "NONE", "score": 0})

        # 3. TOXICITY (volume volatility proxy)
        if idx >= 60:
            recent_vols = [c1m[j]["volume"] for j in range(idx-60, idx)]
            avg_vol = np.mean(recent_vols)
            std_vol = np.std(recent_vols)
            current_vol = c1m[idx]["volume"]
            if avg_vol > 0 and current_vol > avg_vol + 2 * std_vol:
                cps.append({"name": "TOXICITY", "status": "DANGER", "score": 0})
            else:
                cps.append({"name": "TOXICITY", "status": "CLEAR", "score": 0})
        else:
            cps.append({"name": "TOXICITY", "status": "CLEAR", "score": 0})

        # 4. MOMENTUM (price acceleration)
        if idx >= 60:
            price_10s_ago = c1m[idx - 10]["close"] if idx >= 10 else price
            price_30s_ago = c1m[idx - 30]["close"] if idx >= 30 else price
            accel_10s = price - price_10s_ago
            accel_30s = price - price_30s_ago

            if accel_10s > 0 and accel_30s > 0:
                cps.append({"name": "MOMENTUM", "status": "PASS", "score": 2})
            elif accel_10s < 0 and accel_30s < 0:
                cps.append({"name": "MOMENTUM", "status": "PASS", "score": -2})
            elif abs(accel_10s) < price * 0.001:
                cps.append({"name": "MOMENTUM", "status": "FLAT", "score": 0})
            else:
                cps.append({"name": "MOMENTUM", "status": "WEAK", "score": 1 if accel_10s > 0 else -1})
        else:
            cps.append({"name": "MOMENTUM", "status": "FLAT", "score": 0})

        # 5. INSTITUTIONAL (volume-weighted price action)
        if idx >= 120:
            # Large volume candles = institutional activity
            vol_1h = sum(c1m[j]["volume"] for j in range(idx-60, idx))
            vol_2h = sum(c1m[j]["volume"] for j in range(idx-120, idx))
            vol_ratio = vol_1h / (vol_2h / 2) if vol_2h > 0 else 1

            price_1h = (c1m[idx]["close"] - c1m[idx-60]["close"]) / c1m[idx-60]["close"]

            if vol_ratio > 1.5 and price_1h > 0.005:
                cps.append({"name": "INSTITUTIONAL", "status": "PASS", "score": 2})
            elif vol_ratio > 1.5 and price_1h < -0.005:
                cps.append({"name": "INSTITUTIONAL", "status": "PASS", "score": -2})
            else:
                cps.append({"name": "INSTITUTIONAL", "status": "NEUTRAL", "score": 0})
        else:
            cps.append({"name": "INSTITUTIONAL", "status": "NEUTRAL", "score": 0})

        # 6. LIQ TARGET (price position in range)
        if idx >= 1440:
            high_24h = max(c1m[j]["high"] for j in range(idx-1440, idx))
            low_24h = min(c1m[j]["low"] for j in range(idx-1440, idx))
            range_24h = high_24h - low_24h
            position = (price - low_24h) / range_24h if range_24h > 0 else 0.5

            if position > 0.8:
                cps.append({"name": "LIQ TARGET", "status": "PASS", "score": -1})  # Near high = likely pullback
            elif position < 0.2:
                cps.append({"name": "LIQ TARGET", "status": "PASS", "score": 1})  # Near low = likely bounce
            else:
                cps.append({"name": "LIQ TARGET", "status": "NEUTRAL", "score": 0})
        else:
            cps.append({"name": "LIQ TARGET", "status": "NEUTRAL", "score": 0})

        # 7. ORDER BOOK (approximate from volume profile)
        if idx >= 100:
            # Volume concentration above vs below price
            vol_above = sum(c1m[j]["volume"] for j in range(idx-100, idx) if c1m[j]["close"] > price)
            vol_below = sum(c1m[j]["volume"] for j in range(idx-100, idx) if c1m[j]["close"] < price)
            total_vol = vol_above + vol_below

            if total_vol > 0:
                imbalance = (vol_below - vol_above) / total_vol
                if imbalance > 0.2:
                    cps.append({"name": "ORDER BOOK", "status": "PASS", "score": 1})
                elif imbalance < -0.2:
                    cps.append({"name": "ORDER BOOK", "status": "PASS", "score": -1})
                else:
                    cps.append({"name": "ORDER BOOK", "status": "NEUTRAL", "score": 0})
            else:
                cps.append({"name": "ORDER BOOK", "status": "NEUTRAL", "score": 0})
        else:
            cps.append({"name": "ORDER BOOK", "status": "NEUTRAL", "score": 0})

        # 8. MTF ALIGN (multi-timeframe)
        mtf_aligned = 0
        for tf_data in [c5m, c15m, c1h]:
            # Find corresponding candle
            tf_idx = min(idx // (len(c1m) // len(tf_data)), len(tf_data) - 1)
            if tf_idx >= 5:
                close_now = tf_data[tf_idx]["close"]
                close_5_ago = tf_data[tf_idx - 5]["close"]
                if close_now > close_5_ago * 1.002:
                    mtf_aligned += 1
                elif close_now < close_5_ago * 0.998:
                    mtf_aligned -= 1

        if mtf_aligned >= 2:
            cps.append({"name": "MTF ALIGN", "status": "PASS", "score": 2})
        elif mtf_aligned <= -2:
            cps.append({"name": "MTF ALIGN", "status": "PASS", "score": -2})
        elif mtf_aligned == 1:
            cps.append({"name": "MTF ALIGN", "status": "WEAK", "score": 1})
        elif mtf_aligned == -1:
            cps.append({"name": "MTF ALIGN", "status": "WEAK", "score": -1})
        else:
            cps.append({"name": "MTF ALIGN", "status": "FAIL", "score": 0})

        return cps

    def _check_outcome(self, candles, idx, direction):
        """Check price outcome at 1h, 4h, 24h"""
        price = candles[idx]["close"]

        result = {"1h": None, "4h": None, "24h": None, "correct_1h": None, "correct_4h": None, "correct_24h": None}

        for hours, label in [(1, "1h"), (4, "4h"), (24, "24h")]:
            future_idx = idx + hours * 60
            if future_idx < len(candles):
                future_price = candles[future_idx]["close"]
                change_pct = (future_price - price) / price * 100
                result[label] = round(change_pct, 2)

                if direction == "LONG":
                    result[f"correct_{label}"] = change_pct > 0
                elif direction == "SHORT":
                    result[f"correct_{label}"] = change_pct < 0

        return result

    def _analyze(self, results):
        """Analyze backtest results"""
        if not results:
            return {"error": "No signals found"}

        total = len(results)

        # Win rates
        for period in ["1h", "4h", "24h"]:
            valid = [r for r in results if r[f"correct_{period}"] is not None]
            if valid:
                wins = sum(1 for r in valid if r[f"correct_{period}"])
                losses = sum(1 for r in valid if not r[f"correct_{period}"])
                win_rate = wins / len(valid) * 100

                # Average return
                avg_return = np.mean([r[f"outcome_{period}"] for r in valid])

                # By direction
                longs = [r for r in valid if r["direction"] == "LONG"]
                shorts = [r for r in valid if r["direction"] == "SHORT"]

                long_wr = sum(1 for r in longs if r[f"correct_{period}"]) / len(longs) * 100 if longs else 0
                short_wr = sum(1 for r in shorts if r[f"correct_{period}"]) / len(shorts) * 100 if shorts else 0

                results[0][f"analysis_{period}"] = {
                    "total_signals": total,
                    "valid_signals": len(valid),
                    "wins": wins,
                    "losses": losses,
                    "win_rate": round(win_rate, 1),
                    "avg_return": round(avg_return, 2),
                    "long_signals": len(longs),
                    "long_win_rate": round(long_wr, 1),
                    "short_signals": len(shorts),
                    "short_win_rate": round(short_wr, 1),
                }

        # By score range
        score_analysis = {}
        for score_range in [(-10, -5), (-5, -3), (3, 5), (5, 10)]:
            low, high = score_range
            subset = [r for r in results if low <= r["score"] < high]
            if subset:
                valid_4h = [r for r in subset if r["correct_4h"] is not None]
                if valid_4h:
                    wr = sum(1 for r in valid_4h if r["correct_4h"]) / len(valid_4h) * 100
                    score_analysis[f"{low} to {high}"] = {
                        "count": len(subset),
                        "win_rate_4h": round(wr, 1),
                    }

        # By checkpoints passed
        cp_analysis = {}
        for cp_count in [3, 4, 5, 6, 7, 8]:
            subset = [r for r in results if r["passed"] == cp_count]
            if subset:
                valid_4h = [r for r in subset if r["correct_4h"] is not None]
                if valid_4h:
                    wr = sum(1 for r in valid_4h if r["correct_4h"]) / len(valid_4h) * 100
                    cp_analysis[f"{cp_count}_cp"] = {
                        "count": len(subset),
                        "win_rate_4h": round(wr, 1),
                    }

        return {
            "total_signals": total,
            "by_period": {p: results[0].get(f"analysis_{p}") for p in ["1h", "4h", "24h"]},
            "by_score": score_analysis,
            "by_checkpoints": cp_analysis,
            "sample_signals": results[:5],  # First5 for inspection
        }

    def _print_report(self, analysis):
        """Print formatted report"""
        print()
        print("=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print(f"Total signals: {analysis['total_signals']}")
        print()

        for period in ["1h", "4h", "24h"]:
            data = analysis.get("by_period", {}).get(period)
            if data:
                print(f"--- {period.upper()} ---")
                print(f"  Win Rate: {data['win_rate']}% ({data['wins']}/{data['valid_signals']})")
                print(f"  Avg Return: {data['avg_return']:+.2f}%")
                print(f"  LONG: {data['long_signals']} signals, {data['long_win_rate']}% win rate")
                print(f"  SHORT: {data['short_signals']} signals, {data['short_win_rate']}% win rate")
                print()

        print("--- BY SCORE RANGE ---")
        for score_range, data in analysis.get("by_score", {}).items():
            print(f"  Score {score_range}: {data['count']} signals, {data['win_rate_4h']}% win rate (4h)")

        print()
        print("--- BY CHECKPOINTS PASSED ---")
        for cp, data in analysis.get("by_checkpoints", {}).items():
            print(f"  {cp}: {data['count']} signals, {data['win_rate_4h']}% win rate (4h)")

        print()
        print("=" * 60)

        # Verdict
        wr_4h = analysis.get("by_period", {}).get("4h", {}).get("win_rate", 0)
        if wr_4h >= 60:
            print("✅ VERDICT: EDGE EXISTS — system works")
        elif wr_4h >= 55:
            print("🟡 VERDICT: MARGINAL EDGE — needs optimization")
        elif wr_4h >= 50:
            print("⚠️ VERDICT: NO EDGE — system is random")
        else:
            print("❌ VERDICT: NEGATIVE EDGE — system loses money")
        print("=" * 60)


async def main():
    bt = SignalBacktester()
    await bt.run(days=90, check_interval=300)


if __name__ == "__main__":
    asyncio.run(main())
