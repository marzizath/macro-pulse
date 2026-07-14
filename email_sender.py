"""
Formats and sends the daily digest via SMTP - v2 design.

Features: dark header banner, color-coded change chips with arrows, 30-day
sparkline charts embedded inline (CID images), anomaly highlighting,
gold/silver ratio strip, markdown -> HTML conversion for the AI digest,
mobile-friendly 620px layout.
"""
import io
import os
import html
import smtplib
import markdown as md
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --- palette ---
BG = "#f4f5f7"
CARD = "#ffffff"
INK = "#1a1d26"
MUTED = "#6b7280"
GREEN = "#0f9d58"
RED = "#d93025"
AMBER_BG = "#fff7e0"
AMBER_EDGE = "#f0b429"
HEADER_BG = "#141a2e"
ACCENT = "#f0b429"


def _sparkline_png(history: list, up: bool) -> bytes:
    """Render a tiny 30-day sparkline PNG for inline embedding."""
    color = GREEN if up else RED
    fig, ax = plt.subplots(figsize=(1.6, 0.42), dpi=150)
    ax.plot(history, color=color, linewidth=1.4)
    ax.fill_between(range(len(history)), history, min(history),
                    color=color, alpha=0.12)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return buf.getvalue()


def _chip(pct: float) -> str:
    """Colored pill showing the day's % change with an arrow."""
    if pct > 0:
        color, arrow, sign = GREEN, "&#9650;", "+"
    elif pct < 0:
        color, arrow, sign = RED, "&#9660;", ""
    else:
        color, arrow, sign = MUTED, "&#9644;", ""
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;'
        f'background:{color}18;color:{color};font-weight:700;font-size:13px;'
        f'white-space:nowrap;">{arrow} {sign}{pct}%</span>'
    )


def _mood_strip(asset_data: list) -> str:
    """One-line market mood: how many assets flagged, biggest mover."""
    valid = [a for a in asset_data if "error" not in a]
    flagged = [a for a in valid if a.get("anomaly")]
    biggest = max(valid, key=lambda a: abs(a.get("pct_change", 0)), default=None)

    if not flagged:
        mood, mood_color = "Calm - no unusual moves", GREEN
    elif len(flagged) == 1:
        mood, mood_color = f"1 asset flagged: {flagged[0]['name']}", AMBER_EDGE
    else:
        mood, mood_color = f"{len(flagged)} assets flagged", RED

    biggest_txt = ""
    if biggest:
        biggest_txt = (f'&nbsp;&nbsp;&bull;&nbsp;&nbsp;Biggest mover: '
                       f'<b>{biggest["name"]} ({biggest["pct_change"]:+}%)</b>')

    return (
        f'<div style="background:{CARD};border-radius:10px;padding:12px 16px;'
        f'margin:0 0 14px 0;font-size:13px;color:{INK};border-left:4px solid {mood_color};">'
        f'<b style="color:{mood_color};">{mood}</b>{biggest_txt}</div>'
    )


def _ratio_strip(asset_data: list) -> str:
    """Gold/Silver ratio - the fear-vs-growth gauge."""
    by_name = {a["name"]: a for a in asset_data if "error" not in a}
    gold, silver = by_name.get("Gold"), by_name.get("Silver")
    if not (gold and silver and gold.get("last_price") and silver.get("last_price")):
        return ""
    ratio = round(gold["last_price"] / silver["last_price"], 1)
    return (
        f'<div style="background:{CARD};border-radius:10px;padding:12px 16px;'
        f'margin:0 0 14px 0;font-size:13px;color:{MUTED};">'
        f'<b style="color:{INK};">Gold/Silver ratio: {ratio}</b> &mdash; '
        f'rising ratio &asymp; fear-driven market, falling &asymp; '
        f'industrial/growth-driven</div>'
    )


def _asset_rows(asset_data: list, images: dict) -> str:
    rows = ""
    for i, a in enumerate(asset_data):
        if "error" in a:
            rows += (
                f'<tr><td colspan="4" style="padding:10px 14px;color:{MUTED};'
                f'font-size:12px;">{html.escape(a["name"])} &mdash; data error: '
                f'{html.escape(a["error"])}</td></tr>'
            )
            continue

        anomaly = a.get("anomaly")
        row_bg = AMBER_BG if anomaly else CARD
        left_edge = (f'border-left:4px solid {AMBER_EDGE};' if anomaly
                     else 'border-left:4px solid transparent;')
        flag = ('<span style="font-size:11px;font-weight:700;color:#8a6d00;'
                'background:#f6e2a3;border-radius:8px;padding:2px 8px;">UNUSUAL</span>'
                if anomaly else "")

        spark = ""
        cid = f"spark{i}"
        if a.get("history") and len(a["history"]) > 2:
            images[cid] = _sparkline_png(a["history"], a["pct_change"] >= 0)
            spark = f'<img src="cid:{cid}" width="96" height="26" style="display:block;" alt="30d trend"/>'

        z = a.get("zscore")
        z_txt = (f'<span style="color:{MUTED};font-size:11px;">z {z}</span>'
                 if z is not None else "")

        rows += f"""
        <tr style="background:{row_bg};">
          <td style="padding:11px 14px;{left_edge}font-size:14px;font-weight:600;color:{INK};">
            {a['name']}<br/>{z_txt}
          </td>
          <td style="padding:11px 6px;">{spark}</td>
          <td style="padding:11px 6px;text-align:right;">{_chip(a['pct_change'])}</td>
          <td style="padding:11px 14px;text-align:right;">{flag}</td>
        </tr>
        <tr><td colspan="4" style="height:1px;background:#eceef1;"></td></tr>"""
    return rows


