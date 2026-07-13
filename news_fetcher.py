"""
Pulls headlines from free RSS feeds (no API key, no rate-limit-that-quietly-
breaks-in-production) and filters to the last N hours.
"""
import feedparser
import urllib.request
from datetime import datetime, timedelta, timezone
from config import RSS_FEEDS, MAX_HEADLINES_PER_FEED, NEWS_LOOKBACK_HOURS

FEED_FETCH_TIMEOUT_SECONDS = 10  # feedparser.parse(url) has no built-in timeout
# and will hang indefinitely on a slow/dead feed, so fetch the bytes ourselves.


def _entry_time(entry):
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_headlines() -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
    headlines = []

    for source, url in RSS_FEEDS.items():
        try:
            raw = urllib.request.urlopen(url, timeout=FEED_FETCH_TIMEOUT_SECONDS).read()
            feed = feedparser.parse(raw)
            for entry in feed.entries[:MAX_HEADLINES_PER_FEED]:
                published = _entry_time(entry)
                if published and published < cutoff:
                    continue
                headlines.append({
                    "source": source,
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", ""),
                    "published": published.isoformat() if published else None,
                })
        except Exception as e:
            headlines.append({"source": source, "error": str(e)})

    return headlines


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_headlines(), indent=2))
