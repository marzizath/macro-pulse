"""
Macro Pulse - daily orchestrator.

Run locally with: python main.py
Runs automatically via .github/workflows/macro-pulse.yml
"""
from price_data import fetch_asset_data
from news_fetcher import fetch_headlines
from synthesizer import synthesize_digest
from email_sender import send_digest


def main():
    print("Fetching asset data...")
    asset_data = fetch_asset_data()
    for a in asset_data:
        tag = " <-- FLAGGED" if a.get("anomaly") else ""
        print(f"  {a['name']}: {a.get('pct_change', a.get('error'))}%{tag}")

    print("Fetching news...")
    headlines = fetch_headlines()
    print(f"  {len(headlines)} headlines pulled")

    print("Synthesizing digest...")
    digest = synthesize_digest(asset_data, headlines)

    print("Sending email...")
    send_digest(digest, asset_data)

    print("Done.")


if __name__ == "__main__":
    main()
