"""
Smart Money System - Backtester
Runs trading strategy on historical data and calculates performance.
"""

import json
import os
from datetime import datetime
from modules.backtest.data_fetcher import DataFetcher
from modules.backtest.signal_simulator import SignalSimulator

class Backtester:
    def __init__(self, initial_capital=10000, risk_per_trade=1.0, max_positions=3):
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.max_positions = max_positions
        
        # State
        self.capital = initial_capital
        self.positions = []
        self.closed_trades = []
        self.equity_curve = []
        
    async def run(self, symbol="ETHUSDT", interval="4h", days_back=90, 
                  entry_threshold=30, exit_threshold=-10, stop_loss_pct=3.0, take_profit_pct=6.0):
        """
        Run backtest on historical data.
        
        Args:
            symbol: Trading pair
            interval: Candle interval
            days_back: Days of history
            entry_threshold: Score threshold to enter (positive = buy, negative = sell)
            exit_threshold: Score threshold to exit
            stop_loss_pct: Stop loss percentage
            take_profit_pct: Take profit percentage
        """
        print("=" * 60)
        print(f"BACKTEST: {symbol} {interval} ({days_back} days)")
        print("=" * 60)
        print(f"Capital: ${self.initial_capital:,.2f}")
        print(f"Risk per trade: {self.risk_per_trade}%")
        print(f"Entry threshold: {entry_threshold}")
        print(f"Exit threshold: {exit_threshold}")
        print(f"Stop loss: {stop_loss_pct}%")
        print(f"Take profit: {take_profit_pct}%")
        print("=" * 60)
        
        # Fetch data
        fetcher = DataFetcher()
        candles = await fetcher.get_historical_data(symbol, interval, days_back)
        
        if len(candles) < 50:
            print("[BACKTEST] Not enough data!")
            return None
        
        print(f"\nLoaded {len(candles)} candles")
        print(f"From: {candles[0]['timestamp']}")
        print(f"To: {candles[-1]['timestamp']}")
        
        # Generate signals
        simulator = SignalSimulator()
        signals = simulator.calculate_signals(candles, lookback=20)
        
        print(f"Generated {len(signals)} signals")
        
        # Run simulation
        self.capital = self.initial_capital
        self.positions = []
        self.closed_trades = []
        self.equity_curve = []
        
        for i, signal in enumerate(signals):
            price = signal["price"]
            score = signal["score"]
            timestamp = signal["timestamp"]
            
            # Check existing positions for exit
            self._check_exits(price, timestamp, score, exit_threshold, stop_loss_pct, take_profit_pct)
            
            # Check for new entry
            if len(self.positions) < self.max_positions:
                if score > entry_threshold:
                    self._open_position("LONG", price, timestamp, score, stop_loss_pct, take_profit_pct)
                elif score < -entry_threshold:
                    self._open_position("SHORT", price, timestamp, score, stop_loss_pct, take_profit_pct)
            
            # Record equity
            unrealized_pnl = sum(self._calculate_pnl(pos, price) for pos in self.positions)
            total_equity = self.capital + unrealized_pnl
            self.equity_curve.append({
                "timestamp": timestamp,
                "price": price,
                "equity": total_equity,
                "positions": len(self.positions)
            })
        
        # Close remaining positions at last price
        last_price = signals[-1]["price"]
        last_time = signals[-1]["timestamp"]
        for pos in self.positions[:]:
            self._close_position(pos, last_price, last_time, "End of backtest")
        
        # Calculate results
        results = self._calculate_results()
        self._print_results(results)
        
        return results
    
    def _open_position(self, side, price, timestamp, score, sl_pct, tp_pct):
        """Open a new position"""
        # Calculate position size based on risk
        risk_amount = self.capital * (self.risk_per_trade / 100)
        sl_distance = price * (sl_pct / 100)
        position_size = risk_amount / sl_distance
        
        # Cap at 20% of capital
        max_size = (self.capital * 0.20) / price
        position_size = min(position_size, max_size)
        
        if side == "LONG":
            stop_loss = price * (1 - sl_pct / 100)
            take_profit = price * (1 + tp_pct / 100)
        else:
            stop_loss = price * (1 + sl_pct / 100)
            take_profit = price * (1 - tp_pct / 100)
        
        position = {
            "id": len(self.closed_trades) + len(self.positions) + 1,
            "side": side,
            "entry_price": price,
            "entry_time": timestamp,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_size": position_size,
            "position_value": position_size * price,
            "signal_score": score
        }
        
        self.positions.append(position)
        print(f"  📈 OPEN {side} @ ${price:,.2f} (score: {score:+.1f}) | SL: ${stop_loss:,.2f} | TP: ${take_profit:,.2f}")
    
    def _check_exits(self, price, timestamp, score, exit_threshold, sl_pct, tp_pct):
        """Check if any positions should be closed"""
        for pos in self.positions[:]:
            # Stop loss hit
            if pos["side"] == "LONG" and price <= pos["stop_loss"]:
                self._close_position(pos, price, timestamp, "Stop Loss")
            elif pos["side"] == "SHORT" and price >= pos["stop_loss"]:
                self._close_position(pos, price, timestamp, "Stop Loss")
            
            # Take profit hit
            elif pos["side"] == "LONG" and price >= pos["take_profit"]:
                self._close_position(pos, price, timestamp, "Take Profit")
            elif pos["side"] == "SHORT" and price <= pos["take_profit"]:
                self._close_position(pos, price, timestamp, "Take Profit")
            
            # Signal reversal exit
            elif pos["side"] == "LONG" and score < exit_threshold:
                self._close_position(pos, price, timestamp, "Signal Reversal")
            elif pos["side"] == "SHORT" and score > -exit_threshold:
                self._close_position(pos, price, timestamp, "Signal Reversal")
    
    def _close_position(self, position, price, timestamp, reason):
        """Close a position"""
        pnl = self._calculate_pnl(position, price)
        pnl_pct = (pnl / position["position_value"]) * 100
        
        position["exit_price"] = price
        position["exit_time"] = timestamp
        position["exit_reason"] = reason
        position["pnl"] = round(pnl, 2)
        position["pnl_pct"] = round(pnl_pct, 2)
        position["status"] = "closed"
        
        self.capital += pnl
        self.closed_trades.append(position)
        self.positions.remove(position)
        
        emoji = "✅" if pnl > 0 else "❌"
        print(f"  {emoji} CLOSE {position['side']} @ ${price:,.2f} | P&L: ${pnl:+,.2f} ({pnl_pct:+.2f}%) | {reason}")
    
    def _calculate_pnl(self, position, current_price):
        """Calculate P&L for a position"""
        entry = position["entry_price"]
        size = position["position_size"]
        
        if position["side"] == "LONG":
            return size * (current_price - entry)
        else:
            return size * (entry - current_price)
    
    def _calculate_results(self):
        """Calculate backtest results"""
        if not self.closed_trades:
            return {"error": "No trades executed"}
        
        total_trades = len(self.closed_trades)
        winning_trades = [t for t in self.closed_trades if t["pnl"] > 0]
        losing_trades = [t for t in self.closed_trades if t["pnl"] <= 0]
        
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = (win_count / total_trades) * 100
        
        total_pnl = sum(t["pnl"] for t in self.closed_trades)
        total_return_pct = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        
        avg_win = sum(t["pnl"] for t in winning_trades) / win_count if win_count > 0 else 0
        avg_loss = sum(t["pnl"] for t in losing_trades) / loss_count if loss_count > 0 else 0
        
        gross_profit = sum(t["pnl"] for t in winning_trades)
        gross_loss = abs(sum(t["pnl"] for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        
        # Max drawdown
        peak = self.initial_capital
        max_drawdown = 0
        max_drawdown_pct = 0
        
        for point in self.equity_curve:
            equity = point["equity"]
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            drawdown_pct = (drawdown / peak) * 100
            if drawdown_pct > max_drawdown_pct:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct
        
        # Average trade duration
        durations = []
        for trade in self.closed_trades:
            if trade.get("entry_time") and trade.get("exit_time"):
                try:
                    entry = trade["entry_time"]
                    exit_t = trade["exit_time"]
                    if isinstance(entry, str):
                        entry = datetime.fromisoformat(entry)
                    if isinstance(exit_t, str):
                        exit_t = datetime.fromisoformat(exit_t)
                    duration = (exit_t - entry).total_seconds() / 3600
                    durations.append(duration)
                except:
                    pass
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        # By exit reason
        by_reason = {}
        for trade in self.closed_trades:
            reason = trade.get("exit_reason", "Unknown")
            if reason not in by_reason:
                by_reason[reason] = {"count": 0, "pnl": 0, "wins": 0}
            by_reason[reason]["count"] += 1
            by_reason[reason]["pnl"] += trade["pnl"]
            if trade["pnl"] > 0:
                by_reason[reason]["wins"] += 1
        
        return {
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(total_return_pct, 2),
            "final_capital": round(self.capital, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "avg_duration_hours": round(avg_duration, 1),
            "by_exit_reason": by_reason,
            "equity_curve_points": len(self.equity_curve)
        }
    
    def _print_results(self, results):
        """Print backtest results"""
        if "error" in results:
            print(f"\n❌ {results['error']}")
            return
        
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        
        pnl_emoji = "🟢" if results["total_pnl"] >= 0 else "🔴"
        
        print(f"""
💰 Capital: ${self.initial_capital:,.2f} → ${results['final_capital']:,.2f}
{pnl_emoji} Total P&L: ${results['total_pnl']:+,.2f} ({results['total_return_pct']:+.2f}%)

📊 Trades: {results['total_trades']}
   Wins: {results['winning_trades']} ({results['win_rate']}%)
   Losses: {results['losing_trades']}

📈 Avg Win: ${results['avg_win']:+,.2f}
📉 Avg Loss: ${results['avg_loss']:+,.2f}
💎 Profit Factor: {results['profit_factor']}
⏱️ Avg Duration: {results['avg_duration_hours']:.1f}h

⚠️ Max Drawdown: ${results['max_drawdown']:,.2f} ({results['max_drawdown_pct']:.1f}%)
""")
        
        if results.get("by_exit_reason"):
            print("📋 Exit Reasons:")
            for reason, data in results["by_exit_reason"].items():
                win_rate = (data["wins"] / data["count"] * 100) if data["count"] > 0 else 0
                print(f"   {reason}: {data['count']} trades, ${data['pnl']:+,.2f}, {win_rate:.0f}% win rate")
        
        # Grade
        wr = results["win_rate"]
        pf = results["profit_factor"]
        
        if wr >= 60 and pf >= 2.0:
            grade = "A+ (Excellent)"
        elif wr >= 55 and pf >= 1.5:
            grade = "A (Very Good)"
        elif wr >= 50 and pf >= 1.3:
            grade = "B (Good)"
        elif wr >= 45 and pf >= 1.0:
            grade = "C (Average)"
        elif pf >= 1.0:
            grade = "D (Below Average)"
        else:
            grade = "F (Losing Strategy)"
        
        print(f"\n🎯 Strategy Grade: {grade}")
        print("=" * 60)
        
        # Save results
        os.makedirs("data/backtests", exist_ok=True)
        filename = f"data/backtests/backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n📁 Results saved to: {filename}")


async def run_backtest():
    """Run a complete backtest"""
    backtester = Backtester(
        initial_capital=10000,
        risk_per_trade=1.0,
        max_positions=1
    )
    
    results = await backtester.run(
        symbol="ETHUSDT",
        interval="4h",
        days_back=90,
        entry_threshold=30,
        exit_threshold=-10,
        stop_loss_pct=3.0,
        take_profit_pct=6.0
    )
    
    return results


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_backtest())
