/* =========================================================
   個股分析頁 — 圖表 / 訊號明細 / 基本面 / 新聞 分頁
   呼叫 API：GET /api/stock/{ticker}、GET /api/stock/{ticker}/news
   「回測」「模擬交易」「AI 分析」分頁邏輯分別在
   pages/backtest.js、pages/simulation.js、pages/ai-analysis.js。
   ========================================================= */

// ── Main stock analysis ───────────────────────────────────────────────────────
// 載入單一股票的完整分析資料（技術面＋基本面＋歷史K線）並切換到分析頁
async function loadStock(ticker) {
  currentTicker = ticker;
  document.querySelectorAll('.stock-item').forEach(el =>
    el.classList.toggle('active', el.dataset.ticker === ticker));
  showPage('analysis');
  document.getElementById('analysis-content').innerHTML =
    '<div class="loading"><div class="spinner"></div> 分析中...</div>';

  try {
    const r = await fetch(`${API}/api/stock/${ticker}?days=365`);
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    currentHistory = data.history;
    renderAnalysis(data);
  } catch (e) {
    document.getElementById('analysis-content').innerHTML =
      `<div class="loading">載入失敗：${e.message}</div>`;
  }
}

// 渲染個股分析頁面骨架（標題列、分頁籤、各分頁容器），並延遲繪製圖表
function renderAnalysis(data) {
  const { ticker, name, technical: t, fundamental: f, history } = data;
  const latest = history[history.length - 1] || {};
  const prev   = history[history.length - 2] || {};
  const change = latest.close && prev.close
    ? (((latest.close - prev.close) / prev.close) * 100).toFixed(2) : null;
  const changeClass = change > 0 ? 'positive' : change < 0 ? 'negative' : '';

  const lastSig    = history.filter(r => r.signal !== 0).slice(-1)[0];
  const latestDate = history.slice(-1)[0]?.date ?? '';
  const isToday    = lastSig?.date === latestDate;
  const sigBadge   = lastSig
    ? `<span class="badge badge-${lastSig.signal === 1 ? 'buy' : 'sell'}">
         ${lastSig.signal === 1 ? '買入訊號' : '賣出訊號'}
         <span style="font-weight:400;opacity:0.8"> ${lastSig.date}</span>
       </span>`
    : '<span class="badge badge-hold">觀望</span>';
  const sigReason  = lastSig?.signal_reason
    ? `<span style="font-size:11px;color:var(--text-muted);margin-left:6px">${lastSig.signal_reason}${isToday ? '' : ' ⚠ 非今日'}</span>` : '';

  document.getElementById('analysis-content').innerHTML = `
    <div class="topbar">
      <div class="stock-title">
        <div>
          <div class="ticker">${ticker} ${name}</div>
          <div style="display:flex;gap:8px;align-items:center;margin-top:4px;flex-wrap:wrap">
            ${sigBadge}${sigReason}
            ${f.sector ? `<span style="color:var(--text-muted);font-size:12px">${f.sector}</span>` : ''}
          </div>
        </div>
      </div>
      <div style="text-align:right">
        <div class="price-big ${changeClass}">NT$ ${latest.close?.toFixed(2) ?? '—'}</div>
        ${change !== null ? `<div class="${changeClass}" style="font-size:13px">${change > 0 ? '+' : ''}${change}%</div>` : ''}
      </div>
    </div>

    <div class="tabs" id="tabs">
      <div class="tab active" onclick="switchTab('chart')">📈 圖表</div>
      <div class="tab" onclick="switchTab('signals')">🔔 訊號明細</div>
      <div class="tab" onclick="switchTab('fundamental')">📋 基本面</div>
      <div class="tab" onclick="switchTab('backtest')">🧪 回測</div>
      <div class="tab" onclick="switchTab('simulation')">💰 模擬交易</div>
      <div class="tab" onclick="switchTab('ai')">🤖 AI 分析</div>
    </div>

    <div id="tab-chart">
      ${renderTechTab(t)}
      <div class="card">
        <div class="card-header">
          <div class="card-title">K 線圖 + 訊號</div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-outline" onclick="toggleIndicator('bb')">布林通道</button>
            <button class="btn btn-outline" onclick="toggleIndicator('sma')">均線</button>
          </div>
        </div>
        <div class="chart-container"><canvas id="price-chart"></canvas></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title">RSI (14)</div></div>
        <div class="chart-container"><canvas id="rsi-chart"></canvas></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title">MACD</div></div>
        <div class="chart-container"><canvas id="macd-chart"></canvas></div>
      </div>
    </div>

    <div id="tab-signals" style="display:none">
      ${renderSignalsTab(history)}
    </div>
    <div id="tab-fundamental" style="display:none">
      ${renderFundTab(f)}
    </div>
    <div id="tab-backtest" style="display:none">
      ${renderBtPlaceholder()}
    </div>
    <div id="tab-simulation" style="display:none">
      <div id="sim-content"><div class="loading" style="padding:40px 0;color:var(--text-muted)">載入模擬交易狀態...</div></div>
    </div>
    <div id="tab-ai" style="display:none">
      ${renderAiTabPlaceholder()}
    </div>
  `;

  setTimeout(() => renderCharts(history), 100);
}

