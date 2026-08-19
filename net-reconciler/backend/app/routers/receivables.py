from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import get_db
from app.models import Receivable
from app.schemas import ReceivableOut
from app.services import matcher

router = APIRouter(prefix="/receivables", tags=["receivables"], dependencies=[Depends(require_auth)])


def _to_out(r: Receivable) -> ReceivableOut:
    end = r.settled_date if r.settled else date.today()
    return ReceivableOut(
        id=r.id, expense_id=r.expense_id, debtor_user_id=r.debtor_user_id,
        debtor_name=r.debtor_name, amount=r.amount, opened_date=r.opened_date,
        settled=r.settled, settled_date=r.settled_date, settled_via=r.settled_via,
        days_open=(end - r.opened_date).days,
    )


@router.get("", response_model=list[ReceivableOut])
def list_receivables(open: bool = True, db: Session = Depends(get_db)):
    query = db.query(Receivable)
    if open:
        query = query.filter(Receivable.settled.is_(False))
    query = query.order_by(Receivable.opened_date.asc())
    return [_to_out(r) for r in query.all()]


@router.post("/{receivable_id}/settle", response_model=ReceivableOut)
def settle_receivable(receivable_id: int, db: Session = Depends(get_db)):
    receivable = db.get(Receivable, receivable_id)
    if not receivable:
        raise HTTPException(status_code=404, detail="Receivable not found")
    if receivable.settled:
        raise HTTPException(status_code=400, detail="Receivable is already settled")
    matcher.settle_receivable_manual(db, receivable)
    db.commit()
    db.refresh(receivable)
    return _to_out(receivable)
