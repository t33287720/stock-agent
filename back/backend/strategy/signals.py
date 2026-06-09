"""
Signal generation and backtesting.

Taiwan fee rates (also exported for use by simulation.py and auto_trade.py):
  Buy:  0.1425% commission
  Sell: 0.1425% commission + 0.3% securities transaction tax
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import load_config

# Taiwan stock fee constants — imported by auto_trade.py and full_backtest.py
COMMISSION = 0.001425   # 0.1425%  — applies both sides
TAX = 0.003             # 0.3%     — sell only (securities transaction tax)


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_date: str
    entry_price: float
    entry_reason: str = ""
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    shares: int = 0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fee_paid: float = 0.0


@dataclass
class BacktestResult:
    ticker: str
    with_fee: bool
    total_return_pct: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    sharpe_ratio: float
    initial_capital: float
    final_capital: float
    total_fee_paid: float
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)


# ── Signal generation ──────────────────────────────────────────────────────────

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add 'signal' (1/−1/0) and 'signal_reason' columns to the DataFrame.

    Buy triggers (any of):
      • MACD 黃金交叉  (MACD 上穿 Signal) + RSI 低檔 或 多頭排列
      • KD  黃金交叉  (K 上穿 D, K < 40)
      • 均線黃金交叉  (SMA短 上穿 SMA長)

    Sell triggers (any of):
      • MACD 死亡交叉 + RSI 高檔 或 空頭排列
      • KD  死亡交叉  (K 下穿 D, K > 60)
      • 均線死亡交叉  (SMA短 下穿 SMA長)
      • RSI 超買     (RSI > overbought)
    """
    cfg = load_config()["strategy"]
    rsi_low  = cfg.get("rsi_oversold",  30)
    rsi_high = cfg.get("rsi_overbought", 70)
    ma_short_col = f"SMA_{cfg.get('ma_short', 20)}"
    ma_long_col  = f"SMA_{cfg.get('ma_long',  60)}"

    df = df.copy()
    df["signal"] = 0
    df["signal_reason"] = ""

    if "RSI" not in df.columns or "MACD" not in df.columns:
        return df

    rsi      = df["RSI"]
    macd     = df["MACD"]
    macd_sig = df["MACD_signal"]
    k        = df.get("K", pd.Series(np.nan, index=df.index))
    d        = df.get("D", pd.Series(np.nan, index=df.index))
    sma_s    = df.get(ma_short_col, pd.Series(np.nan, index=df.index))
    sma_l    = df.get(ma_long_col,  pd.Series(np.nan, index=df.index))

    # ── Crossover detection ──────────────────────────────────────────
    macd_cross_up = (macd > macd_sig) & (macd.shift(1) <= macd_sig.shift(1))
    macd_cross_dn = (macd < macd_sig) & (macd.shift(1) >= macd_sig.shift(1))

    kd_golden = (k > d) & (k.shift(1) <= d.shift(1))   # K 上穿 D
    kd_death  = (k < d) & (k.shift(1) >= d.shift(1))   # K 下穿 D

    sma_golden = (sma_s > sma_l) & (sma_s.shift(1) <= sma_l.shift(1))
    sma_death  = (sma_s < sma_l) & (sma_s.shift(1) >= sma_l.shift(1))

    # ── State flags ──────────────────────────────────────────────────
    in_uptrend = sma_s > sma_l
    rsi_low_z  = rsi < (rsi_low  + 15)
    rsi_high_z = rsi > (rsi_high -  5)

    # ── Combined conditions ──────────────────────────────────────────
    buy_cond = (
        (macd_cross_up & (rsi_low_z | in_uptrend)) |   # MACD + RSI/trend
        (kd_golden     & (k < 40))                  |   # KD 黃金交叉 (低檔)
        sma_golden                                       # 均線黃金交叉
    )
    sell_cond = (
        (macd_cross_dn & (rsi_high_z | ~in_uptrend)) |  # MACD + RSI/trend
        (kd_death      & (k > 60))                   |  # KD 死亡交叉 (高檔)
        sma_death                                    |  # 均線死亡交叉
        (rsi > rsi_high)                                 # RSI 超買
    )

    df.loc[buy_cond,  "signal"] = 1
    df.loc[sell_cond & (df["signal"] == 0), "signal"] = -1

    # ── Build reason strings ─────────────────────────────────────────
    reasons = []
    for i in range(len(df)):
        sig   = int(df["signal"].iloc[i])
        rsi_v = float(rsi.iloc[i]) if not pd.isna(rsi.iloc[i]) else 50.0
        k_v   = float(k.iloc[i])   if not pd.isna(k.iloc[i])   else 50.0

        if sig == 1:
            parts = []
            if macd_cross_up.iloc[i]:
                parts.append("MACD黃金交叉")
            if kd_golden.iloc[i] and k_v < 40:
                parts.append(f"KD黃金交叉(K={k_v:.0f})")
            if sma_golden.iloc[i]:
                parts.append("均線黃金交叉")
            if rsi_v < rsi_low + 15:
                parts.append(f"RSI低檔({rsi_v:.0f})")
            if bool(in_uptrend.iloc[i]):
                parts.append("多頭排列")
            reasons.append("買入：" + "、".join(parts) if parts else "買入訊號")

        elif sig == -1:
            parts = []
            if macd_cross_dn.iloc[i]:
                parts.append("MACD死亡交叉")
            if kd_death.iloc[i] and k_v > 60:
                parts.append(f"KD死亡交叉(K={k_v:.0f})")
            if sma_death.iloc[i]:
                parts.append("均線死亡交叉")
            if rsi_v > rsi_high - 5:
                parts.append(f"RSI高檔({rsi_v:.0f})")
            if not bool(in_uptrend.iloc[i]):
                parts.append("空頭排列")
            reasons.append("賣出：" + "、".join(parts) if parts else "賣出訊號")

        else:
            reasons.append("")

    df["signal_reason"] = reasons
    return df


