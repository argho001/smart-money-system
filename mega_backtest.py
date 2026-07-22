"""
MEGA BACKTESTER — 50 Signals × Every Combination × Every Risk × Every RR × Every Leverage
Tests everything. Keeps only what works.
"""
import json, os, sys, time
import numpy as np
from itertools import combinations
from datetime import datetime

DATA_DIR = "data/candles"

# ============================================================
# DATA
# ============================================================
def load_candles(symbol, interval, days):
    path = os.path.join(DATA_DIR, f"{symbol}_{interval}_{days}d.json")
    with open(path) as f:
        raw = json.load(f)
    return [{"open": float(d["open"]), "high": float(d["high"]),
             "low": float(d["low"]), "close": float(d["close"]),
             "volume": float(d["volume"])} for d in raw]

# ============================================================
# INDICATORS
# ============================================================
def sma(data, period):
    out = [None]*len(data)
    for i in range(period-1, len(data)):
        out[i] = np.mean(data[i-period+1:i+1])
    return out

def ema(data, period):
    out = [None]*len(data)
    k = 2/(period+1)
    out[period-1] = np.mean(data[:period])
    for i in range(period, len(data)):
        out[i] = data[i]*k + out[i-1]*(1-k)
    return out

def rsi(closes, period=14):
    out = [None]*len(closes)
    for i in range(period, len(closes)):
        g, l = [], []
        for j in range(i-period+1, i+1):
            d = closes[j]-closes[j-1]
            (g if d>0 else l).append(abs(d))
        ag = np.mean(g) if g else 0
        al = np.mean(l) if l else 0.0001
        out[i] = 100-(100/(1+ag/al))
    return out

def macd(closes, fast=12, slow=26, sig=9):
    ef = ema(closes, fast)
    es = ema(closes, slow)
    ml = [None]*len(closes)
    for i in range(len(closes)):
        if ef[i] is not None and es[i] is not None:
            ml[i] = ef[i]-es[i]
    vals = [v for v in ml if v is not None]
    sg = ema(vals, sig) if len(vals)>=sig else [None]*len(vals)
    sl = [None]*len(closes)
    j=0
    for i in range(len(closes)):
        if ml[i] is not None:
            if j<len(sg): sl[i]=sg[j]
            j+=1
    hist = [None]*len(closes)
    for i in range(len(closes)):
        if ml[i] is not None and sl[i] is not None:
            hist[i] = ml[i]-sl[i]
    return ml, sl, hist

def bollinger(closes, period=20, std_mult=2):
    mid = sma(closes, period)
    upper, lower, width = [None]*len(closes), [None]*len(closes), [None]*len(closes)
    for i in range(period-1, len(closes)):
        s = np.std(closes[i-period+1:i+1])
        upper[i] = mid[i]+std_mult*s
        lower[i] = mid[i]-std_mult*s
        width[i] = (upper[i]-lower[i])/mid[i] if mid[i] else 0
    return mid, upper, lower, width

def stochastic(highs, lows, closes, k_period=14, d_period=3):
    k = [None]*len(closes)
    for i in range(k_period-1, len(closes)):
        h = max(highs[i-k_period+1:i+1])
        l = min(lows[i-k_period+1:i+1])
        k[i] = (closes[i]-l)/(h-l)*100 if h!=l else 50
    d = sma([x if x is not None else 50 for x in k], d_period)
    return k, d

def atr(highs, lows, closes, period=14):
    out = [None]*len(closes)
    for i in range(period, len(closes)):
        trs = []
        for j in range(i-period+1, i+1):
            tr = max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1]))
            trs.append(tr)
        out[i] = np.mean(trs)
    return out

def adx(highs, lows, closes, period=14):
    out = [None]*len(closes)
    for i in range(period*2, len(closes)):
        pdm, mdm, trs = [], [], []
        for j in range(i-period*2+1, i+1):
            hd = highs[j]-highs[j-1]
            ld = lows[j-1]-lows[j]
            pdm.append(max(hd,0) if hd>ld else 0)
            mdm.append(max(ld,0) if ld>hd else 0)
            trs.append(max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1])))
        av = np.mean(trs)
        if av>0:
            pdi = np.mean(pdm)/av*100
            mdi = np.mean(mdm)/av*100
            out[i] = abs(pdi-mdi)/(pdi+mdi)*100 if (pdi+mdi)>0 else 0
    return out

