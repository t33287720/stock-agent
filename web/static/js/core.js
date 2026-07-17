/* =========================================================
   台股 AI 分析系統 — 顯示區共用核心
   全域狀態、頁面路由 (showPage/switchTab)、共用小工具 (tip/escapeHtml/
   formatMarketCap/showToast)。必須最先載入 —— index.php 的 onclick、
   以及 pages/*.js 都直接使用這裡定義的全域函式與變數。
   ========================================================= */

const API = '';
let currentTicker = null;
let priceChart = null, rsiChart = null, macdChart = null;
let currentHistory = [];

// ── Tooltip dictionary ────────────────────────────────────────────────────────
const TIPS = {
  'RSI':         'RSI（相對強弱指標）：衡量近期漲跌動能，範圍 0–100。\n低於30：超賣（可能反彈）\n高於70：超買（可能回調）',
  'MACD':        'MACD（移動平均收斂發散）：12日EMA 減 26日EMA 的差值。MACD 高於信號線（9日EMA）為多頭排列，反之為空頭。MACD 由下往上穿越信號線稱「黃金交叉」。',
  'KD':          'KD（隨機指標 Stochastic）：K為快線，D為K的3日均值（慢線）。\nK < 20：超賣；K > 80：超買\nK從下往上穿越D：黃金交叉（買入訊號）\nK從上往下穿越D：死亡交叉（賣出訊號）',
  '黃金交叉':    '黃金交叉：短期均線（SMA20）由下往上穿越長期均線（SMA60），代表短期動能開始強於長期，通常視為多頭訊號。',
  '死亡交叉':    '死亡交叉：短期均線（SMA20）由上往下穿越長期均線（SMA60），代表短期動能弱於長期，通常視為空頭訊號。',
  '多頭排列':    '多頭排列：SMA20 > SMA60，短期均線在長期均線之上，市場處於上升趨勢。',
  '空頭排列':    '空頭排列：SMA20 < SMA60，短期均線在長期均線之下，市場處於下降趨勢。',
  'SMA20':       'SMA（簡單移動平均線）20日：過去20個交易日收盤價的算術平均值。常作為短期支撐與壓力參考。',
  'SMA60':       'SMA（簡單移動平均線）60日：過去60個交易日收盤價的算術平均值。常作為中期趨勢判斷依據。',
  '布林上軌':    '布林上軌（Bollinger Upper Band）：20日均線加兩個標準差。股價接近或突破上軌表示超買或強勢突破，可能面臨壓力。',
  '布林下軌':    '布林下軌（Bollinger Lower Band）：20日均線減兩個標準差。股價接近或跌破下軌表示超賣，可能有支撐力道。',
  '布林通道':    '布林通道（Bollinger Bands）：以20日均線為中軸，上下各兩個標準差形成的通道。帶寬窄表示低波動，帶寬寬表示高波動。',
  'PE':          'P/E（本益比）：股價 ÷ 每股盈餘（EPS）。反映市場願意為每1元獲利支付多少錢。台股平均約15–20倍，越低通常越便宜，但也可能反映低成長預期。',
  'PB':          'P/B（股價淨值比）：股價 ÷ 每股淨值（帳面價值）。低於1代表股價低於帳面資產。銀行股通常P/B較低。',
  '殖利率':      '殖利率（Dividend Yield）：每股現金股利 ÷ 股價。衡量股息收益，台股高殖利率通常指5%以上。注意：高殖利率也可能因股價下跌造成。',
  'EPS':         'EPS（每股盈餘）：公司稅後淨利 ÷ 在外流通股數。是評估公司獲利能力的核心指標，逐季/逐年成長為佳。',
  'ROE':         'ROE（股東權益報酬率）：稅後淨利 ÷ 股東權益。衡量公司利用股東資金的效率，巴菲特認為持續15%以上為優質公司。',
  '夏普比率':    'Sharpe Ratio（夏普比率）：超額報酬 ÷ 報酬標準差。衡量每承擔一單位風險所獲得的超額報酬。\n> 1：良好\n> 2：優秀\n< 0：賠錢（含風險）',
  '最大回撤':    '最大回撤（Max Drawdown）：從峰值到谷底的最大跌幅百分比。衡量策略的最大下行風險，越小表示策略越穩健。',
  '勝率':        '勝率：獲利交易次數 ÷ 總交易次數。注意：高勝率不代表好策略，還需搭配損益比（平均獲利 ÷ 平均虧損）評估。',
  '手續費':      '台灣股票交易成本：\n買入：0.1425%（券商手續費，可打折至0.06%）\n賣出：0.1425%（手續費）+ 0.3%（證券交易稅）\n每千元交易成本約4.3元',
  'ATR':         'ATR（平均真實波幅）：衡量市場波動程度，是每日最高價、最低價、前收盤價三者計算的真實波幅之14日均值。用於設定合理停損距離。',
  '每股投入金額': '每次買入一支股票時最多投入的金額（NTD）。\n持倉數量沒有上限，由可用資金自動決定。\n當可用現金低於此金額時，停止買入新股（避免手續費侵蝕）。',
  '限價買單':    '以低於當前市價的特定價格掛出的買單，只有當股價跌到該價位時才會成交。\n本系統以前一日收盤價 × 0.995 作為限價，相當於比昨收低 0.5% 才買入，避免追高。',
  '停損停利':    '停損：股價跌破設定比例（如 -7%）時自動賣出，限制虧損擴大。\n停利：股價漲過設定比例（如 +15%）時自動賣出，鎖住獲利。\n兩者都是「預先設定好的自動出場機制」。',
  '回測期間':    '模擬此策略在「N 個月前開始運作」的歷史表現。\n期間越長：能看到更多市場週期，結果更具參考性，但運算時間較長。\n期間越短：跑得快，但可能只看到單一市場狀態（純多頭或純空頭）。',
  '等權倉位':    '每支股票平均分配相同比例的資金，不因看好程度不同而加重某支。\n例如初始資金 20 萬、最大持倉 5 支 → 每支上限 4 萬。',
};

