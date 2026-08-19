"""
Unit tests for the matching engine (app/services/matcher.py).

Two layers:
  - test_fixture_sync_end_to_end: runs the full engine over the realistic
    15-transaction / 9-expense demo fixtures (bank_sample.json +
    splitwise_sample.json) and sanity-checks the overall shape of the result.
  - Everything else: focused unit tests, one per hard requirement / edge
    case listed in spec sections 4 and 10, built from small inline payloads
    so each test is self-contained and its intent is obvious.
"""
from datetime import date

from app.models import BankTransaction, SplitwiseExpense, Receivable, LedgerEntry
from app.services import matcher
from app.services.basiq_client import to_domain_transaction
from app.services.splitwise_client import to_domain_expense

MY_USER_ID = 10001
FRIEND_A = 20001
FRIEND_B = 20002


# ---------------------------------------------------------------------------
# Builders - go through the same normalization the real clients use.
# ---------------------------------------------------------------------------

def bank_txn(id, description, amount, post_date, account_name="Test Account"):
    """amount: negative = debit, positive = credit (mirrors Basiq's convention)."""
    raw = {
        "id": id, "description": description, "amount": str(amount),
        "postDate": post_date, "account": {"name": account_name},
    }
    return to_domain_transaction(raw)


def expense(id, description, cost, expense_date, my_paid, my_owed,
            other_user_id=FRIEND_A, other_paid=0.0, other_owed=None,
            currency="AUD", is_payment=False, deleted=False,
            other_name="Friend"):
    if other_owed is None:
        other_owed = my_owed  # simple 2-way even split by default
    raw = {
        "id": id, "description": description, "cost": str(cost),
        "currency_code": currency, "date": f"{expense_date}T12:00:00Z",
        "deleted_at": "2026-01-01T00:00:00Z" if deleted else None,
        "payment": is_payment,
        "users": [
            {"user_id": MY_USER_ID, "paid_share": str(my_paid), "owed_share": str(my_owed),
             "first_name": "Me", "last_name": ""},
            {"user_id": other_user_id, "paid_share": str(other_paid), "owed_share": str(other_owed),
             "first_name": other_name, "last_name": ""},
        ],
    }
    return to_domain_expense(raw, MY_USER_ID)


def ledger_categories(db):
    return [e.category for e in db.query(LedgerEntry).all()]


# ---------------------------------------------------------------------------
# End-to-end fixture sanity check
# ---------------------------------------------------------------------------

def test_fixture_sync_end_to_end(db, bank_sample, splitwise_sample):
    stats = matcher.sync_and_match(db, bank_sample, splitwise_sample, MY_USER_ID)

    assert stats["matched"] >= 2          # Mecca (exact) + Netflix (recurring)
    assert stats["flagged"] >= 2          # Thai surcharge + ambiguous dinners
    assert stats["settled_bank"] >= 2     # Priya bank transfer + rent pending-settle
    assert stats["personal"] >= 4

    # The deleted "Cancelled brunch" expense must never be matchable.
    deleted = db.get(SplitwiseExpense, "90008")
    assert deleted.deleted is True
    assert deleted.matched_bank_txn_id is None

    # The Splitwise payment record must never produce a ledger entry.
    payment_expense_id = "90009"
    assert db.query(LedgerEntry).filter(LedgerEntry.expense_id == payment_expense_id).count() == 0

    # Priya's receivable from Mecca Bar was settled by the matching bank credit.
    priya_receivables = db.query(Receivable).filter(Receivable.debtor_user_id == 10002).all()
    assert any(r.settled and r.settled_via == "bank_credit" for r in priya_receivables)

    # Re-running with the same data must not change any counts (idempotency).
    db2_stats_before = {
        "txns": db.query(BankTransaction).count(),
        "ledger": db.query(LedgerEntry).count(),
        "receivables": db.query(Receivable).count(),
    }
    matcher.sync_and_match(db, bank_sample, splitwise_sample, MY_USER_ID)
    assert db.query(BankTransaction).count() == db2_stats_before["txns"]
    assert db.query(LedgerEntry).count() == db2_stats_before["ledger"]
    assert db.query(Receivable).count() == db2_stats_before["receivables"]


# ---------------------------------------------------------------------------
# Rule 1: exact match
# ---------------------------------------------------------------------------

