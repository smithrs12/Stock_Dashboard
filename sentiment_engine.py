import math
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from config import config
from redis_store import store


ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"

BULLISH_KEYWORDS = {
    "beats": 1.2,
    "beat": 1.0,
    "surge": 1.0,
    "rally": 1.0,
    "upgrade": 1.1,
    "raised": 0.9,
    "raises": 0.9,
    "strong": 0.6,
    "growth": 0.7,
    "record": 0.8,
    "profit": 0.8,
    "profits": 0.8,
    "partnership": 1.0,
    "contract": 1.0,
    "expands": 0.8,
    "expansion": 0.8,
    "approval": 1.2,
    "approved": 1.2,
    "breakthrough": 1.0,
    "acquires": 0.8,
    "acquisition": 0.7,
    "buyback": 1.0,
    "guidance raised": 1.4,
    "earnings beat": 1.5,
    "revenue beat": 1.3,
    "upside": 0.7,
}

BEARISH_KEYWORDS = {
    "miss": -1.1,
    "misses": -1.1,
    "plunge": -1.2,
    "drop": -0.8,
    "falls": -0.8,
    "downgrade": -1.2,
    "cut": -0.8,
    "cuts": -0.8,
    "weak": -0.7,
    "warning": -1.0,
    "warns": -1.0,
    "investigation": -1.1,
    "lawsuit": -1.0,
    "probe": -1.0,
    "offering": -1.2,
    "dilution": -1.2,
    "guidance cut": -1.4,
    "earnings miss": -1.5,
    "revenue miss": -1.3,
    "bankruptcy": -2.0,
    "fraud": -1.8,
    "sec investigation": -1.5,
    "recall": -1.0,
    "delay": -0.8,
    "decline": -0.7,
    "downside": -0.7,
}

CATALYST_PATTERNS = {
    "earnings": [
        "earnings",
        "quarterly results",
        "q1",
        "q2",
        "q3",
        "q4",
        "guidance",
    ],
    "analyst": [
        "upgrade",
        "downgrade",
        "price target",
        "initiates coverage",
        "analyst",
    ],
    "fda": [
        "fda",
        "approval",
        "clinical",
        "trial",
        "phase 1",
        "phase 2",
        "phase 3",
    ],
    "mna": [
        "merger",
        "acquisition",
        "acquires",
        "buyout",
        "takeover",
    ],
    "offering": [
        "offering",
        "secondary",
        "dilution",
        "convertible note",
        "share sale",
    ],
    "legal": [
        "lawsuit",
        "investigation",
        "probe",
        "sec",
        "department of justice",
        "doj",
    ],
    "contract": [
        "contract",
        "partnership",
        "deal",
        "award",
        "customer",
        "signs",
    ],
    "macro": [
        "cpi",
        "fed",
        "rates",
        "treasury yields",
        "inflation",
        "jobs report",
    ],
}


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def recency_weight(created_at: str | None) -> float:
    dt = parse_dt(created_at)
    if not dt:
        return 0.5

    age_minutes = max((utc_now() - dt).total_seconds() / 60, 0)

    if age_minutes <= 15:
        return 1.4
    if age_minutes <= 60:
        return 1.2
    if age_minutes <= 180:
        return 1.0
    if age_minutes <= 360:
        return 0.8
    if age_minutes <= 720:
        return 0.6
    return 0.4


def score_text_sentiment(text: str) -> float:
    if not text:
        return 0.0

    lowered = text.lower()
    score = 0.0

    for phrase, weight in BULLISH_KEYWORDS.items():
        if phrase in lowered:
            score += weight

    for phrase, weight in BEARISH_KEYWORDS.items():
        if phrase in lowered:
            score += weight

    return score


def detect_catalysts(text: str) -> list[str]:
    if not text:
        return []

    lowered = text.lower()
    catalysts = []

    for label, phrases in CATALYST_PATTERNS.items():
        if any(phrase in lowered for phrase in phrases):
            catalysts.append(label)

    return catalysts


