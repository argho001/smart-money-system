"""
Smart Money System - Performance Tracker
Calculates trading performance metrics.
"""

import json
import os
from datetime import datetime, timedelta

TRADES_FILE = "data/paper_trades.json"

class PerformanceTracker:
    def __init__(self):
        self.trades_file = TRADES_FILE
    
    def load_trades(self):
        """Load all trades from file"""
        if os.path.exists(self.trades_file):
            with open(self.trades_file, "r") as f:
                return json.load(f)
        return {"open_trades": [], "closed_trades": [], "portfolio_value": 10000}
    
    def calculate_metrics(self):
        """Calculate comprehensive performance metrics"""
        data = self.load_trades()
        closed = data.get("closed_trades", [])
        open_trades = data.get("open_trades", [])
        portfolio_value = data.get("portfolio_value", 10000)
        initial_value = 10000
        
        if not closed:
            return {
                "total_trades": 0,
                "message": "No closed trades yet"
            }
        
        # Basic stats
        total_trades = len(closed)
        winning_trades = [t for t in closed if t.get("pnl", 0) > 0]
        losing_trades = [t for t in closed if t.get("pnl", 0) <= 0]
        
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        
        # P&L
        total_pnl = sum(t.get("pnl", 0) for t in closed)
        total_pnl_pct = ((portfolio_value - initial_value) / initial_value) * 100
        
        avg_win = sum(t.get("pnl", 0) for t in winning_trades) / win_count if win_count > 0 else 0
        avg_loss = sum(t.get("pnl", 0) for t in losing_trades) / loss_count if loss_count > 0 else 0
        
        # Profit factor
        gross_profit = sum(t.get("pnl", 0) for t in winning_trades)
        gross_loss = abs(sum(t.get("pnl", 0) for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        
        # Max drawdown
        running_pnl = 0
        peak = initial_value
        max_drawdown = 0
        max_drawdown_pct = 0
        
        for trade in closed:
            running_pnl += trade.get("pnl", 0)
            current = initial_value + running_pnl
            if current > peak:
                peak = current
            drawdown = peak - current
            drawdown_pct = (drawdown / peak) * 100
            if drawdown_pct > max_drawdown_pct:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct
        
        # Average trade duration
        durations = []
        for trade in closed:
            opened = trade.get("opened_at", "")
            closed_at = trade.get("exit_time", "")
            if opened and closed_at:
                try:
                    open_time = datetime.fromisoformat(opened)
                    close_time = datetime.fromisoformat(closed_at)
                    duration = (close_time - open_time).total_seconds() / 3600  # hours
                    durations.append(duration)
                except:
                    pass
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        # Signal score correlation
        signal_trades = [t for t in closed if "signal_score" in t]
        if signal_trades:
            high_score = [t for t in signal_trades if abs(t.get("signal_score", 0)) > 50]
            low_score = [t for t in signal_trades if abs(t.get("signal_score", 0)) <= 50]
            
            high_win_rate = len([t for t in high_score if t.get("pnl", 0) > 0]) / len(high_score) * 100 if high_score else 0
            low_win_rate = len([t for t in low_score if t.get("pnl", 0) > 0]) / len(low_score) * 100 if low_score else 0
        else:
            high_win_rate = 0
            low_win_rate = 0
        
        return {
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "avg_duration_hours": round(avg_duration, 1),
            "high_signal_win_rate": round(high_win_rate, 1),
            "low_signal_win_rate": round(low_win_rate, 1),
            "portfolio_value": round(portfolio_value, 2),
            "open_trades": len(open_trades)
        }
    
    def format_report(self):
        """Format performance report for display"""
        m = self.calculate_metrics()
        
        if m.get("total_trades", 0) == 0:
            return "📊 No trades completed yet. Keep the system running!"
        
        pnl_emoji = "🟢" if m["total_pnl"] >= 0 else "🔴"
        
        # Grade
        if m["win_rate"] >= 60 and m["profit_factor"] >= 1.5:
            grade = "A"
        elif m["win_rate"] >= 50 and m["profit_factor"] >= 1.2:
            grade = "B"
        elif m["win_rate"] >= 45 and m["profit_factor"] >= 1.0:
            grade = "C"
        else:
            grade = "D"
        
        report = f"""
📊 <b>PERFORMANCE REPORT</b>

{pnl_emoji} <b>Total P&L:</b> ${m['total_pnl']:+,.2f} ({m['total_pnl_pct']:+.2f}%)
💰 <b>Portfolio:</b> ${m['portfolio_value']:,.2f}

<b>📈 Statistics:</b>
  Total Trades: {m['total_trades']}
  Win Rate: {m['win_rate']}% ({m['winning_trades']}W / {m['losing_trades']}L)
  Profit Factor: {m['profit_factor']}
  Avg Win: ${m['avg_win']:+,.2f}
  Avg Loss: ${m['avg_loss']:+,.2f}
  Max Drawdown: ${m['max_drawdown']:,.2f} ({m['max_drawdown_pct']:.1f}%)
  Avg Duration: {m['avg_duration_hours']:.1f}h

<b>🎯 Signal Quality:</b>
  High score trades win rate: {m['high_signal_win_rate']}%
  Low score trades win rate: {m['low_signal_win_rate']}%

<b>📋 Grade:</b> {grade}

<b>📊 Open Positions:</b> {m['open_trades']}
"""
        return report.strip()


def test_performance():
    """Test performance tracker"""
    tracker = PerformanceTracker()
    print(tracker.format_report())


if __name__ == "__main__":
    test_performance()