def momentum(closes, period):
    out = [None]*len(closes)
    for i in range(period, len(closes)):
        out[i] = (closes[i]-closes[i-period])/closes[i-period]
    return out

def volatility_ratio(highs, lows, closes, short=10, long=50):
    out = [None]*len(closes)
    for i in range(long, len(closes)):
        sr = max(highs[i-short:i])-min(lows[i-short:i])
        lr = max(highs[i-long:i])-min(lows[i-long:i])
        out[i] = sr/lr if lr>0 else 0
    return out

def volume_zscore(volumes, period=50):
    out = [None]*len(volumes)
    for i in range(period, len(volumes)):
        m = np.mean(volumes[i-period:i])
        s = np.std(volumes[i-period:i])
        out[i] = (volumes[i]-m)/s if s>0 else 0
    return out

def price_range_position(highs, lows, closes, period):
    out = [None]*len(closes)
    for i in range(period, len(closes)):
        h = max(highs[i-period:i])
        l = min(lows[i-period:i])
        r = h-l
        out[i] = (closes[i]-l)/r if r>0 else 0.5
    return out

def efficiency_ratio(closes, period=20):
    out = [None]*len(closes)
    for i in range(period, len(closes)):
        net = abs(closes[i]-closes[i-period])
        total = sum(abs(closes[j]-closes[j-1]) for j in range(i-period+1, i+1))
        out[i] = net/total if total>0 else 0
    return out

def cvd_from_candles(candles):
    cvd = 0; out = []
    for c in candles:
        delta = (c["close"]-c["open"])/max(c["open"],0.01)*c["volume"]
        cvd += delta; out.append(cvd)
    return out

def cvd_divergence(closes, cvd, period):
    out = [None]*len(closes)
    for i in range(period, len(closes)):
        pc = (closes[i]-closes[i-period])/closes[i-period]
        cc = cvd[i]-cvd[i-period]
        if pc<-0.003 and cc>0: out[i]=1
        elif pc>0.003 and cc<0: out[i]=-1
        else: out[i]=0
    return out

def ema_cross(closes, fp, sp):
    f = ema(closes, fp); s = ema(closes, sp)
    out = [None]*len(closes)
    for i in range(1, len(closes)):
        if f[i] and s[i] and f[i-1] and s[i-1]:
            if f[i]>s[i] and f[i-1]<=s[i-1]: out[i]=1
            elif f[i]<s[i] and f[i-1]>=s[i-1]: out[i]=-1
            else: out[i]=0
    return out

def obv_slope(closes, volumes, period=20):
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i]>closes[i-1]: obv.append(obv[-1]+volumes[i])
        elif closes[i]<closes[i-1]: obv.append(obv[-1]-volumes[i])
        else: obv.append(obv[-1])
    slopes = [None]*len(closes)
    for i in range(period, len(closes)):
        slopes[i] = (obv[i]-obv[i-period])/period
    return slopes

def vwap_ratio(closes, volumes, period=20):
    out = [None]*len(closes)
    for i in range(period, len(closes)):
        pv = sum(closes[j]*volumes[j] for j in range(i-period, i))
        v = sum(volumes[j] for j in range(i-period, i))
        if v>0: out[i] = closes[i]/(pv/v)
    return out

# ============================================================
# SIGNAL BUILDER
# ============================================================
def expand(arr, n):
    """Expand HTF signal to LTF timeline — NO LOOKAHEAD.
    Uses the PREVIOUS HTF candle's value (lag by 1 HTF bar).
    """
    if len(arr)>=n: return arr[:n]
    result = [None]*n
    ratio = n//len(arr)  # e.g. 12 for 1h->5m
    if ratio < 1: ratio = 1
    for i in range(n):
        htf_idx = i // ratio
        # Use PREVIOUS HTF candle to avoid lookahead
        src_idx = htf_idx - 1
        if 0 <= src_idx < len(arr):
            result[i] = arr[src_idx]
    return result

