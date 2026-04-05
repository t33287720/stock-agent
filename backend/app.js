import express from "express";
import cors from "cors";
import { runAgent } from "./agent/agent.js";
import { loadMemory, saveMemory } from "./agent/memory.js";

// ✅ 新增 import
import { getTopStocksDB } from "./agent/top-stocks-db.js";

const app = express();
app.use(cors());
app.use(express.json());

// ---------------- API ----------------

// Agent 問答
app.post("/ask", async (req, res) => {
  const result = await runAgent(req.body.question);
  res.json({ result });
});

// Top 5 股票
app.get("/agent/top-stocks", async (req, res) => {
  const result = await runAgent("請推薦今日台股Top5");
  res.json({ result });
});

// ✅ 新增 MariaDB Top5 股票 API
app.get("/agent/top-stocks-db", getTopStocksDB);

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