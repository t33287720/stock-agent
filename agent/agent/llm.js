import axios from "axios";

// ⚠️ 注意：API_LIST 保留給參考，但 LLM 不直接呼叫 foreign/revenue
const API_LIST = [
  {
    name: "stock_price",
    endpoint: "/exchangeReport/STOCK_DAY_ALL",
    description: "每日成交資訊（價格、成交量）"
  },
  {
    name: "pe_ratio",
    endpoint: "/exchangeReport/BWIBBU_ALL",
    description: "本益比、殖利率、股價淨值比"
  },
  {
    name: "margin",
    endpoint: "/exchangeReport/MI_MARGN",
    description: "融資融券"
  },
  {
    name: "foreign",
    endpoint: "/fund/MI_QFIIS_sort_20",
    description: "外資持股（注意：LLM 不要直接呼叫，請使用 analyze_stock）"
  },
  {
    name: "revenue",
    endpoint: "/opendata/t187ap05_L",
    description: "每月營收（注意：LLM 不要直接呼叫，請使用 analyze_stock）"
  },
  {
    name: "news",
    endpoint: "/opendata/t187ap04_L",
    description: "重大訊息"
  }
];

// 👉 新增：高階工具說明
const TOOL_SCHEMA = {
  call_api: "查單一市場資料",
  analyze_stock: "分析單一股票（整合價格+外資+營收）",
  analyze_portfolio: "分析目前持股（報酬率+建議）",
  get_portfolio: "取得目前持股"
};

// 👉 新增：決策規則（核心）
const DECISION_RULES = `
【投資決策規則】

1. 獲利 > 10% → 建議賣出（停利）
2. 虧損 < -5% → 建議停損
3. 外資持續買入 → 偏多
4. 營收成長 → 偏多
5. 成交量增加 + 上漲 → 強勢股

請根據以上規則做出：
- 買 / 賣 / 續抱 判斷
`;

export async function callLLM(messages) {
  const prompt = `
  ⚠️ 必須**完全不要文字**，只輸出單一 JSON，且 JSON 必須完整在一行

【輸入格式嚴格規定】

- analyze_stock.input.stock_id 必須是「字串」，不可為陣列
  ✅ 正確: { "stock_id": "2330" }
  ❌ 錯誤: { "stock_id": ["2330"] 

⚠️ 注意：
- 你**絕對不能**輸出文字、表格或示例說明
- 僅能輸出一個完整 JSON 對象，格式如下：
  { "thought": "...", "action": {...}, "final_answer": {...} }
- 絕對不要包含任何額外說明文字

你是一個股票 AI Agent，僅使用以下工具，且**所有輸出必須是單一 JSON**，不能有多餘文字，也不能分段輸出。

========【JSON 格式】========
{
  "thought": "你的思考過程，中文",
  "action": {
    "name": "工具名稱，必填",
    "input": { "必要欄位": "必填且正確" }
  },
  "final_answer": {
    "recommendations": ["股票代碼1", "股票代碼2", "..."],
    "reason": "...",
    "risk": "...",
    "source": "資料來源"
  }
}

========【可用工具】========
${JSON.stringify(TOOL_SCHEMA, null, 2)}

========【可用 API】========
${JSON.stringify(API_LIST, null, 2)}

========【工具選擇策略】========
- 問推薦股票 → 用 analyze_stock，input.stock_id 必填且為單一個股票代碼
  ⚠️ 注意：analyze_stock 已自動抓取 price、foreign、revenue
- 問持股 → 用 analyze_portfolio
- 問價格 → 用 call_api，input.endpoint 必填
- 問投資組合 → 用 get_portfolio

========【規則】========
1. LLM 不可以直接呼叫 foreign 或 revenue

========【決策規則】========
${DECISION_RULES}

========【規則】========
1. 每次只能呼叫一個工具
2. 不可以亂編 API
3. 必須根據 Observation 再決定下一步
4. 所有 input 欄位必填且正確
5. final_answer 必須包含 recommendations、reason、risk、source
6. JSON 必須正確，不能輸出空物件或文字

========【對話歷史】========
${JSON.stringify(messages, null, 2)}
`;

  const res = await axios.post("http://localhost:11434/api/generate", {
    model: "mistral:7b",
    prompt,
    stream: false
  });

  return res.data.response;
}