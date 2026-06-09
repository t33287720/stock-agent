import { useState, useMemo } from "react";

export default function StockTable({ stocks }) {
  const [sortBy, setSortBy] = useState("ranking"); // 排序欄位：ranking / score / company_name
  const [sortOrder, setSortOrder] = useState("asc"); // asc / desc

  // 排序資料
  const sortedStocks = useMemo(() => {
    return [...stocks].sort((a, b) => {
      let valA = a[sortBy];
      let valB = b[sortBy];

      // 如果排序欄位是 ranking，NULL 排到最後
      if (sortBy === "ranking") {
        if (valA === null) return 1;
        if (valB === null) return -1;
      }

      // 比較大小
      if (typeof valA === "string") {
        valA = valA.toLowerCase();
        valB = valB.toLowerCase();
      }

      if (valA < valB) return sortOrder === "asc" ? -1 : 1;
      if (valA > valB) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });
  }, [stocks, sortBy, sortOrder]);

  // 點擊標題切換排序
  const handleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc"); // 同欄位切換升降序
    } else {
      setSortBy(field);
      setSortOrder("asc");
    }
  };

  return (
    <div className="stock-table-container">
      <table className="stock-table">
        <thead>
          <tr>
            <th onClick={() => handleSort("ranking")}>
              排名 {sortBy === "ranking" ? (sortOrder === "asc" ? "↑" : "↓") : ""}
            </th>
            <th onClick={() => handleSort("stock_id")}>
              代碼 {sortBy === "stock_id" ? (sortOrder === "asc" ? "↑" : "↓") : ""}
            </th>
            <th onClick={() => handleSort("company_name")}>
              公司名稱 {sortBy === "company_name" ? (sortOrder === "asc" ? "↑" : "↓") : ""}
            </th>
            <th>分析結果</th>
            <th onClick={() => handleSort("score")}>
              分數 {sortBy === "score" ? (sortOrder === "asc" ? "↑" : "↓") : ""}
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedStocks.map((s) => (
            <tr key={s.stock_id}>
              <td>
                <span
                  className={`rank-badge ${
                    s.ranking === 1
                      ? "rank-1"
                      : s.ranking === 2
                      ? "rank-2"
                      : s.ranking === 3
                      ? "rank-3"
                      : s.ranking === 4
                      ? "rank-4"
                      : s.ranking === 5
                      ? "rank-5"
                      : "rank-other"
                  }`}
                >
                  {s.ranking ?? "-"}
                </span>
              </td>
              <td>{s.stock_id}</td>
              <td>{s.company_name}</td>
              <td>{s.analysis_result}</td>
              <td>
                <div className="score-bar-bg">
                  <div
                    className="score-bar-fill"
                    style={{ width: `${s.score}%` }}
                  >
                    {s.score}%
                  </div>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}