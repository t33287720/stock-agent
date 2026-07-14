/* =========================================================
   問股票聊天頁
   呼叫 API：POST /api/chat（NDJSON 串流）
   renderChatStep() 重用 pages/ai-analysis.js 的 renderStepBody，
   故本檔案需在其後載入。
   ========================================================= */

// ── Chat (問股票) ─────────────────────────────────────────────────────────────
let chatHistory = [];
let chatMsgCounter = 0;
let chatStarted = false;

// 顯示「問股票」聊天頁，首次進入時顯示歡迎提示
function showChatPage() {
  showPage('chat');
  if (!chatStarted) {
    chatStarted = true;
    document.getElementById('chat-messages').innerHTML =
      `<div class="chat-bubble assistant">👋 你好，我可以幫你查詢台股個股近況、技術面、基本面，或搜尋最新新聞。試試問我「台積電最近怎麼樣」。</div>`;
  }
  document.getElementById('chat-input')?.focus();
}

// 清空對話紀錄與畫面，重新開始一段新對話
function clearChat() {
  chatHistory = [];
  chatStarted = false;
  document.getElementById('chat-messages').innerHTML = '';
  showChatPage();
}

// 捲動聊天訊息區到最底部
function scrollChatToBottom() {
  const el = document.getElementById('chat-messages');
  if (el) el.scrollTop = el.scrollHeight;
}

// 附加一則純文字訊息泡泡（使用者訊息）
function appendChatBubble(role, text) {
  const wrap = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `chat-bubble ${role}`;
  div.textContent = text;
  wrap.appendChild(div);
  scrollChatToBottom();
  return div;
}

// 附加一個空的「處理步驟」容器，供這一輪對話即時插入 step_start/step_done 卡片
function appendChatStepsContainer(msgId) {
  const wrap = document.getElementById('chat-messages');
  const turn = document.createElement('div');
  turn.className = 'chat-turn';
  turn.id = `chat-turn-${msgId}`;
  turn.innerHTML = `<div class="chat-steps" id="chat-steps-${msgId}"></div>`;
  wrap.appendChild(turn);
  scrollChatToBottom();
  return document.getElementById(`chat-steps-${msgId}`);
}

// 渲染單一處理步驟卡片（重用個股 AI 分析的 renderStepBody，外層改用不衝突的 id 命名）
function renderChatStep(step, msgId, stepIdx) {
  return `<div id="chat-step-${msgId}-${stepIdx}" class="chat-step">
    <div class="chat-step-label">${escapeHtml(step.label)}</div>
    ${renderStepBody(step)}
  </div>`;
}

// 串流結束、拿到最終回覆後，把處理步驟收合成「顯示完整流程」，並渲染助理回覆泡泡
function finalizeChatResult(msgId, result) {
  const turn = document.getElementById(`chat-turn-${msgId}`);
  if (!turn) return;

  const tickerLinks = (result.used_tickers || []).map(t => `
    <button class="btn btn-outline" style="font-size:11px;padding:2px 8px;margin-top:6px;margin-right:6px"
      onclick="loadStock('${t.ticker}')">📈 ${escapeHtml(t.name)}（${t.ticker}）圖表</button>`).join('');

  const verifyBadge = result.verified === true
    ? '<span style="color:var(--success);font-size:11px">✓ 已二次驗證</span>'
    : result.verified === false
      ? '<span style="color:var(--warning);font-size:11px">⚠ 未通過二次驗證（僅供初步參考）</span>'
      : '';

  const sourcesHtml = result.sources?.length ? `
    <div style="margin-top:8px">
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">參考資料來源</div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${result.sources.map(n => `
          <a href="${escapeHtml(n.url || '#')}" target="_blank" rel="noopener noreferrer"
             style="display:block;padding:6px 8px;border:1px solid var(--border);border-radius:6px;text-decoration:none;color:inherit;font-size:11px">
            <div style="font-weight:600">${escapeHtml(n.title || '')}</div>
            <div style="color:var(--text-muted);font-size:10px;margin-top:2px">${escapeHtml(n.source || '')}${n.date ? ' · ' + escapeHtml(n.date) : ''}</div>
          </a>`).join('')}
      </div>
    </div>` : '';

  const traceHtml = result.trace?.length ? `
    <details style="margin-top:6px">
      <summary style="font-size:11px;color:var(--text-muted);cursor:pointer">🔬 顯示完整流程（${result.trace.length} 步）</summary>
      <div style="display:flex;flex-direction:column;gap:5px;margin-top:5px">
        ${result.trace.map((step, i) => `
        <details style="border:1px solid var(--border);border-radius:6px;padding:5px 8px">
          <summary style="font-size:11px;font-weight:600;cursor:pointer">步驟 ${i + 1}：${escapeHtml(step.label)}</summary>
          <div style="margin-top:2px">${renderStepBody(step)}</div>
        </details>`).join('')}
      </div>
    </details>` : '';

  turn.innerHTML = `
    <div class="chat-bubble assistant">
      ${escapeHtml(result.reply).replace(/\n/g, '<br>')}
      ${verifyBadge ? `<div style="margin-top:6px">${verifyBadge}</div>` : ''}
      ${tickerLinks ? `<div>${tickerLinks}</div>` : ''}
      ${sourcesHtml}
      ${traceHtml}
    </div>`;
  scrollChatToBottom();
}

// 串流過程中發生連線錯誤時，把處理步驟換成錯誤訊息
function finalizeChatError(msgId, message) {
  const turn = document.getElementById(`chat-turn-${msgId}`);
  if (turn) turn.innerHTML = `<div class="chat-bubble assistant" style="color:var(--danger)">發生錯誤：${escapeHtml(message)}</div>`;
  scrollChatToBottom();
}

// 送出使用者輸入的問題，以 NDJSON 串流即時顯示處理步驟，完成後顯示回覆並更新對話歷史
async function sendChatMessage() {
  const input = document.getElementById('chat-input');
  const message = input.value.trim();
  if (!message) return;
  input.value = '';

  appendChatBubble('user', message);
  const historyForRequest = chatHistory.slice();
  chatHistory.push({ role: 'user', content: message });

  const msgId = ++chatMsgCounter;
  const stepsWrap = appendChatStepsContainer(msgId);
  let stepCount = 0;

  try {
    const r = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ history: historyForRequest, message }),
    });
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
          stepsWrap.insertAdjacentHTML('beforeend', renderChatStep(evt.step, msgId, stepCount));
          scrollChatToBottom();
        } else if (evt.type === 'step_done') {
          const card = document.getElementById(`chat-step-${msgId}-${stepCount}`);
          if (card) card.outerHTML = renderChatStep(evt.step, msgId, stepCount);
        } else if (evt.type === 'result') {
          chatHistory.push({ role: 'assistant', content: evt.result.reply });
          finalizeChatResult(msgId, evt.result);
        }
      }
    }
  } catch (e) {
    finalizeChatError(msgId, e.message);
  }
}
