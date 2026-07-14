"""
Paper-trading engine — PostgreSQL backend.

買入規則（硬性）:
  should_buy(row)  — signal==1 AND RSI ≤ 65
  以 per_stock_budget 為每筆上限，買入當日收盤價

賣出規則（硬性）:
  should_sell(rows) — 最近 3 根中最新非零訊號為 -1
  觸發停利 / 停損也會賣出

所有「現在價格」統一用 get_latest_close(ticker)，
買入記錄的 avg_cost 也是同一來源，確保損益計算一致。
"""

from datetime import datetime

from backend.config import load_config
from backend.data.fetcher import get_stock_history, get_top100_stocks, get_latest_close, last_trading_day_str
from backend.analysis.technical import calculate_indicators
from backend.strategy.signals import generate_signals, should_buy, should_sell, check_exit, COMMISSION, TAX
import backend.db.portfolio_db as db
from concurrent.futures import ThreadPoolExecutor

db.init_db()


# ── Portfolio init / load ──────────────────────────────────────────────────────

def init_auto_portfolio(capital: float = 100_000, per_stock_budget: float = 10_000) -> dict:
    return db.reset_portfolio(capital, per_stock_budget)

def load_auto_orders() -> dict:
    return db.load_orders()


def cancel_position(ticker: str) -> dict:
    """
    撤銷持倉：退回原始買入金額（股款 + 手續費），並刪除今日買入紀錄。
    用於修正錯誤買入（如訊號過期），不計入損益。
    """
    portfolio = db.load_portfolio()
    if not portfolio:
        return {"error": "尚未初始化自動交易"}
    pos = portfolio.get("positions", {}).get(ticker)
    if not pos:
        return {"error": f"未持有 {ticker}"}

    refund = round(pos["shares"] * pos["avg_cost"] + pos.get("fee_paid", 0), 2)
    portfolio["cash"] = round(portfolio["cash"] + refund, 2)
    del portfolio["positions"][ticker]
    portfolio["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.save_portfolio(portfolio)
    db.delete_buy_today(ticker)
    return {"status": "ok", "ticker": ticker, "refund": refund, "cash": portfolio["cash"]}


# ── Single-stock trade ─────────────────────────────────────────────────────────

def execute_trade(ticker: str, df, action: str, name: str = "") -> tuple[str, str]:
    """
    action: 'auto' | 'buy' | 'sell'
    Returns (action_taken, message).
    """
    portfolio = db.load_portfolio()
    if not portfolio:
        return "error", "請先初始化自動交易"

    cfg    = load_config()["strategy"]
    tp_pct = cfg.get("take_profit_pct", 15) / 100
    sl_pct = cfg.get("stop_loss_pct",    7) / 100
    per_stock_budget = portfolio.get("per_stock_budget", 10_000)

    df    = generate_signals(df)
    today = datetime.today().strftime("%Y-%m-%d")

    # 統一價格：買入和顯示用同一來源
    price, _ = get_latest_close(ticker)

    # ── 決定訊號 ─────────────────────────────────────────────────────────────
    if action == "auto":
        last_row  = df.iloc[-1]
        last_date = str(df.index[-1])[:10]
        if should_buy(last_row):
            signal = 1
            reason = str(last_row.get("signal_reason", "訊號觸發")) + f"（訊號日：{last_date}）"
        else:
            recent = list(df.iloc[-3:].to_dict("records")) if len(df) >= 3 else list(df.to_dict("records"))
            triggered, sell_reason = should_sell(recent)
            if not triggered:
                return "none", f"{ticker} 今日無訊號"
            signal = -1
            reason = sell_reason
    elif action == "buy":
        signal = 1
        reason = f"手動買入（{price:.2f}）"
    elif action == "sell":
        signal = -1
        reason = f"手動賣出（{price:.2f}）"
    else:
        return "error", f"未知操作：{action}"

    # ── 買入 ──────────────────────────────────────────────────────────────────
    if signal == 1:
        if ticker in portfolio.get("positions", {}):
            return "skip", f"已持有 {ticker}"
        if portfolio["cash"] < per_stock_budget:
            return "skip", f"資金不足（{portfolio['cash']:,.0f} < {per_stock_budget:,.0f}）"
        shares = _calc_shares(per_stock_budget, price)
        if shares <= 0:
            return "skip", f"{ticker} 股價 {price:.2f} 超出預算"
        fee = shares * price * COMMISSION
        portfolio["cash"] = round(portfolio["cash"] - shares * price - fee, 2)
        portfolio.setdefault("positions", {})[ticker] = {
            "shares":       shares,
            "avg_cost":     round(price, 2),
            "bought_at":    today,
            "entry_reason": reason,
            "name":         name or ticker,
            "limit_sell":   round(price * (1 + tp_pct), 2),
            "stop_loss":    round(price * (1 - sl_pct), 2),
            "fee_paid":     round(fee, 2),
        }
        portfolio["last_updated"] = datetime.today().strftime("%Y-%m-%d %H:%M")
        db.save_portfolio(portfolio)
        db.append_trade(_rec(today, ticker, name or ticker, "buy", shares, price, fee, reason))
        return "buy", f"買入 {ticker} {shares} 股 @ {price:.2f}（含費 {shares*price+fee:,.0f} 元）"

    # ── 賣出 ──────────────────────────────────────────────────────────────────
    if signal == -1:
        pos = portfolio.get("positions", {}).get(ticker)
        if not pos:
            return "none", f"未持有 {ticker}"
        shares   = pos["shares"]
        fee      = shares * price * (COMMISSION + TAX)
        proceeds = shares * price - fee
        pnl      = proceeds - shares * pos["avg_cost"] - pos.get("fee_paid", 0)
        pnl_pct  = pnl / (shares * pos["avg_cost"]) * 100
        portfolio["cash"] = round(portfolio["cash"] + proceeds, 2)
        del portfolio["positions"][ticker]
        portfolio["last_updated"] = datetime.today().strftime("%Y-%m-%d %H:%M")
        db.save_portfolio(portfolio)
        db.append_trade(_rec(today, ticker, pos.get("name", ticker), "sell",
                             shares, price, fee, reason,
                             pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 2),
                             entry_price=pos["avg_cost"], entry_reason=pos.get("entry_reason", "")))
        label = "獲利" if pnl >= 0 else "虧損"
        return "sell", f"賣出 {ticker} {shares} 股 @ {price:.2f}，{label} {pnl:+.0f} 元 ({pnl_pct:+.1f}%)"

    return "none", f"{ticker} 無明確訊號"


