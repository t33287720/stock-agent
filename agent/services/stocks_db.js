// backend/agent/top-stocks-db.js
import mysql from "mysql2/promise";

// 建立資料庫連線設定
const pool = mysql.createPool({
  host:     process.env.MYSQL_HOST     || "mariadb",
  user:     process.env.MYSQL_USER     || "root",
  password: process.env.MYSQL_PASSWORD || "",
  database: process.env.MYSQL_DATABASE || "stock",
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0,
});

// API handler
export async function getTopStocksDB(req, res) {
  try {
    const [rows] = await pool.query(
      `SELECT stock_id, company_name, ranking, score, analysis_result
   FROM stock_analysis
   WHERE analysis_date = CURDATE()`
    );
    res.json({ top: rows });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "讀取 Top5 股票失敗" });
  }
}