"""
Full portfolio backtest — simulates the auto-trading strategy over historical data.

Signal logic is identical to auto_trade and scanner (shared should_buy / should_sell):
  Buy:  today's bar should_buy() → buy at today's close
  Sell: today's bar should_sell() (last 3 bars) OR TP/SL triggered by today's High/Low

No look-ahead: indicators are pre-computed on all data, but the buy signal at bar D
uses D's close — same as auto_trade which also acts on the same-day close signal.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from backend.config import load_config
from backend.data.fetcher import get_stock_history, get_top100_stocks
from backend.analysis.technical import calculate_indicators
from backend.strategy.signals import (
    generate_signals, should_buy, should_sell, check_exit,
    COMMISSION, TAX, _max_drawdown, _sharpe_ratio,
)
from backend.utils import get_trading_days, row_for_date


async def run_full_portfolio_backtest(
    months: int = 12,
    initial_capital: float = 100_000,
    per_stock_budget: float = 10_000,
    max_candidates: int = 40,
) -> dict:
    return await asyncio.to_thread(
        _run_sync, months, initial_capital, per_stock_budget, max_candidates
    )


def _run_sync(
    months: int,
    initial_capital: float,
    per_stock_budget: float,
    max_candidates: int,
) -> dict:
    cfg    = load_config()["strategy"]
    tp_pct = cfg.get("take_profit_pct", 15) / 100
    sl_pct = cfg.get("stop_loss_pct",    7) / 100

    end_date   = datetime.today().date()
    start_date = (datetime.today() - timedelta(days=months * 31)).date()
    buffer     = 90   # extra days for indicator warmup before start_date

    trading_days = get_trading_days(start_date, end_date)
    if not trading_days:
        return {"error": "無有效交易日"}

    # ── 1. Pre-load & pre-compute indicators（並行下載加速）──────────────────
    stocks = get_top100_stocks()
    days_needed = months * 31 + buffer

    def _load(s):
        ticker = s["ticker"]
        try:
            df = get_stock_history(ticker, days_needed)
            if df.empty or len(df) < 60:
                return None
            df = calculate_indicators(df)
            df = generate_signals(df)
            return ticker, s.get("name", ticker), df
        except Exception:
            return None

    stock_data: dict[str, tuple[str, pd.DataFrame]] = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for result in ex.map(_load, stocks[:max_candidates * 2]):
            if result:
                ticker, name, df = result
                stock_data[ticker] = (name, df)

    # ── 2. Simulate ────────────────────────────────────────────────────────────
    cash        = float(initial_capital)
    positions   : dict = {}
    trades      : list = []
    equity_curve: list = []

    for day in trading_days:
        day_str = day.strftime("%Y-%m-%d")

        # ── EXIT: TP/SL first, then signal sell ────────────────────────────────
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            if ticker not in stock_data:
                continue
            _, df = stock_data[ticker]

            today = row_for_date(df, day)
            if today is None:
                continue

            day_low  = float(today["Low"])
            day_high = float(today["High"])
            close    = float(today["Close"])
            exit_p, exit_r = None, ""

            if day_low <= pos["stop_loss"]:
                exit_p = pos["stop_loss"]
                exit_r = f"觸發停損（≤ {pos['stop_loss']:.1f}）"
            elif day_high >= pos["limit_sell"]:
                exit_p = pos["limit_sell"]
                exit_r = f"觸發停利（≥ {pos['limit_sell']:.1f}）"
            else:
                # 訊號賣出：與 morning_scan 完全相同的 check_exit 邏輯
                # 取今日含前 2 天共最多 3 根做判斷
                idx = df.index.get_loc(today.name) if hasattr(today, 'name') else None
                recent_rows = (list(df.iloc[max(0, idx - 2): idx + 1].to_dict("records"))
                               if (idx is not None and idx >= 0) else [today.to_dict()])
                exit_p, exit_r = check_exit(pos, close, recent_rows)

            if exit_p:
                shares = pos["shares"]
                fee    = shares * exit_p * (COMMISSION + TAX)
                proc   = shares * exit_p - fee
                cost   = shares * pos["avg_cost"]
                pnl    = proc - cost - pos.get("fee_paid", 0)
                cash  += proc
                trades.append({
                    "date":         day_str,
                    "ticker":       ticker,
                    "name":         pos.get("name", ticker),
                    "action":       "sell",
                    "shares":       shares,
                    "price":        round(exit_p, 2),
                    "fee":          round(fee, 2),
                    "pnl":          round(pnl, 2),
                    "pnl_pct":      round(pnl / cost * 100, 2),
                    "reason":       exit_r,
                    "entry_price":  pos["avg_cost"],
                    "entry_date":   pos.get("bought_at", ""),
                    "entry_reason": pos.get("entry_reason", ""),
                })
                del positions[ticker]

        # ── BUY: 與 auto_trade 相同 — 當日收盤有 should_buy → 收盤買入 ────────
        if cash >= per_stock_budget:
            for ticker, (name, df) in stock_data.items():
                if cash < per_stock_budget:
                    break
                if ticker in positions:
                    continue

                today = row_for_date(df, day)
                if today is None:
                    continue

                # ── 與 scanner / auto_trade 相同的 should_buy 硬性規則 ─────────
                if not should_buy(today):
                    continue

                fill = float(today["Close"])
                if fill <= 0:
                    continue

                budget = per_stock_budget
                shares = int(budget / (fill * (1 + COMMISSION)))
                if shares <= 0 or cash < shares * fill:
                    continue

                fee   = shares * fill * COMMISSION
                cash -= shares * fill + fee
                positions[ticker] = {
                    "shares":       shares,
                    "avg_cost":     round(fill, 2),
                    "bought_at":    day_str,
                    "entry_reason": str(today.get("signal_reason", "")),
                    "name":         name,
                    "limit_sell":   round(fill * (1 + tp_pct), 2),
                    "stop_loss":    round(fill * (1 - sl_pct),  2),
                    "fee_paid":     round(fee, 2),
                }
                trades.append({
                    "date":    day_str,
                    "ticker":  ticker,
                    "name":    name,
                    "action":  "buy",
                    "shares":  shares,
                    "price":   round(fill, 2),
                    "fee":     round(fee, 2),
                    "reason":  str(today.get("signal_reason", "")),
                })

        # ── EQUITY snapshot ────────────────────────────────────────────────────
        pos_val = 0.0
        for ticker, pos in positions.items():
            if ticker in stock_data:
                _, df = stock_data[ticker]
                row = row_for_date(df, day)
                if row is not None:
                    pos_val += pos["shares"] * float(row["Close"])
                else:
                    pos_val += pos["shares"] * pos["avg_cost"]

        equity_curve.append({
            "date":           day_str,
            "equity":         round(cash + pos_val, 2),
            "cash":           round(cash, 2),
            "position_value": round(pos_val, 2),
            "open_positions": len(positions),
        })

    # ── Close remaining positions at last available price ──────────────────────
    for ticker, pos in list(positions.items()):
        if ticker not in stock_data:
            continue
        _, df = stock_data[ticker]
        if df.empty:
            continue
        price = float(df["Close"].iloc[-1])
        fee   = pos["shares"] * price * (COMMISSION + TAX)
        proc  = pos["shares"] * price - fee
        cost  = pos["shares"] * pos["avg_cost"]
        pnl   = proc - cost - pos.get("fee_paid", 0)
        cash += proc
        trades.append({
            "date":         end_date.strftime("%Y-%m-%d"),
            "ticker":       ticker,
            "name":         pos.get("name", ticker),
            "action":       "sell",
            "shares":       pos["shares"],
            "price":        round(price, 2),
            "fee":          round(fee, 2),
            "pnl":          round(pnl, 2),
            "pnl_pct":      round(pnl / cost * 100, 2),
            "reason":       "回測結束（強制平倉）",
            "entry_price":  pos["avg_cost"],
            "entry_date":   pos.get("bought_at", ""),
            "entry_reason": pos.get("entry_reason", ""),
        })

    # ── Metrics ────────────────────────────────────────────────────────────────
    sells     = [t for t in trades if t["action"] == "sell"]
    wins      = [t for t in sells if t.get("pnl", 0) > 0]
    eq        = [e["equity"] for e in equity_curve]
    total_fee = sum(t.get("fee", 0) for t in trades)
    total_pnl = sum(t.get("pnl", 0) for t in sells)

    return {
        "months":           months,
        "start_date":       start_date.strftime("%Y-%m-%d"),
        "end_date":         end_date.strftime("%Y-%m-%d"),
        "trading_days":     len(trading_days),
        "stocks_analyzed":  len(stock_data),
        "initial_capital":  initial_capital,
        "final_capital":    round(cash, 2),
        "total_return_pct": round((cash - initial_capital) / initial_capital * 100, 2),
        "total_pnl":        round(total_pnl, 2),
        "max_drawdown_pct": round(_max_drawdown(eq), 2),
        "sharpe_ratio":     round(_sharpe_ratio(eq), 3),
        "total_trades":     len(sells),
        "win_rate":         round(len(wins) / len(sells) * 100, 2) if sells else 0,
        "winning_trades":   len(wins),
        "losing_trades":    len(sells) - len(wins),
        "total_fee_paid":   round(total_fee, 2),
        "equity_curve":     equity_curve,
        "trades":           trades,
    }
