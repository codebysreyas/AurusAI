import sqlite3
import os
import sys
from datetime import datetime, date
from dataclasses import dataclass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import (
    DB_PATH, MAX_LOSING_STREAK,
    MAX_SIGNALS_PER_DAY, MIN_TP_MOVE
)


def is_duplicate(strategy_name):
    """
    Returns True if this strategy already has a pending signal.
    Prevents same strategy firing every 5 minutes.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM signals
        WHERE strategy = ? AND outcome = 'pending'
    """, (strategy_name,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

# ── DB setup ─────────────────────────────────────────────────
def init_db():
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
    return signal_id


# ── Update outcome ────────────────────────────────────────────
def update_outcome(signal_id, outcome, close_price):
    """
    outcome: 'win' | 'loss' | 'cancelled'
    Called externally when price hits TP or SL.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        UPDATE signals
        SET outcome=?, close_price=?, close_time=?
        WHERE id=?
    """, (outcome, close_price, datetime.utcnow().isoformat(), signal_id))
    conn.commit()
    conn.close()


# ── Stats ─────────────────────────────────────────────────────
def get_today_count():
    """Number of signals sent today."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM signals
        WHERE DATE(timestamp) = ?
    """, (date.today().isoformat(),))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_losing_streak():
    """
    Count consecutive losses from the most recent closed signals.
    Pending signals are ignored.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT outcome FROM signals
        WHERE outcome IN ('win','loss')
        ORDER BY id DESC
        LIMIT 20
    """)
    rows   = c.fetchall()
    conn.close()
    streak = 0
    for (outcome,) in rows:
        if outcome == "loss":
            streak += 1
        else:
            break
    return streak


def get_pending_signals():
    """Return all signals still pending outcome."""
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
    """Stats for today's signals — used in daily recap."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT
            COUNT(*)                                      AS total,
            SUM(CASE WHEN outcome='win'  THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN outcome='pending' THEN 1 ELSE 0 END) AS pending
        FROM signals
        WHERE DATE(timestamp) = ?
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


# ── Main gate ─────────────────────────────────────────────────
@dataclass
class RiskDecision:
    allowed : bool
    reason  : str
    streak  : int
    today   : int


def check(sig):
    """
    Main entry point. Takes a SignalResult, returns RiskDecision.
    """
    streak = get_losing_streak()
    today  = get_today_count()

    # 1. Losing streak breaker
    if streak >= MAX_LOSING_STREAK:
        return RiskDecision(
            allowed=False,
            reason =f"Losing streak {streak} >= {MAX_LOSING_STREAK} — paused",
            streak =streak,
            today  =today,
        )

    # 2. Daily signal cap
    if today >= MAX_SIGNALS_PER_DAY:
        return RiskDecision(
            allowed=False,
            reason =f"Daily cap reached: {today}/{MAX_SIGNALS_PER_DAY} signals sent",
            streak =streak,
            today  =today,
        )

    # 3. Minimum TP move
    if sig.expected_move < MIN_TP_MOVE:
        return RiskDecision(
            allowed=False,
            reason =f"TP move ${sig.expected_move} < minimum ${MIN_TP_MOVE}",
            streak =streak,
            today  =today,
        )

    return RiskDecision(
        allowed=True,
        reason =f"Risk OK — streak={streak} today={today}/{MAX_SIGNALS_PER_DAY}",
        streak =streak,
        today  =today,
    )


# ── Outcome checker ───────────────────────────────────────────
def check_pending_outcomes(current_price):
    """
    Call this every scan cycle with current XAUUSD price.
    Automatically marks pending signals as win or loss
    if price has crossed TP or SL.
    """
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


# ── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()

    # simulate a signal object for testing
    class FakeSig:
        strategy      = "Trend Pullback"
        stype         = "trend"
        direction     = 1
        entry         = 2345.00
        sl            = 2330.00
        tp            = 2405.00
        rr            = 4.0
        expected_move = 60.0
        timestamp     = datetime.utcnow()

    decision = check(FakeSig())
    print(f"\n[RiskAgent] Decision: {'ALLOW' if decision.allowed else 'BLOCK'}")
    print(f"[RiskAgent] Reason  : {decision.reason}")
    print(f"[RiskAgent] Streak  : {decision.streak}")
    print(f"[RiskAgent] Today   : {decision.today}")

    summary = get_daily_summary()
    print(f"\n[RiskAgent] Daily summary: {summary}")