# ── Backtest ───────────────────────────────────────────────────────────────────

def run_backtest(ticker: str, df: pd.DataFrame, with_fee: bool = True) -> BacktestResult:
    """
    Historical simulation with optional Taiwan fee deduction.
    Buy: max lots from capital (falls back to odd-lot when capital < 1 lot).
    """
    cfg = load_config()["strategy"]
    initial_capital = float(cfg.get("initial_capital", 1_000_000))
    stop_loss_pct   = cfg.get("stop_loss_pct",    7) / 100
    take_profit_pct = cfg.get("take_profit_pct", 15) / 100

    comm = COMMISSION if with_fee else 0.0
    tax  = TAX        if with_fee else 0.0

    df = generate_signals(df)

    capital     = initial_capital
    position    = 0
    entry_price = 0.0
    entry_date  = ""
    entry_reason = ""
    trades: list[Trade] = []
    equity_curve = []
    total_fee    = 0.0

    for date, row in df.iterrows():
        price      = float(row["Close"])
        sig        = int(row.get("signal", 0))
        row_reason = str(row.get("signal_reason", ""))
        date_str   = str(date)[:10]

        # Stop-loss / take-profit check overrides the signal
        exit_reason = row_reason
        if position > 0:
            change = (price - entry_price) / entry_price
            if change <= -stop_loss_pct:
                sig = -1
                exit_reason = f"停損 ({change*100:.1f}%)"
            elif change >= take_profit_pct:
                sig = -1
                exit_reason = f"停利 (+{change*100:.1f}%)"

        if sig == -1 and position > 0:
            sell_fee   = position * price * (comm + tax)
            proceeds   = position * price - sell_fee
            cost_basis = position * entry_price
            buy_fee    = cost_basis * comm
            pnl        = proceeds - cost_basis - buy_fee
            pnl_pct    = pnl / cost_basis * 100
            total_fee += sell_fee + buy_fee
            capital   += proceeds
            trades.append(Trade(
                entry_date=entry_date, entry_price=entry_price, entry_reason=entry_reason,
                exit_date=date_str, exit_price=price, exit_reason=exit_reason,
                shares=position,
                pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 2),
                fee_paid=round(sell_fee + buy_fee, 2),
            ))
            position    = 0
            entry_price = 0.0

        elif sig == 1 and position == 0 and price > 0:
            budget     = capital * 0.95
            unit_cost  = price * (1 + comm)
            lot_shares = int(budget / (unit_cost * 1000)) * 1000
            shares     = lot_shares if lot_shares > 0 else int(budget / unit_cost)
            if shares > 0:
                buy_fee  = shares * price * comm
                capital -= shares * price + buy_fee
                position     = shares
                entry_price  = price
                entry_date   = date_str
                entry_reason = row_reason

        equity = capital + position * price
        equity_curve.append({"date": date_str, "equity": round(equity, 2)})

    # Close any open position at last price
    if position > 0:
        last_price    = float(df["Close"].iloc[-1])
        sell_fee      = position * last_price * (comm + tax)
        proceeds      = position * last_price - sell_fee
        cost_basis    = position * entry_price
        buy_fee_final = cost_basis * comm
        pnl           = proceeds - cost_basis - buy_fee_final
        pnl_pct       = pnl / cost_basis * 100
        total_fee    += sell_fee + buy_fee_final
        capital      += proceeds
        trades.append(Trade(
            entry_date=entry_date, entry_price=entry_price, entry_reason=entry_reason,
            exit_date=str(df.index[-1])[:10], exit_price=last_price,
            exit_reason="回測結束（持倉中）",
            shares=position,
            pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 2),
            fee_paid=round(sell_fee + buy_fee_final, 2),
        ))

    final_capital = capital
    total_return  = (final_capital - initial_capital) / initial_capital * 100
    winners       = [t for t in trades if t.pnl > 0]
    win_rate      = len(winners) / len(trades) * 100 if trades else 0.0

    return BacktestResult(
        ticker=ticker,
        with_fee=with_fee,
        total_return_pct=round(total_return, 2),
        max_drawdown_pct=round(_max_drawdown([e["equity"] for e in equity_curve]), 2),
        win_rate=round(win_rate, 2),
        total_trades=len(trades),
        winning_trades=len(winners),
        losing_trades=len(trades) - len(winners),
        sharpe_ratio=round(_sharpe_ratio([e["equity"] for e in equity_curve]), 3),
        initial_capital=initial_capital,
        final_capital=round(final_capital, 2),
        total_fee_paid=round(total_fee, 2),
        trades=[vars(t) for t in trades],
        equity_curve=equity_curve,
    )


