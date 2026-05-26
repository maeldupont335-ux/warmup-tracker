"""
Telegram Member Scraper — Mode daemon (auto)
Tourne en arrière-plan et scrape automatiquement dès qu'un canal
est marqué "A scraper" via le bouton du dashboard.

Lance une seule fois : python scraper.py
"""

import asyncio
import csv
import os
import sys
import time
from datetime import datetime

import requests
from telethon import TelegramClient
from telethon.errors import (
    ChatAdminRequiredError,
    FloodWaitError,
    PeerFloodError,
)
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import (
    ChannelParticipantsSearch,
    UserStatusEmpty,
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

from config import API_ID, API_HASH, PHONE, OUTPUT_CSV, DELAY

# ── Dashboard ──────────────────────────────────────────────
DASHBOARD_URL   = "https://warmup-tracker.onrender.com"
DASHBOARD_TOKEN = "Compte.1"
POLL_INTERVAL   = 30   # secondes entre deux vérifications
# ───────────────────────────────────────────────────────────


def format_status(status) -> str:
    if isinstance(status, UserStatusOnline):     return "En ligne"
    if isinstance(status, UserStatusRecently):   return "Recemment"
    if isinstance(status, UserStatusLastWeek):   return "La semaine derniere"
    if isinstance(status, UserStatusLastMonth):  return "Le mois dernier"
    if isinstance(status, UserStatusOffline):
        return status.was_online.strftime("%Y-%m-%d %H:%M") if status.was_online else "Hors ligne"
    return "Inconnu"


def is_active_recently(status) -> bool:
    """
    Retourne True uniquement si le membre est actif récemment :
      ✓ En ligne maintenant
      ✓ Vu récemment (< 1 semaine)
      ✓ Vu cette semaine
      ✓ Vu ce mois-ci (< 30 jours)
      ✗ Hors ligne depuis plus de 30 jours → exclu
      ✗ Inconnu / vide → exclu
    """
    if isinstance(status, UserStatusOnline):    return True
    if isinstance(status, UserStatusRecently):  return True
    if isinstance(status, UserStatusLastWeek):  return True
    if isinstance(status, UserStatusLastMonth): return True
    if isinstance(status, UserStatusOffline):
        if status.was_online:
            from datetime import timezone
            delta = datetime.now(timezone.utc) - status.was_online
            return delta.days <= 30
        return False
    return False


def parse_user(user) -> dict:
    return {
        "id":        str(user.id),
        "username":  user.username or "",
        "prenom":    user.first_name or "",
        "nom":       user.last_name or "",
        "telephone": user.phone or "",
        "bot":       "Oui" if user.bot else "Non",
        "verifie":   "Oui" if user.verified else "Non",
        "statut":    format_status(user.status),
        "scrape_le": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def load_pending_channels() -> list:
    """Charge uniquement les canaux marqués 'A scraper' depuis le dashboard."""
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/channels", timeout=10)
        if r.status_code == 200:
            all_ch = r.json()
            pending = [c for c in all_ch if c.get("status") == "A scraper"]
            return pending
    except Exception as e:
        print(f"[!] Erreur dashboard : {e}")
    return []


def update_channel_status(channel_id: int, status: str, members_count: int = 0):
    """Met à jour le statut d'un canal sur le dashboard."""
    try:
        requests.post(
            f"{DASHBOARD_URL}/api/channel/update",
            json={
                "token":          DASHBOARD_TOKEN,
                "channel_id":     channel_id,
                "status":         status,
                "members_count":  members_count,
            },
            timeout=10,
        )
    except Exception:
        pass


def normalize_target(url: str) -> str:
    """Convertit une URL t.me ou @username en cible Telethon."""
    url = url.strip()
    if "t.me/" in url:
        slug = url.split("t.me/")[-1].rstrip("/").split("/")[0]
        return f"@{slug}"
    if url.startswith("@"):
        return url
    return f"@{url}"


async def scrape_channel(client: TelegramClient, target: str) -> list:
    """Scrappe les membres actifs (≤30j) d'un canal. Retourne une liste de dicts."""
    print(f"\n  [->] Résolution : {target}")
    try:
        entity = await client.get_entity(target)
    except Exception as e:
        print(f"  [X] Canal introuvable ({target}) : {e}")
        return []

    title = getattr(entity, "title", target)
    print(f"  [OK] Connecté à : {title}")

    members = []
    offset  = 0
    limit   = 200
    total   = None

    while True:
        try:
            result = await client(GetParticipantsRequest(
                channel=entity,
                filter=ChannelParticipantsSearch(""),
                offset=offset,
                limit=limit,
                hash=0,
            ))
        except ChatAdminRequiredError:
            print(f"  [X] Accès refusé — tu dois être admin de ce canal.")
            break
        except FloodWaitError as e:
            print(f"  [!] Rate-limit — attente {e.seconds}s...")
            await asyncio.sleep(e.seconds)
            continue
        except PeerFloodError:
            print(f"  [X] Trop de requêtes. Réessaie dans quelques heures.")
            break
        except Exception as e:
            print(f"  [X] Erreur : {e}")
            break

        if not result.users:
            break

        if total is None:
            total = result.count
            print(f"  [i] {total} membres au total dans ce canal")

        for user in result.users:
            if not user.is_self and user.username:
                if is_active_recently(user.status):
                    members.append(parse_user(user))

        offset += len(result.users)
        pct = (offset / total * 100) if total else 0
        print(f"  [{offset}/{total}] {pct:.0f}% — {len(members)} actifs récents gardés", end="\r")

        if offset >= total or len(result.users) < limit:
            break

        await asyncio.sleep(DELAY)

    print(f"\n  [OK] {len(members)} membres actifs récents (≤30j) avec @username — depuis {title}")
    return members


def save_csv(members: list, path: str) -> None:
    if not members:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Ajoute au fichier existant (sans dupliquer les headers)
    file_exists = os.path.isfile(path)
    with open(path, "a" if file_exists else "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=members[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(members)
    print(f"[OK] CSV mis à jour : {path}  ({len(members)} membres ajoutés)")


async def run_scraping_session(client: TelegramClient, channels: list):
    """Scrappe tous les canaux de la liste et sauvegarde le CSV."""
    all_members = {}   # username → dict (dédoublonnage)
    total = len(channels)

    for idx, channel in enumerate(channels, 1):
        cid    = channel["id"]
        url    = channel["url"]
        target = normalize_target(url)

        print(f"\n{'='*58}")
        print(f"  Canal {idx}/{total} : {url}")
        print(f"{'='*58}")

        update_channel_status(cid, "En cours")

        members = await scrape_channel(client, target)

        if members:
            update_channel_status(cid, "Scrappe", len(members))
            for m in members:
                uname = (m["username"] or "").lower()
                if uname and uname not in all_members:
                    all_members[uname] = m
        else:
            update_channel_status(cid, "Erreur", 0)

        if idx < total:
            print(f"\n[->] Pause 5s avant le canal suivant...")
            await asyncio.sleep(5)

    final_members = list(all_members.values())
    print(f"\n{'='*58}")
    print(f"  Scraping terminé ! {len(final_members)} membres uniques")
    print(f"{'='*58}")

    if final_members:
        save_csv(final_members, OUTPUT_CSV)
        print(f"  Fichier : {OUTPUT_CSV}")


async def main():
    if not API_ID or not API_HASH or not PHONE:
        print("[X] Configure API_ID, API_HASH et PHONE dans config.py")
        sys.exit(1)

    print("=" * 58)
    print("  Telegram Scraper — Mode Daemon (auto)")
    print(f"  Vérification toutes les {POLL_INTERVAL}s")
    print("=" * 58)

    # ── Connexion Telethon (une seule fois au démarrage) ───
    client = TelegramClient("session_scraper", API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"\n[OK] Connecté : {me.first_name} (@{me.username})")
    print(f"[OK] En attente de canaux à scrapper sur le dashboard...\n")
    print("     → Va sur le dashboard, clique '🔍 Scraper' sur les canaux voulus")
    print("     → Ce script les détectera automatiquement et lancera le scraping")
    print("     → Ctrl+C pour arrêter\n")

    # ── Boucle daemon ──────────────────────────────────────
    try:
        while True:
            pending = load_pending_channels()

            if pending:
                print(f"\n[🔍] {len(pending)} canal(aux) détecté(s) — démarrage du scraping...")
                await run_scraping_session(client, pending)
                print(f"\n[OK] Session terminée. Reprise surveillance dans {POLL_INTERVAL}s...\n")
            else:
                # Affiche un point toutes les 30s pour montrer que ça tourne
                print(f"  [·] {datetime.now().strftime('%H:%M:%S')} — En attente de canaux à scrapper...", end="\r")

            await asyncio.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n[OK] Scraper arrêté.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
