"""
"Last N times this happened, here's what followed" - built from the actual
historical archive, not guessed. Returns real recorded outcomes only; if the
archive is too young to have enough history, it says so rather than padding
with nothing.

Explicitly pattern context, not prediction: a handful of past episodes is
not a statistically robust sample, and the synthesizer is instructed to
present it that way.
"""
from config import PATTERN_LOOKBACK_MAX, PATTERN_FORWARD_DAYS
from history_store import load_all_runs


def _asset_from_run(run: dict, name: str):
    for a in run.get("assets", []):
        if a.get("name") == name and "error" not in a:
            return a
    return None


def find_similar_episodes(asset_name: str, current_direction: str) -> dict:
    """
    current_direction: 'up' or 'down' - the sign of today's flagged move.
    Returns a dict summarizing past episodes where this asset flagged in the
    same direction, and what it did over the following recorded sessions.
    """
    runs = load_all_runs()
    episodes = []

    for i, run in enumerate(runs):
        asset = _asset_from_run(run, asset_name)
        if not asset or not asset.get("anomaly"):
            continue
        direction = "up" if asset["pct_change"] >= 0 else "down"
        if direction != current_direction:
            continue

        # Look forward through subsequent *recorded* runs (not calendar days -
        # the archive only has data for days the pipeline actually ran).
        forward_prices = []
        for future_run in runs[i + 1: i + 1 + PATTERN_FORWARD_DAYS]:
            future_asset = _asset_from_run(future_run, asset_name)
            if future_asset:
                forward_prices.append(future_asset["pct_change"])

        if forward_prices:
            episodes.append({
                "date": run["date"],
                "initial_move_pct": asset["pct_change"],
                "following_moves_pct": forward_prices,
                "cumulative_following_pct": round(sum(forward_prices), 2),
            })

    episodes = episodes[-PATTERN_LOOKBACK_MAX:]  # most recent N episodes

    return {
        "asset": asset_name,
        "direction": current_direction,
        "episode_count": len(episodes),
        "episodes": episodes,
        "note": (
            "Archive too young for a meaningful pattern yet - fewer than 2 "
            "prior episodes recorded." if len(episodes) < 2 else None
        ),
    }


def build_pattern_context(asset_data: list) -> list:
    """Run find_similar_episodes for every asset flagged today."""
    contexts = []
    for a in asset_data:
        if not a.get("anomaly") or "error" in a:
            continue
        direction = "up" if a["pct_change"] >= 0 else "down"
        contexts.append(find_similar_episodes(a["name"], direction))
    return contexts
