import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _direction_emoji(direction):
    return "🟢" if direction == 1 else "🔴"


def _direction_text(direction):
    return "BUY" if direction == 1 else "SELL"


def format_signal(decision):
    """
    Format a StrategyDecision into a Telegram message string.
    """
    sig  = decision.signal
    mac  = decision.macro
    sent = decision.sentiment
    risk = decision.risk

    direction_emoji = _direction_emoji(sig.direction)
    direction_text  = _direction_text(sig.direction)

    # macro line
    if mac and mac.blackout:
        macro_line = f"⚠️ Blackout: {mac.blackout_event}"
    elif mac:
        macro_icon = "✅" if mac.vote == "agree" else "➖"
        macro_line = (
            f"{macro_icon} DXY {mac.dxy_trend.upper()} | "
            f"Yields {mac.yield_trend.upper()} | "
            f"Curve {mac.yield_curve.upper()}"
        )
    else:
        macro_line = "➖ Macro data unavailable"

    # sentiment line
    if sent and not sent.error:
        sent_icon  = "✅" if sent.vote in ("bullish","bearish") else "➖"
        sent_line  = f"{sent_icon} {sent.vote.upper()} — {sent.summary}"
    else:
        sent_line  = "➖ Sentiment unavailable"

    # stats line
    stats     = sig.stats or {}
    rsi_val   = stats.get("rsi")
    adx_val   = stats.get("adx")
    trend_7d  = stats.get("trend_7d_pct")
    sharpe    = stats.get("sharpe")
    ann_vol   = stats.get("ann_volatility")

    stats_parts = []
    if rsi_val  is not None: stats_parts.append(f"RSI {rsi_val}")
    if adx_val  is not None: stats_parts.append(f"ADX {adx_val}")
    if trend_7d is not None: stats_parts.append(f"7d {trend_7d:+.2f}%")
    if sharpe   is not None: stats_parts.append(f"Sharpe {sharpe}")
    if ann_vol  is not None: stats_parts.append(f"Vol {ann_vol}%")
    stats_line = " | ".join(stats_parts) if stats_parts else "N/A"

    msg = (
        f"{direction_emoji} *{direction_text} XAUUSD*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Strategy* : {sig.strategy}\n"
        f"🎯 *Entry*    : {sig.entry}\n"
        f"🛑 *SL*       : {sig.sl}\n"
        f"✅ *TP*       : {sig.tp}\n"
        f"📏 *RR*       : 1:{sig.rr}\n"
        f"💰 *Move*     : ~${sig.expected_move}\n"
        f"⭐ *Confidence*: {decision.stars} ({decision.score}/5)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 *Macro*\n"
        f"{macro_line}\n"
        f"📰 *Sentiment*\n"
        f"{sent_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Indicators*\n"
        f"{stats_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *Risk*: Streak {risk.streak} | "
        f"Today {risk.today}/{3}\n"
        f"🕐 {sig.timestamp.strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"#AurusAI #XAUUSD #{sig.stype.upper()}"
    )
    return msg


def format_daily_recap(summary):
    """
    Format daily performance recap message.
    summary: dict from risk_agent.get_daily_summary()
    """
    total   = summary.get("total",   0)
    wins    = summary.get("wins",    0)
    losses  = summary.get("losses",  0)
    pending = summary.get("pending", 0)
    streak  = summary.get("streak",  0)

    hit_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0.0

    streak_line = (
        f"🔴 Losing streak: {streak}" if streak >= 3
        else f"✅ Streak: {streak}"
    )

    msg = (
        f"📋 *AurusAI Daily Recap*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📤 Signals sent : {total}\n"
        f"✅ Wins         : {wins}\n"
        f"❌ Losses       : {losses}\n"
        f"⏳ Pending      : {pending}\n"
        f"🎯 Hit rate     : {hit_rate}%\n"
        f"{streak_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"#AurusAI #DailyRecap"
    )
    return msg


def format_block_alert(reason):
    """
    Format a risk block notification.
    Only sent when streak hits MAX_LOSING_STREAK.
    """
    msg = (
        f"⚠️ *AurusAI — Signals Paused*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Reason: {reason}\n"
        f"Signals will resume automatically when conditions improve.\n"
        f"#AurusAI #RiskAlert"
    )
    return msg


def format_outcome(strategy, outcome, entry, close_price):
    """
    Format TP/SL hit notification.
    """
    icon = "✅ TP HIT" if outcome == "win" else "❌ SL HIT"
    pnl_direction = "+" if outcome == "win" else "-"
    move = abs(round(close_price - entry, 2))

    msg = (
        f"{icon}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Strategy : {strategy}\n"
        f"🎯 Entry    : {entry}\n"
        f"📍 Close    : {close_price}\n"
        f"💰 Move     : {pnl_direction}${move}\n"
        f"#AurusAI #XAUUSD"
    )
    return msg