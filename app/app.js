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
let market = null;   // 大盤概況（舊版 JSON 可能沒有）
let dataDate = '';        // 資料日期（YYYY-MM-DD）
let rules = loadRules();
let watchlist = loadWatch();   // 自選股代號陣列
let holdings = loadHoldings(); // 買進成本 { 代號: {cost, shares} }，欄位皆可留空

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

function loadHoldings() {
  try { return cleanHoldings(JSON.parse(localStorage.getItem('stock-holdings'))); } catch { return {}; }
}
function saveHoldings() {
  try { localStorage.setItem('stock-holdings', JSON.stringify(holdings)); } catch { /* 無痕模式等情況存不了 */ }
}
// 只保留格式正確的成本資料（均價 > 0、股數 > 0，至少一項有值）
function cleanHoldings(h, validCodes) {
  const out = {};
  if (!h || typeof h !== 'object' || Array.isArray(h)) return out;
  for (const [code, v] of Object.entries(h)) {
    if (validCodes && !validCodes.has(code)) continue;
    const cost = Number(v?.cost) > 0 ? Number(v.cost) : null;
    const shares = Number(v?.shares) > 0 ? Number(v.shares) : null;
    if (cost || shares) out[code] = { cost, shares };
  }
  return out;
}
// 未實現損益：需要均價才算；有股數才有金額。未含手續費與證交稅
function holdingPnl(s, h) {
  if (!h?.cost || s.close == null) return null;
  const pct = (s.close / h.cost - 1) * 100;
  const amount = h.shares ? (s.close - h.cost) * h.shares : null;
  return { pct, amount, cost: h.shares ? h.cost * h.shares : null };
}
function pnlText(p) {
  const sign = v => (v > 0 ? '+' : '');
  const amt = p.amount == null ? '' : `${sign(p.amount)}${Math.round(p.amount).toLocaleString()} 元 `;
  return `${amt}(${sign(p.pct)}${p.pct.toFixed(2)}%)`;
}

// 「新進榜」比較基準：每個規則記住最近一個資料日期的名單，以及更早一次的名單。
// 同一個資料日期重複開啟不會覆寫比較基準；沒有基準（第一次、清除資料）就不標示。
function newEntryCodes(rule, hits) {
  const key = `stock-seen:${rule.name}`;
  const codes = hits.map(s => s.code);
  let prev = null;
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (saved && saved.date && Array.isArray(saved.codes)) {
      if (dataDate && saved.date < dataDate) {
        prev = saved.codes;
        localStorage.setItem(key, JSON.stringify({ date: dataDate, codes, prev }));
      } else {
        prev = Array.isArray(saved.prev) ? saved.prev : null;
      }
    } else if (dataDate) {
      localStorage.setItem(key, JSON.stringify({ date: dataDate, codes, prev: null }));
    }
  } catch { /* 無痕模式等情況存不了，就不標示 */ }
  return new Set(prev ? codes.filter(c => !prev.includes(c)) : []);
}

