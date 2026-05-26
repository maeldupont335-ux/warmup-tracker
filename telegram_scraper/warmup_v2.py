"""
warmup_v2.py — Chauffe Telegram 15 jours multi-profils AdsPower
Parcourt 10 profils un par un : warm-up complet sur chaque avant de passer au suivant.

Usage :
  python warmup_v2.py               → lance tous les profils (session du jour)
  python warmup_v2.py --status      → voir la progression de tous les profils
  python warmup_v2.py --profile 3   → lance uniquement le profil n°3 (1-indexed)
  python warmup_v2.py --reset 2     → remet à zéro le profil n°2
"""

import asyncio
import csv
import json
import os
import random
import subprocess
import sys
import time
import urllib.parse
import requests
from datetime import date
from playwright.async_api import async_playwright

# ============================================================
# Profils : chargés depuis le dashboard Supabase en priorité, sinon profiles.txt
DASHBOARD_URL   = "https://warmup-tracker.onrender.com"
DASHBOARD_TOKEN = "Compte.1"

def _load_profiles() -> list:
    # 1. Essai depuis le dashboard (Supabase)
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/profiles", timeout=10)
        if r.status_code == 200:
            ids = r.json()
            if ids:
                print(f"[OK] {len(ids)} profils charges depuis le dashboard Supabase")
                return ids
    except Exception:
        pass
    # 2. Fallback : profiles.txt local
    path = os.path.join(os.path.dirname(__file__), "profiles.txt")
    if not os.path.exists(path):
        return ["k1csfeja"]
    profiles = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                profiles.append(line)
    print(f"[OK] {len(profiles)} profils charges depuis profiles.txt (fallback)")
    return profiles

ADSPOWER_PROFILES = _load_profiles()

ADSPOWER_API = "http://local.adspower.net:50325"
ADSPOWER_KEY = "942d5c4fa00deedac520c3310912ee6100795935b355b33b"
DM_CSV       = "output/membres.csv"

# ── Groupes à rejoindre (J1:4 aléat., J2:3 aléat., J3+:2 tous les 2j) ──
GROUPS_TO_JOIN = [
    ("https://t.me/ofmva_fr",              False, None),
    ("https://t.me/fraofm",                False, None),
    ("https://t.me/c/1900517374/1",        True,  None),
    ("https://t.me/OFstarters",            False, None),
    ("https://t.me/noahofmfr",             False, None),
    ("https://t.me/ofmanagementgroupe",    False, None),
    ("https://t.me/OFMNetworkgroup",       False, None),
    ("https://t.me/richclubofm",           False, None),
    ("https://t.me/ofmglobalnetworkgroup", False, None),
    ("https://t.me/shaftofmjobs",          False, None),
    ("https://t.me/+iI97FqBOGlE4ZWY0",    True,  None),
    ("https://t.me/parismodels_ofm",       False, None),
    ("https://t.me/elisaflamex",           False, None),
    ("https://t.me/cupidbotg",             False, None),
    ("https://t.me/roroivx",               False, None),
    ("https://t.me/TheValere",             False, None),
]

# Groupes publics pour la phase de lecture
PUBLIC_GROUPS = [
    "ofmva_fr", "fraofm", "OFstarters", "noahofmfr",
    "ofmanagementgroupe", "OFMNetworkgroup", "richclubofm",
    "ofmglobalnetworkgroup", "shaftofmjobs", "parismodels_ofm",
    "elisaflamex", "cupidbotg", "roroivx", "TheValere",
]


def get_join_count(day: int) -> int:
    """Retourne le nombre de groupes à rejoindre selon le jour."""
    if day == 1:
        return 4
    elif day == 2:
        return 3
    elif day >= 3 and (day - 3) % 2 == 0:  # Jours 3, 5, 7, 9, 11, 13, 15
        return 2
    else:
        return 0

GROUP_MESSAGES = [
    (
        "Nous recherchons des assistants virtuels pour gérer des comptes Instagram.\n\n"
        "✅Ce que nous offrons :\n"
        "– Formation incluse\n"
        "– Process clairs\n"
        "– Paiement en crypto\n"
        "– 100€/mois + prime💸\n\n"
        "🕐2h/jour, flexibles\n"
        "🎯Profils recherchés : disciplinés, fiables et réactifs"
    ),
    (
        "🚀 On recrute des gestionnaires de comptes Instagram !\n\n"
        "Tu veux un complément de revenu sérieux ?\n\n"
        "✅ Formation complète offerte\n"
        "✅ Méthodes claires et éprouvées\n"
        "✅ Rémunération en crypto\n"
        "✅ 100€/mois + primes💸\n\n"
        "⏰ Seulement 2h/jour — horaires flexibles\n"
        "👤 Profils motivés, fiables et réactifs\n\n"
        "Intéressé(e) ? Envoie un message privé 👇"
    ),
    (
        "💼 Opportunité : Assistant(e) virtuel(le) Instagram\n\n"
        "On agrandit notre équipe !\n\n"
        "• Formation incluse dès le départ\n"
        "• Processus simples et structurés\n"
        "• Paiement en crypto\n"
        "• 100€/mois + bonus💸\n\n"
        "🕐 2h par jour suffisent\n"
        "🎯 Profil : discipliné(e), fiable, réactif(ve)\n\n"
        "MP pour plus d'infos !"
    ),
    (
        "📢 Offre d'emploi en ligne — Gestionnaire Instagram\n\n"
        "Tu cherches un revenu complémentaire depuis chez toi ?\n\n"
        "✅ Formation fournie\n"
        "✅ Process clairs\n"
        "✅ Payé en crypto\n"
        "✅ 100€/mois + prime💸\n\n"
        "⏱️ 2h/jour, horaires flexibles\n"
        "✔️ Discipliné(e) et réactif(ve) ? C'est toi qu'on cherche !"
    ),
    (
        "👀 Tu veux bosser en ligne 2h/jour et être payé(e) ?\n\n"
        "On recherche des assistants virtuels pour gérer des comptes Instagram.\n\n"
        "– Formation complète incluse\n"
        "– Méthodes simples et efficaces\n"
        "– Rémunération crypto\n"
        "– 100€/mois + primes💸\n\n"
        "🎯 Personnes disciplinées, fiables et réactives\n\n"
        "Dis-moi en MP si ça t'intéresse 🙌"
    ),
]