def test_exact_match(db):
    txns = [bank_txn("t1", "MECCA BAR", -120.00, "2026-08-03")]
    exps = [expense("e1", "Mecca Bar dinner", 120.00, "2026-08-03", 120.00, 60.00)]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    assert txn.match_status == "matched"
    assert txn.matched_expense_id == "e1"

    entry = db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t1").one()
    assert entry.category == "shared_matched"
    assert entry.true_amount == 60.00

    receivable = db.query(Receivable).filter(Receivable.expense_id == "e1").one()
    assert receivable.debtor_user_id == FRIEND_A
    assert receivable.amount == 60.00
    assert receivable.settled is False


# ---------------------------------------------------------------------------
# Rule 2: surcharge-tolerant match -> flagged, never auto-committed
# ---------------------------------------------------------------------------

def test_surcharge_match_is_flagged_not_matched(db):
    txns = [bank_txn("t1", "THAI GARDEN RESTAURANT", -152.30, "2026-08-08")]
    exps = [expense("e1", "Thai Garden Restaurant", 150.00, "2026-08-06", 150.00, 75.00)]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    assert txn.match_status == "flagged"
    assert txn.matched_expense_id == "e1"

    # Flagged items must never hit the ledger or create receivables until confirmed.
    assert db.query(LedgerEntry).filter(LedgerEntry.category == "shared_matched").count() == 0
    assert db.query(Receivable).count() == 0


def test_surcharge_match_requires_word_overlap(db):
    """Amount within 5% but no words in common -> must NOT flag a match;
    falls through to personal instead."""
    txns = [bank_txn("t1", "RANDOM MERCHANT XYZ", -152.30, "2026-08-08")]
    exps = [expense("e1", "Completely unrelated purchase", 150.00, "2026-08-08", 150.00, 75.00)]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    assert txn.match_status == "personal"


def test_confirm_flagged_match_commits_ledger_and_receivable(db):
    txns = [bank_txn("t1", "THAI GARDEN RESTAURANT", -152.30, "2026-08-08")]
    exps = [expense("e1", "Thai Garden Restaurant", 150.00, "2026-08-06", 150.00, 75.00)]
    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    matcher.confirm_flagged_match(db, txn, MY_USER_ID)

    assert txn.match_status == "matched"
    entry = db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t1").one()
    assert entry.true_amount == 75.00
    assert db.query(Receivable).filter(Receivable.expense_id == "e1").count() == 1


def test_reject_flagged_match_falls_back_to_personal_and_frees_expense(db):
    txns = [bank_txn("t1", "THAI GARDEN RESTAURANT", -152.30, "2026-08-08")]
    exps = [expense("e1", "Thai Garden Restaurant", 150.00, "2026-08-06", 150.00, 75.00)]
    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    matcher.reject_flagged_match(db, txn)

    assert txn.match_status == "personal"
    assert txn.matched_expense_id is None
    entry = db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t1").one()
    assert entry.true_amount == 152.30
    assert entry.category == "personal"

    # The expense is freed up for a future sync to reconsider.
    freed = db.get(SplitwiseExpense, "e1")
    assert freed.matched_bank_txn_id is None


# ---------------------------------------------------------------------------
# No match -> personal
# ---------------------------------------------------------------------------

def test_no_match_goes_personal(db):
    txns = [bank_txn("t1", "BUNNINGS WAREHOUSE", -34.20, "2026-08-06")]
    matcher.sync_and_match(db, txns, [], MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    assert txn.match_status == "personal"
    entry = db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t1").one()
    assert entry.true_amount == 34.20
    assert entry.category == "personal"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_double_run_idempotency(db):
    txns = [bank_txn("t1", "MECCA BAR", -120.00, "2026-08-03")]
    exps = [expense("e1", "Mecca Bar dinner", 120.00, "2026-08-03", 120.00, 60.00)]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)
    matcher.sync_and_match(db, txns, exps, MY_USER_ID)
    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    assert db.query(BankTransaction).count() == 1
    assert db.query(SplitwiseExpense).count() == 1
    assert db.query(LedgerEntry).count() == 1
    assert db.query(Receivable).count() == 1


# ---------------------------------------------------------------------------
# Rule 4: settlement detection (single + combined)
# ---------------------------------------------------------------------------