// ── Technical indicators card ─────────────────────────────────────────────────
// 渲染技術指標卡片（RSI、MACD、KD、均線、布林通道等最新數值）
function renderTechTab(t) {
  const indicators = [
    { label: 'RSI (14)', tipKey: 'RSI',
      value: t.rsi?.toFixed(1),
      sub: t.rsi < 30 ? '超賣' : t.rsi > 70 ? '超買' : '中性',
      cls: t.rsi < 30 ? 'positive' : t.rsi > 70 ? 'negative' : '' },
    { label: 'MACD', tipKey: 'MACD',
      value: t.macd?.toFixed(3),
      sub: t.macd > t.macd_signal ? '多頭排列' : '空頭排列',
      cls: t.macd > t.macd_signal ? 'positive' : 'negative' },
    { label: 'K / D', tipKey: 'KD',
      value: `${t.k?.toFixed(1)} / ${t.d?.toFixed(1)}`,
      sub: t.k < 20 ? '超賣' : t.k > 80 ? '超買' : '中性' },
    { label: 'SMA 20', tipKey: 'SMA20', value: t.sma20?.toFixed(2), sub: '20日均線' },
    { label: 'SMA 60', tipKey: 'SMA60', value: t.sma60?.toFixed(2), sub: '60日均線' },
    { label: '均線狀態', tipKey: t.golden_cross ? '黃金交叉' : '死亡交叉',
      value: t.golden_cross ? '黃金交叉 ↑' : '死亡交叉 ↓', sub: '',
      cls: t.golden_cross ? 'positive' : 'negative' },
    { label: '布林上軌', tipKey: '布林上軌', value: t.bb_upper?.toFixed(2), sub: '壓力' },
    { label: '布林下軌', tipKey: '布林下軌', value: t.bb_lower?.toFixed(2), sub: '支撐' },
  ];
  return `<div class="card">
    <div class="card-header"><div class="card-title">技術指標（最新）</div></div>
    <div class="metric-grid">
      ${indicators.map(i => `
        <div class="metric">
          <div class="label">${i.label}${tip(i.tipKey)}</div>
          <div class="value ${i.cls || ''}">${i.value ?? '—'}</div>
          <div class="sub">${i.sub || ''}</div>
        </div>`).join('')}
    </div>
  </div>`;
}

// ── Signal detail table ───────────────────────────────────────────────────────
// 渲染近期買賣訊號明細表（最多顯示最近 30 筆）
function renderSignalsTab(history) {
  const sigRows = history.filter(r => r.signal !== 0);
  if (!sigRows.length) return '<div class="card"><div class="loading" style="padding:40px 0">此區間無買賣訊號</div></div>';

  return `<div class="card">
    <div class="card-header">
      <div class="card-title">🔔 買賣訊號明細（近期）</div>
      <span style="font-size:11px;color:var(--text-muted)">${sigRows.length} 個訊號</span>
    </div>
    <table class="bt-table">
      <thead><tr><th>日期</th><th>類型</th><th>收盤價</th><th>觸發原因</th></tr></thead>
      <tbody>
        ${sigRows.slice(-30).reverse().map(r => `
          <tr>
            <td>${r.date}</td>
            <td><span class="badge badge-${r.signal===1?'buy':'sell'}">${r.signal===1?'買入':'賣出'}</span></td>
            <td>NT$ ${r.close?.toFixed(2) ?? '—'}</td>
            <td style="color:var(--text-muted)">${r.signal_reason || '—'}</td>
          </tr>`).join('')}
      </tbody>
    </table>
  </div>`;
}