def build_signals(c5m, c15m, c1h):
    closes = [c["close"] for c in c5m]
    highs = [c["high"] for c in c5m]
    lows = [c["low"] for c in c5m]
    volumes = [c["volume"] for c in c5m]
    n = len(c5m)

    c5 = [c["close"] for c in c5m]
    c15 = [c["close"] for c in c15m]
    c60 = [c["close"] for c in c1h]
    cvd = cvd_from_candles(c5m)

    sigs = {}
    # Momentum (10)
    sigs["mom_5m"] = momentum(closes,5)
    sigs["mom_10m"] = momentum(closes,10)
    sigs["mom_30m"] = momentum(closes,30)
    sigs["mom_1h"] = momentum(closes,60)
    sigs["mom_2h"] = momentum(closes,120)
    sigs["mom_5m_tf"] = expand(momentum(c5,5),n)
    sigs["mom_15m_5"] = expand(momentum(c15,5),n)
    sigs["mom_15m_10"] = expand(momentum(c15,10),n)
    sigs["mom_1h_3"] = expand(momentum(c60,3),n)
    sigs["mom_1h_5"] = expand(momentum(c60,5),n)

    # RSI (6)
    sigs["rsi_7"] = rsi(closes,7)
    sigs["rsi_14"] = rsi(closes,14)
    sigs["rsi_21"] = rsi(closes,21)
    sigs["rsi_5m"] = expand(rsi(c5,14),n)
    sigs["rsi_15m"] = expand(rsi(c15,14),n)
    sigs["rsi_1h"] = expand(rsi(c60,14),n)

    # MACD (4)
    _,_,h1 = macd(closes,12,26,9)
    sigs["macd_hist"] = h1
    sigs["macd_cross"] = [None if v is None else (1 if v>0 else -1) for v in h1]
    _,_,h5 = macd(c5,12,26,9)
    sigs["macd_5m"] = expand(h5,n)
    _,_,h15 = macd(c15,12,26,9)
    sigs["macd_15m"] = expand(h15,n)

    # Bollinger (4)
    _,_,_,bw = bollinger(closes,20,2)
    sigs["bb_squeeze"] = bw
    _,bu,bl,_ = bollinger(closes,20,2)
    bp = [None]*n
    for i in range(n):
        if bu[i] and bl[i] and bu[i]-bl[i]>0:
            bp[i] = (closes[i]-bl[i])/(bu[i]-bl[i])
    sigs["bb_pos"] = bp
    _,bu5,bl5,_ = bollinger(c5,20,2)
    bp5 = [None]*len(c5)
    for i in range(len(c5)):
        if bu5[i] and bl5[i] and bu5[i]-bl5[i]>0:
            bp5[i] = (c5[i]-bl5[i])/(bu5[i]-bl5[i])
    sigs["bb_pos_5m"] = expand(bp5,n)
    _,bu15,bl15,_ = bollinger(c15,20,2)
    bp15 = [None]*len(c15)
    for i in range(len(c15)):
        if bu15[i] and bl15[i] and bu15[i]-bl15[i]>0:
            bp15[i] = (c15[i]-bl15[i])/(bu15[i]-bl15[i])
    sigs["bb_pos_15m"] = expand(bp15,n)

    # Stochastic (2)
    sk,_ = stochastic(highs,lows,closes,14,3)
    sigs["stoch_k"] = sk
    sk5,_ = stochastic([c["high"] for c in c5m],[c["low"] for c in c5m],c5,14,3)
    sigs["stoch_5m"] = expand(sk5,n)

    # Volume (5)
    sigs["vol_z50"] = volume_zscore(volumes,50)
    sigs["vol_z100"] = volume_zscore(volumes,100)
    sigs["vol_z5m"] = expand(volume_zscore([c["volume"] for c in c5m],50),n)
    sigs["obv_20"] = obv_slope(closes,volumes,20)
    sigs["obv_50"] = obv_slope(closes,volumes,50)

    # CVD (4)
    sigs["cvd_div_5m"] = cvd_divergence(closes,cvd,300)
    sigs["cvd_div_15m"] = cvd_divergence(closes,cvd,900)
    sigs["cvd_div_1h"] = cvd_divergence(closes,cvd,3600)
    cs = [None]*n
    for i in range(300,n): cs[i]=(cvd[i]-cvd[i-300])/300
    sigs["cvd_slope"] = cs

    # Trend (4)
    sigs["eff_20"] = efficiency_ratio(closes,20)
    sigs["eff_50"] = efficiency_ratio(closes,50)
    sigs["adx"] = adx(highs,lows,closes,14)
    e20 = ema(closes,20)
    ed = [None]*n
    for i in range(n):
        if e20[i]: ed[i]=(closes[i]-e20[i])/e20[i]
    sigs["ema20_dist"] = ed

    # Volatility (3)
    sigs["vr_10_50"] = volatility_ratio(highs,lows,closes,10,50)
    sigs["vr_5_20"] = volatility_ratio(highs,lows,closes,5,20)
    a14 = atr(highs,lows,closes,14)
    ap = [None]*n
    for i in range(n):
        if a14[i] and closes[i]>0: ap[i]=a14[i]/closes[i]
    sigs["atr_pct"] = ap

    # Price position (3)
    sigs["rp_24h"] = price_range_position(highs,lows,closes,1440)
    sigs["rp_4h"] = price_range_position(highs,lows,closes,240)
    sigs["rp_1h"] = price_range_position(highs,lows,closes,60)

    # Cross-TF (4)
    sigs["ec_9_21"] = ema_cross(closes,9,21)
    sigs["ec_12_26"] = ema_cross(closes,12,26)
    sigs["ec_5m"] = expand(ema_cross(c5,9,21),n)
    sigs["ec_15m"] = expand(ema_cross(c15,9,21),n)

    # VWAP (2)
    sigs["vwap_20"] = vwap_ratio(closes,volumes,20)
    sigs["vwap_50"] = vwap_ratio(closes,volumes,50)

    print(f"[SIGNALS] Built {len(sigs)} signals")
    return sigs, cvd

