"""
create_invite_links.py
Crée 7 liens d'invitation (avec approbation requise) sur le canal de tracking,
nommés MESSAGE 1 à MESSAGE 7, et les enregistre dans le dashboard.

Lance UNE SEULE FOIS :
  python create_invite_links.py
"""

import asyncio
import json
import os
import requests
from telethon import TelegramClient
from telethon.errors import UserAlreadyParticipantError
from telethon.tl.functions.messages import (
    ImportChatInviteRequest,
    ExportChatInviteRequest,
    GetExportedChatInvitesRequest,
)
from telethon.tl.types import InputUserSelf

from config import API_ID, API_HASH, PHONE, TRACKING_CHANNEL

DASHBOARD_URL   = "https://warmup-tracker.onrender.com"
DASHBOARD_TOKEN = "Compte.1"
NB_LINKS        = 7
OUTPUT_JSON     = os.path.join(os.path.dirname(__file__), "output", "invite_links.json")


def get_invite_hash(url: str) -> str:
    return url.split("t.me/+")[-1].rstrip("/")


async def main():
    print("=" * 58)
    print("  Création des liens d'invitation — Mass DM Tracking")
    print("=" * 58)

    client = TelegramClient("session_scraper", API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"\n[OK] Connecté : {me.first_name}")

    # ── Trouver le canal de tracking ──────────────────────────
    entity = None
    if "t.me/+" in TRACKING_CHANNEL:
        invite_hash = get_invite_hash(TRACKING_CHANNEL)
        try:
            result = await client(ImportChatInviteRequest(invite_hash))
            entity = result.chats[0]
            print(f"[OK] Rejoint : {entity.title}")
        except UserAlreadyParticipantError:
            async for dialog in client.iter_dialogs(limit=300):
                if dialog.is_channel and not getattr(dialog.entity, "username", None):
                    entity = dialog.entity
                    print(f"[OK] Canal trouvé : {entity.title}")
                    break
    else:
        entity = await client.get_entity(TRACKING_CHANNEL)
        print(f"[OK] Canal : {entity.title}")

    if entity is None:
        print("[X] Canal introuvable — vérifie TRACKING_CHANNEL dans config.py")
        return

    # ── Vérifier les liens existants ──────────────────────────
    print(f"\n[->] Vérification des liens existants...")
    existing_titles = {}
    try:
        existing = await client(GetExportedChatInvitesRequest(
            peer=entity,
            admin_id=InputUserSelf(),
            revoked=False,
            limit=50,
        ))
        for inv in existing.invites:
            title = getattr(inv, "title", "") or ""
            if title:
                existing_titles[title] = inv.link
                print(f"  [i] Existant : {title} → {inv.link}")
    except Exception as e:
        print(f"  [i] Impossible de lire les liens existants : {e}")

    # ── Créer les liens manquants ─────────────────────────────
    print(f"\n[->] Création des {NB_LINKS} liens d'invitation...")
    created_links = {}

    for i in range(1, NB_LINKS + 1):
        title = f"MESSAGE {i}"

        if title in existing_titles:
            print(f"  [i] {title} — déjà existant → {existing_titles[title]}")
            created_links[title] = existing_titles[title]
            continue

        try:
            inv = await client(ExportChatInviteRequest(
                peer=entity,
                title=title,
                request_needed=True,   # Approbation requise avant accès
            ))
            created_links[title] = inv.link
            print(f"  [OK] {title} créé → {inv.link}")
            await asyncio.sleep(1)   # anti-flood
        except Exception as e:
            print(f"  [X] {title} erreur : {e}")

    # ── Sauvegarder localement ────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(created_links, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] Liens sauvegardés → {OUTPUT_JSON}")

    # ── Envoyer au dashboard ──────────────────────────────────
    try:
        r = requests.post(f"{DASHBOARD_URL}/api/massdm/invite-links/set", json={
            "token": DASHBOARD_TOKEN,
            "links": created_links,
        }, timeout=10)
        if r.ok and r.json().get("ok"):
            print(f"[OK] Dashboard mis à jour avec les {len(created_links)} liens")
        else:
            print(f"[i] Dashboard : {r.text[:100]}")
    except Exception as e:
        print(f"[i] Dashboard non joignable : {e} — liens disponibles dans {OUTPUT_JSON}")

    # ── Afficher le résumé ────────────────────────────────────
    print(f"\n{'='*58}")
    print(f"  RÉSUMÉ — {len(created_links)} liens créés")
    print(f"{'='*58}")
    for title, link in created_links.items():
        print(f"  {title:<12} → {link}")
    print(f"\n  ✅ Colle ces liens dans tes templates Mass DM !")
    print(f"     Template 1 → lien MESSAGE 1, Template 2 → lien MESSAGE 2, etc.")
    print(f"{'='*58}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
