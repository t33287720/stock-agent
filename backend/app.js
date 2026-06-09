import express from "express";
import cors from "cors";
import { runAgent } from "./agent/agent.js";
import { loadMemory, saveMemory } from "./agent/memory.js";


// 資料庫抓取stock
import { getTopStocksDB } from "./services/stocks_db.js";
// 呼叫公開api下載相關資料
import { fetchTodayStocks } from "./services/Stocks_data.js";

const app = express();
app.use(cors());
app.use(express.json());

// ---------------- API ----------------
// ✅ 新增 MariaDB Top5 股票 API
app.get("/agent/top-stocks-db", getTopStocksDB);

// ✅ API: 從公開 API 抓前 300 交易量股票並存 KD
app.get("/agent/fetchTodayStocks", async (req, res) => {
  try {
    await fetchTodayStocks();
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});






// Agent 問答
app.post("/ask", async (req, res) => {
  const result = await runAgent(req.body.question);
  res.json({ result });
});


// 讀取持股
app.get("/agent/portfolio", (req, res) => {
  const memory = loadMemory();
  res.json({ portfolio: memory.portfolio || [] });
});

// 買賣操作
app.post("/agent/trade", (req, res) => {
  const { symbol, action, qty } = req.body;
  const memory = loadMemory();

  let stock = memory.portfolio.find((s) => s.symbol === symbol);

  if (action === "buy") {
    if (stock) stock.qty += qty;
    else memory.portfolio.push({ symbol, name: symbol, qty }); // name 可改成從 API 拿
  } else if (action === "sell") {
    if (stock) stock.qty -= qty;
    if (stock && stock.qty <= 0) memory.portfolio = memory.portfolio.filter((s) => s.symbol !== symbol);
  }

  saveMemory(memory);
  res.json({ success: true });
});

// --------------------------------------
app.listen(3000, () => console.log("Server running on 3000"));