# 🧠 Smart Money System

**Understanding what actually moves crypto prices — before trading them.**

## The Problem

Most traders jump to signals and execution without understanding WHY price moves. They use indicators that are worse than random, trade too frequently, and lose money.

## Our Approach

```
Step 1: UNDERSTAND what drives price (Fundamentals)
Step 2: TRACK smart money movements (Data)
Step 3: GENERATE high-conviction signals (Signals)
Step 4: EXECUTE with proper risk management (Trading)
Step 5: LEARN from results and improve (Intelligence)
```

**We are at Step 1.**

---

## 🎯 Primary Target: What Drives ETH Price

```
PRICE = f(Supply, Demand, Liquidity, Macro)
```

### 1. Supply Side (What Exists)

| Factor | What It Means | Why It Matters | Data Source |
|--------|--------------|----------------|-------------|
| **ETH Staked** | Locked in validators, can't sell | Less supply = bullish | Beaconcha.in |
| **ETH Burned** | EIP-1559 burns ETH every tx | Deflationary = bullish | ultrasound.money |
| **ETH Issuance** | New ETH created as rewards | Inflation = bearish | Beaconcha.in |
| **Exchange Reserves** | ETH sitting on exchanges | More = selling pressure | CryptoQuant |
| **Whale Holdings** | Top 100 wallets | Accumulation = bullish | Etherscan |

**Key Insight:** If staked ETH increases + burned ETH > issued ETH = supply shrinking = bullish

### 2. Demand Side (What People Want)

| Factor | What It Means | Why It Matters | Data Source |
|--------|--------------|----------------|-------------|
| **DeFi TVL** | Money locked in DeFi | More demand = bullish | DefiLlama |
| **Gas Fees** | Network usage | High = busy = demand | Etherscan |
| **Active Addresses** | How many people using ETH | More users = bullish | Etherscan |
| **Transaction Count** | Network activity | More activity = bullish | Etherscan |
| **Stablecoin Supply** | Capital in ecosystem | More capital = bullish | DefiLlama |

**Key Insight:** If DeFi TVL grows + gas fees rise + active addresses increase = demand growing = bullish

### 3. Liquidity (Money Flow)

| Factor | What It Means | Why It Matters | Data Source |
|--------|--------------|----------------|-------------|
| **Stablecoin Minting** | New USDT/USDC created | New money entering = bullish | Tether/Circle |
| **Exchange Inflow** | Coins entering exchanges | Selling pressure = bearish | CryptoQuant |
| **Exchange Outflow** | Coins leaving exchanges | Holding = bullish | CryptoQuant |
| **Funding Rates** | Leveraged positioning | Extreme = reversal likely | Binance |
| **Open Interest** | Total leveraged positions | High = crowded trade | Binance |

**Key Insight:** If stablecoins minting + exchange outflows = liquidity entering = bullish

### 4. Macro (External Forces)

| Factor | What It Means | Why It Matters | Data Source |
|--------|--------------|----------------|-------------|
| **BTC Price** | ETH follows BTC (0.85 correlation) | BTC up = ETH up | Binance |
| **DXY (Dollar Index)** | Dollar strength | Strong dollar = weak crypto | Yahoo Finance |
| **Interest Rates** | Cost of money | High rates = less risk appetite | FRED API |
| **S&P 500** | Stock market | Risk-on = crypto up | Yahoo Finance |
| **News/Events** | Upgrades, regulations | Catalysts | News APIs |

**Key Insight:** If BTC rises + DXY falls + rates low = macro bullish for crypto

---

## What We're Building

### Phase 1: Fundamental Dashboard (NOW)

