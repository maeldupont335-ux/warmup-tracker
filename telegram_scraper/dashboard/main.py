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

# Flag en mémoire — trigger warm-up sans table Supabase
_warmup_trigger: bool = False

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
        ("warmup",  "/",       "Warm-Up"),
        ("massdm",  "/massdm", "Mass DM"),
        ("scraper", "/scraper","Scraper"),
        ("setup",   "/setup",  "⚙ Setup"),
    ]
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
    if not name or not content:
        raise HTTPException(status_code=400, detail="Nom et contenu requis")
    try:
        supabase.table("dm_templates").insert({
            "name": name, "content": content, "content2": content2,
            "active": True, "sends": 0, "replies": 0
        }).execute()
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
        supabase.table("profile_setup").upsert({
            "profile_id": pid,
            "phone":      body.get("phone", "").strip(),
            "first_name": body.get("first_name", "").strip(),
            "username":   body.get("username", "").strip().lstrip("@"),
            "bio":        body.get("bio", "").strip(),
            "photo_b64":  body.get("photo_b64", ""),
            "photo_name": body.get("photo_name", ""),
            "updated_at": now_paris(),
        }, on_conflict="profile_id").execute()

        # Si apply=True → écrit un trigger dans channels pour le daemon local
        if body.get("apply"):
            try:
                trigger_url = f"__profile_apply__{pid}__"
                supabase.table("channels").upsert({
                    "url":          trigger_url,
                    "status":       "triggered",
                    "members_count": 0,
                }, on_conflict="url").execute()
            except Exception:
                pass  # le trigger est optionnel, pas critique

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
          <td class="center">{ddm_btn}</td>
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
  <div style="margin-bottom:20px">
    <button id="btn-launch" onclick="launchWarmup()" style="background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;border:none;border-radius:10px;padding:12px 28px;font-size:1rem;font-weight:700;cursor:pointer;box-shadow:0 0 18px rgba(34,197,94,.35);transition:all .2s">
      ▶ Lancer le Warm-Up maintenant
    </button>
    <span id="launch-msg" style="display:none;margin-left:14px;color:#22c55e;font-weight:600">✓ Signal envoyé — démarrage dans ~30s</span>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-value">{done_today}<span style="color:#334155;font-size:1.2rem">/{n}</span></div><div class="stat-label">Faits aujourd'hui</div></div>
    <div class="stat"><div class="stat-value">{total_dms}</div><div class="stat-label">DMs envoyes</div></div>
    <div class="stat"><div class="stat-value">{total_posts}</div><div class="stat-label">Posts canaux</div></div>
    <div class="stat"><div class="stat-value">{total_groups}</div><div class="stat-label">Groupes rejoints</div></div>
    <div class="stat"><div class="stat-value">{finished}</div><div class="stat-label">Chauffes terminees</div></div>
  </div>
  <div class="card"><table><thead><tr>
    <th class="th-l" style="width:36px">#</th>
    <th class="th-l">ID Profil</th>
    <th class="th-l" style="min-width:180px">Progression</th>
    <th>Jour</th>
    <th>DMs</th>
    <th>Posts</th>
    <th>Groupes</th>
    <th>Rép.</th>
    <th>Statut</th>
    <th>Mode</th>
    <th>Dernière session</th>
    <th style="width:40px"></th>
  </tr></thead><tbody>{rows}</tbody></table></div>
  <p class="refresh">Mis a jour par warmup_v2.py apres chaque profil</p>
  {add_js('/api/profile/add', 'inp', 'Profil ajoute !')}
