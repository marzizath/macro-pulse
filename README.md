# Macro Pulse

A daily email digest that tracks gold, silver, oil (WTI + Brent), USD index,
US 10Y yield, VIX, AUD/USD, and an ASX materials proxy (BHP/RIO/FMG/NST) -
flags unusually large moves, pulls relevant news, and uses Claude to explain
what moved and why, grounded in a fixed set of known macro relationships.

**What this is:** context and education, so you're not starting from zero
every time something moves.
**What this isn't:** a signal generator, a trading system, or investment
advice. It won't tell you to buy or sell anything.

## How it works

1. `price_data.py` — pulls prices via yfinance, flags a move if it's >1.5
   standard deviations from that asset's own recent 20-day behaviour.
2. `news_fetcher.py` — pulls headlines from 10 free RSS feeds (Investing.com,
   OilPrice.com, GoldSeek — no API key, no rate-limit surprises).
3. `synthesizer.py` — sends the data + headlines to Claude along with a fixed
   correlation map (Hormuz→oil→inflation→gold/USD, DXY↔commodities, China
   demand→AUD, EOFY effects, etc.) so the explanation stays grounded instead
   of freelancing.
4. `email_sender.py` — sends you a daily HTML email with a data table + the
   plain-English digest.
5. `.github/workflows/macro-pulse.yml` — runs it daily at 7am Sydney time
   (see the DST note in the workflow file).

## Setup

1. **Copy this folder into a new (or existing) GitHub repo.**

2. **Add these repo secrets** (Settings → Secrets and variables → Actions):
   - `ANTHROPIC_API_KEY` — your Anthropic API key
   - `EMAIL_SENDER` — the Gmail address sending the digest
   - `EMAIL_APP_PASSWORD` — a Gmail [app password](https://myaccount.google.com/apppasswords)
     (not your normal password — needs 2FA enabled on the account)
   - `EMAIL_RECIPIENT` — where the digest should land (can be the same address)

   If you'd rather use a different email provider/method (e.g. whatever you
   used for the portfolio report), swap the internals of `email_sender.py` -
   `main.py` doesn't need to change.

3. **Test locally first** (recommended before trusting the cron job):
   ```bash
   pip install -r requirements.txt
   export ANTHROPIC_API_KEY=...
   export EMAIL_SENDER=...
   export EMAIL_APP_PASSWORD=...
   export EMAIL_RECIPIENT=...
   python main.py
   ```

4. **Verify the Yahoo Finance tickers still resolve.** Ticker symbols on
   Yahoo occasionally get renamed. Quick check:
   ```bash
   python price_data.py
   ```
   If any asset returns an `error`, check the ticker on finance.yahoo.com and
   update `config.py`.

5. Push to GitHub. The workflow runs daily automatically, or trigger it
   manually from the Actions tab (`workflow_dispatch`).

## Customizing

- **Add/remove assets:** edit `ASSETS` in `config.py`.
- **Change sensitivity:** lower `ZSCORE_THRESHOLD` to get flagged more often,
  raise it to only hear about genuinely unusual moves.
- **Change the ASX proxy basket:** edit `ASX_MATERIALS_BASKET`.
- **Extend the correlation map:** add to `CORRELATION_MAP` in `config.py` as
  you learn which relationships you actually find useful — the AI synthesis
  step only uses what's in that list, so it won't drift into speculation.

## Honest limitations

- yfinance data can lag a few minutes and occasionally has gaps around
  market holidays — this is directional context, not a live feed.
- The z-score anomaly detection is a statistical heuristic, not a judgment
  call about what's "important." A quiet 1.6-std-dev move can get flagged
  while a genuinely significant slow-burn trend won't, because it doesn't
  show up as a single-day spike.
- RSS feeds return recent headlines, not a guarantee that the *right*
  headline for a given price move is in there — the digest will say so when
  it can't find a clear driver, rather than inventing one.
- This is not a replacement for professional financial advice. Treat it as
  a well-organized morning briefing, not a decision-maker.
