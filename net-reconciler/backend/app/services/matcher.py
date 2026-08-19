"""
The matching engine - the core of Net Reconciler (spec section 4).

Reconciles bank transactions against Splitwise expenses. Rules run in a
fixed order, first hit wins, and everything is idempotent: re-running
`sync_and_match` on the same data never duplicates a LedgerEntry or
Receivable, and a matched expense/transaction pair can never be re-matched
to something else without going through confirm/reject first.

Rule order for an unmatched DEBIT bank transaction:
  0. Settle an open "pending_settle" entry (you were the ower, already
     counted as true spend when the expense appeared - this debit is you
     paying it back, so it must NOT be double counted as personal spend).
  1. Exact match (amount within $1, date within 2 days) -> 'matched'.
  2. Surcharge-tolerant match (amount within 5%, date within 2 days, at
     least one word in common) -> 'flagged' for human review.
  3. Recurring whitelist match (description contains a whitelisted pattern
     and exactly one candidate expense with the same pattern exists in the
     same calendar month) -> 'matched'.
  else: 'personal'.

For an unmatched CREDIT bank transaction:
  4. Settlement detection: matches one open Receivable, or the sum of two
     open Receivables from the same person, within $1 -> settles them,
     'reimbursement'. No match -> left unmatched (salary etc).

Every sync, independent of bank transactions:
  5. Splitwise-side settlements: a `payment=True` expense where you are the
     receiver settles the payer's matching open Receivable(s).
  6. "You're the ower": an expense where your_paid_share == 0 and
     your_owed_share > 0 creates a 'pending_settle' LedgerEntry immediately
     (counts as true spend the moment the expense exists, per spec).
"""
import json
from datetime import date
from itertools import combinations

from sqlalchemy.orm import Session

from app.config import (
    EXACT_MATCH_AMOUNT_TOLERANCE,
    EXACT_MATCH_DATE_WINDOW_DAYS,
    SURCHARGE_MATCH_PCT_TOLERANCE,
    SETTLEMENT_AMOUNT_TOLERANCE,
    RECURRING_WHITELIST,
    STATIC_FX_TO_AUD,
)
from app.models import BankTransaction, SplitwiseExpense, Receivable, LedgerEntry

STOPWORD_MIN_LEN = 3
PENDING_SETTLE_DATE_WINDOW_DAYS = 60


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def normalize_words(text: str) -> set[str]:
    """Uppercase, strip punctuation, drop words shorter than 3 chars."""
    if not text:
        return set()
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.upper())
    return {w for w in cleaned.split() if len(w) >= STOPWORD_MIN_LEN}


def has_word_overlap(a: str, b: str) -> bool:
    return bool(normalize_words(a) & normalize_words(b))


def to_aud(amount: float, currency: str) -> float:
    rate = STATIC_FX_TO_AUD.get(currency, 1.0)
    return round(amount * rate, 2)


def _date_delta_days(a: date, b: date) -> int:
    return abs((a - b).days)


# ---------------------------------------------------------------------------
# Upsert helpers - idempotency backbone
# ---------------------------------------------------------------------------

def upsert_bank_transactions(db: Session, txns: list[dict]) -> None:
    for t in txns:
        existing = db.get(BankTransaction, t["id"])
        if existing:
            # Refresh mutable fields only - never touch match_status /
            # matched_expense_id here, that would undo human review.
            existing.description = t["description"]
            existing.amount = t["amount"]
            existing.direction = t["direction"]
            existing.post_date = t["post_date"]
            existing.account_name = t.get("account_name")
        else:
            db.add(BankTransaction(
                id=t["id"], description=t["description"], amount=t["amount"],
                direction=t["direction"], post_date=t["post_date"],
                account_name=t.get("account_name"), match_status="unmatched",
            ))
    db.flush()


