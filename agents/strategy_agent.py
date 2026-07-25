import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timezone
from dataclasses import dataclass, field

from agents.risk_agent      import check as risk_check, log_signal, is_duplicate
from agents.macro_agent     import run   as macro_run
from agents.sentiment_agent import run   as sentiment_run

from config import MIN_CONFIDENCE


@dataclass
class StrategyDecision:
    send           : bool
    score          : int
    max_score      : int
    stars          : str
    signal         : object
    risk           : object
    macro          : object
    sentiment      : object
    score_breakdown: dict = field(default_factory=dict)
    block_reason   : str  = ""


def _stars(score, max_score=5):
    return "★" * score + "☆" * (max_score - score)


def evaluate(signal, current_price=None):
    direction = signal.direction

    # ── Step 1: Risk check ────────────────────────────────────
    risk = risk_check(signal)
    if not risk.allowed:
        print(f"[StrategyAgent] BLOCKED by Risk: {risk.reason}")
        return StrategyDecision(
            send         =False,
            score        =0,
            max_score    =5,
            stars        =_stars(0),
            signal       =signal,
            risk         =risk,
            macro        =None,
            sentiment    =None,
            block_reason =risk.reason,
        )

    # ── Step 2: Duplicate check ───────────────────────────────
    if is_duplicate(signal.strategy):
        print(f"[StrategyAgent] SKIP duplicate — {signal.strategy} already pending")
        return StrategyDecision(
            send         =False,
            score        =0,
            max_score    =5,
            stars        =_stars(0),
            signal       =signal,
            risk         =risk,
            macro        =None,
            sentiment    =None,
            block_reason ="Duplicate — already pending",
        )

    # ── Step 3: Macro check ───────────────────────────────────
    macro = macro_run(signal_direction=direction)

    # ── Step 4: Sentiment check ───────────────────────────────
    sentiment = sentiment_run(signal_direction=direction)

    # ── Step 5: Score ─────────────────────────────────────────
    score     = 0
    breakdown = {}

    score += 1
    breakdown["price_signal"] = 1

    if macro.blackout:
        breakdown["macro"] = 0
        print(f"[StrategyAgent] Macro blackout — 0 points")
    elif macro.vote == "agree":
        score += 1
        breakdown["macro"] = 1
        print(f"[StrategyAgent] Macro agrees — +1")
    elif macro.vote == "neutral":
        breakdown["macro"] = 0
        print(f"[StrategyAgent] Macro neutral — +0")
    else:
        breakdown["macro"] = 0
        print(f"[StrategyAgent] Macro disagrees — +0")

    sent_agrees = (
        (direction ==  1 and sentiment.vote == "bullish") or
        (direction == -1 and sentiment.vote == "bearish")
    )
    if sent_agrees:
        score += 1
        breakdown["sentiment"] = 1
        print(f"[StrategyAgent] Sentiment agrees — +1")
    else:
        breakdown["sentiment"] = 0
        print(f"[StrategyAgent] Sentiment neutral/disagrees — +0")

    if risk.streak < 3:
        score += 1
        breakdown["risk_clean"] = 1
        print(f"[StrategyAgent] Risk clean streak={risk.streak} — +1")
    else:
        breakdown["risk_clean"] = 0
        print(f"[StrategyAgent] Risk streak={risk.streak} — +0")

    if signal.pf >= 1.30:
        score += 1
        breakdown["pf_bonus"] = 1
        print(f"[StrategyAgent] PF bonus {signal.pf} >= 1.30 — +1")
    else:
        breakdown["pf_bonus"] = 0
        print(f"[StrategyAgent] PF {signal.pf} < 1.30 — +0")

    # ── Step 6: Decision ──────────────────────────────────────
    send = score >= MIN_CONFIDENCE and not macro.blackout
    print(f"[StrategyAgent] Score={score}/5 {_stars(score)} "
          f"{'SEND' if send else 'SKIP'} — {signal.strategy}")

    decision = StrategyDecision(
        send           =send,
        score          =score,
        max_score      =5,
        stars          =_stars(score),
        signal         =signal,
        risk           =risk,
        macro          =macro,
        sentiment      =sentiment,
        score_breakdown=breakdown,
        block_reason   ="" if send else f"Score {score} < {MIN_CONFIDENCE}",
    )

    # ── Step 7: Log to DB if sending ─────────────────────────
    if send:
        signal_id = log_signal(signal)
        print(f"[StrategyAgent] Signal logged — DB id={signal_id}")
        decision.signal_id = signal_id

    return decision


def run_all(signals, current_price=None):
    approved = []
    for sig in signals:
        print(f"\n[StrategyAgent] Evaluating: {sig.strategy}")
        decision = evaluate(sig, current_price)
        if decision.send:
            approved.append(decision)
    print(f"\n[StrategyAgent] {len(approved)}/{len(signals)} signals approved")
    return approved


if __name__ == "__main__":
    class FakeSignal:
        strategy      = "Trend Pullback"
        stype         = "trend"
        direction     = 1
        entry         = 2345.00
        sl            = 2330.00
        tp            = 2405.00
        rr            = 4.0
        atr           = 15.0
        expected_move = 60.0
        reason        = "H4 bull + RSI pullback 38.5"
        filter_run    = "D"
        pf            = 1.609
        timestamp     = datetime.now(timezone.utc)
        stats         = {}

    decision = evaluate(FakeSignal())
    print(f"\n{'='*55}")
    print(f"Send     : {decision.send}")
    print(f"Score    : {decision.score}/5")
    print(f"Stars    : {decision.stars}")
    print(f"Breakdown: {decision.score_breakdown}")
    if not decision.send:
        print(f"Blocked  : {decision.block_reason}")
    if decision.macro:
        print(f"Macro    : {decision.macro.vote} — {decision.macro.reason}")
    if decision.sentiment:
        print(f"Sentiment: {decision.sentiment.vote} — {decision.sentiment.summary}")