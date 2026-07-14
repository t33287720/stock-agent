"""API 區：策略/系統設定（讀寫 api/config/settings.json）。"""
from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import load_config, save_config

router = APIRouter()


class ConfigUpdate(BaseModel):
    settings: dict | None = None
    strategy: dict | None = None


@router.get("/api/config")
async def get_config():
    cfg = load_config()
    return {
        "settings": cfg.get("settings", {}),
        "strategy": cfg.get("strategy", {}),
    }


@router.put("/api/config")
async def update_config(update: ConfigUpdate):
    cfg = load_config()
    if update.settings:
        cfg["settings"].update(update.settings)
    if update.strategy:
        cfg["strategy"].update(update.strategy)
    save_config(cfg)
    return {"status": "ok", "message": "設定已儲存"}
