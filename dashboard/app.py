"""
Smart Money System - Dashboard Backend
Flask server that fetches live market data and serves the dashboard.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.signals.orderbook_signal import OrderBookSignal
from modules.signals.funding_rate_signal import FundingRateSignal
from modules.signals.sentiment_signal import SentimentSignal
from modules.prediction.regime_detector import RegimeDetector
from modules.prediction.magnitude_predictor import MagnitudePredictor
from modules.prediction.liquidity_map import LiquidityMap
from modules.backtest.data_fetcher import DataFetcher

from flask import Flask, render_template, jsonify, make_response

app = Flask(__name__)

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Cache for slow endpoints
_cache = {}
_cache_ttl = {}  # timestamp when cache expires
import time

def cached(key, ttl_seconds=300):
    if key in _cache and time.time() < _cache_ttl.get(key, 0):
        return _cache[key]
    return None

def cache_set(key, value, ttl_seconds=300):
    _cache[key] = value
    _cache_ttl[key] = time.time() + ttl_seconds

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

# Single event loop for async calls
loop = asyncio.new_event_loop()

def run_async(coro):
    return loop.run_until_complete(coro)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/price")
def api_price():
    """Current price + 24h stats"""
    ob = OrderBookSignal()
    try:
        ticker = run_async(ob.get_24h_stats("ETHUSDT"))
        price = float(ticker.get("price", 0)) if "price" in ticker else float(ticker.get("lastPrice", 0))
        return jsonify({
            "price": price,
            "change_24h": float(ticker.get("priceChangePercent", 0)),
            "high_24h": float(ticker.get("highPrice", 0)),
            "low_24h": float(ticker.get("lowPrice", 0)),
            "volume_24h": float(ticker.get("quoteVolume", 0)),
            "trades_24h": int(ticker.get("count", 0)),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orderbook")
def api_orderbook():
    """Full order book analysis — bid/ask pressure, walls, liquidity"""
    ob = OrderBookSignal()
    try:
        raw_book = run_async(ob.get_order_book("ETHUSDT", limit=500))
        price = run_async(ob.get_ticker("ETHUSDT"))
        analysis = ob.analyze_order_book(raw_book, price)

        # Parse walls
        bid_walls = []
        ask_walls = []
        bids = raw_book.get("bids", [])
        asks = raw_book.get("asks", [])

        all_bid_values = [float(b[0]) * float(b[1]) for b in bids[:100]]
        all_ask_values = [float(a[0]) * float(a[1]) for a in asks[:100]]
        avg_bid = sum(all_bid_values) / len(all_bid_values) if all_bid_values else 1
        avg_ask = sum(all_ask_values) / len(all_ask_values) if all_ask_values else 1

        for b in bids[:100]:
            val = float(b[0]) * float(b[1])
            if val > avg_bid * 3:
                bid_walls.append({"price": float(b[0]), "qty": float(b[1]), "value": val, "multiple": val/avg_bid})

        for a in asks[:100]:
            val = float(a[0]) * float(a[1])
            if val > avg_ask * 3:
                ask_walls.append({"price": float(a[0]), "qty": float(a[1]), "value": val, "multiple": val/avg_ask})

        # Depth buckets for chart
        bid_depth = [{"price": float(b[0]), "qty": float(b[1]), "value": float(b[0])*float(b[1])} for b in bids[:50]]
        ask_depth = [{"price": float(a[0]), "qty": float(a[1]), "value": float(a[0])*float(a[1])} for a in asks[:50]]

        return jsonify({
            "price": price,
            "bid_pct": analysis["bid_pct"],
            "ask_pct": analysis["ask_pct"],
            "imbalance": analysis["imbalance"],
            "bid_volume_usd": analysis["bid_volume"],
            "ask_volume_usd": analysis["ask_volume"],
            "bid_walls": bid_walls[:5],
            "ask_walls": ask_walls[:5],
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "score": analysis["score"],
            "signal": analysis["reason"],
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/funding")
def api_funding():
    """Funding rate + open interest"""
    fr = FundingRateSignal()
    try:
        funding = run_async(fr.get_funding_rate("ETHUSDT"))
        history = run_async(fr.get_funding_rate_history("ETHUSDT", limit=24))
        oi = run_async(fr.get_open_interest("ETHUSDT"))
        analysis = fr.analyze_funding_rate(funding, history)

        rates_history = [{"rate": float(h["fundingRate"]) * 100, "time": h.get("fundingTime", 0)} for h in history]

        return jsonify({
            "current_rate_pct": analysis["details"]["rate_pct"],
            "score": analysis["score"],
            "signal": analysis["reason"],
            "open_interest": float(oi.get("openInterest", 0)),
            "mark_price": analysis["details"]["mark_price"],
            "history": rates_history,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sentiment")
def api_sentiment():
    """Fear & Greed Index"""
    ss = SentimentSignal()
    try:
        fng = run_async(ss.get_fear_greed(limit=30))
        analysis = ss.analyze_sentiment(fng)

        history = [{"value": int(d["value"]), "label": d["value_classification"], "date": d.get("timestamp", "")} for d in fng]

        return jsonify({
            "current_value": analysis["details"]["current_value"],
            "current_label": analysis["details"]["current_label"],
            "score": analysis["score"],
            "signal": analysis["reason"],
            "history": history,
            "trend": analysis["details"].get("trend", "unknown"),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/regime")
def api_regime():
    """Market regime detection"""
    fetcher = DataFetcher()
    rd = RegimeDetector()
    try:
        candles = run_async(fetcher.get_historical_data("ETHUSDT", "1h", 30))
        if candles:
            regime = rd.detect(candles)
            return jsonify(regime)
        return jsonify({"error": "No data"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fundamentals")
def api_fundamentals():
    """
    Fundamental dashboard — supply/demand/liquidity/macro scores.
    Uses on-chain data where available, estimates otherwise.
    """
    # Fetch what we can from public APIs
    ob = OrderBookSignal()
    fr = FundingRateSignal()

    try:
        ticker = run_async(ob.get_24h_stats("ETHUSDT"))
        funding = run_async(fr.get_funding_rate("ETHUSDT"))
        price = float(ticker.get("lastPrice", 0))

        # === SUPPLY SCORE ===
        # Staked ETH (Beaconcha.in approximation — use latest known value)
        eth_staked_m = 34.2  # Latest known ~34.2M ETH staked
        eth_staked_pct = 28.0
        eth_burned_m = 4.3  # EIP-1559 cumulative burn
        net_issuance = -0.5  # Deflationary
        exchange_reserve_m = 16.2  # CryptoQuant approximation

        supply_score = 0
        supply_items = []

        # Staked: more staked = less liquid supply = bullish
        if eth_staked_pct > 25:
            supply_score += 20
            supply_items.append({"name": "ETH Staked", "value": f"{eth_staked_m}M ETH ({eth_staked_pct}%)", "status": "bullish", "emoji": "🟢", "detail": "Locked in validators"})
        elif eth_staked_pct > 20:
            supply_score += 10
            supply_items.append({"name": "ETH Staked", "value": f"{eth_staked_m}M ETH ({eth_staked_pct}%)", "status": "neutral", "emoji": "🟡", "detail": "Moderate staking"})
        else:
            supply_items.append({"name": "ETH Staked", "value": f"{eth_staked_m}M ETH ({eth_staked_pct}%)", "status": "bearish", "emoji": "🔴", "detail": "Low staking"})

        # Burn: deflationary = bullish
        if net_issuance < 0:
            supply_score += 20
            supply_items.append({"name": "ETH Burned", "value": f"{eth_burned_m}M ETH", "status": "bullish", "emoji": "🟢", "detail": "EIP-1559 deflationary"})
        else:
            supply_items.append({"name": "ETH Burned", "value": f"{eth_burned_m}M ETH", "status": "neutral", "emoji": "🟡", "detail": "Inflationary"})

        # Exchange reserves: declining = bullish
        supply_score += 15
        supply_items.append({"name": "Exchange Reserve", "value": f"{exchange_reserve_m}M ETH", "status": "bullish", "emoji": "🟢", "detail": "Declining — less sell pressure"})

        # Net issuance
        if net_issuance < 0:
            supply_score += 10
            supply_items.append({"name": "Net Issuance", "value": f"{net_issuance}%/year", "status": "bullish", "emoji": "🟢", "detail": "Deflationary"})
        else:
            supply_items.append({"name": "Net Issuance", "value": f"+{net_issuance}%/year", "status": "bearish", "emoji": "🔴", "detail": "Inflationary"})

        # === DEMAND SCORE ===
        demand_score = 0
        demand_items = []

        # DeFi TVL (DefiLlama approximate)
        defi_tvl_b = 58
        demand_score += 15
        demand_items.append({"name": "DeFi TVL", "value": f"${defi_tvl_b}B", "status": "bullish", "emoji": "🟢", "detail": "Growing ecosystem"})

        # Gas fees (network usage)
        demand_score += 5
        demand_items.append({"name": "Gas Fees", "value": "~15 gwei", "status": "neutral", "emoji": "🟡", "detail": "Normal activity"})

        # Active addresses
        demand_score += 10
        demand_items.append({"name": "Active Addresses", "value": "~450K/day", "status": "bullish", "emoji": "🟢", "detail": "Healthy usage"})

        # Transaction count
        demand_score += 10
        demand_items.append({"name": "Transaction Count", "value": "~1.1M/day", "status": "bullish", "emoji": "🟢", "detail": "Growing activity"})

        # Stablecoin supply
        demand_score += 5
        demand_items.append({"name": "Stablecoin Supply", "value": "$155B (USDT+USDC)", "status": "bullish", "emoji": "🟢", "detail": "Capital in ecosystem"})

        # === LIQUIDITY SCORE ===
        liquidity_score = 0
        liquidity_items = []

        funding_rate = float(funding.get("lastFundingRate", 0)) * 100

        liquidity_score += 15
        liquidity_items.append({"name": "USDT Supply", "value": "$120B", "status": "bullish", "emoji": "🟢", "detail": "Growing supply"})

        liquidity_score += 10
        liquidity_items.append({"name": "USDC Supply", "value": "$35B", "status": "neutral", "emoji": "🟡", "detail": "Stable"})

        liquidity_score += 10
        liquidity_items.append({"name": "Exchange Flow", "value": "Net outflow", "status": "bullish", "emoji": "🟢", "detail": "Coins leaving exchanges"})

        if abs(funding_rate) < 0.05:
            liquidity_items.append({"name": "Funding Rate", "value": f"{funding_rate:+.4f}%", "status": "neutral", "emoji": "🟡", "detail": "Balanced positioning"})
        elif funding_rate > 0.05:
            liquidity_score -= 5
            liquidity_items.append({"name": "Funding Rate", "value": f"{funding_rate:+.4f}%", "status": "bearish", "emoji": "🔴", "detail": "Crowded longs"})
        else:
            liquidity_score += 10
            liquidity_items.append({"name": "Funding Rate", "value": f"{funding_rate:+.4f}%", "status": "bullish", "emoji": "🟢", "detail": "Crowded shorts"})

        # === MACRO SCORE ===
        macro_score = 0
        macro_items = []

        # BTC (fetch from Binance)
        try:
            btc_ticker = run_async(ob.get_24h_stats("BTCUSDT"))
            btc_price = float(btc_ticker.get("lastPrice", 0))
            btc_change = float(btc_ticker.get("priceChangePercent", 0))
            if btc_change > 1:
                macro_score += 15
                macro_items.append({"name": "BTC", "value": f"${btc_price:,.0f} ({btc_change:+.1f}%)", "status": "bullish", "emoji": "🟢", "detail": "Risk-on"})
            elif btc_change < -1:
                macro_score -= 15
                macro_items.append({"name": "BTC", "value": f"${btc_price:,.0f} ({btc_change:+.1f}%)", "status": "bearish", "emoji": "🔴", "detail": "Risk-off"})
            else:
                macro_items.append({"name": "BTC", "value": f"${btc_price:,.0f} ({btc_change:+.1f}%)", "status": "neutral", "emoji": "🟡", "detail": "Neutral"})
        except:
            macro_items.append({"name": "BTC", "value": "N/A", "status": "neutral", "emoji": "🟡", "detail": "Data unavailable"})

        macro_items.append({"name": "DXY (Dollar)", "value": "~104.2", "status": "neutral", "emoji": "🟡", "detail": "Moderate dollar strength"})
        macro_items.append({"name": "Interest Rates", "value": "5.25%", "status": "bearish", "emoji": "🔴", "detail": "High rates = less risk appetite"})
        macro_items.append({"name": "S&P 500", "value": "Risk-on", "status": "bullish", "emoji": "🟢", "detail": "Stocks supportive"})

        # === COMPOSITE ===
        composite = supply_score + demand_score + liquidity_score + macro_score

        if composite > 40:
            bias = "STRONGLY BULLISH"
        elif composite > 15:
            bias = "BULLISH"
        elif composite > -15:
            bias = "NEUTRAL"
        elif composite > -40:
            bias = "BEARISH"
        else:
            bias = "STRONGLY BEARISH"

        # Build narrative
        bullish_count = sum(1 for items in [supply_items, demand_items, liquidity_items, macro_items]
                          for i in items if i["status"] == "bullish")
        bearish_count = sum(1 for items in [supply_items, demand_items, liquidity_items, macro_items]
                          for i in items if i["status"] == "bearish")

        narratives = []
        if supply_score > 30:
            narratives.append("Supply shrinking (deflationary + staked)")
        if demand_score > 25:
            narratives.append("Demand growing (DeFi + users)")
        if liquidity_score > 20:
            narratives.append("Liquidity entering (stablecoins + outflows)")
        if macro_score > 10:
            narratives.append("Macro supportive")
        elif macro_score < -10:
            narratives.append("Macro headwinds")

        narrative = ". ".join(narratives) if narratives else "Mixed signals across all dimensions"

        return jsonify({
            "price": price,
            "composite_score": composite,
            "bias": bias,
            "narrative": narrative,
            "supply": {"score": supply_score, "items": supply_items},
            "demand": {"score": demand_score, "items": demand_items},
            "liquidity": {"score": liquidity_score, "items": liquidity_items},
            "macro": {"score": macro_score, "items": macro_items},
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prediction")
def api_prediction():
    """Run the prediction engine (cached 5 min)"""
    c = cached('prediction', 300)
    if c:
        return jsonify(c)
    try:
        from modules.prediction.prediction_engine import PredictionEngine
        engine = PredictionEngine()
        prediction = run_async(engine.predict("ETHUSDT"))
        cache_set('prediction', prediction, 300)
        return jsonify(prediction)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/candles/<interval>/<int:days>")
def api_candles(interval, days):
    """Historical candles for charts"""
    fetcher = DataFetcher()
    try:
        candles = run_async(fetcher.get_historical_data("ETHUSDT", interval, days))
        return jsonify([{
            "time": c["timestamp"].isoformat() if hasattr(c["timestamp"], "isoformat") else str(c["timestamp"]),
            "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"],
            "volume": c["volume"]
        } for c in candles[-200:]])  # Last 200 for chart
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("Smart Money Dashboard")
    print("http://localhost:8888")
    print("=" * 50)
    app.run(host="0.0.0.0", port=8888, debug=False, threaded=True)
