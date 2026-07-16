"""
Sends the day's price moves + headlines + historical pattern context to
Claude to produce a plain-English digest, grounded in the correlation map
(base + learned additions) so it explains rather than predicts.
"""
import os
import json
import urllib.request
from config import CORRELATION_MAP

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"  # swap if you standardize on a different model elsewhere

LEARNED_MAP_PATH = "correlation_map_learned.md"


def _load_learned_patterns() -> str:
    """Read AI-proposed, human-approved additions to the correlation map.
    Empty until you've merged at least one feedback-review pull request."""
    if not os.path.exists(LEARNED_MAP_PATH):
        return ""
    with open(LEARNED_MAP_PATH, encoding="utf-8") as f:
        content = f.read()
    # strip the leading HTML comment block (instructions, not content)
    if content.strip().startswith("<!--"):
        end = content.find("-->")
        content = content[end + 3:] if end != -1 else ""
    return content.strip()


EDITION_FRAMING = {
    "morning": (
        "This is the MORNING edition, sent ~7am Sydney time. It should read "
        "as a recap of what happened overnight while the reader slept - "
        "mainly the US and European trading sessions, plus any Middle East "
        "/ geopolitical developments that broke overnight Sydney time."
    ),
    "evening": (
        "This is the EVENING edition, sent ~4:15pm Sydney time, right after "
        "the ASX closes. It should read as a recap of the Australian trading "
        "day - how AUD/USD and ASX materials names actually traded, and any "
        "Asian-session commodity moves - rather than repeating the morning "
        "edition's overnight story unless something materially changed "
        "during the day."
    ),
    "daily": "This is a single daily digest covering the last 24 hours.",
}


def _build_system_prompt(edition: str = "daily") -> str:
    learned = _load_learned_patterns()
    learned_section = (
        f"\n\nLEARNED PATTERNS (added over time from your own feedback, "
        f"human-reviewed before being added - treat with the same care as "
        f"the base list above):\n{learned}\n"
        if learned else ""
    )
    framing = EDITION_FRAMING.get(edition, EDITION_FRAMING["daily"])
    return f"""You are writing a macro briefing for a Sydney-based reader who
tracks gold, silver, oil, USD, US yields, VIX, AUD/USD, and ASX materials
stocks, and wants to understand what moved and why it might matter - not
what to trade.

{framing}

{CORRELATION_MAP}{learned_section}

Rules:
- Explain moves using the relationships above where they genuinely apply.
  Do not invent causal links that aren't in the list or aren't clearly
  supported by the headlines provided.
- Be honest about uncertainty. If assets moved and there's no clear causal
  story in the headlines, say so rather than forcing a narrative.
- If historical pattern context is provided for a flagged asset, present it
  explicitly as "in N past similar episodes, this asset did X" - never as
  a forecast, and say plainly when the sample is too small to mean much
  (fewer than 3 episodes).
- This is informational context, not investment advice or a trading signal.
  Never tell the reader to buy, sell, or hold anything.
- Structure: (1) a one-paragraph summary of the day, (2) a short note for
  each flagged asset (anomaly=true), including its historical pattern
  context if provided, (3) a short "what to watch" list of 2-3 upcoming
  known events if the headlines mention them.
- Keep it under 450 words total. Plain English - briefly explain any jargon
  the first time you use it.
"""


def _strip_history_for_api(asset_data: list) -> list:
    """The 30-day 'history' array exists only to draw sparklines in the
    email locally (see email_sender.py) - the model never needs raw daily
    closes to explain today's move, just today's % change and z-score.
    Dropping it here was the single biggest lever on the API bill, since it
    was the majority of the JSON payload for no reasoning benefit."""
    return [{k: v for k, v in a.items() if k != "history"} for a in asset_data]


def synthesize_digest(asset_data: list, headlines: list, pattern_context: list = None,
                       edition: str = "daily") -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]

    slim_asset_data = _strip_history_for_api(asset_data)

    user_content = (
        "TODAY'S ASSET DATA (anomaly=true means it's an unusually large move "
        "for that asset):\n" + json.dumps(slim_asset_data, indent=2) +
        "\n\nRECENT HEADLINES (last ~30h, from RSS feeds):\n" +
        json.dumps(headlines, indent=2)
    )

    if pattern_context:
        user_content += (
            "\n\nHISTORICAL PATTERN CONTEXT for flagged assets (from this "
            "project's own archive - real recorded outcomes, small sample):\n"
            + json.dumps(pattern_context, indent=2)
        )

    payload = {
        "model": MODEL,
        "max_tokens": 1400,
        "system": _build_system_prompt(edition),
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
