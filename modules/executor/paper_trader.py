"""
Smart Money System - Paper Trader
Simulates trades without real money.
Tracks hypothetical positions, P&L, and performance.
"""

import json
import os
import sys
from datetime import datetime

# Fix import path for standalone testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from modules.database import log_trade
except ImportError:
    log_trade = None  # Will work without DB in standalone mode

TRADES_FILE = "data/paper_trades.json"

class PaperTrader:
    def __init__(self, portfolio_value=10000, max_risk_pct=1.0, max_positions=3):
        self.initial_portfolio = portfolio_value
        self.portfolio_value = portfolio_value
        self.max_risk_pct = max_risk_pct
        self.max_positions = max_positions
        self.trades = []
        self.closed_trades = []
        
        # Load existing trades
        self._load_trades()
    
    def _load_trades(self):
        """Load trades from file"""
        if os.path.exists(TRADES_FILE):
            try:
                with open(TRADES_FILE, "r") as f:
                    data = json.load(f)
                    self.trades = data.get("open_trades", [])
                    self.closed_trades = data.get("closed_trades", [])
                    self.portfolio_value = data.get("portfolio_value", self.initial_portfolio)
            except:
                pass
    
    def _save_trades(self):
        """Save trades to file"""
        os.makedirs(os.path.dirname(TRADES_FILE), exist_ok=True)
        data = {
            "portfolio_value": self.portfolio_value,
            "open_trades": self.trades,
            "closed_trades": self.closed_trades[-100:],  # Keep last 100
            "last_updated": datetime.now().isoformat()
        }
        with open(TRADES_FILE, "w") as f:
            json.dump(data, f, indent=2)
    
    def can_open_trade(self):
        """Check if we can open a new trade"""
        if len(self.trades) >= self.max_positions:
            return False, f"Max positions reached ({self.max_positions})"
        return True, "OK"
    
    def calculate_position_size(self, entry_price, stop_loss_pct):
        """
        Calculate position size based on risk management.
        Risk = portfolio * max_risk_pct%
        Position = risk / stop_loss_distance
        """
        risk_amount = self.portfolio_value * (self.max_risk_pct / 100)
        stop_loss_distance = entry_price * (stop_loss_pct / 100)
        
        if stop_loss_distance <= 0:
            return 0
        
        position_size = risk_amount / stop_loss_distance
        position_value = position_size * entry_price
        
        # Cap at 20% of portfolio
        max_position_value = self.portfolio_value * 0.20
        if position_value > max_position_value:
            position_size = max_position_value / entry_price
        
        return round(position_size, 6)
    
    def open_trade(self, coin, side, entry_price, stop_loss, take_profit_1, take_profit_2, signal_score):
        """Open a new paper trade"""
        can_trade, reason = self.can_open_trade()
        if not can_trade:
            return None, reason
        
        # Calculate stop loss percentage
        if side == "LONG":
            sl_pct = ((entry_price - stop_loss) / entry_price) * 100
        else:
            sl_pct = ((stop_loss - entry_price) / entry_price) * 100
        
        # Calculate position size
        position_size = self.calculate_position_size(entry_price, sl_pct)
        
        if position_size <= 0:
            return None, "Position size too small"
        
        trade = {
            "id": len(self.trades) + len(self.closed_trades) + 1,
            "coin": coin,
            "side": side,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "position_size": position_size,
            "position_value": round(position_size * entry_price, 2),
            "signal_score": signal_score,
            "status": "open",
            "opened_at": datetime.now().isoformat(),
            "pnl": 0,
            "pnl_pct": 0
        }
        
        self.trades.append(trade)
        self._save_trades()
        
        print(f"[PAPER] Opened {side} {coin} @ ${entry_price:,.2f}")
        print(f"  Size: {position_size:.6f} ({trade['position_value']:.2f} USD)")
        print(f"  SL: ${stop_loss:,.2f} | TP1: ${take_profit_1:,.2f} | TP2: ${take_profit_2:,.2f}")
        
        return trade, "OK"
    
    def check_trades(self, current_prices):
        """
        Check open trades against current prices.
        Close trades that hit SL or TP.
        Returns list of closed trades.
        """
        closed = []
        
        for trade in self.trades[:]:  # Copy list to allow modification
            coin = trade["coin"]
            if coin not in current_prices:
                continue
            
            current_price = current_prices[coin]
            entry = trade["entry_price"]
            sl = trade["stop_loss"]
            tp1 = trade["take_profit_1"]
            tp2 = trade["take_profit_2"]
            
            # Calculate current P&L
            if trade["side"] == "LONG":
                pnl_pct = ((current_price - entry) / entry) * 100
                hit_sl = current_price <= sl
                hit_tp = current_price >= tp2
            else:
                pnl_pct = ((entry - current_price) / entry) * 100
                hit_sl = current_price >= sl
                hit_tp = current_price <= tp2
            
            pnl_usd = trade["position_value"] * (pnl_pct / 100)
            
            # Update trade
            trade["pnl"] = round(pnl_usd, 2)
            trade["pnl_pct"] = round(pnl_pct, 2)
            trade["current_price"] = current_price
            
            # Check exit conditions
            if hit_sl:
                trade["status"] = "closed_sl"
                trade["exit_price"] = current_price
                trade["exit_time"] = datetime.now().isoformat()
                trade["exit_reason"] = "Stop Loss"
                self.portfolio_value += pnl_usd
                closed.append(trade)
                self.trades.remove(trade)
                print(f"[PAPER] ❌ SL HIT: {trade['side']} {coin} @ ${current_price:,.2f} | P&L: ${pnl_usd:+,.2f}")
            
            elif hit_tp:
                trade["status"] = "closed_tp"
                trade["exit_price"] = current_price
                trade["exit_time"] = datetime.now().isoformat()
                trade["exit_reason"] = "Take Profit"
                self.portfolio_value += pnl_usd
                closed.append(trade)
                self.trades.remove(trade)
                print(f"[PAPER] ✅ TP HIT: {trade['side']} {coin} @ ${current_price:,.2f} | P&L: ${pnl_usd:+,.2f}")
        
        if closed:
            self.closed_trades.extend(closed)
            self._save_trades()
        
        return closed
    
    def get_status(self):
        """Get portfolio status"""
        total_unrealized_pnl = sum(t["pnl"] for t in self.trades)
        total_realized_pnl = sum(t["pnl"] for t in self.closed_trades)
        
        # Win rate
        if self.closed_trades:
            wins = len([t for t in self.closed_trades if t["pnl"] > 0])
            win_rate = (wins / len(self.closed_trades)) * 100
        else:
            win_rate = 0
        
        return {
            "portfolio_value": round(self.portfolio_value, 2),
            "initial_value": self.initial_portfolio,
            "total_pnl": round(self.portfolio_value - self.initial_portfolio, 2),
            "total_pnl_pct": round(((self.portfolio_value - self.initial_portfolio) / self.initial_portfolio) * 100, 2),
            "unrealized_pnl": round(total_unrealized_pnl, 2),
            "realized_pnl": round(total_realized_pnl, 2),
            "open_trades": len(self.trades),
            "closed_trades": len(self.closed_trades),
            "win_rate": round(win_rate, 1),
            "open_positions": self.trades
        }
    
    def format_status(self):
        """Format status for display"""
        status = self.get_status()
        
        pnl_emoji = "🟢" if status["total_pnl"] >= 0 else "🔴"
        
        # Open positions
        positions_text = ""
        for trade in status["open_positions"]:
            trade_emoji = "🟢" if trade["pnl"] >= 0 else "🔴"
            positions_text += f"\n  {trade_emoji} {trade['side']} {trade['coin']} @ ${trade['entry_price']:,.2f} | P&L: ${trade['pnl']:+,.2f} ({trade['pnl_pct']:+.2f}%)"
        
        if not positions_text:
            positions_text = "\n  No open positions"
        
        text = f"""
📊 <b>PAPER TRADING STATUS</b>

💰 <b>Portfolio:</b> ${status['portfolio_value']:,.2f}
{pnl_emoji} <b>Total P&L:</b> ${status['total_pnl']:+,.2f} ({status['total_pnl_pct']:+.2f}%)
📈 <b>Unrealized:</b> ${status['unrealized_pnl']:+,.2f}
📉 <b>Realized:</b> ${status['realized_pnl']:+,.2f}

<b>📊 Statistics:</b>
  Open: {status['open_trades']} trades
  Closed: {status['closed_trades']} trades
  Win Rate: {status['win_rate']}%

<b>📋 Open Positions:</b>{positions_text}
"""
        return text.strip()


def test_paper_trader():
    """Test the paper trader"""
    print("=" * 50)
    print("Paper Trader - Test")
    print("=" * 50)
    
    trader = PaperTrader(portfolio_value=10000)
    
    # Open a test trade
    trade, reason = trader.open_trade(
        coin="ETHUSDT",
        side="LONG",
        entry_price=1931,
        stop_loss=1873,
        take_profit_1=1989,
        take_profit_2=2047,
        signal_score=48.3
    )
    
    if trade:
        print(f"\nTrade opened: {trade['id']}")
        
        # Simulate price check
        closed = trader.check_trades({"ETHUSDT": 1950})
        print(f"\nPrice at $1,950:")
        print(f"  P&L: ${trade['pnl']:+,.2f} ({trade['pnl_pct']:+.2f}%)")
        
        # Show status
        print(f"\n{trader.format_status()}")
    
    return trader


if __name__ == "__main__":
    test_paper_trader()
