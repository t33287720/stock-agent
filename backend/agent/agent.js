import { callLLM } from "./llm.js";
import { tools } from "./tools.js";
import { loadMemory, saveMemory } from "./memory.js";

// 👉 安全JSON解析（超重要）
export function safeJSONParse(text) {
  try {
    return JSON.parse(text);
  } catch (e) {
    // 嘗試抓取第一個完整 JSON 物件
    const matches = [...text.matchAll(/\{[\s\S]*?\}/g)];
    for (const match of matches) {
      try {
        return JSON.parse(match[0]);
      } catch (_) {
        continue;
      }
    }
    console.log("❌ JSON解析完全失敗，原始文字:", text);
    throw new Error("JSON parse failed");
  }
}

export async function runAgent(userInput = null) {
  const memory = loadMemory();
  memory.recommendations = memory.recommendations || [];
  memory.portfolio = memory.portfolio || [];
  memory.history = memory.history || [];

  const messages = [
    {
      role: "system",
      content: `
      ⚠️ 必須**完全不要文字**，只輸出單一 JSON，且 JSON 必須完整在一行

      【輸入格式嚴格規定】
- analyze_stock.input.stock_id 必須是「字串」，不可為陣列
  ✅ 正確: { "stock_id": "2330" }
  ❌ 錯誤: { "stock_id": ["2330"] 
  
你是一個股票AI Agent，**每次只做一個動作**，請只回傳單個 JSON 物件，不要附加任何文字或其他 JSON。必須使用以下流程：

1. Thought
2. Action（只能使用提供的工具，且一次只能一個）
3. Observation
4. Final Answer

工具說明：
${JSON.stringify({
        call_api: "呼叫證交所API，例如 /exchangeReport/STOCK_DAY_ALL",
        analyze_stock: "分析單一股票（整合價格+外資+營收）",
        analyze_portfolio: "分析目前持股（報酬率+建議）",
        get_portfolio: "取得目前持股"
      }, null, 2)}

規則：
- 一定要用工具取得資料
- 不可以亂猜或編 API
- 必須根據 Observation 再決定下一步
- 最終要附資料來源

輸出規則：
- 僅能回傳完整 JSON
- 格式如下：
{
  "thought": "...",
  "action": { "name": "...", "input": {...} },
  "final_answer": {
      "recommendations": ["股票代碼1", "股票代碼2", "..."],
      "reason": "...",
      "risk": "...",
      "source": "資料來源"
  }
}`
    },
    {
      role: "user",
      content: userInput || "請推薦今日台股Top5"
    },
    {
      role: "system",
      content: `memory: ${JSON.stringify(memory)}`
    }
  ];

  // 📌 抓最外層 JSON（支持多層嵌套）
  function extractJSONFromLLM(str) {
    let stack = [];
    let start = -1;
    for (let i = 0; i < str.length; i++) {
      if (str[i] === "{") {
        if (stack.length === 0) start = i;
        stack.push("{");
      } else if (str[i] === "}") {
        stack.pop();
        if (stack.length === 0 && start !== -1) {
          return str.slice(start, i + 1); // 抓完整 JSON 字串
        }
      }
    }
    return null;
  }

  let loop = 0;
  const maxRetries = 10; // 👉 新增重試次數上限
  let parsed = null;

  while (loop < maxRetries) {
    const llmResponse = await callLLM(messages);

    const jsonStr = extractJSONFromLLM(llmResponse);
    if (!jsonStr) {
      console.log(`❌ 找不到 JSON，LLM 原始輸出:`, llmResponse);
      loop++;
      continue;
    }

    try {
      parsed = JSON.parse(jsonStr);
      console.log("✅ 成功解析 JSON:", parsed);
      break; // 成功就跳出
    } catch (e) {
      console.log(`❌ JSON解析失敗，LLM重新嘗試... (第 ${loop + 1} 次)`);
      loop++;
    }

    if (!parsed) {
      throw new Error("LLM 最終無法回傳有效 JSON");
    }

    // 使用 parsed 前一定要檢查
    if (!parsed.thought || !parsed.action || !parsed.final_answer) {
      console.error("parsed JSON 欄位不完整:", parsed);
      throw new Error("JSON 欄位不完整");
    }

    // 👉 Thought
    if (parsed.thought) {
      console.log("🧠 Thought:", parsed.thought);
    }

    // 👉 Action
    if (parsed.action) {
      const { name, input } = parsed.action;

      if (!tools[name]) {
        console.log("❌ 不存在的工具:", name);
        return "工具錯誤";
      }

      console.log("⚙️ Action:", name, input);

      const result = await tools[name](input);
      console.log("👀 Observation:", result);

      // Observation 回饋給 LLM
      messages.push({ role: "assistant", content: JSON.stringify(parsed) });
      messages.push({ role: "system", content: `Observation: ${JSON.stringify(result)}` });

      continue; // 保持 loop 做下一步動作
    }

    // 👉 Final Answer
if (parsed.final_answer) {
  const codes = parsed.final_answer.recommendations;

  // 去 call API 補資料
  const priceData = await tools.call_api({
    endpoint: "/exchangeReport/STOCK_DAY_ALL"
  });

  const stocks = codes.map(code => {
    const s = priceData.data.find(x => x.Code === code);
    return {
      symbol: code,
      name: s?.Name || "-",
      price: s?.Close || "-",
      score: 0 // 你之後可以加 scoring
    };
  });

  return {
    ...parsed.final_answer,
    stocks   // 👈 給前端用
  };
}
  }

  return "超過最大重試次數，LLM未回傳正確 JSON";
}