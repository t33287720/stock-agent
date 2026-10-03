/* 台股選股 App
   資料：stocks-latest.json（每天由 GitHub Actions 產生，見 pipeline/build.py）
   規則：{ name, conditions: [{field, op, value}], sort: {field, dir}, limit }
   自訂規則存在這支手機的瀏覽器裡（localStorage），不會上傳。 */

// ── 可篩選 / 排序的欄位 ────────────────────────────────────────────────────────
const FIELDS = {
  close:        { label: '收盤價',          unit: '元' },
  change_pct:   { label: '今日漲跌',        unit: '%' },
  ret_5d:       { label: '5 日漲跌',        unit: '%' },
  ret_20d:      { label: '20 日漲跌',       unit: '%' },
  lots:         { label: '今日成交量',      unit: '張' },
  avg_lots_20:  { label: '20 日平均量',     unit: '張' },
  vol_ratio:    { label: '量比',            unit: '倍' },   // 今日成交量 ÷ 前 5 日平均量
  pe:           { label: '本益比',          unit: '倍' },
  pb:           { label: '股價淨值比',      unit: '倍' },
  yield:        { label: '殖利率',          unit: '%' },
  rsi:          { label: 'RSI(14)',         unit: '' },
  k:            { label: 'K 值',            unit: '' },
  d:            { label: 'D 值',            unit: '' },
  macd_hist:    { label: 'MACD 柱狀體',     unit: '' },
  from_high_60: { label: '距 60 日高點',    unit: '%' },
  ma5:          { label: '5 日均線',        unit: '元' },
  ma20:         { label: '20 日均線（月線）', unit: '元' },
  ma60:         { label: '60 日均線（季線）', unit: '元' },
  above_ma20:   { label: '站上月線',        bool: true },
  above_ma60:   { label: '站上季線',        bool: true },
  kd_cross:     { label: '今日 KD 黃金交叉', bool: true },
  macd_cross:   { label: '今日 MACD 黃金交叉', bool: true },
};

// ── 今日推薦：內建規則 ─────────────────────────────────────────────────────────
const PRESETS = [
  {
    name: '存股：高殖利率、低本益比',
    desc: '殖利率 5~15%（再高通常是一次性配息）、本益比 ≤ 15，排除冷門股',
    conditions: [
      { field: 'yield', op: '>=', value: 5 },
      { field: 'yield', op: '<=', value: 15 },
      { field: 'pe', op: '<=', value: 15 },
      { field: 'avg_lots_20', op: '>=', value: 200 },
    ],
    sort: { field: 'yield', dir: 'desc' }, limit: 10,
  },
  {
    name: 'KD 低檔黃金交叉',
    desc: 'K ≤ 30 且今天 K 往上穿過 D',
    conditions: [
      { field: 'k', op: '<=', value: 30 },
      { field: 'kd_cross', op: 'is', value: true },
      { field: 'avg_lots_20', op: '>=', value: 500 },
    ],
    sort: { field: 'vol_ratio', dir: 'desc' }, limit: 10,
  },
  {
    name: '爆量上漲',
    desc: '量比 ≥ 2（成交量是前 5 日均量 2 倍以上）、漲 3% 以上、站上月線',
    conditions: [
      { field: 'vol_ratio', op: '>=', value: 2 },
      { field: 'change_pct', op: '>=', value: 3 },
      { field: 'above_ma20', op: 'is', value: true },
      { field: 'lots', op: '>=', value: 1000 },
    ],
    sort: { field: 'vol_ratio', dir: 'desc' }, limit: 10,
  },
  {
    name: '多頭強勢',
    desc: '站上月線與季線、離 60 日高點 3% 以內',
    conditions: [
      { field: 'above_ma20', op: 'is', value: true },
      { field: 'above_ma60', op: 'is', value: true },
      { field: 'from_high_60', op: '>=', value: -3 },
      { field: 'avg_lots_20', op: '>=', value: 1000 },
    ],
    sort: { field: 'ret_20d', dir: 'desc' }, limit: 10,
  },
  {
    name: '超跌反彈觀察',
    desc: 'RSI ≤ 30 的超賣股',
    conditions: [
      { field: 'rsi', op: '<=', value: 30 },
      { field: 'avg_lots_20', op: '>=', value: 500 },
    ],
    sort: { field: 'rsi', dir: 'asc' }, limit: 10,
  },
];

