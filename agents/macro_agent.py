from datetime import timezone
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from fredapi import Fred

from config import FRED_API_KEY


# ── FRED client ───────────────────────────────────────────────
fred = Fred(api_key=FRED_API_KEY)


# ── FRED series IDs ───────────────────────────────────────────
# DXY — US Dollar Index (Trade Weighted, Broad)
SERIES_DXY      = "DTWEXBGS"
# Fed Funds Rate
SERIES_FFR      = "FEDFUNDS"
# US 10Y Treasury Yield
SERIES_US10Y    = "DGS10"
# US 2Y Treasury Yield (for yield curve)
SERIES_US2Y     = "DGS2"


# ── High impact news schedule ─────────────────────────────────
# Format: (month, day, hour_utc, label)
# Update this list monthly with actual release dates
# These are approximate — replace with real calendar dates
BLACKOUT_HOURS_BEFORE = 2
BLACKOUT_HOURS_AFTER  = 2


def _fetch_forexfactory_events():
    """
    Scrape ForexFactory calendar for today's high-impact USD events.
    Returns list of (hour_utc, label) tuples.
    """
    import requests
    from bs4 import BeautifulSoup

    events = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url     = "https://www.forexfactory.com/calendar"
        resp    = requests.get(url, headers=headers, timeout=10)
        soup    = BeautifulSoup(resp.text, "html.parser")

        rows = soup.select("tr.calendar__row")
        for row in rows:
            # impact
            impact = row.select_one(".calendar__impact span")
            if not impact: continue
            impact_class = impact.get("class", [])
            if not any("red" in c for c in impact_class):
                continue

            # currency
            currency = row.select_one(".calendar__currency")
            if not currency: continue
            if "USD" not in currency.text:
                continue

            # time
            time_el = row.select_one(".calendar__time")
            label_el= row.select_one(".calendar__event")
            if not time_el or not label_el: continue

            time_text = time_el.text.strip()
            label     = label_el.text.strip()

            # parse hour — ForexFactory shows time in EST
            try:
                if "am" in time_text.lower() or "pm" in time_text.lower():
                    t = datetime.strptime(time_text.upper(), "%I:%M%p")
                    # convert EST to UTC (+5)
                    hour_utc = (t.hour + 5) % 24
                    events.append((hour_utc, label))
            except:
                continue

        print(f"[MacroAgent] ForexFactory: {len(events)} high-impact USD events today")
    except Exception as e:
        print(f"[MacroAgent] ForexFactory scrape error: {e}")

    return events


# ── Result dataclass ──────────────────────────────────────────
@dataclass
class MacroResult:
    vote          : str    # "agree" | "disagree" | "neutral"
    reason        : str
    blackout      : bool
    blackout_event: str
    dxy_trend     : str    # "rising" | "falling" | "flat"
    yield_trend   : str    # "rising" | "falling" | "flat"
    yield_curve   : str    # "normal" | "inverted" | "flat"
    ffr           : float
    us10y         : float
    us2y          : float
    details       : dict   = field(default_factory=dict)


# ── Fetch helpers ─────────────────────────────────────────────
def _fetch_series(series_id, periods=10):
    """Fetch last N observations from FRED."""
    try:
        data = fred.get_series(series_id)
        data = data.dropna().tail(periods)
        return data
    except Exception as e:
        print(f"[MacroAgent] FRED fetch error {series_id}: {e}")
        return None


def _trend(series):
    """Simple trend from last 5 vs previous 5 observations."""
    if series is None or len(series) < 6:
        return "flat"
    recent = series.iloc[-3:].mean()
    older  = series.iloc[-6:-3].mean()
    diff   = recent - older
    if diff > 0.05:  return "rising"
    if diff < -0.05: return "falling"
    return "flat"


# ── Blackout check ────────────────────────────────────────────
def _check_blackout():
    now    = datetime.now(timezone.utc)
    events = _fetch_forexfactory_events()

    for (hour_utc, label) in events:
        event_time = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
        delta      = abs((now - event_time).total_seconds() / 3600)
        if delta <= BLACKOUT_HOURS_BEFORE:
            return True, label

    # Friday 12–14 UTC safety window for NFP
    if now.weekday() == 4 and 12 <= now.hour <= 14:
        return True, "Possible NFP window (Friday 12–14 UTC)"

    return False, ""