def test_settlement_exact_single_receivable(db):
    txns = [
        bank_txn("t1", "MECCA BAR", -120.00, "2026-08-03"),
        bank_txn("t2", "TRANSFER FROM FRIEND", 60.00, "2026-08-06"),
    ]
    exps = [expense("e1", "Mecca Bar dinner", 120.00, "2026-08-03", 120.00, 60.00)]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    receivable = db.query(Receivable).filter(Receivable.expense_id == "e1").one()
    assert receivable.settled is True
    assert receivable.settled_via == "bank_credit"
    assert receivable.settled_bank_txn_id == "t2"

    credit_txn = db.get(BankTransaction, "t2")
    assert credit_txn.match_status == "reimbursement"
    entry = db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t2").one()
    assert entry.true_amount == 0.0
    assert entry.category == "reimbursement"


def test_settlement_combined_two_receivables(db):
    txns = [
        bank_txn("t1", "GROCERIES SPLIT", -90.00, "2026-07-20"),
        bank_txn("t2", "MOVIE TICKETS", -40.00, "2026-07-25"),
        bank_txn("t3", "PAYID TRANSFER FRIEND", 50.00, "2026-08-09"),
    ]
    exps = [
        expense("e1", "Housemate groceries", 90.00, "2026-07-20", 90.00, 30.00,
                other_owed=30.00),
        expense("e2", "Movie tickets", 40.00, "2026-07-25", 40.00, 20.00,
                other_owed=20.00),
    ]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    receivables = db.query(Receivable).filter(Receivable.debtor_user_id == FRIEND_A).all()
    assert len(receivables) == 2
    assert all(r.settled and r.settled_via == "bank_credit" and r.settled_bank_txn_id == "t3"
               for r in receivables)


