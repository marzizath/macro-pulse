"""
Fixture-backed stand-in for basiq_client, used when DATA_SOURCE=fixture
(the default until Basiq credentials are wired up - spec section 9 Phase 1).

Replays backend/tests/fixtures/bank_sample.json through the same
normalization function Basiq transactions go through, so the matcher never
has to know which source it's looking at.
"""
import json
import os

from app.services.basiq_client import to_domain_transaction

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tests", "fixtures", "bank_sample.json",
)


def get_domain_transactions(since=None) -> list[dict]:
    with open(FIXTURE_PATH) as f:
        raw = json.load(f)
    txns = [to_domain_transaction(t) for t in raw]
    if since:
        txns = [t for t in txns if t["post_date"] >= since]
    return txns
