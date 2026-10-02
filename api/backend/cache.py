"""
本機 JSON 檔案快取（api/cache/，由 docker-compose 掛載，不進 image）。

股價、基本面、新聞、個股 AI 分析都用同一套：key 對應檔名、以檔案修改時間判斷是否過期。
"""
import json
import time
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


class _DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return super().default(obj)


def _path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def read_json(key: str, ttl_seconds: float) -> Any | None:
    """讀快取；不存在、超過 ttl_seconds 或檔案損毀都回傳 None（損毀的檔案會順便刪掉）。"""
    path = _path(key)
    try:
        if time.time() - path.stat().st_mtime > ttl_seconds:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        path.unlink(missing_ok=True)
        return None


def write_json(key: str, data: Any) -> None:
    with open(_path(key), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, cls=_DateEncoder)


def purge_old(max_age_days: int = 7) -> int:
    """刪除超過 max_age_days 沒更新的快取檔。

    歷史股價、全市場清單等快取的 key 都帶日期（每個交易日換一個新檔），
    舊檔不會再被讀到，不清的話 cache/ 會無限長大。回傳刪掉的檔案數。
    """
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for path in CACHE_DIR.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
