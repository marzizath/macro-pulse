# Net Reconciler

Fully automated true-spend tracking that reconciles bank transactions against
Splitwise, with a web dashboard. See the original build spec for the full
design rationale; this README covers how to actually run it.

**Stack:** Python (FastAPI) · React + Vite · SQLite · GitHub Actions · Basiq
(bank feed) · Splitwise API.

## Status

- **Phase 1 (matching engine + Splitwise, fixture bank data):** done. The
  engine in `backend/app/services/matcher.py` implements all 6 rules (exact
  match, surcharge-tolerant match, recurring whitelist, settlement
  detection, Splitwise-side settlement, and the "you're the ower"
  pending-settle case) plus every edge case from the spec's checklist -
  see `backend/tests/test_matcher.py` (26 tests, all passing).
- **Phase 2 (Basiq):** client is implemented (`basiq_client.py`) with the
  same `DATA_SOURCE=fixture|basiq` switch the spec calls for, but it's
  untested against a live Basiq sandbox/production account - you'll need to
  create a Basiq app and set `BASIQ_API_KEY`/`BASIQ_USER_ID` to exercise it.
- **Phase 3 (FastAPI):** done - all routes from the spec, bearer auth, CORS.
- **Phase 4 (dashboard):** done - dark theme, PWA manifest, all four
  components, wired to the API.
- **Phase 5 (deploy + automate):** scaffolded (`fly.toml`, `backend/Dockerfile`,
  `.github/workflows/daily-sync.yml`) but not deployed - that needs your own
  Fly.io/Vercel accounts and secrets.

## Repo layout

```
net-reconciler/
├── .github/workflows/daily-sync.yml   Cron sync + digest (also manually runnable)
├── backend/
│   ├── app/                           FastAPI app, models, services
│   ├── tests/                         pytest suite + fixtures
│   ├── run_sync.py                    Entrypoint used by cron / Actions
│   └── Dockerfile
├── frontend/                          React + Vite dashboard (PWA)
├── fly.toml                           Backend deploy config
└── .env.example                       Copy to backend/.env
```

## Running it locally

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # DATA_SOURCE=fixture works with no API keys at all
uvicorn app.main:app --reload
```

Hit `POST /sync` (or run `python run_sync.py`) to pull data and run the
matcher. With `DATA_SOURCE=fixture` (the default) this replays
`backend/tests/fixtures/bank_sample.json` instead of calling Basiq, so you
can see the whole pipeline work with zero external accounts. Splitwise still
needs a real `SPLITWISE_API_KEY` for `/sync` to run end-to-end; the matcher
itself is fully covered without one via the test suite.

Run the tests:

```bash
cd backend
pytest
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # set VITE_API_BASE_URL / VITE_APP_SECRET if needed
npm run dev
```

Open http://localhost:5173. Add to Home Screen on your phone once it's
deployed somewhere with HTTPS - it installs as a standalone PWA.

## Getting real credentials

See the build spec's account setup table. Short version:

- **Splitwise:** secure.splitwise.com/apps -> register an app -> personal API key.
- **Basiq:** basiq.io -> free dev account -> sandbox first, then a real CDR
  consent flow to connect your actual bank (read-only, you never share your
  bank password with this app).
- **Gmail / Telegram:** reuses whatever app-password / bot token setup the
  parent Macro Pulse project already uses.

All of these go in `backend/.env` locally, and as GitHub Actions secrets for
the cron workflow.

## The matching engine, briefly

`backend/app/services/matcher.py` is the core of the whole project - see its
module docstring for the full rule order. The short version: every unmatched
bank debit runs through exact-match -> surcharge-tolerant match -> recurring
whitelist -> personal, in that order, first hit wins. Credits are checked
against open receivables (single or a same-person pair). Everything is
idempotent (safe to re-run `sync_and_match` on overlapping data), and
anything uncertain gets flagged for you to confirm/reject in the Review
Queue rather than guessed at.

## Non-goals (v1)

No multi-user support, no budgeting features, no backfill beyond 90 days, no
writing back to Splitwise (read-only), no native app - PWA is the mobile
experience. See spec section 11 for the full list.
