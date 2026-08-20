#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════╗
║                    OPTIX SCORE SYSTEM                         ║
║         Options Trading Intelligence eXplorer                ║
║                                                              ║
║  Fun scoring system for options trading decisions            ║
║  BUY CALL 🟢 | BUY PUT 🔴 | STAY OUT ⚪                     ║
╚═══════════════════════════════════════════════════════════════╝
"""

import json
import math
import urllib.request
import datetime
import statistics
import sys
import os
import argparse

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

WATCHLIST_ETF = ["SPY", "QQQ", "IWM", "SMH", "XLK", "TLT", "HYG", "EEM", "DIA", "ARKK"]
WATCHLIST_TECH = ["NVDA", "AAPL", "TSLA", "MSFT", "AMZN", "META", "GOOGL", "AVGO", "AMD", "CRM"]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

# Score weights
WEIGHTS = {
    "trend": 25,       # Price trend (SMA crossover)
    "momentum": 20,    # RSI + Stochastic
    "volume": 15,      # Volume trend
    "volatility": 15,  # Bollinger Band position
    "macd": 15,        # MACD signal
    "pattern": 10,     # Price action pattern
}

# ═══════════════════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════════════════

def fetch_chart(symbol, interval="1d", range_period="3mo"):
    """Fetch chart data from Yahoo Finance"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_period}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data["chart"]["result"][0]
    except Exception as e:
        return None


def fetch_options(symbol):
    """Fetch options data for IV calculation"""
    url = f"https://query1.finance.yahoo.com/v7/finance/options/{symbol}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data["optionChain"]["result"][0]
    except:
        return None


# ═══════════════════════════════════════════════════════════════
# TECHNICAL INDICATORS
# ═══════════════════════════════════════════════════════════════

def calc_sma(data, period):
    """Simple Moving Average"""
    if len(data) < period:
        return []
    return [statistics.mean(data[i-period:i]) for i in range(period, len(data)+1)]


