# ============================================================
#  AurusAI — agents/macro_agent.py
# ============================================================

from dotenv import load_dotenv
load_dotenv()

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
from dataclasses import dataclass, field

from config import FRED_API_KEY

# ── FRED series ───────────────────────────────────────────────
SERIES_DXY   = "DTWEXBGS"
SERIES_FFR   = "FEDFUNDS"
SERIES_US10Y = "DGS10"
SERIES_US2Y  = "DGS2"

# ── yfinance correlated tickers ───────────────────────────────
CORR_TICKERS = {
    "silver" : "SI=F",
    "crude"  : "CL=F",
    "vix"    : "^VIX",
    "sp500"  : "^GSPC",
    "dxy_yf" : "DX-Y.NYB",
}

# ── ForexFactory blackout ─────────────────────────────────────
BLACKOUT_HOURS_BEFORE = 2
BLACKOUT_HOURS_AFTER  = 2


# ── Result dataclass ──────────────────────────────────────────
@dataclass
class MacroResult:
    vote          : str
    reason        : str
    blackout      : bool
    blackout_event: str
    dxy_trend     : str
    yield_trend   : str
    yield_curve   : str
    ffr           : float
    us10y         : float
    us2y          : float
    silver_trend  : str  = "flat"
    crude_trend   : str  = "flat"
    vix_level     : str  = "normal"
    sp500_trend   : str  = "flat"
    bullish_points: int  = 0
    bearish_points: int  = 0
    details       : dict = field(default_factory=dict)


# ── FRED helpers ──────────────────────────────────────────────
def _fetch_fred(series_id, periods=10):
    try:
        from fredapi import Fred
        key = os.environ.get("FRED_API_KEY", "")
        if not key:
            print(f"[MacroAgent] FRED_API_KEY is empty")
            return None
        client = Fred(api_key=key)
        data   = client.get_series(series_id).dropna().tail(periods)
        return data
    except Exception as e:
        print(f"[MacroAgent] FRED error {series_id}: {e}")
        return None


def _trend_fred(series):
    if series is None or len(series) < 6:
        return "flat"
    recent = series.iloc[-3:].mean()
    older  = series.iloc[-6:-3].mean()
    diff   = recent - older
    if diff >  0.05: return "rising"
    if diff < -0.05: return "falling"
    return "flat"


# ── yfinance correlated asset fetcher ─────────────────────────
def _fetch_yf(ticker, period="30d", interval="1d"):
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False, timeout=10)
        if df.empty:
            return None
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower()
                      for c in df.columns]
        return df["close"].dropna()
    except Exception as e:
        print(f"[MacroAgent] yfinance error {ticker}: {e}")
        return None


def _trend_yf(series, threshold_pct=0.3):
    if series is None or len(series) < 10:
        return "flat"
    recent = series.iloc[-5:].mean()
    older  = series.iloc[-10:-5].mean()
    if older == 0:
        return "flat"
    pct_change = (recent - older) / older * 100
    if pct_change >  threshold_pct: return "rising"
    if pct_change < -threshold_pct: return "falling"
    return "flat"


# ── ForexFactory blackout ─────────────────────────────────────
def _fetch_forexfactory_events():
    import requests
    from bs4 import BeautifulSoup
    events = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp    = requests.get("https://www.forexfactory.com/calendar",
                               headers=headers, timeout=10)
        soup    = BeautifulSoup(resp.text, "html.parser")
        rows    = soup.select("tr.calendar__row")
        for row in rows:
            impact = row.select_one(".calendar__impact span")
            if not impact: continue
            if not any("red" in c for c in impact.get("class", [])): continue
            currency = row.select_one(".calendar__currency")
            if not currency or "USD" not in currency.text: continue
            time_el  = row.select_one(".calendar__time")
            label_el = row.select_one(".calendar__event")
            if not time_el or not label_el: continue
            time_text = time_el.text.strip()
            label     = label_el.text.strip()
            try:
                if "am" in time_text.lower() or "pm" in time_text.lower():
                    t = datetime.strptime(time_text.upper(), "%I:%M%p")
                    hour_utc = (t.hour + 5) % 24
                    events.append((hour_utc, label))
            except:
                continue
        print(f"[MacroAgent] ForexFactory: {len(events)} high-impact USD events today")
    except Exception as e:
        print(f"[MacroAgent] ForexFactory scrape error: {e}")
    return events


