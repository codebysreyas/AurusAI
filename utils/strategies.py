import numpy as np
import pandas as pd


def _get_bias(df_entry, df_bias):
    return df_bias["trend_bias"].reindex(df_entry.index, method="ffill").fillna(0)


def _safe(val):
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except:
        return None


# ── 1. TREND PULLBACK ─────────────────────────────────────────
def trend_pullback(df_h1, df_h4):
    df   = df_h1
    bias = _get_bias(df, df_h4)
    for i in range(len(df)-1, max(len(df)-10, 200), -1):
        row = df.iloc[i]
        b   = bias.iloc[i]
        rsi = _safe(row.get("rsi"))
        e50 = _safe(row.get("ema50"))
        e200= _safe(row.get("ema200"))
        if None in [rsi, e50, e200]: continue
        if b == 1 and e50 > e200 and row["close"] > e50 and rsi < 40:
            return 1, f"H4 bull + RSI pullback {round(rsi,1)}"
        if b == -1 and e50 < e200 and row["close"] < e50 and rsi > 60:
            return -1, f"H4 bear + RSI pullback {round(rsi,1)}"
    return 0, "no signal"


# ── 2. TREND ACCELERATION ─────────────────────────────────────
def trend_acceleration(df_h1, df_h4):
    df   = df_h1
    bias = _get_bias(df, df_h4)
    ema50_vals = df["ema50"].values
    for i in range(len(df)-1, max(len(df)-10, 205), -1):
        row = df.iloc[i]
        b   = bias.iloc[i]
        rsi = _safe(row.get("rsi"))
        atr = _safe(row.get("atr"))
        atr_m50 = _safe(row.get("atr_m50"))
        e50 = _safe(row.get("ema50"))
        e200= _safe(row.get("ema200"))
        if None in [rsi, atr, e50, e200]: continue
        if atr_m50 and atr < atr_m50: continue
        slope = ema50_vals[i] - ema50_vals[i-5] if i >= 5 else 0
        if b == 1 and e50 > e200 and slope > atr * 0.2 and rsi > 55:
            return 1, f"H4 bull + EMA accelerating slope={round(slope,2)}"
        if b == -1 and e50 < e200 and slope < -atr * 0.2 and rsi < 45:
            return -1, f"H4 bear + EMA accelerating slope={round(slope,2)}"
    return 0, "no signal"


# ── 3. TREND + VOLATILITY EXPANSION ──────────────────────────
def trend_volatility_expansion(df_h1, df_h4):
    df   = df_h1
    bias = _get_bias(df, df_h4)
    for i in range(len(df)-1, max(len(df)-10, 200), -1):
        row    = df.iloc[i]
        b      = bias.iloc[i]
        atr    = _safe(row.get("atr"))
        atr_m20= _safe(row.get("atr_m20"))
        atr_m50= _safe(row.get("atr_m50"))
        e50    = _safe(row.get("ema50"))
        e200   = _safe(row.get("ema200"))
        if None in [atr, atr_m20, e50, e200]: continue
        if atr < atr_m20 * 1.2: continue
        if atr_m50 and atr < atr_m50: continue
        prev_h = df["high"].iloc[i-1]
        prev_l = df["low"].iloc[i-1]
        if b == 1 and e50 > e200 and row["close"] > prev_h:
            return 1, f"H4 bull + ATR expansion breakout"
        if b == -1 and e50 < e200 and row["close"] < prev_l:
            return -1, f"H4 bear + ATR expansion breakout"
    return 0, "no signal"


# ── 4. TREND FOLLOWING LOW DD ─────────────────────────────────
def trend_following_low_dd(df_h1, df_h4):
    df   = df_h1
    bias = _get_bias(df, df_h4)
    for i in range(len(df)-1, max(len(df)-10, 200), -1):
        row    = df.iloc[i]
        b      = bias.iloc[i]
        adx    = _safe(row.get("adx"))
        rsi    = _safe(row.get("rsi"))
        atr    = _safe(row.get("atr"))
        atr_m50= _safe(row.get("atr_m50"))
        e50    = _safe(row.get("ema50"))
        e200   = _safe(row.get("ema200"))
        hour   = df.index[i].hour
        if None in [adx, rsi, e50, e200]: continue
        if atr_m50 and atr < atr_m50 * 1.2: continue
        if adx < 20: continue
        if not (7 <= hour <= 17): continue
        if b == 1 and e50 > e200 and rsi > 50:
            return 1, f"H4 bull + ADX {round(adx,1)} trend confirmed"
        if b == -1 and e50 < e200 and rsi < 50:
            return -1, f"H4 bear + ADX {round(adx,1)} trend confirmed"
    return 0, "no signal"


