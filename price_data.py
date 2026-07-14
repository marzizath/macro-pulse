"""
Fetches daily price data for the tracked asset basket and flags anomalies
using a rolling z-score of daily returns (i.e. "is today's move unusually
large compared to this asset's own recent behaviour?").
"""
import time
import yfinance as yf
import pandas as pd
from config import (
    ASSETS,
    ASX_MATERIALS_BASKET,
    ROLLING_WINDOW_DAYS,
    ZSCORE_THRESHOLD,
    ASX_BASKET_FLAT_THRESHOLD,
)

FETCH_RETRIES = 3
FETCH_RETRY_DELAY_SECONDS = 2  # Yahoo occasionally throttles datacenter IPs
# (e.g. GitHub Actions runners) - a short retry clears most transient failures.


def _fetch_close_history(ticker: str) -> pd.Series:
    last_error = None
    for attempt in range(FETCH_RETRIES):
        try:
            return yf.Ticker(ticker).history(period="3mo")["Close"]
        except Exception as e:
            last_error = e
            if attempt < FETCH_RETRIES - 1:
                time.sleep(FETCH_RETRY_DELAY_SECONDS)
    raise last_error


def _pct_change_and_zscore(hist: pd.Series):
    """Return (latest % change, z-score of that change vs its recent rolling window).

    Both returned as native Python floats, not numpy scalars - numpy types
    (and anything compared against them, like the anomaly bool below) aren't
    JSON-serializable and will blow up synthesize_digest()'s json.dumps call.
    """
    returns = hist.pct_change().dropna()
    if len(returns) < ROLLING_WINDOW_DAYS + 1:
        # Not enough history yet - report the move but skip the z-score.
        return round(float(returns.iloc[-1]) * 100, 2), 0.0
    window = returns.iloc[-(ROLLING_WINDOW_DAYS + 1):-1]
    mean, std = window.mean(), window.std()
    latest = returns.iloc[-1]
    z = (latest - mean) / std if std > 0 else 0.0
    return round(float(latest) * 100, 2), round(float(z), 2)


def fetch_asset_data() -> list:
    """Fetch each tracked asset and return a list of result dicts."""
    results = []

    for name, meta in ASSETS.items():
        try:
            hist = _fetch_close_history(meta["ticker"])
            if meta.get("divide_by"):
                hist = hist / meta["divide_by"]
            pct, z = _pct_change_and_zscore(hist)
            results.append({
                "name": name,
                "ticker": meta["ticker"],
                "category": meta["category"],
                "last_price": round(float(hist.iloc[-1]), 4),
                "pct_change": pct,
                "zscore": z,
                "anomaly": abs(z) >= ZSCORE_THRESHOLD,
            })
        except Exception as e:
            results.append({"name": name, "ticker": meta["ticker"], "error": str(e)})

    # ASX materials proxy - equal-weighted average % change across the basket.
    basket_changes = []
    for label, ticker in ASX_MATERIALS_BASKET.items():
        try:
            hist = _fetch_close_history(ticker)
            pct, _ = _pct_change_and_zscore(hist)
            basket_changes.append(pct)
        except Exception:
            continue

    if basket_changes:
        avg_pct = round(sum(basket_changes) / len(basket_changes), 2)
        results.append({
            "name": "ASX Materials (basket proxy)",
            "ticker": "+".join(ASX_MATERIALS_BASKET.values()),
            "category": "equity_sector",
            "last_price": None,
            "pct_change": avg_pct,
            "zscore": None,
            "anomaly": abs(avg_pct) >= ASX_BASKET_FLAT_THRESHOLD,
        })

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_asset_data(), indent=2))
