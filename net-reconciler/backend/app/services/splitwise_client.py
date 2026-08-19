"""
Splitwise API wrapper (v3.0).

Auth: `Authorization: Bearer {SPLITWISE_API_KEY}`.
Docs: https://dev.splitwise.com/

Only read endpoints are used - this app never creates/edits Splitwise
expenses (explicit non-goal, spec section 11).
"""
import json
import urllib.request
import urllib.parse
from datetime import date, datetime

from app.config import SPLITWISE_API_KEY

API_BASE = "https://secure.splitwise.com/api/v3.0"
PAGE_LIMIT = 100


def _get(path: str, params: dict | None = None) -> dict:
    if not SPLITWISE_API_KEY:
        raise RuntimeError("SPLITWISE_API_KEY is not set")
    url = f"{API_BASE}/{path}"
    if params:
        # drop None values so we don't send 'None' as a literal query string
        clean = {k: v for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {SPLITWISE_API_KEY}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_current_user() -> dict:
    """Returns the authenticated user's Splitwise profile (has 'id')."""
    return _get("get_current_user")["user"]


def get_friends() -> dict[int, str]:
    """Returns {user_id: display_name} for building the receivables UI."""
    data = _get("get_friends")
    friends = {}
    for f in data.get("friends", []):
        name = f"{f.get('first_name', '')} {f.get('last_name', '') or ''}".strip()
        friends[f["id"]] = name or f.get("email", str(f["id"]))
    return friends


def get_expenses(dated_after: date | None = None) -> list[dict]:
    """
    Paginates through /get_expenses since `dated_after` (inclusive).
    Returns raw expense dicts including deleted ones (caller filters -
    matcher.py explicitly skips deleted_at is not None per spec section 4).
    """
    expenses = []
    offset = 0
    dated_after_str = dated_after.isoformat() if dated_after else None
    while True:
        data = _get("get_expenses", {
            "dated_after": dated_after_str,
            "limit": PAGE_LIMIT,
            "offset": offset,
        })
        batch = data.get("expenses", [])
        expenses.extend(batch)
        if len(batch) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
    return expenses


def to_domain_expense(raw: dict, my_user_id: int) -> dict | None:
    """
    Normalizes a raw Splitwise expense payload into the shape matcher.py /
    models.SplitwiseExpense expect. Returns None if the current user isn't
    a party to the expense at all (shouldn't happen since get_expenses is
    scoped to the authenticated user, but defensive).
    """
    my_share = next((u for u in raw.get("users", []) if u.get("user_id") == my_user_id), None)
    if my_share is None:
        return None

    expense_date = raw["date"][:10]  # ISO datetime -> date
    return {
        "id": str(raw["id"]),
        "description": raw.get("description") or "(no description)",
        "total_cost": float(raw["cost"]),
        "currency": raw.get("currency_code", "AUD"),
        "expense_date": datetime.strptime(expense_date, "%Y-%m-%d").date(),
        "your_paid_share": float(my_share.get("paid_share", 0.0)),
        "your_owed_share": float(my_share.get("owed_share", 0.0)),
        "is_payment": bool(raw.get("payment", False)),
        "deleted": raw.get("deleted_at") is not None,
        "other_users": [
            {
                "user_id": u["user_id"],
                "name": f"{u.get('first_name', '')} {u.get('last_name', '') or ''}".strip(),
                "owed_share": float(u.get("owed_share", 0.0)),
                "paid_share": float(u.get("paid_share", 0.0)),
            }
            for u in raw.get("users", [])
            if u.get("user_id") != my_user_id
        ],
        "raw_json": json.dumps(raw),
    }
