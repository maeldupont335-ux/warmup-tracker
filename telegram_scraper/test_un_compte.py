"""
TEST - Envoie un message a un compte specifique via AdsPower
"""

import asyncio
import random
import requests
from playwright.async_api import async_playwright

ADSPOWER_ID  = "k1csfeja"
ADSPOWER_API = "http://local.adspower.net:50325"
ADSPOWER_KEY = "942d5c4fa00deedac520c3310912ee6100795935b355b33b"

USERNAME = "paulinee2005"
MESSAGE  = "Salut"


def start_browser() -> str:
    r = requests.get(
        f"{ADSPOWER_API}/api/v1/browser/start",
        params={"user_id": ADSPOWER_ID, "api_key": ADSPOWER_KEY},
        headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
        timeout=15,
    )
    data = r.json()
    if data["code"] != 0:
        raise Exception(f"AdsPower erreur: {data['msg']}")
    return data["data"]["ws"]["puppeteer"]


async def main():
    print(f"[->] Connexion AdsPower...")
    cdp_url = start_browser()
    print(f"[OK] Navigateur ouvert")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        page    = context.pages[0] if context.pages else await context.new_page()

        # Navigue vers le chat
        url = f"https://web.telegram.org/k/#@{USERNAME}"
        print(f"[->] Ouverture du chat @{USERNAME}...")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(random.randint(3000, 5000))

        # Clic sur bouton Demarrer si present
        for sel in ["button.btn-primary", ".start-bot-button", "button[class*='start']"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible():
                    print(f"[->] Clic sur bouton demarrer...")
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        # Zone de message
        input_sel = "div.input-message-input[contenteditable='true']"
        try:
            await page.wait_for_selector(input_sel, timeout=8000)
        except Exception:
            print(f"[X] Zone de message introuvable - DMs peut-etre bloques pour @{USERNAME}")
            return

        msg_input = page.locator(input_sel).first
        await msg_input.click()
        await page.wait_for_timeout(random.randint(800, 1500))

        # Frappe lettre par lettre
        print(f"[->] Frappe du message : \"{MESSAGE}\"")
        for lettre in MESSAGE:
            await msg_input.type(lettre, delay=random.randint(60, 180))

        await page.wait_for_timeout(random.randint(1000, 2000))
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)

        print(f"[OK] Message envoye a @{USERNAME} !")

if __name__ == "__main__":
    asyncio.run(main())
