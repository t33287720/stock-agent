/* =========================================================
   個股分析頁 — 「模擬交易」分頁
   與「自動交易總覽頁」(pages/auto-trade.js) 共用同一組後端投資組合，
   呼叫 API：GET /api/auto/status、/orders、POST /api/auto/init、/trade
   ========================================================= */

// ── Portfolio tab (unified auto_trade portfolio) ──────────────────────────────
// 載入「模擬交易」分頁的投資組合狀態（與自動交易系統共用同一組資料）
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

// 渲染尚未初始化投資組合時的畫面（輸入初始資金並開始）
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

// 渲染投資組合總覽：最新訊號、資產指標、持倉明細、最近交易紀錄
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

// 呼叫後端以指定的初始資金／每股投入金額初始化投資組合
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

// 重置投資組合（沿用原本的資金設定，二次確認後清空持倉與紀錄）
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

// 依目前股票的最新訊號自動判斷買入或賣出
async function simAutoTrade() {
  if (!currentTicker) return;
  await _simTrade('auto');
}
// 手動買入目前股票（不看訊號，直接以現價買入）
async function simManualBuy() {
  if (!currentTicker) return;
  await _simTrade('buy');
}
// 手動賣出目前股票（不看訊號，直接以現價賣出）
async function simManualSell() {
  if (!currentTicker) return;
  await _simTrade('sell');
}

// 送出模擬交易請求並刷新投資組合畫面，供 simAutoTrade/simManualBuy/simManualSell 共用
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
