"""
Smart Money System - Main Entry Point

Usage:
    python3 main.py start        - Start the full system
    python3 main.py listen       - Start blockchain listener only
    python3 main.py live         - Start integrated system (live)
    python3 main.py predict      - Run prediction engine (WHERE/HOW FAR/WHEN)
    python3 main.py regime       - Detect current market regime
    python3 main.py accuracy     - Show prediction accuracy stats
    python3 main.py test         - Test all components
    python3 main.py test-signals - Test signal engine
    python3 main.py test-telegram - Test Telegram connection
    python3 main.py test-db      - Test database
    python3 main.py status       - Show system status
    python3 main.py performance  - Show performance report
    python3 main.py paper        - Paper trading status
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from config import load_wallets, ALCHEMY_API_KEY, TELEGRAM_BOT_TOKEN
from modules.database import init_db, get_recent_movements, get_open_trades
from modules.data.blockchain_listener import BlockchainListener
from modules.signals.movement_scorer import MovementScorer
from modules.signals.signal_runner import SignalRunner
from modules.ui.telegram_bot import TelegramAlerter, test_telegram


async def start_listener():
    """Start the blockchain listener with scored Telegram alerts"""
    alerter = TelegramAlerter()
    scorer = MovementScorer()
    
    # Send startup notification
    await alerter.send_startup_message()
    
    # Callback: score movement and send Telegram alert
    async def on_movement(movement):
        # Score the movement
        score, signal, reasons = scorer.score_movement(movement)
        
        # Skip tiny movements (score < 5)
        if abs(score) < 5:
            return
        
        # Format scored alert
        alert_text = scorer.format_alert(movement, score, signal, reasons)
        
        # Send to Telegram
        await alerter.send_message(alert_text)
        
        # Log to console
        print(f"  → Signal: {signal} (score: {score:+.0f})")
    
    # Start listener
    listener = BlockchainListener(callback=on_movement)
    await listener.listen()


async def start_full_system():
    """Start the full system: blockchain listener + signal engine"""
    alerter = TelegramAlerter()
    scorer = MovementScorer()
    signal_runner = SignalRunner(alerter)
    
    # Send startup notification
    await alerter.send_message(
        "🚀 <b>SMART MONEY SYSTEM v2.0 STARTED</b>\n\n"
        "✅ Blockchain listener (19 wallets)\n"
        "✅ Order book signal (Binance)\n"
        "✅ Funding rate signal\n"
        "✅ Sentiment signal (Fear & Greed)\n"
        "✅ Signal combiner (6 signals)\n"
        "✅ Telegram alerts\n\n"
        "Running..."
    )
    
    # Callback for blockchain movements
    async def on_movement(movement):
        score, signal, reasons = scorer.score_movement(movement)
        if abs(score) < 5:
            return
        
        # Update combiner with wallet signal
        signal_runner.combiner.update_signal("wallet_movement", score)
        
        # Send individual alert
        alert_text = scorer.format_alert(movement, score, signal, reasons)
        await alerter.send_message(alert_text)
        print(f"  → Wallet Signal: {signal} (score: {score:+.0f})")
    
    # Run both in parallel
    listener = BlockchainListener(callback=on_movement)
    
    # Create tasks
    listener_task = asyncio.create_task(listener.listen())
    signals_task = asyncio.create_task(signal_runner.run_loop(interval_seconds=300))
    
    print("[SYSTEM] Full system running...")
    print("  - Blockchain listener: watching 19 wallets")
    print("  - Signal engine: running every 5 minutes")
    print("  - Alerts: sending to Telegram")
    
    # Wait for both (they run forever)
    await asyncio.gather(listener_task, signals_task)


async def test_system():
    """Test all system components"""
    print("=" * 50)
    print("Smart Money System - Component Test")
    print("=" * 50)
    
    # Test 1: Config
    print("\n[1/4] Testing config...")
    wallets = load_wallets()
    print(f"  ✅ Loaded {len(wallets)} wallets")
    for addr, info in wallets.items():
        print(f"     - {info['label']} ({info['category']})")
    
    # Test 2: Database
    print("\n[2/4] Testing database...")
    try:
        await init_db()
        print("  ✅ Database initialized")
    except Exception as e:
        print(f"  ❌ Database error: {e}")
    
    # Test 3: API Keys
    print("\n[3/4] Checking API keys...")
    checks = {
        "Alchemy": ALCHEMY_API_KEY and ALCHEMY_API_KEY != "YOUR_ALCHEMY_KEY",
        "Telegram": TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != "YOUR_TELEGRAM_BOT_TOKEN",
    }
    for name, ok in checks.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    
    # Test 4: Telegram
    print("\n[4/4] Testing Telegram...")
    try:
        result = await test_telegram()
        print(f"  {'✅' if result else '❌'} Telegram connection")
    except Exception as e:
        print(f"  ❌ Telegram error: {e}")
    
    print("\n" + "=" * 50)
    print("Test complete!")
    print("=" * 50)


async def show_status():
    """Show system status"""
    print("=" * 50)
    print("Smart Money System - Status")
    print("=" * 50)
    
    # Wallets
    wallets = load_wallets()
    print(f"\n📋 Monitored Wallets: {len(wallets)}")
    
    categories = {}
    for addr, info in wallets.items():
        cat = info["category"]
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in categories.items():
        print(f"   {cat}: {count}")
    
    # Database
    print("\n📊 Database:")
    try:
        movements = await get_recent_movements(10)
        print(f"   Recent movements: {len(movements)}")
        
        trades = await get_open_trades()
        print(f"   Open trades: {len(trades)}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # API Keys
    print("\n🔑 API Keys:")
    print(f"   Alchemy: {'✅' if ALCHEMY_API_KEY and ALCHEMY_API_KEY != 'YOUR_ALCHEMY_KEY' else '❌'}")
    print(f"   Telegram: {'✅' if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != 'YOUR_TELEGRAM_BOT_TOKEN' else '❌'}")
    
    print("\n" + "=" * 50)


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1].lower()
    
    if command == "start" or command == "listen":
        print("Starting Smart Money System...")
        print("Press Ctrl+C to stop\n")
        asyncio.run(start_listener())
    
    elif command == "full":
        print("Starting Full Smart Money System...")
        print("Press Ctrl+C to stop\n")
        asyncio.run(start_full_system())
    
    elif command == "live":
        print("Starting Integrated Smart Money System...")
        print("Press Ctrl+C to stop\n")
        from modules.integrated_system import IntegratedSystem
        system = IntegratedSystem(portfolio_value=10000)
        asyncio.run(system.run())
    
    elif command == "predict":
        print("Running Prediction Engine...")
        print("=" * 50)
        from modules.prediction.prediction_engine import PredictionEngine
        engine = PredictionEngine()
        prediction = asyncio.run(engine.predict("ETHUSDT"))
        if "error" not in prediction:
            report = engine.format_prediction(prediction)
            print(report)
        else:
            print(f"Error: {prediction['error']}")
    
    elif command == "accuracy":
        from modules.prediction.confidence_tracker import ConfidenceTracker
        tracker = ConfidenceTracker()
        print(tracker.format_accuracy())
    
    elif command == "regime":
        print("Detecting market regime...")
        from modules.prediction.regime_detector import RegimeDetector
        from modules.backtest.data_fetcher import DataFetcher
        fetcher = DataFetcher()
        candles = asyncio.run(fetcher.get_historical_data("ETHUSDT", "1h", 30))
        if candles:
            detector = RegimeDetector()
            regime = detector.detect(candles)
            print(f"\nRegime: {regime['regime']}")
            print(f"Confidence: {regime['confidence']}")
            print(f"Description: {regime['description']}")
            print(f"\nSub-signals:")
            for name, sig in regime['sub_signals'].items():
                print(f"  {name}: {sig['score']:+.2f} — {sig['desc']}")
        else:
            print("Failed to fetch data")
    
    elif command == "test":
        asyncio.run(test_system())
    
    elif command == "test-signals":
        from modules.signals.signal_runner import test_signal_runner
        asyncio.run(test_signal_runner())
    
    elif command == "test-telegram":
        asyncio.run(test_telegram())
    
    elif command == "test-db":
        asyncio.run(init_db())
        print("Database test complete!")
    
    elif command == "status":
        asyncio.run(show_status())
    
    elif command == "performance" or command == "perf":
        from modules.feedback.performance import PerformanceTracker
        tracker = PerformanceTracker()
        print(tracker.format_report())
    
    elif command == "paper":
        from modules.executor.paper_trader import PaperTrader
        trader = PaperTrader()
        print(trader.format_status())
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
