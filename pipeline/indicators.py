"""從歷史股價算出每支股票「最新一天」的技術指標。

輸入：全市場歷史股價（每列 = 某支股票某一天）
輸出：每支股票一列，欄位就是 App 可以拿來篩選、排序的數值。
"""
import numpy as np
import pandas as pd


def _kd(high: pd.Series, low: pd.Series, close: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """台股慣用 KD：9 日 RSV，K = 2/3 前K + 1/3 RSV，D = 2/3 前D + 1/3 K，起始值 50。"""
    low9 = low.rolling(9, min_periods=1).min()
    high9 = high.rolling(9, min_periods=1).max()
    rsv = ((close - low9) / (high9 - low9 + 1e-9) * 100).clip(0, 100).to_numpy()
    k, d = np.empty(len(rsv)), np.empty(len(rsv))
    prev_k = prev_d = 50.0
    for i, r in enumerate(rsv):
        prev_k = prev_k * 2 / 3 + r / 3
        prev_d = prev_d * 2 / 3 + prev_k / 3
        k[i], d[i] = prev_k, prev_d
    return k, d


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def _one_stock(s: pd.DataFrame) -> dict:
    close, high, low, vol = s["close"], s["high"], s["low"], s["volume"]
    n = len(s)

    def ma(window):
        return close.iloc[-window:].mean() if n >= window else None

    def ret(days):
        return (close.iloc[-1] / close.iloc[-1 - days] - 1) * 100 if n > days else None

    k, d = _kd(high, low, close)
    dif = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    dea = dif.ewm(span=9, adjust=False).mean()
    rsi = _rsi(close)
    last = close.iloc[-1]
    ma5, ma20, ma60 = ma(5), ma(20), ma(60)
    prev_vol5 = vol.iloc[-6:-1].mean() if n >= 6 else None

    return {
        "change_pct":   ret(1),
        "ret_5d":       ret(5),
        "ret_20d":      ret(20),
        "lots":         vol.iloc[-1] / 1000,
        "avg_lots_20":  vol.iloc[-20:].mean() / 1000 if n >= 20 else None,
        "vol_ratio":    vol.iloc[-1] / prev_vol5 if prev_vol5 else None,
        "ma5":          ma5,
        "ma20":         ma20,
        "ma60":         ma60,
        "above_ma20":   bool(last > ma20) if ma20 else None,
        "above_ma60":   bool(last > ma60) if ma60 else None,
        "rsi":          rsi.iloc[-1] if n >= 15 else None,
        "k":            k[-1] if n >= 9 else None,
        "d":            d[-1] if n >= 9 else None,
        "kd_cross":     bool(k[-1] > d[-1] and k[-2] <= d[-2]) if n >= 10 else None,
        "macd_hist":    (dif - dea).iloc[-1] if n >= 35 else None,
        "macd_cross":   bool(dif.iloc[-1] > dea.iloc[-1] and dif.iloc[-2] <= dea.iloc[-2]) if n >= 35 else None,
        "from_high_60": (last / high.iloc[-60:].max() - 1) * 100 if n >= 60 else None,
    }


def latest_indicators(history: pd.DataFrame) -> pd.DataFrame:
    """回傳每支「最新交易日有成交」的股票一列：代號、名稱、市場、收盤價 + 各項指標。"""
    latest_day = history["date"].max()
    history = history.sort_values(["code", "date"])
    rows = []
    for code, s in history.groupby("code", sort=False):
        if s["date"].iloc[-1] != latest_day:
            continue  # 今天沒成交（停牌等）就不列入
        last = s.iloc[-1]
        rows.append({"code": code, "name": last["name"], "market": last["market"],
                     "close": last["close"], **_one_stock(s)})
    return pd.DataFrame(rows)
