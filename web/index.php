<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>台股 AI 分析系統</title>
  <link rel="stylesheet" href="/stock/static/css/style.css">
</head>
<body>
<div class="layout">

  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-header">
      <h1>📈 台股 AI 分析</h1>
      <p>技術面 · 基本面 · 回測 · AI 建議</p>
    </div>

    <nav class="nav-section">
      <div class="nav-label">導航</div>
      <button class="nav-item" data-page="welcome" onclick="showPage('welcome')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
        首頁
      </button>
      <button class="nav-item" data-page="chat" onclick="showChatPage()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
        </svg>
        問股票
      </button>
      <button class="nav-item" data-page="settings" onclick="showSettings()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
        </svg>
        策略設定
      </button>
      <button class="nav-item" data-page="scan" onclick="showScanPage()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          <line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/>
        </svg>
        今日訊號掃描
      </button>
      <button class="nav-item" data-page="auto" onclick="showAutoPage()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        自動交易系統
      </button>
      <button class="nav-item" data-page="full-backtest" onclick="showFullBacktestPage()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
        策略歷史驗證
      </button>
      <button class="nav-item" onclick="loadStockList()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>
        </svg>
        重新整理股票列表
      </button>
      <a class="nav-item" href="/stock/system_map.html" target="_blank" style="text-decoration:none;display:flex;align-items:center;gap:8px">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
          <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
        </svg>
        系統架構圖
      </a>
    </nav>

    <div class="search-box">
      <input type="text" id="search" placeholder="搜尋代號或名稱..." autocomplete="off">
    </div>

    <div class="stock-list" id="stock-list">
      <div class="loading"><div class="spinner"></div></div>
    </div>
  </aside>

  <!-- Main content -->
  <main class="main">


    <!-- Welcome page -->
    <div id="page-welcome">
      <div class="welcome">
        <div style="font-size:64px;margin-bottom:16px">📊</div>
        <h2>台股 AI 分析系統</h2>
        <p>從左側選擇股票，取得技術分析、基本面數據、歷史回測與 AI 進出場建議。</p>
        <div style="margin-top:24px;display:flex;gap:12px;flex-wrap:wrap;justify-content:center">
          <div class="card" style="padding:16px 20px;text-align:left;min-width:160px">
            <div style="font-size:24px">🔍</div>
            <div style="font-weight:600;margin-top:8px">技術分析</div>
            <div style="color:var(--text-muted);font-size:12px;margin-top:4px">RSI · MACD · KD · 布林通道</div>
          </div>
          <div class="card" style="padding:16px 20px;text-align:left;min-width:160px">
            <div style="font-size:24px">📋</div>
            <div style="font-weight:600;margin-top:8px">基本面</div>
            <div style="color:var(--text-muted);font-size:12px;margin-top:4px">P/E · P/B · ROE · 殖利率</div>
          </div>
          <div class="card" style="padding:16px 20px;text-align:left;min-width:160px">
            <div style="font-size:24px">🧪</div>
            <div style="font-weight:600;margin-top:8px">歷史回測</div>
            <div style="color:var(--text-muted);font-size:12px;margin-top:4px">勝率 · 夏普比率 · 模擬損益</div>
          </div>
          <div class="card" style="padding:16px 20px;text-align:left;min-width:160px">
            <div style="font-size:24px">🤖</div>
            <div style="font-weight:600;margin-top:8px">AI 建議</div>
            <div style="color:var(--text-muted);font-size:12px;margin-top:4px">進出場價位 · 風險評估</div>
          </div>
        </div>
        <p style="margin-top:24px;font-size:12px;color:var(--text-muted)">
          ⚠️ 本系統為學術研究用途，所有建議僅供參考，不構成投資建議。投資有風險，入市需謹慎。
        </p>
      </div>

      <div class="card" style="margin-top:20px">
        <div class="card-header">
          <div class="card-title">📅 系統執行狀況</div>
          <div style="font-size:11px;color:var(--text-muted)">最近 30 天 · 每小時自動檢查</div>
        </div>
        <div id="run-log-list">
          <div class="loading"><div class="spinner"></div></div>
        </div>
      </div>
    </div>

    <!-- Chat page -->
    <div id="page-chat" style="display:none">
      <div class="card" style="display:flex;flex-direction:column;height:calc(100vh - 96px);padding:0;overflow:hidden">
        <div class="card-header" style="padding:16px 20px;flex-shrink:0">
          <div class="card-title">💬 問股票</div>
          <button class="btn btn-outline" style="font-size:11px" onclick="clearChat()">清空對話</button>
        </div>
        <div id="chat-messages" class="chat-messages"></div>
        <div class="chat-input-row">
          <textarea id="chat-input" class="form-control" rows="1" placeholder="輸入問題，例如：台積電最近怎麼樣？"
            onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChatMessage();}"></textarea>
          <button class="btn btn-primary" onclick="sendChatMessage()">送出</button>
        </div>
      </div>
    </div>

    <!-- Full backtest page -->
    <div id="page-full-backtest" style="display:none">
      <div id="fb-content">
        <div class="loading"><div class="spinner"></div></div>
      </div>
    </div>

    <!-- Scan page -->
    <div id="page-scan" style="display:none">
      <div id="scan-content">
        <div class="loading"><div class="spinner"></div></div>
      </div>
    </div>

    <!-- Auto trading page -->
    <div id="page-auto" style="display:none">
      <div id="auto-page-content">
        <div class="loading"><div class="spinner"></div></div>
      </div>
    </div>

    <!-- Analysis page -->
    <div id="page-analysis" style="display:none">
      <div id="analysis-content">
        <div class="loading"><div class="spinner"></div></div>
      </div>
    </div>

    <!-- Settings page -->
    <div id="page-settings" style="display:none">
      <div class="card">
        <div class="card-header"><div class="card-title">📊 策略參數</div></div>
        <div class="form-row">
          <div class="form-group">
            <label>初始模擬資金 (NTD)</label>
            <input type="number" id="initial-capital" class="form-control" value="100000">
          </div>
          <div class="form-group">
            <label>每筆最高金額 (NTD，0 = 不限制)</label>
            <input type="number" id="max-per-trade" class="form-control" value="0" min="0" placeholder="0 = 不限制（用95%資金）">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>停損 (%)</label>
            <input type="number" id="stop-loss" class="form-control" value="7" step="0.5">
          </div>
          <div class="form-group">
            <label>停利 (%)</label>
            <input type="number" id="take-profit" class="form-control" value="15" step="0.5">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>RSI 超賣值</label>
            <input type="number" id="rsi-oversold" class="form-control" value="30">
          </div>
          <div class="form-group">
            <label>RSI 超買值</label>
            <input type="number" id="rsi-overbought" class="form-control" value="70">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>短期均線 (日)</label>
            <input type="number" id="ma-short" class="form-control" value="20">
          </div>
          <div class="form-group">
            <label>長期均線 (日)</label>
            <input type="number" id="ma-long" class="form-control" value="60">
          </div>
        </div>
        <div style="margin-top:8px">
          <button class="btn btn-primary" onclick="saveSettings()">💾 儲存設定</button>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><div class="card-title">🤖 AI 分析設定</div></div>
        <div class="form-row">
          <div class="form-group">
            <label>Ollama 模型名稱</label>
            <input type="text" id="llm-model" class="form-control" value="qwen2.5:7b" placeholder="例如 qwen2.5:7b、llama3.1:8b">
          </div>
          <div class="form-group">
            <label>Ollama 服務位址</label>
            <input type="text" id="ollama-url" class="form-control" value="http://host.docker.internal:11434">
          </div>
        </div>
        <p style="font-size:11px;color:var(--text-muted)">
          模型需先在 Ollama 中 pull 完成（例如 <code>docker exec ollama ollama pull qwen2.5:7b</code>）才能使用。
        </p>
        <div class="form-group" style="margin-top:8px">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
            <input type="checkbox" id="auto-scan-with-ai" style="width:14px;height:14px">
            每日對前150大成交量股票進行完整 AI 分析，並套用於自動交易
          </label>
          <p style="font-size:11px;color:var(--text-muted);margin-top:4px">
            偵測到新交易日時，對前 150 大成交量股票逐一執行完整 AI 分析（最多 10 輪延伸搜尋），
            結果存入資料庫供今日訊號掃描顯示，並供自動交易系統過濾買入/觸發提早賣出（可能需數十分鐘至數小時）。
          </p>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>AI 買入信心門檻 (%)</label>
            <input type="number" id="ai-min-confidence-buy" class="form-control" value="50" min="0" max="100" step="5">
            <p style="font-size:11px;color:var(--text-muted);margin-top:4px">
              買入訊號股票的 AI 信心低於此值，或 AI 判斷為「偏空」時，自動交易會略過該買入。
            </p>
          </div>
          <div class="form-group">
            <label>AI 提早賣出信心門檻 (%)</label>
            <input type="number" id="ai-min-confidence-sell" class="form-control" value="60" min="0" max="100" step="5">
            <p style="font-size:11px;color:var(--text-muted);margin-top:4px">
              持倉股票的 AI 判斷為「偏空」且信心 ≥ 此值時，自動交易會提早賣出（即使尚未觸發停損停利）。
            </p>
          </div>
        </div>
        <div style="margin-top:8px">
          <button class="btn btn-primary" onclick="saveSettings()">💾 儲存設定</button>
        </div>
      </div>
    </div>

  </main>
</div>

<!-- Toast notification -->
<div id="toast" class="toast"></div>

<!-- JS dependencies -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
<!-- core.js 最先載入（全域狀態、showPage/switchTab、共用小工具）；
     ai-analysis.js 排在 chat.js / scan.js 之前，因為它們重用 renderStepBody -->
<script src="/stock/static/js/core.js"></script>
<script src="/stock/static/js/pages/home.js"></script>
<script src="/stock/static/js/pages/stock-detail.js"></script>
<script src="/stock/static/js/pages/ai-analysis.js"></script>
<script src="/stock/static/js/pages/backtest.js"></script>
<script src="/stock/static/js/pages/simulation.js"></script>
<script src="/stock/static/js/pages/settings.js"></script>
<script src="/stock/static/js/pages/full-backtest.js"></script>
<script src="/stock/static/js/pages/scan.js"></script>
<script src="/stock/static/js/pages/auto-trade.js"></script>
<script src="/stock/static/js/pages/chat.js"></script>
</body>
</html>
