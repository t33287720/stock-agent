"""
Stock Analysis AI Agent.

Claude  → native tool_use loop (真正 agentic，Claude 自主決定呼叫哪些工具)
Gemini/GPT → multi-step prompted loop (模擬 agentic，3 階段引導式推理)

Agent 流程：
1. 收集資料（自主選擇工具）
2. 自我評估信心分數
3. 信心不足 → 繼續收集或修正
4. 信心 ≥ 70 → 提交最終結論
"""
import json
import re
import time
from typing import Any

from backend.config import get_api_key, load_config
from backend.llm.agent_tools import (
    TOOL_SCHEMAS, TOOL_LABELS, execute_tool, summarize_output,
)

MAX_ITER = 6  # 最多幾輪工具呼叫


# ── Public entry point ─────────────────────────────────────────────────────────

def run_agent(ticker: str, name: str) -> dict:
    """
    Run the agent for a given ticker.
    Returns:
        steps:      list of reasoning steps (for UI display)
        verdict:    "強烈看多" | "看多" | "中性觀望" | "看空" | "強烈看空"
        confidence: int 0-100
        key_reasons, risks, entry_price_range, target_price, stop_loss
        summary:    full analysis text
        provider:   which LLM was used
        iterations: number of tool calls made
    """
    cfg      = load_config()
    provider = cfg["settings"].get("llm_provider", "anthropic")
    model    = cfg["settings"].get("llm_model", "claude-opus-4-7")

    if provider == "anthropic":
        return _claude_agent(ticker, name, model)
    else:
        return _prompted_agent(ticker, name, provider, model)


# ── Claude agent (true tool_use) ───────────────────────────────────────────────

def _claude_agent(ticker: str, name: str, model: str) -> dict:
    api_key = get_api_key("anthropic")
    if not api_key:
        return _error("請在設定頁面填入 Anthropic API Key")

    try:
        import anthropic
    except ImportError:
        return _error("請安裝 anthropic 套件：pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)

    system = f"""你是一位嚴謹的台股分析 AI Agent，正在分析 {ticker}（{name}）。

你有 4 個資料工具可以呼叫，以及 1 個提交工具。請遵循以下流程：

【分析流程】
1. 呼叫工具收集資料（至少 2 個資料工具）
2. 分析資料，找出支持和反對某個判斷的證據
3. 評估自己的信心：信心 < 70 時，必須繼續收集更多資料
4. 若技術面和基本面有矛盾，必須執行回測來驗證
5. 信心 ≥ 70 且資料充分後，呼叫 submit_analysis 提交結論

【誠實原則】
- 不確定就說不確定，不要因為「資料看起來不錯」就強行樂觀
- 指標衝突是正常的，要明確說明如何處理衝突
- 信心分數要真實反映資料品質，不是越高越好"""

    messages: list[dict] = [
        {"role": "user", "content": f"請分析 {ticker} {name}，給出有根據的投資判斷。"}
    ]

    steps: list[dict] = []

    for _ in range(MAX_ITER):
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        # Extract text thoughts and tool calls
        tool_uses  = [b for b in resp.content if b.type == "tool_use"]
        text_parts = [b.text for b in resp.content if b.type == "text"]
        thought    = " ".join(text_parts).strip()

        if not tool_uses:
            break  # Claude stopped naturally

        messages.append({"role": "assistant", "content": resp.content})

        tool_results = []
        final_data   = None

        for tu in tool_uses:
            result = execute_tool(tu.name, tu.input)

            steps.append({
                "tool":          tu.name,
                "tool_label":    TOOL_LABELS.get(tu.name, tu.name),
                "input":         tu.input,
                "output_summary": summarize_output(tu.name, result),
                "thought":       thought,
            })

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tu.id,
                "content":     json.dumps(result, ensure_ascii=False, default=str),
            })

            if tu.name == "submit_analysis" and result.get("submitted"):
                final_data = result
                break

        if final_data:
            return _build_result(ticker, name, steps, final_data, "anthropic")

        messages.append({"role": "user", "content": tool_results})

        if resp.stop_reason == "end_turn":
            break

    return _build_result(ticker, name, steps, _fallback_final(), "anthropic")


# ── Prompted agent (Gemini / GPT) ─────────────────────────────────────────────

