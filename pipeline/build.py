"""每天執行一次：補齊缺少的交易日股價 → 算指標 → 輸出 App 讀的 stocks-latest.json。

用法：
    python pipeline/build.py [資料夾]        # 預設 pipeline/data

資料夾裡的兩個檔案：
    history.csv.gz      最近 KEEP_DAYS 個交易日的全市場股價（本程式自己維護）
    stocks-latest.json  給 App 讀的每日快照

第一次執行（沒有 history.csv.gz）會自動往回補 KEEP_DAYS 個交易日，約需 10-20 分鐘；
之後每次只補上次到今天之間缺的日子。
"""
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import sources
from indicators import latest_indicators

KEEP_DAYS = 100          # 保留幾個交易日（MA60、MACD 需要至少 60 天以上）
TAIPEI = ZoneInfo("Asia/Taipei")


def fetch_day(day: date, is_today: bool) -> list[dict] | None:
    """抓某一天上市 + 上櫃的股價。休市或還沒公布回傳 None。"""
    twse = sources.twse_prices(day)
    if twse is None:
        return None
    tpex = sources.tpex_prices(day)
    if not tpex:
        if is_today:
            return None  # 上市已公布、上櫃還沒：等下一次排程再抓
        raise RuntimeError(f"{day} 上市有資料但上櫃抓不到，停止以免存到不完整的資料")
    return twse + tpex


def days_to_fetch(history: pd.DataFrame, today: date):
    """有歷史：從最後一天的隔天到今天；沒歷史：從今天往回（由呼叫端決定何時停）。"""
    if history.empty:
        day = today
        while day > today - timedelta(days=KEEP_DAYS * 2):
            yield day
            day -= timedelta(days=1)
    else:
        day = date.fromisoformat(history["date"].max()) + timedelta(days=1)
        while day <= today:
            yield day
            day += timedelta(days=1)


def update_history(history: pd.DataFrame, today: date) -> pd.DataFrame:
    new_rows, got_days = [], 0
    for day in days_to_fetch(history, today):
        if day.weekday() >= 5:
            continue
        rows = fetch_day(day, is_today=(day == today))
        print(f"  {day}：{'休市或尚未公布' if rows is None else f'{len(rows)} 支'}", flush=True)
        time.sleep(3)  # 證交所對短時間大量請求會暫時封鎖
        if rows is None:
            continue
        new_rows += rows
        got_days += 1
        if history.empty and got_days >= KEEP_DAYS:
            break

    if new_rows:
        history = pd.concat([history, pd.DataFrame(new_rows)], ignore_index=True)
    keep = sorted(history["date"].unique())[-KEEP_DAYS:]
    return history[history["date"].isin(keep)]


def add_valuation(snapshot: pd.DataFrame, day: date) -> tuple[pd.DataFrame, bool]:
    valuation = {**sources.twse_valuation(day), **sources.tpex_valuation(day)}
    for col in ("pe", "pb", "yield"):
        snapshot[col] = snapshot["code"].map(lambda c: valuation.get(c, {}).get(col))
    return snapshot, bool(valuation)


def main():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    history_file = data_dir / "history.csv.gz"

    history = (pd.read_csv(history_file, dtype={"code": str, "date": str})
               if history_file.exists() else pd.DataFrame())
    today = datetime.now(TAIPEI).date()

    print(f"[1/3] 補齊股價（目前有 {history['date'].nunique() if not history.empty else 0} 個交易日）")
    history = update_history(history, today)
    history.to_csv(history_file, index=False)
    latest_day = date.fromisoformat(history["date"].max())

    print(f"[2/3] 計算 {latest_day} 的技術指標")
    snapshot = latest_indicators(history)

    print("[3/3] 加上本益比 / 股價淨值比 / 殖利率")
    snapshot, has_valuation = add_valuation(snapshot, latest_day)

    columns = list(snapshot.columns)
    rows = snapshot.astype(object).where(snapshot.notna(), None).values.tolist()
    rows = [[round(v, 2) if isinstance(v, float) else v for v in r] for r in rows]
    output = {
        "date": latest_day.isoformat(),
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
        "trading_days": int(history["date"].nunique()),
        "has_valuation": has_valuation,
        "columns": columns,
        "rows": rows,
    }
    (data_dir / "stocks-latest.json").write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"完成：{latest_day}，{len(rows)} 支股票，估值資料{'有' if has_valuation else '尚未公布'}")


if __name__ == "__main__":
    main()
