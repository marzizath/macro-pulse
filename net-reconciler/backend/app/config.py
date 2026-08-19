"""
Net Reconciler - Configuration

All settings are read from environment variables (see .env.example). Nothing
here should need editing to run the app; edit .env instead.
"""
import os

# --- Splitwise ---
SPLITWISE_API_KEY = os.environ.get("SPLITWISE_API_KEY", "")

# --- Basiq (bank feed) ---
BASIQ_API_KEY = os.environ.get("BASIQ_API_KEY", "")
BASIQ_USER_ID = os.environ.get("BASIQ_USER_ID", "")

# 'basiq' hits the real API, 'fixture' replays backend/tests/fixtures/bank_sample.json.
# Keep this as 'fixture' until Basiq sandbox/production credentials are wired up.
DATA_SOURCE = os.environ.get("DATA_SOURCE", "fixture")

# --- App / API ---
APP_SECRET = os.environ.get("APP_SECRET", "")  # bearer token for the private API
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

# --- Database ---
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "ledger.db",
))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

# --- Notifier (reuses Macro Pulse's Gmail + Telegram pattern) ---
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

TELEGRAM_ENABLED = os.environ.get("TELEGRAM_ENABLED", "true").lower() == "true"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- Matching engine tuning ---
EXACT_MATCH_AMOUNT_TOLERANCE = 1.00      # AUD
EXACT_MATCH_DATE_WINDOW_DAYS = 2
SURCHARGE_MATCH_PCT_TOLERANCE = 0.05     # 5%
SETTLEMENT_AMOUNT_TOLERANCE = 1.00       # AUD
RECEIVABLE_NUDGE_DAYS = 14               # highlight in digest if open longer than this

# User-defined recurring whitelist patterns (uppercase substrings matched
# against bank transaction descriptions) -> used by Rule 3.
RECURRING_WHITELIST = [
    "NETFLIX",
    "RENT",
    "SPOTIFY",
]

# Static fallback FX rates (multiscale currency support - Rule/edge case in
# section 10). Used only when a Splitwise expense currency != AUD and a live
# rate can't be fetched. Update periodically.
STATIC_FX_TO_AUD = {
    "AUD": 1.0,
    "USD": 1.52,
    "INR": 0.0182,
    "EUR": 1.64,
    "GBP": 1.91,
}
