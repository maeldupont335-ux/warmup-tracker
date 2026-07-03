import fs from "fs";
import path from "path";
import { getDataDir } from "./data-dir";
import type { StyleProfile } from "./style-analyzer";
import { SEED_PROFILES } from "./seed-profiles";

// Initialise les profils seeds si le créateur n'a aucun profil
export function initSeedProfiles(creatorId: string) {
  const index = loadStyleIndex(creatorId);
  if (index.profiles.length > 0) return;
  const seeds = SEED_PROFILES[creatorId];
  if (!seeds) return;
  for (const seed of seeds) {
    saveStyleProfile(seed.creatorId, seed.profile, seed.profileName, true);
  }
}

export interface StyleProfileMeta {
  slug: string;
  name: string;
  totalMessages: number;
  examples: number;
  createdAt: string;
}

export interface StyleIndex {
  active: string | null;
  profiles: StyleProfileMeta[];
}

function indexFile(creatorId: string) {
  return path.join(getDataDir(), `styles-index-${creatorId}.json`);
}

function profileFile(creatorId: string, slug: string) {
  return path.join(getDataDir(), `style-${creatorId}-${slug}.json`);
}

function ensureDir() {
  const dir = getDataDir();
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

export function loadStyleIndex(creatorId: string): StyleIndex {
  try {
    const f = indexFile(creatorId);
    if (!fs.existsSync(f)) return { active: null, profiles: [] };
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return { active: null, profiles: [] }; }
}

function saveStyleIndex(creatorId: string, index: StyleIndex) {
  ensureDir();
  fs.writeFileSync(indexFile(creatorId), JSON.stringify(index, null, 2));
}

export function loadActiveStyleProfile(creatorId: string): StyleProfile | null {
  try {
    // Auto-initialise les profils seeds si aucun profil existant
    initSeedProfiles(creatorId);
    // Nouveau système multi-profils
    const index = loadStyleIndex(creatorId);
    if (index.active) {
      const f = profileFile(creatorId, index.active);
      if (fs.existsSync(f)) return JSON.parse(fs.readFileSync(f, "utf-8"));
    }
    // Fallback: ancien fichier style-{creatorId}.json
    const legacy = path.join(getDataDir(), `style-${creatorId}.json`);
    if (fs.existsSync(legacy)) return JSON.parse(fs.readFileSync(legacy, "utf-8"));
    return null;
  } catch { return null; }
}

export function saveStyleProfile(
  creatorId: string,
  profile: StyleProfile,
  profileName: string,
  setActive = true
): StyleProfileMeta {
  ensureDir();
  const slug = profileName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 40) || `profile-${Date.now()}`;

  fs.writeFileSync(profileFile(creatorId, slug), JSON.stringify(profile, null, 2));

  const index = loadStyleIndex(creatorId);
  const meta: StyleProfileMeta = {
    slug,
    name: profileName,
    totalMessages: profile.totalMessagesAnalyzed ?? 0,
    examples: profile.realExamples?.length ?? 0,
    createdAt: new Date().toISOString(),
  };

  // Remplace si même slug, sinon ajoute
  const idx = index.profiles.findIndex(p => p.slug === slug);
  if (idx >= 0) index.profiles[idx] = meta;
  else index.profiles.push(meta);

  if (setActive || !index.active) index.active = slug;
  saveStyleIndex(creatorId, index);
  return meta;
}

export function deleteStyleProfile(creatorId: string, slug: string) {
  const f = profileFile(creatorId, slug);
  if (fs.existsSync(f)) fs.unlinkSync(f);

  const index = loadStyleIndex(creatorId);
  index.profiles = index.profiles.filter(p => p.slug !== slug);
  if (index.active === slug) {
    index.active = index.profiles[0]?.slug ?? null;
  }
  saveStyleIndex(creatorId, index);
}

export function setActiveProfile(creatorId: string, slug: string) {
  const index = loadStyleIndex(creatorId);
  if (!index.profiles.find(p => p.slug === slug)) return;
  index.active = slug;
  saveStyleIndex(creatorId, index);
}

export function getStyleProfile(creatorId: string, slug: string): StyleProfile | null {
  try {
    const f = profileFile(creatorId, slug);
    if (!fs.existsSync(f)) return null;
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return null; }
}