# ── Shared hard-rule filters (used by scanner, auto_trade, full_backtest) ──────

def should_buy(row, rsi_threshold: float = 65) -> bool:
    """
    Hard buy rule: latest bar must have signal==1 AND RSI below threshold.
    All three systems (scanner, auto_trade, full_backtest) call this.
    """
    try:
        rsi = float(row.get("RSI", 50) or 50)
        rsi = 50.0 if rsi != rsi else rsi  # NaN → 50
    except (TypeError, ValueError):
        rsi = 50.0
    return int(row.get("signal", 0)) == 1 and rsi <= rsi_threshold


def should_sell(recent_rows: list) -> tuple[bool, str]:
    """
    Hard sell rule: most recent non-zero signal in the provided rows is -1.
    Returns (triggered, reason_string).
    All three systems (scanner, auto_trade, full_backtest) call this.
    """
    sig_rows = [r for r in recent_rows if int(r.get("signal", 0)) != 0]
    if sig_rows and int(sig_rows[-1].get("signal", 0)) == -1:
        return True, str(sig_rows[-1].get("signal_reason", "賣出訊號"))
    return False, ""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _max_drawdown(equity: list[float]) -> float:
    if len(equity) < 2:
        return 0.0
    eq   = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd   = (eq - peak) / (peak + 1e-9) * 100
    return float(abs(dd.min()))


def _sharpe_ratio(equity: list[float], risk_free: float = 0.02) -> float:
    if len(equity) < 2:
        return 0.0
    eq       = np.array(equity)
    returns  = np.diff(eq) / (eq[:-1] + 1e-9)
    daily_rf = risk_free / 252
    excess   = returns - daily_rf
    if excess.std() == 0:
        return 0.0
    return float(excess.mean() / excess.std() * np.sqrt(252))
