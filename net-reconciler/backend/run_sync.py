#!/usr/bin/env python3
"""
Entrypoint for GitHub Actions cron (spec section 7) - runs the full sync
pipeline and sends the digest. Equivalent to hitting POST /sync followed by
the notifier, but doesn't require the API server to be running.
"""
import sys
from datetime import date, timedelta

from app.config import DATA_SOURCE
from app.database import SessionLocal, init_db
from app.services import matcher, notifier
from app.services.splitwise_client import get_current_user, get_expenses, to_domain_expense


def load_bank_transactions(since):
    if DATA_SOURCE == "basiq":
        from app.services.basiq_client import get_domain_transactions
    else:
        from app.services.fixture_source import get_domain_transactions
    return get_domain_transactions(since=since)


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        me = get_current_user()
        since = date.today() - timedelta(days=90)

        bank_txns = load_bank_transactions(since)
        raw_expenses = get_expenses(dated_after=since)
        expenses = [
            e for e in (to_domain_expense(r, me["id"]) for r in raw_expenses) if e is not None
        ]

        stats = matcher.sync_and_match(db, bank_txns, expenses, me["id"])
        print(f"Sync complete: {stats}")

        digest_text = notifier.send_digest(db)
        print("Digest sent." if digest_text else "Digest skipped: nothing to report.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
