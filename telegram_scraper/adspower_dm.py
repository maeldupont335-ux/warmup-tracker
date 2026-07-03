"""
AdsPower + Telegram Web DM Sender
Envoie des DMs via le vrai navigateur (web.telegram.org) = 0% detectable
"""

import asyncio
import csv
import os
import random
import sys
import requests
from playwright.async_api import async_playwright

# ============================================================
ADSPOWER_ID  = "k1c91p6c"
ADSPOWER_API = "http://local.adspower.net:50325"
ADSPOWER_KEY = "942d5c4fa00deedac520c3310912ee6100795935b355b33b"
CSV_INPUT    = "output/membres.csv"
MESSAGE      = "Salut"
DELAY_MIN    = 45
DELAY_MAX    = 90
LOG_FILE     = "output/dm_web_log.csv"
RESUME       = True
# ============================================================


def start_browser() -> str:
    print(f"[->] Demarrage AdsPower : {ADSPOWER_ID}...")
    try:
        r = requests.get(
            f"{ADSPOWER_API}/api/v1/browser/start",
            params={"user_id": ADSPOWER_ID, "api_key": ADSPOWER_KEY},
            headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
            timeout=15,
        )
        data = r.json()
    except Exception as e:
        print(f"[X] AdsPower inaccessible : {e}")
        sys.exit(1)
    if data.get("code") != 0:
        print(f"[X] Erreur AdsPower : {data.get('msg')}")
        sys.exit(1)
    cdp_url = data["data"]["ws"]["puppeteer"]
    print(f"[OK] Navigateur demarre")
    return cdp_url


def stop_browser():
    requests.get(
        f"{ADSPOWER_API}/api/v1/browser/stop",
        params={"user_id": ADSPOWER_ID, "api_key": ADSPOWER_KEY},
        headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
        timeout=10,
    )


def load_already_sent() -> set:
    sent = set()
    if RESUME and os.path.exists(LOG_FILE):
        with open(LOG_FILE, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("statut") == "envoye":
                    sent.add(row.get("username", ""))
    return sent


def log_result(username: str, prenom: str, statut: str) -> None:
    from datetime import datetime
    file_exists = os.path.exists(LOG_FILE)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["username", "prenom", "statut", "heure"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "username": username,
            "prenom":   prenom,
            "statut":   statut,
            "heure":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })


async def envoyer_dm(page, username: str, prenom: str, message: str) -> str:
    """
    Navigation via Ctrl+K (recherche native Telegram).
    Plus fiable que page.goto() qui ne declenche pas le routeur SPA apres le 1er chargement.
    """
    try:
        print(f"  [->] Navigation vers @{username}...", flush=True)

        # 1. Ferme tout ce qui est ouvert (dialog, recherche, etc.)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        # 2. Ouvre la recherche globale Telegram (Ctrl+K)
        await page.keyboard.press("Control+k")
        await page.wait_for_timeout(1500)

        # 3. Cherche le champ de recherche et vide-le
        search_ok = False
        for sel in ["input.search-field-input", ".input-search input", ".search-field input"]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.triple_click()
                    await page.wait_for_timeout(200)
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Delete")
                    search_ok = True
                    break
            except Exception:
                pass

        if not search_ok:
            # Tape directement dans ce qui est focus (Ctrl+K met le focus sur la search)
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")

        # 4. Tape le username lettre par lettre
        await page.keyboard.type(username, delay=random.randint(80, 130))
        await page.wait_for_timeout(random.randint(3500, 5000))

        # Screenshot debug
        os.makedirs("output/debug", exist_ok=True)
        await page.screenshot(path=f"output/debug/{username}.png")

        # 5. Cherche le bon resultat dans la liste et clique dessus
        clique = False
        for sel in [".search-result", ".chatlist-chat", ".list-item-inner", ".search-group__item"]:
            items = page.locator(sel)
            count = await items.count()
            for i in range(min(count, 10)):
                try:
                    item = items.nth(i)
                    texte = (await item.inner_text()).lower()
                    if username.lower() in texte:
                        await item.click()
                        await page.wait_for_timeout(random.randint(2500, 3500))
                        clique = True
                        break
                except Exception:
                    pass
            if clique:
                break

        if not clique:
            # Fallback : Entree sur le 1er resultat
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(random.randint(2500, 3500))

        # Screenshot du chat ouvert
        await page.screenshot(path=f"output/debug/{username}_chat.png")

        # 2b. Clique bouton "Envoyer un message" si present (premier contact)
        for sel in ["button.btn-primary", ".start-bot-button", "button[class*='send']"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1500):
                    print(f"  [->] Clic bouton Message...")
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        # 3. Verifie si le vrai champ message existe (pas le fake)
        #    Telegram Web K a 2 divs input-message-input :
        #    - input-field-input-fake  : placeholder visuel (contenteditable=true mais inutile)
        #    - le vrai                 : contenteditable=true (DMs OK) ou false (DMs bloques)
        #    Si data-peer-id est negatif = groupe/canal = pas un DM
        real_input = None
        try:
            all_inputs = page.locator("div.input-message-input")
            count = await all_inputs.count()
            for i in range(count):
                el = all_inputs.nth(i)
                cls       = await el.get_attribute("class") or ""
                ce        = await el.get_attribute("contenteditable") or ""
                peer_id   = await el.get_attribute("data-peer-id") or ""

                if "fake" in cls:
                    continue  # Ignore le fake

                if ce == "false":
                    # Vrai champ desactive = DMs bloques ou groupe/canal
                    if peer_id.startswith("-"):
                        print(f"  [--] @{username} - Canal/groupe (pas un DM)")
                    else:
                        print(f"  [--] @{username} - DMs bloques")
                    return "bloque"

                if ce == "true":
                    real_input = el
                    break

        except Exception:
            pass

        # 4. Fallback si on n'a pas trouve le vrai champ
        if not real_input:
            # Tente quand meme avec le premier contenteditable visible
            for sel in [
                "div.input-message-input[contenteditable='true']:not(.input-field-input-fake)",
                "div.input-message-input[contenteditable='true']",
            ]:
                try:
                    el = page.locator(sel).first
                    await el.wait_for(state="visible", timeout=6000)
                    real_input = el
                    break
                except Exception:
                    pass

        if not real_input:
            print(f"  [--] @{username} - Champ message introuvable")
            return "bloque"

        # 5. Focus via JavaScript (contourne les intercepts pointer-events)
        try:
            await page.evaluate("""
                const inputs = document.querySelectorAll('div.input-message-input[contenteditable="true"]');
                for (const inp of inputs) {
                    if (!inp.classList.contains('input-field-input-fake')) {
                        inp.focus();
                        break;
                    }
                }
            """)
            await page.wait_for_timeout(400)
        except Exception:
            pass

        # Clic force si necessaire
        try:
            await real_input.click(force=True, timeout=5000)
        except Exception:
            pass

        await page.wait_for_timeout(400)

        # Nettoyage du champ
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        await page.wait_for_timeout(200)
        contenu = await real_input.inner_text()
        if contenu.strip():
            await real_input.fill("")
            await page.wait_for_timeout(150)

        # 6. Frappe lettre par lettre (simulation humaine)
        print(f"  [->] Frappe du message...")
        for lettre in message:
            await real_input.type(lettre, delay=random.randint(60, 190))

        await page.wait_for_timeout(random.randint(800, 1500))

        # 7. Envoi
        await page.keyboard.press("Enter")

        # Attend plus longtemps : le point rouge peut mettre 5-6s a apparaitre
        await page.wait_for_timeout(6000)

        # Screenshot apres envoi
        await page.screenshot(path=f"output/debug/{username}_sent.png")

        # 8. Detecte echec — selecteurs etendus + timeout plus long
        erreur_detectee = False
        for sel in [
            ".message.is-error",
            ".tgico-msg-failed",
            ".message-error",
            ".icon-msg-failed",
            "[class*='msg-failed']",
            "[class*='is-error']",
        ]:
            try:
                el = page.locator(sel).last
                if await el.is_visible(timeout=3000):
                    erreur_detectee = True
                    break
            except Exception:
                pass

        if erreur_detectee:
            print(f"  [--] @{username} - Rejete (DMs bloques cote serveur)")
            return "bloque"

        # 9. Verifie que le message a bien un statut d'envoi (coche simple ou double)
        # Si le dernier message own est encore en "pending" apres 6s = probleme silencieux
        try:
            last_own = page.locator(".message.own").last
            if await last_own.is_visible(timeout=2000):
                # Cherche icone d'erreur dans ce message
                err_in_msg = last_own.locator("[class*='failed'], [class*='error']")
                if await err_in_msg.count() > 0:
                    print(f"  [--] @{username} - Erreur silencieuse detectee")
                    return "bloque"
        except Exception:
            pass

        print(f"  [OK] Message envoye a {prenom} (@{username}) !")
        return "envoye"

    except Exception as e:
        print(f"  [X] Erreur @{username} : {e}")
        return "erreur"


