"""
Dashboard warm-up tracker — FastAPI + Supabase
GET  /              → page Warm-Up
GET  /massdm        → page Mass DM
GET  /scraper       → page Scraper (gestion des canaux)
POST /api/update    → warmup stats
POST /api/massdm    → mass DM stats
GET  /api/profiles  → liste profils (pour warmup_v2.py)
GET  /api/channels  → liste canaux (pour scraper.py)
POST /api/profile/add / /api/channel/add
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PARIS_TZ = ZoneInfo("Europe/Paris")

def now_paris(fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Retourne l'heure actuelle en fuseau horaire Europe/Paris."""
    return datetime.now(PARIS_TZ).strftime(fmt)

SECRET_TOKEN = os.environ.get("DASHBOARD_TOKEN", "Compte.1")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://pirlgavzihmnwmqlyeir.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBpcmxnYXZ6aWhtbndtcWx5ZWlyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3MzQxMTAsImV4cCI6MjA5NTMxMDExMH0.0QdskD9IBsx1rUZ_7Sljb8DshovkQMJIhmnAM-Zc6Ps")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ═══════════════════════════════════════════════════════════
#  CSS + NAV partagés
# ═══════════════════════════════════════════════════════════

def nav_html(active: str) -> str:
    pages = [("warmup", "/", "Warm-Up"), ("massdm", "/massdm", "Mass DM"), ("scraper", "/scraper", "Scraper")]
    links = ""
    for key, href, label in pages:
        cls = "active" if key == active else ""
        links += f'<a href="{href}" class="{cls}">{label}</a>'
    return f'<div class="nav">{links}</div>'