// ── 狀態 ──────────────────────────────────────────────────────────────────────
let stocks = [];          // [{code, name, market, close, ...}]
let rules = loadRules();
let watchlist = loadWatch();   // 自選股代號陣列

function loadRules() {
  try { return JSON.parse(localStorage.getItem('stock-rules')) || []; } catch { return []; }
}
function saveRules() {
  try { localStorage.setItem('stock-rules', JSON.stringify(rules)); } catch { /* 無痕模式等情況存不了 */ }
}

function loadWatch() {
  try {
    const list = JSON.parse(localStorage.getItem('stock-watchlist'));
    return Array.isArray(list) ? list.filter(c => typeof c === 'string') : [];
  } catch { return []; }
}
function saveWatch() {
  try { localStorage.setItem('stock-watchlist', JSON.stringify(watchlist)); } catch { /* 無痕模式等情況存不了 */ }
}

// 匯出 / 匯入格式：{ rules, watchlist }；相容舊版純規則陣列。回傳 null 代表格式不正確
function parseBackup(text, validCodes) {
  let data;
  try { data = JSON.parse(text); } catch { return null; }
  if (!data || typeof data !== 'object') return null;
  const rawRules = Array.isArray(data) ? data : data?.rules ?? [];
  const rawWatch = Array.isArray(data) ? [] : data?.watchlist ?? [];
  if (!Array.isArray(rawRules) || !Array.isArray(rawWatch)) return null;
  if (!rawRules.every(r => r && r.name && Array.isArray(r.conditions) && r.sort)) return null;
  return {
    rules: rawRules.filter(r => r.conditions.every(c => FIELDS[c.field]) && FIELDS[r.sort.field]),
    watchlist: [...new Set(rawWatch)].filter(c => validCodes.has(c)),
  };
}

// ── 規則邏輯 ──────────────────────────────────────────────────────────────────
function passes(stock, c) {
  const v = stock[c.field];
  if (v === null || v === undefined) return false;
  if (c.op === 'is') return v === c.value;
  if (c.op === '>=') return v >= c.value;
  if (c.op === '<=') return v <= c.value;
  return false;
}

function applyRule(rule) {
  const { field, dir } = rule.sort;
  return stocks
    .filter(s => rule.conditions.every(c => passes(s, c)) && s[field] != null)
    .sort((a, b) => dir === 'asc' ? a[field] - b[field] : b[field] - a[field])
    .slice(0, rule.limit);
}

function describeCondition(c) {
  const f = FIELDS[c.field];
  if (f.bool) return c.value ? f.label : `未${f.label}`;
  return `${f.label} ${c.op === '>=' ? '≥' : '≤'} ${c.value}${f.unit}`;
}

