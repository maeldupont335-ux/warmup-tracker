"""
profile_changer.py — Applique photo, @username et bio sur Telegram Web K
Usage : python profile_changer.py <profile_id>
"""

import asyncio
import base64
import os
import sys
import json
import tempfile
import requests
from playwright.async_api import async_playwright

# ── Config ──────────────────────────────────────────────────
SUPABASE_URL  = "https://pirlgavzihmnwmqlyeir.supabase.co"
SUPABASE_KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBpcmxnYXZ6aWhtbndtcWx5ZWlyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3MzQxMTAsImV4cCI6MjA5NTMxMDExMH0.0QdskD9IBsx1rUZ_7Sljb8DshovkQMJIhmnAM-Zc6Ps"
SUPABASE_HDRS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
}

ADSPOWER_API = "http://local.adspower.net:50325"
ADSPOWER_KEY = "942d5c4fa00deedac520c3310912ee6100795935b355b33b"


# ── AdsPower helpers ─────────────────────────────────────────

def start_browser(profile_id: str) -> str:
    launch_args = json.dumps([
        "--window-size=1000,700",
        "--window-position=40,40",
    ])
    r = requests.get(
        f"{ADSPOWER_API}/api/v1/browser/start",
        params={"user_id": profile_id, "api_key": ADSPOWER_KEY,
                "launch_args": launch_args},
        headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
        timeout=15,
    )
    data = r.json()
    if data.get("code") != 0:
        raise Exception(f"AdsPower erreur : {data.get('msg')}")
    return data["data"]["ws"]["puppeteer"]


def stop_browser(profile_id: str):
    try:
        requests.get(
            f"{ADSPOWER_API}/api/v1/browser/stop",
            params={"user_id": profile_id, "api_key": ADSPOWER_KEY},
            headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
            timeout=10,
        )
    except Exception:
        pass


# ── Supabase helpers ─────────────────────────────────────────

def load_config(profile_id: str) -> dict | None:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/profile_setup",
        headers=SUPABASE_HDRS,
        params={"profile_id": f"eq.{profile_id}", "select": "*"},
        timeout=10,
    )
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return None


# ── Telegram Web K navigation ────────────────────────────────

async def wait_telegram(page):
    """Attend que la chatlist Telegram soit prête."""
    for _ in range(20):
        try:
            ok = await page.locator(".chatlist-chat, .chat-list, li.chatlist-chat").first.is_visible(timeout=1500)
            if ok:
                return True
        except Exception:
            pass
        await page.wait_for_timeout(1000)
    return False


