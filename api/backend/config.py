import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"

DEFAULT_CONFIG = {
    "api_keys": {
        "anthropic": "",
        "openai": "",
        "gemini": ""
    },
    "settings": {
        "max_stocks": 100,
        "backtest_days": 365,
        "cache_hours": 6,
        "llm_provider": "gemini",
        "llm_model": "gemini-2.0-flash"
    },
    "strategy": {
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "stop_loss_pct": 7,
        "take_profit_pct": 15,
        "ma_short": 20,
        "ma_long": 60,
        "initial_capital": 1000000,
        "max_per_trade": 0
    }
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    for key, val in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = val
        elif isinstance(val, dict):
            for k, v in val.items():
                if k not in config[key]:
                    config[key][k] = v

    return config


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_api_key(provider: str) -> str:
    return load_config().get("api_keys", {}).get(provider, "")


def get_setting(key: str):
    return load_config().get("settings", {}).get(key)


def get_strategy(key: str):
    return load_config().get("strategy", {}).get(key)