def _prompted_agent(ticker: str, name: str, provider: str, model: str) -> dict:
    """
    3-stage agentic loop using structured JSON prompts.
    Stage 1 → gather tech + fundamentals → initial assessment
    Stage 2 → gather what agent requested (backtest / signals) → revised assessment
    Stage 3 → finalize conclusion
    """
    steps: list[dict] = []

    # ── Stage 1: gather baseline data ─────────────────────────────────────────
    tech = _run_tool(steps, "get_price_and_indicators", {"ticker": ticker, "days": 90})
    fund = _run_tool(steps, "get_fundamental_data",     {"ticker": ticker})

    ind  = tech.get("indicators", {})
    ctx  = tech.get("context", {})

    macd_dir = "多頭" if (ind.get("macd") or 0) > (ind.get("macd_signal") or 0) else "空頭"
    ma_dir   = "多頭" if ind.get("golden_cross") else "空頭"

    stage1_prompt = (
        f"你是台股分析師，請分析台股 {ticker}（{name}）並輸出 JSON。\n\n"
        f"技術面（90天）：收盤={ind.get('close','N/A')}，RSI={ind.get('rsi','N/A')}，"
        f"MACD={macd_dir}，KD={ind.get('k','N/A')}/{ind.get('d','N/A')}，"
        f"均線={ma_dir}，5日動能={ctx.get('5day_momentum_pct','N/A')}%\n"
        f"基本面：PE={fund.get('pe','N/A')}，PB={fund.get('pb','N/A')}，"
        f"ROE={fund.get('roe','N/A')}%，殖利率={fund.get('div_yield','N/A')}%\n\n"
        f"請輸出以下 JSON（不要輸出任何其他文字）：\n"
        f'{{"verdict":"看多","confidence":70,"reasoning":"分析邏輯",'
        f'"needs_backtest":true,"needs_signals":false}}\n\n'
        f"欄位說明：\n"
        f"verdict = 看多 / 看空 / 中性觀望（擇一）\n"
        f"confidence = 0到100的整數，代表你對這個判斷的把握程度\n"
        f"reasoning = 100字以內的分析理由\n"
        f"needs_backtest = 技術面和基本面有矛盾，或不確定時填 true\n"
        f"needs_signals = 想確認過去訊號頻率時填 true"
    )

    stage1 = _call_llm_json(stage1_prompt, provider, model)
    # 容錯：Gemini 有時用不同欄位名
    s1_verdict = (stage1.get("verdict") or stage1.get("preliminary_verdict")
                  or stage1.get("analysis") or "中性觀望")
    confidence_1 = int(stage1.get("confidence") or stage1.get("confidence_score") or 50)
    needs_bt  = bool(stage1.get("needs_backtest") or (confidence_1 < 65))
    needs_sig = bool(stage1.get("needs_signals"))

    steps.append({
        "tool":           "self_evaluate",
        "tool_label":     "🤔 初步評估",
        "input":          {"stage": 1},
        "output_summary": f"初步判斷：{s1_verdict}，信心 {confidence_1}%",
        "thought":        stage1.get("reasoning", ""),
    })

    # ── Stage 2: gather extra data and revise ──────────────────────────────────
    extra_lines: list[str] = []

    if needs_bt:
        bt = _run_tool(steps, "run_strategy_backtest", {"ticker": ticker, "days": 365})
        extra_lines.append(
            f"歷史回測：年化報酬{bt.get('total_return_pct','?')}%，"
            f"勝率{bt.get('win_rate','?')}%，"
            f"夏普比率{bt.get('sharpe_ratio','?')}，"
            f"最大回撤{bt.get('max_drawdown_pct','?')}%"
        )

    if needs_sig:
        sg = _run_tool(steps, "get_signal_history", {"ticker": ticker, "days": 180})
        extra_lines.append(
            f"訊號歷史：共{sg.get('total_signals',0)}個，"
            f"買{sg.get('buy_count',0)} 賣{sg.get('sell_count',0)}，"
            f"平均每{sg.get('avg_days_between_signals','?')}天一次"
        )

    extra_text = "；".join(extra_lines) if extra_lines else "無補充資料"

    _rate_limit_wait(provider)   # 避免 429

    stage2_prompt = (
        f"你是台股分析師，請更新對 {ticker}（{name}）的分析並輸出 JSON。\n\n"
        f"初步判斷：{s1_verdict}（信心 {confidence_1}%）\n"
        f"初步理由：{stage1.get('reasoning','')}\n"
        f"補充資料：{extra_text}\n\n"
        f"請輸出以下 JSON（不要輸出任何其他文字）：\n"
        f'{{"verdict":"看多","confidence":80,"reasoning":"更新理由",'
        f'"contradiction":"矛盾說明或無"}}\n\n'
        f"欄位說明：\n"
        f"verdict = 看多 / 看空 / 中性觀望（擇一，根據補充資料修正）\n"
        f"confidence = 0到100整數（回測勝率低於50%則不超過65）\n"
        f"reasoning = 120字以內的更新理由\n"
        f"contradiction = 如何處理矛盾，若無矛盾填「無」"
    )

    stage2 = _call_llm_json(stage2_prompt, provider, model)
    s2_verdict    = (stage2.get("verdict") or stage2.get("updated_verdict")
                     or s1_verdict)
    confidence_2  = int(stage2.get("confidence") or confidence_1)

    steps.append({
        "tool":           "self_evaluate",
        "tool_label":     "🔍 修正評估",
        "input":          {"stage": 2},
        "output_summary": f"修正判斷：{s2_verdict}，信心 {confidence_2}%",
        "thought":        stage2.get("reasoning", ""),
    })

    # ── Stage 3: final verdict ─────────────────────────────────────────────────
    close_price  = ind.get("close")
    price_hint   = f"（收盤約 {close_price}）" if close_price else ""
    best_verdict = s2_verdict
    best_conf    = confidence_2

    _rate_limit_wait(provider)   # 避免 429

    stage3_prompt = (
        f"你是台股分析師，請對 {ticker}（{name}）{price_hint}輸出最終完整分析報告 JSON。\n\n"
        f"分析摘要：最終判斷={best_verdict}，信心={best_conf}%\n"
        f"技術分析：{stage1.get('reasoning','')}\n"
        f"更新分析：{stage2.get('reasoning','')}\n"
        f"矛盾處理：{stage2.get('contradiction','')}\n\n"
        f"請輸出以下 JSON（不要輸出任何其他文字）：\n"
        f'{{"verdict":"看多","confidence":80,"key_reasons":["理由1","理由2"],'
        f'"risks":["風險1"],"entry_price_range":"95-100","target_price":"115",'
        f'"stop_loss":"88","summary":"完整分析摘要"}}\n\n'
        f"欄位說明：\n"
        f"verdict = 強烈看多 / 看多 / 中性觀望 / 看空 / 強烈看空（擇一）\n"
        f"confidence = 0到100整數\n"
        f"key_reasons = 2到3個支持判斷的關鍵理由\n"
        f"risks = 1到2個主要風險\n"
        f"entry_price_range = 建議進場價格區間，例如 95-100，或填「不建議」\n"
        f"target_price = 目標價格\n"
        f"stop_loss = 建議停損價格\n"
        f"summary = 150到250字的完整分析"
    )

    final = _call_llm_json(stage3_prompt, provider, model)

    # ── 關鍵 fallback：stage3 失敗時用 stage2 資料補上 ────────────────────────
    if not final.get("verdict"):
        final["verdict"] = best_verdict
    if not final.get("confidence"):
        final["confidence"] = best_conf
    if not final.get("key_reasons"):
        final["key_reasons"] = [stage2.get("reasoning", stage1.get("reasoning", ""))]
    if not final.get("risks"):
        final["risks"] = [stage2.get("contradiction", "需人工確認")]
    if not final.get("summary"):
        final["summary"] = stage2.get("reasoning", stage1.get("reasoning", ""))
    final["submitted"] = True

    steps.append({
        "tool":           "submit_analysis",
        "tool_label":     "✅ 提交最終結論",
        "input":          {},
        "output_summary": summarize_output("submit_analysis", final),
        "thought":        final.get("summary", ""),
    })

    return _build_result(ticker, name, steps, final, provider)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _run_tool(steps: list, name: str, inp: dict) -> dict:
    """Execute a tool and append a step record."""
    result = execute_tool(name, inp)
    steps.append({
        "tool":           name,
        "tool_label":     TOOL_LABELS.get(name, name),
        "input":          inp,
        "output_summary": summarize_output(name, result),
        "thought":        "",
    })
    return result