# ============================================================
# SIGNAL EVALUATOR
# ============================================================
def get_thresholds(name):
    if "rsi" in name: return [(20,80),(25,75),(30,70),(35,65)]
    if "stoch" in name: return [(20,80),(25,75),(30,70)]
    if "bb_pos" in name: return [(0.1,0.9),(0.15,0.85),(0.2,0.8),(0.05,0.95)]
    if "rp_" in name: return [(0.1,0.9),(0.15,0.85),(0.2,0.8)]
    if "mom" in name: return [(0.002,),(0.003,),(0.005,),(0.008,),(0.01,)]
    if "macd" in name and "hist" in name: return [(0.5,),(1.0,),(2.0,)]
    if "cvd_slope" in name: return [(0.01,),(0.05,),(0.1,)]
    if "ema20_dist" in name: return [(0.005,),(0.01,),(0.02,)]
    if "vwap" in name: return [(0.995,1.005),(0.99,1.01),(0.98,1.02)]
    if "obv" in name: return [(100,),(500,),(1000,)]
    if "vol_z" in name: return [(2.0,),(2.5,),(3.0,)]
    if "eff" in name: return [(0.3,),(0.4,),(0.5,)]
    if "adx" in name: return [(25,),(30,),(35,)]
    if "vr_" in name: return [(1.5,),(2.0,)]
    if "bb_squeeze" in name: return [(0.02,),(0.03,)]
    if "atr_pct" in name: return [(0.01,),(0.02,)]
    if "cross" in name or "ec_" in name: return [(0,)]  # built-in
    if "cvd_div" in name: return [(0,)]  # built-in
    return [(0.005,)]

