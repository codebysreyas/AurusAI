import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from dataclasses import dataclass, field

from utils.indicators import add_all_indicators, get_summary_stats
from utils.strategies  import (
    trend_pullback,
    trend_acceleration,
    trend_volatility_expansion,
    trend_following_low_dd,
    wick_rejection_reversal,
    liquidity_sweep_continuation,
    vwap_reversion,
    mean_reversion,
)
from utils.filters import check_all_filters
from config import STRATEGIES


# ── Signal dataclass ──────────────────────────────────────────
@dataclass
class SignalResult:
    strategy     : str
    stype        : str
    direction    : int
    entry        : float
    sl           : float
    tp           : float
    rr           : float
    atr          : float
    expected_move: float
    reason       : str
    filter_run   : str
    pf           : float
    timestamp    : datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stats        : dict     = field(default_factory=dict)


# ── Timeframe map ─────────────────────────────────────────────
# yfinance interval : (period, internal key)
TF_CONFIG = {
    "M5" : ("5d",  "5m"),
    "M15": ("30d", "15m"),
    "H1" : ("60d", "1h"),
    "H4" : ("60d", "1h"),   # yfinance has no 4h — resample from 1h
}


# ── Fetch data ────────────────────────────────────────────────
def fetch_data(ticker="GC=F"):
    frames = {}
    try:
        # fetch M5
        df = yf.download(ticker, period="5d", interval="5m",
                         auto_adjust=True, progress=False, timeout=20)
        if not df.empty:
            df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
            df = df[["open","high","low","close","volume"]].dropna()
            frames["M5"] = df.tail(500)
            print(f"[PriceAgent] M5 : {len(frames['M5'])} bars")

        # fetch M15
        df = yf.download(ticker, period="30d", interval="15m",
                         auto_adjust=True, progress=False, timeout=20)
        if not df.empty:
            df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
            df = df[["open","high","low","close","volume"]].dropna()
            frames["M15"] = df.tail(500)
            print(f"[PriceAgent] M15: {len(frames['M15'])} bars")

        # fetch H1
        df = yf.download(ticker, period="60d", interval="1h",
                         auto_adjust=True, progress=False, timeout=20)
        if not df.empty:
            df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
            df = df[["open","high","low","close","volume"]].dropna()
            h1 = df.tail(500)
            frames["H1"] = h1
            print(f"[PriceAgent] H1 : {len(frames['H1'])} bars")

            # resample H1 to H4
            h4 = df.resample("4h").agg(
                open =("open",  "first"),
                high =("high",  "max"),
                low  =("low",   "min"),
                close=("close", "last"),
                volume=("volume","sum"),
            ).dropna().tail(500)
            frames["H4"] = h4
            print(f"[PriceAgent] H4 : {len(frames['H4'])} bars")

    except Exception as e:
        print(f"[PriceAgent] Fetch error: {e}")

    return frames


# ── Prepare indicators ────────────────────────────────────────
def prepare_frames(frames):
    prepared = {}
    for tf, df in frames.items():
        try:
            prepared[tf] = add_all_indicators(df)
        except Exception as e:
            print(f"[PriceAgent] Indicator error {tf}: {e}")
    return prepared


# ── Run strategies ────────────────────────────────────────────
def run_strategies(frames):
    signals = []

    df_m5  = frames.get("M5")
    df_m15 = frames.get("M15")
    df_h1  = frames.get("H1")
    df_h4  = frames.get("H4")

    if df_h1 is None or df_m15 is None:
        print("[PriceAgent] Missing required timeframes")
        return signals

    strategy_calls = [
        (trend_pullback,               df_h1,  df_h4,  0),
        (trend_acceleration,           df_h1,  df_h4,  1),
        (trend_volatility_expansion,   df_h1,  df_h4,  2),
        (trend_following_low_dd,       df_h1,  df_h4,  3),
        (wick_rejection_reversal,      df_m15, df_h1,  4),
        (liquidity_sweep_continuation, df_m5,  df_m15, 5),
        (vwap_reversion,               df_m5,  df_m15, 6),
        (mean_reversion,               df_m15, df_h1,  7),
    ]

    for func, df_entry, df_secondary, cfg_idx in strategy_calls:
        if df_entry is None or df_secondary is None:
            continue

        name, rr, filter_run, tf, stype, pf = STRATEGIES[cfg_idx]

        try:
            direction, reason = func(df_entry, df_secondary)
        except Exception as e:
            print(f"[PriceAgent] {name} error: {e}")
            continue

        if direction == 0:
            continue

        latest_idx = len(df_entry) - 1
        passed, filter_reason = check_all_filters(
            df_entry, latest_idx, direction, rr, stype
        )
        if not passed:
            print(f"[PriceAgent] {name} filtered: {filter_reason}")
            continue

        latest = df_entry.iloc[-1]
        entry  = float(latest["close"])
        atr    = float(latest["atr"]) if not np.isnan(latest["atr"]) else 1.0
        sl     = round(entry - direction * atr, 2)
        tp     = round(entry + direction * atr * rr, 2)
        move   = round(atr * rr, 2)

        sig = SignalResult(
            strategy     = name,
            stype        = stype,
            direction    = direction,
            entry        = round(entry, 2),
            sl           = sl,
            tp           = tp,
            rr           = rr,
            atr          = round(atr, 2),
            expected_move= move,
            reason       = reason,
            filter_run   = filter_run,
            pf           = pf,
            stats        = get_summary_stats(df_entry),
        )
        signals.append(sig)
        print(f"[PriceAgent] ✓ {name} "
              f"{'BUY' if direction==1 else 'SELL'} "
              f"entry={entry} SL={sl} TP={tp} move=${move}")

    return signals


# ── Get current price ─────────────────────────────────────────
def get_live_price(ticker="GC=F"):
    """
    Fetch latest price for outcome tracking.
    Returns float or None.
    """
    try:
        df = yf.download(ticker, period="1d", interval="1m",
                         auto_adjust=True, progress=False, timeout=10)
        if df.empty:
            return None
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
        return float(df["close"].iloc[-1])
    except Exception as e:
        print(f"[PriceAgent] Live price error: {e}")
        return None


# ── Main entry point ──────────────────────────────────────────
def run(ticker="GC=F"):
    print(f"[PriceAgent] Fetching {ticker} via yfinance...")
    frames   = fetch_data(ticker)
    if not frames:
        print("[PriceAgent] No data fetched")
        return [], {}
    prepared = prepare_frames(frames)
    signals  = run_strategies(prepared)
    print(f"[PriceAgent] {len(signals)} signal(s) found")
    return signals, prepared


# ── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    sigs, _ = run()
    print(f"\n{'='*55}")
    if not sigs:
        print("No signals at this time.")
    for s in sigs:
        print(f"\nStrategy : {s.strategy}")
        print(f"Direction: {'BUY' if s.direction==1 else 'SELL'}")
        print(f"Entry    : {s.entry}")
        print(f"SL       : {s.sl}")
        print(f"TP       : {s.tp}")
        print(f"Move     : ${s.expected_move}")
        print(f"Reason   : {s.reason}")
        print(f"RSI      : {s.stats.get('rsi')}")
        print(f"ADX      : {s.stats.get('adx')}")
        print(f"Sharpe   : {s.stats.get('sharpe')}")
        print(f"7d Trend : {s.stats.get('trend_7d_pct')}%")