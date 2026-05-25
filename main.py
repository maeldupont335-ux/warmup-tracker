
"""
Dashboard warm-up tracker — FastAPI
POST /api/update  → reçoit les données du script warmup_v2.py
GET  /            → dashboard HTML
GET  /api/status  → JSON brut
"""

import json
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SECRET_TOKEN = os.environ.get("DASHBOARD_TOKEN", "Compte.1")
DATA_FILE    = "data.json"

PROFILE_IDS = [
    "k1csfeja", "k1cup0ch", "k1cup0ci", "k1cup0cj",
    "k1cup0ck", "k1cup0cl", "k1cvbnrr",
]


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {pid: _default_profile(pid) for pid in PROFILE_IDS}


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _default_profile(pid: str) -> dict:
    return {
        "id":           pid,
        "day":          1,
        "start_date":   None,
        "last_run":     None,
        "done_today":   False,
        "dms_sent":     0,
        "posts_done":   0,
        "groups_joined": 0,
        "dm_responses": 0,
        "history":      [],
        "status":       "En attente",
    }


@app.post("/api/update")
async def update_profile(request: Request):
    body = await request.json()

    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")

    data = load_data()
    pid  = body.get("profile_id")

    if pid not in PROFILE_IDS:
        raise HTTPException(status_code=400, detail=f"Profil inconnu : {pid}")

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
        profile["status"] = "Terminé"
    elif profile["done_today"]:
        profile["status"] = "Fait aujourd'hui"
    else:
        profile["status"] = "En cours"

    # Ajoute une entrée dans l'historique
    profile["history"].append({
        "date":      profile["last_run"],
        "day":       profile["day"],
        "dms":       body.get("dms_session", 0),
        "posts":     body.get("posts_session", 0),
        "dm_rep":    body.get("dm_responses", 0),
    })
    profile["history"] = profile["history"][-30:]  # Garde les 30 dernières entrées

    data[pid] = profile
    save_data(data)
    return {"ok": True}


@app.get("/api/status")
def get_status():
    return JSONResponse(load_data())


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
        day    = p["day"]
        pct    = min(int((day - 1) / 15 * 100), 100)
        bar_w  = pct

        if day > 15:
            status_badge = '<span class="badge done">Terminé ✓</span>'
            bar_color    = "#22c55e"
        elif p["done_today"]:
            status_badge = '<span class="badge today">Fait auj. ✓</span>'
            bar_color    = "#3b82f6"
        elif p["last_run"]:
            status_badge = '<span class="badge pending">À faire</span>'
            bar_color    = "#f59e0b"
        else:
            status_badge = '<span class="badge waiting">En attente</span>'
            bar_color    = "#6b7280"

        last = p["last_run"] or "—"

        rows += f"""
        <tr>
          <td class="num">{i}</td>
          <td class="pid">{p['id']}</td>
          <td>
            <div class="progress-wrap">
              <div class="progress-bar" style="width:{bar_w}%;background:{bar_color}"></div>
            </div>
            <span class="day-label">J{min(day,15)}/15 — {pct}%</span>
          </td>
          <td class="center">{p['dms_sent']}</td>
          <td class="center">{p['posts_done']}</td>
          <td class="center">{p['groups_joined']}/8</td>
          <td class="center">{p['dm_responses']}</td>
          <td>{status_badge}</td>
          <td class="last">{last}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Warm-Up Tracker</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 24px;
  }}
  h1 {{ font-size: 1.6rem; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }}
  .subtitle {{ color: #64748b; font-size: .875rem; margin-bottom: 28px; }}

  .stats {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 16px; margin-bottom: 32px;
  }}
  .stat {{
    background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    padding: 18px; text-align: center;
  }}
  .stat-value {{ font-size: 2rem; font-weight: 800; color: #f8fafc; }}
  .stat-label {{ font-size: .75rem; color: #64748b; margin-top: 4px; text-transform: uppercase; letter-spacing: .05em; }}

  .card {{
    background: #1e293b; border: 1px solid #334155; border-radius: 16px;
    overflow: hidden;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: .875rem; }}
  thead th {{
    background: #0f172a; color: #64748b; font-weight: 600;
    padding: 12px 16px; text-align: left; font-size: .75rem;
    text-transform: uppercase; letter-spacing: .05em; border-bottom: 1px solid #334155;
  }}
  tbody tr {{ border-bottom: 1px solid #1e293b; transition: background .15s; }}
  tbody tr:hover {{ background: #0f172a55; }}
  td {{ padding: 14px 16px; vertical-align: middle; }}
  td.num {{ color: #64748b; font-weight: 600; width: 36px; }}
  td.pid {{ font-family: monospace; color: #94a3b8; font-size: .8rem; }}
  td.center {{ text-align: center; }}
  td.last {{ color: #64748b; font-size: .8rem; white-space: nowrap; }}

  .progress-wrap {{
    background: #0f172a; border-radius: 99px; height: 8px;
    overflow: hidden; width: 100%; min-width: 120px;
  }}
  .progress-bar {{ height: 100%; border-radius: 99px; transition: width .4s; }}
  .day-label {{ font-size: .75rem; color: #64748b; margin-top: 4px; display: block; }}

  .badge {{
    display: inline-block; padding: 3px 10px; border-radius: 99px;
    font-size: .72rem; font-weight: 600;
  }}
  .badge.done    {{ background: #14532d; color: #86efac; }}
  .badge.today   {{ background: #1e3a5f; color: #93c5fd; }}
  .badge.pending {{ background: #451a03; color: #fcd34d; }}
  .badge.waiting {{ background: #1e293b; color: #64748b; border: 1px solid #334155; }}

  .refresh {{ margin-top: 20px; text-align: center; color: #475569; font-size: .8rem; }}
  a {{ color: #3b82f6; text-decoration: none; }}
</style>
<meta http-equiv="refresh" content="60">
</head>
<body>
  <h1>Warm-Up Tracker</h1>
  <p class="subtitle">Suivi des 10 profils AdsPower — rafraîchissement auto toutes les 60s</p>

  <div class="stats">
    <div class="stat">
      <div class="stat-value">{done_today}<span style="color:#334155;font-size:1.2rem">/10</span></div>
      <div class="stat-label">Faits aujourd'hui</div>
    </div>
    <div class="stat">
      <div class="stat-value">{total_dms}</div>
      <div class="stat-label">DMs envoyés</div>
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
      <div class="stat-label">Chauffes terminées</div>
    </div>
  </div>

  <div class="card">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>ID Profil</th>
          <th style="min-width:200px">Progression</th>
          <th>DMs</th>
          <th>Posts</th>
          <th>Groupes</th>
          <th>Rép. DMs</th>
          <th>Statut</th>
          <th>Dernière session</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p class="refresh">Mis à jour par warmup_v2.py après chaque profil</p>
</body>
</html>"""
    return html
