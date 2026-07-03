"""
TEST - Scrape 2 membres au hasard et envoie "Salut" en DM
Simule le comportement humain : ouverture du profil avant envoi
"""

import asyncio
import random
import re
from telethon import TelegramClient
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.messages import GetDialogsRequest, ReadHistoryRequest
from telethon.tl.types import (
    ChannelParticipantsSearch,
    InputPeerEmpty,
)
from telethon.errors import (
    UserPrivacyRestrictedError,
    UserIsBlockedError,
    FloodWaitError,
    PeerFloodError,
    InputUserDeactivatedError,
)

from config import API_ID, API_HASH, PHONE, TARGET


async def simuler_ouverture_profil(client, user):
    """
    Simule le fait de cliquer sur un profil et d'ouvrir la conversation
    exactement comme un humain le ferait via l'app Telegram.
    """
    try:
        # 1. Charge le profil complet (comme quand tu cliques sur quelqu'un)
        await client(GetFullUserRequest(user))
        await asyncio.sleep(random.uniform(1.5, 3.0))

        # 2. Charge les dialogues recents (simule l'ouverture de la messagerie)
        await client(GetDialogsRequest(
            offset_date=None,
            offset_id=0,
            offset_peer=InputPeerEmpty(),
            limit=10,
            hash=0,
        ))
        await asyncio.sleep(random.uniform(2.0, 4.0))

    except Exception:
        pass  # Ces etapes sont optionnelles, on continue meme si elles echouent


async def envoyer_avec_retry(client, user, message, prenom, username):
    envoye = False
    tentatives = 0

    while not envoye and tentatives < 3:
        tentatives += 1
        try:
            # Simule ouverture du profil avant envoi (comme un humain)
            print(f"  [->] Ouverture du profil de {prenom}...")
            await simuler_ouverture_profil(client, user)

            # Simule le temps de frappe
            delai_frappe = random.uniform(3.0, 7.0)
            print(f"  [->] Frappe du message ({delai_frappe:.1f}s)...")
            await asyncio.sleep(delai_frappe)

            # Envoi du message
            await client.send_message(user, message)
            print(f"  [OK] Message envoye a {prenom} ({username}) !")
            envoye = True

        except FloodWaitError as e:
            print(f"  [!] Rate-limit : attente {e.seconds}s puis retry...")
            await asyncio.sleep(e.seconds + 5)

        except UserPrivacyRestrictedError:
            print(f"  [--] {prenom} ({username}) - DMs bloques (confidentialite)")
            envoye = True

        except UserIsBlockedError:
            print(f"  [--] {prenom} ({username}) - t'a bloque")
            envoye = True

        except InputUserDeactivatedError:
            print(f"  [--] {prenom} ({username}) - compte supprime")
            envoye = True

        except PeerFloodError:
            print(f"  [!] PeerFlood detecte - pause 5 minutes...")
            await asyncio.sleep(300)

        except Exception as e:
            err = str(e)
            match = re.search(r'(\d+)\s*seconds?', err, re.IGNORECASE)
            if match or "too many" in err.lower() or "flood" in err.lower():
                wait = int(match.group(1)) if match else 60
                print(f"  [!] Bloque temporairement - attente {wait}s...")
                await asyncio.sleep(wait + 5)
            else:
                print(f"  [X] Erreur : {err}")
                envoye = True

    return envoye


async def main():
    print("=" * 45)
    print("  TEST - 2 membres aleatoires")
    print("=" * 45)

    client = TelegramClient(
        "session_scraper",
        API_ID,
        API_HASH,
        device_model="Samsung Galaxy S23",
        system_version="Android 14",
        app_version="10.3.2",
        lang_code="fr",
        system_lang_code="fr-FR",
    )
    await client.start(phone=PHONE)

    me = await client.get_me()
    print(f"\n[OK] Connecte : {me.first_name} (@{me.username})")

    # Recupere les membres
    print(f"\n[->] Chargement des membres de {TARGET}...")
    entity = await client.get_entity(TARGET)

    result = await client(GetParticipantsRequest(
        channel=entity,
        filter=ChannelParticipantsSearch(""),
        offset=0,
        limit=200,
        hash=0,
    ))

    membres = [u for u in result.users if not u.bot and not u.is_self]

    if len(membres) < 2:
        print("[X] Pas assez de membres trouves.")
        return

    choisis = random.sample(membres, 2)
    print(f"\n[->] 2 membres selectionnes au hasard :\n")
    for i, user in enumerate(choisis, 1):
        prenom   = user.first_name or "?"
        username = f"@{user.username}" if user.username else f"id:{user.id}"
        print(f"  {i}. {prenom} ({username})")

    print()
    confirm = input("Envoyer 'Salut' a ces 2 personnes ? (oui/non) : ").strip().lower()
    if confirm not in ("oui", "o", "yes", "y"):
        print("Annule.")
        await client.disconnect()
        return

    print()
    for i, user in enumerate(choisis, 1):
        prenom   = user.first_name or "toi"
        username = f"@{user.username}" if user.username else str(user.id)
        print(f"\n--- Membre {i}/2 : {prenom} ---")

        await envoyer_avec_retry(client, user, "Salut", prenom, username)

        if i < len(choisis):
            pause = random.uniform(20, 40)
            print(f"\n  [->] Pause {pause:.0f}s avant le prochain...")
            await asyncio.sleep(pause)

    print("\n[OK] Test termine !")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