def calc_ema(data, period):
    """Exponential Moving Average"""
    if len(data) < period:
        return []
    multiplier = 2 / (period + 1)
    ema = [statistics.mean(data[:period])]
    for price in data[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema


def calc_rsi(closes, period=14):
    """Relative Strength Index"""
    if len(closes) < period + 1:
        return 50  # neutral default
    
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    
    avg_gain = statistics.mean(gains[:period])
    avg_loss = statistics.mean(losses[:period])
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_stochastic(highs, lows, closes, period=14):
    """%K and %D"""
    if len(closes) < period:
        return 50, 50
    
    k_values = []
    for i in range(period - 1, len(closes)):
        high_n = max(highs[i-period+1:i+1])
        low_n = min(lows[i-period+1:i+1])
        if high_n - low_n != 0:
            k = ((closes[i] - low_n) / (high_n - low_n)) * 100
        else:
            k = 50
        k_values.append(k)
    
    k = k_values[-1]
    d = statistics.mean(k_values[-3:]) if len(k_values) >= 3 else k
    return k, d


def calc_macd(closes):
    """MACD Line, Signal Line, Histogram"""
    if len(closes) < 26:
        return 0, 0, 0
    
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    
    # Align lengths
    min_len = min(len(ema12), len(ema26))
    ema12 = ema12[-min_len:]
    ema26 = ema26[-min_len:]
    
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    
    if len(macd_line) >= 9:
        signal = calc_ema(macd_line, 9)
        signal_val = signal[-1]
    else:
        signal_val = macd_line[-1]
    
    macd_val = macd_line[-1]
    histogram = macd_val - signal_val
    
    return macd_val, signal_val, histogram


def calc_bollinger(closes, period=20, std_dev=2):
    """Bollinger Bands - returns position (0=lower band, 1=upper band)"""
    if len(closes) < period:
        return 0.5
    
    sma = statistics.mean(closes[-period:])
    std = statistics.stdev(closes[-period:])
    
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    
    if upper - lower == 0:
        return 0.5
    
    position = (closes[-1] - lower) / (upper - lower)
    return max(0, min(1, position))


# ═══════════════════════════════════════════════════════════════
# SCORING ENGINE
# ═══════════════════════════════════════════════════════════════

def score_trend(closes):
    """Score based on SMA crossover (20 vs 50)"""
    if len(closes) < 50:
        return 0
    
    sma20 = statistics.mean(closes[-20:])
    sma50 = statistics.mean(closes[-50:])
    price = closes[-1]
    
    # Price above both = bullish, below both = bearish
    score = 0
    
    # SMA20 vs SMA50 crossover
    if sma20 > sma50:
        score += 12  # bullish cross
    else:
        score -= 12  # bearish cross
    
    # Price relative to SMAs
    if price > sma20:
        score += 8
    else:
        score -= 8
    
    if price > sma50:
        score += 5
    else:
        score -= 5
    
    return max(-25, min(25, score))


def score_momentum(rsi, stoch_k, stoch_d):
    """Score based on RSI and Stochastic"""
    score = 0
    
    # RSI scoring
    if rsi > 70:
        score -= 10  # overbought = bearish
    elif rsi > 60:
        score -= 3
    elif rsi < 30:
        score += 10  # oversold = bullish
    elif rsi < 40:
        score += 3
    else:
        score += (rsi - 50) * 0.2  # slight lean
    
    # Stochastic scoring
    if stoch_k > 80:
        score -= 7
    elif stoch_k < 20:
        score += 7
    
    # K crossing D
    if stoch_k > stoch_d:
        score += 3  # bullish cross
    else:
        score -= 3  # bearish cross
    
    return max(-20, min(20, score))


def score_volume(volumes):
    """Score based on volume trend"""
    if len(volumes) < 20:
        return 0
    
    avg_vol = statistics.mean(volumes[-20:])
    recent_vol = statistics.mean(volumes[-5:])
    
    # Volume increasing = confirms trend
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
    
    if vol_ratio > 1.5:
        score = 10  # high volume confirms move
    elif vol_ratio > 1.2:
        score = 5
    elif vol_ratio < 0.7:
        score = -5  # low volume = weak move
    else:
        score = 0
    
    return max(-15, min(15, score))


def score_volatility(bb_position):
    """Score based on Bollinger Band position"""
    # Near lower band = potential bounce (bullish)
    # Near upper band = potential reversal (bearish)
    if bb_position < 0.2:
        return 10  # near lower band, bullish bounce
    elif bb_position < 0.35:
        return 5
    elif bb_position > 0.8:
        return -10  # near upper band, bearish reversal
    elif bb_position > 0.65:
        return -5
    return 0


def score_macd(macd_val, signal_val, histogram):
    """Score based on MACD"""
    score = 0
    
    # MACD above signal = bullish
    if macd_val > signal_val:
        score += 7
    else:
        score -= 7
    
    # Histogram direction (momentum of the momentum)
    if histogram > 0:
        score += 5
    else:
        score -= 5
    
    # MACD above zero line = bullish bias
    if macd_val > 0:
        score += 3
    else:
        score -= 3
    
    return max(-15, min(15, score))


def score_pattern(closes):
    """Score based on recent price action"""
    if len(closes) < 10:
        return 0
    
    score = 0
    
    # Last 5 days trend
    recent = closes[-5:]
    if all(recent[i] >= recent[i-1] for i in range(1, len(recent))):
        score += 7  # 5 green days
    elif all(recent[i] <= recent[i-1] for i in range(1, len(recent))):
        score -= 7  # 5 red days
    
    # Higher lows (bullish) or lower highs (bearish)
    last_3 = closes[-3:]
    prev_3 = closes[-6:-3]
    if min(last_3) > min(prev_3):
        score += 3  # higher lows
    elif max(last_3) < max(prev_3):
        score -= 3  # lower highs
    
    return max(-10, min(10, score))


# ═══════════════════════════════════════════════════════════════
# MAIN SCORING FUNCTION
# ═══════════════════════════════════════════════════════════════

def calculate_score(symbol):
    """Calculate the complete OPTIX score for a symbol"""
    data = fetch_chart(symbol, "1d", "3mo")
    if not data:
        return None
    
    meta = data["meta"]
    quotes = data["indicators"]["quote"][0]
    
    closes = [c for c in quotes["close"] if c is not None]
    highs = [h for h in quotes["high"] if h is not None]
    lows = [l for l in quotes["low"] if l is not None]
    volumes = [v for v in quotes["volume"] if v is not None]
    
    if len(closes) < 30:
        return None
    
    # Calculate all indicators
    rsi = calc_rsi(closes)
    stoch_k, stoch_d = calc_stochastic(highs, lows, closes)
    macd_val, signal_val, histogram = calc_macd(closes)
    bb_position = calc_bollinger(closes)
    
    # Calculate individual scores
    trend_score = score_trend(closes)
    momentum_score = score_momentum(rsi, stoch_k, stoch_d)
    volume_score = score_volume(volumes)
    volatility_score = score_volatility(bb_position)
    macd_score = score_macd(macd_val, signal_val, histogram)
    pattern_score = score_pattern(closes)
    
    # Total score (-100 to +100)
    total_score = int(round(trend_score + momentum_score + volume_score + volatility_score + macd_score + pattern_score))
    
    # Price info
    price = closes[-1]
    prev_price = closes[-2] if len(closes) > 1 else price
    change_pct = ((price - prev_price) / prev_price) * 100
    
    # 5-day change
    five_day_price = closes[-5] if len(closes) >= 5 else closes[0]
    five_day_change = ((price - five_day_price) / five_day_price) * 100
    
    return {
        "symbol": symbol,
        "price": price,
        "change_pct": change_pct,
        "five_day_change": five_day_change,
        "total_score": total_score,
        "scores": {
            "trend": trend_score,
            "momentum": momentum_score,
            "volume": volume_score,
            "volatility": volatility_score,
            "macd": macd_score,
            "pattern": pattern_score,
        },
        "indicators": {
            "rsi": rsi,
            "stoch_k": stoch_k,
            "stoch_d": stoch_d,
            "macd": macd_val,
            "signal": signal_val,
            "bb_position": bb_position,
        },
        "name": meta.get("longName", meta.get("shortName", symbol)),
    }


# ═══════════════════════════════════════════════════════════════
# DISPLAY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def get_signal(score):
    """Get trading signal from score"""
    if score >= 30:
        return "🟢 STRONG BUY CALL", "strong_bull"
    elif score >= 15:
        return "🟢 BUY CALL", "bull"
    elif score >= 5:
        return "🟡 LEAN BULLISH", "lean_bull"
    elif score <= -30:
        return "🔴 STRONG BUY PUT", "strong_bear"
    elif score <= -15:
        return "🔴 BUY PUT", "bear"
    elif score <= -5:
        return "🟡 LEAN BEARISH", "lean_bear"
    else:
        return "⚪ NEUTRAL / STAY OUT", "neutral"


def score_bar(score, width=30):
    """Create ASCII score bar"""
    normalized = int((score + 100) / 200 * width)
    normalized = max(0, min(width, normalized))
    center = width // 2
    
    bar = list("─" * width)
    bar[center] = "│"
    
    if normalized > center:
        for i in range(center + 1, normalized + 1):
            if i < width:
                bar[i] = "█"
    elif normalized < center:
        for i in range(normalized, center):
            bar[i] = "█"
    
    return "".join(bar)


def display_single(result):
    """Display detailed score for a single symbol"""
    if not result:
        print("  ❌ Failed to fetch data")
        return
    
    signal, strength = get_signal(result["total_score"])
    
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║  OPTIX SCORE: {result['symbol']:<10}                                    ║
║  {result['name'][:55]:<55} ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  💰 Price: ${result['price']:.2f}  ({'+' if result['change_pct'] >= 0 else ''}{result['change_pct']:.2f}% today)               
║  📅 5-Day: {'+' if result['five_day_change'] >= 0 else ''}{result['five_day_change']:.2f}%                                      
║                                                               ║
║  ╔══════════════════════════════════════╗                      ║
║  ║  SIGNAL: {signal:<28}║                      ║
║  ║  SCORE:  {result['total_score']:+d}/100{' ' * 24}║                      ║
║  ╚══════════════════════════════════════╝                      ║
║                                                               ║
║  SCORE BREAKDOWN:                                             ║
║  ─────────────────────────────────────                        ║""")
    
    labels = {
        "trend": "📈 Trend    ",
        "momentum": "🚀 Momentum ",
        "volume": "📊 Volume   ",
        "volatility": "🌊 Volatility",
        "macd": "📉 MACD     ",
        "pattern": "🕯️  Pattern  ",
    }
    
    for key, label in labels.items():
        s = result["scores"][key]
        bar = score_bar(s * 4, 20)  # Scale up for visual
        print(f"║  {label} [{bar}] {int(s):+3d}")
    
    print(f"""║                                                               ║
║  INDICATORS:                                                  ║
║  ─────────────────────────────────────                        ║
║  RSI:        {result['indicators']['rsi']:.1f}  {'🔥 Overbought' if result['indicators']['rsi'] > 70 else '❄️  Oversold' if result['indicators']['rsi'] < 30 else '😐 Neutral'}
║  Stoch %K:   {result['indicators']['stoch_k']:.1f}  %D: {result['indicators']['stoch_d']:.1f}
║  MACD:       {result['indicators']['macd']:.4f}  Signal: {result['indicators']['signal']:.4f}
║  BB Position: {result['indicators']['bb_position']:.2f}  {'🔝 Upper' if result['indicators']['bb_position'] > 0.8 else '🔽 Lower' if result['indicators']['bb_position'] < 0.2 else '↔️  Middle'}
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝""")
    
    # Fun commentary
    score = result["total_score"]
    if score >= 30:
        print("  🎯 CONVICTION: The stars are aligning! Strong bullish setup.")
        print("  💡 Consider: ATM or slightly OTM calls, 2-4 weeks out")
    elif score >= 15:
        print("  🎯 LEAN: Bullish signals building. Watch for confirmation.")
        print("  💡 Consider: Slightly OTM calls or bull call spreads")
    elif score <= -30:
        print("  🎯 CONVICTION: Bears are in control! Strong bearish setup.")
        print("  💡 Consider: ATM or slightly OTM puts, 2-4 weeks out")
    elif score <= -15:
        print("  🎯 LEAN: Bearish signals building. Watch for breakdown.")
        print("  💡 Consider: Slightly OTM puts or bear put spreads")
    else:
        print("  🎯 WAIT: Mixed signals. No clear edge right now.")
        print("  💡 Consider: Sell premium (iron condors, strangles) or wait")
    print()


def display_watchlist(symbols, title):
    """Display score dashboard for watchlist"""
    print(f"""
╔═══════════════════════════════════════════════════════════════════════════════════╗
║  OPTIX DASHBOARD: {title:<60}║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║  {'Symbol':<8} {'Price':>9} {'Chg%':>7} {'Score':>6} {'Signal':<25} {'RSI':>5} {'Stoch':>6} ║
╠═══════════════════════════════════════════════════════════════════════════════════╣""")
    
    results = []
    for sym in symbols:
        sys.stdout.write(f"\r  ⏳ Fetching {sym}...          ")
        sys.stdout.flush()
        result = calculate_score(sym)
        if result:
            results.append(result)
    
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()
    
    # Sort by score
    results.sort(key=lambda x: x["total_score"], reverse=True)
    
    for r in results:
        signal, _ = get_signal(r["total_score"])
        chg = f"{'+' if r['change_pct'] >= 0 else ''}{r['change_pct']:.1f}%"
        print(f"║  {r['symbol']:<8} ${r['price']:>8.2f} {chg:>7} {r['total_score']:>+4d}   {signal:<25} {r['indicators']['rsi']:>5.1f} {r['indicators']['stoch_k']:>5.1f}% ║")
    
    print("╚═══════════════════════════════════════════════════════════════════════════════════╝")
    
    # Top picks
    bulls = [r for r in results if r["total_score"] >= 15]
    bears = [r for r in results if r["total_score"] <= -15]
    
    if bulls:
        print(f"\n  🟢 TOP CALL PICKS: {', '.join(r['symbol'] for r in bulls[:3])}")
    if bears:
        print(f"  🔴 TOP PUT PICKS:  {', '.join(r['symbol'] for r in bears[:3])}")
    if not bulls and not bears:
        print(f"\n  ⚪ No strong signals right now. Consider selling premium.")
    print()
    
    return results


# ═══════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════

def print_banner():
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║     ██████  ██████  ████████ ██ ██   ██                  ║
    ║    ██    ██ ██   ██    ██    ██  ██ ██                   ║
    ║    ██    ██ ██████     ██    ██   ███                    ║
    ║    ██    ██ ██         ██    ██  ██ ██                   ║
    ║     ██████  ██         ██    ██ ██   ██                  ║
    ║                                                           ║
    ║     Options Trading Intelligence eXplorer                ║
    ║     Score System v1.0                                    ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)


def print_help():
    print("""
  COMMANDS:
  ─────────────────────────────────────────────────────────
  <SYMBOL>        Score a single stock (e.g., AAPL, TSLA)
  tech            Scan top 10 tech stocks
  etf             Scan top 10 ETFs/indexes
  all             Scan all 20 symbols
  vs <S1> <S2>    Compare two symbols head-to-head

  DAY TRADING:
  ─────────────────────────────────────────────────────────
  dt <SYMBOL>     Day trade scanner for one stock
  dt tech         Day trade scan top 10 tech
  dt etf          Day trade scan top 10 ETFs
  dt all          Day trade scan all 20 symbols

  SELL PREMIUM (Theta Gang):
  ─────────────────────────────────────────────────────────
  sell <SYMBOL>   Sell premium score for one stock
  sell tech       Sell premium scan top 10 tech
  sell etf        Sell premium scan top 10 ETFs
  sell all        Sell premium scan all 20 symbols

  TRADE PLANS:
  ─────────────────────────────────────────────────────────
  plan            Show all trade plans
  plan add        Add a new trade plan
  plan done <ID>  Mark plan as filled
  plan close <ID> Mark plan as closed (took profit)
  plan cancel <ID> Cancel a plan
  plan rm <ID>    Remove a plan

  MY PORTFOLIO:
  ─────────────────────────────────────────────────────────
  my              Scan my holdings (buy + sell + CC recs)

  OTHER:
  ─────────────────────────────────────────────────────────
  help            Show this help
  quit            Exit

  SCORE GUIDE (BUY OPTIONS):
  ─────────────────────────────────────────────────────────
  +30 to +100    🟢 STRONG BUY CALL / SCALP CALLS
  +15 to +29     🟢 BUY CALL
   +5 to +14     🟡 LEAN BULLISH
   -4 to  +4     ⚪ NEUTRAL / STAY OUT
  -14 to  -5     🟡 LEAN BEARISH
  -29 to -15     🔴 BUY PUT
  -100 to -30    🔴 STRONG BUY PUT / SCALP PUTS

  SCORE GUIDE (SELL PREMIUM):
  ─────────────────────────────────────────────────────────
  75 to 100      🟣 STRONG SELL PREMIUM
  60 to 74       🟣 SELL PREMIUM
  45 to 59       🟡 LEAN SELL (reduce size)
  30 to 44       ⚪ MARGINAL
   0 to 29       ❌ DON'T SELL (trending/low IV)
  ─────────────────────────────────────────────────────────
    """)


def compare_symbols(sym1, sym2):
    """Head-to-head comparison"""
    print(f"\n  ⚔️  HEAD TO HEAD: {sym1} vs {sym2}")
    print("  " + "═" * 50)
    
    r1 = calculate_score(sym1)
    r2 = calculate_score(sym2)
    
    if not r1 or not r2:
        print("  ❌ Could not fetch data for one or both symbols")
        return
    
    sig1, _ = get_signal(r1["total_score"])
    sig2, _ = get_signal(r2["total_score"])
    
    print(f"""
  {'':>15} {sym1:>12}  {'vs':^4}  {sym2:<12}
  {'─'*50}
  {'Price':>15} ${r1['price']:>9.2f}  {'':^4}  ${r2['price']:<9.2f}
  {'Daily Chg':>15} {r1['change_pct']:>+8.2f}%  {'':^4}  {r2['change_pct']:<+8.2f}%
  {'5-Day Chg':>15} {r1['five_day_change']:>+8.2f}%  {'':^4}  {r2['five_day_change']:<+8.2f}%
  {'─'*50}
  {'SCORE':>15} {r1['total_score']:>+9d}  {'':^4}  {r2['total_score']:<+9d}
  {'Signal':>15} {sig1}  vs  {sig2}
  {'─'*50}
  {'RSI':>15} {r1['indicators']['rsi']:>9.1f}  {'':^4}  {r2['indicators']['rsi']:<9.1f}
  {'Stoch %K':>15} {r1['indicators']['stoch_k']:>9.1f}  {'':^4}  {r2['indicators']['stoch_k']:<9.1f}
  {'MACD':>15} {r1['indicators']['macd']:>9.4f}  {'':^4}  {r2['indicators']['macd']:<9.4f}
  {'BB Pos':>15} {r1['indicators']['bb_position']:>9.2f}  {'':^4}  {r2['indicators']['bb_position']:<9.2f}
  {'─'*50}""")
    
    if r1["total_score"] > r2["total_score"]:
        print(f"\n  🏆 WINNER: {sym1} (more bullish setup)")
    elif r2["total_score"] > r1["total_score"]:
        print(f"\n  🏆 WINNER: {sym2} (more bullish setup)")
    else:
        print(f"\n  🤝 TIE: Both have similar setups")
    print()


# ═══════════════════════════════════════════════════════════════
# DAY TRADING MODE
# ═══════════════════════════════════════════════════════════════

def fetch_intraday(symbol, interval="5m"):
    """Fetch intraday data"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range=1d&includePrePost=false"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data["chart"]["result"][0]
    except:
        return None


def calc_vwap(highs, lows, closes, volumes):
    """Volume Weighted Average Price - king of day trading"""
    if not highs or not volumes:
        return 0
    
    typical_prices = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    cum_vol = 0
    cum_tp_vol = 0
    vwap_values = []
    
    for tp, vol in zip(typical_prices, volumes):
        if vol is None or tp is None:
            continue
        cum_vol += vol
        cum_tp_vol += tp * vol
        if cum_vol > 0:
            vwap_values.append(cum_tp_vol / cum_vol)
    
    return vwap_values[-1] if vwap_values else 0


def calc_ema_fast(data, period):
    """Fast EMA for intraday"""
    if len(data) < period:
        return data[-1] if data else 0
    multiplier = 2 / (period + 1)
    ema = statistics.mean(data[:period])
    for price in data[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def day_trade_score(symbol):
    """Calculate day trading score using intraday data"""
    # Get 5-minute data for today
    data = fetch_intraday(symbol, "5m")
    if not data:
        return None
    
    meta = data["meta"]
    quotes = data["indicators"]["quote"][0]
    timestamps = data.get("timestamp", [])
    
    closes = [c for c in quotes["close"] if c is not None]
    highs = [h for h in quotes["high"] if h is not None]
    lows = [l for l in quotes["low"] if l is not None]
    volumes = [v for v in quotes["volume"] if v is not None]
    
    if len(closes) < 10:
        return None
    
    price = closes[-1]
    day_open = closes[0]
    day_high = max(highs)
    day_low = min(lows)
    
    # ─── INDICATORS ───
    
    # 1. VWAP (most important for day trading)
    vwap = calc_vwap(highs, lows, closes, volumes)
    
    # 2. EMA 9 & 21 (fast moving averages)
    ema9 = calc_ema_fast(closes, 9)
    ema21 = calc_ema_fast(closes, 21)
    
    # 3. RSI on 5-min (fast)
    rsi = calc_rsi(closes, 14)
    
    # 4. Volume momentum
    avg_vol = statistics.mean(volumes) if volumes else 0
    recent_vol = statistics.mean(volumes[-5:]) if len(volumes) >= 5 else avg_vol
    vol_spike = recent_vol / avg_vol if avg_vol > 0 else 1
    
    # 5. Price momentum (last 5 candles)
    if len(closes) >= 5:
        momentum = ((closes[-1] - closes[-5]) / closes[-5]) * 100
    else:
        momentum = 0
    
    # 6. Day range position
    day_range = day_high - day_low
    if day_range > 0:
        range_pos = (price - day_low) / day_range
    else:
        range_pos = 0.5
    
    # ─── SCORING ───
    score = 0
    signals = []
    
    # VWAP Score (±25 points)
    if price > vwap * 1.002:  # above VWAP with buffer
        vwap_score = 20
        signals.append("📍 Above VWAP (bullish)")
    elif price > vwap:
        vwap_score = 10
        signals.append("📍 Slightly above VWAP")
    elif price < vwap * 0.998:
        vwap_score = -20
        signals.append("📍 Below VWAP (bearish)")
    else:
        vwap_score = -10
        signals.append("📍 Slightly below VWAP")
    score += vwap_score
    
    # EMA Crossover Score (±20 points)
    if ema9 > ema21:
        ema_score = 15
        signals.append("📈 EMA9 > EMA21 (uptrend)")
    else:
        ema_score = -15
        signals.append("📉 EMA9 < EMA21 (downtrend)")
    
    if price > ema9:
        ema_score += 5
    else:
        ema_score -= 5
    score += ema_score
    
    # RSI Score (±15 points)
    if rsi > 70:
        rsi_score = -15
        signals.append("🔥 RSI overbought (reversal risk)")
    elif rsi > 60:
        rsi_score = 5
        signals.append("💪 RSI strong momentum")
    elif rsi < 30:
        rsi_score = 15
        signals.append("❄️ RSI oversold (bounce setup)")
    elif rsi < 40:
        rsi_score = -5
        signals.append("😰 RSI weak momentum")
    else:
        rsi_score = 0
        signals.append(f"😐 RSI neutral ({rsi:.0f})")
    score += rsi_score
    
    # Volume Score (±15 points)
    if vol_spike > 2.0:
        vol_score = 15
        signals.append("🔊 VOLUME SURGE! High conviction move")
    elif vol_spike > 1.5:
        vol_score = 10
        signals.append("📊 Above average volume")
    elif vol_spike < 0.5:
        vol_score = -10
        signals.append("🔇 Low volume (weak move)")
    else:
        vol_score = 0
        signals.append("📊 Normal volume")
    score += vol_score
    
    # Momentum Score (±15 points)
    if momentum > 0.5:
        mom_score = 15
        signals.append(f"🚀 Strong upward momentum (+{momentum:.2f}%)")
    elif momentum > 0.2:
        mom_score = 8
        signals.append(f"↗️ Mild upward momentum (+{momentum:.2f}%)")
    elif momentum < -0.5:
        mom_score = -15
        signals.append(f"💥 Strong downward momentum ({momentum:.2f}%)")
    elif momentum < -0.2:
        mom_score = -8
        signals.append(f"↘️ Mild downward momentum ({momentum:.2f}%)")
    else:
        mom_score = 0
        signals.append(f"↔️ Flat momentum ({momentum:.2f}%)")
    score += mom_score
    
    # Range Position Score (±10 points)
    if range_pos > 0.8:
        range_score = -5  # near HOD, less upside
        signals.append("🔝 Near high of day")
    elif range_pos < 0.2:
        range_score = 5   # near LOD, bounce potential
        signals.append("🔽 Near low of day")
    else:
        range_score = 0
    score += range_score
    
    # Determine action
    if score >= 35:
        action = "🟢🟢🟢 SCALP CALLS NOW"
        confidence = "HIGH"
    elif score >= 20:
        action = "🟢 BUY CALLS"
        confidence = "MEDIUM"
    elif score >= 10:
        action = "🟡 LEAN CALLS (wait for dip)"
        confidence = "LOW"
    elif score <= -35:
        action = "🔴🔴🔴 SCALP PUTS NOW"
        confidence = "HIGH"
    elif score <= -20:
        action = "🔴 BUY PUTS"
        confidence = "MEDIUM"
    elif score <= -10:
        action = "🟡 LEAN PUTS (wait for bounce)"
        confidence = "LOW"
    else:
        action = "⚪ NO TRADE - WAIT"
        confidence = "NONE"
    
    return {
        "symbol": symbol,
        "price": price,
        "vwap": vwap,
        "ema9": ema9,
        "ema21": ema21,
        "rsi": rsi,
        "volume_spike": vol_spike,
        "momentum": momentum,
        "day_open": day_open,
        "day_high": day_high,
        "day_low": day_low,
        "range_pos": range_pos,
        "score": int(round(score)),
        "action": action,
        "confidence": confidence,
        "signals": signals,
        "name": meta.get("longName", meta.get("shortName", symbol)),
    }


def display_day_trade(result):
    """Display day trading analysis"""
    if not result:
        print("  ❌ No intraday data (market might be closed)")
        return
    
    r = result
    change_from_open = ((r["price"] - r["day_open"]) / r["day_open"]) * 100
    
    print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║  ⚡ DAY TRADE SCANNER: {r['symbol']:<10}                              ║
║  {r['name'][:55]:<55}       ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  💰 Price: ${r['price']:.2f}  ({'+' if change_from_open >= 0 else ''}{change_from_open:.2f}% from open)
║  📊 Open: ${r['day_open']:.2f}  High: ${r['day_high']:.2f}  Low: ${r['day_low']:.2f}
║                                                                   ║
║  ╔════════════════════════════════════════════╗                    ║
║  ║  ACTION: {r['action']:<33}║                    ║
║  ║  SCORE:  {r['score']:+d}/100  Confidence: {r['confidence']:<10}║                    ║
║  ╚════════════════════════════════════════════╝                    ║
║                                                                   ║
║  KEY LEVELS:                                                      ║
║  ─────────────────────────────────────────                        ║
║  VWAP:     ${r['vwap']:.2f}  {'🟢 ABOVE' if r['price'] > r['vwap'] else '🔴 BELOW'}
║  EMA 9:    ${r['ema9']:.2f}  {'🟢 ABOVE' if r['price'] > r['ema9'] else '🔴 BELOW'}
║  EMA 21:   ${r['ema21']:.2f}  {'🟢 ABOVE' if r['price'] > r['ema21'] else '🔴 BELOW'}
║                                                                   ║
║  INDICATORS:                                                      ║
║  ─────────────────────────────────────────                        ║
║  RSI (5m):   {r['rsi']:.1f}
║  Vol Spike:  {r['volume_spike']:.1f}x {'🔊' if r['volume_spike'] > 1.5 else '🔇' if r['volume_spike'] < 0.7 else '📊'}
║  Momentum:   {r['momentum']:+.3f}%
║  Day Range:  {r['range_pos']*100:.0f}% (0%=LOD, 100%=HOD)
║                                                                   ║
║  SIGNALS:                                                         ║
║  ─────────────────────────────────────────                        ║""")
    
    for sig in r["signals"]:
        print(f"║  • {sig}")
    
    print(f"""║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝""")
    
    # Trade plan suggestion
    score = r["score"]
    price = r["price"]
    
    if abs(score) >= 20:
        if score > 0:
            entry = price
            stop = r["vwap"] - 0.10
            target1 = price + (price - stop) * 1.5
            target2 = price + (price - stop) * 2.5
            print(f"""
  📋 TRADE PLAN (CALLS):
  ─────────────────────────────────────────
  Entry:    ${entry:.2f} (at market or on pullback to EMA9)
  Stop:     ${stop:.2f} (below VWAP)
  Target 1: ${target1:.2f} (1.5R)
  Target 2: ${target2:.2f} (2.5R)
  Risk:     ${entry - stop:.2f} per share
  
  ⏰ Best timeframe: 0DTE or same-week expiry
  🎯 Strike: ATM or 1 strike OTM
""")
        else:
            entry = price
            stop = r["vwap"] + 0.10
            target1 = price - (stop - price) * 1.5
            target2 = price - (stop - price) * 2.5
            print(f"""
  📋 TRADE PLAN (PUTS):
  ─────────────────────────────────────────
  Entry:    ${entry:.2f} (at market or on bounce to EMA9)
  Stop:     ${stop:.2f} (above VWAP)
  Target 1: ${target1:.2f} (1.5R)
  Target 2: ${target2:.2f} (2.5R)
  Risk:     ${stop - entry:.2f} per share
  
  ⏰ Best timeframe: 0DTE or same-week expiry
  🎯 Strike: ATM or 1 strike OTM
""")
    else:
        print("""
  ⏸️  NO TRADE SETUP - Wait for:
  • Price to clearly break above/below VWAP
  • Volume spike to confirm direction
  • EMA9/21 crossover
""")


def display_day_trade_watchlist(symbols, title):
    """Quick day trade scan across multiple symbols"""
    print(f"""
╔═══════════════════════════════════════════════════════════════════════════════════════════╗
║  ⚡ DAY TRADE SCANNER: {title:<64}║
╠═══════════════════════════════════════════════════════════════════════════════════════════╣
║  {'Symbol':<7} {'Price':>9} {'vs VWAP':>8} {'Mom%':>7} {'RSI':>5} {'VolX':>5} {'Score':>6} {'Action':<30} ║
╠═══════════════════════════════════════════════════════════════════════════════════════════╣""")
    
    results = []
    for sym in symbols:
        sys.stdout.write(f"\r  ⚡ Scanning {sym}...          ")
        sys.stdout.flush()
        result = day_trade_score(sym)
        if result:
            results.append(result)
    
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()
    
    # Sort by absolute score (strongest signals first)
    results.sort(key=lambda x: abs(x["score"]), reverse=True)
    
    for r in results:
        vwap_diff = ((r["price"] - r["vwap"]) / r["vwap"]) * 100 if r["vwap"] > 0 else 0
        vwap_str = f"{'+' if vwap_diff >= 0 else ''}{vwap_diff:.2f}%"
        mom_str = f"{'+' if r['momentum'] >= 0 else ''}{r['momentum']:.2f}%"
        
        print(f"║  {r['symbol']:<7} ${r['price']:>8.2f} {vwap_str:>8} {mom_str:>7} {r['rsi']:>5.0f} {r['volume_spike']:>4.1f}x {r['score']:>+4d}   {r['action']:<30} ║")
    
    print("╚═══════════════════════════════════════════════════════════════════════════════════════════╝")
    
    # Hot picks
    hot_calls = [r for r in results if r["score"] >= 20]
    hot_puts = [r for r in results if r["score"] <= -20]
    
    if hot_calls:
        calls_str = ', '.join(f"{r['symbol']}({r['score']:+d})" for r in hot_calls[:3])
        print(f"\n  ⚡🟢 HOT CALLS: {calls_str}")
    if hot_puts:
        puts_str = ', '.join(f"{r['symbol']}({r['score']:+d})" for r in hot_puts[:3])
        print(f"  ⚡🔴 HOT PUTS:  {puts_str}")
    if not hot_calls and not hot_puts:
        print(f"\n  ⏸️  No hot setups right now. Wait for a catalyst.")
    print()
    
    return results


# ═══════════════════════════════════════════════════════════════
# SELL OPTIONS (PREMIUM SELLING) ENGINE
# ═══════════════════════════════════════════════════════════════

SELL_WEIGHTS = {
    "iv_rank": 25,         # High IV = rich premiums to sell
    "mean_reversion": 20,  # Stretched price likely to revert
    "range_bound": 20,     # Consolidation = theta profits
    "theta_opp": 15,       # Time decay sweet spot
    "liquidity": 10,       # Tight spreads, good fills
    "support_resist": 10,  # Near levels that contain price
}


def calc_historical_volatility(closes, period=20):
    """Calculate historical (realized) volatility"""
    if len(closes) < period + 1:
        return 0
    returns = [(closes[i] / closes[i-1]) - 1 for i in range(1, len(closes))]
    recent_returns = returns[-period:]
    if len(recent_returns) < 2:
        return 0
    hv = statistics.stdev(recent_returns) * math.sqrt(252) * 100
    return hv


def calc_iv_rank(closes, period=60):
    """
    Estimate IV Rank using realized vol percentile as proxy.
    Compares current 20-day HV to the range of HV over the lookback period.
    """
    if len(closes) < period + 21:
        return 50  # default neutral

    hv_values = []
    for i in range(21, len(closes)):
        window = closes[i-20:i]
        returns = [(window[j] / window[j-1]) - 1 for j in range(1, len(window))]
        if len(returns) >= 2:
            hv = statistics.stdev(returns) * math.sqrt(252) * 100
            hv_values.append(hv)

    if len(hv_values) < 10:
        return 50

    current_hv = hv_values[-1]
    hv_min = min(hv_values)
    hv_max = max(hv_values)

    if hv_max - hv_min == 0:
        return 50

    iv_rank = ((current_hv - hv_min) / (hv_max - hv_min)) * 100
    return iv_rank


def calc_adx(highs, lows, closes, period=14):
    """Average Directional Index - measures trend strength"""
    if len(closes) < period * 2:
        return 25  # neutral default

    plus_dm = []
    minus_dm = []
    tr_list = []

    for i in range(1, len(closes)):
        high_diff = highs[i] - highs[i-1]
        low_diff = lows[i-1] - lows[i]

        if high_diff > low_diff and high_diff > 0:
            plus_dm.append(high_diff)
        else:
            plus_dm.append(0)

        if low_diff > high_diff and low_diff > 0:
            minus_dm.append(low_diff)
        else:
            minus_dm.append(0)

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)

    if len(tr_list) < period:
        return 25

    # Smoothed averages
    atr = statistics.mean(tr_list[:period])
    plus_di_smooth = statistics.mean(plus_dm[:period])
    minus_di_smooth = statistics.mean(minus_dm[:period])

    dx_values = []
    for i in range(period, len(tr_list)):
        atr = (atr * (period - 1) + tr_list[i]) / period
        plus_di_smooth = (plus_di_smooth * (period - 1) + plus_dm[i]) / period
        minus_di_smooth = (minus_di_smooth * (period - 1) + minus_dm[i]) / period

        if atr == 0:
            continue
        plus_di = (plus_di_smooth / atr) * 100
        minus_di = (minus_di_smooth / atr) * 100

        di_sum = plus_di + minus_di
        if di_sum == 0:
            continue
        dx = abs(plus_di - minus_di) / di_sum * 100
        dx_values.append(dx)

    if len(dx_values) < period:
        return 25

    adx = statistics.mean(dx_values[-period:])
    return adx


def score_sell_iv_rank(iv_rank):
    """
    Score IV rank for selling premium.
    High IV rank = options are expensive = great time to sell.
    """
    if iv_rank >= 80:
        return 25   # IV at highs - maximum premium selling opportunity
    elif iv_rank >= 60:
        return 18
    elif iv_rank >= 45:
        return 10
    elif iv_rank >= 30:
        return 0    # neutral zone
    elif iv_rank >= 15:
        return -10  # IV too low, not worth selling
    else:
        return -20  # IV crushed, terrible time to sell premium


def score_sell_mean_reversion(rsi, bb_position, closes):
    """
    Score mean reversion potential.
    Extreme moves tend to revert = good for selling premium against the move.
    """
    score = 0

    # RSI extremes favor mean reversion (good for selling)
    if rsi > 75 or rsi < 25:
        score += 12  # Very stretched, high chance of reversion
    elif rsi > 65 or rsi < 35:
        score += 6
    elif 45 <= rsi <= 55:
        score += 3   # Neutral is okay too (range-bound)
    else:
        score -= 3   # Mild trending, not ideal

    # Bollinger Band extremes
    if bb_position > 0.9 or bb_position < 0.1:
        score += 8   # Way outside bands = snap-back likely
    elif bb_position > 0.75 or bb_position < 0.25:
        score += 4
    else:
        score += 2   # Inside bands = contained

    return max(-20, min(20, score))


def score_sell_range_bound(adx, closes, highs, lows):
    """
    Score how range-bound the stock is.
    Low ADX + tight range = perfect for selling premium.
    """
    score = 0

    # ADX score (low ADX = no trend = good for selling)
    if adx < 15:
        score += 15  # No trend at all - ideal for iron condors
    elif adx < 20:
        score += 10  # Weak trend
    elif adx < 25:
        score += 3   # Mild trend
    elif adx < 35:
        score -= 5   # Moderate trend - risky
    else:
        score -= 15  # Strong trend - AVOID selling premium

    # Price range compression (last 10 days vs last 30 days)
    if len(highs) >= 30 and len(lows) >= 30:
        recent_range = max(highs[-10:]) - min(lows[-10:])
        wider_range = max(highs[-30:]) - min(lows[-30:])
        if wider_range > 0:
            compression = recent_range / wider_range
            if compression < 0.4:
                score += 5   # Very compressed - coiling (careful, could break)
            elif compression < 0.6:
                score += 3   # Compressed
            elif compression > 0.9:
                score -= 5   # Expanding range

    return max(-20, min(20, score))


def score_sell_theta_opportunity(closes):
    """
    Score theta decay opportunity.
    Small daily moves = theta eats premium steadily without gamma risk.
    """
    if len(closes) < 20:
        return 0

    score = 0

    # Daily moves - small daily moves = theta heaven
    recent_returns = [abs((closes[i] / closes[i-1]) - 1) * 100 for i in range(-10, 0)]
    avg_daily_move = statistics.mean(recent_returns)

    if avg_daily_move < 0.8:
        score += 12  # Tiny daily moves - theta heaven
    elif avg_daily_move < 1.2:
        score += 8   # Low moves
    elif avg_daily_move < 2.0:
        score += 2   # Average
    elif avg_daily_move < 3.0:
        score -= 5   # Volatile
    else:
        score -= 12  # Very volatile - gamma risk dominates

    # Consecutive days without big moves
    small_days = sum(1 for r in recent_returns if r < 1.5)
    if small_days >= 8:
        score += 3
    elif small_days <= 3:
        score -= 3

    return max(-15, min(15, score))


def score_sell_liquidity(volumes, price):
    """
    Score options liquidity proxy.
    High volume + reasonable price = likely liquid options market.
    """
    if len(volumes) < 10:
        return 0

    score = 0
    avg_vol = statistics.mean(volumes[-20:]) if len(volumes) >= 20 else statistics.mean(volumes)

    # Volume scoring (proxy for options liquidity)
    if avg_vol > 20_000_000:
        score += 8   # Mega liquid (SPY, QQQ, AAPL)
    elif avg_vol > 5_000_000:
        score += 5   # Very liquid
    elif avg_vol > 1_000_000:
        score += 2   # Decent
    elif avg_vol < 500_000:
        score -= 5   # Low liquidity - wide options spreads

    # Price affects options chain richness
    if 20 <= price <= 500:
        score += 2   # Sweet spot for options
    elif price > 500:
        score += 1   # Still fine but bigger capital req
    elif price < 20:
        score -= 3   # Cheap stocks have garbage options spreads

    return max(-10, min(10, score))


def score_sell_support_resistance(closes, highs, lows):
    """
    Score proximity to support/resistance.
    Price at support = sell puts below. Price at resistance = sell calls above.
    """
    if len(closes) < 30:
        return 0

    score = 0
    price = closes[-1]

    # Calculate support and resistance using recent pivots
    recent_highs = highs[-30:]
    recent_lows = lows[-30:]

    resistance = max(recent_highs)
    support = min(recent_lows)
    range_size = resistance - support

    if range_size == 0:
        return 0

    # Position within range
    pos = (price - support) / range_size

    # Near support or resistance is GOOD for selling
    if pos < 0.15 or pos > 0.85:
        score += 7   # Very near a key level - sell against it
    elif pos < 0.25 or pos > 0.75:
        score += 4   # Near a key level
    elif 0.4 <= pos <= 0.6:
        score += 3   # Middle of range - good for iron condors
    else:
        score += 1

    # Bonus: multiple touches at support/resistance
    near_support = sum(1 for l in recent_lows[-15:] if abs(l - support) / support < 0.02)
    near_resistance = sum(1 for h in recent_highs[-15:] if abs(h - resistance) / resistance < 0.02)

    if near_support >= 3 or near_resistance >= 3:
        score += 3   # Well-tested levels = stronger

    return max(-10, min(10, score))


def sell_options_score(symbol):
    """
    Calculate sell options (premium selling) score for a symbol.
    High score = good environment to sell premium.
    """
    data = fetch_chart(symbol, "1d", "6mo")  # Need more history for IV rank
    if not data:
        return None

    meta = data["meta"]
    quotes = data["indicators"]["quote"][0]

    closes = [c for c in quotes["close"] if c is not None]
    highs = [h for h in quotes["high"] if h is not None]
    lows = [l for l in quotes["low"] if l is not None]
    volumes = [v for v in quotes["volume"] if v is not None]

    if len(closes) < 30:
        return None

    # Calculate indicators
    iv_rank = calc_iv_rank(closes)
    rsi = calc_rsi(closes)
    bb_position = calc_bollinger(closes)
    adx = calc_adx(highs, lows, closes)
    hv = calc_historical_volatility(closes)
    price = closes[-1]

    # Calculate individual scores
    iv_score = score_sell_iv_rank(iv_rank)
    reversion_score = score_sell_mean_reversion(rsi, bb_position, closes)
    range_score = score_sell_range_bound(adx, closes, highs, lows)
    theta_score = score_sell_theta_opportunity(closes)
    liquidity_score = score_sell_liquidity(volumes, price)
    sr_score = score_sell_support_resistance(closes, highs, lows)

    # Total raw score (can be -100 to +100)
    raw_score = iv_score + reversion_score + range_score + theta_score + liquidity_score + sr_score

    # Normalize to 0-100 scale (0=terrible, 100=perfect for selling)
    total_score = int(round(max(0, min(100, (raw_score + 100) / 2))))

    # Determine directional lean from buy-side indicators
    trend_sc = score_trend(closes)
    momentum_sc = score_momentum(rsi, *calc_stochastic(highs, lows, closes))

    directional_lean = trend_sc + momentum_sc  # -45 to +45

    # Strategy recommendation
    strategy = determine_sell_strategy(total_score, directional_lean, adx, iv_rank)

    # Price info
    prev_price = closes[-2] if len(closes) > 1 else price
    change_pct = ((price - prev_price) / prev_price) * 100
    five_day_price = closes[-5] if len(closes) >= 5 else closes[0]
    five_day_change = ((price - five_day_price) / five_day_price) * 100

    # Support/Resistance levels for strike selection
    support = min(lows[-30:])
    resistance = max(highs[-30:])

    return {
        "symbol": symbol,
        "price": price,
        "change_pct": change_pct,
        "five_day_change": five_day_change,
        "total_score": total_score,
        "raw_score": raw_score,
        "scores": {
            "iv_rank": iv_score,
            "mean_reversion": reversion_score,
            "range_bound": range_score,
            "theta_opp": theta_score,
            "liquidity": liquidity_score,
            "support_resist": sr_score,
        },
        "indicators": {
            "iv_rank_pct": iv_rank,
            "adx": adx,
            "rsi": rsi,
            "bb_position": bb_position,
            "hv_20": hv,
        },
        "strategy": strategy,
        "directional_lean": directional_lean,
        "support": support,
        "resistance": resistance,
        "name": meta.get("longName", meta.get("shortName", symbol)),
    }


def determine_sell_strategy(score, directional_lean, adx, iv_rank):
    """Determine the best premium selling strategy"""
    if score < 30:
        return {
            "name": "❌ DON'T SELL PREMIUM",
            "desc": "Conditions not favorable - trending market or low IV",
            "type": "none",
        }

    # Neutral / Range-bound strategies
    if abs(directional_lean) < 10 and adx < 25:
        if iv_rank >= 60:
            return {
                "name": "🦅 IRON CONDOR",
                "desc": "Sell OTM put spread + OTM call spread. Profit if price stays in range.",
                "type": "iron_condor",
            }
        else:
            return {
                "name": "🦎 SHORT STRANGLE",
                "desc": "Sell OTM put + OTM call. Higher premium but undefined risk.",
                "type": "strangle",
            }

    # Bullish lean - sell puts
    if directional_lean > 10:
        if directional_lean > 25:
            return {
                "name": "💰 CASH-SECURED PUT (Aggressive)",
                "desc": "Sell ATM/slightly OTM put. Collect premium or get shares at discount.",
                "type": "csp",
            }
        else:
            return {
                "name": "💵 BULL PUT SPREAD",
                "desc": "Sell OTM put + buy further OTM put. Limited risk, bullish bias.",
                "type": "bull_put_spread",
            }

    # Bearish lean - sell calls
    if directional_lean < -10:
        if directional_lean < -25:
            return {
                "name": "📞 COVERED CALL / NAKED CALL",
                "desc": "Sell ATM/slightly OTM call. Collect premium on bearish bias.",
                "type": "covered_call",
            }
        else:
            return {
                "name": "🐻 BEAR CALL SPREAD",
                "desc": "Sell OTM call + buy further OTM call. Limited risk, bearish bias.",
                "type": "bear_call_spread",
            }

    # Default neutral
    return {
        "name": "🦅 IRON CONDOR",
        "desc": "Sell OTM put spread + OTM call spread. Profit if price stays in range.",
        "type": "iron_condor",
    }


def get_sell_signal(score):
    """Get sell premium signal from score"""
    if score >= 75:
        return "🟣 STRONG SELL PREMIUM", "strong_sell"
    elif score >= 60:
        return "🟣 SELL PREMIUM", "sell"
    elif score >= 45:
        return "🟡 LEAN SELL", "lean_sell"
    elif score >= 30:
        return "⚪ MARGINAL", "marginal"
    else:
        return "❌ DON'T SELL", "avoid"


def sell_score_bar(score, width=30):
    """Create ASCII score bar for sell (0-100 scale)"""
    normalized = int(score / 100 * width)
    normalized = max(0, min(width, normalized))

    bar = list("░" * width)
    for i in range(normalized):
        if i < width:
            bar[i] = "█"

    return "".join(bar)


def display_sell_single(result):
    """Display detailed sell options score for a single symbol"""
    if not result:
        print("  ❌ Failed to fetch data")
        return

    signal, strength = get_sell_signal(result["total_score"])
    strat = result["strategy"]

    print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║  💜 SELL PREMIUM SCORE: {result['symbol']:<10}                           ║
║  {result['name'][:55]:<55}       ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  💰 Price: ${result['price']:.2f}  ({'+' if result['change_pct'] >= 0 else ''}{result['change_pct']:.2f}% today)
║  📅 5-Day: {'+' if result['five_day_change'] >= 0 else ''}{result['five_day_change']:.2f}%
║                                                                   ║
║  ╔════════════════════════════════════════════════╗                ║
║  ║  SIGNAL: {signal:<37}║                ║
║  ║  SCORE:  [{sell_score_bar(result['total_score'], 25)}] {result['total_score']}/100   ║                ║
║  ╚════════════════════════════════════════════════╝                ║
║                                                                   ║
║  STRATEGY RECOMMENDATION:                                         ║
║  ─────────────────────────────────────────                        ║
║  {strat['name']}
║  {strat['desc']}
║                                                                   ║
║  SCORE BREAKDOWN:                                                 ║
║  ─────────────────────────────────────────                        ║""")

    labels = {
        "iv_rank": "📊 IV Rank     ",
        "mean_reversion": "🔄 Mean Revert ",
        "range_bound": "📐 Range-Bound ",
        "theta_opp": "⏰ Theta Opp   ",
        "liquidity": "💧 Liquidity   ",
        "support_resist": "🧱 S/R Levels  ",
    }

    for key, label in labels.items():
        s = result["scores"][key]
        max_score = SELL_WEIGHTS[key]
        pct = int((s + max_score) / (2 * max_score) * 20)
        bar = "█" * max(0, pct) + "░" * (20 - max(0, pct))
        print(f"║  {label} [{bar}] {int(s):+3d}/{max_score}")

    print(f"""║                                                                   ║
║  KEY INDICATORS:                                                  ║
║  ─────────────────────────────────────────                        ║
║  IV Rank:    {result['indicators']['iv_rank_pct']:.0f}%  {'🔥 HIGH - Sell!' if result['indicators']['iv_rank_pct'] > 60 else '❄️ LOW - Avoid' if result['indicators']['iv_rank_pct'] < 30 else '😐 Normal'}
║  ADX:        {result['indicators']['adx']:.1f}  {'📐 Range-bound!' if result['indicators']['adx'] < 20 else '📈 Trending!' if result['indicators']['adx'] > 30 else '↔️ Mild'}
║  RSI:        {result['indicators']['rsi']:.1f}  {'🔥 Overbought' if result['indicators']['rsi'] > 70 else '❄️ Oversold' if result['indicators']['rsi'] < 30 else '😐 Neutral'}
║  HV (20d):   {result['indicators']['hv_20']:.1f}%
║  BB Position: {result['indicators']['bb_position']:.2f}
║                                                                   ║
║  STRIKE GUIDE:                                                    ║
║  ─────────────────────────────────────────                        ║
║  Support:     ${result['support']:.2f}  (sell puts below here)
║  Resistance:  ${result['resistance']:.2f}  (sell calls above here)
║  Lean:        {'BULLISH ↗️' if result['directional_lean'] > 10 else 'BEARISH ↘️' if result['directional_lean'] < -10 else 'NEUTRAL ↔️'} ({result['directional_lean']:+.0f})
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝""")

    # Action commentary
    score = result["total_score"]
    if score >= 75:
        print("  🎯 PREMIUM SELLING PARADISE! High IV + Range-bound = collect theta!")
        print(f"  💡 Strategy: {strat['name']}")
        print(f"  📅 Target DTE: 30-45 days for optimal theta decay")
        print(f"  🎯 Sell strikes: Put below ${result['support']:.2f} / Call above ${result['resistance']:.2f}")
    elif score >= 60:
        print("  🎯 Good environment for selling premium. IV is working in your favor.")
        print(f"  💡 Strategy: {strat['name']}")
        print(f"  📅 Target DTE: 30-45 days | Manage at 50% profit")
    elif score >= 45:
        print("  🎯 MARGINAL: Conditions okay but not ideal. Reduce size.")
        print(f"  💡 Strategy: {strat['name']} (smaller position)")
    else:
        print("  ⛔ NOT IDEAL for selling premium right now.")
        print("  💡 Market is trending or IV is too low. Wait for better setup.")
        print("  💡 Consider buying options instead (run the regular scan)")
    print()


def display_sell_watchlist(symbols, title):
    """Display sell premium dashboard for watchlist"""
    print(f"""
╔═══════════════════════════════════════════════════════════════════════════════════════════════════╗
║  💜 SELL PREMIUM DASHBOARD: {title:<65}║
╠═══════════════════════════════════════════════════════════════════════════════════════════════════╣
║  {'Symbol':<8} {'Price':>9} {'Score':>6} {'Signal':<22} {'IV%':>5} {'ADX':>5} {'RSI':>5} {'Strategy':<25} ║
╠═══════════════════════════════════════════════════════════════════════════════════════════════════╣""")

    results = []
    for sym in symbols:
        sys.stdout.write(f"\r  💜 Analyzing {sym}...          ")
        sys.stdout.flush()
        result = sell_options_score(sym)
        if result:
            results.append(result)

    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()

    # Sort by score (best sell opportunities first)
    results.sort(key=lambda x: x["total_score"], reverse=True)

    for r in results:
        signal, _ = get_sell_signal(r["total_score"])
        strat_short = r["strategy"]["name"][:24]
        print(f"║  {r['symbol']:<8} ${r['price']:>8.2f} {r['total_score']:>4d}   {signal:<22} {r['indicators']['iv_rank_pct']:>4.0f}% {r['indicators']['adx']:>5.1f} {r['indicators']['rsi']:>5.1f} {strat_short:<25} ║")

    print("╚═══════════════════════════════════════════════════════════════════════════════════════════════════╝")

    # Top picks
    sellers = [r for r in results if r["total_score"] >= 60]
    avoid = [r for r in results if r["total_score"] < 30]

    if sellers:
        top_sells = ', '.join(f"{r['symbol']}({r['total_score']})" for r in sellers[:4])
        print(f"\n  💜 TOP PREMIUM SELLS: {top_sells}")
    if avoid:
        print(f"  ❌ AVOID SELLING: {', '.join(r['symbol'] for r in avoid[:4])}")
    if not sellers:
        print(f"\n  ⚪ No strong sell-premium setups. Consider directional trades instead.")
    print()

    return results


def run_sell_single(symbol, json_mode=False):
    """Run single sell premium scan"""
    result = sell_options_score(symbol)
    display_sell_single(result)
    if json_mode and result:
        save_json(result, f"sell_{symbol.lower()}.json", f"sell_single_{symbol}")
    return result


def run_sell_watchlist(symbols, title, json_mode=False):
    """Run sell premium watchlist scan"""
    results = display_sell_watchlist(symbols, title)
    if json_mode and results:
        save_json(results, "sell_latest.json", f"sell_watchlist_{title.lower().replace(' ', '_')}")
    return results


# ═══════════════════════════════════════════════════════════════
# JSON OUTPUT
# ═══════════════════════════════════════════════════════════════

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")


def ensure_data_dirs():
    """Create data/ and data/history/ directories if they don't exist"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)


def save_json(data, filename, scan_type):
    """Save scan results to JSON files (latest + history)"""
    ensure_data_dirs()

    now = datetime.datetime.now()
    output = {
        "scan_type": scan_type,
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "data": data,
    }

    # Save as latest
    latest_path = os.path.join(DATA_DIR, filename)
    with open(latest_path, "w") as f:
        json.dump(output, f, indent=2)

    # Save to history with timestamp
    history_filename = f"{now.strftime('%Y-%m-%d_%H%M')}_{filename}"
    history_path = os.path.join(HISTORY_DIR, history_filename)
    with open(history_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"  💾 Saved: {latest_path}")
    print(f"  💾 History: {history_path}")


def run_watchlist_scan(symbols, title, json_mode=False):
    """Run watchlist scan, optionally saving JSON"""
    results = display_watchlist(symbols, title)
    if json_mode and results:
        save_json(results, "watchlist_latest.json", f"watchlist_{title.lower().replace(' ', '_')}")
    return results


# ═══════════════════════════════════════════════════════════════
# TRADE PLAN MANAGER
# ═══════════════════════════════════════════════════════════════

PLANS_FILE = os.path.join(DATA_DIR, "trade_plans.json")


def load_plans():
    """Load trade plans from JSON file"""
    if not os.path.exists(PLANS_FILE):
        return {"portfolio": {}, "plans": []}
    with open(PLANS_FILE, "r") as f:
        return json.load(f)


def save_plans(data):
    """Save trade plans to JSON file"""
    ensure_data_dirs()
    with open(PLANS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_next_plan_id(plans_data):
    """Get next available plan ID"""
    if not plans_data["plans"]:
        return 1
    return max(p["id"] for p in plans_data["plans"]) + 1


def display_plans(filter_status=None):
    """Display all trade plans"""
    data = load_plans()

    if not data["plans"]:
        print("\n  📋 No trade plans yet. Use 'plan add' to create one.\n")
        return

    # Portfolio summary
    if data.get("portfolio"):
        print(f"\n  💼 PORTFOLIO:")
        print(f"  {'─' * 40}")
        for sym, info in data["portfolio"].items():
            print(f"  {sym:<8} {info['shares']:>6} shares")
        print()

    # Filter plans
    plans = data["plans"]
    if filter_status:
        plans = [p for p in plans if p["status"].lower() == filter_status.lower()]

    status_icons = {
        "WAITING": "⏳",
        "ACTIVE": "🟢",
        "FILLED": "✅",
        "CLOSED": "💰",
        "EXPIRED": "⏰",
        "CANCELLED": "❌",
        "OPTIONAL": "💡",
    }

    print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║  📋 TRADE PLANS                                                  ║
╠═══════════════════════════════════════════════════════════════════╣""")

    for p in plans:
        icon = status_icons.get(p["status"], "❓")
        strike_str = f"${p['strike']}" if isinstance(p.get('strike'), (int, float)) else str(p.get('strike', ''))
        contracts = p.get('contracts', 1)

        print(f"""║                                                                   ║
║  #{p['id']} {icon} {p['status']:<10} {p['symbol']} — {p['action']} @ {strike_str}
║     {'Contracts:':<11} {contracts}
║     {'Trigger:':<11} {p.get('trigger', 'N/A')}
║     {'Confirm:':<11} {p.get('confirmation', 'N/A')}
║     {'DTE:':<11} {p.get('dte_target', 'N/A')}
║     {'Exit:':<11} {p.get('exit_plan', 'N/A')}""")

        if p.get("notes"):
            print(f"║     {'Notes:':<11} {p['notes'][:55]}")

    print(f"""║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
""")

    # Summary
    waiting = sum(1 for p in data["plans"] if p["status"] == "WAITING")
    active = sum(1 for p in data["plans"] if p["status"] == "ACTIVE")
    if waiting:
        print(f"  ⏳ {waiting} plan(s) waiting for trigger")
    if active:
        print(f"  🟢 {active} plan(s) active")
    print()


