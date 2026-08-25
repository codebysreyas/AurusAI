from dotenv import load_dotenv
load_dotenv()

import sys
import os
import sqlite3
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron       import CronTrigger
from apscheduler.triggers.interval   import IntervalTrigger

from agents.price_agent    import run     as price_run
from agents.strategy_agent import run_all as strategy_run
from agents.risk_agent     import (
    init_db,
    get_daily_summary,
    check_pending_outcomes,
    get_losing_streak,
    get_current_price,
    expire_old_signals,
)
from agents.telegram_agent import (
    send_signal,
    send_daily_recap,
    send_block_alert,
    send_outcome,
)
from config import (
    SCAN_INTERVAL_MINUTES,
    MAX_LOSING_STREAK,
    DB_PATH,
)


# ── state ─────────────────────────────────────────────────────
_last_block_alert_sent = False
_last_price            = None


# ── market hours ──────────────────────────────────────────────
def is_market_open():
    now     = datetime.now(timezone.utc)
    weekday = now.weekday()
    hour    = now.hour
    if weekday == 5:                 return False
    if weekday == 6 and hour < 21:  return False
    if weekday == 4 and hour >= 21: return False
    return True


# ── stale price detection ─────────────────────────────────────
def is_stale_price(current_price):
    global _last_price
    if _last_price is not None and current_price == _last_price:
        print(f"[AurusAI] Warning: stale price detected ({current_price})")
        return True
    _last_price = current_price
    return False


# ── scan ──────────────────────────────────────────────────────
def scan():
    now = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"[AurusAI] Scan started — {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}")

    global _last_block_alert_sent

    # market closed
    if not is_market_open():
        print(f"[AurusAI] Market closed — skipping scan")
        return

    # expire old signals
    expire_old_signals(hours=24)

    # current price
    current_price = get_current_price()
    if not current_price:
        print(f"[AurusAI] Could not fetch current price — skipping scan")
        return

    print(f"[AurusAI] Current price: {current_price}")

    if is_stale_price(current_price):
        print(f"[AurusAI] Stale price — skipping scan")
        return

    # check pending outcomes
    try:
        closed = check_pending_outcomes(current_price)
        for (sid, strategy, outcome) in closed:
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

    # streak check
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

    if streak < MAX_LOSING_STREAK:
        _last_block_alert_sent = False

    # price signals
    try:
        signals, frames = price_run()
    except Exception as e:
        print(f"[AurusAI] Price Agent error: {e}")
        return

    if not signals:
        print(f"[AurusAI] No signals from Price Agent")
        return

    # evaluate
    try:
        approved = strategy_run(signals)
    except Exception as e:
        print(f"[AurusAI] Strategy Agent error: {e}")
        return

    if not approved:
        print(f"[AurusAI] No signals approved this cycle")
        return

    # send
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
    print(f"\n[AurusAI] Sending daily recap...")
    try:
        summary = get_daily_summary()
        send_daily_recap(summary)
        print(f"[AurusAI] Daily recap sent: {summary}")
    except Exception as e:
        print(f"[AurusAI] Daily recap error: {e}")


def startup():
    from agents.telegram_agent import send
    now = datetime.now(timezone.utc)
    msg = (
        f"◉ *AURUS AI*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*SYSTEM INITIALIZED*\n"
        f"✓ Quantitative Engine Online\n"
        f"✓ Multi\\-Strategy Framework Active\n"
        f"✓ Market Data Connected\n"
        f"✓ Risk Controls Enabled\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 UTC {now.strftime('%Y\\-%m\\-%d %H:%M')}\n"
        f"📡 SCAN CYCLE      Every {SCAN_INTERVAL_MINUTES} Minutes\n"
        f"📊 STRATEGIES      8 Active\n"
        f"🛡️ RISK ENGINE     Enabled\n"
        f"📈 MARKET          XAUUSD\n"
        f"🟢 STATUS          Monitoring\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_Scanning global markets\\._\n"
        f"_Filtering institutional\\-grade opportunities\\._\n"
        f"_Awaiting confirmed execution conditions\\._"
    )
    send(msg)
    print(f"[AurusAI] Startup message sent")


# ── main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"{'='*60}")
    print(f"  AurusAI — XAUUSD Signal Bot")
    print(f"  Starting up...")
    print(f"{'='*60}\n")

    init_db()

    try:
        startup()
    except Exception as e:
        print(f"[AurusAI] Startup message failed: {e}")

    print(f"\n[AurusAI] Running initial scan...")
    scan()

    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        scan,
        trigger           =IntervalTrigger(minutes=SCAN_INTERVAL_MINUTES),
        id                ="scan",
        name              ="Price Scan",
        misfire_grace_time=60,
    )

    scheduler.add_job(
        daily_recap,
        trigger           =CronTrigger(hour=18, minute=0, timezone="UTC"),
        id                ="daily_recap",
        name              ="Daily Recap",
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