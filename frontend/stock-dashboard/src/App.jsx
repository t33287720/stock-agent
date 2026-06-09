import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import PortfolioPage from "./pages/PortfolioPage";
import "./App.css"; // 引入 CSS

import { useState } from "react";

function NavBar() {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const handleFetchTop100 = async () => {
    setLoading(true);
    setMessage("");
    try {
      const res = await fetch("http://localhost:3000/agent/fetchTodayStocks");
      const data = await res.json();
      if (data.success) {
        setMessage("完成！");  // ✅ 只要成功就顯示完成
      } else {
        setMessage(`錯誤: ${data.error}`);
      }
    } catch (err) {
      setMessage(`網路錯誤: ${err.message}`);
    }
    setLoading(false);
  };
  return (
    <nav className="navbar">
      <NavLink to="/" className={({ isActive }) => (isActive ? "active" : "")}>
        Dashboard
      </NavLink>
      <NavLink
        to="/portfolio"
        className={({ isActive }) => (isActive ? "active" : "")}
      >
        Portfolio
      </NavLink>

      {/* 新增按鈕 */}
      <button
        onClick={handleFetchTop100}
        disabled={loading}
        style={{ marginLeft: "20px", padding: "5px 10px" }}
      >
        {loading ? "抓取中..." : "抓取公開 API 資料"}
      </button>

      {/* 顯示訊息 */}
      {message && <span style={{ marginLeft: "10px" }}>{message}</span>}
    </nav>
  );
}

function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <div className="main-container">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;