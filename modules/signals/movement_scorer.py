"""
Smart Money System - Movement Scorer
Scores each wallet movement and determines if it's bullish or bearish.
"""

from datetime import datetime, timedelta

class MovementScorer:
    def __init__(self):
        # Track recent movements to detect patterns
        self.recent_movements = {}
        self.alert_history = {}
    
    def score_movement(self, movement):
        """
        Score a movement from -100 (very bearish) to +100 (very bullish)
        Returns: (score, signal, reason)
        """
        score = 0
        reasons = []
        
        direction = movement.get("direction", "")
        category = movement.get("wallet_category", "")
        wallet_label = movement.get("wallet_label", "")
        amount = movement.get("amount", 0)
        token = movement.get("token", "ETH")
        
        # === Rule 1: Direction ===
        if direction == "outflow":
            # Coins leaving exchange = bullish (holding)
            score += 30
            reasons.append("Outflow from exchange → holding")
        elif direction == "inflow":
            # Coins entering exchange = bearish (about to sell)
            score -= 30
            reasons.append("Inflow to exchange → may sell")
        elif direction == "internal_transfer":
            score += 0
            reasons.append("Internal transfer → neutral")
        
        # === Rule 2: Category weight ===
        category_weights = {
            "exchange": 1.0,      # Standard weight
            "market_maker": 1.5,  # Market makers are more important
            "fund": 2.0,          # Funds are very important
            "whale": 1.8,         # Whales are important
            "stablecoin": 1.3,    # Stablecoin flows matter
            "defi": 0.8           # DeFi is less important
        }
        weight = category_weights.get(category, 1.0)
        score = score * weight
        
        if weight > 1.0:
            reasons.append(f"{category.title()} wallet = higher weight ({weight}x)")
        
        # === Rule 3: Amount significance ===
        if amount > 1000:
            score *= 2.0
            reasons.append(f"MASSIVE amount ({amount:,.0f} {token}) = 2x weight")
        elif amount > 100:
            score *= 1.5
            reasons.append(f"Large amount ({amount:,.0f} {token}) = 1.5x weight")
        elif amount > 10:
            score *= 1.0
            reasons.append(f"Notable amount ({amount:,.0f} {token})")
        elif amount > 1:
            score *= 0.5
            reasons.append(f"Small amount ({amount:,.2f} {token}) = 0.5x weight")
        else:
            score *= 0.1
            reasons.append(f"Tiny amount ({amount:,.4f} {token}) = ignore")
        
        # === Rule 4: Specific wallet bonuses ===
        wallet_bonuses = {
            "Jump Trading": 15,
            "Wintermute": 15,
            "Galaxy Digital": 20,
            "a16z Crypto Fund": 20,
            "Justin Sun / Tron": 15,
            "USDT Treasury (Tether)": 25,
            "USDC Treasury (Circle)": 25,
        }
        
        bonus = wallet_bonuses.get(wallet_label, 0)
        if bonus > 0:
            score += bonus if direction == "outflow" else -bonus
            reasons.append(f"{wallet_label} = {abs(bonus)} point {'bonus' if bonus > 0 else 'penalty'}")
        
        # === Rule 5: Pattern detection (same wallet moving repeatedly) ===
        wallet_key = f"{wallet_label}_{direction}"
        now = datetime.now()
        
        if wallet_key in self.recent_movements:
            last_time = self.recent_movements[wallet_key]
            time_diff = (now - last_time).total_seconds() / 60  # minutes
            
            if time_diff < 60:  # Same wallet, same direction, within 1 hour
                score *= 1.5
                reasons.append(f"Repeated {direction} within {time_diff:.0f}min = pattern detected")
        
        self.recent_movements[wallet_key] = now
        
        # === Clamp score ===
        score = max(-100, min(100, score))
        
        # === Determine signal ===
        if score > 50:
            signal = "STRONG_BUY"
        elif score > 20:
            signal = "BUY"
        elif score > -20:
            signal = "HOLD"
        elif score > -50:
            signal = "SELL"
        else:
            signal = "STRONG_SELL"
        
        return score, signal, reasons
    
    def format_alert(self, movement, score, signal, reasons):
        """Format a scored alert for Telegram"""
        direction = movement.get("direction", "")
        wallet_label = movement.get("wallet_label", "")
        category = movement.get("wallet_category", "")
        amount = movement.get("amount", 0)
        token = movement.get("token", "ETH")
        from_addr = movement.get("from", "0x...")
        to_addr = movement.get("to", "0x...")
        tx_hash = movement.get("tx_hash", "")
        
        # Signal emoji
        signal_emoji = {
            "STRONG_BUY": "🟢🟢",
            "BUY": "🟢",
            "HOLD": "⚪",
            "SELL": "🔴",
            "STRONG_SELL": "🔴🔴"
        }.get(signal, "⚪")
        
        # Direction emoji
        dir_emoji = {
            "outflow": "📤",
            "inflow": "📥",
            "internal_transfer": "🔄"
        }.get(direction, "❓")
        
        # Category emoji
        cat_emoji = {
            "exchange": "🏦",
            "stablecoin": "💵",
            "market_maker": "🤖",
            "defi": "📐",
            "whale": "🐋",
            "fund": "💼"
        }.get(category, "❓")
        
        # Score bar
        score_bar = self._score_bar(score)
        
        # Build reasons text
        reasons_text = "\n".join([f"  • {r}" for r in reasons])
        
        text = f"""
{signal_emoji} <b>SIGNAL: {signal}</b> {signal_emoji}

{dir_emoji} <b>{direction.upper()}</b> — {amount:,.4f} {token}

{cat_emoji} <b>Wallet:</b> {wallet_label}
📊 <b>Score:</b> {score:+.0f}/100 {score_bar}

<b>Analysis:</b>
{reasons_text}

📤 <b>From:</b> <code>{from_addr[:10]}...{from_addr[-6:]}</code>
📥 <b>To:</b> <code>{to_addr[:10]}...{to_addr[-6:]}</code>

🔗 <a href="https://etherscan.io/tx/{tx_hash}">View TX</a>
⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        return text.strip()
    
    def _score_bar(self, score):
        """Visual score bar"""
        normalized = int((score + 100) / 200 * 10)
        bar = "▓" * normalized + "░" * (10 - normalized)
        return f"[{bar}]"


# Test it
if __name__ == "__main__":
    scorer = MovementScorer()
    
    # Test cases
    test_movements = [
        {
            "direction": "outflow",
            "wallet_category": "fund",
            "wallet_label": "a16z Crypto Fund",
            "amount": 500,
            "token": "ETH",
            "from": "0x8EB8a3b98659Cce2904028aeBe8ff6D5dCE6d8c6",
            "to": "0x1234567890abcdef1234567890abcdef12345678",
            "tx_hash": "0xabc123"
        },
        {
            "direction": "inflow",
            "wallet_category": "exchange",
            "wallet_label": "Binance Hot Wallet 14",
            "amount": 200,
            "token": "ETH",
            "from": "0x1234567890abcdef1234567890abcdef12345678",
            "to": "0x28C6c06298d514Db089934071355E5743bf21d60",
            "tx_hash": "0xdef456"
        },
        {
            "direction": "outflow",
            "wallet_category": "market_maker",
            "wallet_label": "Jump Trading",
            "amount": 50,
            "token": "ETH",
            "from": "0xf584f8728b874a6a5c7a8d4d387c9aae9172d621",
            "to": "0x9876543210fedcba9876543210fedcba98765432",
            "tx_hash": "0xghi789"
        },
        {
            "direction": "outflow",
            "wallet_category": "stablecoin",
            "wallet_label": "USDT Treasury (Tether)",
            "amount": 500000,
            "token": "USDT",
            "from": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "to": "0x1111111111111111111111111111111111111111",
            "tx_hash": "0xjkl012"
        },
    ]
    
    print("=" * 60)
    print("MOVEMENT SCORER TEST")
    print("=" * 60)
    
    for m in test_movements:
        score, signal, reasons = scorer.score_movement(m)
        alert = scorer.format_alert(m, score, signal, reasons)
        print(f"\n{alert}")
        print("-" * 40)