def plan_add_interactive():
    """Interactive plan creation"""
    print("\n  📋 NEW TRADE PLAN")
    print("  " + "─" * 40)

    try:
        symbol = input("  Symbol: ").strip().upper()
        if not symbol:
            print("  ❌ Cancelled")
            return

        print("  Actions: SELL CALL, SELL PUT, SELL COVERED CALL, SELL CSP,")
        print("           BUY CALL, BUY PUT, IRON CONDOR, STRANGLE")
        action = input("  Action: ").strip().upper()

        strike_input = input("  Strike price: $").strip()
        try:
            strike = float(strike_input)
        except ValueError:
            strike = strike_input

        contracts = input("  Contracts (default 1): ").strip()
        contracts = int(contracts) if contracts else 1

        trigger = input("  Trigger (e.g., 2h Stoch > 80): ").strip()
        confirmation = input("  Confirmation (optional): ").strip()
        dte = input("  Target DTE (e.g., 7-14 days): ").strip()
        exit_plan = input("  Exit plan (e.g., 50% profit): ").strip()
        notes = input("  Notes (optional): ").strip()

        data = load_plans()
        plan_id = get_next_plan_id(data)

        new_plan = {
            "id": plan_id,
            "created": datetime.datetime.now().isoformat(),
            "status": "WAITING",
            "symbol": symbol,
            "action": action,
            "strike": strike,
            "contracts": contracts,
            "trigger": trigger or "Manual",
            "confirmation": confirmation or "",
            "dte_target": dte or "TBD",
            "exit_plan": exit_plan or "TBD",
            "notes": notes or "",
            "context": {},
        }

        data["plans"].append(new_plan)
        save_plans(data)

        print(f"\n  ✅ Plan #{plan_id} added: {symbol} {action} @ ${strike}")
        print()

    except (KeyboardInterrupt, EOFError):
        print("\n  ❌ Cancelled")


