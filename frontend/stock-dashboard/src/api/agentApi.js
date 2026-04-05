// src/api/agentApi.js
import axios from "axios";

export const getTopStocks = async () => {
  const res = await axios.get("http://localhost:3000/agent/top-stocks-db");
  return res.data.top;
};

export const askAgent = async (question) => {
  const res = await axios.post("http://localhost:3000/ask", { question });
  return res.data.result;
};

// ------------------ 新增 ------------------
export const getPortfolio = async () => {
  const res = await axios.get("http://localhost:3000/agent/portfolio");
  return res.data.portfolio; // 後端要回 { portfolio: [...] }
};

export const executeTrade = async ({ symbol, action, qty }) => {
  const res = await axios.post("http://localhost:3000/agent/trade", {
    symbol,
    action,
    qty,
  });
  return res.data; // { success: true/false }
};