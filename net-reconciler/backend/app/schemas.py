"""Pydantic request/response models for the API (spec section 5)."""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


class TransactionOut(BaseModel):
    id: str
    description: str
    amount: float
    direction: str
    post_date: date
    account_name: Optional[str] = None
    match_status: str
    matched_expense_id: Optional[str] = None
    candidate_description: Optional[str] = None
    candidate_amount: Optional[float] = None

    class Config:
        from_attributes = True


class TransactionPatch(BaseModel):
    """Either confirm/reject a flagged match, or manually recategorize."""
    action: Optional[Literal["confirm", "reject"]] = None
    category: Optional[Literal["personal", "shared_matched", "pending_settle", "reimbursement"]] = None


class ReceivableOut(BaseModel):
    id: int
    expense_id: str
    debtor_user_id: int
    debtor_name: str
    amount: float
    opened_date: date
    settled: bool
    settled_date: Optional[date] = None
    settled_via: Optional[str] = None
    days_open: int

    class Config:
        from_attributes = True


class SummaryOut(BaseModel):
    period: str
    raw_total: float
    true_total: float
    saved: float
    open_receivables: float
    match_rate: float


class SyncResult(BaseModel):
    matched: int
    flagged: int
    personal: int
    pending_settle: int
    settled_bank: int
    settled_splitwise: int
