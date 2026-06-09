// stock_100top.js
import fetch from "node-fetch";

// 計算 KD
function calculateKD(history, period = 14) {
    let K = 50, D = 50;
    history.sort((a, b) => new Date(a.Date) - new Date(b.Date));

    const result = [];

    for (let i = 0; i < history.length; i++) {
        const slice = history.slice(Math.max(0, i - period + 1), i + 1);
        const highs = slice.map(h => parseFloat((h.HighestPrice || "0").replace(/,/g, '')));
        const lows = slice.map(h => parseFloat((h.LowestPrice || "0").replace(/,/g, '')));
        const close = parseFloat((history[i].ClosingPrice || "0").replace(/,/g, ''));

        const highN = Math.max(...highs);
        const lowN = Math.min(...lows);
        const rsv = highN === lowN ? 0 : ((close - lowN) / (highN - lowN)) * 100;

        K = K * 2 / 3 + rsv / 3;
        D = D * 2 / 3 + K / 3;

        result.push({
            trade_date: history[i].Date,
            K: parseFloat(K.toFixed(2)),
            D: parseFloat(D.toFixed(2)),
            rsv: parseFloat(rsv.toFixed(2))
        });
    }

    return result;
}