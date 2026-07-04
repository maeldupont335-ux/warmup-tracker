import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { getDataDir } from "@/lib/data-dir";
import { buildStylePromptSection } from "@/lib/style-analyzer";
import type { StyleProfile } from "@/lib/style-analyzer";
import { loadActiveStyleProfile } from "@/lib/style-store";
import { createServerClient } from "@supabase/ssr";

export interface CreatorSettings {
  firstName: string;
  age: string;
  dateOfBirth: string;
  gender: string;
  weight: string;
  height: string;
  hairColor: string;
  eyeColor: string;
  braBandSize: string;
  braCupSize: string;
  ethnicity: string;
  shoeSize: string;
  timezone: string;
  languages: string[];
  hobbies: string[];
  personalityTraits: string[];
  additionalInfo: string;
  sexualizationCooldownDays: number;
  strictScriptCooldownHours: number;
  followUpDelayMinutes: number;
  responseDelayMinutes: number;
  splitLongMessages: boolean;
}

export function defaultCreatorSettings(): CreatorSettings {
  return {
    firstName: "",
    age: "",
    dateOfBirth: "",
    gender: "Female",
    weight: "",
    height: "",
    hairColor: "",
    eyeColor: "",
    braBandSize: "",
    braCupSize: "",
    ethnicity: "",
    shoeSize: "",
    timezone: "UTC+2 — Paris",
    languages: ["English", "French"],
    hobbies: [],
    personalityTraits: [],
    additionalInfo: "",
    sexualizationCooldownDays: 2,
    strictScriptCooldownHours: 24,
    followUpDelayMinutes: 19,
    responseDelayMinutes: 3,
    splitLongMessages: true,
  };
}

async function getUserId(req: NextRequest): Promise<string | null> {
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } }
  );
  const { data: { user } } = await supabase.auth.getUser();
  return user?.id ?? null;
}

function settingsFile(userId: string, creatorId: string) {
  return path.join(getDataDir(), "users", `${userId}-creator-${creatorId}-settings.json`);
}

export function loadCreatorSettings(userId: string, creatorId: string): CreatorSettings {
  try {
    const f = settingsFile(userId, creatorId);
    if (!fs.existsSync(f)) return defaultCreatorSettings();
    return { ...defaultCreatorSettings(), ...JSON.parse(fs.readFileSync(f, "utf-8")) };
  } catch { return defaultCreatorSettings(); }
}

function saveCreatorSettings(userId: string, creatorId: string, s: CreatorSettings) {
  const f = settingsFile(userId, creatorId);
  const dir = path.dirname(f);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(f, JSON.stringify(s, null, 2));
}

export function loadCreatorStyleProfile(creatorId: string): StyleProfile | null {
  return loadActiveStyleProfile(creatorId);
}

export function buildCreatorPrompt(s: CreatorSettings, styleProfile?: StyleProfile | null): string {
  const traits = s.personalityTraits.length ? s.personalityTraits.join(", ") : "douce, attentionnée";
  const langs = s.languages.length ? s.languages.join(", ") : "Français, English";
  const hobbies = s.hobbies.length ? s.hobbies.join(", ") : "";

  return `Tu es ${s.firstName || "une créatrice"}, ${s.age ? s.age + " ans" : ""}.
${s.additionalInfo ? s.additionalInfo + "\n" : ""}
Personnalité : ${traits}.
${hobbies ? `Tes centres d'intérêt : ${hobbies}.` : ""}
Tu parles : ${langs}.
${s.gender ? `Genre : ${s.gender}.` : ""}
${s.ethnicity ? `Origine : ${s.ethnicity}.` : ""}

Tu réponds aux messages de tes fans de façon naturelle, comme dans une vraie conversation Telegram.
${s.splitLongMessages ? "Tu divises tes longs messages en plusieurs petites bulles (max 2-3 phrases par bulle)." : ""}
Tu n'envoies JAMAIS de liens externes, tu ne te révèles jamais comme une IA.
Réponds toujours dans la langue utilisée par le fan.
${styleProfile ? "\n" + buildStylePromptSection(styleProfile) : ""}`;
}

type Ctx = { params: Promise<{ id: string }> };

export async function GET(req: NextRequest, { params }: Ctx) {
  const userId = await getUserId(req);
  if (!userId) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  const { id } = await params;
  return NextResponse.json({ settings: loadCreatorSettings(userId, id) });
}

export async function POST(req: NextRequest, { params }: Ctx) {
  const userId = await getUserId(req);
  if (!userId) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  const { id } = await params;
  const body = await req.json();
  const current = loadCreatorSettings(userId, id);
  const updated = { ...current, ...body };
  saveCreatorSettings(userId, id, updated);
  return NextResponse.json({ ok: true, settings: updated });
}