// 產生指標名稱旁的「?」提示圖示，hover 時顯示 TIPS 字典裡對應的說明文字
function tip(key) {
  const text = TIPS[key];
  if (!text) return '';
  return `<span class="tip" data-tip="${text.replace(/"/g, '&quot;').replace(/\n/g, '&#10;')}">?</span>`;
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadStockList();
  setupSearch();
  showPage('welcome');
  loadRunLog();
});

// ── Pages / Tabs ──────────────────────────────────────────────────────────────
// 切換左側導覽對應的主要頁面區塊（顯示目前頁、隱藏其餘）
function showPage(page) {
  ['welcome', 'analysis', 'settings', 'auto', 'full-backtest', 'scan', 'market', 'chat'].forEach(p => {
    const el = document.getElementById(`page-${p}`);
    if (el) el.style.display = p === page ? '' : 'none';
  });
  document.querySelectorAll('.nav-item[data-page]').forEach(el =>
    el.classList.toggle('active', el.dataset.page === page));
}


// 切換個股分析頁的分頁籤，並視需要延遲載入模擬交易狀態／相關新聞
function switchTab(tab) {
  const all = ['chart', 'signals', 'fundamental', 'backtest', 'simulation', 'ai'];
  all.forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    if (el) el.style.display = t === tab ? '' : 'none';
  });
  document.querySelectorAll('#tabs .tab').forEach((el, i) => {
    el.classList.toggle('active', all[i] === tab);
  });
  // Lazy-load simulation when tab is opened
  if (tab === 'simulation') loadSimulation();
  // Lazy-load related news (once per ticker)
  if (tab === 'fundamental' && newsLoadedFor !== currentTicker) {
    newsLoadedFor = currentTicker;
    loadNews(currentTicker);
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────────
// 轉義 HTML 特殊字元，避免使用者/外部資料（如新聞標題）造成 XSS
function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// 將市值數字格式化為「億／兆」為單位的字串
function formatMarketCap(v) {
  if (v >= 1e12) return (v / 1e12).toFixed(2) + ' 兆';
  if (v >= 1e8)  return (v / 1e8).toFixed(2)  + ' 億';
  return v.toLocaleString();
}

// 顯示右下角的提示訊息（4 秒後自動消失）
function showToast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast show ${type}`;
  setTimeout(() => el.classList.remove('show'), 4000);
}
