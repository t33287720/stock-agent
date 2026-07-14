/* =========================================================
   策略設定頁
   呼叫 API：GET / PUT /api/config
   ========================================================= */

// ── Settings ──────────────────────────────────────────────────────────────────
// 顯示策略設定頁，並把後端目前設定值填入各輸入欄位
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
    document.getElementById('ai-min-confidence-buy').value = cfg.strategy.ai_min_confidence_buy ?? 50;
    document.getElementById('ai-min-confidence-sell').value = cfg.strategy.ai_min_confidence_sell ?? 60;
  } catch (e) {
    showToast('無法連線後端', 'error');
  }
}

// 收集設定頁所有欄位並存回後端（策略參數 + AI 設定）
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
      ai_min_confidence_buy:  parseInt(document.getElementById('ai-min-confidence-buy').value),
      ai_min_confidence_sell: parseInt(document.getElementById('ai-min-confidence-sell').value),
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