def eval_signal(sigs, name, i, th):
    arr = sigs[name]
    if i>=len(arr): return None
    v = arr[i]
    if v is None: return None

    if "ec_" in name or "cross" in name:
        return 0 if v>0 else (1 if v<0 else None)
    if "cvd_div" in name:
        return 0 if v>0 else (1 if v<0 else None)
    if "rsi" in name or "stoch" in name:
        lo,hi = th
        return 0 if v<lo else (1 if v>hi else None)
    if "bb_pos" in name or "rp_" in name:
        lo,hi = th
        return 0 if v<lo else (1 if v>hi else None)
    if "mom" in name:
        return 0 if v>th[0] else (1 if v<-th[0] else None)
    if "macd" in name and "hist" in name:
        return 0 if v>abs(th[0]) else (1 if v<-abs(th[0]) else None)
    if "cvd_slope" in name:
        return 0 if v>th[0] else (1 if v<-th[0] else None)
    if "ema20_dist" in name:
        return 0 if v<-th[0] else (1 if v>th[0] else None)
    if "vwap" in name:
        return 0 if v<th[0] else (1 if v>th[1] else None)
    if "obv" in name:
        return 0 if v>th[0] else (1 if v<-th[0] else None)
    if "vol_z" in name:
        return None  # not directional alone
    if "eff" in name:
        return None  # not directional alone
    if "adx" in name:
        return None  # not directional alone
    if "vr_" in name:
        return None  # not directional alone
    if "bb_squeeze" in name:
        return None  # not directional alone
    if "atr_pct" in name:
        return None  # not directional alone
    return None

# ============================================================
# BACKTEST ENGINE (optimized)
# ============================================================
def backtest(candles, evals, risk, rr, leverage, sl):
    n = min(len(candles), len(evals))
    cl = np.array([c["close"] for c in candles[:n]])
    hi = np.array([c["high"] for c in candles[:n]])
    lo = np.array([c["low"] for c in candles[:n]])

    cap = 10000.0
    wins = 0; total = 0
    pos = None
    slm = sl/100; rm = risk/100; tpm = slm*rr

    for i in range(n):
        d = evals[i]
        if pos:
            ep,sp,tp,pd = pos
            h,l,c = hi[i],lo[i],cl[i]
            xp = None
            if pd==0:
                if l<=sp: xp=sp
                elif h>=tp: xp=tp
            else:
                if h>=sp: xp=sp
                elif l<=tp: xp=tp
            if xp is None and d is not None and d!=pd: xp=c
            if xp:
                pnl_p = ((xp-ep)/ep if pd==0 else (ep-xp)/ep)
                pnl = cap*rm*(pnl_p/slm)*leverage
                cap += pnl
                total += 1
                if pnl>0: wins += 1
                pos = None
                if cap<=0: break
        if pos is None and d is not None:
            ep = cl[i]
            sd = ep*slm; td = ep*tpm
            if d==0: pos=(ep,ep-sd,ep+td,0)
            else: pos=(ep,ep+sd,ep-td,1)

    if pos and n>0:
        c=cl[-1]; ep=pos[0]; pd=pos[3]
        pnl_p=((c-ep)/ep if pd==0 else (ep-c)/ep)
        cap += cap*rm*(pnl_p/slm)*leverage
        total += 1
        if cap>10000: wins += 1

    return total, wins, cap

def stats(total, wins, cap, initial=10000):
    if total<5: return None
    wr = wins/total*100
    losses = total-wins
    pf = wins/losses if losses>0 else 99.0
    ret = (cap-initial)/initial*100
    return {"trades":total,"wins":wins,"losses":losses,
            "win_rate":round(wr,1),"profit_factor":round(pf,2),
            "total_return":round(ret,2),"final_capital":round(cap,2)}