def plan_update_status(plan_id, new_status):
    """Update a plan's status"""
    data = load_plans()
    for p in data["plans"]:
        if p["id"] == plan_id:
            old_status = p["status"]
            p["status"] = new_status.upper()
            if new_status.upper() in ("FILLED", "ACTIVE"):
                p["filled_date"] = datetime.datetime.now().isoformat()
            elif new_status.upper() in ("CLOSED", "EXPIRED", "CANCELLED"):
                p["closed_date"] = datetime.datetime.now().isoformat()
            save_plans(data)
            print(f"  ✅ Plan #{plan_id} updated: {old_status} → {new_status.upper()}")
            return
    print(f"  ❌ Plan #{plan_id} not found")


def plan_remove(plan_id):
    """Remove a plan"""
    data = load_plans()
    original_len = len(data["plans"])
    data["plans"] = [p for p in data["plans"] if p["id"] != plan_id]
    if len(data["plans"]) < original_len:
        save_plans(data)
        print(f"  🗑️  Plan #{plan_id} removed")
    else:
        print(f"  ❌ Plan #{plan_id} not found")


def handle_plan_command(parts):
    """Handle plan subcommands"""
    if len(parts) <= 1 or parts[1] == "list":
        display_plans()
    elif parts[1] == "add":
        plan_add_interactive()
    elif parts[1] == "waiting":
        display_plans(filter_status="WAITING")
    elif parts[1] == "active":
        display_plans(filter_status="ACTIVE")
    elif parts[1] in ("done", "filled") and len(parts) >= 3:
        try:
            plan_id = int(parts[2])
            plan_update_status(plan_id, "FILLED")
        except ValueError:
            print("  Usage: plan done <ID>")
    elif parts[1] == "close" and len(parts) >= 3:
        try:
            plan_id = int(parts[2])
            plan_update_status(plan_id, "CLOSED")
        except ValueError:
            print("  Usage: plan close <ID>")
    elif parts[1] == "cancel" and len(parts) >= 3:
        try:
            plan_id = int(parts[2])
            plan_update_status(plan_id, "CANCELLED")
        except ValueError:
            print("  Usage: plan cancel <ID>")
    elif parts[1] == "rm" and len(parts) >= 3:
        try:
            plan_id = int(parts[2])
            plan_remove(plan_id)
        except ValueError:
            print("  Usage: plan rm <ID>")
    else:
        print("""
  PLAN COMMANDS:
  ─────────────────────────────────────────────────────────
  plan              Show all trade plans
  plan add          Add a new plan (interactive)
  plan waiting      Show only waiting plans
  plan active       Show only active plans
  plan done <ID>    Mark plan as filled/executed
  plan close <ID>   Mark plan as closed (profit taken)
  plan cancel <ID>  Cancel a plan
  plan rm <ID>      Remove a plan
  ─────────────────────────────────────────────────────────
        """)


