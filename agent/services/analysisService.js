import { loadMemory, saveMemory } from "../agent/memory.js";

export function analyzeStrategy() {
  const memory = loadMemory();
  const perf = memory.performance;

  const win = perf.filter(p => p.profit_percent > 5);
  const lose = perf.filter(p => p.profit_percent < -5);

  const result = {
    date: new Date().toISOString(),
    total: perf.length,
    win: win.length,
    lose: lose.length,
    win_rate: perf.length ? (win.length / perf.length * 100).toFixed(2) : 0,

    problems: lose.map(l => ({
      stock: l.stock,
      reason: l.reason
    })),

    strengths: win.map(w => ({
      stock: w.stock,
      reason: w.reason
    }))
  };

  memory.reflection.push(result);
  saveMemory(memory);

  return result;
}