import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _direction_emoji(direction):
    return "🟢" if direction == 1 else "🔴"


def _direction_text(direction):
    return "BUY" if direction == 1 else "SELL"


def format_signal(decision):
    sig  = decision.signal
    mac  = decision.macro
    sent = decision.sentiment
    risk = decision.risk

    direction_emoji = "🟢" if sig.direction == 1 else "🔴"
    direction_text  = "LONG" if sig.direction == 1 else "SHORT"

    # macro line
    if mac and mac.blackout:
        macro_line = f"⚠️ Blackout: {mac.blackout_event}"
    elif mac:
        macro_icon = "✓" if mac.vote == "agree" else "—"
        macro_line = (
            f"{macro_icon} DXY {mac.dxy_trend.upper()} │ "
            f"Yields {mac.yield_trend.upper()} │ "
            f"Curve {mac.yield_curve.upper()}"
        )
    else:
        macro_line = "— Macro data unavailable"

    # sentiment line
    if sent and not sent.error:
        sent_icon = "✓" if sent.vote in ("bullish","bearish") else "—"
        sent_line = f"{sent_icon} {sent.vote.upper()} — {sent.summary}"
    else:
        sent_line = "— Sentiment unavailable"

    # stats
    stats    = sig.stats or {}
    rsi_val  = stats.get("rsi")
    adx_val  = stats.get("adx")
    trend_7d = stats.get("trend_7d_pct")
    sharpe   = stats.get("sharpe")
    ann_vol  = stats.get("ann_volatility")

    stats_parts = []
    if rsi_val  is not None: stats_parts.append(f"RSI {rsi_val}")
    if adx_val  is not None: stats_parts.append(f"ADX {adx_val}")
    if trend_7d is not None: stats_parts.append(f"7D {trend_7d:+.2f}%")
    if sharpe   is not None: stats_parts.append(f"SHARPE {sharpe}")
    if ann_vol  is not None: stats_parts.append(f"VOL {ann_vol}%")
    stats_line = " │ ".join(stats_parts) if stats_parts else "N/A"

    entry_low  = round(sig.entry - sig.atr * 0.1, 2)
    entry_high = round(sig.entry + sig.atr * 0.1, 2)

    msg = (
        f"◉ *AURUS AI* — SIGNAL ALERT\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{direction_emoji} *{direction_text} XAUUSD*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 STRATEGY      {sig.strategy}\n"
        f"🎯 ENTRY ZONE    {entry_low} – {entry_high}\n"
        f"🛑 STOP LOSS     {sig.sl}\n"
        f"✅ TAKE PROFIT   {sig.tp}\n"
        f"📏 RISK/REWARD   1:{sig.rr}\n"
        f"💰 EXPECTED MOVE ~${sig.expected_move}\n"
        f"⭐ CONFIDENCE    {decision.stars} {decision.score}/5\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 *MACRO CONTEXT*\n"
        f"{macro_line}\n"
        f"📰 *SENTIMENT*\n"
        f"{sent_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *TECHNICALS*\n"
        f"{stats_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ RISK          Streak {risk.streak} │ Today {risk.today}/3\n"
        f"🕐 TIME          {sig.timestamp.strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_This is not financial advice\\._\n"
        f"\\#AurusAI \\#XAUUSD \\#{sig.stype.upper()}"
    )
    return msg


def format_daily_recap(summary):
    total   = summary.get("total",   0)
    wins    = summary.get("wins",    0)
    losses  = summary.get("losses",  0)
    pending = summary.get("pending", 0)
    streak  = summary.get("streak",  0)
    hit_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0.0
    streak_line = f"🔴 LOSING STREAK   {streak}" if streak >= 3 else f"✅ STREAK          {streak}"

    msg = (
        f"◉ *AURUS AI* — DAILY RECAP\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📤 SIGNALS SENT    {total}\n"
        f"✅ WINS            {wins}\n"
        f"❌ LOSSES          {losses}\n"
        f"⏳ PENDING         {pending}\n"
        f"🎯 HIT RATE        {hit_rate}%\n"
        f"{streak_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\\#AurusAI \\#DailyRecap"
    )
    return msg


def format_block_alert(reason):
    msg = (
        f"◉ *AURUS AI* — SIGNALS PAUSED\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ {reason}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_Signals will resume automatically\\._\n"
        f"\\#AurusAI \\#RiskAlert"
    )
    return msg


def format_outcome(strategy, outcome, entry, close_price, direction):
    icon     = "✅ TARGET HIT" if outcome == "win" else "❌ STOPPED OUT"
    pips     = round(abs(close_price - entry) * 10)
    pip_sign = "+" if outcome == "win" else "-"
    result   = "WIN" if outcome == "win" else "LOSS"

    msg = (
        f"◉ *AURUS AI* — TRADE CLOSED\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 STRATEGY      {strategy}\n"
        f"🎯 ENTRY         {entry}\n"
        f"📍 CLOSE         {close_price}\n"
        f"📏 PIPS          {pip_sign}{pips} pips\n"
        f"🏆 RESULT        {result}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\\#AurusAI \\#XAUUSD"
    )
    return msg