/* =========================================================
   台股 AI 分析系統 — Frontend App
   ========================================================= */

const API = '';
let currentTicker = null;
let priceChart = null, rsiChart = null, macdChart = null;
let currentHistory = [];

// ── Tooltip dictionary ────────────────────────────────────────────────────────
const TIPS = {
  'RSI':         'RSI（相對強弱指標）：衡量近期漲跌動能，範圍 0–100。\n低於30：超賣（可能反彈）\n高於70：超買（可能回調）',
  'MACD':        'MACD（移動平均收斂發散）：12日EMA 減 26日EMA 的差值。MACD 高於信號線（9日EMA）為多頭排列，反之為空頭。MACD 由下往上穿越信號線稱「黃金交叉」。',
  'KD':          'KD（隨機指標 Stochastic）：K為快線，D為K的3日均值（慢線）。\nK < 20：超賣；K > 80：超買\nK從下往上穿越D：黃金交叉（買入訊號）\nK從上往下穿越D：死亡交叉（賣出訊號）',
  '黃金交叉':    '黃金交叉：短期均線（SMA20）由下往上穿越長期均線（SMA60），代表短期動能開始強於長期，通常視為多頭訊號。',
  '死亡交叉':    '死亡交叉：短期均線（SMA20）由上往下穿越長期均線（SMA60），代表短期動能弱於長期，通常視為空頭訊號。',
  '多頭排列':    '多頭排列：SMA20 > SMA60，短期均線在長期均線之上，市場處於上升趨勢。',
  '空頭排列':    '空頭排列：SMA20 < SMA60，短期均線在長期均線之下，市場處於下降趨勢。',
  'SMA20':       'SMA（簡單移動平均線）20日：過去20個交易日收盤價的算術平均值。常作為短期支撐與壓力參考。',
  'SMA60':       'SMA（簡單移動平均線）60日：過去60個交易日收盤價的算術平均值。常作為中期趨勢判斷依據。',
  '布林上軌':    '布林上軌（Bollinger Upper Band）：20日均線加兩個標準差。股價接近或突破上軌表示超買或強勢突破，可能面臨壓力。',
  '布林下軌':    '布林下軌（Bollinger Lower Band）：20日均線減兩個標準差。股價接近或跌破下軌表示超賣，可能有支撐力道。',
  '布林通道':    '布林通道（Bollinger Bands）：以20日均線為中軸，上下各兩個標準差形成的通道。帶寬窄表示低波動，帶寬寬表示高波動。',
  'PE':          'P/E（本益比）：股價 ÷ 每股盈餘（EPS）。反映市場願意為每1元獲利支付多少錢。台股平均約15–20倍，越低通常越便宜，但也可能反映低成長預期。',
  'PB':          'P/B（股價淨值比）：股價 ÷ 每股淨值（帳面價值）。低於1代表股價低於帳面資產。銀行股通常P/B較低。',
  '殖利率':      '殖利率（Dividend Yield）：每股現金股利 ÷ 股價。衡量股息收益，台股高殖利率通常指5%以上。注意：高殖利率也可能因股價下跌造成。',
  'EPS':         'EPS（每股盈餘）：公司稅後淨利 ÷ 在外流通股數。是評估公司獲利能力的核心指標，逐季/逐年成長為佳。',
  'ROE':         'ROE（股東權益報酬率）：稅後淨利 ÷ 股東權益。衡量公司利用股東資金的效率，巴菲特認為持續15%以上為優質公司。',
  '夏普比率':    'Sharpe Ratio（夏普比率）：超額報酬 ÷ 報酬標準差。衡量每承擔一單位風險所獲得的超額報酬。\n> 1：良好\n> 2：優秀\n< 0：賠錢（含風險）',
  '最大回撤':    '最大回撤（Max Drawdown）：從峰值到谷底的最大跌幅百分比。衡量策略的最大下行風險，越小表示策略越穩健。',
  '勝率':        '勝率：獲利交易次數 ÷ 總交易次數。注意：高勝率不代表好策略，還需搭配損益比（平均獲利 ÷ 平均虧損）評估。',
  '手續費':      '台灣股票交易成本：\n買入：0.1425%（券商手續費，可打折至0.06%）\n賣出：0.1425%（手續費）+ 0.3%（證券交易稅）\n每千元交易成本約4.3元',
  'ATR':         'ATR（平均真實波幅）：衡量市場波動程度，是每日最高價、最低價、前收盤價三者計算的真實波幅之14日均值。用於設定合理停損距離。',
  '每股投入金額': '每次買入一支股票時最多投入的金額（NTD）。\n持倉數量沒有上限，由可用資金自動決定。\n當可用現金低於此金額時，停止買入新股（避免手續費侵蝕）。',
  '限價買單':    '以低於當前市價的特定價格掛出的買單，只有當股價跌到該價位時才會成交。\n本系統以前一日收盤價 × 0.995 作為限價，相當於比昨收低 0.5% 才買入，避免追高。',
  '停損停利':    '停損：股價跌破設定比例（如 -7%）時自動賣出，限制虧損擴大。\n停利：股價漲過設定比例（如 +15%）時自動賣出，鎖住獲利。\n兩者都是「預先設定好的自動出場機制」。',
  '回測期間':    '模擬此策略在「N 個月前開始運作」的歷史表現。\n期間越長：能看到更多市場週期，結果更具參考性，但運算時間較長。\n期間越短：跑得快，但可能只看到單一市場狀態（純多頭或純空頭）。',
  '等權倉位':    '每支股票平均分配相同比例的資金，不因看好程度不同而加重某支。\n例如初始資金 20 萬、最大持倉 5 支 → 每支上限 4 萬。',
};

function tip(key) {
  const text = TIPS[key];
  if (!text) return '';
  return `<span class="tip" data-tip="${text.replace(/"/g, '&quot;').replace(/\n/g, '&#10;')}">?</span>`;
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadStockList();
  setupSearch();
  showPage('welcome');
});

// ── Stock list ────────────────────────────────────────────────────────────────
async function loadStockList() {
  const el = document.getElementById('stock-list');
  el.innerHTML = '<div class="loading"><div class="spinner"></div> 載入中...</div>';
  try {
    const r = await fetch(`${API}/api/top100`);
    const data = await r.json();
    renderStockList(data.stocks, data.fetched_at);
  } catch {
    el.innerHTML = '<div class="loading">無法連線至後端，請確認 ./start.sh 已執行</div>';
  }
}

function renderStockList(stocks, fetchedAt) {
  const el = document.getElementById('stock-list');
  const header = fetchedAt
    ? `<div style="font-size:10px;color:var(--text-muted);padding:6px 12px 2px;text-align:right">TWSE 收盤價 ${fetchedAt} <span style="cursor:pointer;color:var(--primary)" onclick="loadStockList()" title="重新載入">↺</span></div>`
    : '';
  el.innerHTML = header + stocks.map(s => `
    <div class="stock-item" onclick="loadStock('${s.ticker}')" data-ticker="${s.ticker}" data-name="${s.name}">
      <div>
        <div class="ticker">${s.ticker}</div>
        <div class="sname">${s.name}</div>
      </div>
      <div class="price">
        <div class="val">${s.close > 0 ? s.close.toFixed(2) : '—'}</div>
        ${s.lots > 0 ? `<div style="font-size:10px;color:var(--text-muted)">${(s.lots/1000).toFixed(0)}千張</div>` : ''}
      </div>
    </div>
  `).join('');
}

function setupSearch() {
  document.getElementById('search').addEventListener('input', function () {
    const q = this.value.toLowerCase();
    document.querySelectorAll('.stock-item').forEach(el => {
      const match = el.dataset.ticker.includes(q) || el.dataset.name.includes(q);
      el.style.display = match ? '' : 'none';
    });
  });
}

