import fs from "fs";
import path from "path";
import { getDataDir } from "./data-dir";

export const ADMIN_EMAIL = "mael.dupont335@gmail.com";
export const LICENSE_PRICE_USD = 30;
export const COMMISSION_RATE = 0.10; // 10%
export const STARS_TO_USD = 0.013;   // 1 Star ≈ $0.013

export interface BillingTransaction {
  id: string;
  type: "deposit" | "license" | "commission" | "stars_sale";
  amount: number;       // en USD (positif = crédit, négatif = débit)
  stars?: number;       // nb de Stars vendues
  creatorId?: string;
  fanId?: string;
  scriptId?: string;
  description: string;
  createdAt: string;
}

export interface UserBilling {
  userId: string;
  email: string;
  balance: number;           // USD disponible
  totalStarsSold: number;
  totalRevenueUsd: number;   // avant commission
  totalCommissionUsd: number;
  licenseActive: boolean;
  licenseExpiry: string | null;
  transactions: BillingTransaction[];
}

export interface PlatformStats {
  totalUsers: number;
  totalRevenueUsd: number;
  totalCommissionUsd: number;
  totalStarsSold: number;
}

function billingDir() {
  const d = path.join(getDataDir(), "billing");
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
  return d;
}

function userBillingFile(userId: string) {
  return path.join(billingDir(), `${userId}.json`);
}

export function loadUserBilling(userId: string, email = ""): UserBilling {
  try {
    const f = userBillingFile(userId);
    if (fs.existsSync(f)) return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { /* ignore */ }
  return {
    userId, email, balance: 0,
    totalStarsSold: 0, totalRevenueUsd: 0, totalCommissionUsd: 0,
    licenseActive: false, licenseExpiry: null, transactions: [],
  };
}

export function saveUserBilling(billing: UserBilling) {
  fs.writeFileSync(userBillingFile(billing.userId), JSON.stringify(billing, null, 2));
}

export function addTransaction(userId: string, tx: Omit<BillingTransaction, "id" | "createdAt">) {
  const billing = loadUserBilling(userId);
  const full: BillingTransaction = {
    ...tx, id: Date.now().toString() + Math.random().toString(36).slice(2, 6),
    createdAt: new Date().toISOString(),
  };
  billing.transactions.unshift(full);
  billing.balance += tx.amount;
  if (tx.type === "stars_sale" && tx.stars) {
    billing.totalStarsSold += tx.stars;
    billing.totalRevenueUsd += Math.abs(tx.amount) / (1 - COMMISSION_RATE);
    billing.totalCommissionUsd += Math.abs(tx.amount) / (1 - COMMISSION_RATE) * COMMISSION_RATE;
  }
  saveUserBilling(billing);
  return billing;
}

/** Acheter une licence (déduit 30$ du solde) */
export function purchaseLicense(userId: string): { ok: boolean; error?: string } {
  const billing = loadUserBilling(userId);
  if (billing.balance < LICENSE_PRICE_USD)
    return { ok: false, error: `Solde insuffisant (${billing.balance.toFixed(2)}$ / ${LICENSE_PRICE_USD}$ requis)` };
  billing.balance -= LICENSE_PRICE_USD;
  billing.licenseActive = true;
  const expiry = new Date();
  expiry.setMonth(expiry.getMonth() + 1);
  billing.licenseExpiry = expiry.toISOString();
  billing.transactions.unshift({
    id: Date.now().toString(), type: "license",
    amount: -LICENSE_PRICE_USD, description: "Licence mensuelle OnlyChat AI",
    createdAt: new Date().toISOString(),
  });
  saveUserBilling(billing);
  return { ok: true };
}

/** Enregistre une vente de Stars (appelé par le bot) */
export function recordStarsSale(
  userId: string, creatorId: string, fanId: string,
  scriptId: string, stars: number
) {
  const revenueUsd = stars * STARS_TO_USD;
  const commissionUsd = revenueUsd * COMMISSION_RATE;
  const netUsd = revenueUsd - commissionUsd;
  addTransaction(userId, {
    type: "stars_sale", amount: netUsd, stars,
    creatorId, fanId, scriptId,
    description: `Vente ${stars}⭐ via script (net après 10% commission)`,
  });

  // Met à jour le totalStars du fan
  try {
    const { loadFans, saveFans } = require("../app/api/creators/[id]/fans/route");
    const fans = loadFans(creatorId);
    const idx = fans.findIndex((f: { telegramId: string }) => f.telegramId === fanId);
    if (idx >= 0) {
      fans[idx].totalStars = (fans[idx].totalStars ?? 0) + stars;
      fans[idx].totalUsd = (fans[idx].totalUsd ?? 0) + revenueUsd;
      saveFans(creatorId, fans);
    }
  } catch { /* ignore */ }
}

/** Stats globales de la plateforme (admin seulement) */
export function getPlatformStats(): PlatformStats & { users: UserBilling[] } {
  const dir = billingDir();
  const users: UserBilling[] = [];
  for (const f of fs.readdirSync(dir)) {
    if (!f.endsWith(".json")) continue;
    try { users.push(JSON.parse(fs.readFileSync(path.join(dir, f), "utf-8"))); } catch { /* */ }
  }
  return {
    totalUsers: users.length,
    totalRevenueUsd: users.reduce((s, u) => s + u.totalRevenueUsd, 0),
    totalCommissionUsd: users.reduce((s, u) => s + u.totalCommissionUsd, 0),
    totalStarsSold: users.reduce((s, u) => s + u.totalStarsSold, 0),
    users,
  };
}
