"""
Ollama 傳輸層 — 純粹負責呼叫本機 Ollama API 並解析 JSON 回應，不含任何股票領域知識。
"""
import json
import os
import re

import requests

from backend.config import load_config

DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
DEFAULT_MODEL = "qwen2.5:7b"
REQUEST_TIMEOUT = 90


def _resolve_url() -> str:
    settings = load_config().get("settings", {})
    return settings.get("ollama_url") or DEFAULT_OLLAMA_URL


def _resolve_model() -> str:
    settings = load_config().get("settings", {})
    return settings.get("llm_model") or DEFAULT_MODEL


def _parse_json_relaxed(text: str) -> dict | None:
    """盡量從 LLM 回應中解析出 JSON，容忍 code fence、前後雜訊、trailing comma。"""
    if not text:
        return None

    text = text.strip()

    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 去除 ```json ... ``` code fence
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            text = fence.group(1)

    # 3. 抓第一個 { 到最後一個 } 之間的內容
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # 4. 移除 trailing comma 後再試一次
            cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return None

    return None


def generate_json(prompt: str, system: str | None = None, model: str | None = None,
                   temperature: float = 0.2, num_predict: int = 700,
                   num_ctx: int | None = None) -> dict | None:
    """呼叫 Ollama /api/generate（JSON mode），回傳解析後的 dict，失敗回傳 None。"""
    url = f"{_resolve_url()}/api/generate"
    options = {
        "temperature": temperature,
        "top_p": 0.9,
        "num_predict": num_predict,
    }
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    body = {
        "model": model or _resolve_model(),
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": options,
    }
    if system:
        body["system"] = system

    try:
        resp = requests.post(url, json=body, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return _parse_json_relaxed(resp.json().get("response", ""))
    except Exception as e:
        print(f"[ollama_client] generate_json 失敗: {e}")
        return None


def check_ollama_available() -> bool:
    """快速檢查 Ollama 服務是否可連線（供診斷用）。"""
    try:
        resp = requests.get(f"{_resolve_url()}/api/tags", timeout=5)
        return resp.ok
    except Exception:
        return False
