// backend/scheduler/cron.js
import cron from "node-cron";
import { runAgent } from "../agent/agent.js";
import { evaluatePerformance } from "../services/performanceService.js";
import { analyzeStrategy } from "../services/analysisService.js";

// 每日 8:00 推薦
cron.schedule("0 8 * * *", async () => {
  console.log("⏰ 每日推薦");
  const result = await runAgent();
  console.log(result);
});

// 每日 18:00 回測 + 檢討
cron.schedule("0 18 * * *", async () => {
  console.log("📊 每日回測");

  const performance = await evaluatePerformance();
  console.log("績效:", performance);

  const reflection = analyzeStrategy();
  console.log("策略分析:", reflection);
});