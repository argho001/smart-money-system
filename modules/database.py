"""
Smart Money System - Database Module
SQLite database for storing wallet movements, signals, and trades.
"""

import aiosqlite
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "smart_money.db")

async def init_db():
    """Initialize database tables"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Wallet movements table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_hash TEXT UNIQUE NOT NULL,
                block_number INTEGER,
                timestamp TEXT,
                from_address TEXT NOT NULL,
                to_address TEXT NOT NULL,
                token TEXT,
                amount REAL,
                amount_usd REAL,
                direction TEXT,
                wallet_label TEXT,
                wallet_category TEXT,
                processed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Signals table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                score REAL,
                signal_text TEXT,
                components TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                acted INTEGER DEFAULT 0
            )
        """)
        
        # Trades table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                coin TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                position_size REAL,
                status TEXT DEFAULT 'open',
                exit_price REAL,
                exit_time TEXT,
                pnl REAL,
                pnl_pct REAL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        """)
        
        # Wallet reliability table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wallet_reliability (
                address TEXT PRIMARY KEY,
                label TEXT,
                category TEXT,
                total_moves INTEGER DEFAULT 0,
                correct_predictions INTEGER DEFAULT 0,
                reliability_score REAL DEFAULT 0.5,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Daily performance table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_performance (
                date TEXT PRIMARY KEY,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                portfolio_value REAL
            )
        """)
        
        await db.commit()
        print("[DB] Database initialized successfully")

async def log_movement(tx_hash, block_number, timestamp, from_addr, to_addr, 
                       token, amount, amount_usd, direction, wallet_label, wallet_category):
    """Log a wallet movement to database"""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("""
                INSERT OR IGNORE INTO movements 
                (tx_hash, block_number, timestamp, from_address, to_address, 
                 token, amount, amount_usd, direction, wallet_label, wallet_category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tx_hash, block_number, timestamp, from_addr, to_addr, 
                  token, amount, amount_usd, direction, wallet_label, wallet_category))
            await db.commit()
            return True
        except Exception as e:
            print(f"[DB] Error logging movement: {e}")
            return False

async def log_signal(coin, signal_type, score, signal_text, components):
    """Log a signal to database"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO signals (coin, signal_type, score, signal_text, components)
            VALUES (?, ?, ?, ?, ?)
        """, (coin, signal_type, score, signal_text, str(components)))
        await db.commit()
        return cursor.lastrowid

async def log_trade(signal_id, coin, side, entry_price, stop_loss, take_profit, position_size):
    """Log a trade to database"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO trades (signal_id, coin, side, entry_price, stop_loss, take_profit, position_size)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (signal_id, coin, side, entry_price, stop_loss, take_profit, position_size))
        await db.commit()
        return cursor.lastrowid

async def get_recent_movements(limit=50):
    """Get recent wallet movements"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM movements 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_open_trades():
    """Get all open trades"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM trades WHERE status = 'open'
            ORDER BY created_at DESC
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_wallet_stats():
    """Get wallet reliability stats"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM wallet_reliability 
            ORDER BY reliability_score DESC
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
