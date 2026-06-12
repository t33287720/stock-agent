"""
個股相關新聞搜尋。
使用 DuckDuckGo News（ddgs 套件），免 API key、免額外服務。
結果以 JSON 檔快取於 cache/，TTL 較短（30 分鐘）以保持新聞時效性。
"""
import json
import time

from ddgs import DDGS

from backend.data.fetcher import CACHE_DIR

NEWS_CACHE_TTL = 1800  # 30 分鐘


def _news_cache_path(ticker: str):
    return CACHE_DIR / f"news_{ticker}.json"


def _read_news_cache(ticker: str):
    path = _news_cache_path(ticker)
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > NEWS_CACHE_TTL:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        path.unlink(missing_ok=True)
        return None


def _write_news_cache(ticker: str, data) -> None:
    with open(_news_cache_path(ticker), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def get_stock_news(ticker: str, name: str, limit: int = 8) -> list[dict]:
    """搜尋個股相關新聞，回傳 [{title, url, source, date, body}, ...]。"""
    cached = _read_news_cache(ticker)
    if cached is not None:
        return cached

    query = f"{name} {ticker} 股票"
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.news(query, region="tw-tzh", safesearch="off", max_results=limit):
                results.append({
                    "title":  r.get("title"),
                    "url":    r.get("url"),
                    "source": r.get("source"),
                    "date":   r.get("date"),
                    "body":   r.get("body"),
                })
    except Exception as e:
        print(f"[news] {ticker} 搜尋失敗: {e}")
        return []

    _write_news_cache(ticker, results)
    return results
