"""
Test scraping direct — sans dashboard.
Lance : python test_scrape_direct.py
"""
import asyncio
from scraper import scrape_channel, save_csv
from telethon import TelegramClient
from config import API_ID, API_HASH, PHONE, OUTPUT_CSV

TARGET = "https://t.me/parissportifsfaciles"

async def main():
    client = TelegramClient("session_scraper", API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"\n[OK] Connecté : {me.first_name}\n")

    members = await scrape_channel(client, TARGET)
    print(f"\n>>> RÉSULTAT : {len(members)} membres récupérés")

    if members:
        save_csv(members, OUTPUT_CSV)
        print(f">>> Fichier : {OUTPUT_CSV}")
        # Aperçu des 5 premiers
        print("\n--- Aperçu ---")
        for m in members[:5]:
            print(f"  @{m['username'] or '(sans username)'} | {m['prenom']} | {m['statut']}")

    await client.disconnect()

asyncio.run(main())
