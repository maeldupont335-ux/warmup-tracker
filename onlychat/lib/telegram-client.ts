import { TelegramClient } from "telegram";
import { StringSession } from "telegram/sessions";
import { Api } from "telegram";
import fs from "fs";
import path from "path";

import { getDataDir } from "./data-dir";
const SESSION_FILE = () => path.join(getDataDir(), "telegram-session.txt");
const API_ID = parseInt(process.env.TELEGRAM_API_ID || "0");
const API_HASH = process.env.TELEGRAM_API_HASH || "";

function loadSession(): string {
  try {
    const f = SESSION_FILE();
    if (fs.existsSync(f)) return fs.readFileSync(f, "utf-8").trim();
  } catch { /* ignore */ }
  return "";
}

export function saveSession(session: string) {
  const f = SESSION_FILE();
  const dir = path.dirname(f);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(f, session, "utf-8");
}

export function isConnected(): boolean {
  return loadSession().length > 0;
}

export async function getClient(): Promise<TelegramClient> {
  const session = new StringSession(loadSession());
  const client = new TelegramClient(session, API_ID, API_HASH, {
    connectionRetries: 3,
  });
  await client.connect();
  return client;
}

// Étape 1 : envoie le code SMS
let pendingClient: TelegramClient | null = null;
let pendingPhone = "";

export async function sendCode(phone: string): Promise<{ phoneCodeHash: string }> {
  const session = new StringSession("");
  pendingClient = new TelegramClient(session, API_ID, API_HASH, { connectionRetries: 3 });
  await pendingClient.connect();
  pendingPhone = phone;

  const result = await pendingClient.sendCode({ apiId: API_ID, apiHash: API_HASH }, phone);
  return { phoneCodeHash: result.phoneCodeHash };
}

// Étape 2 : vérifie le code et sauvegarde la session
export async function verifyCode(code: string, phoneCodeHash: string): Promise<boolean> {
  if (!pendingClient) throw new Error("Pas de connexion en attente");
  try {
    await pendingClient.invoke(
      new Api.auth.SignIn({
        phoneNumber: pendingPhone,
        phoneCodeHash,
        phoneCode: code,
      })
    );
    const sessionStr = (pendingClient.session as StringSession).save();
    saveSession(sessionStr);
    pendingClient = null;
    return true;
  } catch (err: unknown) {
    const e = err as { errorMessage?: string };
    if (e?.errorMessage === "SESSION_PASSWORD_NEEDED") {
      throw new Error("2FA_REQUIRED");
    }
    throw err;
  }
}

// 2FA si activé
export async function verify2FA(password: string): Promise<boolean> {
  if (!pendingClient) throw new Error("Pas de connexion en attente");
  await pendingClient.signInWithPassword(
    { apiId: API_ID, apiHash: API_HASH },
    { password: async () => password, onError: async () => false }
  );
  const sessionStr = (pendingClient.session as StringSession).save();
  saveSession(sessionStr);
  pendingClient = null;
  return true;
}
