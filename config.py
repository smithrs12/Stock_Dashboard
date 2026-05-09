import os
from dotenv import load_dotenv

load_dotenv()


def get_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"true", "1", "yes", "y"}


def get_float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def get_int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


class Config:
    ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
    ALPACA_PAPER = get_bool("ALPACA_PAPER", "true")
    ALPACA_DATA_FEED = os.getenv("ALPACA_DATA_FEED", "iex")

    UPSTASH_REDIS_URL = os.getenv("UPSTASH_REDIS_URL", "")

    SIGNAL_LOOP_SECONDS = get_int("SIGNAL_LOOP_SECONDS", "45")
    SIGNAL_MIN_CONFIDENCE = get_float("SIGNAL_MIN_CONFIDENCE", "0.65")
    HIGH_QUALITY_SIGNAL_CONFIDENCE = get_float("HIGH_QUALITY_SIGNAL_CONFIDENCE", "0.75")

    MIN_PRICE = get_float("MIN_PRICE", "2")
    MAX_PRICE = get_float("MAX_PRICE", "750")
    MIN_VOLUME_RATIO = get_float("MIN_VOLUME_RATIO", "1.3")
    MIN_RISK_REWARD = get_float("MIN_RISK_REWARD", "1.5")
    MAX_SPREAD_PCT = get_float("MAX_SPREAD_PCT", "0.005")

    WATCHLIST_LIMIT = get_int("WATCHLIST_LIMIT", "30")

    ENABLE_SHORT_SIGNALS = get_bool("ENABLE_SHORT_SIGNALS", "true")
    ENABLE_AUDIO_ALERTS = get_bool("ENABLE_AUDIO_ALERTS", "true")
    ENABLE_DISCORD_ALERTS = get_bool("ENABLE_DISCORD_ALERTS", "false")

    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

    WATCHLIST = [
        ticker.strip().upper()
        for ticker in os.getenv(
            "WATCHLIST",
            "AAPL,NVDA,TSLA,AMD,MSFT,META,AMZN,GOOGL,SPY,QQQ"
        ).split(",")
        if ticker.strip()
    ]


config = Config()