```
┌─────────────────────────────────────────────────┐
│           ETH FUNDAMENTAL ANALYSIS              │
├─────────────────────────────────────────────────┤
│                                                 │
│  SUPPLY                          SCORE: +65     │
│  ├── Staked: 34.2M ETH (28%)     🟢 Bullish    │
│  ├── Burned: 4.3M ETH            🟢 Bullish    │
│  ├── Exchange Reserve: 16.2M     🟢 Declining  │
│  └── Net Issuance: -0.5%/year    🟢 Deflationary│
│                                                 │
│  DEMAND                          SCORE: +45     │
│  ├── DeFi TVL: $58B              🟢 Growing    │
│  ├── Gas Fees: 15 gwei           🟡 Normal     │
│  ├── Active Addr: 450K/day       🟢 Healthy    │
│  └── Tx Count: 1.1M/day          🟢 Growing    │
│                                                 │
│  LIQUIDITY                       SCORE: +30     │
│  ├── USDT Supply: $120B          🟢 Growing    │
│  ├── USDC Supply: $35B           🟢 Stable     │
│  ├── Exchange Outflow: +5K ETH   🟢 Bullish    │
│  └── Funding Rate: +0.003%       🟡 Neutral    │
│                                                 │
│  MACRO                           SCORE: -20     │
│  ├── BTC: $66,700                🟡 Neutral    │
│  ├── DXY: 104.2                  🟡 Neutral    │
│  ├── Rates: 5.25%                🔴 High       │
│  └── S&P 500: +0.5%              🟢 Risk-on    │
│                                                 │
│  ═══════════════════════════════════════════    │
│  COMPOSITE FUNDAMENTAL SCORE: +30 (BULLISH)    │
│  ═══════════════════════════════════════════    │
│                                                 │
│  NARRATIVE: Supply shrinking, demand growing,   │
│  liquidity entering, macro neutral.             │
│  Bias: Bullish on 30-day timeframe.             │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Phase 2: Smart Money Tracking (DONE)
- [x] 19 whale/exchange wallet tracking
- [x] Real-time movement detection
- [x] Telegram alerts with scoring

### Phase 3: Signal Engine (DONE)
- [x] Order book signal (Binance)
- [x] Funding rate signal
- [x] Sentiment signal
- [x] Signal combiner (weighted scoring)

### Phase 4: Backtesting (DONE)
- [x] Historical data fetcher
- [x] Backtesting engine
- [x] Parameter optimization
- [x] Best config: 71.4% win rate, +7.58% return

### Phase 5: Trading (FUTURE)
- [ ] Paper trading
- [ ] Live trading
- [ ] Risk management

---

## Backtest Results (90-Day ETH)

| Config | Trades | Win Rate | Return | Profit Factor | Grade |
|--------|--------|----------|--------|---------------|-------|
| Entry=25 | 26 | 38.5% | +1.99% | 1.10 | C |
| Entry=30 | 23 | 43.5% | +2.51% | 1.14 | C |
| Entry=35 | 11 | 45.5% | +4.40% | 1.47 | B |
| **Entry=40** | **7** | **71.4%** | **+7.58%** | **3.46** | **A** |

**vs Buy & Hold:** +27.2% outperformance

---

## What We Learned

### Signals That Work
- **Funding Rate** — Contrarian, real money data
- **Momentum** — Recent price direction
- **Volume** — Confirms moves

### Signals That Don't Work
- **Trend (MA crossover)** — Worse than random
- **Support/Resistance** — Worse than random
- **Sentiment (Fear & Greed)** — Biased, dangerous

### The Edge
- Not in any single signal
- In combining multiple signals
- In only acting on high conviction (>40 score)
- In proper risk management (1% per trade)

---

## Setup

```bash
# Clone
git clone https://github.com/argho001/smart-money-system.git
cd smart-money-system

# Install
pip install -r requirements.txt

# Configure
cp config/settings.example.py config/settings.py
# Edit settings.py with your API keys

# Test
python main.py test

# Run
python main.py live
```

### API Keys (All Free)
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
| `python main.py live` | Start full system |
| `python main.py test` | Test all components |
| `python main.py test-signals` | Test signal engine |
| `python main.py paper` | Paper trading status |
| `python main.py performance` | Performance report |

---

## File Structure

```
smart-money-system/
├── README.md                    # This file
├── PLAN.md                      # Full project plan
├── BACKTEST_RESULTS.md          # Backtest analysis
├── requirements.txt             # Dependencies
├── main.py                      # Entry point
├── config/
│   ├── settings.example.py      # Config template
│   └── wallets.json             # 19 wallets
├── modules/
│   ├── data/                    # Blockchain listener
│   ├── signals/                 # Signal engine
│   ├── executor/                # Paper trader
│   ├── backtest/                # Backtesting
│   ├── feedback/                # Performance
│   └── ui/                      # Telegram alerts
└── scripts/
    └── setup.sh                 # Setup script
```

---

## Roadmap

```
DONE     ████████████████████░░░░░░░░░░░░░░░░░░░░  50%
CURRENT  ░░░░░░░░░░░░░░░░░░░░████░░░░░░░░░░░░░░░░  60% (Fundamentals)
FUTURE   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  100%
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
- Not in the signals — signals are public data
- In the combination — multiple signals weighted properly
- In the discipline — only trade high conviction
- In the risk management — small losses, big wins

---

## Disclaimer

⚠️ This is NOT financial advice. Crypto trading is extremely risky. You can lose ALL your money. Past performance ≠ future results. Start with money you can afford to lose. Paper trade first before real money.

---

## License

MIT License

---

Built with 🧠 by [argho001](https://github.com/argho001)

Last updated: 2026-07-21
