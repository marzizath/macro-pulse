"""FastAPI app (spec section 5)."""
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.config import CORS_ORIGINS
from app.database import get_db, init_db
from app.routers import receivables, summary, transactions
from app.schemas import SyncResult
from app.services import matcher
from app.services.splitwise_client import get_current_user, get_expenses, to_domain_expense


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Net Reconciler API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router)
app.include_router(receivables.router)
app.include_router(summary.router)


@app.get("/health")
def health():
    return {"status": "ok"}


def _load_bank_transactions(since):
    from app.config import DATA_SOURCE
    if DATA_SOURCE == "basiq":
        from app.services.basiq_client import get_domain_transactions
    else:
        from app.services.fixture_source import get_domain_transactions
    return get_domain_transactions(since=since)


@app.post("/sync", response_model=SyncResult, dependencies=[Depends(require_auth)])
def sync(db: Session = Depends(get_db)):
    me = get_current_user()
    since = date.today() - timedelta(days=90)  # spec section 11: no backfill beyond 90 days

    bank_txns = _load_bank_transactions(since)
    raw_expenses = get_expenses(dated_after=since)
    expenses = [
        e for e in (to_domain_expense(r, me["id"]) for r in raw_expenses) if e is not None
    ]

    stats = matcher.sync_and_match(db, bank_txns, expenses, me["id"])
    return SyncResult(**stats)
