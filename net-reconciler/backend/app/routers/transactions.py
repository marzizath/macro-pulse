from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.models import BankTransaction, LedgerEntry, SplitwiseExpense
from app.schemas import TransactionOut, TransactionPatch
from app.services import matcher
from app.services.splitwise_client import get_current_user

router = APIRouter(prefix="/transactions", tags=["transactions"], dependencies=[Depends(require_auth)])


def _resolve_my_user_id() -> int:
    # Cheap enough for a single-user personal app; avoids a settings table.
    return get_current_user()["id"]


def _to_out(db: Session, txn: BankTransaction) -> TransactionOut:
    """Attaches the candidate Splitwise expense's description/cost so the
    Review Queue can show a real side-by-side comparison (spec section 6)."""
    out = TransactionOut.model_validate(txn)
    if txn.match_status == "flagged" and txn.matched_expense_id:
        candidate = db.get(SplitwiseExpense, txn.matched_expense_id)
        if candidate:
            out.candidate_description = candidate.description
            out.candidate_amount = candidate.total_cost
    return out


@router.get("", response_model=list[TransactionOut])
def list_transactions(status: Optional[str] = None, limit: int = 50, offset: int = 0,
                       db: Session = Depends(get_db)):
    query = db.query(BankTransaction)
    if status:
        query = query.filter(BankTransaction.match_status == status)
    query = query.order_by(BankTransaction.post_date.desc()).offset(offset).limit(limit)
    return [_to_out(db, t) for t in query.all()]


@router.patch("/{txn_id}", response_model=TransactionOut)
def patch_transaction(txn_id: str, patch: TransactionPatch, db: Session = Depends(get_db)):
    txn = db.get(BankTransaction, txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if patch.action == "confirm":
        try:
            matcher.confirm_flagged_match(db, txn, _resolve_my_user_id())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif patch.action == "reject":
        try:
            matcher.reject_flagged_match(db, txn)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif patch.category:
        txn.match_status = patch.category
        entry = db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == txn.id).first()
        if entry:
            entry.category = patch.category
            if patch.category == "personal":
                entry.true_amount = txn.amount
            elif patch.category == "reimbursement":
                entry.true_amount = 0.0
        db.commit()
    else:
        raise HTTPException(status_code=400, detail="Provide either 'action' or 'category'")

    db.refresh(txn)
    return _to_out(db, txn)
