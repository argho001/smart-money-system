"""
Smart Money System - Signal Runner
Runs all signals periodically and updates the combiner.
"""

import asyncio
from datetime import datetime
from modules.signals.orderbook_signal import OrderBookSignal
from modules.signals.funding_rate_signal import FundingRateSignal
from modules.signals.sentiment_signal import SentimentSignal
from modules.signals.exchange_flow_signal import ExchangeFlowSignal
from modules.signals.combiner import SignalCombiner
from modules.ui.telegram_bot import TelegramAlerter

class SignalRunner:
    def __init__(self, alerter=None):
        self.orderbook = OrderBookSignal()
        self.funding = FundingRateSignal()
        self.sentiment = SentimentSignal()
        self.exchange_flow = ExchangeFlowSignal()
        self.combiner = SignalCombiner()
        self.alerter = alerter or TelegramAlerter()
        
        self.last_report = None
        self.running = False
    
    async def run_all_signals(self):
        """Run all signals and update combiner"""
        print(f"\n[SIGNALS] Running all signals at {datetime.now().strftime('%H:%M:%S')}")
        print("-" * 50)
        
        # 1. Order Book
        try:
            ob_result = await self.orderbook.run()
            for symbol, data in ob_result.items():
                self.combiner.update_signal("orderbook", data["analysis"]["score"])
        except Exception as e:
            print(f"[SIGNALS] Order book error: {e}")
        
        # 2. Funding Rate
        try:
            fr_result = await self.funding.run()
            for symbol, data in fr_result.items():
                self.combiner.update_signal("funding_rate", data["analysis"]["score"])
        except Exception as e:
            print(f"[SIGNALS] Funding rate error: {e}")
        
        # 3. Sentiment
        try:
            sent_result = await self.sentiment.run()
            self.combiner.update_signal("sentiment", sent_result["analysis"]["score"])
        except Exception as e:
            print(f"[SIGNALS] Sentiment error: {e}")
        
        # 4. Exchange Flow (run less frequently due to API limits)
        # Skipped in rapid polling - runs separately
        
        # Get composite
        composite = self.combiner.get_composite_score()
        
        # Get current price for trade setup
        eth_price = ob_result.get("ETHUSDT", {}).get("price", 0)
        trade_setup = self.combiner.get_trade_setup(composite, eth_price)
        
        # Generate report
        report = self.combiner.format_report(composite, trade_setup)
        
        print(f"\n[SIGNALS] Composite: {composite['signal']} ({composite['score']:+.1f})")
        
        return {
            "composite": composite,
            "trade_setup": trade_setup,
            "report": report,
            "raw": {
                "orderbook": ob_result,
                "funding": fr_result,
                "sentiment": sent_result
            }
        }
    
    async def send_signal_report(self, result):
        """Send signal report via Telegram"""
        # Only send if signal changed significantly
        current_signal = result["composite"]["signal"]
        current_score = result["composite"]["score"]
        
        if self.last_report:
            last_signal = self.last_report["composite"]["signal"]
            last_score = self.last_report["composite"]["score"]
            
            # Don't send if same signal and similar score
            if current_signal == last_signal and abs(current_score - last_score) < 10:
                return False
            
            # Don't send HOLD signals unless score changed a lot
            if current_signal == "HOLD" and last_signal == "HOLD":
                return False
        
        # Send report
        await self.alerter.send_message(result["report"])
        self.last_report = result
        return True
    
    async def run_loop(self, interval_seconds=300):
        """Run signals in a loop (default: every 5 minutes)"""
        self.running = True
        print(f"[SIGNALS] Starting signal loop (every {interval_seconds}s)")
        
        while self.running:
            try:
                result = await self.run_all_signals()
                await self.send_signal_report(result)
                
                # Save to file
                import json
                with open("data/latest_signals.json", "w") as f:
                    # Convert to serializable format
                    save_data = {
                        "composite": result["composite"],
                        "trade_setup": result["trade_setup"],
                        "timestamp": datetime.now().isoformat()
                    }
                    json.dump(save_data, f, indent=2)
                
            except Exception as e:
                print(f"[SIGNALS] Error in loop: {e}")
            
            await asyncio.sleep(interval_seconds)
    
    def stop(self):
        """Stop the signal loop"""
        self.running = False


async def test_signal_runner():
    """Test the signal runner"""
    print("=" * 50)
    print("Signal Runner - Test")
    print("=" * 50)
    
    runner = SignalRunner()
    result = await runner.run_all_signals()
    
    print("\n" + "=" * 50)
    print("REPORT:")
    print("=" * 50)
    print(result["report"])


if __name__ == "__main__":
    asyncio.run(test_signal_runner())
