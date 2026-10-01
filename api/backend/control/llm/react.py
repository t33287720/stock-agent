"""
個股 AI 分析（analysis.py）與聊天（chat.py）共用的 ReAct 流程積木。

兩者都是同一個模式：每一步呼叫 LLM 或 SearXNG 前送出 step_start、完成後送出 step_done
（前端即時顯示流程），並把每一步記進 trace。這裡的函式都是 generator，
呼叫端用 `result = yield from ...` 一邊把事件往外送、一邊拿到這一步的結果。
"""
from typing import Callable

from backend.control.data.news import search_news
from backend.control.llm.ollama_client import generate_json


def trace_step(label: str, response, system: str | None = None, prompt: str | None = None) -> dict:
    """記錄一個流程步驟（送給 LLM 的 prompt / SearXNG 查詢 + 收到的回應），供前端顯示完整流程。"""
    return {"label": label, "system": system, "prompt": prompt, "response": response}


def record(trace: list[dict], step: dict):
    """只有結果、沒有等待過程的步驟（例如純程式比對）：直接記錄並送出 step_done。"""
    trace.append(step)
    yield {"type": "step_done", "step": step}


def llm_step(trace: list[dict], label: str, prompt: str, system: str, **options):
    """呼叫一次 LLM（JSON mode），回傳解析後的 dict（失敗為 None）。"""
    yield {"type": "step_start", "step": {"label": label, "system": system, "prompt": prompt}}
    response = generate_json(prompt, system=system, **options)
    yield from record(trace, trace_step(label, response, system=system, prompt=prompt))
    return response


def format_search_block(title: str, query: str, results: list[dict]) -> str:
    if not results:
        return f"{title}（關鍵字：{query}）：（查無結果）"
    lines = [f"{title}（關鍵字：{query}）："]
    for r in results:
        lines.append(f"- {r.get('title') or ''}：{(r.get('body') or '')[:100]}")
    return "\n".join(lines)


def search_rounds(trace: list[dict], context: str, *, max_rounds: int, num_ctx: int,
                  decision_label: str, decision_system: str,
                  decision_prompt: Callable[[str, int, list[str]], str],
                  block_title: str):
    """讓 LLM 逐輪判斷要不要再搜尋，最多 max_rounds 輪；每輪的搜尋結果附加到 context 後面。

    decision_prompt(context, round_no, failed_queries) 產生每一輪的判斷 prompt。
    同一個關鍵字重複出現時改抓下一頁，避免拿到完全相同的結果。
    回傳 (附加搜尋結果後的 context, [{round, query, page, results}, ...])。
    """
    searches: list[dict] = []
    query_counts: dict[str, int] = {}
    failed_queries: list[str] = []

    for round_no in range(1, max_rounds + 1):
        decision = yield from llm_step(
            trace, f"{decision_label}（第 {round_no}/{max_rounds} 輪）",
            decision_prompt(context, round_no, failed_queries), decision_system,
            temperature=0.2, num_predict=150, num_ctx=num_ctx,
        )
        if not isinstance(decision, dict) or not decision.get("need_search"):
            break
        query = str(decision.get("search_query") or "").strip()[:100]
        if not query:
            break

        query_counts[query] = query_counts.get(query, 0) + 1
        page = query_counts[query]
        label = f"SearXNG 搜尋（第 {round_no} 輪）：「{query}」"
        if page > 1:
            label += f"（第 {page} 頁）"
        yield {"type": "step_start", "step": {"label": label, "system": None, "prompt": None}}
        results = search_news(query, limit=5, page=page)
        yield from record(trace, trace_step(label, {"query": query, "page": page, "results": results}))

        context += "\n\n" + format_search_block(f"{block_title}第 {round_no} 輪", query, results)
        searches.append({"round": round_no, "query": query, "page": page, "results": results})
        if not results and query not in failed_queries:
            failed_queries.append(query)

    return context, searches