async def main():
    print("=" * 50)
    print("  AdsPower DM Sender - Telegram Web")
    print("=" * 50)

    if not os.path.exists(CSV_INPUT):
        print(f"[X] CSV introuvable : {CSV_INPUT}")
        sys.exit(1)

    with open(CSV_INPUT, newline="", encoding="utf-8-sig") as f:
        membres = list(csv.DictReader(f))

    already_sent = load_already_sent()
    to_send = [
        m for m in membres
        if m.get("username") and m.get("bot") != "Oui"
        and m["username"] not in already_sent
    ]

    print(f"\n[->] Total membres       : {len(membres)}")
    print(f"[->] Deja envoyes (skip) : {len(already_sent)}")
    print(f"[->] A envoyer           : {len(to_send)}")
    print(f"[->] Message             : \"{MESSAGE}\"\n")

    if not to_send:
        print("[OK] Tout le monde contacte.")
        return

    confirm = input("Confirmes-tu l'envoi ? (oui/non) : ").strip().lower()
    if confirm not in ("oui", "o", "yes", "y"):
        print("Annule.")
        return

    cdp_url = start_browser()
    sent = skipped = failed = 0

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        # S'assure d'etre sur Telegram avant de commencer
        if "web.telegram.org" not in page.url:
            print(f"[->] Chargement de Telegram Web...")
            await page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

        for i, membre in enumerate(to_send, 1):
            username = membre["username"]
            prenom   = membre.get("prenom") or "toi"

            print(f"\n--- [{i}/{len(to_send)}] {prenom} (@{username}) ---", flush=True)

            statut = await envoyer_dm(page, username, prenom, MESSAGE)
            log_result(username, prenom, statut)

            if statut == "envoye":
                sent += 1
            elif statut in ("bloque", "introuvable"):
                skipped += 1
            else:
                failed += 1

            if i < len(to_send):
                pause = random.uniform(DELAY_MIN, DELAY_MAX)
                print(f"  [->] Pause {pause:.0f}s...", flush=True)
                await asyncio.sleep(pause)

    stop_browser()
    print(f"""
{'='*50}
  RESUME
  OK  Envoyes  : {sent}
  --  Ignores  : {skipped}
  X   Erreurs  : {failed}
  Log : {LOG_FILE}
{'='*50}
""")


if __name__ == "__main__":
    asyncio.run(main())
