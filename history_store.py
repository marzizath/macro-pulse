"""
Historical archive.

Every run writes a small JSON file to history/YYYY-MM-DD.json. This is what
makes "last 5 times this happened, here's what followed" an honest claim
instead of decoration - and it's what the dashboard and pattern_lookup.py
read from.

Design choice: plain JSON files, one per day, committed to the repo by the
workflow (see .github/workflows/macro-pulse.yml). No database service to
pay for or lose data in, fully diffable in git history, and trivial to
delete/edit if a bad run needs correcting.
"""
import json
import os
from datetime import date
from config import HISTORY_DIR


def _slim_for_storage(asset_data: list) -> list:
    """Store the fields pattern-matching and the dashboard actually need -
    drop the full 30-day history array per asset to keep files small, since
    that's redundant across consecutive days' files."""
    slim = []
    for a in asset_data:
        if "error" in a:
            slim.append({"name": a["name"], "error": a["error"]})
            continue
        slim.append({
            "name": a["name"],
            "pct_change": a["pct_change"],
            "zscore": a.get("zscore"),
            "anomaly": a.get("anomaly", False),
            "last_price": a.get("last_price"),
        })
    return slim


def save_run(asset_data: list, digest_text: str, run_date: date = None):
    run_date = run_date or date.today()
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = os.path.join(HISTORY_DIR, f"{run_date.isoformat()}.json")

    record = {
        "date": run_date.isoformat(),
        "assets": _slim_for_storage(asset_data),
        "flagged": [a["name"] for a in asset_data if a.get("anomaly")],
        "digest": digest_text,
    }
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return path


def load_all_runs() -> list:
    """Return every saved run, sorted oldest -> newest."""
    if not os.path.isdir(HISTORY_DIR):
        return []
    runs = []
    for fname in sorted(os.listdir(HISTORY_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(HISTORY_DIR, fname)) as f:
            runs.append(json.load(f))
    return runs
