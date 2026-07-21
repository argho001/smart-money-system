"""
Smart Money System - Blockchain Listener
Connects to Alchemy WebSocket and monitors tracked wallets.
Catches transfers, approvals, and token movements in real-time.
"""

import asyncio
import json
import websockets
from datetime import datetime, timezone
from config import (
    ALCHEMY_API_KEY, ETHEREUM_WS_URL, ETHEREUM_HTTP_URL,
    load_wallets, get_tracked_addresses, get_wallet_label, 
    get_wallet_category, get_wallet_priority
)
from modules.database import log_movement

# ERC-20 Transfer event signature
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

class BlockchainListener:
    def __init__(self, callback=None):
        self.ws_url = ETHEREUM_WS_URL
        self.http_url = ETHEREUM_HTTP_URL
        self.tracked_addresses = get_tracked_addresses()
        self.wallets = load_wallets()
        self.callback = callback  # Function to call when movement detected
        self.running = False
        self.ws = None
        
    async def connect(self):
        """Connect to Alchemy WebSocket"""
        try:
            self.ws = await websockets.connect(self.ws_url)
            print(f"[BLOCKCHAIN] Connected to Alchemy WebSocket")
            return True
        except Exception as e:
            print(f"[BLOCKCHAIN] Connection failed: {e}")
            return False
    
    async def subscribe_pending_transactions(self):
        """Subscribe to pending transactions for tracked wallets"""
        if not self.ws:
            return False
        
        # Subscribe to new blocks
        sub_block = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": ["newHeads"]
        }
        await self.ws.send(json.dumps(sub_block))
        response = await self.ws.recv()
        print(f"[BLOCKCHAIN] Subscribed to new blocks: {response[:100]}")
        
        return True
    
    async def get_block_transactions(self, block_number):
        """Get all transactions in a block via HTTP"""
        import aiohttp
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBlockByNumber",
            "params": [hex(block_number), True],
            "id": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.http_url, json=payload) as resp:
                data = await resp.json()
                if "result" in data and data["result"]:
                    return data["result"].get("transactions", [])
        return []
    
    async def get_transaction_receipt(self, tx_hash):
        """Get transaction receipt to see internal transfers and logs"""
        import aiohttp
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getTransactionReceipt",
            "params": [tx_hash],
            "id": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.http_url, json=payload) as resp:
                data = await resp.json()
                if "result" in data:
                    return data["result"]
        return None
    
    async def get_eth_balance(self, address):
        """Get ETH balance for an address"""
        import aiohttp
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [address, "latest"],
            "id": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.http_url, json=payload) as resp:
                data = await resp.json()
                if "result" in data:
                    return int(data["result"], 16) / 1e18
        return 0
    
    def parse_erc20_transfer(self, log):
        """Parse ERC-20 Transfer event from log"""
        if len(log.get("topics", [])) < 3:
            return None
        
        if log["topics"][0] != ERC20_TRANSFER_TOPIC:
            return None
        
        from_addr = "0x" + log["topics"][1][-40:]
        to_addr = "0x" + log["topics"][2][-40:]
        
        # Parse amount (handle different token decimals)
        amount_hex = log.get("data", "0x0")
        if amount_hex == "0x":
            amount_hex = "0x0"
        amount_raw = int(amount_hex, 16)
        
        return {
            "from": from_addr.lower(),
            "to": to_addr.lower(),
            "token": log.get("address", "unknown"),
            "amount_raw": amount_raw,
            "tx_hash": log.get("transactionHash", ""),
            "block_number": int(log.get("blockNumber", "0x0"), 16)
        }
    
    async def process_transaction(self, tx, block_number, block_timestamp):
        """Process a single transaction and check if it involves tracked wallets"""
        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower() if tx.get("to") else ""
        
        # Check if sender or receiver is tracked
        tracked = set(self.tracked_addresses)
        
        if from_addr not in tracked and to_addr not in tracked:
            return None
        
        # Determine direction
        if from_addr in tracked and to_addr in tracked:
            direction = "internal_transfer"
        elif from_addr in tracked:
            direction = "outflow"
        else:
            direction = "inflow"
        
        # ETH transfer
        value_wei = int(tx.get("value", "0x0"), 16)
        value_eth = value_wei / 1e18
        
        if value_eth > 1.0:  # Only log transfers > 1 ETH (ignore dust)
            wallet_addr = from_addr if direction == "outflow" else to_addr
            
            movement = {
                "tx_hash": tx.get("hash", ""),
                "block_number": block_number,
                "timestamp": block_timestamp,
                "from": from_addr,
                "to": to_addr,
                "token": "ETH",
                "amount": value_eth,
                "amount_usd": 0,  # Will be calculated later
                "direction": direction,
                "wallet_label": get_wallet_label(wallet_addr),
                "wallet_category": get_wallet_category(wallet_addr)
            }
            
            return movement
        
        return None
    
    async def process_block(self, block_number):
        """Process all transactions in a block"""
        transactions = await self.get_block_transactions(block_number)
        
        movements = []
        for tx in transactions:
            result = await self.process_transaction(tx, block_number, datetime.now(timezone.utc).isoformat())
            if result:
                movements.append(result)
                
                # Log to database
                await log_movement(
                    tx_hash=result["tx_hash"],
                    block_number=result["block_number"],
                    timestamp=result["timestamp"],
                    from_addr=result["from"],
                    to_addr=result["to"],
                    token=result["token"],
                    amount=result["amount"],
                    amount_usd=result["amount_usd"],
                    direction=result["direction"],
                    wallet_label=result["wallet_label"],
                    wallet_category=result["wallet_category"]
                )
                
                # Call callback if set
                if self.callback:
                    await self.callback(result)
        
        return movements
    
    async def listen(self):
        """Main listen loop - subscribe to blocks and process them"""
        self.running = True
        
        if not await self.connect():
            return
        
        await self.subscribe_pending_transactions()
        
        print(f"[BLOCKCHAIN] Monitoring {len(self.tracked_addresses)} wallets...")
        print(f"[BLOCKCHAIN] Wallets:")
        for addr, info in self.wallets.items():
            print(f"  - {info['label']} ({info['category']}): {addr[:10]}...{addr[-6:]}")
        
        try:
            while self.running:
                try:
                    message = await asyncio.wait_for(self.ws.recv(), timeout=30)
                    data = json.loads(message)
                    
                    # Check if it's a new block notification
                    if "params" in data and "result" in data["params"]:
                        block = data["params"]["result"]
                        block_number = int(block.get("number", "0x0"), 16)
                        block_timestamp = datetime.fromtimestamp(
                            int(block.get("timestamp", "0x0"), 16), 
                            tz=timezone.utc
                        ).isoformat()
                        
                        print(f"[BLOCKCHAIN] New block: #{block_number}")
                        
                        movements = await self.process_block(block_number)
                        
                        if movements:
                            print(f"[BLOCKCHAIN] Found {len(movements)} tracked movements!")
                            for m in movements:
                                print(f"  → {m['wallet_label']}: {m['direction']} "
                                      f"{m['amount']:.4f} {m['token']} "
                                      f"({m['from'][:8]}... → {m['to'][:8]}...)")
                
                except asyncio.TimeoutError:
                    # No message in 30 seconds, send ping to keep connection alive
                    try:
                        await self.ws.ping()
                    except:
                        await self.connect()
                        await self.subscribe_pending_transactions()
                
                except websockets.exceptions.ConnectionClosed:
                    print("[BLOCKCHAIN] Connection closed, reconnecting...")
                    await asyncio.sleep(5)
                    await self.connect()
                    await self.subscribe_pending_transactions()
        
        except KeyboardInterrupt:
            print("\n[BLOCKCHAIN] Stopping listener...")
        finally:
            self.running = False
            if self.ws:
                await self.ws.close()
    
    def stop(self):
        """Stop the listener"""
        self.running = False


async def test_listener():
    """Test the blockchain listener"""
    print("=" * 50)
    print("Smart Money System - Blockchain Listener Test")
    print("=" * 50)
    
    async def on_movement(movement):
        print(f"\n🚨 MOVEMENT DETECTED!")
        print(f"   Wallet: {movement['wallet_label']}")
        print(f"   Category: {movement['wallet_category']}")
        print(f"   Direction: {movement['direction']}")
        print(f"   Amount: {movement['amount']:.4f} {movement['token']}")
        print(f"   From: {movement['from']}")
        print(f"   To: {movement['to']}")
        print(f"   TX: {movement['tx_hash']}")
    
    listener = BlockchainListener(callback=on_movement)
    await listener.listen()


if __name__ == "__main__":
    asyncio.run(test_listener())
