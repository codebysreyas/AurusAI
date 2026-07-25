# ============================================================
#  AurusAI — config.py
# ============================================================

# ── GROQ ─────────────────────────────────────────────────────
GROQ_API_KEY  = "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"
GROQ_MODEL    = "llama-3.3-70b-versatile"

# ── NEWS API ─────────────────────────────────────────────────
NEWS_API_KEY  = "43ce66517f184d0ab4dae32222115913"

# ── FRED API ─────────────────────────────────────────────────
FRED_API_KEY  = "b4ed44dbd1870ce69e013d0498b10221"

# ── TELEGRAM ─────────────────────────────────────────────────
TELEGRAM_TOKEN   = "8983894184:AAGt1qqj-qPB4Tpjr_mUXb3Ndt3sXTL-T4M"
TELEGRAM_CHAT_ID = "-1004478677261"

# ── MT5 ──────────────────────────────────────────────────────
MT5_SYMBOL   = "XAUUSD"
MT5_BARS     = 500

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
# (name, rr, filter_run, timeframe, stype, pf)
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
SCAN_INTERVAL_MINUTES        = 5
NEWS_FETCH_INTERVAL_MINUTES  = 60

# ── DATABASE ─────────────────────────────────────────────────
DB_PATH = "data/signals.db"