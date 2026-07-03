"""
warmup.py - Chauffe Telegram 15 jours
Fonctionnalites :
  - Rejoint 8 groupes (2/jour sur 4 jours)
  - Poste des messages varies dans les groupes
  - Repond automatiquement aux DMs recus
  - Envoie des DMs progressifs (a partir du J8)

Usage :
  python warmup.py            → session du jour
  python warmup.py --status   → voir la progression
  python warmup.py --reset    → repartir du jour 1
"""

import asyncio
import csv
import json
import os
import random
import sys
import urllib.parse
import requests
from datetime import date
from playwright.async_api import async_playwright

# ============================================================
ADSPOWER_ID   = "k1csfeja"
ADSPOWER_API  = "http://local.adspower.net:50325"
ADSPOWER_KEY  = "942d5c4fa00deedac520c3310912ee6100795935b355b33b"
PROGRESS_FILE = "output/warmup_progress.json"
DM_LOG_FILE   = "output/dm_web_log.csv"
DM_CSV        = "output/membres.csv"

# ── 8 groupes a rejoindre (2 par jour, 4 jours) ──────────────
# Ordre exact : les 2 premiers = Jour 1, suivants = Jour 2, etc.
GROUPS_TO_JOIN = [
    # Jour 1 — groupes prives
    ("https://t.me/+uvGQic0R1Lw3NzI0", True,  None),
    ("https://t.me/+vDMk0EkqEKMyNTdk", True,  None),
    # Jour 2 — groupes prives
    ("https://t.me/+wJXdrRx1sng4MDk0", True,  None),
    ("https://t.me/+ELJZSHXtrxkyZjU0", True,  None),
    # Jour 3 — groupes publics
    ("gnetwork_ofm",                   False, "talk zone"),
    ("ofmva_fr",                       False, None),
    # Jour 4 — un public + un prive
    ("ofmanagementgroupe",             False, None),
    ("https://t.me/+45MKai9c7jU1ZGI8", True,  None),
]

# ── Groupes publics pour les posts quotidiens (J5+) ──────────
PUBLIC_GROUPS = [
    ("gnetwork_ofm",      "talk zone"),  # Topic specifique
    ("ofmva_fr",          None),
    ("ofmanagementgroupe",None),
]

# ── Messages a poster dans les groupes (5 variations) ────────
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

# ── Reponses automatiques aux DMs recus ──────────────────────
DM_RESPONSES = [
    "Coucou ! 😊",
    "Salut !",
    "Hey, ça va ?",
    "Bonjour !",
    "Coucou, comment tu vas ?",
    "Salut, tout va bien ?",
    "Hey ! 👋",
    "Bonjour, ça roule ?",
    "Coucou toi 😄",
    "Salut salut !",
    "Hello !",
    "Coucou, quoi de neuf ?",
    "Salut, comment ça se passe ?",
    "Hey, bien ou bien ? 😄",
    "Bonjour ! Comment tu vas ?",
]

# ── Plan 15 jours : (groupes_a_rejoindre, lectures, posts, dms) ──
PLAN = {
    1:  (2, 3, 0, 0),
    2:  (2, 3, 0, 0),
    3:  (2, 3, 1, 0),
    4:  (2, 3, 1, 0),
    5:  (0, 4, 1, 0),
    6:  (0, 3, 1, 0),
    7:  (0, 4, 2, 0),
    8:  (0, 3, 2, 1),
    9:  (0, 4, 2, 2),
    10: (0, 3, 2, 3),
    11: (0, 4, 3, 4),
    12: (0, 3, 3, 5),
    13: (0, 4, 3, 6),
    14: (0, 3, 3, 8),
    15: (0, 4, 3, 10),
}
# ============================================================


# ── Gestion de la progression ─────────────────────────────────

def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Avancement automatique si nouveau jour calendaire
        last = data.get("last_run_date")
        if last and last != str(date.today()) and data.get("done_today"):
            data["day"] += 1
            data["done_today"] = False
            save_progress(data)
        return data
    return {
        "start_date":        str(date.today()),
        "last_run_date":     None,
        "day":               1,
        "done_today":        False,
        "join_index":        0,       # Prochain groupe a rejoindre
        "joined_groups":     [],
        "private_chat_urls": {},      # {invite_url: web_url} apres join
        "dms_sent":          [],
    }


