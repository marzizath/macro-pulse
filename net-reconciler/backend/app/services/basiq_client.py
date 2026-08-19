"""
Basiq API wrapper (Australian Open Banking / CDR bank feed).

Docs: https://api.basiq.io/reference

Flow: exchange BASIQ_API_KEY for a short-lived access token via POST /token,
then page through GET /users/{userId}/transactions.

Every transformation from Basiq's payload shape into our domain shape lives
in `to_domain_transaction` so a Basiq API change only needs one function
touched (spec section 9, Phase 2 prompt).
"""
import json
import urllib.request
import urllib.parse
from datetime import date, datetime

from app.config import BASIQ_API_KEY, BASIQ_USER_ID

API_BASE = "https://au-api.basiq.io"
PAGE_LIMIT = 500


def _get_access_token() -> str:
    if not BASIQ_API_KEY:
        raise RuntimeError("BASIQ_API_KEY is not set")
    req = urllib.request.Request(
        f"{API_BASE}/token",
        data=urllib.parse.urlencode({"scope": "SERVER_ACCESS"}).encode(),
        method="POST",
        headers={
            "Authorization": f"Basic {BASIQ_API_KEY}",
            "Content-Type": "application/x-www-form-urlencoded",
            "basiq-version": "3.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["access_token"]


def _get(path: str, token: str, params: dict | None = None) -> dict:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_transactions(since: date | None = None, user_id: str | None = None) -> list[dict]:
    """
    Paginates through /users/{userId}/transactions, optionally filtered to
    transaction.postDate greater than `since`. Returns raw Basiq transaction
    dicts (caller normalizes via to_domain_transaction).
    """
    uid = user_id or BASIQ_USER_ID
    if not uid:
        raise RuntimeError("BASIQ_USER_ID is not set")

    token = _get_access_token()
    filter_expr = None
    if since:
        filter_expr = f"transaction.postDate.gt('{since.isoformat()}')"

    transactions = []
    next_url = None
    params = {"filter": filter_expr, "limit": PAGE_LIMIT} if filter_expr else {"limit": PAGE_LIMIT}

    while True:
        if next_url:
            req = urllib.request.Request(next_url, headers={
                "Authorization": f"Bearer {token}", "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        else:
            data = _get(f"/users/{uid}/transactions", token, params)

        batch = data.get("data", [])
        transactions.extend(batch)

        next_link = data.get("links", {}).get("next")
        if not next_link or not batch:
            break
        next_url = next_link

    return transactions


def to_domain_transaction(raw: dict) -> dict:
    """
    Normalizes a raw Basiq transaction into the shape matcher.py /
    models.BankTransaction expect.

    Basiq amounts: `amount` is signed as a string (negative = money out).
    We store an unsigned amount + explicit 'debit'/'credit' direction, and
    dedupe pending->posted transitions on posting via the txn id Basiq
    assigns (spec section 10: "pending transaction later posts with a
    slightly different amount/id -> dedupe on posting" - Basiq reuses the
    same id when a pending transaction posts, so upsert-by-id handles this;
    if a *new* id appears for what was a pending txn, the amount+date+desc
    proximity match in the matcher's Rule 1/2 still catches it as a normal
    bank txn).
    """
    signed_amount = float(raw.get("amount", 0.0))
    post_date_raw = raw.get("postDate") or raw.get("transactionDate")
    post_date = datetime.strptime(post_date_raw[:10], "%Y-%m-%d").date()

    return {
        "id": raw["id"],
        "description": raw.get("description", "").strip(),
        "amount": abs(signed_amount),
        "direction": "debit" if signed_amount < 0 else "credit",
        "post_date": post_date,
        "account_name": (raw.get("account") or {}).get("name") if isinstance(raw.get("account"), dict) else raw.get("account"),
    }


def get_domain_transactions(since: date | None = None) -> list[dict]:
    return [to_domain_transaction(t) for t in get_transactions(since=since)]
