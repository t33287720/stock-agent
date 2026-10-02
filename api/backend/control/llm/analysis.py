"""
個股 AI 分析：技術指標 + 基本面 + 新聞 → 本機 LLM。
採兩階段流程（生成 → 二次驗證）以降低幻覺風險，結果快取於 cache/（TTL 1 小時）。
"""
import json

from backend import cache
from backend.control.llm.react import llm_step, search_rounds

AI_CACHE_TTL = 3600  # 1 小時
MAX_SEARCH_ROUNDS = 10  # 個股 AI 分析最多再延伸搜尋幾輪
ANALYSIS_NUM_CTX = 16384  # 延伸搜尋會讓 context 變長，需要比預設更大的視窗

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
    "search_query 請使用繁體中文公司名稱或中文關鍵字（這是台股新聞搜尋，"
    "用英文公司名稱或股票代號搜尋效果不佳，例如應該搜尋「台積電」而不是「TSMC」）。"
    "關鍵字盡量簡短、聚焦單一主題（例如「台積電 法說會」），"
    "避免堆疊過多修飾詞或同時塞入多個主題，否則容易查無結果。"
    "不要有任何說明文字或 markdown。"
)


def get_cached_analysis(ticker: str) -> dict | None:
    return cache.read_json(f"ai_{ticker}", AI_CACHE_TTL)


def save_analysis_cache(ticker: str, data: dict) -> None:
    cache.write_json(f"ai_{ticker}", data)


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


def _search_decision_prompt(context_block: str, round_no: int, total: int,
                             failed_queries: list[str] | None = None) -> str:
    warning = ""
    if failed_queries:
        failed_list = "、".join(f"「{q}」" for q in failed_queries)
        warning = (
            f"\n\n⚠️ 注意：以下關鍵字搜尋皆「查無結果」：{failed_list}。"
            "如果要繼續搜尋，請務必換成完全不同方向、更簡短、更通俗的中文關鍵字"
            "（例如只用公司簡稱或單一主題詞），不要再用上述關鍵字或高度相似的詞彙。"
        )
    return (
        f"{context_block}{warning}\n\n"
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


# ── 個股 AI 分析 ───────────────────────────────────────────────────────────────────

def build_stock_context(ticker: str, name: str, technical: dict, fundamental: dict, news: list[dict]) -> str:
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
    trace: list[dict] = []
    context, extra_searches = yield from search_rounds(
        trace, build_stock_context(ticker, name, technical, fundamental, news),
        max_rounds=MAX_SEARCH_ROUNDS, num_ctx=ANALYSIS_NUM_CTX,
        decision_label="延伸搜尋判斷", decision_system=_SEARCH_DECISION_SYSTEM_PROMPT,
        decision_prompt=lambda ctx, round_no, failed: _search_decision_prompt(ctx, round_no, MAX_SEARCH_ROUNDS, failed),
        block_title="延伸搜尋",
    )

    raw = yield from llm_step(trace, "主分析", _main_analysis_prompt(context), _SYSTEM_PROMPT,
                              num_predict=800, num_ctx=ANALYSIS_NUM_CTX)
    if raw is None:
        yield {"type": "result", "result": _fallback_result("本機 LLM 無回應或逾時，請稍後再試", extra_searches, trace)}
        return

    verified = yield from llm_step(trace, "二次驗證", _verify_prompt(context, raw), _VERIFY_SYSTEM_PROMPT,
                                   temperature=0.1, num_predict=700, num_ctx=ANALYSIS_NUM_CTX)
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
