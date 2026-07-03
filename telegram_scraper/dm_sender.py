"""
Telegram DM Sender
Envoie un message personnalise aux membres de ton canal @sfs_france.
Anti-ban : delai aleatoire, pause toutes les N requetes, gestion des erreurs.
"""

import asyncio
import csv
import os
import random
import sys
from datetime import datetime

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    InputUserDeactivatedError,
    PeerFloodError,
    UserIsBlockedError,
    UserPrivacyRestrictedError,
)

from config import API_ID, API_HASH, PHONE

# ============================================================
#  PARAMETRES D'ENVOI
# ============================================================

CSV_INPUT = "output/membres.csv"

MESSAGE = """Salut {prenom} !

Je suis l'admin de @sfs_france

On fait des SFS (shoutout for shoutout) pour grandir ensemble sur Telegram !

Si ca t'interesse reponds-moi
"""

DELAY_MIN     = 10      # secondes min entre chaque DM
DELAY_MAX     = 20      # secondes max entre chaque DM
PAUSE_EVERY   = 20      # pause longue toutes les N DMs
PAUSE_SECONDS = 300     # duree de la pause longue (5 min)
LOG_FILE      = "output/dm_log.csv"
RESUME        = True    # True = skip les deja envoyes

# ============================================================


def load_already_sent() -> set:
    sent = set()
    if RESUME and os.path.exists(LOG_FILE):
        with open(LOG_FILE, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("statut") == "envoye":
                    sent.add(row["id"])
    return sent


def log_result(user_id: str, username: str, prenom: str, statut: str, note: str = "") -> None:
    file_exists = os.path.exists(LOG_FILE)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "username", "prenom", "statut", "note", "heure"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "id":       user_id,
            "username": username,
            "prenom":   prenom,
            "statut":   statut,
            "note":     note,
            "heure":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })


async def send_dms(client: TelegramClient) -> None:
    if not os.path.exists(CSV_INPUT):
        print(f"[X] Fichier CSV introuvable : {CSV_INPUT}")
        print("    Lance d'abord scraper.py pour generer la liste.")
        return

    already_sent = load_already_sent()

    with open(CSV_INPUT, newline="", encoding="utf-8-sig") as f:
        members = list(csv.DictReader(f))

    to_send = [
        m for m in members
        if m.get("bot") != "Oui" and m["id"] not in already_sent
    ]

    total   = len(to_send)
    sent    = 0
    skipped = 0
    failed  = 0

    print(f"\n[->] {len(already_sent)} deja envoyes (reprise active)")
    print(f"[->] {total} membres restants a contacter\n")

    if total == 0:
        print("[OK] Tout le monde a deja ete contacte.")
        return

    for i, member in enumerate(to_send, 1):
        user_id  = member["id"]
        username = member.get("username", "")
        prenom   = member.get("prenom") or "toi"
        target   = username if username else int(user_id)
        texte    = MESSAGE.replace("{prenom}", prenom)

        try:
            await client.send_message(target, texte)
            statut = "envoye"
            sent  += 1
            print(f"  [{i}/{total}] OK @{username or user_id} - {prenom}")

        except UserPrivacyRestrictedError:
            statut   = "bloque_privacy"
            skipped += 1
            print(f"  [{i}/{total}] -- @{username or user_id} - DMs bloques (confidentialite)")

        except UserIsBlockedError:
            statut   = "bloque"
            skipped += 1
            print(f"  [{i}/{total}] -- @{username or user_id} - t'a bloque")

        except InputUserDeactivatedError:
            statut   = "compte_supprime"
            skipped += 1
            print(f"  [{i}/{total}] -- @{username or user_id} - compte desactive")

        except FloodWaitError as e:
            print(f"\n[!] FLOOD WAIT - Telegram demande {e.seconds}s d'attente...")
            await asyncio.sleep(e.seconds + 10)
            statut = "flood_retry"
            failed += 1

        except PeerFloodError:
            print("\n[X] PEER FLOOD - Arret pour proteger ton compte !")
            log_result(user_id, username, prenom, "peer_flood")
            break

        except Exception as e:
            statut = "erreur"
            failed += 1
            print(f"  [{i}/{total}] X @{username or user_id} - {type(e).__name__}: {e}")

        log_result(user_id, username, prenom, statut)

        if sent > 0 and sent % PAUSE_EVERY == 0:
            print(f"\n[PAUSE] Anti-flood {PAUSE_SECONDS}s ({sent} envoyes)...\n")
            await asyncio.sleep(PAUSE_SECONDS)
            continue

        await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"""
{'='*50}
  RESUME FINAL
{'='*50}
  OK  Envoyes  : {sent}
  --  Ignores  : {skipped}  (privacy / bloque / compte mort)
  X   Erreurs  : {failed}
  Log complet  : {LOG_FILE}
{'='*50}
""")


async def main():
    if not API_ID or not API_HASH or not PHONE or PHONE == "+33":
        print("[X] Remplis ton numero de telephone dans config.py")
        sys.exit(1)

    print("=" * 50)
    print("  Telegram DM Sender - @sfs_france")
    print("=" * 50)
    print(f"\n  Message qui sera envoye :\n")
    print("  " + MESSAGE.replace("\n", "\n  "))
    print()

    confirm = input("Confirmes-tu l'envoi ? (oui/non) : ").strip().lower()
    if confirm not in ("oui", "o", "yes", "y"):
        print("Annule.")
        return

    client = TelegramClient("session_scraper", API_ID, API_HASH)
    await client.start(phone=PHONE)

    me = await client.get_me()
    print(f"\n[OK] Connecte : {me.first_name} (@{me.username})\n")

    await send_dms(client)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
