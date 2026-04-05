// Dashboard.jsx
import { useEffect, useState } from "react";
import { getTopStocks } from "../api/agentApi";
import StockTable from "../components/StockTable";

export default function Dashboard() {
  const [stocks, setStocks] = useState([]);

  useEffect(() => {
    async function fetchStocks() {
      const topStocks = await getTopStocks();
      setStocks(topStocks);
    }
    fetchStocks();
  }, []);

  return (
    <div>
      <h1>今日推薦台股</h1>
      <StockTable stocks={stocks} />
    </div>
  );
}