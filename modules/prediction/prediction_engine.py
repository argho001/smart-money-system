"""
Smart Money System - Prediction Engine (Main Orchestrator)

The brain that connects everything:
1. Regime Detector → What game are we playing?
2. Magnitude Predictor → How far will price move?
3. Analog Engine → What happened before in similar conditions?
4. Liquidity Map → Where does price gravitate?
5. Confidence Tracker → How much should we trust this?

Output: A complete prediction with direction, magnitude, timeframe,
        confidence, and supporting evidence from all modules.
"""

import asyncio
import json
import os
from datetime import datetime

from .regime_detector import RegimeDetector
from .magnitude_predictor import MagnitudePredictor
from .analog_engine import AnalogEngine
from .liquidity_map import LiquidityMap
from .confidence_tracker import ConfidenceTracker

# Import existing modules
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from modules.signals.orderbook_signal import OrderBookSignal
from modules.signals.funding_rate_signal import FundingRateSignal
from modules.signals.sentiment_signal import SentimentSignal
from modules.backtest.data_fetcher import DataFetcher


class PredictionEngine:
    """
    Main prediction orchestrator.
    Combines all prediction modules into a single actionable output.
    """

    def __init__(self, data_dir="data"):
        self.regime_detector = RegimeDetector()
        self.magnitude_predictor = MagnitudePredictor()
        self.analog_engine = AnalogEngine(data_dir)
        self.liquidity_map = LiquidityMap()
        self.confidence_tracker = ConfidenceTracker(data_dir)

        # Data sources
        self.data_fetcher = DataFetcher()
        self.orderbook_signal = OrderBookSignal()
        self.funding_signal = FundingRateSignal()
        self.sentiment_signal = SentimentSignal()

        self.last_prediction = None
        self.prediction_history = []

    async def predict(self, symbol="ETHUSDT"):
        """
        Generate a complete market prediction.

        Steps:
        1. Fetch all data (candles, order book, signals)
        2. Detect regime
        3. Get magnitude prediction
        4. Find historical analogs
        5. Build liquidity map
        6. Combine everything with calibrated confidence
        7. Record for future verification

        Returns: Full prediction dict
        """
        print(f"\n{'='*60}")
        print(f"PREDICTION ENGINE — {symbol}")
        print(f"{'='*60}")

        # === Step 1: Fetch Data ===
        print("\n[1/6] Fetching data...")
        candles = await self._fetch_candles(symbol)
        order_book = await self._fetch_orderbook(symbol)
        signals = await self._fetch_signals(symbol)

        if not candles or len(candles) < 50:
            return {"error": "Insufficient data", "candles_count": len(candles) if candles else 0}

        current_price = candles[-1]["close"]

        # === Step 2: Detect Regime ===
        print("[2/6] Detecting regime...")
        regime = self.regime_detector.detect(candles)
        print(f"  Regime: {regime['regime']} (confidence: {regime['confidence']})")

        # === Step 3: Determine Direction from Signal Combiner ===
        print("[3/6] Analyzing signals...")
        direction, signal_score = self._determine_direction(signals, regime)
        print(f"  Direction: {direction} (signal score: {signal_score:+.1f})")

        # === Step 4: Predict Magnitude ===
        print("[4/6] Predicting magnitude...")
        magnitude = self.magnitude_predictor.predict(candles, direction, signal_score, regime["regime"])
        print(f"  Expected move: {magnitude['expected_move_pct']:.1f}% in ~{magnitude['expected_timeframe_days']:.0f} days")

        # === Step 5: Find Historical Analogs ===
        print("[5/6] Finding historical analogs...")
        fingerprint = self.analog_engine.build_current_fingerprint(candles, signals)
        analogs = self.analog_engine.find_analogs(candles, fingerprint)
        print(f"  Found {len(analogs.get('analogs', []))} similar historical periods")

        # === Step 6: Build Liquidity Map ===
        print("[6/6] Building liquidity map...")
        liq_map = self.liquidity_map.analyze(order_book, current_price)
        print(f"  Liquidity bias: {liq_map['bias']} ({liq_map['score']:+.0f})")

        # === Combine Everything ===
        raw_confidence = self._calculate_confidence(regime, magnitude, analogs, liq_map, signal_score)
        calibrated_confidence = self.confidence_tracker.get_calibrated_confidence(
            raw_confidence, regime["regime"], signal_score
        )

        # Build composite prediction
        prediction = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "current_price": current_price,
            "direction": direction,
            "signal_score": signal_score,

            # Main outputs
            "expected_move_pct": magnitude["expected_move_pct"],
            "expected_timeframe_days": magnitude["expected_timeframe_days"],
            "confidence": calibrated_confidence,
            "confidence_raw": raw_confidence,

            # Targets
            "targets": magnitude.get("targets", {}),

            # Supporting evidence
            "regime": regime,
            "magnitude": magnitude,
            "analogs": {
                "consensus": analogs.get("summary", {}).get("direction_consensus", "NONE"),
                "avg_5d": analogs.get("summary", {}).get("avg_5d", 0),
                "avg_10d": analogs.get("summary", {}).get("avg_10d", 0),
                "avg_20d": analogs.get("summary", {}).get("avg_20d", 0),
                "win_rate": analogs.get("summary", {}).get("win_rate", 0),
                "sample_size": analogs.get("summary", {}).get("sample_size", 0),
                "top_analogs": analogs.get("analogs", [])[:3],
            },
            "liquidity": {
                "bias": liq_map["bias"],
                "score": liq_map["score"],
                "nearest_support": liq_map["nearest_support"],
                "nearest_resistance": liq_map["nearest_resistance"],
                "depth_imbalance": liq_map["depth_analysis"]["depth_imbalance"],
            },

            # Signals
            "signals": signals,

            # Meta
            "model_version": "1.0",
        }

        # Record for future verification
        self.confidence_tracker.record_prediction(prediction)

        # Store
        self.last_prediction = prediction
        self.prediction_history.append(prediction)

        # Save to file
        self._save_prediction(prediction)

        return prediction

    async def _fetch_candles(self, symbol):
        """Fetch historical candles."""
        try:
            candles = await self.data_fetcher.get_historical_data(symbol, "1h", 90)
            return candles
        except Exception as e:
            print(f"  Error fetching candles: {e}")
            return []

    async def _fetch_orderbook(self, symbol):
        """Fetch current order book."""
        try:
            order_book = await self.orderbook_signal.get_order_book(symbol, limit=100)
            return order_book
        except Exception as e:
            print(f"  Error fetching order book: {e}")
            return {}

    async def _fetch_signals(self, symbol):
        """Fetch all signal data."""
        signals = {}

        # Funding rate
        try:
            funding = await self.funding_signal.get_funding_rate(symbol)
            if funding:
                signals["funding_rate"] = float(funding.get("lastFundingRate", 0))
                signals["funding_analysis"] = self.funding_signal.analyze_funding_rate(funding)
        except Exception as e:
            print(f"  Funding signal error: {e}")

        # Sentiment
        try:
            sentiment = await self.sentiment_signal.get_fear_greed(limit=7)
            if sentiment:
                analysis = self.sentiment_signal.analyze_sentiment(sentiment)
                signals["sentiment_score"] = analysis.get("score", 0)
                signals["sentiment_analysis"] = analysis
        except Exception as e:
            print(f"  Sentiment signal error: {e}")

        # Order book
        try:
            ob = await self.orderbook_signal.get_order_book(symbol, limit=50)
            if ob:
                price = await self.orderbook_signal.get_ticker(symbol)
                if price:
                    analysis = self.orderbook_signal.analyze_order_book(ob, price)
                    signals["orderbook_imbalance"] = analysis.get("imbalance", 0)
                    signals["orderbook_analysis"] = analysis
        except Exception as e:
            print(f"  Orderbook signal error: {e}")

        return signals

    def _determine_direction(self, signals, regime):
        """Determine direction from signals + regime."""
        score = 0

        # Funding rate (contrarian)
        funding_score = signals.get("funding_analysis", {}).get("score", 0)
        score += funding_score * 0.30

        # Sentiment (contrarian)
        sentiment_score = signals.get("sentiment_score", 0)
        score += sentiment_score * 0.20

        # Order book
        ob_score = signals.get("orderbook_analysis", {}).get("score", 0)
        score += ob_score * 0.25

        # Regime bias
        regime_name = regime.get("regime", "UNKNOWN")
        if regime_name == "TRENDING_UP":
            score += 20
        elif regime_name == "TRENDING_DOWN":
            score -= 20
        elif regime_name == "ACCUMULATION":
            score += 15
        elif regime_name == "DISTRIBUTION":
            score -= 15

        # Clamp
        score = max(-100, min(100, score))

        if score > 10:
            direction = "UP"
        elif score < -10:
            direction = "DOWN"
        else:
            # In neutral, lean on regime
            if regime_name in ["TRENDING_UP", "ACCUMULATION"]:
                direction = "UP"
            elif regime_name in ["TRENDING_DOWN", "DISTRIBUTION"]:
                direction = "DOWN"
            else:
                direction = "UP" if score >= 0 else "DOWN"

        return direction, score

    def _calculate_confidence(self, regime, magnitude, analogs, liq_map, signal_score):
        """Calculate raw confidence from all modules."""
        conf = 0.5  # Base confidence

        # Regime confidence
        regime_conf = regime.get("confidence", 0.5)
        conf += (regime_conf - 0.5) * 0.3

        # Signal strength
        signal_strength = abs(signal_score) / 100
        conf += (signal_strength - 0.3) * 0.2

        # Analog consensus
        analog_consensus = analogs.get("summary", {}).get("direction_consensus", "NONE")
        if analog_consensus in ["BULLISH", "BEARISH"]:
            conf += 0.1
        elif analog_consensus == "MIXED":
            conf -= 0.05

        # Analog win rate
        analog_win_rate = analogs.get("summary", {}).get("win_rate", 0.5)
        conf += (analog_win_rate - 0.5) * 0.2

        # Liquidity alignment
        liq_bias = liq_map.get("bias", "NEUTRAL")
        liq_score = liq_map.get("score", 0)
        direction = magnitude.get("direction", "UP")
        if (liq_bias == "BULLISH" and direction == "UP") or \
           (liq_bias == "BEARISH" and direction == "DOWN"):
            conf += 0.1
        elif liq_bias != "NEUTRAL":
            conf -= 0.05

        # Magnitude reasonableness (too big = less confident)
        move_pct = magnitude.get("expected_move_pct", 0)
        if move_pct > 20:
            conf -= 0.1  # Unreasonably large move
        elif move_pct < 1:
            conf -= 0.05  # Too small to be useful

        return max(0.15, min(0.90, conf))

    def _save_prediction(self, prediction):
        """Save prediction to file."""
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/latest_prediction.json", "w") as f:
                json.dump(prediction, f, indent=2, default=str)
        except Exception as e:
            print(f"  Error saving prediction: {e}")

    def format_prediction(self, prediction):
        """Format complete prediction for Telegram."""
        if "error" in prediction:
            return f"❌ Prediction error: {prediction['error']}"

        direction = prediction["direction"]
        dir_emoji = "📈" if direction == "UP" else "📉"

        conf = prediction["confidence"]
        if conf >= 0.75:
            conf_label = "🟢 HIGH"
        elif conf >= 0.50:
            conf_label = "🟡 MEDIUM"
        else:
            conf_label = "🔴 LOW"

        regime = prediction["regime"]["regime"]
        regime_desc = prediction["regime"]["description"]

        # Confidence bar
        conf_bar_len = int(conf * 10)
        conf_bar = "▓" * conf_bar_len + "░" * (10 - conf_bar_len)

        lines = [
            f"{'='*40}",
            f"{dir_emoji} <b>MARKET PREDICTION</b> {dir_emoji}",
            f"{'='*40}",
            f"",
            f"💰 <b>ETH:</b> ${prediction['current_price']:,.2f}",
            f"",
            f"<b>🎯 Direction:</b> {direction}",
            f"<b>📊 Move:</b> {'-' if prediction['direction'] == 'DOWN' else '+'}{prediction['expected_move_pct']:.1f}%",
            f"<b>⏱️ Timeframe:</b> ~{prediction['expected_timeframe_days']:.0f} days",
            f"<b>🎲 Confidence:</b> {conf_label} [{conf_bar}] {conf:.0%}",
            f"",
            f"<b>📈 Price Targets:</b>",
        ]

        # Targets
        for sigma, data in prediction.get("targets", {}).items():
            prob = data.get("probability", 0) * 100
            price = data.get("price", 0)
            pct = data.get("pct", 0)
            lines.append(f"  {sigma}: ${price:,.2f} ({pct:+.1f}%) — {prob:.0f}% prob")

        lines.extend([
            f"",
            f"<b>🧠 Regime:</b> {regime}",
            f"  {regime_desc}",
            f"",
            f"<b>🔍 Historical Analogs:</b>",
            f"  Consensus: {prediction['analogs']['consensus']}",
            f"  Win rate: {prediction['analogs']['win_rate']:.0%} ({prediction['analogs']['sample_size']} samples)",
            f"  Avg outcome: 5d={prediction['analogs']['avg_5d']:+.1f}% / 10d={prediction['analogs']['avg_10d']:+.1f}% / 20d={prediction['analogs']['avg_20d']:+.1f}%",
            f"",
            f"<b>🗺️ Liquidity:</b>",
            f"  Bias: {prediction['liquidity']['bias']} ({prediction['liquidity']['score']:+.0f})",
            f"  Support: ${prediction['liquidity']['nearest_support']:,.2f}",
            f"  Resistance: ${prediction['liquidity']['nearest_resistance']:,.2f}",
            f"  Depth imbalance: {prediction['liquidity']['depth_imbalance']:+.1f}%",
            f"",
            f"<b>📡 Signal Score:</b> {prediction['signal_score']:+.1f}/100",
            f"",
            f"{'='*40}",
        ])

        return "\n".join(lines)

    async def verify_and_report(self):
        """Verify old predictions and report accuracy."""
        try:
            current_price = self.orderbook_signal.get_ticker("ETHUSDT")
            if current_price:
                verified = self.confidence_tracker.verify_predictions(current_price)
                if verified:
                    print(f"\n[VERIFY] {len(verified)} predictions verified")
                    for v in verified:
                        outcome = v["actual_outcome"]
                        emoji = "✅" if outcome["direction_correct"] else "❌"
                        print(f"  {emoji} {v['direction']} expected {v['expected_move_pct']:+.1f}% → actual {outcome['actual_change_pct']:+.1f}%")

                return self.confidence_tracker.format_accuracy()
        except Exception as e:
            print(f"[VERIFY] Error: {e}")

        return None


async def test_prediction_engine():
    """Test the prediction engine end-to-end."""
    print("=" * 60)
    print("PREDICTION ENGINE — FULL TEST")
    print("=" * 60)

    engine = PredictionEngine()
    prediction = await engine.predict("ETHUSDT")

    if "error" not in prediction:
        report = engine.format_prediction(prediction)
        print(f"\n{report}")
    else:
        print(f"\nError: {prediction['error']}")

    return prediction


if __name__ == "__main__":
    asyncio.run(test_prediction_engine())