// ── Main stock analysis ───────────────────────────────────────────────────────
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
function renderFundTab(f) {
  const metrics = [
    { label: '本益比 (P/E)',    tipKey: 'PE',  value: f.pe?.toFixed(2) ?? '—' },
    { label: '股價淨值比 (P/B)', tipKey: 'PB',  value: f.pb?.toFixed(2) ?? '—' },
    { label: '殖利率',          tipKey: '殖利率', value: f.div_yield ? f.div_yield + '%' : '—' },
    { label: 'EPS',             tipKey: 'EPS', value: f.eps?.toFixed(2) ?? '—' },
    { label: 'ROE',             tipKey: 'ROE', value: f.roe ? f.roe + '%' : '—' },
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

// ── AI Analysis ───────────────────────────────────────────────────────────────
function renderAiTabPlaceholder() {
  return `<div class="card">
    <div class="card-header">
      <div class="card-title">🤖 AI 分析</div>
      <button class="btn btn-primary" id="ai-run-btn" onclick="runAiAnalysis(false)">▶ 產生 AI 分析</button>
    </div>
    <p style="font-size:11px;color:var(--text-muted);margin-bottom:12px">
      由本機 LLM 根據技術指標、基本面與相關新聞產生分析，並經第二次驗證以降低幻覺風險。結果快取 1 小時。
    </p>
    <div id="ai-result">
      <div class="loading" style="padding:40px 0;color:var(--text-muted)">點擊「產生 AI 分析」開始</div>
    </div>
  </div>`;
}

async function runAiAnalysis(force = false) {
  if (!currentTicker) return;
  const el  = document.getElementById('ai-result');
  const btn = document.getElementById('ai-run-btn');
  if (btn) btn.disabled = true;
  el.innerHTML = `<div class="loading"><div class="spinner"></div> AI 分析中（含二次驗證，可能需 30 秒以上）...</div>`;
  try {
    const r = await fetch(`${API}/api/stock/${currentTicker}/ai-analysis?force=${force}`, { method: 'POST' });
    const data = await r.json();
    el.innerHTML = renderAiResult(data);
    if (btn) {
      btn.textContent = '🔄 重新產生';
      btn.onclick = () => runAiAnalysis(true);
    }
  } catch (e) {
    el.innerHTML = `<div class="loading">AI 分析失敗：${e.message}</div>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderAiResult(data) {
  if (data.error) {
    return `<div class="loading" style="padding:24px 0;color:var(--danger)">⚠ ${escapeHtml(data.summary || 'AI 分析失敗')}</div>`;
  }

  const verdictCls = { '偏多': 'badge-buy', '中性': 'badge-hold', '偏空': 'badge-sell' }[data.verdict] || 'badge-hold';
  const cacheTag  = data.from_cache ? '💾 快取結果' : '✓ 剛產生';
  const verifyTag = data.verified
    ? '<span style="color:var(--success)">✓ 已二次驗證</span>'
    : '<span style="color:var(--warning)">⚠ 未通過二次驗證（僅供初步參考）</span>';

  return `
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:16px">
      <span class="badge ${verdictCls}">${escapeHtml(data.verdict)}</span>
      <span style="font-size:13px;color:var(--text-muted)">信心度 ${data.confidence ?? '—'}%</span>
      <span style="font-size:11px;color:var(--text-muted)">${cacheTag}</span>
      ${verifyTag}
    </div>
    ${data.key_reasons?.length ? `
    <div style="margin-bottom:14px">
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">支持理由</div>
      <ul style="margin:0;padding-left:20px;font-size:13px;line-height:1.8">
        ${data.key_reasons.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
      </ul>
    </div>` : ''}
    ${data.risks?.length ? `
    <div style="margin-bottom:14px">
      <div style="font-size:12px;color:var(--warning);margin-bottom:6px">風險提示</div>
      <ul style="margin:0;padding-left:20px;font-size:13px;line-height:1.8;color:var(--warning)">
        ${data.risks.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
      </ul>
    </div>` : ''}
    <p style="font-size:13px;line-height:1.8;margin-bottom:14px">${escapeHtml(data.summary)}</p>
    <div style="margin-bottom:14px">
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">參考新聞來源</div>
      ${data.news?.length ? `
      <div style="display:flex;flex-direction:column;gap:6px">
        ${data.news.map(n => `
          <a href="${escapeHtml(n.url || '#')}" target="_blank" rel="noopener noreferrer"
             style="display:block;padding:8px 10px;border:1px solid var(--border);border-radius:6px;text-decoration:none;color:inherit;font-size:12px">
            <div style="font-weight:600">${escapeHtml(n.title || '')}</div>
            <div style="color:var(--text-muted);font-size:10px;margin-top:4px">${escapeHtml(n.source || '')}${n.date ? ' · ' + escapeHtml(n.date) : ''}</div>
          </a>`).join('')}
      </div>` : `<div style="font-size:11px;color:var(--text-muted)">查無相關新聞，AI 分析僅根據技術指標與基本面</div>`}
    </div>
    <p style="font-size:11px;color:var(--text-muted);border-top:1px solid var(--border);padding-top:10px">
      ⚠️ AI 分析僅供參考，不構成投資建議
    </p>`;
}

// ── Backtest ──────────────────────────────────────────────────────────────────
function renderBtPlaceholder() {
  return `<div class="card">
    <div class="card-header">
      <div class="card-title">🧪 歷史回測</div>
      <div style="display:flex;align-items:center;gap:12px">
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
          <input type="checkbox" id="fee-toggle" checked style="width:14px;height:14px">
          含手續費+稅
        </label>
        <button class="btn btn-primary" onclick="runBacktest()">▶ 開始回測</button>
      </div>
    </div>
    <div style="font-size:11px;color:var(--text-muted);margin-bottom:12px">
      手續費: 買賣各 0.1425%，賣出另加證交稅 0.3%
    </div>
    <div id="bt-result">
      <div class="loading" style="padding:40px 0;color:var(--text-muted)">點擊「開始回測」執行歷史回測</div>
    </div>
  </div>`;
}

async function runBacktest() {
  if (!currentTicker) return;
  const withFee = document.getElementById('fee-toggle')?.checked ?? true;
  const el = document.getElementById('bt-result');
  el.innerHTML = '<div class="loading"><div class="spinner"></div> 回測中...</div>';
  try {
    const r = await fetch(`${API}/api/backtest/${currentTicker}?days=365&with_fee=${withFee}`, { method: 'POST' });
    const data = await r.json();
    el.innerHTML = renderBtResult(data, withFee);
  } catch (e) {
    el.innerHTML = `<div class="loading">回測失敗：${e.message}</div>`;
  }
}

function renderBtResult(d, withFee) {
  const rc = d.total_return_pct >= 0 ? 'positive' : 'negative';
  const feeNote = withFee ? `（含手續費 NT$ ${d.total_fee_paid?.toLocaleString()}）` : '（不含手續費）';
  return `
    <div class="metric-grid" style="margin-bottom:20px">
      ${[
        { label: '總報酬',   tipKey: '',      value: `${d.total_return_pct}%`, cls: rc },
        { label: '最大回撤', tipKey: '最大回撤', value: `${d.max_drawdown_pct}%`, cls: 'negative' },
        { label: '勝率',     tipKey: '勝率',  value: `${d.win_rate}%` },
        { label: '夏普比率', tipKey: '夏普比率', value: d.sharpe_ratio },
        { label: '交易次數', tipKey: '',      value: d.total_trades },
        { label: '手續費總額', tipKey: '手續費', value: `NT$ ${d.total_fee_paid?.toLocaleString() ?? 0}`, cls: withFee ? 'negative' : '' },
        { label: '初始資金', tipKey: '',      value: `NT$ ${d.initial_capital?.toLocaleString()}` },
        { label: '期末資金', tipKey: '',      value: `NT$ ${d.final_capital?.toLocaleString()}`, cls: rc },
      ].map(m => `<div class="metric"><div class="label">${m.label}${tip(m.tipKey)}</div><div class="value ${m.cls||''}">${m.value}</div></div>`).join('')}
    </div>
    <p style="font-size:11px;color:var(--text-muted);margin-bottom:12px">${feeNote}</p>
    <table class="bt-table">
      <thead>
        <tr>
          <th>進場日</th><th>進場原因</th><th>進場價</th>
          <th>出場日</th><th>出場原因</th><th>出場價</th>
          <th>股數</th><th>損益</th>
          ${withFee ? '<th>手續費</th>' : ''}
        </tr>
      </thead>
      <tbody>
        ${d.trades.map(t => `
          <tr>
            <td>${t.entry_date}</td>
            <td style="color:var(--success);font-size:11px">${t.entry_reason || '—'}</td>
            <td>NT$ ${t.entry_price?.toFixed(2)}</td>
            <td>${t.exit_date ?? '持倉中'}</td>
            <td style="color:var(--danger);font-size:11px">${t.exit_reason || '—'}</td>
            <td>${t.exit_price ? 'NT$ ' + t.exit_price.toFixed(2) : '—'}</td>
            <td>${t.shares}</td>
            <td class="${t.pnl >= 0 ? 'positive' : 'negative'}">${t.pnl_pct?.toFixed(2)}%</td>
            ${withFee ? `<td style="color:var(--text-muted)">${t.fee_paid?.toFixed(0)}</td>` : ''}
          </tr>`).join('')}
      </tbody>
    </table>`;
}

// ── Portfolio tab (unified auto_trade portfolio) ──────────────────────────────
async function loadSimulation() {
  const el = document.getElementById('sim-content');
  try {
    const [statusR, ordersR] = await Promise.all([
      fetch(`${API}/api/auto/status`),
      fetch(`${API}/api/auto/orders`),
    ]);
    const status = await statusR.json();
    const orders = await ordersR.json();
    el.innerHTML = status.initialized
      ? renderSimPortfolio(status, orders.filled || [])
      : renderSimInit();
  } catch (e) {
    el.innerHTML = `<div class="loading">無法載入投資組合：${e.message}</div>`;
  }
}

function renderSimInit() {
  return `<div class="card">
    <div class="card-header"><div class="card-title">💰 投資組合</div></div>
    <p style="color:var(--text-muted);margin-bottom:16px">
      尚未初始化投資組合。請先前往「自動交易」頁面建立投資組合，<br>
      或在此直接初始化（與「自動交易」共用同一套系統）。
    </p>
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <div class="form-group" style="margin:0">
        <label style="font-size:12px;color:var(--text-muted)">初始資金 (NTD)</label>
        <input type="number" id="sim-capital" class="form-control" value="100000" style="width:160px">
      </div>
      <div class="form-group" style="margin:0">
        <label style="font-size:12px;color:var(--text-muted)">每股投入金額 (NTD)</label>
        <input type="number" id="sim-budget" class="form-control" value="10000" min="1000" step="1000" style="width:120px">
      </div>
      <button class="btn btn-success" onclick="initSimulation()" style="margin-top:18px">🚀 開始</button>
    </div>
  </div>`;
}

function renderSimPortfolio(data, trades) {
  const pnlClass  = data.total_pnl >= 0 ? 'positive' : 'negative';
  const positions = data.positions || [];
  const latestSig = currentHistory.filter(r => r.signal !== 0).slice(-1)[0];
  const todayStr  = currentHistory.slice(-1)[0]?.date ?? '';
  const sigIsToday = latestSig?.date === todayStr;
  const sigTxt = latestSig
    ? `${latestSig.signal === 1 ? '📈 買入訊號' : '📉 賣出訊號'}：${latestSig.signal_reason}`
    : '⏸ 目前無明確訊號';

  return `
    <div class="card">
      <div class="card-header">
        <div class="card-title">💰 投資組合</div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-outline" onclick="simAutoTrade()">⚡ 自動執行訊號</button>
          <button class="btn btn-outline" onclick="simManualBuy()">買入</button>
          <button class="btn btn-outline" onclick="simManualSell()">賣出</button>
          <button class="btn btn-outline" onclick="loadSimulation()">🔄 更新</button>
          <button class="btn btn-danger" style="font-size:11px" onclick="resetSimulation()">重置</button>
        </div>
      </div>

      <div style="background:var(--surface2);border-radius:8px;padding:12px;margin-bottom:16px;font-size:13px">
        <strong>最新訊號：</strong> ${sigTxt}
        ${latestSig
          ? `<span style="margin-left:8px;font-size:11px;color:${sigIsToday ? 'var(--success)' : 'var(--warning, #d29922)'}">
               ${sigIsToday ? '● 今日訊號' : `⚠ ${latestSig.date} 的訊號（非今日）`}
             </span>`
          : ''}
      </div>

      <div class="metric-grid" style="margin-bottom:16px">
        ${[
          { label: '總資產',   value: `NT$ ${data.total_value?.toLocaleString()}`,  cls: pnlClass },
          { label: '現金',     value: `NT$ ${data.cash?.toLocaleString()}` },
          { label: '持股市值', value: `NT$ ${data.position_value?.toLocaleString()}` },
          { label: '總損益',   value: `${data.total_pnl >= 0 ? '+' : ''}NT$ ${data.total_pnl?.toLocaleString()}`, cls: pnlClass },
          { label: '損益率',   value: `${data.total_pnl_pct?.toFixed(2)}%`, cls: pnlClass },
          { label: '起始時間', value: data.started_at },
        ].map(m => `<div class="metric"><div class="label">${m.label}</div><div class="value ${m.cls||''}">${m.value}</div></div>`).join('')}
      </div>

      ${positions.length ? `
        <div style="margin-bottom:16px">
          <div style="font-size:13px;font-weight:600;margin-bottom:8px">持倉明細</div>
          <table class="bt-table">
            <thead><tr><th>代號</th><th>股數</th><th>均成本</th><th>現價</th><th>市值</th><th>損益（不含費）</th><th>損益（含費）</th><th>停利</th><th>停損</th><th>進場原因</th></tr></thead>
            <tbody>
              ${positions.map(pos => `
                <tr>
                  <td><strong>${pos.ticker}</strong><br><span style="font-size:11px;color:var(--text-muted)">${pos.name}</span></td>
                  <td>${pos.shares}</td>
                  <td>NT$ ${pos.avg_cost?.toFixed(2)}</td>
                  <td>${pos.price_error
                    ? `<span style="color:var(--danger);font-size:11px">⚠ 報價異常</span>`
                    : `NT$ ${pos.current_price?.toFixed(2)}${pos.price_stale
                        ? `<br><span style="font-size:10px;color:var(--warning)">⚠ ${pos.price_date} 資料</span>`
                        : ''}`
                  }</td>
                  <td>NT$ ${pos.market_value?.toLocaleString() ?? '—'}</td>
                  <td class="${pos.pnl>=0?'positive':'negative'}">${pos.pnl!=null ? pos.pnl_pct?.toFixed(2)+'%' : '—'}<br>
                    <span style="font-size:11px">${pos.pnl!=null ? (pos.pnl>=0?'+':'')+'NT$ '+pos.pnl?.toLocaleString() : ''}</span></td>
                  <td class="${(pos.pnl_net??pos.pnl)>=0?'positive':'negative'}">${pos.pnl_net!=null ? (pos.pnl_net_pct??pos.pnl_pct)?.toFixed(2)+'%' : '—'}<br>
                    <span style="font-size:11px">${pos.pnl_net!=null ? (pos.pnl_net>=0?'+':'')+'NT$ '+pos.pnl_net?.toLocaleString() : ''}</span></td>
                  <td style="color:var(--success);font-size:12px">NT$ ${pos.limit_sell?.toFixed(2)}</td>
                  <td style="color:var(--danger);font-size:12px">NT$ ${pos.stop_loss?.toFixed(2)}</td>
                  <td style="font-size:11px;color:var(--text-muted)">${pos.entry_reason || '—'}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>` : '<p style="color:var(--text-muted);margin-bottom:16px">目前無持倉</p>'}

      ${trades.length ? `
        <div>
          <div style="font-size:13px;font-weight:600;margin-bottom:8px">交易紀錄（最近20筆）</div>
          <table class="bt-table">
            <thead><tr><th>日期</th><th>代號</th><th>動作</th><th>股數</th><th>價格</th><th>金額</th><th>損益</th><th>原因</th></tr></thead>
            <tbody>
              ${trades.slice().reverse().slice(0,20).map(t => `
                <tr>
                  <td>${t.date}</td>
                  <td><strong>${t.ticker}</strong></td>
                  <td><span class="badge badge-${t.action==='buy'?'buy':'sell'}">${t.action==='buy'?'買入':'賣出'}</span></td>
                  <td>${t.shares}</td>
                  <td>NT$ ${t.price?.toFixed(2)}</td>
                  <td>NT$ ${t.amount?.toLocaleString()}</td>
                  <td class="${(t.pnl??0)>=0?'positive':'negative'}">${t.pnl != null ? (t.pnl>=0?'+':'')+t.pnl.toLocaleString() : '—'}</td>
                  <td style="font-size:11px;color:var(--text-muted)">${t.reason || '—'}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>` : ''}
    </div>`;
}

async function initSimulation() {
  const capital          = parseFloat(document.getElementById('sim-capital')?.value || 100000);
  const per_stock_budget = parseFloat(document.getElementById('sim-budget')?.value || 10000);
  try {
    const r = await fetch(`${API}/api/auto/init`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ capital, per_stock_budget }),
    });
    const d = await r.json();
    showToast(d.message, 'success');
    loadSimulation();
  } catch (e) {
    showToast('初始化失敗：' + e.message, 'error');
  }
}

async function resetSimulation() {
  if (!confirm('確定要重置投資組合？所有持倉和紀錄將清空。')) return;
  let capital = 100000, per_stock_budget = 10000;
  try {
    const s = await fetch(`${API}/api/auto/status`).then(r => r.json());
    if (s.initialized) {
      capital = s.initial_capital ?? capital;
      per_stock_budget = s.per_stock_budget ?? per_stock_budget;
    }
  } catch {}
  await fetch(`${API}/api/auto/init`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ capital, per_stock_budget }),
  });
  showToast('投資組合已重置', 'success');
  loadSimulation();
}

async function simAutoTrade() {
  if (!currentTicker) return;
  await _simTrade('auto');
}
async function simManualBuy() {
  if (!currentTicker) return;
  await _simTrade('buy');
}
async function simManualSell() {
  if (!currentTicker) return;
  await _simTrade('sell');
}

async function _simTrade(action) {
  try {
    const r = await fetch(`${API}/api/auto/trade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker: currentTicker, action }),
    });
    const d = await r.json();
    showToast(d.message, d.status === 'ok' ? 'success' : 'error');
    loadSimulation();
  } catch (e) {
    showToast('交易失敗：' + e.message, 'error');
  }
}

