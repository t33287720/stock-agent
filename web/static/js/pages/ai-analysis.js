/* =========================================================
   個股分析頁 — 「AI 分析」分頁
   呼叫 API：POST /api/stock/{ticker}/ai-analysis（NDJSON 串流）
   這裡定義的 renderStepBody / formatStepResponse / renderLiveStep
   也被 pages/chat.js、pages/scan.js 重用，故本檔案需在它們之前載入。
   ========================================================= */

// 渲染 AI 分析分頁的初始畫面（尚未執行分析，顯示「產生 AI 分析」按鈕）
function renderAiTabPlaceholder() {
  return `<div class="card">
    <div class="card-header">
      <div class="card-title">🤖 AI 分析</div>
      <button class="btn btn-primary" id="ai-run-btn" onclick="runAiAnalysis(false)">▶ 產生 AI 分析</button>
    </div>
    <p style="font-size:11px;color:var(--text-muted);margin-bottom:12px">
      由本機 LLM 根據技術指標、基本面與相關新聞產生分析，過程中可能自行延伸搜尋查證（最多 10 輪），並經第二次驗證以降低幻覺風險。結果快取 1 小時，可即時觀看分析過程，總時間可能較長。
    </p>
    <div id="ai-result">
      <div class="loading" style="padding:40px 0;color:var(--text-muted)">點擊「產生 AI 分析」開始</div>
    </div>
  </div>`;
}

