/* =========================================================
   首頁 — 左側股票列表 + 執行狀況列表
   呼叫 API：GET /api/top100、GET /api/scan/calendar
   依賴 core.js 的全域函式（loadStock 在 stock-detail.js 定義）。
   ========================================================= */

// ── Stock list ────────────────────────────────────────────────────────────────
// 載入左側股票列表（依成交量排序的前 100 支台股）
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

// 渲染左側股票列表 HTML（含收盤價與成交張數）
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
  `).join('') + '<div id="stock-search-empty" class="stock-search-empty" style="display:none"></div>';
  // 重新整理列表後沿用搜尋框目前的關鍵字，避免清單與搜尋框內容不一致
  applyStockFilter();
}

// 依搜尋框關鍵字（代號或名稱，不分大小寫）過濾股票列表；無符合結果時顯示空狀態提示
function applyStockFilter() {
  const input = document.getElementById('search');
  const raw = input ? input.value.trim() : '';
  const q = raw.toLowerCase();
  let shown = 0;
  document.querySelectorAll('.stock-item').forEach(el => {
    const match = el.dataset.ticker.toLowerCase().includes(q) || el.dataset.name.toLowerCase().includes(q);
    el.style.display = match ? '' : 'none';
    if (match) shown++;
  });
  const empty = document.getElementById('stock-search-empty');
  if (!empty) return;
  if (q && shown === 0) {
    empty.innerHTML = `找不到符合「${escapeHtml(raw)}」的股票<br>` +
      '<span style="font-size:11px">列表僅含成交量前 100 大，可改用代號或名稱的一部分搜尋</span>';
    empty.style.display = '';
  } else {
    empty.style.display = 'none';
  }
}

// 綁定左側搜尋框，依代號或名稱即時過濾股票列表
function setupSearch() {
  document.getElementById('search').addEventListener('input', applyStockFilter);
}

// ── Run log (首頁執行狀況列表) ──────────────────────────────────────────────────
// 呼叫 /api/scan/calendar 取得最近 30 天的執行狀況並渲染
async function loadRunLog() {
  const el = document.getElementById('run-log-list');
  if (!el) return;
  try {
    const r = await fetch(`${API}/api/scan/calendar?days=30`);
    const data = await r.json();
    renderRunLog(data.days || []);
  } catch {
    el.innerHTML = '<div style="padding:20px;color:var(--danger)">無法連線後端</div>';
  }
}

// 依階段種類（data/scan/ai）與狀態值決定圓點顏色：灰＝未執行、黃＝執行中、綠＝完成、紅＝異常
function _runDotClass(kind, status) {
  if (!status) return 'gray';
  if (status === 'running') return 'yellow';
  if (kind === 'data') return status === 'ok' ? 'green' : 'red';
  return status === 'done' ? 'green' : 'red';
}

// 將多行文字組合成 tooltip 用的 data-tip 屬性字串（過濾空值、跳脫特殊字元）
function _runTip(lines) {
  return lines.filter(Boolean).join('\n')
    .replace(/"/g, '&quot;').replace(/\n/g, '&#10;');
}

// 渲染執行狀況列表：每天一列，四個階段各顯示一個狀態圓點，非交易日整列淡化
function renderRunLog(days) {
  const el = document.getElementById('run-log-list');
  if (!days.length) {
    el.innerHTML = '<div style="padding:20px;color:var(--text-muted);text-align:center">尚無執行紀錄</div>';
    return;
  }

  const phaseDot = (kind, label, obj) => {
    const cls = _runDotClass(kind, obj.status);
    let tipLines;
    if (kind === 'data') {
      tipLines = [
        `資料日期：${obj.data_date || '—'}`,
        cls === 'red' ? `⚠ 抓到的資料仍是 ${obj.data_date}，尚未更新到當天` : null,
      ];
    } else if (kind === 'ai') {
      tipLines = [
        obj.total_count != null ? `進度：${obj.done_count ?? 0} / ${obj.total_count}` : null,
        obj.started_at ? `開始：${obj.started_at.replace('T', ' ').slice(0, 16)}` : null,
        obj.done_at ? `完成：${obj.done_at.replace('T', ' ').slice(0, 16)}` : null,
        obj.error ? `⚠ ${obj.error}` : null,
      ];
    } else {
      tipLines = [
        obj.started_at ? `開始：${obj.started_at.replace('T', ' ').slice(0, 16)}` : null,
        obj.done_at ? `完成：${obj.done_at.replace('T', ' ').slice(0, 16)}` : null,
        obj.error ? `⚠ ${obj.error}` : null,
      ];
    }
    const tipText = _runTip(tipLines);
    return `
      <div class="run-log-phase">
        <span class="phase-label">${label}</span>
        <span class="run-dot ${cls}${tipText ? ' tip' : ''}" ${tipText ? `data-tip="${tipText}"` : ''}></span>
      </div>`;
  };

  el.innerHTML = days.map(d => `
    <div class="run-log-row${d.is_trading_day ? '' : ' muted'}">
      <div class="run-log-date">${d.date}（${d.weekday}）</div>
      <div class="run-log-phases">
        ${phaseDot('data', '資料', d.data)}
        ${phaseDot('scan', '訊號掃描', d.scan)}
        ${phaseDot('ai', 'AI分析', d.ai)}
      </div>
      ${!d.is_trading_day ? '<div style="font-size:11px;color:var(--text-muted)">非交易日</div>' : ''}
    </div>
  `).join('');
}
