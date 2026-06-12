# 台股分析系統

以技術指標 + 規則式策略為核心的台股分析與模擬交易系統。提供個股技術/基本面分析、單股與全組合歷史回測、今日訊號掃描，以及全自動的模擬交易（紙上交易）。

> ⚠️ 本系統為學術研究用途，所有訊號與回測結果僅供參考，不構成投資建議。投資有風險，入市需謹慎。

## 功能

- **個股分析**：技術指標（RSI、MACD、KD、布林通道、SMA 等共 15 種）+ 基本面（P/E、P/B、ROE、殖利率）+ 相關新聞搜尋
- **今日訊號掃描**：掃描追蹤股票池，找出今天觸發買進/賣出訊號的股票
- **單股回測**：用歷史資料模擬單一股票的買賣訊號表現
- **全組合回測**：將自動交易策略套用到過去歷史，逐交易日模擬最多 N 支股票的整體績效（總報酬、最大回撤、勝率、夏普比率）
- **自動交易（模擬）**：依據訊號規則自動買進/賣出、停損停利，所有持倉與交易紀錄存於 PostgreSQL，重啟不丟失

更完整的資料流說明可參考系統內建的[系統架構圖](web/system_map.html)（`/stock/system_map.html`）。

## 架構

五個容器透過 `docker-compose.yml` 啟動：

| 服務 | 說明 | 對外連接埠 |
| --- | --- | --- |
| `web` | PHP 8.3 + Nginx，提供前端頁面並把 `/api/` 反向代理到 `api` | 8080 |
| `api` | Python FastAPI 後端，負責抓資料、計算指標、產生訊號、回測、自動交易 | （僅內部，由 `web` 代理） |
| `db` | PostgreSQL 15，儲存自動交易的投資組合、持倉、交易紀錄、資產曲線 | （僅內部） |
| `searxng` | 自架 SearXNG，供 `api` 搜尋個股相關新聞，免 API key | （僅內部） |
| `adminer` | PostgreSQL 管理介面 | 8082 |

### 技術棧

- **前端**：PHP（單頁 `index.php`）+ 原生 JavaScript（`web/static/js/app.js`）+ Chart.js
- **後端**：Python 3.11 / FastAPI / pandas / `ta`
- **資料來源**：`twstock`（主）、`yfinance`（備援與基本面）、TWSE OpenAPI（股票清單、P/E、P/B、殖利率）、SearXNG（個股相關新聞）
- **資料庫**：PostgreSQL（`psycopg2`）

### 目錄結構

```
api/
  Dockerfile
  requirements.txt
  config/settings.example.json   # 設定範例（實際設定存於 config/settings.json，不進版控）
  backend/
    main.py                      # FastAPI 入口與所有路由
    config.py                    # 讀寫 settings.json（策略參數、快取設定）
    utils.py                     # 台股交易日曆 / 時區
    data/fetcher.py              # 股價、基本面抓取與快取
    data/news.py                 # 個股相關新聞搜尋（透過 SearXNG，免 API key）
    analysis/technical.py        # 技術指標計算
    strategy/signals.py          # 買賣訊號、單股回測、手續費常數
    strategy/scanner.py          # 今日訊號掃描
    strategy/auto_trade.py       # 自動交易（模擬）引擎
    strategy/full_backtest.py    # 全組合歷史回測
    db/portfolio_db.py           # PostgreSQL 存取層
    db/schema.sql                # 資料庫表結構

web/
  Dockerfile
  docker/nginx.conf, supervisord.conf
  index.php                      # 前端頁面
  system_map.html                # 互動式系統架構圖
  static/css/style.css
  static/js/app.js

searxng/
  settings.yml                   # SearXNG 設定（啟用 JSON API，供 api 內部呼叫）

docker-compose.yml
deploy.sh                        # 重建並啟動所有容器（含清除殭屍容器）
```

## 開始使用

1. 在專案根目錄建立 `.env`（PostgreSQL 連線資訊）：

   ```env
   DB_NAME=stockdb
   DB_USER=stockuser
   DB_PASSWORD=<your-password>
   ```

2. （選用）複製 `api/config/settings.example.json` 為 `api/config/settings.json` 並調整策略參數，否則系統會在首次啟動時自動建立預設設定。

3. 啟動所有服務：

   ```bash
   ./deploy.sh
   ```

   或不使用腳本：

   ```bash
   docker-compose up -d --build
   ```

4. 開啟瀏覽器前往 `http://localhost:8080/`。

## 設定

策略參數（停損/停利百分比、RSI 門檻、均線週期、初始模擬資金等）可在前端「策略設定」頁面修改，會寫入 `api/config/settings.json`（`strategy` 區塊）。`settings` 區塊目前僅有 `cache_hours`（股價/基本面快取時數，預設 6 小時）。

## 主要 API

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/api/top100` | 取得追蹤股票清單 |
| GET | `/api/stock/{ticker}` | 個股技術 + 基本面分析 |
| GET | `/api/stock/{ticker}/news` | 個股相關新聞搜尋（透過 SearXNG，快取 30 分鐘） |
| POST | `/api/backtest/{ticker}` | 單股歷史回測 |
| GET / POST | `/api/scan/today` | 今日訊號掃描（讀取快取 / 重新掃描） |
| GET | `/api/auto/status` | 自動交易投資組合狀態 |
| POST | `/api/auto/init` | 初始化自動交易投資組合 |
| POST | `/api/auto/trade` | 執行單筆自動交易（買/賣/自動判斷） |
| POST | `/api/auto/scan` | 掃描並對候選股票下單 |
| POST | `/api/auto/cancel/{ticker}` | 撤銷持倉 |
| GET | `/api/auto/orders` | 今日委託紀錄 |
| GET | `/api/auto/history` | 資產曲線歷史 |
| POST | `/api/full-backtest` | 全組合歷史回測 |
| GET / PUT | `/api/config` | 讀取 / 更新策略設定 |

## 手續費假設

- 買進：0.1425% 手續費
- 賣出：0.1425% 手續費 + 0.3% 證券交易稅