def _check_blackout():
    now    = datetime.now(timezone.utc)
    events = _fetch_forexfactory_events()
    for (hour_utc, label) in events:
        event_time = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
        delta      = abs((now - event_time).total_seconds() / 3600)
        if delta <= BLACKOUT_HOURS_BEFORE:
            return True, label
    if now.weekday() == 4 and 12 <= now.hour <= 14:
        return True, "Possible NFP window (Friday 12–14 UTC)"
    return False, ""


# ── Main run ──────────────────────────────────────────────────
def run(signal_direction=0):
    print("[MacroAgent] Fetching FRED + correlated assets...")

    blackout, blackout_event = _check_blackout()
    if blackout:
        print(f"[MacroAgent] BLACKOUT: {blackout_event}")
        return MacroResult(
            vote="disagree", reason=f"News blackout: {blackout_event}",
            blackout=True, blackout_event=blackout_event,
            dxy_trend="flat", yield_trend="flat", yield_curve="flat",
            ffr=0.0, us10y=0.0, us2y=0.0,
        )

    # ── FRED data ─────────────────────────────────────────────
    dxy_data   = _fetch_fred(SERIES_DXY,   periods=10)
    ffr_data   = _fetch_fred(SERIES_FFR,   periods=5)
    us10y_data = _fetch_fred(SERIES_US10Y, periods=10)
    us2y_data  = _fetch_fred(SERIES_US2Y,  periods=10)

    ffr   = float(ffr_data.iloc[-1])   if ffr_data   is not None and len(ffr_data)   > 0 else 0.0
    us10y = float(us10y_data.iloc[-1]) if us10y_data is not None and len(us10y_data) > 0 else 0.0
    us2y  = float(us2y_data.iloc[-1])  if us2y_data  is not None and len(us2y_data)  > 0 else 0.0

    dxy_trend   = _trend_fred(dxy_data)
    yield_trend = _trend_fred(us10y_data)
    spread      = us10y - us2y
    if spread >  0.2:   yield_curve = "normal"
    elif spread < -0.2: yield_curve = "inverted"
    else:               yield_curve = "flat"

    # ── yfinance correlated assets ────────────────────────────
    print("[MacroAgent] Fetching correlated assets via yfinance...")

    silver_data = _fetch_yf(CORR_TICKERS["silver"])
    crude_data  = _fetch_yf(CORR_TICKERS["crude"])
    vix_data    = _fetch_yf(CORR_TICKERS["vix"])
    sp500_data  = _fetch_yf(CORR_TICKERS["sp500"])
    dxy_yf_data = _fetch_yf(CORR_TICKERS["dxy_yf"])

    silver_trend = _trend_yf(silver_data)
    crude_trend  = _trend_yf(crude_data)
    sp500_trend  = _trend_yf(sp500_data)

    # DXY fallback
    if dxy_trend == "flat" and dxy_yf_data is not None:
        dxy_trend = _trend_yf(dxy_yf_data)
        print(f"[MacroAgent] DXY from yfinance fallback: {dxy_trend}")

    # VIX level
    vix_current = float(vix_data.iloc[-1]) if vix_data is not None and len(vix_data) > 0 else 0.0
    if vix_current >= 30:   vix_level = "extreme"
    elif vix_current >= 20: vix_level = "elevated"
    else:                   vix_level = "normal"

    print(f"[MacroAgent] Silver={silver_trend} Crude={crude_trend} "
          f"VIX={round(vix_current,1)}({vix_level}) SP500={sp500_trend}")

    # ── scoring ───────────────────────────────────────────────
    bullish = 0
    bearish = 0

    if dxy_trend    == "falling": bullish += 1
    if dxy_trend    == "rising":  bearish += 1
    if yield_trend  == "falling": bullish += 1
    if yield_trend  == "rising":  bearish += 1
    if yield_curve  == "inverted":bullish += 1

    if silver_trend == "rising":  bullish += 1
    if silver_trend == "falling": bearish += 1

    if crude_trend  == "rising":  bullish += 1
    if crude_trend  == "falling": bearish += 1

    if vix_level in ("elevated","extreme"): bullish += 1
    if vix_level == "normal":               bearish += 1

    if sp500_trend  == "falling": bullish += 1
    if sp500_trend  == "rising":  bearish += 1

    if bullish > bearish:   macro_bias = "bullish"
    elif bearish > bullish: macro_bias = "bearish"
    else:                   macro_bias = "neutral"

    # ── vote ──────────────────────────────────────────────────
    if signal_direction == 0:
        vote   = "neutral"
        reason = f"No direction — macro is {macro_bias} ({bullish}B/{bearish}Be)"
    elif signal_direction == 1 and macro_bias == "bullish":
        vote   = "agree"
        reason = (f"Macro bullish ({bullish}/{bullish+bearish}) agrees with LONG — "
                  f"DXY {dxy_trend} | Silver {silver_trend} | VIX {vix_level}")
    elif signal_direction == -1 and macro_bias == "bearish":
        vote   = "agree"
        reason = (f"Macro bearish ({bearish}/{bullish+bearish}) agrees with SHORT — "
                  f"DXY {dxy_trend} | Silver {silver_trend} | VIX {vix_level}")
    elif macro_bias == "neutral":
        vote   = "neutral"
        reason = f"Macro neutral ({bullish}B/{bearish}Be) — mixed signals"
    else:
        vote   = "disagree"
        reason = (f"Macro {macro_bias} ({bullish}B/{bearish}Be) disagrees — "
                  f"DXY {dxy_trend} | Silver {silver_trend} | VIX {vix_level}")

    result = MacroResult(
        vote          =vote,
        reason        =reason,
        blackout      =False,
        blackout_event="",
        dxy_trend     =dxy_trend,
        yield_trend   =yield_trend,
        yield_curve   =yield_curve,
        ffr           =round(ffr,   3),
        us10y         =round(us10y, 3),
        us2y          =round(us2y,  3),
        silver_trend  =silver_trend,
        crude_trend   =crude_trend,
        vix_level     =vix_level,
        sp500_trend   =sp500_trend,
        bullish_points=bullish,
        bearish_points=bearish,
        details       ={
            "dxy_trend"   : dxy_trend,
            "yield_trend" : yield_trend,
            "yield_curve" : yield_curve,
            "spread_10y2y": round(spread, 3),
            "ffr"         : round(ffr,    3),
            "us10y"       : round(us10y,  3),
            "us2y"        : round(us2y,   3),
            "silver_trend": silver_trend,
            "crude_trend" : crude_trend,
            "vix"         : round(vix_current, 1),
            "vix_level"   : vix_level,
            "sp500_trend" : sp500_trend,
            "bullish_pts" : bullish,
            "bearish_pts" : bearish,
            "macro_bias"  : macro_bias,
        }
    )

    print(f"[MacroAgent] DXY={dxy_trend} Yields={yield_trend} "
          f"Silver={silver_trend} Crude={crude_trend} "
          f"VIX={vix_level} SP500={sp500_trend}")
    print(f"[MacroAgent] Score: {bullish} bullish / {bearish} bearish → {macro_bias}")
    print(f"[MacroAgent] Vote={vote} — {reason}")

    return result


# ── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    result = run(signal_direction=1)
    print(f"\n{'='*55}")
    print(f"Vote          : {result.vote}")
    print(f"Reason        : {result.reason}")
    print(f"Blackout      : {result.blackout}")
    print(f"DXY Trend     : {result.dxy_trend}")
    print(f"Yield Trend   : {result.yield_trend}")
    print(f"Yield Curve   : {result.yield_curve}")
    print(f"Silver        : {result.silver_trend}")
    print(f"Crude Oil     : {result.crude_trend}")
    print(f"VIX Level     : {result.vix_level}")
    print(f"SP500         : {result.sp500_trend}")
    print(f"Bullish pts   : {result.bullish_points}")
    print(f"Bearish pts   : {result.bearish_points}")
    print(f"Fed Funds     : {result.ffr}%")
    print(f"US 10Y        : {result.us10y}%")
    print(f"US 2Y         : {result.us2y}%")
    print(f"Details       : {result.details}")