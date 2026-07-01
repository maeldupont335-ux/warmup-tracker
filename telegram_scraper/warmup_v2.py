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

# Chemin absolu du dossier du script (stable peu importe le répertoire de lancement)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
DM_CSV       = os.path.join(BASE_DIR, "output", "membres.csv")

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
    # ── Canaux pour poster les annonces ─────────────────────
    ("https://t.me/+45MKai9c7jU1ZGI8",    True,  None),
    ("https://t.me/chattersventure",       False, None),
    ("https://t.me/jobonlinevas",          False, None),
    ("https://t.me/OFMnetworkfrance",      False, None),
    ("https://t.me/StoneServiceBoard",     False, None),
    ("https://t.me/+WVdLZnUpgtpkNDM6",    True,  None),
    # ── Canaux à rejoindre + lire (sans poster) ──────────────
    ("https://t.me/+oQuSGKfMVB00YTQ0",    True,  None),
    ("https://t.me/enzo200k",              False, None),
    ("https://link.me/cassandrabq",        False, None),
    ("https://t.me/rickyvouch",            False, None),
    ("https://t.me/ferrettiofm",           False, None),
    ("https://t.me/evoempire",             False, None),
    ("https://t.me/promotiononlyfans",     False, None),
]

# Groupes publics pour POSTER les annonces
PUBLIC_GROUPS = [
    "ofmva_fr", "fraofm", "OFstarters", "noahofmfr",
    "ofmanagementgroupe", "OFMNetworkgroup", "richclubofm",
    "ofmglobalnetworkgroup", "shaftofmjobs", "parismodels_ofm",
    "elisaflamex", "cupidbotg", "roroivx", "TheValere",
    "chattersventure", "jobonlinevas", "OFMnetworkfrance", "StoneServiceBoard",
]

