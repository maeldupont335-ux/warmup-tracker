C:\Users\MAEL\Downloads\higgsfield-batch\higgsfield-batch\telegram_scraper\dashboard\main.py"""
Dashboard warm-up tracker — FastAPI + Supabase
POST /api/update       → reçoit les données du script warmup_v2.py
POST /api/massdm       → reçoit les données du script mass DM
GET  /                 → dashboard Warm-Up
GET  /massdm           → dashboard Mass DM
GET  /api/status       → JSON warm-up
GET  /api/massdm/status → JSON mass DM
"""

import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SECRET_TOKEN = os.environ.get("DASHBOARD_TOKEN", "Compte.1")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://pirlgavzihmnwmqlyeir.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_MEhlBNL3fXiY72GgvQ7qZQ_8HLkKCHV")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

PROFILE_IDS = [
    "k1csfeja", "k1cup0ch", "k1cup0ci", "k1cup0cj",
    "k1cup0ck", "k1cup0cl", "k1cvbnrr",
]

NAV = """
<div class="nav">
  <a href="/" class="{cls_warmup}">Warm-Up</a>
  <a href="/massdm" class="{cls_massdm}">Mass DM</a>
</div>
"""

NAV_CSS = """
  .nav {
    display: flex; gap: 8px; margin-bottom: 28px;
  }
  .nav a {
    padding: 8px 20px; border-radius: 8px; font-weight: 600;
    font-size: .875rem; text-decoration: none; border: 1px solid #334155;
    color: #94a3b8; transition: all .15s;
  }
  .nav a.active {
    background: #22c55e; border-color: #22c55e; color: #fff;
  }
  .nav a:not(.active):hover { background: #1e293b; color: #e2e8f0; }
"""

