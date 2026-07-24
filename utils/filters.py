import numpy as np
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import MIN_TP_MOVE, MIN_CANDLE_RANGE, MIN_BODY_RATIO, MIN_ATR_RATIO


def passes_global_filters(row, atr, avg_body, rr):
    # 1. Minimum TP
    if atr * rr < MIN_TP_MOVE:
        return False, f"TP too small: ${round(atr*rr,2)} < ${MIN_TP_MOVE}"

    # 2. Dead candle
    candle_range = row["high"] - row["low"]
    if candle_range < MIN_CANDLE_RANGE:
        return False, f"Dead candle: range ${round(candle_range,2)}"

    # 3. Low volatility
    atr_m50 = row.get("atr_m50")
    if atr_m50 and not np.isnan(float(atr_m50)):
        if atr < float(atr_m50) * MIN_ATR_RATIO:
            return False, f"Low volatility: ATR {round(atr,2)}"

    # 4. Tiny body
    body = abs(row["close"] - row["open"])
    if avg_body and not np.isnan(float(avg_body)) and float(avg_body) > 0:
        if body < float(avg_body) * MIN_BODY_RATIO:
            return False, f"Tiny candle body"

    return True, "ok"


def passes_trend_filters(df, i, direction):
    row = df.iloc[i]

    # 5. ADX < 15
    adx = row.get("adx")
    if adx is not None and not np.isnan(float(adx)):
        if float(adx) < 15:
            return False, f"No trend: ADX {round(float(adx),2)}"

    # 6. Wicks both sides
    body       = abs(row["close"] - row["open"])
    upper_wick = row["high"] - max(row["open"], row["close"])
    lower_wick = min(row["open"], row["close"]) - row["low"]
    if body > 0:
        if upper_wick > body * 0.8 and lower_wick > body * 0.8:
            return False, "Indecision candle"

    # 7. Momentum: 2 of last 3 candles agree
    if i >= 3:
        count = 0
        for k in [i-1, i-2, i-3]:
            c = df.iloc[k]["close"]
            o = df.iloc[k]["open"]
            if direction ==  1 and c > o: count += 1
            if direction == -1 and c < o: count += 1
        if count < 2:
            return False, f"Weak momentum: {count}/3 candles agree"

    return True, "ok"


def check_all_filters(df, i, direction, rr, stype):
    row      = df.iloc[i]
    atr      = float(row.get("atr", 0) or 0)
    avg_body = float(row.get("avg_body", 0) or 0)

    passed, reason = passes_global_filters(row, atr, avg_body, rr)
    if not passed:
        return False, reason

    if stype in ("trend", "breakout"):
        passed, reason = passes_trend_filters(df, i, direction)
        if not passed:
            return False, reason

    return True, "ok"