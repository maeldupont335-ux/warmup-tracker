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

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_keepalive_executor = ThreadPoolExecutor(max_workers=1)

SELF_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://warmup-tracker.onrender.com")


async def _keepalive_task():
    """
    Ping self toutes les 8 minutes pour empêcher Render Free de tuer le processus.
    Sans ça, Render endort le service après 15 min d'inactivité HTTP → batch perdu.
    """
    await asyncio.sleep(60)  # Attendre 1 min au démarrage
    while True:
        await asyncio.sleep(480)  # 8 minutes
        if _mass_batch.get("running"):
            def _do_ping():
                try:
                    from urllib.request import urlopen, Request as UReq
                    req = UReq(f"{SELF_URL}/api/setup/batch-status",
                               headers={"User-Agent": "keepalive"})
                    urlopen(req, timeout=8)
                except Exception:
                    pass
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(_keepalive_executor, _do_ping)
                print(f"[KEEPALIVE] Ping Render — batch toujours actif", flush=True)
            except Exception:
                pass


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(_keepalive_task())

# Flag en mémoire — trigger warm-up sans table Supabase
_warmup_trigger: bool = False

# ── Résultats d'application profil (profile_changer.py → dashboard) ──
# {profile_id: {"ok": bool, "error": str, "at": str}}
_apply_results: dict = {}

# ── État du batch mass-upload (survit aux navigations client) ──
_mass_batch: dict = {
    "running":        False,
    "finished":       False,
    "stop_requested": False,
    "stopped":        False,   # arrêté manuellement (vs terminé normalement)
    "profiles":       [],      # [{id, photo_name, status, error}]
    "current_idx":    -1,
    "next_at":        None,    # ISO timestamp — heure du prochain profil
    "total":          0,
    "delay_s":        360,     # 6 min
}

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
    pages = [
        ("overview", "/",        "⊞ Dashboard"),
        ("warmup",   "/warmup",  "🔥 Warm-Up"),
        ("massdm",   "/massdm",  "✉ Mass DM"),
        ("scraper",  "/scraper", "🔍 Scraper"),
        ("setup",    "/setup",   "⚙ Setup"),
    ]
    links = ""
    for key, href, label in pages:
        cls = "active" if key == active else ""
        links += f'<a href="{href}" class="{cls}">{label}</a>'
    return f'<div class="nav">{links}</div>'


# ═══════════════════════════════════════════════════════════
#  SIDEBAR — composant partagé entre toutes les pages
# ═══════════════════════════════════════════════════════════

SIDEBAR_CSS = """
body{background:#0d0d0d!important;overflow:hidden!important;padding:0!important}
.ov-layout{display:flex;height:100vh;overflow:hidden}
.page-main{flex:1;overflow-y:auto;background:#0d0d0d;padding:28px 32px}
.page-main::-webkit-scrollbar{width:4px}
.page-main::-webkit-scrollbar-thumb{background:#222;border-radius:2px}
.side-panel{width:220px;background:#0a0a0a;border-right:1px solid #1a1a1a;display:flex;flex-direction:column;flex-shrink:0;transition:width .25s cubic-bezier(.4,0,.2,1);overflow:hidden}
.side-panel.collapsed{width:60px}
.side-logo{padding:22px 18px 18px;border-bottom:1px solid #1a1a1a;display:flex;align-items:center;gap:12px;flex-shrink:0}
.logo-ico{width:36px;height:36px;border-radius:8px;flex-shrink:0;background:#1f0808;border:1px solid #3d1212;display:flex;align-items:center;justify-content:center;font-size:.55rem;font-weight:900;color:#dc2626;letter-spacing:.02em}
.logo-info{overflow:hidden;white-space:nowrap;transition:opacity .2s}
.side-panel.collapsed .logo-info{opacity:0;pointer-events:none}
.logo-name{font-size:.85rem;font-weight:800;color:#f0f0f0;display:block;letter-spacing:.04em}
.logo-sub{font-size:.6rem;color:#444;display:block;margin-top:3px;text-transform:uppercase;letter-spacing:.08em}
.side-nav{padding:14px 10px 14px 20px;flex:1;display:flex;flex-direction:column;gap:2px;overflow:hidden}
.snav-btn{display:flex;align-items:center;gap:12px;padding:18px 12px;border-radius:8px;color:#555;font-size:.9rem;font-weight:600;white-space:nowrap;overflow:hidden;transition:all .15s;border-right:3px solid transparent;position:relative;text-decoration:none}
.snav-btn:hover{background:#141414;color:#aaa}
.snav-btn.active{background:rgba(220,38,38,.1);color:#dc2626;border-right:3px solid #dc2626;border-radius:8px 0 0 8px}
.snav-ico{width:18px;height:18px;flex-shrink:0;display:flex;align-items:center;justify-content:center}
.snav-lbl{transition:opacity .15s}
.side-panel.collapsed .snav-lbl{opacity:0;pointer-events:none}
.side-panel.collapsed .snav-btn{justify-content:center;padding:11px}
.side-panel.collapsed .snav-btn.active{border-radius:8px;border-right:3px solid #dc2626}
.side-toggle{margin:10px 10px 16px;background:none;border:1px solid #1e1e1e;border-radius:8px;padding:8px;color:#333;font-size:.75rem;display:flex;align-items:center;justify-content:center;transition:all .15s;flex-shrink:0;cursor:pointer}
.side-toggle:hover{border-color:#dc2626;color:#dc2626}
.neon-logo{display:none!important}
"""

SIDEBAR_JS = """<script>
var _sp=document.getElementById('side-panel');
var _st=document.getElementById('side-toggle');
var _po=true;
function togglePanel(){_po=!_po;_sp.classList.toggle('collapsed',!_po);_st.innerHTML=_po?'&#9776;':'&#9654;';}
</script>"""

