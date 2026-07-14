/* =========================================================
   策略歷史驗證頁（全組合回測，非單股回測）
   呼叫 API：POST /api/full-backtest
   ========================================================= */

// ── Full portfolio backtest ────────────────────────────────────────────────────
// 顯示策略歷史驗證頁（先渲染參數輸入表單）
async function showFullBacktestPage() {
  showPage('full-backtest');
  document.getElementById('fb-content').innerHTML = renderFBForm();
}

// 渲染策略歷史驗證的參數輸入表單（回測期間、初始資金、每股投入金額）
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

// 呼叫後端執行完整投資組合歷史回測（模擬每日自動掃描＋下單）
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

// 渲染歷史驗證結果：績效指標卡片 + 資產曲線容器 + 賣出交易明細表
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

// 繪製歷史驗證的資產曲線圖（資產／現金／初始資金三條線）
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