# Groupes publics pour la LECTURE UNIQUEMENT (pas de post d'annonces)
READ_ONLY_GROUPS = [
    "enzo200k", "cassandrabq", "rickyvouch",
    "ferrettiofm", "evoempire", "promotiononlyfans",
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
        "🚨 NOUS RECRUTONS DES VA X (Twitter) 🚨\n\n"
        "Débutants motivés ou profils expérimentés bienvenus\n"
        "(Africains et Malgaches 🇲🇬 de préférence)\n\n"
        "AVANTAGES :\n"
        "💵 Salaire fixe évolutif\n"
        "▶️ Formation complète + accompagnement\n"
        "⭐️ Possibilité d'évolution rapide vers un poste de manager\n"
        "📈 Collaboration sérieuse sur le long terme\n\n"
        "PROFIL RECHERCHÉ :\n"
        "✔️ Smartphone récent obligatoire (iPhone fortement recommandé)\n"
        "📶 Bonne connexion internet\n"
        "⌛ Disponible plusieurs heures par jour\n"
        "🔥 Motivé, discipliné et capable de suivre des consignes précises\n\n"
        "👉🏻 Si tu es débutant mais sérieux et capable d'appliquer exactement les recommandations, tu peux postuler.\n\n"
        "👉🏻 Si tu as déjà de l'expérience, merci d'envoyer uniquement des résultats ou preuves concrètes de ton travail.\n"
        "Ne perds pas ton temps ni le nôtre sans ça.\n\n"
        "🎤 Envoie un vocal obligatoire avec :\n"
        "— le modèle de ton téléphone\n"
        "— ta présentation\n"
        "— tes expériences éventuelles"
    ),
    (
        "🚀 NOUS RECRUTONS DES CHATTER FRANCOPHONES 🇲🇬🇫🇷\n\n"
        "Nous recherchons des personnes sérieuses, motivées et disponibles pour rejoindre notre équipe de chatters.\n\n"
        "✅ Expérience obligatoire\n"
        "✅ Rémunération attractive : jusqu'à 15% selon les performances + primes de performance\n"
        "✅ Possibilité d'évolution rapide (Team Leader, Manager, etc.)\n"
        "✅ Travail sur Grindr et Fanvue\n\n"
        "📅 Activité 7j/7 — 24h/24\n\n"
        "🕒 Créneaux disponibles :\n"
        "• 02h → 08h\n"
        "• 08h → 14h\n"
        "• 14h → 20h\n"
        "• 20h → 02h\n\n"
        "⚠️ Conditions requises :\n"
        "• Malgache uniquement\n"
        "• Bonne connexion internet\n"
        "• Sérieux et assiduité\n"
        "• Français irréprochable\n"
        "• Disponibilité minimum 6 jours par semaine\n\n"
        "📩 Si tu es intéressé(e), merci de m'envoyer une présentation en vocal."
    ),
    (
        "Recrutement chatter\n\n"
        "Nous recherchons des chatteurs pour discuter avec nos modèles françaises.\n"
        "💻 Job : Chatteur\n"
        "💰 Rémunération : 12% sur toutes les ventes + primes\n"
        "💵 Salaire : Toutes les 2 semaines en crypto\n\n"
        "⏰ Shift (Heure France) :\n\n"
        "• 10h-18h\n"
        "• 18h-02h\n"
        "• 02h-10h\n\n"
        "Conditions ✅ :\n"
        "- Maîtrise de la langue française (oral et écrit)\n"
        "- Expérience préalable en chatting\n"
        "- Vitesse de frappe au clavier rapide\n"
        "- À l'aise avec l'utilisation d'un ordinateur\n"
        "- Ponctuel(le) et sérieux"
    ),
    (
        "🚨 HIRING ONLYFANS CHATTERS 🚨\n\n"
        "💰 High earning opportunity\n"
        "🔥 Serious sellers ONLY\n\n"
        "✅ 1–2+ years OF chatting experience\n"
        "✅ Proven sales/results\n"
        "✅ Fluent English\n"
        "✅ Reliable & consistent\n"
        "✅ Able to work fast-paced shifts\n\n"
        "🧪 ALL applicants will be tested before joining.\n\n"
        "🚫 Don't apply if you only have a few months experience or can't commit consistently.\n\n"
        "📩 DM with your experience + sales proof."
    ),
    (
        "Bonjour, il y a des agences mym avec des modèles payants qui recherchent un chatteur ici ? "
        "Je suis dispo pour un shift matin 8h-13h"
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
    (
        "📱 RECRUTEMENT VA INSTAGRAM 📱\n\n"
        "💎 OUVERT À TOUS ! 💎\n\n"
        "Nous recrutons des Assistants pour gérer et développer des comptes Instagram sur le marché Français 🇫🇷.\n\n"
        "📌 Missions\n"
        "• Gérer 2 comptes Instagram\n"
        "• Poster des Réels et stories CTA tous les jours\n\n"
        "⚙️ Conditions\n"
        "• ⏱ Environ 15-20 minutes / jour\n"
        "• 📆 Disponible TOUS les jours\n"
        "• 📲 Avoir un téléphone\n\n"
        "🎯 Profil\n"
        "• Sérieux, régulier, autonome\n"
        "• À l'aise avec Instagram\n\n"
        "💰 Rémunération\n"
        "• Payé au résultat selon les performances du compte :\n"
        "clics / performances / subs des comptes\n"
        "(jusqu'à 1000€ / mois / compte)\n\n"
        "• 📈 Évolution rapide en manager selon performances."
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
    1:  (3, 0, 0),   2:  (3, 0, 0),   3:  (3, 3, 0),
    4:  (3, 3, 0),   5:  (4, 3, 0),   6:  (3, 3, 0),
    7:  (4, 3, 0),   8:  (3, 3, 1),   9:  (4, 3, 2),
    10: (3, 3, 3),   11: (4, 3, 4),   12: (3, 3, 5),
    13: (4, 3, 6),   14: (3, 3, 8),   15: (4, 3, 10),
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


# ── Détection de genre par prénom (gender-guesser) ────────────
# pip install gender-guesser
try:
    import gender_guesser.detector as _gg
    _gd = _gg.Detector(case_sensitive=False)
    _GENDER_LIB = True
except ImportError:
    _GENDER_LIB = False
    print("[!] gender-guesser non installé — lance : pip install gender-guesser")

def detecter_genre(prenom: str) -> str:
    """
    Retourne 'M' (masculin), 'F' (féminin), ou '?' (inconnu/ambigu).
    Utilise gender-guesser (~48 000 prénoms mondiaux dont français/arabes).
    """
    if not prenom or not prenom.strip():
        return "?"
    if _GENDER_LIB:
        r = _gd.get_gender(prenom.strip())
        # male / mostly_male → M
        if r in ("male", "mostly_male"):
            return "M"
        # female / mostly_female → F
        if r in ("female", "mostly_female"):
            return "F"
        # andy (ambigu) ou unknown → ?
        return "?"
    # Fallback minimal si lib absente
    return "?"


def load_massdm_settings() -> dict:
    """Charge les paramètres Mass DM depuis le dashboard (filtre genre, etc.)."""
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/massdm/settings", timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {"genre_filter": "tous"}


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
    return os.path.join(BASE_DIR, "output", f"warmup_progress_{profile_id}.json")

def dm_log_file(profile_id: str) -> str:
    return os.path.join(BASE_DIR, "output", f"dm_log_{profile_id}.csv")

# Log partagé entre tous les profils — garantit qu'un membre ne reçoit qu'1 seul DM
DM_LOG_SHARED = os.path.join(BASE_DIR, "output", "dm_log_shared.csv")


# ── Gestion de la progression ─────────────────────────────────

def load_progress(profile_id: str) -> dict:
    path = progress_file(profile_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        last = data.get("last_run_date")
        # Avance au jour suivant dès qu'une nouvelle date est détectée,
        # même si la session précédente a été interrompue (done_today ignoré).
        # On met à jour last_run_date ICI pour éviter d'incrémenter plusieurs
        # fois le même jour si la session crashe avant la fin.
        if last and last != str(date.today()):
            data["day"] += 1
            data["done_today"] = False
            data["last_run_date"] = str(date.today())
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
    os.makedirs(os.path.join(BASE_DIR, "output"), exist_ok=True)
    with open(progress_file(profile_id), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_already_dmed(profile_id: str) -> set:
    """Retourne les usernames déjà contactés — log individuel ET log partagé.
    Un membre présent dans l'un OU l'autre est considéré déjà traité.
    → Garantit qu'aucun membre ne reçoit plus d'1 DM au total."""
    sent = set()
    # 1. Log individuel du profil
    path = dm_log_file(profile_id)
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("statut") == "envoye":
                    sent.add(row.get("username", ""))
    # 2. Log partagé (tous profils confondus)
    if os.path.exists(DM_LOG_SHARED):
        with open(DM_LOG_SHARED, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("statut") == "envoye":
                    sent.add(row.get("username", ""))
    return sent


def log_dm(profile_id: str, username: str, prenom: str, template_name: str = ""):
    """Enregistre le DM dans le log individuel ET dans le log partagé.
    template_name : nom du template utilisé (ex: 'MESSAGE 1') pour le tracking A/B."""
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs("output", exist_ok=True)

    # 1. Log individuel du profil
    path = dm_log_file(profile_id)
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["username", "prenom", "statut", "template", "heure"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({"username": username, "prenom": prenom,
                         "statut": "envoye", "template": template_name, "heure": now_str})

    # 2. Log partagé — inclut profile_id + template pour traçabilité A/B
    shared_exists = os.path.exists(DM_LOG_SHARED)
    with open(DM_LOG_SHARED, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["profile_id", "username", "prenom", "statut", "template", "heure"])
        if not shared_exists:
            writer.writeheader()
        writer.writerow({"profile_id": profile_id, "username": username, "prenom": prenom,
                         "statut": "envoye", "template": template_name, "heure": now_str})


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

    # ── Vérifier si le message a échoué (icône rouge Telegram) ──
    failed = await page.evaluate("""
        () => {
            // Sélecteurs connus pour les messages échoués dans Telegram Web K
            const FAIL_SELS = [
                '.message.failed',
                '.message.is-failed',
                '[class*="message"][class*="failed"]',
                '.tgico-msg-failed',
                '.icon-msg-failed',
                '.message-status-error',
                'i.tgico-msgfailed',
            ];
            for (const sel of FAIL_SELS) {
                if (document.querySelector(sel)) return sel;
            }
            // Chercher le dernier message avec statut d'erreur
            const msgs = document.querySelectorAll('.bubble.is-out, .message.is-out');
            if (msgs.length > 0) {
                const last = msgs[msgs.length - 1];
                if (last.classList.contains('failed') || last.classList.contains('is-failed')) {
                    return 'last-message-failed';
                }
            }
            return null;
        }
    """)
    if failed:
        raise Exception(f"Message non envoyé (Telegram: {failed})")


# ── Actions Telegram ──────────────────────────────────────────

async def _click_request_to_join(page) -> bool:
    """
    Détecte et clique le bouton 'REQUEST TO JOIN' / 'Send Request' si un popup
    de canal privé (approbation admin requise) est visible.
    Retourne True si le bouton a été cliqué.
    """
    # Textes exacts possibles (Telegram peut varier selon la langue/version)
    request_texts = [
        "REQUEST TO JOIN", "Request to Join", "request to join",
        "SEND REQUEST", "Send Request", "Send request",
        "Demander à rejoindre", "Envoyer une demande", "DEMANDER",
        "Apply to Join", "APPLY TO JOIN",
    ]
    for txt in request_texts:
        try:
            btn = page.get_by_text(txt, exact=True).first
            if await btn.is_visible(timeout=600):
                await btn.click(force=True)
                await page.wait_for_timeout(2500)
                print(f"    [OK] Demande d'adhésion envoyée ('{txt}')", flush=True)
                return True
        except Exception:
            continue
    # Scan JS large : cherche les boutons/liens dont le texte contient "request" ou "join"
    # mais qui sont dans un popup/dialog (élément flottant au-dessus de la page)
    clicked = await page.evaluate("""
        () => {
            const popupSels = [
                '.popup', '.dialog', '.alert', '.confirm-dialog',
                '.popup-confirmation', '[class*="popup"]', '[class*="dialog"]',
            ];
            const words = ['request', 'request to join', 'send request', 'apply'];
            for (const sel of popupSels) {
                const popup = document.querySelector(sel);
                if (!popup || popup.offsetParent === null) continue;
                const btns = popup.querySelectorAll('button, .btn, .btn-primary, a.btn');
                for (const btn of btns) {
                    const txt = (btn.innerText || btn.textContent || '').toLowerCase().trim();
                    if (words.some(w => txt.includes(w))) {
                        btn.click();
                        return txt;
                    }
                }
            }
            return null;
        }
    """)
    if clicked:
        await page.wait_for_timeout(2500)
        print(f"    [OK] Popup 'Request to Join' cliqué via JS : '{clicked}'", flush=True)
        return True
    return False


async def rejoindre_groupe(page, invite_url: str, is_private: bool) -> str | None:
    print(f"    [->] Rejoindre : {invite_url[:55]}...")
    try:
        # Amène la fenêtre au premier plan pour que l'action soit visible
        await page.bring_to_front()
        # Délai humain avant de naviguer
        await page.wait_for_timeout(random.randint(800, 1800))

        # ── Extraction username (canaux publics) ─────────────────
        username = ""
        if not is_private:
            if "t.me/" in invite_url:
                username = invite_url.split("t.me/")[-1].rstrip("/").split("/")[0]
            elif invite_url.startswith("@"):
                username = invite_url[1:]
            else:
                username = invite_url

        if is_private:
            # ── Canal privé : tg:// link via Telegram Web K ───────
            hash_part = invite_url.split("+")[-1].rstrip("/")
            tg_link   = f"tg://join?invite={hash_part}"
            encoded   = urllib.parse.quote(tg_link, safe="")
            web_url   = f"https://web.telegram.org/k/#?tgaddr={encoded}"
            try:
                await page.goto("https://web.telegram.org/k/",
                                wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass
            await page.wait_for_timeout(1200)
            try:
                await page.goto(web_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
            await page.wait_for_timeout(random.randint(1500, 2500))

        else:
            # ── Canal public : page preview t.me → bouton "A K Web" ──
            # Étape 1 : ouvrir la page preview sur t.me
            print(f"    [->] Chargement page preview : {invite_url}")
            try:
                await page.goto(invite_url, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass
            await page.wait_for_timeout(random.randint(1200, 2200))

            cur = page.url

            # Étape 2 : sur la page t.me, cliquer le lien "A K Web"
            # (c'est le bouton qui redirige vers web.telegram.org/k/#@username)
            web_k_clicked = False

            if "t.me" in cur or "telegram.me" in cur:
                print(f"    [->] Page preview chargée — recherche bouton Web K...")

                # Méthode 1 : lien direct vers web.telegram.org/k
                try:
                    web_link = page.locator("a[href*='web.telegram.org/k']").first
                    if await web_link.is_visible(timeout=3000):
                        href = await web_link.get_attribute("href") or ""
                        print(f"    [->] Bouton Web K trouvé, clic...")
                        await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                        await page.wait_for_timeout(random.randint(1500, 2500))
                        web_k_clicked = True
                except Exception:
                    pass

                # Méthode 2 : tous les <a> dont href pointe vers web.telegram.org
                if not web_k_clicked:
                    try:
                        all_links = page.locator("a")
                        cnt = await all_links.count()
                        for i in range(cnt):
                            lnk = all_links.nth(i)
                            try:
                                href = (await lnk.get_attribute("href") or "")
                                if "web.telegram.org" in href:
                                    print(f"    [->] Lien Web Telegram trouvé : {href[:60]}")
                                    await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                                    await page.wait_for_timeout(random.randint(3000, 5000))
                                    web_k_clicked = True
                                    break
                            except Exception:
                                pass
                    except Exception:
                        pass

                if not web_k_clicked:
                    print(f"    [!] Bouton Web K non trouvé sur page preview — fallback direct")

            # Étape 3 (fallback) : navigation directe web.telegram.org/k/#@username
            if not web_k_clicked:
                web_url = f"https://web.telegram.org/k/#@{username}"
                try:
                    await page.goto("https://web.telegram.org/k/",
                                    wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass
                await page.wait_for_timeout(1200)
                try:
                    await page.goto(web_url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass
                await page.wait_for_timeout(random.randint(1500, 2500))

            # Vérification que Telegram Web K est bien chargé
            for _att in range(3):
                if "web.telegram.org" not in page.url:
                    print(f"    [!] Pas sur web.telegram.org — retry...")
                    web_url = f"https://web.telegram.org/k/#@{username}"
                    try:
                        await page.goto(web_url,
                                        wait_until="domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(1500)
                else:
                    break

            if "web.telegram.org" not in page.url:
                print(f"    [X] Impossible d'atteindre Telegram Web K pour {username}")
                return None

        joined = False

        # ── Vérification anticipée : popup "Request to Join" ─────
        # Ce popup peut apparaître immédiatement après la navigation vers
        # un canal qui requiert l'approbation d'un admin.
        if await _click_request_to_join(page):
            joined = True

        # Attente supplementaire pour que la page finisse de rendre
        await page.wait_for_timeout(1200)

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
                        await page.wait_for_timeout(1500)
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
                            await page.wait_for_timeout(1500)
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
                    await page.wait_for_timeout(1500)
                    joined = True
                    print(f"    [OK] Bouton clique via JS : '{clicked}'")
            except Exception:
                pass

        # Fallback 3 : retry tardif — le popup "Request to Join" peut apparaître
        # avec retard (ex: après chargement du profil du canal)
        if not joined:
            print(f"    [i] Aucun bouton trouvé — attente 3s pour popup tardif...", flush=True)
            await page.wait_for_timeout(3000)
            if await _click_request_to_join(page):
                joined = True

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


def _username_from_url(url: str) -> str:
    """Extrait le @username depuis une URL Telegram (t.me/x ou web.telegram.org/k/#@x)."""
    if "#@" in url:
        return url.split("#@")[-1].rstrip("/").split("/")[0]
    if "t.me/" in url:
        return url.split("t.me/")[-1].lstrip("+").rstrip("/").split("/")[0]
    if url.startswith("@"):
        return url[1:]
    return url.split("#")[-1].lstrip("@").rstrip("/")


async def _ouvrir_via_tme(page, username: str) -> bool:
    """
    Ouvre un canal Telegram en collant l'URL t.me/username dans la barre d'adresse
    (comme si on tapait le lien directement dans Google/Chrome).
    Trouve le bouton 'A K Web' (lien web.telegram.org/k) et navigue dessus.
    Retourne True si Telegram Web K est bien ouvert.
    """
    tme_url = f"https://t.me/{username}"
    print(f"    [->] Navigation directe : {tme_url}")
    try:
        await page.goto(tme_url, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pass
    await page.wait_for_timeout(random.randint(2500, 4000))

    web_k_clicked = False
    cur = page.url

    # ── Si on est déjà retombé sur web.telegram.org (redirection auto) ──────
    if "web.telegram.org" in cur:
        print(f"    [->] Redirigé automatiquement vers Telegram Web K")
        return True

    if "t.me" in cur or "telegram.me" in cur:
        # Méthode 1 : attribut href exact vers web.telegram.org/k
        try:
            web_link = page.locator("a[href*='web.telegram.org/k']").first
            if await web_link.is_visible(timeout=3000):
                href = await web_link.get_attribute("href") or ""
                if href:
                    print(f"    [->] Bouton Web K trouvé — clic...")
                    await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(random.randint(2500, 4000))
                    web_k_clicked = True
        except Exception:
            pass

        # Méthode 2 : scan tous les <a> dont le href contient web.telegram.org
        if not web_k_clicked:
            try:
                all_links = page.locator("a")
                cnt = await all_links.count()
                for i in range(cnt):
                    try:
                        href = (await all_links.nth(i).get_attribute("href") or "")
                        if "web.telegram.org" in href:
                            print(f"    [->] Lien Web Telegram trouvé : {href[:60]}")
                            await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                            await page.wait_for_timeout(random.randint(2500, 4000))
                            web_k_clicked = True
                            break
                    except Exception:
                        pass
            except Exception:
                pass

        # Méthode 3 : clic JS sur n'importe quel lien pointant vers web.telegram.org
        if not web_k_clicked:
            try:
                href_js = await page.evaluate("""
                    () => {
                        for (const a of document.querySelectorAll('a')) {
                            if ((a.href || '').includes('web.telegram.org')) return a.href;
                        }
                        return null;
                    }
                """)
                if href_js:
                    await page.goto(href_js, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(random.randint(2500, 4000))
                    web_k_clicked = True
            except Exception:
                pass

    # ── Fallback : navigation directe #@username si t.me n'a pas fonctionné ──
    if not web_k_clicked or "web.telegram.org" not in page.url:
        print(f"    [!] t.me/{username} : bouton Web K non trouvé — fallback direct")
        try:
            await page.goto(f"https://web.telegram.org/k/#@{username}",
                            wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(random.randint(2000, 4000))
        except Exception:
            pass

    if "web.telegram.org" not in page.url:
        print(f"    [X] @{username} : impossible d'atteindre Telegram Web K")
        return False

    await page.wait_for_timeout(1000)
    return True


async def lire_chat(page, url: str):
    username = _username_from_url(url)
    print(f"    [->] Lecture de @{username}...")
    try:
        await page.bring_to_front()
        await page.wait_for_timeout(random.randint(1200, 2800))

        # Ouvre via t.me (colle le lien directement dans la barre d'adresse)
        if not await _ouvrir_via_tme(page, username):
            print(f"    [!] Impossible d'ouvrir @{username}")
            return

        await page.wait_for_timeout(random.randint(1500, 3000))

        # Scroll pour simuler la lecture
        for _ in range(random.randint(3, 7)):
            await page.mouse.wheel(0, random.randint(-220, -70))
            await page.wait_for_timeout(random.randint(1000, 2500))
        await page.mouse.wheel(0, random.randint(80, 200))
        await page.wait_for_timeout(random.randint(800, 1600))
        print(f"    [OK] Lu")
    except Exception as e:
        print(f"    [X] Erreur lecture : {e}")


async def poster_dans_groupe(page, group_url: str, message: str, topic: str = None) -> bool:
    username = _username_from_url(group_url)
    print(f"    [->] Post dans @{username}" + (f" / topic '{topic}'" if topic else "") + "...")
    try:
        await page.bring_to_front()
        await page.wait_for_timeout(random.randint(2000, 4000))

        # Ouvre via t.me (colle le lien dans la barre d'adresse — même méthode que pour rejoindre)
        if not await _ouvrir_via_tme(page, username):
            print(f"    [--] Impossible d'ouvrir @{username}")
            return False

        await page.wait_for_timeout(random.randint(2000, 4000))

        # ── Détection automatique des topics/sous-sections forum ──────────────
        # Mots-clés à chercher dans les noms de topics (priorité ordre)
        if topic:
            topic_keywords = [topic.lower()]
        else:
            topic_keywords = ["job", "offre", "emploi", "recrutement",
                              "annonce", "travail", "mission", "poste", "boulot"]

        # Sélecteurs Telegram Web K pour les éléments de topic forum
        TOPIC_SELECTORS = [
            ".forum-topic",
            ".topic-item",
            ".chat-topic",
            "[class*='forum-topic']",
            "[class*='topic-item']",
            ".bubbles-inner .list-item",
            ".forum-topics .list-item",
            ".chatlist .list-item",
        ]

        forum_found = False

        for sel in TOPIC_SELECTORS:
            try:
                items = page.locator(sel)
                count = await items.count()
                if count == 0:
                    continue

                # Des topics sont visibles — c'est un groupe forum
                print(f"    [->] {count} topic(s) détectés [{sel}] — recherche '{topic_keywords[0]}'...")

                # 1re passe : cherche un topic contenant un mot-clé
                for i in range(count):
                    el = items.nth(i)
                    try:
                        if not await el.is_visible(timeout=800):
                            continue
                        txt = (await el.inner_text()).lower().strip()
                        if any(kw in txt for kw in topic_keywords):
                            print(f"    [->] Topic cible trouvé : '{txt[:50]}' — clic...")
                            await el.click()
                            await page.wait_for_timeout(2500)
                            forum_found = True
                            break
                    except Exception:
                        continue

                # 2e passe : aucun mot-clé trouvé → clic sur le 1er topic visible
                if not forum_found:
                    for i in range(count):
                        el = items.nth(i)
                        try:
                            if not await el.is_visible(timeout=800):
                                continue
                            txt = (await el.inner_text()).strip()
                            if txt:
                                print(f"    [->] Aucun topic '{topic_keywords[0]}' — clic sur '{txt[:40]}'")
                                await el.click()
                                await page.wait_for_timeout(2500)
                                forum_found = True
                                break
                        except Exception:
                            continue

                if forum_found:
                    break

            except Exception:
                continue

        # ── Fallback JS si les sélecteurs CSS n'ont rien trouvé ───────────────
        if not forum_found:
            try:
                import json as _json
                kw_json = _json.dumps(topic_keywords)
                clicked_js = await page.evaluate(f"""
                    () => {{
                        const keywords = {kw_json};
                        const selectors = [
                            '.forum-topic', '.topic-item', '.chat-topic',
                            '[class*="forum-topic"]', '[class*="topic-item"]',
                            '.bubbles-inner .list-item', '.forum-topics .list-item'
                        ];
                        // 1re passe : mot-clé
                        for (const sel of selectors) {{
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {{
                                const txt = (el.innerText || el.textContent || '').toLowerCase().trim();
                                if (txt && keywords.some(kw => txt.includes(kw))) {{
                                    el.click();
                                    return txt.substring(0, 60);
                                }}
                            }}
                        }}
                        // 2e passe : premier topic visible
                        for (const sel of selectors) {{
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {{
                                const txt = (el.innerText || el.textContent || '').trim();
                                if (txt && el.offsetParent !== null) {{
                                    el.click();
                                    return '(premier) ' + txt.substring(0, 50);
                                }}
                            }}
                        }}
                        return null;
                    }}
                """)
                if clicked_js:
                    print(f"    [->] Topic cliqué via JS : '{clicked_js}'")
                    await page.wait_for_timeout(2500)
                    forum_found = True
            except Exception:
                pass

        if forum_found:
            # Laisser le temps à la vue du topic de charger
            await page.wait_for_timeout(random.randint(2000, 4000))
        else:
            # Pas de topics détectés → groupe normal, on poste directement
            await page.wait_for_timeout(random.randint(3000, 5000))

        inp = await get_real_input(page)
        if not inp:
            print(f"    [--] Champ message indisponible (canal broadcast / pas membre ?)")
            return False

        await type_message(page, inp, message)
        print(f"    [OK] Message posté dans @{username}" + (" (topic)" if forum_found else ""))
        return True

    except Exception as e:
        err_str = str(e)
        # Si le browser est fermé → re-raise pour stopper la boucle de posts
        if "closed" in err_str.lower() or "target page" in err_str.lower():
            raise
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


async def _ouvrir_via_recherche(page, username: str) -> bool:
    """
    Ouvre une conversation Telegram en passant par la barre de recherche.
    Retourne True si la conversation est ouverte avec succès, False sinon.
    """
    # ── 1. Aller à la page principale ────────────────────────────
    try:
        await page.goto("https://web.telegram.org/k/",
                        wait_until="domcontentloaded", timeout=15000)
    except Exception:
        pass
    try:
        await page.wait_for_selector("li.chatlist-chat, .chatlist", timeout=10000)
    except Exception:
        pass
    await page.wait_for_timeout(1200)

    # Fermer tout overlay / modal ouvert
    for _ in range(2):
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)
        except Exception:
            pass

    # ── 2. Trouver la barre de recherche ─────────────────────────
    search_input = None
    search_selectors = [
        "input.input-search-input",
        ".search-container input",
        ".search input",
        ".topbar-search input",
        ".chatlist-search input",
        "input[placeholder*='earch']",   # Search / Recherche
        "input[type='search']",
        "input[type='text']",            # fallback générique
    ]
    for sel in search_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1500):
                search_input = el
                break
        except Exception:
            continue

    if not search_input:
        # Essayer via JS : cliquer le premier input visible dans la sidebar gauche
        try:
            await page.evaluate("""
                () => {
                    const inp = document.querySelector(
                        '.sidebar-left input, .search input, input[type="text"]'
                    );
                    if (inp) inp.click();
                }
            """)
            await page.wait_for_timeout(600)
            for sel in ["input.input-search-input", ".search input", "input"]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1000):
                        search_input = el
                        break
                except Exception:
                    continue
        except Exception:
            pass

    if not search_input:
        print(f"    [X] Barre de recherche introuvable (@{username})")
        return False

    # ── 3. Taper @username dans la recherche ─────────────────────
    await search_input.click()
    await page.wait_for_timeout(400)
    # Vider le champ
    await search_input.press("Control+a")
    await page.wait_for_timeout(150)
    await search_input.press("Delete")
    await page.wait_for_timeout(200)
    # Taper avec délai humain
    await search_input.type(f"@{username}", delay=random.randint(60, 130))
    await page.wait_for_timeout(2500)   # laisser les résultats apparaître

    # ── 4. Cliquer sur le résultat correspondant ──────────────────
    clicked = False

    # Tentative A : li.chatlist-chat contenant le username (résultat le plus courant)
    for attempt in range(3):
        try:
            chats = page.locator("li.chatlist-chat")
            count = await chats.count()
            for i in range(count):
                el = chats.nth(i)
                try:
                    text = (await el.inner_text()).lower()
                    if username.lower() in text:
                        await el.click()
                        clicked = True
                        break
                except Exception:
                    continue
        except Exception:
            pass
        if clicked:
            break
        await page.wait_for_timeout(1000)

    if not clicked:
        # Tentative B : éléments dans les groupes de résultats de recherche globale
        result_selectors = [
            ".search-group__items li",
            ".search-group .chatlist-chat",
            ".search-results li",
            ".search-super li",
            "[class*='search-result']",
        ]
        for sel in result_selectors:
            try:
                results = page.locator(sel)
                count   = await results.count()
                for i in range(count):
                    el = results.nth(i)
                    try:
                        text = (await el.inner_text()).lower()
                        if username.lower() in text:
                            await el.click()
                            clicked = True
                            break
                    except Exception:
                        continue
                if clicked:
                    break
            except Exception:
                continue

    if not clicked:
        # Tentative C : flèche bas + Entrée (premier résultat de la liste)
        try:
            await search_input.press("ArrowDown")
            await page.wait_for_timeout(300)
            await search_input.press("Enter")
            await page.wait_for_timeout(2000)
            # Valide uniquement si un vrai input de message est apparu
            if await get_real_input(page):
                clicked = True
        except Exception:
            pass

    if not clicked:
        print(f"    [--] @{username} introuvable dans les résultats de recherche")
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
        except Exception:
            pass
        return False

    # ── 5. Attendre l'ouverture de la conversation ────────────────
    await page.wait_for_timeout(2500)
    return True


async def envoyer_dm_template(page, username: str, prenom: str, messages: list) -> bool:
    """Envoie 1 à 5 messages DM via la barre de recherche Telegram Web K.
    messages = liste de strings déjà formatés (prenom remplacé).
    """
    print(f"    [->] DM template à @{username} ({len(messages)} msg)...")
    try:
        await page.bring_to_front()
        await page.wait_for_timeout(random.randint(2500, 4000))

        # ── Ouvrir la conversation via la recherche ───────────────
        if not await _ouvrir_via_recherche(page, username):
            return False

        # ── Bouton "Démarrer" si première conversation ────────────
        for sel in ["button.btn-primary", ".start-bot-button"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        # ── Trouver le vrai input de message (retry 4×4s) ─────────
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
            print(f"    [--] @{username} input introuvable après sélection")
            return False

        # ── Envoyer le 1er message ────────────────────────────────
        await type_message(page, real_input, messages[0])

        # ── Messages 2 à 5 avec délai aléatoire ──────────────────
        for idx_m, msg in enumerate(messages[1:], 2):
            if msg.strip():
                delay_m = random.uniform(5, 18)
                print(f"    [->] Message {idx_m}/{len(messages)} dans {delay_m:.0f}s...")
                await page.wait_for_timeout(int(delay_m * 1000))
                inp_next = await get_real_input(page)
                if inp_next:
                    await type_message(page, inp_next, msg)

        print(f"    [OK] DM template envoyé à {prenom} (@{username}) — {len(messages)} msg")
        return True, None

    except Exception as e:
        err_msg = str(e)
        print(f"    [X] Erreur DM template @{username} : {err_msg}")
        return False, err_msg


async def envoyer_dm(page, username: str, prenom: str) -> bool:
    print(f"    [->] DM à @{username}...")
    try:
        await page.bring_to_front()
        await page.wait_for_timeout(random.randint(1500, 3000))

        # Ouvrir via la barre de recherche (même approche que envoyer_dm_template)
        if not await _ouvrir_via_recherche(page, username):
            return False

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
        for attempt in range(3):
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
            if real_input:
                break
            if attempt < 2:
                await page.wait_for_timeout(3000)

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
        return True, None

    except Exception as e:
        print(f"    [X] Erreur DM @{username} : {e}")
        return False, str(e)


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

    # ── Filtre genre ──────────────────────────────────────────
    dm_settings   = load_massdm_settings()
    genre_filter  = dm_settings.get("genre_filter", "tous")
    if genre_filter == "garcon":
        avant = len(candidates)
        candidates = [m for m in candidates
                      if detecter_genre(m.get("prenom", "") or "") in ("M", "?")]
        print(f"  [♂] Filtre garçons : {avant} → {len(candidates)} cibles")
    elif genre_filter == "fille":
        avant = len(candidates)
        candidates = [m for m in candidates
                      if detecter_genre(m.get("prenom", "") or "") in ("F", "?")]
        print(f"  [♀] Filtre filles : {avant} → {len(candidates)} cibles")
    # ─────────────────────────────────────────────────────────

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

                    msgs = [tmpl["content"].replace("{prenom}", prenom)]
                    for _key in ["content2", "content3", "content4", "content5"]:
                        _v = (tmpl.get(_key) or "").strip().replace("{prenom}", prenom)
                        if _v:
                            msgs.append(_v)

                    ok, dm_err = await envoyer_dm_template(page, username, prenom, msgs)
                    if ok:
                        progress["dms_sent"].append(username)
                        log_dm(profile_id, username, prenom, tmpl.get("name", ""))
                        session_counts[tmpl["id"]] = session_counts.get(tmpl["id"], 0) + 1
                        report_dm_send(tmpl["id"])
                        dms_ok += 1
                        save_progress(profile_id, progress)
                    elif dm_err:
                        err_detail = f"DM échoué @{username} : {dm_err}"
                        session_errors.append(err_detail)
                        print(f"    [!] {err_detail}", flush=True)

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
            except AttributeError:
                try:
                    await browser.close()
                except Exception:
                    pass
            except Exception:
                pass  # non-critique, ne pas polluer last_error
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

    # ── Met à jour la page Warm-Up (dm_day, done_today…) ─────────
    try:
        requests.post(f"{DASHBOARD_URL}/api/update", json={
            "token":       DASHBOARD_TOKEN,
            "profile_id":  profile_id,
            "day":         1,   # warm-up day ne change pas
            "done_today":  True,
            "dms_total":   len(progress.get("dms_sent", [])),
            "posts_total": 0,
            "groups_joined": 0,
            "dm_responses":  0,
            "dms_session":   dms_ok,
            "posts_session": 0,
            "last_error":    " | ".join(session_errors) if session_errors else "",
            "dm_day":        dm_day,
        }, timeout=30)
    except Exception as e:
        print(f"[!] Dashboard /api/update non joignable : {e}")

    # ── Met à jour la page Mass DM (stats Supabase massdm) ───────
    try:
        requests.post(f"{DASHBOARD_URL}/api/massdm", json={
            "token":            DASHBOARD_TOKEN,
            "profile_id":       profile_id,
            "dms_sent":         len(progress.get("dms_sent", [])),
            "dms_sent_session": dms_ok,
            "dms_replied":      0,
            "conversions":      0,
            "status":           "Actif" if dms_ok > 0 else "En attente",
            "last_error":       " | ".join(session_errors) if session_errors else "",
        }, timeout=30)
        print(f"[->] Stats Mass DM envoyées : {dms_ok} DM(s) cette session")
    except Exception as e:
        print(f"[!] Dashboard /api/massdm non joignable : {e}")

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
        pause = random.uniform(120, 180)
        print(f"[->] Pause {pause:.0f}s avant le profil suivant...\n")
        await asyncio.sleep(pause)


def _auto_switch_to_massdm(profile_id: str):
    """Bascule automatiquement un profil en mode Mass DM sur le dashboard."""
    try:
        r = requests.post(
            f"{DASHBOARD_URL}/api/profile/mode",
            json={"token": DASHBOARD_TOKEN, "profile_id": profile_id, "mode": "direct_dm"},
            timeout=10,
        )
        if r.status_code == 200 and r.json().get("ok"):
            print(f"  [⚡] {profile_id} basculé automatiquement en Mass DM !")
        else:
            print(f"  [!] Switch Mass DM échoué pour {profile_id}: {r.text}")
    except Exception as e:
        print(f"  [!] Impossible de basculer {profile_id} en Mass DM: {e}")


async def run_warmup_for_profile(profile_id: str, profile_num: int, total: int,
                                 force_warmup: bool = False):
    """Lance la session du jour pour un profil AdsPower donné.
    force_warmup=True → ignore le dm_mode, fait TOUJOURS le warm-up.
    """

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
    #  MODE DIRECT DM — seulement si force_warmup est False
    # ════════════════════════════════════════════════════════
    if dm_mode == "direct_dm" and not force_warmup:
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
        # Bascule automatiquement en Mass DM si le profil est encore en mode warmup
        if dm_mode == "warmup":
            _auto_switch_to_massdm(profile_id)
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


    # ── Signal LIVE au dashboard (badge rouge) ────────────────
    try:
        requests.post(f"{DASHBOARD_URL}/api/update", json={
            "token":      DASHBOARD_TOKEN,
            "profile_id": profile_id,
            "day":        day,
            "done_today": False,
        }, timeout=5)
    except Exception:
        pass

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
                except AttributeError:
                    try:
                        await browser.close()
                    except Exception:
                        pass
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
                            # ── Lecture simulée 26-35s avant de poster ──────────
                            lecture_dur = random.uniform(26, 35)
                            print(f"    [->] Lecture simulée {lecture_dur:.0f}s avant de poster...", flush=True)
                            elapsed = 0.0
                            while elapsed < lecture_dur:
                                scroll_y = random.randint(-280, -60)
                                await page.mouse.wheel(0, scroll_y)
                                delay = random.uniform(1.2, 3.5)
                                await asyncio.sleep(delay)
                                elapsed += delay
                            # ── Post ────────────────────────────────────────────
                            inp = await get_real_input(page)
                            if inp:
                                print(f"    [->] Post dans le groupe rejoint...")
                                await type_message(page, inp, msg)
                                print(f"    [OK] Poste !")
                    pause = random.uniform(14, 26)
                    print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                    await asyncio.sleep(pause)

            # ── PHASE 2 : Lecture des chats ───────────────────────
            if n_lect > 0:
                print(f"[->] Phase 2 : Lecture ({n_lect} chats)\n", flush=True)
                read_urls = [f"https://web.telegram.org/k/#@{g}" for g in PUBLIC_GROUPS + READ_ONLY_GROUPS]
                read_urls.append("https://web.telegram.org/k/#@sfs_france")
                for url in progress.get("private_chat_urls", {}).values():
                    if "web.telegram.org" in url:
                        read_urls.append(url)
                random.shuffle(read_urls)
                for i in range(n_lect):
                    await lire_chat(page, read_urls[i % len(read_urls)])
                    if i < n_lect - 1:
                        pause = random.uniform(6, 15)
                        print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                        await asyncio.sleep(pause)

            # ── PHASE 3 : Posts dans groupes publics (J3+) ────────
            if n_posts > 0:
                print(f"\n[->] Phase 3 : Posts ({n_posts})\n", flush=True)
                pool = PUBLIC_GROUPS.copy()
                random.shuffle(pool)
                posted = 0
                browser_dead = False
                for group in pool:
                    if posted >= n_posts:
                        break
                    url = f"https://web.telegram.org/k/#@{group}"
                    msg = random.choice(GROUP_MESSAGES)
                    try:
                        ok = await poster_dans_groupe(page, url, msg, None)
                    except Exception as _e:
                        # Browser fermé — arrêt immédiat de la phase posts
                        print(f"    [X] Browser fermé — arrêt des posts : {_e}")
                        browser_dead = True
                        session_errors.append(f"Browser fermé pendant posts: {_e}")
                        break
                    if ok:
                        posted += 1
                    if posted < n_posts and not browser_dead:
                        pause = random.uniform(14, 26)
                        print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                        await asyncio.sleep(pause)

            # ── PHASE 4 : DMs non-contacts (J8+) ─────────────────
            if dm_targets:
                print(f"\n[->] Phase 4 : DMs ({len(dm_targets)})\n", flush=True)
                for i, membre in enumerate(dm_targets):
                    username = membre["username"]
                    prenom   = membre.get("prenom") or "toi"
                    ok, dm_err = await envoyer_dm(page, username, prenom)
                    if ok:
                        progress["dms_sent"].append(username)
                        log_dm(profile_id, username, prenom)
                        dms_ok += 1
                        save_progress(profile_id, progress)
                    elif dm_err:
                        session_errors.append(f"DM échoué @{username} : {dm_err}")
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
            except AttributeError:
                # Certaines versions Playwright n'ont pas disconnect() → close() à la place
                try:
                    await browser.close()
                    print(f"[->] Playwright : navigateur ferme (close)")
                except Exception:
                    pass
            except Exception as e:
                print(f"[!] Fermeture navigateur (non bloquant) : {e}")
                # Non-critique : ne pas ajouter à session_errors
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

    # ── Bascule automatique en Mass DM si Jour 15 terminé ────
    if day >= 15:
        _auto_switch_to_massdm(profile_id)

    next_msg = (
        f"→ Reviens demain pour le Jour {day + 1} !"
        if day < 15 else
        "CHAUFFE TERMINÉE — basculé en Mass DM automatiquement !"
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

    # Pause entre deux profils (1 minute)
    if profile_num < total:
        pause = random.uniform(120, 180)
        print(f"[->] Pause {pause:.0f}s avant le profil suivant...\n")
        await asyncio.sleep(pause)


# ── Entrée principale ─────────────────────────────────────────

async def main(force: bool = False, warmup_only: bool = False, massdm_only: bool = False, target_profile: str = None):
    """
    warmup_only=True    : force le warm-up pour TOUS les profils, ignore le dm_mode,
                          réinitialise done_today. (bouton 'Lancer Warm-Up')
    massdm_only=True    : lance uniquement les profils en mode direct_dm.
                          (bouton 'Lancer Mass DM')
    target_profile=pid  : restreint massdm_only à UN seul profil.
                          (bouton ▶ Lancer par profil dans Mass DM)
    force=True          : relance même si déjà fait aujourd'hui (mode normal).
    """
    args = [a for a in sys.argv[1:]
            if a not in ("--daemon", "--auto", "--warmup-only", "--massdm-only",
                         "--massdm-profile") and not a.startswith("--massdm-profile")]

    # ── --status ──────────────────────────────────────────────
    if "--status" in args:
        print_all_status()
        return

    # ── --reset-all ───────────────────────────────────────────
    if "--reset-all" in args:
        count = 0
        for pid in ADSPOWER_PROFILES:
            path = progress_file(pid)
            if os.path.exists(path):
                os.remove(path)
                count += 1
        print(f"\n[OK] {count} fichiers de progression supprimés.")
        print(f"[OK] Tous les profils remis à Jour 1 — relance le warm-up normalement.\n")
        return

    # ── --fix-days ────────────────────────────────────────────
    # Recalcule le jour réel depuis start_date + last_run_date.
    # Utile quand le compteur a déraillé (bug sessions multiples).
    if "--fix-days" in args:
        from datetime import datetime as _dt
        print(f"\n{'='*62}")
        print(f"  CORRECTION DES JOURS — basée sur start_date + last_run_date")
        print(f"{'='*62}")
        for pid in ADSPOWER_PROFILES:
            path = progress_file(pid)
            if not os.path.exists(path):
                print(f"  {pid:<14}  pas de fichier → ignoré")
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            start_str    = data.get("start_date")
            last_str     = data.get("last_run_date")
            old_day      = data.get("day", 1)
            if not start_str:
                print(f"  {pid:<14}  pas de start_date → ignoré")
                continue
            start_d = _dt.strptime(start_str, "%Y-%m-%d").date()
            if last_str:
                last_d      = _dt.strptime(last_str, "%Y-%m-%d").date()
                correct_day = (last_d - start_d).days + 1
            else:
                correct_day = 1
            correct_day = max(1, correct_day)  # jamais < 1
            data["day"]       = correct_day
            data["done_today"] = False          # relancer demain
            save_progress(pid, data)
            status = "DONE" if correct_day > 15 else f"J{correct_day}/15"
            print(f"  {pid:<14}  J{old_day:>3} → {status}  (last_run={last_str or 'jamais'})")
        print(f"\n[OK] Correction terminée. Lance maintenant : python warmup_v2.py\n")
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

    # Charge les modes depuis le dashboard
    dash_modes = {}
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/status", timeout=10)
        if r.status_code == 200:
            dash_modes = r.json()
    except Exception:
        pass

    # ── Mode MASS DM UNIQUEMENT ───────────────────────────────
    if massdm_only:
        dm_profiles = [
            (i, pid) for i, pid in profiles_to_run
            if (dash_modes.get(pid) or {}).get("dm_mode", "warmup") == "direct_dm"
        ]
        # Si un profil cible est spécifié, on l'accepte même s'il n'est pas en direct_dm
        # (le daemon le force directement via le bouton)
        if target_profile:
            dm_profiles = [(i, pid) for i, pid in profiles_to_run if pid == target_profile]
            if not dm_profiles:
                print(f"\n[!] Profil '{target_profile}' introuvable dans la liste des profils.")
                return
        elif not dm_profiles:
            print("\n[!] Aucun profil en mode Mass DM trouvé.")
            print("    → Passe d'abord des profils en mode Mass DM dans l'onglet Warm-Up du dashboard")
            return
        profiles_to_run = dm_profiles
        print(f"\n{'='*60}")
        print(f"  ⚡ MASS DM — {len(profiles_to_run)} profil(s) en mode Direct DM")
        print(f"  Date : {date.today()}")
        print(f"{'='*60}")
        for i, pid in profiles_to_run:
            dm_day_cur = int((dash_modes.get(pid) or {}).get("dm_day", 0) or 0)
            print(f"  Profil ({pid}) — Jour {dm_day_cur + 1}")
        print()
        print("\n[->] Démarrage dans 10 secondes... (Ctrl+C pour annuler)")
        await asyncio.sleep(10)
        for i, pid in profiles_to_run:
            await run_warmup_for_profile(pid, i + 1, len(profiles_to_run))
        print(f"\n{'='*60}")
        print(f"  MASS DM TERMINÉ POUR TOUS LES PROFILS")
        print(f"{'='*60}\n")
        return

    # ── Mode WARM-UP FORCÉ ────────────────────────────────────
    if warmup_only:
        print(f"\n{'='*60}")
        print(f"  🔥 WARM-UP FORCÉ — {len(profiles_to_run)} profil(s)")
        print(f"  (Mode dm ignoré — warm-up uniquement)")
        print(f"  Date : {date.today()}")
        print(f"{'='*60}")
        # Réinitialise done_today pour tous les profils warm-up
        for _, pid in profiles_to_run:
            data = load_progress(pid)
            if data.get("done_today"):
                data["done_today"] = False
                save_progress(pid, data)
                print(f"  [->] Reset done_today pour {pid}")
        print()
        print("\n[->] Démarrage dans 10 secondes... (Ctrl+C pour annuler)")
        await asyncio.sleep(10)
        for i, pid in profiles_to_run:
            # force_warmup=True → ignore dm_mode, fait toujours le warm-up
            await run_warmup_for_profile(pid, i + 1, len(profiles_to_run), force_warmup=True)
        print(f"\n{'='*60}")
        print(f"  WARM-UP TERMINÉ POUR TOUS LES PROFILS")
        print(f"{'='*60}\n")
        return

    # ── Mode NORMAL ───────────────────────────────────────────
    total = len(profiles_to_run)
    print(f"\n{'='*60}")
    print(f"  WARM-UP MULTI-PROFILS — {total} profil(s) à traiter")
    print(f"  Date : {date.today()}")
    print(f"{'='*60}")

    # Aperçu rapide
    skip = 0
    for i, pid in profiles_to_run:
        data    = load_progress(pid)
        day     = data["day"]
        dm_mode = (dash_modes.get(pid) or {}).get("dm_mode", "warmup")
        tag     = ""
        if dm_mode == "direct_dm":
            dm_day_cur = int((dash_modes.get(pid) or {}).get("dm_day", 0) or 0)
            tag = f"  [⚡ DIRECT DM — J{dm_day_cur + 1}]"
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
        for _, pid in profiles_to_run:
            data = load_progress(pid)
            if data.get("done_today"):
                data["done_today"] = False
                save_progress(pid, data)

    print()
    print("\n[->] Démarrage automatique dans 10 secondes... (Ctrl+C pour annuler)")
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

def _check_trigger(url_key: str) -> bool:
    """Cherche un trigger dans la table channels par url_key. Retourne True + reset."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/channels",
            headers=SUPABASE_HEADERS,
            params={"url": f"eq.{url_key}", "select": "id,status"},
            timeout=8,
        )
        rows = r.json() if r.status_code == 200 else []
        if any(row.get("status") == "triggered" for row in rows):
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/channels",
                headers=SUPABASE_HEADERS,
                params={"url": f"eq.{url_key}"},
                json={"status": "done"},
                timeout=8,
            )
            return True
    except Exception as e:
        log(f"[!] check_trigger({url_key}) erreur : {e}")
    return False


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


def check_profile_change_triggers() -> list:
    """
    Cherche les lignes channels dont l'url commence par '__profile_apply__'.
    Retourne la liste des profile_id à traiter et remet leur status à 'done'.
    """
    pids = []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/channels",
            headers=SUPABASE_HEADERS,
            params={"url": "like.__profile_apply__%", "select": "id,url,status"},
            timeout=8,
        )
        rows = r.json() if r.status_code == 200 else []
        for row in rows:
            if row.get("status") == "triggered":
                url = row.get("url", "")
                # Extrait le profile_id depuis '__profile_apply__<pid>__'
                pid = url.replace("__profile_apply__", "").replace("__", "").strip()
                if pid:
                    pids.append(pid)
                # Reset le trigger
                requests.patch(
                    f"{SUPABASE_URL}/rest/v1/channels",
                    headers=SUPABASE_HEADERS,
                    params={"url": f"eq.{url}"},
                    json={"status": "done"},
                    timeout=8,
                )
    except Exception as e:
        log(f"[!] check_profile_change_triggers erreur : {e}")
    return pids


def check_profile_massdm_triggers() -> list:
    """
    Cherche les triggers __massdm_pid_<pid>__ dans channels.
    Retourne la liste des profile_id à traiter et remet leur status à 'done'.
    Permet de lancer le Mass DM pour un profil individuel depuis le dashboard.
    """
    pids = []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/channels",
            headers=SUPABASE_HEADERS,
            params={"url": "like.__massdm_pid__%", "select": "id,url,status"},
            timeout=8,
        )
        rows = r.json() if r.status_code == 200 else []
        for row in rows:
            if row.get("status") == "triggered":
                url = row.get("url", "")
                pid = url.replace("__massdm_pid_", "").replace("__", "").strip()
                if pid:
                    pids.append(pid)
                requests.patch(
                    f"{SUPABASE_URL}/rest/v1/channels",
                    headers=SUPABASE_HEADERS,
                    params={"url": f"eq.{url}"},
                    json={"status": "done"},
                    timeout=8,
                )
    except Exception as e:
        log(f"[!] check_profile_massdm_triggers erreur : {e}")
    return pids


async def daemon():
    """
    Mode daemon — tourne en continu.
    - Poll Supabase toutes les 30s
    - Lance le warm-up dès que le bouton 'Lancer' est cliqué
    - Lance profile_changer.py dès qu'un profil est modifié dans Setup
    """
    log("=" * 50)
    log("WARM-UP DAEMON démarré — poll toutes les 30s")
    log(f"Log : {LOG_FILE}")
    log("=" * 50)

    while True:
        # ── Trigger warm-up ──────────────────────────────────
        try:
            triggered = _check_trigger("__warmup_trigger__")
        except Exception as e:
            log(f"[!] Erreur poll warmup : {e}")
            triggered = False

        # ── Trigger mass DM ───────────────────────────────────
        try:
            massdm_triggered = _check_trigger("__massdm_trigger__")
        except Exception as e:
            log(f"[!] Erreur poll massdm : {e}")
            massdm_triggered = False

        # ── Exclusion mutuelle : si les deux tirent en même temps ────
        # (trigger warmup stale + nouveau trigger massdm → priorité massdm)
        if triggered and massdm_triggered:
            log("[!] Warmup ET Mass DM déclenchés simultanément — priorité Mass DM, warmup ignoré")
            triggered = False

        if triggered:
            log("[▶] Signal warm-up reçu ! Ouverture d'un terminal visible...")
            try:
                subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__), "--warmup-only"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                log("[OK] Terminal warm-up ouvert (--warmup-only).")
            except Exception as e:
                log(f"[!] Erreur lancement warm-up : {e}")

        if massdm_triggered:
            log("[⚡] Signal Mass DM reçu ! Ouverture d'un terminal visible...")
            try:
                subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__), "--massdm-only"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                log("[OK] Terminal Mass DM ouvert (--massdm-only).")
            except Exception as e:
                log(f"[!] Erreur lancement Mass DM : {e}")

        # ── Trigger changement de profil (Setup page) ─────────
        try:
            profile_pids = check_profile_change_triggers()
        except Exception as e:
            log(f"[!] Erreur poll profil : {e}")
            profile_pids = []

        # Traitement UN PAR UN — attendre la fin avant de lancer le suivant
        for pid in profile_pids:
            log(f"[✏] Changement profil détecté pour {pid} — lancement profile_changer.py...")
            try:
                changer_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile_changer.py")
                # asyncio.create_subprocess_exec = non-bloquant, compatible async
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, changer_path, pid, "--silent",
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                log(f"[OK] profile_changer.py lancé pour {pid} (PID {proc.pid})")
                # Attendre la fin proprement (async, n'bloque pas l'event loop)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=600)
                    log(f"[OK] profile_changer.py terminé pour {pid}")
                except asyncio.TimeoutError:
                    log(f"[!] profile_changer.py timeout pour {pid} — on passe")
                    proc.kill()
                # Pause 5s entre deux profils
                await asyncio.sleep(5)
            except Exception as e:
                log(f"[!] Erreur lancement profile_changer.py : {e}")
                # Fallback : méthode classique
                try:
                    subprocess.Popen(
                        [sys.executable, changer_path, pid],
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                    )
                    await asyncio.sleep(420)  # 7 min d'attente fixe en fallback
                except Exception as e2:
                    log(f"[!] Fallback aussi échoué : {e2}")

        # ── Trigger Mass DM par profil individuel ─────────────
        try:
            pid_dm_list = check_profile_massdm_triggers()
        except Exception as e:
            log(f"[!] Erreur poll massdm profil : {e}")
            pid_dm_list = []

        for pid in pid_dm_list:
            log(f"[⚡] Mass DM individuel déclenché pour {pid} — lancement...")
            try:
                subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__), "--massdm-profile", pid],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                log(f"[OK] Mass DM lancé pour {pid}")
            except Exception as e:
                log(f"[!] Erreur lancement Mass DM profil {pid} : {e}")

        if not triggered and not massdm_triggered and not profile_pids and not pid_dm_list:
            log(f"[·] En attente du bouton dashboard...")

        await asyncio.sleep(30)


if __name__ == "__main__":
    if "--daemon" in sys.argv or "--auto" in sys.argv:
        asyncio.run(daemon())
    elif "--warmup-only" in sys.argv:
        # Lancé par le daemon via bouton "Lancer Warm-Up"
        asyncio.run(main(force=True, warmup_only=True))
    elif "--massdm-only" in sys.argv:
        # Lancé par le daemon via bouton "Lancer Mass DM" (tous les profils direct_dm)
        try:
            asyncio.run(main(massdm_only=True))
        except Exception as _e:
            print(f"\n[X] ERREUR CRITIQUE : {_e}")
        input("\nAppuie sur Entrée pour fermer...")
    elif "--massdm-profile" in sys.argv:
        # Lancé par le daemon via bouton ▶ Lancer d'un profil individuel
        _idx = sys.argv.index("--massdm-profile")
        _pid = sys.argv[_idx + 1] if _idx + 1 < len(sys.argv) else None
        try:
            asyncio.run(main(massdm_only=True, target_profile=_pid))
        except Exception as _e:
            print(f"\n[X] ERREUR CRITIQUE : {_e}")
        input("\nAppuie sur Entrée pour fermer...")
    else:
        asyncio.run(main())
