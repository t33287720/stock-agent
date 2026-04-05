import { useEffect, useState } from "react";
import { getPortfolio, executeTrade } from "../api/agentApi";

export default function Portfolio() {
  const [portfolio, setPortfolio] = useState([]);

  useEffect(() => {
    async function fetchPortfolio() {
      const data = await getPortfolio();
      setPortfolio(data);
    }
    fetchPortfolio();
  }, []);

  const handleTrade = async (symbol, action) => {
    const res = await executeTrade({ symbol, action, qty: 1 });
    alert(res.success ? "操作成功" : "操作失敗");
    setPortfolio(await getPortfolio());
  };

  return (
    <div>
      <h2>我的持股</h2>
      <table className="portfolio-table">
        <thead>
          <tr>
            <th>代碼</th>
            <th>名稱</th>
            <th>持股數</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {portfolio.map((p) => (
            <tr key={p.symbol}>
              <td>{p.symbol}</td>
              <td>{p.name}</td>
              <td>{p.qty}</td>
              <td>
                <button
                  onClick={() => handleTrade(p.symbol, "buy")}
                  className="trade-btn buy"
                >
                  買
                </button>
                <button
                  onClick={() => handleTrade(p.symbol, "sell")}
                  className="trade-btn sell"
                >
                  賣
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}