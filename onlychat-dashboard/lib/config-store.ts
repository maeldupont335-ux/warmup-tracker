import fs from "fs";
import path from "path";
import { getDataDir } from "./data-dir";
import { OnlyChatConfig } from "./types";

function getConfigFile() {
  return path.join(getDataDir(), "config.json");
}

const emptyConfig: OnlyChatConfig = {
  accessToken: null,
  refreshToken: null,
  organizationId: null,
  tokenSavedAt: null,
};

export function loadConfig(): OnlyChatConfig {
  try {
    const f = getConfigFile();
    if (!fs.existsSync(f)) return emptyConfig;
    return { ...emptyConfig, ...JSON.parse(fs.readFileSync(f, "utf-8")) };
  } catch {
    return emptyConfig;
  }
}

export function saveConfig(partial: Partial<OnlyChatConfig>): OnlyChatConfig {
  const current = loadConfig();
  const next: OnlyChatConfig = { ...current, ...partial, tokenSavedAt: new Date().toISOString() };
  fs.writeFileSync(getConfigFile(), JSON.stringify(next, null, 2), "utf-8");
  return next;
}
