"""
Smart Money System - Integrated System
Connects all modules together:
- Blockchain listener → Movement scorer → Telegram alerts
- Signal engine → Signal combiner → Trade decisions
- Paper trader → Performance tracker
"""

import asyncio
import json
from datetime import datetime
from modules.data.blockchain_listener import BlockchainListener
from modules.signals.movement_scorer import MovementScorer
from modules.signals.signal_runner import SignalRunner
from modules.executor.paper_trader import PaperTrader
from modules.feedback.performance import PerformanceTracker
from modules.ui.telegram_bot import TelegramAlerter

class IntegratedSystem:
    def __init__(self, portfolio_value=10000):
        self.alerter = TelegramAlerter()
        self.scorer = MovementScorer()
        self.signal_runner = SignalRunner(self.alerter)
        self.paper_trader = PaperTrader(portfolio_value=portfolio_value)
        self.performance = PerformanceTracker()
        self.running = False
        
        # Track last signal to avoid duplicate trades
        self.last_signal = None
        self.last_trade_time = None
        
        # Per-wallet cooldown tracking
        self._wallet_cooldown = {}
    
    async def on_wallet_movement(self, movement):
        """Handle wallet movement from blockchain listener"""
        # Filter tiny movements (ignore <1 ETH transfers)
        amount = movement.get("amount", 0)
        if amount < 1.0:
            return
        
        # Score the movement
        score, signal, reasons = self.scorer.score_movement(movement)
        
        # Skip low-score movements (raise threshold from 5 to 20)
        if abs(score) < 20:
            return
        
        # Per-wallet cooldown (don't alert same wallet within 5 minutes)
        wallet_label = movement.get("wallet_label", "unknown")
        now = datetime.now()
        if wallet_label in self._wallet_cooldown:
            time_since = (now - self._wallet_cooldown[wallet_label]).total_seconds()
            if time_since < 300:  # 5 minutes
                return
        self._wallet_cooldown[wallet_label] = now
        
        # Update signal combiner
        self.signal_runner.combiner.update_signal("wallet_movement", score)
        
        # Send alert
        alert_text = self.scorer.format_alert(movement, score, signal, reasons)
        await self.alerter.send_message(alert_text)
        
        print(f"[WALLET] {signal} ({score:+.0f}) - {wallet_label}")
    
    async def run_signal_cycle(self):
        """Run one complete signal cycle"""
        print(f"\n[SIGNAL] Running signal cycle at {datetime.now().strftime('%H:%M:%S')}")
        
        # Run all signals
        result = await self.signal_runner.run_all_signals()
        
        composite = result["composite"]
        trade_setup = result["trade_setup"]
        
        # Check if we should trade
        signal = composite["signal"]
        score = composite["score"]
        confidence = composite["confidence"]
        
        # Only trade on strong signals with good confidence
        if signal in ["STRONG_BUY", "BUY", "STRONG_SELL", "SELL"] and confidence != "low":
            
            # Don't trade same signal twice in a row
            if signal == self.last_signal:
                print(f"[SIGNAL] Same signal as last time ({signal}), skipping trade")
                return result
            
            # Don't trade too frequently (min 1 hour between trades)
            if self.last_trade_time:
                time_since = (datetime.now() - self.last_trade_time).total_seconds() / 3600
                if time_since < 1:
                    print(f"[SIGNAL] Too soon since last trade ({time_since:.1f}h), skipping")
                    return result
            
            # Get current price
            eth_price = result["raw"]["orderbook"].get("ETHUSDT", {}).get("price", 0)
            
            if eth_price > 0 and trade_setup.get("action") != "NO_TRADE":
                # Open paper trade
                trade, reason = self.paper_trader.open_trade(
                    coin="ETHUSDT",
                    side=trade_setup["action"],
                    entry_price=trade_setup["entry"],
                    stop_loss=trade_setup["stop_loss"],
                    take_profit_1=trade_setup["take_profit_1"],
                    take_profit_2=trade_setup["take_profit_2"],
                    signal_score=score
                )
                
                if trade:
                    self.last_signal = signal
                    self.last_trade_time = datetime.now()
                    
                    # Send trade notification
                    await self.alerter.send_message(
                        f"📝 <b>PAPER TRADE OPENED</b>\n\n"
                        f"Action: {trade_setup['action']}\n"
                        f"Entry: ${trade_setup['entry']:,.2f}\n"
                        f"Stop Loss: ${trade_setup['stop_loss']:,.2f}\n"
                        f"TP1: ${trade_setup['take_profit_1']:,.2f}\n"
                        f"TP2: ${trade_setup['take_profit_2']:,.2f}\n"
                        f"Size: {trade['position_size']:.6f} ETH\n"
                        f"Risk: {trade_setup['position_size_pct']}% of portfolio\n\n"
                        f"Signal Score: {score:+.1f}"
                    )
        
        # Check open trades for SL/TP hits
        current_prices = {}
        if "raw" in result and "orderbook" in result["raw"]:
            for symbol, data in result["raw"]["orderbook"].items():
                current_prices[symbol] = data.get("price", 0)
        
        if current_prices:
            closed = self.paper_trader.check_trades(current_prices)
            for trade in closed:
                pnl_emoji = "✅" if trade["pnl"] > 0 else "❌"
                await self.alerter.send_message(
                    f"{pnl_emoji} <b>TRADE CLOSED</b>\n\n"
                    f"Coin: {trade['coin']}\n"
                    f"Side: {trade['side']}\n"
                    f"Entry: ${trade['entry_price']:,.2f}\n"
                    f"Exit: ${trade['exit_price']:,.2f}\n"
                    f"Reason: {trade['exit_reason']}\n"
                    f"P&L: ${trade['pnl']:+,.2f} ({trade['pnl_pct']:+.2f}%)"
                )
        
        # Send periodic status (every 6 hours)
        now = datetime.now()
        if now.hour % 6 == 0 and now.minute < 5:
            status = self.paper_trader.format_status()
            await self.alerter.send_message(status)
        
        return result
    
    async def run(self):
        """Run the complete integrated system"""
        self.running = True
        
        # Init database
        from modules.database import init_db
        await init_db()
        
        # Send startup message
        await self.alerter.send_message(
            "🚀 <b>SMART MONEY SYSTEM v2.0 — FULLY OPERATIONAL</b>\n\n"
            "✅ Blockchain Listener (19 wallets)\n"
            "✅ Order Book Signal (Binance)\n"
            "✅ Funding Rate Signal\n"
            "✅ Sentiment Signal (Fear & Greed)\n"
            "✅ Exchange Flow Signal\n"
            "✅ Signal Combiner (6 signals)\n"
            "✅ Paper Trader\n"
            "✅ Performance Tracker\n"
            "✅ Telegram Alerts\n\n"
            "📊 Running signal cycle every 5 minutes\n"
            "👀 Watching blockchain in real-time\n\n"
            "System is LIVE. You'll receive alerts when signals fire."
        )
        
        # Create tasks
        listener = BlockchainListener(callback=self.on_wallet_movement)
        
        listener_task = asyncio.create_task(listener.listen())
        signal_task = asyncio.create_task(self._signal_loop())
        
        print("[SYSTEM] Integrated system running...")
        print("  - Blockchain listener: real-time")
        print("  - Signal engine: every 5 minutes")
        print("  - Paper trading: active")
        print("  - Alerts: Telegram")
        
        # Run forever
        await asyncio.gather(listener_task, signal_task)
    
    async def _signal_loop(self):
        """Signal loop wrapper"""
        while self.running:
            try:
                await self.run_signal_cycle()
            except Exception as e:
                print(f"[SIGNAL] Error: {e}")
            await asyncio.sleep(300)  # 5 minutes
    
    def stop(self):
        """Stop the system"""
        self.running = False


async def main():
    """Run the integrated system"""
    system = IntegratedSystem(portfolio_value=10000)
    await system.run()


if __name__ == "__main__":
    asyncio.run(main())
