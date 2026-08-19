from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.models import BankTransaction, LedgerEntry, Receivable
from app.schemas import SummaryOut

router = APIRouter(tags=["summary"], dependencies=[Depends(require_auth)])


def _period_start(period: str, today: date) -> date:
    if period == "week":
        return today - timedelta(days=today.weekday())  # Monday
    return today.replace(day=1)  # month


@router.get("/summary", response_model=SummaryOut)
def get_summary(period: Literal["week", "month"] = "week", db: Session = Depends(get_db)):
    today = date.today()
    start = _period_start(period, today)

    debits = (
        db.query(BankTransaction)
        .filter(BankTransaction.direction == "debit", BankTransaction.post_date >= start,
                BankTransaction.post_date <= today)
        .all()
    )
    raw_total = round(sum(t.amount for t in debits), 2)

    ledger_entries = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.date >= start, LedgerEntry.date <= today)
        .all()
    )
    true_total = round(sum(e.true_amount for e in ledger_entries), 2)

    open_receivables = round(
        sum(r.amount for r in db.query(Receivable).filter(Receivable.settled.is_(False)).all()), 2
    )

    # "Resolved" = the sync engine reached a confident answer without a human
    # needing to step in (matched/personal/reimbursement), as opposed to
    # sitting unmatched or waiting in the flagged review queue.
    resolved = sum(1 for t in debits if t.match_status in ("matched", "personal", "reimbursement"))
    match_rate = round(resolved / len(debits), 4) if debits else 1.0

    return SummaryOut(
        period=period, raw_total=raw_total, true_total=true_total,
        saved=round(raw_total - true_total, 2), open_receivables=open_receivables,
        match_rate=match_rate,
    )