def _build_result(ticker: str, name: str, steps: list,
                  final: dict, provider: str) -> dict:
    # confidence=0 幾乎不可能是真實分析結果，用 50 替代避免誤導
    confidence = final.get("confidence") or 0
    if confidence == 0:
        confidence = 50
    return {
        "ticker":            ticker,
        "name":              name,
        "provider":          provider,
        "steps":             steps,
        "verdict":           final.get("verdict") or "中性觀望",
        "confidence":        confidence,
        "key_reasons":       final.get("key_reasons") or [],
        "risks":             final.get("risks") or [],
        "entry_price_range": final.get("entry_price_range") or "N/A",
        "target_price":      final.get("target_price") or "N/A",
        "stop_loss":         final.get("stop_loss") or "N/A",
        "summary":           final.get("summary") or "",
        "iterations":        len([s for s in steps if s["tool"] != "self_evaluate"]),
    }


def _fallback_final() -> dict:
    return {
        "submitted":   True,
        "verdict":     "中性觀望",
        "confidence":  50,
        "key_reasons": ["資料收集未完成"],
        "risks":       ["分析流程中斷，建議重試"],
        "summary":     "Agent 分析流程未正常完成，請重試或切換至一般 AI 分析模式。",
    }


def _error(msg: str) -> dict:
    return {
        "error": msg, "ticker": "", "name": "", "steps": [],
        "verdict": "中性觀望", "confidence": 0,
        "key_reasons": [], "risks": [], "summary": msg,
    }


