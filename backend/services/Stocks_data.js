// Stocks_data.js
import fetch from "node-fetch";
import fs from "fs";
import path from "path";

// 資料存放根目錄
const DATA_ROOT = "/opt/stock/backend/data";
const KEEP_DAYS = 14;

// 今日資料夾
function getTodayFolder() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  const folder = path.join(DATA_ROOT, `${yyyy}${mm}${dd}`);
  if (!fs.existsSync(folder)) fs.mkdirSync(folder, { recursive: true });
  return folder;
}

// 清理過期資料夾
function cleanOldData() {
  if (!fs.existsSync(DATA_ROOT)) return;
  const dirs = fs.readdirSync(DATA_ROOT);
  const now = new Date();
  dirs.forEach(dir => {
    const dirPath = path.join(DATA_ROOT, dir);
    if (!fs.lstatSync(dirPath).isDirectory()) return;
    const dirDate = dir.match(/^(\d{8})$/);
    if (!dirDate) return;
    const y = parseInt(dirDate[1].slice(0,4));
    const m = parseInt(dirDate[1].slice(4,6)) - 1;
    const d = parseInt(dirDate[1].slice(6,8));
    const folderDate = new Date(y, m, d);
    const diffDays = (now - folderDate) / (1000*60*60*24);
    if (diffDays > KEEP_DAYS) fs.rmSync(dirPath, { recursive: true, force: true });
  });
}

// 公開 API 列表（每日抓取）
const APIs = [
  { name: "STOCK_DAY_ALL", url: "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL" },
  { name: "BWIBBU_ALL", url: "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL" },
  { name: "STOCK_DAY_AVG_ALL", url: "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_AVG_ALL" },
  { name: "t187ap03_L", url: "https://openapi.twse.com.tw/v1/opendata/t187ap03_L" }, // 公司基本資料
  { name: "t187ap02_L", url: "https://openapi.twse.com.tw/v1/opendata/t187ap02_L" }, // 大股東持股
  { name: "t187ap05_P", url: "https://openapi.twse.com.tw/v1/opendata/t187ap05_P" }, // 每月營業收入
  { name: "t187ap12_L", url: "https://openapi.twse.com.tw/v1/opendata/t187ap12_L" }, // 內部人持股轉讓日報表
  { name: "t187ap13_L", url: "https://openapi.twse.com.tw/v1/opendata/t187ap13_L" }, // 內部人持股未轉讓
  { name: "TWT48U_ALL", url: "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL" }, // 除權除息預告
  { name: "announcement_notice", url: "https://openapi.twse.com.tw/v1/announcement/notice" }, // 當日注意股票
  { name: "announcement_notetrans", url: "https://openapi.twse.com.tw/v1/announcement/notetrans" }, // 注意累計次數異常資訊
  { name: "t187ap04_L", url: "https://openapi.twse.com.tw/v1/opendata/t187ap04_L" } // 每日重大訊息
];

// 取得今日股票資料
export async function fetchTodayStocks() {
  cleanOldData();
  const folder = getTodayFolder();

  for (const api of APIs) {
    try {
      const res = await fetch(api.url);
      const data = await res.json();
      const filePath = path.join(folder, `${api.name}.json`);

      // 特殊處理每日重大訊息，累積歷史
      if (api.name === "t187ap04_L") {
        const historyFile = path.join(DATA_ROOT, "t187ap04_L_history.json");
        let history = [];
        if (fs.existsSync(historyFile)) {
          history = JSON.parse(fs.readFileSync(historyFile));
        }
        // 合併新資料，去重（依公告編號）
        const existingIds = new Set(history.map(x => x.公告編號 || x.id));
        data.forEach(item => {
          const id = item.公告編號 || item.id;
          if (!existingIds.has(id)) history.push(item);
        });
        fs.writeFileSync(historyFile, JSON.stringify(history, null, 2));
        console.log(`✅ 更新歷史重大訊息到 ${historyFile}`);
      }

      // 其他 API 直接存當天資料
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
      console.log(`✅ 已儲存 ${api.name} 到 ${filePath}`);
    } catch (err) {
      console.error(`❌ 下載 ${api.name} 失敗: ${err.message}`);
    }
  }
}