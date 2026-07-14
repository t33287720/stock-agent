"""
「問股票」聊天助手：自由文字問句 → 解析股票 → 抓資料/搜尋 → 回答。

比照 analysis.py 的 ReAct + NDJSON 串流風格（同樣用 generate_json + search_news），
差別在於這裡要先自己判斷使用者問的是哪支股票，且支援多輪對話（帶入先前對話歷史，
可從代名詞如「這支」「殖利率呢」推回前一輪問過的股票）。
"""
from concurrent.futures import ThreadPoolExecutor

from backend.control.analysis.technical import calculate_indicators, get_indicator_summary
from backend.control.data.fetcher import get_stock_history, get_fundamental, search_tickers
from backend.control.data.news import get_stock_news, search_news
from backend.control.llm.analysis import build_stock_context
from backend.control.llm.ollama_client import generate_json

CHAT_MAX_SEARCH_ROUNDS = 4  # 比個股分析的 10 輪少，聊天要即時性
CHAT_NUM_CTX = 12288
MAX_TICKERS = 3

_EXTRACT_SYSTEM_PROMPT = (
    "你是台股聊天助手的問題解析器。請閱讀使用者最新的問題與先前對話，"
    "判斷使用者是否在問特定的股票或公司（可能用簡稱、代號或代名詞如「這支」「剛剛那家」，"
    "此時請從先前對話推回實際公司名稱）。只能輸出 JSON：\n"
    '{"queries": ["公司名稱或股票代號", ...]}\n'
    "如果沒有提到任何股票或公司，queries 請輸出空陣列 []。"
    "queries 請用繁體中文公司簡稱或股票代號，不要加「股份有限公司」等後綴。"
    "不要有任何說明文字或 markdown。"
)

_CHAT_SEARCH_DECISION_SYSTEM_PROMPT = (
    "你是台股聊天助手，正在準備回答使用者的問題。請判斷目前資料是否足夠回答，"
    "如果不夠，可以提出一個搜尋關鍵字取得更多資訊。只能輸出 JSON：\n"
    '{"need_search": true 或 false, "search_query": "..."}\n'
    "如果資料已經足夠，或者這個問題根本不需要查資料就能回答，need_search 設為 false。"
    "search_query 請使用繁體中文關鍵字，盡量簡短、聚焦單一主題。"
    "不要有任何說明文字或 markdown。"
)

_CHAT_SYSTEM_PROMPT = (
    "你是台股聊天助手，個性親切、講重點。使用者可能會問特定股票的近況，也可能問一般閒聊或概念問題。"
    "如果有提供股票的技術指標／基本面／新聞資料，請根據這些資料回答，不要編造資料以外的數字。"
    "如果問題與股票無關，可以依你所知直接回答。"
    "涉及個股判斷或投資相關的內容，請提醒僅供參考、不構成投資建議。"
    '只能輸出 JSON：{"reply": "繁體中文回覆內容"}，不要有任何說明文字或 markdown。'
)

_CHAT_VERIFY_SYSTEM_PROMPT = (
    "你是嚴謹的事實核對員。你會看到一份可用資料，以及另一位助手根據該資料回覆使用者的內容。"
    "請逐句檢查回覆中的具體陳述（數字、日期、事件、股價等）是否真的有可用資料支持，"
    "移除或修正任何查無依據、憑空捏造或與資料矛盾的內容，但保留其餘正確內容與原本語氣。"
    '只能輸出與原格式相同的 JSON：{"reply": "修正後的繁體中文回覆內容"}，不要有任何說明文字或 markdown。'
)


def _trace_step(label: str, response, system: str | None = None, prompt: str | None = None) -> dict:
    return {"label": label, "system": system, "prompt": prompt, "response": response}


def _format_history(history: list[dict]) -> str:
    if not history:
        return "（無先前對話）"
    lines = []
    for turn in history[-10:]:
        role = "使用者" if turn.get("role") == "user" else "助手"
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"{role}：{content}")
    return "\n".join(lines) if lines else "（無先前對話）"


def _format_search_block(round_no: int, query: str, results: list[dict]) -> str:
    if not results:
        return f"搜尋第 {round_no} 輪（關鍵字：{query}）：（查無結果）"
    lines = [f"搜尋第 {round_no} 輪（關鍵字：{query}）："]
    for r in results:
        title = r.get("title") or ""
        body = (r.get("body") or "")[:100]
        lines.append(f"- {title}：{body}")
    return "\n".join(lines)


