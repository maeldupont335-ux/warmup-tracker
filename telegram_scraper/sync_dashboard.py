"""
sync_dashboard.py — Synchronise la progression locale vers le dashboard Render
Lance ce script une fois pour mettre à jour toutes les données sur le site.

Usage :
  python sync_dashboard.py
"""

import json
import os
import requests

DASHBOARD_URL   = "https://warmup-tracker.onrender.com"
DASHBOARD_TOKEN = "Compte.1"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_profiles() -> list:
    path = os.path.join(SCRIPT_DIR, "profiles.txt")
    profiles = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            l = line.strip()
            if l and not l.startswith("#"):
                profiles.append(l)
    return profiles

def push(pid: str, data: dict):
    payload = {
        "token":         DASHBOARD_TOKEN,
        "profile_id":    pid,
        "day":           data.get("day", 1),
        "start_date":    data.get("start_date"),
        "done_today":    data.get("done_today", False),
        "dms_total":     len(data.get("dms_sent", [])),
        "posts_total":   data.get("posts_total", 0),
        "groups_joined": len(data.get("joined_groups", [])),
        "dm_responses":  0,
        "dms_session":   0,
        "posts_session": 0,
    }
    try:
        r = requests.post(f"{DASHBOARD_URL}/api/update", json=payload, timeout=30)
        if r.status_code == 200:
            print(f"  [OK] {pid} -> Jour {data.get('day',1)}/15 | DMs: {payload['dms_total']} | Groupes: {payload['groups_joined']}/8")
        else:
            print(f"  [X] {pid} -> Erreur {r.status_code}")
    except Exception as e:
        print(f"  [X] {pid} -> {e}")

def main():
    profiles = load_profiles()
    print(f"\n Synchronisation de {len(profiles)} profils vers le dashboard...\n")

    for pid in profiles:
        pf = os.path.join(SCRIPT_DIR, "output", f"warmup_progress_{pid}.json")
        if os.path.exists(pf):
            with open(pf, "r", encoding="utf-8") as f:
                data = json.load(f)
            push(pid, data)
        else:
            print(f"  [!] {pid} -> Pas encore de progression (Jour 1 non commencé)")

    print(f"\n[OK] Synchronisation terminée. Actualise le dashboard :\n     {DASHBOARD_URL}\n")

if __name__ == "__main__":
    main()