def test_unmatched_credit_is_ignored_not_guessed(db):
    """Salary or any credit that doesn't match an open receivable (alone or
    paired) must be left unmatched - never guessed at."""
    txns = [bank_txn("t1", "SALARY XYZ CORP", 3450.00, "2026-08-15")]
    matcher.sync_and_match(db, txns, [], MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    assert txn.match_status == "unmatched"
    assert db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t1").count() == 0


# ---------------------------------------------------------------------------
# Rule 5: Splitwise-side settlement, and payments never counting as spend
# ---------------------------------------------------------------------------

def test_splitwise_payment_settles_receivable_and_never_counts_as_spend(db):
    txns = [bank_txn("t1", "MECCA BAR", -120.00, "2026-08-01")]
    exps = [
        expense("e1", "Mecca Bar dinner", 120.00, "2026-08-01", 120.00, 60.00),
        expense("e2", "Payment from friend", 60.00, "2026-08-05", 0.00, 60.00,
                other_paid=60.00, other_owed=0.00, is_payment=True),
    ]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    receivable = db.query(Receivable).filter(Receivable.expense_id == "e1").one()
    assert receivable.settled is True
    assert receivable.settled_via == "splitwise_payment"

    # The payment expense itself must never appear in the ledger.
    assert db.query(LedgerEntry).filter(LedgerEntry.expense_id == "e2").count() == 0
    # And must never be a matchable candidate.
    assert matcher._unmatched_expense_candidates(db) == []


def test_bank_credit_and_splitwise_payment_for_same_debt_do_not_double_settle(db):
    """Both channels can report the same repayment; only one settlement
    should ever be recorded, and the second must be a safe no-op."""
    txns = [
        bank_txn("t1", "MECCA BAR", -120.00, "2026-08-01"),
        bank_txn("t2", "TRANSFER FROM FRIEND", 60.00, "2026-08-06"),
    ]
    exps = [
        expense("e1", "Mecca Bar dinner", 120.00, "2026-08-01", 120.00, 60.00),
        expense("e2", "Payment from friend", 60.00, "2026-08-06", 0.00, 60.00,
                other_paid=60.00, other_owed=0.00, is_payment=True),
    ]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    receivables = db.query(Receivable).filter(Receivable.expense_id == "e1").all()
    assert len(receivables) == 1
    r = receivables[0]
    assert r.settled is True
    assert r.settled_via == "bank_credit"  # bank credit is processed before the splitwise-payment pass


# ---------------------------------------------------------------------------
# Deleted expense
# ---------------------------------------------------------------------------

def test_deleted_expense_is_never_matched(db):
    txns = [bank_txn("t1", "CANCELLED BRUNCH", -55.00, "2026-08-07")]
    exps = [expense("e1", "Cancelled brunch", 55.00, "2026-08-07", 55.00, 27.50, deleted=True)]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    assert txn.match_status == "personal"
    assert db.query(Receivable).count() == 0


def test_expense_deleted_after_being_matched_reverts_ledger(db):
    txns = [bank_txn("t1", "MECCA BAR", -120.00, "2026-08-03")]
    exps = [expense("e1", "Mecca Bar dinner", 120.00, "2026-08-03", 120.00, 60.00)]
    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    assert db.get(BankTransaction, "t1").match_status == "matched"

    # Next sync: same expense id comes back marked deleted, and no bank data
    # is re-supplied this round (simulates a Splitwise-only sync tick).
    exps_deleted = [expense("e1", "Mecca Bar dinner", 120.00, "2026-08-03", 120.00, 60.00, deleted=True)]
    matcher.sync_and_match(db, [], exps_deleted, MY_USER_ID)

    # The old match is reverted - no trace of it links to the deleted expense.
    assert db.query(LedgerEntry).filter(LedgerEntry.expense_id == "e1").count() == 0
    assert db.query(Receivable).filter(Receivable.expense_id == "e1", Receivable.settled.is_(False)).count() == 0

    # The freed-up transaction is immediately re-evaluated in the same sync:
    # with no valid candidate left, it correctly falls back to personal
    # spend rather than sitting in limbo.
    txn = db.get(BankTransaction, "t1")
    assert txn.match_status == "personal"
    assert txn.matched_expense_id is None
    entry = db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t1").one()
    assert entry.category == "personal"
    assert entry.true_amount == 120.00


# ---------------------------------------------------------------------------
# "You're the ower" - pending_settle, and not double counting on settlement
# ---------------------------------------------------------------------------

def test_ower_case_creates_pending_settle_immediately(db):
    """Expense where you didn't front the money still counts as true spend
    the moment it appears, via a pending_settle ledger entry."""
    exps = [expense("e1", "Ski trip lift passes", 90.00, "2026-08-05", 0.00, 90.00,
                     other_paid=90.00, other_owed=0.00)]

    matcher.sync_and_match(db, [], exps, MY_USER_ID)

    entry = db.query(LedgerEntry).filter(LedgerEntry.expense_id == "e1").one()
    assert entry.category == "pending_settle"
    assert entry.true_amount == 90.00
    assert entry.bank_txn_id is None


def test_ower_case_later_settling_debit_does_not_double_count(db):
    exps = [expense("e1", "Ski trip lift passes", 90.00, "2026-08-05", 0.00, 90.00,
                     other_paid=90.00, other_owed=0.00)]
    matcher.sync_and_match(db, [], exps, MY_USER_ID)

    # Weeks later I pay my friend back.
    txns = [bank_txn("t1", "TRANSFER TO FRIEND", -90.00, "2026-08-20")]
    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    settling_txn = db.get(BankTransaction, "t1")
    assert settling_txn.match_status == "reimbursement"
    assert settling_txn.matched_expense_id == "e1"

    # Still exactly one ledger entry for this expense, still $90 - not $180.
    entries = db.query(LedgerEntry).filter(LedgerEntry.expense_id == "e1").all()
    assert len(entries) == 1
    assert entries[0].true_amount == 90.00
    assert entries[0].bank_txn_id == "t1"

    # And the settling debit must NOT also appear as a personal expense.
    assert db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t1",
                                         LedgerEntry.category == "personal").count() == 0


# ---------------------------------------------------------------------------
# Multi-currency
# ---------------------------------------------------------------------------

def test_multi_currency_expense_converted_to_aud(db):
    # INR trip: cost 5000 INR, static rate 0.0182 -> 91.00 AUD.
    inr_rate = matcher.STATIC_FX_TO_AUD["INR"]
    txns = [bank_txn("t1", "INDIA TRIP HOTEL", -round(5000 * inr_rate, 2), "2026-08-03")]
    exps = [expense("e1", "Hotel in Mumbai", 5000.00, "2026-08-03", 5000.00, 2500.00, currency="INR")]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    assert txn.match_status == "matched"
    entry = db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t1").one()
    assert entry.true_amount == matcher.to_aud(2500.00, "INR")

    # Original values are preserved on the expense row for reference.
    expense_row = db.get(SplitwiseExpense, "e1")
    assert expense_row.currency == "INR"
    assert expense_row.total_cost == 5000.00


