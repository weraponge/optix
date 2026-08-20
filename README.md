# OPTIX — Options Trading Intelligence eXplorer

A CLI-based options scoring system for scanning buy/sell opportunities and managing covered call positions.

## Quick Start

```bash
cd ~/option
python3 optix.py my        # Scan your portfolio (SPCX + AMZN)
python3 optix.py plan      # View trade plans
```

## Commands

### Buy Options (Directional)

| Command | Description |
|---------|-------------|
| `python3 optix.py AAPL` | Score a single stock |
| `python3 optix.py tech` | Scan top 10 tech stocks |
| `python3 optix.py etf` | Scan top 10 ETFs |
| `python3 optix.py all` | Scan all 20 symbols |
| `python3 optix.py vs NVDA AMD` | Compare two stocks |

### Sell Premium (Theta Gang)

| Command | Description |
|---------|-------------|
| `python3 optix.py sell AAPL` | Sell premium score for one stock |
| `python3 optix.py sell tech` | Scan top 10 tech |
| `python3 optix.py sell etf` | Scan top 10 ETFs |
| `python3 optix.py sell all` | Scan all 20 symbols |

### Day Trading

| Command | Description |
|---------|-------------|
| `python3 optix.py dt NVDA` | Day trade scanner (intraday) |
| `python3 optix.py dt tech` | Day trade scan top 10 tech |

### My Portfolio

| Command | Description |
|---------|-------------|
| `python3 optix.py my` | Scan your holdings with covered call recs |

### Trade Plans

| Command | Description |
|---------|-------------|
| `python3 optix.py plan` | Show all plans |
| `python3 optix.py plan add` | Add new plan (interactive) |
| `python3 optix.py plan done 1` | Mark plan #1 as filled |
| `python3 optix.py plan close 1` | Mark plan #1 as closed (profit) |
| `python3 optix.py plan cancel 1` | Cancel plan #1 |
| `python3 optix.py plan rm 1` | Remove plan #1 |

### Options

| Flag | Description |
|------|-------------|
| `--json` | Save scan results to `data/` as JSON |

## Score Guides

### Buy Options Score (-100 to +100)

| Score | Signal |
|-------|--------|
| +30 to +100 | 🟢 STRONG BUY CALL |
| +15 to +29 | 🟢 BUY CALL |
| +5 to +14 | 🟡 LEAN BULLISH |
| -4 to +4 | ⚪ NEUTRAL / STAY OUT |
| -5 to -14 | 🟡 LEAN BEARISH |
| -15 to -29 | 🔴 BUY PUT |
| -30 to -100 | 🔴 STRONG BUY PUT |

**Indicators used:** SMA crossover, RSI, Stochastic, MACD, Bollinger Bands, Volume, Price patterns

### Sell Premium Score (0 to 100)

| Score | Signal |
|-------|--------|
| 75-100 | 🟣 STRONG SELL PREMIUM |
| 60-74 | 🟣 SELL PREMIUM |
| 45-59 | 🟡 LEAN SELL (reduce size) |
| 30-44 | ⚪ MARGINAL |
| 0-29 | ❌ DON'T SELL (trending/low IV) |

**Indicators used:** IV Rank, ADX (trend strength), Mean Reversion, Range compression, Theta opportunity, Liquidity, Support/Resistance

### Strategy Recommendations (Sell Premium)

| Condition | Strategy |
|-----------|----------|
| Neutral + High IV | 🦅 Iron Condor |
| Neutral + Normal IV | 🦎 Short Strangle |
| Bullish + Strong | 💰 Cash-Secured Put |
| Bullish + Mild | 💵 Bull Put Spread |
| Bearish + Strong | 📞 Covered Call |
| Bearish + Mild | 🐻 Bear Call Spread |

## My Portfolio

Current holdings (edit in `data/trade_plans.json`):

| Symbol | Shares | Contracts | Strategy |
|--------|--------|-----------|----------|
| SPCX | 100 | 1 | Sell covered calls |
| AMZN | 1000 | 10 | Sell covered calls |

