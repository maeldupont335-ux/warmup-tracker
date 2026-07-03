import argparse
import json
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path

Path("logs").mkdir(exist_ok=True)
Path("state").mkdir(exist_ok=True)

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add("logs/warmup.log", rotation="1 day", retention="7 days", level="DEBUG",
           format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}")

import wda

from config import WDA_URL, LOW_BATTERY_THRESHOLD, STATE_FILE
from warmup_plan import get_plan_for_day
from scheduler import WarmupScheduler
from actions.snapchat import SnapchatDriver
from actions.human import delay, action_delay, long_pause, shuffle_actions, random_count, should_pause
from filters.names import is_french_male, load_names

STATE_PATH = Path(STATE_FILE)
DEFAULT_STATE = {
    "current_day": 1,
    "session_today": 0,
    "total_sessions": 0,
    "friends_added_today": 0,
    "friends_accepted_today": 0,
    "last_session_time": None,
    "start_date": None,
}


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    s = DEFAULT_STATE.copy()
    s["start_date"] = date.today().isoformat()
    return s


def save_state(state: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def _advance_day(state: dict) -> dict:
    if state["session_today"] >= 2:
        state["current_day"] = min(state["current_day"] + 1, 15)
        state["session_today"] = 0
        state["friends_added_today"] = 0
        state["friends_accepted_today"] = 0
        logger.info(f"Passage au jour {state['current_day']}")
    return state


def run_session(session_name: str = "manual", force_day: int = None):
    state = load_state()
    if force_day is not None:
        state["current_day"] = force_day

    day = state["current_day"]
    plan = get_plan_for_day(day)

    logger.info(f"╔══ Session [{session_name}] — Jour {day}/15 ══╗")
    logger.info(f"Plan: {plan.session_duration[0]}-{plan.session_duration[1]} min")

    load_names()

    client = None
    snap = None
    try:
        client = wda.Client(WDA_URL)
        snap = SnapchatDriver(client)

        battery = snap.check_battery()
        if battery < LOW_BATTERY_THRESHOLD:
            logger.warning(f"Batterie {battery}% — session annulée")
            return

        snap.open_snapchat()

        # Construction de la liste d'actions
        actions = []
        if plan.spotlight_videos:
            actions.append(("spotlight", random_count(plan.spotlight_videos)))
        if plan.stories_friends:
            actions.append(("stories", random_count(plan.stories_friends)))
        if plan.open_convos:
            actions.append(("convos", random_count(plan.open_convos)))
        if plan.send_snaps and plan.send_snaps[1] > 0:
            actions.append(("snap", random_count(plan.send_snaps)))
        if plan.post_story and state["session_today"] == 0:
            actions.append(("story", 1))

        actions = shuffle_actions(actions)

        start = datetime.now()
        target_s = random.uniform(*plan.session_duration) * 60

        for action_name, count in actions:
            if (datetime.now() - start).total_seconds() >= target_s:
                break
            if should_pause(0.12):
                long_pause()
            try:
                if action_name == "spotlight":
                    snap.browse_spotlight(count)
                elif action_name == "stories":
                    snap.browse_friend_stories(count)
                elif action_name == "convos":
                    snap.browse_conversations(count)
                elif action_name == "snap":
                    snap.send_snap(count)
                elif action_name == "story":
                    snap.post_story()
            except Exception as e:
                logger.error(f"Erreur action '{action_name}': {e}")
            action_delay()

        # Acceptation amis (budget quotidien)
        if plan.accept_friends_per_day and plan.accept_friends_per_day[1] > 0:
            daily_max = random_count(plan.accept_friends_per_day)
            remaining = max(0, daily_max - state["friends_accepted_today"])
            if remaining > 0:
                n = snap.accept_friend_requests(remaining, is_french_male)
                state["friends_accepted_today"] += n

        # Ajout rapide (par session)
        if plan.quick_add_per_session and plan.quick_add_per_session[1] > 0:
            n = snap.quick_add_friends(random_count(plan.quick_add_per_session), is_french_male)
            state["friends_added_today"] += n

        # Remplir le temps restant avec de la micro-activité
        while (datetime.now() - start).total_seconds() < target_s:
            snap.micro_activity()
            delay(30, 90)

        state["session_today"] += 1
        state["total_sessions"] += 1
        state["last_session_time"] = datetime.now().isoformat()
        if not state["start_date"]:
            state["start_date"] = date.today().isoformat()
        state = _advance_day(state)
        save_state(state)

        dur = (datetime.now() - start).total_seconds() / 60
        logger.info(f"╚══ Terminé — {dur:.1f} min | ajoutés: {state['friends_added_today']} | acceptés: {state['friends_accepted_today']} ══╝")

    except Exception as e:
        logger.error(f"Erreur critique: {e}", exc_info=True)
        if any(k in str(e).lower() for k in ("connection", "refused", "timeout")):
            logger.critical("WDA inaccessible — vérifie que tidevice xctest tourne")
        raise
    finally:
        if snap and snap.s:
            try:
                snap.s.close()
            except Exception:
                pass


def cmd_status():
    state = load_state()
    plan = get_plan_for_day(state["current_day"])
    print(f"\n{'─'*42}")
    print(f"  Warm-up Snapchat")
    print(f"{'─'*42}")
    print(f"  Jour           : {state['current_day']}/15")
    print(f"  Sessions/jour  : {state['session_today']}/2")
    print(f"  Total sessions : {state['total_sessions']}")
    print(f"  Amis ajoutés   : {state['friends_added_today']}")
    print(f"  Amis acceptés  : {state['friends_accepted_today']}")
    print(f"  Dernière session: {state['last_session_time'] or 'aucune'}")
    print(f"  Démarré le     : {state['start_date'] or '-'}")
    print(f"\n  Plan jour {state['current_day']}:")
    print(f"    Durée          : {plan.session_duration[0]}-{plan.session_duration[1]} min")
    print(f"    Spotlight      : {plan.spotlight_videos} vidéos")
    print(f"    Stories        : {plan.stories_friends} amis")
    print(f"    Accepter/jour  : {plan.accept_friends_per_day}")
    print(f"    Ajout rapide/s : {plan.quick_add_per_session}")
    print(f"    Conversations  : {plan.open_convos}")
    print(f"    Snaps          : {plan.send_snaps}")
    print(f"    Story          : {'oui' if plan.post_story else 'non'}")
    print(f"{'─'*42}\n")


def cmd_reset():
    rep = input("Confirme le reset (oui/non) : ").strip().lower()
    if rep == "oui":
        s = DEFAULT_STATE.copy()
        s["start_date"] = date.today().isoformat()
        save_state(s)
        logger.info("État remis à zéro")
    else:
        print("Annulé")


def main():
    parser = argparse.ArgumentParser(description="Snapchat Warm-up — iOS via WDA")
    parser.add_argument("--start", action="store_true", help="Scheduler automatique 2x/jour")
    parser.add_argument("--status", action="store_true", help="Voir l'état")
    parser.add_argument("--session", metavar="now", help="Forcer une session (valeur: now)")
    parser.add_argument("--day", type=int, metavar="N", help="Simuler le jour N (1-15)")
    parser.add_argument("--reset", action="store_true", help="Remettre à zéro")
    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.reset:
        cmd_reset()
    elif args.session == "now" or (args.day is not None and not args.start):
        run_session("manual", force_day=args.day)
    elif args.start:
        logger.info("Démarrage scheduler automatique (Ctrl+C pour arrêter)")
        WarmupScheduler(lambda name: run_session(session_name=name)).run_blocking()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
