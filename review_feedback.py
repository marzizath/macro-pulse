"""
Monthly feedback review.

Reads issues labeled 'feedback' from the repo, cross-references each one's
digest date against the historical archive to pull the actual digest text,
and asks Claude whether a recurring pattern in the feedback justifies a
correlation-map addition. If so, it APPENDS a proposed entry to
correlation_map_learned.md.

This script never touches config.py, never auto-merges anything, and never
runs without a human reviewing the resulting pull request - see the
"feedback-review.yml" workflow, which opens the PR via
peter-evans/create-pull-request rather than pushing to main directly.

Minimum sample size gate: exits without proposing anything if there's too
little feedback to justify a change - a handful of opinions shouldn't
rewrite the system.
"""
import os
import json
import urllib.request
from datetime import datetime

GITHUB_API = "https://api.github.com"
MIN_FEEDBACK_ITEMS = 5
LEARNED_MAP_PATH = "correlation_map_learned.md"


def _gh_request(path: str, token: str):
    req = urllib.request.Request(
        f"{GITHUB_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _fetch_feedback_issues(repo: str, token: str) -> list:
    issues = _gh_request(f"/repos/{repo}/issues?labels=feedback&state=all&per_page=100", token)
    return [i for i in issues if "pull_request" not in i]  # exclude PRs, API returns both


def _digest_for_date(run_date: str) -> str:
    path = os.path.join("history", f"{run_date}.json")
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        record = json.load(f)
    return record.get("digest", "")


def _extract_date(body: str) -> str:
    for line in (body or "").splitlines():
        if line.lower().startswith("digest date:"):
            return line.split(":", 1)[1].strip()
    return ""


def _call_claude(system: str, user: str) -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    payload = {
        "model": "claude-sonnet-5",
        "max_tokens": 800,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
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
    return "".join(b["text"] for b in data["content"] if b["type"] == "text")


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    gh_token = os.environ["GITHUB_TOKEN"]

    issues = _fetch_feedback_issues(repo, gh_token)
    if len(issues) < MIN_FEEDBACK_ITEMS:
        print(f"Only {len(issues)} feedback item(s) - need {MIN_FEEDBACK_ITEMS}+ before proposing changes. Skipping.")
        return

    records = []
    for issue in issues:
        labels = [l["name"] for l in issue.get("labels", [])]
        sentiment = "positive" if "feedback-positive" in labels else (
            "negative" if "feedback-negative" in labels else "unknown")
        run_date = _extract_date(issue.get("body", ""))
        records.append({
            "sentiment": sentiment,
            "date": run_date,
            "user_note": issue.get("body", ""),
            "digest_excerpt": _digest_for_date(run_date)[:600],
        })

    negative = [r for r in records if r["sentiment"] == "negative"]
    if len(negative) < 3:
        print(f"Only {len(negative)} negative item(s) - not enough signal to propose a change. Skipping.")
        return

    system = """You review feedback on an automated macro-economics email
digest and decide whether there's a clear, recurring, factual pattern in
the negative feedback that justifies adding ONE new entry to a correlation
knowledge base used to ground the digest's explanations.

Be conservative. Most feedback batches will NOT justify a change - only
propose one if multiple negative items point at the same specific,
mechanism-based gap (e.g. "the digest never explains X" recurring 3+
times). If you propose a change, write it in the exact same style as the
existing entries: factual, mechanism-based ("A causes B because C"), never
predictive or advice-like.

Respond with EXACTLY one of:
1. "NO CHANGE JUSTIFIED: <one sentence why>"
2. "PROPOSED ADDITION:\\n<the new entry text, 2-4 sentences>\\nREASONING:\\n<which feedback items support this and why>"
"""

    user = "FEEDBACK RECORDS:\n" + json.dumps(records, indent=2)

    result = _call_claude(system, user)
    print(result)

    if result.strip().startswith("NO CHANGE JUSTIFIED"):
        print("No changes proposed this cycle.")
        return

    if "PROPOSED ADDITION:" not in result:
        print("Unexpected model response format - skipping to be safe.")
        return

    addition = result.split("PROPOSED ADDITION:", 1)[1].split("REASONING:", 1)[0].strip()
    reasoning = result.split("REASONING:", 1)[1].strip() if "REASONING:" in result else ""

    today = datetime.now().date().isoformat()
    entry = f"\n### {today}\n{addition}\n\n<!-- Reasoning: {reasoning} -->\n"

    with open(LEARNED_MAP_PATH, "a") as f:
        f.write(entry)

    # Written for peter-evans/create-pull-request to use as the PR body.
    with open("PROPOSED_CHANGES.md", "w") as f:
        f.write(f"## Proposed correlation map addition\n\n**New entry:**\n{addition}\n\n"
                f"**Reasoning:**\n{reasoning}\n\n"
                f"Based on {len(negative)} negative feedback item(s) out of {len(records)} total. "
                f"Review the addition in `correlation_map_learned.md` and merge if it looks right, "
                f"or close this PR if not.\n")

    print("Proposed addition written. PR will be opened by the workflow.")


if __name__ == "__main__":
    main()
