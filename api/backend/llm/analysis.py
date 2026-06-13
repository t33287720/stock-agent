"""
個股 AI 分析：技術指標 + 基本面 + 新聞 → 本機 LLM。
採兩階段流程（生成 → 二次驗證）以降低幻覺風險，結果快取於 cache/（TTL 1 小時）。
"""
import json
import time
from pathlib import Path

from backend.data.fetcher import CACHE_DIR
from backend.llm.ollama_client import generate_json

AI_CACHE_TTL = 3600  # 1 小時

VERDICTS = ("偏多", "中性", "偏空")

_SYSTEM_PROMPT = (
    "你是台股分析助手。請只根據使用者提供的資料進行分析，"
    "不要假設你擁有即時市場資訊或資料以外的知識。"
    "只能輸出 JSON，不要有任何說明文字或 markdown。"
    "這份分析僅供參考，不構成投資建議。"
)

_VERIFY_SYSTEM_PROMPT = (
    "你是嚴謹的事實核對員。你會看到一份原始資料，以及另一位分析師根據該資料產出的 JSON 結論。"
    "請逐項檢查結論中的每一句陳述是否真的有原始資料支持，"
    "移除任何查無依據、憑空捏造或與資料矛盾的陳述，並據此調整信心分數。"
    "只能輸出與原結論格式完全相同的 JSON，不要有任何說明文字或 markdown。"
)


def _ai_cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"ai_{ticker}.json"


def get_cached_analysis(ticker: str) -> dict | None:
    path = _ai_cache_path(ticker)
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > AI_CACHE_TTL:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        path.unlink(missing_ok=True)
        return None


