import fs from "fs";
import path from "path";
import { getDataDir } from "./data-dir";
import { RevenueHistory } from "./types";

function getHistoryFile() {
  return path.join(getDataDir(), "revenue-history.json");
}

const emptyHistory: RevenueHistory = {
  days: {},
  recentSales: [],
  lastRangeSummary: null,
  lastRefreshAt: null,
};

export function loadHistory(): RevenueHistory {
  try {
    const f = getHistoryFile();
    if (!fs.existsSync(f)) return emptyHistory;
    return { ...emptyHistory, ...JSON.parse(fs.readFileSync(f, "utf-8")) };
  } catch {
    return emptyHistory;
  }
}

export function saveHistory(history: RevenueHistory): void {
  const file = getHistoryFile();
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(history, null, 2), "utf-8");
  fs.renameSync(tmp, file);
}
