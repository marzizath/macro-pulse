"""SQLAlchemy models - see spec section 3 for the conceptual schema."""
from datetime import datetime, date

from sqlalchemy import (
    Column, String, Float, Boolean, Date, DateTime, Integer, Text, ForeignKey
)

from app.database import Base


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id = Column(String, primary_key=True)          # basiq transaction id
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)          # always positive
    direction = Column(String, nullable=False)       # 'debit' | 'credit'
    post_date = Column(Date, nullable=False)
    account_name = Column(String, nullable=True)
    match_status = Column(String, nullable=False, default="unmatched")
    # 'unmatched' | 'matched' | 'flagged' | 'personal' | 'reimbursement' | 'pending_settle'
    matched_expense_id = Column(String, ForeignKey("splitwise_expenses.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SplitwiseExpense(Base):
    __tablename__ = "splitwise_expenses"

    id = Column(String, primary_key=True)
    description = Column(String, nullable=False)
    total_cost = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="AUD")
    expense_date = Column(Date, nullable=False)
    your_paid_share = Column(Float, nullable=False, default=0.0)
    your_owed_share = Column(Float, nullable=False, default=0.0)
    is_payment = Column(Boolean, nullable=False, default=False)
    deleted = Column(Boolean, nullable=False, default=False)
    matched_bank_txn_id = Column(String, ForeignKey("bank_transactions.id"), nullable=True)
    raw_json = Column(Text, nullable=True)


class Receivable(Base):
    __tablename__ = "receivables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    expense_id = Column(String, ForeignKey("splitwise_expenses.id"), nullable=False)
    debtor_user_id = Column(Integer, nullable=False)
    debtor_name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    opened_date = Column(Date, nullable=False)
    settled = Column(Boolean, nullable=False, default=False)
    settled_date = Column(Date, nullable=True)
    settled_via = Column(String, nullable=True)   # 'splitwise_payment' | 'bank_credit' | 'manual'
    settled_bank_txn_id = Column(String, ForeignKey("bank_transactions.id"), nullable=True)


class LedgerEntry(Base):
    """The reconciled 'truth' the dashboard reads."""
    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_txn_id = Column(String, ForeignKey("bank_transactions.id"), nullable=True)
    expense_id = Column(String, ForeignKey("splitwise_expenses.id"), nullable=True)
    date = Column(Date, nullable=False)
    merchant = Column(String, nullable=False)
    raw_amount = Column(Float, nullable=False)
    true_amount = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    # 'shared_matched' | 'personal' | 'pending_settle' | 'reimbursement'
    people_count = Column(Integer, nullable=False, default=1)