# ---------------------------------------------------------------------------
# Ambiguity: never guess
# ---------------------------------------------------------------------------

def test_two_identical_amount_expenses_same_week_are_flagged_not_guessed(db):
    txns = [bank_txn("t1", "DINNER PAYMENT", -60.00, "2026-08-10")]
    exps = [
        expense("e1", "Dinner with friends A", 60.00, "2026-08-09", 60.00, 30.00),
        expense("e2", "Dinner with friends B", 60.00, "2026-08-11", 60.00, 30.00,
                other_user_id=FRIEND_B),
    ]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    txn = db.get(BankTransaction, "t1")
    assert txn.match_status == "flagged"
    assert txn.matched_expense_id is None  # ambiguous - no guess

    # Neither candidate should be reserved; both remain available.
    for eid in ("e1", "e2"):
        assert db.get(SplitwiseExpense, eid).matched_bank_txn_id is None
    assert db.query(Receivable).count() == 0


# ---------------------------------------------------------------------------
# Ower case: you're not always the payer (paid_share == 0)
# ---------------------------------------------------------------------------

def test_expense_where_you_are_the_ower_not_payer_never_creates_receivable(db):
    exps = [expense("e1", "Concert tickets", 200.00, "2026-08-05", 0.00, 100.00,
                     other_paid=200.00, other_owed=0.00)]
    matcher.sync_and_match(db, [], exps, MY_USER_ID)

    # No receivable is ever created for an expense you didn't front.
    assert db.query(Receivable).count() == 0


# ---------------------------------------------------------------------------
# Basiq pending -> posted dedupe (same id, amount/description refined)
# ---------------------------------------------------------------------------

def test_pending_transaction_dedupes_on_posting_by_id(db):
    pending = [bank_txn("t1", "CARD AUTH PENDING", -50.10, "2026-08-10")]
    matcher.sync_and_match(db, pending, [], MY_USER_ID)
    assert db.get(BankTransaction, "t1").match_status == "personal"

    posted = [bank_txn("t1", "WOOLWORTHS 2145", -50.00, "2026-08-10")]
    matcher.sync_and_match(db, posted, [], MY_USER_ID)

    assert db.query(BankTransaction).count() == 1
    txn = db.get(BankTransaction, "t1")
    assert txn.amount == 50.00
    assert txn.description == "WOOLWORTHS 2145"
    # A human-reviewed status must survive the refresh.
    assert txn.match_status == "personal"
    assert db.query(LedgerEntry).filter(LedgerEntry.bank_txn_id == "t1").count() == 1


# ---------------------------------------------------------------------------
# One-to-one matching guarantee
# ---------------------------------------------------------------------------

def test_expense_matches_at_most_one_bank_transaction(db):
    txns = [
        bank_txn("t1", "MECCA BAR", -120.00, "2026-08-03"),
        bank_txn("t2", "MECCA BAR", -120.00, "2026-08-04"),
    ]
    exps = [expense("e1", "Mecca Bar dinner", 120.00, "2026-08-03", 120.00, 60.00)]

    matcher.sync_and_match(db, txns, exps, MY_USER_ID)

    t1, t2 = db.get(BankTransaction, "t1"), db.get(BankTransaction, "t2")
    matched = [t for t in (t1, t2) if t.match_status == "matched"]
    assert len(matched) == 1
    assert db.query(LedgerEntry).filter(LedgerEntry.category == "shared_matched").count() == 1


# ---------------------------------------------------------------------------
# Manual settle (cash) - used by POST /receivables/{id}/settle
# ---------------------------------------------------------------------------

def test_manual_settle_marks_receivable_settled(db):
    exps = [expense("e1", "Mecca Bar dinner", 120.00, "2026-08-03", 120.00, 60.00)]
    matcher.sync_and_match(db, [], exps, MY_USER_ID)
    matcher._create_receivables_for_others(db, db.get(SplitwiseExpense, "e1"), MY_USER_ID)
    db.commit()

    receivable = db.query(Receivable).filter(Receivable.expense_id == "e1").one()
    matcher.settle_receivable_manual(db, receivable)
    db.commit()

    assert receivable.settled is True
    assert receivable.settled_via == "manual"
