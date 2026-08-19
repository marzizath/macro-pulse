"""
Daily digest - email (full) + Telegram (nudge only), reusing the Macro
Pulse patterns (plain SMTP + Telegram Bot API, no extra dependencies).

Spec section 8 format:

    NET RECONCILER — Wed 20 Aug
    True spend yesterday: $46.10 (bank saw $184.50)
    Open receivables: $240.40 across 3 people
    ⚠ 1 flagged match needs review
    ⏰ Priya owes $68.00 — 9 days open

Nudge rule: a receivable open longer than RECEIVABLE_NUDGE_DAYS gets its own
highlighted line. Telegram only fires when there's something that actually
needs a look (a flag, or a stale receivable) - same "stay quiet on calm
days" philosophy as telegram_notifier.py in the parent Macro Pulse project.
"""
import json
import smtplib
import urllib.parse
import urllib.request
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.config import (
    EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_RECIPIENT, SMTP_HOST, SMTP_PORT,
    TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, RECEIVABLE_NUDGE_DAYS,
)
from app.models import BankTransaction, LedgerEntry, Receivable

TELEGRAM_API_BASE = "https://api.telegram.org"


def build_digest(db: Session) -> dict:
    yesterday = date.today() - timedelta(days=1)

    debits = db.query(BankTransaction).filter(
        BankTransaction.direction == "debit", BankTransaction.post_date == yesterday,
    ).all()
    raw_yesterday = round(sum(t.amount for t in debits), 2)

    ledger_yesterday = db.query(LedgerEntry).filter(LedgerEntry.date == yesterday).all()
    true_yesterday = round(sum(e.true_amount for e in ledger_yesterday), 2)

    open_receivables = db.query(Receivable).filter(Receivable.settled.is_(False)).all()
    open_total = round(sum(r.amount for r in open_receivables), 2)
    debtor_count = len({r.debtor_user_id for r in open_receivables})

    flagged_count = db.query(BankTransaction).filter(BankTransaction.match_status == "flagged").count()

    stale = [
        r for r in open_receivables
        if (date.today() - r.opened_date).days > RECEIVABLE_NUDGE_DAYS
    ]
    stale.sort(key=lambda r: r.opened_date)  # longest-open first

    return {
        "raw_yesterday": raw_yesterday, "true_yesterday": true_yesterday,
        "open_total": open_total, "debtor_count": debtor_count,
        "flagged_count": flagged_count, "stale": stale,
        "has_activity": bool(debits or ledger_yesterday or open_receivables or flagged_count),
    }


def _plain_text(digest: dict) -> str:
    today_label = date.today().strftime("%a %d %b")
    lines = [f"NET RECONCILER — {today_label}"]
    lines.append(f"True spend yesterday: ${digest['true_yesterday']:.2f} "
                 f"(bank saw ${digest['raw_yesterday']:.2f})")
    if digest["debtor_count"]:
        lines.append(f"Open receivables: ${digest['open_total']:.2f} across "
                     f"{digest['debtor_count']} people")
    if digest["flagged_count"]:
        lines.append(f"⚠ {digest['flagged_count']} flagged match"
                     f"{'es' if digest['flagged_count'] != 1 else ''} need review")
    for r in digest["stale"]:
        days = (date.today() - r.opened_date).days
        lines.append(f"⏰ {r.debtor_name} owes ${r.amount:.2f} — {days} days open")
    return "\n".join(lines)


def send_digest(db: Session) -> str | None:
    """Returns the digest text if sent, None if skipped (nothing to say)."""
    digest = build_digest(db)
    if not digest["has_activity"]:
        return None

    text = _plain_text(digest)
    _send_email(text)
    if digest["flagged_count"] or digest["stale"]:
        _send_telegram(text)
    return text


def _send_email(text: str) -> None:
    if not (EMAIL_SENDER and EMAIL_APP_PASSWORD and EMAIL_RECIPIENT):
        print("Email digest skipped: EMAIL_SENDER / EMAIL_APP_PASSWORD / EMAIL_RECIPIENT not set.")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Net Reconciler — {date.today().isoformat()}"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT
    msg.attach(MIMEText(text, "plain"))
    html = "<pre style='font-family:monospace;font-size:14px;'>" + text.replace("\n", "<br/>") + "</pre>"
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
    except Exception as e:
        print(f"Email digest failed: {e}")


def _send_telegram(text: str) -> None:
    if not TELEGRAM_ENABLED:
        return
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("Telegram nudge skipped: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set.")
        return
    url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                print(f"Telegram API returned an error: {result}")
    except Exception as e:
        print(f"Telegram nudge failed (non-fatal, email still sent): {e}")
