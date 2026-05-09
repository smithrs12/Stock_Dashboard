import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
    ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
    ALPACA_DATA_FEED = os.getenv("ALPACA_DATA_FEED", "iex")

    UPSTASH_REDIS_URL = os.getenv("UPSTASH_REDIS_URL", "")

    SIGNAL_LOOP_SECONDS = int(os.getenv("SIGNAL_LOOP_SECONDS", "45"))
    SIGNAL_MIN_CONFIDENCE = float(os.getenv("SIGNAL_MIN_CONFIDENCE", "0.65"))
    HIGH_QUALITY_SIGNAL_CONFIDENCE = float(os.getenv("HIGH_QUALITY_SIGNAL_CONFIDENCE", "0.75"))

    WATCHLIST = [
        ticker.strip().upper()
        for ticker in os.getenv(
            "WATCHLIST",
            "AAPL,NVDA,TSLA,AMD,MSFT,META,AMZN,GOOGL,SPY,QQQ"
        ).split(",")
        if ticker.strip()
    ]

    MIN_PRICE = float(os.getenv("MIN_PRICE", "2"))
    MAX_PRICE = float(os.getenv("MAX_PRICE", "750"))
    MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "1.3"))
    MIN_RISK_REWARD = float(os.getenv("MIN_RISK_REWARD", "1.5"))


config = Config()