# ── LLM JSON callers ───────────────────────────────────────────────────────────

def _call_llm_json(prompt: str, provider: str, model: str) -> dict:
    """Call the LLM and parse a JSON response."""
    raw = _call_llm_text(prompt, provider, model)
    return _parse_json(raw)


def _call_llm_text(prompt: str, provider: str, model: str) -> str:
    api_key = get_api_key(provider)
    if not api_key:
        return "{}"

    if provider == "gemini":
        return _gemini_text(prompt, model, api_key)
    if provider == "openai":
        return _openai_text(prompt, model, api_key)
    if provider == "anthropic":
        return _claude_text(prompt, model, api_key)
    return "{}"


def _claude_text(prompt: str, model: str, api_key: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        return f'{{"error": "{e}"}}'


def _openai_text(prompt: str, model: str, api_key: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model or "gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f'{{"error": "{e}"}}'


def _gemini_text(prompt: str, model: str, api_key: str) -> str:
    model = model or "gemini-2.0-flash"
    last_err = ""
    for attempt in range(3):
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            m = genai.GenerativeModel(
                model,
                generation_config={"response_mime_type": "application/json"},
            )
            resp = m.generate_content(prompt)
            return resp.text
        except ImportError:
            return _gemini_rest(prompt, model, api_key)
        except Exception as e:
            last_err = str(e)
            if "429" in last_err or "quota" in last_err.lower():
                wait = (attempt + 1) * 15  # 15s, 30s, 45s
                time.sleep(wait)
                continue
            return f'{{"error": "{last_err}"}}'
    return f'{{"error": "429 Rate limit，已重試3次：{last_err}"}}'


def _gemini_rest(prompt: str, model: str, api_key: str) -> str:
    import urllib.request
    import urllib.error
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 1200,
                             "responseMimeType": "application/json"},
    }).encode()
    for attempt in range(3):
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.loads(r.read())
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep((attempt + 1) * 15)
                continue
            return f'{{"error": "HTTP {e.code}: {e.reason}"}}'
        except Exception as e:
            return f'{{"error": "{e}"}}'
    return '{"error": "429 Rate limit，REST 已重試3次"}'


def _rate_limit_wait(provider: str) -> None:
    """在 LLM API 呼叫之間等待，避免觸發 429 Rate Limit。
    Gemini 免費版限制 10 RPM，每次等 7 秒確保安全。"""
    if provider in ("gemini", "anthropic", "openai"):
        time.sleep(7)


def _parse_json(text: str) -> dict:
    """Robustly extract JSON from LLM output (handles ```json blocks, etc.)."""
    if not text:
        return {}
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}