// ── 畫面：共用 ────────────────────────────────────────────────────────────────
const esc = s => String(s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

function fmt(field, v) {
  if (v === null || v === undefined) return '—';
  const f = FIELDS[field];
  if (f?.bool) return v ? '是' : '否';
  const digits = ['lots', 'avg_lots_20'].includes(field) ? 0 : 2;
  return `${v.toLocaleString('zh-TW', { maximumFractionDigits: digits })}${f?.unit ?? ''}`;
}

const trendClass = v => v > 0 ? 'up' : v < 0 ? 'down' : '';

function starButton(s) {
  const on = watchlist.includes(s.code);
  return `<button type="button" class="star" data-code="${esc(s.code)}" aria-pressed="${on}"
    aria-label="${on ? '從自選移除' : '加入自選'} ${esc(s.name)}">${on ? '★' : '☆'}</button>`;
}

function stockRow(s, highlightField) {
  const extra = highlightField && !['change_pct', 'close'].includes(highlightField)
    ? `<span class="highlight">${esc(FIELDS[highlightField].label)} ${fmt(highlightField, s[highlightField])}</span>` : '';
  return `
    <li class="stock" data-code="${esc(s.code)}" tabindex="0" aria-expanded="false">
      <div class="stock-main">
        ${starButton(s)}
        <div class="stock-name"><b>${esc(s.name)}</b> <span class="muted">${esc(s.code)} · ${esc(s.market)}</span></div>
        <div class="price">
          <span>${s.close}</span>
          <span class="${trendClass(s.change_pct)}">${s.change_pct > 0 ? '+' : ''}${fmt('change_pct', s.change_pct)}</span>
        </div>
      </div>
      ${extra}
    </li>`;
}

function stockDetail(s) {
  const cells = Object.keys(FIELDS).map(f =>
    `<div><span class="muted">${esc(FIELDS[f].label)}</span><span>${fmt(f, s[f])}</span></div>`).join('');
  return `<div class="detail">${cells}
    <a href="https://tw.stock.yahoo.com/quote/${encodeURIComponent(s.code)}" target="_blank" rel="noopener">在 Yahoo 股市看走勢圖 ↗</a></div>`;
}

// 點股票展開 / 收合詳細數字
function toggleDetail(li) {
  const open = li.querySelector('.detail');
  if (open) {
    open.remove();
    li.setAttribute('aria-expanded', 'false');
    return;
  }
  const s = stocks.find(x => x.code === li.dataset.code);
  li.insertAdjacentHTML('beforeend', stockDetail(s));
  li.setAttribute('aria-expanded', 'true');
}
document.addEventListener('click', e => {
  const star = e.target.closest('button.star');
  if (star) { toggleWatch(star.dataset.code); return; }
  const li = e.target.closest('li.stock');
  if (li && li.dataset.code && !e.target.closest('a, button')) toggleDetail(li);
});
// 鍵盤操作：焦點在股票列上時，Enter / 空白鍵可展開、收合
document.addEventListener('keydown', e => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('li.stock')) {
    e.preventDefault();
    toggleDetail(e.target);
  }
});

// 加入 / 移除自選：只局部更新星號，不整頁重繪（避免搜尋框內容消失）
function toggleWatch(code) {
  const i = watchlist.indexOf(code);
  if (i >= 0) watchlist.splice(i, 1); else watchlist.push(code);
  saveWatch();
  const on = i < 0;
  const name = stocks.find(x => x.code === code)?.name ?? code;
  document.querySelectorAll('button.star').forEach(b => {
    if (b.dataset.code !== code) return;
    b.setAttribute('aria-pressed', on);
    b.setAttribute('aria-label', `${on ? '從自選移除' : '加入自選'} ${name}`);
    b.textContent = on ? '★' : '☆';
  });
  renderWatch();
}

function ruleCard(rule, { actions = '' } = {}) {
  const hits = applyRule(rule);
  return `
    <article class="card">
      <div class="card-head">
        <div>
          <h2>${esc(rule.name)}</h2>
          <div class="muted small">${esc(rule.desc || rule.conditions.map(describeCondition).join('、'))}</div>
          <div class="muted small">依「${esc(FIELDS[rule.sort.field].label)}」${rule.sort.dir === 'asc' ? '由低到高' : '由高到低'} · 前 ${rule.limit} 名</div>
        </div>
        ${actions}
      </div>
      ${hits.length ? `<ol class="list">${hits.map(s => stockRow(s, rule.sort.field)).join('')}</ol>`
                    : '<p class="muted empty">今天沒有符合條件的股票</p>'}
    </article>`;
}

// ── 分頁：今日推薦 ────────────────────────────────────────────────────────────
function renderPicks() {
  document.getElementById('tab-picks').innerHTML = PRESETS.map((p, i) =>
    ruleCard(p, { actions: `<button class="ghost" onclick="copyPreset(${i})">複製成我的規則</button>` })).join('');
}

function copyPreset(i) {
  const { desc, ...rule } = structuredClone(PRESETS[i]);
  rule.name += '（我的）';
  rules.push(rule);
  saveRules();
  renderRules();
  switchTab('rules');
}

// ── 分頁：自選 ────────────────────────────────────────────────────────────────
function renderWatch() {
  const el = document.getElementById('tab-watch');
  if (!watchlist.length) {
    el.innerHTML = '<p class="muted empty">還沒有自選股。到任何股票列按「☆」就能收藏。</p>';
    return;
  }
  const rows = watchlist.map(code => {
    const s = stocks.find(x => x.code === code);
    return s ? stockRow(s) : `
      <li class="stock gone">
        <div class="stock-main">
          <div class="stock-name"><b>${esc(code)}</b> <span class="muted">已無資料</span></div>
          <button type="button" class="ghost danger" onclick="toggleWatch('${esc(code)}')">移除</button>
        </div>
      </li>`;
  }).join('');
  el.innerHTML = `<ol class="list">${rows}</ol>`;
}

