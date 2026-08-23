# ============================================================
#  AurusAI — agents/risk_agent.py
# ============================================================

import sqlite3
import os
import sys
from datetime import datetime, date, timezone
from dataclasses import dataclass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DB_PATH, MAX_LOSING_STREAK, MAX_SIGNALS_PER_DAY, MIN_TP_MOVE


# ── S3 ────────────────────────────────────────────────────────
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_KEY    = "aurusai/signals.db"


def _s3_client():
    import boto3
    return boto3.client("s3")


def backup_db_to_s3():
    if not S3_BUCKET:
        return
    try:
        _s3_client().upload_file(DB_PATH, S3_BUCKET, S3_KEY)
        print(f"[RiskAgent] DB backed up to S3")
    except Exception as e:
        print(f"[RiskAgent] S3 backup error: {e}")


def restore_db_from_s3():
    if not S3_BUCKET:
        return
    try:
        from botocore.exceptions import ClientError
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _s3_client().download_file(S3_BUCKET, S3_KEY, DB_PATH)
        print(f"[RiskAgent] DB restored from S3")
    except Exception as e:
        if "404" in str(e) or "NoSuchKey" in str(e):
            print(f"[RiskAgent] No S3 backup found — starting fresh")
        else:
            print(f"[RiskAgent] S3 restore error: {e}")


# ── DB setup ──────────────────────────────────────────────────
def init_db():
    restore_db_from_s3()
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT,
            strategy      TEXT,
            stype         TEXT,
            direction     INTEGER,
            entry         REAL,
            sl            REAL,
            tp            REAL,
            rr            REAL,
            expected_move REAL,
            outcome       TEXT DEFAULT 'pending',
            close_price   REAL,
            close_time    TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("[RiskAgent] DB initialised")


# ── Write signal ──────────────────────────────────────────────
def log_signal(sig):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        INSERT INTO signals
        (timestamp, strategy, stype, direction, entry, sl, tp, rr, expected_move)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        sig.timestamp.isoformat(),
        sig.strategy, sig.stype, sig.direction,
        sig.entry, sig.sl, sig.tp, sig.rr, sig.expected_move
    ))
    conn.commit()
    signal_id = c.lastrowid
    conn.close()
    backup_db_to_s3()
    return signal_id


# ── Update outcome ────────────────────────────────────────────
def update_outcome(signal_id, outcome, close_price):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        UPDATE signals
        SET outcome=?, close_price=?, close_time=?
        WHERE id=?
    """, (outcome, close_price, datetime.now(timezone.utc).isoformat(), signal_id))
    conn.commit()
    conn.close()
    backup_db_to_s3()


# ── Stats ─────────────────────────────────────────────────────
def get_today_count():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("SELECT COUNT(*) FROM signals WHERE DATE(timestamp) = ?",
              (date.today().isoformat(),))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_losing_streak():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT outcome FROM signals
        WHERE outcome IN ('win','loss')
        ORDER BY id DESC LIMIT 20
    """)
    rows   = c.fetchall()
    conn.close()
    streak = 0
    for (outcome,) in rows:
        if outcome == "loss": streak += 1
        else: break
    return streak


def get_pending_signals():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT id, strategy, direction, entry, sl, tp
        FROM signals WHERE outcome='pending'
        ORDER BY id DESC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


def get_daily_summary():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN outcome='win'     THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN outcome='loss'    THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN outcome='pending' THEN 1 ELSE 0 END) AS pending
        FROM signals WHERE DATE(timestamp) = ?
    """, (date.today().isoformat(),))
    row = c.fetchone()
    conn.close()
    total, wins, losses, pending = row
    return {
        "total"  : total   or 0,
        "wins"   : wins    or 0,
        "losses" : losses  or 0,
        "pending": pending or 0,
        "streak" : get_losing_streak(),
    }


# ── Duplicate check ───────────────────────────────────────────
def is_duplicate(strategy_name):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM signals
        WHERE strategy = ? AND outcome = 'pending'
    """, (strategy_name,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0


# ── Expire old signals ────────────────────────────────────────
def expire_old_signals(hours=24):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        UPDATE signals
        SET outcome = 'cancelled', close_time = ?
        WHERE outcome = 'pending'
        AND datetime(timestamp) <= datetime('now', ?)
    """, (datetime.now(timezone.utc).isoformat(), f'-{hours} hours'))
    expired = c.rowcount
    conn.commit()
    conn.close()
    if expired > 0:
        print(f"[RiskAgent] {expired} signal(s) expired after {hours}h")
    return expired


# ── Pending outcome checker ───────────────────────────────────
def check_pending_outcomes(current_price):
    pending = get_pending_signals()
    closed  = []
    for (sid, strategy, direction, entry, sl, tp) in pending:
        outcome = None
        if direction == 1:
            if current_price >= tp: outcome = "win"
            elif current_price <= sl: outcome = "loss"
        else:
            if current_price <= tp: outcome = "win"
            elif current_price >= sl: outcome = "loss"
        if outcome:
            update_outcome(sid, outcome, current_price)
            closed.append((sid, strategy, outcome))
            print(f"[RiskAgent] Signal #{sid} {strategy} → {outcome.upper()} at {current_price}")
    return closed


# ── Current price ─────────────────────────────────────────────
def get_current_price():
    try:
        import MetaTrader5 as mt5
        from config import MT5_SYMBOL if hasattr(__import__('config'), 'MT5_SYMBOL') else None
        symbol = os.environ.get("MT5_SYMBOL", "XAUUSD")
        if not mt5.initialize():
            return None
        tick = mt5.symbol_info_tick(symbol)
        mt5.shutdown()
        if tick is None:
            return None
        return float(tick.bid)
    except Exception as e:
        print(f"[RiskAgent] Price fetch error: {e}")
        return None


# ── Risk gate ─────────────────────────────────────────────────
@dataclass
class RiskDecision:
    allowed : bool
    reason  : str
    streak  : int
    today   : int


def check(sig):
    streak = get_losing_streak()
    today  = get_today_count()

    if streak >= MAX_LOSING_STREAK:
        return RiskDecision(
            allowed=False,
            reason =f"Losing streak {streak} >= {MAX_LOSING_STREAK} — paused",
            streak =streak, today=today)

    if today >= MAX_SIGNALS_PER_DAY:
        return RiskDecision(
            allowed=False,
            reason =f"Daily cap: {today}/{MAX_SIGNALS_PER_DAY}",
            streak =streak, today=today)

    if sig.expected_move < MIN_TP_MOVE:
        return RiskDecision(
            allowed=False,
            reason =f"TP move ${sig.expected_move} < ${MIN_TP_MOVE}",
            streak =streak, today=today)

    return RiskDecision(
        allowed=True,
        reason =f"Risk OK — streak={streak} today={today}/{MAX_SIGNALS_PER_DAY}",
        streak =streak, today=today)


# ── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()

    class FakeSig:
        strategy      = "Trend Pullback"
        stype         = "trend"
        direction     = 1
        entry         = 2345.00
        sl            = 2330.00
        tp            = 2405.00
        rr            = 4.0
        expected_move = 60.0
        timestamp     = datetime.now(timezone.utc)

    decision = check(FakeSig())
    print(f"\n[RiskAgent] Decision: {'ALLOW' if decision.allowed else 'BLOCK'}")
    print(f"[RiskAgent] Reason  : {decision.reason}")
    print(f"[RiskAgent] Streak  : {decision.streak}")
    print(f"[RiskAgent] Today   : {decision.today}")
    print(f"\n[RiskAgent] Daily summary: {get_daily_summary()}")