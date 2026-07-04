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

export interface CreatorLicense {
  creatorId: string;
  creatorName: string;
  active: boolean;
  expiry: string | null;     // ISO date
  autoRenew: boolean;
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
  creatorLicenses: Record<string, CreatorLicense>; // clé = creatorId
  telegramLicensePool: number; // licences Telegram achetées non encore assignées
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
    if (fs.existsSync(f)) {
      const data = JSON.parse(fs.readFileSync(f, "utf-8"));
      if (!data.creatorLicenses) data.creatorLicenses = {};
      if (data.telegramLicensePool === undefined) data.telegramLicensePool = 0;
      return data;
    }
  } catch { /* ignore */ }
  return {
    userId, email, balance: 0,
    totalStarsSold: 0, totalRevenueUsd: 0, totalCommissionUsd: 0,
    licenseActive: false, licenseExpiry: null,
    creatorLicenses: {}, telegramLicensePool: 0, transactions: [],
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

/** Achète N licences Telegram (ajout au pool) */
export function buyTelegramLicenses(
  userId: string, quantity: number
): { ok: boolean; error?: string; newBalance?: number } {
  const total = LICENSE_PRICE_USD * quantity;
  const billing = loadUserBilling(userId);
  if (billing.balance < total)
    return { ok: false, error: `Solde insuffisant (${billing.balance.toFixed(2)}$ / ${total.toFixed(2)}$ requis)` };

  billing.balance -= total;
  billing.telegramLicensePool = (billing.telegramLicensePool ?? 0) + quantity;
  billing.transactions.unshift({
    id: Date.now().toString(), type: "license",
    amount: -total,
    description: `Achat ${quantity} licence${quantity > 1 ? "s" : ""} Telegram ($${LICENSE_PRICE_USD}/mois)`,
    createdAt: new Date().toISOString(),
  });
  saveUserBilling(billing);
  return { ok: true, newBalance: billing.balance };
}

/** Vérifie si la licence d'un créateur est active */
export function isCreatorLicenseActive(userId: string, creatorId: string): boolean {
  const billing = loadUserBilling(userId);
  const lic = billing.creatorLicenses?.[creatorId];
  if (!lic) return false;
  return lic.active && !!lic.expiry && new Date(lic.expiry) > new Date();
}

/** Assigne une licence du pool à un créateur (ou achète directement si pool vide) */
export function purchaseCreatorLicense(
  userId: string, creatorId: string, creatorName: string
): { ok: boolean; error?: string } {
  const billing = loadUserBilling(userId);

  // Guard : si ce créateur a déjà une licence active, ne pas débiter une deuxième fois
  const existing = billing.creatorLicenses?.[creatorId];
  if (existing?.active && existing?.expiry && new Date(existing.expiry) > new Date()) {
    return { ok: true }; // déjà actif, rien à faire
  }

  const fromPool = (billing.telegramLicensePool ?? 0) > 0;

  if (!fromPool && billing.balance < LICENSE_PRICE_USD)
    return { ok: false, error: `Solde insuffisant (${billing.balance.toFixed(2)}$ / ${LICENSE_PRICE_USD}$ requis) et aucune licence disponible dans le pool` };

  if (fromPool) {
    billing.telegramLicensePool -= 1;
    // Pas de transaction : la licence est déjà payée (déjà comptée lors de l'achat du pool)
  } else {
    billing.balance -= LICENSE_PRICE_USD;
    billing.transactions.unshift({
      id: Date.now().toString(), type: "license",
      amount: -LICENSE_PRICE_USD,
      description: `Licence achetée et assignée à ${creatorName}`,
      createdAt: new Date().toISOString(),
    });
  }
  const expiry = new Date();
  expiry.setDate(expiry.getDate() + 30);

  billing.creatorLicenses = billing.creatorLicenses ?? {};
  billing.creatorLicenses[creatorId] = {
    creatorId, creatorName,
    active: true,
    expiry: expiry.toISOString(),
    autoRenew: billing.creatorLicenses[creatorId]?.autoRenew ?? false,
  };

  saveUserBilling(billing);
  return { ok: true };
}

/** Suspend une licence (désactive le bot sans annuler les jours restants) */
export function suspendCreatorLicense(userId: string, creatorId: string): { ok: boolean } {
  const billing = loadUserBilling(userId);
  const lic = billing.creatorLicenses?.[creatorId];
  if (!lic) return { ok: false };
  // On marque active=false mais on garde expiry intact — les jours restants sont préservés
  lic.active = false;
  billing.creatorLicenses[creatorId] = lic;
  saveUserBilling(billing);
  return { ok: true };
}

/** Réactive une licence suspendue (si elle n'a pas encore expiré) */
export function reactivateCreatorLicense(userId: string, creatorId: string): { ok: boolean; error?: string } {
  const billing = loadUserBilling(userId);
  const lic = billing.creatorLicenses?.[creatorId];
  if (!lic) return { ok: false, error: "Aucune licence trouvée" };
  if (!lic.expiry || new Date(lic.expiry) <= new Date())
    return { ok: false, error: "Licence expirée — veuillez en acheter une nouvelle" };
  lic.active = true;
  billing.creatorLicenses[creatorId] = lic;
  saveUserBilling(billing);
  return { ok: true };
}

/** Active/désactive le renouvellement automatique */
export function setCreatorAutoRenew(userId: string, creatorId: string, autoRenew: boolean) {
  const billing = loadUserBilling(userId);
  billing.creatorLicenses = billing.creatorLicenses ?? {};
  if (!billing.creatorLicenses[creatorId]) {
    billing.creatorLicenses[creatorId] = { creatorId, creatorName: creatorId, active: false, expiry: null, autoRenew };
  } else {
    billing.creatorLicenses[creatorId].autoRenew = autoRenew;
  }
  saveUserBilling(billing);
}

/** Vérifie et renouvelle automatiquement les licences expirées */
export function autoRenewExpiredLicenses(userId: string): void {
  const billing = loadUserBilling(userId);
  if (!billing.creatorLicenses) return;
  let changed = false;

  for (const [creatorId, lic] of Object.entries(billing.creatorLicenses)) {
    if (!lic.autoRenew) continue;
    const expired = !lic.expiry || new Date(lic.expiry) <= new Date();
    if (!expired) continue;

    if (billing.balance < LICENSE_PRICE_USD) {
      lic.active = false;
      changed = true;
      continue;
    }

    billing.balance -= LICENSE_PRICE_USD;
    const expiry = new Date();
    expiry.setDate(expiry.getDate() + 30);
    lic.active = true;
    lic.expiry = expiry.toISOString();
    billing.creatorLicenses[creatorId] = lic;

    billing.transactions.unshift({
      id: Date.now().toString() + creatorId.slice(-4), type: "license",
      amount: -LICENSE_PRICE_USD,
      description: `Renouvellement auto licence 30j — ${lic.creatorName}`,
      createdAt: new Date().toISOString(),
    });
    changed = true;
  }

  if (changed) saveUserBilling(billing);
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
