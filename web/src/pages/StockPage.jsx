// frontend/pages/StockPage.jsx
import { useEffect, useState } from "react";
import StockTable from "./StockTable";

export default function StockPage() {
  const [data, setData] = useState({ top5Stocks: [], llmRecommendation: {} });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const res = await fetch("/api/analyze_stock"); // 你的後端 API
        const json = await res.json();

        if (json.success) {
          setData(json.data);
        } else {
          setError(json.error || "未知錯誤");
        }
      } catch (e) {
        setError(e.toString());
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  if (loading) return <div className="p-4">讀取中...</div>;
  if (error) return <div className="p-4 text-red-500">錯誤: {error}</div>;

  return <StockTable top5Stocks={data.top5Stocks} llmRecommendation={data.llmRecommendation} />;
}