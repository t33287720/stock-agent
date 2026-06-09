import axios from "axios";
import { fetchStockData } from "../services/stockService.js";
import { calculateTopStocks } from "../services/scoring.js";
import { loadMemory, saveMemory } from "./memory.js";

const BASE_URL = "https://openapi.twse.com.tw/v1";

// 👉 統一回傳格式
function success(data, meta = {}) {
    return {
        success: true,
        data,
        meta
    };
}

function fail(error) {
    return {
        success: false,
        error: error.toString()
    };
}

export const tools = {

    // 📊 股票資料
    get_stock_data: async () => {
        try {
            const data = await fetchStockData();
            return success(data.slice(0, 50), { source: "STOCK_DAY_ALL" });
        } catch (e) {
            return fail(e);
        }
    },

    // 🏆 Top5
    get_top_stocks: async () => {
        try {
            const data = await fetchStockData();
            const top = calculateTopStocks(data);

            return success(top, { logic: "scoring" });
        } catch (e) {
            return fail(e);
        }
    },

    // 🧠 Memory
    get_memory: async () => {
        try {
            return success(loadMemory());
        } catch (e) {
            return fail(e);
        }
    },

    // 📈 投資組合
    get_portfolio: async () => {
        try {
            const portfolio = loadMemory().portfolio || [];
            // Observation 的回傳格式：固定 key + meta
            return {
                portfolio,
                meta: { message: portfolio.length === 0 ? "目前投資組合為空" : "有持股資料" }
            };
        } catch (e) {
            return { error: e.message };
        }

    },

    // ✍️ 更新持股（強化防呆）
    update_portfolio: async (input) => {
        try {
            if (!input?.stock || !input?.buy_price) {
                return fail("缺少 stock 或 buy_price");
            }

            const memory = loadMemory();

            memory.portfolio.push({
                stock: input.stock,
                buy_price: input.buy_price,
                date: input.date || new Date().toISOString()
            });

            saveMemory(memory);

            return success({ message: "已加入持股" });
        } catch (e) {
            return fail(e);
        }
    },

    // 🌐 通用 API（重點）
    call_api: async ({ endpoint }) => {
        try {
            if (!endpoint) return fail("缺少 endpoint");

            const url = `${BASE_URL}${endpoint}`;
            const res = await axios.get(url);

            return success(res.data.slice(0, 50), {
                endpoint
            });

        } catch (e) {
            return fail(e);
        }
    },
    // 📊 多資料融合（關鍵）
analyze_stock: async ({ stocks }) => {
  try {
    // 取得所有股票資料
    const [priceData, foreignData, revenueData] = await Promise.all([
      tools.call_api({ endpoint: "/exchangeReport/STOCK_DAY_ALL" }),
      tools.call_api({ endpoint: "/fund/MI_QFIIS_sort_20" }),
      tools.call_api({ endpoint: "/opendata/t187ap05_L" })
    ]);

    // 整合資料
    const allStocks = priceData.data.map(s => {
      const code = s.Code;
      const name = s.Name;
      const price = s.ClosePrice;
      const foreignBuy = foreignData.data.find(f => f.Code === code)?.Buy || 0;
      const revenueGrowth = revenueData.data.find(r => r.company_id === code)?.growth || 0;

      return { code, name, price, foreignBuy, revenueGrowth };
    });

    // 選 Top5 股票（範例：依價格 + 外資 + 營收簡單排序）
    const top5Stocks = allStocks
      .sort((a, b) => (b.foreignBuy + b.revenueGrowth) - (a.foreignBuy + a.revenueGrowth))
      .slice(0, 5);

    // 呼叫 LLM 生成建議
    const llmResponse = await callLLM([
      { role: "user", content: `請根據以下股票生成 JSON 建議: ${top5Stocks.map(s => s.code).join(",")}` }
    ]);

    const json = extractJSON(llmResponse); // 使用你原本的 extractJSON
    const llmRecommendation = json?.final_answer || {};

    return {
      success: true,
      data: {
        top5Stocks,
        llmRecommendation
      }
    };
  } catch (e) {
    return { success: false, error: e.toString() };
  }
},
    // 📈 持股分析（超關鍵）
    analyze_portfolio: async () => {
        try {
            const memory = loadMemory();
            const portfolio = memory.portfolio;

            const priceData = await tools.call_api({
                endpoint: "/exchangeReport/STOCK_DAY_ALL"
            });

            const result = portfolio.map(p => {
                const stock = priceData.data.find(s => s.Code === p.stock);

                if (!stock) return null;

                const currentPrice = parseFloat(stock.Close || 0);
                const profit = ((currentPrice - p.buy_price) / p.buy_price) * 100;

                return {
                    stock: p.stock,
                    buy_price: p.buy_price,
                    current_price: currentPrice,
                    profit_percent: profit.toFixed(2)
                };
            });

            return { success: true, data: result };
        } catch (e) {
            return { success: false, error: e.toString() };
        }
    },
    record_recommendation: async (input) => {
        try {
            const memory = loadMemory();

            memory.recommendations.push({
                stock: input.stock,
                buy_price: input.buy_price,
                reason: input.reason,
                date: new Date().toISOString(),
                source: input.source || [],
                status: "tracking"
            });

            saveMemory(memory);

            return { success: true };
        } catch (e) {
            return { success: false, error: e.toString() };
        }
    },
    evaluate_performance: async () => {
        try {
            const memory = loadMemory();

            const priceData = await tools.call_api({
                endpoint: "/exchangeReport/STOCK_DAY_ALL"
            });

            const results = memory.recommendations.map(r => {
                const stock = priceData.data.find(s => s.Code === r.stock);
                if (!stock) return null;

                const currentPrice = parseFloat(stock.Close || 0);
                const profit = ((currentPrice - r.buy_price) / r.buy_price) * 100;

                return {
                    stock: r.stock,
                    buy_price: r.buy_price,
                    current_price: currentPrice,
                    profit_percent: profit.toFixed(2),
                    reason: r.reason
                };
            });

            memory.performance = results;
            saveMemory(memory);

            return { success: true, data: results };
        } catch (e) {
            return { success: false, error: e.toString() };
        }
    },
    reflect_strategy: async () => {
        try {
            const memory = loadMemory();
            const perf = memory.performance;

            const bad = perf.filter(p => p && p.profit_percent < -5);
            const good = perf.filter(p => p && p.profit_percent > 5);

            const reflection = {
                date: new Date().toISOString(),
                summary: {
                    total: perf.length,
                    win: good.length,
                    lose: bad.length
                },
                insight: `
成功策略：${good.map(g => g.reason).join(" | ")}
失敗策略：${bad.map(b => b.reason).join(" | ")}
`
            };

            memory.reflection.push(reflection);
            saveMemory(memory);

            return { success: true, data: reflection };
        } catch (e) {
            return { success: false, error: e.toString() };
        }
    },
    get_performance: async () => {
        const memory = loadMemory();
        return { success: true, data: memory.performance || [] };
    },
    get_reflection: async () => {
        const memory = loadMemory();
        return { success: true, data: memory.reflection || [] };
    }
};