def save_analysis_cache(ticker: str, data: dict) -> None:
    with open(_ai_cache_path(ticker), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# ── 共用：第二次驗證（核對是否有幻覺）──────────────────────────────────────────────

def _verify_and_refine(context_block: str, first_result: dict) -> dict | None:
    prompt = (
        f"{context_block}\n\n"
        "以下是分析師根據上述資料產出的結論（JSON）：\n"
        f"{json.dumps(first_result, ensure_ascii=False)}\n\n"
        "請核對這份結論中的每一項陳述是否有上述資料支持，"
        "移除查無依據的內容並調整信心分數，"
        "輸出修正後、格式完全相同的 JSON。"
    )
    return generate_json(prompt, system=_VERIFY_SYSTEM_PROMPT, temperature=0.1, num_predict=700)


# ── 個股 AI 分析 ───────────────────────────────────────────────────────────────────

def _build_stock_context(ticker: str, name: str, technical: dict, fundamental: dict, news: list[dict]) -> str:
    t = technical or {}
    f = fundamental or {}

    news_lines = []
    for n in (news or [])[:5]:
        title = n.get("title") or ""
        body = (n.get("body") or "")[:100]
        date = n.get("date") or ""
        news_lines.append(f"- [{date}] {title}：{body}")
    news_block = "\n".join(news_lines) if news_lines else "（查無相關新聞）"

    return (
        f"股票：{name}（{ticker}）\n\n"
        "技術指標：\n"
        f"- 收盤價：{t.get('close')}\n"
        f"- RSI(14)：{t.get('rsi')}\n"
        f"- MACD：{t.get('macd')}，訊號線：{t.get('macd_signal')}\n"
        f"- KD：K={t.get('k')}, D={t.get('d')}\n"
        f"- SMA20：{t.get('sma20')}，SMA60：{t.get('sma60')}\n"
        f"- 黃金交叉（SMA20>SMA60）：{t.get('golden_cross')}\n"
        f"- 布林通道：上緣={t.get('bb_upper')}，下緣={t.get('bb_lower')}\n\n"
        "基本面：\n"
        f"- P/E：{f.get('pe')}\n"
        f"- P/B：{f.get('pb')}\n"
        f"- 殖利率：{f.get('div_yield')}%\n"
        f"- EPS：{f.get('eps')}\n"
        f"- ROE：{f.get('roe')}%\n\n"
        "近期相關新聞：\n"
        f"{news_block}"
    )


def analyze_stock(ticker: str, name: str, technical: dict, fundamental: dict, news: list[dict]) -> dict:
    context = _build_stock_context(ticker, name, technical, fundamental, news)
    prompt = (
        f"{context}\n\n"
        "請根據以上資料分析這支股票，輸出以下格式的 JSON：\n"
        "{\n"
        '  "verdict": "偏多 | 中性 | 偏空",\n'
        '  "confidence": 0-100之間的整數,\n'
        '  "key_reasons": ["...", "..."],\n'
        '  "risks": ["...", "..."],\n'
        '  "summary": "150-250字繁體中文總結"\n'
        "}\n"
        "key_reasons 請列出 2-4 點支持你判斷的具體依據，risks 請列出 1-3 點需注意的風險。"
    )

    raw = generate_json(prompt, system=_SYSTEM_PROMPT, num_predict=800)
    if raw is None:
        return _fallback_result("本機 LLM 無回應或逾時，請稍後再試")

    verified = _verify_and_refine(context, raw)
    if verified is not None:
        return _normalize_result(verified, verified_flag=True)

    return _normalize_result(raw, verified_flag=False)


def _normalize_result(raw: dict, verified_flag: bool) -> dict:
    if not isinstance(raw, dict):
        return _fallback_result("AI 回應格式錯誤")

    verdict = _map_verdict(str(raw.get("verdict", "")).strip())

    try:
        confidence = int(round(float(raw.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))

    key_reasons = _to_str_list(raw.get("key_reasons"))[:4]
    risks = _to_str_list(raw.get("risks"))[:3]
    summary = str(raw.get("summary", "")).strip()[:300]

    if not verdict or not summary:
        return _fallback_result("AI 回應缺少必要欄位")

    return {
        "verdict": verdict,
        "confidence": confidence,
        "key_reasons": key_reasons,
        "risks": risks,
        "summary": summary,
        "verified": verified_flag,
    }


def _map_verdict(v: str) -> str:
    if v in VERDICTS:
        return v
    low = v.lower()
    if any(k in low for k in ("看多", "看漲", "正向", "buy", "bullish")):
        return "偏多"
    if any(k in low for k in ("看空", "看跌", "負向", "sell", "bearish")):
        return "偏空"
    if any(k in low for k in ("持平", "中立", "neutral", "hold")):
        return "中性"
    return ""


def _to_str_list(val) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(item).strip()[:150] for item in val if str(item).strip()]


def _fallback_result(reason: str) -> dict:
    return {
        "verdict": "中性",
        "confidence": 0,
        "key_reasons": [],
        "risks": [reason],
        "summary": reason,
        "verified": False,
        "error": True,
    }


# ── 掃描候選股 AI 信心評分 ────────────────────────────────────────────────────────

def _build_scan_context(ticker: str, name: str, signal_reason: str, technical_snapshot: dict, news: list[dict]) -> str:
    t = technical_snapshot or {}
    news_lines = []
    for n in (news or [])[:3]:
        title = n.get("title") or ""
        date = n.get("date") or ""
        news_lines.append(f"- [{date}] {title}")
    news_block = "\n".join(news_lines) if news_lines else "（查無相關新聞）"

    return (
        f"股票：{name}（{ticker}）\n"
        f"觸發訊號：{signal_reason}\n\n"
        "技術指標：\n"
        f"- RSI(14)：{t.get('rsi')}\n"
        f"- MACD 是否多頭：{t.get('macd_bullish')}\n"
        f"- KD：K={t.get('k')}, D={t.get('d')}\n"
        f"- 是否黃金交叉（SMA20>SMA60）：{t.get('golden_cross')}\n\n"
        "近期相關新聞標題：\n"
        f"{news_block}"
    )


def analyze_scan_candidate(ticker: str, name: str, signal_reason: str,
                            technical_snapshot: dict, news: list[dict]) -> dict:
    has_news = bool(news)
    context = _build_scan_context(ticker, name, signal_reason, technical_snapshot, news)
    prompt = (
        f"{context}\n\n"
        "請根據以上資料評估這個訊號的可信程度，輸出以下格式的 JSON：\n"
        "{\n"
        '  "ai_confidence": 0-100之間的整數,\n'
        '  "ai_summary": "30字以內的簡短理由",\n'
        '  "has_news": true 或 false\n'
        "}"
    )

    raw = generate_json(prompt, system=_SYSTEM_PROMPT, num_predict=200)
    if raw is None:
        return {"ai_confidence": None, "ai_summary": "AI 分析失敗", "has_news": has_news, "verified": False}

    verified = _verify_and_refine(context, raw)
    if verified is not None:
        return _normalize_scan_result(verified, has_news, verified_flag=True)

    return _normalize_scan_result(raw, has_news, verified_flag=False)


def _normalize_scan_result(raw: dict, has_news: bool, verified_flag: bool) -> dict:
    if not isinstance(raw, dict):
        return {"ai_confidence": None, "ai_summary": "AI 回應格式錯誤", "has_news": has_news, "verified": False}

    try:
        confidence = int(round(float(raw.get("ai_confidence"))))
        confidence = max(0, min(100, confidence))
    except (TypeError, ValueError):
        confidence = None

    summary = str(raw.get("ai_summary", "")).strip()[:60] or "（無摘要）"

    return {
        "ai_confidence": confidence,
        "ai_summary": summary,
        "has_news": has_news,
        "verified": verified_flag,
    }