async def open_settings(page) -> bool:
    """Ouvre les paramètres Telegram Web K par toutes les méthodes connues."""

    # ── Méthode 1 : URL hash direct ───────────────────────────
    try:
        await page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1500)
        await page.evaluate("() => { window.location.hash = '#?settings=1'; }")
        await page.wait_for_timeout(2500)
        # Vérifier si la vue Settings est ouverte
        for sel in [".settings-container", ".settings-main", "[class*='settings']"]:
            try:
                if await page.locator(sel).first.is_visible(timeout=2000):
                    print("  [OK] Settings ouverts via URL hash")
                    return True
            except Exception:
                pass
    except Exception:
        pass

    # ── Méthode 2 : Hamburger → Settings ──────────────────────
    try:
        await page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)

        # Clic hamburger
        for sel in [
            ".btn-icon.tgico-menu",
            "button.btn-icon[class*='menu']",
            ".sidebar-left .btn-icon:first-child",
            ".sidebar-left-header button",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    await el.click()
                    await page.wait_for_timeout(1200)
                    break
            except Exception:
                continue

        # Clic Settings dans le menu
        for txt in ["Settings", "Paramètres", "Настройки"]:
            try:
                for el_candidate in await page.get_by_text(txt).all():
                    try:
                        if await el_candidate.is_visible(timeout=800):
                            await el_candidate.click()
                            await page.wait_for_timeout(2000)
                            print("  [OK] Settings ouverts via menu hamburger")
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass

    print("  [!] Impossible d'ouvrir les paramètres — essai continué quand même")
    return False


async def click_edit_profile(page) -> bool:
    """Clique sur le bouton Edit (crayon) dans la page Settings."""
    for sel in [
        ".btn-icon.tgico-edit",
        "button.btn-icon[class*='edit']",
        ".btn-icon[title*='Edit']",
        ".btn-icon[title*='edit']",
    ]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.click()
                await page.wait_for_timeout(1500)
                print("  [OK] Mode édition profil activé")
                return True
        except Exception:
            continue

    # Essai JS : cliquer tous les btn-icon en cherchant tgico-edit
    try:
        clicked = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('.btn-icon');
                for (const b of btns) {
                    if (b.className.includes('edit') || b.title?.toLowerCase().includes('edit')) {
                        b.click(); return true;
                    }
                }
                return false;
            }
        """)
        if clicked:
            await page.wait_for_timeout(1500)
            print("  [OK] Mode édition activé via JS")
            return True
    except Exception:
        pass

    return False


async def change_bio(page, bio: str) -> bool:
    """Change la bio dans le formulaire d'édition de profil."""
    if not bio.strip():
        return True

    bio_selectors = [
        "textarea.input-field-textarea",
        "textarea[name='bio']",
        "textarea[placeholder*='bio']",
        "textarea[placeholder*='Bio']",
        "textarea[placeholder*='about']",
        "textarea",
        "div.input-field-textarea[contenteditable='true']",
    ]
    for sel in bio_selectors:
        try:
            els = page.locator(sel)
            count = await els.count()
            for i in range(count):
                el = els.nth(i)
                if not await el.is_visible(timeout=800):
                    continue
                placeholder = (await el.get_attribute("placeholder") or "").lower()
                aria = (await el.get_attribute("aria-label") or "").lower()
                # Prendre la bio s'il y a indice, sinon le dernier textarea visible
                if "bio" in placeholder or "about" in placeholder or "bio" in aria or count == 1:
                    await el.click()
                    await page.wait_for_timeout(300)
                    await page.keyboard.press("Control+a")
                    await page.wait_for_timeout(100)
                    await page.keyboard.press("Delete")
                    await page.wait_for_timeout(100)
                    await el.type(bio, delay=40)
                    print(f"  [OK] Bio mise à jour : {bio[:40]}{'…' if len(bio)>40 else ''}")
                    return True
        except Exception:
            continue
    print("  [!] Champ bio introuvable")
    return False


async def change_username(page, username: str) -> bool:
    """Change le @username dans le formulaire d'édition de profil."""
    username = username.strip().lstrip("@")
    if not username:
        return True

    username_selectors = [
        "input[name='username']",
        "input[placeholder*='username']",
        "input[placeholder*='Username']",
        "input[placeholder*='@']",
        "input.input-field-input[type='text']",
    ]
    for sel in username_selectors:
        try:
            els = page.locator(sel)
            count = await els.count()
            for i in range(count):
                el = els.nth(i)
                if not await el.is_visible(timeout=800):
                    continue
                placeholder = (await el.get_attribute("placeholder") or "").lower()
                name_attr   = (await el.get_attribute("name") or "").lower()
                if "username" in placeholder or "@" in placeholder or "username" in name_attr:
                    await el.click()
                    await page.wait_for_timeout(300)
                    await el.press("Control+a")
                    await page.wait_for_timeout(100)
                    await el.fill("")
                    await page.wait_for_timeout(100)
                    await el.type(username, delay=80)
                    await page.wait_for_timeout(1000)  # attendre validation username
                    print(f"  [OK] Username mis à jour : @{username}")
                    return True
        except Exception:
            continue
    print("  [!] Champ username introuvable")
    return False


async def save_profile_edits(page):
    """Appuie sur le bouton Enregistrer/Done dans le formulaire."""
    for sel in [
        "button.btn-primary",
        ".tgico-check",
        "button[class*='done']",
        "button[class*='save']",
        ".btn-primary",
    ]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                await el.click()
                await page.wait_for_timeout(2000)
                print("  [OK] Modifications enregistrées")
                return True
        except Exception:
            continue

    # Essai touche Entrée
    try:
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1000)
        return True
    except Exception:
        pass
    return False


