import { loadMemory, saveMemory } from "../agent/memory.js";
import axios from "axios";

const BASE_URL = "https://openapi.twse.com.tw/v1";

export async function evaluatePerformance() {
  const memory = loadMemory();

  const res = await axios.get(`${BASE_URL}/exchangeReport/STOCK_DAY_ALL`);
  const priceData = res.data;

  const results = memory.recommendations.map(r => {
    const stock = priceData.find(s => s.Code === r.stock);
    if (!stock) return null;

    const currentPrice = parseFloat(stock.Close || 0);
    const profit = ((currentPrice - r.buy_price) / r.buy_price) * 100;

    return {
      stock: r.stock,
      buy_price: r.buy_price,
      current_price: currentPrice,
      profit_percent: Number(profit.toFixed(2)),
      reason: r.reason
    };
  }).filter(Boolean);

  memory.performance = results;
  saveMemory(memory);

  return results;
}