// src/api/agentApi.js
import axios from "axios";

export const getTopStocks = async () => {
  const res = await axios.get("/agent/top-stocks-db");
  return res.data.top;
};

export const askAgent = async (question) => {
  const res = await axios.post("/ask", { question });
  return res.data.result;
};

export const getPortfolio = async () => {
  const res = await axios.get("/agent/portfolio");
  return res.data.portfolio;
};

export const executeTrade = async ({ symbol, action, qty }) => {
  const res = await axios.post("/agent/trade", { symbol, action, qty });
  return res.data;
};