// ── Fundamental card ──────────────────────────────────────────────────────────
// 渲染基本面數據卡片（P/E、P/B、殖利率、EPS、ROE、市值）與新聞區塊容器
function renderFundTab(f) {
  const metrics = [
    { label: '本益比 (P/E)',    tipKey: 'PE',  value: f.pe?.toFixed(2) ?? '—' },
    { label: '股價淨值比 (P/B)', tipKey: 'PB',  value: f.pb?.toFixed(2) ?? '—' },
    { label: '殖利率',          tipKey: '殖利率', value: f.div_yield ? f.div_yield + '%' : '—' },
    { label: 'EPS',             tipKey: 'EPS', value: f.eps?.toFixed(2) ?? '—' },
    { label: 'ROE',             tipKey: 'ROE', value: f.roe ? f.roe + '%' : '—' },
    { label: '毛利率',          tipKey: '毛利率', value: f.gross_margin ? f.gross_margin + '%' : '—' },
    { label: '市值',            tipKey: '',    value: f.market_cap ? formatMarketCap(f.market_cap) : '—' },
  ];
  return `<div class="card">
    <div class="card-header"><div class="card-title">基本面數據</div></div>
    <div class="metric-grid">
      ${metrics.map(m => `<div class="metric"><div class="label">${m.label}${tip(m.tipKey)}</div><div class="value">${m.value}</div></div>`).join('')}
    </div>
    ${f.description ? `<p style="margin-top:16px;color:var(--text-muted);font-size:12px;line-height:1.8">${f.description}</p>` : ''}
  </div>
  <div class="card">
    <div class="card-header"><div class="card-title">📰 相關新聞</div></div>
    <div id="news-content"><div class="loading" style="padding:40px 0;color:var(--text-muted)">載入新聞中...</div></div>
  </div>`;
}

// ── Related news ──────────────────────────────────────────────────────────────
let newsLoadedFor = null;

// 載入該股票的相關新聞並渲染於基本面分頁
async function loadNews(ticker) {
  const el = document.getElementById('news-content');
  if (!el) return;
  try {
    const r = await fetch(`${API}/api/stock/${ticker}/news`);
    const data = await r.json();
    el.innerHTML = renderNewsList(data.news || []);
  } catch (e) {
    el.innerHTML = `<div class="loading">新聞載入失敗：${e.message}</div>`;
  }
}

// 渲染新聞列表 HTML（無資料時顯示提示文字）
function renderNewsList(news) {
  if (!news.length) return '<div class="loading" style="padding:40px 0;color:var(--text-muted)">查無相關新聞</div>';
  return `<div style="display:flex;flex-direction:column;gap:10px">
    ${news.map(n => `
      <a href="${escapeHtml(n.url || '#')}" target="_blank" rel="noopener noreferrer"
         style="display:block;padding:12px;border:1px solid var(--border);border-radius:8px;text-decoration:none;color:inherit">
        <div style="font-weight:600;font-size:13px">${escapeHtml(n.title)}</div>
        <div style="color:var(--text-muted);font-size:11px;margin-top:6px">${escapeHtml(n.source)}${n.date ? ' · ' + escapeHtml(n.date) : ''}</div>
        ${n.body ? `<div style="color:var(--text-muted);font-size:12px;margin-top:6px;line-height:1.6">${escapeHtml(n.body)}</div>` : ''}
      </a>`).join('')}
  </div>`;
}

