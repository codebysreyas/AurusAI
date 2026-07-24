import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import feedparser
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL


# ── Groq client ───────────────────────────────────────────────
groq_client = Groq(api_key=GROQ_API_KEY)


# ── RSS feeds — gold related ──────────────────────────────────
RSS_FEEDS = [
    {
        "name": "Yahoo Finance Gold",
        "url" : "https://finance.yahoo.com/rss/headline?s=GC%3DF",
    },
    {
        "name": "Reuters Business",
        "url" : "https://feeds.reuters.com/reuters/businessNews",
    },
    {
        "name": "MarketWatch",
        "url" : "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    },
]

# keywords to filter relevant headlines
GOLD_KEYWORDS = [
    "gold", "xauusd", "bullion", "precious metal",
    "fed", "federal reserve", "inflation", "dollar", "dxy",
    "yield", "treasury", "rate", "fomc", "cpi", "nfp",
]


# ── Cache ─────────────────────────────────────────────────────
_cache = {
    "timestamp": None,
    "result"   : None,
}
CACHE_MINUTES = 60


# ── Result dataclass ──────────────────────────────────────────
@dataclass
class SentimentResult:
    vote     : str
    score    : int
    summary  : str
    headlines: list = field(default_factory=list)
    cached   : bool = False
    error    : bool = False


# ── Fetch RSS headlines ───────────────────────────────────────
def _fetch_headlines():
    """
    Fetch and filter gold-relevant headlines from RSS feeds.
    Returns list of headline strings, max 15.
    """
    all_headlines = []

    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            count = 0
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                # filter for gold-relevant headlines
                title_lower = title.lower()
                if any(kw in title_lower for kw in GOLD_KEYWORDS):
                    all_headlines.append(title)
                    count += 1
                if count >= 5:
                    break
            print(f"[SentimentAgent] {feed_info['name']}: {count} relevant headlines")
        except Exception as e:
            print(f"[SentimentAgent] RSS error {feed_info['name']}: {e}")

    # deduplicate and limit
    seen = set()
    unique = []
    for h in all_headlines:
        if h not in seen:
            seen.add(h)
            unique.append(h)
        if len(unique) >= 15:
            break

    print(f"[SentimentAgent] Total: {len(unique)} unique headlines")
    return unique


# ── Score with Groq ───────────────────────────────────────────
def _score_with_ai(headlines):
    if not headlines:
        return "neutral", 0, "No headlines available"

    headlines_text = "\n".join([f"- {h}" for h in headlines])

    prompt = f"""You are a gold market analyst. Analyse these recent headlines and determine gold market sentiment.

Headlines:
{headlines_text}

Respond in this exact JSON format only, no other text:
{{
  "vote": "bullish" or "bearish" or "neutral",
  "score": a number from -2 (very bearish) to +2 (very bullish),
  "summary": "one sentence explanation under 20 words"
}}"""

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.1,
        )

        raw = response.choices[0].message.content.strip()

        # strip markdown fences if present
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data    = json.loads(raw.strip())
        vote    = data.get("vote",    "neutral")
        score   = int(data.get("score", 0))
        summary = data.get("summary", "No summary")

        if vote not in ("bullish", "bearish", "neutral"):
            vote = "neutral"
        score = max(-2, min(2, score))

        return vote, score, summary

    except json.JSONDecodeError as e:
        print(f"[SentimentAgent] JSON parse error: {e}")
        return "neutral", 0, "Could not parse AI response"
    except Exception as e:
        print(f"[SentimentAgent] Groq error: {e}")
        return "neutral", 0, "AI scoring unavailable"


# ── Main run ──────────────────────────────────────────────────
def run(signal_direction=0, force_refresh=False):
    # check cache
    if not force_refresh and _cache["timestamp"] is not None:
        age = (datetime.now(timezone.utc) - _cache["timestamp"]).total_seconds() / 60
        if age < CACHE_MINUTES:
            print(f"[SentimentAgent] Using cached result ({int(age)}min old)")
            cached        = _cache["result"]
            cached.cached = True
            return cached

    print("[SentimentAgent] Fetching RSS headlines...")
    headlines = _fetch_headlines()

    if not headlines:
        return SentimentResult(
            vote    ="neutral",
            score   =0,
            summary ="No headlines fetched",
            error   =True,
        )

    print("[SentimentAgent] Scoring with Groq AI...")
    vote, score, summary = _score_with_ai(headlines)
    print(f"[SentimentAgent] Vote={vote} Score={score} — {summary}")

    result = SentimentResult(
        vote     =vote,
        score    =score,
        summary  =summary,
        headlines=headlines,
        cached   =False,
        error    =False,
    )

    _cache["timestamp"] = datetime.now(timezone.utc)
    _cache["result"]    = result
    return result


# ── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    result = run(signal_direction=1)
    print(f"\n{'='*50}")
    print(f"Vote     : {result.vote}")
    print(f"Score    : {result.score}")
    print(f"Summary  : {result.summary}")
    print(f"Cached   : {result.cached}")
    print(f"Error    : {result.error}")
    print(f"\nHeadlines ({len(result.headlines)}):")
    for h in result.headlines:
        print(f"  - {h}")