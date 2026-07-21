"""
Smart Money System - Market Prediction Engine
Predicts WHERE price goes, HOW FAR, and WHEN.

Modules:
- RegimeDetector: What market state are we in
- MagnitudePredictor: ATR + elasticity based price targets
- AnalogEngine: Historical pattern matching
- LiquidityMap: Order book wall detection & price magnets
- ConfidenceTracker: Prediction accuracy tracking & calibration
- PredictionEngine: Main orchestrator
"""

from .prediction_engine import PredictionEngine

__all__ = ["PredictionEngine"]