def upsert_splitwise_expenses(db: Session, expenses: list[dict]) -> None:
    for e in expenses:
        existing = db.get(SplitwiseExpense, e["id"])
        if existing:
            was_deleted = existing.deleted
            existing.description = e["description"]
            existing.total_cost = e["total_cost"]
            existing.currency = e["currency"]
            existing.expense_date = e["expense_date"]
            existing.your_paid_share = e["your_paid_share"]
            existing.your_owed_share = e["your_owed_share"]
            existing.is_payment = e["is_payment"]
            existing.deleted = e["deleted"]
            existing.raw_json = e.get("raw_json")
            if e["deleted"] and not was_deleted:
                _unmatch_expense(db, existing)
        else:
            db.add(SplitwiseExpense(
                id=e["id"], description=e["description"], total_cost=e["total_cost"],
                currency=e["currency"], expense_date=e["expense_date"],
                your_paid_share=e["your_paid_share"], your_owed_share=e["your_owed_share"],
                is_payment=e["is_payment"], deleted=e["deleted"], raw_json=e.get("raw_json"),
            ))
    db.flush()


def _unmatch_expense(db: Session, expense: SplitwiseExpense) -> None:
    """Expense deleted in Splitwise after being matched -> unmatch + revert
    ledger on next sync (edge case, spec section 10)."""
    if expense.matched_bank_txn_id:
        txn = db.get(BankTransaction, expense.matched_bank_txn_id)
        if txn:
            txn.match_status = "unmatched"
            txn.matched_expense_id = None
        expense.matched_bank_txn_id = None
    db.query(LedgerEntry).filter(LedgerEntry.expense_id == expense.id).delete()
    db.query(Receivable).filter(
        Receivable.expense_id == expense.id, Receivable.settled.is_(False)
    ).delete(synchronize_session=False)


# ---------------------------------------------------------------------------
# Candidate selection with ambiguity detection
# ---------------------------------------------------------------------------

def _unmatched_expense_candidates(db: Session) -> list[SplitwiseExpense]:
    return (
        db.query(SplitwiseExpense)
        .filter(
            SplitwiseExpense.deleted.is_(False),
            SplitwiseExpense.is_payment.is_(False),
            SplitwiseExpense.your_paid_share > 0,
            SplitwiseExpense.matched_bank_txn_id.is_(None),
        )
        .all()
    )


def _rank_by_date_proximity(txn: BankTransaction, scored: list[tuple[int, SplitwiseExpense]]):
    """Given (date_delta, expense) pairs already filtered by amount, returns
    (winner, ambiguous). Ambiguous means >=2 candidates tie on date
    proximity - spec section 10 says never guess in that case."""
    if not scored:
        return None, False
    scored.sort(key=lambda x: x[0])
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None, True
    return scored[0][1], False


def _exact_candidates(db: Session, txn: BankTransaction):
    scored = []
    for e in _unmatched_expense_candidates(db):
        cost_aud = to_aud(e.total_cost, e.currency)
        if abs(cost_aud - txn.amount) > EXACT_MATCH_AMOUNT_TOLERANCE:
            continue
        delta = _date_delta_days(e.expense_date, txn.post_date)
        if delta > EXACT_MATCH_DATE_WINDOW_DAYS:
            continue
        scored.append((delta, e))
    return _rank_by_date_proximity(txn, scored)


def _surcharge_candidates(db: Session, txn: BankTransaction):
    scored = []
    for e in _unmatched_expense_candidates(db):
        cost_aud = to_aud(e.total_cost, e.currency)
        if cost_aud <= 0:
            continue
        pct_diff = abs(cost_aud - txn.amount) / cost_aud
        if pct_diff > SURCHARGE_MATCH_PCT_TOLERANCE:
            continue
        delta = _date_delta_days(e.expense_date, txn.post_date)
        if delta > EXACT_MATCH_DATE_WINDOW_DAYS:
            continue
        if not has_word_overlap(txn.description, e.description):
            continue
        scored.append((delta, e))
    return _rank_by_date_proximity(txn, scored)


# ---------------------------------------------------------------------------
# Ledger / receivable creation
# ---------------------------------------------------------------------------

def _people_count(expense: SplitwiseExpense) -> int:
    if not expense.raw_json:
        return 1
    try:
        raw = json.loads(expense.raw_json)
        return max(1, len(raw.get("users", [])))
    except (ValueError, TypeError):
        return 1