// ── 分頁：我的規則 ────────────────────────────────────────────────────────────
function renderRules() {
  const el = document.getElementById('tab-rules');
  const toolbar = `
    <div class="toolbar">
      <button class="primary" onclick="openEditor()">＋ 新增規則</button>
      <button class="ghost" onclick="exportRules()">匯出</button>
      <button class="ghost" onclick="importRules()">匯入</button>
    </div>`;
  el.innerHTML = toolbar + (rules.length
    ? rules.map((r, i) => ruleCard(r, { actions: `
        <div class="actions">
          <button class="ghost" onclick="openEditor(${i})">編輯</button>
          <button class="ghost danger" onclick="deleteRule(${i})">刪除</button>
        </div>` })).join('')
    : '<p class="muted empty">還沒有自訂規則。按「新增規則」，或到「今日推薦」把現成的規則複製過來再修改。</p>');
}

function deleteRule(i) {
  if (!confirm(`刪除「${rules[i].name}」？`)) return;
  rules.splice(i, 1);
  saveRules();
  renderRules();
}

function exportRules() {
  const text = JSON.stringify({ rules, watchlist });
  navigator.clipboard?.writeText(text).then(
    () => alert('規則與自選股已複製，可以貼到記事本保存，或在另一支手機「匯入」。'),
    () => prompt('複製下面這段文字保存：', text));
}

function importRules() {
  const text = prompt('貼上之前匯出的內容：');
  if (!text) return;
  const incoming = parseBackup(text, new Set(stocks.map(x => x.code)));
  if (!incoming) {
    alert('格式不正確，請貼上從「匯出」複製的文字。');
    return;
  }
  rules.push(...incoming.rules);
  watchlist.push(...incoming.watchlist.filter(c => !watchlist.includes(c)));
  saveRules();
  saveWatch();
  renderRules();
  renderWatch();
  renderPicks();
  renderAll();
}

// ── 規則編輯器 ────────────────────────────────────────────────────────────────
const fieldOptions = (selected, filter = () => true) => Object.entries(FIELDS).filter(([k, f]) => filter(f))
  .map(([k, f]) => `<option value="${k}" ${k === selected ? 'selected' : ''}>${esc(f.label)}</option>`).join('');

function conditionRow(c = { field: 'yield', op: '>=', value: 5 }) {
  const isBool = FIELDS[c.field].bool;
  return `
    <div class="cond">
      <select class="c-field" aria-label="條件欄位">${fieldOptions(c.field)}</select>
      ${isBool
        ? `<select class="c-bool" aria-label="是否符合"><option value="true" ${c.value ? 'selected' : ''}>是</option><option value="false" ${!c.value ? 'selected' : ''}>否</option></select>`
        : `<select class="c-op" aria-label="比較方式"><option value=">=" ${c.op === '>=' ? 'selected' : ''}>≥</option><option value="<=" ${c.op === '<=' ? 'selected' : ''}>≤</option></select>
           <input class="c-value" aria-label="條件數值" type="number" step="any" inputmode="decimal" value="${c.value}">`}
      <button type="button" class="ghost danger" aria-label="刪除此條件" title="刪除此條件" onclick="this.parentElement.remove()">✕</button>
    </div>`;
}