DM_RESPONSES = [
    "Coucou ! 😊", "Salut !", "Hey, ça va ?", "Bonjour !",
    "Coucou, comment tu vas ?", "Salut, tout va bien ?", "Hey ! 👋",
    "Bonjour, ça roule ?", "Coucou toi 😄", "Salut salut !",
    "Hello !", "Coucou, quoi de neuf ?", "Salut, comment ça se passe ?",
    "Hey, bien ou bien ? 😄", "Bonjour ! Comment tu vas ?",
]

PLAN = {
    # (lectures, posts_canal, dms) — groupes gérés par get_join_count()
    1:  (3, 0, 0),   2:  (3, 0, 0),   3:  (3, 1, 0),
    4:  (3, 1, 0),   5:  (4, 1, 0),   6:  (3, 1, 0),
    7:  (4, 1, 0),   8:  (3, 1, 1),   9:  (4, 1, 2),
    10: (3, 1, 3),   11: (4, 1, 4),   12: (3, 1, 5),
    13: (4, 1, 6),   14: (3, 1, 8),   15: (4, 1, 10),
}

# Chemin du script Mass DM à lancer après J15 (à configurer)
MASS_DM_SCRIPT = r"C:\Users\MAEL\Downloads\AGENCY\AUTOMATION\telegram_scraper\dm_sender.py"
# ============================================================


# ── Chemins de fichiers par profil ───────────────────────────

def progress_file(profile_id: str) -> str:
    return f"output/warmup_progress_{profile_id}.json"

def dm_log_file(profile_id: str) -> str:
    return f"output/dm_log_{profile_id}.csv"


# ── Gestion de la progression ─────────────────────────────────

