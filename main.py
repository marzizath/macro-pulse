"""
Macro Pulse - daily orchestrator.

Run locally with: python main.py
Runs automatically via .github/workflows/macro-pulse.yml, which also commits
the day's history record and rebuilds the dashboard afterward.
"""
from price_data import fetch_asset_data
from news_fetcher import fetch_headlines
from pattern_lookup import build_pattern_context
from synthesizer import synthesize_digest
from email_sender import send_digest
from telegram_notifier import send_alert
from history_store import save_run
from dashboard_builder import build_dashboard


def main():
    print("Fetching asset data...")
    asset_data = fetch_asset_data()
    for a in asset_data:
        tag = " <-- FLAGGED" if a.get("anomaly") else ""
        print(f"  {a['name']}: {a.get('pct_change', a.get('error'))}%{tag}")

    print("Fetching news...")
    headlines = fetch_headlines()
    print(f"  {len(headlines)} headlines pulled")

    print("Looking up historical patterns for flagged assets...")
    pattern_context = build_pattern_context(asset_data)
    for p in pattern_context:
        print(f"  {p['asset']}: {p['episode_count']} past similar episode(s)")

    print("Synthesizing digest...")
    digest = synthesize_digest(asset_data, headlines, pattern_context)

    print("Sending email...")
    send_digest(digest, asset_data)

    print("Checking Telegram alert...")
    send_alert(asset_data, digest)

    print("Saving to historical archive...")
    path = save_run(asset_data, digest)
    print(f"  saved {path}")

    print("Rebuilding dashboard...")
    dash_path = build_dashboard()
    print(f"  rebuilt {dash_path}")

    print("Done.")


if __name__ == "__main__":
    main()
