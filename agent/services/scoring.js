export function calculateTopStocks(data) {
  return data
    .map(s => {
      const change = parseFloat(s.change || 0);
      const volume = parseInt(s.tradeVolume || 0);

      let score = 0;

      if (change > 0) score += 30;
      if (volume > 10000) score += 30;

      return {
        ...s,
        score
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);
}