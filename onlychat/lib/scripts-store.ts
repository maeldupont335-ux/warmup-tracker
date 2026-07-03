import fs from "fs";
import path from "path";
import { getDataDir } from "./data-dir";

export interface PostMediaMessage {
  id: string;
  message: string;
  delaySeconds: number;
  mediaUrl?: string;
}

export interface ScriptStep {
  id: string;
  order: number;
  message: string;
  mediaUrls: string[];           // fichiers uploadés
  waitBeforeMedia: boolean;      // attendre avant d'envoyer vidéo/audio
  priceStars: number;            // 0 = gratuit
  discountEnabled: boolean;
  discountedPriceStars: number;
  messagesBetweenSteps: "fast" | "normal" | "slow"; // 1-2 / 4-5 / 8-10
  skipFollowupIfPaid: boolean;
  preMediaTeaser: string;
  postMediaMessages: PostMediaMessage[];
}

export interface Script {
  id: string;
  creatorId: string;
  name: string;
  description: string;
  active: boolean;
  first: boolean;                // marqué comme "premier" (étoile)
  group: string | null;
  strictCooldown: boolean;
  inactivityTimeoutHours: number;
  steps: ScriptStep[];
  createdAt: string;
  updatedAt: string;
}

function filePath(creatorId: string) {
  return path.join(getDataDir(), "creators", `${creatorId}-scripts.json`);
}

function ensureDir(creatorId: string) {
  const dir = path.join(getDataDir(), "creators");
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return filePath(creatorId);
}

export function loadScripts(creatorId: string): Script[] {
  try {
    const file = filePath(creatorId);
    if (!fs.existsSync(file)) return [];
    return JSON.parse(fs.readFileSync(file, "utf-8"));
  } catch { return []; }
}

export function saveScripts(creatorId: string, scripts: Script[]) {
  const file = ensureDir(creatorId);
  fs.writeFileSync(file, JSON.stringify(scripts, null, 2));
}

export function getScript(creatorId: string, scriptId: string): Script | null {
  return loadScripts(creatorId).find(s => s.id === scriptId) ?? null;
}

export function defaultStep(order = 1): ScriptStep {
  return {
    id: Date.now().toString() + Math.random().toString(36).slice(2, 6),
    order,
    message: "",
    mediaUrls: [],
    waitBeforeMedia: false,
    priceStars: 0,
    discountEnabled: false,
    discountedPriceStars: 0,
    messagesBetweenSteps: "normal",
    skipFollowupIfPaid: false,
    preMediaTeaser: "",
    postMediaMessages: [],
  };
}

export function defaultScript(creatorId: string): Script {
  return {
    id: Date.now().toString(),
    creatorId,
    name: `SCRIPT ${Date.now().toString().slice(-4)}`,
    description: "",
    active: false,
    first: false,
    group: null,
    strictCooldown: false,
    inactivityTimeoutHours: 4,
    steps: [defaultStep(1)],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}