def fetch_news(ticker: str, limit: int = 20, lookback_hours: int = 24) -> list[dict]:
    cache_key = f"news_raw:{ticker}"
    cached = store.get_json(cache_key, default=None)
    if cached is not None:
        return cached

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        return []

    start = (utc_now() - timedelta(hours=lookback_hours)).isoformat()

    headers = {
        "APCA-API-KEY-ID": config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
    }

    params = {
        "symbols": ticker,
        "start": start,
        "limit": limit,
        "sort": "desc",
    }

    try:
        response = requests.get(
            ALPACA_NEWS_URL,
            headers=headers,
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            articles = payload.get("news", [])
        elif isinstance(payload, list):
            articles = payload
        else:
            articles = []

        store.set_json(cache_key, articles, ttl=90)
        return articles

    except Exception as exc:
        print(f"[sentiment_engine] failed to fetch news for {ticker}: {exc}")
        return []


def summarize_articles(articles: list[dict], max_items: int = 5) -> list[dict]:
    summaries = []

    for article in articles[:max_items]:
        headline = article.get("headline", "") or ""
        summary = article.get("summary", "") or ""
        created_at = article.get("created_at")
        text = f"{headline}. {summary}".strip()

        raw_score = score_text_sentiment(text)
        weight = recency_weight(created_at)
        weighted_score = raw_score * weight
        catalysts = detect_catalysts(text)

        summaries.append(
            {
                "headline": headline,
                "summary": summary,
                "created_at": created_at,
                "source": article.get("source"),
                "url": article.get("url"),
                "sentiment_score": round(weighted_score, 4),
                "catalysts": catalysts,
            }
        )

    return summaries


def article_count_windows(articles: list[dict]) -> tuple[int, int]:
    now = utc_now()
    recent_60m = 0
    recent_6h = 0

    for article in articles:
        dt = parse_dt(article.get("created_at"))
        if not dt:
            continue

        age = now - dt
        if age <= timedelta(hours=1):
            recent_60m += 1
        if age <= timedelta(hours=6):
            recent_6h += 1

    return recent_60m, recent_6h


def classify_sentiment(score: float) -> str:
    if score >= 0.35:
        return "bullish"
    if score <= -0.35:
        return "bearish"
    return "neutral"


def get_sentiment_snapshot(ticker: str) -> dict:
    cache_key = f"sentiment_snapshot:{ticker}"
    cached = store.get_json(cache_key, default=None)
    if cached is not None:
        return cached

    articles = fetch_news(ticker=ticker, limit=25, lookback_hours=24)

    if not articles:
        snapshot = {
            "ticker": ticker,
            "sentiment_score": 0.0,
            "sentiment_label": "neutral",
            "article_count": 0,
            "recent_60m_count": 0,
            "recent_6h_count": 0,
            "mention_spike": False,
            "catalyst_flags": [],
            "top_catalyst": None,
            "bullish_articles": 0,
            "bearish_articles": 0,
            "recent_headlines": [],
        }
        store.set_json(cache_key, snapshot, ttl=90)
        return snapshot

    weighted_scores = []
    bullish_articles = 0
    bearish_articles = 0
    catalyst_counts = {}

    for article in articles:
        headline = article.get("headline", "") or ""
        summary = article.get("summary", "") or ""
        created_at = article.get("created_at")
        text = f"{headline}. {summary}".strip()

        base_score = score_text_sentiment(text)
        weight = recency_weight(created_at)
        weighted_score = base_score * weight
        weighted_scores.append(weighted_score)

        if weighted_score >= 0.6:
            bullish_articles += 1
        elif weighted_score <= -0.6:
            bearish_articles += 1

        for catalyst in detect_catalysts(text):
            catalyst_counts[catalyst] = catalyst_counts.get(catalyst, 0) + 1

    recent_60m_count, recent_6h_count = article_count_windows(articles)

    avg_score = sum(weighted_scores) / len(weighted_scores) if weighted_scores else 0.0
    sentiment_score = clamp(avg_score / 2.5)

    mention_spike = recent_60m_count >= 3 or (
        recent_60m_count >= 2 and recent_6h_count >= 4
    )

    sorted_catalysts = sorted(
        catalyst_counts.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    catalyst_flags = [name for name, _ in sorted_catalysts]
    top_catalyst = catalyst_flags[0] if catalyst_flags else None

    snapshot = {
        "ticker": ticker,
        "sentiment_score": round(sentiment_score, 4),
        "sentiment_label": classify_sentiment(sentiment_score),
        "article_count": len(articles),
        "recent_60m_count": recent_60m_count,
        "recent_6h_count": recent_6h_count,
        "mention_spike": mention_spike,
        "catalyst_flags": catalyst_flags,
        "top_catalyst": top_catalyst,
        "bullish_articles": bullish_articles,
        "bearish_articles": bearish_articles,
        "recent_headlines": summarize_articles(articles, max_items=5),
    }

    store.set_json(cache_key, snapshot, ttl=90)
    return snapshot


def get_sentiment_score(ticker: str) -> float:
    snapshot = get_sentiment_snapshot(ticker)
    return float(snapshot.get("sentiment_score", 0.0))
