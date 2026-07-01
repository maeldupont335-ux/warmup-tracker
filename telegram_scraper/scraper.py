"""
Telegram Member Scraper — Mode daemon (auto)
Tourne en arrière-plan et scrape automatiquement dès qu'un canal
est marqué "A scraper" via le bouton du dashboard.

Lance une seule fois : python scraper.py
"""

import asyncio
import csv
import os
import sys
import time
from datetime import datetime

import requests
from telethon import TelegramClient
from telethon.errors import (
    ChatAdminRequiredError,
    FloodWaitError,
    PeerFloodError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import GetParticipantsRequest, GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, GetExportedChatInvitesRequest, ExportChatInviteRequest
from telethon.tl.types import PeerUser, InputUserSelf, User, Channel
from telethon.tl.types import (
    ChannelParticipantsSearch,
    UserStatusEmpty,
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

from config import API_ID, API_HASH, PHONE, TARGET, TRACKING_CHANNEL, OUTPUT_CSV, DELAY, FILTER_MALE_ONLY

# ── Détection genre par prénom ─────────────────────────────
PRENOMS_MASCULINS = {
    # Français classiques
    "aaron","adam","adrien","alexandre","alexis","ali","allan","alvin","amine","anatole",
    "andre","antoine","arnaud","arthur","aurelien","axel","ayoub","aziz",
    "baptiste","benjamin","benoit","bilal","boris","brendan","bryan",
    "charles","christophe","clement","colin","corentin","cyril","cyrus",
    "damien","daniel","david","dimitri","dorian","dylan",
    "edouard","emile","enzo","eric","ethan","etienne","evan",
    "fabien","florian","francois","fred","frederic",
    "gabriel","gaetan","gauthier","geoffrey","georges","gerald","gilbert","guillaume","gilles",
    "hamza","hugo","hassan",
    "ibrahim","ilyes","isaac",
    "jack","jacky","james","jean","jeremy","jerome","jimmy","jonathan","jordan","julien","justin",
    "karim","kylian","kevin","kenny",
    "laurent","leo","leonard","liam","lionel","loic","luca","lucas","ludovic","lukas","lyes",
    "malik","marc","martin","mathieu","mathis","matteo","maxime","maximus","mehdi","michael","michel","milan","mohammed","morgan",
    "nathan","nicolas","noah","noel","noam",
    "oliver","olivier","omar",
    "pascal","patrick","paul","paulin","peter","philippe","pierre","pierre-louis","pierre-alexandre",
    "quentin",
    "rayan","remi","renaud","richard","robin","romain","ryan",
    "sam","samuel","samy","sebastien","simon","sofiane","stan","stefan","stephane","steven","swan",
    "theo","thomas","thibault","thibaut","titouan","tom","tony","tristan",
    "valentin","victor","vincent","vivien","wael","william","xavier","yanis","yann","yannick","yoann","yohan","youssef","zakariya",
    # Prénoms courts / surnoms masculins courants
    "alex","max","tom","leo","luc","ben","mat","raph","fab","greg","nico","jul","remi","pat",
    "jo","jojo","dado","nono","momo","kiki","dede","brice","gab","seb","toto","polo",
    # Anglais / internationaux masculins courants
    "james","john","robert","michael","william","david","richard","joseph","charles","thomas",
    "christopher","daniel","paul","mark","donald","george","ken","kevin","brian","edward",
    "jason","ryan","jacob","nicholas","eric","stephen","andrew","joshua","kenneth","timothy",
    "brandon","frank","raymond","gregory","samuel","benjamin","frank","scott","tyler","jack",
    "jake","zach","chris","matt","jeff","mike","steve","tony","billy","bobby","johnny",
    # Arabes / nord-africains masculins
    "ahmed","ali","hamza","hassan","hussein","ibrahim","ismael","karim","khalid","mehdi",
    "mohammed","mouhamed","moussa","mustafa","omar","rachid","rayan","sami","sofiane",
    "tariq","walid","yassine","youcef","youssef","zakariya","ziad",
    # Africains masculins courants
    "amadou","babou","cheikh","daouda","ibrahima","lamine","mamadou","modou","oumar","sekou",
}

def is_male(prenom: str) -> bool:
    """Retourne True si le prénom semble masculin. Si inconnu → True (garder par défaut)."""
    if not prenom:
        return True   # pas de prénom = on garde (pas de DM personnalisé de toute façon)
    name = prenom.lower().strip().split()[0]  # prendre juste le premier prénom
    # Supprimer accents pour comparaison
    import unicodedata
    name_norm = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    # Vérifier dans la liste
    if name_norm in PRENOMS_MASCULINS or name in PRENOMS_MASCULINS:
        return True
    # Terminaisons typiquement féminines françaises → exclure
    SUFFIXES_FEMININS = ("ine","ette","elle","ine","ise","ise","ane","ène","ène",
                         "ille","ille","otte","otte","erie","ery","aly","aly",
                         "alie","alie","elia","elia","aria","aria","inia","inia")
    if name_norm.endswith(SUFFIXES_FEMININS):
        return False
    return True   # inconnu → on garde


# Log partagé des DMs (écrit par warmup_v2.py)
DM_LOG_SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "dm_log_shared.csv")

# ── Dashboard ──────────────────────────────────────────────
DASHBOARD_URL   = "https://warmup-tracker.onrender.com"
DASHBOARD_TOKEN = "Compte.1"
POLL_INTERVAL   = 30   # secondes entre deux vérifications
# ───────────────────────────────────────────────────────────


def format_status(status) -> str:
    if isinstance(status, UserStatusOnline):     return "En ligne"
    if isinstance(status, UserStatusRecently):   return "Recemment"
    if isinstance(status, UserStatusLastWeek):   return "La semaine derniere"
    if isinstance(status, UserStatusLastMonth):  return "Le mois dernier"
    if isinstance(status, UserStatusOffline):
        return status.was_online.strftime("%Y-%m-%d %H:%M") if status.was_online else "Hors ligne"
    return "Inconnu"


def is_active_recently(status) -> bool:
    """
    Retourne True uniquement si le membre est actif récemment :
      ✓ En ligne maintenant
      ✓ Vu récemment (< 1 semaine)
      ✓ Vu cette semaine
      ✓ Vu ce mois-ci (< 30 jours)
      ✗ Hors ligne depuis plus de 30 jours → exclu
      ✗ Inconnu / vide → exclu
    """
    if isinstance(status, UserStatusOnline):    return True
    if isinstance(status, UserStatusRecently):  return True
    if isinstance(status, UserStatusLastWeek):  return True
    if isinstance(status, UserStatusLastMonth): return True
    if isinstance(status, UserStatusOffline):
        if status.was_online:
            from datetime import timezone
            delta = datetime.now(timezone.utc) - status.was_online
            return delta.days <= 30
        return False
    return False


def parse_user(user) -> dict:
    return {
        "id":        str(user.id),
        "username":  user.username or "",
        "prenom":    user.first_name or "",
        "nom":       user.last_name or "",
        "telephone": user.phone or "",
        "bot":       "Oui" if user.bot else "Non",
        "verifie":   "Oui" if user.verified else "Non",
        "statut":    format_status(user.status),
        "scrape_le": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def load_pending_channels() -> list:
    """Charge uniquement les canaux marqués 'A scraper' depuis le dashboard."""
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/channels", timeout=10)
        if r.status_code == 200:
            all_ch = r.json()
            pending = [c for c in all_ch if c.get("status") == "A scraper"]
            return pending
    except Exception as e:
        print(f"[!] Erreur dashboard : {e}")
    return []


def update_channel_status(channel_id: int, status: str, members_count: int = 0):
    """Met à jour le statut d'un canal sur le dashboard."""
    try:
        requests.post(
            f"{DASHBOARD_URL}/api/channel/update",
            json={
                "token":          DASHBOARD_TOKEN,
                "channel_id":     channel_id,
                "status":         status,
                "members_count":  members_count,
            },
            timeout=10,
        )
    except Exception:
        pass


def normalize_target(url: str) -> str:
    """Convertit une URL t.me ou @username en cible Telethon.
    Les liens privés (t.me/+HASH) sont retournés tels quels."""
    url = url.strip()
    if "t.me/+" in url:
        return url   # lien privé — géré séparément dans scrape_channel
    if "t.me/" in url:
        slug = url.split("t.me/")[-1].rstrip("/").split("/")[0]
        return f"@{slug}"
    if url.startswith("@"):
        return url
    return f"@{url}"


def get_invite_hash(url: str) -> str:
    """Extrait le hash d'un lien d'invitation privé t.me/+HASH."""
    return url.split("t.me/+")[-1].rstrip("/")


# Nombre de posts récents à analyser pour les réactions / messages
REACTION_POST_LIMIT = 100
MESSAGE_MONTHS_BACK = 6       # scraper les messages des X derniers mois


async def scrape_via_reactions(client: TelegramClient, entity) -> list:
    """
    Scrape les membres via leurs réactions aux posts récents.
    Utilise message.reactions.recent_reactions — aucune API supplémentaire requise.
    Fonctionne sur les canaux privés SANS droits admin.
    """
    title = getattr(entity, "title", str(entity.id))
    print(f"  [->] Mode réactions — analyse des {REACTION_POST_LIMIT} derniers posts de : {title}")

    seen = {}       # user_id → dict
    posts_analysed  = 0
    resolve_errors  = 0

    async for message in client.iter_messages(entity, limit=REACTION_POST_LIMIT):
        if not message.reactions or not message.reactions.results:
            continue

        total_r = sum(r.count for r in message.reactions.results)
        posts_analysed += 1

        # recent_reactions contient les derniers reacteurs (inclus dans la réponse)
        recent = getattr(message.reactions, "recent_reactions", None) or []
        print(f"  [i] Post {message.id} — {total_r} réaction(s), {len(recent)} récents visibles")

        for reaction_info in recent:
            try:
                peer = reaction_info.peer_id
                if not isinstance(peer, PeerUser):
                    continue
                if peer.user_id in seen:
                    continue
                user = await client.get_entity(peer)
                if user.bot:
                    continue
                seen[user.id] = parse_user(user)
            except FloodWaitError as e:
                print(f"\n  [!] Rate-limit — attente {e.seconds}s...")
                await asyncio.sleep(e.seconds)
            except Exception:
                resolve_errors += 1

        print(f"  [{posts_analysed} posts analysés] {len(seen)} membres collectés...", end="\r")
        await asyncio.sleep(0.5)

    members = list(seen.values())
    print(f"\n  [OK] {len(members)} membres récupérés via réactions ({posts_analysed} posts)")
    if resolve_errors:
        print(f"  [i] {resolve_errors} profil(s) anonymes ignorés (privacy Telegram)")
    return members


async def _iter_participants_on_group(client: TelegramClient, entity) -> dict:
    """Lance le trick alphabet sur un supergroup. Retourne un dict user_id → dict."""
    seen = {}
    queries = list("abcdefghijklmnopqrstuvwxyzéèêëàâùûôîïç0123456789") + [""]
    print(f"  [->] Alphabet trick sur groupe lié ({len(queries)} passes)...")
    for q in queries:
        try:
            async for user in client.iter_participants(entity, search=q):
                if user.id in seen or user.is_self or user.bot:
                    continue
                seen[user.id] = parse_user(user)
            await asyncio.sleep(0.8)
        except FloodWaitError as e:
            if e.seconds > 60:
                print(f"\n  [!] FloodWait {e.seconds}s sur alphabet — arrêt alphabet")
                break
            await asyncio.sleep(e.seconds)
        except Exception:
            continue
    print(f"\n  [OK] {len(seen)} membres via alphabet groupe lié")
    return seen


async def scrape_via_messages(client: TelegramClient, entity) -> list:
    """
    Scrape les membres via les messages des 6 derniers mois.
    Chaque auteur de message = membre récupéré même sans username visible.
    """
    from datetime import timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * MESSAGE_MONTHS_BACK)

    title = getattr(entity, "title", str(entity.id))
    print(f"  [->] Mode messages : {title} (6 derniers mois depuis {cutoff.strftime('%d/%m/%Y')})")

    seen = {}
    msg_count = 0

    try:
        async for message in client.iter_messages(entity, limit=None):
            # Stopper quand on dépasse 6 mois
            if message.date and message.date.replace(tzinfo=timezone.utc) < cutoff:
                break
            msg_count += 1
            sender_id = getattr(message, "sender_id", None)
            if not sender_id or sender_id in seen:
                continue
            sender = getattr(message, "sender", None)
            if sender is None or not hasattr(sender, "first_name"):
                continue
            if getattr(sender, "bot", False) or getattr(sender, "is_self", False):
                continue
            seen[sender_id] = parse_user(sender)
            if msg_count % 200 == 0:
                print(f"  [{msg_count} msgs analysés — {len(seen)} membres trouvés]", end="\r")
    except FloodWaitError as e:
        print(f"\n  [!] FloodWait {e.seconds}s — pause...")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print(f"\n  [i] Fin messages : {e}")

    members = list(seen.values())
    print(f"\n  [OK] {len(members)} membres récupérés via messages ({msg_count} msgs parcourus)")
    return members


async def scrape_channel(client: TelegramClient, target: str) -> list:
    """Scrappe les membres actifs (≤30j) d'un canal. Retourne une liste de dicts.
    Gère automatiquement les canaux privés via lien d'invitation (t.me/+HASH)."""
    print(f"\n  [->] Résolution : {target}")

    entity = None

    # ── Canal privé (lien d'invitation t.me/+HASH) ────────────
    if "t.me/+" in target:
        invite_hash = get_invite_hash(target)
        print(f"  [->] Canal privé détecté — hash : {invite_hash}")

        entity = None

        # Étape 1 : essayer de rejoindre
        try:
            result = await client(ImportChatInviteRequest(invite_hash))
            entity = result.chats[0]
            print(f"  [OK] Rejoint : {entity.title}")
        except UserAlreadyParticipantError:
            print(f"  [OK] Déjà membre — recherche dans les conversations...")
            # Étape 2 : déjà membre → chercher dans les dialogs récents
            try:
                async for dialog in client.iter_dialogs(limit=300):
                    if dialog.is_channel and not dialog.entity.username:
                        entity = dialog.entity
                        print(f"  [OK] Canal trouvé : {entity.title}")
                        break
            except Exception as e2:
                print(f"  [X] Erreur dialogs : {e2}")
        except Exception as e:
            print(f"  [X] Impossible de rejoindre : {e}")
            return []

        if entity is None:
            print(f"  [X] Canal introuvable — vérifie que le compte est bien membre")
            return []

        # Canal privé → tenter GetParticipantsRequest (fonctionne si admin)
        # Le fallback réactions s'active automatiquement si ChatAdminRequiredError
        print(f"  [->] Canal privé trouvé : {entity.title} — tentative scraping membres...")
    else:
        # ── Canal public ──────────────────────────────────────
        try:
            entity = await client.get_entity(target)
        except Exception as e:
            print(f"  [X] Canal introuvable ({target}) : {e}")
            return []



    title = getattr(entity, "title", target)
    print(f"  [OK] Connecté à : {title}")

    seen    = {}   # user_id → dict (dédoublonnage)
    queries = (
        list("abcdefghijklmnopqrstuvwxyz") +
        # Accents français / espagnol / portugais
        list("éèêëàâùûôîïçãõñü") +
        # Cyrillique (russe)
        list("абвгдежзийклмнопрстуфхцчшщыьэюя") +
        # Arabe (lettres les plus communes en début de prénom)
        list("محاسعبيكرلفزودنتش") +
        # Chiffres et symboles
        list("0123456789") +
        ["_", " ", ""]   # "" = sans filtre (récents d'abord)
    )
    # Dédoublonner en gardant l'ordre
    seen_q = set()
    queries = [q for q in queries if not (q in seen_q or seen_q.add(q))]

    print(f"  [i] Scraping multi-alphabet ({len(queries)} passes) — cela peut prendre quelques minutes...")

    for q in queries:
        label = repr(q) if q else "défaut"
        try:
            batch = 0
            async for user in client.iter_participants(entity, search=q):
                if user.id in seen or user.is_self or user.bot:
                    continue
                if is_active_recently(user.status):
                    seen[user.id] = parse_user(user)
                batch += 1
            print(f"  ['{label}'] +{batch} → {len(seen)} membres uniques", end="\r")
            await asyncio.sleep(DELAY)

        except ChatAdminRequiredError:
            print(f"\n  [i] Accès membres refusé — bascule sur messages...")
            return await scrape_via_messages(client, entity)
        except FloodWaitError as e:
            if e.seconds > 60:
                print(f"\n  [!] FloodWait {e.seconds}s trop long — bascule sur messages...")
                return await scrape_via_messages(client, entity)
            print(f"\n  [!] Rate-limit — attente {e.seconds}s...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"\n  [i] Passe '{label}' ignorée : {e}")
            continue

    members = list(seen.values())
    print(f"\n  [OK] {len(members)} membres actifs récents (≤30j) — depuis {title}")

    # Si trop peu de membres (privacy Telegram), compléter via messages
    if len(members) < 50:
        print(f"  [i] Seulement {len(members)} membres visibles — bascule sur scraping par messages...")
        msg_members = await scrape_via_messages(client, entity)
        # Fusionner sans doublons
        existing_ids = {m["id"] for m in members}
        for m in msg_members:
            if m["id"] not in existing_ids:
                members.append(m)
                existing_ids.add(m["id"])
        print(f"  [OK] Total après fusion : {len(members)} membres")

    return members


def save_csv(members: list, path: str) -> None:
    if not members:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Ajoute au fichier existant (sans dupliquer les headers)
    file_exists = os.path.isfile(path)
    with open(path, "a" if file_exists else "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=members[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(members)
    print(f"[OK] CSV mis à jour : {path}  ({len(members)} membres ajoutés)")


async def run_scraping_session(client: TelegramClient, channels: list):
    """Scrappe tous les canaux de la liste et sauvegarde le CSV."""
    all_members = {}   # user_id → dict (dédoublonnage par ID, garde même sans username)
    total = len(channels)

    for idx, channel in enumerate(channels, 1):
        cid    = channel["id"]
        url    = channel["url"]
        target = normalize_target(url)

        print(f"\n{'='*58}")
        print(f"  Canal {idx}/{total} : {url}")
        print(f"{'='*58}")

        update_channel_status(cid, "En cours")

        members = await scrape_channel(client, target)

        if members:
            update_channel_status(cid, "Scrappe", len(members))
            for m in members:
                uid = m["id"]
                if uid and uid not in all_members:
                    all_members[uid] = m
        else:
            update_channel_status(cid, "Erreur", 0)

        if idx < total:
            print(f"\n[->] Pause 5s avant le canal suivant...")
            await asyncio.sleep(5)

    final_members = list(all_members.values())

    # ── Filtre hommes uniquement ──────────────────────────────
    if FILTER_MALE_ONLY:
        avant = len(final_members)
        final_members = [m for m in final_members if is_male(m.get("prenom", ""))]
        print(f"\n  [♂] Filtre hommes : {avant} → {len(final_members)} membres gardés")

    print(f"\n{'='*58}")
    print(f"  Scraping terminé ! {len(final_members)} membres uniques")
    print(f"{'='*58}")

    if final_members:
        save_csv(final_members, OUTPUT_CSV)
        print(f"  Fichier : {OUTPUT_CSV}")


async def main():
    if not API_ID or not API_HASH or not PHONE:
        print("[X] Configure API_ID, API_HASH et PHONE dans config.py")
        sys.exit(1)

    print("=" * 58)
    print("  Telegram Scraper — Mode Daemon (auto)")
    print(f"  Vérification toutes les {POLL_INTERVAL}s")
    print("=" * 58)

    # ── Connexion Telethon (une seule fois au démarrage) ───
    client = TelegramClient("session_scraper", API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"\n[OK] Connecté : {me.first_name} (@{me.username})")

    # ── Rejoindre et mémoriser le canal de tracking ───────────
    _tracking_entity = None
    if TRACKING_CHANNEL and "t.me/+" in TRACKING_CHANNEL:
        invite_hash = get_invite_hash(TRACKING_CHANNEL)
        try:
            result = await client(ImportChatInviteRequest(invite_hash))
            _tracking_entity = result.chats[0]
            print(f"[OK] Rejoint le canal de tracking : {_tracking_entity.title}")
        except UserAlreadyParticipantError:
            # Déjà membre → retrouver via dialogs
            async for dialog in client.iter_dialogs(limit=300):
                if dialog.is_channel and not getattr(dialog.entity, "username", None):
                    _tracking_entity = dialog.entity
                    print(f"[OK] Canal de tracking : {_tracking_entity.title}")
                    break
        except Exception as e:
            print(f"[i] Canal de tracking : {e}")

    print(f"[OK] En attente de canaux à scrapper sur le dashboard...\n")
    print("     → Va sur le dashboard, clique '🔍 Scraper' sur les canaux voulus")
    print("     → Ce script les détectera automatiquement et lancera le scraping")
    print("     → Ctrl+C pour arrêter\n")

    # ── Tracking conversion : vérif toutes les 30 min ─────
    TRACKING_URL    = TRACKING_CHANNEL   # canal avec les liens d'invitation Mass DM
    TRACKING_EVERY  = 60       # minutes entre chaque check
    _tracking_ticks = 0        # compteur de cycles (1 cycle = POLL_INTERVAL s)
    _ticks_per_check = int(TRACKING_EVERY * 60 / POLL_INTERVAL)

    async def check_conversion_tracking():
        """
        Lit les statistiques des liens d'invitation du canal de tracking
        (MESSAGE 1, MESSAGE 2...) et les envoie au dashboard.
        Nécessite d'être admin du canal.
        """
        entity = _tracking_entity
        if entity is None:
            print(f"\n[i] Tracking : canal non trouvé — relance scraper.py")
            return
        try:

            # Récupérer tous les liens d'invitation exportés
            result = await client(GetExportedChatInvitesRequest(
                peer=entity,
                admin_id=InputUserSelf(),
                revoked=False,
                limit=100,
            ))

            links_data = []
            total_joins = 0
            for inv in result.invites:
                title  = getattr(inv, 'title', '') or inv.link
                joins  = getattr(inv, 'usage', 0) or 0
                link   = inv.link
                total_joins += joins
                links_data.append({
                    "title": title,
                    "link":  link,
                    "joins": joins,
                })

            # Compter les DMs par template depuis dm_log_shared.csv
            dms_per_template = {}   # {"MESSAGE 1": 500, "MESSAGE 2": 487, ...}
            dms_sent_total   = 0
            if os.path.exists(DM_LOG_SHARED):
                import csv as _csv
                with open(DM_LOG_SHARED, newline="", encoding="utf-8-sig") as f:
                    for row in _csv.DictReader(f):
                        if row.get("statut") != "envoye":
                            continue
                        dms_sent_total += 1
                        tpl = (row.get("template") or "").strip()
                        if tpl:
                            dms_per_template[tpl] = dms_per_template.get(tpl, 0) + 1

            # Enrichir links_data avec le nb de DMs par template
            for lk in links_data:
                lk["dms_sent"] = dms_per_template.get(lk["title"], 0)
                dms_lk = lk["dms_sent"] or 1
                lk["conv_rate"] = round(lk["joins"] / dms_lk * 100, 1) if lk["dms_sent"] > 0 else 0

            # Envoyer au dashboard
            requests.post(f"{DASHBOARD_URL}/api/massdm/tracking/update", json={
                "token":        DASHBOARD_TOKEN,
                "links":        links_data,
                "total_joins":  total_joins,
                "dms_sent":     dms_sent_total,
            }, timeout=10)

            print(f"\n[📊] Tracking : {len(links_data)} liens | {total_joins} joins | {dms_sent_total} DMs")
            for lk in sorted(links_data, key=lambda x: -x["joins"]):
                rate = lk.get("conv_rate", 0)
                print(f"     {lk['title']:<12} {lk['dms_sent']:>5} DMs → {lk['joins']:>4} joins ({rate}%)")

        except Exception as e:
            print(f"\n[i] Tracking ignoré : {e}")

    # ── Création automatique des liens en attente ─────────────
    async def create_pending_invite_links():
        """Crée les liens d'invitation pour les nouveaux templates détectés."""
        try:
            r = requests.get(f"{DASHBOARD_URL}/api/massdm/pending-links", timeout=5)
            if not r.ok:
                return
            pending = r.json().get("pending", [])
            if not pending:
                return

            entity = _tracking_entity
            if entity is None:
                return

            done = []
            for name in pending:
                try:
                    inv = await client(ExportChatInviteRequest(
                        peer=entity,
                        title=name,
                        request_needed=True,
                    ))
                    _invite_links_local[name] = inv.link
                    done.append(name)
                    print(f"\n[🔗] Lien créé : {name} → {inv.link}")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"\n[i] Lien {name} : {e}")

            if done:
                # Envoyer les nouveaux liens au dashboard
                requests.post(f"{DASHBOARD_URL}/api/massdm/invite-links/set", json={
                    "token": DASHBOARD_TOKEN,
                    "links": _invite_links_local,
                }, timeout=5)
                # Confirmer que c'est fait
                requests.post(f"{DASHBOARD_URL}/api/massdm/pending-links/clear", json={
                    "token": DASHBOARD_TOKEN,
                    "done":  done,
                }, timeout=5)
        except Exception as e:
            print(f"\n[i] Pending links : {e}")

    _invite_links_local = {}   # cache local des liens créés

    # ── Premier check immédiat au démarrage ───────────────────
    print(f"[📊] Récupération initiale des stats de liens d'invitation...")
    await check_conversion_tracking()

    # ── Boucle daemon ──────────────────────────────────────
    try:
        while True:
            pending = load_pending_channels()

            if pending:
                print(f"\n[🔍] {len(pending)} canal(aux) détecté(s) — démarrage du scraping...")
                await run_scraping_session(client, pending)
                print(f"\n[OK] Session terminée. Reprise surveillance dans {POLL_INTERVAL}s...\n")
            else:
                print(f"  [·] {datetime.now().strftime('%H:%M:%S')} — En attente de canaux à scrapper...", end="\r")

            # Créer les liens en attente (nouveaux templates)
            await create_pending_invite_links()

            # Check conversion toutes les 30 min
            _tracking_ticks += 1
            if _tracking_ticks >= _ticks_per_check:
                _tracking_ticks = 0
                await check_conversion_tracking()

            await asyncio.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n[OK] Scraper arrêté.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