def _upsert_ledger_entry(db: Session, **fields) -> LedgerEntry:
    query = db.query(LedgerEntry)
    if fields.get("bank_txn_id"):
        existing = query.filter(LedgerEntry.bank_txn_id == fields["bank_txn_id"]).first()
    elif fields.get("expense_id"):
        existing = query.filter(LedgerEntry.expense_id == fields["expense_id"]).first()
    else:
        existing = None
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        return existing
    entry = LedgerEntry(**fields)
    db.add(entry)
    return entry


def _create_receivables_for_others(db: Session, expense: SplitwiseExpense, my_user_id: int) -> None:
    if not expense.raw_json:
        return
    raw = json.loads(expense.raw_json)
    for u in raw.get("users", []):
        if u.get("user_id") == my_user_id:
            continue
        owed = float(u.get("owed_share", 0.0))
        if owed <= 0:
            continue
        exists = db.query(Receivable).filter(
            Receivable.expense_id == expense.id,
            Receivable.debtor_user_id == u["user_id"],
        ).first()
        if exists:
            continue  # idempotent - don't duplicate on re-sync
        name = f"{u.get('first_name', '')} {u.get('last_name', '') or ''}".strip() or str(u["user_id"])
        db.add(Receivable(
            expense_id=expense.id, debtor_user_id=u["user_id"], debtor_name=name,
            amount=to_aud(owed, expense.currency), opened_date=expense.expense_date,
            settled=False,
        ))


def _create_ledger_and_receivables(db: Session, txn: BankTransaction | None,
                                    expense: SplitwiseExpense, my_user_id: int) -> None:
    _upsert_ledger_entry(
        db,
        bank_txn_id=txn.id if txn else None,
        expense_id=expense.id,
        date=txn.post_date if txn else expense.expense_date,
        merchant=expense.description,
        raw_amount=txn.amount if txn else 0.0,
        true_amount=to_aud(expense.your_owed_share, expense.currency),
        category="shared_matched",
        people_count=_people_count(expense),
    )
    _create_receivables_for_others(db, expense, my_user_id)


def _mark_personal(db: Session, txn: BankTransaction) -> None:
    txn.match_status = "personal"
    _upsert_ledger_entry(
        db, bank_txn_id=txn.id, expense_id=None, date=txn.post_date,
        merchant=txn.description, raw_amount=txn.amount, true_amount=txn.amount,
        category="personal", people_count=1,
    )


# ---------------------------------------------------------------------------
# Rule 0: settle a pending "you're the ower" entry
# ---------------------------------------------------------------------------

def _try_settle_pending_ower(db: Session, txn: BankTransaction) -> bool:
    pending = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.category == "pending_settle", LedgerEntry.bank_txn_id.is_(None))
        .all()
    )
    scored = []
    for entry in pending:
        if abs(entry.true_amount - txn.amount) > EXACT_MATCH_AMOUNT_TOLERANCE:
            continue
        delta = _date_delta_days(entry.date, txn.post_date)
        if delta > PENDING_SETTLE_DATE_WINDOW_DAYS:
            continue
        scored.append((delta, entry))
    winner, ambiguous = _rank_by_date_proximity(txn, scored)
    if ambiguous or winner is None:
        return False
    winner.bank_txn_id = txn.id
    txn.match_status = "reimbursement"
    txn.matched_expense_id = winner.expense_id
    return True


# ---------------------------------------------------------------------------
# Rules 1-3: unmatched debit transactions
# ---------------------------------------------------------------------------

