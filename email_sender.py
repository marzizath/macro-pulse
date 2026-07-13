"""
Formats and sends the daily digest via SMTP. Defaults to Gmail's SMTP with an
app password - the common pattern for GitHub Actions email automations. Swap
this out if your other projects (portfolio report, swing-scanner) already use
a different email method - easy to line them all up.
"""
import os
import html
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date


def send_digest(digest_text: str, asset_data: list):
    sender = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_APP_PASSWORD"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    anomalies = [a for a in asset_data if a.get("anomaly")]
    subject = f"Macro Pulse - {date.today().isoformat()}"
    if anomalies:
        subject += " - flagged: " + ", ".join(a["name"] for a in anomalies)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(digest_text, "plain"))
    msg.attach(MIMEText(_build_html(digest_text, asset_data), "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())


def _build_html(digest_text: str, asset_data: list) -> str:
    rows = ""
    for a in asset_data:
        name = html.escape(a["name"])
        if "error" in a:
            rows += f"<tr><td>{name}</td><td colspan='3'>data error: {html.escape(a['error'])}</td></tr>"
            continue
        flag = "⚠️" if a.get("anomaly") else ""
        z = a.get("zscore")
        z_display = z if z is not None else "—"
        rows += (
            f"<tr><td>{name}</td><td>{a['pct_change']}%</td>"
            f"<td>{z_display}</td><td>{flag}</td></tr>"
        )

    return f"""
    <html><body style="font-family: Arial, sans-serif; color: #222;">
    <h2>Macro Pulse — {date.today().isoformat()}</h2>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">
      <tr style="background:#f0f0f0;">
        <th>Asset</th><th>1-day change</th><th>Z-score</th><th>Flag</th>
      </tr>
      {rows}
    </table>
    <div style="white-space: pre-wrap; margin-top: 20px; line-height: 1.5;">{html.escape(digest_text)}</div>
    <p style="color: #888; font-size: 12px; margin-top: 30px;">
      Informational context only — not investment advice, not a trading signal.
    </p>
    </body></html>
    """