function openEditor(index) {
  const rule = index === undefined
    ? { name: '', conditions: [{ field: 'yield', op: '>=', value: 5 }], sort: { field: 'yield', dir: 'desc' }, limit: 10 }
    : rules[index];
  const dlg = document.getElementById('editor');
  dlg.innerHTML = `
    <form method="dialog">
      <h2>${index === undefined ? '新增規則' : '編輯規則'}</h2>
      <label>名稱<input id="e-name" required value="${esc(rule.name)}" placeholder="例如：便宜的高殖利率股"></label>
      <div class="label">條件（全部都要符合）</div>
      <div id="e-conds">${rule.conditions.map(conditionRow).join('')}</div>
      <button type="button" class="ghost" onclick="document.getElementById('e-conds').insertAdjacentHTML('beforeend', conditionRow())">＋ 加一個條件</button>
      <div class="label">排名方式</div>
      <div class="cond">
        <select id="e-sort">${fieldOptions(rule.sort.field, f => !f.bool)}</select>
        <select id="e-dir">
          <option value="desc" ${rule.sort.dir === 'desc' ? 'selected' : ''}>由高到低</option>
          <option value="asc" ${rule.sort.dir === 'asc' ? 'selected' : ''}>由低到高</option>
        </select>
        <label class="inline">前<input id="e-limit" type="number" min="1" max="100" value="${rule.limit}">名</label>
      </div>
      <div class="toolbar end">
        <button value="cancel" formnovalidate class="ghost">取消</button>
        <button value="save" class="primary">儲存</button>
      </div>
    </form>`;

  // 換欄位時，數值欄位 ↔ 是/否欄位 的輸入框要跟著換
  dlg.querySelector('#e-conds').addEventListener('change', e => {
    if (!e.target.classList.contains('c-field')) return;
    const row = e.target.closest('.cond');
    const field = e.target.value;
    row.outerHTML = conditionRow(FIELDS[field].bool ? { field, op: 'is', value: true } : { field, op: '>=', value: 0 });
  });

  dlg.onclose = () => {
    if (dlg.returnValue !== 'save') return;
    const conditions = [...dlg.querySelectorAll('#e-conds .cond')].map(row => {
      const field = row.querySelector('.c-field').value;
      return FIELDS[field].bool
        ? { field, op: 'is', value: row.querySelector('.c-bool').value === 'true' }
        : { field, op: row.querySelector('.c-op').value, value: parseFloat(row.querySelector('.c-value').value) || 0 };
    });
    const saved = {
      name: dlg.querySelector('#e-name').value.trim() || '未命名規則',
      conditions,
      sort: { field: dlg.querySelector('#e-sort').value, dir: dlg.querySelector('#e-dir').value },
      limit: Math.max(1, Math.min(100, parseInt(dlg.querySelector('#e-limit').value) || 10)),
    };
    if (index === undefined) rules.push(saved); else rules[index] = saved;
    saveRules();
    renderRules();
  };
  dlg.showModal();
}

// ── 分頁：全部股票 ────────────────────────────────────────────────────────────
function renderAll() {
  const el = document.getElementById('tab-all');
  el.innerHTML = `
    <input id="search" type="search" aria-label="搜尋股票代號或名稱" placeholder="輸入代號或名稱，例如 2330 或 台積電">
    <ol id="search-results" class="list"></ol>`;
  const input = el.querySelector('#search');
  const show = () => {
    const q = input.value.trim();
    const hits = q ? stocks.filter(s => s.code.includes(q) || s.name.includes(q)).slice(0, 50) : [];
    el.querySelector('#search-results').innerHTML = hits.map(s => stockRow(s)).join('')
      || (q ? '<p class="muted empty">找不到</p>' : `<p class="muted empty">共 ${stocks.length} 支上市櫃股票</p>`);
  };
  input.addEventListener('input', show);
  show();
}

// ── 分頁切換 ──────────────────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('main > section').forEach(s => s.hidden = s.id !== `tab-${tab}`);
  document.querySelectorAll('.tabbar button').forEach(b => {
    const on = b.dataset.tab === tab;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  window.scrollTo(0, 0);
}
document.querySelectorAll('.tabbar button').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));

// ── 啟動 ──────────────────────────────────────────────────────────────────────
async function init() {
  try {
    const resp = await fetch('stocks-latest.json', { cache: 'no-cache' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    stocks = data.rows.map(r => Object.fromEntries(data.columns.map((c, i) => [c, r[i]])));
    document.getElementById('data-date').textContent =
      `${data.date} 收盤資料 · ${stocks.length} 支${data.has_valuation ? '' : ' · 本益比等估值尚未公布'}`;
  } catch {
    document.getElementById('data-date').textContent = '資料載入失敗，請稍後再試';
    document.getElementById('tab-picks').innerHTML =
      '<p class="muted empty">資料載入失敗，請檢查網路後<button class="ghost" onclick="location.reload()">重新載入</button></p>';
    return;
  }
  renderPicks();
  renderWatch();
  renderRules();
  renderAll();
}
init();
