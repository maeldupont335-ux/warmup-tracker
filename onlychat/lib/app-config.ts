import fs from "fs";
import path from "path";
import { getDataDir } from "./data-dir";

const CONFIG_FILE = path.join(getDataDir(), "app-config.json");

interface AppConfig {
  productionUrl: string; // ex: https://onlychat-ai.onrender.com
}

function ensureDir() {
  const dir = path.dirname(CONFIG_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

export function loadAppConfig(): AppConfig {
  try {
    if (!fs.existsSync(CONFIG_FILE)) return { productionUrl: "" };
    return JSON.parse(fs.readFileSync(CONFIG_FILE, "utf-8"));
  } catch { return { productionUrl: "" }; }
}

export function saveAppConfig(config: AppConfig) {
  ensureDir();
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2));
}

export function getWebhookBase(): string {
  // Priorité : env Render > config sauvegardée > env manuel
  if (process.env.RENDER_EXTERNAL_URL) return process.env.RENDER_EXTERNAL_URL.replace(/\/$/, "");
  if (process.env.NEXT_PUBLIC_APP_URL) return process.env.NEXT_PUBLIC_APP_URL.replace(/\/$/, "");
  const cfg = loadAppConfig();
  if (cfg.productionUrl) return cfg.productionUrl.replace(/\/$/, "");
  return "";
}