BASE_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 24px; position: relative; }
  h1 { font-size: 1.6rem; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }
  .subtitle { color: #64748b; font-size: .875rem; margin-bottom: 20px; }
  .nav { display: flex; gap: 8px; margin-bottom: 28px; }
  .nav a { padding: 8px 20px; border-radius: 8px; font-weight: 600; font-size: .875rem;
    text-decoration: none; border: 1px solid #334155; color: #94a3b8; transition: all .15s; }
  .nav a.active { background: #22c55e; border-color: #22c55e; color: #fff; }
  .nav a:not(.active):hover { background: #1e293b; color: #e2e8f0; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 16px; margin-bottom: 32px; }
  .stat { background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    padding: 18px; text-align: center; }
  .stat-value { font-size: 2rem; font-weight: 800; color: #f8fafc; }
  .stat-label { font-size: .75rem; color: #64748b; margin-top: 4px;
    text-transform: uppercase; letter-spacing: .05em; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px;
    overflow: hidden; margin-bottom: 24px; }
  table { width: 100%; border-collapse: collapse; font-size: .875rem; }
  thead th { background: #0f172a; color: #64748b; font-weight: 600; padding: 12px 16px;
    text-align: left; font-size: .75rem; text-transform: uppercase;
    letter-spacing: .05em; border-bottom: 1px solid #334155; }
  thead th.th-jour { text-align: center; width: 80px; }
  tbody tr { border-bottom: 1px solid #1e293b; transition: background .15s; }
  tbody tr:hover { background: #0f172a55; }
  td { padding: 14px 16px; vertical-align: middle; }
  td.num { color: #64748b; font-weight: 600; width: 36px; }
  td.pid { font-family: monospace; color: #94a3b8; font-size: .8rem; }
  td.center { text-align: center; }
  td.last { color: #64748b; font-size: .8rem; white-space: nowrap; }
  td.url-cell { font-family: monospace; color: #94a3b8; font-size: .75rem;
    max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  /* Progression */
  td.td-prog { min-width: 160px; }
  .progress-wrap { background: #0f172a; border-radius: 99px; height: 8px;
    overflow: hidden; width: 100%; }
  .progress-bar { height: 100%; border-radius: 99px; transition: width .6s ease; }
  .day-label { font-size: .72rem; color: #475569; margin-top: 5px; display: block; text-align:center; }
  /* Badge JOUR */
  td.td-jour { text-align: center; width: 80px; }
  .day-badge { display: inline-flex; align-items: center; justify-content: center;
    width: 62px; height: 62px; border-radius: 12px; font-weight: 800;
    font-size: 1rem; background: #0f1f3d; color: #93c5fd;
    border: 1.5px solid #1e40af;
    box-shadow: 0 0 8px rgba(59,130,246,.25);
    flex-direction: column; gap: 0; line-height: 1.1; }
  .day-badge .badge-num { font-size: 1.3rem; font-weight: 900; color: #bfdbfe; }
  .day-badge .badge-max { font-size: .65rem; color: #3b82f6; font-weight: 600; }
  .day-badge.done { background: #052e16; border-color: #166534;
    box-shadow: 0 0 8px rgba(34,197,94,.3); }
  .day-badge.done .badge-num { color: #86efac; }
  .day-badge.done .badge-max { color: #22c55e; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 99px;
    font-size: .72rem; font-weight: 600; }
  .badge.done    { background: #14532d; color: #86efac; }
  .badge.today   { background: #14532d; color: #86efac; }
  .badge.pending { background: #1e293b; color: #64748b; border: 1px solid #334155; }
  .badge.waiting { background: #1e293b; color: #64748b; border: 1px solid #334155; }
  .badge.active  { background: #1e3a5f; color: #93c5fd; }
  .badge.error   { background: #450a0a; color: #fca5a5; }
  .badge.scrapped{ background: #14532d; color: #86efac; }
  .add-box { background: #1e293b; border: 1px solid #334155; border-radius: 16px;
    padding: 20px; display: flex; align-items: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
  .add-box h2 { font-size: 1rem; font-weight: 600; color: #f8fafc; white-space: nowrap; }
  .add-box input { flex: 1; min-width: 200px; background: #0f172a; border: 1px solid #334155;
    border-radius: 8px; padding: 10px 14px; color: #e2e8f0; font-size: .875rem; font-family: monospace; }
  .add-box input:focus { outline: none; border-color: #22c55e; }
  .add-box button { background: #22c55e; border: none; border-radius: 8px;
    padding: 10px 20px; color: #fff; font-weight: 600; font-size: .875rem;
    cursor: pointer; white-space: nowrap; }
  .add-box button:hover { background: #16a34a; }
  .btn-del { background: none; border: none; color: #ef4444; cursor: pointer; font-size: 1rem; }
  .toast { display: none; position: fixed; top: 20px; right: 20px;
    background: #22c55e; color: #fff; padding: 12px 20px;
    border-radius: 8px; font-weight: 600; z-index: 999; }
  .refresh { margin-top: 20px; text-align: center; color: #475569; font-size: .8rem; }
  /* Indicateur erreur */
  .err-dot { display:inline-flex; align-items:center; justify-content:center;
    width:22px; height:22px; border-radius:50%; font-size:.75rem; font-weight:700;
    margin-left:7px; vertical-align:middle; flex-shrink:0; cursor:pointer;
    position:relative; }
  .err-ok  { background:#14532d; color:#86efac; }
  .err-warn { background:#450a0a; color:#fca5a5; border:1.5px solid #ef4444;
    animation: pulse-err 2s ease-in-out infinite; }
  @keyframes pulse-err {
    0%,100% { box-shadow: 0 0 0 0 rgba(239,68,68,.5); }
    50%      { box-shadow: 0 0 0 6px rgba(239,68,68,.0); } }
  td.last-cell { color:#64748b; font-size:.8rem; white-space:nowrap; }
  /* Tooltip personnalise */
  .err-tooltip-wrap { position:relative; display:inline-flex; align-items:center; }
  .err-tooltip-box  { display:none; position:absolute; bottom:calc(100% + 10px); right:0;
    width:280px; background:#1e293b; border:1px solid #ef4444;
    border-radius:12px; padding:14px 16px; z-index:9999;
    box-shadow:0 8px 32px rgba(239,68,68,.25), 0 2px 8px rgba(0,0,0,.5);
    pointer-events:none; }
  .err-tooltip-wrap:hover .err-tooltip-box { display:block; }
  .err-tooltip-box::after { content:''; position:absolute; bottom:-7px; right:8px;
    width:13px; height:13px; background:#1e293b; border-right:1px solid #ef4444;
    border-bottom:1px solid #ef4444; transform:rotate(45deg); }
  .err-tooltip-title { font-size:.75rem; font-weight:700; color:#fca5a5;
    text-transform:uppercase; letter-spacing:.06em; margin-bottom:8px;
    display:flex; align-items:center; gap:6px; }
  .err-tooltip-title::before { content:'⚠'; font-size:.9rem; }
  .err-tooltip-msg  { font-size:.8rem; color:#e2e8f0; line-height:1.5; }
  .err-tooltip-hint { font-size:.72rem; color:#64748b; margin-top:8px;
    padding-top:8px; border-top:1px solid #334155; line-height:1.4; }
  .err-ok-wrap { display:inline-flex; align-items:center; }
  /* ── Logo neon ── */
  .neon-logo { position: fixed; top: 20px; right: 24px; text-align: center; z-index: 200;
    pointer-events: none; }
  .neon-agency { display: block; font-size: .6rem; letter-spacing: .28em; font-weight: 700;
    color: #f472b6; text-shadow: 0 0 6px #f472b6, 0 0 14px #ec4899;
    margin-bottom: 4px; text-transform: uppercase; }
  .neon-box { border: 1.5px solid rgba(168,85,247,.7); border-radius: 6px;
    padding: 5px 14px 6px;
    background: linear-gradient(160deg,rgba(88,28,135,.18) 0%,rgba(15,23,42,.0) 100%);
    box-shadow: 0 0 14px rgba(168,85,247,.35), inset 0 0 14px rgba(168,85,247,.08); }
  .neon-text { font-size: 1.45rem; font-weight: 900; letter-spacing: .06em;
    background: linear-gradient(135deg, #e879f9 0%, #a855f7 45%, #7c3aed 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
    filter: drop-shadow(0 0 6px rgba(168,85,247,.9)) drop-shadow(0 0 12px rgba(232,121,249,.5)); }
"""


def add_js(endpoint: str, input_id: str, toast_msg: str = "Ajoute !") -> str:
    return f"""
<div id="toast" class="toast">{toast_msg}</div>
<script>
async function addItem() {{
  const val = document.getElementById('{input_id}').value.trim();
  if (!val) return;
  const r = await fetch('{endpoint}', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{token: 'Compte.1', value: val}})
  }});
  const data = await r.json();
  if (data.ok) {{
    document.getElementById('toast').style.display = 'block';
    setTimeout(() => window.location.reload(), 1200);
  }} else {{ alert('Erreur : ' + (data.detail || JSON.stringify(data))); }}
}}
document.getElementById('{input_id}').addEventListener('keydown', e => {{ if (e.key === 'Enter') addItem(); }});

async function delItem(id, endpoint) {{
  if (!confirm('Supprimer ?')) return;
  const r = await fetch(endpoint, {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{token: 'Compte.1', id: id}})
  }});
  const data = await r.json();
  if (data.ok) window.location.reload();
}}
</script>"""


# ═══════════════════════════════════════════════════════════
#  Supabase helpers — Profils
# ═══════════════════════════════════════════════════════════

def get_all_ids() -> list:
    try:
        result = supabase.table("profiles").select("id").execute()
        return [row["id"] for row in result.data]
    except Exception as e:
        print(f"[!] get_all_ids error: {e}")
        return []


def _default_profile(pid: str) -> dict:
    return {"id": pid, "day": 1, "start_date": None, "last_run": None,
            "done_today": False, "dms_sent": 0, "posts_done": 0,
            "groups_joined": 0, "dm_responses": 0, "history": [], "status": "En attente",
            "last_error": ""}


def load_data() -> dict:
    try:
        result = supabase.table("profiles").select("*").execute()
        data = {}
        today_str = now_paris("%d/%m/%Y")
        to_reset = []

        for row in result.data:
            pid = row["id"]
            last_run  = row.get("last_run") or ""
            done_today = row.get("done_today", False)

            # Auto-reset "Fait aujourd'hui" si last_run n'est pas aujourd'hui
            if done_today and last_run:
                last_run_date = last_run[:10]   # "dd/mm/yyyy"
                if last_run_date != today_str:
                    row["done_today"] = False
                    row["status"]     = "En attente"
                    to_reset.append(pid)

            data[pid] = {"id": row["id"], "day": row["day"], "start_date": row["start_date"],
                         "last_run": row["last_run"], "done_today": row["done_today"],
                         "dms_sent": row["dms_sent"], "posts_done": row["posts_done"],
                         "groups_joined": row["groups_joined"], "dm_responses": row["dm_responses"],
                         "history": row["history"] or [], "status": row["status"],
                         "last_error": row.get("last_error") or ""}

        # Reset en base (une seule fois par jour au premier chargement)
        for pid in to_reset:
            try:
                supabase.table("profiles").update(
                    {"done_today": False, "status": "En attente"}
                ).eq("id", pid).execute()
                print(f"[->] Reset done_today pour {pid} (nouveau jour)")
            except Exception:
                pass

        return data
    except Exception as e:
        print(f"[!] load_data error: {e}")
        return {}


def save_profile(profile: dict):
    try:
        supabase.table("profiles").upsert({
            "id": profile["id"], "day": profile["day"], "start_date": profile["start_date"],
            "last_run": profile["last_run"], "done_today": profile["done_today"],
            "dms_sent": profile["dms_sent"], "posts_done": profile["posts_done"],
            "groups_joined": profile["groups_joined"], "dm_responses": profile["dm_responses"],
            "history": profile["history"], "status": profile["status"],
            "last_error": profile.get("last_error", "")}).execute()
    except Exception as e:
        print(f"[!] save_profile error: {e}")


# ═══════════════════════════════════════════════════════════
#  Supabase helpers — Mass DM
# ═══════════════════════════════════════════════════════════

def _default_massdm(pid: str) -> dict:
    return {"id": pid, "dms_sent": 0, "dms_opened": 0, "dms_replied": 0,
            "conversions": 0, "last_run": None, "status": "En attente", "history": []}


def load_massdm() -> dict:
    try:
        result = supabase.table("massdm").select("*").execute()
        data = {}
        for row in result.data:
            pid = row["id"]
            data[pid] = {"id": row["id"], "dms_sent": row["dms_sent"],
                         "dms_opened": row["dms_opened"], "dms_replied": row["dms_replied"],
                         "conversions": row["conversions"], "last_run": row["last_run"],
                         "status": row["status"], "history": row["history"] or []}
        return data
    except Exception as e:
        print(f"[!] load_massdm error: {e}")
        return {}


def save_massdm(profile: dict):
    try:
        supabase.table("massdm").upsert({
            "id": profile["id"], "dms_sent": profile["dms_sent"],
            "dms_opened": profile["dms_opened"], "dms_replied": profile["dms_replied"],
            "conversions": profile["conversions"], "last_run": profile["last_run"],
            "status": profile["status"], "history": profile["history"]}).execute()
    except Exception as e:
        print(f"[!] save_massdm error: {e}")


# ═══════════════════════════════════════════════════════════
#  Supabase helpers — Canaux Scraper
# ═══════════════════════════════════════════════════════════

def load_channels() -> list:
    try:
        result = supabase.table("channels").select("*").order("id").execute()
        return result.data or []
    except Exception as e:
        print(f"[!] load_channels error: {e}")
        return []


# ═══════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/api/profiles")
def api_get_profiles():
    return JSONResponse(get_all_ids())


@app.get("/api/channels")
def api_get_channels():
    return JSONResponse(load_channels())


@app.post("/api/profile/add")
async def api_add_profile(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid = body.get("value", "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="ID manquant")
    try:
        supabase.table("profiles").upsert(_default_profile(pid)).execute()
        supabase.table("massdm").upsert(_default_massdm(pid)).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/profile/delete")
async def api_del_profile(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid = body.get("id", "").strip()
    try:
        supabase.table("profiles").delete().eq("id", pid).execute()
        supabase.table("massdm").delete().eq("id", pid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/channel/add")
async def api_add_channel(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    url = body.get("value", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL manquante")
    try:
        supabase.table("channels").upsert({"url": url, "status": "En attente", "members_count": 0}).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/channel/delete")
async def api_del_channel(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    cid = body.get("id")
    try:
        supabase.table("channels").delete().eq("id", cid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/channel/update")
async def api_update_channel(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    cid = body.get("channel_id")
    try:
        supabase.table("channels").update({
            "status":        body.get("status", "En attente"),
            "members_count": body.get("members_count", 0),
            "last_scraped":  now_paris(),
        }).eq("id", cid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/update")
async def update_profile(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid = body.get("profile_id")
    data    = load_data()
    profile = data.get(pid, _default_profile(pid))
    profile["day"]           = body.get("day", profile["day"])
    profile["start_date"]    = body.get("start_date", profile["start_date"])
    profile["last_run"]      = now_paris()
    profile["done_today"]    = body.get("done_today", False)
    profile["dms_sent"]      = body.get("dms_total", profile["dms_sent"])
    profile["posts_done"]    = body.get("posts_total", profile["posts_done"])
    profile["groups_joined"] = body.get("groups_joined", profile["groups_joined"])
    profile["dm_responses"]  = body.get("dm_responses", profile["dm_responses"])
    profile["last_error"]    = body.get("last_error", "")
    if profile["day"] > 15:   profile["status"] = "Termine"
    elif profile["done_today"]: profile["status"] = "Fait aujourd'hui"
    else:                       profile["status"] = "En cours"
    profile["history"].append({"date": profile["last_run"], "day": profile["day"],
        "dms": body.get("dms_session", 0), "posts": body.get("posts_session", 0),
        "dm_rep": body.get("dm_responses", 0)})
    profile["history"] = profile["history"][-30:]
    save_profile(profile)
    return {"ok": True}


@app.post("/api/massdm")
async def update_massdm_api(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid = body.get("profile_id")
    data    = load_massdm()
    profile = data.get(pid, _default_massdm(pid))
    profile["dms_sent"]    = body.get("dms_sent", profile["dms_sent"])
    profile["dms_replied"] = body.get("dms_replied", profile["dms_replied"])
    profile["conversions"] = body.get("conversions", profile["conversions"])
    profile["last_run"]    = now_paris()
    profile["status"]      = body.get("status", "Actif")
    profile["history"].append({"date": profile["last_run"],
        "sent": body.get("dms_sent_session", 0), "replied": body.get("dms_replied", 0)})
    profile["history"] = profile["history"][-30:]
    save_massdm(profile)
    return {"ok": True}


@app.get("/api/status")
def get_status():
    return JSONResponse(load_data())


def _traduire_erreur(err: str) -> tuple[str, str]:
    """Traduit une erreur technique en message français clair. Retourne (message, conseil)."""
    e = err.lower()
    if "telegram non connecte" in e or "non connecte" in e:
        return ("Aucun compte Telegram connecté sur ce profil AdsPower.",
                "💡 Ouvre AdsPower, lance ce profil manuellement, connecte-toi à Telegram Web, puis relance le script.")
    if "demarrage adspower" in e or "impossible de demarrer" in e:
        return ("AdsPower n'a pas pu ouvrir ce profil navigateur.",
                "💡 Vérifie qu'AdsPower est bien lancé et que le profil existe encore.")
    if "fermeture adspower" in e or "stop" in e:
        return ("Le profil AdsPower ne s'est pas fermé correctement après la session.",
                "💡 Ferme manuellement le profil dans AdsPower si il est encore ouvert.")
    if "navigation telegram" in e:
        return ("Impossible d'accéder à Telegram Web sur ce profil.",
                "💡 Vérifie la connexion internet du profil et que Telegram Web fonctionne.")
    if "deconnexion playwright" in e:
        return ("Le script a perdu le contrôle du navigateur en cours de session.",
                "💡 Relance simplement le script, cela se règle souvent tout seul.")
    if "erreur session critique" in e:
        # Extrait le détail après "—"
        detail = err.split("—")[-1].strip()[:120] if "—" in err else err[:120]
        return (f"Erreur inattendue pendant la session : {detail}",
                "💡 Regarde le terminal pour plus de détails et relance le script.")
    # Erreur générique
    msg = err[:150].replace("<", "&lt;")
    return (f"Erreur technique : {msg}",
            "💡 Consulte le terminal pour le détail complet de l'erreur.")


def _err_dot(last_error: str) -> str:
    """Retourne un indicateur vert (OK) ou rouge avec tooltip français stylé."""
    if not last_error:
        return '<span class="err-dot err-ok" title="Aucune erreur">✓</span>'

    msg, conseil = _traduire_erreur(last_error)
    msg_safe     = msg.replace("<", "&lt;").replace('"', "&quot;")
    conseil_safe = conseil.replace("<", "&lt;").replace('"', "&quot;")

    return f"""<span class="err-tooltip-wrap">
      <span class="err-dot err-warn">⚠</span>
      <div class="err-tooltip-box">
        <div class="err-tooltip-title">Erreur détectée</div>
        <div class="err-tooltip-msg">{msg_safe}</div>
        <div class="err-tooltip-hint">{conseil_safe}</div>
      </div>
    </span>"""


# ═══════════════════════════════════════════════════════════
#  PAGE WARM-UP
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def dashboard():
    data        = load_data()
    profile_ids = get_all_ids()
    profiles    = [data.get(pid, _default_profile(pid)) for pid in profile_ids]
    n           = len(profiles)
    total_dms    = sum(p["dms_sent"] for p in profiles)
    total_posts  = sum(p["posts_done"] for p in profiles)
    total_groups = sum(p["groups_joined"] for p in profiles)
    done_today   = sum(1 for p in profiles if p["done_today"])
    finished     = sum(1 for p in profiles if p["day"] > 15)

    rows = ""
    for i, p in enumerate(profiles, 1):
        day = p["day"]
        # Jours completes = day si session faite aujourd'hui, sinon day-1
        completed = day if p["done_today"] else max(day - 1, 0)
        if day > 15: completed = 15
        pct = min(int(completed / 15 * 100), 100)
        if day > 15:          sb = '<span class="badge done">Termine ✓</span>'
        elif p["done_today"]: sb = '<span class="badge today">Fait auj. ✓</span>'
        elif p["last_run"]:   sb = '<span class="badge pending">A faire</span>'
        else:                 sb = '<span class="badge waiting">En attente</span>'
        pid = p["id"]
        day_display = min(day, 15)
        badge_cls = "day-badge done" if day > 15 else "day-badge"
        rows += f"""<tr>
          <td class="num">{i}</td>
          <td class="pid">{pid}</td>
          <td class="td-prog">
            <div class="progress-wrap">
              <div class="progress-bar" style="width:{pct}%;background:#22c55e"></div>
            </div>
            <span class="day-label">{pct}%</span>
          </td>
          <td class="td-jour">
            <div class="{badge_cls}">
              <span class="badge-num">{day_display}</span>
              <span class="badge-max">/ 15</span>
            </div>
          </td>
          <td class="center">{p['dms_sent']}</td>
          <td class="center">{p['posts_done']}</td>
          <td class="center">{p['groups_joined']}/16</td>
          <td class="center">{p['dm_responses']}</td>
          <td>{sb}</td>
          <td class="last-cell">{p['last_run'] or '—'}{_err_dot(p.get('last_error',''))}</td>
          <td class="center"><button class="btn-del" onclick="delItem('{pid}','/api/profile/delete')" title="Supprimer">✕</button></td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Warm-Up Tracker</title><style>{BASE_CSS}</style>
<meta http-equiv="refresh" content="60"></head><body>
  <div class="neon-logo">
    <span class="neon-agency">Agency</span>
    <div class="neon-box"><span class="neon-text">OF4MYM</span></div>
  </div>
  <h1>Warm-Up Tracker</h1>
  <p class="subtitle">Suivi de {n} profils AdsPower</p>
  {nav_html("warmup")}
  <div class="add-box">
    <h2>+ Ajouter un profil</h2>
    <input id="inp" type="text" placeholder="ID AdsPower  ex: k1abc123">
    <button onclick="addItem()">Ajouter</button>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-value">{done_today}<span style="color:#334155;font-size:1.2rem">/{n}</span></div><div class="stat-label">Faits aujourd'hui</div></div>
    <div class="stat"><div class="stat-value">{total_dms}</div><div class="stat-label">DMs envoyes</div></div>
    <div class="stat"><div class="stat-value">{total_posts}</div><div class="stat-label">Posts canaux</div></div>
    <div class="stat"><div class="stat-value">{total_groups}</div><div class="stat-label">Groupes rejoints</div></div>
    <div class="stat"><div class="stat-value">{finished}</div><div class="stat-label">Chauffes terminees</div></div>
  </div>
  <div class="card"><table><thead><tr>
    <th>#</th><th>ID Profil</th><th style="min-width:180px">Progression</th>
    <th class="th-jour">Jour</th>
    <th>DMs</th><th>Posts</th><th>Groupes</th><th>Rep.</th><th>Statut</th><th>Derniere session / Etat</th><th></th>
  </tr></thead><tbody>{rows}</tbody></table></div>
  <p class="refresh">Mis a jour par warmup_v2.py apres chaque profil</p>
  {add_js('/api/profile/add', 'inp', 'Profil ajoute !')}
</body></html>"""
    return html


# ═══════════════════════════════════════════════════════════
#  PAGE MASS DM
# ═══════════════════════════════════════════════════════════

@app.get("/massdm", response_class=HTMLResponse)
def dashboard_massdm():
    data        = load_massdm()
    profile_ids = get_all_ids()
    profiles    = [data.get(pid, _default_massdm(pid)) for pid in profile_ids]
    n           = len(profiles)
    total_sent    = sum(p["dms_sent"] for p in profiles)
    total_replied = sum(p["dms_replied"] for p in profiles)
    total_conv    = sum(p["conversions"] for p in profiles)
    taux_rep      = round(total_replied / total_sent * 100, 1) if total_sent > 0 else 0
    actifs        = sum(1 for p in profiles if p["status"] == "Actif")

    rows = ""
    for i, p in enumerate(profiles, 1):
        sent    = p["dms_sent"]
        replied = p["dms_replied"]
        taux    = round(replied / sent * 100, 1) if sent > 0 else 0
        pct_bar = min(int(taux), 100)
        if p["status"] == "Actif":   sb = '<span class="badge active">Actif</span>'
        elif p["status"] == "Termine": sb = '<span class="badge done">Termine ✓</span>'
        else:                          sb = '<span class="badge waiting">En attente</span>'
        rows += f"""<tr>
          <td class="num">{i}</td><td class="pid">{p['id']}</td>
          <td class="center">{sent}</td><td class="center">{replied}</td>
          <td><div class="progress-wrap"><div class="progress-bar" style="width:{pct_bar}%;background:#22c55e"></div></div>
          <span class="day-label">{taux}% de reponse</span></td>
          <td class="center">{p['conversions']}</td><td>{sb}</td>
          <td class="last">{p['last_run'] or '—'}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mass DM Tracker</title><style>{BASE_CSS}</style>
<meta http-equiv="refresh" content="60"></head><body>
  <h1>Mass DM Tracker</h1>
  <p class="subtitle">Suivi des campagnes DM sur {n} profils</p>
  {nav_html("massdm")}
  <div class="stats">
    <div class="stat"><div class="stat-value">{actifs}<span style="color:#334155;font-size:1.2rem">/{n}</span></div><div class="stat-label">Profils actifs</div></div>
    <div class="stat"><div class="stat-value">{total_sent}</div><div class="stat-label">DMs envoyes</div></div>
    <div class="stat"><div class="stat-value">{total_replied}</div><div class="stat-label">Reponses</div></div>
    <div class="stat"><div class="stat-value">{taux_rep}<span style="font-size:1.2rem">%</span></div><div class="stat-label">Taux reponse</div></div>
    <div class="stat"><div class="stat-value">{total_conv}</div><div class="stat-label">Conversions</div></div>
  </div>
  <div class="card"><table><thead><tr>
    <th>#</th><th>ID Profil</th><th>DMs envoyes</th><th>Reponses</th>
    <th style="min-width:160px">Taux reponse</th><th>Conversions</th><th>Statut</th><th>Derniere session</th>
  </tr></thead><tbody>{rows}</tbody></table></div>
  <p class="refresh">Mis a jour par dm_sender.py apres chaque session</p>
</body></html>"""
    return html


# ═══════════════════════════════════════════════════════════
#  PAGE SCRAPER
# ═══════════════════════════════════════════════════════════

@app.get("/scraper", response_class=HTMLResponse)
def dashboard_scraper():
    channels      = load_channels()
    total_members = sum(c.get("members_count", 0) for c in channels)
    scraped       = sum(1 for c in channels if c.get("status") == "Scrappe")
    en_attente    = sum(1 for c in channels if c.get("status") == "En attente")

    rows = ""
    for i, c in enumerate(channels, 1):
        status = c.get("status", "En attente")
        count  = c.get("members_count", 0)
        last   = c.get("last_scraped") or "—"
        cid    = c.get("id")
        url    = c.get("url", "")

        if status == "Scrappe":   sb = '<span class="badge scrapped">Scrappe ✓</span>'
        elif status == "En cours": sb = '<span class="badge active">En cours...</span>'
        elif status == "Erreur":   sb = '<span class="badge error">Erreur</span>'
        else:                      sb = '<span class="badge waiting">En attente</span>'

        rows += f"""<tr>
          <td class="num">{i}</td>
          <td class="url-cell" title="{url}">{url}</td>
          <td class="center">{count if count > 0 else '—'}</td>
          <td>{sb}</td>
          <td class="last">{last}</td>
          <td class="center"><button class="btn-del" onclick="delItem({cid},'/api/channel/delete')" title="Supprimer">✕</button></td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scraper — Canaux</title><style>{BASE_CSS}</style>
<meta http-equiv="refresh" content="30"></head><body>
  <h1>Scraper de canaux</h1>
  <p class="subtitle">Ajoute les canaux Telegram a scrapper pour le Mass DM</p>
  {nav_html("scraper")}

  <div class="add-box">
    <h2>+ Ajouter un canal</h2>
    <input id="inp" type="text" placeholder="https://t.me/nom_du_canal  ou  @nom_canal">
    <button onclick="addItem()">Ajouter</button>
  </div>

  <div class="stats">
    <div class="stat"><div class="stat-value">{len(channels)}</div><div class="stat-label">Canaux enregistres</div></div>
    <div class="stat"><div class="stat-value">{scraped}</div><div class="stat-label">Deja scrapes</div></div>
    <div class="stat"><div class="stat-value">{en_attente}</div><div class="stat-label">En attente</div></div>
    <div class="stat"><div class="stat-value">{total_members}</div><div class="stat-label">Membres collectes</div></div>
  </div>

  <div class="card"><table><thead><tr>
    <th>#</th><th>Lien du canal</th><th>Membres</th><th>Statut</th><th>Dernier scraping</th><th></th>
  </tr></thead><tbody>{rows if rows else '<tr><td colspan="6" style="text-align:center;color:#64748b;padding:30px">Aucun canal — ajoutes-en un ci-dessus</td></tr>'}</tbody></table></div>

  <div class="card" style="padding:20px;background:#0f172a;border-color:#1e3a5f">
    <p style="color:#93c5fd;font-size:.875rem;">
      <strong>Comment ca marche :</strong><br><br>
      1. Ajoute ici les liens des canaux Telegram a scrapper<br>
      2. Quand le warm-up J15 est termine, <code style="background:#1e293b;padding:2px 6px;border-radius:4px">scraper.py</code> se lance automatiquement<br>
      3. Il scrappe tous les membres de ces canaux → les sauvegarde dans <code style="background:#1e293b;padding:2px 6px;border-radius:4px">output/membres.csv</code><br>
      4. Puis <code style="background:#1e293b;padding:2px 6px;border-radius:4px">dm_sender.py</code> envoie 28-37 DMs par session depuis chaque profil
    </p>
  </div>

  <p class="refresh">Les statuts se mettent a jour pendant le scraping</p>
  {add_js('/api/channel/add', 'inp', 'Canal ajoute !')}
</body></html>"""
    return html