// ── Charts ────────────────────────────────────────────────────────────────────
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

function toggleIndicator(type) {
  if (!priceChart) return;
  (type === 'bb' ? [3,4] : [1,2]).forEach(i => {
    priceChart.getDatasetMeta(i).hidden = !priceChart.getDatasetMeta(i).hidden;
  });
  priceChart.update();
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function showSettings() {
  showPage('settings');
  try {
    const r = await fetch(`${API}/api/config`);
    const cfg = await r.json();
    document.getElementById('initial-capital').value = cfg.strategy.initial_capital || 100000;
    document.getElementById('max-per-trade').value = cfg.strategy.max_per_trade ?? 0;
    document.getElementById('stop-loss').value = cfg.strategy.stop_loss_pct || 7;
    document.getElementById('take-profit').value = cfg.strategy.take_profit_pct || 15;
    document.getElementById('rsi-oversold').value = cfg.strategy.rsi_oversold || 30;
    document.getElementById('rsi-overbought').value = cfg.strategy.rsi_overbought || 70;
    document.getElementById('ma-short').value = cfg.strategy.ma_short || 20;
    document.getElementById('ma-long').value = cfg.strategy.ma_long || 60;
    document.getElementById('llm-model').value = cfg.settings.llm_model || 'qwen2.5:7b';
    document.getElementById('ollama-url').value = cfg.settings.ollama_url || 'http://host.docker.internal:11434';
    document.getElementById('auto-scan-with-ai').checked = cfg.settings.auto_scan_with_ai ?? true;
  } catch (e) {
    showToast('無法連線後端', 'error');
  }
}

async function saveSettings() {
  const body = {
    strategy: {
      initial_capital:  parseFloat(document.getElementById('initial-capital').value),
      max_per_trade:    parseFloat(document.getElementById('max-per-trade').value) || 0,
      stop_loss_pct:    parseFloat(document.getElementById('stop-loss').value),
      take_profit_pct:  parseFloat(document.getElementById('take-profit').value),
      rsi_oversold:     parseInt(document.getElementById('rsi-oversold').value),
      rsi_overbought:   parseInt(document.getElementById('rsi-overbought').value),
      ma_short:         parseInt(document.getElementById('ma-short').value),
      ma_long:          parseInt(document.getElementById('ma-long').value),
    },
    settings: {
      llm_model:         document.getElementById('llm-model').value.trim(),
      ollama_url:        document.getElementById('ollama-url').value.trim(),
      auto_scan_with_ai: document.getElementById('auto-scan-with-ai').checked,
    },
  };
  try {
    const r = await fetch(`${API}/api/config`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    showToast((await r.json()).message, 'success');
  } catch {
    showToast('儲存失敗', 'error');
  }
}

// ── Full portfolio backtest ────────────────────────────────────────────────────
async function showFullBacktestPage() {
  showPage('full-backtest');
  document.getElementById('fb-content').innerHTML = renderFBForm();
}

function renderFBForm() {
  return `
    <div class="card">
      <div class="card-header">
        <div class="card-title">📊 自動交易策略歷史驗證</div>
      </div>
      <p style="color:var(--text-muted);line-height:1.9;margin-bottom:16px">
        模擬此系統若在 <strong>N 個月前</strong>開始運作，每個交易日自動掃描訊號、掛<span class="tip" data-tip="${TIPS['限價買單'].replace(/\n/g,'&#10;')}">限價買單</span>、觸發<span class="tip" data-tip="${TIPS['停損停利'].replace(/\n/g,'&#10;')}">停利/停損</span>，
        實際上能賺多少。倉位採<span class="tip" data-tip="${TIPS['等權倉位'].replace(/\n/g,'&#10;')}">等權分配</span>，使用含手續費計算，驗證策略可行性。
      </p>
      <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end">
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">回測期間${tip('回測期間')}</label>
          <select id="fb-months" class="form-control" style="width:140px">
            <option value="3">3 個月</option>
            <option value="6">6 個月</option>
            <option value="12" selected>12 個月</option>
            <option value="24">24 個月</option>
          </select>
        </div>
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">初始資金 (NTD)</label>
          <input type="number" id="fb-capital" class="form-control" value="200000" style="width:160px">
        </div>
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">每股投入金額 (NTD)${tip('每股投入金額')}</label>
          <input type="number" id="fb-budget" class="form-control" value="10000" min="1000" step="1000" style="width:120px">
        </div>
        <button class="btn btn-primary" onclick="runFullBacktest()" id="fb-btn">▶ 開始驗證</button>
      </div>
      <p style="margin-top:10px;font-size:11px;color:var(--text-muted)">
        ⚠ 首次執行需下載歷史資料，約需 30–60 秒。之後因快取，僅需數秒。
      </p>
    </div>
    <div id="fb-result"></div>
  `;
}

async function runFullBacktest() {
  const btn = document.getElementById('fb-btn');
  const el  = document.getElementById('fb-result');
  const months          = parseInt(document.getElementById('fb-months').value);
  const capital         = parseFloat(document.getElementById('fb-capital').value);
  const per_stock_budget = parseFloat(document.getElementById('fb-budget').value || 10000);

  btn.disabled = true;
  btn.textContent = '驗證中...';
  el.innerHTML = `<div class="loading"><div class="spinner"></div> 模擬 ${months} 個月 × 每日自動交易中，首次需 30–60 秒...</div>`;

  try {
    const r = await fetch(`${API}/api/full-backtest`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({months, initial_capital: capital, per_stock_budget, max_candidates: 40}),
    });
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    el.innerHTML = renderFBResult(d);
    setTimeout(() => renderFBChart(d.equity_curve), 100);
  } catch (e) {
    el.innerHTML = `<div class="loading">驗證失敗：${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ 開始驗證';
  }
}

function renderFBResult(d) {
  const rc  = d.total_return_pct >= 0 ? 'positive' : 'negative';
  const profitable = d.total_return_pct >= 0;

  return `
    <div class="card">
      <div class="card-header">
        <div class="card-title">
          ${profitable ? '✅' : '⚠️'} 驗證結果：${d.months} 個月
          <span style="font-size:12px;color:var(--text-muted);font-weight:400;margin-left:8px">
            ${d.start_date} → ${d.end_date}（${d.trading_days} 個交易日，分析 ${d.stocks_analyzed} 支股票）
          </span>
        </div>
      </div>

      <div class="metric-grid" style="margin-bottom:20px">
        ${[
          { label: '總報酬率',   value: `${d.total_return_pct > 0 ? '+' : ''}${d.total_return_pct}%`, cls: rc },
          { label: '損益金額',   value: `${d.total_pnl > 0 ? '+' : ''}NT$ ${d.total_pnl?.toLocaleString()}`, cls: rc },
          { label: '最大回撤',   value: `${d.max_drawdown_pct}%`, cls: 'negative', tipKey: '最大回撤' },
          { label: '夏普比率',   value: d.sharpe_ratio, tipKey: '夏普比率' },
          { label: '交易次數',   value: d.total_trades },
          { label: '勝率',       value: `${d.win_rate}%`, tipKey: '勝率' },
          { label: '初始資金',   value: `NT$ ${d.initial_capital?.toLocaleString()}` },
          { label: '期末資金',   value: `NT$ ${d.final_capital?.toLocaleString()}`, cls: rc },
          { label: '獲利交易',   value: `${d.winning_trades} 次`, cls: 'positive', tipKey: '勝率' },
          { label: '虧損交易',   value: `${d.losing_trades} 次`, cls: 'negative' },
          { label: '手續費總額', value: `NT$ ${d.total_fee_paid?.toLocaleString()}`, cls: 'negative', tipKey: '手續費' },
          { label: '結論',
            value: profitable
              ? `${d.months} 個月獲利 ${d.total_return_pct}%`
              : `${d.months} 個月虧損 ${Math.abs(d.total_return_pct)}%`,
            cls: rc },
        ].map(m => `<div class="metric"><div class="label">${m.label}${tip(m.tipKey||'')}</div><div class="value ${m.cls||''}">${m.value}</div></div>`).join('')}
      </div>

      <div style="height:220px;margin-bottom:20px"><canvas id="fb-chart"></canvas></div>

      <div style="font-size:13px;font-weight:600;margin-bottom:8px">交易明細（${d.trades.length} 筆）</div>
      <table class="bt-table">
        <thead><tr>
          <th>日期</th><th>代號</th><th>動作</th><th>股數</th><th>價格</th>
          <th>損益</th><th>進場日</th><th>原因</th>
        </tr></thead>
        <tbody>
          ${d.trades.filter(t => t.action === 'sell').slice(0, 60).map(t => `
            <tr>
              <td>${t.date}</td>
              <td><strong>${t.ticker}</strong><br><span style="font-size:10px;color:var(--text-muted)">${t.name}</span></td>
              <td><span class="badge badge-sell">賣出</span></td>
              <td>${t.shares}</td>
              <td>NT$ ${t.price?.toFixed(2)}<br>
                <span style="font-size:10px;color:var(--text-muted)">進場 NT$ ${t.entry_price?.toFixed(2)}</span>
              </td>
              <td class="${(t.pnl||0)>=0?'positive':'negative'}">
                ${t.pnl!=null?(t.pnl>=0?'+':'')+t.pnl.toLocaleString()+'元<br>'+t.pnl_pct?.toFixed(2)+'%':'—'}
              </td>
              <td>${t.entry_date}</td>
              <td style="font-size:11px;color:var(--text-muted)">${t.reason}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderFBChart(history) {
  const canvas = document.getElementById('fb-chart');
  if (!canvas || !history?.length) return;
  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  const initial = history[0]?.equity || 0;
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: history.map(h => h.date),
      datasets: [
        { label: '資產', data: history.map(h => h.equity),
          borderColor: '#58a6ff', borderWidth: 2, pointRadius: 0,
          fill: true, backgroundColor: '#58a6ff18' },
        { label: '現金', data: history.map(h => h.cash),
          borderColor: '#8b949e', borderWidth: 1, pointRadius: 0,
          fill: false, borderDash: [4,4] },
        { label: '初始資金', data: history.map(() => initial),
          borderColor: '#d29922', borderWidth: 1, pointRadius: 0,
          fill: false, borderDash: [2,4] },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: {mode:'index', intersect:false},
      plugins: { legend: { labels: {color:'#8b949e', font:{size:11}} } },
      scales: {
        x: { ticks: {color:'#8b949e', maxTicksLimit:10, font:{size:10}}, grid:{color:'#21262d'} },
        y: { ticks: {color:'#8b949e', font:{size:10}}, grid:{color:'#21262d'} },
      },
    },
  });
}

// ── 今日訊號掃描 ──────────────────────────────────────────────────────────────
async function showScanPage() {
  showPage('scan');
  const el = document.getElementById('scan-content');
  el.innerHTML = `<div style="padding:0 4px">
    <div style="margin-bottom:20px">
      <h2 style="font-size:18px;font-weight:700">🔍 今日訊號掃描</h2>
      <div style="font-size:12px;color:var(--text-muted);margin-top:4px">
        條件與自動交易相同 · 買入：RSI≤65 + 今日買訊 · 賣出：近3日賣訊 · 系統每小時自動檢查資料並掃描
      </div>
    </div>
    <div id="scan-result">
      <div style="text-align:center;padding:40px 0;color:var(--text-muted)">
        <div class="spinner" style="margin:0 auto 12px"></div>載入上次掃描結果...
      </div>
    </div>
  </div>`;

  // 顯示背景排程自動產生的掃描結果
  try {
    const r = await fetch(`${API}/api/scan/today`);
    const data = await r.json();
    if (data.cached && (data.buy_candidates?.length || data.sell_candidates?.length)) {
      renderScanResult(data);
    } else {
      document.getElementById('scan-result').innerHTML = `
        <div style="text-align:center;padding:60px 0;color:var(--text-muted)">
          <div style="font-size:36px;margin-bottom:12px">📡</div>
          <div style="font-weight:600;margin-bottom:6px">尚無掃描記錄</div>
          <div style="font-size:12px">系統會在資料更新後自動掃描，請稍候</div>
        </div>`;
    }
  } catch {
    document.getElementById('scan-result').innerHTML =
      `<div style="padding:20px;color:var(--danger)">無法連線後端</div>`;
  }
}

function renderScanResult(data) {
  const el = document.getElementById('scan-result');
  const { buy_candidates: buys = [], sell_candidates: sells = [],
          scanned = 0, scan_time = '', errors = [] } = data;

  const statBar = `
    <div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap;align-items:center">
      <div style="background:var(--surface2);border-radius:8px;padding:8px 14px;display:flex;gap:8px;align-items:center">
        <span>📊</span><div><div style="font-size:10px;color:var(--text-muted)">已掃描</div>
        <div style="font-weight:700;font-size:14px">${scanned} 支</div></div>
      </div>
      <div style="background:#0d2a0d;border:1px solid #238636;border-radius:8px;padding:8px 14px;display:flex;gap:8px;align-items:center">
        <span>📈</span><div><div style="font-size:10px;color:#3fb950">買入候選</div>
        <div style="font-weight:700;font-size:14px;color:#3fb950">${buys.length} 支</div></div>
      </div>
      <div style="background:#1f0d0d;border:1px solid #b91c1c;border-radius:8px;padding:8px 14px;display:flex;gap:8px;align-items:center">
        <span>📉</span><div><div style="font-size:10px;color:#f85149">賣出候選</div>
        <div style="font-weight:700;font-size:14px;color:#f85149">${sells.length} 支</div></div>
      </div>
      <div style="margin-left:auto;text-align:right;font-size:11px;color:var(--text-muted)">
        最後掃描時間：${scan_time || '—'}<br>每小時自動檢查資料更新
      </div>
    </div>`;

  const aiEnriched = !!data.ai_enriched;
  const colCount = aiEnriched ? 9 : 8;

  const mkTable = (rows, type, title, subtitle, hdBg, hdBorder, hdColor) => `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header" style="background:${hdBg};border-bottom:1px solid ${hdBorder}">
        <div class="card-title" style="color:${hdColor}">${title}</div>
        <div style="font-size:11px;color:var(--text-muted)">${subtitle}</div>
      </div>
      <div style="overflow-x:auto">
        <table id="tbl-${type}" style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="border-bottom:1px solid var(--border);color:var(--text-muted)">
              <th style="padding:8px 12px;text-align:left">股票</th>
              <th style="padding:8px;text-align:right">現價</th>
              <th style="padding:8px;text-align:center">RSI</th>
              <th style="padding:8px;text-align:center">MACD</th>
              <th style="padding:8px;text-align:center">KD</th>
              <th style="padding:8px;text-align:center">均線</th>
              <th style="padding:8px;text-align:left">觸發訊號</th>
              ${aiEnriched ? '<th style="padding:8px;text-align:center">AI信心</th>' : ''}
              <th style="padding:8px;text-align:center;white-space:nowrap">操作</th>
            </tr>
          </thead>
          <tbody>
            ${rows.length
              ? rows.map(s => scanRow(s, type, aiEnriched)).join('')
              : `<tr><td colspan="${colCount}" style="padding:24px;text-align:center;color:var(--text-muted)">今日無候選</td></tr>`}
          </tbody>
        </table>
      </div>
    </div>`;

  el.innerHTML =
    statBar +
    mkTable(buys,  'buy',  `📈 買入候選（${buys.length} 支）`,
            '今日出現買訊 · RSI≤65 · 依 RSI 由低排序',
            '#0a1f0a','#238636','#3fb950') +
    mkTable(sells, 'sell', `📉 賣出候選（${sells.length} 支）`,
            '近3日出現賣訊 · 今日訊號優先 · 依 RSI 由高排序',
            '#1a0808','#b91c1c','#f85149') +
    (errors.length ? `<div style="font-size:11px;color:var(--text-muted);margin-top:8px">
      ⚠ ${errors.length} 筆異常：${errors.join('；')}</div>` : '');
}

function scanRow(s, type, aiEnriched) {
  const rsiColor = s.rsi < 30 ? '#3fb950' : s.rsi > 70 ? '#f85149' : s.rsi > 60 ? '#e3b341' : 'var(--text-secondary)';
  const macdBadge = s.macd_bullish
    ? `<span style="color:#3fb950;font-weight:700">▲多</span>`
    : `<span style="color:#f85149;font-weight:700">▼空</span>`;
  const gcBadge = s.golden_cross
    ? `<span style="color:#3fb950">黃金</span>`
    : `<span style="color:#f85149">死亡</span>`;
  const todayBadge = !s.is_today
    ? `<span style="color:var(--text-muted);margin-left:4px">⚠非今日</span>` : '';
  const reason = (s.signal_reason || '').replace('買入：','').replace('賣出：','');

  let aiCell = '';
  if (aiEnriched) {
    const c = s.ai_confidence;
    const cColor = c == null ? 'var(--text-muted)' : c >= 70 ? '#3fb950' : c >= 40 ? '#e3b341' : '#f85149';
    const summary = escapeHtml(s.ai_summary || '');
    const newsList = s.ai_news || [];
    const newsHtml = newsList.length ? `
        <details style="margin-top:4px;text-align:left">
          <summary style="cursor:pointer;color:var(--text-muted);font-size:10px">📰 ${newsList.length} 則新聞來源</summary>
          <div style="margin-top:4px;display:flex;flex-direction:column;gap:2px">
            ${newsList.map(n => `<a href="${escapeHtml(n.url || '#')}" target="_blank" rel="noopener noreferrer"
                style="font-size:10px;color:var(--accent,#58a6ff);text-decoration:none;white-space:normal">${escapeHtml(n.title || '')}</a>`).join('')}
          </div>
        </details>` : '';
    aiCell = `
      <td style="padding:8px;text-align:center;max-width:160px" title="${summary}">
        <span style="color:${cColor};font-weight:700">${c ?? '—'}</span>
        <div style="font-size:10px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${summary}</div>
        ${newsHtml}
      </td>`;
  }

  return `
    <tr id="stock-row-${s.ticker}" style="border-bottom:1px solid var(--border)"
        onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background=''">
      <td style="padding:8px 12px">
        <div style="font-weight:700">${s.ticker}</div>
        <div style="font-size:10px;color:var(--text-muted)">${s.name}</div>
      </td>
      <td style="padding:8px;text-align:right;font-weight:600">${s.price?.toFixed(2) ?? '—'}</td>
      <td style="padding:8px;text-align:center;color:${rsiColor};font-weight:700">${s.rsi ?? '—'}</td>
      <td style="padding:8px;text-align:center">${macdBadge}</td>
      <td style="padding:8px;text-align:center;font-size:11px;color:var(--text-muted)">${s.k ?? '—'}/${s.d ?? '—'}</td>
      <td style="padding:8px;text-align:center">${gcBadge}</td>
      <td style="padding:8px;font-size:11px;color:var(--text-muted);max-width:180px">
        ${reason}${todayBadge}
      </td>
      ${aiCell}
      <td style="padding:8px;text-align:center;white-space:nowrap">
        <button class="btn btn-outline" style="font-size:11px;padding:3px 8px;margin-right:4px"
          onclick="loadStock('${s.ticker}')">圖表</button>
      </td>
    </tr>`;
}

// ── Auto Trading ──────────────────────────────────────────────────────────────
async function showAutoPage() {
  showPage('auto');
  await refreshAutoPage();
}

async function refreshAutoPage() {
  const el = document.getElementById('auto-page-content');
  try {
    const r = await fetch(`${API}/api/auto/status`);
    const data = await r.json();
    if (!data.initialized) {
      el.innerHTML = renderAutoInit();
    } else {
      const [ordersR, histR] = await Promise.all([
        fetch(`${API}/api/auto/orders`).then(r => r.json()),
        fetch(`${API}/api/auto/history`).then(r => r.json()),
      ]);
      const history = histR.history || [];
      el.innerHTML = renderAutoDashboard(data, ordersR, history);
      if (history.length > 1) renderEquityChart(history);
    }
  } catch (e) {
    el.innerHTML = `<div class="loading">載入失敗：${e.message}</div>`;
  }
}

function renderAutoInit() {
  return `
    <div class="card">
      <div class="card-header"><div class="card-title">🤖 自動交易系統</div></div>
      <p style="color:var(--text-muted);line-height:1.9;margin-bottom:20px">
        系統每小時自動檢查資料更新，找到買入訊號後<strong>立即買入</strong>（市價成交）。<br>
        同時自動檢查現有持倉：出現賣出訊號、或達到<strong>停利/停損價</strong>時立即賣出。<br>
        此系統與單一股票頁面的「⚡ 自動執行訊號」共用同一個投資組合。
      </p>
      <div style="background:var(--surface2);border-radius:8px;padding:16px;margin-bottom:20px;font-size:13px">
        <strong>費用說明</strong>（台灣標準）：<br>
        買入：手續費 0.1425%　|　賣出：手續費 0.1425% + 證交稅 0.3%
      </div>
      <div style="display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap">
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">初始資金 (NTD)</label>
          <input type="number" id="auto-capital" class="form-control" value="100000" style="width:180px">
        </div>
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">每股投入金額 (NTD)${tip('每股投入金額')}</label>
          <input type="number" id="auto-budget" class="form-control" value="10000" min="1000" step="1000" style="width:120px">
        </div>
        <button class="btn btn-success" onclick="autoInit()">🚀 開始自動交易</button>
      </div>
    </div>`;
}

const ORDERS_PAGE_SIZE = 20;
let autoOrdersData = [];
let autoOrdersPage = 1;

function renderAutoDashboard(portfolio, orders, history) {
  const pnlCls  = portfolio.total_pnl >= 0 ? 'positive' : 'negative';
  const positions = portfolio.positions || [];
  const filled    = orders.filled || [];
  autoOrdersData  = filled;

  return `
    <!-- Top action bar -->
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">🤖 自動交易系統</div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:2px">
            最後更新：${portfolio.last_updated} ｜ 開始日期：${portfolio.started_at}
          </div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-outline" onclick="refreshAutoPage()">🔄 更新</button>
          <button class="btn btn-danger" style="font-size:11px" onclick="autoReset()">重置</button>
        </div>
      </div>

      <div class="metric-grid">
        ${[
          { label: '總資產',      value: `NT$ ${portfolio.total_value?.toLocaleString()}`,  cls: pnlCls },
          { label: '可用現金',    value: `NT$ ${portfolio.cash?.toLocaleString()}` },
          { label: '持股市值',    value: `NT$ ${portfolio.position_value?.toLocaleString()}` },
          { label: '總損益',      value: `${portfolio.total_pnl >= 0 ? '+' : ''}NT$ ${portfolio.total_pnl?.toLocaleString()}`, cls: pnlCls },
          { label: '損益率',      value: `${portfolio.total_pnl_pct?.toFixed(2)}%`, cls: pnlCls },
          { label: '完成交易',    value: `${portfolio.total_trades} 次` },
          { label: '歷史勝率',    value: `${portfolio.win_rate}%`, tipKey: '勝率' },
          { label: '目前持倉', value: `${portfolio.positions?.length ?? 0} 支` },
          { label: '每股投入', value: `NT$ ${(portfolio.per_stock_budget ?? 10000).toLocaleString()}`, tipKey: '每股投入金額' },
        ].map(m => `<div class="metric"><div class="label">${m.label}${tip(m.tipKey||'')}</div><div class="value ${m.cls||''}">${m.value}</div></div>`).join('')}
      </div>
    </div>

    <!-- Equity curve -->
    ${history.length > 1 ? `
    <div class="card">
      <div class="card-header"><div class="card-title">📈 資產曲線</div></div>
      <div style="height:200px"><canvas id="equity-chart"></canvas></div>
    </div>` : ''}

    <!-- Current positions -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">📦 目前持倉</div>
        <span style="font-size:12px;color:var(--text-muted)">${positions.length} 支</span>
      </div>
      ${positions.length ? `
        <table class="bt-table">
          <thead><tr>
            <th>代號</th><th>股數</th><th>均成本</th><th>現價</th>
            <th>損益（不含費）</th><th>損益（含費）</th><th>停利價</th><th>停損價</th>
            <th>距停利</th><th>距停損</th><th>進場原因</th><th></th>
          </tr></thead>
          <tbody>
            ${positions.map(p => `<tr>
              <td><strong>${p.ticker}</strong><br><span style="font-size:11px;color:var(--text-muted)">${p.name}</span></td>
              <td>${p.shares}</td>
              <td>NT$ ${p.avg_cost?.toFixed(2)}</td>
              <td>${p.price_error
                ? `<span style="color:var(--danger);font-size:11px">⚠ 報價異常</span>`
                : `NT$ ${p.current_price?.toFixed(2)}${p.price_stale
                    ? `<br><span style="font-size:10px;color:var(--warning)" title="資料來源尚未更新今日收盤價">⚠ ${p.price_date} 資料</span>`
                    : ''}`
              }</td>
              <td class="${p.pnl>=0?'positive':'negative'}">${p.pnl!=null ? p.pnl_pct?.toFixed(2)+'%' : '—'}<br>
                <span style="font-size:11px">${p.pnl!=null ? (p.pnl>=0?'+':'')+'NT$ '+p.pnl?.toLocaleString() : ''}</span></td>
              <td class="${(p.pnl_net??p.pnl)>=0?'positive':'negative'}">${p.pnl_net!=null ? (p.pnl_net_pct??p.pnl_pct)?.toFixed(2)+'%' : '—'}<br>
                <span style="font-size:11px">${p.pnl_net!=null ? ((p.pnl_net>=0?'+':'')+'NT$ '+(p.pnl_net??p.pnl)?.toLocaleString()) : ''}</span></td>
              <td style="color:var(--success)">NT$ ${p.limit_sell?.toFixed(2)}</td>
              <td style="color:var(--danger)">NT$ ${p.stop_loss?.toFixed(2)}</td>
              <td class="${p.distance_to_tp_pct>0?'positive':'negative'}">${p.distance_to_tp_pct!=null ? p.distance_to_tp_pct?.toFixed(1)+'%' : '—'}</td>
              <td class="positive">${p.distance_to_sl_pct!=null ? p.distance_to_sl_pct?.toFixed(1)+'%' : '—'}</td>
              <td style="font-size:11px;color:var(--text-muted)">${p.entry_reason || '—'}</td>
              <td><button class="btn btn-outline" style="font-size:11px;padding:3px 8px;color:var(--warning);border-color:var(--warning)"
                onclick="cancelPosition('${p.ticker}','${p.name}',${p.shares * (p.avg_cost||0) + (p.fee_paid||0)})">撤銷</button></td>
            </tr>`).join('')}
          </tbody>
        </table>` :
        `<p style="color:var(--text-muted);padding:20px 0">目前無持倉。系統會在資料更新後自動掃描並下單。</p>`}
    </div>

    <!-- Filled order log -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">📋 成交紀錄</div>
        <span style="font-size:12px;color:var(--text-muted)">${filled.length} 筆</span>
      </div>
      <div id="orders-table-wrap">${renderOrdersTable()}</div>
    </div>
  `;
}

function renderOrdersTable() {
  const filled = autoOrdersData;
  if (!filled.length) {
    return `<p style="color:var(--text-muted);padding:20px 0">尚無成交紀錄。</p>`;
  }

  const totalPages = Math.max(1, Math.ceil(filled.length / ORDERS_PAGE_SIZE));
  autoOrdersPage = Math.min(Math.max(1, autoOrdersPage), totalPages);
  const start = (autoOrdersPage - 1) * ORDERS_PAGE_SIZE;
  const pageItems = filled.slice(start, start + ORDERS_PAGE_SIZE);

  return `
    <table class="bt-table">
      <thead><tr>
        <th>日期</th><th>代號</th><th>動作</th><th>股數</th><th>成交價</th>
        <th>金額</th><th>手續費</th><th>損益</th><th>原因</th>
      </tr></thead>
      <tbody>
        ${pageItems.map(t => `<tr>
          <td>${t.date}</td>
          <td><strong>${t.ticker}</strong></td>
          <td><span class="badge badge-${t.action==='buy'?'buy':'sell'}">${t.action==='buy'?'買入':'賣出'}</span></td>
          <td>${t.shares}</td>
          <td>NT$ ${t.price?.toFixed(2)}</td>
          <td>NT$ ${t.amount?.toLocaleString()}</td>
          <td style="color:var(--danger)">NT$ ${t.fee?.toFixed(0)}</td>
          <td class="${(t.pnl||0)>=0?'positive':'negative'}">
            ${t.pnl != null ? (t.pnl>=0?'+':'')+t.pnl.toLocaleString()+'元<br>'+(t.pnl_pct?.toFixed(2))+'%' : '—'}
          </td>
          <td style="font-size:11px;color:var(--text-muted)">${t.reason || '—'}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    ${renderOrdersPager(totalPages)}
  `;
}

function renderOrdersPager(totalPages) {
  if (totalPages <= 1) return '';
  const cur = autoOrdersPage;
  const pages = [];
  if (totalPages <= 7) {
    for (let p = 1; p <= totalPages; p++) pages.push(p);
  } else {
    pages.push(1);
    if (cur > 3) pages.push('…');
    for (let p = Math.max(2, cur - 1); p <= Math.min(totalPages - 1, cur + 1); p++) pages.push(p);
    if (cur < totalPages - 2) pages.push('…');
    pages.push(totalPages);
  }

  const btn = (label, page, disabled, active) => `
    <button class="btn btn-outline" style="font-size:12px;padding:4px 10px;${active ? 'border-color:var(--primary);color:var(--primary)' : ''}"
      ${disabled ? 'disabled' : `onclick="changeOrdersPage(${page})"`}>${label}</button>`;

  return `
    <div style="display:flex;justify-content:center;align-items:center;gap:6px;margin-top:12px;flex-wrap:wrap">
      ${btn('‹ 上一頁', cur - 1, cur <= 1, false)}
      ${pages.map(p => p === '…'
        ? `<span style="padding:4px 6px;color:var(--text-muted)">…</span>`
        : btn(p, p, false, p === cur)
      ).join('')}
      ${btn('下一頁 ›', cur + 1, cur >= totalPages, false)}
    </div>`;
}

function changeOrdersPage(page) {
  autoOrdersPage = page;
  document.getElementById('orders-table-wrap').innerHTML = renderOrdersTable();
}

async function autoInit() {
  const capital          = parseFloat(document.getElementById('auto-capital')?.value || 100000);
  const per_stock_budget = parseFloat(document.getElementById('auto-budget')?.value || 10000);
  const r = await fetch(`${API}/api/auto/init`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({capital, per_stock_budget}),
  });
  const d = await r.json();
  showToast(d.message, 'success');
  await refreshAutoPage();
}

async function cancelPosition(ticker, name, refundAmt) {
  if (!confirm(`撤銷 ${ticker} ${name}？\n將退回約 NT$ ${refundAmt.toFixed(0)}（今日買入紀錄也會刪除）`)) return;
  try {
    const r = await fetch(`${API}/api/auto/cancel/${ticker}`, { method: 'POST' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.statusText);
    showToast(`已撤銷 ${ticker}，退回 NT$ ${d.refund?.toLocaleString()}`, 'success');
    await refreshAutoPage();
  } catch (e) {
    showToast('撤銷失敗：' + e.message, 'error');
  }
}

async function autoReset() {
  if (!confirm('確定重置自動交易？所有持倉和紀錄將清空。')) return;
  let capital = 100000, per_stock_budget = 10000;
  try {
    const s = await fetch(`${API}/api/auto/status`).then(r => r.json());
    if (s.initialized) {
      capital = s.initial_capital ?? capital;
      per_stock_budget = s.per_stock_budget ?? per_stock_budget;
    }
  } catch {}
  await fetch(`${API}/api/auto/init`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({capital, per_stock_budget}),
  });
  showToast('自動交易已重置', 'success');
  await refreshAutoPage();
}

function renderEquityChart(history) {
  const canvas = document.getElementById('equity-chart');
  if (!canvas) return;
  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: history.map(h => h.date),
      datasets: [
        { label: '總資產', data: history.map(h => h.equity),
          borderColor: '#58a6ff', borderWidth: 2, pointRadius: 0, fill: true,
          backgroundColor: '#58a6ff18' },
        { label: '現金',   data: history.map(h => h.cash),
          borderColor: '#8b949e', borderWidth: 1, pointRadius: 0, fill: false,
          borderDash: [4,4] },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: {mode:'index', intersect:false},
      plugins: { legend: { labels: {color:'#8b949e', font:{size:11}} } },
      scales: {
        x: { ticks: {color:'#8b949e', maxTicksLimit:8, font:{size:10}}, grid:{color:'#21262d'} },
        y: { ticks: {color:'#8b949e', font:{size:10}}, grid:{color:'#21262d'} },
      },
    },
  });
}

// ── Pages / Tabs ──────────────────────────────────────────────────────────────
function showPage(page) {
  ['welcome', 'analysis', 'settings', 'auto', 'full-backtest', 'scan'].forEach(p => {
    const el = document.getElementById(`page-${p}`);
    if (el) el.style.display = p === page ? '' : 'none';
  });
  document.querySelectorAll('.nav-item[data-page]').forEach(el =>
    el.classList.toggle('active', el.dataset.page === page));
}


function switchTab(tab) {
  const all = ['chart', 'signals', 'fundamental', 'backtest', 'simulation', 'ai'];
  all.forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    if (el) el.style.display = t === tab ? '' : 'none';
  });
  document.querySelectorAll('#tabs .tab').forEach((el, i) => {
    el.classList.toggle('active', all[i] === tab);
  });
  // Lazy-load simulation when tab is opened
  if (tab === 'simulation') loadSimulation();
  // Lazy-load related news (once per ticker)
  if (tab === 'fundamental' && newsLoadedFor !== currentTicker) {
    newsLoadedFor = currentTicker;
    loadNews(currentTicker);
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatMarketCap(v) {
  if (v >= 1e12) return (v / 1e12).toFixed(2) + ' 兆';
  if (v >= 1e8)  return (v / 1e8).toFixed(2)  + ' 億';
  return v.toLocaleString();
}

function showToast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast show ${type}`;
  setTimeout(() => el.classList.remove('show'), 4000);
}
