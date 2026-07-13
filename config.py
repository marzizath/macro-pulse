"""
Macro Pulse - Configuration

Asset universe, thresholds, news sources, and the correlation knowledge base.
Edit tickers/thresholds here without touching logic in the other files.
"""

# --- Asset universe (Yahoo Finance tickers, used by price_data.py) ---
# Verify these still resolve on Yahoo Finance before your first real run -
# ticker symbols occasionally get renamed or deprecated.
ASSETS = {
    "Gold":            {"ticker": "GC=F",     "category": "precious_metal"},
    "Silver":          {"ticker": "SI=F",     "category": "precious_metal"},
    "WTI Crude":       {"ticker": "CL=F",     "category": "energy"},
    "Brent Crude":     {"ticker": "BZ=F",     "category": "energy"},
    "US Dollar Index": {"ticker": "DX-Y.NYB", "category": "currency"},
    "US 10Y Yield":    {"ticker": "^TNX",     "category": "rates", "divide_by": 10},
    "VIX":             {"ticker": "^VIX",     "category": "volatility"},
    "AUD/USD":         {"ticker": "AUDUSD=X", "category": "currency"},
}

# No single reliable ASX Materials sector index ticker on Yahoo, so we proxy it
# with an equal-weighted basket of the largest ASX materials/mining names.
ASX_MATERIALS_BASKET = {
    "BHP":           "BHP.AX",
    "Rio Tinto":     "RIO.AX",
    "Fortescue":     "FMG.AX",
    "Northern Star": "NST.AX",
}

# --- Anomaly detection ---
ROLLING_WINDOW_DAYS = 20   # trailing window used to compute "normal" daily move size
ZSCORE_THRESHOLD = 1.5     # flag a move if it's this many std devs from its own recent norm
ASX_BASKET_FLAT_THRESHOLD = 2.0  # % move threshold for the basket proxy (no per-asset zscore)

# --- News sources (all free, no API key required) ---
# Sourced from investing.com/webmaster-tools/rss, oilprice.com, and goldseek.com.
RSS_FEEDS = {
    "Commodities & Futures":       "https://www.investing.com/rss/news_11.rss",
    "Economy":                     "https://www.investing.com/rss/news_14.rss",
    "Economic Indicators":         "https://www.investing.com/rss/news_95.rss",
    "Forex":                       "https://www.investing.com/rss/news_1.rss",
    "Metals Analysis":             "https://www.investing.com/rss/commodities_Metals.rss",
    "Energy Analysis":             "https://www.investing.com/rss/commodities_Energy.rss",
    "Central Bank Speeches":       "https://www.investing.com/rss/central_banks.rss",
    "Breaking News":               "https://www.investing.com/rss/news_462.rss",
    "Oil & Energy (OilPrice.com)": "https://oilprice.com/rss/main",
    "Precious Metals (GoldSeek)":  "https://news.goldseek.com/newsRSS.xml",
}
MAX_HEADLINES_PER_FEED = 15
NEWS_LOOKBACK_HOURS = 30   # a bit over 24h to cover weekend/timezone gaps

# --- Correlation knowledge base ---
# This grounds the AI synthesis step so it EXPLAINS observed moves using real,
# known relationships instead of inventing plausible-sounding causal stories.
# Keep this factual and mechanism-based. It is context, not a prediction engine.
CORRELATION_MAP = """
KNOWN MACRO RELATIONSHIPS (use these to explain observed moves where they
genuinely apply - do not invent new causal links beyond this list):

1. Strait of Hormuz / Middle East tension -> ~20% of global seaborne oil passes
   through Hormuz -> supply-risk premium on Brent/WTI -> shipping & insurance
   costs rise -> inflation expectations tick up -> central banks lean hawkish
   -> USD often strengthens (safe-haven flows) even as oil-importing economies
   get squeezed -> gold often rises too (inflation hedge + safe haven) ->
   airline/transport stocks often fall (fuel cost exposure).

2. Gold vs Silver: gold is close to pure store-of-value/safe-haven demand.
   Silver is roughly half industrial demand (electronics, solar, EVs), so it
   also tracks manufacturing PMI and industrial data. A rising gold/silver
   ratio suggests a "fear" move; a falling ratio suggests a "growth /
   industrial demand" move.

3. USD Index (DXY) moves inversely to most USD-priced commodities (gold,
   silver, oil, copper) most of the time, since a stronger dollar makes them
   costlier for foreign buyers - independent of anything happening to the
   commodity itself.

4. China demand data (PMI, imports) feeds directly into iron ore/copper/LNG
   demand, which feeds into AUD strength since AUD is a commodity currency.
   Weak China data tends to pressure AUD and ASX materials names even without
   any local Australian news.

5. Fed / RBA rate decisions -> currency strength shifts -> commodity prices in
   USD -> flow-through to AUD-priced local equivalents.

6. Australian EOFY (30 June) drives tax-loss selling and dividend timing on
   ASX names -> can cause volatility in ASX materials/mining stocks in a
   window that doesn't match US/December year-end effects. Different
   mechanism, different calendar - don't conflate the two.

7. VIX (volatility index) spiking usually accompanies "risk-off" moves: gold
   up, equities down, USD often up, AUD (a risk-sensitive currency) often
   down.

8. A rising US 10Y yield without matching inflation data often signals
   rate-hike expectations or growth optimism -> can pressure gold (higher
   real yields raise the opportunity cost of holding non-yielding gold) ->
   can support USD.
"""