<script>
async function launchWarmup() {{
  const btn = document.getElementById('btn-launch');
  btn.disabled = true;
  btn.textContent = '⏳ Envoi du signal...';
  // Ecrit DIRECTEMENT dans Supabase — bypasse Render (100% fiable)
  const SUPA_URL = 'https://pirlgavzihmnwmqlyeir.supabase.co';
  const SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBpcmxnYXZ6aWhtbndtcWx5ZWlyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3MzQxMTAsImV4cCI6MjA5NTMxMDExMH0.0QdskD9IBsx1rUZ_7Sljb8DshovkQMJIhmnAM-Zc6Ps';
  try {{
    const r = await fetch(`${{SUPA_URL}}/rest/v1/channels`, {{
      method: 'POST',
      headers: {{
        'apikey': SUPA_KEY,
        'Authorization': `Bearer ${{SUPA_KEY}}`,
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates,return=minimal'
      }},
      body: JSON.stringify({{url:'__warmup_trigger__', status:'triggered', members_count:0}})
    }});
    if (r.ok || r.status === 201 || r.status === 200) {{
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

    # Cards
    tpl_cards_html = ""
    for idx, t in enumerate(templates):
        tid      = t["id"]
        sends    = t.get("sends",    0)
        replies  = t.get("replies",  0)
        active   = t.get("active",   True)
        content2 = (t.get("content2") or "").strip()
        rate     = round(replies / sends * 100, 1) if sends > 0 else 0

        preview = t["content"][:110].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        if len(t["content"]) > 110:
            preview += "…"

        color    = COLORS[idx % len(COLORS)]
        card_cls = "tpl-card" + ("" if active else " inactive")
        tog_lbl  = "● Actif"  if active else "○ Inactif"
        tog_cls  = "btn-tpl btn-tpl-on" if active else "btn-tpl btn-tpl-off"
        name_esc = t["name"].replace("&","&amp;").replace("<","&lt;")
        best_badge = '<span class="winner-badge">🏆 Meilleur</span>' if tid == best_id else ""
        msg2_badge = '<span class="msg2-badge">✉×2</span>' if content2 else ""

        # Aperçu du 2ème message
        preview2_html = ""
        if content2:
            prev2 = content2[:90].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            if len(content2) > 90:
                prev2 += "…"
            preview2_html = f'<pre class="tpl-preview tpl-preview2">{prev2}</pre>'

        tpl_cards_html += f"""
<div class="{card_cls}">
  <div class="tpl-name">
    <span class="tpl-num" style="background:{color}22;color:{color};border:1px solid {color}55;">T{idx+1}</span>
    {name_esc}{best_badge}{msg2_badge}
  </div>
  <pre class="tpl-preview">{preview}</pre>
  {preview2_html}
  <div class="tpl-stats">
    <div class="tstat"><div class="tstat-val blue">{sends}</div><div class="tstat-lab">Envoyés</div></div>
    <div class="tstat"><div class="tstat-val green">{replies}</div><div class="tstat-lab">Réponses</div></div>
    <div class="tstat"><div class="tstat-val gold">{rate}%</div><div class="tstat-lab">Taux</div></div>
  </div>
  <div class="tpl-actions">
    <button class="{tog_cls}" onclick="toggleTpl({tid},{str(not active).lower()})">{tog_lbl}</button>
    <button class="btn-tpl" style="background:#1e3a5f;color:#93c5fd;flex:1;" onclick="replyTpl({tid})">+1 Réponse</button>
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

        rows += f"""<tr {row_style}>
          <td class="num">{i}</td><td class="pid">{pid}</td>
          <td class="center">{sent}</td><td class="center">{replied}</td>
          <td><div class="progress-wrap"><div class="progress-bar" style="width:{pct_bar}%;background:#22c55e"></div></div>
          <span class="day-label">{taux}% de réponse</span></td>
          <td class="center">{p['conversions']}</td><td>{sb}</td>
          <td class="center">{mode_badge}</td>
          <td class="last" style="white-space:nowrap;">
            {p['last_run'] or '—'}&nbsp;
            <button class="btn-bio" style="border-color:{bio_color};color:{bio_color};"
              onclick="openBioModal('{pid}','{bio_saved}')">{bio_label}</button>
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mass DM — A/B Testing</title><style>{BASE_CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<meta http-equiv="refresh" content="60"></head><body>
  <div class="neon-logo">
    <span class="neon-agency">Agency</span>
    <div class="neon-box"><span class="neon-text">OF4MYM</span></div>
  </div>
  <h1>Mass DM — A/B Testing</h1>
  <p class="subtitle">Analyse et suivi de tes messages DM · {n} profils actifs</p>
  {nav_html("massdm")}

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
        <textarea id="tcontent" class="add-textarea" placeholder="1er message...&#10;Utilise {{prenom}} pour personnaliser.&#10;Ctrl+Entrée pour ajouter."></textarea>
        <button class="btn-add-msg2" onclick="toggleMsg2()" id="btnMsg2">➕ Ajouter un 2ème message (optionnel — envoyé 5-18s après)</button>
        <textarea id="tcontent2" class="add-textarea" placeholder="2ème message (optionnel)...&#10;Sera envoyé 5 à 18 secondes après le premier.&#10;Utilise aussi {{prenom}}." style="display:none;border-color:#1e3a5f;"></textarea>
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
    <th>Dernière session</th>
  </tr></thead><tbody>{rows}</tbody></table></div>

  <!-- ══ ACTIVITÉ QUOTIDIENNE ══ -->
  <p class="section-title">Activité quotidienne</p>
  {daily_chart}

  <p class="refresh">Mis à jour automatiquement · rechargement dans 60s</p>

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
function toggleMsg2() {{
  const ta  = document.getElementById('tcontent2');
  const btn = document.getElementById('btnMsg2');
  if (ta.style.display === 'none') {{
    ta.style.display = 'block';
    btn.textContent = '✕ Supprimer le 2ème message';
    btn.style.borderColor = '#ef4444'; btn.style.color = '#fca5a5';
  }} else {{
    ta.style.display = 'none'; ta.value = '';
    btn.textContent = '➕ Ajouter un 2ème message (optionnel — envoyé 5-18s après)';
    btn.style.borderColor = ''; btn.style.color = '';
  }}
}}
async function addTpl() {{
  const name     = document.getElementById('tname').value.trim();
  const content  = document.getElementById('tcontent').value.trim();
  const content2 = document.getElementById('tcontent2').value.trim();
  if (!name || !content) {{ alert('Nom et contenu requis.'); return; }}
  const d = await _post('/api/dm_template/add', {{name, content, content2}});
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
  ['tcontent','tcontent2'].forEach(id => {{
    const ta = document.getElementById(id);
    if (ta) ta.addEventListener('keydown', e => {{ if (e.key==='Enter' && e.ctrlKey) addTpl(); }});
  }});
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
<title>Scraper — Canaux</title><style>{BASE_CSS}
.badge.todo{{background:rgba(251,191,36,.15);color:#fbbf24;border:1px solid rgba(251,191,36,.3)}}
.btn-scrape{{background:linear-gradient(135deg,#0ea5e9,#6366f1);color:#fff;border:none;border-radius:6px;padding:5px 11px;font-size:.78rem;cursor:pointer;font-weight:600;transition:opacity .15s;white-space:nowrap}}
.btn-scrape:hover{{opacity:.82}}
.btn-scrape.todo,.btn-scrape:disabled{{background:#334155;color:#64748b;cursor:not-allowed;opacity:.7}}
.actions-cell{{display:flex;gap:6px;justify-content:center;align-items:center}}
.stat-total{{background:linear-gradient(135deg,rgba(14,165,233,.12),rgba(99,102,241,.12));border:1px solid rgba(99,102,241,.3)}}
.stat-total .stat-value{{color:#818cf8}}
</style>
<meta http-equiv="refresh" content="30"></head><body>
  <div class="neon-logo">
    <span class="neon-agency">Agency</span>
    <div class="neon-box"><span class="neon-text">OF4MYM</span></div>
  </div>
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
    <div class="stat"><div class="stat-value" style="color:#fbbf24">{a_scraper}</div><div class="stat-label">En attente scraping</div></div>
    <div class="stat"><div class="stat-value">{en_attente}</div><div class="stat-label">Pas encore marques</div></div>
    <div class="stat stat-total"><div class="stat-value">{total_members}</div><div class="stat-label">Membres collectes au total</div></div>
  </div>

  <div class="card"><table><thead><tr>
    <th class="th-l" style="width:36px">#</th>
    <th class="th-l">Lien du canal</th>
    <th>Membres actifs</th>
    <th>Statut</th>
    <th>Dernier scraping</th>
    <th style="width:160px">Actions</th>
  </tr></thead><tbody>{rows if rows else '<tr><td colspan="6" style="text-align:center;color:#64748b;padding:30px">Aucun canal — ajoutes-en un ci-dessus</td></tr>'}</tbody></table></div>

  <div class="card" style="padding:20px;background:#0f172a;border-color:#1e3a5f">
    <p style="color:#93c5fd;font-size:.875rem;">
      <strong>Comment ca marche :</strong><br><br>
      1. Ajoute ici les liens des canaux Telegram a scrapper<br>
      2. Clique <strong>🔍 Scraper</strong> sur les canaux a scrapper (statut devient <em>A scraper ⏳</em>)<br>
      3. Lance <code style="background:#1e293b;padding:2px 6px;border-radius:4px">python scraper.py</code> sur ton PC — il scrappe uniquement les canaux marques<br>
      4. Seuls les membres actifs (&le;30 jours) avec @username sont gardes → <code style="background:#1e293b;padding:2px 6px;border-radius:4px">output/membres.csv</code><br>
      5. Puis <code style="background:#1e293b;padding:2px 6px;border-radius:4px">dm_sender.py</code> (ou warmup_v2.py en mode Direct DM) envoie les DMs
    </p>
  </div>

  <p class="refresh">Les statuts se mettent a jour pendant le scraping (refresh auto 30s)</p>
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
            photo_html = '<div class="photo-placeholder" style="width:46px;height:46px;border-radius:50%;background:#1e293b;display:flex;align-items:center;justify-content:center;font-size:1.3rem;">👤</div>'

        # Données JS (encodées pour attributs HTML)
        bio_esc  = (c.get("bio","") or "").replace('"','&quot;').replace("'","&#39;")
        un_esc   = uname.replace('"','&quot;')

        rows += f"""<tr>
          <td style="padding:10px 16px;">{photo_html}</td>
          <td class="pid">{pid}</td>
          <td style="font-family:monospace;font-size:.82rem;color:#22c55e;">{"@"+uname if uname else "<span style='color:#334155'>—</span>"}</td>
          <td style="font-size:.75rem;color:#64748b;max-width:220px;">{bio}</td>
          <td style="font-size:.7rem;color:#334155;">{upd[:16]}</td>
          <td style="white-space:nowrap;text-align:center;">
            <button class="btn-edit-setup" onclick="openEditModal('{pid}','{un_esc}','{bio_esc}',{'\''+pb64[:30]+'…\'' if pb64 else 'null'})">✏ Modifier</button>
            &nbsp;
            <button class="btn-del" onclick="deleteSetup('{pid}')" title="Supprimer">✕</button>
          </td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:#475569;padding:36px;">Aucun profil configuré — clique sur un profil ci-dessous pour démarrer</td></tr>'

    # Options profils
    opts_all = "".join(f'<option value="{p}">{p}</option>' for p in profile_ids)
    non_config = [p for p in profile_ids if p not in config_map]

    html = f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Setup Profils</title>
<style>{BASE_CSS}
/* ── Setup spécifique ── */
.setup-modal-overlay {{
  display:none; position:fixed; inset:0; background:rgba(0,0,0,.7);
  z-index:900; align-items:center; justify-content:center; padding:20px;
}}
.setup-modal-overlay.open {{ display:flex; }}
.setup-modal {{
  background:#1e293b; border:1px solid #334155; border-radius:20px;
  padding:28px 32px; width:100%; max-width:520px;
  box-shadow:0 24px 64px rgba(0,0,0,.6);
}}
.setup-modal h2 {{ font-size:1.1rem; color:#f8fafc; margin-bottom:20px; }}
.setup-field {{ margin-bottom:16px; }}
.setup-field label {{ display:block; font-size:.72rem; font-weight:700;
  color:#64748b; text-transform:uppercase; letter-spacing:.06em; margin-bottom:6px; }}
.setup-field input, .setup-field textarea {{
  width:100%; background:#0f172a; border:1px solid #334155; border-radius:8px;
  padding:10px 13px; color:#e2e8f0; font-size:.875rem; font-family:inherit;
  resize:vertical;
}}
.setup-field input:focus, .setup-field textarea:focus {{
  outline:none; border-color:#22c55e;
}}
.setup-field textarea {{ min-height:80px; }}
.photo-upload-area {{
  display:flex; align-items:center; gap:16px; margin-top:4px;
}}
.photo-upload-preview {{
  width:72px; height:72px; border-radius:50%; overflow:hidden;
  background:#0f172a; border:2px solid #334155; flex-shrink:0;
  display:flex; align-items:center; justify-content:center; font-size:2rem;
}}
.photo-upload-preview img {{ width:100%; height:100%; object-fit:cover; }}
.btn-choose-photo {{
  background:#1e3a5f; border:1px solid #1e40af; color:#93c5fd;
  border-radius:8px; padding:9px 18px; font-size:.78rem; font-weight:700;
  cursor:pointer; display:block; margin-bottom:6px;
}}
.btn-choose-photo:hover {{ background:#1e40af; }}
.btn-apply {{
  width:100%; background:linear-gradient(135deg,#22c55e,#16a34a);
  border:none; border-radius:10px; padding:13px;
  color:#fff; font-size:.95rem; font-weight:800; cursor:pointer;
  box-shadow:0 0 18px rgba(34,197,94,.3); margin-top:6px; transition:all .2s;
}}
.btn-apply:hover {{ box-shadow:0 0 26px rgba(34,197,94,.5); }}
.btn-apply:disabled {{ opacity:.5; cursor:not-allowed; box-shadow:none; }}
.btn-cancel-modal {{
  width:100%; background:#1e293b; border:1px solid #334155;
  border-radius:10px; padding:10px; color:#64748b; font-size:.85rem;
  font-weight:600; cursor:pointer; margin-top:8px;
}}
.profiles-quick-list {{
  display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
  gap:12px; margin-bottom:28px;
}}
.profile-quick-card {{
  background:#1e293b; border:1px solid #334155; border-radius:12px;
  padding:16px; text-align:center; cursor:pointer; transition:all .15s;
}}
.profile-quick-card:hover {{ border-color:#22c55e; background:#0f172a; }}
.profile-quick-card .pqc-photo {{
  width:52px; height:52px; border-radius:50%; overflow:hidden; margin:0 auto 10px;
  background:#0f172a; border:2px solid #334155;
  display:flex; align-items:center; justify-content:center; font-size:1.5rem;
}}
.profile-quick-card .pqc-photo img {{ width:100%; height:100%; object-fit:cover; }}
.profile-quick-card .pqc-pid {{ font-size:.75rem; font-family:monospace; color:#94a3b8; margin-bottom:4px; }}
.profile-quick-card .pqc-un {{ font-size:.72rem; color:#22c55e; }}
.profile-quick-card .pqc-status {{ font-size:.65rem; color:#334155; margin-top:6px; }}
.profile-quick-card.configured {{ border-color:#1e40af; }}
.profile-quick-card.configured .pqc-status {{ color:#3b82f6; }}
.apply-status {{
  font-size:.78rem; margin-top:12px; padding:10px 14px; border-radius:8px;
  display:none;
}}
.apply-status.ok {{ background:#052e16; border:1px solid #166534; color:#86efac; }}
.apply-status.err {{ background:#450a0a; border:1px solid #7f1d1d; color:#fca5a5; }}
</style></head><body>
  <div class="neon-logo">
    <span class="neon-agency">Agency</span>
    <div class="neon-box"><span class="neon-text">OF4MYM</span></div>
  </div>
  <h1>Setup Profils</h1>
  <p class="subtitle">Modifie la photo, le @username et la bio de chaque compte Telegram</p>
  {nav_html("setup")}

  <div class="stats">
    <div class="stat"><div class="stat-value">{len(profile_ids)}</div><div class="stat-label">Profils totaux</div></div>
    <div class="stat"><div class="stat-value">{nb_config}</div><div class="stat-label">Configurés</div></div>
    <div class="stat"><div class="stat-value">{len(non_config)}</div><div class="stat-label">Non configurés</div></div>
  </div>

  <!-- ══ CARTES PROFILS ══ -->
  <p class="section-title">Clique sur un profil pour le configurer</p>
  <div class="profiles-quick-list">
    {"".join(f'''<div class="profile-quick-card {"configured" if p in config_map else ""}" onclick="openEditModal('{p}','{(config_map[p].get("username","") or "").replace("'","&#39;")}','{(config_map[p].get("bio","") or "").replace(chr(10)," ").replace("'","&#39;").replace(chr(34),"&quot;")[:80]}',null)">
      <div class="pqc-photo">{"<img src='data:image/{}" + ("jpeg" if (config_map[p].get("photo_name","") or "").lower().endswith((".jpg",".jpeg")) else "png") + ";base64," + (config_map[p].get("photo_b64","") or "")[:200] + "…'>" if p in config_map and config_map[p].get("photo_b64") else "👤"}</div>
      <div class="pqc-pid">{p}</div>
      <div class="pqc-un">{"@"+(config_map[p].get("username","") or "") if p in config_map and config_map[p].get("username") else "<span style=\\'color:#475569\\'>—</span>"}</div>
      <div class="pqc-status">{"✓ Configuré" if p in config_map else "⚪ Non configuré"}</div>
    </div>''' for p in profile_ids)}
  </div>

  <!-- ══ TABLE DES PROFILS CONFIGURÉS ══ -->
  <p class="section-title">Profils configurés ({nb_config})</p>
  <div class="card">
    <table>
      <thead><tr>
        <th style="width:62px;">Photo</th>
        <th class="th-l">ID Profil</th>
        <th class="th-l">@Username</th>
        <th class="th-l">Bio</th>
        <th>Modifié le</th>
        <th style="width:140px;"></th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <!-- ══ MODAL ÉDITION ══ -->
  <div class="setup-modal-overlay" id="setupModal">
    <div class="setup-modal">
      <h2>✏ Modifier le profil — <span id="modalPid" style="color:#93c5fd;font-size:.88rem;"></span></h2>

      <!-- Photo -->
      <div class="setup-field">
        <label>📷 Photo de profil</label>
        <div class="photo-upload-area">
          <div class="photo-upload-preview" id="photoPreview">👤</div>
          <div>
            <input type="file" id="fPhoto" accept="image/*" style="display:none;" onchange="previewPhoto(this)">
            <button class="btn-choose-photo" onclick="document.getElementById('fPhoto').click()">
              📷 Choisir une image
            </button>
            <p id="photoName" style="font-size:.7rem;color:#475569;margin:0;"></p>
          </div>
        </div>
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
      <button class="btn-apply" id="btnApply" onclick="saveAndApply()">
        💾 Enregistrer &amp; Appliquer maintenant
      </button>
      <div class="apply-status" id="applyStatus"></div>
      <button class="btn-cancel-modal" onclick="closeModal()">Annuler</button>
    </div>
  </div>

<div id="toast" class="toast">Sauvegardé !</div>
<script>
let _pid = '';
let _photoB64 = '';
let _photoName = '';

function openEditModal(pid, username, bio, hasPhoto) {{
  _pid = pid;
  _photoB64 = '';
  _photoName = '';
  document.getElementById('modalPid').textContent    = pid;
  document.getElementById('fUsername').value         = username.replace(/&#39;/g,"'").replace(/&quot;/g,'"');
  document.getElementById('fBio').value              = bio.replace(/&#39;/g,"'").replace(/&quot;/g,'"').replace(/ {2}/g,'\\n');
  document.getElementById('photoPreview').innerHTML  = hasPhoto ? '✓ Photo existante' : '👤';
  document.getElementById('photoName').textContent   = hasPhoto ? '(une photo est déjà enregistrée — tu peux en choisir une autre)' : '';
  document.getElementById('fPhoto').value            = '';
  document.getElementById('applyStatus').style.display = 'none';
  document.getElementById('btnApply').disabled = false;
  document.getElementById('btnApply').textContent = '💾 Enregistrer & Appliquer maintenant';
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
  const username = document.getElementById('fUsername').value.trim();
  const bio      = document.getElementById('fBio').value.trim();

  if (!username && !bio && !_photoB64) {{
    alert('Remplis au moins un champ (photo, username ou bio) !');
    return;
  }}

  const btn    = document.getElementById('btnApply');
  const status = document.getElementById('applyStatus');
  btn.disabled = true;
  btn.textContent = '⏳ Enregistrement en cours...';
  status.style.display = 'none';

  try {{
    const r = await fetch('/api/setup/upsert', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        token:      'Compte.1',
        profile_id: _pid,
        username,
        bio,
        photo_b64:  _photoB64,
        photo_name: _photoName,
        apply:      true,   // déclenche le trigger pour profile_changer.py
      }})
    }});
    const d = await r.json();
    if (!d.ok) throw new Error(d.detail || JSON.stringify(d));

    btn.textContent = '✓ Envoyé !';
    status.className = 'apply-status ok';
    status.innerHTML = '✅ Config enregistrée · <strong>profile_changer.py se lance dans ~30s</strong> (daemon en arrière-plan)<br><span style="font-size:.7rem;color:#4ade80;">Assure-toi que LANCER_TOUT.vbs a été exécuté au démarrage.</span>';
    status.style.display = 'block';

    // Recharge la page après 3s pour montrer la nouvelle config
    setTimeout(() => {{ closeModal(); location.reload(); }}, 3500);

  }} catch(e) {{
    btn.disabled = false;
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
</body></html>"""
    return html