def load_progress(profile_id: str) -> dict:
    path = progress_file(profile_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        last = data.get("last_run_date")
        if last and last != str(date.today()) and data.get("done_today"):
            data["day"] += 1
            data["done_today"] = False
            save_progress(profile_id, data)
        return data
    return {
        "start_date":        str(date.today()),
        "last_run_date":     None,
        "day":               1,
        "done_today":        False,
        "join_index":        0,
        "joined_groups":     [],
        "private_chat_urls": {},
        "dms_sent":          [],
        "posts_total":       0,
    }


def save_progress(profile_id: str, data: dict):
    os.makedirs("output", exist_ok=True)
    with open(progress_file(profile_id), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_already_dmed(profile_id: str) -> set:
    sent = set()
    path = dm_log_file(profile_id)
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("statut") == "envoye":
                    sent.add(row.get("username", ""))
    return sent


def log_dm(profile_id: str, username: str, prenom: str):
    from datetime import datetime
    path = dm_log_file(profile_id)
    file_exists = os.path.exists(path)
    os.makedirs("output", exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["username", "prenom", "statut", "heure"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "username": username, "prenom": prenom,
            "statut":   "envoye",
            "heure":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })


# ── Affichage du status ───────────────────────────────────────

def print_all_status():
    print(f"\n{'='*62}")
    print(f"  CHAUFFE TELEGRAM — STATUT MULTI-PROFILS ({len(ADSPOWER_PROFILES)} profils)")
    print(f"{'='*62}")
    for idx, pid in enumerate(ADSPOWER_PROFILES, 1):
        data = load_progress(pid)
        day  = data["day"]
        bar  = "█" * min(day, 15) + "░" * max(0, 15 - day)
        done = "✓" if data.get("done_today") else "·"
        fin  = " TERMINÉ" if day > 15 else ""
        print(f"  [{idx:02d}] {pid:<14} J{day:02d}/15 [{bar}] {done}{fin}")
    print(f"{'='*62}\n")


# ── Envoi données dashboard ───────────────────────────────────

def push_to_dashboard(profile_id: str, progress: dict, session: dict):
    """Envoie les stats du profil au dashboard web après chaque session."""
    if not DASHBOARD_URL:
        return
    try:
        payload = {
            "token":         DASHBOARD_TOKEN,
            "profile_id":    profile_id,
            "day":           progress["day"],
            "start_date":    progress.get("start_date"),
            "done_today":    progress.get("done_today", False),
            "dms_total":     len(progress.get("dms_sent", [])),
            "posts_total":   progress.get("posts_total", 0),
            "groups_joined": len(progress.get("joined_groups", [])),
            "dm_responses":  session.get("dm_responses", 0),
            "dms_session":   session.get("dms_session", 0),
            "posts_session": session.get("posts_session", 0),
            "last_error":    session.get("last_error", ""),
        }
        requests.post(f"{DASHBOARD_URL}/api/update", json=payload, timeout=30)
        print(f"[->] Dashboard mis à jour pour {profile_id}")
    except Exception as e:
        print(f"[!] Dashboard non joignable : {e}")


# ── AdsPower ──────────────────────────────────────────────────

BROWSER_W = 960   # largeur fenetre AdsPower (px)
BROWSER_H = 680   # hauteur fenetre AdsPower (px)
BROWSER_X = 30    # position X depuis le bord gauche
BROWSER_Y = 30    # position Y depuis le haut

def start_browser(profile_id: str) -> str:
    launch_args = json.dumps([
        f"--window-size={BROWSER_W},{BROWSER_H}",
        f"--window-position={BROWSER_X},{BROWSER_Y}",
    ])
    r = requests.get(
        f"{ADSPOWER_API}/api/v1/browser/start",
        params={
            "user_id":     profile_id,
            "api_key":     ADSPOWER_KEY,
            "launch_args": launch_args,
        },
        headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
        timeout=15,
    )
    data = r.json()
    if data.get("code") != 0:
        raise Exception(f"AdsPower ({profile_id}) : {data.get('msg')}")
    return data["data"]["ws"]["puppeteer"]


def stop_browser(profile_id: str):
    """Arrete le profil AdsPower (sans retour)."""
    _stop_browser_check(profile_id)


def _stop_browser_check(profile_id: str) -> bool:
    """Arrete le profil AdsPower — retourne True si succes, False si echec."""
    for attempt in range(1, 4):
        try:
            r = requests.get(
                f"{ADSPOWER_API}/api/v1/browser/stop",
                params={"user_id": profile_id, "api_key": ADSPOWER_KEY},
                headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
                timeout=10,
            )
            data = r.json()
            code = data.get("code")
            msg  = data.get("msg", "")
            if code == 0:
                print(f"[OK] AdsPower ferme ({profile_id})")
                return True
            print(f"[!] AdsPower stop tentative {attempt}/3 — code={code} msg={msg}")
        except Exception as e:
            print(f"[!] AdsPower stop tentative {attempt}/3 — erreur : {e}")
        time.sleep(3)
    print(f"[X] Echec fermeture AdsPower {profile_id} apres 3 tentatives")
    return False


# ── Helpers Playwright ────────────────────────────────────────

async def get_real_input(page):
    try:
        all_inputs = page.locator("div.input-message-input")
        count = await all_inputs.count()
        for i in range(count):
            el  = all_inputs.nth(i)
            cls = await el.get_attribute("class") or ""
            ce  = await el.get_attribute("contenteditable") or ""
            if "fake" in cls:
                continue
            if ce == "true":
                return el
    except Exception:
        pass
    return None


async def focus_input(page):
    try:
        await page.evaluate("""
            const inputs = document.querySelectorAll('div.input-message-input[contenteditable="true"]');
            for (const el of inputs) {
                if (!el.classList.contains('input-field-input-fake')) { el.focus(); break; }
            }
        """)
        await page.wait_for_timeout(300)
    except Exception:
        pass


async def type_message(page, inp, text: str):
    await focus_input(page)
    try:
        await inp.click(force=True)
    except Exception:
        pass
    await page.wait_for_timeout(300)
    await page.keyboard.press("Control+a")
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(200)

    for char in text:
        if char == "\n":
            await page.keyboard.press("Shift+Enter")
            await page.wait_for_timeout(random.randint(100, 300))
        else:
            await inp.type(char, delay=random.randint(55, 150))

    await page.wait_for_timeout(random.randint(700, 1400))
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(2500)


# ── Actions Telegram ──────────────────────────────────────────

async def rejoindre_groupe(page, invite_url: str, is_private: bool) -> str | None:
    print(f"    [->] Rejoindre : {invite_url[:55]}...")
    try:
        # Amène la fenêtre au premier plan pour que l'action soit visible
        await page.bring_to_front()
        # Délai humain avant de naviguer
        await page.wait_for_timeout(random.randint(1500, 3500))

        if is_private:
            hash_part = invite_url.split("+")[-1].rstrip("/")
            tg_link   = f"tg://join?invite={hash_part}"
            encoded   = urllib.parse.quote(tg_link, safe="")
            web_url   = f"https://web.telegram.org/k/#?tgaddr={encoded}"
        else:
            # Extraire le username depuis l'URL t.me
            if "t.me/" in invite_url:
                username = invite_url.split("t.me/")[-1].rstrip("/").split("/")[0]
            elif invite_url.startswith("@"):
                username = invite_url[1:]
            else:
                username = invite_url
            web_url = f"https://web.telegram.org/k/#@{username}"

        # ── Navigation en 2 étapes ──────────────────────────────
        # Étape 1 : charge Telegram sans hash pour initialiser le SPA
        try:
            await page.goto("https://web.telegram.org/k/",
                            wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(2500)   # laisse Telegram charger son état interne

        # Étape 2 : navigue vers la cible (SPA initialisé = hash géré)
        try:
            await page.goto(web_url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(random.randint(3000, 5000))

        # ── Détection redirection t.me → popup "Ouvrir Telegram Desktop" ──────
        # Si le browser a quitté web.telegram.org, on force le retour
        for _attempt in range(3):
            cur = page.url
            if "web.telegram.org" not in cur:
                print(f"    [!] Redirection detectee ({cur[:50]}) — retour Telegram Web K...")
                try:
                    await page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(1500)
                try:
                    await page.goto("https://web.telegram.org/k/",
                                    wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass
                await page.wait_for_timeout(2500)
                try:
                    await page.goto(web_url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass
                await page.wait_for_timeout(random.randint(3000, 5000))
            else:
                break
        # ────────────────────────────────────────────────────────────────────────

        # Vérification URL — si on n'est pas sur la bonne page, force un 2ème essai
        if not is_private:
            current = page.url
            if username.lower() not in current.lower():
                print(f"    [!] Mauvaise page ({current.split('#')[-1]}) — retry...")
                try:
                    await page.goto(web_url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass
                await page.wait_for_timeout(random.randint(3000, 5000))
                if username.lower() not in page.url.lower():
                    print(f"    [X] Impossible de charger {username} — page incorrecte")
                    return None
        # ───────────────────────────────────────────────────────

        joined = False

        # Attente supplementaire pour que la page finisse de rendre
        await page.wait_for_timeout(2500)

        # Sélecteurs étendus pour Telegram Web K (toutes versions)
        SELECTORS = [
            "button.btn-primary",
            ".popup-button.btn-primary",
            ".join-button",
            "button[class*='join']",
            ".chat-join",
            ".bubbles-inner button",
            "button.chat-join-button",
            ".bottom-bar button",
            ".preloader-container + div button",
            "button.btn.btn-primary",
            ".tgme_action_button_new",
            ".chat-input-main button",
            "button.btn-circle-border",
        ]

        MOTS_JOIN = ["join", "rejoindre", "subscribe", "abonner", "s'abonner",
                     "participer", "entrer", "ok", "view", "voir", "ouvrir",
                     "request", "demande", "apply", "send request", "suivre"]

        for sel in SELECTORS:
            try:
                btns = page.locator(sel)
                count = await btns.count()
                for i in range(count):
                    btn = btns.nth(i)
                    if not await btn.is_visible(timeout=2000):
                        continue
                    txt = (await btn.inner_text()).strip().lower()
                    if not txt or any(w in txt for w in MOTS_JOIN):
                        await btn.click(force=True)
                        await page.wait_for_timeout(3000)
                        joined = True
                        break
            except Exception:
                pass
            if joined:
                break

        # Fallback 1 : cherche n'importe quel bouton visible avec un texte de join
        if not joined:
            try:
                all_btns = page.locator("button")
                count = await all_btns.count()
                for i in range(count):
                    btn = all_btns.nth(i)
                    try:
                        if not await btn.is_visible(timeout=500):
                            continue
                        txt = (await btn.inner_text()).strip().lower()
                        if any(w in txt for w in MOTS_JOIN):
                            await btn.click(force=True)
                            await page.wait_for_timeout(3000)
                            joined = True
                            print(f"    [OK] Bouton trouve via fallback : '{txt}'")
                            break
                    except Exception:
                        pass
            except Exception:
                pass

        # Fallback 2 : JavaScript — clique direct sur tout élément avec texte join
        if not joined:
            try:
                clicked = await page.evaluate("""
                    () => {
                        const words = ['join', 'rejoindre', 'subscribe', 'abonner',
                                       'apply', 'participer', 'request', 'demande',
                                       "s'abonner", 'suivre', 'voir'];
                        const els = document.querySelectorAll(
                            'button, .btn-primary, .chat-join, [class*="join"], .bottom-bar *'
                        );
                        for (const el of els) {
                            const txt = (el.innerText || el.textContent || '').toLowerCase().trim();
                            if (txt && words.some(w => txt.includes(w))) {
                                el.click();
                                return txt;
                            }
                        }
                        return null;
                    }
                """)
                if clicked:
                    await page.wait_for_timeout(3000)
                    joined = True
                    print(f"    [OK] Bouton clique via JS : '{clicked}'")
            except Exception:
                pass

        final_url = page.url

        if joined:
            print(f"    [OK] Rejoint ! URL : {final_url.split('#')[-1]}")
            return final_url

        # ── Pas de bouton trouvé : vérifie si réellement déjà membre ──────────
        # Check 1 : champ de saisie visible = membre de groupe (100% fiable)
        try:
            if await page.locator("div.input-message-input[contenteditable='true']").first.is_visible(timeout=3000):
                print(f"    [OK] Deja membre de ce groupe (champ de saisie actif)")
                return final_url
        except Exception:
            pass

        # Check 2 : URL correcte ET aucun bouton Join/Subscribe visible = abonne canal
        if not is_private and username.lower() in final_url.lower():
            try:
                btn_visible = await page.evaluate("""
                    () => {
                        const mots = ['join','rejoindre','subscribe','abonner',"s'abonner",'participer'];
                        const els  = document.querySelectorAll('button, .btn-primary, [class*="join"]');
                        for (const el of els) {
                            const txt = (el.innerText || el.textContent || '').toLowerCase().trim();
                            if (txt && mots.some(w => txt.includes(w)) && el.offsetParent !== null)
                                return true;
                        }
                        return false;
                    }
                """)
            except Exception:
                btn_visible = True  # en cas d'erreur JS, on ne suppose rien

            if not btn_visible:
                print(f"    [OK] Deja abonne a ce canal (aucun bouton rejoindre)")
                return final_url

        # Echec réel
        print(f"    [!] Bouton rejoindre non trouve pour : {invite_url[:45]}")
        return None

    except Exception as e:
        print(f"    [X] Erreur join : {e}")
        return None


async def lire_chat(page, url: str):
    label = url.split("#")[-1] or url
    print(f"    [->] Lecture de {label}...")
    try:
        await page.bring_to_front()
        # Délai humain avant navigation
        await page.wait_for_timeout(random.randint(1200, 2800))
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(random.randint(2000, 4000))
        for _ in range(random.randint(3, 7)):
            await page.mouse.wheel(0, random.randint(-220, -70))
            await page.wait_for_timeout(random.randint(1000, 2800))
        await page.mouse.wheel(0, random.randint(80, 200))
        await page.wait_for_timeout(random.randint(800, 1600))
        print(f"    [OK] Lu")
    except Exception as e:
        print(f"    [X] Erreur lecture : {e}")


async def poster_dans_groupe(page, group_url: str, message: str, topic: str = None) -> bool:
    label = group_url.split("#")[-1]
    print(f"    [->] Post dans {label}" + (f" / topic '{topic}'" if topic else "") + "...")
    try:
        await page.bring_to_front()
        # Délai humain avant d'arriver dans le canal
        await page.wait_for_timeout(random.randint(2000, 4500))
        await page.goto(group_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(random.randint(2000, 4000))

        if topic:
            found = False
            for sel in [".topic-item", ".forum-topic", ".chat-topic", ".list-item", ".chatlist-chat"]:
                try:
                    items = page.locator(sel)
                    count = await items.count()
                    for i in range(count):
                        el  = items.nth(i)
                        txt = (await el.inner_text()).lower()
                        if topic.lower() in txt:
                            await el.click()
                            await page.wait_for_timeout(2500)
                            found = True
                            break
                    if found:
                        break
                except Exception:
                    pass
            if not found:
                print(f"    [!] Topic '{topic}' non trouvé, post dans le chat principal")

        await page.wait_for_timeout(random.randint(4000, 9000))
        inp = await get_real_input(page)
        if not inp:
            print(f"    [--] Champ message indisponible (canal broadcast ?)")
            return False

        await type_message(page, inp, message)
        print(f"    [OK] Message posté")
        return True

    except Exception as e:
        print(f"    [X] Erreur post : {e}")
        return False


async def repondre_dms_recus(page) -> int:
    print("\n[->] Verification des DMs recus...")
    reponses = 0
    try:
        await page.bring_to_front()
        await page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        # Trouve directement les li.chatlist-chat qui contiennent un badge non-gris
        chats_avec_badge = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('li.chatlist-chat');
                const result = [];
                for (const item of items) {
                    const badge = item.querySelector('.badge:not(.badge-gray)');
                    if (badge) {
                        const rect = item.getBoundingClientRect();
                        result.push({ x: rect.x + rect.width/2, y: rect.y + rect.height/2 });
                    }
                }
                return result.slice(0, 5);
            }
        """)

        if not chats_avec_badge:
            print("    [OK] Aucun DM non lu\n")
            return 0

        print(f"    [->] {len(chats_avec_badge)} chat(s) non lu(s)")

        for coords in chats_avec_badge:
            try:
                # Clic direct aux coordonnées du chat
                await page.mouse.click(coords['x'], coords['y'])
                await page.wait_for_timeout(random.randint(1500, 3000))

                inp = await get_real_input(page)
                if not inp:
                    continue

                # Vérifie que c'est bien un DM (peer_id positif)
                peer_id = await inp.get_attribute("data-peer-id") or ""
                if peer_id.startswith("-"):
                    continue

                reponse = random.choice(DM_RESPONSES)
                print(f"    [->] Reponse : '{reponse}'")
                await type_message(page, inp, reponse)
                reponses += 1
                await page.wait_for_timeout(random.randint(12000, 25000))

            except Exception as e:
                print(f"    [X] Erreur reponse : {e}")

    except Exception as e:
        print(f"    [X] Erreur verif DMs : {e}")

    print(f"    [OK] {reponses} reponse(s) envoyee(s)\n")
    return reponses


async def envoyer_dm(page, username: str, prenom: str) -> bool:
    print(f"    [->] DM à @{username}...")
    try:
        await page.bring_to_front()
        # Délai humain avant d'ouvrir la conversation
        await page.wait_for_timeout(random.randint(2000, 5000))
        await page.goto(
            f"https://web.telegram.org/k/#@{username}",
            wait_until="domcontentloaded", timeout=20000,
        )
        await page.wait_for_timeout(random.randint(3000, 5000))

        for sel in ["button.btn-primary", ".start-bot-button"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1500):
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        real_input = None
        try:
            all_inp = page.locator("div.input-message-input")
            count   = await all_inp.count()
            for i in range(count):
                el  = all_inp.nth(i)
                cls = await el.get_attribute("class") or ""
                ce  = await el.get_attribute("contenteditable") or ""
                if "fake" in cls:
                    continue
                if ce == "false":
                    print(f"    [--] @{username} DMs bloqués")
                    return False
                if ce == "true":
                    real_input = el
                    break
        except Exception:
            pass

        if not real_input:
            print(f"    [--] @{username} introuvable")
            return False

        await type_message(page, real_input, "Salut")

        for sel in [".message.is-error", ".tgico-msg-failed"]:
            try:
                if await page.locator(sel).last.is_visible(timeout=1500):
                    print(f"    [--] @{username} rejeté (confidentialité)")
                    return False
            except Exception:
                pass

        print(f"    [OK] DM envoyé à {prenom} (@{username})")
        return True

    except Exception as e:
        print(f"    [X] Erreur DM @{username} : {e}")
        return False


# ── Session warm-up pour UN profil ───────────────────────────

async def run_warmup_for_profile(profile_id: str, profile_num: int, total: int):
    """Lance la session du jour pour un profil AdsPower donné."""

    progress        = load_progress(profile_id)
    day             = progress["day"]
    n_lect, n_posts, n_dms = PLAN.get(day, (3, 0, 0))
    join_count      = get_join_count(day)
    bar             = "█" * day + "░" * (15 - day)
    session_errors  = []   # collecte toutes les erreurs de la session

    print(f"\n{'='*60}", flush=True)
    print(f"  PROFIL [{profile_num}/{total}]  ID: {profile_id}", flush=True)
    print(f"  CHAUFFE TELEGRAM — Jour {day}/15  [{bar}]", flush=True)
    print(f"  Début : {progress['start_date']}  |  Aujourd'hui : {date.today()}", flush=True)
    print(f"{'='*60}", flush=True)

    if day > 15:
        print(f"  [OK] Chauffe déjà terminée pour ce profil — passage au suivant.\n")
        return

    if progress.get("done_today"):
        print(f"  [OK] Session du jour déjà effectuée pour ce profil — passage au suivant.\n")
        return

    print(f"\n  Plan du Jour {day} :")
    print(f"  • {join_count} groupe(s) à rejoindre")
    print(f"  • {n_lect} chat(s) à lire")
    print(f"  • {n_posts} post(s) dans les groupes")
    print(f"  • Réponses aux DMs reçus : OUI")
    print(f"  • {n_dms} DM(s) à envoyer à des non-contacts\n")

    # Prépare les cibles DM
    dm_targets = []
    if n_dms > 0 and os.path.exists(DM_CSV):
        already = load_already_dmed(profile_id) | set(progress.get("dms_sent", []))
        with open(DM_CSV, newline="", encoding="utf-8-sig") as f:
            members = list(csv.DictReader(f))
        candidates = [m for m in members
                      if m.get("username") and m.get("bot") != "Oui"
                      and m["username"] not in already]
        dm_targets = random.sample(candidates, min(n_dms, len(candidates))) if candidates else []

    # Démarrage AdsPower
    try:
        print(f"[->] Démarrage du navigateur AdsPower ({profile_id})...", flush=True)
        cdp_url = start_browser(profile_id)
    except Exception as e:
        err = f"Demarrage AdsPower echoue : {e}"
        print(f"[X] {err}\n")
        session_errors.append(err)
        push_to_dashboard(profile_id, progress, {"last_error": " | ".join(session_errors)})
        return

    nb_rep = 0
    groups_joined_today = 0
    dms_ok = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            page    = context.pages[0] if context.pages else await context.new_page()

            # ── Force la fenêtre AdsPower au premier plan ──────────
            await page.bring_to_front()
            try:
                import ctypes
                # Active la fenêtre Chrome via l'API Windows
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            # ───────────────────────────────────────────────────────

            # Attend que la page soit prête (max 15s)
            for _ in range(15):
                if "web.telegram.org" in page.url:
                    break
                await page.wait_for_timeout(1000)

            if "web.telegram.org" not in page.url:
                print("[->] Navigation vers Telegram Web...")
                try:
                    await page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded", timeout=30000)
                    await page.bring_to_front()
                except Exception as e:
                    session_errors.append(f"Navigation Telegram echouee : {e}")

            # Attente que la liste des chats soit visible
            print("[->] Attente chargement Telegram...", flush=True)
            telegram_ok = False
            for _ in range(20):
                try:
                    ok = await page.locator(".chatlist-chat, .chat-list, .sidebar").first.is_visible(timeout=1500)
                    if ok:
                        telegram_ok = True
                        break
                except Exception:
                    pass
                await page.wait_for_timeout(1000)

            if not telegram_ok:
                err = "Telegram non connecte — connecte un compte dans AdsPower !"
                print(f"\n{'='*60}")
                print(f"  [X] COMPTE TELEGRAM ABSENT sur le profil {profile_id}")
                print(f"  [X] Le profil AdsPower n'a pas de compte Telegram connecte.")
                print(f"  [X] Session annulee — ouvre AdsPower, connecte le compte, relance.")
                print(f"{'='*60}\n")
                session_errors.append(err)
                # Envoie l'erreur au dashboard immediatement
                push_to_dashboard(profile_id, progress, {
                    "last_error": " | ".join(session_errors)
                })
                # Fermeture immediate sans executer les phases
                try:
                    await browser.disconnect()
                except Exception:
                    pass
                return   # finally appellera stop_browser automatiquement

            await page.wait_for_timeout(random.randint(2000, 4000))

            # ── PHASE 0 : Réponses aux DMs reçus ─────────────────
            nb_rep = await repondre_dms_recus(page)

            # ── PHASE 1 : Rejoindre des groupes (aléatoire) ──────
            deja_rejoints = progress.get("joined_groups", [])
            restants = [(url, priv, top) for (url, priv, top) in GROUPS_TO_JOIN
                        if url not in deja_rejoints]
            if join_count > 0 and restants:
                a_rejoindre = random.sample(restants, min(join_count, len(restants)))
                print(f"[->] Phase 1 : Rejoindre {len(a_rejoindre)} groupe(s) aleatoirement\n", flush=True)
                for invite_url, is_private, topic in a_rejoindre:
                    final_url = await rejoindre_groupe(page, invite_url, is_private)
                    if final_url:
                        if invite_url not in progress["joined_groups"]:
                            progress["joined_groups"].append(invite_url)
                        if is_private:
                            progress.setdefault("private_chat_urls", {})[invite_url] = final_url
                        groups_joined_today += 1
                        save_progress(profile_id, progress)
                        if n_posts > 0:
                            msg = random.choice(GROUP_MESSAGES)
                            await page.wait_for_timeout(random.randint(5000, 10000))
                            inp = await get_real_input(page)
                            if inp:
                                print(f"    [->] Post immediat dans le groupe rejoint...")
                                await type_message(page, inp, msg)
                                print(f"    [OK] Poste !")
                    pause = random.uniform(30, 70)
                    print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                    await asyncio.sleep(pause)

            # ── PHASE 2 : Lecture des chats ───────────────────────
            if n_lect > 0:
                print(f"[->] Phase 2 : Lecture ({n_lect} chats)\n", flush=True)
                read_urls = [f"https://web.telegram.org/k/#@{g}" for g in PUBLIC_GROUPS]
                read_urls.append("https://web.telegram.org/k/#@sfs_france")
                for url in progress.get("private_chat_urls", {}).values():
                    if "web.telegram.org" in url:
                        read_urls.append(url)
                random.shuffle(read_urls)
                for i in range(n_lect):
                    await lire_chat(page, read_urls[i % len(read_urls)])
                    if i < n_lect - 1:
                        pause = random.uniform(20, 55)
                        print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                        await asyncio.sleep(pause)

            # ── PHASE 3 : Posts dans groupes publics (J3+) ────────
            if n_posts > 0:
                print(f"\n[->] Phase 3 : Posts ({n_posts})\n", flush=True)
                pool = PUBLIC_GROUPS.copy()
                random.shuffle(pool)
                posted = 0
                for i, group in enumerate(pool * 3):
                    if posted >= n_posts:
                        break
                    url = f"https://web.telegram.org/k/#@{group}"
                    msg = random.choice(GROUP_MESSAGES)
                    ok  = await poster_dans_groupe(page, url, msg, None)
                    if ok:
                        posted += 1
                    if posted < n_posts:
                        pause = random.uniform(120, 250)
                        print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                        await asyncio.sleep(pause)

            # ── PHASE 4 : DMs non-contacts (J8+) ─────────────────
            if dm_targets:
                print(f"\n[->] Phase 4 : DMs ({len(dm_targets)})\n", flush=True)
                for i, membre in enumerate(dm_targets):
                    username = membre["username"]
                    prenom   = membre.get("prenom") or "toi"
                    ok = await envoyer_dm(page, username, prenom)
                    if ok:
                        progress["dms_sent"].append(username)
                        log_dm(profile_id, username, prenom)
                        dms_ok += 1
                        save_progress(profile_id, progress)
                    if i < len(dm_targets) - 1:
                        pause = random.uniform(90, 160)
                        print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                        await asyncio.sleep(pause)

            # ── Fermeture propre ─────────────────────────────────
            print(f"[->] Fermeture de la page Telegram...", flush=True)
            try:
                await page.goto("about:blank", timeout=5000)
            except Exception:
                pass
            await asyncio.sleep(2)
            # Deconnecte Playwright du navigateur sans tuer le process Chrome
            # AdsPower detectera la deconnexion CDP et pourra fermer proprement
            try:
                await browser.disconnect()
                print(f"[->] Playwright deconnecte du navigateur")
            except Exception as e:
                err = f"Deconnexion Playwright echouee : {e}"
                print(f"[!] {err}")
                session_errors.append(err)
            # Delai important : laisser AdsPower detecter la fin de session CDP
            await asyncio.sleep(4)

    except Exception as e:
        err = f"Erreur session critique : {type(e).__name__} — {e}"
        print(f"[X] {err}")
        session_errors.append(err)

    finally:
        # Stop AdsPower et détecte si ça échoue
        stop_ok = _stop_browser_check(profile_id)
        if not stop_ok:
            session_errors.append("Fermeture AdsPower echouee — profil potentiellement encore ouvert")
        await asyncio.sleep(2)
        print(f"[->] Profil AdsPower ferme ({profile_id})")

    progress["done_today"]    = True
    progress["last_run_date"] = str(date.today())
    progress["posts_total"]   = progress.get("posts_total", 0) + (n_posts if n_posts > 0 else 0)
    save_progress(profile_id, progress)

    # Envoi au dashboard web (avec erreurs si présentes)
    push_to_dashboard(profile_id, progress, {
        "dm_responses":  nb_rep,
        "dms_session":   dms_ok,
        "posts_session": n_posts,
        "last_error":    " | ".join(session_errors) if session_errors else "",
    })

    next_msg = (
        f"→ Reviens demain pour le Jour {day + 1} !"
        if day < 15 else
        "CHAUFFE TERMINÉE pour ce profil !"
    )

    print(f"""
{'='*60}
  PROFIL {profile_num}/{total}  [{profile_id}]  —  JOUR {day}/15 TERMINÉ

  Réponses DMs reçus   : {nb_rep}
  Groupes rejoints auj : {groups_joined_today}  (total {len(progress['joined_groups'])}/16)
  Posts dans groupes   : {n_posts}
  DMs envoyés          : {dms_ok}
  Total DMs depuis J1  : {len(progress.get('dms_sent', []))}

  {next_msg}
{'='*60}
""", flush=True)

    # Pause entre deux profils (2 minutes)
    if profile_num < total:
        pause = random.uniform(120, 140)
        print(f"[->] Pause {pause:.0f}s avant le profil suivant...\n")
        await asyncio.sleep(pause)


# ── Entrée principale ─────────────────────────────────────────

async def main():
    args = sys.argv[1:]

    # ── --status ──────────────────────────────────────────────
    if "--status" in args:
        print_all_status()
        return

    # ── --reset N ─────────────────────────────────────────────
    if "--reset" in args:
        idx = args.index("--reset")
        try:
            n = int(args[idx + 1]) - 1
            pid = ADSPOWER_PROFILES[n]
        except (IndexError, ValueError):
            print("[X] Usage : python warmup_v2.py --reset N  (N = numéro de profil 1-10)")
            return
        path = progress_file(pid)
        if os.path.exists(path):
            os.remove(path)
        print(f"[OK] Progression du profil {n+1} ({pid}) remise à zéro.\n")
        return

    # ── --profile N ───────────────────────────────────────────
    if "--profile" in args:
        idx = args.index("--profile")
        try:
            n = int(args[idx + 1]) - 1
            profiles_to_run = [(n, ADSPOWER_PROFILES[n])]
        except (IndexError, ValueError):
            print("[X] Usage : python warmup_v2.py --profile N  (N = numéro de profil 1-10)")
            return
    else:
        profiles_to_run = list(enumerate(ADSPOWER_PROFILES))

    total = len(profiles_to_run)
    print(f"\n{'='*60}")
    print(f"  WARM-UP MULTI-PROFILS — {total} profil(s) à traiter")
    print(f"  Date : {date.today()}")
    print(f"{'='*60}")

    # Aperçu rapide de ce qui va être fait
    skip = 0
    for i, pid in profiles_to_run:
        data = load_progress(pid)
        day  = data["day"]
        tag  = ""
        if day > 15:
            tag = "  [TERMINÉ]"
        elif data.get("done_today"):
            tag = "  [DÉJÀ FAIT AUJOURD'HUI]"
            skip += 1
        print(f"  Profil {i+1:02d} ({pid}) — Jour {day}/15{tag}")

    if skip == total:
        print("\n[OK] Tous les profils ont déjà été traités aujourd'hui.\n")
        return

    print()
    print("\n[->] Demarrage automatique dans 10 secondes... (Ctrl+C pour annuler)")
    await asyncio.sleep(10)

    for i, pid in profiles_to_run:
        await run_warmup_for_profile(pid, i + 1, total)

    print(f"\n{'='*60}")
    print(f"  TOUS LES PROFILS ONT ETE TRAITES")
    print(f"  Reviens demain pour continuer la chauffe !")
    print(f"{'='*60}\n")

    # ── Auto-lancement Mass DM si tous les profils ont fini J15 ──
    tous_termines = all(
        load_progress(pid).get("day", 1) > 15
        for _, pid in profiles_to_run
    )
    if tous_termines:
        print(f"\n{'='*60}")
        print(f"  CHAUFFE 15 JOURS COMPLETE SUR TOUS LES PROFILS !")
        print(f"  Lancement automatique du script Mass DM...")
        print(f"{'='*60}\n")
        if os.path.exists(MASS_DM_SCRIPT):
            subprocess.Popen(
                [sys.executable, MASS_DM_SCRIPT],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            print(f"[OK] Mass DM lance : {MASS_DM_SCRIPT}")
        else:
            print(f"[!] Script Mass DM introuvable : {MASS_DM_SCRIPT}")
            print(f"[!] Modifie la variable MASS_DM_SCRIPT dans warmup_v2.py")


if __name__ == "__main__":
    asyncio.run(main())
