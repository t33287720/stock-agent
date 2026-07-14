/* =========================================================
   自動交易總覽頁
   與個股分析頁的「模擬交易」分頁 (pages/simulation.js) 共用同一組後端投資組合，
   呼叫 API：GET /api/auto/status、/orders、/history、POST /api/auto/init、/cancel/{ticker}
   ========================================================= */

// ── Auto Trading ──────────────────────────────────────────────────────────────
// 顯示自動交易系統頁
async function showAutoPage() {
  showPage('auto');
  await refreshAutoPage();
}

// 重新載入自動交易系統的投資組合狀態、成交紀錄與資產曲線
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

// 渲染自動交易系統尚未初始化時的畫面（說明文字＋開始設定表單）
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

// 渲染自動交易總覽：資產指標、資產曲線、目前持倉、成交紀錄
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

// 依目前頁碼（autoOrdersPage）從 autoOrdersData 截取一頁成交紀錄並渲染表格
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

// 渲染成交紀錄的分頁按鈕（頁數多時中間以「…」省略）
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

// 切換成交紀錄目前頁碼並重新渲染表格
function changeOrdersPage(page) {
  autoOrdersPage = page;
  document.getElementById('orders-table-wrap').innerHTML = renderOrdersTable();
}

// 呼叫後端以指定的初始資金／每股投入金額初始化自動交易投資組合
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

// 撤銷指定持倉：退回買入金額並刪除今日買入紀錄（用於修正錯誤買入，需二次確認）
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

// 重置自動交易投資組合（沿用原本的資金設定，二次確認後清空持倉與紀錄）
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

// 繪製自動交易系統的資產曲線圖（總資產／現金兩條線）
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