// 呼叫後端串流 API 執行 ReAct AI 分析，即時把每個步驟插入畫面，完成後渲染最終結果
async function runAiAnalysis(force = false) {
  if (!currentTicker) return;
  const el  = document.getElementById('ai-result');
  const btn = document.getElementById('ai-run-btn');
  if (btn) btn.disabled = true;
  el.innerHTML = `<div class="loading"><div class="spinner"></div> 準備中...</div>`;

  let stepCount = 0;
  try {
    const r = await fetch(`${API}/api/stock/${currentTicker}/ai-analysis?force=${force}`, { method: 'POST' });
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;
        const evt = JSON.parse(line);

        if (evt.type === 'step_start') {
          stepCount++;
          if (stepCount === 1) el.innerHTML = '';
          el.insertAdjacentHTML('beforeend', renderLiveStep(evt.step, stepCount));
        } else if (evt.type === 'step_done') {
          const card = document.getElementById(`ai-live-step-${stepCount}`);
          if (card) card.outerHTML = renderLiveStep(evt.step, stepCount);
        } else if (evt.type === 'result') {
          el.innerHTML = renderAiResult(evt.result);
          if (btn) {
            btn.textContent = '🔄 重新產生';
            btn.onclick = () => runAiAnalysis(true);
          }
        }
      }
    }
  } catch (e) {
    el.innerHTML = `<div class="loading">AI 分析失敗：${e.message}</div>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

// 把 LLM/工具回應轉成一句人話，取代原始 JSON（依常見回應欄位判斷格式，未知格式才逐欄位列出）
function formatStepResponse(step) {
  const r = step.response;
  if (r == null) return '<span style="color:var(--danger)">⚠ 無回應</span>';
  if (typeof r !== 'object' || Array.isArray(r)) return escapeHtml(String(r));

  if ('need_search' in r) {
    return r.need_search
      ? `需要再搜尋關鍵字：「${escapeHtml(r.search_query || '')}」`
      : '目前資料已足夠，不需要再搜尋';
  }
  if ('results' in r && 'query' in r) {
    const n = (r.results || []).length;
    return n ? `找到 ${n} 筆搜尋結果` : '查無搜尋結果';
  }
  if ('queries' in r) {
    const qs = (r.queries || []).filter(Boolean);
    return qs.length ? `辨識出股票關鍵字：${qs.map(escapeHtml).join('、')}` : '這個問題沒有提到特定股票';
  }
  if ('resolved' in r) {
    return r.resolved ? `解析為：${escapeHtml(r.resolved)}` : escapeHtml(r.note || '找不到符合的股票');
  }
  if ('reply' in r) return escapeHtml(r.reply).replace(/\n/g, '<br>');
  if ('verdict' in r) {
    const reasons = (r.key_reasons || []).map(escapeHtml).join('；');
    return `判斷：${escapeHtml(r.verdict)}（信心 ${r.confidence ?? '—'}%）`
      + (reasons ? `<br>理由：${reasons}` : '')
      + (r.summary ? `<br>${escapeHtml(r.summary)}` : '');
  }
  if ('error' in r) return `<span style="color:var(--danger)">⚠ ${escapeHtml(r.error)}</span>`;
  if ('summary' in r) return escapeHtml(r.summary);

  return Object.entries(r).map(([k, v]) =>
    `${escapeHtml(k)}：${escapeHtml(typeof v === 'object' ? JSON.stringify(v) : String(v))}`).join('<br>');
}

// 顯示單一流程步驟的結果：只用一句人話總結 AI 決定/查到了什麼，不顯示原始 prompt（步驟標題本身已說明在做什麼）
function renderStepBody(step) {
  if (step.response === undefined) {
    const pendingText = step.label.includes('SearXNG') ? '搜尋中...' : 'LLM 運算中...';
    return `<div style="display:flex;align-items:center;gap:8px;font-size:12px;color:var(--text-muted)"><div class="spinner" style="width:14px;height:14px"></div> ${pendingText}</div>`;
  }
  return `<div style="font-size:12px;line-height:1.6">${formatStepResponse(step)}</div>`;
}

// 即時流程卡片：分析進行中即時插入/更新
function renderLiveStep(step, index) {
  return `<div id="ai-live-step-${index}" style="border:1px solid var(--border);border-radius:6px;padding:5px 8px;margin-bottom:5px">
    <div style="font-size:12px;font-weight:600;margin-bottom:3px">步驟 ${index}：${escapeHtml(step.label)}</div>
    ${renderStepBody(step)}
  </div>`;
}

// 渲染 AI 分析最終結果：判斷、信心度、支持理由、風險提示、新聞來源與完整流程
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
    ${data.extra_searches?.length ? `
    <div style="margin-bottom:14px">
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">🔍 AI 延伸查證</div>
      <div style="display:flex;flex-direction:column;gap:10px">
        ${data.extra_searches.map(s => `
        <div>
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">第 ${s.round} 輪・關鍵字：「${escapeHtml(s.query)}」${s.page > 1 ? `（第 ${s.page} 頁）` : ''}</div>
          ${s.results?.length ? `
          <div style="display:flex;flex-direction:column;gap:6px">
            ${s.results.map(n => `
              <a href="${escapeHtml(n.url || '#')}" target="_blank" rel="noopener noreferrer"
                 style="display:block;padding:8px 10px;border:1px solid var(--border);border-radius:6px;text-decoration:none;color:inherit;font-size:12px">
                <div style="font-weight:600">${escapeHtml(n.title || '')}</div>
                <div style="color:var(--text-muted);font-size:10px;margin-top:4px">${escapeHtml(n.source || '')}${n.date ? ' · ' + escapeHtml(n.date) : ''}</div>
              </a>`).join('')}
          </div>` : `<div style="font-size:11px;color:var(--text-muted)">查無結果</div>`}
        </div>`).join('')}
      </div>
    </div>` : ''}
    ${data.trace?.length ? `
    <details style="margin-bottom:14px">
      <summary style="font-size:12px;color:var(--text-muted);cursor:pointer">🔬 顯示完整流程（送給 LLM 的 prompt 與回應）</summary>
      <div style="display:flex;flex-direction:column;gap:5px;margin-top:6px">
        ${data.trace.map((step, i) => `
        <details style="border:1px solid var(--border);border-radius:6px;padding:5px 8px">
          <summary style="font-size:12px;font-weight:600;cursor:pointer">步驟 ${i + 1}：${escapeHtml(step.label)}</summary>
          <div style="margin-top:2px">${renderStepBody(step)}</div>
        </details>`).join('')}
      </div>
    </details>` : ''}
    <p style="font-size:11px;color:var(--text-muted);border-top:1px solid var(--border);padding-top:10px">
      ⚠️ AI 分析僅供參考，不構成投資建議
    </p>`;
}
