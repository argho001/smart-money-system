# 🧠 Smart Money System

Real-time crypto market intelligence terminal. No predictions — pure math on live data.

## What It Does

Shows you **WHAT is happening**, **WHAT IT MEANS**, and **WHERE price will go** — in real-time.

```
┌─────────────────────────────────────────────────────┐
│  SIGNAL PIPELINE (8 Checkpoints)                    │
├─────────────────────────────────────────────────────┤
│  🟢 DIRECTION    | CVD bullish (+173 in 5m)        │
│  ⚪ DIVERGENCE   | No divergence                   │
│  ⚪ TOXICITY     | VPIN 0% — normal flow           │
│  🟢 MOMENTUM     | Accelerating (+719/+1802)       │
│  ⚪ INSTITUTIONAL | No clear signal                 │
│  ⚪ LIQ TARGET   | Balanced levels                 │
│  ⚪ ORDER BOOK   | Balanced (-9.6%)                │
│  🟢 MTF ALIGN    | 5/5 timeframes bullish          │
├─────────────────────────────────────────────────────┤
│  🟢 LONG  | Score: 6 | R:R 1:2.0                   │
│  Entry: $1,924 | Stop: $1,895 | Target: $1,982     │
└─────────────────────────────────────────────────────┘
```

## Features

### Core Engines
- **CVD Engine** — Cumulative Volume Delta + divergence detection
- **VPIN Engine** — Volume-Synchronized Probability of Informed Trading (toxic flow)
- **OI Delta Tracker** — Open Interest change (not just absolute)
- **Liquidation Clusters** — Where liquidation levels are clustered
- **Cross-Exchange OI** — OI rotation across Binance, Bybit, OKX

### Signal Pipeline
8 checkpoints that must align before a signal fires:
1. **Direction** — CVD shows who's in control
2. **Divergence** — CVD-Price divergence (strongest signal)
3. **Toxicity** — VPIN level (informed traders active = don't trade)
4. **Momentum** — Acceleration/deceleration
5. **Institutional** — Whale + OI alignment
6. **Liq Target** — Liquidation cluster direction
7. **Order Book** — Bid/ask imbalance
8. **MTF Align** — Multi-timeframe convergence

### Data Sources
- Binance (trades, order book, funding, OI)
- Etherscan (whale wallet tracking — 45 wallets)
- 6 exchange prices (Binance, OKX, Bybit, Coinbase, Bitget, KuCoin)

### Dashboard
- Real-time WebSocket updates
- Sidebar with signal pipeline + key metrics
- Both LONG and SHORT setups visible
- Anomaly detection with Z-score alerts
- Historical outcome tracking

## Quick Start

```bash
# Clone
git clone https://github.com/argho001/smart-money-system.git
cd smart-money-system

# Install
pip install -r requirements.txt

# Configure
cp config/settings.example.py config/settings.py
# Edit settings.py with your API keys

# Run live terminal
python3 dashboard/live_server.py
# Open http://localhost:8888
```

### API Keys Needed
| Service | Purpose | Get It At |
|---|---|---|
| Binance | Trades, order book, funding, OI | binance.com (free) |
| Etherscan | Whale wallet tracking | etherscan.io (free) |

## Commands

```bash
python3 main.py live         # Start integrated system
python3 main.py predict      # Run prediction engine
python3 main.py regime       # Detect market regime
python3 main.py accuracy     # Prediction accuracy stats
```

## File Structure

```
smart-money-system/
├── dashboard/
│   ├── live_server.py       # Live terminal server
│   ├── app.py               # Prediction dashboard
│   └── templates/
│       ├── live.html         # Live terminal UI
│       └── index.html        # Prediction dashboard UI
├── modules/
│   ├── live/
│   │   ├── live_engine.py    # Core data engine
│   │   ├── cvd_engine.py     # CVD + divergence
│   │   ├── vpin_engine.py    # VPIN (toxic flow)
│   │   ├── oi_delta.py       # OI change tracker
│   │   ├── liquidation_clusters.py
│   │   ├── cross_exchange_oi.py
│   │   ├── signal_pipeline.py # 8-checkpoint signal
│   │   ├── anomaly_detector.py
│   │   ├── outcome_tracker.py
│   │   └── entry_exit_engine.py
│   ├── signals/              # Signal modules
│   ├── prediction/           # Prediction engine
│   └── backtest/             # Backtesting
├── config/
│   ├── settings.example.py
│   └── wallets.json          # 45 whale wallets
└── main.py
```

## Disclaimer

⚠️ This is NOT financial advice. Crypto trading is extremely risky. You can lose ALL your money. This is a research tool, not a money machine. Prove it works with paper trading before risking real money.

## License

MIT License

Built with 🧠 by [argho001](https://github.com/argho001)
