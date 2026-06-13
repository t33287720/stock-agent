"""
個股相關新聞搜尋。
透過自架的 SearXNG（docker-compose 中的 searxng 服務）查詢新聞，免 API key。
結果以 JSON 檔快取於 cache/，TTL 較短（30 分鐘）以保持新聞時效性。
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from backend.data.fetcher import CACHE_DIR

NEWS_CACHE_TTL = 1800  # 30 分鐘
NEWS_MAX_AGE_DAYS = 1  # 只保留 24 小時內的新聞
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://searxng:8080")


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(date_str)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except ValueError:
        return None


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

    query = f"{name} {ticker} 股票 新聞"
    results = []
    try:
        resp = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "categories": "general",
                "language": "zh-TW",
                "time_range": "day",
            },
            timeout=10,
        )
        resp.raise_for_status()
        for r in resp.json().get("results", []):
            results.append({
                "title":  r.get("title"),
                "url":    r.get("url"),
                "source": r.get("engine"),
                "date":   r.get("publishedDate"),
                "body":   r.get("content"),
            })
    except Exception as e:
        print(f"[news] {ticker} 搜尋失敗: {e}")
        return []

    # 過濾掉過舊的新聞，並依日期新到舊排序（無日期者排到最後）
    now = datetime.now(timezone.utc)
    results = [
        r for r in results
        if (d := _parse_date(r["date"])) is None or now - d <= timedelta(days=NEWS_MAX_AGE_DAYS)
    ]
    results.sort(key=lambda r: _parse_date(r["date"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    results = results[:limit]

    _write_news_cache(ticker, results)
    return results
