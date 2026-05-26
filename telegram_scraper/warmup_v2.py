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

# ── Plan Direct DM (sans chauffe — progression du J1 au J7+) ──
DIRECT_DM_LIMITS = {1: 5, 2: 8, 3: 12, 4: 15, 5: 20, 6: 25}
# Jour 7+ → random 28-33

def get_direct_dm_limit(dm_day: int) -> int:
    if dm_day in DIRECT_DM_LIMITS:
        return DIRECT_DM_LIMITS[dm_day]
    return random.randint(28, 33)


def load_direct_dm_templates() -> list:
    """Charge les templates actifs depuis le dashboard pour le mode Direct DM."""
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/dm_templates", timeout=10)
        if r.status_code == 200:
            all_t = r.json()
            active = [t for t in all_t if t.get("active", True)]
            return active
    except Exception as e:
        print(f"[!] Impossible de charger les templates DM : {e}")
    return []


def pick_dm_template(templates: list, session_counts: dict) -> dict | None:
    """Sélectionne le template avec le moins d'envois (round-robin)."""
    if not templates:
        return None
    scores = {t["id"]: t.get("sends", 0) + session_counts.get(t["id"], 0) for t in templates}
    min_score = min(scores.values())
    candidates = [t for t in templates if scores[t["id"]] == min_score]
    return random.choice(candidates)


