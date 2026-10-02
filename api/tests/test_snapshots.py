"""
快照測試：用固定的假資料跑一遍主要流程，輸出要跟 tests/snapshots/outputs.json 完全相同。

涵蓋技術指標、買賣訊號、回測、今日訊號掃描、AI 分析與聊天的完整串流（每一步送給 LLM 的
prompt 與參數）、證交所／櫃買中心資料解析、全市場篩選。重構時輸出只要有一點不同就會失敗。

輸出是刻意改變的話，重新產生快照並在 commit 裡一起看 diff：
    UPDATE_SNAPSHOTS=1 python -m pytest tests/test_snapshots.py
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from conftest import fake_http

SNAPSHOT = Path(__file__).parent / "snapshots" / "outputs.json"


def synthetic(seed: int, n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    vol = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.bdate_range("2025-01-01", periods=n, name="Date")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=idx)


def jsonable(o):
    return json.loads(json.dumps(o, default=str, ensure_ascii=False))


def scripted_llm(script: dict):
    """依 system prompt 裡的關鍵字回傳事先排好的回應，並記錄每次呼叫的參數。"""
    calls = []

    def fake(prompt, system=None, **kw):
        calls.append({"system": system, "kw": sorted(kw.items())})
        for key, responses in script.items():
            if system and key in system:
                return responses.pop(0) if responses else None
        return None
    return fake, calls


def fake_search(query, limit=5, page=1):
    if "空" in query:
        return []
    return [{"title": f"{query}-p{page}-{i}", "url": f"http://x/{query}/{page}/{i}", "body": "內容" * 60,
             "date": None, "source": "e"} for i in range(2)]


ANALYSIS_SCRIPTS = {
    "normal": {"判斷目前資料是否足夠": [{"need_search": True, "search_query": "台積電 法說會"},
                                      {"need_search": True, "search_query": "台積電 法說會"},
                                      {"need_search": True, "search_query": "空查詢"},
                                      {"need_search": False}],
               "事實核對員": [{"verdict": "偏多", "confidence": 77, "key_reasons": ["a"], "risks": ["r"], "summary": "verified"}],
               "台股分析助手。請只根據": [{"verdict": "看漲", "confidence": "55.6", "key_reasons": ["x", "y"], "risks": [], "summary": "s"}]},
    "llm_down": {},
    "verify_fail": {"判斷目前資料是否足夠": [{"need_search": False}],
                    "台股分析助手。請只根據": [{"verdict": "bearish", "confidence": 140, "summary": "x" * 400}]},
    "max_rounds": {"判斷目前資料是否足夠": [{"need_search": True, "search_query": f"q{i}"} for i in range(12)]},
}

CHAT_SCRIPTS = {
    "stock": {"問題解析器": [{"queries": ["台積電", "不存在"]}],
              "正在準備回答": [{"need_search": True, "search_query": "半導體"}, {"need_search": True, "search_query": "空"},
                          {"need_search": False}],
              "個性親切": [{"reply": "原回覆"}],
              "事實核對員": [{"reply": "驗證後"}]},
    "smalltalk": {"問題解析器": [{"queries": []}], "正在準備回答": [{"need_search": False}], "個性親切": [{"reply": "hi"}]},
    "unresolved": {"問題解析器": [{"queries": ["無此公司"]}], "個性親切": [None]},
    "verify_empty": {"問題解析器": [{"queries": ["台積電"]}], "正在準備回答": [{"need_search": False}],
                     "個性親切": [{"reply": "a"}], "事實核對員": [{"reply": ""}]},
}

MARKET_HTTP = {
    "STOCK_DAY_ALL": [{"Code": "2330", "Name": "台積電", "TradeVolume": "12,345,000", "ClosingPrice": "1,000.5", "TradeValue": "9,999"},
                      {"Code": "0050", "Name": "元大50", "TradeVolume": "1000", "ClosingPrice": "--", "TradeValue": "1"},
                      {"Code": "BAD", "Name": "x", "TradeVolume": "abc"}],
    "tpex_mainboard_daily_close_quotes": [{"SecuritiesCompanyCode": "6488", "CompanyName": "環球晶", "TradingShares": "2,000", "Close": "400", "TransactionAmount": "800,000"},
                                          {"SecuritiesCompanyCode": "1234", "CompanyName": "y", "TradingShares": "", "Close": "1"}],
    "BWIBBU_d": {"stat": "OK", "fields": ["證券代號", "證券名稱", "收盤價", "殖利率(%)", "股利年度", "本益比", "股價淨值比", "財報年/季"],
                 "data": [["2330", "台積電", "1000", "1.5", "114", "20.1", "5.5", "114/2"]]},
    "peratio_analysis": [{"SecuritiesCompanyCode": "6488", "PriceEarningRatio": "15", "PriceBookRatio": "N/A", "YieldRatio": "3.2"}, {}],
}


def collect(monkeypatch) -> dict:
    from backend.control.analysis import technical
    from backend.control.data import fetcher
    from backend.control.llm import analysis, chat, ollama_client, react
    from backend.control.strategy import scanner, signals

    out = {}

    for seed in (1, 2, 3):
        df = technical.calculate_indicators(synthetic(seed))
        sig = signals.generate_signals(df)
        out[f"summary_{seed}"] = technical.get_indicator_summary(sig)
        out[f"signals_{seed}"] = sig[["signal", "signal_reason"]].reset_index().astype(str).values.tolist()
        for fee in (True, False):
            out[f"backtest_{seed}_{fee}"] = jsonable(vars(signals.run_backtest("T", df, with_fee=fee)))

    universe = [{"ticker": f"{1000 + i}", "name": f"股{i}"} for i in range(40)]
    monkeypatch.setattr(scanner, "get_top100_stocks", lambda: universe)
    monkeypatch.setattr(scanner, "get_stock_history",
                        lambda t, days: synthetic(int(t)).tail(days) if int(t) % 7 else pd.DataFrame())
    res = scanner.scan_today(max_candidates=40)
    res.pop("scan_time")
    out["scan"] = jsonable(res)

    cases = ['{"a":1}', '```json\n{"a":2}\n```', 'noise {"a":3,} tail', "garbage", "", '{"a": [1,2,],}']
    out["parse"] = [ollama_client._parse_json_relaxed(c) for c in cases]

    monkeypatch.setattr(react, "search_news", fake_search)
    for name, script in ANALYSIS_SCRIPTS.items():
        fake, calls = scripted_llm(json.loads(json.dumps(script)))
        monkeypatch.setattr(react, "generate_json", fake)
        events = list(analysis.analyze_stock_stream("2330", "台積電", out["summary_1"], {"pe": 10}, [
            {"title": "n1", "body": "b", "date": "2026-01-01"}]))
        out[f"analysis_{name}"] = jsonable(events)
        out[f"analysis_{name}_calls"] = jsonable(calls)

    monkeypatch.setattr(chat, "search_tickers", lambda q, limit=1: [{"ticker": "2330", "name": "台積電"}] if "積" in q else [])
    monkeypatch.setattr(chat, "get_stock_history", lambda t, d: synthetic(5).tail(d))
    monkeypatch.setattr(chat, "get_fundamental", lambda t: {"pe": 12, "name": "台積電"})
    monkeypatch.setattr(chat, "get_stock_news", lambda t, n: [{"title": "news", "url": "http://n/1", "body": "b"}])
    for name, script in CHAT_SCRIPTS.items():
        fake, calls = scripted_llm(json.loads(json.dumps(script)))
        monkeypatch.setattr(react, "generate_json", fake)
        events = list(chat.chat_stream([{"role": "user", "content": "之前"}, {"role": "assistant", "content": "好"}], "台積電如何"))
        out[f"chat_{name}"] = jsonable(events)
        out[f"chat_{name}_calls"] = jsonable(calls)

    monkeypatch.setattr(fetcher.requests, "get", fake_http(MARKET_HTTP))
    out["twse_quotes"] = fetcher._fetch_all_twse_quotes()
    out["tpex_quotes"] = fetcher._fetch_all_tpex_quotes()
    out["tpex_val"] = fetcher._fetch_all_tpex_valuation()
    out["screener"] = fetcher.get_market_screener()

    out["normalize"] = [analysis._normalize_result(x, True) for x in (
        None, {"verdict": "中立", "confidence": "abc", "summary": " s "}, {"verdict": "??", "summary": "s"},
        {"verdict": "偏空", "confidence": -5, "summary": "s", "key_reasons": "notlist", "risks": [1, "", None, "r"]})]
    return jsonable(out)


def test_outputs_match_snapshot(monkeypatch):
    actual = collect(monkeypatch)
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps(actual, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(actual) == sorted(expected)
    for key in expected:
        assert actual[key] == expected[key], f"「{key}」的輸出跟快照不同"