def save_progress(data: dict):
    os.makedirs("output", exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_already_dmed() -> set:
    sent = set()
    if os.path.exists(DM_LOG_FILE):
        with open(DM_LOG_FILE, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("statut") == "envoye":
                    sent.add(row.get("username", ""))
    return sent


def log_dm(username: str, prenom: str):
    from datetime import datetime
    file_exists = os.path.exists(DM_LOG_FILE)
    os.makedirs("output", exist_ok=True)
    with open(DM_LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["username", "prenom", "statut", "heure"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "username": username, "prenom": prenom,
            "statut":   "envoye",
            "heure":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })


def print_status():
    data = load_progress()
    day  = data["day"]
    bar  = "█" * min(day, 15) + "░" * max(0, 15 - day)
    print(f"\n{'='*55}")
    print(f"  CHAUFFE TELEGRAM  [{bar}]")
    print(f"{'='*55}")
    print(f"  Debut           : {data['start_date']}")
    print(f"  Jour actuel     : {day}/15")
    print(f"  Fait aujourd'hui: {'Oui ✓' if data.get('done_today') else 'Non'}")
    print(f"  Groupes rejoints: {len(data.get('joined_groups', []))}/8")
    print(f"  DMs envoyes     : {len(data.get('dms_sent', []))}")
    print(f"\n  Planning :")
    for j in range(day, 16):
        jn, sc, po, dm = PLAN.get(j, (0, 3, 0, 0))
        m = " ← aujourd'hui" if j == day else ""
        print(f"  J{j:02d}: join={jn} | scroll={sc} | posts={po} | DMs={dm}{m}")
    print(f"{'='*55}\n")


# ── AdsPower ──────────────────────────────────────────────────

def start_browser() -> str:
    r = requests.get(
        f"{ADSPOWER_API}/api/v1/browser/start",
        params={"user_id": ADSPOWER_ID, "api_key": ADSPOWER_KEY},
        headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
        timeout=15,
    )
    data = r.json()
    if data.get("code") != 0:
        raise Exception(f"AdsPower : {data.get('msg')}")
    return data["data"]["ws"]["puppeteer"]


def stop_browser():
    requests.get(
        f"{ADSPOWER_API}/api/v1/browser/stop",
        params={"user_id": ADSPOWER_ID, "api_key": ADSPOWER_KEY},
        timeout=10,
    )


# ── Helpers Playwright ────────────────────────────────────────

async def get_real_input(page):
    """Retourne le vrai champ de saisie (ignore le fake placeholder)."""
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
    """Focus via JS pour contourner les intercepts pointer-events."""
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
    """
    Tape un texte lettre par lettre.
    Les \n sont convertis en Shift+Enter (saut de ligne sans envoi).
    """
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
    """
    Rejoint un groupe et retourne l'URL interne Telegram Web K
    pour pouvoir y revenir plus tard.
    """
    print(f"    [->] Rejoindre : {invite_url[:55]}...")
    try:
        if is_private:
            hash_part = invite_url.split("+")[-1].rstrip("/")
            tg_link   = f"tg://join?invite={hash_part}"
            encoded   = urllib.parse.quote(tg_link, safe="")
            web_url   = f"https://web.telegram.org/k/#?tgaddr={encoded}"
        else:
            username = invite_url.lstrip("@")
            web_url  = f"https://web.telegram.org/k/#{username}"

        await page.goto(web_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(random.randint(3000, 5000))

        # Cherche le bouton Rejoindre
        joined = False
        for sel in ["button.btn-primary", ".popup-button.btn-primary", ".join-button", "button[class*='join']"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    txt = (await btn.inner_text()).lower()
                    if any(w in txt for w in ["join", "rejoindre", "subscribe", "abonner", "ok"]):
                        await btn.click()
                        await page.wait_for_timeout(3000)
                        joined = True
                        break
            except Exception:
                pass

        # Capture l'URL apres le join (contient le chat ID)
        final_url = page.url
        if joined:
            print(f"    [OK] Rejoint ! URL : {final_url.split('#')[-1]}")
        else:
            print(f"    [OK] Deja membre (ou bouton non trouve)")

        return final_url

    except Exception as e:
        print(f"    [X] Erreur join : {e}")
        return None


async def lire_chat(page, url: str):
    """Simule la lecture d'un chat (scroll humain)."""
    label = url.split("#")[-1] or url
    print(f"    [->] Lecture de {label}...")
    try:
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
    """Poste un message dans un groupe. Gere le topic 'talk zone' si specifie."""
    label = group_url.split("#")[-1]
    print(f"    [->] Post dans {label}" + (f" / topic '{topic}'" if topic else "") + "...")
    try:
        await page.goto(group_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(random.randint(2000, 4000))

        # Cherche le topic si demande
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

        # Pause "lecture avant ecriture" (humain)
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
    """Detecte les DMs non lus et repond avec une salutation aleatoire."""
    print("\n[->] Vérification des DMs reçus...")
    reponses = 0
    try:
        await page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        # Trouve les chats avec badge non lu (badge rouge/bleu, pas gris = muted)
        chat_items = []
        for badge_sel in [".chatlist-chat .badge:not(.badge-gray)", ".badge.badge-20"]:
            try:
                badges = page.locator(badge_sel)
                nb = await badges.count()
                for i in range(nb):
                    badge = badges.nth(i)
                    if not await badge.is_visible(timeout=500):
                        continue
                    # Remonte au li.chatlist-chat parent
                    try:
                        parent = badge.locator("xpath=ancestor::li[contains(@class,'chatlist-chat')]").first
                        chat_items.append(parent)
                    except Exception:
                        pass
            except Exception:
                pass

        if not chat_items:
            print("    [OK] Aucun DM non lu\n")
            return 0

        print(f"    [->] {len(chat_items)} chat(s) non lu(s)")

        for chat in chat_items[:5]:   # Max 5 reponses par session
            try:
                await chat.click()
                await page.wait_for_timeout(random.randint(1500, 3000))

                # Verifie que c'est un DM (peer-id positif = user, negatif = groupe)
                inp = await get_real_input(page)
                if not inp:
                    continue
                peer_id = await inp.get_attribute("data-peer-id") or ""
                if peer_id.startswith("-"):
                    continue   # Groupe — on ignore

                reponse = random.choice(DM_RESPONSES)
                print(f"    [->] Réponse : '{reponse}'")
                await type_message(page, inp, reponse)
                reponses += 1

                await page.wait_for_timeout(random.randint(12000, 25000))

            except Exception as e:
                print(f"    [X] Erreur réponse : {e}")

    except Exception as e:
        print(f"    [X] Erreur vérif DMs : {e}")

    print(f"    [OK] {reponses} réponse(s) envoyée(s)\n")
    return reponses


async def envoyer_dm(page, username: str, prenom: str) -> bool:
    """Envoie un DM 'Salut' a un non-contact."""
    print(f"    [->] DM à @{username}...")
    try:
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


# ── Main ──────────────────────────────────────────────────────

async def main():
    if "--status" in sys.argv:
        print_status()
        return
    if "--reset" in sys.argv:
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
        print("[OK] Progression remise à zéro — Jour 1 au prochain lancement.\n")
        return

    progress = load_progress()
    day = progress["day"]

    if day > 15:
        print("\n[🎉] Chauffe terminée ! Ton compte est prêt.")
        print("Lance : python -u adspower_dm.py\n")
        return

    join_count, n_lect, n_posts, n_dms = PLAN.get(day, (0, 3, 0, 0))
    bar = "█" * day + "░" * (15 - day)

    print(f"\n{'='*55}", flush=True)
    print(f"  CHAUFFE TELEGRAM — Jour {day}/15  [{bar}]", flush=True)
    print(f"  Début : {progress['start_date']}  |  Aujourd'hui : {date.today()}", flush=True)
    print(f"{'='*55}", flush=True)
    print(f"\n  Plan du Jour {day} :")
    print(f"  • {join_count} groupe(s) à rejoindre")
    print(f"  • {n_lect} chat(s) à lire")
    print(f"  • {n_posts} post(s) dans les groupes")
    print(f"  • Réponses aux DMs reçus : OUI")
    print(f"  • {n_dms} DM(s) à envoyer à des non-contacts")

    # Preparer cibles DM
    dm_targets = []
    if n_dms > 0 and os.path.exists(DM_CSV):
        already = load_already_dmed() | set(progress.get("dms_sent", []))
        with open(DM_CSV, newline="", encoding="utf-8-sig") as f:
            members = list(csv.DictReader(f))
        candidates = [m for m in members
                      if m.get("username") and m.get("bot") != "Oui"
                      and m["username"] not in already]
        dm_targets = random.sample(candidates, min(n_dms, len(candidates))) if candidates else []

    input(f"\n  Appuie sur Entrée pour lancer le Jour {day}...")
    print()

    try:
        cdp_url = start_browser()
    except Exception as e:
        print(f"[X] {e}")
        return

    nb_rep = 0
    groups_joined_today = 0
    dms_ok = 0

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        page    = context.pages[0] if context.pages else await context.new_page()

        if "web.telegram.org" not in page.url:
            print("[->] Chargement de Telegram Web...")
            await page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

        # ════════════════════════════════════════════════
        # PHASE 0 — Réponses aux DMs reçus
        # ════════════════════════════════════════════════
        nb_rep = await repondre_dms_recus(page)

        # ════════════════════════════════════════════════
        # PHASE 1 — Rejoindre des groupes (J1 → J4)
        # ════════════════════════════════════════════════
        join_idx = progress.get("join_index", 0)
        if join_count > 0 and join_idx < len(GROUPS_TO_JOIN):
            print(f"[->] Phase 1 : Rejoindre {join_count} groupe(s)\n", flush=True)
            for _ in range(join_count):
                if join_idx >= len(GROUPS_TO_JOIN):
                    break
                invite_url, is_private, topic = GROUPS_TO_JOIN[join_idx]
                final_url = await rejoindre_groupe(page, invite_url, is_private)
                if final_url:
                    if invite_url not in progress["joined_groups"]:
                        progress["joined_groups"].append(invite_url)
                    if is_private and final_url:
                        progress.setdefault("private_chat_urls", {})[invite_url] = final_url
                    join_idx += 1
                    groups_joined_today += 1
                    progress["join_index"] = join_idx
                    save_progress(progress)

                    # Post immediat dans le groupe qu'on vient de rejoindre
                    if n_posts > 0:
                        msg = random.choice(GROUP_MESSAGES)
                        await page.wait_for_timeout(random.randint(5000, 10000))
                        inp = await get_real_input(page)
                        if inp:
                            print(f"    [->] Post immédiat dans le groupe rejoint...")
                            await type_message(page, inp, msg)
                            print(f"    [OK] Posté !")

                pause = random.uniform(30, 70)
                print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                await asyncio.sleep(pause)

        # ════════════════════════════════════════════════
        # PHASE 2 — Lecture des chats
        # ════════════════════════════════════════════════
        if n_lect > 0:
            print(f"[->] Phase 2 : Lecture ({n_lect} chats)\n", flush=True)
            read_urls = [f"https://web.telegram.org/k/#{g}" for g, _ in PUBLIC_GROUPS]
            read_urls.append("https://web.telegram.org/k/#sfs_france")
            # Ajoute les chats prives rejoints precedemment
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

        # ════════════════════════════════════════════════
        # PHASE 3 — Posts dans groupes publics (J3+)
        # ════════════════════════════════════════════════
        if n_posts > 0:
            print(f"\n[->] Phase 3 : Posts ({n_posts})\n", flush=True)
            pool = PUBLIC_GROUPS.copy()
            random.shuffle(pool)
            posted = 0
            for i, (group, topic) in enumerate(pool * 3):   # *3 pour avoir assez de candidats
                if posted >= n_posts:
                    break
                url = f"https://web.telegram.org/k/#{group}"
                msg = random.choice(GROUP_MESSAGES)
                ok  = await poster_dans_groupe(page, url, msg, topic)
                if ok:
                    posted += 1
                if posted < n_posts:
                    pause = random.uniform(120, 250)
                    print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                    await asyncio.sleep(pause)

        # ════════════════════════════════════════════════
        # PHASE 4 — DMs non-contacts (J8+)
        # ════════════════════════════════════════════════
        if dm_targets:
            print(f"\n[->] Phase 4 : DMs ({len(dm_targets)})\n", flush=True)
            for i, membre in enumerate(dm_targets):
                username = membre["username"]
                prenom   = membre.get("prenom") or "toi"
                ok = await envoyer_dm(page, username, prenom)
                if ok:
                    progress["dms_sent"].append(username)
                    log_dm(username, prenom)
                    dms_ok += 1
                    save_progress(progress)
                if i < len(dm_targets) - 1:
                    pause = random.uniform(90, 160)
                    print(f"    [->] Pause {pause:.0f}s...\n", flush=True)
                    await asyncio.sleep(pause)

    stop_browser()

    progress["done_today"]    = True
    progress["last_run_date"] = str(date.today())
    save_progress(progress)

    next_msg = f"→ Reviens demain pour le Jour {day + 1} !" if day < 15 else "🎉 CHAUFFE TERMINÉE ! Lance adspower_dm.py"

    print(f"""
{'='*55}
  JOUR {day}/15 TERMINÉ  [{bar}]

  Réponses DMs reçus   : {nb_rep}
  Groupes rejoints auj : {groups_joined_today}  (total {len(progress['joined_groups'])}/8)
  Posts dans groupes   : {n_posts}
  DMs envoyés          : {dms_ok}

  Total DMs depuis J1  : {len(progress.get('dms_sent', []))}

  {next_msg}
{'='*55}
""", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