async def change_photo(page, photo_path: str) -> bool:
    """Change la photo de profil dans Telegram Web K."""
    if not photo_path or not os.path.isfile(photo_path):
        return True

    print("  [->] Changement de photo de profil...")

    # ── Trouver et cliquer sur l'avatar dans Settings ──────────
    avatar_clicked = False
    avatar_selectors = [
        ".profile-photo .avatar",
        ".settings-main-profile .avatar",
        ".sidebar-left .profile-photo",
        ".settings-profile .avatar",
        ".userpic",
        ".avatar-full",
        "[class*='avatar']",
    ]
    for sel in avatar_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.click()
                await page.wait_for_timeout(1500)
                avatar_clicked = True
                print(f"  [OK] Avatar cliqué ({sel})")
                break
        except Exception:
            continue

    if not avatar_clicked:
        print("  [!] Avatar introuvable — essai direct input file")

    # ── Essayer de déclencher un file chooser ──────────────────
    # Méthode A : après le clic sur l'avatar, chercher "Upload Photo" dans le menu
    for txt in ["Upload Photo", "Charger une photo", "Set as Main Photo", "Choose Photo",
                "Change Photo", "Choisir une photo", "Upload photo"]:
        try:
            opt = page.get_by_text(txt).first
            if await opt.is_visible(timeout=1000):
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    await opt.click()
                fc = await fc_info.value
                await fc.set_files(photo_path)
                await page.wait_for_timeout(4000)
                print(f"  [OK] Photo uploadée via '{txt}'")
                # Confirmer le crop si dialogue
                for conf in ["button.btn-primary", ".crop-confirm", ".tgico-check"]:
                    try:
                        btn = page.locator(conf).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            await page.wait_for_timeout(2000)
                            break
                    except Exception:
                        pass
                return True
        except Exception:
            continue

    # Méthode B : hover sur l'avatar + click overlay d'upload
    for sel in [".profile-photo .avatar-edit", ".profile-photo-edit", ".avatar-edit-icon"]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1000):
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    await el.click()
                fc = await fc_info.value
                await fc.set_files(photo_path)
                await page.wait_for_timeout(4000)
                print(f"  [OK] Photo uploadée via overlay d'édition")
                return True
        except Exception:
            continue

    # Méthode C : trouver directement un input[type=file] caché
    try:
        file_inputs = page.locator("input[type='file']")
        count = await file_inputs.count()
        for i in range(count):
            try:
                fi = file_inputs.nth(i)
                await fi.set_input_files(photo_path)
                await page.wait_for_timeout(4000)
                print(f"  [OK] Photo uploadée via input file direct")
                # Confirmer crop
                for conf in ["button.btn-primary", ".tgico-check"]:
                    try:
                        btn = page.locator(conf).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            await page.wait_for_timeout(2000)
                            break
                    except Exception:
                        pass
                return True
            except Exception:
                continue
    except Exception:
        pass

    print("  [!] Upload photo échoué — vérifier le sélecteur avatar")
    return False