// ── Charts ────────────────────────────────────────────────────────────────────
// 繪製K線圖（含買賣訊號標記）、RSI 圖、MACD 圖三張 Chart.js 圖表
function renderCharts(history) {
  const dates  = history.map(r => r.date);
  const closes = history.map(r => r.close);
  const sma20  = history.map(r => r.sma20);
  const sma60  = history.map(r => r.sma60);
  const bbU    = history.map(r => r.bb_upper);
  const bbL    = history.map(r => r.bb_lower);
  const rsi    = history.map(r => r.rsi);
  const macd   = history.map(r => r.macd);
  const macdSig  = history.map(r => r.macd_signal);
  const macdHist = history.map(r => r.macd_hist);

  const buyPoints  = history.filter(r => r.signal === 1).map(r => ({ x: r.date, y: r.close, reason: r.signal_reason }));
  const sellPoints = history.filter(r => r.signal === -1).map(r => ({ x: r.date, y: r.close, reason: r.signal_reason }));

  const commonOpts = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { color: '#8b949e', font: { size: 11 } } },
      tooltip: {
        callbacks: {
          afterBody(ctx) {
            // Show signal reason in tooltip when hovering near a signal point
            const di = ctx[0]?.dataIndex;
            const reason = history[di]?.signal_reason;
            return reason ? [reason] : [];
          }
        }
      }
    },
    scales: {
      x: { ticks: { color: '#8b949e', maxTicksLimit: 8, font: { size: 10 } }, grid: { color: '#21262d' } },
      y: { ticks: { color: '#8b949e', font: { size: 10 } }, grid: { color: '#21262d' } },
    },
  };

  if (priceChart) priceChart.destroy();
  priceChart = new Chart(document.getElementById('price-chart'), {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        { label: '收盤價',   data: closes,    borderColor: '#58a6ff', borderWidth: 2, pointRadius: 0, tension: 0.1, fill: false },
        { label: 'SMA 20',  data: sma20,     borderColor: '#d29922', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
        { label: 'SMA 60',  data: sma60,     borderColor: '#8b949e', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
        { label: '布林上軌', data: bbU,       borderColor: '#3fb95044', borderWidth: 1, pointRadius: 0, fill: false, borderDash: [3,3] },
        { label: '布林下軌', data: bbL,       borderColor: '#f8514944', borderWidth: 1, pointRadius: 0, fill: '+1', backgroundColor: '#3fb95008', borderDash: [3,3] },
        { label: '▲買入',   data: buyPoints,  type: 'scatter', pointRadius: 9, pointStyle: 'triangle', pointBackgroundColor: '#3fb950', showLine: false },
        { label: '▼賣出',   data: sellPoints, type: 'scatter', pointRadius: 9, pointStyle: 'triangle', rotation: 180, pointBackgroundColor: '#f85149', showLine: false },
      ],
    },
    options: { ...commonOpts },
  });

  if (rsiChart) rsiChart.destroy();
  rsiChart = new Chart(document.getElementById('rsi-chart'), {
    type: 'line',
    data: {
      labels: dates,
      datasets: [{ label: 'RSI', data: rsi, borderColor: '#79c0ff', borderWidth: 1.5, pointRadius: 0, fill: false }],
    },
    options: { ...commonOpts, scales: { ...commonOpts.scales, y: { ...commonOpts.scales.y, min: 0, max: 100 } } },
  });

  if (macdChart) macdChart.destroy();
  macdChart = new Chart(document.getElementById('macd-chart'), {
    type: 'bar',
    data: {
      labels: dates,
      datasets: [
        { label: 'Hist', data: macdHist, backgroundColor: macdHist.map(v => v >= 0 ? '#3fb95066' : '#f8514966'), type: 'bar' },
        { label: 'MACD', data: macd,    borderColor: '#58a6ff', borderWidth: 1.5, pointRadius: 0, fill: false, type: 'line' },
        { label: 'Sig',  data: macdSig, borderColor: '#f0883e', borderWidth: 1.5, pointRadius: 0, fill: false, type: 'line' },
      ],
    },
    options: { ...commonOpts },
  });
}

// 切換 K 線圖上布林通道（bb）或均線（sma）資料集的顯示/隱藏
function toggleIndicator(type) {
  if (!priceChart) return;
  (type === 'bb' ? [3,4] : [1,2]).forEach(i => {
    priceChart.getDatasetMeta(i).hidden = !priceChart.getDatasetMeta(i).hidden;
  });
  priceChart.update();
}