def _match_debit_transactions(db: Session, stats: dict, my_user_id: int) -> None:
    unmatched = (
        db.query(BankTransaction)
        .filter(BankTransaction.direction == "debit", BankTransaction.match_status == "unmatched")
        .order_by(BankTransaction.post_date)
        .all()
    )
    for txn in unmatched:
        if _try_settle_pending_ower(db, txn):
            stats["settled_bank"] += 1
            continue

        winner, ambiguous = _exact_candidates(db, txn)
        if winner is not None:
            txn.match_status = "matched"
            txn.matched_expense_id = winner.id
            winner.matched_bank_txn_id = txn.id
            _create_ledger_and_receivables(db, txn, winner, my_user_id)
            stats["matched"] += 1
            continue
        if ambiguous:
            # Two+ equally-close candidates (e.g. identical-amount dinners in
            # the same week) - flag for a human, but reserve neither
            # candidate since we don't know which one is right.
            txn.match_status = "flagged"
            stats["flagged"] += 1
            continue

        winner, ambiguous = _surcharge_candidates(db, txn)
        if winner is not None:
            txn.match_status = "flagged"
            txn.matched_expense_id = winner.id
            winner.matched_bank_txn_id = txn.id  # reserve it until confirmed/rejected
            stats["flagged"] += 1
            continue

        if _try_recurring_match(db, txn, my_user_id):
            stats["matched"] += 1
            continue

        _mark_personal(db, txn)
        stats["personal"] += 1
    db.flush()


def _try_recurring_match(db: Session, txn: BankTransaction, my_user_id: int) -> bool:
    desc_upper = txn.description.upper()
    pattern = next((p for p in RECURRING_WHITELIST if p in desc_upper), None)
    if not pattern:
        return False
    candidates = [
        e for e in _unmatched_expense_candidates(db)
        if pattern in e.description.upper()
        and e.expense_date.year == txn.post_date.year
        and e.expense_date.month == txn.post_date.month
    ]
    if len(candidates) != 1:
        return False  # none, or ambiguous - don't guess
    expense = candidates[0]
    txn.match_status = "matched"
    txn.matched_expense_id = expense.id
    expense.matched_bank_txn_id = txn.id
    _create_ledger_and_receivables(db, txn, expense, my_user_id)
    return True


# ---------------------------------------------------------------------------
# Rule 4: settlement detection on credit transactions
# ---------------------------------------------------------------------------

def _find_pair_matching_sum(receivables: list[Receivable], amount: float):
    by_person: dict[int, list[Receivable]] = {}
    for r in receivables:
        by_person.setdefault(r.debtor_user_id, []).append(r)
    for person_receivables in by_person.values():
        if len(person_receivables) < 2:
            continue
        for a, b in combinations(person_receivables, 2):
            if abs((a.amount + b.amount) - amount) <= SETTLEMENT_AMOUNT_TOLERANCE:
                return [a, b]
    return None


def _settle_receivable(db: Session, receivable: Receivable, settled_date: date,
                        via: str, bank_txn_id: str | None = None) -> None:
    receivable.settled = True
    receivable.settled_date = settled_date
    receivable.settled_via = via
    receivable.settled_bank_txn_id = bank_txn_id


def _match_credit_transactions(db: Session, stats: dict) -> None:
    unmatched = (
        db.query(BankTransaction)
        .filter(BankTransaction.direction == "credit", BankTransaction.match_status == "unmatched")
        .order_by(BankTransaction.post_date)
        .all()
    )
    for txn in unmatched:
        open_receivables = db.query(Receivable).filter(Receivable.settled.is_(False)).all()

        single = next(
            (r for r in open_receivables if abs(r.amount - txn.amount) <= SETTLEMENT_AMOUNT_TOLERANCE),
            None,
        )
        settled_group = None
        if single:
            settled_group = [single]
        else:
            pair = _find_pair_matching_sum(open_receivables, txn.amount)
            if pair:
                settled_group = pair

        if not settled_group:
            continue  # salary etc - leave unmatched, don't guess

        for r in settled_group:
            _settle_receivable(db, r, txn.post_date, "bank_credit", bank_txn_id=txn.id)
        txn.match_status = "reimbursement"
        _upsert_ledger_entry(
            db, bank_txn_id=txn.id, expense_id=None, date=txn.post_date,
            merchant=txn.description, raw_amount=txn.amount, true_amount=0.0,
            category="reimbursement", people_count=1,
        )
        stats["settled_bank"] += 1
    db.flush()


# ---------------------------------------------------------------------------
# Rule 5: Splitwise-side settlements (payment=True expenses)
# ---------------------------------------------------------------------------

