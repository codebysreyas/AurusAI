import os

# ── GROQ ─────────────────────────────────────────────────────
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL    = "llama-3.3-70b-versatile"

# ── NEWS API ─────────────────────────────────────────────────
NEWS_API_KEY  = os.environ.get("NEWS_API_KEY", "")

# ── FRED API ─────────────────────────────────────────────────
FRED_API_KEY  = os.environ.get("FRED_API_KEY", "")

# ── TELEGRAM ─────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── SIGNAL QUALITY THRESHOLDS ────────────────────────────────
MIN_TP_MOVE        = 10.0
MIN_CANDLE_RANGE   = 1.0
MIN_BODY_RATIO     = 0.3
MIN_ATR_RATIO      = 0.7

# ── RISK CONTROLS ────────────────────────────────────────────
MAX_LOSING_STREAK   = 5
MAX_SIGNALS_PER_DAY = 3
MIN_CONFIDENCE      = 3

# ── STRATEGIES ───────────────────────────────────────────────
STRATEGIES = [
    ("Trend Pullback",               4.0, "D", "H1",  "trend",    1.609),
    ("Trend Acceleration",           4.0, "D", "H1",  "trend",    1.486),
    ("Trend + Volatility Expansion", 4.0, "A", "H1",  "trend",    1.368),
    ("Trend Following Low DD",       4.0, "D", "H1",  "trend",    1.354),
    ("Wick Rejection Reversal",      2.5, "A", "M15", "reversal", 1.183),
    ("Liquidity Sweep Continuation", 3.0, "D", "M5",  "breakout", 1.195),
    ("VWAP Reversion",               2.0, "B", "M5",  "reversal", 1.106),
    ("Mean Reversion",               3.0, "B", "M15", "reversal", 1.137),
]

# ── SCHEDULER ────────────────────────────────────────────────
SCAN_INTERVAL_MINUTES       = 5
NEWS_FETCH_INTERVAL_MINUTES = 60

# ── DATABASE ─────────────────────────────────────────────────
DB_PATH = "data/signals.db"