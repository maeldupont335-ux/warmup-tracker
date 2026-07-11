import fs from "fs";
import path from "path";
import { getDataDir } from "./data-dir";

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
  ts: number;
}

const MAX_MESSAGES = 40;

function historyFile(creatorId: string, fanId: string) {
  const dir = path.join(getDataDir(), "history");
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `${creatorId}_${fanId}.json`);
}

export function loadLocalHistory(creatorId: string, fanId: string): HistoryMessage[] {
  try {
    const f = historyFile(creatorId, fanId);
    if (!fs.existsSync(f)) return [];
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return []; }
}

export function appendLocalHistory(creatorId: string, fanId: string, messages: HistoryMessage[]) {
  try {
    const existing = loadLocalHistory(creatorId, fanId);
    const updated = [...existing, ...messages].slice(-MAX_MESSAGES);
    fs.writeFileSync(historyFile(creatorId, fanId), JSON.stringify(updated));
  } catch { /* ignore */ }
}