// 匯出 / 匯入格式：{ rules, watchlist, holdings }；相容舊版純規則陣列。回傳 null 代表格式不正確
function parseBackup(text, validCodes) {
  let data;
  try { data = JSON.parse(text); } catch { return null; }
  if (!data || typeof data !== 'object') return null;
  const rawRules = Array.isArray(data) ? data : data?.rules ?? [];
  const rawWatch = Array.isArray(data) ? [] : data?.watchlist ?? [];
  if (!Array.isArray(rawRules) || !Array.isArray(rawWatch)) return null;
  if (!rawRules.every(r => r && r.name && Array.isArray(r.conditions) && r.sort)) return null;
  return {
    rules: rawRules.filter(r => r.conditions.every(c => FIELDS[c.field]) && FIELDS[r.sort.field])
      // 名次數量缺漏或異常時補預設值，避免畫面出現「前 undefined 名」
      .map(r => ({ ...r, limit: Math.max(1, Math.min(100, parseInt(r.limit) || 10)) })),
    watchlist: [...new Set(rawWatch)].filter(c => validCodes.has(c)),
    holdings: cleanHoldings(data.holdings, validCodes),
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

// ── 規則回測 ──────────────────────────────────────────────────────────────────
// 只用 JSON 裡每支股票近 60 日的收盤（spark）與成交量（vols）重算各天指標，
// 對過去每一天套用同一條規則，看選出的股票隔 1／5／10 日的平均漲跌與勝率。
// 需要最高／最低價、估值或超過 60 日資料的條件算不出來，回測時略過（畫面會標示）。
const BT_SKIP = new Set(['k', 'd', 'kd_cross', 'pe', 'pb', 'yield', 'ma60', 'above_ma60', 'from_high_60']);
const BT_HORIZONS = [1, 5, 10];

// 逐日指標序列（與 pipeline/indicators.py 同公式；只有 60 日起算，RSI／MACD 與正式值略有差異）
function btSeries(s) {
  const c = s.spark, v = s.vols;
  if (!Array.isArray(c) || !Array.isArray(v) || c.length !== v.length || c.length < 2) return null;
  const n = c.length;
  const mean = (arr, end, len) => end + 1 >= len ? arr.slice(end + 1 - len, end + 1).reduce((a, b) => a + b, 0) / len : null;
  const ewm = (vals, span, from = 0) => {
    const a = 2 / (span + 1), out = Array(n).fill(null);
    for (let i = from; i < n; i++) out[i] = i === from ? vals[i] : out[i - 1] * (1 - a) + vals[i] * a;
    return out;
  };
  const e12 = ewm(c, 12), e26 = ewm(c, 26);
  const dif = c.map((_, i) => e12[i] - e26[i]), dea = ewm(dif, 9);
  let gain = 0, loss = 0;
  const rsi = c.map((x, i) => {
    if (i === 0) return null;
    const d = x - c[i - 1], a = 1 / 14;
    gain = i === 1 ? Math.max(d, 0) : gain * (1 - a) + Math.max(d, 0) * a;
    loss = i === 1 ? Math.max(-d, 0) : loss * (1 - a) + Math.max(-d, 0) * a;
    return i >= 14 && loss > 0 ? 100 - 100 / (1 + gain / loss) : null;
  });
  const ret = (i, days) => i >= days ? (c[i] / c[i - days] - 1) * 100 : null;
  const at = i => {
    const prev5 = i >= 5 ? mean(v, i - 1, 5) : null, ma20 = mean(c, i, 20);
    return {
      close: c[i], change_pct: ret(i, 1), ret_5d: ret(i, 5), ret_20d: ret(i, 20),
      lots: v[i], avg_lots_20: mean(v, i, 20), vol_ratio: prev5 ? v[i] / prev5 : null,
      rsi: rsi[i], ma5: mean(c, i, 5), ma20, above_ma20: ma20 === null ? null : c[i] > ma20,
      macd_hist: i >= 34 ? dif[i] - dea[i] : null,
      macd_cross: i >= 34 ? dif[i] > dea[i] && dif[i - 1] <= dea[i - 1] : null,
    };
  };
  return { n, close: c, at };
}

function backtestRule(rule) {
  if (BT_SKIP.has(rule.sort.field)) return { error: `排名依據「${FIELDS[rule.sort.field].label}」無法用近 60 日資料回測。` };
  const conds = rule.conditions.filter(c => !BT_SKIP.has(c.field));
  const skipped = rule.conditions.filter(c => BT_SKIP.has(c.field));
  const series = stocks.map(s => s._bt ??= btSeries(s) ?? false).filter(Boolean);
  const maxN = Math.max(0, ...series.map(x => x.n));
  const stat = Object.fromEntries(BT_HORIZONS.map(h => [h, { sum: 0, win: 0, n: 0, mSum: 0, mN: 0 }]));
  const { field, dir } = rule.sort;
  let days = 0, picks = 0;
  for (let back = 1; back < maxN; back++) {     // back：往前推幾個交易日（以最新一天為 0）
    const rows = [];
    for (const ser of series) {
      const i = ser.n - 1 - back;
      if (i < 0) continue;
      const row = ser.at(i);
      if (row[field] != null && conds.every(c => passes(row, c))) rows.push({ ser, i, v: row[field] });
    }
    rows.sort((a, b) => dir === 'asc' ? a.v - b.v : b.v - a.v);
    const hits = rows.slice(0, rule.limit);
    if (!hits.length) continue;
    days++; picks += hits.length;
    for (const h of BT_HORIZONS) {
      if (back < h) continue;
      const st = stat[h];
      for (const { ser, i } of hits) {
        const r = (ser.close[i + h] / ser.close[i] - 1) * 100;
        st.sum += r; st.n++; if (r > 0) st.win++;
      }
      for (const ser of series) {
        const i = ser.n - 1 - back;
        if (i >= 0) { st.mSum += (ser.close[i + h] / ser.close[i] - 1) * 100; st.mN++; }
      }
    }
  }
  return { days, picks, skipped, stat, span: maxN };
}

function backtestHtml(res) {
  if (res.error) return `<p class="muted small">${esc(res.error)}</p>`;
  const pct = v => v === null ? '—' : `<span class="${trendClass(v)}">${v > 0 ? '+' : ''}${v.toFixed(2)}%</span>`;
  const cell = (h, f) => { const st = res.stat[h]; return st.n ? f(st) : null; };
  const row = (label, f) => `<tr><th scope="row">${label}</th>${BT_HORIZONS.map(h => `<td>${f(h)}</td>`).join('')}</tr>`;
  const skipNote = res.skipped.length
    ? `<p class="muted small">以下條件需要近 60 日以外的資料，回測時已略過：${esc(res.skipped.map(describeCondition).join('、'))}</p>` : '';
  if (!res.days) return `<p class="muted small">近 ${res.span} 個交易日內，這條規則沒有選出任何股票（或資料天數不足以計算條件）。</p>${skipNote}`;
  return `
    <p class="small">過去 ${res.days} 天有選出股票，共 ${res.picks} 檔次；持有後的表現：</p>
    <table class="bt-table">
      <thead><tr><th></th>${BT_HORIZONS.map(h => `<th scope="col">隔 ${h} 日</th>`).join('')}</tr></thead>
      <tbody>
        ${row('命中股平均', h => pct(cell(h, st => st.sum / st.n)))}
        ${row('勝率', h => cell(h, st => `${(st.win / st.n * 100).toFixed(0)}%`) ?? '—')}
        ${row('全市場平均', h => pct(cell(h, st => st.mSum / st.mN)))}
        ${row('樣本數', h => res.stat[h].n)}
      </tbody>
    </table>
    ${skipNote}
    <p class="muted small">⚠️ 只有近 ${res.span} 個交易日、樣本少，參考價值有限；過去績效不代表未來。</p>`;
}

function toggleBacktest(i, btn) {
  const card = btn.closest('.card');
  const open = card.querySelector('.bt');
  if (open) { open.remove(); btn.setAttribute('aria-expanded', 'false'); return; }
  card.insertAdjacentHTML('beforeend', `<div class="bt">${backtestHtml(backtestRule(rules[i]))}</div>`);
  btn.setAttribute('aria-expanded', 'true');
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

function stockRow(s, highlightField, isNew = false) {
  const extra = highlightField && !['change_pct', 'close'].includes(highlightField)
    ? `<span class="highlight">${esc(FIELDS[highlightField].label)} ${fmt(highlightField, s[highlightField])}</span>` : '';
  return `
    <li class="stock" data-code="${esc(s.code)}" tabindex="0" aria-expanded="false">
      <div class="stock-main">
        ${starButton(s)}
        <div class="stock-name"><b>${esc(s.name)}</b> <span class="muted">${esc(s.code)} · ${esc(s.market)}</span>${isNew ? ' <span class="badge-new" aria-label="新進榜">新進榜</span>' : ''}</div>
        <div class="price">
          <span>${s.close}</span>
          <span class="${trendClass(s.change_pct)}">${s.change_pct > 0 ? '+' : ''}${fmt('change_pct', s.change_pct)}</span>
        </div>
      </div>
      ${extra}
    </li>`;
}

// 近 N 日收盤價迷你走勢圖（inline SVG）；漲紅跌綠沿用 .up / .down，虛線為目前的月線／季線
function sparkline(values, ma20, ma60) {
  if (!Array.isArray(values) || values.length < 2) return '';
  const W = 280, H = 64, P = 4;
  const refs = [[ma20, 'ma20'], [ma60, 'ma60']].filter(([v]) => typeof v === 'number');
  const all = values.concat(refs.map(([v]) => v));
  const min = Math.min(...all), max = Math.max(...all), span = max - min || 1;
  const y = v => (H - P - (v - min) / span * (H - 2 * P)).toFixed(1);
  const x = i => (P + i / (values.length - 1) * (W - 2 * P)).toFixed(1);
  const line = values.map((v, i) => `${x(i)},${y(v)}`).join(' ');
  const lines = refs.map(([v, cls]) =>
    `<line class="${cls}" x1="${P}" x2="${W - P}" y1="${y(v)}" y2="${y(v)}"/>`).join('');
  const cls = trendClass(values[values.length - 1] - values[0]);
  const label = `近 ${values.length} 日收盤價走勢，由 ${values[0]} 到 ${values[values.length - 1]} 元`;
  return `<svg class="spark ${cls}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${label}">${lines}
    <polyline points="${line}"/></svg>`;
}

// 近 20 日成交量柱狀圖（inline SVG）；最後一根（今日）用強調色，量比 > 1.5 以醒目顏色標示
function volumeBars(vols) {
  if (!Array.isArray(vols) || vols.length < 2) return '';
  const v = vols.slice(-20);
  const W = 280, H = 40, G = 2;
  const max = Math.max(...v) || 1;
  const bw = (W - G * (v.length - 1)) / v.length;
  const bars = v.map((n, i) => {
    const h = Math.max(1, n / max * H);
    return `<rect class="${i === v.length - 1 ? 'today' : ''}" x="${(i * (bw + G)).toFixed(1)}" y="${(H - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}"/>`;
  }).join('');
  return `<svg class="volbars" viewBox="0 0 ${W} ${H}" role="img" aria-label="近 ${v.length} 日成交量，今日 ${v[v.length - 1]} 張">${bars}</svg>`;
}

function stockDetail(s) {
  const cells = Object.keys(FIELDS).map(f =>
    `<div><span class="muted">${esc(FIELDS[f].label)}</span><span>${fmt(f, s[f])}</span></div>`).join('');
  const chart = sparkline(s.spark, s.ma20, s.ma60);
  const legend = chart ? '<span class="muted spark-legend">近 60 日收盤 · 虛線：月線／季線</span>' : '';
  const vchart = volumeBars(s.vols);
  const ratio = typeof s.vol_ratio === 'number'
    ? `量比 <b class="${s.vol_ratio > 1.5 ? 'vol-hot' : ''}">${s.vol_ratio.toFixed(2)}</b> 倍` : '量比 —';
  const vlegend = vchart ? `<span class="muted spark-legend">近 20 日成交量（張）· 最右為今日 · ${ratio}</span>` : '';
  return `<div class="detail">${chart}${legend}${vchart}${vlegend}${cells}
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
  if (i >= 0 && holdings[code]) { delete holdings[code]; saveHoldings(); }
  const on = i < 0;
  const name = stocks.find(x => x.code === code)?.name ?? code;
  document.querySelectorAll('button.star').forEach(b => {
    if (b.dataset.code !== code) return;
    b.setAttribute('aria-pressed', on);
    b.setAttribute('aria-label', `${on ? '從自選移除' : '加入自選'} ${name}`);
    b.textContent = on ? '★' : '☆';
  });
  renderWatch();
  renderPicks();
}

function ruleCard(rule, { actions = '' } = {}) {
  const hits = applyRule(rule);
  const fresh = newEntryCodes(rule, hits);
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
      ${hits.length ? `<ol class="list">${hits.map(s => stockRow(s, rule.sort.field, fresh.has(s.code))).join('')}</ol>`
                    : '<p class="muted empty">今天沒有符合條件的股票</p>'}
    </article>`;
}

// ── 分頁：今日推薦 ────────────────────────────────────────────────────────────
function marketCard(m) {
  if (!m) return '';   // 舊版 JSON 沒有 market 欄位就不顯示
  const total = m.up + m.down + m.flat || 1;
  const pct = n => (n / total * 100).toFixed(1);
  const amount = m.amount >= 1e8 ? `${(m.amount / 1e8).toLocaleString('zh-TW', { maximumFractionDigits: 0 })} 億` : '—';
  const ratio = m.amount_ratio ? `（前 5 日均額的 ${m.amount_ratio} 倍）` : '';
  return `
    <article class="card market" aria-label="大盤漲跌家數概況">
      <h2>今日盤勢</h2>
      <div class="breadth" role="img" aria-label="上漲 ${m.up} 家、下跌 ${m.down} 家、平盤 ${m.flat} 家">
        <span class="b-up" style="width:${pct(m.up)}%"></span><span class="b-flat" style="width:${pct(m.flat)}%"></span><span class="b-down" style="width:${pct(m.down)}%"></span>
      </div>
      <div class="small market-nums">
        <span class="up">上漲 ${m.up}</span><span class="muted">平盤 ${m.flat}</span><span class="down">下跌 ${m.down}</span>
      </div>
      <div class="small muted">漲停約 ${m.limit_up} · 跌停約 ${m.limit_down}（以 ±9.5% 近似）</div>
      <div class="small muted">成交金額 ${amount}${ratio}</div>
    </article>`;
}

// 自選股今日摘要：依漲跌幅排序，標出命中的推薦／自訂規則；預設顯示前 10 檔
const WATCH_SUMMARY_LIMIT = 10;
let watchSummaryOpen = true, watchSummaryAll = false;

function watchSummary() {
  const items = watchlist.map(code => stocks.find(x => x.code === code)).filter(Boolean)
    .sort((a, b) => (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity));
  if (!items.length) return '';   // 沒有自選股（或都已無資料）就不顯示
  const tags = new Map();
  for (const r of [...PRESETS, ...rules]) {
    for (const s of applyRule(r)) tags.set(s.code, [...(tags.get(s.code) ?? []), r.name]);
  }
  const shown = watchSummaryAll ? items : items.slice(0, WATCH_SUMMARY_LIMIT);
  const li = s => {
    const hit = tags.get(s.code);
    const chg = s.change_pct == null ? '—' : `${s.change_pct > 0 ? '+' : ''}${fmt('change_pct', s.change_pct)}`;
    const pnl = holdingPnl(s, holdings[s.code]);
    return `<li class="watch-sum-row">
      <span><b>${esc(s.name)}</b> <span class="muted small">${esc(s.code)}</span></span>
      <span class="${trendClass(s.change_pct)}">${chg}</span>
      ${pnl ? `<span class="small ${trendClass(pnl.pct)} watch-hit">損益 ${pnlText(pnl)}</span>` : ''}
      ${hit ? `<span class="small muted watch-hit">命中：${hit.map(esc).join('、')}</span>` : ''}</li>`;
  };
  const more = items.length > WATCH_SUMMARY_LIMIT
    ? `<button type="button" class="ghost" onclick="toggleWatchSummaryAll()">${watchSummaryAll ? '收合' : `顯示全部 ${items.length} 檔`}</button>` : '';
  return `
    <details class="card watch-sum" ${watchSummaryOpen ? 'open' : ''} ontoggle="watchSummaryOpen = this.open">
      <summary><h2>我的自選 · 今日</h2></summary>
      <ol class="list">${shown.map(li).join('')}</ol>${more}
    </details>`;
}

function toggleWatchSummaryAll() {
  watchSummaryAll = !watchSummaryAll;
  renderPicks();
}

function renderPicks() {
  document.getElementById('tab-picks').innerHTML = watchSummary() + marketCard(market) + PRESETS.map((p, i) =>
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
    return s ? stockRow(s) + holdingForm(s) : `
      <li class="stock gone">
        <div class="stock-main">
          <div class="stock-name"><b>${esc(code)}</b> <span class="muted">已無資料</span></div>
          <button type="button" class="ghost danger" onclick="toggleWatch('${esc(code)}')" aria-label="從自選移除 ${esc(code)}">移除</button>
        </div>
      </li>`;
  }).join('');
  el.innerHTML = portfolioTotal() + `<ol class="list">${rows}</ol>`;
}

// 自選頁頂端：有填成本（均價與股數）的持股總損益
function portfolioTotal() {
  let cost = 0, amount = 0;
  for (const code of watchlist) {
    const s = stocks.find(x => x.code === code);
    const p = s && holdingPnl(s, holdings[code]);
    if (p && p.amount != null) { cost += p.cost; amount += p.amount; }
  }
  if (!cost) return '';
  return `<div class="card portfolio"><b>持股總損益</b>
    <span class="${trendClass(amount)}">${pnlText({ amount, pct: amount / cost * 100 })}</span>
    <div class="small muted">成本 ${Math.round(cost).toLocaleString()} 元・概估，未含手續費與證交稅</div></div>`;
}

// 每檔自選下方的成本表單（可收合）；有填時顯示未實現損益
function holdingForm(s) {
  const h = holdings[s.code] ?? {};
  const pnl = holdingPnl(s, h);
  return `<li class="holding-row"><details ${h.cost || h.shares ? 'open' : ''}>
    <summary class="small">${pnl ? `<span class="${trendClass(pnl.pct)}">損益 ${pnlText(pnl)}</span>` : '填入買進成本'}</summary>
    <form class="holding-form" onsubmit="saveHolding(event, '${esc(s.code)}')">
      <label class="small">均價 <input name="cost" type="number" inputmode="decimal" min="0" step="any" value="${h.cost ?? ''}"></label>
      <label class="small">股數 <input name="shares" type="number" inputmode="numeric" min="0" step="1" value="${h.shares ?? ''}"></label>
      <button type="submit" class="ghost">儲存</button>
    </form>
    <div class="small muted">損益為概估，未含手續費與證交稅；資料只存在這支手機的瀏覽器。</div>
  </details></li>`;
}

function saveHolding(e, code) {
  e.preventDefault();
  const f = e.target;
  const next = cleanHoldings({ [code]: { cost: f.cost.value, shares: f.shares.value } });
  if (next[code]) holdings[code] = next[code]; else delete holdings[code];
  saveHoldings();
  renderWatch();
  renderPicks();
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
          <button class="ghost" onclick="toggleBacktest(${i}, this)" aria-expanded="false" aria-label="回測規則 ${esc(r.name)}">回測</button>
          <button class="ghost" onclick="openEditor(${i})" aria-label="編輯規則 ${esc(r.name)}">編輯</button>
          <button class="ghost danger" onclick="deleteRule(${i})" aria-label="刪除規則 ${esc(r.name)}">刪除</button>
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
  if (!rules.length && !watchlist.length) {
    alert('目前沒有規則或自選股可以匯出。');
    return;
  }
  const text = JSON.stringify({ rules, watchlist, holdings });
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
  const newWatch = incoming.watchlist.filter(c => !watchlist.includes(c));
  rules.push(...incoming.rules);
  watchlist.push(...newWatch);
  for (const [c, h] of Object.entries(incoming.holdings)) if (!holdings[c]) holdings[c] = h;
  saveRules();
  saveWatch();
  saveHoldings();
  renderRules();
  renderWatch();
  renderPicks();
  renderAll();
  alert(`匯入完成：${incoming.rules.length} 條規則、${newWatch.length} 檔新自選股。`);
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
        <select id="e-sort" aria-label="排名依據">${fieldOptions(rule.sort.field, f => !f.bool)}</select>
        <select id="e-dir" aria-label="排序方向">
          <option value="desc" ${rule.sort.dir === 'desc' ? 'selected' : ''}>由高到低</option>
          <option value="asc" ${rule.sort.dir === 'asc' ? 'selected' : ''}>由低到高</option>
        </select>
        <label class="inline">前<input id="e-limit" aria-label="顯示名次數量" type="number" min="1" max="100" value="${rule.limit}">名</label>
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
    const all = q ? stocks.filter(s => s.code.includes(q) || s.name.includes(q)) : [];
    const hits = all.slice(0, 50);
    const more = all.length > hits.length ? `<p class="muted empty">共 ${all.length} 筆，僅顯示前 ${hits.length} 筆，請輸入更完整的關鍵字</p>` : '';
    el.querySelector('#search-results').innerHTML = hits.map(s => stockRow(s)).join('') + more
      || (q ? `<p class="muted empty">找不到「${esc(q)}」</p>` : `<p class="muted empty">共 ${stocks.length} 支上市櫃股票</p>`);
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
    market = data.market ?? null;
    dataDate = data.date;
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
