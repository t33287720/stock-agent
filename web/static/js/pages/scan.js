/* =========================================================
   今日訊號掃描頁
   呼叫 API：GET /api/scan/today、/api/scan/ai-progress、POST /api/scan/ai-retry
   結果由控制區背景排程 (backend/control/scheduler.py) 自動產生，本頁只讀取。
   scanRow() 重用 pages/ai-analysis.js 的 renderStepBody，故本檔案需在其後載入。
   ========================================================= */

// ── 今日訊號掃描 ──────────────────────────────────────────────────────────────
// 顯示今日訊號掃描頁，載入背景排程自動產生的最新掃描結果
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
    const [r, progR] = await Promise.all([
      fetch(`${API}/api/scan/today`),
      fetch(`${API}/api/scan/ai-progress`),
    ]);
    const data = await r.json();
    const progress = await progR.json().catch(() => null);
    if (data.cached && (data.buy_candidates?.length || data.sell_candidates?.length)) {
      renderScanResult(data, progress);
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

// 渲染買入/賣出候選清單表格，含統計列與 AI 分析進度
function renderScanResult(data, progress) {
  const el = document.getElementById('scan-result');
  const { buy_candidates: buys = [], sell_candidates: sells = [],
          scanned = 0, scan_time = '', errors = [] } = data;

  const aiProgressHtml = progress?.total
    ? `<div style="background:var(--surface2);border-radius:8px;padding:8px 14px;display:flex;gap:8px;align-items:center">
        <span>🤖</span><div><div style="font-size:10px;color:var(--text-muted)">AI 分析進度</div>
        <div style="font-weight:700;font-size:14px">${progress.done} / ${progress.total}</div></div>
      </div>
      <button id="btn-ai-retry" onclick="retryAiAnalysis()" ${progress.running ? 'disabled' : ''}
        style="padding:8px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface2);
        color:var(--text-secondary);cursor:${progress.running ? 'default' : 'pointer'};font-size:12px">
        ${progress.running ? '⏳ 重新分析中...' : '🔄 重新分析失敗項目'}
      </button>`
    : '';

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
      ${aiProgressHtml}
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
              ${aiEnriched ? '<th style="padding:8px;text-align:center">AI 分析</th>' : ''}
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

  if (progress?.running) _pollAiRetry();
}

let _aiRetryPoll = null;

// 觸發後端重新分析今日掃描候選股中先前失敗的項目，並開始輪詢進度
async function retryAiAnalysis() {
  const btn = document.getElementById('btn-ai-retry');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 重新分析中...'; }
  try {
    await fetch(`${API}/api/scan/ai-retry`, { method: 'POST' });
  } catch {}
  _pollAiRetry();
}

// 每 5 秒輪詢一次 AI 重新分析進度，完成或頁面關閉時自動停止
function _pollAiRetry() {
  if (_aiRetryPoll) return;
  _aiRetryPoll = setInterval(async () => {
    if (!document.getElementById('scan-result')) {
      clearInterval(_aiRetryPoll);
      _aiRetryPoll = null;
      return;
    }
    try {
      const [r, progR] = await Promise.all([
        fetch(`${API}/api/scan/today`),
        fetch(`${API}/api/scan/ai-progress`),
      ]);
      const data = await r.json();
      const progress = await progR.json();
      if (!progress.running) {
        clearInterval(_aiRetryPoll);
        _aiRetryPoll = null;
      }
      renderScanResult(data, progress);
    } catch {}
  }, 5000);
}

// 渲染掃描候選清單中的單一股票列（技術指標欄位 + 可展開的 AI 分析詳情）
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
    const v = s.ai_verdict;
    const verdictCls = { '偏多': 'badge-buy', '中性': 'badge-hold', '偏空': 'badge-sell' }[v] || '';
    const c = s.ai_confidence;
    const cColor = c == null ? 'var(--text-muted)' : c >= 70 ? '#3fb950' : c >= 40 ? '#e3b341' : '#f85149';
    const summary = escapeHtml(s.ai_summary || '');
    const reasons = s.ai_key_reasons || [];
    const risks = s.ai_risks || [];
    const trace = s.ai_trace || [];
    const newsList = s.ai_news || [];

    const newsHtml = newsList.length ? `
        <div style="font-size:10px;margin-top:4px"><b>新聞來源：</b>
          <div style="margin-top:2px;display:flex;flex-direction:column;gap:2px">
            ${newsList.map(n => `<a href="${escapeHtml(n.url || '#')}" target="_blank" rel="noopener noreferrer"
                style="font-size:10px;color:var(--accent,#58a6ff);text-decoration:none;white-space:normal">${escapeHtml(n.title || '')}</a>`).join('')}
          </div>
        </div>` : '';

    const traceHtml = trace.length ? `
        <details style="margin-top:4px">
          <summary style="cursor:pointer;color:var(--text-muted);font-size:10px">🔬 完整流程（${trace.length} 步）</summary>
          <div style="display:flex;flex-direction:column;gap:6px;margin-top:6px">
            ${trace.map((step, i) => `
            <details style="border:1px solid var(--border);border-radius:6px;padding:6px 8px">
              <summary style="font-size:10px;font-weight:600;cursor:pointer">步驟 ${i + 1}：${escapeHtml(step.label)}</summary>
              <div style="margin-top:6px">${renderStepBody(step)}</div>
            </details>`).join('')}
          </div>
        </details>` : '';

    aiCell = `
      <td style="padding:8px;text-align:center;max-width:220px">
        ${v
          ? `<span class="badge ${verdictCls}" style="font-size:10px">${escapeHtml(v)}</span>
             <span style="color:${cColor};font-weight:700;margin-left:4px">${c ?? '—'}%</span>`
          : `<span style="color:var(--text-muted);font-size:11px">分析中...</span>`}
        ${summary ? `<div style="font-size:10px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px" title="${summary}">${summary}</div>` : ''}
        ${v ? `
        <details style="margin-top:4px;text-align:left">
          <summary style="cursor:pointer;color:var(--text-muted);font-size:10px">詳細</summary>
          <div style="margin-top:4px">
            ${reasons.length ? `<div style="font-size:10px;margin-bottom:4px"><b>理由：</b><ul style="margin:2px 0 0 14px;padding:0">${reasons.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul></div>` : ''}
            ${risks.length ? `<div style="font-size:10px;color:var(--warning);margin-bottom:4px"><b>風險：</b><ul style="margin:2px 0 0 14px;padding:0">${risks.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul></div>` : ''}
            ${newsHtml}
            ${traceHtml}
          </div>
        </details>` : ''}
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
