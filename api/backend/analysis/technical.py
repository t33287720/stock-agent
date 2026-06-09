"""
Technical indicator calculation using the `ta` library.
Falls back to manual pandas calculations if ta is unavailable.
"""
import numpy as np
import pandas as pd

try:
    import ta as ta_lib
    HAS_TA = True
except ImportError:
    HAS_TA = False


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Input:  OHLCV DataFrame (columns: Open, High, Low, Close, Volume)
    Output: same DataFrame enriched with indicator columns
    """
    if df.empty or len(df) < 20:
        return df

    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    if HAS_TA:
        # Trend
        df["SMA_20"] = ta_lib.trend.sma_indicator(close, window=20)
        df["SMA_60"] = ta_lib.trend.sma_indicator(close, window=60)
        df["EMA_12"] = ta_lib.trend.ema_indicator(close, window=12)
        df["EMA_26"] = ta_lib.trend.ema_indicator(close, window=26)

        # MACD
        macd = ta_lib.trend.MACD(close)
        df["MACD"] = macd.macd()
        df["MACD_signal"] = macd.macd_signal()
        df["MACD_hist"] = macd.macd_diff()

        # Momentum
        df["RSI"] = ta_lib.momentum.rsi(close, window=14)
        stoch = ta_lib.momentum.StochasticOscillator(high, low, close)
        df["K"] = stoch.stoch()
        df["D"] = stoch.stoch_signal()

        # Volatility / Bollinger Bands
        bb = ta_lib.volatility.BollingerBands(close, window=20, window_dev=2)
        df["BB_upper"] = bb.bollinger_hband()
        df["BB_mid"] = bb.bollinger_mavg()
        df["BB_lower"] = bb.bollinger_lband()
        df["ATR"] = ta_lib.volatility.average_true_range(high, low, close, window=14)
    else:
        # Manual fallback
        df["SMA_20"] = close.rolling(20).mean()
        df["SMA_60"] = close.rolling(60).mean()
        df["EMA_12"] = close.ewm(span=12, adjust=False).mean()
        df["EMA_26"] = close.ewm(span=26, adjust=False).mean()

        ema12 = df["EMA_12"]
        ema26 = df["EMA_26"]
        df["MACD"] = ema12 - ema26
        df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
        df["MACD_hist"] = df["MACD"] - df["MACD_signal"]

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        df["RSI"] = 100 - 100 / (1 + gain / (loss + 1e-9))

        lo14 = low.rolling(14).min()
        hi14 = high.rolling(14).max()
        df["K"] = 100 * (close - lo14) / (hi14 - lo14 + 1e-9)
        df["D"] = df["K"].rolling(3).mean()

        sma20 = df["SMA_20"]
        std20 = close.rolling(20).std()
        df["BB_upper"] = sma20 + 2 * std20
        df["BB_mid"] = sma20
        df["BB_lower"] = sma20 - 2 * std20

        df["ATR"] = (high - low).rolling(14).mean()

    # Derived: golden/death cross
    df["golden_cross"] = (df["SMA_20"] > df["SMA_60"]).astype(int)

    return df


def get_indicator_summary(df: pd.DataFrame) -> dict:
    """Return latest indicator values as a plain dict."""
    if df.empty:
        return {}
    row = df.iloc[-1]

    def val(col):
        v = row.get(col)
        if v is None:
            return None
        try:
            f = float(v)
            return None if np.isnan(f) else round(f, 4)
        except (TypeError, ValueError):
            return None

    return {
        "close": val("Close"),
        "sma20": val("SMA_20"),
        "sma60": val("SMA_60"),
        "ema12": val("EMA_12"),
        "ema26": val("EMA_26"),
        "rsi": val("RSI"),
        "macd": val("MACD"),
        "macd_signal": val("MACD_signal"),
        "macd_hist": val("MACD_hist"),
        "k": val("K"),
        "d": val("D"),
        "bb_upper": val("BB_upper"),
        "bb_mid": val("BB_mid"),
        "bb_lower": val("BB_lower"),
        "atr": val("ATR"),
        "golden_cross": bool(row.get("golden_cross", 0)),
    }
