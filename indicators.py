import numpy as np
import pandas as pd

from market_data import get_intraday_bars


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    return (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_macd(series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_12 = series.ewm(span=12, adjust=False).mean()
    ema_26 = series.ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return macd, signal, histogram


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr_1 = high - low
    tr_2 = (high - close.shift()).abs()
    tr_3 = (low - close.shift()).abs()
    true_range = pd.concat([tr_1, tr_2, tr_3], axis=1).max(axis=1)

    atr = true_range.rolling(period).mean()

    plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, np.nan))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(period).mean()


def calculate_bollinger_position(series: pd.Series, period: int = 20) -> pd.Series:
    middle = series.rolling(period).mean()
    std = series.rolling(period).std()

    upper = middle + (2 * std)
    lower = middle - (2 * std)

    return (series - lower) / (upper - lower).replace(0, np.nan)


def get_support_resistance(df: pd.DataFrame, lookback: int = 30) -> tuple:
    recent = df.tail(lookback)
    return float(recent["low"].min()), float(recent["high"].max())


def classify_vwap_state(price: float, vwap: float, previous_price: float, previous_vwap: float) -> str:
    was_below = previous_price < previous_vwap
    was_above = previous_price > previous_vwap
    now_above = price > vwap
    now_below = price < vwap

    if was_below and now_above:
        return "reclaim"
    if was_above and now_below:
        return "breakdown"
    if now_above:
        return "above"
    if now_below:
        return "below"

    return "neutral"


def get_indicator_snapshot(ticker: str) -> dict:
    df = get_intraday_bars(ticker, minutes=240)

    if df.empty or len(df) < 60:
        return {}

    df = df.copy()

    df["vwap"] = calculate_vwap(df)
    df["rsi"] = calculate_rsi(df["close"])
    df["macd"], df["macd_signal"], df["macd_histogram"] = calculate_macd(df["close"])
    df["adx"] = calculate_adx(df)
    df["bollinger_position"] = calculate_bollinger_position(df["close"])

    high_low = df["high"] - df["low"]
    df["atr"] = high_low.rolling(14).mean()

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    previous_5 = df.iloc[-5]
    previous_15 = df.iloc[-15]
    previous_30 = df.iloc[-30]

    price = float(latest["close"])
    vwap = float(latest["vwap"])

    rolling_volume_20 = df["volume"].rolling(20).mean().iloc[-1]
    rolling_volume_60 = df["volume"].rolling(60).mean().iloc[-1]

    volume_ratio_20 = float(latest["volume"] / rolling_volume_20) if rolling_volume_20 else 0.0
    volume_ratio_60 = float(latest["volume"] / rolling_volume_60) if rolling_volume_60 else 0.0

    momentum_5m = (price - float(previous_5["close"])) / float(previous_5["close"])
    momentum_15m = (price - float(previous_15["close"])) / float(previous_15["close"])
    momentum_30m = (price - float(previous_30["close"])) / float(previous_30["close"])

    prior_momentum_15m = (
        float(previous_15["close"]) - float(previous_30["close"])
    ) / float(previous_30["close"])

    momentum_acceleration = momentum_15m - prior_momentum_15m

    support, resistance = get_support_resistance(df)

    distance_to_resistance = (resistance - price) / price if price else 0.0
    distance_to_support = (price - support) / price if price else 0.0

    vwap_state = classify_vwap_state(
        price=price,
        vwap=vwap,
        previous_price=float(previous["close"]),
        previous_vwap=float(previous["vwap"]),
    )

    macd_histogram = float(latest["macd_histogram"]) if not pd.isna(latest["macd_histogram"]) else 0.0
    previous_macd_histogram = float(previous["macd_histogram"]) if not pd.isna(previous["macd_histogram"]) else 0.0

    signal_decay = (
        momentum_acceleration < 0
        and volume_ratio_20 < 1.0
        and macd_histogram < previous_macd_histogram
    )

    return {
        "ticker": ticker,
        "price": price,
        "vwap": vwap,
        "above_vwap": price > vwap,
        "vwap_distance": (price - vwap) / vwap if vwap else 0.0,
        "vwap_state": vwap_state,

        "volume": float(latest["volume"]),
        "volume_ratio": volume_ratio_20,
        "volume_ratio_60": volume_ratio_60,

        "momentum_5m": float(momentum_5m),
        "momentum_15m": float(momentum_15m),
        "momentum_30m": float(momentum_30m),
        "momentum_acceleration": float(momentum_acceleration),

        "rsi": float(latest["rsi"]) if not pd.isna(latest["rsi"]) else 50.0,
        "macd": float(latest["macd"]) if not pd.isna(latest["macd"]) else 0.0,
        "macd_signal": float(latest["macd_signal"]) if not pd.isna(latest["macd_signal"]) else 0.0,
        "macd_histogram": macd_histogram,
        "macd_histogram_rising": macd_histogram > previous_macd_histogram,

        "adx": float(latest["adx"]) if not pd.isna(latest["adx"]) else 0.0,
        "bollinger_position": float(latest["bollinger_position"]) if not pd.isna(latest["bollinger_position"]) else 0.5,

        "atr": float(latest["atr"]) if not pd.isna(latest["atr"]) else 0.0,
        "support": support,
        "resistance": resistance,
        "distance_to_support": float(distance_to_support),
        "distance_to_resistance": float(distance_to_resistance),

        "day_high": float(df["high"].max()),
        "day_low": float(df["low"].min()),

        "signal_decay": bool(signal_decay),
    }
