"""
Smart Money System - Telegram Bot
Sends alerts when tracked wallets move.
"""

import asyncio
import aiohttp
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

class TelegramAlerter:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.last_alert_time = {}  # Cooldown tracking
    
    async def send_message(self, text, parse_mode="HTML"):
        """Send a message to Telegram"""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        return True
                    else:
                        print(f"[TELEGRAM] Error: {data.get('description', 'Unknown error')}")
                        return False
        except Exception as e:
            print(f"[TELEGRAM] Failed to send: {e}")
            return False
    
    async def send_movement_alert(self, movement):
        """Send a formatted movement alert"""
        # Cooldown check (prevent spam)
        wallet_key = movement.get("wallet_label", "unknown")
        now = datetime.now().timestamp()
        
        if wallet_key in self.last_alert_time:
            if now - self.last_alert_time[wallet_key] < 60:  # 60s cooldown
                return False
        
        self.last_alert_time[wallet_key] = now
        
        # Format the alert
        direction_emoji = {
            "outflow": "🔴",
            "inflow": "🟢",
            "internal_transfer": "🔄"
        }.get(movement.get("direction", ""), "⚪")
        
        category_emoji = {
            "exchange": "🏦",
            "stablecoin": "💵",
            "market_maker": "🤖",
            "defi": "📐",
            "whale": "🐋",
            "fund": "💼"
        }.get(movement.get("wallet_category", ""), "❓")
        
        amount = movement.get("amount", 0)
        token = movement.get("token", "ETH")
        wallet_label = movement.get("wallet_label", "Unknown")
        category = movement.get("wallet_category", "unknown")
        direction = movement.get("direction", "unknown")
        from_addr = movement.get("from", "0x...")
        to_addr = movement.get("to", "0x...")
        tx_hash = movement.get("tx_hash", "")
        
        # Determine significance
        if amount > 1000:
            significance = "🚨 MASSIVE"
        elif amount > 100:
            significance = "⚠️ LARGE"
        elif amount > 10:
            significance = "📊 NOTABLE"
        else:
            significance = "📝 Small"
        
        text = f"""
{direction_emoji} <b>WALLET MOVEMENT DETECTED</b> {direction_emoji}

{significance} {direction.upper()}

{category_emoji} <b>Wallet:</b> {wallet_label}
📋 <b>Category:</b> {category.title()}
💰 <b>Amount:</b> {amount:,.4f} {token}
📍 <b>Direction:</b> {direction.title()}

📤 <b>From:</b> <code>{from_addr[:10]}...{from_addr[-6:]}</code>
📥 <b>To:</b> <code>{to_addr[:10]}...{to_addr[-6:]}</code>

🔗 <a href="https://etherscan.io/tx/{tx_hash}">View on Etherscan</a>

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        
        return await self.send_message(text)
    
    async def send_signal_alert(self, signal):
        """Send a signal alert"""
        score = signal.get("score", 0)
        coin = signal.get("coin", "Unknown")
        signal_type = signal.get("signal", "HOLD")
        
        # Color based on signal
        emoji = {
            "STRONG_BUY": "🟢🟢",
            "BUY": "🟢",
            "HOLD": "⚪",
            "SELL": "🔴",
            "STRONG_SELL": "🔴🔴"
        }.get(signal_type, "⚪")
        
        text = f"""
{emoji} <b>SIGNAL: {signal_type}</b> {emoji}

🪙 <b>Coin:</b> {coin}
📊 <b>Score:</b> {score:.1f}/100
⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        return await self.send_message(text)
    
    async def send_daily_summary(self, stats):
        """Send a daily summary"""
        text = f"""
📊 <b>DAILY SUMMARY</b> 📊

📅 {datetime.now().strftime('%Y-%m-%d')}

<b>Wallet Movements:</b>
  • Total: {stats.get('total_movements', 0)}
  • Inflows: {stats.get('inflows', 0)}
  • Outflows: {stats.get('outflows', 0)}

<b>Signals:</b>
  • Buy signals: {stats.get('buy_signals', 0)}
  • Sell signals: {stats.get('sell_signals', 0)}

<b>Portfolio:</b>
  • Value: ${stats.get('portfolio_value', 0):,.2f}
  • Daily P&L: ${stats.get('daily_pnl', 0):,.2f}
"""
        
        return await self.send_message(text)
    
    async def send_startup_message(self):
        """Send a startup notification"""
        text = f"""
🚀 <b>SMART MONEY SYSTEM STARTED</b> 🚀

✅ Blockchain listener active
✅ Telegram alerts enabled
✅ Database connected

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Monitoring wallet movements...
"""
        
        return await self.send_message(text)


async def test_telegram():
    """Test Telegram connection"""
    print("Testing Telegram connection...")
    alerter = TelegramAlerter()
    
    result = await alerter.send_message(
        "🧪 <b>Test Message</b>\n\nSmart Money System - Telegram connection working!"
    )
    
    if result:
        print("✅ Telegram test successful!")
    else:
        print("❌ Telegram test failed!")
    
    return result


if __name__ == "__main__":
    asyncio.run(test_telegram())
