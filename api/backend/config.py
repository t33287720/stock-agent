import copy
import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"

DEFAULT_CONFIG = {
    "settings": {
        "cache_hours": 6,
        "llm_model": "qwen2.5:7b",
        "ollama_url": os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434"),
        "auto_scan_with_ai": True
    },
    "strategy": {
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "stop_loss_pct": 7,
        "take_profit_pct": 15,
        "ma_short": 20,
        "ma_long": 60,
        "initial_capital": 1000000
    }
}


# 讀快取、呼叫 LLM 前都會 load_config()，一輪掃描就會呼叫上百次；
# 以檔案修改時間判斷要不要重讀，檔案沒變就直接回傳記憶體裡的副本。
_cached_mtime: float | None = None
_cached_config: dict | None = None


def load_config() -> dict:
    global _cached_mtime, _cached_config
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    mtime = CONFIG_PATH.stat().st_mtime
    if _cached_config is not None and mtime == _cached_mtime:
        return copy.deepcopy(_cached_config)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    for key, val in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = val
        elif isinstance(val, dict):
            for k, v in val.items():
                if k not in config[key]:
                    config[key][k] = v

    _cached_mtime, _cached_config = mtime, config
    return copy.deepcopy(config)


def save_config(config: dict) -> None:
    global _cached_config
    _cached_config = None  # 不依賴 mtime 精度，存檔後一律重讀
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