BASE_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 24px;
  }
  h1 { font-size: 1.6rem; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }
  .subtitle { color: #64748b; font-size: .875rem; margin-bottom: 20px; }
  .stats {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 16px; margin-bottom: 32px;
  }
  .stat {
    background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    padding: 18px; text-align: center;
  }
  .stat-value { font-size: 2rem; font-weight: 800; color: #f8fafc; }
  .stat-label { font-size: .75rem; color: #64748b; margin-top: 4px; text-transform: uppercase; letter-spacing: .05em; }
  .card {
    background: #1e293b; border: 1px solid #334155; border-radius: 16px;
    overflow: hidden;
  }
  table { width: 100%; border-collapse: collapse; font-size: .875rem; }
  thead th {
    background: #0f172a; color: #64748b; font-weight: 600;
    padding: 12px 16px; text-align: left; font-size: .75rem;
    text-transform: uppercase; letter-spacing: .05em; border-bottom: 1px solid #334155;
  }
  tbody tr { border-bottom: 1px solid #1e293b; transition: background .15s; }
  tbody tr:hover { background: #0f172a55; }
  td { padding: 14px 16px; vertical-align: middle; }
  td.num { color: #64748b; font-weight: 600; width: 36px; }
  td.pid { font-family: monospace; color: #94a3b8; font-size: .8rem; }
  td.center { text-align: center; }
  td.last { color: #64748b; font-size: .8rem; white-space: nowrap; }
  .progress-wrap {
    background: #0f172a; border-radius: 99px; height: 8px;
    overflow: hidden; width: 100%; min-width: 120px;
  }
  .progress-bar { height: 100%; border-radius: 99px; transition: width .4s; }
  .day-label { font-size: .75rem; color: #64748b; margin-top: 4px; display: block; }
  .badge {
    display: inline-block; padding: 3px 10px; border-radius: 99px;
    font-size: .72rem; font-weight: 600;
  }
  .badge.done    { background: #14532d; color: #86efac; }
  .badge.today   { background: #14532d; color: #86efac; }
  .badge.pending { background: #1e293b; color: #64748b; border: 1px solid #334155; }
  .badge.waiting { background: #1e293b; color: #64748b; border: 1px solid #334155; }
  .refresh { margin-top: 20px; text-align: center; color: #475569; font-size: .8rem; }
"""


# ═══════════════════════════════════════════════════════════
#  WARM-UP — Supabase helpers
# ═══════════════════════════════════════════════════════════

def _default_profile(pid: str) -> dict:
    return {
        "id": pid, "day": 1, "start_date": None, "last_run": None,
        "done_today": False, "dms_sent": 0, "posts_done": 0,
        "groups_joined": 0, "dm_responses": 0, "history": [], "status": "En attente",
    }


def load_data() -> dict:
    try:
        result = supabase.table("profiles").select("*").execute()
        data = {}
        for row in result.data:
            pid = row["id"]
            data[pid] = {
                "id": row["id"], "day": row["day"], "start_date": row["start_date"],
                "last_run": row["last_run"], "done_today": row["done_today"],
                "dms_sent": row["dms_sent"], "posts_done": row["posts_done"],
                "groups_joined": row["groups_joined"], "dm_responses": row["dm_responses"],
                "history": row["history"] or [], "status": row["status"],
            }
        for pid in PROFILE_IDS:
            if pid not in data:
                data[pid] = _default_profile(pid)
        return data
    except Exception as e:
        print(f"[!] Supabase load error: {e}")
        return {pid: _default_profile(pid) for pid in PROFILE_IDS}


def save_profile(profile: dict):
    try:
        supabase.table("profiles").upsert({
            "id": profile["id"], "day": profile["day"],
            "start_date": profile["start_date"], "last_run": profile["last_run"],
            "done_today": profile["done_today"], "dms_sent": profile["dms_sent"],
            "posts_done": profile["posts_done"], "groups_joined": profile["groups_joined"],
            "dm_responses": profile["dm_responses"], "history": profile["history"],
            "status": profile["status"],
        }).execute()
    except Exception as e:
        print(f"[!] Supabase save error: {e}")


# ═══════════════════════════════════════════════════════════
#  MASS DM — Supabase helpers
# ═══════════════════════════════════════════════════════════

def _default_massdm(pid: str) -> dict:
    return {
        "id": pid, "dms_sent": 0, "dms_opened": 0, "dms_replied": 0,
        "conversions": 0, "last_run": None, "status": "En attente", "history": [],
    }


def load_massdm() -> dict:
    try:
        result = supabase.table("massdm").select("*").execute()
        data = {}
        for row in result.data:
            pid = row["id"]
            data[pid] = {
                "id": row["id"], "dms_sent": row["dms_sent"],
                "dms_opened": row["dms_opened"], "dms_replied": row["dms_replied"],
                "conversions": row["conversions"], "last_run": row["last_run"],
                "status": row["status"], "history": row["history"] or [],
            }
        for pid in PROFILE_IDS:
            if pid not in data:
                data[pid] = _default_massdm(pid)
        return data
    except Exception as e:
        print(f"[!] Supabase massdm load error: {e}")
        return {pid: _default_massdm(pid) for pid in PROFILE_IDS}


def save_massdm(profile: dict):
    try:
        supabase.table("massdm").upsert({
            "id": profile["id"], "dms_sent": profile["dms_sent"],
            "dms_opened": profile["dms_opened"], "dms_replied": profile["dms_replied"],
            "conversions": profile["conversions"], "last_run": profile["last_run"],
            "status": profile["status"], "history": profile["history"],
        }).execute()
    except Exception as e:
        print(f"[!] Supabase massdm save error: {e}")


# ═══════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.post("/api/update")
async def update_profile(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid = body.get("profile_id")
    if pid not in PROFILE_IDS:
        raise HTTPException(status_code=400, detail=f"Profil inconnu : {pid}")

    data    = load_data()
    profile = data.get(pid, _default_profile(pid))
    profile["day"]           = body.get("day", profile["day"])
    profile["start_date"]    = body.get("start_date", profile["start_date"])
    profile["last_run"]      = datetime.now().strftime("%d/%m/%Y %H:%M")
    profile["done_today"]    = body.get("done_today", False)
    profile["dms_sent"]      = body.get("dms_total", profile["dms_sent"])
    profile["posts_done"]    = body.get("posts_total", profile["posts_done"])
    profile["groups_joined"] = body.get("groups_joined", profile["groups_joined"])
    profile["dm_responses"]  = body.get("dm_responses", profile["dm_responses"])

    if profile["day"] > 15:
        profile["status"] = "Termine"
    elif profile["done_today"]:
        profile["status"] = "Fait aujourd'hui"
    else:
        profile["status"] = "En cours"

    profile["history"].append({
        "date": profile["last_run"], "day": profile["day"],
        "dms": body.get("dms_session", 0), "posts": body.get("posts_session", 0),
        "dm_rep": body.get("dm_responses", 0),
    })
    profile["history"] = profile["history"][-30:]
    save_profile(profile)
    return {"ok": True}


@app.post("/api/massdm")
async def update_massdm(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid = body.get("profile_id")
    if pid not in PROFILE_IDS:
        raise HTTPException(status_code=400, detail=f"Profil inconnu : {pid}")

    data    = load_massdm()
    profile = data.get(pid, _default_massdm(pid))
    profile["dms_sent"]    = body.get("dms_sent", profile["dms_sent"])
    profile["dms_opened"]  = body.get("dms_opened", profile["dms_opened"])
    profile["dms_replied"] = body.get("dms_replied", profile["dms_replied"])
    profile["conversions"] = body.get("conversions", profile["conversions"])
    profile["last_run"]    = datetime.now().strftime("%d/%m/%Y %H:%M")
    profile["status"]      = body.get("status", "Actif")

    profile["history"].append({
        "date": profile["last_run"],
        "sent": body.get("dms_sent_session", 0),
        "replied": body.get("dms_replied", 0),
    })
    profile["history"] = profile["history"][-30:]
    save_massdm(profile)
    return {"ok": True}


@app.get("/api/status")
def get_status():
    return JSONResponse(load_data())


@app.get("/api/massdm/status")
def get_massdm_status():
    return JSONResponse(load_massdm())


# ═══════════════════════════════════════════════════════════
#  PAGE WARM-UP
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def dashboard():
    data     = load_data()
    profiles = [data.get(pid, _default_profile(pid)) for pid in PROFILE_IDS]

    total_dms    = sum(p["dms_sent"] for p in profiles)
    total_posts  = sum(p["posts_done"] for p in profiles)
    total_groups = sum(p["groups_joined"] for p in profiles)
    done_today   = sum(1 for p in profiles if p["done_today"])
    finished     = sum(1 for p in profiles if p["day"] > 15)

    rows = ""
    for i, p in enumerate(profiles, 1):
        day   = p["day"]
        pct   = min(int(day / 15 * 100), 100)

        if day > 15:
            status_badge = '<span class="badge done">Termine ✓</span>'
        elif p["done_today"]:
            status_badge = '<span class="badge today">Fait auj. ✓</span>'
        elif p["last_run"]:
            status_badge = '<span class="badge pending">A faire</span>'
        else:
            status_badge = '<span class="badge waiting">En attente</span>'

        last = p["last_run"] or "—"
        rows += f"""
        <tr>
          <td class="num">{i}</td>
          <td class="pid">{p['id']}</td>
          <td>
            <div class="progress-wrap">
              <div class="progress-bar" style="width:{pct}%;background:#22c55e"></div>
            </div>
            <span class="day-label">J{min(day,15)}/15 — {pct}%</span>
          </td>
          <td class="center">{p['dms_sent']}</td>
          <td class="center">{p['posts_done']}</td>
          <td class="center">{p['groups_joined']}/16</td>
          <td class="center">{p['dm_responses']}</td>
          <td>{status_badge}</td>
          <td class="last">{last}</td>
        </tr>"""

    nav = NAV.format(cls_warmup="active", cls_massdm="")
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Warm-Up Tracker</title>
<style>
{BASE_CSS}
{NAV_CSS}
</style>
<meta http-equiv="refresh" content="60">
</head>
<body>
  <h1>Warm-Up Tracker</h1>
  <p class="subtitle">Suivi des 7 profils AdsPower — rafraichissement auto toutes les 60s</p>
  {nav}
  <div class="stats">
    <div class="stat">
      <div class="stat-value">{done_today}<span style="color:#334155;font-size:1.2rem">/7</span></div>
      <div class="stat-label">Faits aujourd'hui</div>
    </div>
    <div class="stat">
      <div class="stat-value">{total_dms}</div>
      <div class="stat-label">DMs envoyes</div>
    </div>
    <div class="stat">
      <div class="stat-value">{total_posts}</div>
      <div class="stat-label">Posts canaux</div>
    </div>
    <div class="stat">
      <div class="stat-value">{total_groups}</div>
      <div class="stat-label">Groupes rejoints</div>
    </div>
    <div class="stat">
      <div class="stat-value">{finished}</div>
      <div class="stat-label">Chauffes terminees</div>
    </div>
  </div>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>#</th><th>ID Profil</th>
          <th style="min-width:200px">Progression</th>
          <th>DMs</th><th>Posts</th><th>Groupes</th>
          <th>Rep. DMs</th><th>Statut</th><th>Derniere session</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p class="refresh">Mis a jour par warmup_v2.py apres chaque profil</p>
</body>
</html>"""
    return html


# ═══════════════════════════════════════════════════════════
#  PAGE MASS DM
# ═══════════════════════════════════════════════════════════

@app.get("/massdm", response_class=HTMLResponse)
def dashboard_massdm():
    data     = load_massdm()
    profiles = [data.get(pid, _default_massdm(pid)) for pid in PROFILE_IDS]

    total_sent      = sum(p["dms_sent"] for p in profiles)
    total_replied   = sum(p["dms_replied"] for p in profiles)
    total_conv      = sum(p["conversions"] for p in profiles)
    taux_rep        = round(total_replied / total_sent * 100, 1) if total_sent > 0 else 0
    actifs          = sum(1 for p in profiles if p["status"] == "Actif")

    rows = ""
    for i, p in enumerate(profiles, 1):
        sent    = p["dms_sent"]
        replied = p["dms_replied"]
        conv    = p["conversions"]
        taux    = round(replied / sent * 100, 1) if sent > 0 else 0
        pct_bar = min(int(taux), 100)

        if p["status"] == "Actif":
            status_badge = '<span class="badge today">Actif</span>'
        elif p["status"] == "Termine":
            status_badge = '<span class="badge done">Termine ✓</span>'
        else:
            status_badge = '<span class="badge waiting">En attente</span>'

        last = p["last_run"] or "—"
        rows += f"""
        <tr>
          <td class="num">{i}</td>
          <td class="pid">{p['id']}</td>
          <td class="center">{sent}</td>
          <td class="center">{replied}</td>
          <td>
            <div class="progress-wrap">
              <div class="progress-bar" style="width:{pct_bar}%;background:#22c55e"></div>
            </div>
            <span class="day-label">{taux}% de reponse</span>
          </td>
          <td class="center">{conv}</td>
          <td>{status_badge}</td>
          <td class="last">{last}</td>
        </tr>"""

    nav = NAV.format(cls_warmup="", cls_massdm="active")
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mass DM Tracker</title>
<style>
{BASE_CSS}
{NAV_CSS}
</style>
<meta http-equiv="refresh" content="60">
</head>
<body>
  <h1>Mass DM Tracker</h1>
  <p class="subtitle">Suivi des campagnes DM sur les 7 profils — rafraichissement auto toutes les 60s</p>
  {nav}
  <div class="stats">
    <div class="stat">
      <div class="stat-value">{actifs}<span style="color:#334155;font-size:1.2rem">/7</span></div>
      <div class="stat-label">Profils actifs</div>
    </div>
    <div class="stat">
      <div class="stat-value">{total_sent}</div>
      <div class="stat-label">DMs envoyes</div>
    </div>
    <div class="stat">
      <div class="stat-value">{total_replied}</div>
      <div class="stat-label">Reponses recues</div>
    </div>
    <div class="stat">
      <div class="stat-value">{taux_rep}<span style="font-size:1.2rem">%</span></div>
      <div class="stat-label">Taux de reponse</div>
    </div>
    <div class="stat">
      <div class="stat-value">{total_conv}</div>
      <div class="stat-label">Conversions</div>
    </div>
  </div>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>#</th><th>ID Profil</th>
          <th>DMs envoyes</th><th>Reponses</th>
          <th style="min-width:160px">Taux reponse</th>
          <th>Conversions</th><th>Statut</th><th>Derniere session</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p class="refresh">Mis a jour par le script mass DM apres chaque session</p>
</body>
</html>"""
    return html
