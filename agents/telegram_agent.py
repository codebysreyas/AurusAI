import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from telegram import Bot
from telegram.constants import ParseMode
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


# ── Bot instance ──────────────────────────────────────────────
_bot = None

def _get_bot():
    global _bot
    if _bot is None:
        if not TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN is empty — set it in config.py")
        from telegram.request import HTTPXRequest
        _bot = Bot(
            token=TELEGRAM_TOKEN,
            request=HTTPXRequest(connect_timeout=30, read_timeout=30)
        )
    return _bot


# ── Send message ──────────────────────────────────────────────
async def _send(text):
    bot = _get_bot()
    await bot.send_message(
        chat_id    =TELEGRAM_CHAT_ID,
        text       =text,
        parse_mode =ParseMode.MARKDOWN,
    )


def send(text):
    """Synchronous wrapper — safe for use inside schedulers."""
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(_send(text))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_send(text))
        print(f"[TelegramAgent] Message sent ({len(text)} chars)")
        return True
    except Exception as e:
        print(f"[TelegramAgent] Send error: {e}")
        return False


# ── Convenience senders ───────────────────────────────────────
def send_signal(decision):
    from utils.formatter import format_signal
    msg = format_signal(decision)
    return send(msg)


def send_daily_recap(summary):
    from utils.formatter import format_daily_recap
    msg = format_daily_recap(summary)
    return send(msg)


def send_block_alert(reason):
    from utils.formatter import format_block_alert
    msg = format_block_alert(reason)
    return send(msg)


def send_outcome(strategy, outcome, entry, close_price, direction):
    from utils.formatter import format_outcome
    msg = format_outcome(strategy, outcome, entry, close_price, direction)
    return send(msg)


# ── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[TelegramAgent] Sending test message...")
    ok = send(
        "🤖 *AurusAI* is online and connected\\!\n"
        "Signal bot is ready\\.\n"
        "\\#AurusAI \\#Test"
    )
    if ok:
        print("[TelegramAgent] ✓ Test message sent successfully")
    else:
        print("[TelegramAgent] ✗ Failed — check TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in config.py")