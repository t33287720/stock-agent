/* =========================================================
   個股分析頁 — 「回測」分頁（單股歷史回測，非全組合）
   呼叫 API：POST /api/backtest/{ticker}
   ========================================================= */

// 渲染單股回測分頁的初始畫面（含手續費開關與「開始回測」按鈕）
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

// 呼叫後端對目前股票執行單股歷史回測
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

// 渲染單股回測結果：績效指標卡片 + 逐筆進出場明細表
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