# ============================================================
# MAIN
# ============================================================
def run():
    print("="*70)
    print("MEGA BACKTESTER — 50 Signals × Everything")
    print("="*70)
    t0 = time.time()

    print("\n[1] Loading data...")
    c5m = load_candles("ETHUSDT","5m",90)
    c15m = load_candles("ETHUSDT","15m",90)
    c1h = load_candles("ETHUSDT","1h",90)
    print(f"  5m:{len(c5m)} 15m:{len(c15m)} 1h:{len(c1h)}")

    print("\n[2] Building signals...")
    sigs, cvd = build_signals(c5m, c15m, c1h)
    names = list(sigs.keys())

    # === PHASE 1: Individual signals ===
    print("\n[3] PHASE 1: Individual signal test...")
    ind_results = []

    for name in names:
        for th in get_thresholds(name):
            evals = [eval_signal(sigs,name,i,th) for i in range(len(c5m))]
            total, wins, cap = backtest(c5m, evals, 1.0, 2.0, 1, 2.0)
            s = stats(total, wins, cap)
            if s and s["trades"]>=10:
                ind_results.append({"signal":name,"th":th,"s":s,"evals":evals})

    ind_results.sort(key=lambda x: x["s"]["profit_factor"], reverse=True)
    print(f"  {len(names)} signals tested, {len(ind_results)} combos with >=10 trades")

    print(f"\n  {'Signal':<20} {'Thresh':<15} {'Trades':>7} {'Win%':>6} {'PF':>6} {'Return':>8}")
    print("  " + "-"*65)
    for r in ind_results[:20]:
        s=r["s"]
        print(f"  {r['signal']:<20} {str(r['th']):<15} {s['trades']:>7} {s['win_rate']:>5.1f}% {s['profit_factor']:>5.2f} {s['total_return']:>+7.2f}%")

    # === PHASE 2: Full parameter sweep ===
    print(f"\n[4] PHASE 2: Parameter sweep on top 15...")
    top15 = ind_results[:15]
    risks = [0.5, 1.0, 2.0, 3.0]
    rrs = [1.0, 1.5, 2.0, 3.0, 4.0]
    levs = [1, 2, 3, 5, 10]
    sls = [1.0, 2.0, 3.0]

    sweep = []
    prog = 0
    total_combos = len(top15)*len(risks)*len(rrs)*len(levs)*len(sls)
    print(f"  {total_combos} combinations...")

    for tr in top15:
        ev = tr["evals"]
        for r in risks:
            for rr in rrs:
                for lev in levs:
                    for sl in sls:
                        t,w,c = backtest(c5m, ev, r, rr, lev, sl)
                        s = stats(t,w,c)
                        prog += 1
                        if prog%500==0:
                            print(f"    {prog}/{total_combos} ({prog/total_combos*100:.0f}%)")
                        if s and s["trades"]>=10:
                            sweep.append({"signal":tr["signal"],"th":tr["th"],
                                          "risk":r,"rr":rr,"lev":lev,"sl":sl,"s":s})

    sweep.sort(key=lambda x: x["s"]["profit_factor"], reverse=True)
    print(f"  Valid results: {len(sweep)}")

    # === PHASE 3: Combinations ===
    print(f"\n[5] PHASE 3: Signal combinations...")
    top10 = ind_results[:10]
    combos = []

    for sz in range(2,5):
        for combo in combinations(range(len(top10)),sz):
            names_c = [top10[i]["signal"] for i in combo]
            ths_c = [top10[i]["th"] for i in combo]

            combined = []
            for i in range(len(c5m)):
                dirs = []
                for j,nm in enumerate(names_c):
                    d = eval_signal(sigs,nm,i,ths_c[j])
                    if d is not None: dirs.append(d)
                if len(dirs)==len(names_c) and len(set(dirs))==1:
                    combined.append(dirs[0])
                else:
                    combined.append(None)

            for r in [0.5,1.0,2.0]:
                for rr in [1.5,2.0,3.0]:
                    for sl in [1.5,2.0,3.0]:
                        t,w,c = backtest(c5m, combined, r, rr, 1, sl)
                        s = stats(t,w,c)
                        if s and s["trades"]>=5:
                            combos.append({"signals":names_c,"risk":r,"rr":rr,
                                           "sl":sl,"lev":1,"s":s})

    combos.sort(key=lambda x: x["s"]["profit_factor"], reverse=True)
    print(f"  Tested {len(combos)} combo configs")

    # === REPORT ===
    elapsed = time.time()-t0
    print("\n"+"="*70)
    print("FINAL RESULTS")
    print("="*70)
    print(f"\nTime: {elapsed:.0f}s | Signals: {len(names)} | Combos tested: {total_combos}")

    def grade(pf,wr,trades):
        sc = 0
        if pf>=3: sc+=3
        elif pf>=2: sc+=2
        elif pf>=1.5: sc+=1
        if wr>=65: sc+=3
        elif wr>=55: sc+=2
        elif wr>=50: sc+=1
        if trades>=30: sc+=2
        elif trades>=15: sc+=1
        return {8:"S",7:"A+",6:"A",5:"B+",4:"B",3:"C+",2:"C",1:"D"}.get(sc,"F")

    print("\n"+"="*70)
    print("TOP 30 SINGLE SIGNALS")
    print("="*70)
    print(f"{'#':>3} {'Signal':<20} {'Grade':>5} {'Risk':>5} {'RR':>4} {'Lev':>4} {'SL':>5} {'Trades':>7} {'Win%':>6} {'PF':>6} {'Return':>8}")
    print("-"*85)
    for i,r in enumerate(sweep[:30],1):
        s=r["s"]; g=grade(s["profit_factor"],s["win_rate"],s["trades"])
        print(f"{i:>3} {r['signal']:<20} {g:>5} {r['risk']:>4.1f}% {r['rr']:>3.1f} {r['lev']:>3d}x {r['sl']:>4.1f}% {s['trades']:>7} {s['win_rate']:>5.1f}% {s['profit_factor']:>5.2f} {s['total_return']:>+7.2f}%")

    print("\n"+"="*70)
    print("TOP 15 COMBINATIONS")
    print("="*70)
    print(f"{'#':>3} {'Signals':<40} {'Risk':>5} {'RR':>4} {'SL':>5} {'Trades':>7} {'Win%':>6} {'PF':>6} {'Return':>8}")
    print("-"*90)
    for i,r in enumerate(combos[:15],1):
        s=r["s"]
        sig_str = " + ".join(r["signals"])
        if len(sig_str)>39: sig_str=sig_str[:36]+"..."
        print(f"{i:>3} {sig_str:<40} {r['risk']:>4.1f}% {r['rr']:>3.1f} {r['sl']:>4.1f}% {s['trades']:>7} {s['win_rate']:>5.1f}% {s['profit_factor']:>5.2f} {s['total_return']:>+7.2f}%")

    # === BEST CONFIGS BY GRADE ===
    print("\n"+"="*70)
    print("ALL GRADE-A+ CONFIGS (PF>=2, WR>=55%, trades>=15)")
    print("="*70)
    a_configs = [r for r in sweep if r["s"]["profit_factor"]>=2 and r["s"]["win_rate"]>=55 and r["s"]["trades"]>=15]
    print(f"Found {len(a_configs)} configs")
    print(f"\n{'#':>3} {'Signal':<20} {'Grade':>5} {'Risk':>5} {'RR':>4} {'Lev':>4} {'SL':>5} {'Trades':>7} {'Win%':>6} {'PF':>6} {'Return':>8}")
    print("-"*85)
    for i,r in enumerate(a_configs[:20],1):
        s=r["s"]; g=grade(s["profit_factor"],s["win_rate"],s["trades"])
        print(f"{i:>3} {r['signal']:<20} {g:>5} {r['risk']:>4.1f}% {r['rr']:>3.1f} {r['lev']:>3d}x {r['sl']:>4.1f}% {s['trades']:>7} {s['win_rate']:>5.1f}% {s['profit_factor']:>5.2f} {s['total_return']:>+7.2f}%")

    # Save
    output = {
        "timestamp": datetime.now().isoformat(),
        "elapsed": round(elapsed,1),
        "signals_tested": len(names),
        "top_30_single": [
            {"signal":r["signal"],"thresholds":str(r["th"]),"risk":r["risk"],
             "rr":r["rr"],"leverage":r["lev"],"sl":r["sl"],**r["s"]}
            for r in sweep[:30]
        ],
        "top_15_combos": [
            {"signals":r["signals"],"risk":r["risk"],"rr":r["rr"],
             "sl":r["sl"],**r["s"]}
            for r in combos[:15]
        ],
        "grade_a_configs": [
            {"signal":r["signal"],"thresholds":str(r["th"]),"risk":r["risk"],
             "rr":r["rr"],"leverage":r["lev"],"sl":r["sl"],**r["s"]}
            for r in a_configs[:20]
        ],
    }
    os.makedirs("data",exist_ok=True)
    with open("data/mega_backtest_results.json","w") as f:
        json.dump(output, f, indent=2)
    print(f"\n[SAVED] data/mega_backtest_results.json")

if __name__ == "__main__":
    run()