## Workflow

### Daily Routine

```bash
python3 optix.py my            # Check portfolio + covered call timing
python3 optix.py plan          # Review pending plans
```

### When Looking for New Trades

```bash
python3 optix.py tech          # Buy options scan
python3 optix.py sell tech     # Sell premium scan
```

### Covered Call Timing (My Strategy)

1. Run `python3 optix.py my`
2. Check Stochastic %K — wait for **2h Stoch > 80** (overbought)
3. When triggered → sell calls above resistance
4. Target DTE: 7-14 days (SPCX), 14-30 days (AMZN)
5. Exit at 50% profit or let expire

### File Structure

```
~/option/
├── optix.py              # Main script
├── README.md             # This file
└── data/
    ├── trade_plans.json  # Portfolio + trade plans
    ├── *_latest.json     # Latest scan results
    └── history/          # Historical scan data
```

## Watchlists

**Tech:** NVDA, AAPL, TSLA, MSFT, AMZN, META, GOOGL, AVGO, AMD, CRM
**ETF:** SPY, QQQ, IWM, SMH, XLK, TLT, HYG, EEM, DIA, ARKK

## Data Source

All market data fetched from Yahoo Finance (free, no API key needed).

---

## Developer Guide

### Requirements

- Python 3.10+
- No external packages — uses only stdlib (`json`, `math`, `urllib`, `datetime`, `statistics`, `sys`, `os`, `argparse`)
- Data source: Yahoo Finance v8 chart API (no API key)

### Code Architecture

`optix.py` is a single-file script (~2000 lines) organized into sections:

```
┌─────────────────────────────────────────────────────┐
│  CONFIGURATION         Watchlists, weights, headers │
├─────────────────────────────────────────────────────┤
│  DATA FETCHING         fetch_chart(), fetch_options()│
├─────────────────────────────────────────────────────┤
│  TECHNICAL INDICATORS  calc_sma, calc_ema, calc_rsi,│
│                        calc_stochastic, calc_macd,  │
│                        calc_bollinger              │
├─────────────────────────────────────────────────────┤
│  BUY SCORING ENGINE    score_trend, score_momentum, │
│                        score_volume, score_volatility│
│                        score_macd, score_pattern    │
│                        → calculate_score()          │
├─────────────────────────────────────────────────────┤
│  BUY DISPLAY           display_single,              │
│                        display_watchlist            │
├─────────────────────────────────────────────────────┤
│  DAY TRADE ENGINE      day_trade_score() using VWAP,│
│                        EMA9/21, intraday RSI       │
├─────────────────────────────────────────────────────┤
│  SELL PREMIUM ENGINE   sell_options_score() using   │
│                        IV rank, ADX, mean reversion,│
│                        theta opp, liquidity, S/R   │
│                        → determine_sell_strategy()  │
├─────────────────────────────────────────────────────┤
│  SELL DISPLAY          display_sell_single,         │
│                        display_sell_watchlist       │
├─────────────────────────────────────────────────────┤
│  JSON OUTPUT           save_json(), ensure_data_dirs│
├─────────────────────────────────────────────────────┤
│  TRADE PLAN MANAGER    load/save_plans, display,    │
│                        plan_add_interactive,        │
│                        handle_plan_command          │
├─────────────────────────────────────────────────────┤
│  MY PORTFOLIO          display_my_portfolio()       │
├─────────────────────────────────────────────────────┤
│  CLI / MAIN            parse_args, main() with CLI  │
│                        args + interactive mode      │
└─────────────────────────────────────────────────────┘
```

### Scoring Logic

#### Buy Score (-100 to +100)

Sum of 6 sub-scores:

| Component | Max Points | Logic |
|-----------|-----------|-------|
| `score_trend` | ±25 | SMA20 vs SMA50 crossover + price position |
| `score_momentum` | ±20 | RSI zones + Stochastic K/D cross |
| `score_volume` | ±15 | Recent 5d volume vs 20d average |
| `score_volatility` | ±15 | Bollinger Band position (lower=bullish) |
| `score_macd` | ±15 | MACD vs signal line + histogram |
| `score_pattern` | ±10 | 5-day streak + higher lows / lower highs |

