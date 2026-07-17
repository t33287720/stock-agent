/* =========================================================
   全市場篩選頁
   呼叫 API：GET /api/market/screener（一次拿全市場 TWSE+TPEX 清單，
   前端 client-side 篩選）、POST /api/market/technical（只對篩選後的
   子集現算 RSI/KD，上限 150 支）。
   ========================================================= */

let marketStocks = [];       // 全市場原始清單（screener 回傳，只有價格/量/PE/PB/殖利率）
let marketFiltered = [];     // 目前篩選後的清單
let marketTechnical = {};    // ticker -> 技術指標 summary（按需計算）
const MARKET_DISPLAY_LIMIT = 500;
const MARKET_TECHNICAL_LIMIT = 150;

// 顯示全市場篩選頁，載入一次全市場清單
async function showMarketPage() {
  showPage('market');
  const el = document.getElementById('market-content');
  el.innerHTML = '<div class="loading"><div class="spinner"></div> 載入全市場清單中...</div>';
  try {
    const r = await fetch(`${API}/api/market/screener`);
    const data = await r.json();
    marketStocks = data.stocks || [];
    marketTechnical = {};
    el.innerHTML = renderMarketPage(data.fetched_at, data.count);
    applyMarketFilters();
  } catch (e) {
    el.innerHTML = `<div class="loading">載入失敗：${e.message}</div>`;
  }
}

// 渲染篩選表單 + 結果表格容器骨架
function renderMarketPage(fetchedAt, count) {
  return `
    <div class="card">
      <div class="card-header">
        <div class="card-title">🌐 全市場篩選（TWSE 上市 + TPEX 上櫃）</div>
        <span style="font-size:11px;color:var(--text-muted)">共 ${count ?? 0} 支 · 資料時間 ${fetchedAt ?? '—'}</span>
      </div>
      <p style="font-size:11px;color:var(--text-muted);margin-bottom:12px">
        價格／成交量／PE／PB／殖利率為全市場批次資料，載入後即時篩選；RSI／KD 等技術指標需要抓歷史 K 線，
        只對篩選後的子集（上限 ${MARKET_TECHNICAL_LIMIT} 支）現算，不會對全市場預先計算。
      </p>
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">代號／名稱關鍵字</label>
          <input type="text" id="mk-keyword" class="form-control" style="width:140px" placeholder="例如 台積電">
        </div>
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">PE 範圍</label>
          <div style="display:flex;gap:4px">
            <input type="number" id="mk-pe-min" class="form-control" style="width:70px" placeholder="最小">
            <input type="number" id="mk-pe-max" class="form-control" style="width:70px" placeholder="最大">
          </div>
        </div>
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">PB 範圍</label>
          <div style="display:flex;gap:4px">
            <input type="number" id="mk-pb-min" class="form-control" style="width:70px" placeholder="最小">
            <input type="number" id="mk-pb-max" class="form-control" style="width:70px" placeholder="最大">
          </div>
        </div>
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">殖利率 ≥ (%)</label>
          <input type="number" id="mk-yield-min" class="form-control" style="width:80px">
        </div>
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;color:var(--text-muted)">成交張數 ≥</label>
          <input type="number" id="mk-lots-min" class="form-control" style="width:90px" placeholder="例如 1000">
        </div>
        <button class="btn btn-primary" onclick="applyMarketFilters()">🔍 套用篩選</button>
        <button class="btn btn-outline" onclick="computeMarketTechnical()">📈 計算技術指標（RSI/KD）</button>
      </div>
    </div>
    <div id="market-result"></div>
  `;
}

// 依表單目前的值，對 marketStocks 做 client-side 篩選並重新渲染表格
function applyMarketFilters() {
  const keyword = document.getElementById('mk-keyword')?.value.trim().toLowerCase() || '';
  const peMin   = parseFloat(document.getElementById('mk-pe-min')?.value);
  const peMax   = parseFloat(document.getElementById('mk-pe-max')?.value);
  const pbMin   = parseFloat(document.getElementById('mk-pb-min')?.value);
  const pbMax   = parseFloat(document.getElementById('mk-pb-max')?.value);
  const yieldMin = parseFloat(document.getElementById('mk-yield-min')?.value);
  const lotsMin  = parseFloat(document.getElementById('mk-lots-min')?.value);

  marketFiltered = marketStocks.filter(s => {
    if (keyword && !s.ticker.toLowerCase().includes(keyword) && !(s.name || '').toLowerCase().includes(keyword)) return false;
    if (!isNaN(peMin) && !(s.pe >= peMin)) return false;
    if (!isNaN(peMax) && !(s.pe <= peMax)) return false;
    if (!isNaN(pbMin) && !(s.pb >= pbMin)) return false;
    if (!isNaN(pbMax) && !(s.pb <= pbMax)) return false;
    if (!isNaN(yieldMin) && !(s.div_yield >= yieldMin)) return false;
    if (!isNaN(lotsMin) && !(s.lots >= lotsMin)) return false;
    return true;
  });
  marketFiltered.sort((a, b) => (b.lots || 0) - (a.lots || 0));

  document.getElementById('market-result').innerHTML = renderMarketTable();
}

