"""
Sends the day's price moves + headlines to Claude to produce a plain-English
digest, grounded in the correlation map so it explains rather than predicts.
"""
import os
import json
import urllib.request
from config import CORRELATION_MAP

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"  # swap if you standardize on a different model elsewhere

SYSTEM_PROMPT = f"""You are writing a daily macro briefing for a Sydney-based
reader who tracks gold, silver, oil, USD, US yields, VIX, AUD/USD, and ASX
materials stocks, and wants to understand what moved and why it might matter
- not what to trade.

{CORRELATION_MAP}

Rules:
- Explain moves using the relationships above where they genuinely apply.
  Do not invent causal links that aren't in the list or aren't clearly
  supported by the headlines provided.
- Be honest about uncertainty. If assets moved and there's no clear causal
  story in the headlines, say so rather than forcing a narrative.
- This is informational context, not investment advice or a trading signal.
  Never tell the reader to buy, sell, or hold anything.
- Structure: (1) a one-paragraph summary of the day, (2) a short note for
  each asset flagged as anomalous (anomaly=true), explaining the likely
  driver and what it typically flows through to, (3) a short "what to watch"
  list of 2-3 upcoming known events if the headlines mention them (OPEC
  meetings, Fed/RBA decisions, EOFY-type calendar effects).
- Keep it under 400 words total. Plain English - briefly explain any jargon
  the first time you use it.
"""


def synthesize_digest(asset_data: list, headlines: list) -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]

    user_content = (
        "TODAY'S ASSET DATA (anomaly=true means it's an unusually large move "
        "for that asset):\n" + json.dumps(asset_data, indent=2) +
        "\n\nRECENT HEADLINES (last ~30h, from RSS feeds):\n" +
        json.dumps(headlines, indent=2)
    )

    payload = {
        "model": MODEL,
        "max_tokens": 1200,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    return "".join(block["text"] for block in data["content"] if block["type"] == "text")
