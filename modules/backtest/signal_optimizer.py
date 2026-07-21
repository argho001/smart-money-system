"""
Smart Money System - Signal Optimizer
Tests each checkpoint individually and finds the best combination.
"""
import asyncio
import json
import os
import sys
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from modules.backtest.data_fetcher import DataFetcher


class SignalOptimizer:
    def __init__(self):
        self.fetcher = DataFetcher()

    async def run(self, symbol="ETHUSDT", days=90):
        """Test each checkpoint individually, then find best combination"""
        print("=" * 60)
        print("SIGNAL OPTIMIZER — Finding What Actually Works")
        print("=" * 60)

        # Fetch data
        print("[1/4] Fetching data...")
        c1m = await self.fetcher.get_historical_data(symbol, "1m", days)
        c5m = await self.fetcher.get_historical_data(symbol, "5m", days)
        c15m = await self.fetcher.get_historical_data(symbol, "15m", days)
        c1h = await self.fetcher.get_historical_data(symbol, "1h", days)
        print(f"  1m: {len(c1m)}, 5m: {len(c5m)}, 15m: {len(c15m)}, 1h: {len(c1h)}")

        # Build CVD
        print("[2/4] Building indicators...")
        cvd = self._build_cvd(c1m)

        # Test each checkpoint individually
        print("[3/4] Testing each checkpoint individually...")
        checkpoint_results = self._test_individual_checkpoints(c1m, c5m, c15m, c1h, cvd)

        # Find best combination
        print("[4/4] Finding best combination...")
        best_combo = self._find_best_combination(c1m, c5m, c15m, c1h, cvd, checkpoint_results)

        # Print report
        self._print_report(checkpoint_results, best_combo)

        return {"checkpoints": checkpoint_results, "best_combo": best_combo}

    def _build_cvd(self, candles):
        cvd = 0
        history = []
        for c in candles:
            delta = (c["close"] - c["open"]) / c["open"] * c["volume"]
            cvd += delta
            history.append({"cvd": cvd, "delta": delta, "price": c["close"]})
        return history

    def _test_individual_checkpoints(self, c1m, c5m, c15m, c1h, cvd):
        """Test each checkpoint's predictive power individually"""
        results = {}

        # Define checkpoints with different threshold variations
        checkpoints = {
            "CVD_5m": self._test_cvd_5m(c1m, cvd),
            "CVD_15m": self._test_cvd_15m(c1m, cvd),
            "CVD_1h": self._test_cvd_1h(c1m, cvd),
            "CVD_divergence": self._test_cvd_divergence(c1m, cvd),
            "Momentum_10m": self._test_momentum(c1m, 10),
            "Momentum_30m": self._test_momentum(c1m, 30),
            "Momentum_1h": self._test_momentum(c1m, 60),
            "Volume_surge": self._test_volume_surge(c1m),
            "Price_position": self._test_price_position(c1m),
            "MTF_5m": self._test_mtf(c1m, c5m, 5),
            "MTF_15m": self._test_mtf(c1m, c15m, 15),
            "MTF_1h": self._test_mtf(c1m, c1h, 60),
            "Trend_strength": self._test_trend_strength(c1m),
            "Volatility_regime": self._test_volatility(c1m),
            "Mean_reversion": self._test_mean_reversion(c1m),
        }

        return checkpoints

    def _test_cvd_5m(self, c1m, cvd):
        """Test: CVD change over 5 minutes"""
        signals = []
        for i in range(300, len(c1m) - 1440, 300):
            cvd_5m = cvd[i]["cvd"] - cvd[i-300]["cvd"]
            if cvd_5m > 50:
                direction = "LONG"
            elif cvd_5m < -50:
                direction = "SHORT"
            else:
                continue
            outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
            correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
            signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, "CVD 5m")

    def _test_cvd_15m(self, c1m, cvd):
        """Test: CVD change over 15 minutes"""
        signals = []
        for i in range(900, len(c1m) - 1440, 300):
            cvd_15m = cvd[i]["cvd"] - cvd[i-900]["cvd"]
            if cvd_15m > 100:
                direction = "LONG"
            elif cvd_15m < -100:
                direction = "SHORT"
            else:
                continue
            outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
            correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
            signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, "CVD 15m")

    def _test_cvd_1h(self, c1m, cvd):
        """Test: CVD change over 1 hour"""
        signals = []
        for i in range(3600, len(c1m) - 1440, 300):
            cvd_1h = cvd[i]["cvd"] - cvd[i-3600]["cvd"]
            if cvd_1h > 200:
                direction = "LONG"
            elif cvd_1h < -200:
                direction = "SHORT"
            else:
                continue
            outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
            correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
            signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, "CVD 1h")

    def _test_cvd_divergence(self, c1m, cvd):
        """Test: CVD-Price divergence"""
        signals = []
        for i in range(600, len(c1m) - 1440, 300):
            price_change = (c1m[i]["close"] - c1m[i-300]["close"]) / c1m[i-300]["close"]
            cvd_change = cvd[i]["cvd"] - cvd[i-300]["cvd"]

            # Bullish divergence: price down, CVD up
            if price_change < -0.003 and cvd_change > 50:
                direction = "LONG"
            # Bearish divergence: price up, CVD down
            elif price_change > 0.003 and cvd_change < -50:
                direction = "SHORT"
            else:
                continue

            outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
            correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
            signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, "CVD Divergence")

    def _test_momentum(self, c1m, period):
        """Test: Price momentum over N minutes"""
        signals = []
        for i in range(period, len(c1m) - 1440, 300):
            price_change = (c1m[i]["close"] - c1m[i-period]["close"]) / c1m[i-period]["close"]

            if price_change > 0.005:
                direction = "LONG"
            elif price_change < -0.005:
                direction = "SHORT"
            else:
                continue

            outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
            correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
            signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, f"Momentum {period}m")

    def _test_volume_surge(self, c1m):
        """Test: Volume surge (unusual volume)"""
        signals = []
        for i in range(100, len(c1m) - 1440, 300):
            recent_vol = np.mean([c1m[j]["volume"] for j in range(i-20, i)])
            avg_vol = np.mean([c1m[j]["volume"] for j in range(i-100, i)])
            std_vol = np.std([c1m[j]["volume"] for j in range(i-100, i)])

            if avg_vol > 0 and recent_vol > avg_vol + 2 * std_vol:
                # Volume surge — direction from price
                price_change = (c1m[i]["close"] - c1m[i-5]["close"]) / c1m[i-5]["close"]
                direction = "LONG" if price_change > 0 else "SHORT"

                outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
                correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
                signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, "Volume Surge")

    def _test_price_position(self, c1m):
        """Test: Price position in 24h range"""
        signals = []
        for i in range(1440, len(c1m) - 1440, 300):
            high_24h = max(c1m[j]["high"] for j in range(i-1440, i))
            low_24h = min(c1m[j]["low"] for j in range(i-1440, i))
            range_24h = high_24h - low_24h
            position = (c1m[i]["close"] - low_24h) / range_24h if range_24h > 0 else 0.5

            if position > 0.85:
                direction = "SHORT"  # Near high = mean reversion
            elif position < 0.15:
                direction = "LONG"  # Near low = mean reversion
            else:
                continue

            outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
            correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
            signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, "Price Position")

    def _test_mtf(self, c1m, c_tf, tf_minutes):
        """Test: Multi-timeframe alignment"""
        signals = []
        ratio = len(c1m) // len(c_tf)

        for i in range(5 * ratio, len(c1m) - 1440, 300):
            tf_idx = min(i // ratio, len(c_tf) - 6)
            if tf_idx < 5:
                continue

            close_now = c_tf[tf_idx]["close"]
            close_5_ago = c_tf[tf_idx - 5]["close"]
            change = (close_now - close_5_ago) / close_5_ago

            if change > 0.005:
                direction = "LONG"
            elif change < -0.005:
                direction = "SHORT"
            else:
                continue

            outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
            correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
            signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, f"MTF {tf_minutes}m")

    def _test_trend_strength(self, c1m):
        """Test: ADX-like trend strength"""
        signals = []
        for i in range(200, len(c1m) - 1440, 300):
            # Efficiency ratio
            net_move = abs(c1m[i]["close"] - c1m[i-100]["close"])
            sum_moves = sum(abs(c1m[j]["close"] - c1m[j-1]["close"]) for j in range(i-100, i))
            efficiency = net_move / sum_moves if sum_moves > 0 else 0

            if efficiency > 0.4:
                # Strong trend — direction from recent price
                price_change = (c1m[i]["close"] - c1m[i-20]["close"]) / c1m[i-20]["close"]
                direction = "LONG" if price_change > 0 else "SHORT"

                outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
                correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
                signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, "Trend Strength")

    def _test_volatility(self, c1m):
        """Test: Volatility regime"""
        signals = []
        for i in range(100, len(c1m) - 1440, 300):
            # Recent volatility vs historical
            recent_range = max(c1m[j]["high"] for j in range(i-20, i)) - min(c1m[j]["low"] for j in range(i-20, i))
            avg_range = np.mean([c1m[j]["high"] - c1m[j]["low"] for j in range(i-100, i)])

            if avg_range > 0 and recent_range / avg_range > 2:
                # High volatility — mean reversion likely
                price_change = (c1m[i]["close"] - c1m[i-5]["close"]) / c1m[i-5]["close"]
                direction = "SHORT" if price_change > 0 else "LONG"  # Contrarian

                outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
                correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
                signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, "Volatility Regime")

    def _test_mean_reversion(self, c1m):
        """Test: Mean reversion from moving average"""
        signals = []
        for i in range(200, len(c1m) - 1440, 300):
            sma_50 = np.mean([c1m[j]["close"] for j in range(i-50, i)])
            sma_200 = np.mean([c1m[j]["close"] for j in range(i-200, i)])
            price = c1m[i]["close"]

            # Distance from SMA
            dist_50 = (price - sma_50) / sma_50
            dist_200 = (price - sma_200) / sma_200

            if dist_50 < -0.02 and dist_200 < -0.03:
                direction = "LONG"  # Oversold
            elif dist_50 > 0.02 and dist_200 > 0.03:
                direction = "SHORT"  # Overbought
            else:
                continue

            outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
            correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
            signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return self._calc_stats(signals, "Mean Reversion")

    def _calc_stats(self, signals, name):
        """Calculate statistics for a set of signals"""
        if not signals:
            return {"name": name, "count": 0, "win_rate": 0, "avg_return": 0, "edge": "NO DATA"}

        total = len(signals)
        wins = sum(1 for s in signals if s["correct"])
        win_rate = wins / total * 100
        avg_return = np.mean([s["outcome"] for s in signals])

        if win_rate >= 58:
            edge = "✅ STRONG EDGE"
        elif win_rate >= 54:
            edge = "🟡 WEAK EDGE"
        elif win_rate >= 50:
            edge = "⚪ NO EDGE"
        else:
            edge = "❌ NEGATIVE"

        return {
            "name": name,
            "count": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": round(win_rate, 1),
            "avg_return": round(avg_return, 3),
            "edge": edge,
        }

    def _find_best_combination(self, c1m, c5m, c15m, c1h, cvd, checkpoint_results):
        """Find the best combination of checkpoints"""
        # Sort checkpoints by win rate
        valid = [(k, v) for k, v in checkpoint_results.items() if v["count"] >= 20]
        valid.sort(key=lambda x: x[1]["win_rate"], reverse=True)

        # Test combinations of top checkpoints
        best = {"win_rate": 0, "combo": [], "count": 0}

        top_names = [name for name, _ in valid[:8]]

        # Test each subset size
        for size in range(2, min(6, len(top_names) + 1)):
            from itertools import combinations
            for combo in combinations(top_names, size):
                # Simulate: signal fires when ALL checkpoints in combo agree
                signals = self._simulate_combo(c1m, cvd, combo, checkpoint_results)
                stats = self._calc_stats(signals, " + ".join(combo))
                if stats["count"] >= 10 and stats["win_rate"] > best["win_rate"]:
                    best = {
                        "win_rate": stats["win_rate"],
                        "avg_return": stats["avg_return"],
                        "combo": list(combo),
                        "count": stats["count"],
                        "edge": stats["edge"],
                    }

        return best

    def _simulate_combo(self, c1m, cvd, combo, checkpoint_results):
        """Simulate a combination of checkpoints"""
        signals = []

        for i in range(3600, len(c1m) - 1440, 300):
            long_votes = 0
            short_votes = 0

            for name in combo:
                result = self._evaluate_single(c1m, cvd, i, name)
                if result == "LONG":
                    long_votes += 1
                elif result == "SHORT":
                    short_votes += 1

            # All must agree
            if long_votes == len(combo):
                direction = "LONG"
            elif short_votes == len(combo):
                direction = "SHORT"
            else:
                continue

            outcome = (c1m[i+60]["close"] - c1m[i]["close"]) / c1m[i]["close"] * 100
            correct = (direction == "LONG" and outcome > 0) or (direction == "SHORT" and outcome < 0)
            signals.append({"direction": direction, "outcome": outcome, "correct": correct})

        return signals

    def _evaluate_single(self, c1m, cvd, i, name):
        """Evaluate a single checkpoint at index i"""
        if name == "CVD_5m":
            if i < 300: return None
            cvd_5m = cvd[i]["cvd"] - cvd[i-300]["cvd"]
            return "LONG" if cvd_5m > 50 else "SHORT" if cvd_5m < -50 else None

        elif name == "CVD_15m":
            if i < 900: return None
            cvd_15m = cvd[i]["cvd"] - cvd[i-900]["cvd"]
            return "LONG" if cvd_15m > 100 else "SHORT" if cvd_15m < -100 else None

        elif name == "CVD_1h":
            if i < 3600: return None
            cvd_1h = cvd[i]["cvd"] - cvd[i-3600]["cvd"]
            return "LONG" if cvd_1h > 200 else "SHORT" if cvd_1h < -200 else None

        elif name == "CVD_divergence":
            if i < 600: return None
            price_change = (c1m[i]["close"] - c1m[i-300]["close"]) / c1m[i-300]["close"]
            cvd_change = cvd[i]["cvd"] - cvd[i-300]["cvd"]
            if price_change < -0.003 and cvd_change > 50: return "LONG"
            if price_change > 0.003 and cvd_change < -50: return "SHORT"
            return None

        elif name == "Momentum_10m":
            if i < 10: return None
            change = (c1m[i]["close"] - c1m[i-10]["close"]) / c1m[i-10]["close"]
            return "LONG" if change > 0.005 else "SHORT" if change < -0.005 else None

        elif name == "Momentum_30m":
            if i < 30: return None
            change = (c1m[i]["close"] - c1m[i-30]["close"]) / c1m[i-30]["close"]
            return "LONG" if change > 0.005 else "SHORT" if change < -0.005 else None

        elif name == "Momentum_1h":
            if i < 60: return None
            change = (c1m[i]["close"] - c1m[i-60]["close"]) / c1m[i-60]["close"]
            return "LONG" if change > 0.005 else "SHORT" if change < -0.005 else None

        elif name == "Volume_surge":
            if i < 100: return None
            recent = np.mean([c1m[j]["volume"] for j in range(i-20, i)])
            avg = np.mean([c1m[j]["volume"] for j in range(i-100, i)])
            std = np.std([c1m[j]["volume"] for j in range(i-100, i)])
            if avg > 0 and recent > avg + 2 * std:
                change = (c1m[i]["close"] - c1m[i-5]["close"]) / c1m[i-5]["close"]
                return "LONG" if change > 0 else "SHORT"
            return None

        elif name == "Price_position":
            if i < 1440: return None
            high = max(c1m[j]["high"] for j in range(i-1440, i))
            low = min(c1m[j]["low"] for j in range(i-1440, i))
            rng = high - low
            pos = (c1m[i]["close"] - low) / rng if rng > 0 else 0.5
            return "SHORT" if pos > 0.85 else "LONG" if pos < 0.15 else None

        elif name == "MTF_5m":
            return None  # Simplified — skip for now

        elif name == "MTF_15m":
            return None

        elif name == "MTF_1h":
            return None

        elif name == "Trend_strength":
            if i < 100: return None
            net = abs(c1m[i]["close"] - c1m[i-100]["close"])
            total = sum(abs(c1m[j]["close"] - c1m[j-1]["close"]) for j in range(i-100, i))
            eff = net / total if total > 0 else 0
            if eff > 0.4:
                change = (c1m[i]["close"] - c1m[i-20]["close"]) / c1m[i-20]["close"]
                return "LONG" if change > 0 else "SHORT"
            return None

        elif name == "Mean_reversion":
            if i < 200: return None
            sma50 = np.mean([c1m[j]["close"] for j in range(i-50, i)])
            sma200 = np.mean([c1m[j]["close"] for j in range(i-200, i)])
            price = c1m[i]["close"]
            d50 = (price - sma50) / sma50
            d200 = (price - sma200) / sma200
            if d50 < -0.02 and d200 < -0.03: return "LONG"
            if d50 > 0.02 and d200 > 0.03: return "SHORT"
            return None

        return None

    def _print_report(self, checkpoint_results, best_combo):
        print()
        print("=" * 60)
        print("INDIVIDUAL CHECKPOINT RESULTS")
        print("=" * 60)
        print(f"{'Checkpoint':<20} {'Signals':>8} {'Win Rate':>10} {'Avg Return':>12} {'Edge'}")
        print("-" * 70)

        sorted_results = sorted(checkpoint_results.items(), key=lambda x: x[1]["win_rate"], reverse=True)
        for name, stats in sorted_results:
            if stats["count"] > 0:
                print(f"{stats['name']:<20} {stats['count']:>8} {stats['win_rate']:>9.1f}% {stats['avg_return']:>+11.3f}% {stats['edge']}")

        print()
        print("=" * 60)
        print("BEST COMBINATION")
        print("=" * 60)
        if best_combo["win_rate"] > 0:
            print(f"Checkpoints: {' + '.join(best_combo['combo'])}")
            print(f"Win Rate: {best_combo['win_rate']:.1f}%")
            print(f"Avg Return: {best_combo['avg_return']:+.3f}%")
            print(f"Signals: {best_combo['count']}")
            print(f"Edge: {best_combo['edge']}")
        else:
            print("No profitable combination found")

        print()
        print("=" * 60)


async def main():
    opt = SignalOptimizer()
    await opt.run(days=90)


if __name__ == "__main__":
    asyncio.run(main())
