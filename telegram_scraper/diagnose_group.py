"""
Diagnostic rapide d'un groupe Telegram.
Indique : canal ou groupe, broadcast ou supergroup, groupe lié, nb messages récents.
Usage : python diagnose_group.py
"""
import asyncio
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel, User
from config import API_ID, API_HASH, PHONE

TARGET = "https://t.me/parissportifsfaciles"   # ← change ici si besoin


async def diagnose(target: str):
    client = TelegramClient("session_scraper", API_ID, API_HASH)
    await client.start(phone=PHONE)

    # Normaliser l'URL
    if "t.me/" in target:
        slug = target.split("t.me/")[-1].rstrip("/").split("/")[0]
        target = f"@{slug}"

    print(f"\n=== DIAGNOSTIC : {target} ===\n")

    entity = await client.get_entity(target)
    print(f"Type         : {type(entity).__name__}")
    print(f"Titre        : {getattr(entity, 'title', '?')}")
    print(f"ID           : {entity.id}")
    print(f"broadcast    : {getattr(entity, 'broadcast', False)}")
    print(f"megagroup    : {getattr(entity, 'megagroup', False)}")
    print(f"username     : {getattr(entity, 'username', None)}")

    # Chercher groupe lié
    try:
        full = await client(GetFullChannelRequest(entity))
        linked_id = getattr(full.full_chat, "linked_chat_id", None)
        participants_count = getattr(full.full_chat, "participants_count", "?")
        print(f"Abonnés total: {participants_count}")
        if linked_id:
            linked = await client.get_entity(linked_id)
            print(f"Groupe lié   : {getattr(linked, 'title', linked_id)} (id={linked_id})")
        else:
            print(f"Groupe lié   : Aucun")
    except Exception as e:
        print(f"Full info    : erreur — {e}")

    # Compter les messages et types d'expéditeurs
    print(f"\n--- Analyse des 200 derniers messages ---")
    user_senders = 0
    channel_senders = 0
    none_senders = 0
    total = 0
    async for msg in client.iter_messages(entity, limit=200):
        total += 1
        sender = getattr(msg, "sender", None)
        if sender is None:
            try:
                sender = await msg.get_sender()
            except Exception:
                pass
        if sender is None:
            none_senders += 1
        elif isinstance(sender, User):
            user_senders += 1
        else:
            channel_senders += 1

    print(f"Total msgs   : {total}")
    print(f"→ Expéditeurs User    : {user_senders}  ← scrapables")
    print(f"→ Expéditeurs Channel : {channel_senders}  ← non scrapables (broadcast)")
    print(f"→ Expéditeurs None    : {none_senders}")
    print()

    if user_senders == 0:
        print("⚠  CANAL BROADCAST pur — les membres ne sont pas récupérables via messages.")
        print("   Solution : chercher un groupe où les membres peuvent écrire.")
    elif user_senders > 10:
        print(f"✓  {user_senders} expéditeurs utilisateurs détectés — scraping messages possible !")

    await client.disconnect()


asyncio.run(diagnose(TARGET))
