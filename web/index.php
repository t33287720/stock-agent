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
            自動掃描時同步進行 AI 信心分析
          </label>
          <p style="font-size:11px;color:var(--text-muted);margin-top:4px">
            每小時自動掃描找到今日訊號時，是否同時呼叫 Ollama 產生信心評分與摘要（會增加掃描時間）。
          </p>
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
<script src="/stock/static/js/app.js"></script>
</body>
</html>
