import numpy as np
import pandas as pd


def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calc_atr(df, period=14):
    hi, lo, cl = df["high"], df["low"], df["close"]
    tr = pd.concat([
        hi - lo,
        (hi - cl.shift()).abs(),
        (lo - cl.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast    = series.ewm(span=fast,   adjust=False).mean()
    ema_slow    = series.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(series, period=20, std_dev=2):
    ma    = series.rolling(period).mean()
    std   = series.rolling(period).std()
    upper = ma + std_dev * std
    lower = ma - std_dev * std
    return upper, ma, lower


def calc_adx(df, period=14):
    hi, lo, cl = df["high"], df["low"], df["close"]
    plus_dm    = hi.diff().clip(lower=0)
    minus_dm   = (-lo.diff()).clip(lower=0)
    plus_dm[plus_dm   < minus_dm] = 0
    minus_dm[minus_dm < plus_dm]  = 0
    tr = pd.concat([
        hi - lo,
        (hi - cl.shift()).abs(),
        (lo - cl.shift()).abs()
    ], axis=1).max(axis=1)
    atr_  = tr.rolling(period).mean()
    pdi   = 100 * plus_dm.rolling(period).mean() / atr_
    mdi   = 100 * minus_dm.rolling(period).mean() / atr_
    dx    = (abs(pdi - mdi) / (pdi + mdi + 1e-9)) * 100
    return dx.rolling(period).mean(), pdi, mdi


def calc_sharpe(returns, risk_free=0.0, periods=252):
    excess = returns - risk_free / periods
    if excess.std() == 0:
        return 0.0
    return float(round((excess.mean() / excess.std()) * np.sqrt(periods), 3))


def calc_annualised_volatility(returns, periods=252):
    return float(round(returns.std() * np.sqrt(periods) * 100, 2))


def add_all_indicators(df):
    df = df.copy()
    df["ema50"]    = calc_ema(df["close"], 50)
    df["ema200"]   = calc_ema(df["close"], 200)
    df["atr"]      = calc_atr(df)
    df["atr_m50"]  = df["atr"].rolling(50).mean()
    df["atr_m20"]  = df["atr"].rolling(20).mean()
    df["rsi"]      = calc_rsi(df["close"])
    df["macd"], df["macd_signal"], df["macd_hist"] = calc_macd(df["close"])
    df["bb_upper"], df["bb_mid"], df["bb_lower"]   = calc_bollinger(df["close"])
    df["adx"], df["plus_di"], df["minus_di"]       = calc_adx(df)
    df["body"]         = (df["close"] - df["open"]).abs()
    df["avg_body"]     = df["body"].rolling(50).mean()
    df["candle_range"] = df["high"] - df["low"]
    df["returns"]      = df["close"].pct_change()
    df["trend_bias"]   = 0
    df.loc[df["ema50"] > df["ema200"], "trend_bias"] =  1
    df.loc[df["ema50"] < df["ema200"], "trend_bias"] = -1
    return df


def get_summary_stats(df):
    if len(df) < 50:
        return {}

    latest  = df.iloc[-1]
    returns = df["returns"].dropna().tail(252)

    trend_7d = None
    if len(df) >= 7:
        trend_7d = round(
            (df["close"].iloc[-1] - df["close"].iloc[-7]) /
            df["close"].iloc[-7] * 100, 2
        )

    def safe(val):
        try:
            if val is None: return None
            f = float(val)
            return None if np.isnan(f) else round(f, 4)
        except:
            return None

    return {
        "rsi":            safe(latest.get("rsi")),
        "macd":           safe(latest.get("macd")),
        "macd_signal":    safe(latest.get("macd_signal")),
        "macd_hist":      safe(latest.get("macd_hist")),
        "bb_upper":       safe(latest.get("bb_upper")),
        "bb_lower":       safe(latest.get("bb_lower")),
        "atr":            safe(latest.get("atr")),
        "adx":            safe(latest.get("adx")),
        "ema50":          safe(latest.get("ema50")),
        "ema200":         safe(latest.get("ema200")),
        "trend_7d_pct":   trend_7d,
        "sharpe":         calc_sharpe(returns),
        "ann_volatility": calc_annualised_volatility(returns),
        "close":          safe(latest.get("close")),
    }