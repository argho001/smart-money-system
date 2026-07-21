"""
Smart Money System - Signal Combiner
Combines all signals into a single composite score and decision.

Signals:
1. Wallet Movement Score (from blockchain listener)
2. Exchange Flow Score (from exchange flow signal)
3. Order Book Score (from Binance)
4. Funding Rate Score (from Binance Futures)
5. Sentiment Score (from Fear & Greed)

Output:
- Composite score: -100 to +100
- Decision: STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL
- Confidence: low / medium / high
- Trade setup (if actionable): entry, stop loss, take profit
"""

import asyncio
from datetime import datetime

class SignalCombiner:
    def __init__(self):
        # Signal weights (must sum to 1.0)
        self.weights = {
            "wallet_movement": 0.15,   # Individual wallet moves
            "exchange_flow": 0.25,      # Overall exchange flows
            "orderbook": 0.25,          # Order book pressure
            "funding_rate": 0.20,       # Funding rate (crowding)
            "sentiment": 0.15,          # Fear & Greed
        }
        
        # Signal cache
        self.signals = {}
    
    def update_signal(self, signal_name, score, details=None):
        """Update a signal score"""
        self.signals[signal_name] = {
            "score": score,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
    
    def get_composite_score(self):
        """
        Calculate weighted composite score.
        Returns: {score, signal, confidence, components}
        """
        if not self.signals:
            return {
                "score": 0,
                "signal": "HOLD",
                "confidence": "low",
                "reason": "No signals available",
                "components": {}
            }
        
        weighted_sum = 0
        total_weight = 0
        components = {}
        
        for name, weight in self.weights.items():
            if name in self.signals:
                score = self.signals[name]["score"]
                weighted_score = score * weight
                weighted_sum += weighted_score
                total_weight += weight
                
                components[name] = {
                    "score": score,
                    "weight": weight,
                    "weighted_score": weighted_score
                }
        
        # Normalize
        if total_weight > 0:
            composite = weighted_sum / total_weight
        else:
            composite = 0
        
        # Clamp to -100 to +100
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
        
        # Determine confidence
        active_signals = len(components)
        if active_signals >= 4:
            confidence = "high"
        elif active_signals >= 2:
            confidence = "medium"
        else:
            confidence = "low"
        
        # Build reason
        reasons = []
        for name, comp in components.items():
            if abs(comp["score"]) > 30:
                direction = "bullish" if comp["score"] > 0 else "bearish"
                reasons.append(f"{name}: {direction} ({comp['score']:+.0f})")
        
        reason = "; ".join(reasons) if reasons else "Mixed signals"
        
        return {
            "score": round(composite, 1),
            "signal": signal,
            "confidence": confidence,
            "reason": reason,
            "components": components,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_trade_setup(self, composite_result, current_price):
        """
        Generate trade setup from composite signal.
        Returns: {action, entry, stop_loss, take_profit, position_size_pct}
        """
        score = composite_result["score"]
        signal = composite_result["signal"]
        confidence = composite_result["confidence"]
        
        if signal == "HOLD":
            return {
                "action": "NO_TRADE",
                "reason": "Score within neutral range"
            }
        
        # Don't trade on low confidence
        if confidence == "low":
            return {
                "action": "NO_TRADE",
                "reason": "Insufficient signal confidence"
            }
        
        # Calculate entry, SL, TP based on signal strength
        if signal in ["STRONG_BUY", "BUY"]:
            # Long trade
            entry = current_price
            
            # Stop loss: tighter for strong signals, wider for weak
            if signal == "STRONG_BUY":
                sl_pct = 0.02  # 2% stop loss
                tp_pct = 0.06  # 6% take profit (3:1 R:R)
            else:
                sl_pct = 0.03  # 3% stop loss
                tp_pct = 0.06  # 6% take profit (2:1 R:R)
            
            stop_loss = entry * (1 - sl_pct)
            take_profit_1 = entry * (1 + tp_pct * 0.5)  # 50% at first target
            take_profit_2 = entry * (1 + tp_pct)          # 50% at second target
            
            return {
                "action": "LONG",
                "entry": round(entry, 2),
                "stop_loss": round(stop_loss, 2),
                "take_profit_1": round(take_profit_1, 2),
                "take_profit_2": round(take_profit_2, 2),
                "risk_reward": f"1:{tp_pct/sl_pct:.1f}",
                "position_size_pct": 1.0 if confidence == "high" else 0.5
            }
        
        else:
            # Short trade
            entry = current_price
            
            if signal == "STRONG_SELL":
                sl_pct = 0.02
                tp_pct = 0.06
            else:
                sl_pct = 0.03
                tp_pct = 0.06
            
            stop_loss = entry * (1 + sl_pct)
            take_profit_1 = entry * (1 - tp_pct * 0.5)
            take_profit_2 = entry * (1 - tp_pct)
            
            return {
                "action": "SHORT",
                "entry": round(entry, 2),
                "stop_loss": round(stop_loss, 2),
                "take_profit_1": round(take_profit_1, 2),
                "take_profit_2": round(take_profit_2, 2),
                "risk_reward": f"1:{tp_pct/sl_pct:.1f}",
                "position_size_pct": 1.0 if confidence == "high" else 0.5
            }
    
    def format_report(self, composite_result, trade_setup=None):
        """Format a full signal report"""
        score = composite_result["score"]
        signal = composite_result["signal"]
        confidence = composite_result["confidence"]
        reason = composite_result["reason"]
        components = composite_result["components"]
        
        # Signal emoji
        signal_emoji = {
            "STRONG_BUY": "🟢🟢",
            "BUY": "🟢",
            "HOLD": "⚪",
            "SELL": "🔴",
            "STRONG_SELL": "🔴🔴"
        }.get(signal, "⚪")
        
        # Confidence emoji
        conf_emoji = {"low": "🟡", "medium": "🟠", "high": "🟢"}.get(confidence, "⚪")
        
        # Score bar
        normalized = int((score + 100) / 200 * 10)
        bar = "▓" * normalized + "░" * (10 - normalized)
        
        # Components
        comp_lines = []
        for name, comp in components.items():
            comp_score = comp["score"]
            comp_emoji = "🟢" if comp_score > 0 else "🔴" if comp_score < 0 else "⚪"
            comp_lines.append(f"  {comp_emoji} {name}: {comp_score:+.0f} (×{comp['weight']:.0%})")
        comp_text = "\n".join(comp_lines) if comp_lines else "  No signals yet"
        
        # Trade setup
        trade_text = ""
        if trade_setup and trade_setup.get("action") != "NO_TRADE":
            trade_text = f"""
<b>📋 TRADE SETUP:</b>
  Action: {trade_setup['action']}
  Entry: ${trade_setup['entry']:,.2f}
  Stop Loss: ${trade_setup['stop_loss']:,.2f}
  TP1 (50%): ${trade_setup['take_profit_1']:,.2f}
  TP2 (50%): ${trade_setup['take_profit_2']:,.2f}
  R:R: {trade_setup['risk_reward']}
  Position Size: {trade_setup['position_size_pct']}% of portfolio
"""
        
        report = f"""
{signal_emoji} <b>SIGNAL: {signal}</b> {signal_emoji}

📊 <b>Composite Score:</b> {score:+.1f}/100 [{bar}]
{conf_emoji} <b>Confidence:</b> {confidence.upper()}

<b>📡 Signals:</b>
{comp_text}

<b>💡 Analysis:</b> {reason}
{trade_text}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        return report.strip()


async def test_combiner():
    """Test the signal combiner with mock data"""
    print("=" * 50)
    print("Signal Combiner - Test")
    print("=" * 50)
    
    combiner = SignalCombiner()
    
    # Simulate signals
    combiner.update_signal("wallet_movement", 45, {"source": "a16z outflow"})
    combiner.update_signal("exchange_flow", 30, {"net_outflow": "500 ETH"})
    combiner.update_signal("orderbook", 20, {"bid_pct": 58})
    combiner.update_signal("funding_rate", -15, {"rate": -0.01})
    combiner.update_signal("sentiment", 60, {"fng": 22})
    
    # Get composite
    result = combiner.get_composite_score()
    print(f"\nComposite Score: {result['score']}")
    print(f"Signal: {result['signal']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Reason: {result['reason']}")
    
    # Get trade setup
    trade = combiner.get_trade_setup(result, current_price=3500)
    print(f"\nTrade Setup: {trade}")
    
    # Format report
    report = combiner.format_report(result, trade)
    print(f"\n{report}")
    
    return result


if __name__ == "__main__":
    asyncio.run(test_combiner())