def _fetch_stock_block(ticker: str, name: str) -> tuple[str, str, str | None, list[dict], str | None]:
    try:
        df = get_stock_history(ticker, 90)
        if df.empty:
            return ticker, name, None, [], "查無歷史資料"
        df = calculate_indicators(df)
        technical = get_indicator_summary(df)
        fund = get_fundamental(ticker)
        news = get_stock_news(ticker, name)
        block = build_stock_context(ticker, name, technical, fund, news)
        return ticker, name, block, news, None
    except Exception as e:
        return ticker, name, None, [], str(e)


def chat_stream(history: list[dict], message: str):
    """逐步處理一次聊天問答（generator）。

    依序 yield：
    - {"type": "step_start", "step": {label, system, prompt}}
    - {"type": "step_done",  "step": {label, system, prompt, response}}
    最後 yield {"type": "result", "result": {reply, used_tickers, trace}}。
    """
    history_block = _format_history(history)
    trace = []

    # ── 1. 理解問題：判斷使用者問的是哪支股票 ──────────────────────────────
    extract_prompt = (
        f"先前對話：\n{history_block}\n\n"
        f"使用者最新問題：{message}\n\n"
        "請判斷這個問題有沒有提到特定股票或公司，輸出 JSON。"
    )
    yield {"type": "step_start", "step": {"label": "理解問題", "system": _EXTRACT_SYSTEM_PROMPT, "prompt": extract_prompt}}
    extracted = generate_json(extract_prompt, system=_EXTRACT_SYSTEM_PROMPT, temperature=0.1, num_predict=200)
    step = _trace_step("理解問題", extracted, system=_EXTRACT_SYSTEM_PROMPT, prompt=extract_prompt)
    trace.append(step)
    yield {"type": "step_done", "step": step}

    queries = []
    if isinstance(extracted, dict):
        queries = [str(q).strip() for q in (extracted.get("queries") or []) if str(q).strip()]

    # ── 2. 代號解析（純程式比對，不呼叫 LLM）─────────────────────────────
    used_tickers: list[dict] = []
    seen_tickers = set()
    for q in queries:
        for cand in search_tickers(q, limit=1):
            if cand["ticker"] not in seen_tickers:
                seen_tickers.add(cand["ticker"])
                used_tickers.append(cand)
        if len(used_tickers) >= MAX_TICKERS:
            break
    used_tickers = used_tickers[:MAX_TICKERS]

    if used_tickers:
        resolved = "、".join(f"{t['name']}（{t['ticker']}）" for t in used_tickers)
        step = _trace_step("解析股票", {"resolved": resolved})
        trace.append(step)
        yield {"type": "step_done", "step": step}
    elif queries:
        step = _trace_step("解析股票", {"resolved": None,
                            "note": f"找不到符合「{'、'.join(queries)}」的股票，將以一般方式回答"})
        trace.append(step)
        yield {"type": "step_done", "step": step}

    # ── 3. 抓股票資料（平行處理，含個股新聞）─────────────────────────────
    stock_blocks = []
    sources: list[dict] = []
    seen_urls = set()
    if used_tickers:
        with ThreadPoolExecutor(max_workers=min(4, len(used_tickers))) as ex:
            for ticker, name, block, news, err in ex.map(lambda t: _fetch_stock_block(t["ticker"], t["name"]), used_tickers):
                label = f"查詢 {name}（{ticker}）資料"
                if block:
                    stock_blocks.append(block)
                    step = _trace_step(label, {"summary": f"已取得技術面與基本面資料，相關新聞 {len(news)} 則"})
                    for r in news:
                        url = r.get("url")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            sources.append(r)
                else:
                    step = _trace_step(label, {"error": err})
                trace.append(step)
                yield {"type": "step_done", "step": step}

    context = "\n\n".join(stock_blocks) if stock_blocks else "（本次問題未鎖定特定股票，無股票資料）"

    # ── 4. 延伸搜尋迴圈 ────────────────────────────────────────────────────
    query_counts: dict[str, int] = {}
    failed_queries: list[str] = []

    for round_no in range(1, CHAT_MAX_SEARCH_ROUNDS + 1):
        label = f"搜尋判斷（第 {round_no}/{CHAT_MAX_SEARCH_ROUNDS} 輪）"
        decision_prompt = (
            f"對話：\n{history_block}\n使用者：{message}\n\n"
            f"目前已有的資料：\n{context}\n\n"
            "請判斷是否需要再搜尋更多資訊才能回答，並輸出 JSON。"
        )
        yield {"type": "step_start", "step": {"label": label, "system": _CHAT_SEARCH_DECISION_SYSTEM_PROMPT, "prompt": decision_prompt}}
        decision = generate_json(decision_prompt, system=_CHAT_SEARCH_DECISION_SYSTEM_PROMPT,
                                  temperature=0.2, num_predict=150, num_ctx=CHAT_NUM_CTX)
        step = _trace_step(label, decision, system=_CHAT_SEARCH_DECISION_SYSTEM_PROMPT, prompt=decision_prompt)
        trace.append(step)
        yield {"type": "step_done", "step": step}

        if not isinstance(decision, dict) or not decision.get("need_search"):
            break
        query = str(decision.get("search_query") or "").strip()[:100]
        if not query:
            break

        query_counts[query] = query_counts.get(query, 0) + 1
        page = query_counts[query]
        search_label = f"SearXNG 搜尋（第 {round_no} 輪）：「{query}」"
        if page > 1:
            search_label += f"（第 {page} 頁）"
        yield {"type": "step_start", "step": {"label": search_label, "system": None, "prompt": None}}
        results = search_news(query, limit=5, page=page)
        step = _trace_step(search_label, {"query": query, "page": page, "results": results})
        trace.append(step)
        yield {"type": "step_done", "step": step}

        for r in results:
            url = r.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append(r)

        context += "\n\n" + _format_search_block(round_no, query, results)
        if not results and query not in failed_queries:
            failed_queries.append(query)

    # ── 5. 回答 ────────────────────────────────────────────────────────────
    answer_prompt = (
        f"先前對話：\n{history_block}\n\n"
        f"使用者最新問題：{message}\n\n"
        f"可用資料：\n{context}\n\n"
        "請回答使用者的問題，輸出 JSON。"
    )
    yield {"type": "step_start", "step": {"label": "整理回答", "system": _CHAT_SYSTEM_PROMPT, "prompt": answer_prompt}}
    raw = generate_json(answer_prompt, system=_CHAT_SYSTEM_PROMPT, temperature=0.4,
                         num_predict=700, num_ctx=CHAT_NUM_CTX)
    step = _trace_step("整理回答", raw, system=_CHAT_SYSTEM_PROMPT, prompt=answer_prompt)
    trace.append(step)
    yield {"type": "step_done", "step": step}

    reply = ""
    if isinstance(raw, dict):
        reply = str(raw.get("reply", "")).strip()
    if not reply:
        reply = "抱歉，本機 LLM 無回應或逾時，請稍後再試。"

    # ── 6. 二次驗證：僅在有股票資料／搜尋結果可核對時執行，純聊天則略過 ──────────
    verified: bool | None = None
    has_context_data = bool(stock_blocks) or bool(sources)
    if has_context_data:
        verify_prompt = (
            f"可用資料：\n{context}\n\n"
            f"以下是另一位助手根據上述資料，回覆使用者「{message}」的內容：\n{reply}\n\n"
            "請核對回覆中的每一句具體陳述是否有上述資料支持，移除或修正查無依據的內容，"
            '輸出修正後、格式相同的 JSON：{"reply": "..."}。'
        )
        yield {"type": "step_start", "step": {"label": "二次驗證", "system": _CHAT_VERIFY_SYSTEM_PROMPT, "prompt": verify_prompt}}
        verified_raw = generate_json(verify_prompt, system=_CHAT_VERIFY_SYSTEM_PROMPT,
                                      temperature=0.1, num_predict=700, num_ctx=CHAT_NUM_CTX)
        step = _trace_step("二次驗證", verified_raw, system=_CHAT_VERIFY_SYSTEM_PROMPT, prompt=verify_prompt)
        trace.append(step)
        yield {"type": "step_done", "step": step}

        verified_reply = ""
        if isinstance(verified_raw, dict):
            verified_reply = str(verified_raw.get("reply", "")).strip()
        if verified_reply:
            reply = verified_reply
            verified = True
        else:
            verified = False

    yield {"type": "result", "result": {
        "reply": reply,
        "used_tickers": used_tickers,
        "sources": sources,
        "verified": verified,
        "trace": trace,
    }}