# ── 5. WICK REJECTION REVERSAL ────────────────────────────────
def wick_rejection_reversal(df_m15, df_h1):
    h1_res = df_h1["high"].rolling(30).max().reindex(df_m15.index, method="ffill")
    h1_sup = df_h1["low"].rolling(30).min().reindex(df_m15.index, method="ffill")
    df     = df_m15
    for i in range(len(df)-1, max(len(df)-10, 200), -1):
        row    = df.iloc[i]
        atr    = _safe(row.get("atr"))
        atr_m50= _safe(row.get("atr_m50"))
        if None in [atr]: continue
        if atr_m50 and atr < atr_m50: continue
        body = abs(row["close"] - row["open"])
        uw   = row["high"] - max(row["open"], row["close"])
        lw   = min(row["open"], row["close"]) - row["low"]
        res  = h1_res.iloc[i]
        sup  = h1_sup.iloc[i]
        if pd.isna(res): continue
        if row["high"] >= res and uw > body * 2:
            return -1, f"Wick rejection at H1 resistance {round(res,2)}"
        if row["low"] <= sup and lw > body * 2:
            return 1, f"Wick rejection at H1 support {round(sup,2)}"
    return 0, "no signal"


# ── 6. LIQUIDITY SWEEP CONTINUATION ──────────────────────────
def liquidity_sweep_continuation(df_m5, df_m15):
    bias       = _get_bias(df_m5, df_m15)
    df         = df_m5
    recent_high= df["high"].rolling(20).max().values
    recent_low = df["low"].rolling(20).min().values
    for i in range(len(df)-1, max(len(df)-10, 200), -1):
        row    = df.iloc[i]
        b      = bias.iloc[i]
        atr    = _safe(row.get("atr"))
        atr_m50= _safe(row.get("atr_m50"))
        if atr is None: continue
        if atr_m50 and atr < atr_m50: continue
        if np.isnan(recent_high[i]): continue
        if b == 1 and row["low"] < recent_low[i-1] and row["close"] > recent_low[i-1]:
            return 1, "Liq sweep below low, reclaimed — long"
        if b == -1 and row["high"] > recent_high[i-1] and row["close"] < recent_high[i-1]:
            return -1, "Liq sweep above high, reclaimed — short"
    return 0, "no signal"


# ── 7. VWAP REVERSION ─────────────────────────────────────────
def vwap_reversion(df_m5, df_m15):
    m15_gap     = (df_m15["ema50"] - df_m15["ema200"]).abs()
    m15_ranging = (m15_gap < df_m15["atr"] * 0.5).astype(int)
    ranging     = m15_ranging.reindex(df_m5.index, method="ffill").fillna(0)
    df          = df_m5
    dates       = df.index.date
    vwap        = np.zeros(len(df))
    cum_p = 0; cnt = 0; cur_day = None
    for i in range(len(df)):
        if dates[i] != cur_day:
            cur_day = dates[i]; cum_p = 0; cnt = 0
        cum_p += df["close"].iloc[i]; cnt += 1
        vwap[i] = cum_p / cnt
    deviation = df["close"].values - vwap
    std_dev   = pd.Series(deviation).rolling(100).std().values
    for i in range(len(df)-1, max(len(df)-10, 200), -1):
        row    = df.iloc[i]
        atr    = _safe(row.get("atr"))
        atr_m50= _safe(row.get("atr_m50"))
        if atr is None: continue
        if atr_m50 and atr > atr_m50 * 1.3: continue
        if ranging.iloc[i] != 1: continue
        if np.isnan(std_dev[i]) or std_dev[i] == 0: continue
        if deviation[i] > std_dev[i] * 1.5:
            return -1, f"Above VWAP by {round(deviation[i],2)} — reversion short"
        if deviation[i] < -std_dev[i] * 1.5:
            return 1, f"Below VWAP by {round(abs(deviation[i]),2)} — reversion long"
    return 0, "no signal"


# ── 8. MEAN REVERSION ─────────────────────────────────────────
def mean_reversion(df_m15, df_h1):
    h1_gap     = (df_h1["ema50"] - df_h1["ema200"]).abs()
    h1_ranging = (h1_gap < df_h1["atr"] * 0.5).astype(int)
    ranging    = h1_ranging.reindex(df_m15.index, method="ffill").fillna(0)
    df         = df_m15
    for i in range(len(df)-1, max(len(df)-10, 200), -1):
        row      = df.iloc[i]
        atr      = _safe(row.get("atr"))
        atr_m50  = _safe(row.get("atr_m50"))
        rsi      = _safe(row.get("rsi"))
        bb_upper = _safe(row.get("bb_upper"))
        bb_lower = _safe(row.get("bb_lower"))
        if None in [atr, rsi, bb_upper, bb_lower]: continue
        if atr_m50 and atr > atr_m50 * 1.5: continue
        if ranging.iloc[i] != 1: continue
        if row["close"] > bb_upper and rsi > 70:
            return -1, f"BB upper + RSI {round(rsi,1)} — mean reversion short"
        if row["close"] < bb_lower and rsi < 30:
            return 1, f"BB lower + RSI {round(rsi,1)} — mean reversion long"
    return 0, "no signal"