# ── Morning scan ───────────────────────────────────────────────────────────────

def morning_scan(max_candidates: int = 100) -> dict:
    """
    批次掃描：先賣出持倉釋放資金，再用剩餘資金買入新訊號。
    兩個階段都並行抓資料，加速完成。
    """
    full_cfg = load_config()
    cfg    = full_cfg["strategy"]
    tp_pct = cfg.get("take_profit_pct", 15) / 100
    sl_pct = cfg.get("stop_loss_pct",    7) / 100
    ai_buy_min  = cfg.get("ai_min_confidence_buy", 50)
    ai_sell_min = cfg.get("ai_min_confidence_sell", 60)
    ai_enabled  = full_cfg.get("settings", {}).get("auto_scan_with_ai", True)
    ai_results  = db.get_stock_ai_results_for_date(last_trading_day_str()) if ai_enabled else {}

    portfolio = db.load_portfolio()
    if not portfolio:
        return {"error": "請先初始化自動交易"}

    per_stock_budget = portfolio.get("per_stock_budget", 10_000)
    today  = datetime.today().strftime("%Y-%m-%d")
    bought, sold, errors = [], [], []

    try:
        _, last_trading_day = get_latest_close("2330")
    except Exception:
        last_trading_day = None

    # ── 1. 並行抓取所有持倉的最新資料 ──────────────────────────────────────────
    positions_snapshot = dict(portfolio.get("positions", {}))

    def _fetch_pos(ticker):
        try:
            df = get_stock_history(ticker, 90)
            if df.empty:
                return ticker, None, None
            df = calculate_indicators(df)
            df = generate_signals(df)
            price, _ = get_latest_close(ticker)
            return ticker, df, price
        except Exception as e:
            return ticker, None, str(e)

    pos_data: dict = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for ticker, df, price_or_err in ex.map(_fetch_pos, positions_snapshot.keys()):
            if isinstance(price_or_err, str):
                errors.append(f"{ticker}(持倉): {price_or_err}")
            elif df is not None:
                pos_data[ticker] = (df, price_or_err)

    # ── 2. 先執行賣出（停利 / 停損 / 賣訊），釋放資金 ─────────────────────────
    position_watch = []
    for ticker, pos in list(positions_snapshot.items()):
        if ticker not in pos_data:
            continue
        df, price = pos_data[ticker]
        recent = list(df.iloc[-3:].to_dict("records")) if len(df) >= 3 else list(df.to_dict("records"))
        ai = ai_results.get(ticker)
        ai_ok = bool(ai) and not ai.get("error")

        exit_price, exit_reason = check_exit(pos, price, recent)

        if not exit_price and ai_ok:
            if ai.get("verdict") == "偏空" and (ai.get("confidence") or 0) >= ai_sell_min:
                exit_price = price
                exit_reason = f"AI研判偏空（信心{ai.get('confidence')}%）：{(ai.get('summary') or '')[:40]}"

        if exit_price and not ai_ok:
            # 尚無有效 AI 判斷，風控訊號暫緩執行，待下次掃描有 AI 結果再賣出
            errors.append(f"{ticker}: 觸發{exit_reason}，但尚無有效AI判斷，暫不賣出")
            exit_price, exit_reason = None, None

        if exit_price:
            if db.sold_today(ticker):
                continue
            shares   = pos["shares"]
            fee      = shares * exit_price * (COMMISSION + TAX)
            proceeds = shares * exit_price - fee
            pnl      = proceeds - shares * pos["avg_cost"] - pos.get("fee_paid", 0)
            pnl_pct  = pnl / (shares * pos["avg_cost"]) * 100
            portfolio["cash"] = round(portfolio["cash"] + proceeds, 2)
            del portfolio["positions"][ticker]
            portfolio["last_updated"] = today
            db.save_portfolio(portfolio)
            rec = _rec(today, ticker, pos.get("name", ticker), "sell",
                       shares, exit_price, fee, exit_reason,
                       pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 2),
                       entry_price=pos["avg_cost"], entry_reason=pos.get("entry_reason", ""))
            sold.append(rec)
            db.append_trade(rec)
        else:
            position_watch.append({
                "ticker":         ticker,
                "name":           pos.get("name", ticker),
                "shares":         pos["shares"],
                "avg_cost":       pos["avg_cost"],
                "current_price":  round(price, 2),
                "unrealized_pct": round((price - pos["avg_cost"]) / pos["avg_cost"] * 100, 2),
                "limit_sell":     pos.get("limit_sell", round(pos["avg_cost"] * (1 + tp_pct), 2)),
                "stop_loss":      pos.get("stop_loss",  round(pos["avg_cost"] * (1 - sl_pct), 2)),
                "bought_at":      pos.get("bought_at", ""),
            })

    # ── 3. 賣出完畢後，並行抓取買入候選資料（現金已更新）────────────────────────
    stocks = get_top100_stocks()
    current_held = set(portfolio.get("positions", {}).keys())
    # 多抓 2x 候選以防資料失效，但只算前 max_candidates 支已成功抓到的
    fetch_pool = [s for s in stocks if s["ticker"] not in current_held][:max_candidates * 2]

    def _fetch_cand(s):
        ticker = s["ticker"]
        try:
            df = get_stock_history(ticker, 90)
            if df.empty or len(df) < 20:
                return ticker, None, None, s.get("name", ticker)
            df = calculate_indicators(df)
            df = generate_signals(df)
            price, _ = get_latest_close(ticker)
            return ticker, df, price, s.get("name", ticker)
        except Exception as e:
            return ticker, None, str(e), s.get("name", ticker)

    cand_data: dict = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for ticker, df, price_or_err, name in ex.map(_fetch_cand, fetch_pool):
            if isinstance(price_or_err, str):
                errors.append(f"{ticker}: {price_or_err}")
            elif df is not None:
                cand_data[ticker] = (df, price_or_err, name)

    # ── 4. 依成交量排名順序決定買入（現金不足就停止）───────────────────────────
    scanned = 0
    for s in stocks:
        if scanned >= max_candidates or portfolio["cash"] < per_stock_budget:
            break
        ticker = s["ticker"]
        if ticker in portfolio.get("positions", {}):
            continue
        if ticker not in cand_data:
            # 已在 fetch_pool 且抓失敗才算 scanned，原本就不在候選清單就跳過
            if any(c["ticker"] == ticker for c in fetch_pool):
                scanned += 1
            continue

        df, price, name = cand_data[ticker]
        scanned += 1
        last_row = df.iloc[-1]

        if not should_buy(last_row):
            continue

        ai = ai_results.get(ticker)
        ai_ok = bool(ai) and not ai.get("error")
        if not ai_ok:
            errors.append(f"{ticker}: 尚無有效AI判斷，暫不買入")
            continue
        if ai.get("verdict") == "偏空" or (ai.get("confidence") or 0) < ai_buy_min:
            errors.append(f"{ticker}: AI過濾（{ai.get('verdict')}，信心{ai.get('confidence')}%），略過買入")
            continue

        sig_date = str(df.index[-1])[:10]
        if last_trading_day and sig_date != last_trading_day:
            errors.append(f"{ticker}: 訊號非最新交易日（{sig_date} ≠ {last_trading_day}），跳過")
            continue

        reason = str(last_row.get("signal_reason", "訊號觸發")) + f"（訊號日：{sig_date}）"
        shares = _calc_shares(per_stock_budget, price)
        if shares > 0:
            fee = shares * price * COMMISSION
            portfolio["cash"] = round(portfolio["cash"] - shares * price - fee, 2)
            portfolio.setdefault("positions", {})[ticker] = {
                "shares":       shares,
                "avg_cost":     round(price, 2),
                "bought_at":    today,
                "entry_reason": reason,
                "name":         name,
                "limit_sell":   round(price * (1 + tp_pct), 2),
                "stop_loss":    round(price * (1 - sl_pct), 2),
                "fee_paid":     round(fee, 2),
            }
            portfolio["last_updated"] = today
            db.save_portfolio(portfolio)
            rec = _rec(today, ticker, name, "buy", shares, price, fee, reason)
            bought.append(rec)
            db.append_trade(rec)

    portfolio["last_updated"] = today
    db.save_portfolio(portfolio)

    return {
        "scanned":             scanned,
        "buy_count":           len(bought),
        "sell_count":          len(sold),
        "available_slots":     int(portfolio["cash"] // per_stock_budget),
        "positions_monitored": len(position_watch),
        "bought":              bought,
        "sold":                sold,
        "position_watch":      position_watch,
        "errors":              errors[:5],
    }


# ── Portfolio summary ──────────────────────────────────────────────────────────

def auto_portfolio_summary() -> dict:
    portfolio = db.load_portfolio()
    if not portfolio:
        return {"initialized": False}

    positions_detail = []
    total_pos = 0.0
    price_errors = []
    today_str = datetime.today().strftime("%Y-%m-%d")

    # 並行抓所有持倉的最新收盤價
    def _fetch_price(item):
        ticker, pos = item
        try:
            price, price_date = get_latest_close(ticker)
            return ticker, price, price_date, None
        except ValueError as e:
            return ticker, None, None, str(e)

    positions_items = list(portfolio.get("positions", {}).items())
    price_map: dict = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for ticker, price, price_date, err in ex.map(_fetch_price, positions_items):
            price_map[ticker] = (price, price_date, err)

    for ticker, pos in positions_items:
        price, price_date, err = price_map[ticker]
        if err:
            price_errors.append({"ticker": ticker, "reason": err})
            positions_detail.append({
                "ticker": ticker, "name": pos.get("name", ticker),
                "shares": pos["shares"], "avg_cost": pos["avg_cost"],
                "price_error": True, "price_stale": False, "price_date": None,
                "current_price": None, "market_value": None,
                "pnl": None, "pnl_pct": None, "pnl_net": None, "pnl_net_pct": None,
                "limit_sell": pos.get("limit_sell", 0),
                "stop_loss": pos.get("stop_loss", 0),
                "distance_to_tp_pct": None, "distance_to_sl_pct": None,
                "bought_at": pos.get("bought_at", ""),
                "entry_reason": pos.get("entry_reason", ""),
            })
            continue

        shares  = pos["shares"]
        cost    = pos["avg_cost"]
        mktval  = shares * price
        total_pos += mktval

        buy_fee   = pos.get("fee_paid", 0)
        sell_fee  = shares * price * (COMMISSION + TAX)
        cost_base = cost * shares
        pnl       = (price - cost) * shares                  # 不含費
        pnl_pct   = pnl / cost_base * 100 if cost_base else 0
        pnl_net   = pnl - buy_fee - sell_fee                 # 含費（含假設賣出成本）
        pnl_net_pct = pnl_net / cost_base * 100 if cost_base else 0

        positions_detail.append({
            "ticker":             ticker,
            "name":               pos.get("name", ticker),
            "shares":             shares,
            "avg_cost":           cost,
            "price_error":        False,
            "price_stale":        price_date < today_str,
            "price_date":         price_date,
            "current_price":      round(price, 2),
            "market_value":       round(mktval, 2),
            "pnl":                round(pnl, 2),
            "pnl_pct":            round(pnl_pct, 2),
            "pnl_net":            round(pnl_net, 2),
            "pnl_net_pct":        round(pnl_net_pct, 2),
            "limit_sell":         pos.get("limit_sell", 0),
            "stop_loss":          pos.get("stop_loss", 0),
            "distance_to_tp_pct": round((pos.get("limit_sell", price) - price) / price * 100, 2) if price else 0,
            "distance_to_sl_pct": round((price - pos.get("stop_loss", price)) / price * 100, 2) if price else 0,
            "bought_at":          pos.get("bought_at", ""),
            "entry_reason":       pos.get("entry_reason", ""),
        })

    total   = portfolio["cash"] + total_pos
    initial = portfolio.get("initial_capital", total)
    orders  = db.load_orders()
    filled  = orders.get("filled", [])
    sells   = [t for t in filled if t.get("action") == "sell"]
    wins    = [t for t in sells if (t.get("pnl") or 0) > 0]

    return {
        "initialized":      True,
        "started_at":       portfolio.get("started_at", ""),
        "last_updated":     portfolio.get("last_updated", ""),
        "initial_capital":  initial,
        "per_stock_budget": portfolio.get("per_stock_budget", 10_000),
        "cash":             round(portfolio["cash"], 2),
        "position_value":   round(total_pos, 2),
        "total_value":      round(total, 2),
        "total_pnl":        round(total - initial, 2),
        "total_pnl_pct":    round((total - initial) / initial * 100, 2) if initial else 0,
        "positions":        positions_detail,
        "price_errors":     price_errors,
        "win_rate":         round(len(wins) / len(sells) * 100, 1) if sells else 0,
        "total_trades":     len(sells),
        "pending_count":    0,
    }


def get_equity_history() -> list:
    return db.load_history()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _calc_shares(budget: float, price: float) -> int:
    """在預算內計算能買幾股（支援零股，≥1000股自動換算為整張）。"""
    raw = int(budget / (price * (1 + COMMISSION)))
    if raw >= 1000:
        lots = int(budget / (price * 1000 * (1 + COMMISSION)))
        if lots > 0:
            return lots * 1000
    return raw


def _rec(date, ticker, name, action, shares, price, fee, reason, **extra) -> dict:
    rec = {
        "date":   date, "ticker": ticker, "name": name,
        "action": action, "shares": shares,
        "price":  round(price, 2),
        "amount": round(shares * price, 2),
        "fee":    round(fee, 2),
        "reason": reason,
    }
    rec.update(extra)
    return rec
