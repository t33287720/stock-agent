import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const dataDir = path.join(__dirname, "/var/www/html/stock-ai-agent/backend/data");  // 指向 backend/data
const memoryPath = path.join(dataDir, "memory.json");

export function loadMemory() {
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }

  if (!fs.existsSync(memoryPath)) {
    const initialMemory = { history: [], portfolio: [], recommendations: [] };
    fs.writeFileSync(memoryPath, JSON.stringify(initialMemory, null, 2));
    return initialMemory;
  }

  const data = JSON.parse(fs.readFileSync(memoryPath));
  data.history = data.history || [];
  data.portfolio = data.portfolio || [];
  data.recommendations = data.recommendations || [];
  return data;
}

export function saveMemory(data) {
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
  fs.writeFileSync(memoryPath, JSON.stringify(data, null, 2));
}