# ═══════════════════════════════════════════════════════════════
# MY PORTFOLIO SCANNER
# ═══════════════════════════════════════════════════════════════

def display_my_portfolio(sell_mode=False):
    """Scan user's own holdings with buy + sell scores and covered call recs"""
    data = load_plans()
    portfolio = data.get("portfolio", {})

    if not portfolio:
        print("\n  ❌ No portfolio found. Add holdings to data/trade_plans.json")
        print("  💡 Or run: plan add\n")
        return

    symbols = list(portfolio.keys())

    print(f"""
╔═══════════════════════════════════════════════════════════════════════════════════╗
║  💼 MY PORTFOLIO SCAN                                                            ║
╠═══════════════════════════════════════════════════════════════════════════════════╣""")

    results = []
    for sym in symbols:
        sys.stdout.write(f"\r  💼 Scanning {sym}...          ")
        sys.stdout.flush()

        shares = portfolio[sym]["shares"]
        contracts_available = shares // 100

        # Get both scores
        buy_result = calculate_score(sym)
        sell_result = sell_options_score(sym)

        if buy_result and sell_result:
            results.append({
                "symbol": sym,
                "shares": shares,
                "contracts": contracts_available,
                "buy": buy_result,
                "sell": sell_result,
            })

    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()

    for r in results:
        sym = r["symbol"]
        shares = r["shares"]
        contracts = r["contracts"]
        buy = r["buy"]
        sell = r["sell"]

        buy_signal, _ = get_signal(buy["total_score"])
        sell_signal, _ = get_sell_signal(sell["total_score"])
        strat = sell["strategy"]

        print(f"""║                                                                                   ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║  {sym} — {shares} shares ({contracts} contract{'s' if contracts > 1 else ''} available)
║  {buy['name'][:60]}
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║
║  💰 Price: ${buy['price']:.2f}  ({'+' if buy['change_pct'] >= 0 else ''}{buy['change_pct']:.2f}% today)
║  📅 5-Day: {'+' if buy['five_day_change'] >= 0 else ''}{buy['five_day_change']:.2f}%
║
║  ┌─────────────────────────┐  ┌──────────────────────────┐
║  │ BUY SCORE: {buy['total_score']:>+4d}/100      │  │ SELL SCORE: {sell['total_score']:>3d}/100       │
║  │ {buy_signal:<23}│  │ {sell_signal:<24}│
║  └─────────────────────────┘  └──────────────────────────┘
║
║  📊 Indicators:
║     RSI: {buy['indicators']['rsi']:.1f}  │  Stoch: {buy['indicators']['stoch_k']:.1f}%  │  IV Rank: {sell['indicators']['iv_rank_pct']:.0f}%  │  ADX: {sell['indicators']['adx']:.1f}
║
║  📞 COVERED CALL RECOMMENDATION:
║  ─────────────────────────────────────────
║     Strategy:   {strat['name']}
║     Sell above: ${sell['resistance']:.2f} (resistance)
║     Support:    ${sell['support']:.2f}
║     Direction:  {'BULLISH ↗️' if sell['directional_lean'] > 10 else 'BEARISH ↘️' if sell['directional_lean'] < -10 else 'NEUTRAL ↔️'} ({sell['directional_lean']:+.0f})""")

        # Specific covered call strike suggestion
        price = buy['price']
        resistance = sell['resistance']
        # Suggest strike ~5% OTM or above resistance
        suggested_strike = max(resistance, price * 1.05)
        # Round to nearest $5 for cleaner strikes
        if price > 100:
            suggested_strike = round(suggested_strike / 5) * 5
        else:
            suggested_strike = round(suggested_strike)

        print(f"""║     💡 Suggested strike: ${suggested_strike:.0f} ({((suggested_strike - price) / price * 100):.1f}% OTM)
║     📝 Contracts to sell: {contracts} (covers all {shares} shares)""")

        # Timing advice
        if buy['indicators']['stoch_k'] < 20:
            print(f"║     ⏳ WAIT — Stoch oversold ({buy['indicators']['stoch_k']:.0f}%), let it bounce first")
        elif buy['indicators']['stoch_k'] > 80:
            print(f"║     ✅ NOW — Stoch overbought ({buy['indicators']['stoch_k']:.0f}%), ideal time to sell calls")
        elif buy['indicators']['stoch_k'] > 60:
            print(f"║     🟡 SOON — Stoch rising ({buy['indicators']['stoch_k']:.0f}%), approaching sell zone")
        else:
            print(f"║     ⏳ WAIT — Stoch neutral ({buy['indicators']['stoch_k']:.0f}%), wait for >80")

        # Score-based advice
        if sell['total_score'] >= 60 and buy['indicators']['stoch_k'] > 70:
            print(f"║     🎯 READY TO SELL! High sell score + Stoch overbought")
        elif sell['total_score'] >= 60:
            print(f"║     🎯 Good sell conditions — wait for Stoch trigger")

    # Plans reminder
    waiting_plans = [p for p in data.get("plans", []) if p["status"] == "WAITING"]
    my_plans = [p for p in waiting_plans if p["symbol"] in [r["symbol"] for r in results]]

    if my_plans:
        print(f"""║                                                                                   ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║  📋 PENDING PLANS:                                                                ║""")
        for p in my_plans:
            strike_str = f"${p['strike']}" if isinstance(p.get('strike'), (int, float)) else str(p.get('strike', ''))
            print(f"║     #{p['id']} {p['symbol']} — {p['action']} @ {strike_str} | Trigger: {p['trigger'][:40]}")

    print(f"""║                                                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
""")



