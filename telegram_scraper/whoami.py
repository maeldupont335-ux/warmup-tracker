from telethon.sync import TelegramClient
from config import API_ID, API_HASH

with TelegramClient("session_scraper", API_ID, API_HASH) as c:
    me = c.get_me()
    print(f"Nom      : {me.first_name} {me.last_name or ''}")
    print(f"Username : @{me.username}")
    print(f"Tel      : +{me.phone}")
