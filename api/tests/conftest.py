"""
共用測試設定：
- 不連外網：requests 一律丟例外，需要外部資料的測試自己 monkeypatch 假資料
- 設定檔、快取都寫到暫存目錄，不碰 api/config、api/cache
- 休市日只用程式內建清單（不打證交所 API）

執行：cd api && python -m pytest
資料庫測試需要 Postgres（DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD），沒設定就略過。
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    import requests

    import backend.cache as cache
    import backend.config as config
    import backend.utils as utils

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config" / "settings.json")
    monkeypatch.setattr(config, "_cached_config", None)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(cache, "CACHE_DIR", cache_dir)

    monkeypatch.setattr(utils, "_HOLIDAY_CACHE", cache_dir / "twse_holidays.json")
    monkeypatch.setattr(utils, "_holidays_by_year", {})
    monkeypatch.setattr(utils, "_holidays_next_refresh", float("inf"))

    # 模組層級的記憶快取每個測試都重來
    from backend.control.data import fetcher, price_store
    monkeypatch.setattr(fetcher, "_valuation_memo", {})
    monkeypatch.setattr(price_store, "_coverage", None)

    def no_network(*args, **kwargs):
        raise RuntimeError("測試不應該連外網，請 monkeypatch 假資料")

    monkeypatch.setattr(requests, "get", no_network)
    monkeypatch.setattr(requests.Session, "request", no_network)


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def fake_http(routes: dict):
    """回傳一個假的 requests.get：網址包含 routes 的 key 就回對應的 JSON。"""
    def get(url, *args, **kwargs):
        for key, data in routes.items():
            if key in url:
                return FakeResponse(data)
        raise RuntimeError(f"沒有對應的假資料：{url}")
    return get


requires_db = pytest.mark.skipif(not os.environ.get("DB_HOST"), reason="需要 Postgres（設定 DB_HOST 等環境變數）")
