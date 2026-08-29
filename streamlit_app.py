"""
OPTIX Web — Options Trading Intelligence eXplorer (Streamlit UI)

A web front-end for the OPTIX scoring engine. It reuses the scoring
functions from optix.py directly (no reimplementation):

  - calculate_score(symbol)     -> directional buy-call / buy-put score
  - sell_options_score(symbol)  -> premium-selling (theta) score

Run locally:
    streamlit run streamlit_app.py
"""

import streamlit as st
import pandas as pd

# Reuse the existing OPTIX scoring engine. These are pure functions that
# fetch data and return dicts (no printing), so they drop straight into a UI.
from optix import (
    calculate_score,
    get_signal,
    sell_options_score,
    get_sell_signal,
    WATCHLIST_TECH,
    WATCHLIST_ETF,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="OPTIX — Options Intelligence",
    page_icon="📊",
    layout="wide",
)

ALL_SYMBOLS = sorted(set(WATCHLIST_TECH + WATCHLIST_ETF))


# ---------------------------------------------------------------------------
# Cached wrappers (avoid refetching Yahoo data on every rerun)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def get_buy_score(symbol: str):
    return calculate_score(symbol)


@st.cache_data(ttl=300, show_spinner=False)
def get_sell_score(symbol: str):
    return sell_options_score(symbol)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def score_color(score: int, lo: int, hi: int) -> str:
    """Map a score to a red→green color for display."""
    if hi == lo:
        pct = 0.5
    else:
        pct = (score - lo) / (hi - lo)
    pct = max(0.0, min(1.0, pct))
    r = int(220 * (1 - pct))
    g = int(180 * pct)
    return f"rgb({r},{g},60)"


def render_buy(result: dict):
    signal, _ = get_signal(result["total_score"])
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        st.subheader(f"{result['symbol']} — {result['name'][:40]}")
        st.markdown(f"### {signal}")
    with c2:
        st.metric("Price", f"${result['price']:.2f}", f"{result['change_pct']:+.2f}%")
    with c3:
        st.metric("OPTIX Score", f"{result['total_score']:+d}/100",
                  f"5d {result['five_day_change']:+.2f}%")

    # Score gauge (-100..+100)
    st.progress((result["total_score"] + 100) / 200)

    st.markdown("#### Score breakdown")
    scores = result["scores"]
    df = pd.DataFrame(
        {"Component": list(scores.keys()), "Score": list(scores.values())}
    )
    st.bar_chart(df.set_index("Component"))

    ind = result["indicators"]
    st.markdown("#### Indicators")
    ic = st.columns(4)
    ic[0].metric("RSI", f"{ind['rsi']:.1f}")
    ic[1].metric("Stoch %K", f"{ind['stoch_k']:.1f}")
    ic[2].metric("MACD", f"{ind['macd']:.3f}")
    ic[3].metric("BB pos", f"{ind['bb_position']:.2f}")


def render_sell(result: dict):
    signal, _ = get_sell_signal(result["total_score"])
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        st.subheader(f"{result['symbol']} — {result['name'][:40]}")
        st.markdown(f"### {signal}")
    with c2:
        st.metric("Price", f"${result['price']:.2f}", f"{result['change_pct']:+.2f}%")
    with c3:
        st.metric("Sell Score", f"{result['total_score']}/100")

    st.progress(result["total_score"] / 100)

    strat = result["strategy"]
    st.info(f"**Strategy: {strat['name']}**\n\n{strat['desc']}")

    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown("#### Score breakdown")
        scores = result["scores"]
        df = pd.DataFrame(
            {"Component": list(scores.keys()), "Score": list(scores.values())}
        )
        st.bar_chart(df.set_index("Component"))
    with sc2:
        st.markdown("#### Indicators & levels")
        ind = result["indicators"]
        st.metric("IV Rank", f"{ind['iv_rank_pct']:.0f}%")
        st.metric("ADX", f"{ind['adx']:.1f}")
        st.metric("RSI", f"{ind['rsi']:.1f}")
        st.write(f"Support: **${result['support']:.2f}**  |  "
                 f"Resistance: **${result['resistance']:.2f}**")


def scan_table(symbols, mode: str) -> pd.DataFrame:
    rows = []
    prog = st.progress(0.0, text="Scanning…")
    for i, sym in enumerate(symbols):
        try:
            if mode == "buy":
                r = get_buy_score(sym)
                if r:
                    sig, _ = get_signal(r["total_score"])
                    rows.append({
                        "Symbol": sym,
                        "Price": round(r["price"], 2),
                        "Score": r["total_score"],
                        "Signal": sig,
                        "5d %": round(r["five_day_change"], 2),
                    })
            else:
                r = get_sell_score(sym)
                if r:
                    sig, _ = get_sell_signal(r["total_score"])
                    rows.append({
                        "Symbol": sym,
                        "Price": round(r["price"], 2),
                        "Score": r["total_score"],
                        "Signal": sig,
                        "Strategy": r["strategy"]["name"],
                    })
        except Exception as e:
            rows.append({"Symbol": sym, "Signal": f"error: {e}"})
        prog.progress((i + 1) / len(symbols), text=f"Scanning… {sym}")
    prog.empty()
    df = pd.DataFrame(rows)
    if not df.empty and "Score" in df.columns:
        # Best opportunities first for both modes (highest score on top).
        df = df.sort_values("Score", ascending=False)
    return df


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("📊 OPTIX")
st.sidebar.caption("Options Trading Intelligence eXplorer")

mode = st.sidebar.radio(
    "Scoring mode",
    ["Buy (directional)", "Sell (premium / theta)"],
)
is_buy = mode.startswith("Buy")

view = st.sidebar.radio("View", ["Single symbol", "Scan watchlist"])

st.sidebar.markdown("---")
st.sidebar.caption(
    "Data: Yahoo Finance (delayed). For research/education only — "
    "not financial advice."
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
st.title("📊 OPTIX — Options Intelligence")

if view == "Single symbol":
    default = "NVDA"
    col_a, col_b = st.columns([3, 1])
    with col_a:
        symbol = st.text_input("Ticker symbol", value=default).strip().upper()
    with col_b:
        st.write("")
        st.write("")
        go = st.button("Score", type="primary", use_container_width=True)

    if symbol and (go or symbol):
        with st.spinner(f"Scoring {symbol}…"):
            if is_buy:
                result = get_buy_score(symbol)
            else:
                result = get_sell_score(symbol)
        if not result:
            st.error(f"Could not fetch data for '{symbol}'. "
                     "Check the ticker or try again (Yahoo may be rate-limiting).")
        else:
            if is_buy:
                render_buy(result)
            else:
                render_sell(result)

else:  # Scan watchlist
    universe = st.selectbox(
        "Watchlist",
        ["Tech (10)", "ETF (10)", "All (20)"],
    )
    symbols = {
        "Tech (10)": WATCHLIST_TECH,
        "ETF (10)": WATCHLIST_ETF,
        "All (20)": ALL_SYMBOLS,
    }[universe]

    if st.button("Run scan", type="primary"):
        df = scan_table(symbols, "buy" if is_buy else "sell")
        if df.empty:
            st.warning("No results (data fetch may have failed).")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download CSV",
                df.to_csv(index=False).encode("utf-8"),
                file_name=f"optix_{'buy' if is_buy else 'sell'}_scan.csv",
                mime="text/csv",
            )
