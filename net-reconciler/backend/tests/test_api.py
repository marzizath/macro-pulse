"""
API smoke tests - verifies routing, auth, and DB wiring using an in-memory
SQLite DB and a monkeypatched Splitwise client (no live credentials needed).
"""
import os

os.environ.setdefault("APP_SECRET", "")  # no auth required for these tests

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services import matcher
import app.routers.transactions as transactions_router
from tests.test_matcher import bank_txn, expense, MY_USER_ID


@pytest.fixture()
def client(monkeypatch):
    # StaticPool: FastAPI runs sync route handlers in a threadpool, and a
    # plain ":memory:" DB is otherwise a fresh empty database per connection.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()

    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(transactions_router, "_resolve_my_user_id", lambda: MY_USER_ID)

    with TestClient(app) as c:
        yield c, session

    app.dependency_overrides.clear()


def test_health(client):
    c, _ = client
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_transactions_list_and_patch_flow(client):
    c, db = client
    txns = [bank_txn("t1", "THAI GARDEN RESTAURANT", -152.30, "2026-08-08")]
    exps = [expense("e1", "Thai Garden Restaurant", 150.00, "2026-08-06", 150.00, 75.00)]
    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    resp = c.get("/transactions", params={"status": "flagged"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == "t1"

    resp = c.patch("/transactions/t1", json={"action": "confirm"})
    assert resp.status_code == 200
    assert resp.json()["match_status"] == "matched"

    resp = c.get("/summary", params={"period": "month"})
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["true_total"] >= 75.00


def test_receivables_list_and_manual_settle(client):
    c, db = client
    txns = [bank_txn("t1", "MECCA BAR", -120.00, "2026-08-03")]
    exps = [expense("e1", "Mecca Bar dinner", 120.00, "2026-08-03", 120.00, 60.00)]
    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    resp = c.get("/receivables")
    assert resp.status_code == 200
    receivables = resp.json()
    assert len(receivables) == 1
    rid = receivables[0]["id"]

    resp = c.post(f"/receivables/{rid}/settle")
    assert resp.status_code == 200
    assert resp.json()["settled_via"] == "manual"

    resp = c.get("/receivables", params={"open": True})
    assert resp.json() == []
