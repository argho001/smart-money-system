# 🧠 Smart Money System

A personal crypto trading system that tracks whale wallets, analyzes market fundamentals, and generates trading signals.

## 📋 Table of Contents

- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [What's Built](#whats-built)
- [What's Left](#whats-left)
- [Full Plan](#full-plan)
- [Setup](#setup)
- [Commands](#commands)
- [File Structure](#file-structure)
- [Backtest Results](#backtest-results)
- [Roadmap](#roadmap)

---

## What It Does

```
Data Collection → Signal Generation → Trade Execution → Learning
     ↓                  ↓                  ↓              ↓
 19 wallets        6 signal types      Paper trading    Auto-tune
 5 data sources    Weighted scoring    Risk management  Performance
 Real-time         -100 to +100       Position sizing  Improvement
```

**Core Idea:** Follow smart money (whales, institutions). Ignore the crowd (retail).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      USER INTERFACE                          │
│                    Telegram Alerts + CLI                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     SIGNAL ENGINE                            │
│           Combine all signals → Score → Decide               │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────┘
   │          │          │          │          │
┌──▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│Wallet│ │ Order │ │Funding│ │Sentim.│ │Exchange│
│Track │ │ Book  │ │ Rate  │ │Engine │ │ Flow  │
└──┬───┘ └───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘
   │         │         │         │          │
┌──▼─────────▼─────────▼─────────▼──────────▼─────────────────┐
│                      DATA LAYER                              │
│       Blockchain Node + Exchange API + Social API            │
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    TRADE EXECUTOR                             │
│        Position Sizing → Order Placement → Monitoring         │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    FEEDBACK LOOP                              │
│        Track Results → Calculate Metrics → Auto-Tune          │
└─────────────────────────────────────────────────────────────┘
```

---

## What's Built ✅

### Phase 1: Data Collection (DONE)
- [x] Blockchain listener (Alchemy WebSocket)
- [x] 19 whale/exchange wallet tracking
- [x] Real-time movement detection
- [x] SQLite database for storage
- [x] Telegram alerts with scoring

### Phase 2: Signal Engine (DONE)
- [x] Order Book Signal (Binance API)
- [x] Funding Rate Signal (Binance Futures)
- [x] Sentiment Signal (Fear & Greed Index)
- [x] Exchange Flow Signal (Etherscan)
- [x] Wallet Movement Scorer
- [x] Signal Combiner (weighted scoring)
- [x] Signal Runner (periodic execution)

### Phase 3: Paper Trading (DONE)
- [x] Simulated trade execution
- [x] Position sizing based on risk
- [x] Stop loss / take profit
- [x] Portfolio tracking

### Phase 4: Backtesting (DONE)
- [x] Historical data fetcher (Binance)
- [x] Signal simulator
- [x] Backtester engine
- [x] Performance metrics
- [x] Parameter optimization

### Phase 5: Performance Tracking (DONE)
- [x] Win rate, profit factor, max drawdown
- [x] Signal quality correlation
- [x] Trade journal

---

## What's Left ⬜

### Phase 6: Fundamental Analysis (NEXT)
- [ ] Supply metrics (staked, burned, issued)
- [ ] Demand metrics (DeFi TVL, gas, active addresses)
- [ ] Liquidity metrics (stablecoin supply, exchange flows)
- [ ] Macro tracker (BTC, DXY, rates)
- [ ] Fundamental dashboard

### Phase 7: Enhanced Signals
- [ ] Liquidation data (Coinglass)
- [ ] Social sentiment (Twitter NLP)
- [ ] On-chain metrics (MVRV, NVT)
- [ ] Multi-timeframe analysis
- [ ] Signal correlation/conflict detection

### Phase 8: Live Trading
- [ ] Binance API integration (real orders)
- [ ] Order execution engine
- [ ] Slippage handling
- [ ] Error recovery
- [ ] Position monitoring

### Phase 9: Intelligence
- [ ] Wallet reliability scoring
- [ ] Pattern discovery
- [ ] Auto-tuning (ML)
- [ ] Market regime detection
- [ ] Dynamic weight adjustment

### Phase 10: Scale
- [ ] Multi-chain (Solana, Base)
- [ ] Multi-exchange
- [ ] Web dashboard
- [ ] Mobile app
- [ ] API for external access

---

## Full Plan

### Week 1-2: Data Foundation ✅
```
[x] Alchemy WebSocket connection
[x] Wallet registry (19 wallets)
[x] Movement detector
[x] SQLite database
[x] Telegram alerts
```

### Week 3-4: Signal Engine ✅
```
[x] Order book signal (Binance)
[x] Funding rate signal
[x] Sentiment signal (Fear & Greed)
[x] Exchange flow signal
[x] Signal combiner
```

### Week 5-6: Trading System ✅
```
[x] Paper trader
[x] Position calculator
[x] Risk management
[x] Backtesting engine
```

### Week 7-8: Optimization ✅
```
[x] Parameter optimization
[x] Performance metrics
[x] Signal accuracy analysis
[x] Strategy grading
```

### Week 9-10: Fundamental Analysis (NEXT)
```
[ ] Supply metrics (Beaconcha.in)
[ ] Demand metrics (DefiLlama)
[ ] Liquidity metrics (DefiLlama)
[ ] Macro tracker (Yahoo Finance)
[ ] Fundamental dashboard
```

### Week 11-12: Enhanced Intelligence
```
[ ] Wallet reliability scoring
[ ] Liquidation data
[ ] Social sentiment
[ ] Auto-tuning
```

### Week 13-14: Live Trading
```
[ ] Binance real API
[ ] Order execution
[ ] Error handling
[ ] Live monitoring
```

### Week 15-16: Scale
```
[ ] Multi-chain support
[ ] Web dashboard
[ ] Mobile alerts
[ ] Performance optimization
```

---

## Setup

### Prerequisites
- Python 3.11+
- API keys (see below)

### Install
```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/smart-money-system.git
cd smart-money-system

# Install dependencies
pip install -r requirements.txt

# Copy config template
cp config/settings.example.py config/settings.py

# Edit config with your API keys
nano config/settings.py

# Test everything
python main.py test

# Start the system
python main.py live
```

### API Keys Needed (All Free)
| Service | Get It At | Purpose |
|---------|----------|---------|
| Alchemy | alchemy.com | Blockchain data |
| Etherscan | etherscan.io | Wallet labels |
| Binance | binance.com | Market data |
| Telegram | @BotFather | Alerts |

---

## Commands

| Command | Description |
|---------|-------------|
| `python main.py live` | Start full integrated system |
| `python main.py start` | Start blockchain listener only |
| `python main.py test` | Test all components |
| `python main.py test-signals` | Test signal engine |
| `python main.py test-telegram` | Test Telegram connection |
| `python main.py paper` | Show paper trading status |
| `python main.py performance` | Show performance report |
| `python main.py status` | Show system status |

---

## File Structure

```
smart-money-system/
│
├── README.md                          # This file
├── PLAN.md                            # Full project plan
├── BACKTEST_RESULTS.md                # Backtest analysis
├── requirements.txt                   # Python dependencies
├── .gitignore                         # Git ignore rules
├── main.py                            # Entry point
│
├── config/
│   ├── __init__.py                    # Config loader
│   ├── settings.example.py            # Config template (safe to commit)
│   └── wallets.json                   # Wallet watchlist (19 wallets)
│
├── modules/
│   ├── __init__.py
│   ├── database.py                    # SQLite database
│   ├── integrated_system.py           # Full system integration
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   └── blockchain_listener.py     # Alchemy WebSocket listener
│   │
│   ├── signals/
│   │   ├── __init__.py
│   │   ├── movement_scorer.py         # Wallet movement scoring
│   │   ├── orderbook_signal.py        # Order book signal (Binance)
│   │   ├── funding_rate_signal.py     # Funding rate signal
│   │   ├── sentiment_signal.py        # Fear & Greed signal
│   │   ├── exchange_flow_signal.py    # Exchange flow signal
│   │   ├── combiner.py                # Signal combiner (weighted)
│   │   └── signal_runner.py           # Periodic signal runner
│   │
│   ├── executor/
│   │   ├── __init__.py
│   │   └── paper_trader.py            # Simulated trading
│   │
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── data_fetcher.py            # Historical data fetcher
│   │   ├── signal_simulator.py        # Signal simulator
│   │   ├── real_signal_simulator.py   # Real signal simulator
│   │   └── backtester.py              # Backtesting engine
│   │
│   ├── feedback/
│   │   ├── __init__.py
│   │   └── performance.py             # Performance tracker
│   │
│   └── ui/
│       ├── __init__.py
│       └── telegram_bot.py            # Telegram alerts
│
├── data/
│   ├── .gitkeep
│   ├── candles/                       # Historical price cache
│   ├── backtests/                     # Backtest results
│   └── paper_trades.json              # Paper trading state
│
├── scripts/
│   └── setup.sh                       # Setup script
│
└── logs/
    └── .gitkeep
```

---

## Backtest Results

### 90-Day ETH Backtest (Real Signals)

| Config | Trades | Win Rate | Return | Profit Factor | Grade |
|--------|--------|----------|--------|---------------|-------|
| Entry=25 | 26 | 38.5% | +1.99% | 1.10 | C |
| Entry=30 | 23 | 43.5% | +2.51% | 1.14 | C |
| Entry=35 | 11 | 45.5% | +4.40% | 1.47 | B |
| **Entry=40** | **7** | **71.4%** | **+7.58%** | **3.46** | **A** |

### Best Config
```
Entry threshold:  ±40 (high conviction only)
Stop loss:        3%
Take profit:      6%
Trades in 90 days: 7
Win rate:         71.4%
Return:           +7.58%
Profit factor:    3.46
```

### vs Buy and Hold
| Strategy | Return |
|----------|--------|
| Buy & Hold ETH | -19.6% |
| Our Strategy | +7.58% |
| **Difference** | **+27.2%** |

---

## Signal Scoring

```
Score > +40  → STRONG_BUY   🟢🟢
Score > +15  → BUY          🟢
Score -15 to +15 → HOLD     ⚪
Score < -15  → SELL         🔴
Score < -40  → STRONG_SELL  🔴🔴
```

### Signal Weights (Optimized)
| Signal | Weight | Source |
|--------|--------|--------|
| Funding Rate | 35% | Binance Futures |
| Momentum | 30% | Price action |
| Volume | 20% | Binance |
| Open Interest | 15% | Binance Futures |

---

## Roadmap

```
DONE     ████████████████████░░░░░░░░░░░░░░░░░░░░  50%
CURRENT  ░░░░░░░░░░░░░░░░░░░░████░░░░░░░░░░░░░░░░  60% (Fundamentals)
FUTURE   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  100% (Full system)
```

### Priority Order
1. **Fundamental Analysis** (NOW) — understand what moves price
2. **Enhanced Signals** — more data sources
3. **Live Trading** — real execution
4. **Intelligence** — auto-tuning, ML
5. **Scale** — multi-chain, dashboard

---

## Key Learnings

### What Works
- High conviction signals (>40 score) = 71% win rate
- Contrarian approach (buy fear, sell greed)
- Risk management (1% per trade, 3% SL)
- Combining multiple signals reduces noise

### What Doesn't Work
- Low conviction signals (<25 score) = 38% win rate
- Sentiment alone (Fear & Greed) = biased
- Trading too frequently = noise
- Simple price patterns (trend, S/R) = random

### The Edge
- **Not in the signals** — signals are public data
- **In the combination** — 5 signals weighted properly
- **In the discipline** — only trade high conviction
- **In the risk management** — small losses, big wins

---

## Contributing

This is a personal project. Feel free to fork and customize.

---

## Disclaimer

⚠️ This is NOT financial advice. Crypto trading is extremely risky. You can lose ALL your money. Past performance ≠ future results. Start with money you can afford to lose. Paper trade first before real money.

---

## License

MIT License

---

Built with 🧠 by [Your Name]

Last updated: 2026-07-21