def _sidebar_html(active="dashboard"):
    def _c(n): return "snav-btn active" if active == n else "snav-btn"
    return (
        '<div class="side-panel" id="side-panel">'
        '<div class="side-logo"><div class="logo-ico">OF</div>'
        '<div class="logo-info"><span class="logo-name">OF4MYM</span>'
        '<span class="logo-sub">Agency</span></div></div>'
        '<nav class="side-nav">'
        f'<a href="/" class="{_c("dashboard")}">'
        '<span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="1" y="1" width="6" height="6" rx="1.5"/><rect x="9" y="1" width="6" height="6" rx="1.5"/><rect x="1" y="9" width="6" height="6" rx="1.5"/><rect x="9" y="9" width="6" height="6" rx="1.5"/></svg></span>'
        '<span class="snav-lbl">Dashboard</span></a>'
        f'<a href="/warmup" class="{_c("warmup")}">'
        '<span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M8 1.5C5.5 4.5 4 7 5.5 9.5 6 10.3 6 11 6 12a2 2 0 004 0c0-1 .5-1.7 1-2.5 1.5-2.5 0-5-3-8z"/></svg></span>'
        '<span class="snav-lbl">Warm Up</span></a>'
        f'<a href="/massdm" class="{_c("massdm")}">'
        '<span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="1" y="3" width="14" height="10" rx="2"/><polyline points="1,4 8,9.5 15,4"/></svg></span>'
        '<span class="snav-lbl">Mass DM</span></a>'
        f'<a href="/scraper" class="{_c("scraper")}">'
        '<span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="7" cy="7" r="5"/><line x1="11" y1="11" x2="15" y2="15"/></svg></span>'
        '<span class="snav-lbl">Scraper</span></a>'
        f'<a href="/setup" class="{_c("setup")}">'
        '<span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="8" cy="8" r="2.5"/><path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3.2 3.2l1.1 1.1M11.7 11.7l1.1 1.1M3.2 12.8l1.1-1.1M11.7 4.3l1.1-1.1"/></svg></span>'
        '<span class="snav-lbl">Setup</span></a>'
        '</nav>'
        '<button class="side-toggle" id="side-toggle" onclick="togglePanel()">&#9776;</button>'
        '</div>'
    )


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
  thead tr { background: #060c18; }
  thead th { color: #3b5278; font-weight: 800; padding: 13px 16px;
    text-align: center; font-size: .65rem; text-transform: uppercase;
    letter-spacing: .14em; border-bottom: 2px solid #1e3a5f;
    white-space: nowrap; }
  thead th.th-l { text-align: left; }
  thead th.th-jour { text-align: center; width: 80px; }
  tbody tr { border-bottom: 1px solid #1e293b; transition: background .15s; }
  tbody tr:hover { background: #0f172a55; }
  td { padding: 14px 16px; vertical-align: middle; }
  td.num { color: #64748b; font-weight: 600; width: 36px; text-align: center; }
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
  .err-tooltip-box  { display:none; width:280px; background:#1e293b; border:1px solid #ef4444;
    border-radius:12px; padding:14px 16px; z-index:9999;
    box-shadow:0 8px 32px rgba(239,68,68,.25), 0 2px 8px rgba(0,0,0,.5);
    pointer-events:none;
    white-space:normal; word-wrap:break-word; overflow-wrap:break-word; }
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
  /* ── Graphique ── */
  .chart-card { padding: 24px 24px 20px; }
  .chart-header { display:flex; align-items:flex-start; justify-content:space-between;
    margin-bottom:22px; }
  .chart-title { color:#f8fafc; font-size:1rem; font-weight:700; margin-bottom:3px; }
  .chart-sub { color:#475569; font-size:.75rem; }
  .chart-legend { display:flex; align-items:center; gap:7px; font-size:.72rem;
    color:#22c55e; font-weight:700; text-transform:uppercase; letter-spacing:.06em;
    background:#0d2318; border:1px solid #166534; border-radius:99px; padding:4px 12px; }
  .chart-legend::before { content:''; width:8px; height:8px; border-radius:50%;
    background:#22c55e; flex-shrink:0;
    box-shadow:0 0 6px rgba(34,197,94,.8); }
  .chart-empty { padding:40px; text-align:center; color:#475569; font-size:.875rem; }
  /* ── Section titles ── */
  .section-title { font-size:.68rem; font-weight:800; color:#3b5278; text-transform:uppercase;
    letter-spacing:.14em; display:flex; align-items:center; gap:8px; margin-bottom:16px; }
  .section-title::before { content:''; width:3px; height:14px; background:#22c55e;
    border-radius:99px; flex-shrink:0; }
  /* ── Templates A/B ── */
  .templates-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(265px,1fr));
    gap:14px; margin-bottom:28px; }
  .tpl-card { background:#0f172a; border:1px solid #1e3a5f; border-radius:14px;
    padding:18px; display:flex; flex-direction:column; gap:10px; }
  .tpl-card.inactive { opacity:.48; border-style:dashed; }
  .tpl-name { font-size:.85rem; font-weight:700; color:#e2e8f0; display:flex;
    align-items:center; gap:7px; flex-wrap:wrap; line-height:1.3; }
  .tpl-num { font-size:.62rem; font-weight:800; padding:2px 9px; border-radius:99px;
    text-transform:uppercase; letter-spacing:.06em; flex-shrink:0; }
  .tpl-preview { font-size:.72rem; color:#475569; line-height:1.55; font-family:monospace;
    white-space:pre-wrap; word-break:break-word; max-height:68px; overflow:hidden;
    padding:9px 11px; background:#060c18; border-radius:8px; border:1px solid #1e293b; margin:0; }
  .tpl-stats { display:flex; border-top:1px solid #1e293b; padding-top:12px; }
  .tstat { flex:1; text-align:center; }
  .tstat + .tstat { border-left:1px solid #1e293b; }
  .tstat-val { font-size:1.15rem; font-weight:800; color:#f8fafc; line-height:1.2; }
  .tstat-val.blue  { color:#93c5fd; }
  .tstat-val.green { color:#22c55e; }
  .tstat-val.gold  { color:#fbbf24; }
  .tstat-lab { font-size:.59rem; color:#475569; text-transform:uppercase;
    letter-spacing:.06em; margin-top:2px; }
  .tpl-actions { display:flex; gap:6px; }
  .btn-tpl { font-size:.72rem; font-weight:700; padding:6px 12px; border-radius:7px;
    border:none; cursor:pointer; transition:all .15s; white-space:nowrap; }
  .btn-tpl-del { background:#450a0a; color:#fca5a5; }
  .btn-tpl-del:hover { background:#7f1d1d; }
  .btn-tpl-on  { background:#052e16; color:#86efac; border:1px solid #166534; }
  .btn-tpl-on:hover  { background:#14532d; }
  .btn-tpl-off { background:#1e293b; color:#64748b; border:1px solid #334155; }
  .btn-tpl-off:hover { background:#334155; }
  .add-textarea { width:100%; background:#0f172a; border:1px solid #334155;
    border-radius:8px; padding:10px 14px; color:#e2e8f0; font-size:.8rem;
    font-family:monospace; resize:vertical; line-height:1.5; min-height:90px; }
  .add-textarea:focus { outline:none; border-color:#22c55e; }
  .add-textarea::placeholder { color:#334155; }
  /* ── A/B Analytics table ── */
  .ab-table { width:100%; border-collapse:collapse; font-size:.875rem; }
  .ab-table th { background:#070d1b; color:#3b5278; font-weight:800; padding:10px 16px;
    text-align:center; font-size:.65rem; text-transform:uppercase; letter-spacing:.12em;
    border-bottom:2px solid #1e3a5f; white-space:nowrap; }
  .ab-table th.th-l { text-align:left; }
  .ab-table td { padding:13px 16px; border-bottom:1px solid #1e293b; vertical-align:middle; }
  .ab-table tr:last-child td { border-bottom:none; }
  .ab-table tr:hover td { background:#0f172a55; }
  .rate-bar-wrap { display:flex; align-items:center; gap:10px; }
  .rate-bar-bg { flex:1; height:7px; background:#0f172a; border-radius:99px;
    overflow:hidden; min-width:60px; }
  .rate-bar-fg { height:100%; border-radius:99px; transition:width .6s ease; }
  .rate-pct { font-size:.82rem; font-weight:800; min-width:44px; text-align:right; }
  .winner-badge { background:#052e16; color:#22c55e; border:1px solid #166534;
    font-size:.62rem; font-weight:700; padding:2px 8px; border-radius:99px; margin-left:5px; }
  /* Badge double message */
  .msg2-badge { background:#1e3a5f; color:#93c5fd; border:1px solid #1e40af;
    font-size:.58rem; font-weight:700; padding:2px 7px; border-radius:99px; margin-left:4px; }
  .tpl-preview2 { border-color:#1e3a5f !important; margin-top:4px !important; }
  .tpl-preview2::before { content:'2ème msg  '; color:#3b82f6; font-size:.68rem; font-weight:700; }
  /* Bouton toggle 2ème message */
  .btn-add-msg2 { background:none; border:1px dashed #334155; border-radius:8px;
    color:#475569; font-size:.75rem; cursor:pointer; padding:7px 14px; width:100%;
    text-align:center; transition:all .15s; margin-top:4px; }
  .btn-add-msg2:hover { border-color:#3b82f6; color:#93c5fd; background:#0f1f3d; }
  /* ── Direct DM badge ── */
  .badge-ddm { background:#2d1b69; color:#c4b5fd; border:1px solid #6d28d9;
    font-size:.62rem; font-weight:700; padding:2px 8px; border-radius:99px; }
  /* ── Modal Bio ── */
  .modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.65);
    z-index:1000; align-items:center; justify-content:center; }
  .modal-overlay.open { display:flex; }
  .modal-box { background:#1e293b; border:1px solid #334155; border-radius:18px;
    padding:28px; width:min(480px,90vw); box-shadow:0 20px 60px rgba(0,0,0,.6); }
  .modal-title { font-size:1rem; font-weight:700; color:#f8fafc; margin-bottom:16px; }
  .modal-textarea { width:100%; background:#0f172a; border:1px solid #334155;
    border-radius:8px; padding:10px 14px; color:#e2e8f0; font-size:.82rem;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    resize:vertical; min-height:90px; line-height:1.55; }
  .modal-textarea:focus { outline:none; border-color:#22c55e; }
  .modal-actions { display:flex; gap:8px; margin-top:14px; justify-content:flex-end; }
  .btn-modal-save { background:#22c55e; border:none; border-radius:8px;
    padding:9px 22px; color:#fff; font-weight:700; font-size:.85rem; cursor:pointer; }
  .btn-modal-save:hover { background:#16a34a; }
  .btn-modal-cancel { background:#1e293b; border:1px solid #334155; border-radius:8px;
    padding:9px 18px; color:#94a3b8; font-weight:600; font-size:.85rem; cursor:pointer; }
  .btn-modal-cancel:hover { background:#334155; color:#e2e8f0; }
  .btn-bio { background:#1e3a5f; border:1px solid #1e40af; color:#93c5fd;
    border-radius:7px; padding:4px 10px; font-size:.68rem; font-weight:700;
    cursor:pointer; white-space:nowrap; transition:all .15s; }
  .btn-bio:hover { background:#1d4ed8; color:#fff; }
  .btn-launch-profile { background:linear-gradient(135deg,#1e3a5f,#1e40af); border:none;
    color:#93c5fd; border-radius:7px; padding:5px 12px; font-size:.7rem; font-weight:700;
    cursor:pointer; transition:all .15s; white-space:nowrap; }
  .btn-launch-profile:hover { background:linear-gradient(135deg,#1d4ed8,#2563eb); color:#fff; }
  .btn-launch-profile:disabled { opacity:.45; cursor:not-allowed; }
  .btn-ddm { font-size:.65rem; font-weight:700; padding:4px 9px; border-radius:7px;
    border:none; cursor:pointer; transition:all .15s; white-space:nowrap; }
  .btn-ddm-warmup { background:#0f172a; color:#475569; border:1px solid #334155; }
  .btn-ddm-warmup:hover { background:#1e3a5f; color:#93c5fd; }
  .btn-ddm-active { background:#2d1b69; color:#c4b5fd; border:1px solid #6d28d9; }
  .btn-ddm-active:hover { background:#4c1d95; }
  /* ── Setup page ── */
  .setup-grid { display:grid; grid-template-columns:1fr 1fr; gap:24px; margin-bottom:24px; }
  @media(max-width:768px){ .setup-grid { grid-template-columns:1fr; } }
  .setup-form { background:#1e293b; border:1px solid #334155; border-radius:16px; padding:22px; }
  .setup-form h2 { font-size:.85rem; font-weight:700; color:#f8fafc; margin-bottom:16px; }
  .setup-field { display:flex; flex-direction:column; gap:5px; margin-bottom:12px; }
  .setup-field label { font-size:.68rem; font-weight:700; color:#3b5278;
    text-transform:uppercase; letter-spacing:.1em; }
  .setup-field input, .setup-field textarea { background:#0f172a; border:1px solid #334155;
    border-radius:8px; padding:9px 12px; color:#e2e8f0; font-size:.82rem; }
  .setup-field input:focus, .setup-field textarea:focus { outline:none; border-color:#22c55e; }
  .setup-field textarea { resize:vertical; min-height:70px; line-height:1.5; }
  .photo-preview { width:64px; height:64px; border-radius:50%; object-fit:cover;
    border:2px solid #334155; display:block; margin:6px 0; }
  .photo-placeholder { width:64px; height:64px; border-radius:50%;
    background:#0f172a; border:2px dashed #334155; display:flex;
    align-items:center; justify-content:center; color:#475569; font-size:1.4rem; }
  .setup-profiles-table { width:100%; border-collapse:collapse; font-size:.82rem; }
  .setup-profiles-table th { background:#060c18; color:#3b5278; font-weight:800;
    padding:10px 14px; text-align:left; font-size:.62rem; text-transform:uppercase;
    letter-spacing:.12em; border-bottom:2px solid #1e3a5f; }
  .setup-profiles-table td { padding:12px 14px; border-bottom:1px solid #1e293b;
    vertical-align:middle; }
  .setup-profiles-table tr:hover td { background:#0f172a33; }
  .profile-photo-thumb { width:40px; height:40px; border-radius:50%; object-fit:cover;
    border:1.5px solid #334155; }
  .btn-edit-setup { background:#1e3a5f; border:none; color:#93c5fd; border-radius:6px;
    padding:4px 10px; font-size:.7rem; font-weight:700; cursor:pointer; }
  .btn-edit-setup:hover { background:#1d4ed8; }
  /* ── Dots indicateurs statut profil ── */
  .status-dot { display:inline-block; width:11px; height:11px; border-radius:50%;
    flex-shrink:0; cursor:default; }
  .status-dot.dot-ok     { background:#22c55e; box-shadow:0 0 6px rgba(34,197,94,.6); }
  .status-dot.dot-nc     { background:#ef4444;
    box-shadow:0 0 0 0 rgba(239,68,68,.6);
    animation:pulse-dot-r 1.8s ease-in-out infinite; }
  .status-dot.dot-upload { background:#f97316;
    box-shadow:0 0 0 0 rgba(249,115,22,.6);
    animation:pulse-dot-o 1.8s ease-in-out infinite; }
  .status-dot.dot-err    { background:#f97316;
    animation:pulse-dot-o 1.8s ease-in-out infinite; }
  .status-dot.dot-none   { background:#1e293b; border:1px solid #334155; }
  @keyframes pulse-dot-r {
    0%,100% { box-shadow:0 0 0 0 rgba(239,68,68,.6); }
    50%     { box-shadow:0 0 0 5px rgba(239,68,68,0); } }
  @keyframes pulse-dot-o {
    0%,100% { box-shadow:0 0 0 0 rgba(249,115,22,.6); }
    50%     { box-shadow:0 0 0 5px rgba(249,115,22,0); } }
  .status-dot-wrap { display:flex; align-items:center; gap:7px; }
  .status-dot-lbl  { font-size:.68rem; color:#555; white-space:nowrap; }
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
            "last_error": "", "dm_mode": "warmup", "dm_day": 0}


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
                         "last_error": row.get("last_error") or "",
                         "dm_mode": row.get("dm_mode") or "warmup",
                         "dm_day":  row.get("dm_day")  or 0}

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
            "last_error": profile.get("last_error", ""),
            "dm_mode": profile.get("dm_mode", "warmup"),
            "dm_day":  profile.get("dm_day", 0)}).execute()
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
#  Supabase helpers — Templates A/B
# ═══════════════════════════════════════════════════════════

def load_dm_templates() -> list:
    try:
        result = supabase.table("dm_templates").select("*").order("id").execute()
        return result.data or []
    except Exception as e:
        print(f"[!] load_dm_templates error: {e}")
        return []


@app.get("/api/dm_templates")
def api_get_dm_templates():
    return JSONResponse(load_dm_templates())


@app.post("/api/dm_template/add")
async def api_add_dm_template(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    name     = body.get("name", "").strip()
    content  = body.get("content", "").strip()
    content2 = body.get("content2", "").strip()
    content3 = body.get("content3", "").strip()
    content4 = body.get("content4", "").strip()
    content5 = body.get("content5", "").strip()
    if not name or not content:
        raise HTTPException(status_code=400, detail="Nom et contenu requis")
    try:
        supabase.table("dm_templates").insert({
            "name": name, "content": content, "content2": content2,
            "content3": content3, "content4": content4, "content5": content5,
            "active": True, "sends": 0, "replies": 0
        }).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dm_template/update")
async def api_update_dm_template(request: Request):
    """Met à jour le contenu et/ou le nom d'un template existant."""
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    tid = body.get("id")
    if not tid:
        raise HTTPException(status_code=400, detail="id requis")
    upd: dict = {}
    if body.get("name", "").strip():
        upd["name"] = body["name"].strip()
    for k in ["content", "content2", "content3", "content4", "content5"]:
        if k in body:
            upd[k] = (body[k] or "").strip()
    if not upd:
        raise HTTPException(status_code=400, detail="Aucun champ à modifier")
    if not upd.get("content", "x"):  # content vide interdit
        raise HTTPException(status_code=400, detail="Message 1 obligatoire")
    try:
        supabase.table("dm_templates").update(upd).eq("id", tid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dm_template/delete")
async def api_del_dm_template(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    tid = body.get("id")
    try:
        supabase.table("dm_templates").delete().eq("id", tid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dm_template/toggle")
async def api_toggle_dm_template(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    tid    = body.get("id")
    active = body.get("active", True)
    try:
        supabase.table("dm_templates").update({"active": active}).eq("id", tid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dm_template/reply")
async def api_reply_dm_template(request: Request):
    """Incrémente manuellement le compteur de réponses d'un template (+1)."""
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    tid = body.get("id")
    try:
        cur = supabase.table("dm_templates").select("replies").eq("id", tid).execute()
        if cur.data:
            supabase.table("dm_templates").update(
                {"replies": cur.data[0]["replies"] + 1}
            ).eq("id", tid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dm_template/stats")
async def api_stats_dm_template(request: Request):
    """Incrémente sends et/ou replies d'un template (appelé par dm_sender.py)."""
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    tid     = body.get("template_id")
    n_sends = int(body.get("sends",   0))
    n_rep   = int(body.get("replies", 0))
    try:
        cur = supabase.table("dm_templates").select("sends,replies").eq("id", tid).execute()
        if cur.data:
            row = cur.data[0]
            supabase.table("dm_templates").update({
                "sends":   row["sends"]   + n_sends,
                "replies": row["replies"] + n_rep,
            }).eq("id", tid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
#  Supabase helpers — Setup Profils
# ═══════════════════════════════════════════════════════════

def load_profile_setup() -> list:
    try:
        result = supabase.table("profile_setup").select("*").order("profile_id").execute()
        return result.data or []
    except Exception as e:
        print(f"[!] load_profile_setup error: {e}")
        return []

def get_profile_setup(pid: str) -> dict:
    try:
        result = supabase.table("profile_setup").select("*").eq("profile_id", pid).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        print(f"[!] get_profile_setup error: {e}")
    return {}


@app.get("/api/setup")
def api_get_setup():
    return JSONResponse(load_profile_setup())


@app.post("/api/setup/upsert")
async def api_upsert_setup(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid = body.get("profile_id", "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="profile_id requis")
    try:
        update_data: dict = {
            "profile_id": pid,
            "first_name": body.get("first_name", "").strip(),
            "username":   body.get("username", "").strip().lstrip("@"),
            "bio":        body.get("bio", "").strip(),
            "updated_at": now_paris(),
        }
        # Ne remplace la photo QUE si une nouvelle est envoyée (évite d'effacer l'existante)
        new_photo = body.get("photo_b64", "")
        if new_photo:
            update_data["photo_b64"]  = new_photo
            update_data["photo_name"] = body.get("photo_name", "")

        supabase.table("profile_setup").upsert(update_data, on_conflict="profile_id").execute()

        # Si apply=True → écrit un trigger dans channels pour le daemon local
        if body.get("apply"):
            try:
                supabase.table("channels").upsert({
                    "url":           f"__profile_apply__{pid}__",
                    "status":        "triggered",
                    "members_count": 0,
                }, on_conflict="url").execute()
            except Exception:
                pass

        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/setup/delete")
async def api_delete_setup(request: Request):
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid = body.get("profile_id", "").strip()
    try:
        supabase.table("profile_setup").delete().eq("profile_id", pid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _check_adspower(profile_id: str) -> tuple:
    """
    Vérifie si un profil AdsPower existe SANS ouvrir le navigateur.
    Retourne (existe: bool, message_erreur: str).
    En cas d'erreur réseau → retourne (True, '') pour ne pas bloquer.
    """
    try:
        import requests as _req
        r = _req.get(
            "http://local.adspower.net:50325/api/v1/user/list",
            params={
                "api_key": "942d5c4fa00deedac520c3310912ee6100795935b355b33b",
                "user_id": profile_id,
            },
            timeout=5,
        )
        data = r.json()
        if data.get("code") == 0:
            lst = data.get("data", {}).get("list", [])
            if not lst:
                return False, "Profil introuvable dans AdsPower"
            return True, ""
        return False, f"AdsPower: {data.get('msg', 'code=' + str(data.get('code')))}"
    except Exception:
        return True, ""  # Erreur réseau → ne pas bloquer le batch


async def _run_mass_batch(items: list):
    """Tâche de fond — sauvegarde les photos une par une avec délai entre chaque."""
    global _mass_batch
    _mass_batch["running"]        = True
    _mass_batch["finished"]       = False
    _mass_batch["stopped"]        = False
    _mass_batch["stop_requested"] = False
    _mass_batch["total"]          = len(items)
    _mass_batch["current_idx"]    = -1
    _mass_batch["next_at"]        = None
    _mass_batch["profiles"]       = [
        {"id": it["profile_id"], "photo_name": it.get("photo_name", ""),
         "status": "pending", "error": ""}
        for it in items
    ]

    # ═══════════════════════════════════════════════════════════
    # NOUVEAU FLOW : Render sauvegarde TOUT en quelques secondes,
    # c'est warmup_v2.py LOCAL qui gère les délais entre profils.
    # Fini le problème de Render qui s'endort !
    # ═══════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════
    # Render sauve TOUTES les photos + écrit TOUS les triggers
    # en ~30 secondes. Pas de délais sur Render = pas de sleep.
    # warmup_v2.py local traite ensuite les triggers UN PAR UN.
    # ═══════════════════════════════════════════════════════════
    for i, it in enumerate(items):
        if _mass_batch["stop_requested"]:
            for j in range(i, len(items)):
                _mass_batch["profiles"][j]["status"] = "skipped"
            break

        _mass_batch["current_idx"] = i
        _mass_batch["profiles"][i]["status"] = "running"
        pid = it["profile_id"]

        # Vérifier AdsPower
        try:
            ads_ok, ads_err = await asyncio.to_thread(_check_adspower, pid)
        except Exception:
            ads_ok, ads_err = True, ""

        if not ads_ok:
            _mass_batch["profiles"][i]["status"] = "error"
            _mass_batch["profiles"][i]["error"]  = ads_err or "Profil AdsPower introuvable"
            print(f"[!] {pid} — {ads_err}", flush=True)
            await asyncio.sleep(1)
            continue

        # Sauvegarder photo + écrire trigger immédiatement (pas de délai)
        try:
            supabase.table("profile_setup").upsert({
                "profile_id": pid,
                "photo_b64":  it.get("photo_b64", ""),
                "photo_name": it.get("photo_name", ""),
                "updated_at": now_paris(),
            }, on_conflict="profile_id").execute()
            supabase.table("channels").upsert({
                "url":           f"__profile_apply__{pid}__",
                "status":        "triggered",
                "members_count": 0,
            }, on_conflict="url").execute()
            _mass_batch["profiles"][i]["status"] = "done"
            print(f"[OK] {pid} — photo + trigger OK", flush=True)
        except Exception as e:
            _mass_batch["profiles"][i]["status"] = "error"
            _mass_batch["profiles"][i]["error"]  = str(e)[:120]

        await asyncio.sleep(0.3)  # Respirer entre chaque save Supabase

    _mass_batch["running"]     = False
    _mass_batch["finished"]    = True
    _mass_batch["stopped"]     = _mass_batch["stop_requested"]
    _mass_batch["current_idx"] = -1
    _mass_batch["next_at"]     = None


@app.post("/api/setup/batch-start")
async def api_batch_start(request: Request):
    """Lance le batch mass-upload côté serveur (persiste entre navigations)."""
    global _mass_batch
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    if _mass_batch.get("running"):
        raise HTTPException(status_code=409, detail="Un batch est déjà en cours")
    items = body.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="Aucun item")
    if len(items) > 25:
        raise HTTPException(status_code=400, detail="Maximum 25 profils")
    import asyncio as _aio
    _aio.create_task(_run_mass_batch(items))
    return JSONResponse({"ok": True, "total": len(items)})


@app.post("/api/setup/apply-result")
async def api_apply_result(request: Request):
    """
    Reçoit le résultat d'un profile_changer.py (succès ou erreur).
    Appelé automatiquement à la fin de chaque exécution locale.
    """
    global _apply_results
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid   = body.get("profile_id", "").strip()
    ok    = body.get("ok", False)
    error = body.get("error", "").strip()
    if pid:
        _apply_results[pid] = {
            "ok":         ok,
            "error":      error,
            "error_type": body.get("error_type", ""),
            "at":         now_paris(),
        }
    return {"ok": True}


@app.get("/api/setup/apply-results")
def api_get_apply_results():
    """Retourne tous les résultats d'application (pour le frontend Setup)."""
    return JSONResponse(_apply_results)


@app.get("/reset-batch")
def reset_batch_get():
    """Reset forcé du batch via URL — accessible directement depuis le navigateur."""
    global _mass_batch
    _mass_batch = {
        "running": False, "finished": True, "stop_requested": False,
        "stopped": True, "profiles": [], "current_idx": -1,
        "next_at": None, "total": 0, "delay_s": 600,
    }
    return HTMLResponse("""
    <html><body style="background:#0d0d0d;color:#22c55e;font-family:monospace;
    display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:16px">
    <div style="font-size:2rem">✅ Batch réinitialisé</div>
    <div style="color:#666">Retourne sur le dashboard et recharge la page</div>
    <a href="/setup" style="color:#22c55e;margin-top:8px">← Retour au dashboard</a>
    </body></html>
    """)


@app.get("/api/setup/batch-status")
def api_batch_status():
    """Retourne l'état courant du batch (pour polling frontend)."""
    return JSONResponse(_mass_batch)


@app.post("/api/setup/batch-reset")
async def api_batch_reset(request: Request):
    """Force la réinitialisation complète du batch (déblocage en cas de gel)."""
    global _mass_batch
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    _mass_batch = {
        "running": False, "finished": True, "stop_requested": False,
        "stopped": True, "profiles": [], "current_idx": -1,
        "next_at": None, "total": 0, "delay_s": 600,
    }
    return JSONResponse({"ok": True})


@app.post("/api/setup/batch-stop")
async def api_batch_stop(request: Request):
    """Demande l'arrêt du batch en cours (interrompt le sleep entre profils)."""
    global _mass_batch
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    # Toujours mettre stop_requested AVANT de vérifier running
    # (évite la race condition entre profils où running peut être vrai
    #  mais la boucle est entre deux profils)
    _mass_batch["stop_requested"] = True
    if not _mass_batch.get("running"):
        # Batch pas en cours — retourner ok=True quand même pour que
        # le JS n'essaie pas de re-activer le bouton
        return JSONResponse({"ok": True, "msg": "Aucun batch actif, flag posé"})
    return JSONResponse({"ok": True})


@app.post("/api/setup/bio")
async def api_update_bio(request: Request):
    """Met à jour uniquement la bio d'un profil (appelé depuis Mass DM)."""
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid = body.get("profile_id", "").strip()
    bio = body.get("bio", "").strip()
    try:
        supabase.table("profile_setup").upsert(
            {"profile_id": pid, "bio": bio, "updated_at": now_paris()},
            on_conflict="profile_id"
        ).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/profile/mode")
async def api_set_profile_mode(request: Request):
    """Bascule un profil entre mode warm-up et mode Direct DM."""
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    pid  = body.get("profile_id", "").strip()
    mode = body.get("mode", "warmup")
    try:
        supabase.table("profiles").update({"dm_mode": mode}).eq("id", pid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/massdm/settings")
def api_get_massdm_settings():
    """Retourne les paramètres Mass DM (filtre genre, etc.)."""
    genre_filter = get_setting("massdm_genre_filter", "tous")
    return JSONResponse({"genre_filter": genre_filter})


@app.post("/api/massdm/settings")
async def api_set_massdm_settings(request: Request):
    """Sauvegarde les paramètres Mass DM."""
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    genre_filter = body.get("genre_filter", "tous")
    if genre_filter not in ("tous", "garcon", "fille"):
        raise HTTPException(status_code=400, detail="genre_filter invalide")
    set_setting("massdm_genre_filter", genre_filter)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
#  Supabase helpers — Settings (triggers)
# ═══════════════════════════════════════════════════════════

def get_setting(key: str, default: str = "0") -> str:
    try:
        r = supabase.table("settings").select("value").eq("key", key).execute()
        if r.data:
            return r.data[0]["value"]
    except Exception:
        pass
    return default


def set_setting(key: str, value: str):
    try:
        supabase.table("settings").upsert({"key": key, "value": value, "updated_at": now_paris()}).execute()
    except Exception as e:
        print(f"[!] set_setting error: {e}")


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


@app.post("/api/reset-errors")
async def api_reset_errors(request: Request):
    """Efface le champ last_error de tous les profils warm-up."""
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    try:
        supabase.table("profiles").update({"last_error": ""}).neq("last_error", "").execute()
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


@app.post("/api/channel/request-scrape")
async def api_request_scrape(request: Request):
    """Marque un canal 'A scraper' — scraper.py le prendra au prochain lancement."""
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    cid = body.get("channel_id")
    try:
        supabase.table("channels").update({"status": "A scraper"}).eq("id", cid).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/warmup/trigger")
async def api_warmup_trigger(request: Request):
    """Déclenche le warm-up — stocke dans Supabase (survit aux redémarrages Render)."""
    body = await request.json()
    if body.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    try:
        result = supabase.table("channels").upsert({
            "url":           "__warmup_trigger__",
            "status":        "triggered",
            "members_count": 0,
        }).execute()
        return {"ok": True, "debug_data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/warmup/poll")
def api_warmup_poll():
    """warmup_v2.py poll toutes les 30s — retourne triggered=true une fois puis reset."""
    try:
        r = supabase.table("channels").select("status").eq("url", "__warmup_trigger__").execute()
        if r.data and r.data[0]["status"] == "triggered":
            supabase.table("channels").update({"status": "done"}).eq("url", "__warmup_trigger__").execute()
            return {"triggered": True}
    except Exception:
        pass
    return {"triggered": False}


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
    if "dm_day" in body:
        profile["dm_day"]    = int(body["dm_day"] or 0)
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

# ═══════════════════════════════════════════════════════════
#  API OVERVIEW
# ═══════════════════════════════════════════════════════════

@app.get("/api/overview/stats")
def get_overview_stats(start: str = None, end: str = None):
    """Stats globales pour la page overview (filtrées par période)."""
    warmup_data = load_data()
    massdm_data = load_massdm()
    profiles    = list(warmup_data.values())
    mdm_profs   = list(massdm_data.values())

    warmup_count = sum(1 for p in profiles if 1 <= p.get("day", 1) <= 15)
    dm_available = sum(1 for p in profiles if p.get("dm_mode") == "direct_dm")

    total_dms  = 0
    total_resp = 0

    if start and end:
        try:
            start_d = datetime.strptime(start, "%Y-%m-%d").date()
            end_d   = datetime.strptime(end,   "%Y-%m-%d").date()
            for p in profiles:
                for h in p.get("history", []):
                    try:
                        d = datetime.strptime(h["date"][:10], "%d/%m/%Y").date()
                        if start_d <= d <= end_d:
                            total_dms  += h.get("dms", 0)
                            total_resp += h.get("dm_rep", 0)
                    except Exception:
                        pass
            for p in mdm_profs:
                for h in p.get("history", []):
                    try:
                        d = datetime.strptime(h["date"][:10], "%d/%m/%Y").date()
                        if start_d <= d <= end_d:
                            total_dms += h.get("sent", 0)
                    except Exception:
                        pass
        except Exception:
            total_dms  = sum(p.get("dms_sent", 0) for p in profiles) + sum(p.get("dms_sent", 0) for p in mdm_profs)
            total_resp = sum(p.get("dm_responses", 0) for p in profiles)
    else:
        total_dms  = sum(p.get("dms_sent", 0) for p in profiles) + sum(p.get("dms_sent", 0) for p in mdm_profs)
        total_resp = sum(p.get("dm_responses", 0) for p in profiles)

    unlock_rate = round(total_resp / total_dms * 100, 1) if total_dms > 0 else 0

    return JSONResponse({"warmup_count": warmup_count, "dm_available": dm_available,
                         "total_dms": total_dms, "total_responses": total_resp,
                         "unlock_rate": unlock_rate, "resultat": total_resp})


@app.get("/api/overview/chart")
def get_overview_chart(start: str = None, end: str = None):
    """Données DMs/jour pour le graphique (filtrées par période)."""
    from collections import defaultdict
    warmup_data = load_data()
    massdm_data = load_massdm()
    daily = defaultdict(int)

    now_d = datetime.now(PARIS_TZ).date()
    if not start:
        start = (now_d - timedelta(days=6)).strftime("%Y-%m-%d")
    if not end:
        end = now_d.strftime("%Y-%m-%d")

    try:
        start_d = datetime.strptime(start, "%Y-%m-%d").date()
        end_d   = datetime.strptime(end,   "%Y-%m-%d").date()

        _MN_C = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        for p in warmup_data.values():
            for h in p.get("history", []):
                try:
                    d = datetime.strptime(h["date"][:10], "%d/%m/%Y").date()
                    if start_d <= d <= end_d:
                        daily[f"{_MN_C[d.month-1]} {d.day}"] += h.get("dms", 0)
                except Exception:
                    pass
        for p in massdm_data.values():
            for h in p.get("history", []):
                try:
                    d = datetime.strptime(h["date"][:10], "%d/%m/%Y").date()
                    if start_d <= d <= end_d:
                        daily[f"{_MN_C[d.month-1]} {d.day}"] += h.get("sent", 0)
                except Exception:
                    pass

        labels, values = [], []
        cur = start_d
        while cur <= end_d:
            k = f"{_MN_C[cur.month-1]} {cur.day}"
            labels.append(k)
            values.append(daily.get(k, 0))
            cur += timedelta(days=1)

        return JSONResponse({"labels": labels, "values": values})
    except Exception as e:
        return JSONResponse({"labels": [], "values": [], "error": str(e)})


@app.get("/api/overview/history")
def get_overview_history():
    """Historique récent des activités (warmup + massdm + erreurs)."""
    warmup_data = load_data()
    massdm_data = load_massdm()
    events = []

    for pid, p in warmup_data.items():
        for h in (p.get("history") or [])[-5:]:
            events.append({"date": h.get("date", ""), "type": "warmup",
                           "pid": pid[:14], "day": h.get("day", 0), "dms": h.get("dms", 0)})
        if p.get("last_error"):
            events.append({"date": p.get("last_run", ""), "type": "error",
                           "pid": pid[:14], "message": p.get("last_error", "")[:80]})
    for pid, p in massdm_data.items():
        for h in (p.get("history") or [])[-3:]:
            events.append({"date": h.get("date", ""), "type": "massdm",
                           "pid": pid[:14], "sent": h.get("sent", 0)})

    def _key(e):
        try: return datetime.strptime(e["date"], "%d/%m/%Y %H:%M")
        except: return datetime.min

    events.sort(key=_key, reverse=True)
    return JSONResponse(events[:20])


# ═══════════════════════════════════════════════════════════
#  PAGE WARMUP  (anciennement "/")
# ═══════════════════════════════════════════════════════════

@app.get("/warmup", response_class=HTMLResponse)
def warmup_page():
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
        badge_cls   = "day-badge done" if day > 15 else "day-badge"
        dm_mode     = p.get("dm_mode", "warmup")
        dm_day      = p.get("dm_day", 0)
        if dm_mode == "direct_dm":
            ddm_btn = f'<button class="btn-ddm btn-ddm-active" onclick="toggleMode(\'{pid}\',\'warmup\')" title="Basculer en mode Warm-Up">⚡ Direct DM<br><small style="font-size:.58rem">J{dm_day}</small></button>'
        else:
            ddm_btn = f'<button class="btn-ddm btn-ddm-warmup" onclick="toggleMode(\'{pid}\',\'direct_dm\')" title="Passer en mode Direct DM (sans chauffe)">WU→DM</button>'
        rows += f"""<tr>
          <td class="num">{i}</td>
          <td class="pid">{pid}</td>
          <td class="td-prog">
            <div class="progress-wrap">
              <div class="progress-bar" style="width:{pct}%;background:#dc2626"></div>
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
          <td class="center">{ddm_btn}</td>
          <td class="last-cell">{p['last_run'] or '—'}{_err_dot(p.get('last_error',''))}</td>
          <td class="center"><button class="btn-del" onclick="delItem('{pid}','/api/profile/delete')" title="Supprimer">✕</button></td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Warm-Up Tracker</title>
<style>{BASE_CSS}
/* ── Warmup — dark dashboard theme ── */
.wu-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px}}
.wu-stat{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:20px 22px;transition:border-color .2s,box-shadow .25s,transform .25s}}
.wu-stat:hover{{border-color:#dc2626;box-shadow:0 0 24px rgba(220,38,38,.14);transform:translateY(-2px)}}
.wu-stat .sv{{font-size:2.2rem;font-weight:900;color:#f0f0f0;line-height:1}}
.wu-stat .sl{{font-size:.67rem;font-weight:800;color:#555;text-transform:uppercase;letter-spacing:.1em;margin-top:6px}}
.wu-shdr{{display:flex;align-items:center;gap:8px;margin:24px 0 14px}}
.wu-shdr .sec-bar{{width:3px;height:13px;background:#dc2626;border-radius:99px;flex-shrink:0}}
.wu-shdr .sec-title{{font-size:.7rem;font-weight:800;color:#888;text-transform:uppercase;letter-spacing:.12em}}
.wu-shdr .sec-count{{font-size:.72rem;color:#444;margin-left:auto}}
.wu-add-box{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:18px 22px;display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap}}
.wu-add-box h2{{font-size:.88rem;font-weight:700;color:#e0e0e0;white-space:nowrap}}
.wu-add-box input{{flex:1;min-width:200px;background:#0d0d0d;border:1px solid #1f1f1f;border-radius:8px;padding:10px 14px;color:#e0e0e0;font-size:.875rem;font-family:monospace;transition:border-color .15s}}
.wu-add-box input:focus{{outline:none;border-color:#dc2626}}
.wu-add-box button{{background:#dc2626;border:none;border-radius:8px;padding:10px 22px;color:#fff;font-weight:700;font-size:.82rem;cursor:pointer;transition:all .15s;white-space:nowrap}}
.wu-add-box button:hover{{background:#b91c1c}}
.wu-actions-bar{{display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap}}
.btn-launch{{background:linear-gradient(135deg,#dc2626,#b91c1c);color:#fff;border:none;border-radius:10px;padding:12px 28px;font-size:.92rem;font-weight:800;cursor:pointer;box-shadow:0 0 18px rgba(220,38,38,.3);transition:all .2s;letter-spacing:.02em}}
.btn-launch:hover{{box-shadow:0 0 28px rgba(220,38,38,.55)}}
.btn-launch:disabled{{opacity:.5;cursor:not-allowed;box-shadow:none}}
.btn-reset-err{{background:#1a0a0a;color:#f87171;border:1px solid #3d1212;border-radius:10px;padding:12px 22px;font-size:.82rem;font-weight:700;cursor:pointer;transition:all .15s}}
.btn-reset-err:hover{{background:#450a0a;border-color:#7f1d1d}}
.launch-msg{{display:none;margin-left:4px;color:#4ade80;font-size:.82rem;font-weight:700}}
.wu-table-card{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;overflow:hidden;margin-bottom:16px}}
.wu-table-card table{{width:100%;border-collapse:collapse;font-size:.875rem}}
.wu-table-card thead tr{{background:#0d0d0d}}
.wu-table-card thead th{{color:#333;font-weight:800;padding:13px 16px;text-align:center;font-size:.62rem;text-transform:uppercase;letter-spacing:.12em;border-bottom:1px solid #1a1a1a;white-space:nowrap}}
.wu-table-card thead th.thl{{text-align:left}}
.wu-table-card tbody tr{{border-bottom:1px solid #1a1a1a;transition:background .15s}}
.wu-table-card tbody tr:hover{{background:rgba(220,38,38,.04)}}
.wu-table-card td{{padding:14px 16px;vertical-align:middle;color:#888;font-size:.82rem}}
.wu-table-card td.num{{color:#333;text-align:center;font-size:.75rem;width:36px}}
.wu-table-card td.pid{{font-family:monospace;color:#666;font-size:.78rem}}
.wu-table-card td.center{{text-align:center}}
.wu-table-card td.td-prog{{min-width:140px}}
.wu-table-card td.td-jour{{text-align:center;width:70px}}
.wu-table-card td.last-cell{{color:#444;font-size:.75rem;white-space:nowrap}}
/* Progress bar */
.progress-wrap{{background:#0d0d0d;border-radius:99px;height:6px;overflow:hidden;width:100%;border:1px solid #1a1a1a}}
.progress-bar{{height:100%;border-radius:99px;transition:width .6s ease}}
.day-label{{font-size:.68rem;color:#444;margin-top:5px;display:block;text-align:center}}
/* Day badge */
.day-badge{{display:inline-flex;align-items:center;justify-content:center;width:56px;height:56px;border-radius:10px;font-weight:800;background:#1a1a1a;border:1.5px solid #2a2a2a;flex-direction:column;gap:0;line-height:1.1}}
.day-badge .badge-num{{font-size:1.2rem;font-weight:900;color:#ccc}}
.day-badge .badge-max{{font-size:.6rem;color:#444;font-weight:600}}
.day-badge.done{{background:#1a0d0d;border-color:#3d1212;box-shadow:0 0 8px rgba(220,38,38,.18)}}
.day-badge.done .badge-num{{color:#f87171}}
.day-badge.done .badge-max{{color:#dc2626}}
/* Status badges */
.badge{{display:inline-block;padding:3px 10px;border-radius:99px;font-size:.68rem;font-weight:700;letter-spacing:.05em}}
.badge.done{{background:rgba(22,163,74,.15);color:#4ade80;border:1px solid rgba(22,163,74,.25)}}
.badge.today{{background:rgba(22,163,74,.15);color:#4ade80;border:1px solid rgba(22,163,74,.25)}}
.badge.pending{{background:#1a1a1a;color:#555;border:1px solid #2a2a2a}}
.badge.waiting{{background:#111;color:#333;border:1px solid #1a1a1a}}
.badge.error{{background:rgba(220,38,38,.15);color:#f87171;border:1px solid rgba(220,38,38,.25)}}
/* DDM toggle */
.btn-ddm{{border-radius:7px;padding:5px 10px;font-size:.68rem;font-weight:800;cursor:pointer;transition:all .15s;border:1px solid transparent;line-height:1.3;text-align:center}}
.btn-ddm-active{{background:rgba(220,38,38,.18);color:#f87171;border-color:rgba(220,38,38,.35)}}
.btn-ddm-active:hover{{background:rgba(220,38,38,.28)}}
.btn-ddm-warmup{{background:#1a1a1a;color:#555;border-color:#2a2a2a}}
.btn-ddm-warmup:hover{{border-color:#dc2626;color:#f0f0f0}}
/* Del button */
.btn-del{{background:#1a0a0a;border:1px solid #3d1212;color:#666;border-radius:6px;padding:5px 10px;font-size:.75rem;cursor:pointer;transition:all .15s}}
.btn-del:hover{{background:#450a0a;color:#fca5a5;border-color:#7f1d1d}}
/* Toast */
.toast{{display:none;position:fixed;top:20px;right:20px;background:#141414;border:1px solid #dc2626;color:#f0f0f0;padding:12px 20px;border-radius:8px;font-weight:600;z-index:999;box-shadow:0 0 20px rgba(220,38,38,.3)}}
/* Error dot + tooltip */
.err-dot{{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;font-size:.7rem;font-weight:700;margin-left:6px;vertical-align:middle;flex-shrink:0;cursor:pointer;position:relative}}
.err-ok{{background:#0a1a0a;color:#4ade80;border:1px solid #166534}}
.err-warn{{background:#1a0a0a;color:#f87171;border:1.5px solid #dc2626;animation:pulse-err 2s ease-in-out infinite}}
@keyframes pulse-err{{0%,100%{{box-shadow:0 0 0 0 rgba(220,38,38,.5)}}50%{{box-shadow:0 0 0 6px rgba(220,38,38,0)}}}}
.err-tooltip-wrap{{position:relative;display:inline-flex;align-items:center}}
.err-tooltip-box{{display:none;width:280px;background:#141414;border:1px solid #dc2626;border-radius:12px;padding:14px 16px;z-index:9999;box-shadow:0 8px 32px rgba(220,38,38,.2),0 2px 8px rgba(0,0,0,.6);pointer-events:none;white-space:normal;word-wrap:break-word}}
.err-tooltip-box::after{{content:'';position:absolute;bottom:-7px;right:8px;width:13px;height:13px;background:#141414;border-right:1px solid #dc2626;border-bottom:1px solid #dc2626;transform:rotate(45deg)}}
.err-tooltip-title{{font-size:.72rem;font-weight:700;color:#f87171;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;display:flex;align-items:center;gap:6px}}
.err-tooltip-title::before{{content:'⚠';font-size:.9rem}}
.err-tooltip-msg{{font-size:.78rem;color:#ccc;line-height:1.5}}
.err-tooltip-hint{{font-size:.7rem;color:#555;margin-top:8px;padding-top:8px;border-top:1px solid #1f1f1f;line-height:1.4}}
.err-ok-wrap{{display:inline-flex;align-items:center}}
{SIDEBAR_CSS}</style>
<meta http-equiv="refresh" content="60"></head><body>
<div class="ov-layout">{_sidebar_html('warmup')}<div class="page-main">

  <!-- ── Header ── -->
  <div class="ov-header" style="margin-bottom:24px">
    <div class="ov-title">Warm-Up</div>
    <div class="ov-subtitle">Suivi de {n} profils AdsPower — chauffe progressive sur 15 jours</div>
  </div>

  <!-- ── Stats ── -->
  <div class="wu-stats">
    <div class="wu-stat"><div class="sv">{done_today}<span style="color:#2a2a2a;font-size:1.4rem">/{n}</span></div><div class="sl">Faits aujourd'hui</div></div>
    <div class="wu-stat"><div class="sv">{total_dms}</div><div class="sl">DMs envoyes</div></div>
    <div class="wu-stat"><div class="sv">{total_posts}</div><div class="sl">Posts canaux</div></div>
    <div class="wu-stat"><div class="sv">{total_groups}</div><div class="sl">Groupes rejoints</div></div>
    <div class="wu-stat"><div class="sv" style="color:#dc2626">{finished}</div><div class="sl">Chauffes terminees</div></div>
  </div>

  <!-- ── Actions ── -->
  <div class="wu-shdr">
    <div class="sec-bar"></div>
    <div class="sec-title">Actions</div>
  </div>
  <div class="wu-actions-bar">
    <button id="btn-launch" class="btn-launch" onclick="launchWarmup()">▶ Lancer le Warm-Up</button>
    <span id="launch-msg" class="launch-msg">✓ Signal envoye — demarrage dans ~30s</span>
    <button id="btn-reset-err" class="btn-reset-err" onclick="resetErrors()">🔄 Reinitialiser les erreurs</button>
    <span id="reset-err-msg" class="launch-msg">✓ Erreurs effacees</span>
  </div>

  <!-- ── Ajouter un profil ── -->
  <div class="wu-shdr">
    <div class="sec-bar"></div>
    <div class="sec-title">Ajouter un profil</div>
  </div>
  <div class="wu-add-box">
    <h2>+ Nouveau profil</h2>
    <input id="inp" type="text" placeholder="ID AdsPower  ex: k1abc123">
    <button onclick="addItem()">Ajouter</button>
  </div>

  <!-- ── Tableau des profils ── -->
  <div class="wu-shdr">
    <div class="sec-bar"></div>
    <div class="sec-title">Profils</div>
    <div class="sec-count">{n} profil{'s' if n > 1 else ''}</div>
  </div>
  <div class="wu-table-card"><table><thead><tr>
    <th class="thl" style="width:36px">#</th>
    <th class="thl">ID Profil</th>
    <th class="thl" style="min-width:160px">Progression</th>
    <th>Jour</th>
    <th>DMs</th>
    <th>Posts</th>
    <th>Groupes</th>
    <th>Rep.</th>
    <th>Statut</th>
    <th>Mode</th>
    <th>Derniere session</th>
    <th style="width:40px"></th>
  </tr></thead><tbody>{rows}</tbody></table></div>

  <p class="refresh" style="color:#333;font-size:.72rem;text-align:center">Mis a jour par warmup_v2.py apres chaque profil — refresh auto 60s</p>
  {add_js('/api/profile/add', 'inp', 'Profil ajoute !')}
<script>
async function launchWarmup() {{
  const btn = document.getElementById('btn-launch');
  btn.disabled = true;
  btn.textContent = '⏳ Envoi du signal...';
  // Ecrit DIRECTEMENT dans Supabase — bypasse Render (100% fiable)
  const SUPA_URL = 'https://pirlgavzihmnwmqlyeir.supabase.co';
  const SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBpcmxnYXZ6aWhtbndtcWx5ZWlyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3MzQxMTAsImV4cCI6MjA5NTMxMDExMH0.0QdskD9IBsx1rUZ_7Sljb8DshovkQMJIhmnAM-Zc6Ps';
  const HDRS = {{
    'apikey': SUPA_KEY,
    'Authorization': `Bearer ${{SUPA_KEY}}`,
    'Content-Type': 'application/json',
    'Prefer': 'resolution=merge-duplicates,return=minimal'
  }};
  try {{
    // 1. Efface tout trigger mass DM en attente (évite double terminal)
    await fetch(`${{SUPA_URL}}/rest/v1/channels?url=eq.__massdm_trigger__`, {{
      method: 'PATCH', headers: HDRS,
      body: JSON.stringify({{status:'idle'}})
    }});
    // 2. Active le trigger warm-up
    const r = await fetch(`${{SUPA_URL}}/rest/v1/channels?on_conflict=url`, {{
      method: 'POST', headers: HDRS,
      body: JSON.stringify({{url:'__warmup_trigger__', status:'triggered', members_count:0}})
    }});
    if (r.ok || r.status === 201 || r.status === 200 || r.status === 204) {{
      btn.textContent = '✓ Signal envoyé';
      btn.style.background = '#1e293b';
      document.getElementById('launch-msg').style.display = 'inline';
    }} else {{
      const err = await r.text();
      throw new Error(err);
    }}
  }} catch(e) {{
    btn.disabled = false;
    btn.textContent = '▶ Lancer le Warm-Up maintenant';
    alert('Erreur Supabase : ' + e.message);
  }}
}}
async function toggleMode(pid, mode) {{
  const label = mode === 'direct_dm'
    ? '⚡ Passer ce profil en mode Mass DM ?\\n(Il sautera le warm-up et enverra directement des DMs depuis le CSV scrappe)'
    : 'Repasser ce profil en mode Warm-Up ?';
  if (!confirm(label)) return;
  const r = await fetch('/api/profile/mode', {{
    method: 'POST', headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{token:'Compte.1', profile_id: pid, mode}})
  }});
  const d = await r.json();
  if (d.ok) {{
    // Redirige vers l'onglet Mass DM si on active le mode, sinon recharge
    if (mode === 'direct_dm') window.location.href = '/massdm';
    else location.reload();
  }} else alert('Erreur : ' + JSON.stringify(d));
}}
async function resetErrors() {{
  const btn = document.getElementById('btn-reset-err');
  btn.disabled = true;
  btn.textContent = '⏳ En cours...';
  try {{
    const r = await fetch('/api/reset-errors', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{token: 'Compte.1'}})
    }});
    const d = await r.json();
    if (d.ok) {{
      btn.textContent = '✓ Effacé';
      btn.style.background = '#052e16';
      btn.style.color = '#86efac';
      document.getElementById('reset-err-msg').style.display = 'inline';
      setTimeout(() => location.reload(), 1500);
    }} else {{
      throw new Error(JSON.stringify(d));
    }}
  }} catch(e) {{
    btn.disabled = false;
    btn.textContent = '🔄 Réinitialiser les erreurs';
    alert('Erreur : ' + e.message);
  }}
}}
</script>
<script>
(function(){{
  document.querySelectorAll('.err-tooltip-wrap').forEach(function(wrap){{
    var box = wrap.querySelector('.err-tooltip-box');
    if (!box) return;
    wrap.addEventListener('mouseenter', function(){{
      var dot = wrap.querySelector('.err-dot');
      var r   = dot.getBoundingClientRect();
      var W   = 280;
      /* alignement horizontal : bord droit du tooltip = bord droit du point, sans deborder a gauche */
      var left = Math.max(10, r.right - W);
      /* afficher hors-ecran pour mesurer la hauteur reelle */
      box.style.cssText = 'display:block;position:fixed;width:'+W+'px;left:'+left+'px;top:-9999px;right:auto;bottom:auto;z-index:9999;';
      var H   = box.offsetHeight;
      /* prefere au-dessus, bascule en-dessous si pas assez de place */
      var top = r.top - H - 12;
      if (top < 10) top = r.bottom + 8;
      box.style.top = top + 'px';
    }});
    wrap.addEventListener('mouseleave', function(){{
      box.style.display = 'none';
    }});
  }});
}})();
</script>
</div></div>{SIDEBAR_JS}
</body></html>"""
    return html


# ═══════════════════════════════════════════════════════════
#  PAGE OVERVIEW  (page principale "/")
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def overview():
    """Overview / Dashboard — page principale."""
    from collections import defaultdict

    # ── Données initiales ──────────────────────────────────────
    warmup_data = load_data()
    massdm_data = load_massdm()
    profiles    = list(warmup_data.values())
    mdm_profs   = list(massdm_data.values())

    warmup_count = sum(1 for p in profiles if 1 <= p.get("day", 1) <= 15)
    dm_available = sum(1 for p in profiles if p.get("dm_mode") == "direct_dm")
    total_wu_dms = sum(p.get("dms_sent", 0) for p in profiles)
    total_md_dms = sum(p.get("dms_sent", 0) for p in mdm_profs)
    total_dms    = total_wu_dms + total_md_dms   # warmup + massdm
    total_resp   = sum(p.get("dm_responses", 0) for p in profiles)
    unlock_rate  = round(total_resp / total_dms * 100, 1) if total_dms > 0 else 0

    # ── Chart : 7 derniers jours (SSR) ────────────────────────
    _MN_EN = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    today_d = datetime.now(PARIS_TZ).date()
    daily   = defaultdict(int)
    labels_7 = []
    for i in range(6, -1, -1):
        d = today_d - timedelta(days=i)
        labels_7.append(f"{_MN_EN[d.month-1]} {d.day}")
    for p in profiles:
        for h in p.get("history", []):
            try:
                d = datetime.strptime(h["date"][:10], "%d/%m/%Y").date()
                if today_d - timedelta(days=6) <= d <= today_d:
                    daily[f"{_MN_EN[d.month-1]} {d.day}"] += h.get("dms", 0)
            except Exception:
                pass
    for p in mdm_profs:
        for h in p.get("history", []):
            try:
                d = datetime.strptime(h["date"][:10], "%d/%m/%Y").date()
                if today_d - timedelta(days=6) <= d <= today_d:
                    daily[f"{_MN_EN[d.month-1]} {d.day}"] += h.get("sent", 0)
            except Exception:
                pass
    values_7 = [daily.get(l, 0) for l in labels_7]
    chart_labels_json = json.dumps(labels_7)
    chart_values_json = json.dumps(values_7)

    # ── History (SSR) ─────────────────────────────────────────
    hist_events = []
    for pid, p in warmup_data.items():
        for h in (p.get("history") or [])[-4:]:
            hist_events.append({"date": h.get("date",""), "type":"warmup",
                                 "pid": pid[:14], "day": h.get("day",0), "dms": h.get("dms",0)})
        if p.get("last_error"):
            hist_events.append({"date": p.get("last_run",""), "type":"error",
                                 "pid": pid[:14], "message": p.get("last_error","")[:80]})
    for pid, p in massdm_data.items():
        for h in (p.get("history") or [])[-2:]:
            hist_events.append({"date": h.get("date",""), "type":"massdm",
                                 "pid": pid[:14], "sent": h.get("sent",0)})

    def _ev_key(e):
        try: return datetime.strptime(e["date"], "%d/%m/%Y %H:%M")
        except: return datetime.min
    hist_events.sort(key=_ev_key, reverse=True)
    hist_events = hist_events[:15]

    # ── Ring chart params ────────────────────────────────────
    ring_r   = 72
    ring_c   = round(2 * 3.14159 * ring_r, 2)
    ring_off = round(ring_c * (1 - min(unlock_rate, 100) / 100), 2)
    n_profiles = len(profiles)
    dm_pct   = min(round(dm_available / max(n_profiles, 1) * 100), 100)

    # ── Mini bars (NEW CONVERSATIONS card) ───────────────────
    max_v7 = max(values_7) if any(values_7) else 1
    mini_bars_html = ""
    for _vi, _vv in enumerate(values_7):
        _pct = round(_vv / max_v7 * 100) if max_v7 > 0 else 5
        _hi  = " hi" if _vi == len(values_7) - 1 else ""
        mini_bars_html += f'<div class="mbar{_hi}" style="height:{max(_pct, 5)}%"></div>'

    # ── History rows (avatars numérotés) ─────────────────────
    HIST_COLORS = ['#dc2626','#ea580c','#d97706','#16a34a','#0891b2','#7c3aed','#db2777']
    _all_pids   = get_all_ids()
    _pid_to_num = {pid[:14]: str(i + 1) for i, pid in enumerate(_all_pids)}
    hist_rows_html = ""
    if not hist_events:
        hist_rows_html = '<div class="hist-empty">Aucune activité récente</div>'
    for _hi2, _ev in enumerate(hist_events[:10]):
        _date   = (_ev.get("date") or "")[:16]
        _pid    = _ev.get("pid", "")
        _num    = _pid_to_num.get(_pid, "?")
        _color  = HIST_COLORS[_hi2 % len(HIST_COLORS)]
        if _ev["type"] == "warmup":
            _hname = _pid; _hmeta = f"Warm Up &bull; J{_ev['day']} &bull; {_date}"; _hamt = f"+&#9733; {_ev['dms']}"
        elif _ev["type"] == "massdm":
            _hname = _pid; _hmeta = f"Mass DM &bull; {_date}"; _hamt = f"+&#9733; {_ev.get('sent',0)}"
        else:
            _raw = (_ev.get("message") or "")[:50].replace("<","&lt;").replace(">","&gt;")
            _hname = _pid; _hmeta = f"Erreur &bull; {_date}"; _hamt = "&#9888;"
        hist_rows_html += (
            f'<div class="hist-row">'
            f'<div class="hava" style="background:{_color}">{_num}</div>'
            f'<div class="hinfo"><div class="hname">{_hname}</div>'
            f'<div class="hmeta">{_hmeta}</div></div>'
            f'<div class="hamount">{_hamt}</div></div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard — OF4MYM</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d0d0d;color:#f0f0f0;overflow:hidden}}
a{{text-decoration:none;color:inherit}}button{{font-family:inherit;cursor:pointer}}

/* LAYOUT */
.ov-layout{{display:flex;height:100vh;overflow:hidden}}

/* ── SIDEBAR ── */
.side-panel{{width:220px;background:#0a0a0a;border-right:1px solid #1a1a1a;display:flex;flex-direction:column;flex-shrink:0;transition:width .25s cubic-bezier(.4,0,.2,1);overflow:hidden}}
.side-panel.collapsed{{width:60px}}
.side-logo{{padding:22px 18px 18px;border-bottom:1px solid #1a1a1a;display:flex;align-items:center;gap:12px;flex-shrink:0}}
.logo-ico{{width:36px;height:36px;border-radius:8px;flex-shrink:0;background:#1f0808;border:1px solid #3d1212;display:flex;align-items:center;justify-content:center;font-size:.55rem;font-weight:900;color:#dc2626;letter-spacing:.02em}}
.logo-info{{overflow:hidden;white-space:nowrap;transition:opacity .2s}}
.side-panel.collapsed .logo-info{{opacity:0;pointer-events:none}}
.logo-name{{font-size:.85rem;font-weight:800;color:#f0f0f0;display:block;letter-spacing:.04em}}
.logo-sub{{font-size:.6rem;color:#444;display:block;margin-top:3px;text-transform:uppercase;letter-spacing:.08em}}
.side-nav{{padding:14px 10px 14px 20px;flex:1;display:flex;flex-direction:column;gap:2px;overflow:hidden}}
.snav-btn{{display:flex;align-items:center;gap:12px;padding:18px 12px;border-radius:8px;color:#555;font-size:.9rem;font-weight:600;white-space:nowrap;overflow:hidden;transition:all .15s;border-right:3px solid transparent;position:relative}}
.snav-btn:hover{{background:#141414;color:#aaa}}
.snav-btn.active{{background:rgba(220,38,38,.1);color:#dc2626;border-right:3px solid #dc2626;border-radius:8px 0 0 8px}}
.snav-ico{{width:18px;height:18px;flex-shrink:0;display:flex;align-items:center;justify-content:center}}
.snav-lbl{{transition:opacity .15s}}
.side-panel.collapsed .snav-lbl{{opacity:0;pointer-events:none}}
.side-panel.collapsed .snav-btn{{justify-content:center;padding:11px}}
.side-panel.collapsed .snav-btn.active{{border-radius:8px;border-right:3px solid #dc2626}}
.side-toggle{{margin:10px 10px 16px;background:none;border:1px solid #1e1e1e;border-radius:8px;padding:8px;color:#333;font-size:.75rem;display:flex;align-items:center;justify-content:center;transition:all .15s;flex-shrink:0}}
.side-toggle:hover{{border-color:#dc2626;color:#dc2626}}

/* ── MAIN ── */
.ov-main{{flex:1;overflow-y:auto;padding:70px 380px 40px 74px;min-width:0;background:#0d0d0d}}
.ov-main::-webkit-scrollbar{{width:4px}}
.ov-main::-webkit-scrollbar-thumb{{background:#222;border-radius:2px}}

/* ── HEADER ── */
.ov-header{{margin-bottom:28px}}
.ov-title{{font-size:2rem;font-weight:800;color:#f0f0f0;line-height:1;white-space:nowrap}}
.ov-subtitle{{font-size:.88rem;color:#666;margin-top:6px;white-space:nowrap}}

/* ── DATE PICKER ── */
.dp-wrap{{position:relative}}
.dp-trigger{{display:flex;align-items:center;gap:8px;background:#141414;border:1px solid #222;border-radius:10px;padding:9px 16px;color:#888;font-size:.78rem;font-weight:600;white-space:nowrap;transition:all .15s}}
.dp-trigger:hover{{border-color:#dc2626;color:#f0f0f0}}
.dp-popup{{display:none;position:fixed;top:auto;right:auto;z-index:9999;background:#111;border:1px solid #2a2a2a;border-radius:14px;box-shadow:0 24px 80px rgba(0,0,0,.9);overflow:hidden}}
.dp-popup.open{{display:flex}}
.dp-presets{{padding:14px 10px;border-right:1px solid #1e1e1e;display:flex;flex-direction:column;gap:4px;min-width:155px}}
.dp-pre{{background:#0d0d0d;border:1px solid #2a2a2a;border-radius:8px;padding:10px 14px;color:#aaa;font-size:.77rem;font-weight:600;text-align:left;white-space:nowrap;transition:all .12s;width:100%;cursor:pointer}}
.dp-pre:hover{{background:#1e1e1e;color:#f0f0f0;border-color:#444}}
.dp-pre.active{{background:#dc2626;border-color:#dc2626;color:#fff}}
.dp-cals{{padding:18px 22px}}
.dp-cals-nav{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}}
.dp-nav{{background:none;border:1px solid #2a2a2a;border-radius:6px;width:28px;height:28px;color:#666;display:flex;align-items:center;justify-content:center;font-size:.8rem;transition:all .12s;cursor:pointer}}
.dp-nav:hover{{border-color:#dc2626;color:#dc2626}}
.dp-months{{display:flex;gap:32px}}
.dp-month{{min-width:200px}}
.dp-month-title{{text-align:center;font-size:.82rem;font-weight:700;color:#f0f0f0;margin-bottom:12px;letter-spacing:.04em}}
.dp-cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}}
.dp-day{{text-align:center;padding:8px 3px;font-size:.74rem;color:#555;border-radius:50%;transition:all .1s;line-height:1.3;aspect-ratio:1;display:flex;align-items:center;justify-content:center}}
.dp-day.hd{{color:#444;font-size:.65rem;font-weight:700;border-radius:0;aspect-ratio:auto;padding:4px 0 8px}}
.dp-day.other{{color:#252525}}
.dp-day.click{{cursor:pointer}}
.dp-day.click:hover{{background:#222;color:#f0f0f0}}
.dp-day.start,.dp-day.end{{background:#dc2626!important;color:#fff!important;font-weight:700;border-radius:50%}}
.dp-day.inrange{{background:rgba(220,38,38,.18);color:#ddd;border-radius:3px}}

/* ── TOP NAV ROW ── */
.ov-topnav{{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;gap:10px;flex-wrap:wrap}}
.ov-tabs{{display:flex;gap:3px}}
.ov-tab{{background:#161616;border:1px solid #252525;border-radius:7px;padding:5px 16px;color:#555;font-size:.72rem;font-weight:700;cursor:pointer;transition:all .15s;letter-spacing:.03em}}
.ov-tab.active{{background:#f0f0f0;color:#0d0d0d;border-color:#f0f0f0}}
.ov-tab:hover:not(.active){{background:#222;color:#aaa}}
.ov-topnav-right{{display:flex;align-items:center;gap:6px;flex-wrap:wrap}}
.plat-filters{{display:flex;gap:3px}}
.plat-btn{{display:flex;align-items:center;gap:5px;padding:5px 11px;border-radius:7px;border:1px solid transparent;font-size:.7rem;font-weight:700;cursor:pointer;background:#1c1c1c;color:#555;white-space:nowrap;transition:all .15s}}
.plat-btn.active{{background:#dc2626;color:#fff;border-color:#dc2626}}
.plat-btn:hover:not(.active){{background:#222;color:#aaa}}
.plat-ico-only{{padding:5px 8px}}
.all-crt-btn{{display:flex;align-items:center;gap:6px;padding:5px 13px;border-radius:7px;border:1px solid #252525;background:#161616;color:#888;font-size:.72rem;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap}}
.all-crt-btn:hover{{border-color:#444;color:#f0f0f0}}

/* ── STATS GRID ── */
.ov-cards{{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;grid-template-rows:minmax(130px,1fr) minmax(110px,auto);gap:12px;margin-bottom:18px}}
.ov-card{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:18px;display:flex;flex-direction:column;transition:border-color .2s,box-shadow .25s,transform .25s}}
.ov-card:hover{{border-color:#dc2626;box-shadow:0 0 28px rgba(220,38,38,.18);transform:translateY(-3px)}}
.ov-card.locked{{opacity:.35;pointer-events:none;border-style:dashed}}
.ctag{{font-size:.67rem;font-weight:800;color:#888;text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between}}
.ctag-ico{{color:#666;font-size:.85rem}}
.cval{{font-size:2.2rem;font-weight:900;color:#f0f0f0;line-height:1;margin:4px 0}}
.cdesc{{font-size:.8rem;color:#666;margin-top:4px}}

/* UNLOCK RATE card */
.card-unlock{{grid-row:1/3}}
.unlock-box{{display:flex;flex-direction:column;align-items:center;gap:14px;width:100%;flex:1;justify-content:center;margin-top:6px}}
.ring-svg{{overflow:visible}}
.ring-track{{fill:none;stroke:#1f1f1f;stroke-width:13}}
.ring-fill{{fill:none;stroke:#dc2626;stroke-width:13;stroke-linecap:round;transform-origin:center;transform:rotate(-90deg);filter:drop-shadow(0 0 14px rgba(220,38,38,.5));transition:stroke-dashoffset .8s ease}}
.ring-pct{{font-size:2.6rem;font-weight:900;fill:#dc2626;text-anchor:middle;dominant-baseline:central}}
.unlock-sub{{font-size:.8rem;color:#777;text-align:center;letter-spacing:.04em}}

/* Progress bar (DM card) */
.prog-row{{margin-top:auto;padding-top:10px;display:flex;align-items:center;gap:8px}}
.prog-bg{{flex:1;height:4px;background:#222;border-radius:2px;overflow:hidden}}
.prog-fg{{height:100%;background:#dc2626;border-radius:2px;transition:width .5s}}
.prog-pct{{font-size:.7rem;color:#38bdf8;font-weight:800;white-space:nowrap}}

/* Redacted bars (BIENTÔT card) */
.redacted-bars{{display:flex;flex-direction:column;gap:6px;margin-top:10px;flex:1}}
.redact-row{{display:flex;align-items:center;gap:8px}}
.redact-bar{{height:10px;background:#1a1a1a;border-radius:3px}}
.redact-dot{{width:8px;height:8px;border-radius:50%;background:#1a1a1a;flex-shrink:0}}

/* Mini bars (NEW CONVERSATIONS) */
.mini-bars{{display:flex;align-items:flex-end;gap:3px;margin-top:auto;padding-top:8px;height:32px}}
.mbar{{flex:1;background:rgba(220,38,38,.3);border-radius:2px 2px 0 0;min-height:3px}}
.mbar.hi{{background:#dc2626}}

/* ── BOTTOM ROW ── */
.ov-bottom{{display:grid;grid-template-columns:1fr 310px;gap:14px}}
.ov-chart-card{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:0;overflow:hidden;display:flex;flex-direction:column}}
.ov-hist-card{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:20px}}
.ov-chart-card .sec-hdr{{padding:14px 18px 8px;flex-shrink:0}}
.sec-hdr{{display:flex;align-items:center;gap:8px;margin-bottom:14px}}
.sec-bar{{width:3px;height:13px;background:#dc2626;border-radius:99px;flex-shrink:0}}
.sec-title{{font-size:.7rem;font-weight:800;color:#888;text-transform:uppercase;letter-spacing:.12em;flex:none;margin-right:auto}}
.sec-sub{{font-size:.78rem;color:#666}}
.bar-chart-svg{{width:100%;display:block;flex:1;min-height:200px}}

/* History */
.hist-list{{display:flex;flex-direction:column}}
.hist-row{{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #1a1a1a}}
.hist-row:last-child{{border-bottom:none}}
.hava{{width:30px;height:30px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:.6rem;font-weight:800;color:#fff}}
.hinfo{{flex:1;min-width:0}}
.hname{{font-size:.85rem;font-weight:700;color:#e0e0e0}}
.hmeta{{font-size:.72rem;color:#666;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.hamount{{font-size:.82rem;font-weight:700;color:#e0e0e0;white-space:nowrap}}
.hist-empty{{color:#666;font-size:.82rem;text-align:center;padding:20px}}

@media(max-width:1200px){{.ov-bottom{{grid-template-columns:1fr}}}}
@media(max-width:900px){{.ov-cards{{grid-template-columns:1fr 1fr;}}}}

/* ── BAR TOOLTIP ── */
.bar-tip{{position:fixed;background:#0d0d0d;border:1px solid #2a2a2a;border-radius:14px;padding:13px 20px;pointer-events:none;z-index:9999;display:none;box-shadow:0 12px 40px rgba(0,0,0,.8),0 0 0 1px rgba(220,38,38,.08);min-width:140px}}
.bar-tip-jour{{font-size:.68rem;color:#555;font-weight:700;margin-bottom:6px;font-family:sans-serif;letter-spacing:.08em;text-transform:uppercase}}
.bar-tip-dm{{font-size:1.5rem;font-weight:900;color:#dc2626;font-family:sans-serif;letter-spacing:.01em;line-height:1}}
</style>
</head>
<body>
<div class="ov-layout">

<!-- ═══ SIDEBAR ═══ -->
<div class="side-panel" id="side-panel">
  <div class="side-logo">
    <div class="logo-ico">OF</div>
    <div class="logo-info">
      <span class="logo-name">OF4MYM</span>
      <span class="logo-sub">Agency</span>
    </div>
  </div>
  <nav class="side-nav">
    <a href="/" class="snav-btn active">
      <span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="1" y="1" width="6" height="6" rx="1.5"/><rect x="9" y="1" width="6" height="6" rx="1.5"/><rect x="1" y="9" width="6" height="6" rx="1.5"/><rect x="9" y="9" width="6" height="6" rx="1.5"/></svg></span>
      <span class="snav-lbl">Dashboard</span>
    </a>
    <a href="/warmup" class="snav-btn">
      <span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M8 1.5C5.5 4.5 4 7 5.5 9.5 6 10.3 6 11 6 12a2 2 0 004 0c0-1 .5-1.7 1-2.5 1.5-2.5 0-5-3-8z"/></svg></span>
      <span class="snav-lbl">Warm Up</span>
    </a>
    <a href="/massdm" class="snav-btn">
      <span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="1" y="3" width="14" height="10" rx="2"/><polyline points="1,4 8,9.5 15,4"/></svg></span>
      <span class="snav-lbl">Mass DM</span>
    </a>
    <a href="/scraper" class="snav-btn">
      <span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="7" cy="7" r="5"/><line x1="11" y1="11" x2="15" y2="15"/></svg></span>
      <span class="snav-lbl">Scraper</span>
    </a>
    <a href="/setup" class="snav-btn">
      <span class="snav-ico"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="8" cy="8" r="2.5"/><path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3.2 3.2l1.1 1.1M11.7 11.7l1.1 1.1M3.2 12.8l1.1-1.1M11.7 4.3l1.1-1.1"/></svg></span>
      <span class="snav-lbl">Setup</span>
    </a>
  </nav>
  <button class="side-toggle" id="side-toggle" onclick="togglePanel()">&#9776;</button>
</div>

<!-- ═══ MAIN ═══ -->
<div class="ov-main">

  <!-- ═══ TOP NAV ROW ═══ -->
  <div class="ov-topnav">
    <div class="ov-tabs">
      <button class="ov-tab active">Overview</button>
      <button class="ov-tab" onclick="location.href='/warmup'">Warmup</button>
    </div>
    <div class="ov-topnav-right">
      <div class="plat-filters">
        <button class="plat-btn active">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.6 0 12 0zm5.9 8.2-2 9.3c-.1.7-.6.9-1.1.6l-3-2.2-1.4 1.4c-.2.2-.3.3-.6.3l.2-3.1 5.6-5c.2-.2-.1-.4-.4-.1L8.8 14.1l-3-1c-.7-.2-.7-.7.1-1l11.6-4.5c.5-.2 1 .1.9.9-.1-.4-.6 0-.5-.3z"/></svg>
          Telegram
        </button>
        <button class="plat-btn plat-ico-only">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="8" cy="5.5" r="3"/><path d="M2 14c0-3 2.7-5 6-5s6 2 6 5"/></svg>
        </button>
      </div>
      <button class="all-crt-btn">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="8" cy="5.5" r="3"/><path d="M2 14c0-3 2.7-5 6-5s6 2 6 5"/></svg>
        All creators &#9662;
      </button>
      <div class="dp-wrap" id="dp-wrap">
        <button class="dp-trigger" onclick="toggleDp(event)">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="1" y="2" width="14" height="13" rx="2"/><line x1="1" y1="6" x2="15" y2="6"/><line x1="5" y1="1" x2="5" y2="4"/><line x1="11" y1="1" x2="11" y2="4"/></svg>
          <span id="dp-label">Last 7 Days</span> &#9662;
        </button>
        <div class="dp-popup" id="dp-popup">
          <div class="dp-presets">
            <button class="dp-pre" id="pre-today"     onclick="setPreset('today')">Today</button>
            <button class="dp-pre active" id="pre-last7" onclick="setPreset('last7')">Last 7 Days</button>
            <button class="dp-pre" id="pre-thisWeek"  onclick="setPreset('thisWeek')">This Week</button>
            <button class="dp-pre" id="pre-lastWeek"  onclick="setPreset('lastWeek')">Last Week</button>
            <button class="dp-pre" id="pre-thisMonth" onclick="setPreset('thisMonth')">This Month</button>
            <button class="dp-pre" id="pre-lastMonth" onclick="setPreset('lastMonth')">Last Month</button>
            <button class="dp-pre" id="pre-thisYear"  onclick="setPreset('thisYear')">This Year</button>
            <button class="dp-pre" id="pre-lastYear"  onclick="setPreset('lastYear')">Last Year</button>
          </div>
          <div class="dp-cals">
            <div class="dp-cals-nav">
              <button class="dp-nav" onclick="navCal(-1)">&#8249;</button>
              <button class="dp-nav" onclick="navCal(1)">&#8250;</button>
            </div>
            <div class="dp-months">
              <div class="dp-month" id="dp-cal1"></div>
              <div class="dp-month" id="dp-cal2"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ TITRE ═══ -->
  <div class="ov-header">
    <div>
      <div class="ov-title">Dashboard</div>
      <div class="ov-subtitle">Monitor your Telegram performance and key metrics</div>
    </div>
  </div><!-- /.ov-header -->

  <!-- Stats cards -->
  <div class="ov-cards">

    <!-- UNLOCK RATE — spans 2 rows -->
    <div class="ov-card card-unlock" style="grid-row:1/3">
      <div class="ctag">UNLOCK RATE <span class="ctag-ico">&#10022;</span></div>
      <div class="unlock-box">
        <svg class="ring-svg" width="190" height="190" viewBox="0 0 190 190">
          <circle class="ring-track" cx="95" cy="95" r="{ring_r}"/>
          <circle class="ring-fill" id="ring-fill" cx="95" cy="95" r="{ring_r}"
            stroke-dasharray="{ring_c}" stroke-dashoffset="{ring_off}"/>
          <text class="ring-pct" id="ring-pct" x="95" y="95">{unlock_rate}%</text>
        </svg>
        <div class="unlock-sub">unlock percentage</div>
      </div>
    </div>

    <!-- WARM UP -->
    <div class="ov-card">
      <div class="ctag">WARM UP <span class="ctag-ico">&#10022;</span></div>
      <div class="cval" id="stat-warmup">{warmup_count}</div>
      <div class="cdesc">comptes en chauffe active</div>
      <div class="cdesc" style="margin-top:4px;color:#555">sur {n_profiles} profil(s)</div>
    </div>

    <!-- DM -->
    <div class="ov-card" style="grid-column:3/5">
      <div class="ctag">DM <span class="ctag-ico">&#8599;</span></div>
      <div class="cval" id="stat-dm-val">{dm_available}<span style="font-size:1rem;color:#444;font-weight:600">/{n_profiles}</span></div>
      <div class="cdesc">comptes disponibles Mass DM</div>
      <div class="prog-row">
        <div class="prog-bg"><div class="prog-fg" id="prog-dm" style="width:{dm_pct}%"></div></div>
        <span class="prog-pct" id="prog-pct">{dm_pct}%</span>
      </div>
    </div>

    <!-- NEW CONVERSATIONS -->
    <div class="ov-card">
      <div class="ctag">NEW CONVERSATIONS <span class="ctag-ico">&#9656;</span></div>
      <div class="cval" id="stat-dms">{total_dms}</div>
      <div class="cdesc">DMs envoy&eacute;s sur la p&eacute;riode</div>
      <div class="mini-bars" id="mini-bars">{mini_bars_html}</div>
    </div>

    <!-- RÉSULTAT -->
    <div class="ov-card">
      <div class="ctag">R&Eacute;SULTAT <span class="ctag-ico">&#8857;</span></div>
      <div class="cval" id="stat-resultat">{total_resp}</div>
      <div class="cdesc">r&eacute;ponses re&ccedil;ues</div>
      <div class="mini-bars">
        <div class="mbar" style="height:30%"></div>
        <div class="mbar" style="height:20%"></div>
        <div class="mbar hi" style="height:80%"></div>
        <div class="mbar" style="height:55%"></div>
        <div class="mbar" style="height:40%"></div>
        <div class="mbar hi" style="height:70%"></div>
        <div class="mbar" style="height:50%"></div>
      </div>
    </div>

    <!-- BIENTÔT -->
    <div class="ov-card">
      <div class="ctag">BIENT&Ocirc;T DISPONIBLE <span class="ctag-ico">&#9200;</span></div>
      <div class="redacted-bars">
        <div class="redact-row"><div class="redact-dot"></div><div class="redact-bar" style="width:70%"></div></div>
        <div class="redact-row"><div class="redact-dot"></div><div class="redact-bar" style="width:50%"></div></div>
        <div class="redact-row"><div class="redact-dot"></div><div class="redact-bar" style="width:85%"></div></div>
        <div class="redact-row"><div class="redact-dot"></div><div class="redact-bar" style="width:40%"></div></div>
      </div>
    </div>

  </div><!-- /.ov-cards -->

  <!-- Bottom row -->
  <div class="ov-bottom">
    <div class="ov-chart-card">
      <div class="sec-hdr">
        <div class="sec-bar"></div>
        <span class="sec-title">STATISTIQUE</span>
        <span class="sec-sub" id="chart-lbl">Daily &middot; Weekly &middot; Monthly</span>
      </div>
      <svg class="bar-chart-svg" id="bar-chart" viewBox="0 0 700 240" preserveAspectRatio="none">
        <text x="350" y="100" text-anchor="middle" fill="#2a2a2a" font-size="14">Chargement...</text>
      </svg>
    </div>
    <div class="ov-hist-card">
      <div class="sec-hdr">
        <div class="sec-bar"></div>
        <span class="sec-title">HISTORY</span>
        <span class="sec-sub">{len(hist_events)} latest</span>
      </div>
      <div class="hist-list">{hist_rows_html}</div>
    </div>
  </div>

</div><!-- /.ov-main -->
</div><!-- /.ov-layout -->

<!-- BAR TOOLTIP -->
<div class="bar-tip" id="bar-tip">
  <div class="bar-tip-dm" id="bar-tip-dm"></div>
  <div class="bar-tip-jour" id="bar-tip-jour"></div>
</div>

<script>
// ── Panel ──
const _panel=document.getElementById('side-panel');
const _stog=document.getElementById('side-toggle');
let _pOpen=true;
function togglePanel(){{
  _pOpen=!_pOpen;
  _panel.classList.toggle('collapsed',!_pOpen);
  _stog.innerHTML=_pOpen?'&#9776;':'&#9654;';
}}

// ── Date picker ──
let gStart=null,gEnd=null,_activeP='last7';
let _calY,_calM;
(function _initDp(){{
  const n=new Date();n.setHours(0,0,0,0);
  gEnd=new Date(n);gStart=new Date(n);gStart.setDate(gStart.getDate()-6);
  _calY=n.getFullYear();_calM=n.getMonth();
  _renderCals();
}})();

function _dOff(n){{const x=new Date();x.setHours(0,0,0,0);x.setDate(x.getDate()+n);return x;}}
function _fmt(d){{const y=d.getFullYear(),mo=String(d.getMonth()+1).padStart(2,'0'),dd=String(d.getDate()).padStart(2,'0');return y+'-'+mo+'-'+dd;}}
function _fmtD(d){{return d.toLocaleDateString('en-US',{{month:'short',day:'numeric',year:'numeric'}});}}

function _getPS(){{
  const n=new Date();n.setHours(0,0,0,0);
  const dow=n.getDay(),mo=dow===0?-6:1-dow;
  return {{
    today:    {{lbl:'Today',        s:new Date(n),e:new Date(n)}},
    last7:    {{lbl:'Last 7 Days',  s:_dOff(-6),  e:new Date(n)}},
    thisWeek: {{lbl:'This Week',    s:_dOff(mo),  e:new Date(n)}},
    lastWeek: {{lbl:'Last Week',
      s:(()=>{{const x=new Date(n);x.setDate(x.getDate()+mo-7);return x;}})(),
      e:(()=>{{const x=new Date(n);x.setDate(x.getDate()+mo-1);return x;}})()}},
    thisMonth:{{lbl:'This Month',   s:new Date(n.getFullYear(),n.getMonth(),1),e:new Date(n)}},
    lastMonth:{{lbl:'Last Month',
      s:new Date(n.getFullYear(),n.getMonth()-1,1),
      e:new Date(n.getFullYear(),n.getMonth(),0)}},
    thisYear: {{lbl:'This Year',    s:new Date(n.getFullYear(),0,1),e:new Date(n)}},
    lastYear: {{lbl:'Last Year',
      s:new Date(n.getFullYear()-1,0,1),
      e:new Date(n.getFullYear()-1,11,31)}},
  }};
}}

function setPreset(id){{
  const ps=_getPS();if(!ps[id])return;
  _activeP=id;gStart=ps[id].s;gEnd=ps[id].e;
  document.getElementById('dp-label').textContent=ps[id].lbl;
  document.querySelectorAll('.dp-pre').forEach(b=>b.classList.remove('active'));
  const el=document.getElementById('pre-'+id);if(el)el.classList.add('active');
  _closeDp();refreshAll();
}}

let _pStage=0;
function pickDate(y,m,day){{
  const dt=new Date(y,m,day);dt.setHours(0,0,0,0);
  if(_pStage===0||gEnd){{gStart=dt;gEnd=null;_pStage=1;}}
  else{{
    if(dt<gStart){{gEnd=gStart;gStart=dt;}}else{{gEnd=dt;}}
    _pStage=0;_activeP=null;
    document.querySelectorAll('.dp-pre').forEach(b=>b.classList.remove('active'));
    document.getElementById('dp-label').textContent=_fmtD(gStart)+' - '+_fmtD(gEnd);
    _closeDp();refreshAll();
  }}
  _renderCals();
}}

const _MN=['January','February','March','April','May','June','July','August','September','October','November','December'];
const _DN=['Su','Mo','Tu','We','Th','Fr','Sa'];

function _renderMonth(elId,yr,mo){{
  const el=document.getElementById(elId);
  let h=`<div class="dp-month-title">${{_MN[mo]}} ${{yr}}</div><div class="dp-cal-grid">`;
  _DN.forEach(d=>h+=`<div class="dp-day hd">${{d}}</div>`);
  const fd=new Date(yr,mo,1).getDay();
  const dim=new Date(yr,mo+1,0).getDate();
  const pd=new Date(yr,mo,0).getDate();
  for(let i=fd-1;i>=0;i--)h+=`<div class="dp-day other">${{pd-i}}</div>`;
  for(let day=1;day<=dim;day++){{
    const dt=new Date(yr,mo,day);dt.setHours(0,0,0,0);
    const ts=dt.getTime();
    let cls='dp-day click';
    if(gStart&&ts===gStart.getTime())cls+=' start';
    else if(gEnd&&ts===gEnd.getTime())cls+=' end';
    else if(gStart&&gEnd&&dt>gStart&&dt<gEnd)cls+=' inrange';
    h+=`<div class="${{cls}}" onclick="pickDate(${{yr}},${{mo}},${{day}})">${{day}}</div>`;
  }}
  h+='</div>';
  el.innerHTML=h;
}}

function _renderCals(){{
  _renderMonth('dp-cal1',_calY,_calM);
  let m2=_calM+1,y2=_calY;
  if(m2>11){{m2=0;y2++;}}
  _renderMonth('dp-cal2',y2,m2);
}}
function navCal(dir){{
  _calM+=dir;
  if(_calM<0){{_calM=11;_calY--;}}else if(_calM>11){{_calM=0;_calY++;}}
  _renderCals();
}}
function toggleDp(e){{
  e.stopPropagation();
  const pop=document.getElementById('dp-popup');
  const isOpen=pop.classList.contains('open');
  if(isOpen){{pop.classList.remove('open');return;}}
  const r=document.getElementById('dp-wrap').getBoundingClientRect();
  pop.style.top=(r.bottom+8)+'px';
  pop.style.right=(window.innerWidth-r.right)+'px';
  pop.style.left='auto';
  pop.classList.add('open');
}}
function _closeDp(){{document.getElementById('dp-popup').classList.remove('open');}}
document.addEventListener('click',e=>{{if(!document.getElementById('dp-wrap').contains(e.target))_closeDp();}});

// ── Stats ──
const _RING_C={ring_c};
async function loadStats(){{
  try{{
    const r=await fetch('/api/overview/stats?start='+_fmt(gStart)+'&end='+_fmt(gEnd));
    if(!r.ok)return;
    const d=await r.json();
    document.getElementById('stat-dms').textContent=d.total_dms??0;
    document.getElementById('stat-warmup').textContent=d.warmup_count??0;
    document.getElementById('stat-resultat').textContent=d.resultat??0;
    const rate=d.unlock_rate??0;
    document.getElementById('ring-pct').textContent=rate+'%';
    document.getElementById('ring-fill').setAttribute('stroke-dashoffset',(_RING_C*(1-Math.min(rate,100)/100)).toFixed(2));
    const av=d.dm_available??0,tot={n_profiles};
    document.getElementById('stat-dm-val').innerHTML=av+'<span style="font-size:1rem;color:#444;font-weight:600">/'+tot+'</span>';
    const pct=Math.min(Math.round(av/Math.max(tot,1)*100),100);
    document.getElementById('prog-dm').style.width=pct+'%';
    document.getElementById('prog-pct').textContent=pct+'%';
  }}catch(e){{console.error(e);}}
}}

// ── Chart ──
function renderChart(labels,values){{
  const svg=document.getElementById('bar-chart');
  if(!labels||!labels.length){{svg.innerHTML='<text x="350" y="100" text-anchor="middle" fill="#2a2a2a" font-size="13">Aucune donnée</text>';return;}}
  const W=700,H=240,pL=42,pR=8,pT=16,pB=26,cW=W-pL-pR,cH=H-pT-pB;
  const maxV=Math.max(...values,1),n=labels.length,slot=cW/n,bW=Math.min(20,Math.max(5,Math.floor(slot*.15)));
  const _TD=new Date();
  const today=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][_TD.getMonth()]+' '+_TD.getDate();
  // SVG gradient + filter defs
  let out=`<defs>
    <linearGradient id="barGrad" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="#7f1d1d" stop-opacity="0.8"/>
      <stop offset="100%" stop-color="#dc2626" stop-opacity="1"/>
    </linearGradient>
    <linearGradient id="barGradHi" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="#991b1b" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#ff4444" stop-opacity="1"/>
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>`;
  // Y-axis scale labels (left side): max, half, 0
  const halfV=Math.round(maxV/2);
  out+=`<text x="${{pL-6}}" y="${{(pT+6).toFixed(1)}}" text-anchor="end" font-size="9" fill="#555" font-family="sans-serif">${{maxV}}</text>`;
  out+=`<text x="${{pL-6}}" y="${{(pT+cH/2+3).toFixed(1)}}" text-anchor="end" font-size="9" fill="#555" font-family="sans-serif">${{halfV}}</text>`;
  out+=`<text x="${{pL-6}}" y="${{(pT+cH+1).toFixed(1)}}" text-anchor="end" font-size="9" fill="#555" font-family="sans-serif">0</text>`;
  // subtle grid
  for(let i=1;i<=4;i++){{
    const y=pT+cH-(i/4)*cH;
    out+=`<line x1="${{pL}}" y1="${{y.toFixed(1)}}" x2="${{W-pR}}" y2="${{y.toFixed(1)}}" stroke="#1a1a1a" stroke-width="1"/>`;
  }}
  labels.forEach((lbl,i)=>{{
    const cx=pL+slot*i+slot/2,v=values[i]||0;
    const bH=v>0?Math.max(8,(v/maxV)*cH):4,bY=pT+cH-bH;
    const isT=(lbl===today);
    const grad=isT?'url(#barGradHi)':'url(#barGrad)';
    const flt=isT?'filter="url(#glow)"':'';
    out+=`<rect x="${{(cx-bW/2).toFixed(1)}}" y="${{bY.toFixed(1)}}" width="${{bW}}" height="${{bH.toFixed(1)}}" rx="4" fill="${{grad}}" ${{flt}}/>`;
    out+=`<text x="${{cx.toFixed(1)}}" y="${{(H-3).toFixed(1)}}" text-anchor="middle" font-size="10" fill="${{isT?'#dc2626':'#444'}}" font-family="sans-serif">${{lbl}}</text>`;
    /* Zone de survol invisible sur toute la hauteur de la colonne */
    out+=`<rect class="bar-hit" x="${{(cx-slot/2).toFixed(1)}}" y="${{pT}}" width="${{slot.toFixed(1)}}" height="${{(cH+8).toFixed(1)}}" fill="transparent" style="cursor:crosshair"
      onmouseenter="showBarTip(event,'${{lbl}}',${{v}},${{cx.toFixed(1)}},${{bW}})" onmouseleave="hideBarTip()"/>`;
  }});
  svg.innerHTML=out;
}}

async function loadChart(){{
  try{{
    const r=await fetch('/api/overview/chart?start='+_fmt(gStart)+'&end='+_fmt(gEnd));
    if(!r.ok)return;
    const d=await r.json();
    renderChart(d.labels,d.values);
    document.getElementById('chart-lbl').textContent='DMs envoyés — '+_fmtD(gStart)+' → '+_fmtD(gEnd);
  }}catch(e){{console.error(e);}}
}}

function refreshAll(){{loadStats();loadChart();}}

// ── Tooltip graphique — position fixe à droite de la barre ──
function showBarTip(e,lbl,val,svgCx,svgBw){{
  const tip=document.getElementById('bar-tip');
  const _mn=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const _dn=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const parts=lbl.split(' ');
  const mi=_mn.indexOf(parts[0]);
  let fullLbl=lbl;
  if(mi>=0&&parts[1]){{
    const now=new Date();
    const d=new Date(now.getFullYear(),mi,parseInt(parts[1]));
    fullLbl=_dn[d.getDay()]+', '+lbl;
  }}
  document.getElementById('bar-tip-jour').textContent=fullLbl;
  document.getElementById('bar-tip-dm').textContent=val+' DMs';
  tip.style.display='block';
  /* Positionne à droite de la barre, centré verticalement sur le graphique */
  const svg=document.getElementById('bar-chart');
  const sr=svg.getBoundingClientRect();
  const scale=sr.width/700;
  const barRightX=sr.left+(parseFloat(svgCx)+parseFloat(svgBw)/2+4)*scale;
  const midY=sr.top+sr.height*0.42;
  const tipW=tip.offsetWidth,tipH=tip.offsetHeight;
  let left=barRightX+10;
  let top=midY-tipH/2;
  /* Si déborde à droite → placer à gauche de la barre */
  if(left+tipW>window.innerWidth-10){{
    left=sr.left+(parseFloat(svgCx)-parseFloat(svgBw)/2-4)*scale-tipW-10;
  }}
  if(top<8)top=8;
  if(top+tipH>window.innerHeight-8)top=window.innerHeight-tipH-8;
  tip.style.left=left+'px';
  tip.style.top=top+'px';
}}
function hideBarTip(){{
  document.getElementById('bar-tip').style.display='none';
}}

const _IL={chart_labels_json},_IV={chart_values_json};
renderChart(_IL,_IV);
refreshAll();
setInterval(refreshAll,60000);
</script>
</body></html>"""
    return html


# ═══════════════════════════════════════════════════════════
#  PAGE MASS DM
# ═══════════════════════════════════════════════════════════

@app.get("/massdm", response_class=HTMLResponse)
def dashboard_massdm():
    from collections import defaultdict

    data        = load_massdm()
    profile_ids = get_all_ids()
    profiles    = [data.get(pid, _default_massdm(pid)) for pid in profile_ids]
    n           = len(profiles)
    total_sent    = sum(p["dms_sent"]    for p in profiles)
    total_replied = sum(p["dms_replied"] for p in profiles)
    total_conv    = sum(p["conversions"] for p in profiles)
    taux_rep      = round(total_replied / total_sent * 100, 1) if total_sent > 0 else 0
    actifs        = sum(1 for p in profiles if p["status"] == "Actif")

    # ── Paramètres Mass DM (filtre genre) ─────────────────────
    genre_filter = get_setting("massdm_genre_filter", "tous")

    # ── Templates A/B ─────────────────────────────────────────
    templates = load_dm_templates()
    COLORS = ['#22c55e','#3b82f6','#a855f7','#f59e0b','#ef4444',
              '#06b6d4','#ec4899','#84cc16','#f97316','#8b5cf6','#14b8a6','#e11d48']

    tpl_active_count = sum(1 for t in templates if t.get("active", True))
    tpl_total_sends  = sum(t.get("sends", 0) for t in templates)

    # Calcule le meilleur template (taux de réponse max)
    def _rate(t):
        s = t.get("sends", 0)
        return t.get("replies", 0) / s if s > 0 else 0

    best_id = None
    if templates:
        best = max(templates, key=_rate)
        if _rate(best) > 0:
            best_id = best["id"]

    # JSON injecté dans la page — évite les problèmes d'échappement dans les onclick
    tpl_data_js = {}
    for t in templates:
        tpl_data_js[t["id"]] = {
            "name":     t.get("name", "") or "",
            "content":  t.get("content", "") or "",
            "content2": t.get("content2", "") or "",
            "content3": t.get("content3", "") or "",
            "content4": t.get("content4", "") or "",
            "content5": t.get("content5", "") or "",
        }
    tpl_json = json.dumps(tpl_data_js, ensure_ascii=False)

    # Cards
    tpl_cards_html = ""
    for idx, t in enumerate(templates):
        tid      = t["id"]
        sends    = t.get("sends",    0)
        replies  = t.get("replies",  0)
        active   = t.get("active",   True)
        # Collecte tous les messages non-vides
        all_contents = [t["content"]]
        for _ck in ["content2", "content3", "content4", "content5"]:
            _cv = (t.get(_ck) or "").strip()
            if _cv:
                all_contents.append(_cv)
        msg_count = len(all_contents)

        rate     = round(replies / sends * 100, 1) if sends > 0 else 0

        preview = all_contents[0][:110].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        if len(all_contents[0]) > 110:
            preview += "…"

        color    = COLORS[idx % len(COLORS)]
        card_cls = "tpl-card" + ("" if active else " inactive")
        tog_lbl  = "● Actif"  if active else "○ Inactif"
        tog_cls  = "btn-tpl btn-tpl-on" if active else "btn-tpl btn-tpl-off"
        name_esc = t["name"].replace("&","&amp;").replace("<","&lt;")
        best_badge = '<span class="winner-badge">🏆 Meilleur</span>' if tid == best_id else ""
        msg_count_badge = f'<span class="msg2-badge">✉×{msg_count}</span>' if msg_count > 1 else ""

        # Aperçus des messages 2→5
        extra_previews_html = ""
        for _ei, _ec in enumerate(all_contents[1:], 2):
            _ep = _ec[:90].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            if len(_ec) > 90:
                _ep += "…"
            extra_previews_html += f'<pre class="tpl-preview tpl-preview2"><span style="color:#475569;font-size:.65rem;font-weight:700;">MSG {_ei}</span> {_ep}</pre>'

        tpl_cards_html += f"""
<div class="{card_cls}">
  <div class="tpl-name">
    <span class="tpl-num" style="background:{color}22;color:{color};border:1px solid {color}55;">T{idx+1}</span>
    {name_esc}{best_badge}{msg_count_badge}
  </div>
  <pre class="tpl-preview"><span style="color:#475569;font-size:.65rem;font-weight:700;">MSG 1</span> {preview}</pre>
  {extra_previews_html}
  <div class="tpl-stats">
    <div class="tstat"><div class="tstat-val blue">{sends}</div><div class="tstat-lab">Envoyés</div></div>
    <div class="tstat"><div class="tstat-val green">{replies}</div><div class="tstat-lab">Réponses</div></div>
    <div class="tstat"><div class="tstat-val gold">{rate}%</div><div class="tstat-lab">Taux</div></div>
  </div>
  <div class="tpl-actions">
    <button class="{tog_cls}" onclick="toggleTpl({tid},{str(not active).lower()})">{tog_lbl}</button>
    <button class="btn-tpl" style="background:#1e3a5f;color:#93c5fd;flex:1;" onclick="openEditTplModal({tid})">✏ Modifier</button>
    <button class="btn-tpl btn-tpl-del" onclick="delTpl({tid})">✕</button>
  </div>
</div>"""

    if not tpl_cards_html:
        tpl_cards_html = '<p style="color:#475569;text-align:center;padding:30px 0;grid-column:1/-1;">Aucun template — ajoute ton premier message A/B ci-dessus.</p>'

    # ── Analyse comparative A/B ───────────────────────────────
    chart_tpls = [(idx, t) for idx, t in enumerate(templates) if t.get("sends", 0) > 0]
    if chart_tpls:
        # Sorted by reply rate (best first) for the ranking table
        srt = sorted(chart_tpls, key=lambda x: _rate(x[1]), reverse=True)
        medals = ["🥇","🥈","🥉"] + [f"#{i}" for i in range(4, 50)]

        ab_rows = ""
        for rank, (idx, t) in enumerate(srt):
            r2  = round(_rate(t) * 100, 1)
            bw  = min(r2, 100)
            co  = COLORS[idx % len(COLORS)]
            wb  = '<span class="winner-badge">Top ✓</span>' if rank == 0 and t["replies"] > 0 else ""
            nm  = t["name"].replace("&","&amp;").replace("<","&lt;")
            ab_rows += f"""<tr>
              <td class="center" style="font-weight:800;font-size:.95rem;">{medals[rank]}</td>
              <td><span style="font-size:.7rem;font-weight:800;color:{co};margin-right:6px;">T{idx+1}</span>
                  <span style="font-size:.82rem;color:#e2e8f0;">{nm}</span>{wb}</td>
              <td class="center" style="color:#93c5fd;font-weight:700;">{t["sends"]}</td>
              <td class="center" style="color:#22c55e;font-weight:700;">{t["replies"]}</td>
              <td><div class="rate-bar-wrap">
                <div class="rate-bar-bg"><div class="rate-bar-fg" style="width:{bw}%;background:{co};"></div></div>
                <span class="rate-pct" style="color:{co};">{r2}%</span>
              </div></td>
            </tr>"""

        _cl  = "[" + ",".join(f'"T{idx+1} — {t["name"][:16].replace(chr(34),chr(39))}"' for idx, t in chart_tpls) + "]"
        _cr  = "[" + ",".join(str(round(_rate(t)*100,1)) for _, t in chart_tpls) + "]"
        _cbg = "[" + ",".join(f'"{COLORS[idx%len(COLORS)]}2e"' for idx,_ in chart_tpls) + "]"
        _cbd = "[" + ",".join(f'"{COLORS[idx%len(COLORS)]}"'   for idx,_ in chart_tpls) + "]"
        _cs  = "[" + ",".join(str(t["sends"])   for _, t in chart_tpls) + "]"
        _crp = "[" + ",".join(str(t["replies"]) for _, t in chart_tpls) + "]"
        ch_h = max(160, 55 * len(chart_tpls))

        ab_section = f"""
<div class="card chart-card" style="margin-bottom:16px;">
  <div class="chart-header">
    <div>
      <p class="chart-title">Analyse comparative A/B</p>
      <p class="chart-sub">Taux de réponse par template · tous profils confondus</p>
    </div>
  </div>
  <canvas id="abChart" height="{ch_h}" style="max-height:420px;"></canvas>
</div>
<div class="card" style="margin-bottom:24px;">
  <p style="padding:14px 20px 12px;font-size:.65rem;font-weight:800;color:#3b5278;
     text-transform:uppercase;letter-spacing:.14em;border-bottom:2px solid #1e3a5f;">
    Classement des templates
  </p>
  <table class="ab-table"><thead><tr>
    <th style="width:52px;">Rang</th>
    <th class="th-l">Template</th>
    <th>Envoyés</th>
    <th>Réponses</th>
    <th style="min-width:200px;">Taux de réponse</th>
  </tr></thead><tbody>{ab_rows}</tbody></table>
</div>
<script>
(function(){{
  const ctx = document.getElementById('abChart');
  if (!ctx) return;
  new Chart(ctx, {{
    type: 'bar', indexAxis: 'y',
    data: {{
      labels: {_cl},
      datasets: [{{
        label: 'Taux de réponse (%)',
        data: {_cr},
        backgroundColor: {_cbg},
        borderColor: {_cbd},
        borderWidth: 2.5,
        borderRadius: 8,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1e293b', borderColor: '#334155', borderWidth: 1,
          titleColor: '#94a3b8', bodyColor: '#f8fafc', padding: 12, cornerRadius: 10,
          callbacks: {{
            label: (c) => {{
              const i = c.dataIndex;
              return [' Taux : ' + c.raw + '%',
                      ' Envoyés : ' + {_cs}[i],
                      ' Réponses : ' + {_crp}[i]];
            }}
          }}
        }}
      }},
      scales: {{
        x: {{ grid: {{ color: '#1a2639' }},
              ticks: {{ color: '#475569', font: {{ size: 11 }} }},
              beginAtZero: true, max: 100 }},
        y: {{ grid: {{ color: '#1a2639', drawBorder: false }},
              ticks: {{ color: '#94a3b8', font: {{ size: 11, weight: '600' }} }} }}
      }}
    }}
  }});
}})();
</script>"""
    else:
        ab_section = '<div class="card chart-empty" style="margin-bottom:24px;">Lance dm_sender.py pour voir l\'analyse A/B — les données apparaîtront ici automatiquement.</div>'

    # ── Graphique DMs par jour ────────────────────────────────
    _daily = defaultdict(int)
    for p in profiles:
        for entry in p.get("history", []):
            d = (entry.get("date") or "")[:10]
            if len(d) == 10:
                _daily[d] += entry.get("sent", 0)

    def _dk(d):
        try:    return datetime.strptime(d, "%d/%m/%Y")
        except: return datetime.min

    _days    = sorted(_daily.keys(), key=_dk)[-14:]
    _dl      = "[" + ",".join(f'"{x}"' for x in _days) + "]"
    _dd      = "[" + ",".join(str(_daily[x]) for x in _days) + "]"
    _maxv    = max((_daily[x] for x in _days), default=0)

    if _days:
        daily_chart = f"""
<div class="card chart-card">
  <div class="chart-header">
    <div>
      <p class="chart-title">DMs envoyés par jour</p>
      <p class="chart-sub">Cumul de tous les profils &middot; 14 derniers jours</p>
    </div>
    <span class="chart-legend">Tous profils</span>
  </div>
  <canvas id="dmChart" height="90"></canvas>
</div>
<script>
(function(){{
  const ctx = document.getElementById('dmChart');
  if (!ctx) return;
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: {_dl},
      datasets: [{{
        data: {_dd},
        borderColor: '#22c55e',
        backgroundColor: (c) => {{
          const g = c.chart.ctx.createLinearGradient(0,0,0,c.chart.height);
          g.addColorStop(0,'rgba(34,197,94,.18)'); g.addColorStop(1,'rgba(34,197,94,.01)');
          return g;
        }},
        borderWidth:2.5, tension:0.4, fill:true,
        pointBackgroundColor:'#22c55e', pointBorderColor:'#0f172a',
        pointBorderWidth:2, pointRadius:5, pointHoverRadius:9,
      }}]
    }},
    options: {{
      responsive: true,
      interaction: {{ mode:'index', intersect:false }},
      plugins: {{
        legend: {{ display:false }},
        tooltip: {{
          backgroundColor:'#1e293b', borderColor:'#22c55e', borderWidth:1,
          titleColor:'#94a3b8', bodyColor:'#f8fafc', padding:12, cornerRadius:10,
          callbacks: {{ label: c => '  ' + c.raw + ' DMs envoyés' }}
        }}
      }},
      scales: {{
        x: {{ grid:{{ color:'#1a2639',drawBorder:false }},
              ticks:{{ color:'#475569',font:{{ size:11 }} }} }},
        y: {{ grid:{{ color:'#1a2639',drawBorder:false }},
              ticks:{{ color:'#475569',font:{{ size:11 }},stepSize:Math.max(1,Math.ceil({_maxv}/6)) }},
              beginAtZero:true, suggestedMax:{_maxv}+2 }}
      }}
    }}
  }});
}})();
</script>"""
    else:
        daily_chart = '<div class="card chart-empty">Aucune donnée — lance dm_sender.py pour voir les statistiques ici.</div>'

    # ── Charge les bios + modes ───────────────────────────────
    setup_map  = {s["profile_id"]: s for s in load_profile_setup()}
    warmup_data = load_data()  # contient dm_mode pour chaque profil

    # Recompte les actifs en mode direct_dm uniquement
    massdm_pids   = [pid for pid in profile_ids
                     if warmup_data.get(pid, {}).get("dm_mode") == "direct_dm"]
    massdm_actifs = sum(1 for pid in massdm_pids
                        if data.get(pid, _default_massdm(pid))["status"] == "Actif")

    # ── Table profils ─────────────────────────────────────────
    rows = ""
    for i, pid in enumerate(profile_ids, 1):
        p       = data.get(pid, _default_massdm(pid))
        wp      = warmup_data.get(pid, {})
        dm_mode = wp.get("dm_mode", "warmup")
        dm_day  = wp.get("dm_day", 0)

        sent    = p["dms_sent"]
        replied = p["dms_replied"]
        taux    = round(replied / sent * 100, 1) if sent > 0 else 0
        pct_bar = min(int(taux), 100)

        if p["status"] == "Actif":     sb = '<span class="badge active">Actif</span>'
        elif p["status"] == "Termine": sb = '<span class="badge done">Terminé ✓</span>'
        else:                          sb = '<span class="badge waiting">En attente</span>'

        bio_saved  = (setup_map.get(pid, {}).get("bio") or "").replace('"', "&quot;").replace("'", "&#39;")
        bio_label  = "✏ Bio" if not bio_saved else "✏ Bio ✓"
        bio_color  = "#22c55e" if bio_saved else "#1e40af"

        if dm_mode == "direct_dm":
            mode_badge = f'<button class="btn-ddm btn-ddm-active" onclick="toggleModeMassDm(\'{pid}\',\'warmup\')" title="Repasser en Warm-Up">⚡ Mass DM<br><small style="font-size:.58rem">J{dm_day}</small></button>'
            row_style  = ""
        else:
            mode_badge = f'<button class="btn-ddm btn-ddm-warmup" onclick="toggleModeMassDm(\'{pid}\',\'direct_dm\')" title="Passer en Mass DM">WU→DM</button>'
            row_style  = 'style="opacity:.45"'  # profil en warm-up : grisé

        if dm_mode == "direct_dm":
            launch_btn = f'<button class="btn-launch-profile" onclick="launchProfileDm(\'{pid}\')" title="Lancer Mass DM pour ce profil">▶ Lancer</button>'
        else:
            launch_btn = '<span style="color:#334155;font-size:.7rem">—</span>'

        rows += f"""<tr {row_style}>
          <td class="num">{i}</td><td class="pid">{pid}</td>
          <td class="center">{sent}</td><td class="center">{replied}</td>
          <td><div class="progress-wrap"><div class="progress-bar" style="width:{pct_bar}%;background:#22c55e"></div></div>
          <span class="day-label">{taux}% de réponse</span></td>
          <td class="center">{p['conversions']}</td><td>{sb}</td>
          <td class="center">{mode_badge}</td>
          <td class="center">{launch_btn}</td>
          <td class="last" style="white-space:nowrap;">
            {p['last_run'] or '—'}&nbsp;
            <button class="btn-bio" style="border-color:{bio_color};color:{bio_color};"
              onclick="openBioModal('{pid}','{bio_saved}')">{bio_label}</button>
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mass DM — A/B Testing</title><style>{BASE_CSS}{SIDEBAR_CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<meta http-equiv="refresh" content="60"></head><body>
<div class="ov-layout">{_sidebar_html('massdm')}<div class="page-main">
  <div class="neon-logo">
    <span class="neon-agency">Agency</span>
    <div class="neon-box"><span class="neon-text">OF4MYM</span></div>
  </div>
  <h1>Mass DM — A/B Testing</h1>
  <p class="subtitle">Analyse et suivi de tes messages DM · {n} profils actifs</p>
  {nav_html("massdm")}

  <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;margin-bottom:20px;">
    <button id="btn-launch-dm" onclick="launchMassDm()" style="background:linear-gradient(135deg,#3b82f6,#1d4ed8);color:#fff;border:none;border-radius:10px;padding:12px 28px;font-size:1rem;font-weight:700;cursor:pointer;box-shadow:0 0 18px rgba(59,130,246,.35);transition:all .2s">
      ⚡ Lancer le Mass DM maintenant
    </button>
    <span id="launch-dm-msg" style="display:none;color:#3b82f6;font-weight:600">✓ Signal envoyé — démarrage dans ~30s</span>
    <!-- Filtre genre -->
    <div style="background:#1e293b;border:1px solid #334155;border-radius:10px;padding:10px 16px;display:flex;align-items:center;gap:14px;">
      <span style="font-size:.72rem;font-weight:800;color:#3b5278;text-transform:uppercase;letter-spacing:.1em;">Cibler</span>
      <label style="display:flex;align-items:center;gap:5px;cursor:pointer;font-size:.82rem;color:#e2e8f0;">
        <input type="radio" name="genre" value="tous" {'checked' if genre_filter == 'tous' else ''} onchange="setGenreFilter(this.value)"> Tout le monde
      </label>
      <label style="display:flex;align-items:center;gap:5px;cursor:pointer;font-size:.82rem;color:#93c5fd;">
        <input type="radio" name="genre" value="garcon" {'checked' if genre_filter == 'garcon' else ''} onchange="setGenreFilter(this.value)"> ♂ Garçons uniquement
      </label>
      <label style="display:flex;align-items:center;gap:5px;cursor:pointer;font-size:.82rem;color:#f9a8d4;">
        <input type="radio" name="genre" value="fille" {'checked' if genre_filter == 'fille' else ''} onchange="setGenreFilter(this.value)"> ♀ Filles uniquement
      </label>
      <span id="genre-saved" style="display:none;font-size:.72rem;color:#22c55e;font-weight:700;">✓ Sauvegardé</span>
    </div>
  </div>

  <div class="stats">
    <div class="stat"><div class="stat-value">{len(massdm_pids)}<span style="color:#334155;font-size:1.2rem">/{n}</span></div><div class="stat-label">Profils Mass DM</div></div>
    <div class="stat"><div class="stat-value">{total_sent}</div><div class="stat-label">DMs envoyés</div></div>
    <div class="stat"><div class="stat-value">{total_replied}</div><div class="stat-label">Réponses</div></div>
    <div class="stat"><div class="stat-value">{taux_rep}<span style="font-size:1.2rem">%</span></div><div class="stat-label">Taux global</div></div>
    <div class="stat"><div class="stat-value">{tpl_active_count}<span style="color:#334155;font-size:1.2rem">/{len(templates)}</span></div><div class="stat-label">Templates actifs</div></div>
  </div>

  <!-- ══ TEMPLATES ══ -->
  <p class="section-title">Gestion des templates A/B</p>
  <div class="card" style="padding:20px 24px 22px;margin-bottom:16px;">
    <div class="add-box" style="border:none;padding:0;margin:0;flex-wrap:wrap;align-items:flex-start;">
      <div style="display:flex;flex-direction:column;flex:1;gap:8px;min-width:260px;">
        <input id="tname" type="text" placeholder="Nom du template  ex: Template A — Recrutement court">
        <textarea id="tcontent" class="add-textarea" placeholder="Message 1 (obligatoire)&#10;Utilise {{prenom}} pour personnaliser."></textarea>
        <div id="extra-msgs-container"></div>
        <button class="btn-add-msg2" onclick="addExtraMsg()" id="btnAddMsg">➕ Ajouter un message supplémentaire (max 5 — envoyé 5-18s après le précédent)</button>
      </div>
      <button onclick="addTpl()" style="align-self:flex-end;height:40px;white-space:nowrap;margin-top:0;">+ Ajouter</button>
    </div>
  </div>
  <div class="templates-grid">
    {tpl_cards_html}
  </div>

  <!-- ══ ANALYSE A/B ══ -->
  <p class="section-title">Analyse comparative des messages</p>
  {ab_section}

  <!-- ══ PROFILS ══ -->
  <p class="section-title">Statistiques par profil</p>
  <div class="card" style="margin-bottom:24px;"><table><thead><tr>
    <th class="th-l" style="width:36px">#</th>
    <th class="th-l">ID Profil</th>
    <th>DMs envoyés</th>
    <th>Réponses</th>
    <th style="min-width:160px">Taux réponse</th>
    <th>Conversions</th>
    <th>Statut</th>
    <th>Mode</th>
    <th>Action</th>
    <th>Dernière session</th>
  </tr></thead><tbody>{rows}</tbody></table></div>

  <!-- ══ ACTIVITÉ QUOTIDIENNE ══ -->
  <p class="section-title">Activité quotidienne</p>
  {daily_chart}

  <p class="refresh">Mis à jour automatiquement · rechargement dans 60s</p>

<!-- ── Modal Édition Template ── -->
<div class="modal-overlay" id="editTplModal">
  <div class="modal-box" style="max-width:620px;width:100%;max-height:90vh;overflow-y:auto;">
    <p class="modal-title">✏ Modifier — <span id="editTplModalName" style="color:#93c5fd;font-size:.85rem;"></span></p>
    <div style="display:flex;flex-direction:column;gap:10px;">
      <div>
        <label style="font-size:.68rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px;">Nom du template</label>
        <input id="etName" type="text" placeholder="Template A — Recrutement court"
          style="width:100%;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:9px 12px;color:#e2e8f0;font-size:.875rem;font-family:inherit;">
      </div>
      <div>
        <label style="font-size:.68rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px;">Message 1 <span style="color:#ef4444">*</span></label>
        <textarea id="etContent"  class="modal-textarea" style="min-height:90px;" placeholder="Message principal (obligatoire)&#10;Utilise {{prenom}} pour personnaliser."></textarea>
      </div>
      <div>
        <label style="font-size:.68rem;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px;">Message 2 <span style="color:#475569">(optionnel — envoyé 5-18s après)</span></label>
        <textarea id="etContent2" class="modal-textarea" style="border-color:#1e3a5f;" placeholder="Laisser vide pour désactiver"></textarea>
      </div>
      <div>
        <label style="font-size:.68rem;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px;">Message 3</label>
        <textarea id="etContent3" class="modal-textarea" style="border-color:#1e3a5f;" placeholder="Laisser vide pour désactiver"></textarea>
      </div>
      <div>
        <label style="font-size:.68rem;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px;">Message 4</label>
        <textarea id="etContent4" class="modal-textarea" style="border-color:#1e3a5f;" placeholder="Laisser vide pour désactiver"></textarea>
      </div>
      <div>
        <label style="font-size:.68rem;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px;">Message 5</label>
        <textarea id="etContent5" class="modal-textarea" style="border-color:#1e3a5f;" placeholder="Laisser vide pour désactiver"></textarea>
      </div>
    </div>
    <div class="modal-actions" style="margin-top:16px;">
      <button class="btn-modal-cancel" onclick="closeEditTplModal()">Annuler</button>
      <button class="btn-modal-save" id="btnSaveEditTpl" onclick="saveEditTpl()">💾 Enregistrer</button>
    </div>
  </div>
</div>

<!-- ── Modal Bio ── -->
<div class="modal-overlay" id="bioModal">
  <div class="modal-box">
    <p class="modal-title">✏ Bio Telegram — <span id="bioModalPid" style="color:#93c5fd;font-size:.85rem;"></span></p>
    <p style="font-size:.72rem;color:#475569;margin-bottom:10px;">
      Sera appliquée lors du prochain lancement de <code style="background:#0f172a;padding:1px 5px;border-radius:4px;">profile_changer.py</code>
    </p>
    <textarea class="modal-textarea" id="bioText" placeholder="Ta bio Telegram...&#10;Ex: Gestion de comptes Instagram · OF Agency · DM pour infos"></textarea>
    <div class="modal-actions">
      <button class="btn-modal-cancel" onclick="closeBioModal()">Annuler</button>
      <button class="btn-modal-save" onclick="saveBio()">💾 Enregistrer la bio</button>
    </div>
  </div>
</div>

<div id="toast" class="toast">Enregistré !</div>
<script>
// ── Données templates pour le modal d'édition ──
const TPL_DATA = {tpl_json};
let _editTplId = null;

function openEditTplModal(id) {{
  const d = TPL_DATA[id] || {{}};
  _editTplId = id;
  document.getElementById('editTplModalName').textContent = d.name || ('Template #' + id);
  document.getElementById('etName').value     = d.name     || '';
  document.getElementById('etContent').value  = d.content  || '';
  document.getElementById('etContent2').value = d.content2 || '';
  document.getElementById('etContent3').value = d.content3 || '';
  document.getElementById('etContent4').value = d.content4 || '';
  document.getElementById('etContent5').value = d.content5 || '';
  document.getElementById('editTplModal').classList.add('open');
}}
function closeEditTplModal() {{
  document.getElementById('editTplModal').classList.remove('open');
}}
async function saveEditTpl() {{
  if (!_editTplId) return;
  const name    = document.getElementById('etName').value.trim();
  const content = document.getElementById('etContent').value.trim();
  if (!name || !content) {{ alert('Le nom et le Message 1 sont obligatoires.'); return; }}
  const btn = document.getElementById('btnSaveEditTpl');
  btn.disabled    = true;
  btn.textContent = '⏳ Enregistrement...';
  const payload = {{
    id: _editTplId,
    name,
    content,
    content2: document.getElementById('etContent2').value.trim(),
    content3: document.getElementById('etContent3').value.trim(),
    content4: document.getElementById('etContent4').value.trim(),
    content5: document.getElementById('etContent5').value.trim(),
  }};
  const d = await _post('/api/dm_template/update', payload);
  btn.disabled    = false;
  btn.textContent = '💾 Enregistrer';
  if (d.ok) {{
    showToast('Template mis à jour ✓');
    closeEditTplModal();
    setTimeout(() => location.reload(), 1000);
  }} else {{
    alert('Erreur : ' + (d.detail || JSON.stringify(d)));
  }}
}}
document.getElementById('editTplModal').addEventListener('click', function(e) {{
  if (e.target === this) closeEditTplModal();
}});

function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.display = 'block';
  setTimeout(() => t.style.display='none', 2200);
}}
async function _post(url, body) {{
  const r = await fetch(url, {{method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify(Object.assign({{token:'Compte.1'}}, body))}});
  return r.json();
}}
// ── Gestion dynamique des messages supplémentaires (max 5) ──
let _extraMsgCount = 0;
function addExtraMsg() {{
  if (_extraMsgCount >= 4) return; // déjà 5 messages (1 de base + 4 extra)
  _extraMsgCount++;
  const n = _extraMsgCount + 1; // numéro affiché (2, 3, 4, 5)
  const container = document.getElementById('extra-msgs-container');
  const wrapper = document.createElement('div');
  wrapper.id = `extra-msg-wrapper-${{n}}`;
  wrapper.style = 'position:relative;';
  wrapper.innerHTML = `
    <textarea id="tcontent${{n}}" class="add-textarea"
      placeholder="Message ${{n}} (optionnel — envoyé 5-18s après le précédent)&#10;Utilise aussi {{prenom}}."
      style="border-color:#1e3a5f;padding-right:36px;"></textarea>
    <button onclick="removeExtraMsg(${{n}})" title="Supprimer ce message"
      style="position:absolute;top:6px;right:6px;background:#450a0a;border:none;color:#fca5a5;
             border-radius:5px;width:24px;height:24px;cursor:pointer;font-size:.8rem;line-height:1;">✕</button>
  `;
  container.appendChild(wrapper);
  if (_extraMsgCount >= 4) {{
    document.getElementById('btnAddMsg').style.display = 'none';
  }}
}}
function removeExtraMsg(n) {{
  const w = document.getElementById(`extra-msg-wrapper-${{n}}`);
  if (w) w.remove();
  _extraMsgCount--;
  document.getElementById('btnAddMsg').style.display = 'block';
}}
function _resetTplForm() {{
  document.getElementById('tname').value = '';
  document.getElementById('tcontent').value = '';
  document.getElementById('extra-msgs-container').innerHTML = '';
  _extraMsgCount = 0;
  document.getElementById('btnAddMsg').style.display = 'block';
}}
async function addTpl() {{
  const name    = document.getElementById('tname').value.trim();
  const content = document.getElementById('tcontent').value.trim();
  if (!name || !content) {{ alert('Nom et contenu requis.'); return; }}
  const body = {{name, content}};
  for (let i = 2; i <= 5; i++) {{
    const el = document.getElementById('tcontent' + i);
    if (el) body['content' + i] = el.value.trim();
  }}
  const d = await _post('/api/dm_template/add', body);
  if (d.ok) {{ showToast('Template ajouté !'); setTimeout(() => location.reload(), 1200); }}
  else alert('Erreur : ' + (d.detail || JSON.stringify(d)));
}}
async function delTpl(id) {{
  if (!confirm('Supprimer ce template définitivement ?')) return;
  const d = await _post('/api/dm_template/delete', {{id}});
  if (d.ok) location.reload();
}}
async function toggleTpl(id, active) {{
  const d = await _post('/api/dm_template/toggle', {{id, active}});
  if (d.ok) {{ showToast(active ? 'Template activé ✓' : 'Template désactivé'); setTimeout(() => location.reload(), 800); }}
}}
async function replyTpl(id) {{
  const d = await _post('/api/dm_template/reply', {{id}});
  if (d.ok) {{ showToast('+1 réponse enregistrée !'); setTimeout(() => location.reload(), 800); }}
}}
document.addEventListener('DOMContentLoaded', () => {{
  const ta = document.getElementById('tcontent');
  if (ta) ta.addEventListener('keydown', e => {{ if (e.key==='Enter' && e.ctrlKey) addTpl(); }});
}});
let _bioPid = '';
function openBioModal(pid, currentBio) {{
  _bioPid = pid;
  document.getElementById('bioModalPid').textContent = pid;
  document.getElementById('bioText').value = currentBio.replace(/&#39;/g,"'").replace(/&quot;/g,'"');
  document.getElementById('bioModal').classList.add('open');
}}
function closeBioModal() {{
  document.getElementById('bioModal').classList.remove('open');
}}
async function saveBio() {{
  const bio = document.getElementById('bioText').value.trim();
  const r = await fetch('/api/setup/bio', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{token:'Compte.1', profile_id: _bioPid, bio}})
  }});
  const d = await r.json();
  if (d.ok) {{ showToast('Bio sauvegardée ✓'); closeBioModal(); setTimeout(() => location.reload(), 1200); }}
  else alert('Erreur : ' + JSON.stringify(d));
}}
document.getElementById('bioModal').addEventListener('click', function(e) {{
  if (e.target === this) closeBioModal();
}});
async function launchMassDm() {{
  const btn = document.getElementById('btn-launch-dm');
  btn.disabled = true;
  btn.textContent = '⏳ Envoi du signal...';
  const SUPA_URL = 'https://pirlgavzihmnwmqlyeir.supabase.co';
  const SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBpcmxnYXZ6aWhtbndtcWx5ZWlyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3MzQxMTAsImV4cCI6MjA5NTMxMDExMH0.0QdskD9IBsx1rUZ_7Sljb8DshovkQMJIhmnAM-Zc6Ps';
  const HDRS = {{
    'apikey': SUPA_KEY,
    'Authorization': `Bearer ${{SUPA_KEY}}`,
    'Content-Type': 'application/json',
    'Prefer': 'resolution=merge-duplicates,return=minimal'
  }};
  try {{
    // 1. Efface tout trigger warmup en attente (évite double terminal)
    await fetch(`${{SUPA_URL}}/rest/v1/channels?url=eq.__warmup_trigger__`, {{
      method: 'PATCH', headers: HDRS,
      body: JSON.stringify({{status:'idle'}})
    }});
    // 2. Active le trigger Mass DM
    const r = await fetch(`${{SUPA_URL}}/rest/v1/channels?on_conflict=url`, {{
      method: 'POST', headers: HDRS,
      body: JSON.stringify({{url:'__massdm_trigger__', status:'triggered', members_count:0}})
    }});
    if (r.ok || r.status === 201 || r.status === 200 || r.status === 204) {{
      btn.textContent = '✓ Signal envoyé';
      btn.style.background = '#1e293b';
      document.getElementById('launch-dm-msg').style.display = 'inline';
    }} else {{
      throw new Error(await r.text());
    }}
  }} catch(e) {{
    btn.disabled = false;
    btn.textContent = '⚡ Lancer le Mass DM maintenant';
    alert('Erreur Supabase : ' + e.message);
  }}
}}
async function setGenreFilter(val) {{
  const r = await fetch('/api/massdm/settings', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{token: 'Compte.1', genre_filter: val}})
  }});
  const d = await r.json();
  if (d.ok) {{
    const el = document.getElementById('genre-saved');
    el.style.display = 'inline';
    setTimeout(() => el.style.display = 'none', 2000);
  }}
}}
async function launchProfileDm(pid) {{
  const btn = event.currentTarget;
  btn.disabled = true;
  btn.textContent = '⏳...';
  const SUPA_URL = 'https://pirlgavzihmnwmqlyeir.supabase.co';
  const SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBpcmxnYXZ6aWhtbndtcWx5ZWlyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3MzQxMTAsImV4cCI6MjA5NTMxMDExMH0.0QdskD9IBsx1rUZ_7Sljb8DshovkQMJIhmnAM-Zc6Ps';
  try {{
    const r = await fetch(`${{SUPA_URL}}/rest/v1/channels?on_conflict=url`, {{
      method: 'POST',
      headers: {{
        'apikey': SUPA_KEY,
        'Authorization': `Bearer ${{SUPA_KEY}}`,
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates,return=minimal'
      }},
      body: JSON.stringify({{url:`__massdm_pid_${{pid}}__`, status:'triggered', members_count:0}})
    }});
    if (r.ok || r.status === 201 || r.status === 200 || r.status === 204) {{
      btn.textContent = '✓ Lancé';
      btn.style.background = '#14532d';
      showToast(`⚡ Mass DM lancé pour ${{pid}} — démarrage dans ~30s`);
    }} else {{
      throw new Error(await r.text());
    }}
  }} catch(e) {{
    btn.disabled = false;
    btn.textContent = '▶ Lancer';
    alert('Erreur Supabase : ' + e.message);
  }}
}}
async function toggleModeMassDm(pid, mode) {{
  const label = mode === 'direct_dm'
    ? '⚡ Activer le Mass DM pour ce profil ?\\n(Il quittera le warm-up et enverra des DMs depuis le CSV scrapé)'
    : '↩ Repasser ce profil en Warm-Up ?';
  if (!confirm(label)) return;
  const r = await fetch('/api/profile/mode', {{
    method: 'POST', headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{token:'Compte.1', profile_id: pid, mode}})
  }});
  const d = await r.json();
  if (d.ok) location.reload();
  else alert('Erreur : ' + JSON.stringify(d));
}}
</script>
</div></div>{SIDEBAR_JS}
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
    a_scraper     = sum(1 for c in channels if c.get("status") == "A scraper")
    en_cours      = sum(1 for c in channels if c.get("status") == "En cours")
    en_attente    = sum(1 for c in channels if c.get("status") not in ("Scrappe", "A scraper", "En cours", "Erreur"))

    rows = ""
    for i, c in enumerate(channels, 1):
        status = c.get("status", "En attente")
        count  = c.get("members_count", 0)
        last   = c.get("last_scraped") or "—"
        cid    = c.get("id")
        url    = c.get("url", "")

        if status == "Scrappe":
            sb = '<span class="badge scrapped">Scrappe ✓</span>'
        elif status == "En cours":
            sb = '<span class="badge active">En cours...</span>'
        elif status == "Erreur":
            sb = '<span class="badge error">Erreur</span>'
        elif status == "A scraper":
            sb = '<span class="badge todo">A scraper ⏳</span>'
        else:
            sb = '<span class="badge waiting">En attente</span>'

        # Bouton scraper : desactive si deja en cours ou marque
        if status in ("En cours",):
            scrape_btn = '<button class="btn-scrape" disabled title="En cours...">⏳</button>'
        elif status == "A scraper":
            scrape_btn = '<button class="btn-scrape todo" disabled title="En attente du script">⏳ Queue</button>'
        else:
            scrape_btn = f'<button class="btn-scrape" onclick="requestScrape({cid})" title="Marquer ce canal pour scraping">🔍 Scraper</button>'

        rows += f"""<tr>
          <td class="num">{i}</td>
          <td class="url-cell" title="{url}">{url}</td>
          <td class="center">{count if count > 0 else '—'}</td>
          <td>{sb}</td>
          <td class="last">{last}</td>
          <td class="center actions-cell">{scrape_btn}<button class="btn-del" onclick="delItem({cid},'/api/channel/delete')" title="Supprimer">✕</button></td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scraper — Canaux</title>
<style>{BASE_CSS}
/* ── Scraper — dark dashboard theme ── */
.sc-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px}}
.sc-stat{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:20px 22px;transition:border-color .2s,box-shadow .25s,transform .25s}}
.sc-stat:hover{{border-color:#dc2626;box-shadow:0 0 24px rgba(220,38,38,.14);transform:translateY(-2px)}}
.sc-stat .sv{{font-size:2.2rem;font-weight:900;color:#f0f0f0;line-height:1}}
.sc-stat .sl{{font-size:.67rem;font-weight:800;color:#555;text-transform:uppercase;letter-spacing:.1em;margin-top:6px}}
.sc-stat.sc-total .sv{{color:#dc2626}}
.sc-stat.sc-warn .sv{{color:#f59e0b}}
.sc-shdr{{display:flex;align-items:center;gap:8px;margin:24px 0 14px}}
.sc-shdr .sec-bar{{width:3px;height:13px;background:#dc2626;border-radius:99px;flex-shrink:0}}
.sc-shdr .sec-title{{font-size:.7rem;font-weight:800;color:#888;text-transform:uppercase;letter-spacing:.12em}}
.sc-shdr .sec-count{{font-size:.72rem;color:#444;margin-left:auto}}
.sc-add-box{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:18px 22px;display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap}}
.sc-add-box h2{{font-size:.88rem;font-weight:700;color:#e0e0e0;white-space:nowrap}}
.sc-add-box input{{flex:1;min-width:200px;background:#0d0d0d;border:1px solid #1f1f1f;border-radius:8px;padding:10px 14px;color:#e0e0e0;font-size:.875rem;font-family:monospace;transition:border-color .15s}}
.sc-add-box input:focus{{outline:none;border-color:#dc2626}}
.sc-add-box button{{background:#dc2626;border:none;border-radius:8px;padding:10px 22px;color:#fff;font-weight:700;font-size:.82rem;cursor:pointer;transition:all .15s;white-space:nowrap}}
.sc-add-box button:hover{{background:#b91c1c}}
.sc-table-card{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;overflow:hidden;margin-bottom:16px}}
.sc-table-card table{{width:100%;border-collapse:collapse;font-size:.875rem}}
.sc-table-card thead tr{{background:#0d0d0d}}
.sc-table-card thead th{{color:#333;font-weight:800;padding:13px 16px;text-align:center;font-size:.62rem;text-transform:uppercase;letter-spacing:.12em;border-bottom:1px solid #1a1a1a;white-space:nowrap}}
.sc-table-card thead th.thl{{text-align:left}}
.sc-table-card tbody tr{{border-bottom:1px solid #1a1a1a;transition:background .15s}}
.sc-table-card tbody tr:hover{{background:rgba(220,38,38,.04)}}
.sc-table-card td{{padding:14px 16px;vertical-align:middle;color:#888;font-size:.82rem}}
.sc-table-card td.url-cell{{color:#e0e0e0;font-family:monospace;font-size:.78rem;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.sc-table-card td.num{{color:#333;text-align:center;font-size:.75rem}}
.sc-table-card td.center{{text-align:center}}
.sc-table-card td.last{{color:#555;font-size:.75rem}}
.badge{{display:inline-block;padding:3px 10px;border-radius:99px;font-size:.68rem;font-weight:700;letter-spacing:.05em}}
.badge.done{{background:rgba(22,163,74,.15);color:#4ade80;border:1px solid rgba(22,163,74,.25)}}
.badge.todo{{background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.25)}}
.badge.inprogress{{background:rgba(220,38,38,.15);color:#f87171;border:1px solid rgba(220,38,38,.25)}}
.badge.waiting{{background:rgba(100,100,100,.12);color:#555;border:1px solid rgba(100,100,100,.2)}}
.btn-scrape{{background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;border-radius:6px;padding:5px 12px;font-size:.75rem;font-weight:700;cursor:pointer;transition:all .15s;white-space:nowrap}}
.btn-scrape:hover{{border-color:#dc2626;color:#f0f0f0}}
.btn-scrape.todo,.btn-scrape:disabled{{background:#111;color:#333;cursor:not-allowed;border-color:#1a1a1a}}
.actions-cell{{display:flex;gap:6px;justify-content:center;align-items:center}}
.btn-del{{background:#1a0a0a;border:1px solid #3d1212;color:#666;border-radius:6px;padding:5px 10px;font-size:.75rem;cursor:pointer;transition:all .15s}}
.btn-del:hover{{background:#450a0a;color:#fca5a5;border-color:#7f1d1d}}
.sc-info-card{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:22px 26px;margin-bottom:16px}}
.sc-info-card p{{color:#666;font-size:.82rem;line-height:1.8;margin:0}}
.sc-info-card strong{{color:#aaa}}
.sc-info-card code{{background:#0d0d0d;border:1px solid #1f1f1f;padding:2px 7px;border-radius:5px;font-family:monospace;color:#dc2626;font-size:.78rem}}
{SIDEBAR_CSS}</style>
<meta http-equiv="refresh" content="30"></head><body>
<div class="ov-layout">{_sidebar_html('scraper')}<div class="page-main">

  <!-- ── Header ── -->
  <div class="ov-header" style="margin-bottom:24px">
    <div class="ov-title">Scraper</div>
    <div class="ov-subtitle">Canaux Telegram a scrapper pour le Mass DM</div>
  </div>

  <!-- ── Stats ── -->
  <div class="sc-stats">
    <div class="sc-stat"><div class="sv">{len(channels)}</div><div class="sl">Canaux enregistres</div></div>
    <div class="sc-stat"><div class="sv">{scraped}</div><div class="sl">Deja scrapes</div></div>
    <div class="sc-stat sc-warn"><div class="sv">{a_scraper}</div><div class="sl">En attente scraping</div></div>
    <div class="sc-stat"><div class="sv">{en_attente}</div><div class="sl">Pas encore marques</div></div>
    <div class="sc-stat sc-total"><div class="sv">{total_members}</div><div class="sl">Membres collectes au total</div></div>
  </div>

  <!-- ── Ajouter un canal ── -->
  <div class="sc-shdr">
    <div class="sec-bar"></div>
    <div class="sec-title">Ajouter un canal</div>
  </div>
  <div class="sc-add-box">
    <h2>+ Nouveau canal</h2>
    <input id="inp" type="text" placeholder="https://t.me/nom_du_canal  ou  @nom_canal">
    <button onclick="addItem()">Ajouter</button>
  </div>

  <!-- ── Tableau des canaux ── -->
  <div class="sc-shdr">
    <div class="sec-bar"></div>
    <div class="sec-title">Canaux configures</div>
    <div class="sec-count">{len(channels)} canal{'x' if len(channels) > 1 else ''}</div>
  </div>
  <div class="sc-table-card"><table><thead><tr>
    <th class="thl" style="width:36px">#</th>
    <th class="thl">Lien du canal</th>
    <th>Membres actifs</th>
    <th>Statut</th>
    <th>Dernier scraping</th>
    <th style="width:160px">Actions</th>
  </tr></thead><tbody>{rows if rows else '<tr><td colspan="6" style="text-align:center;color:#333;padding:36px;font-size:.82rem">Aucun canal — ajoutes-en un ci-dessus</td></tr>'}</tbody></table></div>

  <!-- ── Comment ca marche ── -->
  <div class="sc-shdr">
    <div class="sec-bar"></div>
    <div class="sec-title">Comment ca marche</div>
  </div>
  <div class="sc-info-card">
    <p>
      <strong>1.</strong> Ajoute ici les liens des canaux Telegram a scrapper<br>
      <strong>2.</strong> Clique <strong>🔍 Scraper</strong> sur les canaux voulus — le statut devient <em style="color:#f59e0b">A scraper ⏳</em><br>
      <strong>3.</strong> Lance <code>python scraper.py</code> sur ton PC — il scrappe uniquement les canaux marques<br>
      <strong>4.</strong> Seuls les membres actifs (&le;30 jours) avec @username sont gardes → <code>output/membres.csv</code><br>
      <strong>5.</strong> Puis <code>dm_sender.py</code> (ou warmup_v2.py en mode Direct DM) envoie les DMs
    </p>
  </div>

  <p class="refresh" style="color:#333;font-size:.72rem;text-align:center">Refresh auto toutes les 30s</p>
  {add_js('/api/channel/add', 'inp', 'Canal ajoute !')}
<script>
async function requestScrape(cid) {{
  const btn = event.target.closest('button');
  btn.disabled = true;
  btn.textContent = '⏳ Queue';
  const r = await fetch('/api/channel/request-scrape', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{token: 'Compte.1', channel_id: cid}})
  }});
  const data = await r.json();
  if (data.ok) {{
    setTimeout(() => window.location.reload(), 800);
  }} else {{
    btn.disabled = false;
    btn.textContent = '🔍 Scraper';
    alert('Erreur : ' + (data.detail || JSON.stringify(data)));
  }}
}}
</script>
</div></div>{SIDEBAR_JS}
</body></html>"""
    return html


# ═══════════════════════════════════════════════════════════
#  PAGE SETUP
# ═══════════════════════════════════════════════════════════

@app.get("/setup", response_class=HTMLResponse)
def dashboard_setup():
    configs     = load_profile_setup()
    profile_ids = get_all_ids()
    nb_config   = len(configs)
    config_map  = {c["profile_id"]: c for c in configs}
    apply_res   = _apply_results  # résultats profile_changer.py

    # JSON pour le JS — évite tout problème d'échappement dans les onclick
    setup_data_js: dict = {}
    for c in configs:
        setup_data_js[c["profile_id"]] = {
            "first_name": c.get("first_name", "") or "",
            "username":   c.get("username", "") or "",
            "bio":        c.get("bio", "") or "",
            "has_photo":  bool(c.get("photo_b64")),
        }
    setup_json = json.dumps(setup_data_js, ensure_ascii=False)

    # ── Tableau des profils configurés ───────────────────────
    rows = ""
    for c in configs:
        pid   = c["profile_id"]
        uname = c.get("username", "") or ""
        bio   = (c.get("bio", "") or "")[:60]
        if len(c.get("bio","") or "") > 60:
            bio += "…"
        bio   = bio.replace("&","&amp;").replace("<","&lt;") or "—"
        upd   = c.get("updated_at", "") or "—"

        # Photo
        pb64  = c.get("photo_b64", "") or ""
        pname = c.get("photo_name", "") or ""
        if pb64:
            ext = "jpeg" if pname.lower().endswith((".jpg",".jpeg")) else "png"
            photo_html = f'<img src="data:image/{ext};base64,{pb64}" class="profile-photo-thumb" alt="photo" style="width:46px;height:46px;border-radius:50%;object-fit:cover;">'
        else:
            photo_html = '<div style="width:46px;height:46px;border-radius:50%;background:#1a1a1a;border:1px solid #1f1f1f;display:flex;align-items:center;justify-content:center;font-size:1.3rem;">👤</div>'

        # ── Dot indicateur statut ──────────────────────────────
        res   = apply_res.get(pid, {})
        etype = res.get("error_type", "")
        err   = (res.get("error") or "")[:60]
        at    = res.get("at", "")

        if res.get("ok") is True:
            dot_cls  = "dot-ok"
            dot_tip  = f"✅ Upload réussi · {at}"
            dot_lbl  = f'<span class="status-dot-lbl" style="color:#22c55e;">✅ {at}</span>'
        elif etype == "not_connected":
            dot_cls  = "dot-nc"
            dot_tip  = "⛔ Telegram non connecté"
            dot_lbl  = '<span class="status-dot-lbl" style="color:#ef4444;">Telegram non connecté</span>'
        elif etype in ("upload_failed",):
            dot_cls  = "dot-upload"
            dot_tip  = f"⚠ Upload échoué · {err}"
            dot_lbl  = '<span class="status-dot-lbl" style="color:#f97316;">Upload échoué</span>'
        elif res.get("ok") is False:
            dot_cls  = "dot-err"
            dot_tip  = f"⚠ Erreur · {err}"
            dot_lbl  = f'<span class="status-dot-lbl" style="color:#f97316;">{err[:40]}</span>'
        else:
            dot_cls  = "dot-none"
            dot_tip  = "En attente"
            dot_lbl  = ""

        status_html = (
            f'<div class="status-dot-wrap">'
            f'<span class="status-dot {dot_cls}" title="{dot_tip}"></span>'
            f'{dot_lbl}'
            f'</div>'
        )

        rows += f"""<tr>
          <td style="padding:10px 16px;">{photo_html}</td>
          <td style="font-family:monospace;font-size:.78rem;color:#888;">{pid}</td>
          <td style="font-family:monospace;font-size:.82rem;color:#dc2626;">{"@"+uname if uname else "<span style='color:#2a2a2a'>—</span>"}</td>
          <td style="font-size:.75rem;color:#555;max-width:180px;">{bio}</td>
          <td style="font-size:.7rem;max-width:200px;">{status_html}</td>
          <td style="font-size:.7rem;color:#333;">{upd[:16]}</td>
          <td style="white-space:nowrap;text-align:center;">
            <button class="btn-edit-setup" onclick="openEditModal('{pid}')">✏ Modifier</button>
            &nbsp;
            <button class="btn-del" onclick="deleteSetup('{pid}')" title="Supprimer">✕</button>
          </td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:#333;padding:36px;">Aucun profil configuré — clique sur un profil ci-dessous pour démarrer</td></tr>'

    non_config = [p for p in profile_ids if p not in config_map]

    # ── Cartes profils ──
    cards_html = ""
    for i, p in enumerate(profile_ids):
        cfg        = config_map.get(p, {})
        is_cfg     = p in config_map
        card_cls   = "profile-quick-card configured" if is_cfg else "profile-quick-card"
        pb64_val   = cfg.get("photo_b64", "") or ""
        pname_val  = cfg.get("photo_name", "") or ""

        # Photo : image complète si dispo, sinon placeholder
        if pb64_val:
            ext      = "jpeg" if pname_val.lower().endswith((".jpg", ".jpeg")) else "png"
            photo_el = f'<img src="data:image/{ext};base64,{pb64_val}" style="width:100%;height:100%;object-fit:cover;" alt="">'
        else:
            photo_el = "👤"

        fname      = (cfg.get("first_name", "") or "").strip()
        uname      = (cfg.get("username", "") or "").strip()
        # Nom affiché : prénom si dispo, sinon "—"
        name_disp  = fname if fname else ("<span style='color:#2a2a2a'>Sans nom</span>" if not is_cfg else "<span style='color:#555'>Prénom non défini</span>")
        un_display = f"@{uname}" if uname else "<span style='color:#333'>@—</span>"
        status_lbl = "✓ Configuré" if is_cfg else "Non configuré"
        btn_label  = "✏ Modifier" if is_cfg else "⚙ Configurer"
        btn_color  = "rgba(220,38,38,.15)" if is_cfg else "#1a1a1a"
        btn_txt_col= "#dc2626" if is_cfg else "#666"

        cards_html += f"""<div class="{card_cls}" data-pid="{p}">
      <div class="pqc-num">#{i+1}</div>
      <div class="pqc-photo" onclick="openEditModal('{p}')">{photo_el}</div>
      <div class="pqc-name">{name_disp}</div>
      <div class="pqc-pid">{p}</div>
      <div class="pqc-un">{un_display}</div>
      <div class="pqc-status">{status_lbl}</div>
      <button onclick="openEditModal('{p}')" style="margin-top:10px;width:100%;background:{btn_color};color:{btn_txt_col};border:1px solid rgba(220,38,38,.25);border-radius:7px;padding:8px 0;font-size:.72rem;font-weight:700;cursor:pointer;letter-spacing:.04em;transition:all .15s;">{btn_label}</button>
    </div>"""

    # ── Carte spéciale "Upload en masse" — toujours en dernière position ──
    cards_html += """<div class="profile-mass-card" onclick="openMassUpload()">
      <div class="pmc-icon">📤</div>
      <div class="pmc-title">Upload en masse</div>
      <div class="pmc-sub">Jusqu'à 25 photos<br>1 par profil sélectionné</div>
      <div class="pmc-delay">⏱ 6 min entre chaque profil</div>
    </div>"""

    # JSON profils pour JS
    profiles_for_js = json.dumps([
        {
            "id": p,
            "num": str(i + 1),
            "has_photo": bool(config_map.get(p, {}).get("photo_b64")),
            "username": config_map.get(p, {}).get("username", "") or "",
        }
        for i, p in enumerate(profile_ids)
    ], ensure_ascii=False)

    html = f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Setup Profils</title>
<style>{BASE_CSS}
/* ── Setup — dark dashboard theme ── */
.setup-shdr{{display:flex;align-items:center;gap:8px;margin:24px 0 14px}}
.setup-shdr .sec-bar{{width:3px;height:13px;background:#dc2626;border-radius:99px;flex-shrink:0}}
.setup-shdr .sec-title{{font-size:.7rem;font-weight:800;color:#888;text-transform:uppercase;letter-spacing:.12em}}
.setup-shdr .sec-count{{font-size:.72rem;color:#444;margin-left:auto}}
.setup-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px}}
.setup-stat{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:20px 22px;transition:border-color .2s,box-shadow .25s,transform .25s}}
.setup-stat:hover{{border-color:#dc2626;box-shadow:0 0 24px rgba(220,38,38,.14);transform:translateY(-2px)}}
.setup-stat .sv{{font-size:2.2rem;font-weight:900;color:#f0f0f0;line-height:1}}
.setup-stat .sl{{font-size:.67rem;font-weight:800;color:#555;text-transform:uppercase;letter-spacing:.1em;margin-top:6px}}
.setup-add-box{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:18px 22px;display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap}}
.setup-add-box h2{{font-size:.88rem;font-weight:700;color:#e0e0e0;white-space:nowrap}}
.setup-add-box input{{flex:1;min-width:200px;background:#0d0d0d;border:1px solid #1f1f1f;border-radius:8px;padding:10px 14px;color:#e0e0e0;font-size:.875rem;font-family:monospace;transition:border-color .15s}}
.setup-add-box input:focus{{outline:none;border-color:#dc2626}}
.setup-add-box button{{background:#dc2626;border:none;border-radius:8px;padding:10px 22px;color:#fff;font-weight:700;font-size:.82rem;cursor:pointer;transition:all .15s;white-space:nowrap}}
.setup-add-box button:hover{{background:#b91c1c}}
.setup-modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9000;align-items:center;justify-content:center;padding:20px}}
.setup-modal-overlay.open{{display:flex}}
.setup-modal{{background:#141414;border:1px solid #1f1f1f;border-radius:16px;padding:28px 32px;width:100%;max-width:520px;box-shadow:0 24px 80px rgba(0,0,0,.9)}}
.setup-modal h2{{font-size:1rem;color:#f0f0f0;margin-bottom:20px;font-weight:800;letter-spacing:.02em}}
.setup-field{{margin-bottom:16px}}
.setup-field label{{display:block;font-size:.67rem;font-weight:800;color:#555;text-transform:uppercase;letter-spacing:.1em;margin-bottom:7px}}
.setup-field input,.setup-field textarea{{width:100%;background:#0d0d0d;border:1px solid #1f1f1f;border-radius:8px;padding:10px 13px;color:#e0e0e0;font-size:.875rem;font-family:inherit;resize:vertical;transition:border-color .15s}}
.setup-field input:focus,.setup-field textarea:focus{{outline:none;border-color:#dc2626}}
.setup-field textarea{{min-height:80px}}
.photo-upload-area{{display:flex;align-items:center;gap:16px;margin-top:4px}}
.photo-upload-preview{{width:72px;height:72px;border-radius:50%;overflow:hidden;background:#0d0d0d;border:2px solid #1f1f1f;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:2rem}}
.photo-upload-preview img{{width:100%;height:100%;object-fit:cover}}
.btn-choose-photo{{background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;border-radius:8px;padding:9px 18px;font-size:.78rem;font-weight:700;cursor:pointer;display:inline-block;margin-bottom:6px;transition:all .15s;user-select:none;-webkit-user-select:none;text-align:center}}
.btn-choose-photo:hover{{border-color:#dc2626;color:#f0f0f0}}
.btn-apply{{width:100%;background:linear-gradient(135deg,#dc2626,#b91c1c);border:none;border-radius:10px;padding:13px;color:#fff;font-size:.92rem;font-weight:800;cursor:pointer;box-shadow:0 0 18px rgba(220,38,38,.3);margin-top:6px;transition:all .2s}}
.btn-apply:hover{{box-shadow:0 0 28px rgba(220,38,38,.55)}}
.btn-apply:disabled{{opacity:.5;cursor:not-allowed;box-shadow:none}}
.btn-cancel-modal{{width:100%;background:transparent;border:1px solid #1f1f1f;border-radius:10px;padding:10px;color:#555;font-size:.82rem;font-weight:600;cursor:pointer;margin-top:8px;transition:all .15s}}
.btn-cancel-modal:hover{{border-color:#333;color:#aaa}}
.profiles-quick-list{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-bottom:8px}}
.profile-quick-card{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;padding:18px;text-align:center;cursor:pointer;transition:all .15s;position:relative}}
.profile-quick-card:hover{{border-color:#dc2626;box-shadow:0 0 20px rgba(220,38,38,.14);transform:translateY(-2px)}}
.profile-quick-card .pqc-num{{position:absolute;top:8px;left:8px;background:#0d0d0d;border:1px solid #222;color:#444;font-size:.62rem;font-weight:900;padding:2px 7px;border-radius:99px;font-family:monospace;letter-spacing:.02em;pointer-events:none}}
.profile-quick-card.configured .pqc-num{{color:#dc2626;border-color:rgba(220,38,38,.35)}}
.profile-quick-card .pqc-photo{{width:54px;height:54px;border-radius:50%;overflow:hidden;margin:0 auto 10px;background:#0d0d0d;border:2px solid #1f1f1f;display:flex;align-items:center;justify-content:center;font-size:1.5rem;transition:border-color .15s}}
.profile-quick-card:hover .pqc-photo{{border-color:#dc2626}}
.profile-quick-card .pqc-photo img{{width:100%;height:100%;object-fit:cover}}
.profile-quick-card .pqc-name{{font-size:.8rem;color:#d0d0d0;font-weight:700;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}}
.profile-quick-card .pqc-pid{{font-size:.65rem;font-family:monospace;color:#444;margin-bottom:3px}}
.profile-quick-card .pqc-un{{font-size:.72rem;color:#dc2626;font-weight:700}}
.profile-quick-card .pqc-status{{font-size:.6rem;color:#333;margin-top:5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}}
.profile-quick-card.configured{{border-color:rgba(220,38,38,.25)}}
.profile-quick-card.configured .pqc-status{{color:#dc2626}}
.apply-status{{font-size:.78rem;margin-top:12px;padding:10px 14px;border-radius:8px;display:none}}
.apply-status.ok{{background:#0a1a0a;border:1px solid #166534;color:#86efac}}
.apply-status.err{{background:#1a0a0a;border:1px solid #7f1d1d;color:#fca5a5}}
/* override BASE_CSS table/card for setup */
.setup-table-card{{background:#141414;border:1px solid #1f1f1f;border-radius:12px;overflow:hidden;margin-bottom:24px}}
.setup-table-card table{{width:100%;border-collapse:collapse;font-size:.875rem}}
.setup-table-card thead tr{{background:#0d0d0d}}
.setup-table-card thead th{{color:#333;font-weight:800;padding:13px 16px;text-align:center;font-size:.62rem;text-transform:uppercase;letter-spacing:.12em;border-bottom:1px solid #1a1a1a;white-space:nowrap}}
.setup-table-card thead th.thl{{text-align:left}}
.setup-table-card tbody tr{{border-bottom:1px solid #1a1a1a;transition:background .15s}}
.setup-table-card tbody tr:hover{{background:rgba(220,38,38,.04)}}
.setup-table-card td{{padding:14px 16px;vertical-align:middle;color:#888;font-size:.82rem}}
.btn-edit-setup{{background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;border-radius:6px;padding:5px 12px;font-size:.75rem;font-weight:700;cursor:pointer;transition:all .15s}}
.btn-edit-setup:hover{{border-color:#dc2626;color:#f0f0f0}}
.btn-del{{background:#1a0a0a;border:1px solid #3d1212;color:#666;border-radius:6px;padding:5px 10px;font-size:.75rem;cursor:pointer;transition:all .15s}}
.btn-del:hover{{background:#450a0a;color:#fca5a5;border-color:#7f1d1d}}
/* ── Carte upload en masse ── */
.profile-mass-card{{background:#0d0d0d;border:2px dashed #2a2a2a;border-radius:12px;padding:18px;text-align:center;cursor:pointer;transition:all .2s;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;min-height:180px}}
.profile-mass-card:hover{{border-color:#dc2626;background:#111;box-shadow:0 0 28px rgba(220,38,38,.18);transform:translateY(-2px)}}
.pmc-icon{{font-size:2rem;line-height:1}}
.pmc-title{{font-size:.88rem;font-weight:800;color:#e0e0e0;letter-spacing:.02em}}
.pmc-sub{{font-size:.68rem;color:#555;font-weight:600;line-height:1.4}}
.pmc-delay{{font-size:.62rem;color:#333;margin-top:4px;padding:4px 10px;background:#141414;border-radius:99px;border:1px solid #1f1f1f}}
/* ── Overlay upload en masse ── */
.mass-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:9500;align-items:center;justify-content:center;padding:20px}}
.mass-overlay.open{{display:flex}}
.mass-panel{{background:#141414;border:1px solid #1f1f1f;border-radius:18px;width:100%;max-width:680px;max-height:90vh;overflow-y:auto;box-shadow:0 32px 100px rgba(0,0,0,.9);display:flex;flex-direction:column}}
.mass-hdr{{display:flex;align-items:center;justify-content:space-between;padding:20px 24px 0;flex-shrink:0}}
.mass-hdr-title{{font-size:1rem;font-weight:800;color:#f0f0f0;letter-spacing:.02em}}
.mass-hdr-close{{background:none;border:none;color:#555;font-size:1.2rem;cursor:pointer;padding:4px;transition:color .15s}}
.mass-hdr-close:hover{{color:#f0f0f0}}
/* Steps indicator */
.mass-steps{{display:flex;align-items:center;padding:16px 24px 0;gap:0;flex-shrink:0}}
.mass-sdot{{width:28px;height:28px;border-radius:50%;background:#1a1a1a;border:2px solid #2a2a2a;color:#444;font-size:.72rem;font-weight:800;display:flex;align-items:center;justify-content:center;transition:all .3s;flex-shrink:0}}
.mass-sdot.active{{background:#dc2626;border-color:#dc2626;color:#fff;box-shadow:0 0 12px rgba(220,38,38,.4)}}
.mass-sdot.done{{background:#0a1a0a;border-color:#166534;color:#4ade80}}
.mass-sline{{flex:1;height:2px;background:#1f1f1f;transition:background .3s}}
.mass-sline.done{{background:#166534}}
/* Step labels */
.mass-step-labels{{display:flex;padding:6px 14px 0;gap:0;flex-shrink:0}}
.mass-slbl{{flex:1;font-size:.58rem;color:#444;font-weight:700;text-transform:uppercase;letter-spacing:.06em;text-align:center}}
.mass-slbl:first-child{{text-align:left;padding-left:4px}}
.mass-slbl:last-child{{text-align:right;padding-right:4px}}
/* Content */
.mass-content{{padding:20px 24px 24px;flex:1}}
.mass-content-title{{font-size:.72rem;font-weight:800;color:#888;text-transform:uppercase;letter-spacing:.1em;margin-bottom:14px}}
/* Step 1 – sélection profils */
.mass-prof-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:10px;margin-bottom:20px;max-height:280px;overflow-y:auto;padding-right:4px}}
.mass-pcard{{background:#0d0d0d;border:2px solid #1f1f1f;border-radius:10px;padding:10px 6px;text-align:center;cursor:pointer;transition:all .18s;user-select:none;position:relative}}
.mass-pcard:hover{{border-color:#444}}
.mass-pcard.sel{{border-color:#dc2626!important;background:#1a0d0d!important;transform:scale(1.04)}}
.mass-pcard.sel .mpcard-num{{color:#dc2626}}
.mass-pcheck{{position:absolute;top:5px;right:5px;width:16px;height:16px;border-radius:50%;background:#1f1f1f;border:1.5px solid #2a2a2a;font-size:.55rem;display:flex;align-items:center;justify-content:center;transition:all .18s}}
.mass-pcard.sel .mass-pcheck{{background:#dc2626;border-color:#dc2626;color:#fff;content:"✓"}}
.mpcard-avatar{{width:44px;height:44px;border-radius:50%;background:#1a1a1a;border:2px solid #1f1f1f;margin:0 auto 7px;overflow:hidden;display:flex;align-items:center;justify-content:center;font-size:1.1rem;transition:border-color .18s}}
.mass-pcard.sel .mpcard-avatar{{border-color:#dc2626}}
.mpcard-avatar img{{width:100%;height:100%;object-fit:cover}}
.mpcard-num{{font-size:.65rem;font-weight:800;color:#555;letter-spacing:.04em}}
.mpcard-un{{font-size:.6rem;color:#333;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%}}
.mass-sel-info{{font-size:.75rem;color:#555;margin-bottom:14px}}
.mass-sel-info span{{color:#dc2626;font-weight:800}}
.mass-selall{{background:none;border:1px solid #2a2a2a;color:#666;border-radius:6px;padding:5px 12px;font-size:.7rem;font-weight:700;cursor:pointer;margin-bottom:14px;transition:all .15s}}
.mass-selall:hover{{border-color:#dc2626;color:#f0f0f0}}
/* Step 2 – photos */
.mass-file-zone{{background:#0d0d0d;border:2px dashed #2a2a2a;border-radius:10px;padding:28px;text-align:center;cursor:pointer;margin-bottom:16px;transition:all .2s}}
.mass-file-zone:hover{{border-color:#dc2626;background:#111}}
.mass-file-zone label{{cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:8px}}
.mass-file-icon{{font-size:2rem}}
.mass-file-txt{{font-size:.82rem;font-weight:700;color:#888}}
.mass-file-sub{{font-size:.68rem;color:#444}}
.mass-photo-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px;margin-bottom:18px;max-height:200px;overflow-y:auto}}
.mass-photo-item{{position:relative;aspect-ratio:1;border-radius:8px;overflow:hidden;background:#0d0d0d;border:1px solid #1f1f1f}}
.mass-photo-item img{{width:100%;height:100%;object-fit:cover}}
.mass-photo-label{{position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,.7);font-size:.55rem;color:#ccc;padding:2px 4px;text-align:center;font-weight:700}}
.mass-photo-item.unassigned{{border-color:#3d1212;opacity:.5}}
.mass-warn{{background:#1a0d0d;border:1px solid #3d1212;border-radius:8px;padding:10px 14px;font-size:.72rem;color:#f87171;margin-bottom:14px}}
/* Step 3 – progression */
.mass-progress-item{{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid #1a1a1a}}
.mass-progress-item:last-child{{border-bottom:none}}
.mpi-num{{width:28px;height:28px;border-radius:50%;background:#1a1a1a;border:1.5px solid #2a2a2a;font-size:.7rem;font-weight:800;color:#555;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.mpi-num.running{{background:#1a0d0d;border-color:#dc2626;color:#f87171;animation:pulse-err 1.5s infinite}}
.mpi-num.done{{background:#0a1a0a;border-color:#166534;color:#4ade80}}
.mpi-info{{flex:1}}
.mpi-id{{font-size:.72rem;font-family:monospace;color:#888}}
.mpi-status{{font-size:.65rem;color:#444;margin-top:2px}}
.mpi-status.running{{color:#f87171}}
.mpi-status.done{{color:#4ade80}}
.mpi-countdown{{font-size:.82rem;font-weight:800;color:#dc2626;font-family:monospace;flex-shrink:0}}
.mass-global-status{{background:#141414;border:1px solid #1f1f1f;border-radius:8px;padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;gap:10px}}
.mgs-dot{{width:8px;height:8px;border-radius:50%;background:#dc2626;animation:pulse-err 1.5s infinite;flex-shrink:0}}
.mgs-txt{{font-size:.78rem;color:#888}}
/* Boutons actions masse */
.mass-btn{{width:100%;border:none;border-radius:10px;padding:13px;font-size:.88rem;font-weight:800;cursor:pointer;transition:all .2s;letter-spacing:.02em;margin-top:8px}}
.mass-btn-primary{{background:linear-gradient(135deg,#dc2626,#b91c1c);color:#fff;box-shadow:0 0 18px rgba(220,38,38,.3)}}
.mass-btn-primary:hover{{box-shadow:0 0 28px rgba(220,38,38,.55)}}
.mass-btn-primary:disabled{{opacity:.4;cursor:not-allowed;box-shadow:none}}
.mass-btn-sec{{background:#1a1a1a;border:1px solid #2a2a2a;color:#888}}
.mass-btn-sec:hover{{border-color:#dc2626;color:#f0f0f0}}
/* ── Bouton stop circulaire ── */
.mass-stop-btn{{position:relative;width:88px;height:88px;border-radius:50%;background:#0d0d0d;border:none;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;transition:all .25s;outline:none}}
.mass-stop-btn:hover{{background:#120000;transform:scale(1.06)}}
.mass-stop-btn:hover .mass-stop-arc{{stroke:#ff4444}}
.mass-stop-btn:disabled{{opacity:.35;cursor:not-allowed;transform:none}}
.mass-stop-ring{{position:absolute;inset:0;width:100%;height:100%;color:#dc2626;transform:rotate(-90deg)}}
.mass-stop-arc{{transition:stroke .2s;stroke-linecap:round;animation:stop-arc-spin 8s linear infinite}}
@keyframes stop-arc-spin{{to{{stroke-dashoffset:-100}}}}
.mass-stop-icon{{font-size:1.3rem;line-height:1;position:relative;z-index:1}}
.mass-stop-lbl{{font-size:.6rem;font-weight:800;color:#dc2626;letter-spacing:.06em;text-transform:uppercase;position:relative;z-index:1}}
{SIDEBAR_CSS}</style></head><body>
<div class="ov-layout">{_sidebar_html('setup')}<div class="page-main">
  <!-- ── Header ── -->
  <div class="ov-header" style="margin-bottom:24px">
    <div class="ov-title">Setup</div>
    <div class="ov-subtitle">Configure les profils Telegram — photo, @username et bio</div>
  </div>

  <!-- ── Stats ── -->
  <div class="setup-stats">
    <div class="setup-stat">
      <div class="sv">{len(profile_ids)}</div>
      <div class="sl">Profils totaux</div>
    </div>
    <div class="setup-stat">
      <div class="sv" style="color:#dc2626">{nb_config}</div>
      <div class="sl">Configurés</div>
    </div>
    <div class="setup-stat">
      <div class="sv">{len(non_config)}</div>
      <div class="sl">Non configurés</div>
    </div>
  </div>

  <!-- ── Profile cards ── -->
  <div class="setup-shdr">
    <div class="sec-bar"></div>
    <span class="sec-title">PROFILS</span>
    <span class="sec-count">{len(profile_ids)} profil(s)</span>
  </div>
  <div class="profiles-quick-list">
    {cards_html}
  </div>

  <!-- ── Configured table ── -->
  <div class="setup-shdr">
    <div class="sec-bar"></div>
    <span class="sec-title">CONFIGURÉS</span>
    <span class="sec-count">{nb_config} profil(s)</span>
  </div>
  <div class="setup-table-card">
    <table>
      <thead><tr>
        <th style="width:62px;">Photo</th>
        <th class="thl">ID Profil</th>
        <th class="thl">@Username</th>
        <th class="thl">Bio</th>
        <th>Modifié le</th>
        <th style="width:140px;"></th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <!-- ══ MODAL ÉDITION ══ -->
  <div class="setup-modal-overlay" id="setupModal">
    <div class="setup-modal">
      <h2>✏ Modifier le profil — <span id="modalPid" style="color:#dc2626;font-size:.88rem;font-family:monospace;"></span></h2>

      <!-- Photo -->
      <div class="setup-field">
        <label>📷 Photo de profil</label>
        <div class="photo-upload-area">
          <div class="photo-upload-preview" id="photoPreview">👤</div>
          <div>
            <input type="file" id="fPhoto" accept="image/*"
              style="position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;pointer-events:none;"
              onchange="previewPhoto(this)">
            <label for="fPhoto" class="btn-choose-photo">
              📷 Choisir une image
            </label>
            <p id="photoName" style="font-size:.7rem;color:#555;margin:0;margin-top:5px;"></p>
          </div>
        </div>
      </div>

      <!-- Prénom -->
      <div class="setup-field">
        <label>👤 Prénom (affiché dans Telegram)</label>
        <input id="fFirstName" type="text" placeholder="Sophie">
      </div>

      <!-- Username -->
      <div class="setup-field">
        <label>🔑 @Username (sans le @)</label>
        <input id="fUsername" type="text" placeholder="sophie_agency">
      </div>

      <!-- Bio -->
      <div class="setup-field">
        <label>📝 Bio Telegram</label>
        <textarea id="fBio" placeholder="Gestion de comptes Instagram · OF Agency&#10;DM pour infos 📩"></textarea>
      </div>

      <!-- Bouton -->
      <button type="button" class="btn-apply" id="btnApply" onclick="saveAndApply()">
        💾 Enregistrer &amp; Appliquer maintenant
      </button>
      <div class="apply-status" id="applyStatus"></div>
      <button type="button" class="btn-cancel-modal" onclick="closeModal()">Annuler</button>
    </div>
  </div>

<div id="toast" class="toast">Sauvegardé !</div>
<script>
const SETUP_DATA = {setup_json};

let _pid = '';
let _photoB64 = '';
let _photoName = '';

function openEditModal(pid) {{
  const d = SETUP_DATA[pid] || {{}};
  _pid = pid;
  _photoB64 = '';
  _photoName = '';
  document.getElementById('modalPid').textContent   = pid;
  document.getElementById('fFirstName').value       = d.first_name || '';
  document.getElementById('fUsername').value        = d.username || '';
  document.getElementById('fBio').value             = d.bio || '';
  if (d.has_photo) {{
    document.getElementById('photoPreview').innerHTML = '<span style="color:#22c55e;font-size:.75rem;text-align:center;line-height:1.3;">✓ Photo<br>enregistrée</span>';
    document.getElementById('photoName').textContent  = 'Photo déjà enregistrée — choisis-en une autre pour remplacer';
  }} else {{
    document.getElementById('photoPreview').innerHTML = '👤';
    document.getElementById('photoName').textContent  = '';
  }}
  document.getElementById('fPhoto').value           = '';
  document.getElementById('applyStatus').style.display = 'none';
  document.getElementById('btnApply').disabled      = false;
  document.getElementById('btnApply').textContent   = '💾 Enregistrer & Appliquer maintenant';
  document.getElementById('setupModal').classList.add('open');
}}

function closeModal() {{
  document.getElementById('setupModal').classList.remove('open');
}}

function previewPhoto(input) {{
  if (!input.files || !input.files[0]) return;
  const file = input.files[0];
  _photoName = file.name;
  const reader = new FileReader();
  reader.onload = (e) => {{
    _photoB64 = e.target.result.split(',')[1];
    const ext  = file.name.toLowerCase().endsWith('.png') ? 'png' : 'jpeg';
    document.getElementById('photoPreview').innerHTML =
      '<img src="data:image/'+ext+';base64,'+_photoB64+'" style="width:72px;height:72px;object-fit:cover;">';
    document.getElementById('photoName').textContent = file.name;
  }};
  reader.readAsDataURL(file);
}}

async function saveAndApply() {{
  if (!_pid) {{ alert('Aucun profil sélectionné'); return; }}
  const firstName = document.getElementById('fFirstName').value.trim();
  const username  = document.getElementById('fUsername').value.trim();
  const bio       = document.getElementById('fBio').value.trim();

  if (!firstName && !username && !bio && !_photoB64) {{
    alert('Remplis au moins un champ : prénom, @username, bio ou photo.');
    return;
  }}

  const btn    = document.getElementById('btnApply');
  const status = document.getElementById('applyStatus');
  btn.disabled    = true;
  btn.textContent = '⏳ Enregistrement...';
  status.style.display = 'none';

  try {{
    const payload = {{
      token:      'Compte.1',
      profile_id: _pid,
      first_name: firstName,
      username,
      bio,
      apply:      true,
    }};
    // N'envoie la photo que si une nouvelle a été sélectionnée (évite d'écraser l'ancienne)
    if (_photoB64) {{
      payload.photo_b64  = _photoB64;
      payload.photo_name = _photoName;
    }}

    const r = await fetch('/api/setup/upsert', {{
      method:  'POST',
      headers: {{'Content-Type': 'application/json'}},
      body:    JSON.stringify(payload),
    }});

    let d;
    try {{ d = await r.json(); }} catch(_) {{ d = {{}}; }}

    if (!r.ok || !d.ok) {{
      throw new Error(d.detail || ('HTTP ' + r.status));
    }}

    btn.textContent  = '✓ Sauvegardé !';
    status.className = 'apply-status ok';
    status.innerHTML = '✅ Config enregistrée.<br><span style="font-size:.7rem;color:#64748b;">Le daemon appliquera les changements dans ~30 s (LANCER_TOUT.vbs doit tourner).</span>';
    status.style.display = 'block';
    setTimeout(() => {{ closeModal(); location.reload(); }}, 3000);

  }} catch(e) {{
    btn.disabled    = false;
    btn.textContent = '💾 Enregistrer & Appliquer maintenant';
    status.className = 'apply-status err';
    status.innerHTML = '❌ Erreur : ' + e.message;
    status.style.display = 'block';
  }}
}}

async function deleteSetup(pid) {{
  if (!confirm('Supprimer la config de ' + pid + ' ?')) return;
  const r = await fetch('/api/setup/delete', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{token:'Compte.1', profile_id: pid}})
  }});
  const d = await r.json();
  if (d.ok) location.reload();
  else alert('Erreur : ' + JSON.stringify(d));
}}

// Fermer le modal en cliquant en dehors
document.getElementById('setupModal').addEventListener('click', function(e) {{
  if (e.target === this) closeModal();
}});
</script>

<!-- ══ OVERLAY UPLOAD EN MASSE ══ -->
<div class="mass-overlay" id="massOverlay">
  <div class="mass-panel">
    <!-- Header -->
    <div class="mass-hdr">
      <span class="mass-hdr-title">📤 Upload en masse</span>
      <button type="button" class="mass-hdr-close" onclick="closeMassUpload()">✕</button>
    </div>
    <!-- Steps -->
    <div class="mass-steps">
      <div class="mass-sdot active" id="msDot1">1</div>
      <div class="mass-sline" id="msLine1"></div>
      <div class="mass-sdot" id="msDot2">2</div>
      <div class="mass-sline" id="msLine2"></div>
      <div class="mass-sdot" id="msDot3">3</div>
    </div>
    <div class="mass-step-labels">
      <span class="mass-slbl">Sélection</span>
      <span class="mass-slbl" style="text-align:center">Photos</span>
      <span class="mass-slbl">Progression</span>
    </div>

    <!-- ── Step 1 : Sélectionner les profils ── -->
    <div class="mass-content" id="massStep1">
      <div class="mass-content-title">Choisis les profils à modifier</div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div class="mass-sel-info">
          <span id="msSelCount">0</span> profil(s) sélectionné(s) · max 25
        </div>
        <button type="button" class="mass-selall" onclick="massToggleAll()">
          Tout sélectionner
        </button>
      </div>
      <div class="mass-prof-grid" id="massProfGrid"></div>
      <button type="button" class="mass-btn mass-btn-primary" id="msBtnNext1"
        onclick="massGoStep2()" disabled>Suivant →</button>
      <button type="button" class="mass-btn mass-btn-sec" onclick="closeMassUpload()" style="margin-top:6px">Annuler</button>
    </div>

    <!-- ── Step 2 : Upload photos ── -->
    <div class="mass-content" id="massStep2" style="display:none">
      <div class="mass-content-title">Ajoute les photos (<span id="msNeedCount">0</span> nécessaires)</div>
      <div class="mass-file-zone">
        <label for="massFilesInput">
          <span class="mass-file-icon">🖼</span>
          <span class="mass-file-txt">Clique pour choisir les photos</span>
          <span class="mass-file-sub" id="msFileSubTxt">Sélectionne jusqu'à <span id="msMaxPhotos">0</span> images</span>
        </label>
        <input type="file" id="massFilesInput" multiple accept="image/*"
          style="position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;pointer-events:none;"
          onchange="handleMassFiles(this)">
      </div>
      <div class="mass-photo-grid" id="massPhotoGrid"></div>
      <div class="mass-warn" id="massWarn" style="display:none"></div>
      <button type="button" class="mass-btn mass-btn-primary" id="msBtnLaunch"
        onclick="massLaunch()" disabled>🚀 Lancer — 6 min/profil</button>
      <button type="button" class="mass-btn mass-btn-sec" onclick="massGoStep1()" style="margin-top:6px">← Retour</button>
    </div>

    <!-- ── Step 3 : Progression ── -->
    <div class="mass-content" id="massStep3" style="display:none">
      <div class="mass-global-status" id="massGlobalStatus">
        <div class="mgs-dot"></div>
        <span class="mgs-txt" id="massGlobalTxt">Initialisation...</span>
      </div>
      <div id="massProgressList"></div>
      <!-- Bouton stop circulaire -->
      <div style="display:flex;justify-content:center;margin-top:24px;" id="massStopZone">
        <button type="button" class="mass-stop-btn" id="massStopBtn" onclick="batchStop()">
          <svg viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg" class="mass-stop-ring">
            <circle cx="18" cy="18" r="16" stroke="currentColor" stroke-width="2.5" stroke-dasharray="100" stroke-dashoffset="0" class="mass-stop-arc"/>
          </svg>
          <span class="mass-stop-icon">⏹</span>
          <span class="mass-stop-lbl" id="massStopLbl">Arrêter</span>
        </button>
      </div>
      <!-- Bouton forcer fermeture — visible si batch bloqué -->
      <div style="display:flex;justify-content:center;margin-top:12px;" id="massForceZone">
        <button type="button" id="massForceBtn" onclick="batchForceReset()"
          style="background:transparent;border:1px solid #333;border-radius:8px;color:#555;
                 font-size:.75rem;padding:7px 18px;cursor:pointer;transition:all .15s;"
          onmouseover="this.style.borderColor='#dc2626';this.style.color='#dc2626'"
          onmouseout="this.style.borderColor='#333';this.style.color='#555'">
          ✕ Forcer la fermeture
        </button>
      </div>
    </div>
  </div>
</div>

<script>
/* ════════════════════════════════════════
   UPLOAD EN MASSE — logique
   ════════════════════════════════════════ */
const MASS_PROFILES = {profiles_for_js};
let _mSel     = [];   // IDs sélectionnés (dans l'ordre)
let _mPhotos  = [];   // {{name, b64}} dans l'ordre
let _mRunning = false;
let _mTimers  = [];

// ── Tri par ordre AdsPower (serial_number) ────────────────
// Appelé au chargement : tente de récupérer l'ordre AdsPower en local.
// Si AdsPower est inaccessible (ex : Render), garde l'ordre Supabase.
async function syncAdsPowerOrder() {{
  const ADS_KEY = '942d5c4fa00deedac520c3310912ee6100795935b355b33b';
  try {{
    const ctrl = new AbortController();
    const tid  = setTimeout(() => ctrl.abort(), 3000);
    const resp = await fetch(
      `http://local.adspower.net:50325/api/v1/user/list?page=1&page_size=100&api_key=${{ADS_KEY}}`,
      {{ signal: ctrl.signal }}
    );
    clearTimeout(tid);
    const data = await resp.json();
    if (data.code !== 0 || !data.data?.list) return;

    // Map user_id → serial_number
    const order = {{}};
    data.data.list.forEach(p => {{ order[p.user_id] = parseInt(p.serial_number, 10) || 9999; }});

    const grid = document.querySelector('.profiles-quick-list');
    if (!grid) return;
    const massCard  = grid.querySelector('.profile-mass-card');
    const pCards    = Array.from(grid.querySelectorAll('.profile-quick-card'));

    pCards.sort((a, b) => (order[a.dataset.pid] || 9999) - (order[b.dataset.pid] || 9999));

    pCards.forEach((card, idx) => {{
      const num = order[card.dataset.pid];
      const badge = card.querySelector('.pqc-num');
      if (badge) badge.textContent = '#' + (num || (idx + 1));
      grid.insertBefore(card, massCard || null);
    }});
    console.log('[Setup] ✓ Profils triés par numéro AdsPower');
  }} catch(e) {{
    console.log('[Setup] AdsPower inaccessible — ordre Supabase conservé');
  }}
}}
// Lancer après chargement DOM
setTimeout(syncAdsPowerOrder, 300);

// ── Arrêt du batch ────────────────────────────────────────
async function batchStop() {{
  const btn  = document.getElementById('massStopBtn');
  const lbl  = document.getElementById('massStopLbl');
  if (btn) {{ btn.disabled = true; }}
  if (lbl) lbl.textContent = 'Arrêt...';
  try {{
    const r = await fetch('/api/setup/batch-stop', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify({{token: '{SECRET_TOKEN}'}})
    }});
    const d = await r.json();
    if (d.ok) {{
      if (lbl) lbl.textContent = 'Arrêté';
      const arc = document.querySelector('.mass-stop-arc');
      if (arc) arc.style.animation = 'none';
    }} else {{
      if (btn) btn.disabled = false;
      if (lbl) lbl.textContent = 'Arrêter';
    }}
  }} catch(e) {{
    if (btn) btn.disabled = false;
    if (lbl) lbl.textContent = 'Arrêter';
  }}
}}

async function batchForceReset() {{
  if (!confirm('Forcer la fermeture va réinitialiser le batch côté serveur.\nContinuer ?')) return;
  try {{
    await fetch('/api/setup/batch-reset', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify({{token: '{SECRET_TOKEN}'}})
    }});
  }} catch(e) {{ /* ignore */ }}
  // Stopper le polling
  if (_pollInterval) {{ clearInterval(_pollInterval); _pollInterval = null; }}
  _mRunning = false;
  // Fermer l'overlay
  document.getElementById('massOverlay').classList.remove('open');
  _mSel = []; _mPhotos = [];
  // Recharger la page pour état propre
  location.reload();
}}

function openMassUpload() {{
  document.getElementById('massOverlay').classList.add('open');
  massGoStep1(true);
}}
function closeMassUpload() {{
  if (_mRunning) {{
    if (!confirm('Un batch est en cours. Fermer quand même ?')) return;
    _mTimers.forEach(clearTimeout);
    _mRunning = false;
  }}
  document.getElementById('massOverlay').classList.remove('open');
  _mSel = []; _mPhotos = [];
}}

/* ─── Step 1 ─── */
function massGoStep1(init) {{
  _setStep(1);
  const grid = document.getElementById('massProfGrid');
  if (init || !grid.children.length) {{
    grid.innerHTML = '';
    MASS_PROFILES.forEach(p => {{
      const div = document.createElement('div');
      div.className = 'mass-pcard';
      div.dataset.pid = p.id;
      const avatarInner = p.has_photo
        ? `<img src="" data-pid="${{p.id}}" class="mass-lazy-avatar">`
        : '👤';
      div.innerHTML = `
        <div class="mass-pcheck" id="mpc-${{p.id}}"></div>
        <div class="mpcard-avatar">${{avatarInner}}</div>
        <div class="mpcard-num">Profil ${{p.num}}</div>
        <div class="mpcard-un">${{p.username ? '@'+p.username : '—'}}</div>`;
      div.onclick = () => massToggle(p.id, div);
      grid.appendChild(div);
    }});
  }}
  _mSel = [];
  grid.querySelectorAll('.mass-pcard').forEach(c => c.classList.remove('sel'));
  grid.querySelectorAll('.mass-pcheck').forEach(c => c.textContent = '');
  _updateSelCount();
}}

function massToggle(pid, card) {{
  const idx = _mSel.indexOf(pid);
  if (idx >= 0) {{
    _mSel.splice(idx, 1);
    card.classList.remove('sel');
    card.querySelector('.mass-pcheck').textContent = '';
  }} else {{
    if (_mSel.length >= 25) {{ alert('Maximum 25 profils.'); return; }}
    _mSel.push(pid);
    card.classList.add('sel');
    card.querySelector('.mass-pcheck').textContent = '✓';
  }}
  _updateSelCount();
}}

let _allSelected = false;
function massToggleAll() {{
  const cards = document.querySelectorAll('.mass-pcard');
  _allSelected = !_allSelected;
  _mSel = [];
  cards.forEach(c => {{
    const pid = c.dataset.pid;
    if (_allSelected && _mSel.length < 25) {{
      c.classList.add('sel');
      c.querySelector('.mass-pcheck').textContent = '✓';
      _mSel.push(pid);
    }} else {{
      c.classList.remove('sel');
      c.querySelector('.mass-pcheck').textContent = '';
    }}
  }});
  document.querySelector('.mass-selall').textContent = _allSelected ? 'Tout désélectionner' : 'Tout sélectionner';
  _updateSelCount();
}}

function _updateSelCount() {{
  document.getElementById('msSelCount').textContent = _mSel.length;
  document.getElementById('msBtnNext1').disabled = (_mSel.length === 0);
}}

function massGoStep2() {{
  if (!_mSel.length) return;
  _setStep(2);
  document.getElementById('msNeedCount').textContent = _mSel.length;
  document.getElementById('msMaxPhotos').textContent = _mSel.length;
  _mPhotos = [];
  document.getElementById('massPhotoGrid').innerHTML = '';
  document.getElementById('massFilesInput').value = '';
  document.getElementById('massWarn').style.display = 'none';
  document.getElementById('msBtnLaunch').disabled = true;
}}

/* ─── Step 2 ─── */
function handleMassFiles(input) {{
  const files = Array.from(input.files).slice(0, _mSel.length);
  _mPhotos = [];
  const grid = document.getElementById('massPhotoGrid');
  grid.innerHTML = '';
  const warn = document.getElementById('massWarn');

  if (files.length !== _mSel.length) {{
    warn.style.display = 'block';
    warn.textContent = `⚠ Tu as sélectionné ${{files.length}} photo(s) pour ${{_mSel.length}} profil(s). Il en faut exactement ${{_mSel.length}}.`;
    document.getElementById('msBtnLaunch').disabled = true;
  }} else {{
    warn.style.display = 'none';
  }}

  let loaded = 0;
  files.forEach((f, i) => {{
    const reader = new FileReader();
    reader.onload = e => {{
      const b64 = e.target.result.split(',')[1];
      _mPhotos[i] = {{name: f.name, b64}};
      loaded++;
      // Aperçu
      const item = document.createElement('div');
      item.className = 'mass-photo-item' + (i >= _mSel.length ? ' unassigned' : '');
      item.innerHTML = `<img src="${{e.target.result}}"><div class="mass-photo-label">P${{i+1}}</div>`;
      grid.appendChild(item);
      if (loaded === files.length && files.length === _mSel.length) {{
        document.getElementById('msBtnLaunch').disabled = false;
      }}
    }};
    reader.readAsDataURL(f);
  }});
}}

/* ─── Step 3 – lancement (envoie tout au serveur, poll état) ─── */
async function massLaunch() {{
  if (!_mSel.length || _mPhotos.length !== _mSel.length) return;
  const btn = document.getElementById('msBtnLaunch');
  btn.disabled = true;
  btn.textContent = '⏳ Envoi au serveur...';

  // Construire la liste items
  const items = _mSel.map((pid, i) => ({{
    profile_id: pid,
    photo_b64:  _mPhotos[i].b64,
    photo_name: _mPhotos[i].name,
  }}));

  try {{
    const r = await fetch('/api/setup/batch-start', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{token: 'Compte.1', items}})
    }});
    const d = await r.json().catch(() => ({{}}));
    if (!r.ok) throw new Error(d.detail || 'HTTP ' + r.status);
    // Serveur a pris en charge → afficher step 3 et démarrer polling
    _setStep(3);
    _buildProgressList(_mSel);
    _startPolling();
  }} catch(e) {{
    btn.disabled = false;
    btn.textContent = '🚀 Lancer — 6 min/profil';
    alert('Erreur : ' + e.message);
  }}
}}

/* ─── Polling serveur (fonctionne après navigation) ─── */
let _pollInterval = null;

function _startPolling() {{
  if (_pollInterval) clearInterval(_pollInterval);
  _pollInterval = setInterval(_pollBatch, 2000);
  _pollBatch(); // premier appel immédiat
}}

async function _pollBatch() {{
  try {{
    const r = await fetch('/api/setup/batch-status');
    if (!r.ok) return;
    const s = await r.json();
    _applyBatchState(s);
    // Arrêter le polling si terminé
    if (!s.running && (s.finished || !s.profiles || !s.profiles.length)) {{
      clearInterval(_pollInterval);
      _pollInterval = null;
    }}
  }} catch(e) {{ /* réseau temporairement indisponible */ }}
}}

function _applyBatchState(s) {{
  const overlay = document.getElementById('massOverlay');
  // Si le serveur répond "aucun batch" (après redémarrage), fermer la modal automatiquement
  if (!s.profiles || !s.profiles.length) {{
    if (overlay && overlay.classList.contains('open') && !_mRunning) {{
      overlay.classList.remove('open');
      if (_pollInterval) {{ clearInterval(_pollInterval); _pollInterval = null; }}
    }}
    return;
  }}

  // Auto-ouvrir le panel si batch en cours et overlay fermé
  if (s.running && overlay && !overlay.classList.contains('open')) {{
    overlay.classList.add('open');
    _setStep(3);
    _buildProgressList(s.profiles.map(p => p.id));
  }}

  const gTxt = document.getElementById('massGlobalTxt');
  const gDot = document.querySelector('.mgs-dot');

  // Bouton stop : visible si en cours, caché si terminé/arrêté
  const stopZone  = document.getElementById('massStopZone');
  const stopBtn   = document.getElementById('massStopBtn');
  const stopLbl   = document.getElementById('massStopLbl');
  const forceZone = document.getElementById('massForceZone');
  if (stopZone) stopZone.style.display = s.running ? 'flex' : 'none';
  // Bouton "Forcer la fermeture" : toujours visible dans step 3
  if (forceZone) forceZone.style.display = 'flex';
  // Si stop_requested, désactiver le bouton stop et montrer "Arrêt..."
  if (s.stop_requested && stopBtn && !stopBtn.disabled) {{
    stopBtn.disabled = true;
    if (stopLbl) stopLbl.textContent = 'Arrêt...';
    const arc = document.querySelector('.mass-stop-arc');
    if (arc) arc.style.animation = 'none';
  }}

  if (s.running) {{
    const done = s.profiles.filter(p => p.status === 'done' || p.status === 'error').length;
    gTxt.textContent = s.stop_requested
      ? `⏳ Arrêt en cours · ${{done}}/${{s.total}} traité(s)`
      : `Batch en cours · ${{done}}/${{s.total}} traité(s)`;
    if (gDot) {{ gDot.style.background='#dc2626'; gDot.style.animation=''; }}
  }} else if (s.finished) {{
    if (s.stopped) {{
      const done = s.profiles.filter(p => p.status === 'done' || p.status === 'error').length;
      gTxt.textContent = `⏹ Arrêté · ${{done}}/${{s.total}} traité(s)`;
      if (gDot) {{ gDot.style.background='#f59e0b'; gDot.style.animation='none'; }}
    }} else {{
      gTxt.textContent = `✅ Terminé · ${{s.total}} profil(s) traité(s)`;
      if (gDot) {{ gDot.style.background='#22c55e'; gDot.style.animation='none'; }}
    }}
  }}

  s.profiles.forEach((p, i) => {{
    const numEl = document.getElementById('mpi-num-' + p.id);
    const stEl  = document.getElementById('mpi-st-'  + p.id);
    const cdEl  = document.getElementById('mpi-cd-'  + p.id);
    if (!numEl) return; // ligne pas encore dans le DOM

    if (p.status === 'running') {{
      numEl.className = 'mpi-num running';
      stEl.textContent = 'Enregistrement en cours...';
      stEl.className = 'mpi-status running';
      // Countdown : calcule à partir de next_at du serveur
      if (s.next_at && cdEl) {{
        const rem = Math.max(0, Math.round((new Date(s.next_at) - Date.now()) / 1000));
        const m = String(Math.floor(rem/60)).padStart(2,'0');
        const sc = String(rem%60).padStart(2,'0');
        cdEl.textContent = '';
      }}
    }} else if (p.status === 'done') {{
      numEl.className = 'mpi-num done';
      stEl.textContent = '✓ Photo enregistrée';
      stEl.className = 'mpi-status done';
      if (cdEl) cdEl.textContent = '';
      // Afficher countdown sur le profil EN ATTENTE suivant (i+1)
      if (s.running && s.next_at && i === s.current_idx) {{
        const nextP = s.profiles[i + 1];
        if (nextP) {{
          const cdNext = document.getElementById('mpi-cd-' + nextP.id);
          const rem = Math.max(0, Math.round((new Date(s.next_at) - Date.now()) / 1000));
          if (cdNext && rem > 0) {{
            const m = String(Math.floor(rem/60)).padStart(2,'0');
            const sc = String(rem%60).padStart(2,'0');
            cdNext.textContent = m+':'+sc;
          }}
        }}
      }}
    }} else if (p.status === 'error') {{
      numEl.className = 'mpi-num';
      numEl.style.color = '#f87171';
      stEl.textContent = '✗ ' + (p.error || 'Erreur');
      stEl.className = 'mpi-status';
      if (cdEl) cdEl.textContent = '';
    }} else if (p.status === 'skipped') {{
      numEl.className = 'mpi-num';
      numEl.style.color = '#444';
      stEl.textContent = '— Annulé';
      stEl.className = 'mpi-status';
      stEl.style.color = '#333';
      if (cdEl) cdEl.textContent = '';
    }} else {{
      // pending
      numEl.className = 'mpi-num';
      stEl.textContent = 'En attente';
      stEl.className = 'mpi-status';
    }}
  }});
}}

function _buildProgressList(pids) {{
  const list = document.getElementById('massProgressList');
  if (!list) return;
  list.innerHTML = '';
  pids.forEach((pid, i) => {{
    const row = document.createElement('div');
    row.className = 'mass-progress-item';
    row.id = `mpi-${{pid}}`;
    row.innerHTML = `
      <div class="mpi-num" id="mpi-num-${{pid}}">${{i+1}}</div>
      <div class="mpi-info">
        <div class="mpi-id">${{pid}}</div>
        <div class="mpi-status" id="mpi-st-${{pid}}">En attente</div>
      </div>
      <div class="mpi-countdown" id="mpi-cd-${{pid}}"></div>`;
    list.appendChild(row);
  }});
}}

/* ─── Vérif au chargement de la page : batch en cours ? ─── */
(async () => {{
  try {{
    const r = await fetch('/api/setup/batch-status');
    if (!r.ok) return;
    const s = await r.json();
    if (s.running) {{
      // Batch en cours → ouvrir panel et reprendre polling
      document.getElementById('massOverlay').classList.add('open');
      _setStep(3);
      _buildProgressList(s.profiles.map(p => p.id));
      _applyBatchState(s);
      _startPolling();
    }}
  }} catch(e) {{}}
}})();

/* ─── Helpers step ─── */
function _setStep(n) {{
  ['massStep1','massStep2','massStep3'].forEach((id,i) => {{
    document.getElementById(id).style.display = (i+1===n) ? '' : 'none';
  }});
  [1,2,3].forEach(i => {{
    const dot = document.getElementById('msDot'+i);
    dot.className = 'mass-sdot' + (i<n?' done':i===n?' active':'');
  }});
  [1,2].forEach(i => {{
    const line = document.getElementById('msLine'+i);
    line.className = 'mass-sline' + (i<n?' done':'');
  }});
}}

// Fermer en cliquant dehors
document.getElementById('massOverlay').addEventListener('click', function(e) {{
  if (e.target === this) closeMassUpload();
}});
</script>
</div></div>{SIDEBAR_JS}
</body></html>"""
    return html