def run_day_trade_watchlist(symbols, title, json_mode=False):
    """Run day trade watchlist scan, optionally saving JSON"""
    results = display_day_trade_watchlist(symbols, title)
    if json_mode and results:
        save_json(results, "dt_latest.json", f"day_trade_{title.lower().replace(' ', '_')}")
    return results


def run_day_trade_single(symbol, json_mode=False):
    """Run single day trade scan, optionally saving JSON"""
    result = day_trade_score(symbol)
    display_day_trade(result)
    if json_mode and result:
        save_json(result, f"dt_{symbol.lower()}.json", f"day_trade_single_{symbol}")
    return result


def run_single_scan(symbol, json_mode=False):
    """Run single stock scan, optionally saving JSON"""
    result = calculate_score(symbol)
    display_single(result)
    if json_mode and result:
        save_json(result, f"scan_{symbol.lower()}.json", f"single_{symbol}")
    return result


def run_compare(sym1, sym2, json_mode=False):
    """Run comparison, optionally saving JSON"""
    compare_symbols(sym1, sym2)
    if json_mode:
        r1 = calculate_score(sym1)
        r2 = calculate_score(sym2)
        if r1 and r2:
            data = {"symbol_1": r1, "symbol_2": r2}
            save_json(data, "compare_latest.json", f"compare_{sym1}_vs_{sym2}")