# ── Main run ──────────────────────────────────────────────────
def run(signal_direction=0):
    """
    Main entry point.
    signal_direction: 1=long, -1=short, 0=unknown
    Returns MacroResult.
    """
    print("[MacroAgent] Fetching FRED data...")

    # blackout check first — fastest exit
    blackout, blackout_event = _check_blackout()
    if blackout:
        print(f"[MacroAgent] BLACKOUT: {blackout_event}")
        return MacroResult(
            vote          ="disagree",
            reason        =f"News blackout: {blackout_event}",
            blackout      =True,
            blackout_event=blackout_event,
            dxy_trend     ="flat",
            yield_trend   ="flat",
            yield_curve   ="flat",
            ffr           =0.0,
            us10y         =0.0,
            us2y          =0.0,
        )

    # fetch data
    dxy_data  = _fetch_series(SERIES_DXY,  periods=10)
    ffr_data  = _fetch_series(SERIES_FFR,  periods=5)
    us10y_data= _fetch_series(SERIES_US10Y,periods=10)
    us2y_data = _fetch_series(SERIES_US2Y, periods=10)

    # current values
    ffr   = float(ffr_data.iloc[-1])   if ffr_data   is not None and len(ffr_data)   > 0 else 0.0
    us10y = float(us10y_data.iloc[-1]) if us10y_data is not None and len(us10y_data) > 0 else 0.0
    us2y  = float(us2y_data.iloc[-1])  if us2y_data  is not None and len(us2y_data)  > 0 else 0.0

    # trends
    dxy_trend   = _trend(dxy_data)
    yield_trend = _trend(us10y_data)

    # yield curve
    spread = us10y - us2y
    if spread > 0.2:   yield_curve = "normal"
    elif spread < -0.2:yield_curve = "inverted"
    else:               yield_curve = "flat"

    # macro vote for gold
    # Gold is bullish when: DXY falling + yields falling/flat
    # Gold is bearish when: DXY rising  + yields rising
    bullish_points = 0
    bearish_points = 0

    if dxy_trend   == "falling": bullish_points += 1
    if dxy_trend   == "rising":  bearish_points += 1
    if yield_trend == "falling": bullish_points += 1
    if yield_trend == "rising":  bearish_points += 1
    if yield_curve == "inverted":bullish_points += 1  # risk-off = gold up

    if bullish_points > bearish_points:
        macro_bias = "bullish"
    elif bearish_points > bullish_points:
        macro_bias = "bearish"
    else:
        macro_bias = "neutral"

    # compare with signal direction
    if signal_direction == 0:
        vote   = "neutral"
        reason = f"No signal direction to compare — macro is {macro_bias}"
    elif signal_direction == 1 and macro_bias == "bullish":
        vote   = "agree"
        reason = f"Macro bullish agrees with LONG — DXY {dxy_trend}, yields {yield_trend}"
    elif signal_direction == -1 and macro_bias == "bearish":
        vote   = "agree"
        reason = f"Macro bearish agrees with SHORT — DXY {dxy_trend}, yields {yield_trend}"
    elif macro_bias == "neutral":
        vote   = "neutral"
        reason = f"Macro neutral — DXY {dxy_trend}, yields {yield_trend}"
    else:
        vote   = "disagree"
        reason = f"Macro {macro_bias} disagrees with signal — DXY {dxy_trend}, yields {yield_trend}"

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
        details       ={
            "dxy_trend"   : dxy_trend,
            "yield_trend" : yield_trend,
            "yield_curve" : yield_curve,
            "spread_10y2y": round(spread, 3),
            "ffr"         : round(ffr,    3),
            "us10y"       : round(us10y,  3),
            "us2y"        : round(us2y,   3),
            "macro_bias"  : macro_bias,
        }
    )

    print(f"[MacroAgent] DXY={dxy_trend} Yields={yield_trend} "
          f"Curve={yield_curve} FFR={ffr}% 10Y={us10y}%")
    print(f"[MacroAgent] Vote={vote} — {reason}")

    return result


# ── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # test with a long signal
    result = run(signal_direction=1)
    print(f"\n{'='*50}")
    print(f"Vote         : {result.vote}")
    print(f"Reason       : {result.reason}")
    print(f"Blackout     : {result.blackout}")
    print(f"DXY Trend    : {result.dxy_trend}")
    print(f"Yield Trend  : {result.yield_trend}")
    print(f"Yield Curve  : {result.yield_curve}")
    print(f"Fed Funds    : {result.ffr}%")
    print(f"US 10Y       : {result.us10y}%")
    print(f"US 2Y        : {result.us2y}%")
    print(f"Details      : {result.details}")