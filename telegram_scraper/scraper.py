"""
Telegram Member Scraper — Multi-canaux depuis le dashboard
Lit la liste des canaux sur /scraper du dashboard et scrappe tous leurs membres.
Lance : python scraper.py
"""

import asyncio
import csv
import os
import sys
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
    if isinstance(status, UserStatusOnline):    return True   # En ligne maintenant
    if isinstance(status, UserStatusRecently):  return True   # < 1 semaine
    if isinstance(status, UserStatusLastWeek):  return True   # < 7 jours
    if isinstance(status, UserStatusLastMonth): return True   # < 30 jours
    # UserStatusOffline : on vérifie la date de dernière connexion
    if isinstance(status, UserStatusOffline):
        if status.was_online:
            from datetime import timezone
            delta = datetime.now(timezone.utc) - status.was_online
            return delta.days <= 30   # garde si vu il y a ≤ 30 jours
        return False   # date inconnue → exclu
    # UserStatusEmpty ou autre → inconnu → exclu
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


def load_channels_from_dashboard() -> list:
    """
    Charge depuis le dashboard uniquement les canaux marqués 'A scraper'.
    Si aucun n'est marqué, retourne une liste vide et affiche un message.
    """
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/channels", timeout=10)
        if r.status_code == 200:
            all_channels = r.json()
            # Filtre : seulement les canaux marqués "A scraper" via le dashboard
            to_scrape = [c for c in all_channels if c.get("status") == "A scraper"]
            if to_scrape:
                print(f"[OK] {len(to_scrape)} canal(aux) marqué(s) 'A scraper' sur {len(all_channels)} total")
            else:
                print(f"[!] Aucun canal marqué 'A scraper' ({len(all_channels)} canal(aux) enregistré(s))")
                print("    → Va sur le dashboard onglet Scraper et clique '🔍 Scraper' sur les canaux à scrapper.")
            return to_scrape
    except Exception as e:
        print(f"[!] Impossible de charger les canaux : {e}")
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
    """Scrappe les membres d'un canal. Retourne une liste de dicts."""
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
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=members[0].keys())
        writer.writeheader()
        writer.writerows(members)
    print(f"[OK] CSV enregistré : {path}  ({len(members)} membres)")


async def main():
    if not API_ID or not API_HASH or not PHONE:
        print("[X] Configure API_ID, API_HASH et PHONE dans config.py")
        sys.exit(1)

    print("=" * 58)
    print("  Telegram Multi-Scraper — canaux depuis le dashboard")
    print("=" * 58)

    # ── Charge les canaux depuis le dashboard ──────────────
    channels = load_channels_from_dashboard()
    if not channels:
        print("\n[!] Aucun canal à scrapper.")
        print("    → Va sur le dashboard onglet Scraper, clique '🔍 Scraper' sur les canaux voulus, puis relance.")
        sys.exit(0)

    print(f"\n  Canaux à scrapper :")
    for i, c in enumerate(channels, 1):
        print(f"  {i:02d}. {c['url']}  (statut : {c.get('status','?')})")

    print()
    confirm = input("Lancer le scraping ? (oui/non) : ").strip().lower()
    if confirm not in ("oui", "o", "yes", "y"):
        print("Annulé.")
        return

    # ── Connexion Telethon ─────────────────────────────────
    client = TelegramClient("session_scraper", API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"\n[OK] Connecté : {me.first_name} (@{me.username})\n")

    # ── Scraping de chaque canal ───────────────────────────
    all_members = {}   # username → dict (dédoublonnage)
    total_channels = len(channels)

    for idx, channel in enumerate(channels, 1):
        cid    = channel["id"]
        url    = channel["url"]
        target = normalize_target(url)

        print(f"\n{'='*58}")
        print(f"  Canal {idx}/{total_channels} : {url}")
        print(f"{'='*58}")

        # Marque "En cours" sur le dashboard
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

        if idx < total_channels:
            print(f"\n[->] Pause 5s avant le canal suivant...")
            await asyncio.sleep(5)

    # ── Sauvegarde ─────────────────────────────────────────
    final_members = list(all_members.values())
    print(f"\n{'='*58}")
    print(f"  Scraping terminé !")
    print(f"  {len(final_members)} membres uniques avec @username")
    print(f"{'='*58}")

    save_csv(final_members, OUTPUT_CSV)

    print(f"""
  Les membres sont dans : {OUTPUT_CSV}
  Lance maintenant warmup_v2.py (mode Direct DM activé)
  ou dm_sender.py pour envoyer les Mass DMs.
""")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
