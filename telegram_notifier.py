"""
Telegram push alert - fires only when at least one asset is flagged, so it
stays meaningful instead of becoming a second daily digest you start
ignoring. The full write-up still lives in the email; this is a "check your
inbox" nudge.

Setup: message @BotFather on Telegram, /newbot, grab the token. Message your
new bot once, then hit https://api.telegram.org/bot<TOKEN>/getUpdates to
find your chat_id. Full steps in README.md.
"""
import os
import json
import urllib.request
import urllib.parse
from config import TELEGRAM_ENABLED

API_BASE = "https://api.telegram.org"


def send_alert(asset_data: list, digest_text: str):
    if not TELEGRAM_ENABLED:
        return

    flagged = [a for a in asset_data if a.get("anomaly")]
    if not flagged:
        return  # nothing unusual - stay quiet

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram alert skipped: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set.")
        return

    lines = [f"\u26a1 *Macro Pulse* \u2014 {len(flagged)} asset(s) flagged\n"]
    for a in flagged:
        arrow = "\U0001F53A" if a["pct_change"] >= 0 else "\U0001F53B"
        lines.append(f"{arrow} *{a['name']}*: {a['pct_change']:+}% (z={a.get('zscore')})")
    lines.append("\nFull digest is in your email. Informational only, not a signal.")
    text = "\n".join(lines)

    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                print(f"Telegram API returned an error: {result}")
    except Exception as e:
        print(f"Telegram alert failed (non-fatal, email still sent): {e}")
