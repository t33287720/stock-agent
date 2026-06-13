"""
今日訊號掃描器 — 不依賴投資組合，純訊號掃描。

買入候選：最新一根 K 棒 should_buy() == True
賣出候選：should_sell() == True（最近 3 根內最新訊號為 -1）
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from backend.data.fetcher import get_stock_history, get_top100_stocks
from backend.data.news import get_stock_news
from backend.analysis.technical import calculate_indicators
from backend.llm.analysis import analyze_scan_candidate
from backend.strategy.signals import generate_signals, should_buy, should_sell


def scan_today(max_candidates: int = 80) -> dict:
    """
    掃描前 N 支股票，回傳今日買入/賣出候選清單。
    並行抓取資料，使用與 auto_trade / full_backtest 完全相同的硬性規則篩選。
    """
    stocks = get_top100_stocks()
    candidates = [s for s in stocks if s.get("ticker")][:max_candidates]

    # ── 並行抓取所有候選股票資料 ──────────────────────────────────────────────
    def _fetch(s):
        ticker = s["ticker"]
        try:
            df = get_stock_history(ticker, 90)
            if df.empty or len(df) < 20:
                return ticker, s, None
            df = calculate_indicators(df)
            df = generate_signals(df)
            return ticker, s, df
        except Exception as e:
            return ticker, s, e

    with ThreadPoolExecutor(max_workers=15) as ex:
        fetched = list(ex.map(_fetch, candidates))

    # ── 依原始排名順序處理結果 ────────────────────────────────────────────────
    buy_candidates:  list[dict] = []
    sell_candidates: list[dict] = []
    errors: list[str] = []
    scanned = 0

    for ticker, s, df_or_err in fetched:
        if df_or_err is None:
            continue
        if isinstance(df_or_err, Exception):
            errors.append(f"{ticker}: {str(df_or_err)[:60]}")
            continue

        df          = df_or_err
        last_row    = df.iloc[-1]
        latest_date = str(df.index[-1])[:10]

        price = float(last_row["Close"])
        rsi   = _safe_float(last_row.get("RSI"), 50.0)
        macd  = _safe_float(last_row.get("MACD"), 0.0)
        msig  = _safe_float(last_row.get("MACD_signal"), 0.0)
        k_val = _safe_float(last_row.get("K"), 50.0)
        d_val = _safe_float(last_row.get("D"), 50.0)
        sma20 = _safe_float(last_row.get("SMA_20"), price)
        sma60 = _safe_float(last_row.get("SMA_60"), price)

        entry = {
            "ticker":       ticker,
            "name":         s.get("name", ticker),
            "price":        round(price, 2),
            "rsi":          round(rsi, 1),
            "macd_bullish": macd > msig,
            "k":            round(k_val, 1),
            "d":            round(d_val, 1),
            "golden_cross": bool(sma20 > sma60),
            "sma20":        round(sma20, 2),
            "sma60":        round(sma60, 2),
        }

        # ── 買入候選：與 auto_trade 相同的 should_buy 硬性規則 ──────────────
        if should_buy(last_row):
            buy_candidates.append({
                **entry,
                "signal_reason": str(last_row.get("signal_reason", "買入訊號")),
                "signal_date":   latest_date,
                "is_today":      True,
            })
        else:
            # ── 賣出候選：與 auto_trade 相同的 should_sell 硬性規則 ──────────
            recent = list(df.iloc[-3:].to_dict("records")) if len(df) >= 3 else list(df.to_dict("records"))
            triggered, reason = should_sell(recent)
            if triggered:
                sell_idx = next(
                    (i for i in range(len(recent) - 1, -1, -1)
                     if int(recent[i].get("signal", 0)) == -1),
                    len(recent) - 1,
                )
                sig_date = str(df.index[-(len(recent) - sell_idx)])[:10]
                sell_candidates.append({
                    **entry,
                    "signal_reason": reason,
                    "signal_date":   sig_date,
                    "is_today":      sig_date == latest_date,
                })

        scanned += 1

    # 買入候選依 RSI 由低到高（訊號越乾淨越前面）
    buy_candidates.sort(key=lambda x: x["rsi"])
    # 賣出候選：今日訊號排前面，再依 RSI 由高到低
    sell_candidates.sort(key=lambda x: (not x["is_today"], -x["rsi"]))

    return {
        "scanned":         scanned,
        "buy_count":       len(buy_candidates),
        "sell_count":      len(sell_candidates),
        "buy_candidates":  buy_candidates,
        "sell_candidates": sell_candidates,
        "scan_time":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        "errors":          errors[:5],
    }


def enrich_with_ai(result: dict) -> dict:
    """為今日訊號候選股加上 AI 信心評分（含新聞佐證），僅處理 is_today=True 的候選。"""
    candidates = result.get("buy_candidates", []) + result.get("sell_candidates", [])

    def _enrich_one(c):
        if not c.get("is_today"):
            c["ai_confidence"] = None
            c["ai_summary"] = None
            c["ai_has_news"] = None
            return
        try:
            name = c.get("name", c["ticker"])
            news = get_stock_news(c["ticker"], name, limit=3)
            technical_snapshot = {
                "rsi": c.get("rsi"),
                "macd_bullish": c.get("macd_bullish"),
                "k": c.get("k"),
                "d": c.get("d"),
                "golden_cross": c.get("golden_cross"),
            }
            ai = analyze_scan_candidate(c["ticker"], name, c.get("signal_reason", ""), technical_snapshot, news)
            c["ai_confidence"] = ai.get("ai_confidence")
            c["ai_summary"] = ai.get("ai_summary")
            c["ai_has_news"] = ai.get("has_news")
        except Exception as e:
            c["ai_confidence"] = None
            c["ai_summary"] = f"AI 分析失敗: {str(e)[:40]}"
            c["ai_has_news"] = None

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(_enrich_one, candidates))

    result["ai_enriched"] = True
    return result


def _safe_float(val, default: float = 0.0) -> float:
    try:
        f = float(val)
        return default if (f != f) else f
    except (TypeError, ValueError):
        return default