def _match_splitwise_settlements(db: Session, stats: dict, my_user_id: int) -> None:
    payments = db.query(SplitwiseExpense).filter(
        SplitwiseExpense.is_payment.is_(True),
        SplitwiseExpense.deleted.is_(False),
    ).all()
    for p in payments:
        if p.your_owed_share <= 0 or not p.raw_json:
            continue  # you're not the receiver of this payment
        raw = json.loads(p.raw_json)
        payer = next(
            (u for u in raw.get("users", [])
             if u.get("user_id") != my_user_id and float(u.get("paid_share", 0)) > 0),
            None,
        )
        if not payer:
            continue
        amount_aud = to_aud(p.your_owed_share, p.currency)
        open_receivables = db.query(Receivable).filter(
            Receivable.settled.is_(False),
            Receivable.debtor_user_id == payer["user_id"],
        ).all()

        target = next(
            (r for r in open_receivables if abs(r.amount - amount_aud) <= SETTLEMENT_AMOUNT_TOLERANCE),
            None,
        )
        group = [target] if target else _find_pair_matching_sum(open_receivables, amount_aud)
        if not group:
            continue
        for r in group:
            _settle_receivable(db, r, p.expense_date, "splitwise_payment")
        stats["settled_splitwise"] += 1
    db.flush()


# ---------------------------------------------------------------------------
# Rule 6: "you're the ower" - pending_settle ledger entries
# ---------------------------------------------------------------------------

def _create_pending_settle_entries(db: Session, stats: dict) -> None:
    candidates = db.query(SplitwiseExpense).filter(
        SplitwiseExpense.deleted.is_(False),
        SplitwiseExpense.is_payment.is_(False),
        SplitwiseExpense.your_paid_share == 0,
        SplitwiseExpense.your_owed_share > 0,
    ).all()
    for e in candidates:
        exists = db.query(LedgerEntry).filter(LedgerEntry.expense_id == e.id).first()
        if exists:
            continue
        db.add(LedgerEntry(
            bank_txn_id=None, expense_id=e.id, date=e.expense_date,
            merchant=e.description, raw_amount=0.0,
            true_amount=to_aud(e.your_owed_share, e.currency),
            category="pending_settle", people_count=_people_count(e),
        ))
        stats["pending_settle"] += 1
    db.flush()


# ---------------------------------------------------------------------------
# Human review actions (used by the FastAPI PATCH /transactions/{id} route)
# ---------------------------------------------------------------------------

def confirm_flagged_match(db: Session, txn: BankTransaction, my_user_id: int) -> None:
    if txn.match_status != "flagged" or not txn.matched_expense_id:
        raise ValueError("transaction is not a pending flagged match")
    expense = db.get(SplitwiseExpense, txn.matched_expense_id)
    txn.match_status = "matched"
    _create_ledger_and_receivables(db, txn, expense, my_user_id)
    db.flush()


def settle_receivable_manual(db: Session, receivable: Receivable) -> None:
    """Used by POST /receivables/{id}/settle - 'paid me in cash' button."""
    _settle_receivable(db, receivable, date.today(), "manual")


def reject_flagged_match(db: Session, txn: BankTransaction) -> None:
    if txn.match_status != "flagged":
        raise ValueError("transaction is not a pending flagged match")
    if txn.matched_expense_id:
        expense = db.get(SplitwiseExpense, txn.matched_expense_id)
        if expense:
            expense.matched_bank_txn_id = None
    txn.matched_expense_id = None
    _mark_personal(db, txn)
    db.flush()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def sync_and_match(db: Session, bank_txns: list[dict], splitwise_expenses: list[dict],
                    my_user_id: int) -> dict:
    """Upserts fresh data then runs all rules. Safe to call repeatedly with
    overlapping data - see module docstring for idempotency guarantees."""
    stats = {
        "matched": 0, "flagged": 0, "personal": 0, "pending_settle": 0,
        "settled_bank": 0, "settled_splitwise": 0,
    }

    upsert_bank_transactions(db, bank_txns)
    upsert_splitwise_expenses(db, splitwise_expenses)

    _create_pending_settle_entries(db, stats)
    _match_debit_transactions(db, stats, my_user_id)
    _match_credit_transactions(db, stats)
    _match_splitwise_settlements(db, stats, my_user_id)

    db.commit()
    return stats
