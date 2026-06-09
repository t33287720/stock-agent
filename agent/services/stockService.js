import axios from "axios";

export async function fetchStockData() {
  const res = await axios.get(
    "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
  );

  return res.data;
}