def report_dm_send(template_id: int):
    """Incrémente le compteur d'envois du template dans le dashboard."""
    try:
        requests.post(
            f"{DASHBOARD_URL}/api/dm_template/stats",
            json={"token": DASHBOARD_TOKEN, "template_id": template_id, "sends": 1, "replies": 0},
            timeout=8,
        )
    except Exception:
        pass

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
        await page.wait_for_timeout(random.randint(1200, 2800))
        # Navigation 2 étapes pour forcer le routeur SPA
        try:
            await page.goto("https://web.telegram.org/k/",
                            wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
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

        # Attendre que la chatlist soit vraiment chargée
        try:
            await page.wait_for_selector("li.chatlist-chat", timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        # Cherche les chats non lus via JS (retourne leurs index dans la liste)
        indices_non_lus = await page.evaluate("""
            () => {
                const items = Array.from(document.querySelectorAll('li.chatlist-chat'));
                const result = [];
                items.forEach((item, idx) => {
                    const badge = item.querySelector('.badge:not(.badge-gray):not(.badge-muted)');
                    if (badge && idx < 8) result.push(idx);
                });
                return result.slice(0, 5);
            }
        """)

        if not indices_non_lus:
            print("    [OK] Aucun DM non lu\n")
            return 0

        print(f"    [->] {len(indices_non_lus)} chat(s) non lu(s)")

        all_chats = page.locator("li.chatlist-chat")

        for idx in indices_non_lus:
            try:
                item = all_chats.nth(idx)

                # Scroll vers l'élément puis clic Playwright (fiable)
                await item.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                await item.click()
                await page.wait_for_timeout(random.randint(1800, 3200))

                inp = await get_real_input(page)
                if not inp:
                    continue

                # Vérifie que c'est bien un DM (pas un groupe → peer_id positif)
                peer_id = await inp.get_attribute("data-peer-id") or ""
                if peer_id.startswith("-"):
                    # C'est un groupe, on passe
                    await page.goto("https://web.telegram.org/k/",
                                    wait_until="domcontentloaded", timeout=10000)
                    await page.wait_for_timeout(2000)
                    continue

                reponse = random.choice(DM_RESPONSES)
                print(f"    [->] Reponse : '{reponse}'")
                await type_message(page, inp, reponse)
                reponses += 1
                await page.wait_for_timeout(random.randint(12000, 25000))

                # Retour à la liste pour le prochain
                await page.goto("https://web.telegram.org/k/",
                                wait_until="domcontentloaded", timeout=10000)
                await page.wait_for_timeout(2500)

            except Exception as e:
                print(f"    [X] Erreur reponse : {e}")

    except Exception as e:
        print(f"    [X] Erreur verif DMs : {e}")

    print(f"    [OK] {reponses} reponse(s) envoyee(s)\n")
    return reponses


async def envoyer_dm_template(page, username: str, prenom: str, message: str, message2: str = "") -> bool:
    """Envoie un DM avec le texte du template (pour le mode Direct DM)."""
    print(f"    [->] DM template à @{username}...")
    try:
        await page.bring_to_front()
        await page.wait_for_timeout(random.randint(1000, 2000))

        # ── Étape 1 : base URL pour réinitialiser le routeur SPA ──
        try:
            await page.goto("https://web.telegram.org/k/",
                            wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        # Attendre que la chatlist soit prête (SPA initialisé)
        try:
            await page.wait_for_selector("li.chatlist-chat, .chatlist", timeout=8000)
        except Exception:
            pass
        await page.wait_for_timeout(1500)

        # ── Étape 2 : navigation vers le profil ───────────────────
        target_url = f"https://web.telegram.org/k/#@{username}"
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)

        # ── Vérification critique : sommes-nous bien chez @{username} ? ──
        # Si Telegram n'a pas trouvé l'user, l'URL revient à la base
        # et la conversation précédente reste ouverte → on enverrait au mauvais
        current_url = page.url
        if f"@{username}" not in current_url:
            # Deuxième tentative via la barre de recherche
            try:
                # Clique sur la loupe / barre de recherche
                for search_sel in [".btn-icon.sidebar-left-section-content", "button.btn-icon[class*='search']", ".search-input"]:
                    try:
                        s = page.locator(search_sel).first
                        if await s.is_visible(timeout=1500):
                            await s.click()
                            break
                    except Exception:
                        pass
                await page.wait_for_timeout(800)
                # Tape le username dans la recherche
                await page.keyboard.type(f"@{username}", delay=60)
                await page.wait_for_timeout(2000)
                # Clique sur le premier résultat
                first_result = page.locator(".chatlist-chat, .search-group-peer").first
                if await first_result.is_visible(timeout=3000):
                    await first_result.click()
                    await page.wait_for_timeout(1500)
                else:
                    # Personne trouvé → ferme la recherche et skip
                    await page.keyboard.press("Escape")
                    print(f"    [--] @{username} introuvable via URL et recherche")
                    return False
            except Exception:
                print(f"    [--] @{username} introuvable")
                return False

        # ── Bouton "Démarrer" si première conversation ─────────────
        for sel in ["button.btn-primary", ".start-bot-button"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        # ── Attente du vrai input (retry jusqu'à 16s) ─────────────
        real_input = None
        for attempt in range(4):
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
                        print(f"    [--] @{username} DMs bloqués (confidentialité)")
                        return False
                    if ce == "true":
                        real_input = el
                        break
            except Exception:
                pass

            if real_input:
                break
            if attempt < 3:
                await page.wait_for_timeout(4000)

        if not real_input:
            print(f"    [--] @{username} introuvable (profil privé ou inexistant)")
            return False

        # ── Envoi du 1er message ───────────────────────────────────
        await type_message(page, real_input, message)

        # ── 2ème message si configuré ──────────────────────────────
        if message2.strip():
            delay2 = random.uniform(5, 18)
            print(f"    [->] 2ème message dans {delay2:.0f}s...")
            await page.wait_for_timeout(int(delay2 * 1000))
            inp2 = await get_real_input(page)
            if inp2:
                await type_message(page, inp2, message2)

        print(f"    [OK] DM template envoyé à {prenom} (@{username})")
        return True

    except Exception as e:
        print(f"    [X] Erreur DM template @{username} : {e}")
        return False


async def envoyer_dm(page, username: str, prenom: str) -> bool:
    print(f"    [->] DM à @{username}...")
    try:
        await page.bring_to_front()
        await page.wait_for_timeout(random.randint(1500, 3000))
        # Navigation 2 étapes pour forcer le routeur SPA
        try:
            await page.goto("https://web.telegram.org/k/",
                            wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        await page.goto(
            f"https://web.telegram.org/k/#@{username}",
            wait_until="domcontentloaded", timeout=20000,
        )
        try:
            await page.wait_for_selector(
                "div.input-message-input, .empty-peer-placeholder",
                timeout=12000
            )
        except Exception:
            pass
        await page.wait_for_timeout(random.randint(1500, 3000))

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

async def run_direct_dm_for_profile(profile_id: str, profile_num: int, total: int, current_dm_day: int):
    """Mode Direct DM : saute la chauffe, envoie des DMs avec templates progressifs."""

    dm_day  = current_dm_day + 1
    max_dms = get_direct_dm_limit(dm_day)
    bar_dm  = "⚡" * min(dm_day, 7) + "·" * max(0, 7 - dm_day)

    print(f"\n{'='*60}", flush=True)
    print(f"  PROFIL [{profile_num}/{total}]  ID: {profile_id}", flush=True)
    print(f"  ⚡ MODE DIRECT DM — Jour {dm_day}  [{bar_dm}]", flush=True)
    print(f"  Limite aujourd'hui : {max_dms} DMs", flush=True)
    print(f"{'='*60}", flush=True)

    # Charge les templates
    templates = load_direct_dm_templates()
    if not templates:
        print(f"  [!] Aucun template configuré sur le dashboard — session annulée")
        print(f"      → Va sur le dashboard onglet Mass DM pour créer des templates")
        return

    print(f"  [OK] {len(templates)} template(s) A/B chargé(s)")

    # Prépare les cibles DM
    if not os.path.exists(DM_CSV):
        print(f"  [!] Fichier membres introuvable : {DM_CSV}")
        print(f"      → Lance scraper.py d'abord")
        return

    progress = load_progress(profile_id)
    already  = load_already_dmed(profile_id) | set(progress.get("dms_sent", []))

    with open(DM_CSV, newline="", encoding="utf-8-sig") as f:
        import csv as csv_mod
        members = list(csv_mod.DictReader(f))

    candidates = [m for m in members
                  if m.get("username") and m.get("bot") != "Oui"
                  and m["username"] not in already]

    if not candidates:
        print(f"  [OK] Plus personne à contacter pour ce profil.")
        return

    dm_targets     = random.sample(candidates, min(max_dms, len(candidates)))
    session_counts = {}
    session_errors = []

    # Démarrage AdsPower
    try:
        print(f"[->] Démarrage du navigateur AdsPower ({profile_id})...", flush=True)
        cdp_url = start_browser(profile_id)
    except Exception as e:
        print(f"[X] Démarrage échoué : {e}\n")
        return

    dms_ok = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            page    = context.pages[0] if context.pages else await context.new_page()

            await page.bring_to_front()

            # Attend Telegram Web
            for _ in range(15):
                if "web.telegram.org" in page.url:
                    break
                await page.wait_for_timeout(1000)

            if "web.telegram.org" not in page.url:
                try:
                    await page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass

            telegram_ok = False
            for _ in range(20):
                try:
                    ok = await page.locator(".chatlist-chat, .chat-list").first.is_visible(timeout=1500)
                    if ok:
                        telegram_ok = True
                        break
                except Exception:
                    pass
                await page.wait_for_timeout(1000)

            if not telegram_ok:
                print(f"  [X] Telegram non connecté sur ce profil — session annulée")
                session_errors.append("Telegram non connecte")
            else:
                print(f"\n[->] ⚡ Direct DM — envoi de {len(dm_targets)} message(s)\n", flush=True)

                for i, membre in enumerate(dm_targets, 1):
                    username = membre["username"]
                    prenom   = membre.get("prenom") or "toi"

                    # Sélection du template (round-robin)
                    tmpl = pick_dm_template(templates, session_counts)
                    if not tmpl:
                        continue

                    texte  = tmpl["content"].replace("{prenom}", prenom)
                    texte2 = (tmpl.get("content2") or "").strip().replace("{prenom}", prenom)

                    ok = await envoyer_dm_template(page, username, prenom, texte, texte2)
                    if ok:
                        progress["dms_sent"].append(username)
                        log_dm(profile_id, username, prenom)
                        session_counts[tmpl["id"]] = session_counts.get(tmpl["id"], 0) + 1
                        report_dm_send(tmpl["id"])
                        dms_ok += 1
                        save_progress(profile_id, progress)

                    if i < len(dm_targets):
                        pause = random.uniform(10, 22)
                        await asyncio.sleep(pause)

            # Fermeture
            try:
                await page.goto("about:blank", timeout=5000)
            except Exception:
                pass
            await asyncio.sleep(2)
            try:
                await browser.disconnect()
            except Exception as e:
                session_errors.append(f"Deconnexion Playwright echouee : {e}")
            await asyncio.sleep(4)

    except Exception as e:
        err = f"Erreur session critique : {type(e).__name__} — {e}"
        print(f"[X] {err}")
        session_errors.append(err)
    finally:
        stop_ok = _stop_browser_check(profile_id)
        if not stop_ok:
            session_errors.append("Fermeture AdsPower echouee")
        await asyncio.sleep(2)

    # Met à jour le dm_day dans le dashboard
    try:
        requests.post(f"{DASHBOARD_URL}/api/update", json={
            "token":      DASHBOARD_TOKEN,
            "profile_id": profile_id,
            "day":        1,   # warm-up day ne change pas
            "done_today": True,
            "dms_total":  len(progress.get("dms_sent", [])),
            "posts_total": 0,
            "groups_joined": 0,
            "dm_responses":  0,
            "dms_session":   dms_ok,
            "posts_session": 0,
            "last_error":    " | ".join(session_errors) if session_errors else "",
            "dm_day":        dm_day,
        }, timeout=30)
    except Exception as e:
        print(f"[!] Dashboard non joignable : {e}")

    next_limit = get_direct_dm_limit(dm_day + 1)
    print(f"""
{'='*60}
  ⚡ DIRECT DM  [{profile_id}]  —  Jour {dm_day} terminé

  DMs envoyés aujourd'hui  : {dms_ok}
  Total DMs toutes sessions: {len(progress.get('dms_sent', []))}
  Demain (Jour {dm_day+1})         : {next_limit} DMs max
{'='*60}
""", flush=True)

    if profile_num < total:
        pause = random.uniform(90, 130)
        print(f"[->] Pause {pause:.0f}s avant le profil suivant...\n")
        await asyncio.sleep(pause)


async def run_warmup_for_profile(profile_id: str, profile_num: int, total: int):
    """Lance la session du jour pour un profil AdsPower donné."""

    # ── Récupère le mode du profil depuis le dashboard ────────
    dm_mode = "warmup"
    dm_day  = 0
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/status", timeout=10)
        if r.status_code == 200:
            all_data = r.json()
            if profile_id in all_data:
                dm_mode = all_data[profile_id].get("dm_mode", "warmup") or "warmup"
                dm_day  = int(all_data[profile_id].get("dm_day", 0) or 0)
    except Exception:
        pass

    # ════════════════════════════════════════════════════════
    #  MODE DIRECT DM — saute la chauffe, envoie des DMs
    # ════════════════════════════════════════════════════════
    if dm_mode == "direct_dm":
        return await run_direct_dm_for_profile(profile_id, profile_num, total, dm_day)

    # ════════════════════════════════════════════════════════
    #  MODE WARM-UP (normal)
    # ════════════════════════════════════════════════════════
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

async def main(force: bool = False):
    """
    force=True : ignore done_today → relance même si déjà fait aujourd'hui
    (utilisé quand le bouton dashboard est cliqué)
    """
    args = [a for a in sys.argv[1:] if a not in ("--daemon", "--auto")]

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

    # Récupère les modes depuis le dashboard (pour détecter direct_dm)
    dash_modes = {}
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/status", timeout=10)
        if r.status_code == 200:
            dash_modes = r.json()
    except Exception:
        pass

    # Aperçu rapide de ce qui va être fait
    skip = 0
    for i, pid in profiles_to_run:
        data    = load_progress(pid)
        day     = data["day"]
        dm_mode = (dash_modes.get(pid) or {}).get("dm_mode", "warmup")
        tag     = ""
        if dm_mode == "direct_dm":
            dm_day_cur = int((dash_modes.get(pid) or {}).get("dm_day", 0) or 0)
            tag = f"  [⚡ DIRECT DM — J{dm_day_cur + 1}]"
            # Ne pas compter dans skip : les direct_dm doivent toujours tourner
        elif day > 15:
            tag = "  [TERMINÉ]"
        elif data.get("done_today"):
            tag = "  [DÉJÀ FAIT AUJOURD'HUI]"
            skip += 1
        print(f"  Profil {i+1:02d} ({pid}) — Jour {day}/15{tag}")

    if skip == total and not force:
        print("\n[OK] Tous les profils ont déjà été traités aujourd'hui.\n")
        return
    elif skip == total and force:
        print("\n[▶] Force=True — relance même si déjà fait aujourd'hui.\n")
        # Remet done_today à False pour que run_warmup_for_profile reparte
        for _, pid in profiles_to_run:
            data = load_progress(pid)
            if data.get("done_today"):
                data["done_today"] = False
                save_progress(pid, data)

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


SUPABASE_URL = "https://pirlgavzihmnwmqlyeir.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBpcmxnYXZ6aWhtbndtcWx5ZWlyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3MzQxMTAsImV4cCI6MjA5NTMxMDExMH0.0QdskD9IBsx1rUZ_7Sljb8DshovkQMJIhmnAM-Zc6Ps"
SUPABASE_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
}

def check_warmup_trigger() -> bool:
    """
    Interroge Supabase DIRECTEMENT (pas via Render) — 100% fiable.
    Cherche une ligne channels avec url='__warmup_trigger__' et status='triggered'.
    Si trouvée → reset à 'done' et retourne True.
    """
    try:
        # Cherche le trigger
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/channels",
            headers=SUPABASE_HEADERS,
            params={"url": "eq.__warmup_trigger__", "select": "id,status"},
            timeout=8,
        )
        rows = r.json() if r.status_code == 200 else []
        triggered_rows = [row for row in rows if row.get("status") == "triggered"]
        if triggered_rows:
            # Reset le trigger
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/channels",
                headers=SUPABASE_HEADERS,
                params={"url": "eq.__warmup_trigger__"},
                json={"status": "done"},
                timeout=8,
            )
            return True
    except Exception as e:
        log(f"[!] check_warmup_trigger erreur : {e}")
    return False


LOG_FILE = os.path.join(os.path.dirname(__file__), "output", "daemon_warmup.log")

def log(msg: str):
    """Écrit dans le fichier log ET affiche dans le terminal."""
    from datetime import datetime as _dt
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


async def daemon():
    """
    Mode daemon — tourne en continu.
    - Poll le dashboard toutes les 30s
    - Lance le warm-up dès que le bouton 'Lancer' est cliqué (force=True)
    """
    log("=" * 50)
    log("WARM-UP DAEMON démarré — poll toutes les 30s")
    log(f"Log : {LOG_FILE}")
    log("=" * 50)

    while True:
        try:
            triggered = check_warmup_trigger()
        except Exception as e:
            log(f"[!] Erreur poll : {e}")
            triggered = False

        if triggered:
            log("[▶] Signal reçu ! Ouverture d'un terminal visible...")
            try:
                # Lance warmup_v2.py dans un NOUVEAU terminal visible
                subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__)],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                log("[OK] Terminal warm-up ouvert.")
            except Exception as e:
                log(f"[!] Erreur lancement terminal : {e}")
            log("[·] Retour en veille...")
        else:
            log(f"[·] En attente du bouton dashboard...")

        await asyncio.sleep(30)


if __name__ == "__main__":
    # Si lancé avec --daemon (ou via start_all.vbs), mode daemon
    if "--daemon" in sys.argv or "--auto" in sys.argv:
        from datetime import datetime
        asyncio.run(daemon())
    else:
        asyncio.run(main())