def parse_args():
    """Parse CLI arguments, handling --json flag alongside positional commands"""
    # Check for --json flag manually since we mix positional commands with flags
    json_mode = "--json" in sys.argv
    # Remove --json from argv for simpler positional parsing
    args = [a for a in sys.argv[1:] if a != "--json"]
    return args, json_mode


def main():
    """Main CLI loop"""
    print_banner()

    # Handle command-line arguments
    args, json_mode = parse_args()

    if args:
        cmd = args[0].lower()
        if cmd == "tech":
            run_watchlist_scan(WATCHLIST_TECH, "TOP TECH STOCKS", json_mode)
        elif cmd == "etf":
            run_watchlist_scan(WATCHLIST_ETF, "TOP ETFs & INDEXES", json_mode)
        elif cmd == "all":
            run_watchlist_scan(WATCHLIST_ETF + WATCHLIST_TECH, "ALL WATCHLIST", json_mode)
        elif cmd == "vs" and len(args) >= 3:
            run_compare(args[1].upper(), args[2].upper(), json_mode)
        elif cmd == "dt":
            if len(args) >= 2:
                arg = args[1].lower()
                if arg == "tech":
                    run_day_trade_watchlist(WATCHLIST_TECH, "TECH STOCKS", json_mode)
                elif arg == "etf":
                    run_day_trade_watchlist(WATCHLIST_ETF, "ETFs & INDEXES", json_mode)
                elif arg == "all":
                    run_day_trade_watchlist(WATCHLIST_ETF + WATCHLIST_TECH, "ALL WATCHLIST", json_mode)
                else:
                    run_day_trade_single(arg.upper(), json_mode)
            else:
                run_day_trade_watchlist(WATCHLIST_TECH, "TECH STOCKS (default)", json_mode)
        elif cmd == "sell":
            if len(args) >= 2:
                arg = args[1].lower()
                if arg == "tech":
                    run_sell_watchlist(WATCHLIST_TECH, "TECH STOCKS", json_mode)
                elif arg == "etf":
                    run_sell_watchlist(WATCHLIST_ETF, "ETFs & INDEXES", json_mode)
                elif arg == "all":
                    run_sell_watchlist(WATCHLIST_ETF + WATCHLIST_TECH, "ALL WATCHLIST", json_mode)
                else:
                    run_sell_single(arg.upper(), json_mode)
            else:
                run_sell_watchlist(WATCHLIST_TECH, "TECH STOCKS (default)", json_mode)
        elif cmd == "plan":
            handle_plan_command(args)
        elif cmd == "my":
            display_my_portfolio()
        elif cmd in ("help", "-h", "--help"):
            print_help()
        else:
            run_single_scan(cmd.upper(), json_mode)
        return

    # Interactive mode
    print_help()

    while True:
        try:
            cmd = input("  optix> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  👋 Happy trading! Remember: manage your risk! 🎲\n")
            break

        if not cmd:
            continue
        elif cmd in ("quit", "exit", "q"):
            print("\n  👋 Happy trading! Remember: manage your risk! 🎲\n")
            break
        elif cmd == "help":
            print_help()
        elif cmd == "tech":
            display_watchlist(WATCHLIST_TECH, "TOP TECH STOCKS")
        elif cmd == "etf":
            display_watchlist(WATCHLIST_ETF, "TOP ETFs & INDEXES")
        elif cmd == "all":
            display_watchlist(WATCHLIST_ETF + WATCHLIST_TECH, "ALL WATCHLIST")
        elif cmd.startswith("vs "):
            parts = cmd.split()
            if len(parts) >= 3:
                compare_symbols(parts[1].upper(), parts[2].upper())
            else:
                print("  Usage: vs SYMBOL1 SYMBOL2")
        elif cmd.startswith("dt"):
            parts = cmd.split()
            if len(parts) >= 2:
                arg = parts[1].lower()
                if arg == "tech":
                    display_day_trade_watchlist(WATCHLIST_TECH, "TECH STOCKS")
                elif arg == "etf":
                    display_day_trade_watchlist(WATCHLIST_ETF, "ETFs & INDEXES")
                elif arg == "all":
                    display_day_trade_watchlist(WATCHLIST_ETF + WATCHLIST_TECH, "ALL WATCHLIST")
                else:
                    print(f"\n  ⚡ Day trade scanning {arg.upper()}...")
                    result = day_trade_score(arg.upper())
                    display_day_trade(result)
            else:
                display_day_trade_watchlist(WATCHLIST_TECH, "TECH STOCKS (default)")
        elif cmd.startswith("sell"):
            parts = cmd.split()
            if len(parts) >= 2:
                arg = parts[1].lower()
                if arg == "tech":
                    display_sell_watchlist(WATCHLIST_TECH, "TECH STOCKS")
                elif arg == "etf":
                    display_sell_watchlist(WATCHLIST_ETF, "ETFs & INDEXES")
                elif arg == "all":
                    display_sell_watchlist(WATCHLIST_ETF + WATCHLIST_TECH, "ALL WATCHLIST")
                else:
                    print(f"\n  💜 Sell premium scanning {arg.upper()}...")
                    result = sell_options_score(arg.upper())
                    display_sell_single(result)
            else:
                display_sell_watchlist(WATCHLIST_TECH, "TECH STOCKS (default)")
        elif cmd.startswith("plan"):
            parts = cmd.split()
            handle_plan_command(parts)
        elif cmd == "my":
            display_my_portfolio()
        else:
            symbol = cmd.upper()
            print(f"\n  ⏳ Analyzing {symbol}...")
            result = calculate_score(symbol)
            display_single(result)


if __name__ == "__main__":
    main()
