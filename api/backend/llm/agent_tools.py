"""
Tool definitions and executors for the Stock Analysis Agent.
Each tool wraps existing backend functions so the agent can call them on demand.
"""
import math
from backend.data.fetcher import get_stock_history, get_fundamental
from backend.analysis.technical import calculate_indicators, get_indicator_summary
from backend.strategy.signals import generate_signals, run_backtest


# ── Claude tool_use schemas ────────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "get_price_and_indicators",
        "description": (
            "取得股票歷史K線資料與所有技術指標（RSI、MACD、KD、布林通道、均線）。"
            "建議先用 90 天快速掃描，若趨勢不清晰或指標衝突，再用 365 天確認。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "台股代號，例如 2330"},
                "days":   {"type": "integer", "description": "歷史天數（60–365），預設 90", "default": 90},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_fundamental_data",
        "description": (
            "取得基本面資料：本益比(PE)、股價淨值比(PB)、ROE、EPS、殖利率、市值、產業。"
            "用於評估估值是否合理，以及是否有長期投資價值。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "台股代號"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "run_strategy_backtest",
        "description": (
            "執行歷史策略回測，驗證當前技術訊號在過去的實際表現。"
            "若勝率低於 50% 或夏普比率為負，應對當前訊號持保留態度。"
            "這是驗證技術分析可靠性最重要的工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "台股代號"},
                "days":   {"type": "integer", "description": "回測天數，建議 365", "default": 365},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_signal_history",
        "description": (
            "取得此股票過去所有買賣訊號的歷史記錄。"
            "用於判斷訊號一致性：若多個指標同向確認（MACD+KD+SMA同時買訊），可信度更高。"
            "若訊號頻繁反轉，代表此股波動大、技術分析適用性低。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days":   {"type": "integer", "default": 180},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "submit_analysis",
        "description": (
            "完成分析後呼叫此工具提交最終結論。"
            "規則：\n"
            "1. 至少已呼叫 2 個資料工具才能提交\n"
            "2. 信心分數 < 70 時不應提交，應繼續收集資料\n"
            "3. 若技術面和基本面有明顯矛盾，需先透過回測驗證才能提交\n"
            "4. 誠實評估，不要因為「資料已夠」就過度樂觀"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["強烈看多", "看多", "中性觀望", "看空", "強烈看空"],
                    "description": "最終多空判斷",
                },
                "confidence": {
                    "type": "integer",
                    "description": "分析信心分數 0-100，代表結論的可靠程度",
                },
                "key_reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "支持此判斷的 2-4 個具體理由",
                },
                "risks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需注意的 1-3 個風險因素",
                },
                "entry_price_range": {
                    "type": "string",
                    "description": "建議進場價格區間，例如 '580–600'，若不適合進場則填 '不建議'",
                },
                "target_price": {
                    "type": "string",
                    "description": "目標價位（停利參考）",
                },
                "stop_loss": {
                    "type": "string",
                    "description": "建議停損價位",
                },
                "summary": {
                    "type": "string",
                    "description": "完整分析摘要（150-250字），說明判斷依據、矛盾點處理方式、操作建議",
                },
            },
            "required": ["verdict", "confidence", "key_reasons", "risks", "summary"],
        },
    },
]


# ── Tool executor ──────────────────────────────────────────────────────────────

