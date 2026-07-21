"""
Smart Money System - Signal Simulator
Generates trading signals from historical price data.
Simulates what the signal engine would have said at each point in time.
"""

import numpy as np
from datetime import datetime

class SignalSimulator:
    def __init__(self):
        # Signal weights (same as live system)
        self.weights = {
            "trend": 0.30,
            "momentum": 0.25,
            "volatility": 0.15,
            "volume": 0.15,
            "support_resistance": 0.15
        }
    
    def calculate_signals(self, candles, lookback=20):
        """
        Calculate signals for each candle using historical data.
        
        Args:
            candles: list of OHLCV candles
            lookback: number of candles to look back
        
        Returns: list of signals with scores
        """
        signals = []
        
        for i in range(lookback, len(candles)):
            window = candles[i-lookback:i+1]
            current = candles[i]
            
            # Calculate each signal
            trend_score = self._trend_signal(window)
            momentum_score = self._momentum_signal(window)
            volatility_score = self._volatility_signal(window)
            volume_score = self._volume_signal(window)
            sr_score = self._support_resistance_signal(window)
            
            # Weighted composite
            composite = (
                trend_score * self.weights["trend"] +
                momentum_score * self.weights["momentum"] +
                volatility_score * self.weights["volatility"] +
                volume_score * self.weights["volume"] +
                sr_score * self.weights["support_resistance"]
            )
            
            composite = max(-100, min(100, composite))
            
            # Determine signal
            if composite > 50:
                signal = "STRONG_BUY"
            elif composite > 20:
                signal = "BUY"
            elif composite > -20:
                signal = "HOLD"
            elif composite > -50:
                signal = "SELL"
            else:
                signal = "STRONG_SELL"
            
            signals.append({
                "timestamp": current["timestamp"],
                "price": current["close"],
                "score": round(composite, 1),
                "signal": signal,
                "components": {
                    "trend": round(trend_score, 1),
                    "momentum": round(momentum_score, 1),
                    "volatility": round(volatility_score, 1),
                    "volume": round(volume_score, 1),
                    "support_resistance": round(sr_score, 1)
                }
            })
        
        return signals
    
    def _trend_signal(self, window):
        """
        Trend signal using moving average crossover.
        Short MA > Long MA = bullish
        """
        closes = [c["close"] for c in window]
        
        # Short MA (5 periods)
        short_ma = np.mean(closes[-5:])
        
        # Long MA (20 periods)
        long_ma = np.mean(closes)
        
        # Score based on distance between MAs
        diff_pct = ((short_ma - long_ma) / long_ma) * 100
        
        # Scale: -5% to +5% maps to -100 to +100
        score = diff_pct * 20
        return max(-100, min(100, score))
    
    def _momentum_signal(self, window):
        """
        Momentum signal using RSI-like calculation.
        """
        closes = [c["close"] for c in window]
        
        # Calculate price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        gains = [c for c in changes if c > 0]
        losses = [-c for c in changes if c < 0]
        
        avg_gain = np.mean(gains) if gains else 0
        avg_loss = np.mean(losses) if losses else 0.001
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # RSI 30 = oversold (buy), RSI 70 = overbought (sell)
        # Map RSI to score: 30 → +100, 50 → 0, 70 → -100
        score = (50 - rsi) * 5
        return max(-100, min(100, score))
    
    def _volatility_signal(self, window):
        """
        Volatility signal.
        High volatility after a move = reversal likely
        Low volatility = consolidation
        """
        closes = [c["close"] for c in window]
        highs = [c["high"] for c in window]
        lows = [c["low"] for c in window]
        
        # Average True Range (ATR)
        trs = []
        for i in range(1, len(window)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            trs.append(tr)
        
        atr = np.mean(trs)
        atr_pct = (atr / closes[-1]) * 100
        
        # High volatility (>3%) after a downtrend = reversal buy
        # High volatility (>3%) after an uptrend = reversal sell
        # Low volatility (<1%) = neutral
        
        price_change = ((closes[-1] - closes[0]) / closes[0]) * 100
        
        if atr_pct > 3:
            # High volatility - contrarian
            score = -price_change * 10  # Opposite of recent move
        elif atr_pct < 1:
            # Low volatility - neutral
            score = 0
        else:
            # Medium volatility - slight trend continuation
            score = price_change * 5
        
        return max(-100, min(100, score))
    
    def _volume_signal(self, window):
        """
        Volume signal.
        High volume + price up = bullish
        High volume + price down = bearish
        """
        volumes = [c["volume"] for c in window]
        closes = [c["close"] for c in window]
        
        # Average volume
        avg_volume = np.mean(volumes[:-1])
        current_volume = volumes[-1]
        
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        
        # Price direction
        price_change = ((closes[-1] - closes[-2]) / closes[-2]) * 100
        
        # High volume confirms direction
        if volume_ratio > 1.5:
            score = price_change * 20
        elif volume_ratio > 1.0:
            score = price_change * 10
        else:
            score = price_change * 5  # Low volume = weak signal
        
        return max(-100, min(100, score))
    
    def _support_resistance_signal(self, window):
        """
        Support/Resistance signal.
        Price near support = buy, near resistance = sell.
        """
        closes = [c["close"] for c in window]
        highs = [c["high"] for c in window]
        lows = [c["low"] for c in window]
        
        current = closes[-1]
        
        # Simple support/resistance using recent highs/lows
        recent_high = max(highs)
        recent_low = min(lows)
        
        # Position within range (0 = at low, 1 = at high)
        range_size = recent_high - recent_low
        if range_size > 0:
            position = (current - recent_low) / range_size
        else:
            position = 0.5
        
        # Near support (0-0.2) = buy, near resistance (0.8-1.0) = sell
        if position < 0.2:
            score = 80  # Near support = buy
        elif position < 0.4:
            score = 30
        elif position < 0.6:
            score = 0  # Middle = neutral
        elif position < 0.8:
            score = -30
        else:
            score = -80  # Near resistance = sell
        
        return max(-100, min(100, score))
    
    def format_signal(self, signal):
        """Format a signal for display"""
        score = signal["score"]
        sig = signal["signal"]
        price = signal["price"]
        time = signal["timestamp"]
        
        emoji = {
            "STRONG_BUY": "🟢🟢",
            "BUY": "🟢",
            "HOLD": "⚪",
            "SELL": "🔴",
            "STRONG_SELL": "🔴🔴"
        }.get(sig, "⚪")
        
        return f"{emoji} {sig} ({score:+.1f}) @ ${price:,.2f} [{time}]"


def test_signal_simulator():
    """Test the signal simulator with sample data"""
    import asyncio
    from modules.backtest.data_fetcher import DataFetcher
    
    async def run():
        print("=" * 50)
        print("Signal Simulator - Test")
        print("=" * 50)
        
        fetcher = DataFetcher()
        candles = await fetcher.get_historical_data("ETHUSDT", "4h", 30)
        
        simulator = SignalSimulator()
        signals = simulator.calculate_signals(candles, lookback=20)
        
        print(f"\nGenerated {len(signals)} signals from {len(candles)} candles")
        print(f"\nLast 10 signals:")
        for s in signals[-10:]:
            print(f"  {simulator.format_signal(s)}")
        
        # Count signals
        counts = {}
        for s in signals:
            sig = s["signal"]
            counts[sig] = counts.get(sig, 0) + 1
        
        print(f"\nSignal distribution:")
        for sig, count in sorted(counts.items()):
            print(f"  {sig}: {count} ({count/len(signals)*100:.1f}%)")
        
        return signals
    
    return asyncio.run(run())


if __name__ == "__main__":
    test_signal_simulator()