Data: Daily candles, 3-month lookback.

#### Sell Premium Score (0 to 100)

Raw score (-100 to +100) normalized to 0-100 via `(raw + 100) / 2`:

| Component | Max Points | Logic |
|-----------|-----------|-------|
| `score_sell_iv_rank` | ±25 | HV percentile over 60-day window |
| `score_sell_mean_reversion` | ±20 | RSI + BB extremes (stretched = good) |
| `score_sell_range_bound` | ±20 | ADX < 20 = no trend + range compression |
| `score_sell_theta_opportunity` | ±15 | Small avg daily moves = theta wins |
| `score_sell_liquidity` | ±10 | Volume proxy + price sweet spot |
| `score_sell_support_resistance` | ±10 | Near tested S/R levels |

Data: Daily candles, 6-month lookback. IV rank estimated from realized volatility (no options chain needed).

Strategy selection uses `directional_lean` (trend + momentum from buy engine, range -45 to +45) combined with ADX and IV rank.

#### Day Trade Score (-100 to +100)

| Component | Max Points | Logic |
|-----------|-----------|-------|
| VWAP position | ±25 | Above/below VWAP |
| EMA crossover | ±20 | EMA9 vs EMA21 + price relative |
| RSI (5m) | ±15 | Overbought/oversold on intraday |
| Volume spike | ±15 | Current vs average volume ratio |
| Momentum | ±15 | Last 5 candles % change |
| Range position | ±10 | Near HOD vs LOD |

Data: 5-minute candles, 1-day range.

### Data Schemas

#### trade_plans.json

```json
{
  "portfolio": {
    "SPCX": {"shares": 100},
    "AMZN": {"shares": 1000}
  },
  "plans": [
    {
      "id": 1,
      "created": "2026-08-21T03:48:00+07:00",
      "status": "WAITING|ACTIVE|FILLED|CLOSED|CANCELLED|OPTIONAL",
      "symbol": "SPCX",
      "action": "SELL CALL|SELL PUT|BUY CALL|BUY PUT|SELL COVERED CALL|IRON CONDOR",
      "strike": 145,
      "contracts": 1,
      "trigger": "2h Stochastic %K > 80",
      "confirmation": "Price bounced to $138-142",
      "dte_target": "7-14 days",
      "exit_plan": "Close at 50% profit",
      "notes": "free text",
      "context": {}
    }
  ]
}
```

#### Yahoo Finance API

```
Chart:   https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?interval={1d|5m}&range={3mo|6mo|1d}
Options: https://query1.finance.yahoo.com/v7/finance/options/{SYMBOL}
```

No auth required. Rate limits apply (aggressive scanning may get 429s). User-Agent header required.

### Known Limitations

- **IV Rank is estimated** from historical volatility percentile (no real options chain IV). Good proxy but not exact.
- **SPCX has limited data** (~48 days). Newer stocks may have sparse history.
- **Yahoo Finance can be unreliable** — sometimes returns null data or 429 errors on rapid scanning.
- **2h Stochastic not available here** — the `my` command shows daily Stoch. The 2h trigger should be checked on your broker's chart (TradingView, ToS, etc).
- **No real-time data** — Yahoo provides delayed/EOD quotes. Intraday data (`dt` mode) only works during market hours.
- **Single-threaded** — watchlist scans are sequential. Could parallelize with threading.

### Future Ideas / TODOs

- [ ] Add `my` command with `--watch` flag for continuous refresh
- [ ] Telegram/Discord bot alert when Stoch > 80 on portfolio stocks
- [ ] Track P&L history (premium collected, total return)
- [ ] Add earnings date check (don't sell calls through earnings)
- [ ] Parallelize API calls for faster watchlist scans
- [ ] Add actual options chain data (bid/ask, OI, Greeks) for strike selection
- [ ] Cron job to auto-save daily scans for historical analysis
- [ ] Position sizing calculator (% of portfolio risk)

