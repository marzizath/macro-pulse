# Macro Pulse

A daily email digest that tracks gold, silver, oil (WTI + Brent), USD index,
US 10Y yield, VIX, AUD/USD, and an ASX materials proxy (BHP/RIO/FMG/NST) -
flags unusually large moves, pulls relevant news, and uses Claude to explain
what moved and why, grounded in a fixed set of known macro relationships
**plus real patterns from your own historical archive.**

**What this is:** context and education, so you're not starting from zero
every time something moves - and over time, a system that gets sharper
based on what you actually find useful.
**What this isn't:** a signal generator, a trading system, or investment
advice. It won't tell you to buy or sell anything, and its self-improvement
loop never edits itself unsupervised - see "Feedback loop" below.

## What's in this version

- **Daily email** - styled digest with sparklines, color-coded moves, and a
  market mood strip.
- **Historical archive** (`history/`) - every run is saved as JSON and
  committed back to the repo, so "last 5 times this happened" is a real
  claim, not decoration.
- **Pattern lookup** - when an asset flags, the digest checks the archive
  for past similar episodes and reports what actually followed (explicitly
  framed as pattern context, never a forecast).
- **Web dashboard** (`docs/`, deployed via GitHub Pages) - charts of every
  tracked asset over time and a log of past flagged anomalies.
- **Telegram alerts** - a short push notification, but *only* when something
  is actually flagged, so it doesn't become a second daily digest you learn
  to ignore.
- **Feedback loop** - 👍/👎 links in each email. Once you've left enough
  feedback, a monthly workflow analyzes it and *proposes* (via pull request,
  never auto-merged) an addition to the correlation knowledge base.

## How it works (pipeline order)

1. `price_data.py` - prices via yfinance, flags moves >1.5 std devs from
   that asset's own recent 20-day behaviour.
2. `news_fetcher.py` - headlines from 10 free RSS feeds (Investing.com,
   OilPrice.com, GoldSeek - no API key required).
3. `pattern_lookup.py` - scans `history/` for past episodes matching
   today's flagged assets.
4. `synthesizer.py` - sends data + headlines + pattern context + the
   correlation map (base + any learned additions) to Claude.
5. `email_sender.py` - sends the styled HTML digest with feedback links.
6. `telegram_notifier.py` - pushes an alert if anything was flagged.
7. `history_store.py` - saves today's run.
8. `dashboard_builder.py` - rebuilds `docs/index.html` from the full archive.
9. The workflow commits `history/` + `docs/` back to the repo and deploys
   the dashboard to GitHub Pages.

## Setup

### 1. Repo and secrets

Copy this folder into a new (or existing) GitHub repo, then add these repo
secrets (Settings → Secrets and variables → Actions):

| Secret | What it's for |
|---|---|
| `ANTHROPIC_API_KEY` | Digest synthesis + feedback review |
| `EMAIL_SENDER` | Gmail address sending the digest |
| `EMAIL_APP_PASSWORD` | Gmail [app password](https://myaccount.google.com/apppasswords) (needs 2FA on the account) |
| `EMAIL_RECIPIENT` | Where the digest lands |
| `TELEGRAM_BOT_TOKEN` | Optional - see below |
| `TELEGRAM_CHAT_ID` | Optional - see below |

`GITHUB_TOKEN` is provided automatically by GitHub Actions - you don't set
that one yourself.

### 2. Set your repo name in config.py

```python
GITHUB_REPO = "yourusername/macro-pulse"   # used to build the feedback links
```

### 3. Enable GitHub Pages

Settings → Pages → Source → **GitHub Actions**. That's it - the workflow
handles the rest.

### 4. Telegram bot (optional, skip if you only want email)

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` →
   follow the prompts → copy the token it gives you (`TELEGRAM_BOT_TOKEN`).
2. Send your new bot any message (so it can find your chat).
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser
   and find `"chat":{"id": ...}` in the response - that number is
   `TELEGRAM_CHAT_ID`.
4. If you'd rather not use Telegram, set `TELEGRAM_ENABLED = False` in
   `config.py` and skip the two secrets.

### 5. Test locally first

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
export EMAIL_SENDER=...
export EMAIL_APP_PASSWORD=...
export EMAIL_RECIPIENT=...
export TELEGRAM_BOT_TOKEN=...      # optional
export TELEGRAM_CHAT_ID=...        # optional
python main.py
```

Also verify the Yahoo Finance tickers still resolve (they occasionally get
renamed): `python price_data.py`.

### 6. Push to GitHub

The daily workflow runs automatically, or trigger it manually from the
Actions tab. The dashboard will be live at
`https://yourusername.github.io/macro-pulse/` after the first successful run.

## Feedback loop - how it actually works

Each email has 👍/👎 links. Clicking one opens a pre-filled GitHub issue -
you add a one-line note and submit. On the 1st of each month, a workflow:

1. Reads all issues labeled `feedback`.
2. Cross-references each one's date against `history/` to pull the actual
   digest text that prompted the feedback.
3. If there's at least 5 feedback items and 3+ negative ones pointing at the
   *same recurring gap*, asks Claude to draft one new correlation-map entry.
4. Opens a **pull request** adding that entry to `correlation_map_learned.md`
   - it does not touch `config.py`, and nothing is ever merged automatically.

You review the PR like any other code change. Merge it, edit it, or close
it. This is deliberately not a fully autonomous self-tuning system - an AI
silently rewriting its own instructions with no review step is a bad idea
regardless of how it's framed, so the human approval gate stays.

## Customizing

- **Add/remove assets:** edit `ASSETS` in `config.py`.
- **Change sensitivity:** lower `ZSCORE_THRESHOLD` to get flagged more
  often, raise it for only genuinely unusual moves.
- **Change the ASX proxy basket:** edit `ASX_MATERIALS_BASKET`.
- **Adjust pattern lookup:** `PATTERN_LOOKBACK_MAX` (episodes shown) and
  `PATTERN_FORWARD_DAYS` (how far forward each episode looks) in `config.py`.
- **Edit the correlation map directly** any time - `CORRELATION_MAP` in
  `config.py` for the base list, `correlation_map_learned.md` for additions.

## Honest limitations

- yfinance data can lag a few minutes and occasionally has gaps around
  market holidays - this is directional context, not a live feed.
- Z-score anomaly detection is a statistical heuristic. A quiet 1.6-std-dev
  move can get flagged while a genuinely significant slow-burn trend won't,
  since it doesn't show up as a single-day spike.
- **Pattern lookup is only as good as the archive's age.** In the first few
  weeks there won't be enough history for meaningful patterns - the digest
  will say so explicitly rather than padding with a false sense of history.
  A handful of episodes is never a statistically robust sample; treat the
  pattern notes as "here's what happened before," not "here's what will
  happen now."
- RSS feeds return recent headlines, not a guarantee the *right* headline
  for a price move is in there - the digest says so when it can't find a
  clear driver.
- This is not a replacement for professional financial advice. Treat it as
  a well-organized, increasingly well-informed morning briefing - not a
  decision-maker.