// 送出目前篩選後的清單給後端計算技術指標（RSI/KD等），完成後合併進表格欄位
async function computeMarketTechnical() {
  if (!marketFiltered.length) return;
  if (marketFiltered.length > MARKET_TECHNICAL_LIMIT) {
    showToast(`目前篩選出 ${marketFiltered.length} 支，超過上限 ${MARKET_TECHNICAL_LIMIT} 支，請先縮小篩選範圍`, 'error');
    return;
  }
  const el = document.getElementById('market-result');
  el.insertAdjacentHTML('afterbegin', `<div id="mk-tech-loading" class="loading"><div class="spinner"></div> 計算技術指標中（${marketFiltered.length} 支）...</div>`);
  try {
    const r = await fetch(`${API}/api/market/technical`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickers: marketFiltered.map(s => s.ticker) }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const data = await r.json();
    marketTechnical = { ...marketTechnical, ...data.results };
    el.innerHTML = renderMarketTable();
  } catch (e) {
    document.getElementById('mk-tech-loading')?.remove();
    showToast('計算失敗：' + e.message, 'error');
  }
}

// 渲染篩選結果表格（若已算過技術指標則多顯示 RSI/K/D/均線狀態欄位）
function renderMarketTable() {
  const rows = marketFiltered.slice(0, MARKET_DISPLAY_LIMIT);
  const hasTechnical = Object.keys(marketTechnical).length > 0;
  const truncatedNote = marketFiltered.length > MARKET_DISPLAY_LIMIT
    ? `<div style="font-size:11px;color:var(--text-muted);margin-bottom:8px">符合條件共 ${marketFiltered.length} 支，僅顯示前 ${MARKET_DISPLAY_LIMIT} 支（依成交張數排序）</div>`
    : '';

  return `
    <div class="card">
      <div class="card-header">
        <div class="card-title">篩選結果（${marketFiltered.length} 支）</div>
      </div>
      ${truncatedNote}
      <div style="overflow-x:auto">
        <table class="bt-table">
          <thead>
            <tr>
              <th>股票</th><th>市場</th><th>現價</th><th>成交張數</th>
              <th>PE</th><th>PB</th><th>殖利率</th>
              ${hasTechnical ? '<th>RSI</th><th>K/D</th><th>均線狀態</th>' : ''}
            </tr>
          </thead>
          <tbody>
            ${rows.length ? rows.map(s => marketRow(s, hasTechnical)).join('')
                          : `<tr><td colspan="${hasTechnical ? 10 : 7}" style="padding:24px;text-align:center;color:var(--text-muted)">無符合條件的股票</td></tr>`}
          </tbody>
        </table>
      </div>
    </div>`;
}

// 渲染單一股票列
function marketRow(s, hasTechnical) {
  const t = marketTechnical[s.ticker];
  let techCells = '';
  if (hasTechnical) {
    if (!t) {
      techCells = '<td colspan="3" style="text-align:center;color:var(--text-muted);font-size:11px">未計算</td>';
    } else if (t.error) {
      techCells = `<td colspan="3" style="text-align:center;color:var(--danger);font-size:11px">${escapeHtml(t.error)}</td>`;
    } else {
      const rsiColor = t.rsi < 30 ? '#3fb950' : t.rsi > 70 ? '#f85149' : 'var(--text-secondary)';
      techCells = `
        <td style="text-align:center;color:${rsiColor};font-weight:700">${t.rsi ?? '—'}</td>
        <td style="text-align:center;font-size:11px;color:var(--text-muted)">${t.k ?? '—'}/${t.d ?? '—'}</td>
        <td style="text-align:center">${t.golden_cross ? '<span style="color:#3fb950">黃金</span>' : '<span style="color:#f85149">死亡</span>'}</td>`;
    }
  }
  return `
    <tr>
      <td style="cursor:pointer" onclick="loadStock('${s.ticker}')" title="查看個股分析">
        <strong>${s.ticker}</strong><br><span style="font-size:11px;color:var(--text-muted)">${escapeHtml(s.name || '')}</span>
      </td>
      <td style="font-size:11px;color:var(--text-muted)">${s.market}</td>
      <td>${s.close?.toFixed(2) ?? '—'}</td>
      <td>${s.lots?.toLocaleString() ?? '—'}</td>
      <td>${s.pe ?? '—'}</td>
      <td>${s.pb ?? '—'}</td>
      <td>${s.div_yield != null ? s.div_yield + '%' : '—'}</td>
      ${techCells}
    </tr>`;
}