def execute_tool(name: str, inp: dict) -> dict:
    """Execute a named tool and return the result as a plain dict."""
    ticker = inp.get("ticker", "")
    days   = inp.get("days", 365)

    if name == "get_price_and_indicators":
        df = get_stock_history(ticker, days)
        if df.empty:
            return {"error": f"找不到 {ticker} 的資料"}
        df = calculate_indicators(df)
        df = generate_signals(df)
        summary = get_indicator_summary(df)
        return {
            "ticker": ticker,
            "days": days,
            "indicators": _safe_dict(summary),
            "context": _price_context(df),
        }

    if name == "get_fundamental_data":
        data = get_fundamental(ticker)
        return _safe_dict(data)

    if name == "run_strategy_backtest":
        df = get_stock_history(ticker, days)
        if df.empty:
            return {"error": "找不到資料"}
        df = calculate_indicators(df)
        result = run_backtest(ticker, df, with_fee=True)
        return _safe_dict(vars(result))

    if name == "get_signal_history":
        df = get_stock_history(ticker, days)
        if df.empty:
            return {"error": "找不到資料"}
        df = calculate_indicators(df)
        df = generate_signals(df)
        signals = [
            {
                "date": str(d)[:10],
                "type": "買入" if int(row.get("signal", 0)) == 1 else "賣出",
                "reason": str(row.get("signal_reason", "")),
            }
            for d, row in df.iterrows()
            if int(row.get("signal", 0)) != 0
        ]
        buys  = [s for s in signals if s["type"] == "買入"]
        sells = [s for s in signals if s["type"] == "賣出"]
        return {
            "total_signals": len(signals),
            "buy_count":  len(buys),
            "sell_count": len(sells),
            "recent_20":  signals[-20:],
            "avg_days_between_signals": round(days / max(len(signals), 1), 1),
        }

    if name == "submit_analysis":
        return {"submitted": True, **inp}

    return {"error": f"未知工具：{name}"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_val(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return v


def _safe_dict(d: dict) -> dict:
    return {k: _safe_val(v) if not isinstance(v, (dict, list, str, bool)) else v
            for k, v in d.items()}


def _price_context(df) -> dict:
    """Extra price context not in get_indicator_summary."""
    if df.empty:
        return {}
    closes = df["Close"].dropna()
    if closes.empty:
        return {}
    hi = float(closes.max())
    lo = float(closes.min())
    last = float(closes.iloc[-1])
    pct_from_high = round((last - hi) / hi * 100, 2) if hi else 0
    pct_from_low  = round((last - lo) / lo * 100, 2) if lo else 0
    # 5-day momentum
    mom5 = round((last - float(closes.iloc[-6])) / float(closes.iloc[-6]) * 100, 2) \
        if len(closes) >= 6 else None
    return {
        "period_high":      round(hi, 2),
        "period_low":       round(lo, 2),
        "pct_from_high":    pct_from_high,
        "pct_from_low":     pct_from_low,
        "5day_momentum_pct": mom5,
    }


# ── Human-readable tool labels ─────────────────────────────────────────────────

TOOL_LABELS = {
    "get_price_and_indicators": "📊 取得技術指標",
    "get_fundamental_data":     "📋 取得基本面資料",
    "run_strategy_backtest":    "📉 執行歷史回測",
    "get_signal_history":       "🔔 查詢訊號歷史",
    "submit_analysis":          "✅ 提交分析結論",
}


def summarize_output(name: str, result: dict) -> str:
    """One-line summary of a tool result for the reasoning chain display."""
    if "error" in result:
        return f"⚠ 錯誤：{result['error']}"

    if name == "get_price_and_indicators":
        ind = result.get("indicators", {})
        ctx = result.get("context", {})
        rsi   = ind.get("rsi")
        macd  = ind.get("macd")
        msig  = ind.get("macd_signal")
        k, d  = ind.get("k"), ind.get("d")
        gc    = ind.get("golden_cross")
        mom   = ctx.get("5day_momentum_pct")
        parts = []
        if rsi  is not None: parts.append(f"RSI={rsi:.1f}({'超買' if rsi>70 else '超賣' if rsi<30 else '中性'})")
        if macd is not None and msig is not None:
            parts.append(f"MACD={'黃金交叉' if macd>msig else '死亡交叉'}")
        if k is not None and d is not None:
            parts.append(f"KD={k:.1f}/{d:.1f}")
        if gc  is not None: parts.append("均線多頭" if gc else "均線空頭")
        if mom is not None: parts.append(f"5日動能{mom:+.1f}%")
        return "，".join(parts) if parts else "資料取得完成"

    if name == "get_fundamental_data":
        pe  = result.get("pe")
        pb  = result.get("pb")
        roe = result.get("roe")
        dy  = result.get("div_yield")
        parts = []
        if pe  is not None: parts.append(f"PE={pe}")
        if pb  is not None: parts.append(f"PB={pb}")
        if roe is not None: parts.append(f"ROE={roe}%")
        if dy  is not None: parts.append(f"殖利率={dy}%")
        return "，".join(parts) if parts else "基本面資料取得完成"

    if name == "run_strategy_backtest":
        ret = result.get("total_return_pct")
        wr  = result.get("win_rate")
        sr  = result.get("sharpe_ratio")
        dd  = result.get("max_drawdown_pct")
        parts = []
        if ret is not None: parts.append(f"年化報酬{ret:.1f}%")
        if wr  is not None: parts.append(f"勝率{wr:.1f}%")
        if sr  is not None: parts.append(f"夏普{sr:.2f}")
        if dd  is not None: parts.append(f"最大回撤{dd:.1f}%")
        return "，".join(parts) if parts else "回測完成"

    if name == "get_signal_history":
        total = result.get("total_signals", 0)
        buys  = result.get("buy_count", 0)
        sells = result.get("sell_count", 0)
        avg   = result.get("avg_days_between_signals")
        s = f"共 {total} 個訊號（買{buys} 賣{sells}）"
        if avg: s += f"，平均每 {avg} 天一次"
        return s

    if name == "submit_analysis":
        v  = result.get("verdict", "")
        c  = result.get("confidence", 0)
        return f"判斷：{v}，信心度 {c}%"

    return "完成"
