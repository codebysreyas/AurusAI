import sys
import os
import time
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron       import CronTrigger
from apscheduler.triggers.interval   import IntervalTrigger

# ── agent imports ─────────────────────────────────────────────
from agents.price_agent    import run         as price_run
from agents.strategy_agent import run_all     as strategy_run
from agents.risk_agent     import (
    init_db,
    get_daily_summary,
    check_pending_outcomes,
    get_losing_streak,
    MAX_LOSING_STREAK,
)
from agents.telegram_agent import (
    send_signal,
    send_daily_recap,
    send_block_alert,
    send_outcome,
)
from agents.risk_agent import get_current_price
from config import (
    SCAN_INTERVAL_MINUTES,
    MAX_LOSING_STREAK,
)


# ── state ─────────────────────────────────────────────────────
_last_block_alert_sent = False   # avoid spamming block alerts


# ── main scan cycle ───────────────────────────────────────────
def scan():
    """
    Runs every SCAN_INTERVAL_MINUTES minutes.
    1. Fetch live price + run strategies
    2. Check pending signal outcomes
    3. Evaluate each signal through all agents
    4. Send approved signals to Telegram
    """
    now = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"[AurusAI] Scan started — {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}")

    global _last_block_alert_sent

    # ── step 1: get live price signals ────────────────────────
    try:
        signals, frames = price_run()
    except Exception as e:
        print(f"[AurusAI] Price Agent error: {e}")
        return

    # ── step 2: check pending outcomes ────────────────────────
    try:
        from agents.risk_agent import get_current_price
        current_price = get_current_price()
        if current_price:
            print(f"[AurusAI] Current price: {current_price}")
            closed = check_pending_outcomes(current_price)
            for (sid, strategy, outcome) in closed:
                # fetch entry from DB
                import sqlite3
                from config import DB_PATH
                conn = sqlite3.connect(DB_PATH)
                c    = conn.cursor()
                c.execute("SELECT entry, direction FROM signals WHERE id=?", (sid,))
                row  = c.fetchone()
                conn.close()
                if row:
                    entry, direction = row
                    send_outcome(strategy, outcome, entry, current_price, direction)
    except Exception as e:
        print(f"[AurusAI] Outcome check error: {e}")

    # ── step 3: check if bot is paused ────────────────────────
    streak = get_losing_streak()
    if streak >= MAX_LOSING_STREAK:
        if not _last_block_alert_sent:
            reason = f"Losing streak reached {streak} — signals paused"
            send_block_alert(reason)
            _last_block_alert_sent = True
            print(f"[AurusAI] Bot paused — streak={streak}")
        else:
            print(f"[AurusAI] Still paused — streak={streak}")
        return

    # reset block alert flag when streak clears
    if streak < MAX_LOSING_STREAK:
        _last_block_alert_sent = False

    # ── step 4: evaluate signals ──────────────────────────────
    if not signals:
        print(f"[AurusAI] No signals from Price Agent")
        return

    try:
        approved = strategy_run(signals)
    except Exception as e:
        print(f"[AurusAI] Strategy Agent error: {e}")
        return

    # ── step 5: send approved signals ─────────────────────────
    if not approved:
        print(f"[AurusAI] No signals approved this cycle")
        return

    for decision in approved:
        try:
            ok = send_signal(decision)
            if ok:
                print(f"[AurusAI] ✓ Sent: {decision.signal.strategy} "
                      f"{'BUY' if decision.signal.direction==1 else 'SELL'} "
                      f"score={decision.score}/5")
            else:
                print(f"[AurusAI] ✗ Failed to send: {decision.signal.strategy}")
        except Exception as e:
            print(f"[AurusAI] Telegram send error: {e}")

    print(f"[AurusAI] Cycle complete — {len(approved)} signal(s) sent")


# ── daily recap ───────────────────────────────────────────────
def daily_recap():
    """
    Runs at 18:00 UTC every day.
    Sends performance summary to Telegram.
    """
    print(f"\n[AurusAI] Sending daily recap...")
    try:
        summary = get_daily_summary()
        send_daily_recap(summary)
        print(f"[AurusAI] Daily recap sent: {summary}")
    except Exception as e:
        print(f"[AurusAI] Daily recap error: {e}")


# ── startup message ───────────────────────────────────────────
def startup():
    from agents.telegram_agent import send
    now = datetime.now(timezone.utc)
    msg = (
        f"🤖 *AurusAI Started*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now.strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"📡 Scanning every {SCAN_INTERVAL_MINUTES} minutes\n"
        f"📊 8 strategies active\n"
        f"✅ All systems operational\n"
        f"\\#AurusAI"
    )
    send(msg)
    print(f"[AurusAI] Startup message sent")


# ── main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"{'='*60}")
    print(f"  AurusAI — XAUUSD Signal Bot")
    print(f"  Starting up...")
    print(f"{'='*60}\n")

    # initialise database
    init_db()

    # send startup notification
    try:
        startup()
    except Exception as e:
        print(f"[AurusAI] Startup message failed: {e}")

    # run one scan immediately on startup
    print(f"\n[AurusAI] Running initial scan...")
    scan()

    # set up scheduler
    scheduler = BlockingScheduler(timezone="UTC")

    # scan every 5 minutes
    scheduler.add_job(
        scan,
        trigger  =IntervalTrigger(minutes=SCAN_INTERVAL_MINUTES),
        id       ="scan",
        name     ="Price Scan",
        misfire_grace_time=60,
    )

    # daily recap at 18:00 UTC
    scheduler.add_job(
        daily_recap,
        trigger  =CronTrigger(hour=18, minute=0, timezone="UTC"),
        id       ="daily_recap",
        name     ="Daily Recap",
        misfire_grace_time=300,
    )

    print(f"\n[AurusAI] Scheduler started")
    print(f"[AurusAI] Scanning every {SCAN_INTERVAL_MINUTES} minutes")
    print(f"[AurusAI] Daily recap at 18:00 UTC")
    print(f"[AurusAI] Press Ctrl+C to stop\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print(f"\n[AurusAI] Stopped by user")
        scheduler.shutdown()