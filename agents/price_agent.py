import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field

from utils.indicators import add_all_indicators, get_summary_stats
from utils.strategies import (
    trend_pullback, trend_acceleration,
    trend_volatility_expansion, trend_following_low_dd,
    wick_rejection_reversal, liquidity_sweep_continuation,
    vwap_reversion, mean_reversion,
)
from utils.filters import check_all_filters
from config import STRATEGIES, MT5_SYMBOL, MT5_BARS


# ── Data class ───────────────────────────────────────────────
@dataclass
class SignalResult:
    strategy    : str
    stype       : str
    direction   : int
    entry       : float
    sl          : float
    tp          : float
    rr          : float
    atr         : float
    expected_move: float
    reason      : str
    filter_run  : str
    pf          : float
    timestamp   : datetime = field(default_factory=datetime.utcnow)
    stats       : dict     = field(default_factory=dict)


# ── MT5 connection ────────────────────────────────────────────
def connect_mt5():
    if not mt5.initialize():
        print(f"[PriceAgent] MT5 init failed: {mt5.last_error()}")
        return False
    print(f"[PriceAgent] MT5 connected — {mt5.terminal_info().name}")
    return True


def disconnect_mt5():
    mt5.shutdown()


# ── Fetch OHLCV ───────────────────────────────────────────────
TF_MAP = {
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
}

def fetch_data():
    frames = {}
    for tf_name, tf_const in TF_MAP.items():
        rates = mt5.copy_rates_from_pos(MT5_SYMBOL, tf_const, 0, MT5_BARS)
        if rates is None or len(rates) == 0:
            print(f"[PriceAgent] No data for {tf_name}: {mt5.last_error()}")
            continue
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        df.rename(columns={
            "open": "open", "high": "high",
            "low": "low",   "close": "close",
            "tick_volume": "volume"
        }, inplace=True)
        df = df[["open","high","low","close","volume"]].copy()
        frames[tf_name] = df
        print(f"[PriceAgent] {tf_name}: {len(df)} bars fetched")
    return frames


# ── Prepare indicators ────────────────────────────────────────
def prepare_frames(frames):
    return {tf: add_all_indicators(df) for tf, df in frames.items()}


# ── Run all strategies ────────────────────────────────────────
def run_strategies(frames):
    signals = []

    df_m5  = frames.get("M5")
    df_m15 = frames.get("M15")
    df_h1  = frames.get("H1")
    df_h4  = frames.get("H4")

    if df_h1 is None or df_m15 is None:
        print("[PriceAgent] Missing required timeframes H1/M15")
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
            print(f"[PriceAgent] {name} blocked by filter: {filter_reason}")
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


# ── Main entry point ──────────────────────────────────────────
def run():
    if not connect_mt5():
        return [], {}
    try:
        print(f"[PriceAgent] Fetching {MT5_SYMBOL}...")
        frames   = fetch_data()
        prepared = prepare_frames(frames)
        signals  = run_strategies(prepared)
        print(f"[PriceAgent] {len(signals)} signal(s) found")
        return signals, prepared
    finally:
        disconnect_mt5()


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
        print(f"Ann.Vol  : {s.stats.get('ann_volatility')}%")
        print(f"7d Trend : {s.stats.get('trend_7d_pct')}%")