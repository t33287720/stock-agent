"""
個股 AI 分析：技術指標 + 基本面 + 新聞 → 本機 LLM。
採兩階段流程（生成 → 二次驗證）以降低幻覺風險，結果快取於 cache/（TTL 1 小時）。
"""
import json
import time
from pathlib import Path

from backend.data.fetcher import CACHE_DIR
from backend.data.news import search_news
from backend.llm.ollama_client import generate_json

AI_CACHE_TTL = 3600  # 1 小時
MAX_SEARCH_ROUNDS = 3  # 個股 AI 分析最多再延伸搜尋幾輪

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

_SEARCH_DECISION_SYSTEM_PROMPT = (
    "你是台股分析助手，正在準備分析資料。請判斷目前資料是否足夠做出可靠判斷；"
    "如果不夠，可以提出一個搜尋關鍵字取得更多資訊（不限財經類，也可以用來查證"
    "已取得消息是否屬實）。只能輸出 JSON：\n"
    '{"need_search": true 或 false, "search_query": "..."}\n'
    "如果資料已經足夠，need_search 設為 false，search_query 可留空字串。"
    "不要有任何說明文字或 markdown。"
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


# ── 共用：prompt 組裝 ──────────────────────────────────────────────────────────────

def _verify_prompt(context_block: str, first_result: dict) -> str:
    return (
        f"{context_block}\n\n"
        "以下是分析師根據上述資料產出的結論（JSON）：\n"
        f"{json.dumps(first_result, ensure_ascii=False)}\n\n"
        "請核對這份結論中的每一項陳述是否有上述資料支持，"
        "移除查無依據的內容並調整信心分數，"
        "輸出修正後、格式完全相同的 JSON。"
    )


def _verify_and_refine(context_block: str, first_result: dict) -> tuple[str, dict | None]:
    prompt = _verify_prompt(context_block, first_result)
    return prompt, generate_json(prompt, system=_VERIFY_SYSTEM_PROMPT, temperature=0.1, num_predict=700)


def _search_decision_prompt(context_block: str, round_no: int, total: int) -> str:
    return (
        f"{context_block}\n\n"
        f"（目前是第 {round_no}/{total} 輪資料蒐集）\n"
        "請判斷是否需要再搜尋更多資訊，並輸出 JSON。"
    )


def _main_analysis_prompt(context_block: str) -> str:
    return (
        f"{context_block}\n\n"
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


def _trace_step(label: str, response, system: str | None = None, prompt: str | None = None) -> dict:
    """記錄一個流程步驟（送給 LLM 的 prompt / SearXNG 查詢 + 收到的回應），供前端顯示完整流程。"""
    return {"label": label, "system": system, "prompt": prompt, "response": response}


def _format_extra_search_block(round_no: int, query: str, results: list[dict]) -> str:
    if not results:
        return f"延伸搜尋第 {round_no} 輪（關鍵字：{query}）：（查無結果）"
    lines = [f"延伸搜尋第 {round_no} 輪（關鍵字：{query}）："]
    for r in results:
        title = r.get("title") or ""
        body = (r.get("body") or "")[:100]
        lines.append(f"- {title}：{body}")
    return "\n".join(lines)


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


def analyze_stock_stream(ticker: str, name: str, technical: dict, fundamental: dict, news: list[dict]):
    """逐步執行個股 AI 分析（generator），供前端即時顯示整個流程。

    依序 yield：
    - {"type": "step_start", "step": {label, system, prompt}}：即將呼叫 LLM / SearXNG
    - {"type": "step_done",  "step": {label, system, prompt, response}}：該步驟完成
    最後 yield {"type": "result", "result": {...}}（與舊版 analyze_stock 回傳格式相同）。
    """
    context = _build_stock_context(ticker, name, technical, fundamental, news)
    trace = []
    extra_searches = []

    for round_no in range(1, MAX_SEARCH_ROUNDS + 1):
        label = f"延伸搜尋判斷（第 {round_no}/{MAX_SEARCH_ROUNDS} 輪）"
        prompt = _search_decision_prompt(context, round_no, MAX_SEARCH_ROUNDS)
        yield {"type": "step_start", "step": {"label": label, "system": _SEARCH_DECISION_SYSTEM_PROMPT, "prompt": prompt}}
        decision = generate_json(prompt, system=_SEARCH_DECISION_SYSTEM_PROMPT, temperature=0.2, num_predict=150)
        step = _trace_step(label, decision, system=_SEARCH_DECISION_SYSTEM_PROMPT, prompt=prompt)
        trace.append(step)
        yield {"type": "step_done", "step": step}

        if not isinstance(decision, dict) or not decision.get("need_search"):
            break
        query = str(decision.get("search_query") or "").strip()[:100]
        if not query:
            break

        search_label = f"SearXNG 搜尋（第 {round_no} 輪）：「{query}」"
        yield {"type": "step_start", "step": {"label": search_label, "system": None, "prompt": None}}
        results = search_news(query, limit=5)
        step = _trace_step(search_label, {"query": query, "results": results})
        trace.append(step)
        yield {"type": "step_done", "step": step}

        context += "\n\n" + _format_extra_search_block(round_no, query, results)
        extra_searches.append({"round": round_no, "query": query, "results": results})

    prompt = _main_analysis_prompt(context)
    yield {"type": "step_start", "step": {"label": "主分析", "system": _SYSTEM_PROMPT, "prompt": prompt}}
    raw = generate_json(prompt, system=_SYSTEM_PROMPT, num_predict=800)
    step = _trace_step("主分析", raw, system=_SYSTEM_PROMPT, prompt=prompt)
    trace.append(step)
    yield {"type": "step_done", "step": step}

    if raw is None:
        yield {"type": "result", "result": _fallback_result("本機 LLM 無回應或逾時，請稍後再試", extra_searches, trace)}
        return

    verify_prompt = _verify_prompt(context, raw)
    yield {"type": "step_start", "step": {"label": "二次驗證", "system": _VERIFY_SYSTEM_PROMPT, "prompt": verify_prompt}}
    verified = generate_json(verify_prompt, system=_VERIFY_SYSTEM_PROMPT, temperature=0.1, num_predict=700)
    step = _trace_step("二次驗證", verified, system=_VERIFY_SYSTEM_PROMPT, prompt=verify_prompt)
    trace.append(step)
    yield {"type": "step_done", "step": step}

    if verified is not None:
        result = _normalize_result(verified, verified_flag=True, extra_searches=extra_searches, trace=trace)
    else:
        result = _normalize_result(raw, verified_flag=False, extra_searches=extra_searches, trace=trace)
    yield {"type": "result", "result": result}


def _normalize_result(raw: dict, verified_flag: bool, extra_searches: list[dict] | None = None,
                       trace: list[dict] | None = None) -> dict:
    extra_searches = extra_searches or []
    trace = trace or []

    if not isinstance(raw, dict):
        return _fallback_result("AI 回應格式錯誤", extra_searches, trace)

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
        return _fallback_result("AI 回應缺少必要欄位", extra_searches, trace)

    return {
        "verdict": verdict,
        "confidence": confidence,
        "key_reasons": key_reasons,
        "risks": risks,
        "summary": summary,
        "verified": verified_flag,
        "extra_searches": extra_searches,
        "trace": trace,
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


def _fallback_result(reason: str, extra_searches: list[dict] | None = None, trace: list[dict] | None = None) -> dict:
    return {
        "verdict": "中性",
        "confidence": 0,
        "key_reasons": [],
        "risks": [reason],
        "summary": reason,
        "verified": False,
        "error": True,
        "extra_searches": extra_searches or [],
        "trace": trace or [],
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

    _, verified = _verify_and_refine(context, raw)
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
