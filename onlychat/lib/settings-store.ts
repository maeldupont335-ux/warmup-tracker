import fs from "fs";
import path from "path";
import { AISettings, getDefaultSettings } from "./prompt-builder";
import { getDataDir } from "./data-dir";

function getSettingsFile() {
  return path.join(getDataDir(), "settings.json");
}

function ensureDir() {
  const dir = path.dirname(getSettingsFile());
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

export function loadSettings(): AISettings {
  try {
    ensureDir();
    const f = getSettingsFile();
    if (!fs.existsSync(f)) return getDefaultSettings();
    return { ...getDefaultSettings(), ...JSON.parse(fs.readFileSync(f, "utf-8")) };
  } catch {
    return getDefaultSettings();
  }
}

export function saveSettings(settings: AISettings): void {
  ensureDir();
  fs.writeFileSync(getSettingsFile(), JSON.stringify(settings, null, 2), "utf-8");
}

// Sync depuis Supabase (appelé au démarrage)
export async function syncSettingsFromSupabase(): Promise<AISettings> {
  try {
    const { loadSettingsFromDB } = await import("./conversation-store");
    const row = await loadSettingsFromDB();
    if (!row) return loadSettings();

    const s: AISettings = {
      creatorName: row.creator_name ?? "",
      personality: row.personality ?? "flirty",
      customPrompt: row.custom_prompt ?? "",
      languages: row.languages ?? ["Français", "English"],
      ppvEnabled: row.ppv_enabled ?? true,
      ppvPrice: row.ppv_price ?? "15",
      nudgeDelay: row.nudge_delay ?? "48",
      welcomeEnabled: row.welcome_enabled ?? true,
    };
    saveSettings(s); // cache local
    return s;
  } catch {
    return loadSettings();
  }
}