def _digest_html(digest_text: str) -> str:
    """Convert the AI digest's markdown to styled HTML."""
    body = md.markdown(digest_text)
    # inline-style the generated tags so email clients respect them
    body = (body
            .replace("<h1>", f'<h1 style="font-size:17px;color:{INK};margin:18px 0 8px;">')
            .replace("<h2>", f'<h2 style="font-size:15px;color:{INK};margin:16px 0 6px;">')
            .replace("<h3>", f'<h3 style="font-size:14px;color:{INK};margin:14px 0 6px;">')
            .replace("<p>", f'<p style="font-size:13.5px;line-height:1.65;color:{INK};margin:8px 0;">')
            .replace("<li>", f'<li style="font-size:13.5px;line-height:1.6;color:{INK};margin:4px 0;">')
            .replace("<strong>", f'<strong style="color:{INK};">'))
    return (
        f'<div style="background:{CARD};border-radius:10px;padding:6px 18px 14px;'
        f'margin:14px 0 0 0;">{body}</div>'
    )


def build_email_html(digest_text: str, asset_data: list, images: dict) -> str:
    """Full email HTML. `images` dict gets populated with cid -> png bytes."""
    today = date.today().strftime("%A, %d %B %Y")
    return f"""
<html><body style="margin:0;padding:0;background:{BG};">
<div style="max-width:620px;margin:0 auto;padding:18px 12px;
     font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;">

  <!-- header -->
  <div style="background:{HEADER_BG};border-radius:12px;padding:22px 22px 18px;margin-bottom:14px;">
    <div style="font-size:21px;font-weight:800;color:#ffffff;letter-spacing:0.3px;">
      &#9889; Macro Pulse
    </div>
    <div style="font-size:12.5px;color:{ACCENT};margin-top:4px;font-weight:600;">
      {today} &nbsp;&bull;&nbsp; Sydney Morning Briefing
    </div>
  </div>

  {_mood_strip(asset_data)}
  {_ratio_strip(asset_data)}

  <!-- asset table -->
  <div style="background:{CARD};border-radius:10px;overflow:hidden;">
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <tr style="background:#fafbfc;">
        <th style="text-align:left;padding:10px 14px;font-size:11px;color:{MUTED};
            text-transform:uppercase;letter-spacing:0.6px;">Asset</th>
        <th style="text-align:left;padding:10px 6px;font-size:11px;color:{MUTED};
            text-transform:uppercase;letter-spacing:0.6px;">30d trend</th>
        <th style="text-align:right;padding:10px 6px;font-size:11px;color:{MUTED};
            text-transform:uppercase;letter-spacing:0.6px;">Today</th>
        <th style="padding:10px 14px;"></th>
      </tr>
      {_asset_rows(asset_data, images)}
    </table>
  </div>

  {_digest_html(digest_text)}

  {_feedback_links(date.today().isoformat())}

  <p style="color:#9aa0aa;font-size:11px;margin-top:8px;text-align:center;line-height:1.5;">
    Informational context only &mdash; not investment advice, not a trading signal.<br/>
    Generated automatically by your Macro Pulse pipeline.
  </p>
</div>
</body></html>"""


def _feedback_links(run_date: str) -> str:
    """Two links -> pre-filled GitHub issue creation pages, so feedback lands
    somewhere the review workflow can actually read it later. Import here to
    avoid a circular import at module load time."""
    from config import GITHUB_REPO
    import urllib.parse

    def issue_url(label: str, emoji: str, prompt: str) -> str:
        title = urllib.parse.quote(f"{emoji} Feedback: {run_date}")
        body = urllib.parse.quote(
            f"Digest date: {run_date}\n\n{prompt}\n(replace this line with your note)"
        )
        return (f"https://github.com/{GITHUB_REPO}/issues/new"
                f"?labels=feedback,{label}&title={title}&body={body}")

    up_url = issue_url("feedback-positive", "\U0001F44D", "What was useful about this one?")
    down_url = issue_url("feedback-negative", "\U0001F44E", "What missed the mark?")

    return (
        f'<div style="text-align:center;margin:16px 0 4px;">'
        f'<span style="font-size:12px;color:{MUTED};">Was today\'s briefing useful? '
        f'<a href="{up_url}" style="color:{GREEN};font-weight:700;text-decoration:none;">&#128077; Yes</a>'
        f'&nbsp;&nbsp;&nbsp;'
        f'<a href="{down_url}" style="color:{RED};font-weight:700;text-decoration:none;">&#128078; No</a>'
        f'</span></div>'
    )


def send_digest(digest_text: str, asset_data: list):
    sender = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_APP_PASSWORD"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    anomalies = [a for a in asset_data if a.get("anomaly")]
    subject = f"\u26a1 Macro Pulse - {date.today().isoformat()}"
    if anomalies:
        subject += " - flagged: " + ", ".join(a["name"] for a in anomalies)

    images: dict = {}
    html = build_email_html(digest_text, asset_data, images)

    # multipart/related so inline CID images render in Gmail/Outlook
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(digest_text, "plain"))
    alt.attach(MIMEText(html, "html"))
    msg.attach(alt)

    for cid, png in images.items():
        img = MIMEImage(png, _subtype="png")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
        msg.attach(img)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