async def apply_changes(page, config: dict):
    """Applique tous les changements de profil (photo, username, bio)."""

    username  = (config.get("username")  or "").strip().lstrip("@")
    bio       = (config.get("bio")       or "").strip()
    photo_b64 = (config.get("photo_b64") or "").strip()
    photo_nm  = (config.get("photo_name") or "photo.jpg").strip()

    print(f"\n{'='*56}")
    print(f"  CHANGEMENTS PROFIL → {config['profile_id']}")
    if username:  print(f"  @Username : @{username}")
    if bio:       print(f"  Bio       : {bio[:50]}{'…' if len(bio)>50 else ''}")
    if photo_b64: print(f"  Photo     : {photo_nm}")
    print(f"{'='*56}\n")

    # ── Sauvegarde de la photo dans un fichier temp ────────────
    photo_tmp = None
    if photo_b64:
        ext = "jpg" if photo_nm.lower().endswith((".jpg", ".jpeg")) else "png"
        photo_tmp = os.path.join(tempfile.gettempdir(), f"tg_photo_{config['profile_id']}.{ext}")
        try:
            with open(photo_tmp, "wb") as fh:
                fh.write(base64.b64decode(photo_b64))
            print(f"  [OK] Photo temp écrite : {photo_tmp}")
        except Exception as e:
            print(f"  [!] Erreur écriture photo temp : {e}")
            photo_tmp = None

    # ── Navigation vers Telegram ───────────────────────────────
    try:
        await page.goto("https://web.telegram.org/k/",
                        wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pass

    if not await wait_telegram(page):
        raise Exception("Telegram non connecté sur ce profil — connecte-toi manuellement d'abord dans AdsPower")

    print("  [OK] Telegram connecté")

    # ── PHOTO DE PROFIL (avant settings pour éviter les conflits) ──
    if photo_tmp:
        await open_settings(page)
        await page.wait_for_timeout(1000)
        await change_photo(page, photo_tmp)
        try:
            os.remove(photo_tmp)
        except Exception:
            pass
        # Revenir aux settings après l'upload
        await open_settings(page)
        await page.wait_for_timeout(1500)
    else:
        await open_settings(page)
        await page.wait_for_timeout(1500)

    # ── BIO + USERNAME ─────────────────────────────────────────
    if bio or username:
        edit_ok = await click_edit_profile(page)
        await page.wait_for_timeout(1000)

        if not edit_ok:
            # Certains builds de Telegram Web K mettent les champs directement dans Settings
            print("  [i] Bouton Edit non trouvé — tentative directe sur les champs")

        bio_ok  = await change_bio(page, bio)       if bio      else True
        user_ok = await change_username(page, username) if username else True

        if bio_ok or user_ok:
            await save_profile_edits(page)

    await page.wait_for_timeout(2000)
    print(f"\n{'='*56}")
    print(f"  Profil {config['profile_id']} mis à jour !")
    print(f"{'='*56}\n")


# ── Main ─────────────────────────────────────────────────────

async def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("[X] Usage : python profile_changer.py <profile_id> [--silent]")
        sys.exit(1)

    IS_SILENT = "--silent" in sys.argv   # lancé depuis le daemon → pas de pause

    profile_id = sys.argv[1].strip()
    print(f"\n{'='*56}")
    print(f"  Profile Changer — {profile_id}")
    print(f"{'='*56}")

    # Charge la config depuis Supabase
    config = load_config(profile_id)
    if not config:
        print(f"[X] Aucune config trouvée pour {profile_id} dans Supabase (table profile_setup)")
        print("    → Configure d'abord le profil dans le dashboard onglet ⚙ Setup")
        if not IS_SILENT:
            input("\nAppuie sur Entrée pour fermer...")
        sys.exit(1)

    print(f"[OK] Config chargée pour {profile_id}")

    # Démarre AdsPower
    print(f"[->] Démarrage du navigateur AdsPower ({profile_id})...")
    try:
        cdp_url = start_browser(profile_id)
    except Exception as e:
        print(f"[X] Impossible de démarrer AdsPower : {e}")
        print("    → Vérifie qu'AdsPower est lancé et que le profil existe")
        if not IS_SILENT:
            input("\nAppuie sur Entrée pour fermer...")
        sys.exit(1)

    print(f"[OK] Navigateur démarré")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            page    = context.pages[0] if context.pages else await context.new_page()
            await page.bring_to_front()

            # Applique les changements
            await apply_changes(page, config)

            # Déconnexion propre
            try:
                await browser.disconnect()
            except Exception:
                pass

    except Exception as e:
        print(f"\n[X] Erreur : {e}")

    finally:
        stop_browser(profile_id)
        print(f"[OK] AdsPower fermé ({profile_id})")

    if not IS_SILENT:
        input("\nTerminé ! Appuie sur Entrée pour fermer...")


if __name__ == "__main__":
    asyncio.run(main())
