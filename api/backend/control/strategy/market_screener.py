"""
全市場篩選頁的技術指標計算 — 對「使用者篩選後」的任意股票清單現算 RSI/KD 等指標。

跟 scanner.py（固定對 get_top100_stocks() 的候選池做買賣訊號掃描）不同：
這裡的股票清單由前端使用者自己篩選出來（不限於成交量前 300 大），
所以獨立成檔，不與「今日訊號掃描」的邏輯混在一起。
"""
from concurrent.futures import ThreadPoolExecutor

from backend.control.data.fetcher import get_stock_history
from backend.control.analysis.technical import calculate_indicators, get_indicator_summary

MAX_TICKERS = 150


def compute_technical_for_tickers(tickers: list[str]) -> dict[str, dict]:
    """對傳入的股票代號清單平行抓歷史 K 線並計算技術指標，回傳 {ticker: summary|{"error":...}}。"""

    def _fetch(ticker: str):
        try:
            df = get_stock_history(ticker, 90)
            if df.empty or len(df) < 20:
                return ticker, {"error": "資料不足"}
            df = calculate_indicators(df)
            summary = get_indicator_summary(df)
            summary["macd_bullish"] = bool(summary.get("macd") is not None
                                            and summary.get("macd_signal") is not None
                                            and summary["macd"] > summary["macd_signal"])
            return ticker, summary
        except Exception as e:
            return ticker, {"error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=15) as ex:
        results = list(ex.map(_fetch, tickers))

    return dict(results)
