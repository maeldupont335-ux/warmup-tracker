"""
launcher.py — Lanceur automatique au démarrage Windows
Lance tous les scripts dans des fenêtres séparées et visibles.

Scripts lancés :
  1. warmup_v2.py      — Chauffe des comptes Telegram (10 profils)
  2. spoofer.py        — Spoofer Telegram      (ajoute le chemin ci-dessous)
  3. repost.py         — Repost Telegram        (ajoute le chemin ci-dessous)
"""

import subprocess
import sys
import os
import time
import json
from datetime import date

# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON     = sys.executable

# Chemins des scripts (modifie si besoin)
WARMUP_SCRIPT  = os.path.join(SCRIPT_DIR, "warmup_v2.py")
SCRAPER_SCRIPT = os.path.join(SCRIPT_DIR, "scraper.py")
REPOST_SCRIPT  = r"C:\Users\MAEL\Downloads\AGENCY\TELEGRAM IA\main.py"

LOG_FILE = os.path.join(SCRIPT_DIR, "output", "launcher_log.txt")
# ============================================================


def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def tous_faits_aujourd_hui() -> bool:
    """Vérifie si tous les profils ont déjà fait leur session aujourd'hui."""
    profiles_file = os.path.join(SCRIPT_DIR, "profiles.txt")
    if not os.path.exists(profiles_file):
        return False
    profiles = []
    with open(profiles_file, "r", encoding="utf-8") as f:
        for line in f:
            l = line.strip()
            if l and not l.startswith("#"):
                profiles.append(l)

    today = str(date.today())
    for pid in profiles:
        pf = os.path.join(SCRIPT_DIR, "output", f"warmup_progress_{pid}.json")
        if not os.path.exists(pf):
            return False
        with open(pf, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("done_today") or data.get("last_run_date") != today:
            return False
    return True


def lancer_script(nom: str, chemin: str, args: list = None):
    """Ouvre le script dans une nouvelle fenêtre CMD visible."""
    if not chemin or not os.path.exists(chemin):
        log(f"[!] {nom} — script introuvable : {chemin or '(non configure)'}")
        return None

    script_dir = os.path.dirname(chemin)

    # Utilise le venv local si présent, sinon Python global
    venv_python = os.path.join(script_dir, "venv", "Scripts", "python.exe")
    python_exe  = venv_python if os.path.exists(venv_python) else PYTHON

    cmd = [python_exe, chemin] + (args or [])
    log(f"[->] Lancement : {nom}  ({python_exe})")

    proc = subprocess.Popen(
        cmd,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=script_dir,
    )
    return proc


def main():
    log("=" * 50)
    log(f"  LAUNCHER DEMARRE — {date.today()}")
    log("=" * 50)

    # Attente démarrage Windows (réseau, AdsPower, etc.)
    log("[->] Attente 60s pour laisser Windows demarrer completement...")
    time.sleep(60)

    # ── 1. Repost / surveillance canal (tourne en permanence) ──
    lancer_script("Repost Telegram", REPOST_SCRIPT)
    time.sleep(5)

    # ── 2. Warm-up (1 session par jour par profil) ─────────────
    if tous_faits_aujourd_hui():
        log("[OK] Warm-up : tous les profils deja traites aujourd'hui — skip")
    else:
        lancer_script("Warm-up Telegram", WARMUP_SCRIPT)
        time.sleep(3)

    # ── 3. Scraper membres (optionnel) ─────────────────────────
    # lancer_script("Scraper Telegram", SCRAPER_SCRIPT)  # Decommente si besoin

    log("[OK] Tous les scripts lancés.")


if __name__ == "__main__":
    main()
