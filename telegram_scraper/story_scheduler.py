"""
Story Scheduler — Multi-comptes + Playlists
Run: python telegram_scraper/story_scheduler.py
"""

import asyncio, json, os, sys, uuid, hashlib, time as _time, secrets
import concurrent.futures
import stripe as _stripe
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Sessions ──────────────────────────────────────────────────────────────────
SESSION_COOKIE  = "ss_session"
SESSION_MAX_AGE = 86400 * 7       # 7 jours

def _load_sessions() -> dict[str, dict]:
    try:
        raw = json.loads(_SESSIONS_FILE.read_text(encoding="utf-8")) if _SESSIONS_FILE.exists() else {}
    except Exception:
        raw = {}
    now = _time.time()
    return {t: v for t, v in raw.items() if isinstance(v, dict) and v.get("exp", 0) > now}

def _save_sessions(s: dict) -> None:
    _SESSIONS_FILE.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")

_sessions: dict[str, dict] = _load_sessions()   # token → {pid, exp}

def _new_session(profile_id: str) -> str:
    token = secrets.token_hex(32)
    _sessions[token] = {"pid": profile_id, "exp": _time.time() + SESSION_MAX_AGE}
    _save_sessions(_sessions)
    return token

def _get_session_profile(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token: return None
    entry = _sessions.get(token)
    if not entry: return None
    if entry.get("exp", 0) < _time.time():
        _sessions.pop(token, None)
        return None
    return entry.get("pid")

def _require_auth(request: Request) -> str:
    pid = _get_session_profile(request)
    if not pid:
        raise HTTPException(401, "Non authentifié")
    return pid

def _hash_password(pw: str) -> str:
    return hashlib.sha256(pw.strip().encode()).hexdigest()

BASE_DIR      = Path(__file__).parent
_SESSIONS_FILE = BASE_DIR / "sessions.json"
# Sur Render : données persistées dans /data si DATA_DIR défini
_DATA_DIR     = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))
_DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR    = _DATA_DIR / "story_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
SCHED_FILE    = _DATA_DIR / "scheduled_stories.json"
ACCOUNTS_FILE = _DATA_DIR / "story_accounts.json"
PLAYLIST_FILE = _DATA_DIR / "story_playlists.json"
PARIS_TZ      = ZoneInfo("Europe/Paris")

# ── Multi-profiles ─────────────────────────────────────────────────────────────
PROFILES_FILE       = BASE_DIR / "profiles.json"
ACTIVE_PROFILE_FILE = BASE_DIR / "active_profile.json"
PROFILE_DATA_ROOT   = _DATA_DIR / "profile_data"
PROFILE_DATA_ROOT.mkdir(exist_ok=True)

def _load_profiles() -> list[dict]:
    return _load_json(PROFILES_FILE, [])

def _save_profiles(profs: list[dict]):
    _save_json(PROFILES_FILE, profs)

def _get_active_profile_id() -> str | None:
    return _load_json(ACTIVE_PROFILE_FILE, {}).get("id")

def _get_active_profile() -> dict | None:
    pid = _get_active_profile_id()
    if not pid: return None
    return next((p for p in _load_profiles() if p["id"] == pid), None)

def _get_profile_data_dir(profile_id: str | None = None) -> Path:
    if profile_id is None:
        profile_id = _get_active_profile_id()
    if not profile_id:
        return _DATA_DIR
    profs = _load_profiles()
    p = next((x for x in profs if x["id"] == profile_id), None)
    if p and p.get("data_dir"):
        d = Path(p["data_dir"])
    else:
        d = PROFILE_DATA_ROOT / profile_id
    d.mkdir(parents=True, exist_ok=True)
    return d

sys.path.insert(0, str(BASE_DIR))
try:
    from config import API_ID, API_HASH
except ImportError:
    API_ID   = int(os.environ.get("TG_API_ID", "0"))
    API_HASH = os.environ.get("TG_API_HASH", "")

# ── Persistance ───────────────────────────────────────────────────────────────
def _load_json(path: Path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default

def _save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

_accounts:  list[dict] = _load_json(ACCOUNTS_FILE, [])
_scheduled: list[dict] = _load_json(SCHED_FILE, [])
_playlists: list[dict] = _load_json(PLAYLIST_FILE, [])

# ── Clients Telethon ──────────────────────────────────────────────────────────
_clients:      dict[str, object] = {}
_phone_hashes: dict[str, str]    = {}
_pending_phone: dict[str, str]   = {}
_tg_lock = asyncio.Lock()  # Évite les conflits SQLite sur les fichiers .session

async def _get_client(acc_id: str, accounts_list: list | None = None):
    from telethon import TelegramClient
    accs = accounts_list if accounts_list is not None else _accounts
    acc = next((a for a in accs if a["id"] == acc_id), None)
    if not acc:
        # Chercher dans tous les profils (pour le scheduler multi-profil)
        for prof in _load_profiles():
            pdir = _get_profile_data_dir(prof["id"])
            candidate = pdir / f"session_story_{acc_id}"
            if (Path(str(candidate) + ".session")).exists():
                acc = {"id": acc_id, "session_file": str(candidate),
                       "name": f"Compte {acc_id[:8]}", "phone": "?"}
                print(f"[RECOVER] Compte {acc_id} trouvé dans profil {prof.get('name','?')}", flush=True)
                break
    if not acc:
        raise ValueError(f"Compte {acc_id} introuvable dans ce profil")
    async with _tg_lock:
        if acc_id not in _clients:
            _clients[acc_id] = TelegramClient(acc["session_file"], API_ID, API_HASH)
        c = _clients[acc_id]
        if not c.is_connected(): await c.connect()
    return c

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Story Scheduler")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

# ── Stripe ────────────────────────────────────────────────────────────────────
_stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET_AG", "")
STRIPE_PRICES = {
    "starter":  os.getenv("STRIPE_PRICE_STARTER_AG", ""),
    "pro":      os.getenv("STRIPE_PRICE_PRO_AG", ""),
    "business": os.getenv("STRIPE_PRICE_BUSINESS_AG", ""),
}
BASE_URL = "https://agencymael.duckdns.org"

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

_PUBLIC_PATHS = {"/", "/api/auth/login", "/api/auth/logout", "/api/auth/check", "/api/auth/register"}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Allow public paths, static files, uploads, and avatar images
        if (path in _PUBLIC_PATHS or
            path.startswith("/uploads/") or
            path.startswith("/static/") or
            path.startswith("/api/social/avatar/") or
            (path.startswith("/api/accounts/") and path.endswith("/photo"))):
            return await call_next(request)
        # Protect all /api/* routes
        if path.startswith("/api/"):
            token = request.cookies.get(SESSION_COOKIE)
            if not token or token not in _sessions:
                return StarletteResponse(
                    content='{"detail":"Non authentifié"}',
                    status_code=401,
                    media_type="application/json"
                )
        return await call_next(request)

app.add_middleware(AuthMiddleware)
# Dossier uploads partagé entre tous les profils (un seul dossier physique)
# Chaque profil voit ses propres stories via son scheduled_stories.json
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# ─────────────────────────────────────────────────────────────────────────────
#  Comptes
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/accounts")
async def list_accounts():
    async def _check(acc):
        try:
            c = await asyncio.wait_for(_get_client(acc["id"]), timeout=5)
            ok = await asyncio.wait_for(c.is_user_authorized(), timeout=5)
            return {**acc, "connected": ok}
        except:
            return {**acc, "connected": False}
    return await asyncio.gather(*[_check(a) for a in _accounts])

@app.get("/api/accounts/{acc_id}/photo")
async def get_account_photo(acc_id: str):
    """Retourne la photo de profil Telegram (JPEG), avec cache disque."""
    import io
    from fastapi.responses import Response
    cache_dir = Path("/opt/storyscheduler/telegram_scraper/avatar_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"tg_{acc_id}.jpg"
    if cache_file.exists() and cache_file.stat().st_size > 0:
        return Response(content=cache_file.read_bytes(), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})
    acc = next((a for a in _accounts if a["id"] == acc_id), None)
    if not acc:
        raise HTTPException(404, "Compte non trouvé dans le profil actif")
    try:
        client = await _get_client(acc_id)
        if not await client.is_user_authorized():
            raise HTTPException(404, "Non autorisé")
        buf = io.BytesIO()
        result = await client.download_profile_photo("me", file=buf, download_big=False)
        if result is None:
            raise HTTPException(404, "Pas de photo")
        buf.seek(0)
        data = buf.read()
        cache_file.write_bytes(data)
        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(404, "Photo indisponible")

@app.post("/api/accounts/send-code")
async def accounts_send_code(data: dict):
    phone = data.get("phone","").strip()
    if not phone: raise HTTPException(400,"Numéro requis")
    acc_id = uuid.uuid4().hex[:8]
    session_file = str(_get_profile_data_dir() / f"session_story_{acc_id}")
    # Marqueur pour éviter que _recover_orphan_sessions récupère ce fichier si l'ajout est abandonné
    Path(session_file + ".pending").touch()
    _pending_phone[acc_id] = phone
    from telethon import TelegramClient
    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.connect()
    _clients[acc_id] = client
    result = await client.send_code_request(phone)
    _phone_hashes[acc_id] = result.phone_code_hash
    return {"ok": True, "acc_id": acc_id}

@app.post("/api/accounts/verify-code")
async def accounts_verify_code(data: dict):
    acc_id = data.get("acc_id",""); code = str(data.get("code","")).strip()
    phone  = _pending_phone.get(acc_id)
    if not phone: raise HTTPException(400,"Session expirée")
    try:
        client = _clients[acc_id]
        await client.sign_in(phone, code, phone_code_hash=_phone_hashes[acc_id])
        me = await client.get_me()
        name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        display = f"{name} (@{me.username})" if me.username else name
        sess_path = str(_get_profile_data_dir()/f"session_story_{acc_id}")
        acc = {"id":acc_id,"phone":phone,"name":display,"session_file":sess_path}
        _accounts.append(acc); _save_json(ACCOUNTS_FILE, _accounts)
        Path(sess_path + ".pending").unlink(missing_ok=True)
        _pending_phone.pop(acc_id,None); _phone_hashes.pop(acc_id,None)
        return {"ok":True,"acc_id":acc_id,"name":display}
    except Exception as e:
        if "two" in str(e).lower() or "password" in str(e).lower():
            return {"ok":False,"need_2fa":True,"acc_id":acc_id}
        raise HTTPException(400, str(e))

@app.post("/api/accounts/verify-2fa")
async def accounts_verify_2fa(data: dict):
    acc_id = data.get("acc_id",""); password = data.get("password","")
    try:
        client = _clients[acc_id]
        await client.sign_in(password=password)
        me = await client.get_me()
        name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        display = f"{name} (@{me.username})" if me.username else name
        phone = _pending_phone.get(acc_id,"")
        sess_path = str(_get_profile_data_dir()/f"session_story_{acc_id}")
        acc = {"id":acc_id,"phone":phone,"name":display,"session_file":sess_path}
        _accounts.append(acc); _save_json(ACCOUNTS_FILE, _accounts)
        Path(sess_path + ".pending").unlink(missing_ok=True)
        _pending_phone.pop(acc_id,None); _phone_hashes.pop(acc_id,None)
        return {"ok":True,"acc_id":acc_id,"name":display}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.delete("/api/accounts/{acc_id}")
async def delete_account(acc_id: str):
    global _accounts
    acc = next((a for a in _accounts if a["id"]==acc_id), None)
    if not acc: raise HTTPException(404,"Introuvable")
    if acc_id in _clients:
        try: await _clients[acc_id].disconnect()
        except: pass
        del _clients[acc_id]
    for ext in ("",".session",".session-journal"):
        p = Path(acc["session_file"]+ext)
        if p.exists(): p.unlink(missing_ok=True)
    _accounts = [a for a in _accounts if a["id"]!=acc_id]
    _save_json(ACCOUNTS_FILE, _accounts)
    return {"ok":True}

@app.patch("/api/accounts/{acc_id}")
async def rename_account(acc_id: str, req: dict = Body(...)):
    acc = next((a for a in _accounts if a["id"]==acc_id), None)
    if not acc: raise HTTPException(404,"Compte introuvable")
    if "name" in req: acc["name"] = req["name"].strip()
    if "description" in req: acc["description"] = req["description"].strip()
    _save_json(ACCOUNTS_FILE, _accounts)
    return {"ok": True}

@app.patch("/api/scheduled/{sid}")
async def patch_scheduled(sid: str, req: dict = Body(...)):
    s = next((x for x in _scheduled if x["id"]==sid), None)
    if not s: raise HTTPException(404,"Introuvable")
    if "note" in req: s["note"] = req["note"].strip()
    if "scheduled_at" in req: s["scheduled_at"] = req["scheduled_at"]
    if "account_ids" in req: s["account_ids"] = req["account_ids"]
    _save_json(SCHED_FILE, _scheduled)
    return {"ok": True}

@app.post("/api/scheduled/bulk-delete")
async def bulk_delete_scheduled(req: dict = Body(...)):
    global _scheduled
    ids = set(req.get("ids", []))
    before = len(_scheduled)
    _scheduled = [s for s in _scheduled if s["id"] not in ids or s["status"] != "pending"]
    _save_json(SCHED_FILE, _scheduled)
    return {"deleted": before - len(_scheduled)}

@app.post("/api/scheduled/bulk-reschedule")
async def bulk_reschedule_scheduled(req: dict = Body(...)):
    """Change la DATE uniquement pour un lot de stories (garde l'heure originale)."""
    ids = set(req.get("ids", []))
    new_date = req.get("date", "")  # "YYYY-MM-DD"
    if not new_date: raise HTTPException(400, "date requis")
    count = 0
    for s in _scheduled:
        if s["id"] not in ids or s["status"] != "pending": continue
        orig = s.get("scheduled_at", "")
        time_part = orig[10:] if len(orig) > 10 else "T12:00:00"
        s["scheduled_at"] = new_date + time_part
        count += 1
    _save_json(SCHED_FILE, _scheduled)
    return {"rescheduled": count}

# ─────────────────────────────────────────────────────────────────────────────
#  Upload
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload_photo(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in (".jpg",".jpeg",".png",".webp",".gif"):
        raise HTTPException(400,"Format non supporté")
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR/filename).write_bytes(await file.read())
    return {"filename":filename,"url":f"/uploads/{filename}"}

# ─────────────────────────────────────────────────────────────────────────────
#  Playlists
# ─────────────────────────────────────────────────────────────────────────────
# Playlist entry: {id, name, entries:[{filename, day_offset(0-based), time:"HH:MM"}], created_at}
# Launch: start_date + account_ids → crée des scheduled stories

@app.get("/api/playlists")
async def get_playlists():
    return _playlists

class PlaylistEntry(BaseModel):
    filename: str
    day_offset: int   # 0 = jour 1, 1 = jour 2...
    time: str         # "HH:MM"

class PlaylistCreate(BaseModel):
    name: str
    entries: list[PlaylistEntry]

@app.post("/api/playlists")
async def create_playlist(req: PlaylistCreate):
    if not req.name.strip(): raise HTTPException(400,"Nom requis")
    if not req.entries: raise HTTPException(400,"Aucune entrée")
    pl = {
        "id":         uuid.uuid4().hex[:8],
        "name":       req.name.strip(),
        "entries":    [e.dict() for e in req.entries],
        "created_at": datetime.now(PARIS_TZ).isoformat(),
    }
    _playlists.append(pl); _save_json(PLAYLIST_FILE, _playlists)
    return {"ok":True,"id":pl["id"]}

@app.put("/api/playlists/{pl_id}")
async def update_playlist(pl_id: str, req: PlaylistCreate):
    pl = next((p for p in _playlists if p["id"]==pl_id), None)
    if not pl: raise HTTPException(404,"Introuvable")
    pl["name"]    = req.name.strip()
    pl["entries"] = [e.dict() for e in req.entries]
    _save_json(PLAYLIST_FILE, _playlists)
    return {"ok":True}

@app.delete("/api/playlists/{pl_id}")
async def delete_playlist(pl_id: str):
    global _playlists
    _playlists = [p for p in _playlists if p["id"]!=pl_id]
    _save_json(PLAYLIST_FILE, _playlists)
    return {"ok":True}

class LaunchRequest(BaseModel):
    start_date:  str        # "YYYY-MM-DD"
    account_ids: list[str]

@app.post("/api/playlists/{pl_id}/launch")
async def launch_playlist(pl_id: str, req: LaunchRequest):
    pl = next((p for p in _playlists if p["id"]==pl_id), None)
    if not pl: raise HTTPException(404,"Playlist introuvable")
    if not req.account_ids: raise HTTPException(400,"Aucun compte sélectionné")
    try:
        start = date.fromisoformat(req.start_date)
    except:
        raise HTTPException(400,"Date invalide")
    created = 0
    for entry in pl["entries"]:
        post_date = start + timedelta(days=entry["day_offset"])
        scheduled_at = f"{post_date.isoformat()}T{entry['time']}"
        sid = uuid.uuid4().hex[:8]
        _scheduled.append({
            "id":           sid,
            "filename":     entry["filename"],
            "scheduled_at": scheduled_at,
            "account_ids":  req.account_ids,
            "status":       "pending",
            "results":      {},
            "playlist_id":  pl_id,
            "playlist_name": pl["name"],
            "created_at":   datetime.now(PARIS_TZ).isoformat(),
        })
        created += 1
    _save_json(SCHED_FILE, _scheduled)
    return {"ok":True,"count":created,"start":str(start)}

# ─────────────────────────────────────────────────────────────────────────────
#  Schedule manuel
# ─────────────────────────────────────────────────────────────────────────────
class PhotoEntry(BaseModel):
    filename: str
    scheduled_at: str

class ScheduleRequest(BaseModel):
    photos: list[PhotoEntry]
    account_ids: list[str]

@app.post("/api/schedule")
async def schedule_stories(req: ScheduleRequest):
    if not req.photos: raise HTTPException(400,"Aucune photo")
    if not req.account_ids: raise HTTPException(400,"Aucun compte")
    for p in req.photos:
        _scheduled.append({"id":uuid.uuid4().hex[:8],"filename":p.filename,
            "scheduled_at":p.scheduled_at,"account_ids":req.account_ids,
            "status":"pending","results":{},"created_at":datetime.now(PARIS_TZ).isoformat()})
    _save_json(SCHED_FILE, _scheduled)
    return {"ok":True,"count":len(req.photos)}

@app.get("/api/scheduled")
async def get_scheduled():
    return sorted(_load_json(SCHED_FILE, []), key=lambda x: x["scheduled_at"])

@app.get("/api/telegram/next-dates")
async def get_telegram_next_dates():
    """Pour chaque compte Telegram, retourne le nb de posts programmés et la prochaine date libre."""
    from datetime import date as _date
    result = []
    for acc in _accounts:
        acc_id = acc["id"]
        name   = acc.get("name") or acc.get("phone", acc_id)
        taken_dates: set = set()
        for e in _scheduled:
            if e.get("account_id") == acc_id and e.get("status") not in ("error", "failed"):
                try:
                    taken_dates.add(datetime.fromisoformat(e["scheduled_at"]).date())
                except Exception:
                    pass
        check = (datetime.now() + timedelta(days=1)).date()
        while check in taken_dates:
            check += timedelta(days=1)
        last_date = max(taken_dates) if taken_dates else None
        result.append({
            "account_id": acc_id,
            "name": name,
            "scheduled_count": len(taken_dates),
            "last_scheduled": str(last_date) if last_date else None,
            "next_free": str(check),
        })
    return result

@app.get("/api/snap/stories/blocked-until")
async def get_snap_blocked():
    return _load_snap_blocked()

@app.post("/api/snap/stories/blocked-until")
async def set_snap_blocked(req: Request):
    body    = await req.json()   # {"account_id": "xxx", "until": "2026-07-04"}
    blocked = _load_snap_blocked()
    acc_id  = body.get("account_id","")
    until   = body.get("until","")
    if acc_id and until:
        blocked[acc_id] = until
    elif acc_id and not until:
        blocked.pop(acc_id, None)
    _save_snap_blocked(blocked)
    return blocked

@app.get("/api/snap/stories/next-dates")
async def get_snap_stories_next_dates():
    """Pour chaque compte Snapchat : nb de stories programmées + prochaine date libre.
    Prend en compte : _snap_scheduled (dashboard) + snap_blocked_until (manuel)."""
    blocked = _load_snap_blocked()
    result  = []
    for acc in SNAP_ACCOUNTS:
        acc_id   = acc["id"]
        username = acc["username"]
        taken_dates: set = set()
        # 1. Stories programmées via ce dashboard
        for e in _snap_scheduled:
            if acc_id in e.get("account_ids", []) and e.get("status") not in ("error",):
                try:
                    taken_dates.add(datetime.fromisoformat(e["scheduled_at"]).date())
                except Exception:
                    pass
        # 2. Dates bloquées manuellement (stories programmées via d'autres outils)
        manual_until_str = blocked.get(acc_id)
        manual_until = None
        if manual_until_str:
            try:
                manual_until = datetime.fromisoformat(manual_until_str).date()
                # Toutes les dates de demain jusqu'à manual_until sont prises
                d = (datetime.now() + timedelta(days=1)).date()
                while d <= manual_until:
                    taken_dates.add(d)
                    d += timedelta(days=1)
            except Exception:
                pass
        # 3. Chercher la prochaine date vraiment libre
        check = (datetime.now() + timedelta(days=1)).date()
        while check in taken_dates:
            check += timedelta(days=1)
        last_date = max(taken_dates) if taken_dates else None
        result.append({
            "account_id":      acc_id,
            "username":        username,
            "scheduled_count": len(taken_dates),
            "last_scheduled":  str(last_date) if last_date else None,
            "next_free":       str(check),
            "manual_until":    manual_until_str or None,
        })
    return result

@app.delete("/api/scheduled/{sid}")
async def delete_scheduled(sid: str):
    global _scheduled
    before = len(_scheduled)
    _scheduled = [s for s in _scheduled if s["id"]!=sid]
    if len(_scheduled)==before: raise HTTPException(404,"Introuvable")
    _save_json(SCHED_FILE, _scheduled)
    return {"ok":True}

@app.post("/api/scheduled/clone-to-accounts")
async def clone_to_accounts(req: dict = Body(...)):
    account_ids = req.get("account_ids", [])
    story_ids   = req.get("story_ids", [])   # vide = tous les pending
    if not account_ids: raise HTTPException(400,"Aucun compte sélectionné")
    targets = [s for s in _scheduled if s["status"]=="pending" and (not story_ids or s["id"] in story_ids)]
    added = 0
    for story in targets:
        for acc_id in account_ids:
            if acc_id in (story.get("account_ids") or []): continue  # déjà assigné
            story.setdefault("account_ids", []).append(acc_id)
            added += 1
    _save_json(SCHED_FILE, _scheduled)
    return {"ok": True, "count": added}

@app.get("/api/stats/views")
async def api_stats_views():
    sent = [s for s in _scheduled if s["status"] in ("done","partial")]
    out  = []
    for s in sent[-30:]:
        item = {
            "id": s["id"], "filename": s["filename"],
            "sent_at": s.get("scheduled_at"), "playlist_name": s.get("playlist_name"),
            "accounts": []
        }
        for acc_id, res in (s.get("results") or {}).items():
            if res.get("status") != "done": continue
            sid  = res.get("story_id")
            views = await _get_story_views(acc_id, sid) if sid else None
            item["accounts"].append({"acc_id": acc_id, "story_id": sid, "views": views})
        out.append(item)
    return out

@app.get("/api/stats/history")
async def api_stats_history():
    """Retourne toutes les stories envoyées avec vues sauvegardées — permanent."""
    sent = [s for s in _scheduled if s["status"] in ("done","partial","error")]
    out  = []
    for s in sent:
        accs = []
        for acc_id, res in (s.get("results") or {}).items():
            if res.get("status") != "done": continue
            acc = next((a for a in _accounts if a["id"] == acc_id), None)
            accs.append({
                "acc_id":    acc_id,
                "acc_name":  acc.get("name", acc_id) if acc else acc_id,
                "story_id":  res.get("story_id"),
                "views":     res.get("views_snapshot"),
                "reactions": res.get("reactions_snapshot"),
                "forwards":  res.get("forwards_snapshot"),
                "views_at":  res.get("views_updated_at"),
                "sent_at":   res.get("sent_at"),
            })
        if not accs and s["status"] == "error":
            continue  # 100% d'échec → inutile dans les stats
        out.append({
            "id":            s["id"],
            "filename":      s["filename"],
            "scheduled_at":  s.get("scheduled_at"),
            "playlist_name": s.get("playlist_name"),
            "status":        s["status"],
            "accounts":      accs,
        })
    return list(reversed(out))

async def _snapshot_views_loop():
    """Sauvegarde les vues toutes les heures pour les stories actives (<48h)."""
    await asyncio.sleep(60)
    while True:
        now = datetime.now(PARIS_TZ)
        changed = False
        for story in _scheduled:
            if story["status"] not in ("done", "partial"): continue
            try:
                sent_dt = datetime.fromisoformat(
                    next(iter(story.get("results", {}).values()), {}).get("sent_at", story.get("scheduled_at",""))
                )
                if sent_dt.tzinfo is None: sent_dt = sent_dt.replace(tzinfo=PARIS_TZ)
            except Exception:
                continue
            age_h = (now - sent_dt).total_seconds() / 3600
            if age_h > 48: continue  # story expirée depuis longtemps, skip
            for acc_id, res in (story.get("results") or {}).items():
                if res.get("status") != "done": continue
                sid = res.get("story_id")
                if not sid: continue
                try:
                    from telethon.tl.functions.stories import GetPeerStoriesRequest
                    from telethon.tl.types import InputPeerSelf
                    client = await _get_client(acc_id)
                    resp   = await client(GetPeerStoriesRequest(peer=InputPeerSelf()))
                    stories = resp.stories.stories if resp and resp.stories else []
                    st = next((x for x in stories if x.id == sid), None)
                    if st:
                        v = getattr(st, "views", None)
                        res["views_snapshot"]     = getattr(v, "views_count",     0) or 0
                        res["reactions_snapshot"] = getattr(v, "reactions_count", 0) or 0
                        res["forwards_snapshot"]  = getattr(v, "forwards_count",  0) or 0
                        res["views_updated_at"]   = now.isoformat()
                        changed = True
                except Exception as e:
                    print(f"[SNAPSHOT] {acc_id}/{sid}: {e}", flush=True)
        if changed:
            _save_json(SCHED_FILE, _scheduled)
            print(f"[SNAPSHOT] Vues sauvegardées ({now.strftime('%H:%M')})", flush=True)
        await asyncio.sleep(3600)  # toutes les heures

async def _snap_scheduler_loop():
    """Envoie les posts Snapchat programmés à OneUp — parcourt TOUS les profils à chaque tick."""
    await asyncio.sleep(20)
    import re as _re_snap2
    import random as _rnd_snap
    while True:
        now = datetime.now(PARIS_TZ)
        try:
            profs = _load_profiles()
        except Exception:
            profs = []
        for prof in profs:
            pid = prof["id"]
            pdir = _get_profile_data_dir(pid)
            snap_sf = pdir / "snap_scheduled.json"
            if not snap_sf.exists():
                continue
            try:
                snap_scheduled = _load_json(snap_sf, [])
                snap_accounts  = prof.get("snap_accounts", [])
                p_oneup        = prof.get("oneup_api_key", ONEUP_API_KEY)
                p_cat          = prof.get("category_id_snap", CATEGORY_ID_SNAP)
                p_cn           = prof.get("cloudinary_cloud_name", CLOUDINARY_CLOUD_NAME)
                p_ck           = prof.get("cloudinary_api_key", CLOUDINARY_API_KEY_CL)
                p_cs           = prof.get("cloudinary_api_secret", CLOUDINARY_API_SECRET)
                p_fld          = _re_snap2.sub(r"[^A-Za-z0-9_-]", "", prof.get("name") or pid) or pid
            except Exception:
                continue
            for story in list(snap_scheduled):
                if story["status"] != "pending": continue
                try:
                    dt = datetime.fromisoformat(story["scheduled_at"])
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=PARIS_TZ)
                    if now < dt: continue
                except Exception:
                    continue
                story["status"] = "posting"
                _save_json(snap_sf, snap_scheduled)
                fpath = UPLOAD_DIR / story["filename"]
                if not fpath.exists():
                    story["status"] = "error"
                    story["results"] = {"_": {"status": "error", "error": "Fichier introuvable"}}
                    _save_json(snap_sf, snap_scheduled)
                    continue
                loop = asyncio.get_event_loop()
                is_video = fpath.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv")
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    media_url = await loop.run_in_executor(pool, _cloudinary_upload, fpath, is_video, p_cn, p_ck, p_cs, p_fld)
                if not media_url:
                    story["status"] = "error"
                    story["results"] = {"_": {"status": "error", "error": "Upload Cloudinary échoué"}}
                    _save_json(snap_sf, snap_scheduled)
                    continue
                if not is_video:
                    conv_path = _story_convert(fpath)
                    if conv_path != fpath:
                        with concurrent.futures.ThreadPoolExecutor() as pool2:
                            media_url = await loop.run_in_executor(pool2, _cloudinary_upload, conv_path, False, p_cn, p_ck, p_cs, p_fld)
                        if not media_url:
                            story["status"] = "error"
                            story["results"] = {"_": {"status": "error", "error": "Cloudinary story convert failed"}}
                            _save_json(snap_sf, snap_scheduled)
                            continue
                story["cloudinary_url"] = media_url
                results = {}
                for n_acc, acc_id in enumerate(story.get("account_ids", [])):
                    acc = next((a for a in snap_accounts if a["id"] == acc_id), None)
                    uname = acc["username"] if acc else acc_id
                    try:
                        offset_min = sum(_rnd_snap.randint(2, 6) for _ in range(n_acc))
                        dt_offset = (datetime.fromisoformat(story["scheduled_at"]) + timedelta(minutes=offset_min)).isoformat()
                    except Exception:
                        dt_offset = story["scheduled_at"]
                    with concurrent.futures.ThreadPoolExecutor() as pool3:
                        ok, msg = await loop.run_in_executor(
                            pool3, _oneup_schedule, media_url, is_video, acc_id, dt_offset, p_oneup, p_cat)
                    results[acc_id] = {"username": uname, "status": "done" if ok else "error", "msg": msg}
                story["results"] = results
                ss = [r["status"] for r in results.values()]
                story["status"] = "done" if all(s == "done" for s in ss) else "error" if all(s == "error" for s in ss) else "partial"
                _save_json(snap_sf, snap_scheduled)
                print(f"[SNAP][{prof.get('name','?')}] {story['filename']} → {story['status']}", flush=True)
        await asyncio.sleep(30)

async def _ig_scheduler_loop():
    """Envoie les posts Instagram programmés — parcourt TOUS les profils à chaque tick."""
    await asyncio.sleep(15)
    import re as _re_ig2
    while True:
        now = datetime.now(PARIS_TZ)
        try:
            profs = _load_profiles()
        except Exception:
            profs = []
        for prof in profs:
            pid = prof["id"]
            pdir = _get_profile_data_dir(pid)
            ig_sf = pdir / "instagram_scheduled.json"
            if not ig_sf.exists():
                continue
            try:
                ig_scheduled  = _load_json(ig_sf, [])
                ig_accounts   = prof.get("instagram_accounts", [])
                p_oneup       = prof.get("oneup_api_key", ONEUP_API_KEY)
                p_cat         = prof.get("category_id_instagram", CATEGORY_ID_IG)
                p_cn          = prof.get("cloudinary_cloud_name", CLOUDINARY_CLOUD_NAME)
                p_ck          = prof.get("cloudinary_api_key", CLOUDINARY_API_KEY_CL)
                p_cs          = prof.get("cloudinary_api_secret", CLOUDINARY_API_SECRET)
                p_fld         = _re_ig2.sub(r"[^A-Za-z0-9_-]", "", prof.get("name") or pid) or pid
            except Exception:
                continue
            for story in list(ig_scheduled):
                if story["status"] != "pending": continue
                try:
                    dt = datetime.fromisoformat(story["scheduled_at"])
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=PARIS_TZ)
                    if now < dt: continue
                except Exception: continue
                story["status"] = "posting"
                _save_json(ig_sf, ig_scheduled)
                fpath = UPLOAD_DIR / story["filename"]
                if not fpath.exists():
                    story["status"] = "error"
                    story["results"] = {"_": {"status": "error", "error": "Fichier introuvable"}}
                    _save_json(ig_sf, ig_scheduled)
                    continue
                loop = asyncio.get_event_loop()
                is_video = fpath.suffix.lower() in (".mp4", ".mov", ".avi")
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    media_url = await loop.run_in_executor(pool, _cloudinary_upload, fpath, is_video, p_cn, p_ck, p_cs, p_fld)
                if not media_url:
                    story["status"] = "error"
                    story["results"] = {"_": {"status": "error", "error": "Upload Cloudinary échoué"}}
                    _save_json(ig_sf, ig_scheduled)
                    continue
                results = {}
                for n, acc_id in enumerate(story.get("account_ids", [])):
                    acc = next((a for a in ig_accounts if a["id"] == acc_id), None)
                    uname = acc["username"] if acc else acc_id
                    dt_offset = (datetime.fromisoformat(story["scheduled_at"]) + timedelta(minutes=n)).isoformat()
                    with concurrent.futures.ThreadPoolExecutor() as pool2:
                        ok, msg = await loop.run_in_executor(
                            pool2, _oneup_ig_schedule, media_url, is_video, acc_id, dt_offset, story.get("caption", ""), p_oneup, p_cat)
                    results[acc_id] = {"username": uname, "status": "done" if ok else "error", "msg": msg}
                story["results"] = results
                ss = [r["status"] for r in results.values()]
                story["status"] = "done" if all(s == "done" for s in ss) else "error" if all(s == "error" for s in ss) else "partial"
                _save_json(ig_sf, ig_scheduled)
                print(f"[IG][{prof.get('name','?')}] {story['filename']} → {story['status']}", flush=True)
        await asyncio.sleep(30)

def _oneup_ig_schedule(media_url: str, is_video: bool, account_id: str, dt_str: str, caption: str = "", oneup_key: str | None = None, category_id: str | None = None) -> tuple[bool, str]:
    import requests as _req
    dt_obj = datetime.fromisoformat(dt_str)
    dt_fmt = dt_obj.strftime("%Y-%m-%d %H:%M")
    endpoint = "schedulevideopost" if is_video else "scheduleimagepost"
    key_media = "video_url" if is_video else "image_url"
    params = {
        "apiKey": oneup_key or ONEUP_API_KEY,
        "category_id": category_id or CATEGORY_ID_IG,
        "social_network_id": f'["{account_id}"]',
        "scheduled_date_time": dt_fmt,
        "content": caption,
        key_media: media_url,
    }
    try:
        r = _req.post(f"https://www.oneupapp.io/api/{endpoint}", params=params, timeout=30)
        try:
            ok = r.status_code in (200, 201) and not r.json().get("error")
        except Exception:
            ok = r.status_code in (200, 201)
        return ok, r.text[:200]
    except Exception as e:
        return False, str(e)[:200]

def _oneup_fb_schedule(media_url: str, is_video: bool, account_id: str, dt_str: str, caption: str = "", oneup_key: str | None = None, category_id: str | None = None) -> tuple[bool, str]:
    import requests as _req
    dt_obj = datetime.fromisoformat(dt_str)
    dt_fmt = dt_obj.strftime("%Y-%m-%d %H:%M")
    endpoint = "schedulevideopost" if is_video else "scheduleimagepost"
    key_media = "video_url" if is_video else "image_url"
    params = {
        "apiKey": oneup_key or ONEUP_API_KEY,
        "category_id": category_id or CATEGORY_ID_FB,
        "social_network_id": f'["{account_id}"]',
        "scheduled_date_time": dt_fmt,
        "content": caption,
        key_media: media_url,
    }
    try:
        r = _req.post(f"https://www.oneupapp.io/api/{endpoint}", params=params, timeout=30)
        try:
            ok = r.status_code in (200, 201) and not r.json().get("error")
        except Exception:
            ok = r.status_code in (200, 201)
        return ok, r.text[:200]
    except Exception as e:
        return False, str(e)[:200]

async def _fb_scheduler_loop():
    """Envoie les posts Facebook programmés — parcourt TOUS les profils à chaque tick."""
    await asyncio.sleep(20)
    import re as _re_fb
    while True:
        now = datetime.now(PARIS_TZ)
        try:
            profs = _load_profiles()
        except Exception:
            profs = []
        for prof in profs:
            pid = prof["id"]
            pdir = _get_profile_data_dir(pid)
            fb_sf = pdir / "facebook_scheduled.json"
            if not fb_sf.exists():
                continue
            try:
                fb_scheduled  = _load_json(fb_sf, [])
                fb_accounts   = prof.get("facebook_accounts", [])
                p_oneup       = prof.get("oneup_api_key", ONEUP_API_KEY)
                p_cat         = prof.get("category_id_facebook", CATEGORY_ID_FB)
                p_cn          = prof.get("cloudinary_cloud_name", CLOUDINARY_CLOUD_NAME)
                p_ck          = prof.get("cloudinary_api_key", CLOUDINARY_API_KEY_CL)
                p_cs          = prof.get("cloudinary_api_secret", CLOUDINARY_API_SECRET)
                p_fld         = _re_fb.sub(r"[^A-Za-z0-9_-]", "", prof.get("name") or pid) or pid
            except Exception:
                continue
            for story in list(fb_scheduled):
                if story["status"] != "pending": continue
                try:
                    dt = datetime.fromisoformat(story["scheduled_at"])
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=PARIS_TZ)
                    if now < dt: continue
                except Exception: continue
                story["status"] = "posting"
                _save_json(fb_sf, fb_scheduled)
                fpath = UPLOAD_DIR / story["filename"]
                if not fpath.exists():
                    story["status"] = "error"
                    story["results"] = {"_": {"status": "error", "error": "Fichier introuvable"}}
                    _save_json(fb_sf, fb_scheduled)
                    continue
                loop = asyncio.get_event_loop()
                is_video = fpath.suffix.lower() in (".mp4", ".mov", ".avi")
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    media_url = await loop.run_in_executor(pool, _cloudinary_upload, fpath, is_video, p_cn, p_ck, p_cs, p_fld)
                if not media_url:
                    story["status"] = "error"
                    story["results"] = {"_": {"status": "error", "error": "Upload Cloudinary échoué"}}
                    _save_json(fb_sf, fb_scheduled)
                    continue
                results = {}
                for n, acc_id in enumerate(story.get("account_ids", [])):
                    acc = next((a for a in fb_accounts if a["id"] == acc_id), None)
                    uname = acc["username"] if acc else acc_id
                    dt_offset = (datetime.fromisoformat(story["scheduled_at"]) + timedelta(minutes=n)).isoformat()
                    with concurrent.futures.ThreadPoolExecutor() as pool2:
                        ok, msg = await loop.run_in_executor(
                            pool2, _oneup_fb_schedule, media_url, is_video, acc_id, dt_offset, story.get("caption", ""), p_oneup, p_cat)
                    results[acc_id] = {"username": uname, "status": "done" if ok else "error", "msg": msg}
                story["results"] = results
                ss = [r["status"] for r in results.values()]
                story["status"] = "done" if all(s == "done" for s in ss) else "error" if all(s == "error" for s in ss) else "partial"
                _save_json(fb_sf, fb_scheduled)
                print(f"[FB][{prof.get('name','?')}] {story['filename']} → {story['status']}", flush=True)
        await asyncio.sleep(30)

@app.get("/api/stats/live")
async def api_stats_live():
    """Récupère TOUTES les stories actives de chaque compte Telegram via Telethon
    (y compris celles publiées manuellement, hors dashboard).
    Retourne vues en temps réel."""
    from telethon.tl.functions.stories import GetPeerStoriesRequest
    from telethon.tl.types import InputPeerSelf

    async def _fetch_one(acc: dict) -> list[dict]:
        acc_id = acc["id"]
        try:
            client = await _get_client(acc_id)
            resp   = await client(GetPeerStoriesRequest(peer=InputPeerSelf()))
            stories = resp.stories.stories if resp and resp.stories else []
            out = []
            for st in stories:
                v_obj     = getattr(st, "views", None)
                views     = getattr(v_obj, "views_count",     0) or 0
                reactions = getattr(v_obj, "reactions_count", 0) or 0
                forwards  = getattr(v_obj, "forwards_count",  0) or 0
                date_s    = st.date.isoformat()        if getattr(st, "date",        None) else None
                exp_s     = st.expire_date.isoformat() if getattr(st, "expire_date", None) else None
                out.append({
                    "acc_id":    acc_id,
                    "acc_name":  acc.get("name", acc_id),
                    "story_id":  st.id,
                    "views":     views,
                    "reactions": reactions,
                    "forwards":  forwards,
                    "date":      date_s,
                    "expire":    exp_s,
                })
            return out
        except Exception as e:
            return [{"acc_id": acc_id, "acc_name": acc.get("name", acc_id),
                     "error": str(e)[:150]}]

    # Tous les comptes en parallèle
    chunks = await asyncio.gather(*[_fetch_one(a) for a in _accounts], return_exceptions=False)
    result = [item for chunk in chunks for item in chunk]
    return result

_REVENUE_FILE = _DATA_DIR / "revenues.json"
def _load_revenues():
    if _REVENUE_FILE.exists():
        try: return json.loads(_REVENUE_FILE.read_text("utf-8"))
        except: pass
    return []
def _save_revenues(data): _REVENUE_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),"utf-8")

@app.get("/api/revenue")
async def api_revenue_get():
    return _load_revenues()

@app.post("/api/revenue")
async def api_revenue_post(req: Request):
    body = await req.json()
    entries = _load_revenues()
    entry = {"id": str(uuid.uuid4())[:8], "date": body.get("date",""), "amount": float(body.get("amount",0)),
             "source": body.get("source",""), "note": body.get("note",""), "created_at": datetime.now().isoformat()}
    entries.append(entry)
    _save_revenues(entries)
    return entry

@app.delete("/api/revenue/{rid}")
async def api_revenue_delete(rid: str):
    entries = [e for e in _load_revenues() if e.get("id") != rid]
    _save_revenues(entries)
    return {"ok": True}

@app.get("/api/status")
async def api_status():
    return {
        "pending":  sum(1 for s in _scheduled if s["status"]=="pending"),
        "done":     sum(1 for s in _scheduled if s["status"]=="done"),
        "accounts": len(_accounts),
        "playlists":len(_playlists),
    }

# ─────────────────────────────────────────────────────────────────────────────
#  Image → 9:16 cover
# ─────────────────────────────────────────────────────────────────────────────
def _prepare_story_image(fpath: Path) -> Path:
    from PIL import Image
    W,H = 1080,1920
    img = Image.open(fpath).convert("RGB")
    w,h = img.size
    ratio = max(W/w, H/h)
    nw,nh = int(w*ratio), int(h*ratio)
    img_r = img.resize((nw,nh), Image.LANCZOS)
    x,y = (nw-W)//2, (nh-H)//2
    out = img_r.crop((x,y,x+W,y+H))
    p = fpath.parent/f"_story_{fpath.stem}.jpg"
    out.save(p,"JPEG",quality=95)
    return p

# ─────────────────────────────────────────────────────────────────────────────
#  Poster
# ─────────────────────────────────────────────────────────────────────────────
async def _post_to_account(fpath: Path, acc_id: str, accounts_list: list | None = None) -> dict:
    from telethon.tl.functions.stories import SendStoryRequest
    from telethon.tl.types import InputPrivacyValueAllowAll, InputMediaUploadedPhoto, InputPeerSelf
    client   = await _get_client(acc_id, accounts_list)
    uploaded = await client.upload_file(str(fpath))
    result   = await client(SendStoryRequest(
        peer=InputPeerSelf(), media=InputMediaUploadedPhoto(file=uploaded),
        privacy_rules=[InputPrivacyValueAllowAll()], period=86400,
    ))
    story_id = None
    try: story_id = result.updates[0].story.id if result and result.updates else None
    except: pass
    return {"status":"done","sent_at":datetime.now(PARIS_TZ).isoformat(),"story_id":story_id}

async def _get_story_views(acc_id: str, story_id: int) -> int | None:
    try:
        from telethon.tl.functions.stories import GetStoriesViewsRequest
        client = await _get_client(acc_id)
        r = await client(GetStoriesViewsRequest(id=[story_id]))
        return r.views[0].views_count if r and r.views else None
    except Exception as e:
        print(f"[VIEWS] {acc_id}/{story_id}: {e}", flush=True)
        return None

async def _post_one(story: dict, stories_list: list | None = None, sched_file_: Path | None = None, accounts_list: list | None = None):
    sl = stories_list if stories_list is not None else _scheduled
    sf = sched_file_ if sched_file_ is not None else SCHED_FILE
    al = accounts_list if accounts_list is not None else _accounts
    story["status"] = "posting"; _save_json(sf, sl)
    fpath = UPLOAD_DIR/story["filename"]
    if not fpath.exists():
        story["status"]="error"; story["results"]={"_":{"status":"error","error":"Fichier introuvable"}}
        _save_json(sf, sl); return
    tmp = None
    try:
        tmp = _prepare_story_image(fpath)
        up  = tmp
    except Exception as e:
        print(f"[STORY] Pillow: {e}",flush=True); up = fpath
    results = {}
    for acc_id in (story.get("account_ids") or [a["id"] for a in al]):
        acc  = next((a for a in al if a["id"]==acc_id), None)
        name = acc["name"] if acc else acc_id
        try:
            results[acc_id] = await _post_to_account(up, acc_id, al)
            print(f"[STORY] ✓ {story['filename']} → {name}",flush=True)
        except Exception as e:
            results[acc_id] = {"status":"error","error":str(e)}
            print(f"[STORY] ✗ {story['filename']} → {name}: {e}",flush=True)
    if tmp and tmp.exists(): tmp.unlink(missing_ok=True)
    story["results"] = results
    ss = [r["status"] for r in results.values()]
    story["status"] = "done" if all(s=="done" for s in ss) else "error" if all(s=="error" for s in ss) else "partial"
    _save_json(sf, sl)

async def _scheduler_loop():
    await asyncio.sleep(5)
    while True:
        now = datetime.now(PARIS_TZ)
        try:
            profs = _load_profiles()
        except Exception:
            profs = []
        for prof in profs:
            pid = prof["id"]
            pdir = _get_profile_data_dir(pid)
            sf = pdir / "scheduled_stories.json"
            if not sf.exists():
                continue
            try:
                stories = _load_json(sf, [])
                accounts = _load_json(pdir / "story_accounts.json", [])
            except Exception:
                continue
            for story in list(stories):
                if story["status"] != "pending": continue
                try:
                    dt = datetime.fromisoformat(story["scheduled_at"])
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=PARIS_TZ)
                    if now >= dt:
                        asyncio.create_task(_post_one(story, stories, sf, accounts))
                except Exception as e:
                    print(f"[SCHED][{prof.get('name','?')}] {e}", flush=True)
        await asyncio.sleep(30)

def _recover_orphan_sessions():
    """Réinjecte dans _accounts les fichiers .session du dossier du profil actif uniquement.
    Ignore les sessions marquées .pending (ajout abandonné en cours).
    Nettoie les fichiers .session abandonnés (marqués .pending depuis >1h)."""
    import time
    existing_ids = {a["id"] for a in _accounts}
    recovered = 0
    pdir = _get_profile_data_dir()
    for sess_file in sorted(pdir.glob("session_story_*.session")):
        acc_id = sess_file.stem[len("session_story_"):]
        if not acc_id or acc_id in existing_ids:
            continue
        pending_marker = sess_file.parent / (sess_file.stem + ".pending")
        if pending_marker.exists():
            # Session en cours d'ajout ou abandonnée : nettoyer si >1h
            age = time.time() - pending_marker.stat().st_mtime
            if age > 3600:
                try:
                    sess_file.unlink(missing_ok=True)
                    (Path(str(sess_file) + "-journal")).unlink(missing_ok=True)
                    pending_marker.unlink(missing_ok=True)
                    print(f"[CLEANUP] Session abandonnée supprimée : {acc_id}", flush=True)
                except Exception:
                    pass
            else:
                print(f"[SKIP] Session en attente de vérification : {acc_id}", flush=True)
            continue
        session_path = str(sess_file.parent / sess_file.stem)
        _accounts.append({"id": acc_id, "session_file": session_path,
                           "name": f"Compte {acc_id[:8]}", "phone": "?"})
        existing_ids.add(acc_id)
        recovered += 1
        print(f"[RECOVER] Session orpheline réinjectée : {acc_id}", flush=True)
    if recovered:
        _save_json(ACCOUNTS_FILE, _accounts)
    return recovered

async def _tg_keepalive_loop():
    """Reconnecte automatiquement les comptes Telegram déconnectés (tous profils)."""
    from telethon import TelegramClient
    await asyncio.sleep(60)  # Laisser le démarrage se terminer
    while True:
        try:
            profs = _load_profiles()
            for prof in profs:
                pdir = _get_profile_data_dir(prof["id"])
                accs_file = pdir / "story_accounts.json"
                if not accs_file.exists():
                    continue
                accs = _load_json(accs_file, [])
                for acc in accs:
                    acc_id = acc.get("id")
                    session_file = acc.get("session_file", "")
                    if not acc_id or not session_file:
                        continue
                    if not Path(session_file + ".session").exists():
                        continue
                    try:
                        async with _tg_lock:
                            if acc_id not in _clients:
                                _clients[acc_id] = TelegramClient(session_file, API_ID, API_HASH)
                            c = _clients[acc_id]
                            if not c.is_connected():
                                await c.connect()
                        if c.is_connected() and not await c.is_user_authorized():
                            print(f"[KEEPALIVE] Session expirée : {acc.get('name', acc_id)} — reconnexion manuelle requise", flush=True)
                    except Exception as e:
                        print(f"[KEEPALIVE] {acc_id}: {e}", flush=True)
        except Exception as e:
            print(f"[KEEPALIVE] Erreur boucle: {e}", flush=True)
        await asyncio.sleep(300)  # Vérifier toutes les 5 minutes


@app.on_event("startup")
async def on_startup():
    global _scheduled
    # Restaurer le profil actif sauvegardé dès le démarrage
    active_id = _get_active_profile_id()
    if active_id:
        _reload_for_profile(active_id)
        print(f"[STARTUP] Profil actif restauré : {active_id}", flush=True)
    # Réinjecter les sessions orphelines (comptes effacés par accident)
    n = _recover_orphan_sessions()
    if n: print(f"[STARTUP] {n} session(s) orpheline(s) récupérée(s)", flush=True)

    # Fusionner les doublons : même filename + même scheduled_at → un seul item avec tous les comptes
    merged, seen = [], {}
    for s in _scheduled:
        key = (s["filename"], s["scheduled_at"])
        if key in seen:
            for acc in (s.get("account_ids") or []):
                if acc not in seen[key]["account_ids"]:
                    seen[key]["account_ids"].append(acc)
        else:
            seen[key] = s
            merged.append(s)
    if len(merged) < len(_scheduled):
        _scheduled = merged
        _save_json(SCHED_FILE, _scheduled)
        print(f"[STARTUP] {len(_scheduled)} doublons fusionnés", flush=True)
    asyncio.create_task(_scheduler_loop())
    asyncio.create_task(_snapshot_views_loop())
    asyncio.create_task(_snap_scheduler_loop())
    asyncio.create_task(_ig_scheduler_loop())
    asyncio.create_task(_fb_scheduler_loop())
    asyncio.create_task(_tg_keepalive_loop())

# ══════════════════════════════════════════════════════════════════════════════
#  SNAPCHAT — One Up + Cloudinary
# ══════════════════════════════════════════════════════════════════════════════

ONEUP_API_KEY         = "a596437209bb16ce9d73"
CLOUDINARY_CLOUD_NAME = "donimprgr"
CLOUDINARY_API_KEY_CL = "588748259662185"
CLOUDINARY_API_SECRET = "x0IrhR0Y06zAXQU2uo_ktUizigI"
CLOUDINARY_FOLDER     = "default"   # dossier Cloudinary = nom du profil (rempli au chargement)
CATEGORY_ID_SNAP      = "177234"
CLAUDE_API_KEY        = os.environ.get("CLAUDE_API_KEY", "REMOVED")
SNAP_SCHED_FILE       = _DATA_DIR / "snap_scheduled.json"
_snap_scheduled: list[dict] = _load_json(SNAP_SCHED_FILE, [])
SNAP_BLOCKED_FILE     = _DATA_DIR / "snap_blocked_until.json"
def _load_snap_blocked() -> dict: return _load_json(SNAP_BLOCKED_FILE, {})
def _save_snap_blocked(d: dict): _save_json(SNAP_BLOCKED_FILE, d)
def _planning_file(platform: str) -> Path:
    """Returns the planning JSON file path for the active profile."""
    return _get_profile_data_dir() / f"{platform}_plannings.json"

SNAP_ACCOUNTS = [
    {"username": "la_petite2003",   "id": "24c727b3-1030-40ef-8b69-d1eb279823e2"},
    {"username": "bby_louloutee",   "id": "71486fff-253b-4210-b3f1-fc95a99f0cd8"},
    {"username": "poulette95",      "id": "8054ecd2-41d8-4a41-be4c-b742948e9ca5"},
    {"username": "pauline.onlinee", "id": "9036dd0e-7107-4c18-a752-7f1579ac69fc"},
    {"username": "blm.pauline",     "id": "1d993bbe-0734-4813-ab62-73a14cc36868"},
    {"username": "pauline_esp",     "id": "d7189755-4eeb-458d-b577-fd8ea4fb01ab"},
]

@app.get("/api/tg/plannings")
async def get_tg_plannings():
    return _load_json(_planning_file("tg"), [])

@app.post("/api/tg/plannings")
async def save_tg_planning(req: dict = Body(...)):
    name   = req.get("name", "").strip()
    photos = req.get("photos", [])
    if not name:   raise HTTPException(400, "Nom requis")
    if not photos: raise HTTPException(400, "Aucune photo")
    entry = {"id": uuid.uuid4().hex[:8], "name": name, "photos": photos,
             "created_at": datetime.now().isoformat(), "count": len(photos)}
    f = _planning_file("tg"); plans = _load_json(f, []); plans.append(entry); _save_json(f, plans)
    return entry

@app.delete("/api/tg/plannings/{pid}")
async def delete_tg_planning(pid: str):
    f = _planning_file("tg"); plans = [p for p in _load_json(f, []) if p["id"] != pid]; _save_json(f, plans)
    return {"ok": True}

@app.patch("/api/tg/plannings/{pid}")
async def rename_tg_planning(pid: str, req: dict = Body(...)):
    name = req.get("name", "").strip()
    if not name: raise HTTPException(400, "Nom requis")
    f = _planning_file("tg"); plans = _load_json(f, [])
    for p in plans:
        if p["id"] == pid: p["name"] = name
    _save_json(f, plans)
    return {"ok": True}

@app.patch("/api/tg/plannings/reorder")
async def reorder_tg_plannings(req: dict = Body(...)):
    order = {id: i for i, id in enumerate(req.get("ids", []))}
    f = _planning_file("tg"); plans = _load_json(f, []); plans.sort(key=lambda p: order.get(p["id"], 9999)); _save_json(f, plans)
    return {"ok": True}

@app.get("/api/snap/plannings")
async def get_snap_plannings():
    return _load_json(_planning_file("snap"), [])

@app.post("/api/snap/plannings")
async def save_snap_planning(req: dict = Body(...)):
    name   = req.get("name", "").strip()
    photos = req.get("photos", [])
    if not name:   raise HTTPException(400, "Nom requis")
    if not photos: raise HTTPException(400, "Aucune photo")
    entry = {"id": uuid.uuid4().hex[:8], "name": name, "photos": photos,
             "created_at": datetime.now().isoformat(), "count": len(photos)}
    f = _planning_file("snap"); plans = _load_json(f, []); plans.append(entry); _save_json(f, plans)
    return entry

@app.delete("/api/snap/plannings/{pid}")
async def delete_snap_planning(pid: str):
    f = _planning_file("snap"); plans = [p for p in _load_json(f, []) if p["id"] != pid]; _save_json(f, plans)
    return {"ok": True}

@app.patch("/api/snap/plannings/{pid}")
async def rename_snap_planning(pid: str, req: dict = Body(...)):
    name = req.get("name", "").strip()
    if not name: raise HTTPException(400, "Nom requis")
    f = _planning_file("snap"); plans = _load_json(f, [])
    for p in plans:
        if p["id"] == pid: p["name"] = name
    _save_json(f, plans)
    return {"ok": True}

@app.patch("/api/snap/plannings/reorder")
async def reorder_snap_plannings(req: dict = Body(...)):
    order = {id: i for i, id in enumerate(req.get("ids", []))}
    f = _planning_file("snap"); plans = _load_json(f, []); plans.sort(key=lambda p: order.get(p["id"], 9999)); _save_json(f, plans)
    return {"ok": True}

@app.get("/api/ig/plannings")
async def get_ig_plannings():
    return _load_json(_planning_file("ig"), [])

@app.post("/api/ig/plannings")
async def save_ig_planning(req: dict = Body(...)):
    name   = req.get("name", "").strip()
    photos = req.get("photos", [])
    if not name:   raise HTTPException(400, "Nom requis")
    if not photos: raise HTTPException(400, "Aucune photo")
    entry = {"id": uuid.uuid4().hex[:8], "name": name, "photos": photos,
             "created_at": datetime.now().isoformat(), "count": len(photos)}
    f = _planning_file("ig"); plans = _load_json(f, []); plans.append(entry); _save_json(f, plans)
    return entry

@app.delete("/api/ig/plannings/{pid}")
async def delete_ig_planning(pid: str):
    f = _planning_file("ig"); plans = [p for p in _load_json(f, []) if p["id"] != pid]; _save_json(f, plans)
    return {"ok": True}

@app.patch("/api/ig/plannings/{pid}")
async def rename_ig_planning(pid: str, req: dict = Body(...)):
    name = req.get("name", "").strip()
    if not name: raise HTTPException(400, "Nom requis")
    f = _planning_file("ig"); plans = _load_json(f, [])
    for p in plans:
        if p["id"] == pid: p["name"] = name
    _save_json(f, plans)
    return {"ok": True}

@app.patch("/api/ig/plannings/reorder")
async def reorder_ig_plannings(req: dict = Body(...)):
    order = {id: i for i, id in enumerate(req.get("ids", []))}
    f = _planning_file("ig"); plans = _load_json(f, []); plans.sort(key=lambda p: order.get(p["id"], 9999)); _save_json(f, plans)
    return {"ok": True}

# ── Facebook Plannings (Médias) ────────────────────────────────────────────────
@app.get("/api/fb/plannings")
async def get_fb_plannings_media():
    return _load_json(_planning_file("fb"), [])

@app.post("/api/fb/plannings")
async def save_fb_planning(req: dict = Body(...)):
    name   = req.get("name", "").strip()
    photos = req.get("photos", [])
    if not name:   raise HTTPException(400, "Nom requis")
    if not photos: raise HTTPException(400, "Aucune photo")
    entry = {"id": uuid.uuid4().hex[:8], "name": name, "photos": photos,
             "created_at": datetime.now().isoformat(), "count": len(photos)}
    f = _planning_file("fb"); plans = _load_json(f, []); plans.append(entry); _save_json(f, plans)
    return entry

@app.delete("/api/fb/plannings/{pid}")
async def delete_fb_planning(pid: str):
    f = _planning_file("fb"); plans = [p for p in _load_json(f, []) if p["id"] != pid]; _save_json(f, plans)
    return {"ok": True}

@app.patch("/api/fb/plannings/{pid}")
async def rename_fb_planning(pid: str, req: dict = Body(...)):
    name = req.get("name", "").strip()
    if not name: raise HTTPException(400, "Nom requis")
    f = _planning_file("fb"); plans = _load_json(f, [])
    for p in plans:
        if p["id"] == pid: p["name"] = name
    _save_json(f, plans)
    return {"ok": True}

@app.patch("/api/fb/plannings/reorder")
async def reorder_fb_plannings(req: dict = Body(...)):
    order = {id: i for i, id in enumerate(req.get("ids", []))}
    f = _planning_file("fb"); plans = _load_json(f, []); plans.sort(key=lambda p: order.get(p["id"], 9999)); _save_json(f, plans)
    return {"ok": True}

def _analyze_photo_ia(filepath: Path) -> dict:
    import base64 as _b64, requests as _req
    default = {"moment_journee":"apres_midi","ambiance":"autre","tenue_type":"neutre",
               "fatigue":False,"alcool_visible":False,"fait_la_fete":False,
               "nourriture_presente":False,"personne_visible":False,"type_fichier":"photo"}
    try:
        with open(filepath, "rb") as f:
            img_b64 = _b64.b64encode(f.read()).decode()
        ext = filepath.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        prompt = ('Analyse cette photo et reponds UNIQUEMENT en JSON :\n'
                  '{"personne_visible":true,"moment_journee":"matin/apres_midi/soir/nuit/interieur_neutre",'
                  '"ambiance":"detente/sortie/apero/repas/sport/plage/maison/fete/autre",'
                  '"tenue_type":"decontracte/habille/pyjama/maillot/neutre",'
                  '"tenue_description":"ex: hoodie noir jogging",'
                  '"fatigue":false,"alcool_visible":false,"fait_la_fete":false,"nourriture_presente":false}')
        r = _req.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":CLAUDE_API_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":"claude-haiku-4-5-20251001","max_tokens":300,"messages":[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":mime,"data":img_b64}},
                {"type":"text","text":prompt}
            ]}]}, timeout=30)
        data = r.json()
        txt = data.get("content",[{}])[0].get("text","{}").replace("```json","").replace("```","").strip()
        result = {**default, **json.loads(txt)}
        result["type_fichier"] = "photo"
        return result
    except Exception:
        return default

def _suggest_datetime(analyse: dict, day_offset: int = 0) -> str:
    import random as _rnd
    base = (datetime.now() + timedelta(days=1+day_offset)).replace(second=0, microsecond=0)
    if analyse.get("fait_la_fete") or analyse.get("alcool_visible"):
        h, m = _rnd.randint(1,4), _rnd.randint(0,59)
    elif analyse.get("moment_journee") in ("nuit","soir") or analyse.get("tenue_type")=="pyjama" or analyse.get("fatigue"):
        h, m = _rnd.choice([8,21,22]), _rnd.randint(0,59)
    elif analyse.get("moment_journee") == "matin":
        h, m = _rnd.choice([8,9,10]), _rnd.randint(0,59)
    else:
        h, m = _rnd.randint(12,21), _rnd.randint(0,59)
    return base.replace(hour=h, minute=m).strftime("%Y-%m-%dT%H:%M")

@app.post("/api/snap/analyze")
async def analyze_snap_photos(req: dict = Body(...)):
    filenames = req.get("filenames", [])
    loop = asyncio.get_event_loop()
    results = []
    for i, fn in enumerate(filenames):
        filepath = UPLOAD_DIR / fn
        if not filepath.exists():
            continue
        is_video = filepath.suffix.lower() in (".mp4",".mov",".avi",".mkv")
        if is_video:
            analyse = {"moment_journee":"apres_midi","ambiance":"autre","tenue_type":"neutre",
                       "fatigue":False,"alcool_visible":False,"fait_la_fete":False,
                       "nourriture_presente":False,"personne_visible":False,"type_fichier":"video"}
        else:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                analyse = await loop.run_in_executor(pool, _analyze_photo_ia, filepath)
        dt_suggested = _suggest_datetime(analyse, day_offset=i)
        results.append({"filename": fn, "analyse": analyse, "suggested_dt": dt_suggested})
    return results

def _cloudinary_upload(filepath: Path, is_video: bool, cloud_name: str | None = None, api_key_cl: str | None = None, api_secret: str | None = None, folder: str | None = None) -> str | None:
    import requests as _req
    _cn  = cloud_name or CLOUDINARY_CLOUD_NAME
    _key = api_key_cl or CLOUDINARY_API_KEY_CL
    _sec = api_secret or CLOUDINARY_API_SECRET
    _fld = folder     or CLOUDINARY_FOLDER
    nom        = filepath.stem.replace(" ", "_")
    ts         = str(int(_time.time()))
    public_id  = f"{_fld}/snap_{nom}_{ts[-5:]}"
    to_sign    = f"public_id={public_id}&timestamp={ts}"
    sig        = hashlib.sha1((to_sign + _sec).encode()).hexdigest()
    rtype      = "video" if is_video else "image"
    url        = f"https://api.cloudinary.com/v1_1/{_cn}/{rtype}/upload"
    with open(filepath, "rb") as f:
        r = _req.post(url, data={
            "api_key": _key,
            "timestamp": ts, "signature": sig, "public_id": public_id,
        }, files={"file": f}, timeout=120)
    if r.status_code != 200:
        print(f"[!] Cloudinary {r.status_code} (cloud='{_cn}'): {r.text[:150]}")
        return None
    url = r.json().get("secure_url") or ""
    # Forcer le format MP4 pour les vidéos (MOV, AVI, etc. → MP4)
    if is_video and url:
        import re as _re_url
        url = _re_url.sub(r'\.(mov|avi|mkv|m4v|3gp|webm)$', '.mp4', url, flags=_re_url.IGNORECASE)
    return url or None

def _oneup_schedule(media_url: str, is_video: bool, account_id: str, dt_str: str, oneup_key: str | None = None, category_id: str | None = None) -> tuple[bool, str]:
    import requests as _req
    dt_obj = datetime.fromisoformat(dt_str)
    dt_fmt = dt_obj.strftime("%Y-%m-%d %H:%M")
    endpoint = "schedulevideopost" if is_video else "scheduleimagepost"
    key = "video_url" if is_video else "image_url"
    params = {
        "apiKey": oneup_key or ONEUP_API_KEY,
        "category_id": category_id or CATEGORY_ID_SNAP,
        "social_network_id": f'["{account_id}"]',
        "scheduled_date_time": dt_fmt,
        "content": "",
        key: media_url,
    }
    try:
        r = _req.post(f"https://www.oneupapp.io/api/{endpoint}", params=params, timeout=30)
        try:
            ok = r.status_code in (200, 201) and not r.json().get("error")
        except Exception:
            ok = r.status_code in (200, 201)
        return ok, r.text[:200]
    except Exception as e:
        return False, str(e)

@app.get("/api/snap/accounts")
async def get_snap_accounts():
    return SNAP_ACCOUNTS

@app.get("/api/snap/scheduled")
async def get_snap_scheduled():
    return _load_json(SNAP_SCHED_FILE, [])

@app.delete("/api/snap/scheduled")
async def delete_all_snap_scheduled():
    global _snap_scheduled
    before = len(_snap_scheduled)
    _snap_scheduled = [s for s in _snap_scheduled if s["status"] != "pending"]
    _save_json(SNAP_SCHED_FILE, _snap_scheduled)
    return {"deleted": before - len(_snap_scheduled)}

@app.delete("/api/snap/scheduled/{sid}")
async def delete_snap_scheduled(sid: str):
    global _snap_scheduled
    _snap_scheduled = [s for s in _snap_scheduled if s["id"] != sid]
    _save_json(SNAP_SCHED_FILE, _snap_scheduled)
    return {"ok": True}

@app.post("/api/snap/schedule")
async def schedule_snap(req: dict = Body(...)):
    """Enregistre localement — l'envoi à OneUp se fait AU MOMENT de l'heure programmée
    via _snap_scheduler_loop. Aucune limite de slots OneUp."""
    photos      = req.get("photos", [])
    account_ids = req.get("account_ids", [])
    playlist_name = req.get("playlist_name", "")
    if not photos:      raise HTTPException(400, "Aucune photo")
    if not account_ids: raise HTTPException(400, "Aucun compte sélectionné")

    added = 0
    for p in photos:
        filename     = p["filename"]
        scheduled_at = p["scheduled_at"]
        filepath     = UPLOAD_DIR / filename
        if not filepath.exists():
            continue
        sid = uuid.uuid4().hex[:8]
        entry = {
            "id": sid,
            "filename": filename,
            "scheduled_at": scheduled_at,
            "account_ids": account_ids,
            "playlist_name": playlist_name,
            "status": "pending",   # sera traité par _snap_scheduler_loop
            "results": {},
        }
        _snap_scheduled.append(entry)
        added += 1

    _save_json(SNAP_SCHED_FILE, _snap_scheduled)
    return {"ok": True, "count": added}

SNAP_SPOTLIGHT_FILE  = _DATA_DIR / "snap_spotlight.json"
_snap_spotlight: list[dict] = _load_json(SNAP_SPOTLIGHT_FILE, [])

IG_ACCOUNTS: list[dict] = []  # rempli par _reload_for_profile
CATEGORY_ID_IG: str = ""
IG_SCHED_FILE = _DATA_DIR / "instagram_scheduled.json"
_ig_scheduled: list[dict] = _load_json(IG_SCHED_FILE, [])

FB_ACCOUNTS: list[dict] = []  # rempli par _reload_for_profile
CATEGORY_ID_FB: str = ""
FB_SCHED_FILE = _DATA_DIR / "facebook_scheduled.json"
_fb_scheduled: list[dict] = _load_json(FB_SCHED_FILE, [])
_VIDEO_EXT = (".mp4", ".mov", ".avi", ".m4v", ".3gp", ".webm")
SPOTLIGHT_POOL_DIR   = Path(os.environ.get("SPOTLIGHT_POOL_DIR",
    r"C:\Users\MAEL\Downloads\Telegram Desktop\MYM PAULINE\AUTO SPOTLIGHT\3 - A POSTER"))
SPOTLIGHT_POSTED_DIR = Path(os.environ.get("SPOTLIGHT_POSTED_DIR",
    r"C:\Users\MAEL\Downloads\Telegram Desktop\MYM PAULINE\AUTO SPOTLIGHT\4 - DEJA POSTEES"))

def _story_convert(src: Path) -> Path:
    try:
        from PIL import Image as _Img
        img = _Img.open(src).convert("RGB")
        W, H = img.size
        tgt = 9 / 16
        cur = W / H
        if cur > tgt:
            nw = int(H * tgt); l = (W - nw) // 2; img = img.crop((l, 0, l + nw, H))
        elif cur < tgt:
            nh = int(W / tgt); t = (H - nh) // 2; img = img.crop((0, t, W, t + nh))
        img = img.resize((1080, 1920), _Img.LANCZOS)
        out = src.parent / (src.stem + "_s9x16" + src.suffix)
        img.save(out, quality=92)
        return out
    except Exception:
        return src

def _oneup_spotlight(media_url: str, account_id: str, dt_str: str, description: str = "") -> tuple[bool, str]:
    import requests as _req, json as _json
    dt_obj = datetime.fromisoformat(dt_str)
    dt_fmt = dt_obj.strftime("%Y-%m-%d %H:%M")
    params = {
        "apiKey": ONEUP_API_KEY,
        "category_id": CATEGORY_ID_SNAP,
        "social_network_id": f'["{account_id}"]',
        "scheduled_date_time": dt_fmt,
        "content": description,
        "video_url": media_url,
        "snapchat": _json.dumps({"isSpotLight": True}),
    }
    try:
        r = _req.post("https://www.oneupapp.io/api/schedulevideopost", params=params, timeout=60)
        ok = r.status_code in (200, 201)
        return ok, r.text[:200]
    except Exception as e:
        return False, str(e)

@app.get("/api/snap/spotlight")
async def get_snap_spotlight():
    return _snap_spotlight

@app.get("/api/snap/spotlight/pool")
async def get_spotlight_pool():
    SPOTLIGHT_POOL_DIR.mkdir(parents=True, exist_ok=True)
    vids = sorted(f for f in SPOTLIGHT_POOL_DIR.iterdir() if f.suffix.lower() in _VIDEO_EXT)
    return {"count": len(vids), "path": str(SPOTLIGHT_POOL_DIR)}

@app.post("/api/snap/spotlight/pool/upload")
async def upload_spotlight_pool(files: list[UploadFile] = File(...)):
    SPOTLIGHT_POOL_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        if Path(f.filename).suffix.lower() not in _VIDEO_EXT:
            continue
        dest = SPOTLIGHT_POOL_DIR / Path(f.filename).name
        content = await f.read()
        dest.write_bytes(content)
        saved.append(f.filename)
    total = len([x for x in SPOTLIGHT_POOL_DIR.iterdir() if x.suffix.lower() in _VIDEO_EXT])
    return {"uploaded": len(saved), "files": saved, "pool_total": total}

SPOTLIGHT_BLOCKED_FILE = _DATA_DIR / "spotlight_blocked_until.json"
def _load_spl_blocked() -> dict: return _load_json(SPOTLIGHT_BLOCKED_FILE, {})
def _save_spl_blocked(d: dict): _save_json(SPOTLIGHT_BLOCKED_FILE, d)

# ── Profile reload (all globals in one shot) ──────────────────────────────────
def _reload_for_profile(profile_id: str):
    global ONEUP_API_KEY, CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY_CL, CLOUDINARY_API_SECRET
    global CLOUDINARY_FOLDER
    global SNAP_ACCOUNTS, SPOTLIGHT_POOL_DIR, CATEGORY_ID_SNAP
    global SCHED_FILE, ACCOUNTS_FILE, PLAYLIST_FILE
    global SNAP_SCHED_FILE, SNAP_BLOCKED_FILE, SNAP_SPOTLIGHT_FILE, SPOTLIGHT_BLOCKED_FILE
    global _REVENUE_FILE
    global _accounts, _scheduled, _playlists, _snap_scheduled, _snap_spotlight
    global IG_ACCOUNTS, CATEGORY_ID_IG, IG_SCHED_FILE, _ig_scheduled
    global FB_ACCOUNTS, CATEGORY_ID_FB, FB_SCHED_FILE, _fb_scheduled
    global _clients, _phone_hashes, _pending_phone

    profs = _load_profiles()
    prof  = next((p for p in profs if p["id"] == profile_id), None)
    if not prof:
        return

    ONEUP_API_KEY         = prof.get("oneup_api_key",         ONEUP_API_KEY)
    CLOUDINARY_CLOUD_NAME = prof.get("cloudinary_cloud_name", CLOUDINARY_CLOUD_NAME)
    CLOUDINARY_API_KEY_CL = prof.get("cloudinary_api_key",    CLOUDINARY_API_KEY_CL)
    CLOUDINARY_API_SECRET = prof.get("cloudinary_api_secret", CLOUDINARY_API_SECRET)
    CATEGORY_ID_SNAP      = prof.get("category_id_snap",      CATEGORY_ID_SNAP)
    SNAP_ACCOUNTS         = prof.get("snap_accounts",         [])
    import re as _re_f
    CLOUDINARY_FOLDER = _re_f.sub(r"[^A-Za-z0-9_-]", "", prof.get("name") or profile_id) or profile_id
    if prof.get("spotlight_pool_dir"):
        SPOTLIGHT_POOL_DIR = Path(prof["spotlight_pool_dir"])
    else:
        # Dossier pool automatique par profil
        SPOTLIGHT_POOL_DIR = _get_profile_data_dir(profile_id) / "spotlight_pool"

    pdir = _get_profile_data_dir(profile_id)
    SCHED_FILE             = pdir / "scheduled_stories.json"
    ACCOUNTS_FILE          = pdir / "story_accounts.json"
    PLAYLIST_FILE          = pdir / "story_playlists.json"
    SNAP_SCHED_FILE        = pdir / "snap_scheduled.json"
    SNAP_BLOCKED_FILE      = pdir / "snap_blocked_until.json"
    SNAP_SPOTLIGHT_FILE    = pdir / "snap_spotlight.json"
    SPOTLIGHT_BLOCKED_FILE = pdir / "spotlight_blocked_until.json"
    _REVENUE_FILE          = pdir / "revenues.json"

    _accounts      = _load_json(ACCOUNTS_FILE,    [])
    _scheduled     = _load_json(SCHED_FILE,        [])
    _playlists     = _load_json(PLAYLIST_FILE,     [])
    _snap_scheduled= _load_json(SNAP_SCHED_FILE,   [])
    _snap_spotlight= _load_json(SNAP_SPOTLIGHT_FILE,[])

    IG_SCHED_FILE    = pdir / "instagram_scheduled.json"
    _ig_scheduled    = _load_json(IG_SCHED_FILE, [])
    IG_ACCOUNTS      = prof.get("instagram_accounts", [])
    CATEGORY_ID_IG   = prof.get("category_id_instagram", "")

    FB_SCHED_FILE    = pdir / "facebook_scheduled.json"
    _fb_scheduled    = _load_json(FB_SCHED_FILE, [])
    FB_ACCOUNTS      = prof.get("facebook_accounts", [])
    CATEGORY_ID_FB   = prof.get("category_id_facebook", "")

    _clients.clear()
    _phone_hashes.clear()
    _pending_phone.clear()


def _init_profiles():
    profs = _load_profiles()
    if not profs:
        default = {
            "id":                    "default",
            "name":                  "Profil principal",
            "oneup_api_key":         ONEUP_API_KEY,
            "cloudinary_cloud_name": CLOUDINARY_CLOUD_NAME,
            "cloudinary_api_key":    CLOUDINARY_API_KEY_CL,
            "cloudinary_api_secret": CLOUDINARY_API_SECRET,
            "category_id_snap":      CATEGORY_ID_SNAP,
            "snap_accounts":         list(SNAP_ACCOUNTS),
            "spotlight_pool_dir":    str(SPOTLIGHT_POOL_DIR),
            "data_dir":              str(_DATA_DIR),
        }
        _save_profiles([default])
        _save_json(ACTIVE_PROFILE_FILE, {"id": "default"})
    elif not _get_active_profile_id():
        _save_json(ACTIVE_PROFILE_FILE, {"id": profs[0]["id"]})

_init_profiles()

@app.get("/api/snap/spotlight/blocked-until")
async def get_spl_blocked():
    return _load_spl_blocked()

@app.post("/api/snap/spotlight/blocked-until")
async def set_spl_blocked(req: Request):
    body    = await req.json()
    blocked = _load_spl_blocked()
    acc_id  = body.get("account_id", "")
    until   = body.get("until", "")
    if acc_id and until:
        blocked[acc_id] = until
    elif acc_id and not until:
        blocked.pop(acc_id, None)
    _save_spl_blocked(blocked)
    return blocked

@app.get("/api/snap/spotlight/next-dates")
async def get_spotlight_next_dates():
    """Retourne, pour chaque compte, le nombre de posts programmés et la prochaine date libre.
    Combine la base locale + les dates bloquées manuellement."""
    blocked = _load_spl_blocked()
    result  = []
    for acc in SNAP_ACCOUNTS:
        acc_id = acc["id"]
        taken_dates: set = set()
        # 1. Spotlights de la base locale
        for e in _snap_spotlight:
            if e.get("account_id") == acc_id and e.get("status") != "error":
                try:
                    taken_dates.add(datetime.fromisoformat(e["scheduled_at"]).date())
                except Exception:
                    pass
        # 2. Dates bloquées manuellement (programmés hors dashboard)
        manual_until_str = blocked.get(acc_id)
        if manual_until_str:
            try:
                manual_until = datetime.fromisoformat(manual_until_str).date()
                d = (datetime.now() + timedelta(days=1)).date()
                while d <= manual_until:
                    taken_dates.add(d)
                    d += timedelta(days=1)
            except Exception:
                pass
        # 3. Prochaine date libre
        check = (datetime.now() + timedelta(days=1)).date()
        while check in taken_dates:
            check += timedelta(days=1)
        last_date = max(taken_dates) if taken_dates else None
        result.append({
            "account_id":      acc_id,
            "username":        acc["username"],
            "scheduled_count": len(taken_dates),
            "last_scheduled":  str(last_date) if last_date else None,
            "next_free":       str(check),
            "manual_until":    manual_until_str or None,
        })
    return result

@app.get("/api/snap/oneup-analytics")
async def api_snap_oneup_analytics(preset: str = "last_30_days"):
    """Récupère les analytics Snapchat depuis OneUp (analyze.oneupapp.io) pour chaque compte."""
    import requests as _req

    ANALYZE_BASE = "https://analyze.oneupapp.io/api/snapchat"
    key = ONEUP_API_KEY

    def _fetch_account(acc):
        sid    = acc["id"]
        uname  = acc["username"]
        result = {"username": uname, "account_id": sid}
        # Posts public-stories
        try:
            r = _req.get(
                f"{ANALYZE_BASE}/posts",
                params={"apiKey": key, "social_network_id": sid, "preset": preset},
                timeout=12
            )
            result["posts_status"] = r.status_code
            if r.status_code == 200:
                result["posts"] = r.json()
            else:
                result["posts_error"] = r.text[:300]
        except Exception as e:
            result["posts_error"] = str(e)

        # Posts Spotlight (endpoint confirmé fonctionnel)
        try:
            r3 = _req.get(
                f"{ANALYZE_BASE}/posts",
                params={"apiKey": key, "social_network_id": sid, "preset": preset, "type": "spotlight"},
                timeout=12
            )
            if r3.status_code == 200:
                result["spotlight"] = r3.json()
        except Exception:
            pass

        # Overview (totaux)
        try:
            r2 = _req.get(
                f"{ANALYZE_BASE}/overview",
                params={"apiKey": key, "social_network_id": sid, "preset": preset},
                timeout=12
            )
            result["overview_status"] = r2.status_code
            if r2.status_code == 200:
                result["overview"] = r2.json()
            else:
                result["overview_error"] = r2.text[:300]
        except Exception as e:
            result["overview_error"] = str(e)

        return result

    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _fetch_account, acc) for acc in SNAP_ACCOUNTS]
    results = await asyncio.gather(*tasks)

    return {"preset": preset, "accounts": list(results)}


@app.get("/api/snap/oneup-posts")
async def api_snap_oneup_posts():
    """Tente de récupérer les 10 dernières publications Snapchat depuis One Up."""
    import httpx
    ONEUP_BASE = "https://www.oneupapp.io/api"
    key = ONEUP_API_KEY

    endpoints_to_try = [
        f"{ONEUP_BASE}/posts?apiKey={key}&limit=10&status=published&order=desc",
        f"{ONEUP_BASE}/posts?apiKey={key}&limit=10",
    ]

    async with httpx.AsyncClient(timeout=15) as client:
        for url in endpoints_to_try:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    posts = data if isinstance(data, list) else data.get("posts") or data.get("data") or []
                    if posts:
                        return {"ok": True, "posts": posts[:10], "endpoint": url.split("?")[0]}
            except Exception:
                continue

    return {"error": "Aucun endpoint One Up n'a répondu avec des données", "posts": []}


# ── Auth API ──────────────────────────────────────────────────────────────────
@app.post("/api/auth/login")
async def api_auth_login(req: dict = Body(...)):
    username = req.get("username", "").strip().lower()
    password = req.get("password", "").strip()
    if not username or not password:
        raise HTTPException(401, "Identifiant et mot de passe requis")
    profs = _load_profiles()
    # Match ONLY by explicit `login` field — profiles without a login field cannot log in
    prof = next((p for p in profs if
                 p.get("login", "").strip().lower() == username), None)
    if not prof:
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    pw_hash = prof.get("password_hash", "")
    if not pw_hash:
        raise HTTPException(401, "Ce profil n'a pas de mot de passe configuré — contacte l'administrateur")
    if _hash_password(password) != pw_hash:
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    pid = prof["id"]
    _reload_for_profile(pid)
    _save_json(ACTIVE_PROFILE_FILE, {"id": pid})
    token = _new_session(pid)
    resp = JSONResponse({"ok": True, "profile_id": pid, "profile_name": prof["name"], "is_admin": bool(prof.get("is_admin"))})
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_MAX_AGE)
    return resp

@app.post("/api/auth/register")
async def api_auth_register(req: dict = Body(...)):
    import uuid
    name     = req.get("name", "").strip()
    login    = req.get("login", "").strip().lower()
    password = req.get("password", "").strip()
    if not name or not login or not password:
        raise HTTPException(400, "Nom, identifiant et mot de passe requis")
    if len(password) < 6:
        raise HTTPException(400, "Le mot de passe doit faire au moins 6 caractères")
    profs = _load_profiles()
    if any(p.get("login", "").strip().lower() == login for p in profs):
        raise HTTPException(409, "Cet identifiant est déjà utilisé")
    new_pid = str(uuid.uuid4())
    new_prof = {
        "id": new_pid,
        "owner_id": new_pid,
        "name": name,
        "login": login,
        "password_hash": _hash_password(password),
        "is_admin": False,
        "accounts": [],
        "stories": [],
        "scheduled": [],
    }
    profs.append(new_prof)
    _save_profiles(profs)
    pid = new_pid
    _reload_for_profile(pid)
    _save_json(ACTIVE_PROFILE_FILE, {"id": pid})
    token = _new_session(pid)
    resp = JSONResponse({"ok": True, "profile_id": pid, "profile_name": name, "is_admin": False})
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_MAX_AGE)
    return resp

@app.post("/api/auth/logout")
async def api_auth_logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        _sessions.pop(token, None)
        _save_sessions(_sessions)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE)
    return resp

@app.get("/api/auth/check")
async def api_auth_check(request: Request):
    pid = _get_session_profile(request)
    if not pid:
        raise HTTPException(401, "Non authentifié")
    profs = _load_profiles()
    prof = next((p for p in profs if p["id"] == pid), None)
    name = prof["name"] if prof else pid
    is_admin = bool(prof.get("is_admin")) if prof else False
    return {"ok": True, "profile_id": pid, "profile_name": name, "is_admin": is_admin}

# ── Profiles API ──────────────────────────────────────────────────────────────
def _hash_pin(pin: str) -> str:
    import hashlib
    return hashlib.sha256(pin.strip().encode()).hexdigest()

@app.get("/api/profiles")
async def api_get_profiles(request: Request):
    session_pid = _get_session_profile(request)
    profs = _load_profiles()
    if session_pid:
        me = next((p for p in profs if p["id"] == session_pid), None)
        if me:
            # Premier admin = propriétaire des profils legacy sans owner_id
            first_admin_id = next((p["id"] for p in profs if p.get("is_admin")), None)
            def _owns(p):
                oid = p.get("owner_id")
                if oid:
                    return oid == session_pid
                # Profil legacy sans owner_id → appartient au premier admin
                return session_pid == first_admin_id
            profs = [p for p in profs if _owns(p)]
    safe = [{**p,
             "pin_set": bool(p.get("pin_hash")),
             "password_set": bool(p.get("password_hash")),
             "is_admin": bool(p.get("is_admin")),
             "pin_hash": None,
             "password_hash": None} for p in profs]
    return {"profiles": safe, "active_id": _get_active_profile_id()}

@app.post("/api/profiles")
async def api_create_profile(request: Request, req: dict = Body(...)):
    session_pid = _get_session_profile(request)
    profs  = _load_profiles()
    pid    = str(uuid.uuid4())[:8]
    new_p  = {
        "id":                    pid,
        "owner_id":              session_pid or pid,
        "name":                  req.get("name", "Nouveau profil").strip(),
        "oneup_api_key":         req.get("oneup_api_key", ""),
        "cloudinary_cloud_name": req.get("cloudinary_cloud_name", ""),
        "cloudinary_api_key":    req.get("cloudinary_api_key", ""),
        "cloudinary_api_secret": req.get("cloudinary_api_secret", ""),
        "category_id_snap":      req.get("category_id_snap", ""),
        "snap_accounts":         req.get("snap_accounts", []),
        "spotlight_pool_dir":    req.get("spotlight_pool_dir", ""),
    }
    profs.append(new_p)
    _save_profiles(profs)
    return new_p

@app.put("/api/profiles/{pid}")
async def api_update_profile(pid: str, req: dict = Body(...)):
    profs = _load_profiles()
    idx   = next((i for i, p in enumerate(profs) if p["id"] == pid), None)
    if idx is None:
        raise HTTPException(404, "Profil introuvable")
    # Handle PIN separately (never update pin_hash via the general update)
    if "pin" in req:
        pin_val = str(req.pop("pin", "")).strip()
        if pin_val:
            profs[idx]["pin_hash"] = _hash_pin(pin_val)
        else:
            profs[idx].pop("pin_hash", None)
    # Handle password separately
    if "password" in req:
        pw_val = str(req.pop("password", "")).strip()
        if pw_val:
            profs[idx]["password_hash"] = _hash_password(pw_val)
        else:
            profs[idx].pop("password_hash", None)
    if "login" in req:
        profs[idx]["login"] = str(req.pop("login", "")).strip().lower()
    # Never allow overwriting hashes directly from the client
    req.pop("pin_hash", None)
    req.pop("password_hash", None)
    profs[idx].update({k: v for k, v in req.items() if k != "id"})
    _save_profiles(profs)
    if _get_active_profile_id() == pid:
        _reload_for_profile(pid)
    return {**profs[idx], "pin_set": bool(profs[idx].get("pin_hash")), "pin_hash": None}

@app.post("/api/stripe/checkout")
async def api_stripe_checkout(req: dict = Body(...)):
    plan = req.get("plan", "")
    profile_id = req.get("profile_id", "")
    price_id = STRIPE_PRICES.get(plan, "")
    if not price_id:
        raise HTTPException(400, f"Plan invalide ou price_id manquant pour '{plan}'")
    session = _stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{BASE_URL}/?checkout=success&sid={{CHECKOUT_SESSION_ID}}&pid={profile_id}",
        cancel_url=f"{BASE_URL}/",
        metadata={"plan": plan, "profile_id": profile_id},
    )
    return {"url": session.url}

@app.get("/api/stripe/verify-session")
async def api_stripe_verify_session(sid: str, pid: str):
    try:
        session = _stripe.checkout.Session.retrieve(sid)
        if session.status == "complete" and session.payment_status in ("paid", "no_payment_required"):
            meta = session.metadata or {}
            plan = meta.get("plan", "")
            profile_id = meta.get("profile_id", pid)
            if plan and profile_id:
                profs = _load_profiles()
                idx = next((i for i, p in enumerate(profs) if p["id"] == profile_id), None)
                if idx is not None:
                    profs[idx]["plan"] = plan
                    profs[idx]["stripe_customer_id"] = session.customer
                    profs[idx]["stripe_subscription_id"] = session.subscription
                    _save_profiles(profs)
                    return {"ok": True, "plan": plan}
        return {"ok": False, "error": "Paiement non confirmé"}
    except Exception as e:
        raise HTTPException(400, str(e))

def _oneup_fetch_social_accounts(key: str, platform: str) -> dict[str, dict]:
    """Récupère les comptes d'une plateforme via l'API OneUp (listsocialaccounts)."""
    import requests as _req
    seen: dict[str, dict] = {}
    platform_types = {
        "snap": ["snapchat"],
        "ig":   ["instagram"],
        "fb":   ["facebook"],
    }
    kws = platform_types.get(platform, [platform])

    try:
        r = _req.get("https://www.oneupapp.io/api/listsocialaccounts",
                     params={"apiKey": key}, timeout=15)
        if r.status_code == 200:
            raw = r.json()
            items = raw.get("data") or []
            for a in items:
                sn = (a.get("social_network_type") or "").lower()
                if not any(k in sn for k in kws):
                    continue
                sid  = str(a.get("social_account_id") or "")
                name = (a.get("username") or a.get("full_name") or "").strip("@ ")
                pic  = (a.get("profile_image_url") or a.get("picture_url")
                        or a.get("avatar_url") or a.get("image_url")
                        or a.get("profile_picture_url") or a.get("thumbnail") or "")
                if sid and sid not in seen:
                    seen[sid] = {"username": name or sid, "id": sid, "picture": pic}
    except Exception:
        pass

    return seen


@app.get("/api/oneup/snap-accounts")
async def api_oneup_snap_accounts(oneup_key: str = ""):
    key = oneup_key or ONEUP_API_KEY
    if not key:
        raise HTTPException(400, "Clef OneUp manquante")
    seen = _oneup_fetch_social_accounts(key, "snap")
    return {"ok": True, "accounts": [a for a in seen.values() if a.get("id")]}


@app.get("/api/instagram/accounts")
async def get_ig_accounts():
    return IG_ACCOUNTS

@app.get("/api/instagram/scheduled")
async def get_ig_scheduled():
    return list(reversed(_load_json(IG_SCHED_FILE, [])))

@app.delete("/api/instagram/scheduled/{sid}")
async def delete_ig_scheduled(sid: str):
    global _ig_scheduled
    _ig_scheduled = [s for s in _ig_scheduled if s["id"] != sid]
    _save_json(IG_SCHED_FILE, _ig_scheduled)
    return {"ok": True}

class IgScheduleRequest(BaseModel):
    filename: str
    scheduled_at: str
    account_ids: list[str]
    caption: str = ""
    playlist_name: str = ""

@app.post("/api/instagram/schedule")
async def schedule_ig_post(req: IgScheduleRequest):
    import uuid as _uuid
    entry = {
        "id": _uuid.uuid4().hex[:8],
        "filename": req.filename,
        "scheduled_at": req.scheduled_at,
        "account_ids": req.account_ids,
        "caption": req.caption,
        "playlist_name": req.playlist_name,
        "status": "pending",
        "results": {},
        "created_at": datetime.now(PARIS_TZ).isoformat(),
    }
    _ig_scheduled.append(entry)
    _save_json(IG_SCHED_FILE, _ig_scheduled)
    return {"ok": True, "id": entry["id"]}

@app.get("/api/instagram/next-dates")
async def ig_next_dates():
    result = []
    for acc in IG_ACCOUNTS:
        acc_id = acc["id"]
        taken = set()
        for s in _ig_scheduled:
            if acc_id in s.get("account_ids", []) and s.get("status") not in ("error",):
                try: taken.add(datetime.fromisoformat(s["scheduled_at"]).date())
                except: pass
        d = datetime.now(PARIS_TZ).date()
        while d in taken:
            d += timedelta(days=1)
        result.append({"acc_id": acc_id, "username": acc["username"], "next_free": str(d), "taken_count": len(taken)})
    return result

@app.get("/api/oneup/ig-accounts")
async def api_oneup_ig_accounts(oneup_key: str = ""):
    key = oneup_key or ONEUP_API_KEY
    if not key:
        raise HTTPException(400, "Clef OneUp manquante")
    seen = _oneup_fetch_social_accounts(key, "ig")
    return {"ok": True, "accounts": [a for a in seen.values() if a.get("id")]}


@app.get("/api/facebook/accounts")
async def get_fb_accounts():
    return FB_ACCOUNTS

@app.get("/api/facebook/scheduled")
async def get_fb_scheduled():
    return list(reversed(_load_json(FB_SCHED_FILE, [])))

@app.delete("/api/facebook/scheduled/{sid}")
async def delete_fb_scheduled(sid: str):
    global _fb_scheduled
    _fb_scheduled = [s for s in _fb_scheduled if s["id"] != sid]
    _save_json(FB_SCHED_FILE, _fb_scheduled)
    return {"ok": True}

class FbScheduleRequest(BaseModel):
    filename: str
    scheduled_at: str
    account_ids: list[str]
    caption: str = ""

@app.post("/api/facebook/schedule")
async def schedule_fb_post(req: FbScheduleRequest):
    import uuid as _uuid
    entry = {
        "id": _uuid.uuid4().hex[:8],
        "filename": req.filename,
        "scheduled_at": req.scheduled_at,
        "account_ids": req.account_ids,
        "caption": req.caption,
        "status": "pending",
        "results": {},
        "created_at": datetime.now(PARIS_TZ).isoformat(),
    }
    _fb_scheduled.append(entry)
    _save_json(FB_SCHED_FILE, _fb_scheduled)
    return {"ok": True, "id": entry["id"]}

@app.get("/api/oneup/fb-accounts")
async def api_oneup_fb_accounts(oneup_key: str = ""):
    key = oneup_key or ONEUP_API_KEY
    if not key:
        raise HTTPException(400, "Clef OneUp manquante")
    seen = _oneup_fetch_social_accounts(key, "fb")
    return {"ok": True, "accounts": [a for a in seen.values() if a.get("id")]}


@app.get("/api/social/avatar/{platform}/{username}")
async def api_social_avatar(platform: str, username: str, uid: str = ""):
    """Proxy avec cache disque pour les photos de profil des comptes sociaux."""
    from fastapi.responses import Response as _Resp
    import requests as _req, hashlib as _hl
    safe_user = "".join(c for c in username if c.isalnum() or c in "._-")[:60]
    safe_plat = "".join(c for c in platform if c.isalnum())[:20]
    safe_uid  = "".join(c for c in uid if c.isdigit())[:30]
    cache_dir = Path("/opt/storyscheduler/telegram_scraper/avatar_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Use numeric uid for cache key when available (fb/ig) so we don't mix with username cache
    ck_str = f"{safe_plat}:{safe_uid}" if safe_uid and safe_plat in ("fb", "ig") else f"{safe_plat}:{safe_user}"
    cache_key = _hl.md5(ck_str.encode()).hexdigest()
    cache_file = cache_dir / f"{cache_key}.jpg"
    if cache_file.exists() and cache_file.stat().st_size > 0:
        return _Resp(content=cache_file.read_bytes(), media_type="image/jpeg",
                     headers={"Cache-Control": "public, max-age=86400"})
    sources = []
    # Facebook Graph API: works for FB pages and IG Business accounts with their numeric ID
    if safe_uid and safe_plat in ("fb", "ig"):
        sources.append(f"https://graph.facebook.com/{safe_uid}/picture?type=normal")
    # unavatar.io works for Snapchat
    if safe_plat == "snap":
        sources.append(f"https://unavatar.io/snapchat/{safe_user}")
    for url in sources:
        try:
            r = _req.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 500:
                cache_file.write_bytes(r.content)
                return _Resp(content=r.content, media_type="image/jpeg",
                             headers={"Cache-Control": "public, max-age=86400"})
        except Exception:
            continue
    # Fallback: SVG initials avatar (not cached — generated instantly)
    initials = (safe_user[:2] or "??").upper()
    color = {"snap": "#f5c518", "ig": "#c084fc", "fb": "#60a5fa"}.get(safe_plat, "#888")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">'
           f'<circle cx="20" cy="20" r="20" fill="#1a1a2e"/>'
           f'<text x="20" y="26" text-anchor="middle" font-family="Arial,sans-serif" '
           f'font-size="15" font-weight="bold" fill="{color}">{initials}</text></svg>')
    return _Resp(content=svg.encode(), media_type="image/svg+xml",
                 headers={"Cache-Control": "public, max-age=3600"})

@app.post("/api/social/avatar/{platform}/{username}/set-url")
async def api_social_avatar_set_url(platform: str, username: str, body: dict = Body(...)):
    """Télécharge une photo depuis une URL fournie et la met en cache."""
    from fastapi.responses import Response as _Resp
    import requests as _req, hashlib as _hl
    url = (body.get("url") or "").strip()
    if not url or not url.startswith("http"):
        raise HTTPException(400, "URL invalide")
    safe_user = "".join(c for c in username if c.isalnum() or c in "._-")[:60]
    safe_plat = "".join(c for c in platform if c.isalnum())[:20]
    safe_uid  = "".join(c for c in (body.get("uid") or "") if c.isdigit())[:30]
    cache_dir = Path("/opt/storyscheduler/telegram_scraper/avatar_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    ck_str = f"{safe_plat}:{safe_uid}" if safe_uid and safe_plat in ("fb", "ig") else f"{safe_plat}:{safe_user}"
    cache_key = _hl.md5(ck_str.encode()).hexdigest()
    cache_file = cache_dir / f"{cache_key}.jpg"
    try:
        r = _req.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        if r.status_code != 200 or len(r.content) < 200:
            raise HTTPException(400, f"URL inaccessible ({r.status_code})")
        cache_file.write_bytes(r.content)
        return {"ok": True, "size": len(r.content)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Erreur : {e}")

@app.delete("/api/social/avatar/{platform}/{username}")
async def api_social_avatar_clear(platform: str, username: str):
    """Vide le cache pour forcer un rechargement."""
    import hashlib as _hl
    safe_user = "".join(c for c in username if c.isalnum() or c in "._-")[:60]
    safe_plat = "".join(c for c in platform if c.isalnum())[:20]
    cache_dir = Path("/opt/storyscheduler/telegram_scraper/avatar_cache")
    cache_key = _hl.md5(f"{safe_plat}:{safe_user}".encode()).hexdigest()
    cache_file = cache_dir / f"{cache_key}.jpg"
    if cache_file.exists():
        cache_file.unlink()
    return {"ok": True}

@app.get("/api/debug/oneup-raw")
async def api_debug_oneup_raw():
    """Debug : retourne les réponses brutes des endpoints OneUp pour diagnostiquer."""
    import requests as _req
    key = ONEUP_API_KEY
    results = {}
    test_urls = [
        ("listsocialaccounts",    f"https://www.oneupapp.io/api/listsocialaccounts?apiKey={key}"),
        ("listcategory",          f"https://www.oneupapp.io/api/listcategory?apiKey={key}"),
        ("listcategoryaccount",   f"https://www.oneupapp.io/api/listcategoryaccount?apiKey={key}&category_id=177234"),
    ]
    for name, url in test_urls:
        try:
            r = _req.get(url, timeout=15)
            try:
                body = r.json()
            except Exception:
                body = r.text[:500]
            results[name] = {"status": r.status_code, "body": body}
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


@app.get("/api/profiles/{pid}/telegram-accounts")
async def api_profile_tg_accounts(pid: str):
    pdir  = _get_profile_data_dir(pid)
    accs  = _load_json(pdir / "story_accounts.json", [])
    return accs


@app.delete("/api/profiles/{pid}/telegram-accounts/{acc_id}")
async def api_profile_tg_delete(pid: str, acc_id: str):
    pdir  = _get_profile_data_dir(pid)
    fpath = pdir / "story_accounts.json"
    accs  = _load_json(fpath, [])
    acc   = next((a for a in accs if a["id"] == acc_id), None)
    if not acc:
        raise HTTPException(404, "Compte introuvable")
    # Déconnecte si c'est le profil actif
    if _get_active_profile_id() == pid and acc_id in _clients:
        try: await _clients[acc_id].disconnect()
        except: pass
        _clients.pop(acc_id, None)
    for ext in ("", ".session", ".session-journal"):
        p = Path(acc.get("session_file","") + ext)
        if p.exists(): p.unlink(missing_ok=True)
    new_accs = [a for a in accs if a["id"] != acc_id]
    _save_json(fpath, new_accs)
    if _get_active_profile_id() == pid:
        global _accounts
        _accounts = new_accs
    return {"ok": True}


@app.post("/api/accounts/disconnect-all")
async def api_disconnect_all():
    """Déconnecte proprement tous les clients Telethon."""
    for acc_id, client in list(_clients.items()):
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass
    _clients.clear()
    _phone_hashes.clear()
    _pending_phone.clear()
    return {"ok": True}

@app.delete("/api/profiles/{pid}")
async def api_delete_profile(pid: str):
    profs = [p for p in _load_profiles() if p["id"] != pid]
    if not profs:
        raise HTTPException(400, "Impossible de supprimer le dernier profil")
    _save_profiles(profs)
    if _get_active_profile_id() == pid:
        _save_json(ACTIVE_PROFILE_FILE, {"id": profs[0]["id"]})
        _reload_for_profile(profs[0]["id"])
    return {"ok": True}

@app.post("/api/profiles/{pid}/activate")
async def api_activate_profile(pid: str, req: dict = Body(default={}), request: Request = None):
    profs = _load_profiles()
    # Non-admins cannot switch profiles
    session_pid = _get_session_profile(request) if request else None
    if session_pid:
        me = next((p for p in profs if p["id"] == session_pid), None)
        if me and not me.get("is_admin"):
            raise HTTPException(403, "Accès refusé")
    prof  = next((p for p in profs if p["id"] == pid), None)
    if not prof:
        raise HTTPException(404, "Profil introuvable")
    if prof.get("pin_hash"):
        pin = str(req.get("pin", "")).strip()
        if not pin or _hash_pin(pin) != prof["pin_hash"]:
            raise HTTPException(403, "PIN incorrect")
    _clients.clear()  # Libère les anciens clients sans attendre disconnect (keepalive les reconnecte)
    _save_json(ACTIVE_PROFILE_FILE, {"id": pid})
    _reload_for_profile(pid)
    return {"ok": True, "active_id": pid}


@app.delete("/api/snap/spotlight/{sid}")
async def delete_snap_spotlight(sid: str):
    global _snap_spotlight
    _snap_spotlight = [s for s in _snap_spotlight if s["id"] != sid]
    _save_json(SNAP_SPOTLIGHT_FILE, _snap_spotlight)
    return {"ok": True}

@app.post("/api/snap/spotlight")
async def schedule_spotlight(req: dict = Body(...)):
    import random as _rnd, shutil as _sh
    account_ids  = req.get("account_ids", [])
    total_videos = max(1, int(req.get("total_videos", 1)))
    if not account_ids: raise HTTPException(400, "Aucun compte sélectionné")
    if not SPOTLIGHT_POOL_DIR.exists():
        raise HTTPException(400, f"Dossier pool introuvable : {SPOTLIGHT_POOL_DIR}")

    pool_vids = sorted(f for f in SPOTLIGHT_POOL_DIR.iterdir() if f.suffix.lower() in _VIDEO_EXT)
    if not pool_vids:
        raise HTTPException(400, "Pool vide — aucune vidéo à poster")

    n_acc = len(account_ids)
    # Distribution égale : total_videos / n_acc vidéos par compte
    vids_per_acc = total_videos // n_acc
    remainder    = total_videos % n_acc  # premiers comptes reçoivent 1 de plus
    _rnd.shuffle(pool_vids)

    per_account: dict[str, list] = {}
    idx = 0
    for ai, acc_id in enumerate(account_ids):
        count = vids_per_acc + (1 if ai < remainder else 0)
        per_account[acc_id] = pool_vids[idx:idx + count]
        idx += count

    SPOTLIGHT_POSTED_DIR.mkdir(parents=True, exist_ok=True)
    loop  = asyncio.get_event_loop()
    added = 0
    _ACCOUNT_OFFSET_MIN = 25  # minutes fixes entre comptes le même jour

    for ai, acc_id in enumerate(account_ids):
        acc   = next((a for a in SNAP_ACCOUNTS if a["id"] == acc_id), None)
        uname = acc["username"] if acc else acc_id
        vids  = per_account[acc_id]

        # Jours DÉJÀ pris pour ce compte (non-erreur, y compris pending = futurs)
        taken_dates: set = set()
        for e in _snap_spotlight:
            if e.get("account_id") == acc_id and e.get("status") != "error":
                try:
                    taken_dates.add(datetime.fromisoformat(e["scheduled_at"]).date())
                except Exception:
                    pass

        # Cherche les N premiers jours LIBRES à partir de demain
        from datetime import date as _date
        check = (datetime.now() + timedelta(days=1)).date()
        free_days = []
        while len(free_days) < len(vids):
            if check not in taken_dates:
                free_days.append(check)
                taken_dates.add(check)   # marque comme pris pour les vidéos suivantes
            check += timedelta(days=1)

        for k, filepath in enumerate(vids):
            jour    = free_days[k]
            h, m    = _rnd.randint(8, 20), _rnd.randint(0, 59)
            dt_post = datetime(jour.year, jour.month, jour.day, h, m, 0) + timedelta(minutes=ai * _ACCOUNT_OFFSET_MIN)
            dt_str  = dt_post.isoformat()

            sid   = uuid.uuid4().hex[:8]
            entry = {"id": sid, "filename": filepath.name, "scheduled_at": dt_str,
                     "account_id": acc_id, "username": uname, "status": "pending", "result": {}}
            _snap_spotlight.append(entry)
            _save_json(SNAP_SPOTLIGHT_FILE, _snap_spotlight)

            with concurrent.futures.ThreadPoolExecutor() as pool:
                media_url = await loop.run_in_executor(pool, _cloudinary_upload, filepath, True)
            if not media_url:
                entry["status"] = "error"; entry["result"] = {"msg": "Cloudinary failed"}
                _save_json(SNAP_SPOTLIGHT_FILE, _snap_spotlight); continue

            entry["cloudinary_url"] = media_url
            # Générer URL miniature Cloudinary (so_0 = frame 0, format jpg)
            thumb_url = media_url
            import re as _re_th
            thumb_url = _re_th.sub(r'/upload/', '/upload/so_0,w_120,h_160,c_fill/', thumb_url, count=1)
            thumb_url = _re_th.sub(r'\.(mp4|mov|avi|mkv|m4v|webm)$', '.jpg', thumb_url, flags=_re_th.IGNORECASE)
            entry["thumb_url"] = thumb_url
            with concurrent.futures.ThreadPoolExecutor() as pool:
                ok, msg = await loop.run_in_executor(pool, _oneup_spotlight, media_url, acc_id, dt_str, "")
            # "scheduled" = soumis à OneUp, sera posté à la date prévue
            entry["status"] = "scheduled" if ok else "error"
            entry["result"] = {"msg": msg}
            _save_json(SNAP_SPOTLIGHT_FILE, _snap_spotlight)
            if ok:
                added += 1
                try: _sh.move(str(filepath), str(SPOTLIGHT_POSTED_DIR / filepath.name))
                except Exception: pass

    remaining = len([f for f in SPOTLIGHT_POOL_DIR.iterdir() if f.suffix.lower() in _VIDEO_EXT])
    return {"ok": True, "count": added, "pool_remaining": remaining}

# ─────────────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Propriétaire de l&#x2019;agence — Mael</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%232d1f5e'/%3E%3Ccircle cx='32' cy='32' r='4' fill='%23a78bfa'/%3E%3Cg stroke='%23a78bfa' stroke-width='2' stroke-linecap='round'%3E%3Cline x1='32' y1='32' x2='32' y2='14'/%3E%3Ccircle cx='32' cy='12' r='3' fill='%23a78bfa' stroke='none'/%3E%3Cline x1='32' y1='32' x2='32' y2='50'/%3E%3Ccircle cx='32' cy='52' r='3' fill='%23a78bfa' stroke='none'/%3E%3Cline x1='32' y1='32' x2='14' y2='32'/%3E%3Ccircle cx='12' cy='32' r='3' fill='%23a78bfa' stroke='none'/%3E%3Cline x1='32' y1='32' x2='50' y2='32'/%3E%3Ccircle cx='52' cy='32' r='3' fill='%23a78bfa' stroke='none'/%3E%3Cline x1='32' y1='32' x2='19' y2='19'/%3E%3Ccircle cx='17' cy='17' r='3' fill='%23a78bfa' stroke='none'/%3E%3Cline x1='32' y1='32' x2='45' y2='45'/%3E%3Ccircle cx='47' cy='47' r='3' fill='%23a78bfa' stroke='none'/%3E%3Cline x1='32' y1='32' x2='45' y2='19'/%3E%3Ccircle cx='47' cy='17' r='3' fill='%23a78bfa' stroke='none'/%3E%3Cline x1='32' y1='32' x2='19' y2='45'/%3E%3Ccircle cx='17' cy='47' r='3' fill='%23a78bfa' stroke='none'/%3E%3C/g%3E%3C/svg%3E">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080808;--sb:#0d0d0d;--c1:#111;--c2:#161616;
  --b1:#1c1c1c;--b2:#262626;--b3:#333;
  --t1:#f0f0f0;--t2:#777;--t3:#333;
  --purple:#8b5cf6;--purple2:#7c3aed;
  --red:#ef4444;--red2:#dc2626;
  --green:#22c55e;--yellow:#f59e0b;--blue:#3b82f6;
  --r:10px;--r2:7px;--sbw:230px;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--t1);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:15px;line-height:1.55}

/* Layout */
.app{display:grid;grid-template-columns:var(--sbw) 1fr;height:100vh;overflow:hidden}

/* Sidebar */
.sidebar{background:var(--sb);border-right:1px solid var(--b1);display:flex;flex-direction:column;height:100vh;overflow:hidden}
.sb-logo{padding:18px 16px;border-bottom:1px solid var(--b1);display:flex;align-items:center;gap:12px;flex-shrink:0}
.sb-logo-icon{width:46px;height:46px;border-radius:12px;background:linear-gradient(135deg,#7c3aed,#4f46e5);display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 4px 14px rgba(124,58,237,.5)}
.sb-logo-name{font-size:1rem;font-weight:800;letter-spacing:-.02em;line-height:1.2}
.sb-logo-sub{font-size:.88rem;color:var(--purple);margin-top:3px;font-weight:700;letter-spacing:.01em}
.sb-nav{padding:12px 8px;flex:1;display:flex;flex-direction:column;gap:5px}
.sb-item{display:flex;align-items:center;gap:12px;padding:14px 14px;border-radius:10px;cursor:pointer;transition:.15s;color:var(--t2);font-size:.92rem;font-weight:500;border:none;background:transparent;width:100%;text-align:left;letter-spacing:-.01em}
.sb-item:hover{color:var(--t1);background:rgba(255,255,255,.05);transform:translateX(2px)}
.sb-item.active{color:var(--t1);background:linear-gradient(90deg,rgba(139,92,246,.18),rgba(139,92,246,.04));border-left:2px solid var(--purple);padding-left:11px}
.sb-item-ico{width:26px;height:26px;display:flex;align-items:center;justify-content:center;flex-shrink:0;border-radius:7px;background:rgba(255,255,255,.05);color:var(--t2);transition:.15s}.sb-item.active .sb-item-ico,.sb-item:hover .sb-item-ico{color:var(--t1);background:rgba(139,92,246,.18)}
.sb-badge{margin-left:auto;background:var(--purple);color:#fff;font-size:.58rem;font-weight:700;padding:1px 6px;border-radius:8px;min-width:18px;text-align:center}
.sb-badge.orange{background:var(--yellow);color:#000}
.sb-sep{height:1px;background:var(--b1);margin:10px 10px}
.sb-bottom{padding:8px;border-top:1px solid var(--b1);flex-shrink:0;display:flex;flex-direction:column;gap:6px}
.sb-status{display:flex;align-items:center;gap:7px;padding:7px 10px;border-radius:var(--r2);background:var(--c1);font-size:.7rem;color:var(--t2)}
.sb-dot{width:6px;height:6px;border-radius:50%;background:var(--green);flex-shrink:0}
.sb-dot.orange{background:var(--yellow)}
/* Profile selector */
.sb-profile-wrap{position:relative}
.sb-profile-btn{display:flex;align-items:center;gap:9px;padding:7px 10px;border-radius:var(--r2);background:var(--c1);cursor:pointer;border:1px solid transparent;transition:.15s}
.sb-profile-btn:hover{border-color:var(--b1);background:var(--c2)}
.sb-profile-avatar{width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#7c3aed,#4f46e5);display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:800;color:#fff;flex-shrink:0}
.sb-profile-info{flex:1;min-width:0}
.sb-profile-name{font-size:.72rem;font-weight:700;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sb-profile-sub{font-size:.6rem;color:var(--t3)}
.sb-profile-menu{position:absolute;bottom:calc(100% + 6px);left:0;right:0;background:var(--c2);border:1px solid var(--b1);border-radius:10px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.5);z-index:200}
.sb-profile-menu-item{display:flex;align-items:center;gap:8px;width:100%;padding:8px 12px;font-size:.72rem;color:var(--t2);background:none;border:none;cursor:pointer;text-align:left;transition:.1s}
.sb-profile-menu-item:hover{background:var(--c3);color:var(--t1)}
.sb-profile-menu-item.active-prof{color:var(--purple);font-weight:700}
.sb-profile-menu-sep{height:1px;background:var(--b1);margin:4px 0}
/* Profile manager modal */
.pm-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:500;align-items:center;justify-content:center}
.pm-modal.open{display:flex}
.pm-box{background:var(--c2);border:1px solid var(--b1);border-radius:14px;width:min(700px,95vw);max-height:90vh;display:flex;flex-direction:column;overflow:hidden}
.pm-hd{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--b1);flex-shrink:0}
.pm-hd h2{font-size:.95rem;font-weight:800;color:var(--t1);margin:0}
.pm-body{display:flex;flex:1;min-height:0;overflow:hidden}
.pm-list{width:220px;border-right:1px solid var(--b1);padding:12px;overflow-y:auto;flex-shrink:0;display:flex;flex-direction:column;gap:6px}
.pm-list-item{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;cursor:pointer;font-size:.75rem;color:var(--t2);border:1px solid transparent;transition:.1s}
.pm-list-item:hover{background:var(--c3);color:var(--t1)}
.pm-list-item.selected{background:var(--c3);border-color:var(--purple);color:var(--t1)}
.pm-list-item .pm-li-av{width:24px;height:24px;border-radius:6px;background:linear-gradient(135deg,#7c3aed,#4f46e5);display:flex;align-items:center;justify-content:center;font-size:.65rem;font-weight:800;color:#fff;flex-shrink:0}
.pm-list-item .pm-li-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pm-list-item .pm-li-active{width:6px;height:6px;border-radius:50%;background:var(--green);flex-shrink:0}
.pm-form{flex:1;padding:20px;overflow-y:auto}
.pm-form h3{font-size:.8rem;font-weight:700;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;margin:0 0 12px}
.pm-field{margin-bottom:12px}
.pm-field label{display:block;font-size:.68rem;color:var(--t3);margin-bottom:4px}
.pm-field input,.pm-field textarea{width:100%;background:var(--c1);border:1px solid var(--b1);border-radius:7px;padding:7px 10px;font-size:.75rem;color:var(--t1);box-sizing:border-box}
.pm-field input:focus,.pm-field textarea:focus{outline:none;border-color:var(--purple)}
.pm-field textarea{min-height:90px;resize:vertical;font-family:monospace}
.pm-snap-list{display:flex;flex-direction:column;gap:5px;margin-bottom:6px}
.pm-snap-row{display:flex;gap:6px;align-items:center}
.pm-snap-row input{flex:1;min-width:0}
.pm-form-actions{display:flex;gap:8px;margin-top:16px;padding-top:16px;border-top:1px solid var(--b1)}
.pm-new-btn{display:flex;align-items:center;gap:6px;padding:8px 10px;border-radius:8px;border:1px dashed var(--b1);color:var(--t3);font-size:.72rem;background:none;cursor:pointer;width:100%;transition:.1s}
.pm-new-btn:hover{border-color:var(--purple);color:var(--purple)}
.sb-item-soon{opacity:.65}
.sb-item-soon:hover{opacity:1}
/* PIN modal */
.pin-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:600;align-items:center;justify-content:center}
.pin-modal.open{display:flex}
.pin-box{background:var(--c2);border:1px solid var(--b1);border-radius:16px;padding:28px 32px;width:280px;text-align:center}
.pin-box h3{font-size:.9rem;font-weight:800;color:var(--t1);margin:0 0 6px}
.pin-box p{font-size:.72rem;color:var(--t3);margin:0 0 18px}
.pin-dots{display:flex;gap:10px;justify-content:center;margin-bottom:18px}
.pin-dot{width:14px;height:14px;border-radius:50%;border:2px solid var(--b1);background:transparent;transition:.15s}
.pin-dot.filled{background:var(--purple);border-color:var(--purple)}
.pin-dot.error{background:#ef4444;border-color:#ef4444}
.pin-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}
.pin-key{height:48px;border-radius:10px;background:var(--c1);border:1px solid var(--b1);font-size:1.1rem;font-weight:700;color:var(--t1);cursor:pointer;transition:.1s}
.pin-key:hover{background:var(--c3);border-color:var(--purple)}
.pin-key:active{transform:scale(.95)}
.pin-cancel{font-size:.7rem;color:var(--t3);background:none;border:none;cursor:pointer;text-decoration:underline;margin-top:4px}
/* Docs / Logout buttons */
/* Documentation page */
.doc-nav-section{margin-bottom:6px}
.doc-nav-label{font-size:.65rem;font-weight:800;color:var(--t3);text-transform:uppercase;letter-spacing:.08em;padding:10px 16px 5px}
.doc-nav-item{display:block;width:100%;text-align:left;padding:7px 16px 7px 22px;background:none;border:none;color:var(--t2);font-size:.8rem;cursor:pointer;border-radius:0;transition:.1s;border-left:2px solid transparent}
.doc-nav-item:hover{color:var(--t1);background:var(--c1)}
.doc-nav-item.active{color:var(--purple);border-left-color:var(--purple);background:rgba(124,58,237,.07);font-weight:700}
.doc-breadcrumb{font-size:.68rem;color:var(--t3);font-weight:600;margin-bottom:10px;letter-spacing:.04em}
.doc-h1{font-size:1.55rem;font-weight:900;letter-spacing:-.025em;color:var(--t1);margin:0 0 18px;line-height:1.2}
.doc-h2{font-size:1rem;font-weight:800;color:var(--t1);margin:26px 0 12px;padding-top:6px}
.doc-p{font-size:.85rem;color:var(--t2);line-height:1.75;margin:0 0 14px}
.doc-callout{border-radius:10px;padding:13px 16px;font-size:.82rem;line-height:1.65;margin:16px 0}
.doc-callout.info{background:rgba(124,58,237,.08);border:1px solid rgba(124,58,237,.22);color:#c4b5fd}
.doc-callout.warn{background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.2);color:#fcd34d}
.doc-steps{display:flex;flex-direction:column;gap:12px;margin:14px 0}
.doc-step{display:flex;gap:14px;align-items:flex-start}
.doc-step-num{width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#7c3aed,#4f46e5);display:flex;align-items:center;justify-content:center;font-size:.78rem;font-weight:900;color:#fff;flex-shrink:0;margin-top:1px}
.doc-step strong{font-size:.87rem;color:var(--t1);display:block;margin-bottom:3px}
.doc-step p{font-size:.8rem;color:var(--t2);margin:0;line-height:1.6}
.doc-checklist{display:flex;flex-direction:column;gap:8px;margin:12px 0}
.doc-check-item{display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:var(--t2);line-height:1.5}
.doc-check{color:#a78bfa;font-weight:800;flex-shrink:0}
.doc-grid-2{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:14px 0}
.doc-feature-card{background:var(--c1);border:1px solid var(--b1);border-radius:12px;padding:16px;display:flex;gap:12px}
.doc-feature-ico{font-size:1.4rem;flex-shrink:0;line-height:1}
.doc-feature-card strong{font-size:.85rem;color:var(--t1);display:block;margin-bottom:4px}
.doc-feature-card p{font-size:.78rem;color:var(--t3);margin:0;line-height:1.55}
.doc-platform-list{display:flex;flex-direction:column;gap:10px;margin:14px 0}
.doc-platform{display:flex;gap:14px;align-items:flex-start;background:var(--c1);border:1px solid var(--b1);border-radius:10px;padding:14px}
.doc-platform strong{font-size:.87rem;color:var(--t1);margin-right:8px}
.doc-platform p{font-size:.78rem;color:var(--t3);margin:4px 0 0;line-height:1.5}
.doc-badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;vertical-align:middle}
.doc-badge.green{background:rgba(34,197,94,.12);color:#4ade80;border:1px solid rgba(34,197,94,.2)}
.doc-badge.yellow{background:rgba(245,158,11,.1);color:#fbbf24;border:1px solid rgba(245,158,11,.2)}
.doc-table{border:1px solid var(--b1);border-radius:10px;overflow:hidden;margin:14px 0;font-size:.8rem}
.doc-table-row{display:grid;grid-template-columns:1.5fr 1fr 1.5fr;padding:10px 14px;border-bottom:1px solid var(--b1)}
.doc-table-row:last-child{border-bottom:none}
.doc-table-head{background:var(--c1);font-weight:700;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--t3)}
.doc-next-btn-row{margin-top:32px;padding-top:20px;border-top:1px solid var(--b1)}
.doc-next-btn{background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.3);color:#a78bfa;padding:10px 20px;border-radius:9px;cursor:pointer;font-size:.83rem;font-weight:700;transition:.15s}
.doc-next-btn:hover{background:rgba(124,58,237,.22);color:#c4b5fd}
.doc-faq-list{display:flex;flex-direction:column;gap:0}
.doc-faq{border-bottom:1px solid var(--b1);padding:16px 0}
.doc-faq-q{font-size:.87rem;font-weight:700;color:var(--t1);margin-bottom:8px}
.doc-faq-a{font-size:.8rem;color:var(--t2);line-height:1.7}
.sb-util-btns{display:flex;flex-direction:column;gap:3px}
.sb-util-btn{display:flex;align-items:center;gap:9px;padding:7px 10px;border-radius:var(--r2);background:none;border:none;cursor:pointer;font-size:.73rem;color:var(--t2);width:100%;text-align:left;transition:.1s}
.sb-util-btn:hover{background:var(--c1);color:var(--t1)}
.sb-util-btn.danger{color:#f87171}
.sb-util-btn.danger:hover{background:#1a0505;color:#fca5a5}
.sb-util-ico{width:28px;height:28px;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:var(--c1)}
.sb-util-btn.danger .sb-util-ico{background:#1a0505}

/* Plan system */
.plan-lock-overlay{position:absolute;inset:0;z-index:500;background:rgba(8,8,10,.88);backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;flex-direction:column;gap:0}
.plan-cards-wrap{display:flex;gap:16px;flex-wrap:wrap;justify-content:center;padding:0 24px;max-width:860px}
.plan-card{background:#0d0d0f;border:1px solid #1c1c22;border-radius:18px;padding:26px 24px;width:230px;flex-shrink:0}
.plan-card.plan-card-pro{background:linear-gradient(145deg,#13102e,#0f0c22);border-color:#5b4fe8}
.plan-card .plan-price{font-size:2rem;font-weight:900;letter-spacing:-.04em;color:#fff;margin:8px 0 2px}
.plan-card .plan-sub{font-size:.75rem;color:#333;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid #111}
.plan-card.plan-card-pro .plan-sub{border-bottom-color:rgba(124,58,237,.15);color:#4a4570}
.plan-card .plan-feat{font-size:.78rem;color:#666;line-height:1.65;margin-bottom:18px}
.plan-card.plan-card-pro .plan-feat{color:#a78bfa}
.sb-item.plan-locked{opacity:.35;cursor:not-allowed;position:relative}
.sb-item.plan-locked::after{content:'🔒';font-size:.6rem;position:absolute;right:10px;top:50%;transform:translateY(-50%)}
/* Main */
.main{display:flex;flex-direction:column;overflow:hidden;height:100vh;position:relative}
.topbar{border-bottom:1px solid var(--b1);padding:0 20px;height:62px;display:flex;align-items:center;gap:12px;flex-shrink:0;background:var(--sb)}
.topbar-title{font-size:1.55rem;font-weight:800;flex:1;letter-spacing:-.02em;color:var(--t1)}
.topbar-actions{display:flex;gap:6px}
.dr-bar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.dr-btn{padding:7px 15px;border-radius:9px;border:1px solid var(--b2);background:var(--c2);color:var(--t2);font-size:.73rem;font-weight:700;cursor:pointer;transition:background .12s,color .12s,border-color .12s;white-space:nowrap;user-select:none}
.dr-btn:hover{border-color:#6d28d9;color:var(--t1)}
.dr-btn.dr-active{background:#6d28d9;border-color:#6d28d9;color:#fff}

/* Content */
.content-wrap{flex:1;overflow:hidden;display:flex}
.content-main{flex:1;overflow-y:auto;padding:16px 20px 20px}
.content-main::-webkit-scrollbar,.rp-list::-webkit-scrollbar,.plist::-webkit-scrollbar,.acc-list::-webkit-scrollbar,.pl-grid-wrap::-webkit-scrollbar{width:3px}
.content-main::-webkit-scrollbar-thumb,.rp-list::-webkit-scrollbar-thumb,.plist::-webkit-scrollbar-thumb,.acc-list::-webkit-scrollbar-thumb,.pl-grid-wrap::-webkit-scrollbar-thumb{background:var(--b2)}
.page{display:none}
.page.active{display:block}

/* Metrics */
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
.metric{background:var(--c1);border:1px solid var(--b1);border-radius:var(--r);padding:14px 16px}
.metric-val{font-size:1.9rem;font-weight:700;letter-spacing:-.03em;line-height:1}
.metric-lbl{font-size:.7rem;color:var(--t2);margin-top:5px;text-transform:uppercase;letter-spacing:.06em}

/* Panel */
.panel{background:var(--c1);border:1px solid var(--b1);border-radius:var(--r);padding:16px;margin-bottom:12px}
.panel-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.panel-title{font-size:.74rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--t2)}

/* Right panel */
.right-panel{width:360px;border-left:1px solid var(--b1);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0;background:var(--sb)}
.rp-hd{padding:14px 16px;border-bottom:1px solid var(--b1);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.rp-title{font-size:.82rem;font-weight:700;letter-spacing:-.01em;color:var(--t1)}
.rp-list{flex:1;overflow-y:auto;padding:10px}

/* Skeleton loader */
@keyframes shimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}
.skel{background:linear-gradient(90deg,var(--b1) 25%,var(--b2) 50%,var(--b1) 75%);background-size:800px 100%;animation:shimmer 1.4s infinite linear;border-radius:6px}

/* Scheduled item */
.sitem{display:flex;gap:11px;padding:11px 10px;border-radius:10px;border:1px solid var(--b1);background:var(--c1);margin-bottom:7px;position:relative}
.sitem:hover{border-color:var(--b2)}
.sthumb{width:64px;height:84px;border-radius:9px;object-fit:cover;flex-shrink:0;cursor:zoom-in;transition:.15s}
.sinfo{flex:1;min-width:0}
.sdate{font-size:.92rem;font-weight:700;color:var(--t1);margin-bottom:4px;letter-spacing:-.02em}
.spl{font-size:.82rem;color:var(--purple);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.saccs{font-size:.82rem;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.acc-badge{display:inline-flex;align-items:center;gap:5px;background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.25);border-radius:7px;padding:3px 9px;font-size:.73rem;font-weight:600;color:#a5b4fc;cursor:default;position:relative;margin-top:3px}
.sched-tabs{display:flex;gap:2px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:3px;flex-shrink:0}
.sched-tab{padding:5px 14px;background:none;border:none;border-radius:6px;color:var(--t3);font-size:.73rem;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap;display:flex;align-items:center;gap:5px}
.sched-tab.sched-tab-act{background:rgba(124,58,237,.3);color:#c4b5fd;box-shadow:0 1px 4px rgba(124,58,237,.2)}
.accs-panel{background:var(--c2);border:1px solid var(--b1);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:0}
.accs-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--b1)}
.accs-hd-left{display:flex;align-items:center;gap:10px}
.accs-plat-ico{width:32px;height:32px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.accs-plat-name{font-size:.92rem;font-weight:800;color:var(--t1);letter-spacing:-.01em}
.accs-badge{font-size:.65rem;font-weight:700;background:rgba(124,58,237,.18);border:1px solid rgba(124,58,237,.3);color:#a78bfa;border-radius:20px;padding:1px 7px;min-width:18px;text-align:center}
.accs-btn{background:#111;border:1px solid var(--b2);border-radius:7px;color:var(--t2);cursor:pointer;font-size:.75rem;font-weight:600;padding:5px 10px;transition:.12s;white-space:nowrap}
.accs-btn:hover{border-color:var(--b1);color:var(--t1)}
.accs-btn-add{background:rgba(124,58,237,.12);border-color:rgba(124,58,237,.3);color:#a78bfa}
.accs-btn-add:hover{background:rgba(124,58,237,.22);border-color:rgba(124,58,237,.5);color:#c4b5fd}
.acc-badge::after{content:attr(data-tooltip);position:absolute;bottom:calc(100% + 7px);left:0;background:#13131f;border:1px solid rgba(99,102,241,.35);border-radius:8px;padding:7px 11px;font-size:.75rem;color:#e2e8f0;white-space:pre;pointer-events:none;opacity:0;transition:opacity .15s;z-index:200;box-shadow:0 4px 16px rgba(0,0,0,.6);line-height:1.6;font-weight:500}
.acc-badge:hover::after{opacity:1}
.snote{font-size:.78rem;color:var(--yellow);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
.sright{display:flex;flex-direction:column;align-items:flex-end;gap:3px;flex-shrink:0}
.badge{font-size:.68rem;font-weight:700;padding:4px 8px;border-radius:5px;text-transform:uppercase;white-space:nowrap}
.badge.be[data-tooltip],.badge.bpar[data-tooltip]{position:relative;cursor:help}
.badge.be[data-tooltip]::after,.badge.bpar[data-tooltip]::after{content:attr(data-tooltip);position:absolute;bottom:calc(100% + 8px);right:0;background:#1a0a0a;border:1px solid rgba(239,68,68,.4);border-radius:9px;padding:9px 13px;font-size:.72rem;color:#fca5a5;white-space:pre-wrap;pointer-events:none;opacity:0;transition:opacity .15s;z-index:400;box-shadow:0 6px 24px rgba(0,0,0,.8);line-height:1.75;font-weight:500;min-width:180px;max-width:340px;word-break:break-word}
.badge.be[data-tooltip]:hover::after,.badge.bpar[data-tooltip]:hover::after{opacity:1}
.bp{background:rgba(245,158,11,.13);color:#f59e0b}
.bs{background:rgba(59,130,246,.13);color:#60a5fa}
.bd{background:rgba(34,197,94,.13);color:#4ade80}
.be{background:rgba(239,68,68,.13);color:#f87171}
.bpar{background:rgba(245,158,11,.13);color:#fbbf24}
.sdel2,.snote-btn{background:none;border:none;color:var(--t3);cursor:pointer;font-size:11px;padding:2px;transition:.12s}
.sdel2:hover{color:#f87171}.snote-btn:hover{color:var(--yellow)}
.no-rp{color:var(--t2);font-size:.73rem;text-align:center;padding:20px 10px}
/* ── Image preview popup ───────────────────────────────────────────────────*/
.img-preview-popup{
  position:fixed;z-index:500;pointer-events:none;
  width:180px;border-radius:12px;overflow:hidden;
  box-shadow:0 20px 60px rgba(0,0,0,.8),0 0 0 1px rgba(255,255,255,.08);
  opacity:0;transform:scale(.92) translateY(4px);
  transition:opacity .18s ease,transform .18s ease;
  background:#0a0a0a;
}
.img-preview-popup.visible{opacity:1;transform:scale(1) translateY(0)}
.img-preview-popup img{width:100%;display:block;aspect-ratio:9/16;object-fit:cover}
.img-preview-popup .prev-date{
  position:absolute;bottom:0;left:0;right:0;
  background:linear-gradient(transparent,rgba(0,0,0,.9));
  padding:20px 8px 8px;
  font-size:.62rem;color:#e0e0e0;font-weight:600;text-align:center;
}



/* Stats charts */
.stats-platform-tabs{display:flex;gap:8px;margin-bottom:14px}
.spt{flex:1;background:var(--c1);border:1px solid var(--b1);border-radius:var(--r);padding:14px 16px;cursor:pointer;transition:.15s;text-align:center}
.spt:hover{border-color:var(--b2)}.spt.active{border-color:var(--purple)}
.spt-ico{width:36px;height:36px;margin:0 auto 6px;display:flex;align-items:center;justify-content:center}
.spt-ico svg{width:36px;height:36px;border-radius:7px}
.spt-name{font-size:.82rem;font-weight:700;margin-bottom:2px}
.spt-sub{font-size:.68rem;color:var(--t2)}
.stat-overview{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}
.stat-ov-card{background:var(--c2);border:1px solid var(--b1);border-radius:var(--r2);padding:12px 14px;text-align:center}
.stat-ov-val{font-size:1.5rem;font-weight:800;letter-spacing:-.04em;line-height:1}
.stat-ov-lbl{font-size:.6rem;color:var(--t2);margin-top:4px;text-transform:uppercase;letter-spacing:.06em}
.chart-wrap{background:var(--c2);border:1px solid var(--b1);border-radius:var(--r);padding:14px;margin-bottom:12px}
.chart-title{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--t2);margin-bottom:10px}
.bar-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.bar-label{font-size:.68rem;color:var(--t2);width:75px;flex-shrink:0;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{flex:1;height:8px;background:var(--b1);border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;transition:.6s ease}
.bar-val{font-size:.65rem;color:var(--t1);font-weight:700;width:28px;text-align:right;flex-shrink:0}
.stats-section-title{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--t2);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--b1)}

/* Buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 16px;border-radius:var(--r2);border:1px solid var(--b2);font-size:.84rem;font-weight:600;cursor:pointer;transition:.12s;background:transparent;color:var(--t1);min-height:36px}
.btn:hover{background:var(--b1)}
.btn-primary{background:var(--purple);border-color:var(--purple);color:#fff}
.btn-primary:hover{background:var(--purple2)}
.btn-danger{background:var(--red);border-color:var(--red);color:#fff}
.btn-danger:hover{background:var(--red2)}
.btn-sm{padding:7px 12px;font-size:.79rem;min-height:32px}
.btn-xs{padding:5px 10px;font-size:.74rem;min-height:28px}
.btn:disabled{opacity:.4;cursor:not-allowed}

/* Upload */
.uz{border:2px dashed var(--b2);border-radius:var(--r);padding:20px;text-align:center;cursor:pointer;transition:.2s;position:relative}
.uz:hover,.uz.over{border-color:var(--purple);background:rgba(139,92,246,.04)}
.uz input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.uz-ico{font-size:1.6rem;opacity:.25;margin-bottom:5px}
.uz-txt{font-size:.76rem;color:var(--t2)}
.uz-txt b{color:var(--t1)}

/* Photo list */
.plist{display:flex;flex-direction:column;gap:5px;margin-top:10px;max-height:280px;overflow-y:auto}
.prow{background:var(--c2);border:1px solid var(--b1);border-radius:var(--r2);padding:6px 9px;display:flex;align-items:center;gap:7px;cursor:grab;flex-shrink:0}
.prow:hover{border-color:var(--b2)}
.prow.dragging{opacity:.3}.prow.drag-over{border-color:var(--purple)}
.dh{color:var(--t3);cursor:grab;font-size:13px;user-select:none;flex-shrink:0}
.pord{font-size:.63rem;font-weight:700;color:var(--t2);min-width:13px;flex-shrink:0}
.pthumb{width:36px;height:36px;border-radius:4px;object-fit:cover;flex-shrink:0}
.pdt{flex:1;min-width:0}
.pdt input{width:100%;background:var(--c1);border:1px solid var(--b1);border-radius:4px;padding:5px 7px;color:var(--t1);font-size:.7rem;color-scheme:dark;outline:none;transition:.12s}
.pdt input:focus{border-color:var(--purple)}
.pdel{background:none;border:none;color:var(--t3);cursor:pointer;padding:3px;opacity:.5;transition:.12s;font-size:12px}
.pdel:hover{opacity:1;color:#f87171}
.no-p{color:var(--t2);font-size:.73rem;text-align:center;padding:10px 0}

/* Account checks */
.acc-section{margin-top:12px;padding-top:11px;border-top:1px solid var(--b1)}
.acc-section-lbl{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--t2);margin-bottom:7px}
.acc-checks{display:flex;flex-direction:column;gap:3px;max-height:185px;overflow-y:auto}
.acc-check{display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:var(--r2);border:1px solid var(--b1);background:var(--c2);cursor:pointer;transition:.12s}
.acc-check:hover{border-color:var(--b2)}
.acc-check.sel{border-color:var(--purple);background:rgba(139,92,246,.07)}
.acc-check input{accent-color:var(--purple);flex-shrink:0}
.acc-check-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.acc-check-name{font-size:.8rem;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.no-acc-warn{font-size:.7rem;color:var(--yellow);padding:5px 8px;background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.2);border-radius:var(--r2)}

/* Account list */
.acc-list{display:flex;flex-direction:column;gap:5px}
.acc-item{display:flex;align-items:center;gap:12px;padding:12px 14px;border-radius:10px;background:#0d0d10;border:1px solid var(--b1);margin-bottom:7px;transition:border-color .15s}.acc-item:last-child{margin-bottom:0}.acc-item:hover{border-color:rgba(124,58,237,.25)}
.acc-item-sm{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:8px;background:#0d0d10;border:1px solid var(--b1);margin-bottom:4px;transition:border-color .15s}.acc-item-sm:last-child{margin-bottom:0}.acc-item-sm:hover{border-color:rgba(124,58,237,.25)}
.acc-avatar-sm{width:30px;height:30px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:800;color:#fff;overflow:hidden;position:relative}
.acc-avatar-sm img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:50%}
.acc-avatar-wrap-sm{position:relative;width:30px;height:30px;flex-shrink:0}
.acc-dot-sm{width:7px;height:7px;border-radius:50%;flex-shrink:0;position:absolute;bottom:0px;right:0px;border:1.5px solid var(--c2)}
.acc-name-sm{font-size:.82rem;font-weight:700;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--t1)}
.acc-plat-sm{font-size:.65rem;margin-top:1px}
.acc-desc-sm{font-size:.65rem;color:#555;font-style:italic;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}
.acc-desc-sm:hover{color:var(--purple)}
.acc-btn-sq{width:26px;height:26px;padding:0;display:flex;align-items:center;justify-content:center;background:#1a1a1a;border:1px solid var(--b2);border-radius:6px;color:var(--t2);cursor:pointer;font-size:13px;transition:.12s;flex-shrink:0}
.acc-btn-sq:hover{border-color:var(--t1);color:var(--t1)}.acc-btn-sq.del:hover{border-color:#f87171;color:#f87171;background:#1a0a0a}
.acc-avatar{width:54px;height:54px;border-radius:50%;object-fit:cover;flex-shrink:0;background:linear-gradient(135deg,#1e1b4b,#312e81);display:flex;align-items:center;justify-content:center;font-size:1.4rem;font-weight:800;color:#fff;overflow:hidden}
.acc-avatar img{width:100%;height:100%;object-fit:cover;border-radius:50%}
.acc-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;position:absolute;bottom:1px;right:1px;border:2px solid var(--c2)}
.acc-avatar-wrap{position:relative;width:54px;height:54px;flex-shrink:0}
.acc-name-el{font-size:1rem;font-weight:700;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--t1)}
.acc-phone-el{font-size:.78rem;color:var(--t2);margin-top:2px}
.acc-desc-el{font-size:.8rem;color:var(--t2);margin-top:5px;line-height:1.4;word-break:break-word;white-space:pre-wrap}
.acc-desc-click{cursor:pointer;border-radius:5px;padding:2px 4px;margin-left:-4px;transition:.12s}
.acc-desc-click:hover{background:rgba(124,58,237,.12);color:var(--purple)}
.cpl-slot-lbl{display:flex;align-items:center;gap:5px;background:var(--c2);border:1px solid var(--b2);border-radius:7px;padding:5px 10px;cursor:pointer;font-size:.75rem;color:var(--t2);transition:.12s;user-select:none}
.cpl-slot-lbl:has(input:checked){border-color:var(--purple);color:var(--purple);background:rgba(124,58,237,.12)}
.cpl-photo-thumb{width:72px;height:72px;border-radius:7px;object-fit:cover;position:relative;cursor:grab}
#cplDrop.drag-over{border-color:var(--purple);background:rgba(124,58,237,.08)}
.md-card{background:var(--c2);border:1px solid var(--b1);border-radius:9px;overflow:hidden;transition:box-shadow .15s,border-color .15s;user-select:none}
.md-card:hover{border-color:var(--b2);box-shadow:0 4px 16px rgba(0,0,0,.3)}
.md-card-media{height:180px;background:#000;position:relative;overflow:hidden}
.md-card-del{position:absolute;top:6px;right:6px;background:rgba(0,0,0,.72);border:none;color:#fc8181;border-radius:50%;width:24px;height:24px;font-size:12px;cursor:pointer;display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity .15s;z-index:2}
.md-card:hover .md-card-del{opacity:1}
.md-card-handle{position:absolute;top:6px;left:6px;background:rgba(0,0,0,.6);color:rgba(255,255,255,.8);border-radius:5px;width:26px;height:26px;font-size:16px;display:flex;align-items:center;justify-content:center;cursor:grab;opacity:0;transition:opacity .15s;z-index:2;touch-action:none}
.md-card:hover .md-card-handle{opacity:1}
.md-card-num{position:absolute;bottom:6px;left:6px;background:rgba(0,0,0,.6);color:#fff;border-radius:4px;font-size:.6rem;font-weight:700;padding:2px 6px;z-index:2}
.md-drop-target{border-color:var(--purple)!important;box-shadow:0 0 0 2px var(--purple)!important;transform:scale(.97);transition:transform .12s,box-shadow .12s,border-color .12s}
.acc-desc-inp{width:100%;background:#0d0d0d;border:1px solid var(--purple);border-radius:6px;padding:7px 10px;color:var(--t1);font-size:.82rem;resize:none;outline:none;margin-top:6px;font-family:inherit;line-height:1.4}
.acc-desc-btn{background:#1a1a1a;border:1px solid var(--b2);border-radius:8px;color:var(--t2);cursor:pointer;font-size:16px;padding:8px 13px;transition:.12s;white-space:nowrap;flex-shrink:0}
.acc-desc-btn:hover{border-color:var(--purple);color:var(--purple);background:#1e1730}
.acc-ren,.acc-del-btn{background:#1a1a1a;border:1px solid var(--b2);border-radius:8px;color:var(--t2);cursor:pointer;font-size:16px;padding:8px 13px;transition:.12s}
.acc-ren:hover{border-color:var(--t1);color:var(--t1)}.acc-del-btn:hover{border-color:#f87171;color:#f87171;background:#1a0a0a}
.no-acc{font-size:.88rem;color:var(--t2);text-align:center;padding:24px 0}

/* Playlist */

/* ── Playlist redesign ─────────────────────────────────────────────────────*/
.pl-folder-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.pl-folder-card{background:var(--c2);border:1px solid var(--b1);border-radius:10px;padding:14px 16px;display:flex;align-items:center;gap:12px;cursor:pointer;transition:.15s}
.pl-folder-card:hover{border-color:var(--b2);background:#1a1a1a;transform:translateY(-1px)}
.pl-folder-ico{font-size:1.3rem;flex-shrink:0;opacity:.85}
.pl-folder-body{flex:1;min-width:0}
.pl-folder-name{font-size:.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pl-folder-meta{font-size:.62rem;color:var(--t2);margin-top:2px}
.pl-folder-arr{color:var(--t3);font-size:.9rem;flex-shrink:0;transition:.15s}
.pl-folder-card:hover .pl-folder-arr{color:var(--t2);transform:translateX(3px)}
.pl-folder-del{background:none;border:none;color:var(--t3);cursor:pointer;font-size:13px;padding:4px;transition:.12s;flex-shrink:0}
.pl-folder-del:hover{color:#f87171}

.pl-detail-hd{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.pl-detail-name{font-size:1rem;font-weight:800;text-transform:uppercase;letter-spacing:.05em;flex:1}
.pl-detail-sub{font-size:.67rem;color:var(--t2);margin-top:1px}

.pl-media-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
.pl-media-card{position:relative;border-radius:8px;overflow:hidden;background:var(--c2);border:1px solid var(--b1);transition:.15s;cursor:pointer}
.pl-media-card:hover{border-color:var(--b2)}
.pl-media-img-wrap{position:relative;width:100%;padding-bottom:133%;overflow:hidden;background:#0a0a0a}
.pl-media-img-wrap img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;pointer-events:none}
.pl-media-day{position:absolute;top:5px;left:5px;background:var(--purple);color:#fff;font-size:.6rem;font-weight:800;padding:2px 7px;border-radius:4px;z-index:2;box-shadow:0 1px 4px rgba(0,0,0,.5)}
.pl-media-actions{position:absolute;top:5px;right:5px;display:flex;gap:3px;z-index:3;opacity:0;transition:.15s}
.pl-media-card:hover .pl-media-actions{opacity:1}
.pl-media-btn{width:24px;height:24px;border-radius:5px;background:rgba(0,0,0,.75);border:1px solid rgba(255,255,255,.12);color:#fff;cursor:pointer;font-size:11px;display:flex;align-items:center;justify-content:center;transition:.12s;padding:0}
.pl-media-btn:hover{background:rgba(139,92,246,.8);border-color:var(--purple)}
.pl-media-btn.del:hover{background:rgba(239,68,68,.8);border-color:var(--red)}
.pl-media-footer{padding:5px 7px;background:var(--sb)}
.pl-media-fname{font-size:.55rem;color:var(--t2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pl-media-time{font-size:.58rem;color:var(--t1);font-weight:600;margin-top:1px}
.pl-no-media{grid-column:1/-1;text-align:center;padding:30px;color:var(--t2);font-size:.78rem}

.pl-day-edit-pop{position:absolute;z-index:10;background:#161616;border:1px solid var(--b2);border-radius:8px;padding:10px;width:140px;box-shadow:0 8px 24px rgba(0,0,0,.6)}
.pl-day-edit-pop label{font-size:.58rem;color:var(--t2);text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:3px}
.pl-day-edit-pop input{width:100%;background:#0a0a0a;border:1px solid var(--b2);border-radius:4px;padding:5px 7px;color:var(--t1);font-size:.75rem;outline:none;margin-bottom:6px}
.pl-day-edit-pop input:focus{border-color:var(--purple)}
.pl-day-edit-pop .btn{width:100%;font-size:.7rem;padding:5px}


/* ── Line charts ─────────────────────────────────────────────────────────── */
.snap-tabs{display:flex;gap:0;margin-bottom:14px;background:var(--c2);border:1px solid var(--b1);border-radius:10px;padding:3px}
.snap-tab{flex:1;padding:9px 14px;border-radius:8px;border:none;background:transparent;color:var(--t2);font-size:.83rem;font-weight:600;cursor:pointer;transition:.15s;text-align:center}
.snap-tab:hover{color:var(--t1)}
.snap-tab.active{background:#1c1c1c;color:var(--t1);box-shadow:0 1px 4px rgba(0,0,0,.4)}
.snap-tab[data-snap="spotlight"].active{color:#f5c518}
.snap-subview{display:none}.snap-subview.active{display:block}
.lc-wrap{background:var(--c2);border:1px solid var(--b1);border-radius:var(--r);padding:0;margin-bottom:12px;position:relative;overflow:hidden}
.lc-header{padding:12px 16px 0;display:flex;align-items:center;justify-content:space-between}
.lc-title{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--t2)}
.lc-subtitle{font-size:.62rem;color:var(--t3)}
.lc-canvas-box{position:relative;width:100%;height:440px;padding:8px 0 0;cursor:grab;user-select:none}
.lc-canvas-box.dragging{cursor:grabbing}
.lc-canvas-box canvas{width:100%;height:100%;display:block}
.lc-scroll-hint{text-align:center;font-size:.6rem;color:var(--t3);padding:4px 0 8px;letter-spacing:.04em}
.lc-tooltip{position:absolute;pointer-events:none;background:#181818;border:1px solid var(--b2);border-radius:8px;padding:9px 12px;font-size:.7rem;opacity:0;transition:opacity .1s;z-index:10;min-width:140px;box-shadow:0 8px 24px rgba(0,0,0,.6)}
.lc-tooltip-date{font-size:.65rem;font-weight:700;color:var(--t1);margin-bottom:5px}
.lc-tooltip-total{font-size:.72rem;font-weight:800;color:var(--purple);margin-bottom:5px}
.lc-tooltip-row{display:flex;align-items:center;gap:6px;margin-bottom:2px}
.lc-tooltip-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.lc-tooltip-name{flex:1;color:var(--t2);font-size:.65rem}
.lc-tooltip-val{font-weight:700;color:var(--t1);font-size:.7rem}

/* Stats */
.stat-card{background:var(--c2);border:1px solid var(--b1);border-radius:var(--r2);padding:12px 14px;display:flex;gap:14px;margin-bottom:10px;align-items:center}
.stat-thumb{width:64px;height:86px;border-radius:8px;object-fit:cover;flex-shrink:0;background:var(--c1)}
.stat-info{flex:1;min-width:0}
.stat-date{font-size:.88rem;font-weight:700;margin-bottom:6px;color:var(--t1)}
.stat-pl{font-size:.65rem;color:var(--purple);margin-bottom:5px}
.stat-views-big{font-size:1.4rem;font-weight:800;letter-spacing:-.04em;color:var(--t1);line-height:1}
.stat-views-big span{font-size:.65rem;color:var(--t2);font-weight:500;margin-left:4px;letter-spacing:0}
.stat-sent-big{font-size:1.15rem;font-weight:800;color:var(--green);line-height:1}
.stat-sent-big span{font-size:.65rem;color:var(--t2);font-weight:500;margin-left:4px}
.stat-na{font-size:.7rem;color:var(--t3);font-style:italic}
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
.btn-spinning .btn-ico{display:inline-block;animation:spin .7s linear infinite}
.empty{text-align:center;padding:28px;color:var(--t2);font-size:.75rem;line-height:1.8}
.empty-ico{font-size:1.6rem;opacity:.18;margin-bottom:6px}

/* Modal */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:100;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.overlay.hidden{display:none}
.modal{background:#141414;border:1px solid var(--b2);border-radius:var(--r);padding:20px;width:360px;max-width:92vw;max-height:88vh;overflow-y:auto}
.modal-t{font-size:.9rem;font-weight:700;margin-bottom:2px}
.modal-s{font-size:.72rem;color:var(--t2);margin-bottom:14px}
.fld{margin-bottom:10px}
.fld label{display:block;font-size:.63rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--t2);margin-bottom:4px}
.fld input{width:100%;background:#0a0a0a;border:1px solid var(--b2);border-radius:var(--r2);padding:8px 10px;color:var(--t1);font-size:.82rem;outline:none;transition:.12s}
.fld input:focus{border-color:var(--purple)}
.merr{color:#f87171;font-size:.7rem;margin-top:4px;min-height:14px}
.mbtns{display:flex;gap:6px;margin-top:12px}
.mbtns .btn{flex:1}
.launch-accs,.acc-checks-modal{display:flex;flex-direction:column;gap:4px;max-height:185px;overflow-y:auto;margin-top:4px}
.l-acc{display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:var(--r2);background:#0a0a0a;border:1px solid var(--b1);cursor:pointer;transition:.12s}
.l-acc:hover{border-color:var(--b2)}.l-acc.sel{border-color:var(--purple);background:rgba(139,92,246,.07)}
.l-acc input{accent-color:var(--purple);flex-shrink:0}
.l-acc-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.l-acc-name{font-size:.74rem;flex:1}

/* Sélection multiple stories */
.sitem-sel{outline:2px solid var(--purple);background:rgba(139,92,246,.08)!important}
.sitem-cb{width:16px;height:16px;accent-color:var(--purple);cursor:pointer;flex-shrink:0}
.sel-bar{position:sticky;bottom:0;background:var(--c2);border-top:1px solid var(--b2);padding:8px 10px;display:flex;gap:6px;align-items:center;z-index:10}
.sel-bar-count{font-size:.7rem;color:var(--t2);flex:1;white-space:nowrap}
.rp-hd-btns{display:flex;gap:5px;align-items:center}
/* Stats live */
.live-story-row{display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:8px;background:var(--c2);border:1px solid var(--b1);margin-bottom:6px}
.live-views-num{font-size:1.1rem;font-weight:800;color:var(--t1);min-width:38px;text-align:right}
.live-dot{width:7px;height:7px;border-radius:50%;background:#22c55e;flex-shrink:0;box-shadow:0 0 6px #22c55e}
/* Toast */
.tw{position:fixed;bottom:15px;right:15px;z-index:200;display:flex;flex-direction:column;gap:4px}
.toast{background:#181818;border:1px solid var(--b2);border-radius:var(--r2);padding:7px 11px;font-size:.76rem;display:flex;align-items:center;gap:6px;box-shadow:0 4px 14px rgba(0,0,0,.4);max-width:260px;animation:tIn .18s ease}
.toast.ok{border-left:3px solid var(--green)}.toast.err{border-left:3px solid var(--red)}.toast.inf{border-left:3px solid var(--blue)}
@keyframes tIn{from{opacity:0;transform:translateX(8px)}to{opacity:1;transform:none}}
</style>
</head>
<body>
<!-- Écran de verrouillage — affiché après logout -->
<div id="loginScreen" style="display:none;position:fixed;inset:0;z-index:99999;background:#0a0b0d;overflow-y:auto">

  <!-- ═══════════════════════════════ LANDING PAGE ═══════════════════════════════ -->
  <div id="landingPanel" style="display:none;min-height:100vh;color:#fff;font-family:inherit;background:#080809">
    <style>
      .lp-btn-primary{background:linear-gradient(135deg,#7c3aed,#4f46e5);border:none;color:#fff;padding:14px 30px;border-radius:12px;cursor:pointer;font-size:.95rem;font-weight:700;box-shadow:0 4px 24px rgba(124,58,237,.4);transition:transform .15s,box-shadow .15s}
      .lp-btn-primary:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(124,58,237,.55)}
      .lp-btn-ghost{background:rgba(255,255,255,.04);border:1px solid #222;color:#ccc;padding:14px 28px;border-radius:12px;cursor:pointer;font-size:.95rem;transition:all .15s}
      .lp-btn-ghost:hover{background:rgba(255,255,255,.08);border-color:#444;color:#fff}
      .lp-feat-card{background:#0d0d0f;border:1px solid #1c1c22;border-radius:18px;padding:28px;transition:border-color .2s,transform .2s}
      .lp-feat-card:hover{border-color:rgba(124,58,237,.4);transform:translateY(-3px)}
      .lp-check{color:#a78bfa;font-weight:700}
      .lp-cross{color:#333}
      .lp-tag{display:inline-block;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.3);color:#a78bfa;border-radius:20px;padding:5px 14px;font-size:.7rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-bottom:22px}
      .lp-section-title{font-size:clamp(1.6rem,3vw,2.2rem);font-weight:900;letter-spacing:-.03em;margin:0 0 10px}
      .lp-section-sub{color:#555;font-size:.92rem;line-height:1.7}
      .lp-divider{height:1px;background:linear-gradient(90deg,transparent,#1c1c22,transparent);margin:0}
      .lp-plat-badge{display:flex;align-items:center;gap:8px;background:#0d0d0f;border:1px solid #1c1c22;border-radius:12px;padding:10px 18px;font-size:.82rem;color:#aaa;transition:border-color .2s}
      .lp-plat-badge:hover{border-color:rgba(124,58,237,.35);color:#fff}
      .lp-step-num{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#7c3aed,#4f46e5);display:flex;align-items:center;justify-content:center;font-size:.95rem;font-weight:900;flex-shrink:0}
      .lp-price-card{background:#0d0d0f;border:1px solid #1c1c22;border-radius:22px;padding:32px}
      .lp-price-card-pro{background:linear-gradient(145deg,#13102e,#0f0c22);border:1.5px solid #5b4fe8;border-radius:22px;padding:32px;box-shadow:0 0 60px rgba(79,70,229,.15)}
      .lp-faq-item{border-bottom:1px solid #111;padding:20px 0;cursor:pointer}
      .lp-testi{background:#0d0d0f;border:1px solid #1c1c22;border-radius:18px;padding:26px}
      @keyframes lp-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
      .lp-float{animation:lp-float 4s ease-in-out infinite}
      @keyframes lp-pulse-glow{0%,100%{box-shadow:0 0 20px rgba(124,58,237,.3)}50%{box-shadow:0 0 40px rgba(124,58,237,.6)}}
    </style>

    <!-- ── Nav ── -->
    <nav style="display:flex;align-items:center;justify-content:space-between;padding:16px 5%;border-bottom:1px solid #111;position:sticky;top:0;background:rgba(8,8,9,.93);backdrop-filter:blur(14px);z-index:100">
      <div style="display:flex;align-items:center;gap:10px">
        <div style="width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#7c3aed,#4f46e5);display:flex;align-items:center;justify-content:center"><svg width="22" height="22" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"><line x1="16" y1="16" x2="16" y2="5" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="24.7" y2="11" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="24.7" y2="21" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="16" y2="27" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="7.3" y2="21" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="7.3" y2="11" stroke="white" stroke-width="2.4" stroke-linecap="round"/><circle cx="16" cy="5" r="2.5" fill="white"/><circle cx="24.7" cy="11" r="2.5" fill="white"/><circle cx="24.7" cy="21" r="2.5" fill="white"/><circle cx="16" cy="27" r="2.5" fill="white"/><circle cx="7.3" cy="21" r="2.5" fill="white"/><circle cx="7.3" cy="11" r="2.5" fill="white"/><circle cx="16" cy="16" r="2.8" fill="white"/></svg></div>
        <span style="font-weight:900;font-size:1.1rem;letter-spacing:-.03em">Story<span style="color:#a78bfa">Scheduler</span></span>
      </div>
      <div style="display:flex;align-items:center;gap:24px">
        <a onclick="document.getElementById('lp-features').scrollIntoView({behavior:'smooth'})" style="font-size:.82rem;color:#666;cursor:pointer;transition:color .15s" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#666'">Fonctionnalités</a>
        <a onclick="document.getElementById('lp-pricing').scrollIntoView({behavior:'smooth'})" style="font-size:.82rem;color:#666;cursor:pointer;transition:color .15s" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#666'">Tarifs</a>
        <a onclick="document.getElementById('lp-faq').scrollIntoView({behavior:'smooth'})" style="font-size:.82rem;color:#666;cursor:pointer;transition:color .15s" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#666'">FAQ</a>
      </div>
      <div style="display:flex;gap:8px">
        <button onclick="_showLogin()" class="lp-btn-ghost" style="padding:9px 18px;font-size:.82rem;border-radius:9px">Se connecter</button>
        <button onclick="_showRegister()" class="lp-btn-primary" style="padding:9px 18px;font-size:.82rem;border-radius:9px">Commencer →</button>
      </div>
    </nav>

    <!-- ── Hero ── -->
    <div style="position:relative;overflow:hidden">
      <div style="position:absolute;inset:0;background:radial-gradient(ellipse 80% 60% at 50% -10%,rgba(124,58,237,.18),transparent);pointer-events:none"></div>
      <div style="text-align:center;padding:90px 5% 70px;max-width:820px;margin:0 auto;position:relative">
        <div class="lp-tag">✨ AUTOMATISATION MULTI-PLATEFORMES</div>
        <h1 style="font-size:clamp(2.2rem,5.5vw,3.6rem);font-weight:900;line-height:1.08;margin:0 0 22px;letter-spacing:-.035em">Publie sur tous tes réseaux<br><span style="background:linear-gradient(135deg,#a78bfa,#7c3aed,#60a5fa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">sans lever le petit doigt</span></h1>
        <p style="font-size:1.08rem;color:#5a5a6e;max-width:560px;margin:0 auto 40px;line-height:1.75">Programme tes stories et posts Telegram, Snapchat, Instagram et Facebook des semaines à l'avance. L'auto-scheduling choisit les créneaux pour toi — 24h/24, 7j/7.</p>
        <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-bottom:52px">
          <button onclick="_showRegister()" class="lp-btn-primary" style="font-size:1rem;padding:15px 34px">Créer mon compte gratuitement →</button>
          <button onclick="_showLogin()" class="lp-btn-ghost" style="font-size:1rem;padding:15px 28px">J'ai déjà un compte</button>
        </div>
        <div style="display:flex;justify-content:center;gap:10px;flex-wrap:wrap">
          <div class="lp-plat-badge"><svg width="20" height="20" viewBox="0 0 240 240" style="flex-shrink:0"><defs><radialGradient id="tgGlp" cx="50%" cy="15%" r="90%"><stop offset="0%" stop-color="#37AEE2"/><stop offset="100%" stop-color="#1E96C8"/></radialGradient></defs><circle cx="120" cy="120" r="120" fill="url(#tgGlp)"/><path fill="#fff" d="M20.665 100.68c49.238-21.462 82.064-35.607 98.477-42.437 46.905-19.52 56.629-22.918 62.959-23.04 1.396-.024 4.52.322 6.547 1.97 1.707 1.389 2.177 3.262 2.405 4.576.229 1.315.512 4.306.284 6.647-2.548 26.78-13.558 91.763-19.161 121.77-2.369 12.696-7.038 16.951-11.561 17.36-9.826.906-17.294-6.492-26.828-12.73-14.913-9.766-23.33-15.844-37.82-25.386-16.718-11.016-5.882-17.068 3.638-26.978 2.49-2.583 45.749-41.925 46.575-45.503.104-.447.201-2.113-1.28-2.994-1.481-.88-3.666-.577-5.243-.339-2.233.336-37.78 24.014-106.64 70.58-10.091 6.929-19.232 10.308-27.424 10.132-9.025-.193-26.383-5.108-39.284-9.306-15.832-5.148-28.405-7.875-27.324-16.619.565-4.561 6.867-9.225 18.905-14.003z"/></svg> Telegram</div>
          <div class="lp-plat-badge"><svg width="20" height="20" viewBox="0 0 48 48" style="flex-shrink:0;border-radius:22%"><rect width="48" height="48" rx="9" fill="#FFFC00"/><path fill="white" d="M24 7c-5.3 0-9.5 4.1-9.5 9.2v1.4c-1 .3-2.2.6-3 .6h-.5c-.11-.02-.2.07-.17.18.28.7 1.46 1.37 2.24 1.65.07.02.13.09.14.17.38 1.76 1.08 3.23 2.1 4.35-1.33.75-2.66 1.55-2.66 2.92 0 .98.84 1.73 2.57 2.18.17.05.3.18.31.35.21.98.58 1.91 1.06 2.47-.47.2-.9.4-.9.7 0 .54.83 1.03 2.33 1.03h1.25c.82.76 1.94 1.22 3.3 1.22s2.48-.46 3.3-1.22h1.25c1.5 0 2.33-.49 2.33-1.03 0-.3-.43-.5-.9-.7.48-.56.85-1.49 1.06-2.47.01-.17.14-.3.31-.35 1.73-.45 2.57-1.2 2.57-2.18 0-1.37-1.33-2.17-2.66-2.92 1.02-1.12 1.72-2.59 2.1-4.35.01-.08.07-.15.14-.17.78-.28 1.96-.95 2.24-1.65.03-.11-.06-.2-.17-.18h-.05c-.78 0-1.9-.27-3-.6v-1.4C33.5 11.1 29.3 7 24 7z"/></svg> Snapchat</div>
          <div class="lp-plat-badge"><svg width="20" height="20" viewBox="0 0 100 100" style="flex-shrink:0;border-radius:22%"><defs><radialGradient id="lpIgG2" cx="30%" cy="110%" r="140%"><stop offset="0%" stop-color="#ffd600"/><stop offset="10%" stop-color="#ff7a00"/><stop offset="50%" stop-color="#ff0069"/><stop offset="75%" stop-color="#d300c5"/><stop offset="100%" stop-color="#7638fa"/></radialGradient></defs><rect width="100" height="100" rx="22" fill="url(#lpIgG2)"/><rect x="12" y="12" width="76" height="76" rx="16" fill="none" stroke="white" stroke-width="6.5"/><circle cx="50" cy="50" r="18" fill="none" stroke="white" stroke-width="6.5"/><circle cx="71" cy="29" r="5" fill="white"/></svg> Instagram</div>
          <div class="lp-plat-badge"><svg width="20" height="20" viewBox="0 0 100 100" style="flex-shrink:0;border-radius:22%"><rect width="100" height="100" rx="22" fill="#1877F2"/><path fill="#fff" d="M62.5 53h-8.8v30.3H40.2V53H34V41.2h6.2v-7.4c0-8.6 3.6-13.8 13.4-13.8 3.9 0 8.4.4 8.4.4v9.2h-4.7c-3.5 0-4.7 2.2-4.7 4.5v7.1h9.3L60.5 53z"/></svg> Facebook</div>
        </div>
      </div>
    </div>

    <!-- ── Stats bar ── -->
    <div class="lp-divider"></div>
    <div style="background:#0a0a0c;padding:28px 5%">
      <div style="max-width:900px;margin:0 auto;display:flex;justify-content:space-around;flex-wrap:wrap;gap:20px">
        <div style="text-align:center">
          <div style="font-size:1.9rem;font-weight:900;letter-spacing:-.04em;background:linear-gradient(135deg,#a78bfa,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">10 000+</div>
          <div style="font-size:.75rem;color:#444;margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:.08em">Stories publiées</div>
        </div>
        <div style="text-align:center">
          <div style="font-size:1.9rem;font-weight:900;letter-spacing:-.04em;background:linear-gradient(135deg,#a78bfa,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">4</div>
          <div style="font-size:.75rem;color:#444;margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:.08em">Plateformes supportées</div>
        </div>
        <div style="text-align:center">
          <div style="font-size:1.9rem;font-weight:900;letter-spacing:-.04em;background:linear-gradient(135deg,#a78bfa,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">99.9%</div>
          <div style="font-size:.75rem;color:#444;margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:.08em">Uptime garanti</div>
        </div>
        <div style="text-align:center">
          <div style="font-size:1.9rem;font-weight:900;letter-spacing:-.04em;background:linear-gradient(135deg,#a78bfa,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">3h+</div>
          <div style="font-size:.75rem;color:#444;margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:.08em">Économisées / semaine</div>
        </div>
      </div>
    </div>
    <div class="lp-divider"></div>

    <!-- ── Comment ça marche ── -->
    <div style="padding:80px 5%;max-width:960px;margin:0 auto">
      <div style="text-align:center;margin-bottom:56px">
        <div class="lp-tag">COMMENT ÇA MARCHE</div>
        <h2 class="lp-section-title">3 étapes, c'est tout</h2>
        <p class="lp-section-sub" style="max-width:440px;margin:0 auto">Pas de configuration complexe. Tu es opérationnel en moins de 5 minutes.</p>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px">
        <div style="display:flex;flex-direction:column;gap:16px;padding:28px;background:#0d0d0f;border:1px solid #1c1c22;border-radius:18px">
          <div style="display:flex;align-items:center;gap:14px">
            <div class="lp-step-num">1</div>
            <div style="font-weight:800;font-size:1rem">Connecte tes comptes</div>
          </div>
          <p style="font-size:.85rem;color:#4a4a5a;line-height:1.7;margin:0">Ajoute tes comptes Telegram, Snapchat, Instagram et Facebook. La connexion est sécurisée et ne prend que quelques secondes par compte.</p>
        </div>
        <div style="display:flex;flex-direction:column;gap:16px;padding:28px;background:#0d0d0f;border:1px solid #1c1c22;border-radius:18px">
          <div style="display:flex;align-items:center;gap:14px">
            <div class="lp-step-num">2</div>
            <div style="font-weight:800;font-size:1rem">Upload tes médias</div>
          </div>
          <p style="font-size:.85rem;color:#4a4a5a;line-height:1.7;margin:0">Crée des playlists avec tes photos et vidéos. Organise ton contenu une fois, réutilise-le sur toutes tes plateformes en un clic.</p>
        </div>
        <div style="display:flex;flex-direction:column;gap:16px;padding:28px;background:#0d0d0f;border:1px solid #1c1c22;border-radius:18px">
          <div style="display:flex;align-items:center;gap:14px">
            <div class="lp-step-num">3</div>
            <div style="font-weight:800;font-size:1rem">L'IA publie à ta place</div>
          </div>
          <p style="font-size:.85rem;color:#4a4a5a;line-height:1.7;margin:0">Active l'auto-scheduling et oublie. StoryScheduler choisit les créneaux, publie tes stories et te notifie. Tu n'as plus qu'à suivre les stats.</p>
        </div>
      </div>
    </div>

    <!-- ── Features ── -->
    <div id="lp-features" style="background:#050506;border-top:1px solid #111;border-bottom:1px solid #111;padding:80px 5%">
      <div style="max-width:1000px;margin:0 auto">
        <div style="text-align:center;margin-bottom:56px">
          <div class="lp-tag">FONCTIONNALITÉS</div>
          <h2 class="lp-section-title">Tout ce dont tu as besoin</h2>
          <p class="lp-section-sub" style="max-width:440px;margin:0 auto">Un outil complet pensé pour les créateurs sérieux et les agences.</p>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px">
          <div class="lp-feat-card">
            <div style="width:44px;height:44px;border-radius:12px;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.2);display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:16px">📅</div>
            <div style="font-weight:800;font-size:.95rem;margin-bottom:8px;color:#e5e5f0">Auto-scheduling intelligent</div>
            <div style="font-size:.8rem;color:#3a3a4a;line-height:1.65">Détecte automatiquement le prochain créneau libre pour chaque plateforme. Zéro conflit, zéro doublons.</div>
          </div>
          <div class="lp-feat-card">
            <div style="width:44px;height:44px;border-radius:12px;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.2);display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:16px">📚</div>
            <div style="font-weight:800;font-size:.95rem;margin-bottom:8px;color:#e5e5f0">Bibliothèque de médias</div>
            <div style="font-size:.8rem;color:#3a3a4a;line-height:1.65">Crée des playlists réutilisables et déploie-les sur toutes tes plateformes d'un seul clic.</div>
          </div>
          <div class="lp-feat-card">
            <div style="width:44px;height:44px;border-radius:12px;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.2);display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:16px">👥</div>
            <div style="font-weight:800;font-size:.95rem;margin-bottom:8px;color:#e5e5f0">Multi-profils isolés</div>
            <div style="font-size:.8rem;color:#3a3a4a;line-height:1.65">Gère plusieurs créateurs depuis un seul dashboard. Chaque profil a ses comptes, playlists et stats séparés.</div>
          </div>
          <div class="lp-feat-card">
            <div style="width:44px;height:44px;border-radius:12px;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.2);display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:16px">⚡</div>
            <div style="font-weight:800;font-size:.95rem;margin-bottom:8px;color:#e5e5f0">Publication instantanée</div>
            <div style="font-size:.8rem;color:#3a3a4a;line-height:1.65">Upload via Cloudinary, publication via OneUp. Tes médias sont traités et envoyés sans aucune intervention.</div>
          </div>
          <div class="lp-feat-card">
            <div style="width:44px;height:44px;border-radius:12px;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.2);display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:16px">📊</div>
            <div style="font-weight:800;font-size:.95rem;margin-bottom:8px;color:#e5e5f0">Stats & revenus en temps réel</div>
            <div style="font-size:.8rem;color:#3a3a4a;line-height:1.65">Visualise tes revenus, le nombre de posts envoyés, le taux d'erreur et les graphiques par plateforme.</div>
          </div>
          <div class="lp-feat-card">
            <div style="width:44px;height:44px;border-radius:12px;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.2);display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:16px">🔄</div>
            <div style="font-weight:800;font-size:.95rem;margin-bottom:8px;color:#e5e5f0">Spotlight Snapchat automatique</div>
            <div style="font-size:.8rem;color:#3a3a4a;line-height:1.65">Pool de vidéos tournant en boucle sur tes comptes Snapchat. Un compte, +1 min, en automatique.</div>
          </div>
          <div class="lp-feat-card">
            <div style="width:44px;height:44px;border-radius:12px;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.2);display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:16px">🔐</div>
            <div style="font-weight:800;font-size:.95rem;margin-bottom:8px;color:#e5e5f0">Accès par PIN sécurisé</div>
            <div style="font-size:.8rem;color:#3a3a4a;line-height:1.65">Chaque profil est protégé par un PIN. Idéal pour les agences qui gèrent plusieurs créateurs.</div>
          </div>
          <div class="lp-feat-card">
            <div style="width:44px;height:44px;border-radius:12px;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.2);display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:16px">📡</div>
            <div style="font-weight:800;font-size:.95rem;margin-bottom:8px;color:#e5e5f0">Monitoring en direct</div>
            <div style="font-size:.8rem;color:#3a3a4a;line-height:1.65">Suis tes stories actives en temps réel avec les miniatures, le nombre de vues et le statut de chaque publication.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Pricing ── -->
    <div id="lp-pricing" style="padding:80px 5%">
      <div style="max-width:940px;margin:0 auto">
        <div style="text-align:center;margin-bottom:56px">
          <div class="lp-tag">TARIFS</div>
          <h2 class="lp-section-title">Simple et transparent</h2>
          <p class="lp-section-sub" style="max-width:380px;margin:0 auto">Sans engagement. Annulable à tout moment. Pas de surprise.</p>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px;align-items:start">

          <!-- Starter -->
          <div class="lp-price-card">
            <div style="font-size:.68rem;font-weight:800;letter-spacing:.1em;color:#555;text-transform:uppercase;margin-bottom:16px">STARTER</div>
            <div style="font-size:2.6rem;font-weight:900;letter-spacing:-.04em;margin-bottom:2px;color:#fff">15€<span style="font-size:.95rem;font-weight:400;color:#333">/mois</span></div>
            <div style="color:#333;font-size:.8rem;margin-bottom:28px;border-bottom:1px solid #111;padding-bottom:20px">Pour démarrer seul</div>
            <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:30px">
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> <strong style="color:#ccc">10 comptes</strong> Telegram/Snapchat</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> Telegram + Snapchat</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> 50 médias en bibliothèque</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> Auto-scheduling</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#2a2a2a"><span class="lp-cross">✗</span> Instagram / Facebook</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#2a2a2a"><span class="lp-cross">✗</span> Statistiques avancées</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#2a2a2a"><span class="lp-cross">✗</span> Spotlight Snapchat</div>
            </div>
            <button onclick="_showRegister()" class="lp-btn-ghost" style="width:100%;padding:12px;font-size:.88rem;font-weight:700;border-radius:10px">Commencer</button>
          </div>

          <!-- Pro -->
          <div class="lp-price-card-pro" style="position:relative">
            <div style="position:absolute;top:-13px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg,#7c3aed,#4f46e5);border-radius:20px;padding:5px 16px;font-size:.65rem;font-weight:800;letter-spacing:.07em;color:#fff;white-space:nowrap">⭐ LE PLUS POPULAIRE</div>
            <div style="font-size:.68rem;font-weight:800;letter-spacing:.1em;color:#a78bfa;text-transform:uppercase;margin-bottom:16px">PRO</div>
            <div style="font-size:2.6rem;font-weight:900;letter-spacing:-.04em;margin-bottom:2px;color:#fff">39€<span style="font-size:.95rem;font-weight:400;color:#5550a0">/mois</span></div>
            <div style="color:#4a4570;font-size:.8rem;margin-bottom:28px;border-bottom:1px solid rgba(124,58,237,.15);padding-bottom:20px">Pour les créateurs actifs</div>
            <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:30px">
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#c4b5fd"><span style="color:#a78bfa;font-weight:700">✓</span> <strong style="color:#e9d5ff">25 comptes</strong> toutes plateformes</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#c4b5fd"><span style="color:#a78bfa;font-weight:700">✓</span> Telegram + Snapchat + IG + FB</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#c4b5fd"><span style="color:#a78bfa;font-weight:700">✓</span> Bibliothèque illimitée</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#c4b5fd"><span style="color:#a78bfa;font-weight:700">✓</span> Auto-scheduling avancé</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#c4b5fd"><span style="color:#a78bfa;font-weight:700">✓</span> Statistiques & suivi des revenus</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#c4b5fd"><span style="color:#a78bfa;font-weight:700">✓</span> Spotlight Snapchat automatique</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#c4b5fd"><span style="color:#a78bfa;font-weight:700">✓</span> Monitoring en temps réel</div>
            </div>
            <button onclick="_showRegister()" class="lp-btn-primary" style="width:100%;padding:13px;font-size:.88rem;border-radius:10px">Choisir Pro →</button>
          </div>

          <!-- Business -->
          <div class="lp-price-card">
            <div style="font-size:.68rem;font-weight:800;letter-spacing:.1em;color:#555;text-transform:uppercase;margin-bottom:16px">BUSINESS</div>
            <div style="font-size:2.6rem;font-weight:900;letter-spacing:-.04em;margin-bottom:2px;color:#fff">239€<span style="font-size:.95rem;font-weight:400;color:#333">/mois</span></div>
            <div style="color:#333;font-size:.8rem;margin-bottom:28px;border-bottom:1px solid #111;padding-bottom:20px">Pour les agences & studios</div>
            <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:30px">
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> <strong style="color:#ccc">Comptes illimités</strong></div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> Toutes plateformes</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> Bibliothèque illimitée</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> Accès API prioritaire</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> Support dédié 7j/7</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> Onboarding personnalisé</div>
              <div style="display:flex;gap:10px;align-items:flex-start;font-size:.82rem;color:#888"><span class="lp-check">✓</span> SLA 99.9% uptime garanti</div>
            </div>
            <button onclick="_showRegister()" class="lp-btn-ghost" style="width:100%;padding:12px;font-size:.88rem;font-weight:700;border-radius:10px">Nous contacter</button>
          </div>

        </div>
        <p style="text-align:center;margin-top:24px;font-size:.75rem;color:#252530">Sans carte bancaire pour commencer · Annulable à tout moment · Paiement 100% sécurisé</p>
      </div>
    </div>

    <!-- ── Testimonials ── -->
    <div style="background:#050506;border-top:1px solid #111;border-bottom:1px solid #111;padding:80px 5%">
      <div style="max-width:960px;margin:0 auto">
        <div style="text-align:center;margin-bottom:56px">
          <div class="lp-tag">TÉMOIGNAGES</div>
          <h2 class="lp-section-title">Ce qu'ils en disent</h2>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px">
          <div class="lp-testi">
            <div style="color:#f59e0b;font-size:.95rem;margin-bottom:14px;letter-spacing:3px">★★★★★</div>
            <p style="color:#888;font-size:.85rem;line-height:1.8;margin:0 0 20px;font-style:italic">"Depuis que j'utilise StoryScheduler, je programme mes stories à l'avance et j'économise au moins 3h par semaine. L'auto-scheduling est une révolution !"</p>
            <div style="display:flex;align-items:center;gap:12px">
              <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#7c3aed,#ec4899);display:flex;align-items:center;justify-content:center;font-size:.9rem;font-weight:800;color:#fff;flex-shrink:0">P</div>
              <div>
                <div style="font-weight:800;font-size:.82rem;color:#ddd">Pauline M.</div>
                <div style="font-size:.72rem;color:#333;margin-top:2px">Créatrice de contenu · Snapchat</div>
              </div>
            </div>
          </div>
          <div class="lp-testi">
            <div style="color:#f59e0b;font-size:.95rem;margin-bottom:14px;letter-spacing:3px">★★★★★</div>
            <p style="color:#888;font-size:.85rem;line-height:1.8;margin:0 0 20px;font-style:italic">"La gestion multi-profils est parfaite pour notre agence. On gère 8 créatrices depuis un seul dashboard sans jamais mélanger les contenus."</p>
            <div style="display:flex;align-items:center;gap:12px">
              <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#1877F2,#42A5F5);display:flex;align-items:center;justify-content:center;font-size:.9rem;font-weight:800;color:#fff;flex-shrink:0">S</div>
              <div>
                <div style="font-weight:800;font-size:.82rem;color:#ddd">Sarah K.</div>
                <div style="font-size:.72rem;color:#333;margin-top:2px">Responsable agence · Instagram & FB</div>
              </div>
            </div>
          </div>
          <div class="lp-testi">
            <div style="color:#f59e0b;font-size:.95rem;margin-bottom:14px;letter-spacing:3px">★★★★★</div>
            <p style="color:#888;font-size:.85rem;line-height:1.8;margin:0 0 20px;font-style:italic">"J'ai multiplié ma fréquence de publication par 4 grâce aux playlists. Je prépare tout le dimanche et ça tourne toute la semaine. Indispensable."</p>
            <div style="display:flex;align-items:center;gap:12px">
              <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#2CA5E0,#1a6b99);display:flex;align-items:center;justify-content:center;font-size:.9rem;font-weight:800;color:#fff;flex-shrink:0">L</div>
              <div>
                <div style="font-weight:800;font-size:.82rem;color:#ddd">Lucas T.</div>
                <div style="font-size:.72rem;color:#333;margin-top:2px">Creator Manager · Telegram</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── FAQ ── -->
    <div id="lp-faq" style="padding:80px 5%;max-width:760px;margin:0 auto">
      <div style="text-align:center;margin-bottom:56px">
        <div class="lp-tag">FAQ</div>
        <h2 class="lp-section-title">Questions fréquentes</h2>
      </div>
      <div id="lpFaqList">
        <div class="lp-faq-item" onclick="lpToggleFaq(this)">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px">
            <span style="font-weight:700;font-size:.9rem;color:#ddd">C'est quoi StoryScheduler exactement ?</span>
            <span style="color:#7c3aed;font-size:1.1rem;flex-shrink:0;transition:transform .2s" class="lp-faq-icon">+</span>
          </div>
          <div class="lp-faq-body" style="display:none;margin-top:14px;font-size:.83rem;color:#444;line-height:1.75">StoryScheduler est une plateforme SaaS d'automatisation de publication de stories et posts sur Telegram, Snapchat, Instagram et Facebook. Tu uploades tes médias, tu configures tes comptes, et le système publie automatiquement au bon moment — même quand tu dors.</div>
        </div>
        <div class="lp-faq-item" onclick="lpToggleFaq(this)">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px">
            <span style="font-weight:700;font-size:.9rem;color:#ddd">Est-ce que c'est sécurisé pour mes comptes ?</span>
            <span style="color:#7c3aed;font-size:1.1rem;flex-shrink:0;transition:transform .2s" class="lp-faq-icon">+</span>
          </div>
          <div class="lp-faq-body" style="display:none;margin-top:14px;font-size:.83rem;color:#444;line-height:1.75">Oui. Les connexions Telegram passent par l'API officielle Telethon. Instagram et Facebook utilisent l'API OneUp certifiée Meta. Aucun mot de passe n'est stocké en clair — tout est chiffré. Tes credentials ne sont jamais partagés avec des tiers.</div>
        </div>
        <div class="lp-faq-item" onclick="lpToggleFaq(this)">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px">
            <span style="font-weight:700;font-size:.9rem;color:#ddd">Combien de comptes puis-je connecter ?</span>
            <span style="color:#7c3aed;font-size:1.1rem;flex-shrink:0;transition:transform .2s" class="lp-faq-icon">+</span>
          </div>
          <div class="lp-faq-body" style="display:none;margin-top:14px;font-size:.83rem;color:#444;line-height:1.75">Il n'y a pas de limite au nombre de comptes par plateforme. Tu peux connecter autant de comptes Telegram, Snapchat, Instagram et Facebook que tu veux dans chaque profil. Seul le nombre de profils créateurs est limité selon ton plan.</div>
        </div>
        <div class="lp-faq-item" onclick="lpToggleFaq(this)">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px">
            <span style="font-weight:700;font-size:.9rem;color:#ddd">Comment fonctionne l'auto-scheduling ?</span>
            <span style="color:#7c3aed;font-size:1.1rem;flex-shrink:0;transition:transform .2s" class="lp-faq-icon">+</span>
          </div>
          <div class="lp-faq-body" style="display:none;margin-top:14px;font-size:.83rem;color:#444;line-height:1.75">Quand tu ajoutes un média à programmer, le système analyse ton calendrier existant et choisit automatiquement la prochaine date libre disponible. Tu n'as jamais à saisir d'heure manuellement. Les publications se font à intervalles réguliers pour maximiser l'engagement.</div>
        </div>
        <div class="lp-faq-item" onclick="lpToggleFaq(this)">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px">
            <span style="font-weight:700;font-size:.9rem;color:#ddd">Puis-je annuler à tout moment ?</span>
            <span style="color:#7c3aed;font-size:1.1rem;flex-shrink:0;transition:transform .2s" class="lp-faq-icon">+</span>
          </div>
          <div class="lp-faq-body" style="display:none;margin-top:14px;font-size:.83rem;color:#444;line-height:1.75">Oui, sans engagement et sans frais de résiliation. Tu peux annuler ton abonnement à n'importe quel moment depuis ton dashboard. Tes données sont conservées 30 jours après l'annulation.</div>
        </div>
        <div class="lp-faq-item" onclick="lpToggleFaq(this)" style="border-bottom:none">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px">
            <span style="font-weight:700;font-size:.9rem;color:#ddd">Quelle est la différence entre les plans ?</span>
            <span style="color:#7c3aed;font-size:1.1rem;flex-shrink:0;transition:transform .2s" class="lp-faq-icon">+</span>
          </div>
          <div class="lp-faq-body" style="display:none;margin-top:14px;font-size:.83rem;color:#444;line-height:1.75">Le plan Starter (29€) couvre 2 profils avec Telegram et Snapchat uniquement. Le plan Pro (49€) débloque toutes les plateformes (Instagram, Facebook), les statistiques avancées, le Spotlight Snapchat et 5 profils. Le plan Business (99€) est pour les agences avec des profils illimités et un support dédié.</div>
        </div>
      </div>
    </div>

    <!-- ── CTA Footer ── -->
    <div style="position:relative;overflow:hidden;background:linear-gradient(135deg,#0d0b20,#0a0818,#0d0b20);border-top:1px solid #1a1737;padding:80px 5%;text-align:center">
      <div style="position:absolute;inset:0;background:radial-gradient(ellipse 60% 80% at 50% 120%,rgba(124,58,237,.2),transparent);pointer-events:none"></div>
      <div style="position:relative">
        <div class="lp-tag" style="margin-bottom:24px">PRÊT À DÉMARRER ?</div>
        <h2 style="font-size:clamp(1.8rem,4vw,2.8rem);font-weight:900;margin:0 0 16px;letter-spacing:-.035em;line-height:1.1">Publie en pilote automatique<br><span style="background:linear-gradient(135deg,#a78bfa,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">dès aujourd'hui</span></h2>
        <p style="color:#3a3a50;margin-bottom:40px;font-size:.95rem;max-width:440px;margin-left:auto;margin-right:auto;line-height:1.7">Rejoins des centaines de créateurs qui font confiance à StoryScheduler pour publier leur contenu 24h/24.</p>
        <button onclick="_showRegister()" class="lp-btn-primary" style="font-size:1.05rem;padding:16px 42px">Créer mon compte gratuitement →</button>
        <div style="margin-top:16px;font-size:.75rem;color:#1e1e2e">Sans carte bancaire · Sans engagement · Annulable à tout moment</div>
        <div style="margin-top:52px;padding-top:32px;border-top:1px solid #111;display:flex;justify-content:center;align-items:center;gap:32px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;gap:8px;font-size:.8rem;color:#252535"><span style="font-size:1rem">📅</span> StoryScheduler</div>
          <div style="font-size:.75rem;color:#1c1c28">© 2025 StoryScheduler · Tous droits réservés</div>
          <div style="display:flex;gap:20px">
            <span style="font-size:.75rem;color:#1c1c28;cursor:pointer" onmouseover="this.style.color='#555'" onmouseout="this.style.color='#1c1c28'">Mentions légales</span>
            <span style="font-size:.75rem;color:#1c1c28;cursor:pointer" onmouseover="this.style.color='#555'" onmouseout="this.style.color='#1c1c28'">CGU</span>
            <span style="font-size:.75rem;color:#1c1c28;cursor:pointer" onmouseover="this.style.color='#555'" onmouseout="this.style.color='#1c1c28'">Contact</span>
          </div>
        </div>
      </div>
    </div>
  </div>
  <!-- ══════════════════════════════════════════════════════════════════════════════ -->

  <div id="loginFormWrapper" style="min-height:100%;display:flex;align-items:center;justify-content:center;padding:40px 20px">
    <div style="max-width:380px;width:100%">

      <!-- === PANNEAU CONNEXION === -->
      <div id="loginPanel">
        <div style="text-align:center;margin-bottom:40px">
          <div style="width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#7c3aed,#4f46e5);display:flex;align-items:center;justify-content:center;margin:0 auto 16px"><svg width="38" height="38" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"><line x1="16" y1="16" x2="16" y2="5" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="24.7" y2="11" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="24.7" y2="21" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="16" y2="27" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="7.3" y2="21" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="7.3" y2="11" stroke="white" stroke-width="2.4" stroke-linecap="round"/><circle cx="16" cy="5" r="2.5" fill="white"/><circle cx="24.7" cy="11" r="2.5" fill="white"/><circle cx="24.7" cy="21" r="2.5" fill="white"/><circle cx="16" cy="27" r="2.5" fill="white"/><circle cx="7.3" cy="21" r="2.5" fill="white"/><circle cx="7.3" cy="11" r="2.5" fill="white"/><circle cx="16" cy="16" r="2.8" fill="white"/></svg></div>
          <div style="color:#fff;font-size:1.4rem;font-weight:800;letter-spacing:-.01em">Connexion</div>
          <div style="color:#555;font-size:.82rem;margin-top:5px">Entrez vos identifiants pour accéder</div>
        </div>
        <form id="loginForm" onsubmit="return false" style="display:flex;flex-direction:column;gap:14px">
          <div>
            <label style="font-size:.75rem;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:6px">Identifiant</label>
            <input id="loginUsername" name="username" type="text" autocomplete="username" placeholder="Votre identifiant" style="width:100%;padding:13px 14px;background:#111;border:1px solid #222;border-radius:10px;color:#fff;font-size:.9rem;outline:none;box-sizing:border-box;transition:border-color .15s" onfocus="this.style.borderColor='#7c3aed'" onblur="this.style.borderColor='#222'">
          </div>
          <div>
            <label style="font-size:.75rem;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:6px">Mot de passe</label>
            <div style="position:relative">
              <input id="loginPassword" name="password" type="password" autocomplete="current-password" placeholder="Votre mot de passe" style="width:100%;padding:13px 42px 13px 14px;background:#111;border:1px solid #222;border-radius:10px;color:#fff;font-size:.9rem;outline:none;box-sizing:border-box;transition:border-color .15s" onfocus="this.style.borderColor='#7c3aed'" onblur="this.style.borderColor='#222'">
              <button type="button" onclick="const i=document.getElementById('loginPassword');i.type=i.type==='password'?'text':'password'" style="position:absolute;right:12px;top:50%;transform:translateY(-50%);background:none;border:none;color:#555;cursor:pointer;font-size:.85rem;padding:4px">👁</button>
            </div>
          </div>
          <div id="loginErr" style="color:#f87171;font-size:.78rem;min-height:18px;text-align:center"></div>
          <button type="submit" id="loginBtn" onclick="_doLogin()" style="padding:14px;background:linear-gradient(135deg,#7c3aed,#4f46e5);border:none;border-radius:10px;color:#fff;font-size:.95rem;font-weight:700;cursor:pointer;transition:opacity .15s;margin-top:4px" onmouseover="this.style.opacity='.88'" onmouseout="this.style.opacity='1'">Se connecter</button>
        </form>
        <div style="text-align:center;margin-top:18px">
          <span style="color:#444;font-size:.8rem">Pas encore de compte ?</span>
          <button onclick="_showLanding()" style="background:none;border:none;color:#8b5cf6;font-size:.8rem;font-weight:600;cursor:pointer;margin-left:6px;text-decoration:underline;padding:0">Créer un compte</button>
        </div>
      </div>

      <!-- === PANNEAU INSCRIPTION === -->
      <div id="registerPanel" style="display:none">
        <div style="text-align:center;margin-bottom:32px">
          <div style="width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#7c3aed,#4f46e5);display:flex;align-items:center;justify-content:center;margin:0 auto 16px"><svg width="38" height="38" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"><line x1="16" y1="16" x2="16" y2="5" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="24.7" y2="11" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="24.7" y2="21" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="16" y2="27" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="7.3" y2="21" stroke="white" stroke-width="2.4" stroke-linecap="round"/><line x1="16" y1="16" x2="7.3" y2="11" stroke="white" stroke-width="2.4" stroke-linecap="round"/><circle cx="16" cy="5" r="2.5" fill="white"/><circle cx="24.7" cy="11" r="2.5" fill="white"/><circle cx="24.7" cy="21" r="2.5" fill="white"/><circle cx="16" cy="27" r="2.5" fill="white"/><circle cx="7.3" cy="21" r="2.5" fill="white"/><circle cx="7.3" cy="11" r="2.5" fill="white"/><circle cx="16" cy="16" r="2.8" fill="white"/></svg></div>
          <div style="color:#fff;font-size:1.4rem;font-weight:800;letter-spacing:-.01em">Créer un compte</div>
          <div style="color:#555;font-size:.82rem;margin-top:5px">Nouveau compte pour accéder au dashboard</div>
        </div>
        <form id="registerForm" onsubmit="return false" style="display:flex;flex-direction:column;gap:14px">
          <div>
            <label style="font-size:.75rem;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:6px">Nom affiché</label>
            <input id="regName" name="name" type="text" autocomplete="name" placeholder="Ex: LOUNA" style="width:100%;padding:13px 14px;background:#111;border:1px solid #222;border-radius:10px;color:#fff;font-size:.9rem;outline:none;box-sizing:border-box;transition:border-color .15s" onfocus="this.style.borderColor='#7c3aed'" onblur="this.style.borderColor='#222'">
          </div>
          <div>
            <label style="font-size:.75rem;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:6px">Identifiant (email)</label>
            <input id="regLogin" name="email" type="email" autocomplete="email" placeholder="email@exemple.com" style="width:100%;padding:13px 14px;background:#111;border:1px solid #222;border-radius:10px;color:#fff;font-size:.9rem;outline:none;box-sizing:border-box;transition:border-color .15s" onfocus="this.style.borderColor='#7c3aed'" onblur="this.style.borderColor='#222'">
          </div>
          <div>
            <label style="font-size:.75rem;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:6px">Mot de passe</label>
            <div style="position:relative">
              <input id="regPassword" name="new-password" type="password" autocomplete="new-password" placeholder="Au moins 6 caractères" style="width:100%;padding:13px 42px 13px 14px;background:#111;border:1px solid #222;border-radius:10px;color:#fff;font-size:.9rem;outline:none;box-sizing:border-box;transition:border-color .15s" onfocus="this.style.borderColor='#7c3aed'" onblur="this.style.borderColor='#222'">
              <button type="button" onclick="const i=document.getElementById('regPassword');i.type=i.type==='password'?'text':'password'" style="position:absolute;right:12px;top:50%;transform:translateY(-50%);background:none;border:none;color:#555;cursor:pointer;font-size:.85rem;padding:4px">👁</button>
            </div>
          </div>
          <div>
            <label style="font-size:.75rem;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:6px">Confirmer le mot de passe</label>
            <input id="regConfirm" type="password" autocomplete="new-password" placeholder="Répétez le mot de passe" style="width:100%;padding:13px 14px;background:#111;border:1px solid #222;border-radius:10px;color:#fff;font-size:.9rem;outline:none;box-sizing:border-box;transition:border-color .15s" onfocus="this.style.borderColor='#7c3aed'" onblur="this.style.borderColor='#222'">
          </div>
          <div id="registerErr" style="color:#f87171;font-size:.78rem;min-height:18px;text-align:center"></div>
          <button type="submit" id="registerBtn" onclick="_doRegister()" style="padding:14px;background:linear-gradient(135deg,#7c3aed,#4f46e5);border:none;border-radius:10px;color:#fff;font-size:.95rem;font-weight:700;cursor:pointer;transition:opacity .15s;margin-top:4px" onmouseover="this.style.opacity='.88'" onmouseout="this.style.opacity='1'">Créer le compte</button>
        </form>
        <div style="text-align:center;margin-top:18px">
          <span style="color:#444;font-size:.8rem">Déjà un compte ?</span>
          <button onclick="_showLogin()" style="background:none;border:none;color:#8b5cf6;font-size:.8rem;font-weight:600;cursor:pointer;margin-left:6px;text-decoration:underline;padding:0">Se connecter</button>
        </div>
      </div>

    </div>
  </div>
</div>
<script>
// Check on page load if not authenticated
document.addEventListener('DOMContentLoaded', async function(){
  try{
    const r = await fetch('/api/auth/check');
    if(!r.ok){ _showLoginScreenRaw(); return; }
    const d = await r.json().catch(()=>({}));
    _sessionIsAdmin = !!d.is_admin;
    const appEl=document.querySelector('.app');
    if(appEl)appEl.style.display='';
    reloadAllData();
    loadProfiles();
  } catch(e){ _showLoginScreenRaw(); }
});
function _showLoginScreenRaw(){
  const ls=document.getElementById('loginScreen');
  const app=document.querySelector('.app');
  if(ls){ls.style.display='block';}
  if(app){app.style.display='none';}
  const lp=document.getElementById('landingPanel');
  const lw=document.getElementById('loginFormWrapper');
  if(lp)lp.style.display='block';
  if(lw)lw.style.display='none';
}
// Enter key support
document.addEventListener('keydown',function(e){
  if(e.key==='Enter'&&document.getElementById('loginScreen').style.display!=='none'){
    _doLogin();
  }
});
</script>
<div class="app" style="display:none">
  <aside class="sidebar">
    <div class="sb-logo">
      <div class="sb-logo-icon">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
          <!-- Hub central -->
          <circle cx="14" cy="14" r="3.5" fill="white" opacity="0.95"/>
          <!-- Noeuds satellites -->
          <circle cx="14" cy="4" r="2.5" fill="white" opacity="0.8"/>
          <circle cx="23" cy="9.5" r="2.5" fill="white" opacity="0.8"/>
          <circle cx="23" cy="18.5" r="2.5" fill="white" opacity="0.8"/>
          <circle cx="14" cy="24" r="2.5" fill="white" opacity="0.8"/>
          <circle cx="5" cy="18.5" r="2.5" fill="white" opacity="0.8"/>
          <circle cx="5" cy="9.5" r="2.5" fill="white" opacity="0.8"/>
          <!-- Connexions -->
          <line x1="14" y1="10.5" x2="14" y2="6.5" stroke="white" stroke-width="1.3" stroke-opacity="0.5"/>
          <line x1="17" y1="12" x2="21" y2="11" stroke="white" stroke-width="1.3" stroke-opacity="0.5"/>
          <line x1="17" y1="16" x2="21" y2="17" stroke="white" stroke-width="1.3" stroke-opacity="0.5"/>
          <line x1="14" y1="17.5" x2="14" y2="21.5" stroke="white" stroke-width="1.3" stroke-opacity="0.5"/>
          <line x1="11" y1="16" x2="7" y2="17" stroke="white" stroke-width="1.3" stroke-opacity="0.5"/>
          <line x1="11" y1="12" x2="7" y2="11" stroke="white" stroke-width="1.3" stroke-opacity="0.5"/>
        </svg>
      </div>
      <div><div class="sb-logo-name">Propriétaire de l&#x2019;agence</div><div class="sb-logo-sub">Mael</div></div>
    </div>
    <nav class="sb-nav">
      <button class="sb-item active" data-page="schedule"><span class="sb-item-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg></span>Telegram<span class="sb-badge orange" id="badgePending" style="display:none">0</span></button>
      <button class="sb-item" data-page="snapchat"><span class="sb-item-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C9.1 2 6.8 4.2 6.8 6.9v1c-.72.22-1.52.42-2.04.42-.1 0-.2 0-.3-.02-.09-.01-.16.06-.13.14.22.55 1.14 1.06 1.75 1.28.05.02.09.07.1.12.29 1.37.83 2.52 1.61 3.35-1.16.66-2.79 1.37-2.79 2.6 0 .87.73 1.52 2.23 1.9.14.04.24.15.27.28.16.75.45 1.47.82 1.9-.28.12-.68.24-.68.6 0 .41.51.63 1.43.63h.76c.63.58 1.49.95 2.54.95s1.91-.37 2.54-.95h.76c.92 0 1.43-.22 1.43-.63 0-.36-.4-.48-.68-.6.37-.43.66-1.15.82-1.9.03-.13.13-.24.27-.28 1.5-.38 2.23-1.03 2.23-1.9 0-1.23-1.63-1.94-2.79-2.6.78-.83 1.32-1.98 1.61-3.35.01-.05.05-.1.1-.12.61-.22 1.53-.73 1.75-1.28.03-.08-.04-.15-.13-.14-.1.02-.2.02-.3.02-.52 0-1.32-.2-2.04-.42v-1C17.2 4.2 14.9 2 12 2z"/></svg></span>Snapchat<span class="sb-badge" id="badgeSnap" style="display:none">0</span></button>
      <button class="sb-item" data-page="instagram"><span class="sb-item-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4.5"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg></span>Instagram</button>
      <button class="sb-item sb-item-soon" onclick="showComingSoon('Threads')"><span class="sb-item-ico"><svg width="16" height="16" viewBox="0 0 192 192" fill="currentColor"><path d="M141.537 88.988c-.829-.394-1.67-.776-2.52-1.141-1.483-27.307-16.403-42.94-41.457-43.1h-.333c-14.986 0-27.449 6.397-35.12 17.037l13.779 9.452c5.73-8.695 14.724-10.548 21.347-10.548h.228c8.25.053 14.474 2.451 18.503 7.129 2.932 3.405 4.893 8.111 5.864 14.05-7.314-1.243-15.224-1.625-23.68-1.14-23.82 1.372-39.134 15.265-38.105 34.569.521 9.792 5.399 18.216 13.734 23.719 7.047 4.652 16.124 6.927 25.557 6.412 12.458-.683 22.231-5.436 29.049-14.127 5.178-6.6 8.453-15.153 9.899-25.93 5.937 3.583 10.337 8.298 12.767 13.966 4.132 9.635 4.373 25.468-8.546 38.376-11.319 11.308-24.925 16.2-45.488 16.351-22.809-.169-40.06-7.484-51.275-21.742C30.7 152.633 25.272 133.35 25.07 108.667c.202-24.683 5.63-43.967 16.132-57.318C52.418 37.081 69.668 29.766 92.477 29.597c23.226.171 41.127 7.698 53.212 22.39 5.937 7.286 10.393 16.35 13.322 27.038l16.148-4.308C171.72 61.637 166.307 50.71 158.941 41.65 143.812 23.283 121.978 13.87 93.845 13.676h-.333C65.248 13.87 43.658 23.318 29.154 41.755 16.248 58.162 9.59 81 9.366 109.617l-.001.05.001.05c.224 28.617 6.882 51.447 19.788 67.854 14.504 18.437 36.094 27.885 64.169 28.079h.333c24.96-.173 42.554-6.884 57.048-21.353 18.963-18.734 18.392-42.52 12.142-57.28-4.661-10.929-13.685-19.402-24.723-24.379l.413.35zM98.44 129.507c-10.44.588-21.286-4.098-21.821-14.135-.394-7.442 5.298-15.746 22.464-16.735 1.966-.113 3.895-.168 5.79-.168 6.235 0 12.068.606 17.371 1.765-1.978 24.702-13.58 28.713-23.804 29.273z"/></svg></span>Threads<span style="font-size:.52rem;background:linear-gradient(135deg,#833ab4,#fd1d1d,#fcb045);color:#fff;padding:1px 5px;border-radius:4px;margin-left:5px;font-weight:700">SOON</span></button>
      <button class="sb-item" data-page="facebook"><span class="sb-item-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg></span>Facebook</button>
      <button class="sb-item" data-page="playlists"><span class="sb-item-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg></span>Médias</button>
      <button class="sb-item" data-page="stats"><span class="sb-item-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></span>Statistiques</button>
      <button class="sb-item" data-page="revenue"><span class="sb-item-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><text x="12" y="18" font-size="18" font-family="system-ui,sans-serif" font-weight="900" text-anchor="middle">$</text></svg></span>Revenus</button>
      <div class="sb-sep"></div>
      <button class="sb-item" data-page="accounts"><span class="sb-item-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-3.866 3.582-7 8-7s8 3.134 8 7"/></svg></span>Comptes<span class="sb-badge" id="badgeAccounts" style="display:none">0</span></button>
    </nav>
    <div class="sb-bottom">
      <div class="sb-profile-wrap" id="sbProfileWrap">
        <div class="sb-profile-menu" id="sbProfileMenu" style="display:none">
          <div id="sbProfileList"></div>
          <div class="sb-profile-menu-sep"></div>
          <button class="sb-profile-menu-item" onclick="openProfileManager()">⚙️ Gérer les profils</button>
          <button class="sb-profile-menu-item" onclick="newProfileQuick()">＋ Nouveau profil</button>
        </div>
        <div class="sb-profile-btn" id="sbProfileBtn" onclick="toggleProfileMenu()">
          <div class="sb-profile-avatar" id="sbProfileAvatar">?</div>
          <div class="sb-profile-info">
            <div class="sb-profile-name" id="sbProfileName">Chargement…</div>
            <div class="sb-profile-sub">Profil actif</div>
          </div>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" style="flex-shrink:0;opacity:.4"><path d="M7 14l5-5 5 5z"/></svg>
        </div>
      </div>
      <div class="sb-util-btns">
        <button class="sb-util-btn" onclick="openSubModal()" id="sbSubBtn">
          <div class="sb-util-ico" style="background:rgba(124,58,237,.18)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg></div>
          <span id="sbSubLabel">Mon abonnement</span>
        </button>
        <button class="sb-util-btn" onclick="switchToDocs()">
          <div class="sb-util-ico"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg></div>
          Docs
        </button>
        <button class="sb-util-btn danger" onclick="confirmLogout()">
          <div class="sb-util-ico"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg></div>
          Logout
        </button>
      </div>
      <div class="sb-status"><div class="sb-dot" id="sbDot"></div><span id="sbText">Chargement…</span></div>
    </div>
  </aside>

  <!-- Subscription modal -->
  <style>
    #subModal .sub-box{background:linear-gradient(160deg,#0d0b1a,#080810);border:1px solid #1e1b3a;border-radius:24px;padding:32px 28px;width:580px;max-width:96vw;max-height:90vh;overflow-y:auto;position:relative}
    #subModal .sub-box::before{content:'';position:absolute;inset:0;border-radius:24px;background:radial-gradient(ellipse 60% 40% at 50% 0%,rgba(124,58,237,.12),transparent 70%);pointer-events:none}
    .sub-plan-card{border-radius:16px;padding:18px 20px;position:relative;overflow:hidden;transition:.2s}
    .sub-plan-card.active{box-shadow:0 0 32px rgba(124,58,237,.25)}
    .sub-pay-btn{width:100%;padding:14px;border-radius:14px;border:none;font-size:.82rem;font-weight:800;cursor:pointer;transition:all .2s;position:relative;overflow:hidden}
    .sub-pay-btn:hover{transform:translateY(-1px)}
    .sub-pay-btn:disabled{opacity:.5;cursor:wait;transform:none}
    @keyframes sub-spinner-rot{to{transform:rotate(360deg)}}
    @keyframes sub-grad-shift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
    .sub-spinner{width:13px;height:13px;border-radius:50%;border:2px solid currentColor;border-top-color:transparent;display:inline-block;animation:sub-spinner-rot .7s linear infinite;margin-right:6px;vertical-align:middle}
  </style>
  <div class="pin-modal" id="subModal" onclick="if(event.target===this)this.classList.remove('open')">
    <div class="sub-box" onclick="event.stopPropagation()">
      <!-- Header -->
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:28px">
        <div>
          <div style="font-size:1.3rem;font-weight:900;letter-spacing:-.03em;color:#fff">Mon abonnement</div>
          <div style="font-size:.75rem;color:#555;margin-top:3px">Gérer ton forfait</div>
        </div>
        <button onclick="document.getElementById('subModal').classList.remove('open')" style="background:rgba(255,255,255,.06);border:1px solid #2a2040;color:#888;cursor:pointer;width:32px;height:32px;border-radius:10px;font-size:1rem;display:flex;align-items:center;justify-content:center;transition:.15s" onmouseover="this.style.background='rgba(255,255,255,.1)'" onmouseout="this.style.background='rgba(255,255,255,.06)'">✕</button>
      </div>

      <!-- Forfait actuel -->
      <div id="subCurrentPlan" style="margin-bottom:24px">
        <div style="font-size:.6rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:#444;margin-bottom:10px">Forfait actuel</div>
        <div class="sub-plan-card" style="background:rgba(255,255,255,.03);border:1px solid #1e1b3a">
          <div style="display:flex;align-items:center;gap:14px">
            <div id="subPlanBadge" style="font-size:2rem;width:48px;height:48px;display:flex;align-items:center;justify-content:center;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.2);border-radius:14px"></div>
            <div>
              <div id="subPlanName" style="font-size:1.15rem;font-weight:900;color:#fff;letter-spacing:-.02em">—</div>
              <div id="subPlanPrice" style="font-size:.8rem;color:#555;margin-top:3px">—</div>
            </div>
          </div>
          <div id="subPlanFeats" style="margin-top:14px;display:flex;flex-wrap:wrap;gap:6px"></div>
        </div>
      </div>

      <!-- Admin section -->
      <div id="subAdminSection" style="display:none;margin-bottom:8px">
        <div style="font-size:.6rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:#444;margin-bottom:12px">Modifier le forfait <span style="color:#7c3aed;background:rgba(124,58,237,.1);padding:2px 7px;border-radius:5px;font-size:.6rem">ADMIN</span></div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
          <button onclick="subSetPlan('')" id="subBtnNone" style="padding:12px 6px;border-radius:12px;border:1px solid #222;background:#0d0b1a;color:#555;font-size:.72rem;font-weight:700;cursor:pointer;transition:.15s">🔒<br><span style="font-size:.6rem;font-weight:400">Aucun</span></button>
          <button onclick="subSetPlan('starter')" id="subBtnStarter" style="padding:12px 6px;border-radius:12px;border:1px solid #2a2040;background:#100e20;color:#a78bfa;font-size:.72rem;font-weight:700;cursor:pointer;transition:.15s">⚡<br><span style="font-size:.6rem;font-weight:400">Starter<br>15€</span></button>
          <button onclick="subSetPlan('pro')" id="subBtnPro" style="padding:12px 6px;border-radius:12px;border:1px solid #5b4fe8;background:linear-gradient(145deg,#13102e,#0f0c22);color:#a78bfa;font-size:.72rem;font-weight:700;cursor:pointer;box-shadow:0 0 16px rgba(91,79,232,.2);transition:.15s">🚀<br><span style="font-size:.6rem;font-weight:400">Pro<br>39€</span></button>
          <button onclick="subSetPlan('business')" id="subBtnBusiness" style="padding:12px 6px;border-radius:12px;border:1px solid #1e3a5f;background:#0a1628;color:#60a5fa;font-size:.72rem;font-weight:700;cursor:pointer;transition:.15s">🏢<br><span style="font-size:.6rem;font-weight:400">Business<br>239€</span></button>
        </div>
        <div id="subSaveStatus" style="margin-top:10px;font-size:.72rem;min-height:16px;text-align:center"></div>
      </div>

      <!-- User payment section -->
      <div id="subUserSection" style="display:none">
        <div style="font-size:.6rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:#444;margin-bottom:14px">Choisir un forfait</div>
        <div style="display:flex;flex-direction:column;gap:10px">

          <!-- Starter -->
          <div style="border-radius:16px;padding:1px;background:linear-gradient(135deg,#2a2040,#1e1b3a)">
            <div style="border-radius:15px;background:#0d0b1a;padding:16px 18px;display:flex;align-items:center;gap:14px">
              <div style="width:40px;height:40px;border-radius:12px;background:rgba(167,139,250,.1);border:1px solid rgba(167,139,250,.2);display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0">⚡</div>
              <div style="flex:1">
                <div style="font-weight:800;font-size:.9rem;color:#fff">Starter</div>
                <div style="font-size:.72rem;color:#555;margin-top:1px">10 comptes · Auto-scheduling · Telegram</div>
              </div>
              <div style="text-align:right;flex-shrink:0;margin-right:12px">
                <div style="font-size:1.2rem;font-weight:900;color:#a78bfa">15€</div>
                <div style="font-size:.62rem;color:#444">/mois</div>
              </div>
              <button class="sub-pay-btn" onclick="subPayPlan('starter')" id="subPayStarter" style="width:auto;padding:10px 18px;background:rgba(167,139,250,.12);border:1px solid rgba(167,139,250,.25);color:#a78bfa">S'abonner</button>
            </div>
          </div>

          <!-- Pro -->
          <div style="border-radius:16px;padding:1px;background:linear-gradient(135deg,#7c3aed,#4f46e5,#a78bfa,#4f46e5,#7c3aed);background-size:300%;animation:sub-grad-shift 3s ease infinite" id="subProWrap">
            <div style="border-radius:15px;background:linear-gradient(145deg,#13102e,#0f0c22);padding:16px 18px;display:flex;align-items:center;gap:14px;position:relative">
              <div style="position:absolute;top:-10px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff;font-size:.6rem;font-weight:900;padding:3px 12px;border-radius:99px;white-space:nowrap;letter-spacing:.05em">✦ POPULAIRE ✦</div>
              <div style="width:40px;height:40px;border-radius:12px;background:rgba(124,58,237,.2);border:1px solid rgba(124,58,237,.3);display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0">🚀</div>
              <div style="flex:1">
                <div style="font-weight:800;font-size:.9rem;color:#fff">Pro</div>
                <div style="font-size:.72rem;color:#7c6aad;margin-top:1px">25 comptes · Stats · Toutes plateformes</div>
              </div>
              <div style="text-align:right;flex-shrink:0;margin-right:12px">
                <div style="font-size:1.2rem;font-weight:900;background:linear-gradient(135deg,#a78bfa,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">39€</div>
                <div style="font-size:.62rem;color:#444">/mois</div>
              </div>
              <button class="sub-pay-btn" onclick="subPayPlan('pro')" id="subPayPro" style="width:auto;padding:10px 18px;background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff;box-shadow:0 0 20px rgba(124,58,237,.4)">S'abonner</button>
            </div>
          </div>

          <!-- Business -->
          <div style="border-radius:16px;padding:1px;background:linear-gradient(135deg,#1e3a5f,#0a1628)">
            <div style="border-radius:15px;background:#080f1e;padding:16px 18px;display:flex;align-items:center;gap:14px">
              <div style="width:40px;height:40px;border-radius:12px;background:rgba(96,165,250,.08);border:1px solid rgba(96,165,250,.15);display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0">🏢</div>
              <div style="flex:1">
                <div style="font-weight:800;font-size:.9rem;color:#fff">Business</div>
                <div style="font-size:.72rem;color:#555;margin-top:1px">Illimité · Support dédié · SLA 99.9%</div>
              </div>
              <div style="text-align:right;flex-shrink:0;margin-right:12px">
                <div style="font-size:1.2rem;font-weight:900;color:#60a5fa">239€</div>
                <div style="font-size:.62rem;color:#444">/mois</div>
              </div>
              <button class="sub-pay-btn" onclick="subPayPlan('business')" id="subPayBusiness" style="width:auto;padding:10px 18px;background:rgba(96,165,250,.1);border:1px solid rgba(96,165,250,.2);color:#60a5fa">S'abonner</button>
            </div>
          </div>
        </div>

        <div id="subPayStatus" style="margin-top:12px;font-size:.75rem;text-align:center;color:#888;min-height:16px"></div>
        <div style="margin-top:14px;display:flex;align-items:center;justify-content:center;gap:6px;font-size:.68rem;color:#2a2840">
          <span>🔒</span><span>Paiement 100% sécurisé via Stripe</span><span>·</span><span>Sans engagement</span><span>·</span><span>Annule quand tu veux</span>
        </div>
      </div>

    </div>
  </div>

  <!-- Coming soon modal -->
  <div class="pin-modal" id="comingSoonModal" onclick="this.classList.remove('open')">
    <div class="pin-box" onclick="event.stopPropagation()" style="width:360px;padding:40px 36px;text-align:center">
      <div style="font-size:3.5rem;margin-bottom:16px;line-height:1" id="comingSoonEmoji">📸</div>
      <div style="font-size:1.5rem;font-weight:900;margin-bottom:10px" id="comingSoonTitle">Instagram</div>
      <div style="font-size:1.1rem;font-weight:800;color:var(--t1);margin-bottom:8px">Bientôt disponible</div>
      <div style="font-size:.78rem;color:var(--t3);line-height:1.5;margin-bottom:24px">Cette fonctionnalité est en cours de développement.<br>Elle sera disponible dans une prochaine mise à jour.</div>
      <button class="btn btn-primary" onclick="document.getElementById('comingSoonModal').classList.remove('open')" style="width:100%;padding:10px">OK</button>
    </div>
  </div>

  <!-- PIN unlock modal -->
  <div class="pin-modal" id="pinModal">
    <div class="pin-box">
      <h3>🔒 Profil verrouillé</h3>
      <p id="pinModalLabel">Entre le code PIN</p>
      <div class="pin-dots" id="pinDots">
        <div class="pin-dot" id="pd0"></div>
        <div class="pin-dot" id="pd1"></div>
        <div class="pin-dot" id="pd2"></div>
        <div class="pin-dot" id="pd3"></div>
      </div>
      <div class="pin-grid">
        <button class="pin-key" onclick="pinKey('1')">1</button>
        <button class="pin-key" onclick="pinKey('2')">2</button>
        <button class="pin-key" onclick="pinKey('3')">3</button>
        <button class="pin-key" onclick="pinKey('4')">4</button>
        <button class="pin-key" onclick="pinKey('5')">5</button>
        <button class="pin-key" onclick="pinKey('6')">6</button>
        <button class="pin-key" onclick="pinKey('7')">7</button>
        <button class="pin-key" onclick="pinKey('8')">8</button>
        <button class="pin-key" onclick="pinKey('9')">9</button>
        <button class="pin-key" onclick="pinKey('')" style="font-size:.8rem;color:var(--t3)">←</button>
        <button class="pin-key" onclick="pinKey('0')">0</button>
        <button class="pin-key" onclick="pinKey('')" style="font-size:.8rem;color:var(--t3)">✕</button>
      </div>
      <button class="pin-cancel" onclick="pinCancel()">Annuler</button>
    </div>
  </div>

  <!-- Profile Manager Modal -->
  <div class="pm-modal" id="pmModal">
    <div class="pm-box">
      <div class="pm-hd">
        <h2>👤 Gestion des profils</h2>
        <button class="btn btn-xs" onclick="closeProfileManager()" style="padding:4px 10px">✕</button>
      </div>
      <div class="pm-body">
        <div class="pm-list" id="pmList">
          <button class="pm-new-btn" onclick="pmNewProfile()">＋ Nouveau profil</button>
        </div>
        <div class="pm-form" id="pmForm">
          <div style="color:var(--t3);font-size:.8rem;text-align:center;margin-top:40px">← Sélectionne un profil</div>
        </div>
      </div>
    </div>
  </div>

  <div class="main">
    <!-- Plan paywall overlay (shown when no plan active) -->
    <div id="planPaywall" class="plan-lock-overlay" style="display:none">
      <div style="text-align:center;margin-bottom:28px">
        <div style="font-size:2rem;margin-bottom:10px">🔒</div>
        <div style="font-size:1.2rem;font-weight:900;color:#fff;letter-spacing:-.02em">Aucun forfait actif</div>
        <div style="font-size:.83rem;color:#444;margin-top:6px;max-width:380px">Ce profil n'a pas encore de forfait. Contacte l'administrateur pour activer l'accès.</div>
      </div>
      <div class="plan-cards-wrap">
        <div class="plan-card">
          <div style="font-size:.62rem;font-weight:800;letter-spacing:.1em;color:#555;text-transform:uppercase">STARTER</div>
          <div class="plan-price">15€<span style="font-size:.8rem;font-weight:400;color:#333">/mois</span></div>
          <div class="plan-sub">Telegram + Snapchat</div>
          <div class="plan-feat">✓ 10 comptes<br>✓ 50 médias<br>✓ Auto-scheduling<br>✗ Instagram/Facebook<br>✗ Statistiques</div>
        </div>
        <div class="plan-card plan-card-pro" style="position:relative">
          <div style="position:absolute;top:-10px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg,#7c3aed,#4f46e5);border-radius:20px;padding:3px 12px;font-size:.6rem;font-weight:800;color:#fff;white-space:nowrap">⭐ POPULAIRE</div>
          <div style="font-size:.62rem;font-weight:800;letter-spacing:.1em;color:#a78bfa;text-transform:uppercase">PRO</div>
          <div class="plan-price" style="background:linear-gradient(135deg,#a78bfa,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">39€<span style="font-size:.8rem;font-weight:400;-webkit-text-fill-color:#5550a0">/mois</span></div>
          <div class="plan-sub">Toutes plateformes</div>
          <div class="plan-feat">✓ 25 comptes<br>✓ Bibliothèque illimitée<br>✓ Stats & Revenus<br>✓ Spotlight Snapchat<br>✓ Instagram + Facebook</div>
        </div>
        <div class="plan-card">
          <div style="font-size:.62rem;font-weight:800;letter-spacing:.1em;color:#555;text-transform:uppercase">BUSINESS</div>
          <div class="plan-price">239€<span style="font-size:.8rem;font-weight:400;color:#333">/mois</span></div>
          <div class="plan-sub">Agences & Studios</div>
          <div class="plan-feat">✓ Comptes illimités<br>✓ Toutes plateformes<br>✓ Support dédié 7j/7<br>✓ Onboarding perso<br>✓ SLA 99.9%</div>
        </div>
      </div>
      <div style="margin-top:22px;font-size:.75rem;color:#222;text-align:center">Contacte ton administrateur pour activer un forfait · Stripe bientôt disponible</div>
    </div>
    <div class="topbar">
      <div class="topbar-title" id="topTitle">Programmer</div>
      <div class="topbar-actions">
        <button class="btn btn-sm" id="btnClone" style="display:none">+ Compte</button>
      </div>
    </div>

    <div class="content-wrap">
      <div class="content-main">

        <!-- PAGE : Programmer -->
        <div class="page active" id="page-schedule">
          <div class="metrics">
            <div class="metric"><div class="metric-val" id="mPending">—</div><div class="metric-lbl">En attente</div></div>
            <div class="metric"><div class="metric-val" id="mDone">—</div><div class="metric-lbl">Envoyées</div></div>
            <div class="metric"><div class="metric-val" id="mAccounts">—</div><div class="metric-lbl">Comptes actifs</div></div>
            <div class="metric"><div class="metric-val" id="mPlaylists">—</div><div class="metric-lbl">Playlists</div></div>
          </div>
          <div class="panel">
            <div class="panel-hd"><div class="panel-title">📱 Photos Telegram</div></div>
            <div style="display:flex;justify-content:flex-end;margin-bottom:8px">
              <button class="btn btn-xs" id="tgBtnSavePl" style="background:#1a1a2e;border-color:#6366f1;color:#a5b4fc" disabled>&#x1F4BE; Sauvegarder dans Médias</button>
            </div>
            <div class="uz" id="uz">
              <input type="file" id="fi" accept="image/*" multiple>
              <div class="uz-ico">🖼</div>
              <div class="uz-txt"><b>Clique ou glisse</b> tes photos ici</div>
            </div>
            <div class="plist" id="plist"></div>
            <div class="no-p" id="noP">Aucune photo ajoutée</div>
            <div class="acc-section">
              <div class="acc-section-lbl">Poster sur :</div>
              <div class="acc-checks" id="accChecks"><div class="no-acc-warn">Aucun compte — ajoute un compte dans Comptes</div></div>
            </div>
            <div style="display:flex;gap:6px;margin-top:12px">
              <button class="btn btn-danger" id="btnSchedule" disabled style="flex:1">📅 Programmer</button>
              <button class="btn" id="btnClear">🗑 Vider</button>
            </div>
          </div>
        </div>

        <!-- PAGE : Instagram -->
        <div class="page" id="page-instagram">
          <div class="metrics" style="margin-bottom:12px">
            <div class="metric"><div class="metric-val" id="igMPending">—</div><div class="metric-lbl">En attente</div></div>
            <div class="metric"><div class="metric-val" id="igMDone">—</div><div class="metric-lbl">Envoyées</div></div>
            <div class="metric"><div class="metric-val" id="igMErr">—</div><div class="metric-lbl">Erreurs</div></div>
            <div class="metric"><div class="metric-val" id="igMAccounts">—</div><div class="metric-lbl">Comptes</div></div>
          </div>

          <div class="panel">
            <div class="panel-hd">
              <div class="panel-title" style="background:linear-gradient(135deg,#833ab4,#fd1d1d,#fcb045);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">📸 Programmer des Stories Instagram</div>
            </div>
            <div class="uz" id="igUz" style="border-color:#833ab430">
              <input type="file" id="igFi" accept="image/*,video/*" multiple>
              <div class="uz-ico">📸</div>
              <div class="uz-txt"><b>Photos / vidéos</b> — converties auto en 9:16 portrait</div>
            </div>
            <!-- Heure de programmation -->
            <div style="margin:10px 0;background:#0d0d0d;border:1px solid #1e1e1e;border-radius:8px;padding:10px 12px">
              <div style="font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#555;margin-bottom:8px">⏰ Heure de programmation</div>
              <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <label style="display:flex;align-items:center;gap:6px;font-size:.75rem;cursor:pointer">
                  <input type="radio" name="igDateMode" value="auto" checked id="igDateAuto"> Prochaine date libre
                </label>
                <label style="display:flex;align-items:center;gap:6px;font-size:.75rem;cursor:pointer">
                  <input type="radio" name="igDateMode" value="manual" id="igDateManual"> Manuel
                </label>
                <input type="datetime-local" id="igDateInput" style="display:none;background:var(--c1);border:1px solid var(--b2);color:var(--t1);border-radius:5px;padding:4px 8px;font-size:.72rem;color-scheme:dark">
              </div>
            </div>
            <div style="margin:8px 0">
              <input id="igCaption" class="acc-desc-inp" style="margin-top:0;font-size:.82rem;padding:8px 11px" placeholder="Légende (optionnelle)…">
            </div>
            <div style="display:flex;justify-content:flex-end;margin-bottom:8px">
              <button class="btn btn-xs" id="igBtnSavePl" style="background:#1a1a2e;border-color:#833ab4;color:#c084fc" disabled>💾 Sauvegarder dans Médias</button>
            </div>
            <div class="plist" id="igPlist"></div>
            <div class="no-p" id="igNoP">Aucune photo ajoutée</div>
            <div class="acc-section">
              <div class="acc-section-lbl">Comptes qui reçoivent la Story :</div>
              <div class="acc-checks" id="igAccChecks"><div class="no-acc-warn">Chargement…</div></div>
            </div>
            <div style="display:flex;gap:6px;margin-top:12px">
              <button class="btn btn-danger" id="igBtnSchedule" disabled style="flex:1;background:linear-gradient(135deg,#833ab4,#fd1d1d);border:none;color:#fff">📸 Programmer</button>
              <button class="btn" id="igBtnClear">🗑</button>
            </div>
            <div style="margin-top:8px;padding:7px 10px;background:rgba(131,58,180,.06);border:1px solid rgba(131,58,180,.2);border-radius:6px;font-size:.67rem;color:#aaa">
              ✅ Cloudinary → One Up · +1 min entre chaque compte
            </div>
          </div>

                  </div>

<!-- PAGE : Facebook -->
        <div class="page" id="page-facebook">
          <div class="metrics" style="margin-bottom:12px">
            <div class="metric"><div class="metric-val" id="fbMPending">—</div><div class="metric-lbl">En attente</div></div>
            <div class="metric"><div class="metric-val" id="fbMDone">—</div><div class="metric-lbl">Publiées</div></div>
            <div class="metric"><div class="metric-val" id="fbMErr">—</div><div class="metric-lbl">Erreurs</div></div>
            <div class="metric"><div class="metric-val" id="fbMAccounts">—</div><div class="metric-lbl">Comptes</div></div>
          </div>

          <div class="panel">
            <div class="panel-hd">
              <div class="panel-title" style="background:linear-gradient(135deg,#1877F2,#42A5F5);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">📘 Programmer des Posts Facebook</div>
            </div>
            <div class="uz" id="fbUz" style="border-color:#1877F230">
              <input type="file" id="fbFi" accept="image/*,video/*" multiple>
              <div class="uz-ico">📘</div>
              <div class="uz-txt"><b>Photos / vidéos</b> — upload via Cloudinary → OneUp</div>
            </div>
            <div style="display:flex;justify-content:flex-end;margin-bottom:8px">
              <button class="btn btn-xs" id="fbBtnSavePl" style="background:#1a1a2e;border-color:#1877F2;color:#60a5fa" disabled>💾 Sauvegarder dans Médias</button>
            </div>
            <div class="plist" id="fbPlist"></div>
            <div class="no-p" id="fbNoP">Aucune photo ajoutée</div>
            <div style="margin:10px 0;background:#0d0d0d;border:1px solid #1e1e1e;border-radius:8px;padding:10px 12px">
              <div style="font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#555;margin-bottom:8px">⏰ Heure de programmation</div>
              <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <label style="display:flex;align-items:center;gap:6px;font-size:.75rem;cursor:pointer">
                  <input type="radio" name="fbDateMode" value="auto" checked id="fbDateAuto"> Prochaine date libre
                </label>
                <label style="display:flex;align-items:center;gap:6px;font-size:.75rem;cursor:pointer">
                  <input type="radio" name="fbDateMode" value="manual" id="fbDateManual"> Manuel
                </label>
                <input type="datetime-local" id="fbDateInput" style="display:none;background:var(--c1);border:1px solid var(--b2);color:var(--t1);border-radius:5px;padding:4px 8px;font-size:.72rem;color-scheme:dark">
              </div>
            </div>
            <div style="margin:8px 0">
              <input id="fbCaption" class="acc-desc-inp" style="margin-top:0;font-size:.82rem;padding:8px 11px" placeholder="Texte du post (optionnel)…">
            </div>
            <div class="acc-section">
              <div class="acc-section-lbl">Pages / comptes qui reçoivent le post :</div>
              <div class="acc-checks" id="fbAccChecks"><div class="no-acc-warn">Chargement…</div></div>
            </div>
            <div style="display:flex;gap:6px;margin-top:12px">
              <button class="btn btn-danger" id="fbBtnSchedule" disabled style="flex:1;background:linear-gradient(135deg,#1877F2,#42A5F5);border:none;color:#fff">📘 Programmer (+1 min/compte)</button>
              <button class="btn" id="fbBtnClear">🗑</button>
            </div>
            <div style="margin-top:8px;padding:7px 10px;background:rgba(24,119,242,.06);border:1px solid rgba(24,119,242,.2);border-radius:6px;font-size:.67rem;color:#aaa">
              ✅ Cloudinary → One Up · +1 min entre chaque compte
            </div>
          </div>

        </div>

        <!-- PAGE : Playlists / Médias -->
        <div class="page" id="page-playlists">

          <!-- VUE LISTE : 4 colonnes TG / Snap / IG / FB -->
          <div id="mediaListView">
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:14px">
              <!-- Colonne Telegram -->
              <div>
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--b1)">
                  <svg width="28" height="28" viewBox="0 0 240 240"><circle cx="120" cy="120" r="120" fill="#2CA5E0"/><path fill="#FFF" fill-rule="evenodd" d="M20.665 100.68c49.238-21.462 82.064-35.607 98.477-42.437 46.905-19.52 56.629-22.918 62.959-23.04 1.396-.024 4.52.322 6.547 1.97 1.707 1.389 2.177 3.262 2.405 4.576.229 1.315.512 4.306.284 6.647-2.548 26.78-13.558 91.763-19.161 121.77-2.369 12.696-7.038 16.951-11.561 17.36-9.826.906-17.294-6.492-26.828-12.73-14.913-9.766-23.33-15.844-37.82-25.386-16.718-11.016-5.882-17.068 3.638-26.978 2.49-2.583 45.749-41.925 46.575-45.503.104-.447.201-2.113-1.28-2.994-1.481-.88-3.666-.577-5.243-.339-2.233.336-37.78 24.014-106.64 70.58-10.091 6.929-19.232 10.308-27.424 10.132-9.025-.193-26.383-5.108-39.284-9.306-15.832-5.148-28.405-7.875-27.324-16.619.565-4.561 6.867-9.225 18.905-14.003z"/></svg>
                  <span style="font-weight:800;font-size:1rem;letter-spacing:-.01em;color:var(--t1)">Telegram</span>
                  <button class="btn btn-xs" style="margin-left:auto;background:rgba(124,58,237,.15);border-color:rgba(124,58,237,.4);color:#a78bfa" onclick="openCreatePlaylist('tg')">+ Nouvelle</button>
                </div>
                <div id="tgMediaCol"><div style="color:var(--t3);font-size:.8rem;padding:10px 0">Aucune playlist</div></div>
              </div>
              <!-- Colonne Snapchat -->
              <div>
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--b1)">
                  <svg width="28" height="28" viewBox="0 0 100 100"><rect width="100" height="100" rx="20" fill="#FFFC00"/><path fill="#fff" d="M50 14c-8.8 0-15.9 7.1-15.9 15.8v3.5c-.7.2-1.6.4-2.3.4h-.5c-.2 0-.3.2-.2.4.5 1.2 2.3 2.2 3.5 2.6.1 0 .2.1.2.3.6 2.8 1.8 5.2 3.5 7-2.2 1.2-4.4 2.6-4.4 4.8 0 1.6 1.4 2.9 4.3 3.6l.5.1c.1.2.2.4.3.6.3 1.6.9 3 1.7 3.9-.7.3-1.4.7-1.4 1.4 0 .9 1.3 1.7 3.9 1.7h2c1.3 1.2 3.2 2 5.4 2s4.1-.8 5.4-2h2c2.6 0 3.9-.8 3.9-1.7 0-.7-.7-1.1-1.4-1.4.8-.9 1.4-2.3 1.7-3.9.1-.2.3-.4.5-.6 2.9-.7 4.3-2 4.3-3.6 0-2.2-2.2-3.6-4.4-4.8 1.7-1.8 2.9-4.2 3.5-7 0-.2.1-.3.2-.3 1.2-.4 3-1.4 3.5-2.6.1-.2-.1-.4-.2-.4h-.1c-.7 0-1.6-.2-2.3-.4v-3.5C65.9 21.1 58.8 14 50 14z"/></svg>
                  <span style="font-weight:800;font-size:1rem;letter-spacing:-.01em;color:var(--t1)">Snapchat</span>
                  <button class="btn btn-xs" style="margin-left:auto;background:rgba(245,197,24,.1);border-color:rgba(245,197,24,.4);color:#f5c518" onclick="openCreatePlaylist('snap')">+ Nouvelle</button>
                </div>
                <div id="snapMediaCol"><div style="color:var(--t3);font-size:.8rem;padding:10px 0">Aucune playlist</div></div>
              </div>
              <!-- Colonne Instagram -->
              <div>
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--b1)">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none"><rect width="24" height="24" rx="6" fill="url(#igGrad)"/><defs><linearGradient id="igGrad" x1="0" y1="24" x2="24" y2="0"><stop offset="0%" stop-color="#f09433"/><stop offset="25%" stop-color="#e6683c"/><stop offset="50%" stop-color="#dc2743"/><stop offset="75%" stop-color="#cc2366"/><stop offset="100%" stop-color="#bc1888"/></linearGradient></defs><rect x="2" y="2" width="20" height="20" rx="5" stroke="#fff" stroke-width="1.5"/><circle cx="12" cy="12" r="4.5" stroke="#fff" stroke-width="1.5"/><circle cx="17.5" cy="6.5" r="1" fill="#fff"/></svg>
                  <span style="font-weight:800;font-size:1rem;letter-spacing:-.01em;color:var(--t1)">Instagram</span>
                  <button class="btn btn-xs" style="margin-left:auto;background:rgba(131,58,180,.12);border-color:rgba(131,58,180,.5);color:#c084fc" onclick="openCreatePlaylist('ig')">+ Nouvelle</button>
                </div>
                <div id="igMediaCol"><div style="color:var(--t3);font-size:.8rem;padding:10px 0">Aucune playlist</div></div>
              </div>
              <!-- Colonne Facebook -->
              <div>
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--b1)">
                  <svg width="28" height="28" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" fill="#1877F2"/><path fill="#fff" d="M15.12 12.78h-2.1v7.22h-3V12.78H8.5V10.1h1.52V8.38C10.02 6.4 11.1 5 13.38 5c.97 0 2 .1 2 .1v2.2h-1.13c-.84 0-1.13.52-1.13 1.08V10.1h2.23l-.23 2.68z"/></svg>
                  <span style="font-weight:800;font-size:1rem;letter-spacing:-.01em;color:var(--t1)">Facebook</span>
                  <button class="btn btn-xs" style="margin-left:auto;background:rgba(24,119,242,.12);border-color:rgba(24,119,242,.5);color:#60a5fa" onclick="openCreatePlaylist('fb')">+ Nouvelle</button>
                </div>
                <div id="fbMediaCol"><div style="color:var(--t3);font-size:.8rem;padding:10px 0">Aucune playlist</div></div>
              </div>
            </div>
          </div>

          <!-- VUE DÉTAIL d'une playlist -->
          <div id="mediaDetailView" style="display:none">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap">
              <button class="btn btn-sm" id="mdBtnBack">← Retour</button>
              <div style="font-weight:700;font-size:.88rem;cursor:pointer;display:flex;align-items:center;gap:5px;user-select:none" id="mdTitle" title="Cliquer pour renommer">—<span style="font-size:.7rem;opacity:.4;font-weight:400">✏️</span></div>
              <span id="mdBadge" style="font-size:.65rem;padding:2px 8px;border-radius:20px;font-weight:700">—</span>
              <div style="margin-left:auto;display:flex;gap:6px;flex-wrap:wrap">
                <label class="btn btn-xs" style="cursor:pointer;background:#1a1a2e;border-color:#6366f1;color:#a5b4fc">
                  &#x2795; Ajouter photos<input type="file" id="mdAddFi" accept="image/*,video/*" multiple style="display:none">
                </label>
                <button class="btn btn-xs" id="mdBtnSave" style="background:#22543d;border-color:#48bb78;color:#9ae6b4">&#x1F4BE; Sauvegarder</button>
                <button class="btn btn-xs btn-danger" id="mdBtnDelete" style="background:#742a2a;border-color:#e23744;color:#fc8181">&#x1F5D1; Supprimer</button>
                <button class="btn btn-xs" id="mdBtnLoad" style="background:#f5c518;border-color:#f5c518;color:#000;font-weight:700">&#x25B6; Charger</button>
              </div>
            </div>
            <div id="mdGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px"></div>
          </div>

        </div>

        <!-- MODAL : Créer playlist -->
        <div class="pin-modal" id="createPlModal" onclick="if(event.target===this)closeCreatePlaylist()">
          <div class="pin-box" onclick="event.stopPropagation()" style="width:520px;max-width:96vw;max-height:90vh;overflow-y:auto;padding:28px 26px">
            <!-- Header -->
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
              <div id="cplIcon" style="width:36px;height:36px;border-radius:9px;display:flex;align-items:center;justify-content:center"></div>
              <div>
                <div style="font-size:1.05rem;font-weight:800" id="cplTitle">Nouvelle playlist</div>
                <div style="font-size:.7rem;color:var(--t3)" id="cplSub">Étape 1 sur 2 — Photos</div>
              </div>
              <button class="btn btn-ghost" style="margin-left:auto;padding:6px 10px;font-size:18px" onclick="closeCreatePlaylist()">✕</button>
            </div>

            <!-- STEP 1 : Nom + Upload -->
            <div id="cplStep1">
              <input id="cplName" class="acc-desc-inp" style="margin-bottom:14px;font-size:.9rem;padding:10px 13px" placeholder="Nom de la playlist (ex: STORY 1, Pack Lundi…)">

              <!-- Drop zone -->
              <div id="cplDrop" style="border:2px dashed var(--b2);border-radius:12px;padding:32px 20px;text-align:center;cursor:pointer;transition:.15s;margin-bottom:14px;background:var(--c1)" onclick="document.getElementById('cplFileIn').click()">
                <div style="font-size:2rem;margin-bottom:8px">📁</div>
                <div style="font-size:.82rem;font-weight:700;color:var(--t1);margin-bottom:4px">Glisse tes photos ici</div>
                <div style="font-size:.72rem;color:var(--t3)">ou clique pour sélectionner · JPG, PNG, MP4</div>
                <input type="file" id="cplFileIn" accept="image/*,video/*" multiple style="display:none">
              </div>

              <!-- Preview grille photos -->
              <div id="cplPhotoGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(72px,1fr));gap:8px;margin-bottom:16px"></div>

              <div style="display:flex;gap:8px;justify-content:flex-end">
                <button class="btn btn-ghost" onclick="closeCreatePlaylist()">Annuler</button>
                <button class="btn btn-primary" id="cplBtnNext" onclick="cplGoStep2()" style="opacity:.4;pointer-events:none">Suivant → IA</button>
              </div>
            </div>

            <!-- STEP 2 : IA Scheduling -->
            <div id="cplStep2" style="display:none">
              <div style="font-size:.75rem;font-weight:700;color:var(--t2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px">✨ Programmation intelligente</div>

              <!-- Résumé photos -->
              <div id="cplPhotoSummary" style="background:var(--c1);border-radius:8px;padding:10px 13px;margin-bottom:14px;font-size:.78rem;color:var(--t2)"></div>

              <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">
                <div>
                  <label style="font-size:.72rem;color:var(--t3);display:block;margin-bottom:4px">Date de début</label>
                  <input type="date" id="cplStartDate" class="acc-desc-inp" style="padding:9px 11px;font-size:.85rem">
                </div>
                <div>
                  <label style="font-size:.72rem;color:var(--t3);display:block;margin-bottom:4px">Durée (jours)</label>
                  <input type="number" id="cplDays" class="acc-desc-inp" value="30" min="1" max="365" style="padding:9px 11px;font-size:.85rem">
                </div>
              </div>

              <div style="margin-bottom:14px">
                <label style="font-size:.72rem;color:var(--t3);display:block;margin-bottom:8px">Créneaux horaires préférés</label>
                <div style="display:flex;flex-wrap:wrap;gap:7px" id="cplTimeSlots">
                  <label class="cpl-slot-lbl"><input type="checkbox" value="8" checked> 🌅 8h matin</label>
                  <label class="cpl-slot-lbl"><input type="checkbox" value="12"> ☀️ 12h midi</label>
                  <label class="cpl-slot-lbl"><input type="checkbox" value="17" checked> 🌆 17h soir</label>
                  <label class="cpl-slot-lbl"><input type="checkbox" value="20" checked> 🌙 20h nuit</label>
                  <label class="cpl-slot-lbl"><input type="checkbox" value="22"> 🌜 22h tard</label>
                </div>
              </div>

              <div style="margin-bottom:16px">
                <label style="font-size:.72rem;color:var(--t3);display:block;margin-bottom:4px">Décalage aléatoire (aspect naturel)</label>
                <div style="display:flex;gap:8px">
                  <label class="cpl-slot-lbl"><input type="radio" name="cplJitter" value="0"> Aucun</label>
                  <label class="cpl-slot-lbl"><input type="radio" name="cplJitter" value="15" checked> ±15 min</label>
                  <label class="cpl-slot-lbl"><input type="radio" name="cplJitter" value="45"> ±45 min</label>
                </div>
              </div>

              <!-- Bouton IA -->
              <button class="btn btn-primary" style="width:100%;margin-bottom:14px;font-size:.9rem;padding:11px" onclick="cplRunAI()">
                ✨ Générer le planning IA
              </button>

              <!-- Aperçu planning -->
              <div id="cplPreview" style="display:none;margin-bottom:14px">
                <div style="font-size:.72rem;color:var(--t2);font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">Aperçu du planning généré</div>
                <div id="cplPreviewList" style="max-height:220px;overflow-y:auto;display:flex;flex-direction:column;gap:5px;background:var(--c1);border-radius:8px;padding:10px"></div>
              </div>

              <div style="display:flex;gap:8px;justify-content:space-between">
                <button class="btn btn-ghost" onclick="cplGoBack()">← Retour</button>
                <div style="display:flex;gap:8px">
                  <button class="btn btn-ghost" id="cplBtnSaveOnly" onclick="cplSaveOnly()" style="display:none">💾 Sauvegarder seulement</button>
                  <button class="btn btn-primary" id="cplBtnConfirm" onclick="cplConfirm()" style="display:none">✅ Sauvegarder & programmer</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- PAGE : Stats -->
        <div class="page" id="page-stats">
          <!-- Date range selector -->
          <div class="dr-bar" id="drBar">
            <button class="dr-btn" data-dr="today">Aujourd'hui</button>
            <button class="dr-btn" data-dr="yesterday">Hier</button>
            <button class="dr-btn dr-active" data-dr="last_7">7 derniers jours</button>
            <button class="dr-btn" data-dr="this_week">Cette semaine</button>
            <button class="dr-btn" data-dr="last_week">Semaine dernière</button>
            <button class="dr-btn" data-dr="this_month">Ce mois</button>
            <button class="dr-btn" data-dr="last_month">Mois dernier</button>
            <button class="dr-btn" data-dr="this_year">Cette année</button>
            <button class="dr-btn" data-dr="last_year">Année dernière</button>
            <button class="dr-btn" data-dr="all">Tout</button>
          </div>
          <!-- Platform tabs -->
          <div class="stats-platform-tabs">
            <div class="spt active" id="sptTg" onclick="switchStatsPlatform('telegram')">
              <div class="spt-ico"><svg width="28" height="28" viewBox="0 0 240 240"><circle cx="120" cy="120" r="120" fill="#2CA5E0"/><path fill="#FFF" fill-rule="evenodd" d="M20.665 100.68c49.238-21.462 82.064-35.607 98.477-42.437 46.905-19.52 56.629-22.918 62.959-23.04 1.396-.024 4.52.322 6.547 1.97 1.707 1.389 2.177 3.262 2.405 4.576.229 1.315.512 4.306.284 6.647-2.548 26.78-13.558 91.763-19.161 121.77-2.369 12.696-7.038 16.951-11.561 17.36-9.826.906-17.294-6.492-26.828-12.73-14.913-9.766-23.33-15.844-37.82-25.386-16.718-11.016-5.882-17.068 3.638-26.978 2.49-2.583 45.749-41.925 46.575-45.503.104-.447.201-2.113-1.28-2.994-1.481-.88-3.666-.577-5.243-.339-2.233.336-37.78 24.014-106.64 70.58-10.091 6.929-19.232 10.308-27.424 10.132-9.025-.193-26.383-5.108-39.284-9.306-15.832-5.148-28.405-7.875-27.324-16.619.565-4.561 6.867-9.225 18.905-14.003z"/></svg></div>
              <div class="spt-name">Telegram</div>
              <div class="spt-sub" id="sptTgSub">— posts</div>
            </div>
            <div class="spt" id="sptSnap" onclick="switchStatsPlatform('snapchat')">
              <div class="spt-ico"><svg width="28" height="28" viewBox="0 0 100 100"><rect width="100" height="100" rx="20" fill="#FFFC00"/><path fill="#fff" d="M50 14c-8.8 0-15.9 7.1-15.9 15.8v3.5c-.7.2-1.6.4-2.3.4h-.5c-.2 0-.3.2-.2.4.5 1.2 2.3 2.2 3.5 2.6.1 0 .2.1.2.3.6 2.8 1.8 5.2 3.5 7-2.2 1.2-4.4 2.6-4.4 4.8 0 1.6 1.4 2.9 4.3 3.6l.5.1c.1.2.2.4.3.6.3 1.6.9 3 1.7 3.9-.7.3-1.4.7-1.4 1.4 0 .9 1.3 1.7 3.9 1.7h2c1.3 1.2 3.2 2 5.4 2s4.1-.8 5.4-2h2c2.6 0 3.9-.8 3.9-1.7 0-.7-.7-1.1-1.4-1.4.8-.9 1.4-2.3 1.7-3.9.1-.2.3-.4.5-.6 2.9-.7 4.3-2 4.3-3.6 0-2.2-2.2-3.6-4.4-4.8 1.7-1.8 2.9-4.2 3.5-7 0-.2.1-.3.2-.3 1.2-.4 3-1.4 3.5-2.6.1-.2-.1-.4-.2-.4h-.1c-.7 0-1.6-.2-2.3-.4v-3.5C65.9 21.1 58.8 14 50 14z"/></svg></div>
              <div class="spt-name">Snapchat</div>
              <div class="spt-sub" id="sptSnapSub">— posts</div>
            </div>
          </div>
          <!-- Overview cards -->
          <div class="stat-overview" id="statOverview">
            <div class="stat-ov-card"><div class="stat-ov-val" id="sovTotal">—</div><div class="stat-ov-lbl">Total posts</div></div>
            <div class="stat-ov-card"><div class="stat-ov-val" id="sovDone" style="color:var(--green)">—</div><div class="stat-ov-lbl">Envoyés</div></div>
            <div class="stat-ov-card"><div class="stat-ov-val" id="sovViews" style="color:#8b5cf6">—</div><div class="stat-ov-lbl" id="sovViewsLbl">Vues totales</div></div>
            <div class="stat-ov-card"><div class="stat-ov-val" id="sovErr" style="color:var(--red)">—</div><div class="stat-ov-lbl">Erreurs</div></div>
          </div>
          <!-- Line charts -->
          <div class="lc-wrap" id="lcTgWrap">
            <div class="lc-header">
              <div class="lc-title">📱 Telegram — vues totales par jour</div>
              <div class="lc-subtitle" id="lcTgSub">Actualisez pour charger</div>
            </div>
            <div class="lc-canvas-box" id="lcTgBox">
              <canvas id="lcTgCanvas"></canvas>
              <div class="lc-tooltip" id="lcTgTooltip"></div>
            </div>
            <div class="lc-scroll-hint" id="lcTgHint" style="display:none">🖱 Molette ou glisser pour naviguer</div>
          </div>
          <div class="lc-wrap" id="lcSnapWrap" style="display:none">
            <div class="lc-header">
              <div class="lc-title" style="color:#f5c518">👻 Snapchat — posts envoyés par jour</div>
              <div class="lc-subtitle" id="lcSnapSub">Actualisez pour charger</div>
            </div>
            <div class="lc-canvas-box" id="lcSnapBox">
              <canvas id="lcSnapCanvas"></canvas>
              <div class="lc-tooltip" id="lcSnapTooltip"></div>
            </div>
            <div class="lc-scroll-hint" id="lcSnapHint" style="display:none">🖱 Molette ou glisser pour naviguer</div>
          </div>
          <!-- Detail -->
          <div class="panel">
            <div class="panel-hd">
              <div class="panel-title" id="statsDetailTitle">📊 Détail des stories</div>
              <div style="display:flex;align-items:center;gap:8px">
                <span style="font-size:.62rem;color:var(--t3)" id="statsLastUpdate"></span>
                <button class="btn btn-sm" id="btnRefreshStats"><span class="btn-ico">🔄</span> Actualiser</button>
              </div>
            </div>
            <div id="statsList"><div class="empty"><div class="empty-ico">📊</div>Clique sur Actualiser</div></div>
          </div>
        </div>


        <!-- PAGE : Snapchat -->
        <div class="page" id="page-snapchat">

          <!-- Onglets Stories / Spotlight -->
          <div class="snap-tabs">
            <button class="snap-tab active" data-snap="stories" onclick="switchSnapTab('stories')">&#x1F4F8; Stories</button>
            <button class="snap-tab" data-snap="spotlight" onclick="switchSnapTab('spotlight')">&#x1F3AC; Spotlight</button>
          </div>

          <!-- VUE STORIES -->
          <div class="snap-subview active" id="snapStories">
            <div class="metrics" style="margin-bottom:12px">
              <div class="metric"><div class="metric-val" id="snapMPending">—</div><div class="metric-lbl">En attente</div></div>
              <div class="metric"><div class="metric-val" id="snapMDone">—</div><div class="metric-lbl">Envoyées</div></div>
              <div class="metric"><div class="metric-val" id="snapMErr">—</div><div class="metric-lbl">Erreurs</div></div>
              <div class="metric"><div class="metric-val">6</div><div class="metric-lbl">Comptes</div></div>
            </div>
            <div class="panel">
              <div class="panel-hd"><div class="panel-title" style="color:#f5c518">&#x1F47B; Programmer des Stories</div></div>
              <div class="uz" id="snapUz" style="border-color:#f5c51830">
                <input type="file" id="snapFi" accept="image/*,video/*" multiple>
                <div class="uz-ico">&#x1F47B;</div>
                <div class="uz-txt"><b>Photos / vidéos</b> — converties auto en 9:16 portrait</div>
              </div>
              <div style="display:flex;justify-content:flex-end;margin-top:10px;margin-bottom:8px">
                <button class="btn btn-xs" id="snapBtnSavePl" style="background:#1a1a2e;border-color:#6366f1;color:#a5b4fc" disabled>&#x1F4BE; Sauvegarder dans Médias</button>
              </div>

              <!-- Étape 2 : Analyse IA -->
              <div id="snapAnalyzeBar" style="display:none;margin-top:8px">
                <button class="btn" id="snapBtnAnalyze" style="width:100%;background:#1a1a2e;border-color:#6366f1;color:#a5b4fc;font-weight:700">
                  &#x1F9E0; Analyser avec l'IA (heure optimale)
                </button>
                <div id="snapAnalyzeStatus" style="font-size:.67rem;color:var(--t3);margin-top:4px;text-align:center"></div>
              </div>
              <div class="plist" id="snapPlist"></div>
              <div class="no-p" id="snapNoP">Aucune photo ajoutée</div>
              <div class="acc-section">
                <div class="acc-section-lbl">Comptes qui reçoivent la Story :</div>
                <div class="acc-checks" id="snapAccChecks"><div class="no-acc-warn">Chargement…</div></div>
              </div>
              <div style="display:flex;gap:6px;margin-top:12px">
                <button class="btn btn-danger" id="snapBtnSchedule" disabled style="flex:1;background:#f5c518;border-color:#f5c518;color:#000">&#x1F47B; Programmer (+1 min/compte)</button>
                <button class="btn" id="snapBtnClear">&#x1F5D1;</button>
              </div>
              <div style="margin-top:8px;padding:7px 10px;background:rgba(245,197,24,.06);border:1px solid rgba(245,197,24,.15);border-radius:6px;font-size:.67rem;color:#aaa">
                &#x2705; Analyse IA · Conversion 9:16 auto · +1 min entre chaque compte · Cloudinary &#x2192; One Up
              </div>
            </div>
          </div>

          <!-- VUE SPOTLIGHT -->
          <div class="snap-subview" id="snapSpotlight">
            <div class="metrics" style="margin-bottom:12px">
              <div class="metric"><div class="metric-val" id="splMPool">—</div><div class="metric-lbl">Dans le pool</div></div>
              <div class="metric"><div class="metric-val" id="splMTotal">—</div><div class="metric-lbl">Programmés</div></div>
              <div class="metric"><div class="metric-val" id="splMDone">—</div><div class="metric-lbl">Envoyés</div></div>
              <div class="metric"><div class="metric-val" id="splMErr">—</div><div class="metric-lbl">Erreurs</div></div>
            </div>
            <div class="panel">
              <div class="panel-hd"><div class="panel-title" style="color:#f5c518">&#x1F3AC; Programmer des Spotlight</div></div>
              <div id="splPoolInfo" style="padding:10px 12px;background:#0d0d0d;border:1px solid #222;border-radius:8px;margin-bottom:10px;font-size:.75rem;color:var(--t2)">
                &#x1F4C2; Chargement du pool...
              </div>
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap">
                <label style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--t2);white-space:nowrap">Vidéos à programmer</label>
                <input id="splCount" type="number" min="1" max="100" value="10" style="width:80px;background:var(--c2);border:1px solid var(--b2);border-radius:7px;padding:7px 10px;color:var(--t1);font-size:.95rem;font-weight:700;text-align:center;outline:none;color-scheme:dark">
                <span id="splCountInfo" style="font-size:.7rem;color:var(--t3)">— vidéo(s) par compte</span>
              </div>
              <div class="acc-section">
                <div class="acc-section-lbl">Comptes qui reçoivent les Spotlight :</div>
                <div class="acc-checks" id="splAccChecks"><div class="no-acc-warn">Chargement…</div></div>
              </div>
              <!-- Dossiers locaux → pool VPS -->
              <div style="margin-bottom:12px;background:#0a0a0a;border:1px solid #1e1e1e;border-radius:8px;padding:10px 12px">
                <div style="font-size:.75rem;font-weight:700;color:var(--t2);margin-bottom:8px">&#x1F4C2; Dossiers locaux</div>
                <div style="font-size:.62rem;color:#f5c518;background:rgba(245,197,24,.08);border:1px solid rgba(245,197,24,.2);border-radius:5px;padding:5px 8px;margin-bottom:8px">
                  &#x26A0;&#xFE0F; Dans la boîte de dialogue : navigue jusqu'au dossier voulu, puis clique <b>Sélectionner le dossier</b> (ne clique pas sur les fichiers à l'intérieur).
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px">
                  <div>
                    <div style="font-size:.62rem;color:#888;margin-bottom:3px">📥 A POSTER (source)</div>
                    <button class="btn btn-xs" id="splPickSrc" style="width:100%;font-size:.68rem;padding:6px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                      📁 Choisir dossier source
                    </button>
                    <button class="btn btn-xs" id="splPickFiles" style="width:100%;font-size:.62rem;padding:4px 8px;margin-top:3px;opacity:.7">
                      🎬 Sélectionner des vidéos
                    </button>
                  </div>
                  <div>
                    <div style="font-size:.62rem;color:#888;margin-bottom:3px">📤 DEJA POSTEES (dest.)</div>
                    <button class="btn btn-xs" id="splPickDst" style="width:100%;font-size:.68rem;padding:6px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" disabled>
                      📁 Choisir dossier dest.
                    </button>
                  </div>
                </div>
                <div id="splFolderStatus" style="font-size:.66rem;color:#aaa;min-height:14px"></div>
                <div id="splDebugInfo" style="font-size:.6rem;color:#666;margin-top:4px;display:none"></div>
              </div>
              <button class="btn" id="splBtnSchedule" disabled style="width:100%;margin-top:4px;background:#f5c518;border-color:#f5c518;color:#000;font-weight:700;padding:11px">
                &#x1F3AC; Programmer les Spotlight
              </button>
              <div style="margin-top:8px;padding:7px 10px;background:rgba(245,197,24,.06);border:1px solid rgba(245,197,24,.15);border-radius:6px;font-size:.67rem;color:#aaa">
                &#x26A1; 1 vidéo/jour/compte · 8h-21h aléatoire · reprend au lendemain du dernier Spotlight · 25 min entre comptes · déplace dans <b>Déjà postées</b> après envoi
              </div>
            </div>
            <div class="panel" style="margin-top:12px">
              <div class="panel-hd">
                <div class="panel-title">&#x1F4CB; Historique Spotlight</div>
                <button class="btn btn-xs" id="splBtnRefresh">&#x1F504;</button>
              </div>
              <div id="splList"><div class="empty"><div class="empty-ico">&#x1F3AC;</div>Aucun Spotlight programmé</div></div>
            </div>
          </div>

        </div>

        <!-- PAGE : Revenus -->
        <div class="page" id="page-revenue">
          <!-- KPI cards -->
          <div class="stat-overview" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">
            <div class="stat-ov-card"><div class="stat-ov-val" id="revTotal" style="color:#22c55e">—</div><div class="stat-ov-lbl">Revenu total</div></div>
            <div class="stat-ov-card"><div class="stat-ov-val" id="revMonth" style="color:#8b5cf6">—</div><div class="stat-ov-lbl">Ce mois-ci</div></div>
            <div class="stat-ov-card"><div class="stat-ov-val" id="revAvg">—</div><div class="stat-ov-lbl">Moy. / jour</div></div>
            <div class="stat-ov-card"><div class="stat-ov-val" id="revTx" style="color:#f59e0b">—</div><div class="stat-ov-lbl">Transactions</div></div>
          </div>
          <!-- Saisie rapide -->
          <div class="panel" style="margin-bottom:14px">
            <div class="panel-hd"><div class="panel-title">💰 Ajouter un revenu</div></div>
            <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">
              <div class="fld" style="flex:1;min-width:120px;margin:0">
                <label>Date</label>
                <input type="date" id="revDate" style="background:#0a0a0a;border:1px solid var(--b2);border-radius:var(--r2);padding:8px 10px;color:var(--t1);font-size:.84rem;width:100%;outline:none">
              </div>
              <div class="fld" style="flex:1;min-width:120px;margin:0">
                <label>Montant (€)</label>
                <input type="number" id="revAmount" placeholder="0.00" step="0.01" min="0" style="background:#0a0a0a;border:1px solid var(--b2);border-radius:var(--r2);padding:8px 10px;color:var(--t1);font-size:.84rem;width:100%;outline:none">
              </div>
              <div class="fld" style="flex:2;min-width:160px;margin:0">
                <label>Source</label>
                <input type="text" id="revSource" placeholder="ex: MYM, OnlyFans, Telegram…" style="background:#0a0a0a;border:1px solid var(--b2);border-radius:var(--r2);padding:8px 10px;color:var(--t1);font-size:.84rem;width:100%;outline:none">
              </div>
              <div class="fld" style="flex:1;min-width:100px;margin:0">
                <label>Note (optionnel)</label>
                <input type="text" id="revNote" placeholder="" style="background:#0a0a0a;border:1px solid var(--b2);border-radius:var(--r2);padding:8px 10px;color:var(--t1);font-size:.84rem;width:100%;outline:none">
              </div>
              <button class="btn btn-primary" onclick="addRevenue()" style="height:37px;padding:0 20px;flex-shrink:0">+ Ajouter</button>
            </div>
          </div>
          <!-- Histogramme mensuel -->
          <div class="lc-wrap" id="revChartWrap">
            <div class="lc-header">
              <div class="lc-title" style="color:#22c55e">💵 Revenus par jour</div>
              <div class="lc-subtitle" id="revChartSub"></div>
            </div>
            <div class="lc-canvas-box" id="revChartBox" style="height:300px">
              <canvas id="revCanvas"></canvas>
              <div class="lc-tooltip" id="revTooltip"></div>
            </div>
          </div>
          <!-- Liste transactions -->
          <div class="panel">
            <div class="panel-hd">
              <div class="panel-title">📋 Historique</div>
              <span style="font-size:.65rem;color:var(--t3)" id="revLastUpdate"></span>
            </div>
            <div id="revList"><div class="empty"><div class="empty-ico">💵</div>Aucun revenu enregistré</div></div>
          </div>
        </div>

        <!-- PAGE : Comptes -->
        <div class="page" id="page-accounts">
          <!-- Clef API OneUp -->
          <div style="display:flex;align-items:center;gap:10px;background:rgba(124,58,237,.08);border:1px solid rgba(124,58,237,.22);border-radius:10px;padding:12px 16px;margin-bottom:14px">
            <span style="font-size:.85rem;color:var(--fg2);white-space:nowrap;font-weight:600">🔑 Clef API OneUp</span>
            <input id="acsOneupKey" type="password" placeholder="Colle ta clef API OneUp ici…" style="flex:1;background:#1a1a1a;border:1px solid #333;border-radius:7px;padding:7px 10px;color:var(--fg);font-size:.85rem">
            <button class="btn btn-xs" onclick="(()=>{const i=document.getElementById('acsOneupKey');i.type=i.type==='password'?'text':'password'})()" title="Afficher/masquer" style="white-space:nowrap">👁</button>
            <button class="btn btn-xs" onclick="navigator.clipboard.readText().then(t=>{document.getElementById('acsOneupKey').value=t.trim();toast('✅ Clef collée','ok');}).catch(()=>alert('Autorise le presse-papiers dans le navigateur.'))" title="Coller" style="white-space:nowrap">📋 Coller</button>
            <button class="btn btn-xs" style="background:var(--purple);color:#fff;white-space:nowrap" onclick="(async()=>{const v=document.getElementById('acsOneupKey').value.trim();if(!v)return toast('Entre une clef','err');const pid=_activeProfileId;if(!pid)return;const r=await fetch('/api/profiles/'+pid,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({oneup_api_key:v})});if(r.ok)toast('✅ Clef sauvegardée','ok');else toast('Erreur sauvegarde','err');})()">💾 Sauvegarder</button>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">

            <!-- Telegram -->
            <div class="accs-panel">
              <div class="accs-hd">
                <div class="accs-hd-left">
                  <div class="accs-plat-ico" style="background:rgba(44,165,224,.15)"><svg width="16" height="16" viewBox="0 0 240 240"><circle cx="120" cy="120" r="120" fill="#2CA5E0"/><path fill="#fff" d="M20.665 100.68c49.238-21.462 82.064-35.607 98.477-42.437 46.905-19.52 56.629-22.918 62.959-23.04 1.396-.024 4.52.322 6.547 1.97 1.707 1.389 2.177 3.262 2.405 4.576.229 1.315.512 4.306.284 6.647-2.548 26.78-13.558 91.763-19.161 121.77-2.369 12.696-7.038 16.951-11.561 17.36-9.826.906-17.294-6.492-26.828-12.73-14.913-9.766-23.33-15.844-37.82-25.386-16.718-11.016-5.882-17.068 3.638-26.978 2.49-2.583 45.749-41.925 46.575-45.503.104-.447.201-2.113-1.28-2.994-1.481-.88-3.666-.577-5.243-.339-2.233.336-37.78 24.014-106.64 70.58-10.091 6.929-19.232 10.308-27.424 10.132-9.025-.193-26.383-5.108-39.284-9.306-15.832-5.148-28.405-7.875-27.324-16.619.565-4.561 6.867-9.225 18.905-14.003z"/></svg></div>
                  <span class="accs-plat-name">Telegram</span>
                  <span class="accs-badge" id="acsBadgeTg">0</span>
                </div>
                <div style="display:flex;gap:6px">
                  <button class="accs-btn" id="btnReconnectAll" onclick="reconnectAllDisconnected()" title="Reconnecter les déconnectés">🔄</button>
                  <button class="accs-btn accs-btn-add" id="btnAddAcc" onclick="openAuthModal()">+ Ajouter</button>
                </div>
              </div>
              <div class="acc-list" id="accList"><div class="no-acc">Aucun compte</div></div>
            </div>

            <!-- Snapchat -->
            <div class="accs-panel">
              <div class="accs-hd">
                <div class="accs-hd-left">
                  <div class="accs-plat-ico" style="background:rgba(255,252,0,.12)"><svg width="16" height="16" viewBox="0 0 48 48"><rect width="48" height="48" rx="9" fill="#FFFC00"/><path fill="#000" d="M24 7c-5.3 0-9.5 4.1-9.5 9.2v1.4c-1 .3-2.2.6-3 .6h-.5c-.11-.02-.2.07-.17.18.28.7 1.46 1.37 2.24 1.65.07.02.13.09.14.17.38 1.76 1.08 3.23 2.1 4.35-1.33.75-2.66 1.55-2.66 2.92 0 .98.84 1.73 2.57 2.18.17.05.3.18.31.35.21.98.58 1.91 1.06 2.47-.47.2-.9.4-.9.7 0 .54.83 1.03 2.33 1.03h1.25c.82.76 1.94 1.22 3.3 1.22s2.48-.46 3.3-1.22h1.25c1.5 0 2.33-.49 2.33-1.03 0-.3-.43-.5-.9-.7.48-.56.85-1.49 1.06-2.47.01-.17.14-.3.31-.35 1.73-.45 2.57-1.2 2.57-2.18 0-1.37-1.33-2.17-2.66-2.92 1.02-1.12 1.72-2.59 2.1-4.35.01-.08.07-.15.14-.17.78-.28 1.96-.95 2.24-1.65.03-.11-.06-.2-.17-.18h-.05c-.78 0-1.9-.27-3-.6v-1.4C33.5 11.1 29.3 7 24 7z"/></svg></div>
                  <span class="accs-plat-name">Snapchat</span>
                  <span class="accs-badge" id="acsBadgeSnap">0</span>
                </div>
                <button class="accs-btn accs-btn-add" onclick="_openAddSocialModal('snap')">+ Ajouter</button>
              </div>
              <div class="acc-list" id="snapAccListPage"><div class="no-acc">Aucun compte</div></div>
            </div>

            <!-- Instagram -->
            <div class="accs-panel">
              <div class="accs-hd">
                <div class="accs-hd-left">
                  <div class="accs-plat-ico" style="background:rgba(131,58,180,.15)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#c084fc" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4.5"/><circle cx="17.5" cy="6.5" r="1" fill="#c084fc" stroke="none"/></svg></div>
                  <span class="accs-plat-name">Instagram</span>
                  <span class="accs-badge" id="acsBadgeIg">0</span>
                </div>
                <button class="accs-btn accs-btn-add" onclick="_openAddSocialModal('ig')">+ Ajouter</button>
              </div>
              <div class="acc-list" id="igAccListPage"><div class="no-acc">Aucun compte</div></div>
            </div>

            <!-- Facebook -->
            <div class="accs-panel">
              <div class="accs-hd">
                <div class="accs-hd-left">
                  <div class="accs-plat-ico" style="background:rgba(24,119,242,.15)"><svg width="16" height="16" viewBox="0 0 24 24" fill="#1877F2"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg></div>
                  <span class="accs-plat-name">Facebook</span>
                  <span class="accs-badge" id="acsBadgeFb">0</span>
                </div>
                <button class="accs-btn accs-btn-add" onclick="_openAddSocialModal('fb')">+ Ajouter</button>
              </div>
              <div class="acc-list" id="fbAccListPage"><div class="no-acc">Aucun compte</div></div>
            </div>

          </div>
        </div>

        <!-- PAGE : Documentation -->
        <div class="page" id="page-docs" style="padding:0;overflow:hidden">
          <div style="display:flex;height:100%;overflow:hidden">

            <!-- ── Doc sidebar ── -->
            <div id="docSidebar" style="width:226px;flex-shrink:0;border-right:1px solid var(--b1);overflow-y:auto;padding:20px 0;background:var(--bg)">
              <div style="padding:0 16px 14px;font-size:.65rem;font-weight:800;letter-spacing:.1em;color:var(--t3);text-transform:uppercase">Documentation</div>

              <div class="doc-nav-section">
                <div class="doc-nav-label">🚀 Démarrage</div>
                <button class="doc-nav-item active" data-doc="intro" onclick="showDoc('intro',this)">Introduction</button>
                <button class="doc-nav-item" data-doc="account" onclick="showDoc('account',this)">Créer un compte</button>
                <button class="doc-nav-item" data-doc="profile" onclick="showDoc('profile',this)">Configurer son profil</button>
              </div>

              <div class="doc-nav-section">
                <div class="doc-nav-label">🔗 Comptes</div>
                <button class="doc-nav-item" data-doc="tg-connect" onclick="showDoc('tg-connect',this)">Connecter Telegram</button>
                <button class="doc-nav-item" data-doc="snap-connect" onclick="showDoc('snap-connect',this)">Connecter Snapchat</button>
                <button class="doc-nav-item" data-doc="ig-connect" onclick="showDoc('ig-connect',this)">Connecter Instagram/FB</button>
              </div>

              <div class="doc-nav-section">
                <div class="doc-nav-label">📅 Publication</div>
                <button class="doc-nav-item" data-doc="scheduling" onclick="showDoc('scheduling',this)">Auto-scheduling</button>
                <button class="doc-nav-item" data-doc="playlists" onclick="showDoc('playlists',this)">Playlists & médias</button>
                <button class="doc-nav-item" data-doc="publishing" onclick="showDoc('publishing',this)">Publier une story</button>
              </div>

              <div class="doc-nav-section">
                <div class="doc-nav-label">📊 Stats & Revenus</div>
                <button class="doc-nav-item" data-doc="stats" onclick="showDoc('stats',this)">Statistiques</button>
                <button class="doc-nav-item" data-doc="revenue" onclick="showDoc('revenue',this)">Suivi des revenus</button>
              </div>

              <div class="doc-nav-section">
                <div class="doc-nav-label">⚡ Avancé</div>
                <button class="doc-nav-item" data-doc="spotlight" onclick="showDoc('spotlight',this)">Spotlight Snapchat</button>
                <button class="doc-nav-item" data-doc="multiprofile" onclick="showDoc('multiprofile',this)">Multi-profils</button>
                <button class="doc-nav-item" data-doc="oneup" onclick="showDoc('oneup',this)">Clef API OneUp</button>
              </div>

              <div class="doc-nav-section">
                <div class="doc-nav-label">❓ Support</div>
                <button class="doc-nav-item" data-doc="faq" onclick="showDoc('faq',this)">FAQ</button>
                <button class="doc-nav-item" data-doc="legal" onclick="showDoc('legal',this)">Mentions légales</button>
                <button class="doc-nav-item" data-doc="cgu" onclick="showDoc('cgu',this)">CGU</button>
              </div>
            </div>

            <!-- ── Doc content ── -->
            <div id="docContent" style="flex:1;overflow-y:auto;padding:36px 48px;max-width:860px">

              <!-- intro -->
              <div class="doc-section active" id="doc-intro">
                <div class="doc-breadcrumb">🚀 Démarrage</div>
                <h1 class="doc-h1">Bienvenue sur StoryScheduler</h1>
                <div class="doc-callout info">
                  <strong>StoryScheduler</strong> est une plateforme d'automatisation de publication de stories et posts sur <strong>Telegram, Snapchat, Instagram et Facebook</strong>. Configure tes comptes une fois, et le système publie pour toi — 24h/24, 7j/7.
                </div>
                <h2 class="doc-h2">Ce que tu peux faire</h2>
                <div class="doc-grid-2">
                  <div class="doc-feature-card"><div class="doc-feature-ico">📅</div><div><strong>Auto-scheduling</strong><p>Le système choisit automatiquement le prochain créneau libre pour publier sans conflit.</p></div></div>
                  <div class="doc-feature-card"><div class="doc-feature-ico">📚</div><div><strong>Playlists de médias</strong><p>Organise tes photos/vidéos en playlists et déploie-les en un clic sur toutes tes plateformes.</p></div></div>
                  <div class="doc-feature-card"><div class="doc-feature-ico">👥</div><div><strong>Multi-profils</strong><p>Gère plusieurs créateurs depuis un seul dashboard, chaque profil complètement isolé.</p></div></div>
                  <div class="doc-feature-card"><div class="doc-feature-ico">📊</div><div><strong>Stats & Revenus</strong><p>Visualise tes publications, vues et revenus en temps réel avec des graphiques.</p></div></div>
                </div>
                <h2 class="doc-h2">Plateformes supportées</h2>
                <div class="doc-platform-list">
                  <div class="doc-platform"><span style="font-size:1.4rem">✈️</span><div><strong>Telegram</strong><span class="doc-badge green">Complet</span><p>Stories, publication automatique, multi-comptes, monitoring en direct.</p></div></div>
                  <div class="doc-platform"><span style="font-size:1.4rem">👻</span><div><strong>Snapchat</strong><span class="doc-badge green">Complet</span><p>Stories + Spotlight automatique via API OneUp.</p></div></div>
                  <div class="doc-platform"><span style="font-size:1.4rem">📸</span><div><strong>Instagram</strong><span class="doc-badge yellow">Via OneUp</span><p>Reels et stories programmés via l'API officielle OneUp/Meta.</p></div></div>
                  <div class="doc-platform"><span style="font-size:1.4rem">📘</span><div><strong>Facebook</strong><span class="doc-badge yellow">Via OneUp</span><p>Posts et stories programmés via l'API officielle OneUp/Meta.</p></div></div>
                </div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('account',document.querySelector('[data-doc=account]'))">Créer un compte →</button>
                </div>
              </div>

              <!-- account -->
              <div class="doc-section" id="doc-account" style="display:none">
                <div class="doc-breadcrumb">🚀 Démarrage</div>
                <h1 class="doc-h1">Créer un compte</h1>
                <div class="doc-callout info">La création de compte est réservée aux personnes autorisées. Si tu n'as pas encore accès, contacte l'administrateur de ta plateforme.</div>
                <h2 class="doc-h2">Étapes</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Accède à la page d'accueil</strong><p>Ouvre le site et clique sur <em>Créer un compte</em> ou <em>Commencer</em> dans le menu.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Remplis le formulaire</strong><p>Saisis un nom affiché, un identifiant de connexion et un mot de passe (minimum 8 caractères).</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Confirmation</strong><p>Une fois le compte créé, tu es automatiquement connecté et redirigé vers le dashboard.</p></div></div>
                </div>
                <div class="doc-callout warn">⚠️ Ton identifiant et mot de passe sont sensibles. Ne les partage jamais. En cas de perte, contacte l'administrateur.</div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('profile',document.querySelector('[data-doc=profile]'))">Configurer son profil →</button>
                </div>
              </div>

              <!-- profile -->
              <div class="doc-section" id="doc-profile" style="display:none">
                <div class="doc-breadcrumb">🚀 Démarrage</div>
                <h1 class="doc-h1">Configurer son profil</h1>
                <p class="doc-p">Chaque compte utilisateur peut gérer plusieurs <strong>profils créateurs</strong>. Un profil regroupe tous tes comptes réseaux sociaux, playlists et paramètres de façon isolée.</p>
                <h2 class="doc-h2">Créer un profil</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Ouvre le menu profil</strong><p>Clique sur ton avatar en bas à gauche de la sidebar pour ouvrir le menu de profils.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Nouveau profil</strong><p>Clique sur <em>＋ Nouveau profil</em>. Saisis un nom et un PIN de sécurité (4 chiffres).</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Switcher de profil</strong><p>Depuis le menu profil, clique sur n'importe quel profil pour switcher. Le PIN te sera demandé.</p></div></div>
                </div>
                <div class="doc-callout info">💡 Chaque profil a ses propres comptes, playlists et statistiques. Parfait pour gérer plusieurs créateurs depuis un seul dashboard.</div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('tg-connect',document.querySelector('[data-doc=tg-connect]'))">Connecter Telegram →</button>
                </div>
              </div>

              <!-- tg-connect -->
              <div class="doc-section" id="doc-tg-connect" style="display:none">
                <div class="doc-breadcrumb">🔗 Comptes</div>
                <h1 class="doc-h1">Connecter Telegram</h1>
                <p class="doc-p">StoryScheduler publie via les comptes Telegram officiels grâce à l'API Telegram (Telethon). La connexion se fait par numéro de téléphone et code SMS.</p>
                <div class="doc-callout warn">⚠️ Utilise uniquement des comptes Telegram qui t'appartiennent légalement. La publication automatisée doit respecter les <a href="https://telegram.org/tos" target="_blank" style="color:var(--purple)">Conditions d'utilisation Telegram</a>.</div>
                <h2 class="doc-h2">Ajouter un compte</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Va dans Comptes</strong><p>Clique sur <em>Comptes</em> dans la sidebar, section Telegram → <em>+ Ajouter</em>.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Saisis le numéro</strong><p>Entre le numéro de téléphone au format international (ex: +33612345678).</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Code de vérification</strong><p>Telegram t'envoie un code SMS ou via l'app. Saisis-le dans la fenêtre qui s'ouvre.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">4</div><div><strong>2FA (si activée)</strong><p>Si tu as activé la vérification en 2 étapes, saisis ton mot de passe Telegram.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">5</div><div><strong>Compte connecté ✓</strong><p>Le compte apparaît dans la liste avec un indicateur vert. Il est prêt pour la programmation.</p></div></div>
                </div>
                <h2 class="doc-h2">Reconnecter un compte déconnecté</h2>
                <p class="doc-p">Si un compte se déconnecte (session expirée), un indicateur rouge s'affiche. Clique sur 🔄 à côté du compte pour relancer le processus de connexion.</p>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('snap-connect',document.querySelector('[data-doc=snap-connect]'))">Connecter Snapchat →</button>
                </div>
              </div>

              <!-- snap-connect -->
              <div class="doc-section" id="doc-snap-connect" style="display:none">
                <div class="doc-breadcrumb">🔗 Comptes</div>
                <h1 class="doc-h1">Connecter Snapchat</h1>
                <p class="doc-p">La connexion Snapchat et la publication de stories passent par <strong>l'API OneUp</strong>. Tu dois avoir une clef API OneUp valide et y avoir connecté tes comptes Snapchat.</p>
                <div class="doc-callout info">ℹ️ OneUp est un outil tiers officiel partenaire de Snapchat. La publication via OneUp est conforme aux <a href="https://snap.com/en-US/terms" target="_blank" style="color:var(--purple)">CGU Snapchat</a>.</div>
                <h2 class="doc-h2">Prérequis</h2>
                <div class="doc-checklist">
                  <div class="doc-check-item"><span class="doc-check">✓</span> Avoir un compte OneUp actif avec une clef API</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Avoir connecté tes comptes Snapchat dans OneUp</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Avoir sauvegardé ta clef API dans la page Comptes</div>
                </div>
                <h2 class="doc-h2">Ajouter un compte Snapchat</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Configure ta clef API</strong><p>Dans la page Comptes, colle ta clef API OneUp dans le champ dédié et clique Sauvegarder.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Ajouter un compte</strong><p>Dans la section Snapchat → <em>+ Ajouter</em>. Tu peux importer automatiquement depuis OneUp ou entrer l'ID manuellement.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Prêt</strong><p>Le compte Snapchat apparaît dans la liste. Il peut maintenant recevoir des stories programmées.</p></div></div>
                </div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('ig-connect',document.querySelector('[data-doc=ig-connect]'))">Connecter Instagram/FB →</button>
                </div>
              </div>

              <!-- ig-connect -->
              <div class="doc-section" id="doc-ig-connect" style="display:none">
                <div class="doc-breadcrumb">🔗 Comptes</div>
                <h1 class="doc-h1">Connecter Instagram & Facebook</h1>
                <p class="doc-p">Instagram et Facebook utilisent également <strong>l'API OneUp</strong>, qui s'appuie sur l'API officielle Meta Business. La publication est 100% conforme aux règles Meta.</p>
                <div class="doc-callout info">ℹ️ Seuls les comptes <strong>Instagram Business</strong> ou <strong>Creator</strong> peuvent être connectés. Les comptes personnels ne sont pas supportés par l'API Meta.</div>
                <h2 class="doc-h2">Procédure</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Clef API OneUp</strong><p>Assure-toi d'avoir configuré ta clef API OneUp dans la page Comptes.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Ajouter le compte</strong><p>Instagram → <em>+ Ajouter</em> ou Facebook → <em>+ Ajouter</em>. Utilise l'import automatique OneUp pour récupérer tes comptes déjà connectés.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Créer du contenu</strong><p>Navigue vers Instagram ou Facebook dans la sidebar pour programmer tes posts.</p></div></div>
                </div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('scheduling',document.querySelector('[data-doc=scheduling]'))">Auto-scheduling →</button>
                </div>
              </div>

              <!-- scheduling -->
              <div class="doc-section" id="doc-scheduling" style="display:none">
                <div class="doc-breadcrumb">📅 Publication</div>
                <h1 class="doc-h1">Auto-scheduling</h1>
                <p class="doc-p">L'auto-scheduling est la fonctionnalité principale de StoryScheduler. Au lieu de saisir manuellement une date et heure, le système calcule automatiquement le prochain créneau disponible.</p>
                <h2 class="doc-h2">Comment ça fonctionne</h2>
                <div class="doc-callout info">Le système analyse ton calendrier de publications existant et ajoute la prochaine story/post <strong>immédiatement après la dernière programmée</strong>, en respectant un intervalle minimal configurable.</div>
                <h2 class="doc-h2">Avantages</h2>
                <div class="doc-checklist">
                  <div class="doc-check-item"><span class="doc-check">✓</span> Aucun conflit d'horaire entre tes publications</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Zéro saisie manuelle de date/heure</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Fonctionne pour Telegram, Snapchat, Instagram et Facebook</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Peut programmer des séries entières de médias en quelques clics</div>
                </div>
                <h2 class="doc-h2">Programmer via une playlist</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Va sur la plateforme</strong><p>Clique sur Telegram, Snapchat, Instagram ou Facebook dans la sidebar.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Sélectionne une playlist</strong><p>Choisis une playlist dans le panneau gauche, puis coche les comptes de destination.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Programmer</strong><p>Clique sur <em>Programmer</em>. L'auto-scheduling calcule les créneaux et ajoute toutes les stories en file.</p></div></div>
                </div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('playlists',document.querySelector('[data-doc=playlists]'))">Playlists & médias →</button>
                </div>
              </div>

              <!-- playlists -->
              <div class="doc-section" id="doc-playlists" style="display:none">
                <div class="doc-breadcrumb">📅 Publication</div>
                <h1 class="doc-h1">Playlists & médias</h1>
                <p class="doc-p">Les playlists sont des collections de médias (photos, vidéos) que tu peux créer, organiser et déployer sur toutes tes plateformes.</p>
                <h2 class="doc-h2">Créer une playlist</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Va dans Médias</strong><p>Clique sur <em>Médias</em> dans la sidebar.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Nouvelle playlist</strong><p>Clique sur <em>+ Nouvelle playlist</em>. Donne-lui un nom clair.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Ajouter des médias</strong><p>Upload tes fichiers (JPG, PNG, MP4…). Chaque fichier est traité et stocké.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">4</div><div><strong>Réorganiser</strong><p>Glisse-dépose les médias pour changer leur ordre de publication.</p></div></div>
                </div>
                <h2 class="doc-h2">Formats acceptés</h2>
                <div class="doc-table">
                  <div class="doc-table-row doc-table-head"><span>Format</span><span>Type</span><span>Plateformes</span></div>
                  <div class="doc-table-row"><span>JPG, PNG, WEBP</span><span>Image</span><span>Toutes</span></div>
                  <div class="doc-table-row"><span>MP4, MOV</span><span>Vidéo</span><span>Snapchat (Spotlight), TG</span></div>
                </div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('publishing',document.querySelector('[data-doc=publishing]'))">Publier une story →</button>
                </div>
              </div>

              <!-- publishing -->
              <div class="doc-section" id="doc-publishing" style="display:none">
                <div class="doc-breadcrumb">📅 Publication</div>
                <h1 class="doc-h1">Publier une story</h1>
                <p class="doc-p">Tu peux programmer une story immédiatement ou la laisser à l'auto-scheduling. Voici le flux complet.</p>
                <h2 class="doc-h2">Workflow de publication Telegram</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Sélectionne les comptes</strong><p>Dans Telegram, coche les comptes Telegram sur lesquels publier.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Choisis la playlist</strong><p>Sélectionne la playlist contenant tes médias.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Programme</strong><p>Clique sur <em>Programmer</em>. Les stories apparaissent dans le panneau droit sous <em>Programmées</em>.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">4</div><div><strong>Publication automatique</strong><p>Le daemon vérifie toutes les minutes les stories à publier et les envoie à l'heure prévue.</p></div></div>
                </div>
                <div class="doc-callout info">💡 Après publication, les stories passent dans l'onglet <strong>Publiées</strong> du panneau droit avec un timestamp et statut.</div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('stats',document.querySelector('[data-doc=stats]'))">Statistiques →</button>
                </div>
              </div>

              <!-- stats -->
              <div class="doc-section" id="doc-stats" style="display:none">
                <div class="doc-breadcrumb">📊 Stats & Revenus</div>
                <h1 class="doc-h1">Statistiques</h1>
                <p class="doc-p">Le dashboard Statistiques centralise toutes les données de publication de ton profil actif.</p>
                <h2 class="doc-h2">Ce que tu vois</h2>
                <div class="doc-grid-2">
                  <div class="doc-feature-card"><div class="doc-feature-ico">📈</div><div><strong>Graphique journalier</strong><p>Vues par jour sur les 7/30/90 derniers jours ou depuis le début.</p></div></div>
                  <div class="doc-feature-card"><div class="doc-feature-ico">🔢</div><div><strong>Compteurs globaux</strong><p>Total de vues, stories envoyées et taux d'erreur.</p></div></div>
                  <div class="doc-feature-card"><div class="doc-feature-ico">📡</div><div><strong>En direct</strong><p>Monitoring des stories actives en ce moment, avec miniatures et nombre de vues live.</p></div></div>
                  <div class="doc-feature-card"><div class="doc-feature-ico">📋</div><div><strong>Détail des stories</strong><p>Liste de toutes les stories publiées avec date, compte et statut.</p></div></div>
                </div>
                <div class="doc-callout warn">ℹ️ Les vues Telegram sont mises à jour en temps réel. Les vues Snapchat/Instagram peuvent prendre 24h à apparaître selon les APIs.</div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('revenue',document.querySelector('[data-doc=revenue]'))">Suivi des revenus →</button>
                </div>
              </div>

              <!-- revenue -->
              <div class="doc-section" id="doc-revenue" style="display:none">
                <div class="doc-breadcrumb">📊 Stats & Revenus</div>
                <h1 class="doc-h1">Suivi des revenus</h1>
                <p class="doc-p">La section Revenus te permet d'enregistrer et visualiser tes revenus issus de ta création de contenu.</p>
                <h2 class="doc-h2">Ajouter un revenu</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Va dans Revenus</strong><p>Clique sur $ Revenus dans la sidebar.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Saisir le montant</strong><p>Entre la date, la plateforme source et le montant en euros.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Visualiser</strong><p>Le graphique se met à jour automatiquement avec le cumul journalier.</p></div></div>
                </div>
                <div class="doc-callout info">💡 Ces données sont stockées localement sur le serveur et ne sont jamais partagées avec des tiers.</div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('spotlight',document.querySelector('[data-doc=spotlight]'))">Spotlight Snapchat →</button>
                </div>
              </div>

              <!-- spotlight -->
              <div class="doc-section" id="doc-spotlight" style="display:none">
                <div class="doc-breadcrumb">⚡ Avancé</div>
                <h1 class="doc-h1">Spotlight Snapchat</h1>
                <p class="doc-p">Le Spotlight Snapchat est une fonctionnalité avancée qui envoie automatiquement des vidéos courtes en boucle sur tes comptes Snapchat pour maximiser la visibilité.</p>
                <h2 class="doc-h2">Principe</h2>
                <div class="doc-callout info">Le système envoie +1 vidéo par compte à chaque minute. Il utilise un <strong>pool de vidéos</strong> : une liste de vidéos qui sont envoyées en rotation sur tous les comptes connectés.</div>
                <h2 class="doc-h2">Configurer le pool Spotlight</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Va dans Snapchat</strong><p>Clique sur Snapchat dans la sidebar → onglet <em>Spotlight</em>.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Ajouter des vidéos au pool</strong><p>Upload tes vidéos courtes (max 60s, format MP4/MOV).</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Activer</strong><p>Active le Spotlight. Le daemon prend le relais et envoie automatiquement les vidéos.</p></div></div>
                </div>
                <div class="doc-callout warn">⚠️ Respecte les <a href="https://snap.com/en-US/terms" target="_blank" style="color:var(--purple)">règles de contenu Snapchat Spotlight</a>. Le contenu inapproprié peut entraîner la suspension du compte.</div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('multiprofile',document.querySelector('[data-doc=multiprofile]'))">Multi-profils →</button>
                </div>
              </div>

              <!-- multiprofile -->
              <div class="doc-section" id="doc-multiprofile" style="display:none">
                <div class="doc-breadcrumb">⚡ Avancé</div>
                <h1 class="doc-h1">Multi-profils</h1>
                <p class="doc-p">Le système de profils permet de gérer plusieurs créateurs ou projets distincts depuis un seul compte administrateur, sans jamais mélanger les données.</p>
                <h2 class="doc-h2">Architecture</h2>
                <div class="doc-callout info">Chaque profil dispose de son propre répertoire de données isolé. Les comptes, playlists, statistiques et revenus d'un profil sont <strong>100% séparés</strong> des autres profils.</div>
                <h2 class="doc-h2">Sécurité — PIN</h2>
                <p class="doc-p">Chaque profil peut être protégé par un PIN à 4 chiffres. Pour switcher vers ce profil, le PIN est obligatoire. Cela permet à plusieurs créateurs de partager le même dashboard en toute sécurité.</p>
                <div class="doc-checklist">
                  <div class="doc-check-item"><span class="doc-check">✓</span> Le PIN est stocké sous forme de hash, jamais en clair</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Seul l'admin peut créer/supprimer des profils</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Chaque profil peut être personnalisé (couleur, avatar, nom)</div>
                </div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('oneup',document.querySelector('[data-doc=oneup]'))">Clef API OneUp →</button>
                </div>
              </div>

              <!-- oneup -->
              <div class="doc-section" id="doc-oneup" style="display:none">
                <div class="doc-breadcrumb">⚡ Avancé</div>
                <h1 class="doc-h1">Clef API OneUp</h1>
                <p class="doc-p">OneUp est un service tiers partenaire de Snapchat et Meta qui permet la publication programmée. StoryScheduler l'utilise pour Snapchat, Instagram et Facebook.</p>
                <h2 class="doc-h2">Obtenir ta clef API</h2>
                <div class="doc-steps">
                  <div class="doc-step"><div class="doc-step-num">1</div><div><strong>Crée un compte OneUp</strong><p>Rends-toi sur 1up.app et crée un compte (plan payant requis pour l'accès API).</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">2</div><div><strong>Génère une clef API</strong><p>Dans les paramètres OneUp → API → Générer une clef.</p></div></div>
                  <div class="doc-step"><div class="doc-step-num">3</div><div><strong>Configure dans StoryScheduler</strong><p>Dans la page Comptes, colle ta clef dans le champ <em>Clef API OneUp</em> et clique Sauvegarder.</p></div></div>
                </div>
                <div class="doc-callout warn">⚠️ Ta clef API est confidentielle. Ne la partage jamais. Régénère-la immédiatement si elle est compromise.</div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('faq',document.querySelector('[data-doc=faq]'))">FAQ →</button>
                </div>
              </div>

              <!-- faq -->
              <div class="doc-section" id="doc-faq" style="display:none">
                <div class="doc-breadcrumb">❓ Support</div>
                <h1 class="doc-h1">FAQ</h1>
                <div class="doc-faq-list">
                  <div class="doc-faq"><div class="doc-faq-q">Mon compte Telegram se déconnecte souvent, pourquoi ?</div><div class="doc-faq-a">Les sessions Telegram peuvent expirer si Telegram détecte une activité inhabituelle. Utilise la fonction 🔄 Reconnecter dans la page Comptes. Assure-toi que le numéro utilisé est actif et que 2FA est correctement configuré.</div></div>
                  <div class="doc-faq"><div class="doc-faq-q">Pourquoi ma story n'est pas publiée à l'heure prévue ?</div><div class="doc-faq-a">Le daemon vérifie les publications toutes les minutes. Un retard de 1-2 minutes est normal. Si la story reste bloquée, vérifie que le compte est bien connecté (indicateur vert).</div></div>
                  <div class="doc-faq"><div class="doc-faq-q">Puis-je programmer des stories à l'avance sur plusieurs semaines ?</div><div class="doc-faq-a">Oui. L'auto-scheduling empile les stories les unes après les autres sans limite de date. Tu peux programmer plusieurs centaines de stories à l'avance.</div></div>
                  <div class="doc-faq"><div class="doc-faq-q">Les données de mon profil sont-elles partagées avec d'autres profils ?</div><div class="doc-faq-a">Non. Chaque profil est stocké dans un répertoire totalement isolé. Il est techniquement impossible qu'un profil accède aux données d'un autre.</div></div>
                  <div class="doc-faq"><div class="doc-faq-q">Comment supprimer une story programmée ?</div><div class="doc-faq-a">Dans la page de la plateforme concernée, clique sur la story dans le panneau droit → icône de suppression ✕. La story est annulée immédiatement.</div></div>
                  <div class="doc-faq"><div class="doc-faq-q">Le site est-il conforme RGPD ?</div><div class="doc-faq-a">Oui. Aucune donnée personnelle n'est transmise à des serveurs tiers. Toutes les données (comptes, médias, statistiques) sont stockées sur le serveur dédié de la plateforme. Voir les Mentions légales pour plus de détails.</div></div>
                </div>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('legal',document.querySelector('[data-doc=legal]'))">Mentions légales →</button>
                </div>
              </div>

              <!-- legal -->
              <div class="doc-section" id="doc-legal" style="display:none">
                <div class="doc-breadcrumb">❓ Support</div>
                <h1 class="doc-h1">Mentions légales</h1>
                <h2 class="doc-h2">Éditeur</h2>
                <p class="doc-p">StoryScheduler est un logiciel SaaS édité à titre privé. Pour toute question, contacte l'administrateur via les coordonnées fournies lors de ton inscription.</p>
                <h2 class="doc-h2">Hébergement</h2>
                <p class="doc-p">Le service est hébergé sur un serveur dédié sécurisé. Les données sont stockées exclusivement sur ce serveur et ne sont jamais transmises à des tiers, sauf aux APIs officielles des plateformes (Telegram, OneUp/Meta).</p>
                <h2 class="doc-h2">Données personnelles (RGPD)</h2>
                <p class="doc-p">Conformément au Règlement Général sur la Protection des Données (RGPD — Règlement UE 2016/679) :</p>
                <div class="doc-checklist">
                  <div class="doc-check-item"><span class="doc-check">✓</span> Seules les données strictement nécessaires au fonctionnement sont collectées (identifiant, hash du mot de passe, données de comptes réseaux sociaux)</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Aucune donnée n'est revendue ou partagée avec des tiers à des fins commerciales</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Tu disposes d'un droit d'accès, de rectification et de suppression de tes données</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Les mots de passe sont stockés sous forme de hash bcrypt (jamais en clair)</div>
                </div>
                <h2 class="doc-h2">Propriété intellectuelle</h2>
                <p class="doc-p">Le code source, le design et les contenus de StoryScheduler sont protégés par le droit d'auteur. Toute reproduction ou distribution sans autorisation est interdite.</p>
                <h2 class="doc-h2">Limitation de responsabilité</h2>
                <p class="doc-p">L'éditeur décline toute responsabilité en cas d'utilisation de la plateforme en violation des conditions d'utilisation des réseaux sociaux tiers (Telegram, Snapchat, Meta). L'utilisateur est seul responsable du contenu qu'il publie.</p>
                <div class="doc-next-btn-row">
                  <button class="doc-next-btn" onclick="showDoc('cgu',document.querySelector('[data-doc=cgu]'))">CGU →</button>
                </div>
              </div>

              <!-- cgu -->
              <div class="doc-section" id="doc-cgu" style="display:none">
                <div class="doc-breadcrumb">❓ Support</div>
                <h1 class="doc-h1">Conditions Générales d'Utilisation</h1>
                <p class="doc-p" style="font-size:.78rem;color:var(--t3)">Dernière mise à jour : juillet 2025</p>
                <h2 class="doc-h2">1. Objet</h2>
                <p class="doc-p">Les présentes CGU définissent les conditions d'utilisation de la plateforme StoryScheduler, outil d'automatisation de publication de contenu sur les réseaux sociaux.</p>
                <h2 class="doc-h2">2. Accès au service</h2>
                <p class="doc-p">L'accès est réservé aux utilisateurs disposant d'un compte valide. Toute tentative d'accès non autorisé est interdite et susceptible d'engager la responsabilité pénale.</p>
                <h2 class="doc-h2">3. Obligations de l'utilisateur</h2>
                <div class="doc-checklist">
                  <div class="doc-check-item"><span class="doc-check">✓</span> Utiliser le service conformément aux CGU des plateformes tierces (Telegram, Snapchat, Meta)</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Ne pas publier de contenu illégal, diffamatoire, ou portant atteinte aux droits de tiers</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Ne pas tenter de contourner les mécanismes de sécurité du service</div>
                  <div class="doc-check-item"><span class="doc-check">✓</span> Maintenir la confidentialité de ses identifiants de connexion</div>
                </div>
                <h2 class="doc-h2">4. Contenu publié</h2>
                <p class="doc-p">L'utilisateur est seul responsable des contenus qu'il programme et publie via StoryScheduler. L'éditeur ne peut être tenu responsable de contenus publiés en violation des lois en vigueur ou des CGU des plateformes concernées.</p>
                <h2 class="doc-h2">5. Interruption du service</h2>
                <p class="doc-p">L'éditeur se réserve le droit de suspendre l'accès au service pour maintenance, mise à jour, ou en cas de violation des présentes CGU, sans préavis ni indemnité.</p>
                <h2 class="doc-h2">6. Droit applicable</h2>
                <p class="doc-p">Les présentes CGU sont soumises au droit français. Tout litige sera soumis aux tribunaux compétents du ressort de l'éditeur.</p>
              </div>

            </div><!-- /docContent -->
          </div>
        </div>
        <!-- /Documentation -->

        <!-- Modal ajout compte social -->
        <div class="overlay hidden" id="overlayAddSocial" onclick="if(event.target===this)this.classList.add('hidden')">
          <div class="modal" style="max-width:400px">
            <div class="modal-t" id="addSocialTitle">Ajouter un compte</div>
            <div class="modal-s">Entre le nom d'affichage et l'identifiant OneUp du compte</div>
            <div id="addSocialImportRow" style="margin-top:14px;padding:10px 12px;background:rgba(124,58,237,.07);border:1px solid rgba(124,58,237,.2);border-radius:8px;display:flex;align-items:center;gap:10px">
              <span style="font-size:.75rem;color:var(--t2);flex:1">Importer automatiquement via OneUp</span>
              <button class="btn btn-xs" id="addSocialImportBtn" onclick="_importSocialFromOneUp()" style="background:rgba(124,58,237,.2);border-color:rgba(124,58,237,.4);color:#a78bfa;white-space:nowrap">🔄 Importer</button>
            </div>
            <div id="addSocialImportList" style="display:none;margin-top:8px;max-height:160px;overflow-y:auto;flex-direction:column;gap:4px"></div>
            <div style="display:flex;align-items:center;gap:8px;margin:12px 0 8px">
              <div style="flex:1;height:1px;background:var(--b1)"></div>
              <span style="font-size:.7rem;color:var(--t3)">ou entrer manuellement</span>
              <div style="flex:1;height:1px;background:var(--b1)"></div>
            </div>
            <input id="addSocialName" class="inp" placeholder="Nom / @username">
            <input id="addSocialId" class="inp" placeholder="ID OneUp (ex: 123456)" style="margin-top:8px">
            <div id="addSocialErr" style="color:#f87171;font-size:.78rem;min-height:16px;margin-top:6px"></div>
            <div style="display:flex;gap:8px;margin-top:14px">
              <button class="btn btn-primary" style="flex:1" onclick="_confirmAddSocial()">✓ Ajouter</button>
              <button class="btn" onclick="document.getElementById('overlayAddSocial').classList.add('hidden')">Annuler</button>
            </div>
          </div>
        </div>

        <!-- MODAL PHOTO URL -->
        <div class="overlay hidden" id="overlayPhotoUrl" onclick="if(event.target===this)this.classList.add('hidden')">
          <div class="modal" style="max-width:380px">
            <div class="modal-t">📷 Photo de profil</div>
            <div class="modal-s">Compte : <strong id="photoUrlPlatLabel"></strong> — <span id="photoUrlAccLabel"></span></div>
            <div style="margin:14px 0 6px;font-size:.78rem;color:var(--t2)">Colle l'URL directe de la photo de profil :</div>
            <input id="photoUrlInput" class="inp" placeholder="https://…" style="font-size:.78rem">
            <div style="margin-top:7px;padding:8px 10px;background:rgba(124,58,237,.06);border:1px solid rgba(124,58,237,.15);border-radius:7px;font-size:.7rem;color:#888">
              💡 Sur Instagram : ouvre ton profil dans un navigateur → clic droit sur la photo → "Copier l'adresse de l'image"
            </div>
            <div id="photoUrlErr" style="color:#f87171;font-size:.75rem;min-height:16px;margin-top:6px"></div>
            <div style="display:flex;gap:8px;margin-top:12px">
              <button class="btn btn-primary" id="photoUrlConfirmBtn" style="flex:1" onclick="_confirmPhotoUrl()">✓ Enregistrer</button>
              <button class="btn" onclick="document.getElementById('overlayPhotoUrl').classList.add('hidden')">Annuler</button>
            </div>
          </div>
        </div>

        <!-- MODAL RECONNEXION TELEGRAM -->
        <div class="pin-modal" id="reconnectModal">
          <div class="pin-box" onclick="event.stopPropagation()" style="width:380px;padding:32px 28px">
            <div style="font-size:1.1rem;font-weight:800;margin-bottom:4px" id="reconTitle">🔄 Reconnecter le compte</div>
            <div style="font-size:.78rem;color:var(--t3);margin-bottom:20px" id="reconPhone"></div>

            <!-- Étape 1 : envoi code -->
            <div id="reconStep1">
              <div style="font-size:.82rem;color:var(--t2);margin-bottom:12px">Clique pour recevoir un code SMS / Telegram sur ce numéro.</div>
              <button class="btn" id="reconBtnSend" onclick="reconSendCode()" style="width:100%">📨 Envoyer le code</button>
            </div>

            <!-- Étape 2 : saisie code -->
            <div id="reconStep2" style="display:none">
              <div style="font-size:.82rem;color:var(--t2);margin-bottom:8px">Entre le code reçu :</div>
              <input id="reconCodeInp" class="inp" placeholder="ex: 12345" style="width:100%;margin-bottom:10px;text-align:center;letter-spacing:6px;font-size:1.3rem" maxlength="6" oninput="if(this.value.length===5)reconVerify()">
              <button class="btn" onclick="reconVerify()" style="width:100%">✅ Valider</button>
            </div>

            <!-- Étape 3 : 2FA -->
            <div id="reconStep3" style="display:none">
              <div style="font-size:.82rem;color:var(--t2);margin-bottom:8px">Mot de passe 2FA :</div>
              <input id="recon2faInp" class="inp" type="password" placeholder="Mot de passe Telegram" style="width:100%;margin-bottom:10px">
              <button class="btn" onclick="recon2fa()" style="width:100%">🔐 Valider</button>
            </div>

            <div id="reconMsg" style="margin-top:10px;font-size:.8rem;min-height:18px;text-align:center"></div>
            <button class="btn btn-ghost" onclick="closeReconModal()" style="width:100%;margin-top:12px;font-size:.8rem">Annuler</button>
          </div>
        </div>

      </div>

      <!-- RIGHT PANEL -->
      <div class="right-panel" id="rightPanel">
        <div class="rp-hd" style="flex-direction:column;align-items:stretch;gap:10px;padding-bottom:12px">
          <div style="display:flex;align-items:center;justify-content:space-between">
            <div class="rp-title" id="rpTitle">📱 Telegram</div>
            <div class="rp-hd-btns" style="display:flex;gap:6px">
              <button class="btn btn-xs btn-danger" id="btnSnapDeleteAll" style="display:none" title="Supprimer tout">🗑 Tout</button>
              <button class="btn btn-xs" id="btnSelMode">Sélectionner</button>
              <button class="btn btn-xs" id="btnCloneRP" title="Copier vers un compte">+ Compte</button>
              <button class="btn btn-xs" id="btnSplRpRefresh" style="display:none" title="Rafraîchir">🔄</button>
              <button class="btn btn-xs" id="btnRpRefresh" style="display:none" title="Rafraîchir">🔄</button>
            </div>
          </div>
          <div class="sched-tabs" id="rpSchedTabs" style="align-self:stretch;display:grid;grid-template-columns:1fr 1fr">
            <button class="sched-tab sched-tab-act" data-tab="pending" onclick="_setSchedFilter('pending')" style="justify-content:center">📅 En attente</button>
            <button class="sched-tab" data-tab="done" onclick="_setSchedFilter('done')" style="justify-content:center">✅ Publiées</button>
          </div>
          <!-- Filtres Spotlight dans le panneau droit -->
          <div id="rpSplTabs" style="display:none;align-self:stretch;display:none;grid-template-columns:1fr 1fr 1fr;gap:4px">
            <button class="sched-tab sched-tab-act" onclick="_setSplFilter('all')" data-splf="all" style="justify-content:center;font-size:.65rem">Tous</button>
            <button class="sched-tab" onclick="_setSplFilter('pending')" data-splf="pending" style="justify-content:center;font-size:.65rem">⏳ Attente</button>
            <button class="sched-tab" onclick="_setSplFilter('done')" data-splf="done" style="justify-content:center;font-size:.65rem">✅ Envoyés</button>
          </div>
        </div>
        <div class="rp-list" id="slist"><div class="no-rp">Aucune story programmée</div></div>
        <div class="rp-list" id="splRpList" style="display:none"><div class="no-rp">Aucun Spotlight programmé</div></div>
        <div class="rp-list" id="igRpList" style="display:none"><div class="no-rp">Aucun post programmé</div></div>
        <div class="rp-list" id="fbRpList" style="display:none"><div class="no-rp">Aucun post programmé</div></div>
      </div>
    </div>
  </div>
</div>

<!-- Modal sélecteur de plateforme -->
<div class="overlay hidden" id="overlayPlatformPicker" onclick="if(event.target===this)this.classList.add('hidden')">
  <div class="modal" style="max-width:420px">
    <div class="modal-t">Ajouter un compte</div>
    <div class="modal-s">Choisis la plateforme</div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:20px">
      <button onclick="document.getElementById('overlayPlatformPicker').classList.add('hidden');openAuthModal()" style="display:flex;flex-direction:column;align-items:center;gap:10px;padding:20px 12px;background:#111;border:1px solid #222;border-radius:14px;cursor:pointer;transition:border-color .2s,background .2s" onmouseover="this.style.borderColor='#2CA5E0';this.style.background='rgba(44,165,224,.08)'" onmouseout="this.style.borderColor='#222';this.style.background='#111'">
        <svg width="36" height="36" viewBox="0 0 240 240"><circle cx="120" cy="120" r="120" fill="#2CA5E0"/><path fill="#fff" d="M20.665 100.68c49.238-21.462 82.064-35.607 98.477-42.437 46.905-19.52 56.629-22.918 62.959-23.04 1.396-.024 4.52.322 6.547 1.97 1.707 1.389 2.177 3.262 2.405 4.576.229 1.315.512 4.306.284 6.647-2.548 26.78-13.558 91.763-19.161 121.77-2.369 12.696-7.038 16.951-11.561 17.36-9.826.906-17.294-6.492-26.828-12.73-14.913-9.766-23.33-15.844-37.82-25.386-16.718-11.016-5.882-17.068 3.638-26.978 2.49-2.583 45.749-41.925 46.575-45.503.104-.447.201-2.113-1.28-2.994-1.481-.88-3.666-.577-5.243-.339-2.233.336-37.78 24.014-106.64 70.58-10.091 6.929-19.232 10.308-27.424 10.132-9.025-.193-26.383-5.108-39.284-9.306-15.832-5.148-28.405-7.875-27.324-16.619.565-4.561 6.867-9.225 18.905-14.003z"/></svg>
        <span style="color:#fff;font-size:.8rem;font-weight:700">Telegram</span>
        <span style="color:#555;font-size:.68rem">Connexion SMS</span>
      </button>
      <button onclick="document.getElementById('overlayPlatformPicker').classList.add('hidden');openSnapConfigModal()" style="display:flex;flex-direction:column;align-items:center;gap:10px;padding:20px 12px;background:#111;border:1px solid #222;border-radius:14px;cursor:pointer;transition:border-color .2s,background .2s" onmouseover="this.style.borderColor='#FFFC00';this.style.background='rgba(255,252,0,.06)'" onmouseout="this.style.borderColor='#222';this.style.background='#111'">
        <svg width="36" height="36" viewBox="0 0 48 48"><rect width="48" height="48" rx="9" fill="#FFFC00"/><path fill="#000" d="M24 7c-5.3 0-9.5 4.1-9.5 9.2v1.4c-1 .3-2.2.6-3 .6h-.5c-.11-.02-.2.07-.17.18.28.7 1.46 1.37 2.24 1.65.07.02.13.09.14.17.38 1.76 1.08 3.23 2.1 4.35-1.33.75-2.66 1.55-2.66 2.92 0 .98.84 1.73 2.57 2.18.17.05.3.18.31.35.21.98.58 1.91 1.06 2.47-.47.2-.9.4-.9.7 0 .54.83 1.03 2.33 1.03h1.25c.82.76 1.94 1.22 3.3 1.22s2.48-.46 3.3-1.22h1.25c1.5 0 2.33-.49 2.33-1.03 0-.3-.43-.5-.9-.7.48-.56.85-1.49 1.06-2.47.01-.17.14-.3.31-.35 1.73-.45 2.57-1.2 2.57-2.18 0-1.37-1.33-2.17-2.66-2.92 1.02-1.12 1.72-2.59 2.1-4.35.01-.08.07-.15.14-.17.78-.28 1.96-.95 2.24-1.65.03-.11-.06-.2-.17-.18h-.05c-.78 0-1.9-.27-3-.6v-1.4C33.5 11.1 29.3 7 24 7z"/></svg>
        <span style="color:#fff;font-size:.8rem;font-weight:700">Snapchat</span>
        <span style="color:#555;font-size:.68rem">Via OneUp</span>
      </button>
      <button onclick="document.getElementById('overlayPlatformPicker').classList.add('hidden');openIgConfigModal()" style="display:flex;flex-direction:column;align-items:center;gap:10px;padding:20px 12px;background:#111;border:1px solid #222;border-radius:14px;cursor:pointer;transition:border-color .2s,background .2s" onmouseover="this.style.borderColor='#c084fc';this.style.background='rgba(192,132,252,.08)'" onmouseout="this.style.borderColor='#222';this.style.background='#111'">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="url(#igGrad)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><defs><linearGradient id="igGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#833ab4"/><stop offset="50%" stop-color="#fd1d1d"/><stop offset="100%" stop-color="#fcb045"/></linearGradient></defs><rect x="2" y="2" width="20" height="20" rx="5" stroke="url(#igGrad)"/><circle cx="12" cy="12" r="4.5" stroke="url(#igGrad)"/><circle cx="17.5" cy="6.5" r="1" fill="#fd1d1d" stroke="none"/></svg>
        <span style="color:#fff;font-size:.8rem;font-weight:700">Instagram</span>
        <span style="color:#555;font-size:.68rem">Via OneUp</span>
      </button>
    </div>
    <button class="btn" onclick="document.getElementById('overlayPlatformPicker').classList.add('hidden')" style="width:100%;margin-top:16px">Annuler</button>
  </div>
</div>

<!-- Modal config Snapchat (OneUp) -->
<div class="overlay hidden" id="overlaySnapConfig" onclick="if(event.target===this)this.classList.add('hidden')">
  <div class="modal" style="max-width:400px">
    <div class="modal-t">👻 Comptes Snapchat</div>
    <div class="modal-s">Les comptes Snap sont importés depuis OneUp</div>
    <div style="margin-top:16px;padding:14px;background:#0d0d0d;border:1px solid #1a1a1a;border-radius:10px;font-size:.78rem;color:var(--t2);line-height:1.6">
      Les comptes Snapchat se connectent via <b style="color:#f5c518">OneUp</b>.<br>
      Configure ta clé API OneUp dans <b>Réglages → Profil</b>, puis clique <b>Rafraîchir</b> dans le panel Snapchat.
    </div>
    <button class="btn btn-primary" onclick="document.getElementById('overlaySnapConfig').classList.add('hidden');navigateTo('settings')" style="width:100%;margin-top:14px;background:rgba(245,197,24,.15);border-color:rgba(245,197,24,.4);color:#f5c518">⚙️ Aller dans Réglages</button>
    <button class="btn" onclick="document.getElementById('overlaySnapConfig').classList.add('hidden')" style="width:100%;margin-top:8px">Fermer</button>
  </div>
</div>

<!-- Modal config Instagram (OneUp) -->
<div class="overlay hidden" id="overlayIgConfig" onclick="if(event.target===this)this.classList.add('hidden')">
  <div class="modal" style="max-width:400px">
    <div class="modal-t">📸 Comptes Instagram</div>
    <div class="modal-s">Les comptes Instagram sont importés depuis OneUp</div>
    <div style="margin-top:16px;padding:14px;background:#0d0d0d;border:1px solid #1a1a1a;border-radius:10px;font-size:.78rem;color:var(--t2);line-height:1.6">
      Les comptes Instagram se connectent via <b style="color:#c084fc">OneUp</b>.<br>
      Configure ta clé API OneUp dans <b>Réglages → Profil</b>, puis clique <b>Rafraîchir</b> dans le panel Instagram.
    </div>
    <button class="btn btn-primary" onclick="document.getElementById('overlayIgConfig').classList.add('hidden');navigateTo('settings')" style="width:100%;margin-top:14px;background:rgba(192,132,252,.15);border-color:rgba(192,132,252,.4);color:#c084fc">⚙️ Aller dans Réglages</button>
    <button class="btn" onclick="document.getElementById('overlayIgConfig').classList.add('hidden')" style="width:100%;margin-top:8px">Fermer</button>
  </div>
</div>

<!-- Modal Auth -->
<div class="overlay hidden" id="overlayAuth">
  <div class="modal">
    <div class="modal-t" id="mTitle">Ajouter un compte</div>
    <div class="modal-s" id="mSub">Numéro de téléphone pour recevoir le SMS</div>
    <div id="sPhone"><div class="fld"><label>Téléphone</label><input type="tel" id="iPhone" placeholder="+33612345678"></div></div>
    <div id="sCode" style="display:none"><div class="fld"><label>Code SMS</label><input type="text" id="iCode" placeholder="12345" maxlength="6" inputmode="numeric"></div></div>
    <div id="s2fa" style="display:none"><div class="fld"><label>Mot de passe 2FA</label><input type="password" id="iPass"></div></div>
    <div class="merr" id="mErr"></div>
    <div class="mbtns"><button class="btn" onclick="closeAuthModal()">Annuler</button><button class="btn btn-danger" id="btnMOk">Envoyer le code</button></div>
  </div>
</div>

<!-- Modal Renommer -->
<div class="overlay hidden" id="overlayRename">
  <div class="modal">
    <div class="modal-t">✏ Renommer le compte</div>
    <div class="modal-s" id="renameSub"></div>
    <div class="fld"><label>Nouveau pseudo</label><input type="text" id="renameInp" placeholder="Ex: Pauline principale"></div>
    <div class="merr" id="renameErr"></div>
    <div class="mbtns"><button class="btn" onclick="document.getElementById('overlayRename').classList.add('hidden')">Annuler</button><button class="btn btn-primary" id="btnRenameOk">✓ Sauvegarder</button></div>
  </div>
</div>

<!-- Modal Note -->
<div class="overlay hidden" id="overlayNote">
  <div class="modal">
    <div class="modal-t">📝 Remarque</div>
    <div class="modal-s" id="noteSub"></div>
    <div class="fld"><label>Remarque</label><input type="text" id="noteInp" placeholder="Ex: Campagne été, lancement…"></div>
    <div class="merr" id="noteErr"></div>
    <div class="mbtns"><button class="btn" onclick="document.getElementById('overlayNote').classList.add('hidden')">Annuler</button><button class="btn btn-primary" id="btnNoteOk">✓ Sauvegarder</button></div>
  </div>
</div>

<!-- Modal Reprogrammer en masse -->
<div class="overlay hidden" id="overlayBulkReschedule">
  <div class="modal">
    <div class="modal-t">📅 Reprogrammer la sélection</div>
    <div class="modal-s" id="bulkRescheduleSub">Change la date de toutes les stories sélectionnées (l'heure reste inchangée).</div>
    <div class="fld"><label>Nouvelle date</label><input type="date" id="bulkDateInp" style="width:100%;background:#0a0a0a;border:1px solid var(--b2);border-radius:var(--r2);padding:8px 10px;color:var(--t1);font-size:.82rem;color-scheme:dark"></div>
    <div class="merr" id="bulkRescheduleErr"></div>
    <div class="mbtns">
      <button class="btn" onclick="document.getElementById('overlayBulkReschedule').classList.add('hidden')">Annuler</button>
      <button class="btn btn-primary" id="btnBulkRescheduleOk">✓ Reprogrammer</button>
    </div>
  </div>
</div>

<!-- Modal Copier vers compte -->
<div class="overlay hidden" id="overlayClone">
  <div class="modal">
    <div class="modal-t">➕ Reprogrammer sur un compte</div>
    <div class="modal-s">Copie tous les posts <b>en attente</b> vers un autre compte, aux mêmes dates.</div>
    <div class="fld"><label>Ajouter sur :</label><div class="launch-accs" id="cloneAccs"></div></div>
    <div class="merr" id="cloneErr"></div>
    <div class="mbtns"><button class="btn" onclick="document.getElementById('overlayClone').classList.add('hidden')">Annuler</button><button class="btn btn-primary" id="btnCloneOk">➕ Copier</button></div>
  </div>
</div>

<!-- Modal Lancer playlist -->
<div class="overlay hidden" id="overlayLaunch">
  <div class="modal">
    <div class="modal-t" id="launchTitle">Lancer la playlist</div>
    <div class="modal-s">Les jours s'adaptent automatiquement à la date de début</div>
    <div class="fld"><label>Date de début</label><input type="date" id="launchDate"></div>
    <div class="fld"><label>Poster sur :</label><div class="launch-accs" id="launchAccs"></div></div>
    <div class="merr" id="launchErr"></div>
    <div class="mbtns"><button class="btn" onclick="closeLaunchModal()">Annuler</button><button class="btn btn-primary" id="btnLaunchOk">▶ Lancer</button></div>
  </div>
</div>

<div class="tw" id="tw"></div>
<div class="img-preview-popup" id="imgPreview"><img id="imgPreviewImg" src=""><div class="prev-date" id="imgPreviewDate"></div></div>

<script>
// ── Utils ──────────────────────────────────────────────────────────────────
function toast(msg,type='inf'){
  const el=document.createElement('div');el.className=`toast ${type}`;
  el.innerHTML=`<span>${type==='ok'?'✓':type==='err'?'✕':'ℹ'}</span><span>${msg}</span>`;
  document.getElementById('tw').appendChild(el);
  setTimeout(()=>{el.style.animation='none';el.style.opacity='0';setTimeout(()=>el.remove(),300);},3500);
}
function fmt(iso){try{return new Date(iso).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});}catch{return iso;}}
function defDt(ms=3600000){const d=new Date(Date.now()+ms);d.setSeconds(0,0);const p=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;}
// Convertit un objet Date en chaîne datetime-local (heure LOCALE, pas UTC)
function _localDtStr(d){const p=n=>String(n).padStart(2,'0');return`${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`}
function todayStr(){const d=new Date();const p=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;}

async function confirmLogout(){
  await fetch('/api/auth/logout',{method:'POST'}).catch(()=>{});
  window.location.reload();
}

const _PLAN_INFO={
  '':        {badge:'🔒',name:'Aucun forfait',price:'Accès bloqué',feats:[]},
  'starter': {badge:'⚡',name:'Starter',price:'15€ / mois',feats:['Telegram ✓','Snapchat ✓','Médias ✓','Comptes ✓ (10 max)','Instagram ✗','Facebook ✗','Stats ✗','Revenus ✗']},
  'pro':     {badge:'🚀',name:'Pro',price:'39€ / mois',feats:['Toutes les plateformes ✓','Médias ✓','Comptes ✓ (25 max)','Stats ✓','Revenus ✓']},
  'business':{badge:'🏢',name:'Business',price:'239€ / mois',feats:['Tout illimité ✓','Support prioritaire ✓','Comptes illimités ✓']},
};

function openSubModal(){
  const prof=(_profiles||[]).find(p=>p.id===_activeProfileId);
  const plan=prof?prof.plan||'':'';
  const info=_PLAN_INFO[plan]||_PLAN_INFO[''];
  document.getElementById('subPlanBadge').textContent=info.badge;
  document.getElementById('subPlanName').textContent=info.name;
  document.getElementById('subPlanPrice').textContent=info.price;
  const featsEl=document.getElementById('subPlanFeats');
  featsEl.innerHTML=info.feats.map(f=>`<span style="font-size:.72rem;padding:3px 10px;border-radius:20px;background:${f.includes('✗')?'rgba(248,113,113,.08)':'rgba(124,58,237,.12)'};border:1px solid ${f.includes('✗')?'rgba(248,113,113,.2)':'rgba(124,58,237,.25)'};color:${f.includes('✗')?'#6b7280':'#a78bfa'}">${f}</span>`).join('');
  const adminSec=document.getElementById('subAdminSection');
  const userSec=document.getElementById('subUserSection');
  if(_sessionIsAdmin){adminSec.style.display='block';userSec.style.display='none';_subHighlightBtn(plan);}
  else{adminSec.style.display='none';userSec.style.display='block';}
  document.getElementById('subSaveStatus').textContent='';
  const lbl=document.getElementById('sbSubLabel');
  if(lbl)lbl.textContent=info.name==='Aucun forfait'?'Mon abonnement':`Forfait ${info.name}`;
  document.getElementById('subModal').classList.add('open');
}

function _subHighlightBtn(plan){
  ['','starter','pro','business'].forEach(p=>{
    const id='subBtn'+(p===''?'None':p.charAt(0).toUpperCase()+p.slice(1));
    const btn=document.getElementById(id);
    if(!btn)return;
    btn.style.outline=plan===p?'2px solid #a78bfa':'none';
    btn.style.outlineOffset='2px';
  });
}

async function subSetPlan(plan){
  if(!_activeProfileId)return;
  const st=document.getElementById('subSaveStatus');
  st.textContent='Enregistrement…';st.style.color='#888';
  const r=await fetch(`/api/profiles/${_activeProfileId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan:plan||null})}).catch(()=>null);
  if(r&&r.ok){
    const prof=(_profiles||[]).find(p=>p.id===_activeProfileId);
    if(prof)prof.plan=plan||null;
    const info=_PLAN_INFO[plan||'']||_PLAN_INFO[''];
    document.getElementById('subPlanBadge').textContent=info.badge;
    document.getElementById('subPlanName').textContent=info.name;
    document.getElementById('subPlanPrice').textContent=info.price;
    const featsEl=document.getElementById('subPlanFeats');
    featsEl.innerHTML=info.feats.map(f=>`<span style="font-size:.72rem;padding:3px 10px;border-radius:20px;background:${f.includes('✗')?'rgba(248,113,113,.08)':'rgba(124,58,237,.12)'};border:1px solid ${f.includes('✗')?'rgba(248,113,113,.2)':'rgba(124,58,237,.25)'};color:${f.includes('✗')?'#6b7280':'#a78bfa'}">${f}</span>`).join('');
    _subHighlightBtn(plan||'');
    const lbl=document.getElementById('sbSubLabel');
    if(lbl)lbl.textContent=info.name==='Aucun forfait'?'Mon abonnement':`Forfait ${info.name}`;
    st.textContent='✓ Forfait mis à jour';st.style.color='#4ade80';
    _applyPlanRestrictions(plan||null);
  }else{st.textContent='Erreur lors de la sauvegarde';st.style.color='#f87171';}
}

async function subPayPlan(plan){
  const st=document.getElementById('subPayStatus');
  const btns=['subPayStarter','subPayPro','subPayBusiness'].map(id=>document.getElementById(id));
  btns.forEach(b=>{if(b)b.disabled=true;});
  st.textContent='Redirection vers Stripe…';st.style.color='#a78bfa';
  try{
    const r=await fetch('/api/stripe/checkout',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({plan,profile_id:_activeProfileId})
    });
    const d=await r.json();
    if(d.url){window.location.href=d.url;}
    else{st.textContent='Erreur: '+(d.error||'price_id manquant');st.style.color='#f87171';}
  }catch(e){st.textContent='Erreur réseau';st.style.color='#f87171';}
  btns.forEach(b=>{if(b)b.disabled=false;});
}

// ── Filtre programmé/publié ────────────────────────────────────────────────
let _schedFilter='pending'; // 'pending' | 'done'
function _setSchedFilter(v){
  _schedFilter=v;
  document.querySelectorAll('.sched-tab').forEach(t=>t.classList.toggle('sched-tab-act',t.dataset.tab===v));
  if(currentPage==='schedule')loadScheduled();
  else if(currentPage==='snapchat')loadSnapScheduled();
  else if(currentPage==='instagram')loadIgScheduled();
  else if(currentPage==='facebook')loadFbScheduled();
}

async function _doLogin(){
  const btn=document.getElementById('loginBtn');
  const username=document.getElementById('loginUsername').value.trim();
  const password=document.getElementById('loginPassword').value;
  const errEl=document.getElementById('loginErr');
  errEl.textContent='';
  if(!username||!password){errEl.textContent='Remplis tous les champs.';return;}
  btn.disabled=true;btn.textContent='Connexion…';
  try{
    const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){errEl.textContent=d.detail||'Identifiant ou mot de passe incorrect';return;}
    // Demander au navigateur d'enregistrer les identifiants
    if(window.PasswordCredential){
      try{
        const cred=new PasswordCredential({id:username,password,name:username});
        await navigator.credentials.store(cred);
      }catch(_){}
    }
    // Success — enter app
    _sessionIsAdmin = !!d.is_admin;
    document.getElementById('loginScreen').style.display='none';
    document.querySelector('.app').style.display='';
    reloadAllData();
    loadProfiles();
  }catch(e){
    errEl.textContent='Erreur de connexion — réessaie.';
  }finally{
    btn.disabled=false;btn.textContent='Se connecter';
  }
}

function _showLanding(){
  document.getElementById('landingPanel').style.display='block';
  document.getElementById('loginFormWrapper').style.display='none';
}
function lpToggleFaq(el){
  const body=el.querySelector('.lp-faq-body');
  const icon=el.querySelector('.lp-faq-icon');
  const open=body.style.display==='block';
  body.style.display=open?'none':'block';
  icon.textContent=open?'+':'−';
  icon.style.transform=open?'':'rotate(45deg)';
}
function _showRegister(){
  document.getElementById('landingPanel').style.display='none';
  document.getElementById('loginFormWrapper').style.display='flex';
  document.getElementById('loginPanel').style.display='none';
  document.getElementById('registerPanel').style.display='';
  document.getElementById('registerErr').textContent='';
  ['regName','regLogin','regPassword','regConfirm'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
}
function _showLogin(){
  document.getElementById('landingPanel').style.display='none';
  document.getElementById('loginFormWrapper').style.display='flex';
  document.getElementById('registerPanel').style.display='none';
  document.getElementById('loginPanel').style.display='';
  document.getElementById('loginErr').textContent='';
}
async function _doRegister(){
  const btn=document.getElementById('registerBtn');
  const name=document.getElementById('regName').value.trim();
  const login=document.getElementById('regLogin').value.trim();
  const password=document.getElementById('regPassword').value;
  const confirm=document.getElementById('regConfirm').value;
  const errEl=document.getElementById('registerErr');
  errEl.textContent='';
  if(!name||!login||!password){errEl.textContent='Remplis tous les champs.';return;}
  if(password!==confirm){errEl.textContent='Les mots de passe ne correspondent pas.';return;}
  if(password.length<6){errEl.textContent='Le mot de passe doit faire au moins 6 caractères.';return;}
  btn.disabled=true;btn.textContent='Création…';
  try{
    const r=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,login,password})});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){errEl.textContent=d.detail||'Erreur lors de la création du compte.';return;}
    if(window.PasswordCredential){
      try{const cred=new PasswordCredential({id:login,password,name});await navigator.credentials.store(cred);}catch(_){}
    }
    _sessionIsAdmin=!!d.is_admin;
    document.getElementById('loginScreen').style.display='none';
    document.querySelector('.app').style.display='';
    reloadAllData();
    loadProfiles();
  }catch(e){
    errEl.textContent='Erreur de connexion — réessaie.';
  }finally{
    btn.disabled=false;btn.textContent='Créer le compte';
  }
}

// ── Profile system ─────────────────────────────────────────────────────────
let _profiles=[], _activeProfileId=null, _pmSelected=null, _sessionIsAdmin=false, _switchGen=0;

async function loadProfiles(){
  const d=await fetch('/api/profiles').then(r=>r.json()).catch(()=>null);
  if(!d)return;
  _profiles=d.profiles||[];
  _activeProfileId=d.active_id||null;
  _renderSbProfile();
  _renderPmList();
}

function _profileAvatar(name){return(name||'?')[0].toUpperCase();}

function _renderSbProfile(){
  const prof=_profiles.find(p=>p.id===_activeProfileId)||_profiles[0];
  if(!prof)return;
  const isAdmin=_sessionIsAdmin;
  const hasMany=_profiles.length>1;
  document.getElementById('sbProfileAvatar').textContent=_profileAvatar(prof.name);
  document.getElementById('sbProfileName').textContent=prof.name;
  // Switcher visible dès qu'il y a plusieurs profils OU qu'on est admin
  const btn=document.getElementById('sbProfileBtn');
  if(isAdmin||hasMany){
    btn.onclick=toggleProfileMenu;btn.style.cursor='pointer';
    btn.querySelector('svg').style.display='';
  } else {
    btn.onclick=null;btn.style.cursor='default';
    btn.querySelector('svg').style.display='none';
  }
  // Liste des profils — visible pour tous (admin ou non)
  const list=document.getElementById('sbProfileList');
  list.innerHTML=_profiles.map(p=>`
    <button class="sb-profile-menu-item${p.id===_activeProfileId?' active-prof':''}" onclick="switchProfile('${p.id}')">
      <span style="width:18px;height:18px;border-radius:5px;background:linear-gradient(135deg,#7c3aed,#4f46e5);display:inline-flex;align-items:center;justify-content:center;font-size:.6rem;font-weight:800;color:#fff;flex-shrink:0">${_profileAvatar(p.name)}</span>
      <span style="flex:1;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.name}</span>
      ${p.pin_set?'<span style="font-size:.7rem;opacity:.6">🔒</span>':''}
      ${p.id===_activeProfileId?'<span style="width:6px;height:6px;border-radius:50%;background:var(--green);flex-shrink:0"></span>':''}
    </button>`).join('');
  // Boutons de gestion : visibles pour tous
  const manageBtn=document.querySelector('.sb-profile-menu-item[onclick="openProfileManager()"]');
  const newBtn=document.querySelector('.sb-profile-menu-item[onclick="newProfileQuick()"]');
  const sep=document.querySelector('.sb-profile-menu-sep');
  [manageBtn,newBtn,sep].forEach(el=>{if(el)el.style.display='';});
  // Settings : admin seulement
  const settingsBtn=document.querySelector('.sb-item[data-page="settings"]');
  if(settingsBtn) settingsBtn.style.display=isAdmin?'':'none';
}

function toggleProfileMenu(){
  const m=document.getElementById('sbProfileMenu');
  m.style.display=m.style.display==='none'?'block':'none';
}
document.addEventListener('click',e=>{
  const w=document.getElementById('sbProfileWrap');
  if(w&&!w.contains(e.target)){document.getElementById('sbProfileMenu').style.display='none';}
});

function _skeletonItems(n=4){
  return Array.from({length:n},()=>`
    <div class="sitem" style="pointer-events:none">
      <div class="skel" style="width:64px;height:84px;border-radius:9px;flex-shrink:0"></div>
      <div class="sinfo" style="gap:7px;display:flex;flex-direction:column;justify-content:center">
        <div class="skel" style="height:13px;width:80%;border-radius:4px"></div>
        <div class="skel" style="height:11px;width:55%;border-radius:4px"></div>
        <div class="skel" style="height:10px;width:65%;border-radius:4px;margin-top:4px"></div>
      </div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex-shrink:0">
        <div class="skel" style="height:20px;width:52px;border-radius:5px"></div>
      </div>
    </div>`).join('');
}
async function reloadAllData(gen){
  if(gen===undefined)gen=_switchGen;
  accounts=[];
  document.getElementById('slist').innerHTML=_skeletonItems(4);
  const snapEl=document.getElementById('snapSlist');
  if(snapEl)snapEl.innerHTML=_skeletonItems(3);

  // Tout en parallèle — chaque fonction est indépendante
  await Promise.all([
    loadAccounts(),
    loadScheduled(),
    loadSnapScheduled(),
    loadPlaylists(),
    loadSnapAccounts(),
    loadIgAccounts(),
    loadFbAccounts(),
    loadSplList(),
    loadSplPool(),
    loadRevenue(),
  ]);
  if(gen!==_switchGen)return; // un switch plus récent a pris la main, on abandonne
  // Actualiser la page courante une fois toutes les données chargées
  if(currentPage==='stats') loadStats();
  if(currentPage==='accounts') _renderAllSocialAccounts();
  if(currentPage==='instagram') loadIgScheduled();
  if(currentPage==='facebook') loadFbScheduled();
  // Apply plan restrictions after data is loaded
  const _activeProfObj=(_profiles||[]).find(p=>p.id===_activeProfileId);
  _applyPlanRestrictions(_activeProfObj?_activeProfObj.plan:null);
}

// ── Plan restrictions ──────────────────────────────────────────────────────
const _PLAN_LOCKED_MAP={
  starter:   new Set(['instagram','facebook','stats','revenue']),
  pro:       new Set(),
  business:  new Set(),
};
let _lockedPages=new Set(['instagram','facebook','stats','revenue','snapchat','playlists','schedule','accounts','docs']);
function _applyPlanRestrictions(plan){
  if(_sessionIsAdmin){
    _lockedPages=new Set();
    document.getElementById('planPaywall').style.display='none';
    document.querySelectorAll('.sb-item.plan-locked').forEach(b=>b.classList.remove('plan-locked'));
    return;
  }
  const hasPlan=plan&&plan!=='';
  _lockedPages=hasPlan?(_PLAN_LOCKED_MAP[plan]||new Set()):new Set(['instagram','facebook','stats','revenue','snapchat','playlists','schedule','accounts','docs']);
  document.getElementById('planPaywall').style.display=hasPlan?'none':'flex';
  document.querySelectorAll('.sb-item[data-page]').forEach(btn=>{
    btn.classList.toggle('plan-locked',_lockedPages.has(btn.dataset.page));
  });
  if(hasPlan&&_lockedPages.has(currentPage)){
    const first=['schedule','snapchat','playlists'].find(p=>!_lockedPages.has(p));
    if(first)setTimeout(()=>navigateTo(first),50);
  }
}

function _clearForSwitch(){
  accounts=[];snapAccounts=[];igAccounts=[];fbAccounts=[];
  const skel4=_skeletonItems(4), skel3=_skeletonItems(3);
  const loading='<div class="no-acc-warn">Chargement…</div>';
  const _c=(id,h)=>{const e=document.getElementById(id);if(e)e.innerHTML=h;};
  _c('slist',skel4);
  _c('snapSlist',skel3);
  _c('igRpList',skel3);
  _c('fbRpList',skel3);
  _c('splList',skel3);
  _c('revList',skel3);
  _c('tgMediaCol',skel3);
  _c('snapMediaCol',skel3);
  _c('igMediaCol',skel3);
  _c('splPoolInfo','📂 Chargement du pool...');
  // Vider les checkboxes de comptes (snap/ig/fb) pour qu'ils s'affichent à jour
  _c('snapAccChecks',loading);
  _c('igAccChecks',loading);
  _c('fbAccChecks',loading);
  // Vider la page Comptes
  _c('snapAccListPage',loading);
  _c('igAccListPage',loading);
  _c('fbAccListPage',loading);
}
async function switchProfile(pid){
  document.getElementById('sbProfileMenu').style.display='none';
  if(pid===_activeProfileId)return;
  _clearForSwitch();
  const prof=_profiles.find(p=>p.id===pid);
  if(prof&&prof.pin_set){
    _pinTarget=pid; _pinCallback=_doSwitchProfile; _pinEntry=''; _pinLabel=prof.name;
    _openPinModal(); return;
  }
  await _doSwitchProfile(pid,'');
}
async function _doSwitchProfile(pid,pin){
  const myGen=++_switchGen;
  const r=await fetch(`/api/profiles/${pid}/activate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin})}).then(x=>x.json()).catch(()=>({ok:false}));
  if(myGen!==_switchGen)return; // un autre switch a démarré entre-temps
  if(!r.ok){_pinError();loadScheduled();return;}
  _closePinModal();
  _activeProfileId=pid;
  _renderSbProfile();
  // Afficher l'indicateur de chargement dans la sidebar
  const sbName=document.getElementById('sbProfileName');
  if(sbName){sbName.textContent='Chargement…';sbName.style.opacity='.5';}
  await reloadAllData(myGen);
  if(myGen!==_switchGen)return; // dépassé par un switch plus récent
  if(sbName){sbName.style.opacity='';}
  const prof=_profiles.find(p=>p.id===pid);
  if(sbName&&prof)sbName.textContent=prof.name;
}

function newProfileQuick(){
  document.getElementById('sbProfileMenu').style.display='none';
  openProfileManager();
  setTimeout(pmNewProfile,100);
}

function openProfileManager(){
  document.getElementById('pmModal').classList.add('open');
  _renderPmList();
}
function closeProfileManager(){
  document.getElementById('pmModal').classList.remove('open');
  _pmSelected=null;
}

function _renderPmList(){
  const el=document.getElementById('pmList');
  el.innerHTML=_profiles.map(p=>`
    <div class="pm-list-item${p.id===_pmSelected?' selected':''}" onclick="pmSelectProfile('${p.id}')">
      <div class="pm-li-av">${_profileAvatar(p.name)}</div>
      <div class="pm-li-name">${p.name}</div>
      ${p.id===_activeProfileId?'<div class="pm-li-active"></div>':''}
    </div>`).join('')+'<button class="pm-new-btn" onclick="pmNewProfile()">＋ Nouveau profil</button>';
}

function pmSelectProfile(pid){
  _pmSelected=pid;
  _renderPmList();
  const prof=_profiles.find(p=>p.id===pid);
  if(!prof)return;
  document.getElementById('pmForm').innerHTML=`
    <h3>Identité</h3>
    <div class="pm-field"><label>Nom du profil</label><input id="pmName" value="${esc(prof.name)}"></div>
    <h3 style="margin-top:16px">OneUp</h3>
    <div class="pm-field"><label>Clef API OneUp</label>
      <div style="display:flex;gap:6px">
        <input id="pmOneup" value="${esc(prof.oneup_api_key||'')}" style="flex:1">
        <button class="btn btn-xs" onclick="navigator.clipboard.readText().then(t=>{document.getElementById('pmOneup').value=t.trim();toast('✅ Clef collée','ok');}).catch(()=>alert('Autorise le presse-papiers dans le navigateur.'))" title="Coller depuis le presse-papiers" style="white-space:nowrap">📋 Coller</button>
        <button class="btn btn-xs" onclick="pmImportSnap()" title="Pré-remplir avec les comptes du profil actif" style="white-space:nowrap">🔄 Importer comptes actifs</button>
      </div>
    </div>
    <div class="pm-field"><label>Category ID Snap</label><input id="pmCatSnap" value="${esc(prof.category_id_snap||'')}"></div>
    <h3 style="margin-top:16px">Cloudinary</h3>
    <div class="pm-field"><label>Cloud name</label><input id="pmCloudName" value="${esc(prof.cloudinary_cloud_name||'')}"></div>
    <div class="pm-field"><label>API Key</label><input id="pmCloudKey" value="${esc(prof.cloudinary_api_key||'')}"></div>
    <div class="pm-field"><label>API Secret</label><input id="pmCloudSecret" type="password" value="${esc(prof.cloudinary_api_secret||'')}"></div>
    <h3 style="margin-top:16px">Comptes Snapchat
      <button class="btn btn-xs" onclick="pmAddSnap()" style="margin-left:6px">+ Manuel</button>
    </h3>
    <div id="pmSnapImportStatus" style="font-size:.68rem;color:var(--t3);margin-bottom:6px"></div>
    <div class="pm-snap-list" id="pmSnapList">${(prof.snap_accounts||[]).map((a,i)=>pmSnapRow(i,a.username,a.id)).join('')}</div>
    <h3 style="margin-top:16px">Comptes Instagram
      <button class="btn btn-xs" onclick="pmImportIg()" style="margin-left:6px">🔄 Importer depuis OneUp</button>
      <button class="btn btn-xs" onclick="pmAddIg()" style="margin-left:4px">+ Manuel</button>
    </h3>
    <div id="pmIgImportStatus" style="font-size:.68rem;color:var(--t3);margin-bottom:6px"></div>
    <div class="pm-snap-list" id="pmIgList">${(prof.instagram_accounts||[]).map((a,i)=>pmSnapRow(i,a.username,a.id,'ig')).join('')}</div>
    <div class="pm-field"><label>Category ID Instagram (OneUp)</label><input id="pmCatIg" value="${esc(prof.category_id_instagram||'')}"></div>
    <h3 style="margin-top:16px">Comptes Facebook
      <button class="btn btn-xs" onclick="pmImportFb()" style="margin-left:6px">🔄 Importer depuis OneUp</button>
      <button class="btn btn-xs" onclick="pmAddFb()" style="margin-left:4px">+ Manuel</button>
    </h3>
    <div id="pmFbImportStatus" style="font-size:.68rem;color:var(--t3);margin-bottom:6px"></div>
    <div class="pm-snap-list" id="pmFbList">${(prof.facebook_accounts||[]).map((a,i)=>pmSnapRow(i,a.username,a.id,'fb')).join('')}</div>
    <div class="pm-field"><label>Category ID Facebook (OneUp)</label><input id="pmCatFb" value="${esc(prof.category_id_facebook||'')}"></div>
    <h3 style="margin-top:16px">Dossier Spotlight (local)</h3>
    <div class="pm-field"><label>Chemin dossier pool</label><input id="pmSpotDir" value="${esc(prof.spotlight_pool_dir||'')}"></div>
    <h3 style="margin-top:16px">💳 Forfait</h3>
    <div class="pm-field">
      <label>Plan actif</label>
      <select id="pmPlan" style="background:var(--c1);border:1px solid var(--b1);color:var(--t1);border-radius:var(--r2);padding:8px 10px;font-size:.83rem;width:100%">
        <option value="" ${!prof.plan?'selected':''}>🔒 Aucun forfait (accès bloqué)</option>
        <option value="starter" ${prof.plan==='starter'?'selected':''}>⚡ Starter — 15€/mois (10 comptes)</option>
        <option value="pro" ${prof.plan==='pro'?'selected':''}>🚀 Pro — 39€/mois (25 comptes)</option>
        <option value="business" ${prof.plan==='business'?'selected':''}>🏢 Business — 239€/mois (illimité)</option>
      </select>
    </div>
    <h3 style="margin-top:16px">🔑 Accès client (Login)</h3>
    <div style="background:var(--c1);border:1px solid var(--b1);border-radius:8px;padding:14px;margin-bottom:12px">
      <div style="font-size:.72rem;color:var(--t3);margin-bottom:10px">Ces identifiants permettent au client de se connecter à son espace. Sans mot de passe configuré, le profil est inaccessible.</div>
      <div class="pm-field">
        <label>Identifiant (login)</label>
        <input id="pmLogin" value="${esc(prof.login||prof.name.toLowerCase().replace(/\s+/g,'_'))}" placeholder="ex: louna" autocomplete="off">
      </div>
      <div class="pm-field">
        <label>Mot de passe ${prof.password_set?'<span style="color:var(--green);font-size:.65rem">✓ configuré</span>':'<span style="color:#f5c518;font-size:.65rem">⚠ non défini</span>'}</label>
        <input id="pmPassword" type="password" placeholder="${prof.password_set?'Laisser vide pour ne pas changer':'Définir un mot de passe'}" autocomplete="new-password">
      </div>
      <button class="btn btn-xs btn-primary" onclick="pmSaveCredentials('${pid}')" style="margin-top:4px">💾 Enregistrer les accès</button>
      <span id="pmCredStatus" style="font-size:.72rem;margin-left:8px;color:var(--green)"></span>
    </div>
    <h3 style="margin-top:4px">Sécurité — Code PIN (app interne)</h3>
    <div style="background:var(--c1);border:1px solid var(--b1);border-radius:8px;padding:10px 12px;margin-bottom:12px">
      <div style="font-size:.68rem;color:var(--t3);margin-bottom:8px">Le PIN protège le changement de profil dans l'app (optionnel)</div>
      ${prof.pin_set
        ? `<div style="display:flex;align-items:center;gap:10px">
             <span style="font-size:.8rem">🔒 PIN configuré</span>
             <button class="btn btn-xs" onclick="pmChangePinShow()" style="margin-left:auto">Modifier</button>
             <button class="btn btn-xs btn-danger" onclick="pmRemovePin('${pid}')">Supprimer</button>
           </div>`
        : `<div style="font-size:.72rem;color:var(--t3);margin-bottom:8px">Aucun PIN — changement de profil libre</div>
           <button class="btn btn-xs" onclick="pmChangePinShow()">🔒 Définir un code PIN</button>`
      }
      <div id="pmPinForm" style="display:none;margin-top:10px">
        <div class="pm-field" style="margin:0"><label>Nouveau code PIN (4 chiffres)</label>
          <div style="display:flex;gap:6px">
            <input id="pmPinInput" type="password" maxlength="4" placeholder="••••" style="flex:1;font-size:1.2rem;letter-spacing:.3em;text-align:center">
            <button class="btn btn-xs btn-primary" onclick="pmSavePin('${pid}')">Valider</button>
            <button class="btn btn-xs" onclick="document.getElementById('pmPinForm').style.display='none'">✕</button>
          </div>
        </div>
      </div>
    </div>
    <h3 style="margin-top:16px">Comptes Telegram</h3>
    <div id="pmTgList" style="margin-bottom:8px"><span style="font-size:.7rem;color:var(--t3)">Chargement…</span></div>
    ${pid===_activeProfileId
      ? `<button class="btn btn-xs" onclick="pmAddTg()" style="margin-bottom:12px">+ Connecter un compte Telegram</button>
         <div id="pmTgAddForm" style="display:none"></div>`
      : `<div style="font-size:.7rem;color:var(--t3);padding:6px 0;margin-bottom:12px">⚡ Active ce profil pour ajouter des comptes Telegram</div>`
    }
    <div class="pm-form-actions">
      <button class="btn btn-primary" onclick="pmSave('${pid}')">💾 Enregistrer</button>
      <button class="btn" onclick="pmActivate('${pid}')" style="${pid===_activeProfileId?'display:none':''}">⚡ Activer</button>
      <button class="btn btn-danger" onclick="pmDelete('${pid}')" style="margin-left:auto">🗑 Supprimer</button>
    </div>`;
  pmLoadTgAccounts(pid);
}

async function pmImportSnap(){
  const key=document.getElementById('pmOneup').value.trim();
  if(!key){alert('Entre la clef API OneUp d\'abord.');return;}
  const st=document.getElementById('pmSnapImportStatus');
  st.textContent='⏳ Import en cours…';
  const d=await fetch(`/api/oneup/snap-accounts?oneup_key=${encodeURIComponent(key)}`).then(r=>r.json()).catch(e=>({ok:false,error:String(e)}));
  if(!d.ok){st.style.color='#f87171';st.textContent='❌ '+(d.detail||d.error||'Erreur');return;}
  if(!d.accounts.length){st.style.color='var(--yellow)';st.textContent='⚠️ Aucun compte Snapchat configuré sur ce profil — ajoute-les manuellement';return;}
  const list=document.getElementById('pmSnapList');
  list.innerHTML='';
  d.accounts.forEach((a,i)=>list.insertAdjacentHTML('beforeend',pmSnapRow(i,a.username,a.id)));
  st.style.color='var(--green)';
  st.textContent=`✅ ${d.accounts.length} compte(s) importé(s) — clique Enregistrer pour sauvegarder`;
}

async function pmLoadTgAccounts(pid){
  const el=document.getElementById('pmTgList');
  if(!el)return;
  const accs=await fetch(`/api/profiles/${pid}/telegram-accounts`).then(r=>r.json()).catch(()=>[]);
  if(!accs.length){el.innerHTML='<span style="font-size:.7rem;color:var(--t3)">Aucun compte Telegram connecté</span>';return;}
  el.innerHTML=accs.map(a=>`
    <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--c1);border-radius:7px;margin-bottom:5px">
      <img src="/api/accounts/${a.id}/photo" style="width:26px;height:26px;border-radius:50%;object-fit:cover" onerror="this.style.display='none'">
      <span style="flex:1;font-size:.74rem;color:var(--t1)">${esc(a.name||a.phone||a.id)}</span>
      <span style="font-size:.63rem;color:var(--t3)">${esc(a.phone||'')}</span>
      <button class="btn btn-xs btn-danger" onclick="pmDeleteTg('${pid}','${a.id}')">✕</button>
    </div>`).join('');
}

async function pmDeleteTg(pid,accId){
  if(!confirm('Déconnecter et supprimer ce compte Telegram ?'))return;
  await fetch(`/api/profiles/${pid}/telegram-accounts/${accId}`,{method:'DELETE'});
  pmLoadTgAccounts(pid);
  if(pid===_activeProfileId&&typeof loadAccounts==='function')loadAccounts();
}

function pmAddTg(){
  document.getElementById('pmTgAddForm').style.display='block';
  document.getElementById('pmTgAddForm').innerHTML=`
    <div style="background:var(--c1);border:1px solid var(--b1);border-radius:8px;padding:12px;margin-bottom:10px">
      <div style="font-size:.72rem;font-weight:700;color:var(--t2);margin-bottom:8px">Connecter un compte Telegram</div>
      <div id="pmTgStep1">
        <div class="pm-field"><label>Numéro de téléphone (ex: +33612345678)</label>
          <div style="display:flex;gap:6px"><input id="pmTgPhone" placeholder="+33…" style="flex:1"><button class="btn btn-xs btn-primary" onclick="pmTgSendCode()">Envoyer le code</button></div>
        </div>
      </div>
      <div id="pmTgStep2" style="display:none">
        <div class="pm-field"><label>Code reçu par Telegram</label>
          <div style="display:flex;gap:6px"><input id="pmTgCode" placeholder="12345" style="flex:1"><button class="btn btn-xs btn-primary" onclick="pmTgVerify()">Vérifier</button></div>
        </div>
      </div>
      <div id="pmTgStep3" style="display:none">
        <div class="pm-field"><label>Mot de passe 2FA</label>
          <div style="display:flex;gap:6px"><input id="pmTg2fa" type="password" placeholder="mot de passe" style="flex:1"><button class="btn btn-xs btn-primary" onclick="pmTg2fa()">Valider</button></div>
        </div>
      </div>
      <div id="pmTgMsg" style="font-size:.7rem;margin-top:6px"></div>
    </div>`;
}

let _pmTgAccId=null;
async function pmTgSendCode(){
  const phone=document.getElementById('pmTgPhone').value.trim();
  if(!phone)return;
  document.getElementById('pmTgMsg').textContent='⏳ Envoi du code…';
  const d=await fetch('/api/accounts/send-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone})}).then(r=>r.json()).catch(e=>({ok:false,error:String(e)}));
  if(!d.ok){document.getElementById('pmTgMsg').textContent='❌ '+(d.detail||d.error);return;}
  _pmTgAccId=d.acc_id;
  document.getElementById('pmTgStep2').style.display='block';
  document.getElementById('pmTgMsg').textContent='✅ Code envoyé sur Telegram';
}
async function pmTgVerify(){
  const code=document.getElementById('pmTgCode').value.trim();
  document.getElementById('pmTgMsg').textContent='⏳ Vérification…';
  const d=await fetch('/api/accounts/verify-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({acc_id:_pmTgAccId,code})}).then(r=>r.json()).catch(e=>({ok:false,error:String(e)}));
  if(d.need_2fa){document.getElementById('pmTgStep3').style.display='block';document.getElementById('pmTgMsg').textContent='🔐 2FA requis';return;}
  if(!d.ok){document.getElementById('pmTgMsg').textContent='❌ '+(d.detail||d.error);return;}
  document.getElementById('pmTgAddForm').style.display='none';
  document.getElementById('pmTgMsg').textContent='';
  pmLoadTgAccounts(_pmSelected);
  if(typeof loadAccounts==='function')loadAccounts();
}
async function pmTg2fa(){
  const pw=document.getElementById('pmTg2fa').value;
  document.getElementById('pmTgMsg').textContent='⏳ Vérification 2FA…';
  const d=await fetch('/api/accounts/verify-2fa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({acc_id:_pmTgAccId,password:pw})}).then(r=>r.json()).catch(e=>({ok:false,error:String(e)}));
  if(!d.ok){document.getElementById('pmTgMsg').textContent='❌ '+(d.detail||d.error);return;}
  document.getElementById('pmTgAddForm').style.display='none';
  pmLoadTgAccounts(_pmSelected);
  if(typeof loadAccounts==='function')loadAccounts();
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');}
function pmSnapRow(i,username='',id=''){
  return `<div class="pm-snap-row" data-snap="${i}">
    <input placeholder="@username" value="${esc(username)}" oninput="this.setAttribute('value',this.value)">
    <input placeholder="OneUp ID (uuid)" value="${esc(id)}" oninput="this.setAttribute('value',this.value)">
    <button class="btn btn-xs btn-danger" onclick="this.parentNode.remove()">✕</button>
  </div>`;
}
function pmAddSnap(){
  const list=document.getElementById('pmSnapList');
  const i=list.querySelectorAll('.pm-snap-row').length;
  list.insertAdjacentHTML('beforeend',pmSnapRow(i));
}
function pmAddIg(){
  const list=document.getElementById('pmIgList');
  const i=list.querySelectorAll('.pm-snap-row').length;
  list.insertAdjacentHTML('beforeend',pmSnapRow(i,'','','ig'));
}
function pmAddFb(){
  const list=document.getElementById('pmFbList');
  const i=list.querySelectorAll('.pm-snap-row').length;
  list.insertAdjacentHTML('beforeend',pmSnapRow(i,'','','fb'));
}
async function pmImportFb(){
  const key=document.getElementById('pmOneup').value.trim();
  if(!key){alert('Entre la clef API OneUp d\'abord.');return;}
  const st=document.getElementById('pmFbImportStatus');
  st.textContent='⏳ Import en cours…';
  const d=await fetch(`/api/oneup/fb-accounts?oneup_key=${encodeURIComponent(key)}`).then(r=>r.json()).catch(e=>({ok:false,error:String(e)}));
  if(!d.ok){st.style.color='#f87171';st.textContent='❌ '+(d.detail||d.error||'Erreur');return;}
  if(!d.accounts.length){st.style.color='var(--yellow)';st.textContent='⚠️ Aucun compte Facebook trouvé — ajoute-les manuellement';return;}
  const list=document.getElementById('pmFbList');
  list.innerHTML='';
  d.accounts.forEach((a,i)=>list.insertAdjacentHTML('beforeend',pmSnapRow(i,a.username,a.id,'fb')));
  st.style.color='var(--green)';
  st.textContent=`✅ ${d.accounts.length} compte(s) Facebook importé(s) — clique Enregistrer pour sauvegarder`;
}
async function pmImportIg(){
  const key=document.getElementById('pmOneup').value.trim();
  if(!key){alert('Entre la clef API OneUp d\'abord.');return;}
  const st=document.getElementById('pmIgImportStatus');
  st.textContent='⏳ Import en cours…';
  const d=await fetch(`/api/oneup/ig-accounts?oneup_key=${encodeURIComponent(key)}`).then(r=>r.json()).catch(e=>({ok:false,error:String(e)}));
  if(!d.ok){st.style.color='#f87171';st.textContent='❌ '+(d.detail||d.error||'Erreur');return;}
  if(!d.accounts.length){st.style.color='var(--yellow)';st.textContent='⚠️ Aucun compte Instagram trouvé — ajoute-les manuellement';return;}
  const list=document.getElementById('pmIgList');
  list.innerHTML='';
  d.accounts.forEach((a,i)=>list.insertAdjacentHTML('beforeend',pmSnapRow(i,a.username,a.id,'ig')));
  st.style.color='var(--green)';
  st.textContent=`✅ ${d.accounts.length} compte(s) Instagram importé(s) — clique Enregistrer pour sauvegarder`;
}

async function pmSave(pid){
  const snaps=[...document.getElementById('pmSnapList').querySelectorAll('.pm-snap-row')].map(row=>{
    const ins=row.querySelectorAll('input');
    return {username:ins[0].value.replace('@','').trim(),id:ins[1].value.trim()};
  }).filter(a=>a.username&&a.id);
  const igList=document.getElementById('pmIgList');
  const igs=igList?[...igList.querySelectorAll('.pm-snap-row')].map(row=>{
    const ins=row.querySelectorAll('input');
    return {username:ins[0].value.replace('@','').trim(),id:ins[1].value.trim()};
  }).filter(a=>a.username&&a.id):[];
  const fbList=document.getElementById('pmFbList');
  const fbs=fbList?[...fbList.querySelectorAll('.pm-snap-row')].map(row=>{
    const ins=row.querySelectorAll('input');
    return {username:ins[0].value.replace('@','').trim(),id:ins[1].value.trim()};
  }).filter(a=>a.username&&a.id):[];
  const catIgEl=document.getElementById('pmCatIg');
  const catFbEl=document.getElementById('pmCatFb');
  const body={
    name:           document.getElementById('pmName').value.trim(),
    oneup_api_key:  document.getElementById('pmOneup').value.trim(),
    category_id_snap:document.getElementById('pmCatSnap').value.trim(),
    category_id_instagram:catIgEl?catIgEl.value.trim():'',
    category_id_facebook:catFbEl?catFbEl.value.trim():'',
    cloudinary_cloud_name:document.getElementById('pmCloudName').value.trim(),
    cloudinary_api_key:   document.getElementById('pmCloudKey').value.trim(),
    cloudinary_api_secret:document.getElementById('pmCloudSecret').value.trim(),
    snap_accounts:  snaps,
    instagram_accounts: igs,
    facebook_accounts: fbs,
    spotlight_pool_dir:document.getElementById('pmSpotDir').value.trim(),
    plan: document.getElementById('pmPlan')?document.getElementById('pmPlan').value||null:undefined,
  };
  const r=await fetch(pid?`/api/profiles/${pid}`:'/api/profiles',{method:pid?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());
  await loadProfiles();
  _pmSelected=r.id||pid;
  _renderPmList();
  pmSelectProfile(_pmSelected);
}

async function pmNewProfile(){
  _pmSelected=null;
  _renderPmList();
  document.getElementById('pmForm').innerHTML=`
    <h3>Nouveau profil</h3>
    <div class="pm-field"><label>Nom du profil</label><input id="pmName" value="Nouveau profil"></div>
    <h3 style="margin-top:16px">OneUp</h3>
    <div class="pm-field"><label>Clef API OneUp</label>
      <div style="display:flex;gap:6px">
        <input id="pmOneup" value="" style="flex:1">
        <button class="btn btn-xs" onclick="navigator.clipboard.readText().then(t=>{document.getElementById('pmOneup').value=t.trim();toast('✅ Clef collée','ok');}).catch(()=>alert('Autorise le presse-papiers dans le navigateur.'))" title="Coller depuis le presse-papiers" style="white-space:nowrap">📋 Coller</button>
      </div>
    </div>
    <div class="pm-field"><label>Category ID Snap</label><input id="pmCatSnap" value=""></div>
    <h3 style="margin-top:16px">Cloudinary</h3>
    <div class="pm-field"><label>Cloud name</label><input id="pmCloudName" value=""></div>
    <div class="pm-field"><label>API Key</label><input id="pmCloudKey" value=""></div>
    <div class="pm-field"><label>API Secret</label><input id="pmCloudSecret" type="password" value=""></div>
    <h3 style="margin-top:16px">Comptes Snapchat <button class="btn btn-xs" onclick="pmAddSnap()" style="margin-left:6px">+ Ajouter</button></h3>
    <div class="pm-snap-list" id="pmSnapList"></div>
    <h3 style="margin-top:16px">Dossier Spotlight (local)</h3>
    <div class="pm-field"><label>Chemin dossier pool</label><input id="pmSpotDir" value=""></div>
    <div class="pm-form-actions">
      <button class="btn btn-primary" onclick="pmSave(null)">💾 Créer le profil</button>
    </div>`;
}

function showComingSoon(name){
  const cfg={
    'Instagram':{emoji:'📸',gradient:'linear-gradient(135deg,#833ab4,#fd1d1d,#fcb045)'},
    'Threads':  {emoji:'🧵',gradient:'linear-gradient(135deg,#000,#333,#555)'},
  };
  const c=cfg[name]||{emoji:'🚀',gradient:'linear-gradient(135deg,var(--purple),#a78bfa)'};
  const titleEl=document.getElementById('comingSoonTitle');
  titleEl.textContent=name;
  titleEl.style.background=c.gradient;
  titleEl.style.webkitBackgroundClip='text';
  titleEl.style.webkitTextFillColor='transparent';
  titleEl.style.backgroundClip='text';
  document.getElementById('comingSoonEmoji').textContent=c.emoji;
  document.getElementById('comingSoonModal').classList.add('open');
}

// ── PIN modal logic ──────────────────────────────────────────────────────────
let _pinTarget=null, _pinCallback=null, _pinEntry='', _pinLabel='';
function _openPinModal(){
  document.getElementById('pinModal').classList.add('open');
  document.getElementById('pinModalLabel').textContent=`Code PIN pour « ${_pinLabel} »`;
  _pinEntry=''; _updatePinDots(false);
}
function _closePinModal(){document.getElementById('pinModal').classList.remove('open');}
function pinCancel(){_closePinModal();_pinTarget=null;_pinCallback=null;_pinEntry='';}
function _updatePinDots(error=false){
  for(let i=0;i<4;i++){
    const d=document.getElementById('pd'+i);
    d.classList.toggle('filled',i<_pinEntry.length&&!error);
    d.classList.toggle('error',error&&i<_pinEntry.length);
  }
}
function _pinError(){
  _updatePinDots(true);
  setTimeout(()=>{_pinEntry='';_updatePinDots(false);},700);
}
function pinKey(k){
  if(!k){_pinEntry=_pinEntry.slice(0,-1);_updatePinDots();return;}
  if(_pinEntry.length>=4)return;
  _pinEntry+=k;
  _updatePinDots();
  if(_pinEntry.length===4&&_pinCallback&&_pinTarget){
    const cb=_pinCallback, pid=_pinTarget, pin=_pinEntry;
    cb(pid,pin);
  }
}
// ── PIN management in profile form ───────────────────────────────────────────
async function pmSaveCredentials(pid){
  const login=document.getElementById('pmLogin').value.trim().toLowerCase();
  const password=document.getElementById('pmPassword').value;
  const st=document.getElementById('pmCredStatus');
  if(!login){alert('L\'identifiant ne peut pas être vide.');return;}
  const body={login};
  if(password) body.password=password;
  const r=await fetch(`/api/profiles/${pid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(x=>x.json()).catch(()=>null);
  if(r){
    st.textContent='✓ Accès enregistrés';
    document.getElementById('pmPassword').value='';
    setTimeout(()=>st.textContent='',3000);
    await loadProfiles();
  } else { st.style.color='#f87171';st.textContent='Erreur';setTimeout(()=>{st.textContent='';st.style.color='var(--green)';},3000);}
}
function pmChangePinShow(){document.getElementById('pmPinForm').style.display='block';}
async function pmSavePin(pid){
  const pin=document.getElementById('pmPinInput').value.trim();
  if(!/^\d{4}$/.test(pin)){alert('Le code PIN doit être composé de 4 chiffres.');return;}
  await fetch(`/api/profiles/${pid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin})}).then(r=>r.json());
  await loadProfiles();
  pmSelectProfile(pid);
}
async function pmRemovePin(pid){
  if(!confirm('Supprimer le code PIN de ce profil ?'))return;
  await fetch(`/api/profiles/${pid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:''})}).then(r=>r.json());
  await loadProfiles();
  pmSelectProfile(pid);
}
// ─────────────────────────────────────────────────────────────────────────────

async function pmActivate(pid){
  const prof=_profiles.find(p=>p.id===pid);
  if(prof&&prof.pin_set){
    _pinTarget=pid; _pinCallback=_doPmActivate; _pinEntry=''; _pinLabel=prof.name;
    _openPinModal(); return;
  }
  await _doPmActivate(pid,'');
}
async function _doPmActivate(pid,pin){
  const r=await fetch(`/api/profiles/${pid}/activate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin})}).then(x=>x.json()).catch(()=>({ok:false}));
  if(!r.ok){_pinError();return;}
  _closePinModal();
  _activeProfileId=pid;
  await loadProfiles();
  _pmSelected=pid;
  _renderPmList();
  pmSelectProfile(pid);
  reloadAllData();
}

async function pmDelete(pid){
  if(!confirm('Supprimer ce profil ? Les données ne seront pas effacées.'))return;
  await fetch(`/api/profiles/${pid}`,{method:'DELETE'});
  await loadProfiles();
  _pmSelected=null;
  _renderPmList();
  document.getElementById('pmForm').innerHTML='<div style="color:var(--t3);font-size:.8rem;text-align:center;margin-top:40px">← Sélectionne un profil</div>';
}

// ── Navigation sidebar ──────────────────────────────────────────────────────
const pages={schedule:'Telegram',playlists:'Médias',stats:'Statistiques',snapchat:'Snapchat',instagram:'Instagram',facebook:'Facebook',revenue:'Revenus',accounts:'Comptes',docs:'Documentation'};
function showDoc(id,btn){
  document.querySelectorAll('.doc-section').forEach(s=>s.style.display='none');
  document.querySelectorAll('.doc-nav-item').forEach(b=>b.classList.remove('active'));
  const sec=document.getElementById('doc-'+id);
  if(sec)sec.style.display='';
  if(btn)btn.classList.add('active');
  const dc=document.getElementById('docContent');
  if(dc)dc.scrollTop=0;
}
let currentPage='schedule';
function navigateTo(page){
  if(page==='docs'){switchToDocs();return;}
  const btn=document.querySelector(`.sb-item[data-page="${page}"]`);if(btn)btn.click();
}
function switchToDocs(){
  document.querySelectorAll('.sb-item').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  currentPage='docs';
  document.getElementById('page-docs').classList.add('active');
  document.getElementById('topTitle').textContent='Documentation';
  document.getElementById('rightPanel').style.display='none';
  ['btnClone','btnSelMode','btnCloneRP','btnRpRefresh','btnSnapDeleteAll'].forEach(id=>{const e=document.getElementById(id);if(e)e.style.display='none';});
}
document.querySelectorAll('.sb-item[data-page]').forEach(btn=>{
  btn.addEventListener('click',()=>{
    if(_lockedPages&&_lockedPages.has(btn.dataset.page)){toast('🔒 Non inclus dans ton forfait — contacte l\'administrateur','warn');return;}
    document.querySelectorAll('.sb-item').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    btn.classList.add('active');
    currentPage=btn.dataset.page;
    document.getElementById('page-'+currentPage).classList.add('active');
    document.getElementById('topTitle').textContent=pages[currentPage]||'';
    const isSchedule=currentPage==='schedule';
    const isSnap=currentPage==='snapchat';
    const isIg=currentPage==='instagram';
    const isFb=currentPage==='facebook';
    document.getElementById('btnClone').style.display=isSchedule?'':'none';
    document.getElementById('rightPanel').style.display=(isSchedule||isSnap||isIg||isFb)?'':'none';
    document.getElementById('btnSnapDeleteAll').style.display=isSnap?'':'none';
    document.getElementById('btnSelMode').style.display=isSchedule?'':'none';
    document.getElementById('btnCloneRP').style.display=isSchedule?'':'none';
    document.getElementById('btnRpRefresh').style.display=(isIg||isFb)?'':'none';
    if(isSchedule){
      document.getElementById('rpTitle').textContent='📱 Telegram';
      document.getElementById('slist').style.display='';
      document.getElementById('splRpList').style.display='none';
      document.getElementById('igRpList').style.display='none';
      document.getElementById('fbRpList').style.display='none';
      document.getElementById('rpSchedTabs').style.display='grid';
      loadScheduled();
    } else if(isSnap){
      document.getElementById('rpTitle').textContent='👻 Snapchat';
      document.getElementById('slist').style.display='';
      document.getElementById('igRpList').style.display='none';
      document.getElementById('fbRpList').style.display='none';
      if(!snapAccounts.length)loadSnapAccounts().then(()=>loadSnapScheduled());else loadSnapScheduled();
      _splRestoreFolders();
    } else if(isIg){
      document.getElementById('rpTitle').textContent='📸 Instagram';
      document.getElementById('slist').style.display='none';
      document.getElementById('splRpList').style.display='none';
      document.getElementById('igRpList').style.display='';
      document.getElementById('fbRpList').style.display='none';
      document.getElementById('rpSchedTabs').style.display='grid';
      document.getElementById('rpSplTabs').style.display='none';
      document.getElementById('btnSplRpRefresh').style.display='none';
      if(!igAccounts.length) loadIgAccounts();
      loadIgScheduled();
    } else if(isFb){
      document.getElementById('rpTitle').textContent='📘 Facebook';
      document.getElementById('slist').style.display='none';
      document.getElementById('splRpList').style.display='none';
      document.getElementById('igRpList').style.display='none';
      document.getElementById('fbRpList').style.display='';
      document.getElementById('rpSchedTabs').style.display='grid';
      document.getElementById('rpSplTabs').style.display='none';
      document.getElementById('btnSplRpRefresh').style.display='none';
      if(!fbAccounts.length) loadFbAccounts();
      loadFbScheduled();
    } else if(currentPage==='stats'){
      loadStats();
    } else if(currentPage==='revenue'){
      loadRevenue();
    } else if(currentPage==='playlists'){
      loadPlaylists();
    } else if(currentPage==='accounts'){
      _renderAllSocialAccounts();
      Promise.all([
        snapAccounts.length?Promise.resolve():loadSnapAccounts(),
        igAccounts.length?Promise.resolve():loadIgAccounts(),
        fbAccounts.length?Promise.resolve():loadFbAccounts(),
      ]).then(_renderAllSocialAccounts);
    }
  });
});

// ── Accounts ──────────────────────────────────────────────────────────────
let accounts=[];
async function loadAccounts(){
  const r=await fetch('/api/accounts');accounts=await r.json();
  renderAccList();renderAccChecks();
  const _acsProf=(_profiles||[]).find(p=>p.id===_activeProfileId);
  if(_acsProf)document.getElementById('acsOneupKey').value=_acsProf.oneup_api_key||'';
  const n=accounts.filter(a=>a.connected).length;
  const b=document.getElementById('badgeAccounts');
  b.textContent=accounts.length;b.style.display='none';
  document.getElementById('mAccounts').textContent=n;
}
// ── Reconnexion Telegram ────────────────────────────────────────────────────
let _reconAccId=null, _reconPhone='';
function openReconModal(accId, phone, name){
  _reconAccId=accId; _reconPhone=phone;
  document.getElementById('reconTitle').textContent='🔄 Reconnecter le compte';
  document.getElementById('reconPhone').textContent=(name||phone)+' — '+phone;
  document.getElementById('reconMsg').textContent='';
  document.getElementById('reconStep1').style.display='';
  document.getElementById('reconStep2').style.display='none';
  document.getElementById('reconStep3').style.display='none';
  document.getElementById('reconCodeInp').value='';
  document.getElementById('recon2faInp').value='';
  document.getElementById('reconnectModal').classList.add('open');
}
function closeReconModal(){
  document.getElementById('reconnectModal').classList.remove('open');
  _reconAccId=null;
}
async function reconSendCode(){
  const btn=document.getElementById('reconBtnSend');
  btn.disabled=true; btn.textContent='⏳ Envoi…';
  document.getElementById('reconMsg').textContent='';
  const d=await fetch('/api/accounts/send-code',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({phone:_reconPhone})}).then(r=>r.json()).catch(e=>({ok:false,error:String(e)}));
  btn.disabled=false; btn.textContent='📨 Envoyer le code';
  if(!d.ok){document.getElementById('reconMsg').textContent='❌ '+(d.detail||d.error);return;}
  _reconAccId=d.acc_id;
  document.getElementById('reconStep1').style.display='none';
  document.getElementById('reconStep2').style.display='';
  document.getElementById('reconMsg').textContent='✅ Code envoyé !';
  setTimeout(()=>document.getElementById('reconCodeInp').focus(),50);
}
async function reconVerify(){
  const code=document.getElementById('reconCodeInp').value.trim();
  if(!code)return;
  document.getElementById('reconMsg').textContent='⏳ Vérification…';
  const d=await fetch('/api/accounts/verify-code',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({acc_id:_reconAccId,code})}).then(r=>r.json()).catch(e=>({ok:false,error:String(e)}));
  if(d.need_2fa){
    document.getElementById('reconStep2').style.display='none';
    document.getElementById('reconStep3').style.display='';
    document.getElementById('reconMsg').textContent='🔐 Entre ton mot de passe 2FA';
    setTimeout(()=>document.getElementById('recon2faInp').focus(),50);
    return;
  }
  if(!d.ok){document.getElementById('reconMsg').textContent='❌ '+(d.detail||d.error);return;}
  document.getElementById('reconMsg').textContent='✅ Reconnecté !';
  setTimeout(()=>{closeReconModal();loadAccounts();},800);
}
async function recon2fa(){
  const pw=document.getElementById('recon2faInp').value;
  document.getElementById('reconMsg').textContent='⏳ Vérification 2FA…';
  const d=await fetch('/api/accounts/verify-2fa',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({acc_id:_reconAccId,password:pw})}).then(r=>r.json()).catch(e=>({ok:false,error:String(e)}));
  if(!d.ok){document.getElementById('reconMsg').textContent='❌ '+(d.detail||d.error);return;}
  document.getElementById('reconMsg').textContent='✅ Reconnecté !';
  setTimeout(()=>{closeReconModal();loadAccounts();},800);
}
async function reconnectAllDisconnected(){
  const disc=accounts.filter(a=>!a.connected);
  if(!disc.length){toast('Tous les comptes sont déjà connectés','ok');return;}
  // Ouvrir le premier compte déconnecté
  const a=disc[0];
  openReconModal(a.id, a.phone, a.name||a.phone);
}

// ── Comptes sociaux unifiés (Snap / IG / FB) ───────────────────────────────
let _addSocialPlatform='snap';

function _socialAvatarBg(platform){
  return {snap:'linear-gradient(135deg,#3a3000,#5a4800)',ig:'linear-gradient(135deg,#4a1060,#7a1a1a)',fb:'linear-gradient(135deg,#0a2050,#1040a0)'}[platform]||'#222';
}
function _socialInitials(name){return(name||'?').replace('@','').slice(0,2).toUpperCase();}
function _socialPlatformLabel(p){return{snap:'Snapchat',ig:'Instagram',fb:'Facebook'}[p]||p;}
function _socialPlatformColor(p){return{snap:'#f5c518',ig:'#c084fc',fb:'#60a5fa'}[p]||'#888';}

async function _saveSocialAccountPicture(platform, accId, picUrl){
  const accs=_getSocialAccounts(platform);
  const acc=accs.find(a=>a.id===accId);
  if(!acc||acc.picture===picUrl)return;
  acc.picture=picUrl;
  await _saveSocialAccounts(platform, accs);
  // Mettre à jour les checkboxes aussi
  const cb=document.querySelector(`#${platform==='snap'?'snapAccChecks':platform==='ig'?'igAccChecks':'fbAccChecks'} input[data-id="${accId}"]`);
  if(cb){
    const lbl=cb.closest('label');
    const oldImg=lbl&&lbl.querySelector('img');
    if(!oldImg){
      const dot=lbl&&lbl.querySelector('.acc-check-dot');
      if(dot){
        const img=document.createElement('img');
        img.src=picUrl;img.style.cssText='width:22px;height:22px;border-radius:50%;object-fit:cover;flex-shrink:0';
        img.onerror=()=>img.remove();
        dot.replaceWith(img);
      }
    }
  }
}

function _makeSocialCard(a, platform){
  const initials=_socialInitials(a.username);
  const bg=_socialAvatarBg(platform);
  const platLabel=_socialPlatformLabel(platform);
  const platColor=_socialPlatformColor(platform);
  const desc=a.description||'';
  const uname=a.username.replace(/[^a-zA-Z0-9._-]/g,'');
  const platSlug={snap:'snapchat',ig:'instagram',fb:'facebook'}[platform]||platform;
  // Photo via endpoint proxy/cache VPS → instantané après 1ère visite
  const uidParam=(a.id&&['ig','fb'].includes(platform))?`?uid=${encodeURIComponent(a.id)}`:'';
  const imgTag=uname
    ? `<img src="/api/social/avatar/${platform}/${encodeURIComponent(uname)}${uidParam}" loading="lazy" onerror="this.remove()">`
    : '';
  return `<div class="acc-item-sm" data-sid="${a.id}" data-plat="${platform}">
    <div class="acc-avatar-wrap-sm">
      <div class="acc-avatar-sm" style="background:${bg}">${initials}${imgTag}
      </div>
      <div class="acc-dot-sm" style="background:var(--green)"></div>
    </div>
    <div style="flex:1;min-width:0">
      <div class="acc-name-sm">@${a.username}</div>
      <div class="acc-plat-sm" style="color:${platColor}">${platLabel}</div>
      <div class="acc-desc-wrap"><div class="acc-desc-sm" data-sid="${a.id}" data-plat="${platform}">${desc||'Ajouter une description…'}</div></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end;flex-shrink:0">
      <button class="acc-btn-sq" data-sid="${a.id}" data-plat="${platform}" data-desc="${desc.replace(/"/g,'&quot;')}" title="Modifier la description">📝</button>
      <button class="acc-btn-sq acc-ren" data-plat="${platform}" data-id="${a.id}" data-name="${a.username.replace(/"/g,'&quot;')}" title="Renommer">✏</button>
      <button class="acc-btn-sq acc-photo-btn" data-plat="${platform}" data-id="${a.id}" data-uname="${uname}" title="Changer la photo de profil">📷</button>
      <button class="acc-btn-sq del acc-del-btn" data-plat="${platform}" data-id="${a.id}">✕</button>
    </div>
  </div>`;
}

function _getSocialAccounts(platform){
  const active=_profiles.find(p=>p.id===_activeProfileId)||_profiles[0];
  if(!active)return[];
  const key={snap:'snap_accounts',ig:'instagram_accounts',fb:'facebook_accounts'}[platform];
  return (active[key]||[]).map(a=>({...a}));
}
async function _saveSocialAccounts(platform, list){
  const key={snap:'snap_accounts',ig:'instagram_accounts',fb:'facebook_accounts'}[platform];
  const pid=_activeProfileId;
  const r=await fetch(`/api/profiles/${pid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:list})}).then(r=>r.json()).catch(()=>null);
  // Mettre à jour _profiles en local pour éviter un rechargement complet
  const prof=_profiles.find(p=>p.id===pid);
  if(prof)prof[key]=list;
}

function _renderAllSocialAccounts(){
  // Snapchat
  const snapEl=document.getElementById('snapAccListPage');
  if(snapEl){
    document.getElementById('acsBadgeSnap').textContent=snapAccounts.length;
    if(!snapAccounts.length) snapEl.innerHTML='<div class="no-acc">Aucun compte — clique + Ajouter</div>';
    else{snapEl.innerHTML=snapAccounts.map(a=>_makeSocialCard(a,'snap')).join('');_attachSocialCardEvents(snapEl,'snap');}
  }
  // Instagram
  const igEl=document.getElementById('igAccListPage');
  if(igEl){
    document.getElementById('acsBadgeIg').textContent=igAccounts.length;
    if(!igAccounts.length) igEl.innerHTML='<div class="no-acc">Aucun compte — clique + Ajouter</div>';
    else{igEl.innerHTML=igAccounts.map(a=>_makeSocialCard(a,'ig')).join('');_attachSocialCardEvents(igEl,'ig');}
  }
  // Facebook
  const fbEl=document.getElementById('fbAccListPage');
  if(fbEl){
    document.getElementById('acsBadgeFb').textContent=fbAccounts.length;
    if(!fbAccounts.length) fbEl.innerHTML='<div class="no-acc">Aucun compte — clique + Ajouter</div>';
    else{fbEl.innerHTML=fbAccounts.map(a=>_makeSocialCard(a,'fb')).join('');_attachSocialCardEvents(fbEl,'fb');}
  }
}

function _attachSocialCardEvents(el, platform){
  el.querySelectorAll('.acc-del-btn').forEach(b=>b.addEventListener('click',async()=>{
    if(!confirm('Supprimer ce compte ?'))return;
    const list=_getSocialAccounts(platform).filter(a=>a.id!==b.dataset.id);
    await _saveSocialAccounts(platform,list);
    await _reloadPlatformAccounts(platform);
    _renderAllSocialAccounts();
    toast('Compte supprimé');
  }));
  el.querySelectorAll('.acc-ren').forEach(b=>b.addEventListener('click',async()=>{
    const newName=prompt('Nouveau nom :',b.dataset.name);
    if(!newName||!newName.trim())return;
    const list=_getSocialAccounts(platform);
    const acc=list.find(a=>a.id===b.dataset.id);
    if(acc)acc.username=newName.trim().replace('@','');
    await _saveSocialAccounts(platform,list);
    await _reloadPlatformAccounts(platform);
    _renderAllSocialAccounts();
    toast('Renommé');
  }));
  // Bouton description (📝) et clic sur le texte de description
  const openDesc=(sid)=>{
    const item=el.querySelector(`.acc-item[data-sid="${sid}"]`);
    if(!item)return;
    const wrap=item.querySelector('.acc-desc-wrap');
    if(!wrap||wrap.querySelector('.acc-desc-inp'))return;
    const list=_getSocialAccounts(platform);
    const acc=list.find(a=>a.id===sid);
    const cur=acc?.description||'';
    wrap.innerHTML=`<textarea class="acc-desc-inp" rows="2" placeholder="Description…">${cur.replace(/</g,'&lt;')}</textarea>
      <div style="display:flex;gap:6px;margin-top:5px">
        <button class="btn btn-xs btn-primary" data-save-sid="${sid}">💾 Enregistrer</button>
        <button class="btn btn-xs" data-cancel-sid="${sid}">Annuler</button>
      </div>`;
    wrap.querySelector(`[data-save-sid]`).addEventListener('click',async()=>{
      const val=wrap.querySelector('.acc-desc-inp').value.trim();
      const list2=_getSocialAccounts(platform);
      const acc2=list2.find(a=>a.id===sid);
      if(acc2)acc2.description=val;
      await _saveSocialAccounts(platform,list2);
      await _reloadPlatformAccounts(platform);
      _renderAllSocialAccounts();
      toast('Description enregistrée','ok');
    });
    wrap.querySelector(`[data-cancel-sid]`).addEventListener('click',()=>{
      _renderAllSocialAccounts();
    });
    wrap.querySelector('.acc-desc-inp').focus();
  };
  el.querySelectorAll('.acc-btn-sq[data-desc]').forEach(b=>b.addEventListener('click',()=>openDesc(b.dataset.sid)));
  el.querySelectorAll('.acc-desc-sm').forEach(d=>d.addEventListener('click',()=>openDesc(d.dataset.sid)));
  // Bouton photo 📷
  el.querySelectorAll('.acc-photo-btn').forEach(b=>b.addEventListener('click',()=>{
    const accId=b.dataset.id, uname=b.dataset.uname||'', plat=b.dataset.plat;
    _openPhotoUrlModal(plat, accId, uname);
  }));
}

let _photoModalCtx={plat:'',id:'',uname:''};
function _openPhotoUrlModal(plat, id, uname){
  _photoModalCtx={plat,id,uname};
  const ov=document.getElementById('overlayPhotoUrl');
  if(!ov)return;
  document.getElementById('photoUrlInput').value='';
  document.getElementById('photoUrlErr').textContent='';
  document.getElementById('photoUrlPlatLabel').textContent={snap:'Snapchat',ig:'Instagram',fb:'Facebook'}[plat]||plat;
  document.getElementById('photoUrlAccLabel').textContent='@'+(uname||id);
  ov.classList.remove('hidden');
  setTimeout(()=>document.getElementById('photoUrlInput').focus(),60);
}
async function _confirmPhotoUrl(){
  const url=document.getElementById('photoUrlInput').value.trim();
  const errEl=document.getElementById('photoUrlErr');
  errEl.textContent='';
  if(!url){errEl.textContent='Colle une URL de photo.';return;}
  const btn=document.getElementById('photoUrlConfirmBtn');
  btn.disabled=true;btn.textContent='Chargement…';
  try{
    const {plat,id,uname}=_photoModalCtx;
    const r=await fetch(`/api/social/avatar/${plat}/${encodeURIComponent(uname||id)}/set-url`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url,uid:id})
    });
    const d=await r.json().catch(()=>({}));
    if(!r.ok){errEl.textContent=d.detail||'Erreur lors du téléchargement.';return;}
    document.getElementById('overlayPhotoUrl').classList.add('hidden');
    // Forcer le rechargement de l'avatar dans les cartes
    document.querySelectorAll(`[data-sid="${id}"] .acc-avatar-sm img`).forEach(img=>{
      img.src=img.src.split('?')[0]+'?t='+Date.now();
    });
    toast('Photo mise à jour','ok');
  }catch(e){
    errEl.textContent='Erreur réseau.';
  }finally{
    btn.disabled=false;btn.textContent='✓ Enregistrer';
  }
}

async function _reloadPlatformAccounts(platform){
  if(platform==='snap'){await loadSnapAccounts();}
  else if(platform==='ig'){await loadIgAccounts();}
  else if(platform==='fb'){await loadFbAccounts();}
}

function _openAddSocialModal(platform){
  _addSocialPlatform=platform;
  const titles={snap:'Ajouter un compte Snapchat',ig:'Ajouter un compte Instagram',fb:'Ajouter un compte Facebook'};
  document.getElementById('addSocialTitle').textContent=titles[platform]||'Ajouter un compte';
  document.getElementById('addSocialName').value='';
  document.getElementById('addSocialId').value='';
  document.getElementById('addSocialErr').textContent='';
  const importList=document.getElementById('addSocialImportList');
  if(importList){importList.innerHTML='';importList.style.display='none';}
  const importBtn=document.getElementById('addSocialImportBtn');
  if(importBtn){importBtn.textContent='🔄 Importer';importBtn.disabled=false;}
  document.getElementById('overlayAddSocial').classList.remove('hidden');
  setTimeout(()=>document.getElementById('addSocialName').focus(),50);
}

async function _importSocialFromOneUp(){
  const eps={snap:'/api/oneup/snap-accounts',ig:'/api/oneup/ig-accounts',fb:'/api/oneup/fb-accounts'};
  const ep=eps[_addSocialPlatform];
  if(!ep)return;
  const btn=document.getElementById('addSocialImportBtn');
  const listEl=document.getElementById('addSocialImportList');
  if(btn){btn.textContent='…';btn.disabled=true;}
  const raw=await fetch(ep).then(r=>r.json()).catch(()=>null);
  if(btn){btn.textContent='🔄 Importer';btn.disabled=false;}
  if(!raw){
    document.getElementById('addSocialErr').textContent='Impossible de récupérer les comptes OneUp.';
    return;
  }
  const data=Array.isArray(raw)?raw:(raw.accounts||raw.data||[]);
  if(!data.length){
    document.getElementById('addSocialErr').textContent='Aucun compte trouvé dans OneUp.';
    return;
  }
  const existing=_getSocialAccounts(_addSocialPlatform).map(a=>a.id);
  const platColors={snap:'#FFFC00',ig:'#E1306C',fb:'#1877F2'};
  const platC=platColors[_addSocialPlatform]||'#a78bfa';
  listEl.innerHTML=data.map(a=>{
    const already=existing.includes(String(a.id));
    return `<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--c2);border-radius:6px;border:1px solid var(--b1)">
      <div style="width:28px;height:28px;border-radius:8px;background:${platC}22;border:1px solid ${platC}44;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;color:${platC}">${(a.name||a.username||'?').slice(0,2).toUpperCase()}</div>
      <div style="flex:1;min-width:0">
        <div style="font-size:.8rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">@${a.name||a.username||a.id}</div>
        <div style="font-size:.65rem;color:var(--t3);font-family:monospace">${a.id}</div>
      </div>
      ${already
        ?`<span style="font-size:.65rem;color:var(--green);white-space:nowrap">✓ Ajouté</span>`
        :`<button class="btn btn-xs" style="background:${platC}22;border-color:${platC}66;color:${platC};white-space:nowrap;font-size:.7rem" onclick="_importOneSocial('${a.id}','${(a.name||a.username||a.id).replace(/'/g,"\\'")}',this)">+ Ajouter</button>`
      }
    </div>`;
  }).join('');
  listEl.style.display='flex';
}

async function _importOneSocial(id, name, btn){
  const list=_getSocialAccounts(_addSocialPlatform);
  if(list.find(a=>a.id===String(id))){return;}
  list.push({username:name,id:String(id)});
  await _saveSocialAccounts(_addSocialPlatform,list);
  await _reloadPlatformAccounts(_addSocialPlatform);
  _renderAllSocialAccounts();
  if(btn){btn.outerHTML=`<span style="font-size:.65rem;color:var(--green);white-space:nowrap">✓ Ajouté</span>`;}
  toast('@'+name+' ajouté ✓','ok');
}

async function _confirmAddSocial(){
  const name=document.getElementById('addSocialName').value.trim().replace('@','');
  const id=document.getElementById('addSocialId').value.trim();
  const errEl=document.getElementById('addSocialErr');
  if(!name){errEl.textContent='Entre un nom.';return;}
  if(!id){errEl.textContent='Entre un ID OneUp.';return;}
  const list=_getSocialAccounts(_addSocialPlatform);
  if(list.find(a=>a.id===id)){errEl.textContent='Ce compte existe déjà.';return;}
  list.push({username:name,id});
  await _saveSocialAccounts(_addSocialPlatform,list);
  await _reloadPlatformAccounts(_addSocialPlatform);
  _renderAllSocialAccounts();
  document.getElementById('overlayAddSocial').classList.add('hidden');
  toast('Compte ajouté ✓','ok');
}

function renderAccList(){
  const el=document.getElementById('accList');
  const badge=document.getElementById('acsBadgeTg');if(badge)badge.textContent=accounts.length;
  if(!accounts.length){el.innerHTML='<div class="no-acc">Aucun compte</div>';return;}
  el.innerHTML=accounts.map(a=>{
    const desc=a.description||'';
    const initials=(a.name||a.phone||'?').slice(0,2).toUpperCase();
    return `<div class="acc-item-sm" data-id="${a.id}">
      <div class="acc-avatar-wrap-sm">
        <div class="acc-avatar-sm" id="av-${a.id}" style="background:linear-gradient(135deg,#1e1b4b,#312e81)">${initials}<img src="/api/accounts/${a.id}/photo" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:50%" onerror="this.remove()"></div>
        <div class="acc-dot-sm" style="background:${a.connected?'var(--green)':'#444'}"></div>
      </div>
      <div style="flex:1;min-width:0">
        <div class="acc-name-sm">${a.name||a.phone}</div>
        <div class="acc-plat-sm" style="color:var(--t2)">${a.phone} · <span style="color:#5b6acf;font-size:.7rem;font-weight:700">Telegram</span></div>
        <div class="acc-desc-wrap"><div class="acc-desc-sm acc-desc-click" data-id="${a.id}">${desc||'Ajouter une description…'}</div></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end;flex-shrink:0">
        ${a.connected
          ?`<button class="acc-btn-sq" style="color:#a78bfa;border-color:rgba(124,58,237,.3);cursor:default" title="Connecté" disabled>✓</button>`
          :`<button class="acc-btn-sq" style="color:#a78bfa;border-color:rgba(124,58,237,.4)" data-recon-id="${a.id}" data-recon-phone="${a.phone}" data-recon-name="${(a.name||a.phone).replace(/"/g,'&quot;')}" title="Reconnecter">🔄</button>`}
        <button class="acc-btn-sq acc-desc-btn" data-id="${a.id}" data-desc="${desc.replace(/"/g,'&quot;')}" title="Modifier la description">📝</button>
        <button class="acc-btn-sq acc-ren" data-id="${a.id}" data-name="${a.name||''}" data-phone="${a.phone}" title="Renommer">✏</button>
        <button class="acc-btn-sq del acc-del-btn" data-id="${a.id}">✕</button>
      </div>
    </div>`;
  }).join('');

  el.querySelectorAll('.acc-del-btn').forEach(b=>b.addEventListener('click',async()=>{
    if(!confirm('Supprimer ce compte ?'))return;
    await fetch(`/api/accounts/${b.dataset.id}`,{method:'DELETE'});toast('Compte supprimé');loadAccounts();
  }));
  el.querySelectorAll('.acc-ren').forEach(b=>b.addEventListener('click',()=>{
    document.getElementById('renameSub').textContent=b.dataset.phone;
    document.getElementById('renameInp').value=b.dataset.name;
    document.getElementById('renameErr').textContent='';
    document.getElementById('overlayRename').dataset.accId=b.dataset.id;
    document.getElementById('overlayRename').classList.remove('hidden');
    setTimeout(()=>document.getElementById('renameInp').focus(),50);
  }));

  // Charger les photos de profil en arrière-plan
  accounts.forEach(a=>{
    if(!a.connected)return;
    const av=document.getElementById('av-'+a.id);
    if(!av)return;
    const img=new Image();
    img.onload=()=>{av.textContent='';av.appendChild(img);};
    img.onerror=()=>{}; // 404 silencieux (compte absent du profil actif)
    // Léger délai pour que le profil soit bien rechargé avant la requête photo
    setTimeout(()=>{img.src=`/api/accounts/${a.id}/photo?t=${Date.now()}`;},200);
  });

  // Boutons Reconnecter
  el.querySelectorAll('[data-recon-id]').forEach(b=>b.addEventListener('click',()=>{
    openReconModal(b.dataset.reconId, b.dataset.reconPhone, b.dataset.reconName);
  }));

  // Fonction commune d'édition inline description
  function _openDescEditor(accId, wrap){
    if(wrap.querySelector('textarea'))return;
    const acc=accounts.find(a=>a.id===accId);
    const curDesc=(acc&&acc.description)||'';
    wrap.innerHTML=`<textarea class="acc-desc-inp" rows="2" placeholder="Description, notes, objectifs…">${curDesc.replace(/</g,'&lt;')}</textarea>
      <div style="display:flex;gap:6px;margin-top:5px">
        <button class="btn btn-xs btn-save-desc">Sauvegarder</button>
        <button class="btn btn-xs" style="background:#222">Annuler</button>
      </div>`;
    const ta=wrap.querySelector('textarea');
    ta.focus();ta.selectionStart=ta.selectionEnd=ta.value.length;
    const _setDesc=(v)=>{
      wrap.innerHTML=`<div class="acc-desc-sm acc-desc-click" data-id="${accId}">${v||'Ajouter une description…'}</div>`;
      wrap.querySelector('.acc-desc-click').addEventListener('click',()=>_openDescEditor(accId,wrap));
    };
    wrap.querySelector('.btn-save-desc').addEventListener('click',async()=>{
      const val=ta.value;
      await fetch(`/api/accounts/${accId}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:val})});
      if(acc)acc.description=val;
      _setDesc(val);
      toast('Description sauvegardée');
    });
    wrap.querySelectorAll('.btn-xs')[1].addEventListener('click',()=>_setDesc(curDesc));
    ta.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter')wrap.querySelector('.btn-save-desc').click();});
  }

  // Clic sur le texte de description (nouveau)
  el.querySelectorAll('.acc-desc-click').forEach(d=>d.addEventListener('click',()=>{
    const accId=d.dataset.id;
    const wrap=d.closest('.acc-desc-wrap')||d.parentElement;
    _openDescEditor(accId, wrap);
  }));

  // Bouton 📝
  el.querySelectorAll('.acc-desc-btn').forEach(b=>b.addEventListener('click',()=>{
    const accId=b.dataset.id;
    const item=el.querySelector(`[data-id="${accId}"]`);
    const wrap=item?.querySelector('.acc-desc-wrap');
    if(wrap)_openDescEditor(accId, wrap);
  }));
}
function renderAccChecks(){
  const el=document.getElementById('accChecks');
  if(!accounts.length){el.innerHTML='<div class="no-acc-warn">Aucun compte — ajoute un compte dans Comptes</div>';updateSchedBtn();return;}
  el.innerHTML=accounts.map(a=>`
    <label class="acc-check ${a.connected?'sel':''}" style="${!a.connected?'opacity:.55':''}">
      <input type="checkbox" data-id="${a.id}" ${a.connected?'checked':''}>
      <img src="/api/accounts/${a.id}/photo"
           style="width:22px;height:22px;border-radius:50%;object-fit:cover;flex-shrink:0"
           onerror="this.style.display='none'">
      <span class="acc-check-name">${a.name||a.phone}${!a.connected?' 🔴':''}</span>
    </label>`).join('');
  el.querySelectorAll('.acc-check').forEach(l=>{
    const cb=l.querySelector('input');
    cb.addEventListener('change',()=>{l.classList.toggle('sel',cb.checked);updateSchedBtn();});
  });
  updateSchedBtn();
}
function getSelAccIds(){return [...document.querySelectorAll('#accChecks input:checked')].map(i=>i.dataset.id);}

// ── Auth Modal ─────────────────────────────────────────────────────────────
function openPlatformPicker(){
  document.getElementById('overlayPlatformPicker').classList.remove('hidden');
}
function openSnapConfigModal(){
  document.getElementById('overlaySnapConfig').classList.remove('hidden');
}
function openIgConfigModal(){
  document.getElementById('overlayIgConfig').classList.remove('hidden');
}
function openAuthModal(){
  mStep='phone';mAccId='';
  ['sPhone','sCode','s2fa'].forEach((id,i)=>document.getElementById(id).style.display=i===0?'':'none');
  document.getElementById('mTitle').textContent='Ajouter un compte';
  document.getElementById('mSub').textContent='Numéro pour recevoir le SMS';
  document.getElementById('btnMOk').textContent='Envoyer le code';
  document.getElementById('mErr').textContent='';
  document.getElementById('iPhone').value='';
  document.getElementById('overlayAuth').classList.remove('hidden');
  setTimeout(()=>document.getElementById('iPhone').focus(),50);
}
function closeAuthModal(){document.getElementById('overlayAuth').classList.add('hidden');}
document.getElementById('overlayAuth').addEventListener('click',e=>{if(e.target===e.currentTarget)closeAuthModal();});
let mStep='phone',mAccId='';
document.getElementById('btnMOk').addEventListener('click',async()=>{
  const btn=document.getElementById('btnMOk'),err=document.getElementById('mErr');
  btn.disabled=true;err.textContent='';
  if(mStep==='phone'){
    const phone=document.getElementById('iPhone').value.trim();
    if(!phone){err.textContent='Numéro requis';btn.disabled=false;return;}
    try{
      const r=await fetch('/api/accounts/send-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone})});
      if(!r.ok)throw new Error((await r.json()).detail);
      const d=await r.json();mAccId=d.acc_id;mStep='code';
      document.getElementById('sPhone').style.display='none';
      document.getElementById('sCode').style.display='';
      document.getElementById('mSub').textContent=`Code SMS envoyé sur ${phone}`;
      document.getElementById('btnMOk').textContent='Vérifier';
      setTimeout(()=>document.getElementById('iCode').focus(),50);
    }catch(e){err.textContent=e.message;}
  }else if(mStep==='code'){
    const code=document.getElementById('iCode').value.trim();
    if(!code){err.textContent='Code requis';btn.disabled=false;return;}
    try{
      const r=await fetch('/api/accounts/verify-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({acc_id:mAccId,code})});
      const d=await r.json();
      if(d.need_2fa){mStep='2fa';document.getElementById('sCode').style.display='none';document.getElementById('s2fa').style.display='';document.getElementById('mSub').textContent='Mot de passe 2FA';document.getElementById('btnMOk').textContent='Confirmer';setTimeout(()=>document.getElementById('iPass').focus(),50);}
      else if(d.ok){toast(`✓ ${d.name} ajouté !`,'ok');closeAuthModal();loadAccounts();}
      else throw new Error(d.detail||'Erreur');
    }catch(e){err.textContent=String(e.message||e);}
  }else if(mStep==='2fa'){
    const pass=document.getElementById('iPass').value;
    if(!pass){err.textContent='Requis';btn.disabled=false;return;}
    try{
      const r=await fetch('/api/accounts/verify-2fa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({acc_id:mAccId,password:pass})});
      if(!r.ok)throw new Error((await r.json()).detail);
      const d=await r.json();toast(`✓ ${d.name} ajouté !`,'ok');closeAuthModal();loadAccounts();
    }catch(e){err.textContent=e.message;}
  }
  btn.disabled=false;
});
['iPhone','iCode','iPass'].forEach(id=>document.getElementById(id)?.addEventListener('keydown',e=>{if(e.key==='Enter')document.getElementById('btnMOk').click();}));

// ── Renommer compte ─────────────────────────────────────────────────────────
document.getElementById('overlayRename').addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.classList.add('hidden');});
document.getElementById('renameInp').addEventListener('keydown',e=>{if(e.key==='Enter')document.getElementById('btnRenameOk').click();});
document.getElementById('btnRenameOk').addEventListener('click',async()=>{
  const name=document.getElementById('renameInp').value.trim();
  if(!name){document.getElementById('renameErr').textContent='Pseudo requis';return;}
  const accId=document.getElementById('overlayRename').dataset.accId;
  const btn=document.getElementById('btnRenameOk');btn.disabled=true;
  try{
    await fetch(`/api/accounts/${accId}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
    toast(`✓ Renommé en "${name}"`,'ok');
    document.getElementById('overlayRename').classList.add('hidden');
    await loadAccounts();loadScheduled();
  }catch(e){document.getElementById('renameErr').textContent=e.message;}
  finally{btn.disabled=false;}
});

// ── Tab Schedule ───────────────────────────────────────────────────────────
let photos=[],dragSrc=null;
const uz=document.getElementById('uz'),fi=document.getElementById('fi');
uz.addEventListener('dragover',e=>{e.preventDefault();uz.classList.add('over');});
uz.addEventListener('dragleave',()=>uz.classList.remove('over'));
uz.addEventListener('drop',e=>{e.preventDefault();uz.classList.remove('over');uploadFiles([...e.dataTransfer.files],'sched');});
fi.addEventListener('change',()=>{uploadFiles([...fi.files],'sched');fi.value='';});

async function uploadFiles(files,mode){
  const imgs=files.filter(f=>f.type.startsWith('image/'));
  if(!imgs.length){toast('Aucune image valide','err');return;}
  toast(`Upload de ${imgs.length} photo(s)…`);
  let n=0;
  for(const f of imgs){
    const fd=new FormData();fd.append('file',f);
    try{
      const r=await fetch('/api/upload',{method:'POST',body:fd});
      if(!r.ok)continue;
      const d=await r.json();
      if(mode==='sched') photos.push({filename:d.filename,url:d.url,dt:defDt((photos.length+1)*3600000)});
      else{plPhotos.push({filename:d.filename,url:d.url,day:plPhotos.length+1,time:'10:00'});updatePlDates();}
      n++;
    }catch{}
  }
  if(mode==='sched') renderPhotos();else renderPlGrid();
  if(n) toast(`${n} photo(s) ajoutée(s)`,'ok');
}
function renderPhotos(){
  const list=document.getElementById('plist'),noP=document.getElementById('noP');
  list.innerHTML='';noP.style.display=photos.length?'none':'block';updateSchedBtn();
  photos.forEach((p,i)=>{
    const row=document.createElement('div');row.className='prow';row.draggable=true;row.dataset.idx=i;
    row.innerHTML=`<span class="dh">⠿</span><span class="pord">${i+1}</span>
      <img class="pthumb" src="${p.url}">
      <div class="pdt"><input type="datetime-local" value="${p.dt}" data-idx="${i}"></div>
      <button class="pdel" data-idx="${i}">✕</button>`;
    row.querySelector('input[type=datetime-local]').addEventListener('change',e=>{photos[+e.target.dataset.idx].dt=e.target.value;});
    row.querySelector('.pdel').addEventListener('click',e=>{e.stopPropagation();photos.splice(+e.currentTarget.dataset.idx,1);renderPhotos();});
    row.addEventListener('dragstart',e=>{dragSrc=i;setTimeout(()=>row.classList.add('dragging'),0);});
    row.addEventListener('dragend',()=>{row.classList.remove('dragging');list.querySelectorAll('.prow').forEach(r=>r.classList.remove('drag-over'));});
    row.addEventListener('dragover',e=>{e.preventDefault();list.querySelectorAll('.prow').forEach(r=>r.classList.remove('drag-over'));row.classList.add('drag-over');});
    row.addEventListener('drop',e=>{e.preventDefault();if(dragSrc===null||dragSrc===i)return;const m=photos.splice(dragSrc,1)[0];photos.splice(i,0,m);dragSrc=null;renderPhotos();});
    list.appendChild(row);
  });
}
function updateSchedBtn(){
  document.getElementById('btnSchedule').disabled=!(photos.length>0&&getSelAccIds().length>0);
  document.getElementById('tgBtnSavePl').disabled=photos.length===0;
}
document.getElementById('btnClear').addEventListener('click',()=>{photos=[];renderPhotos();toast('Vidé');});

// ── Plannings sauvegardés Telegram ─────────────────────────────────────────
function loadTgPlannings(){if(currentPage==='playlists')loadPlaylists();}


document.getElementById('tgBtnSavePl').addEventListener('click',async()=>{
  if(!photos.length)return;
  const name=prompt('Nom du planning :','Planning '+(new Date().toLocaleDateString('fr-FR')));
  if(!name)return;
  const r=await fetch('/api/tg/plannings',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,photos:photos.map(p=>({filename:p.filename,url:p.url,dt:p.dt}))})});
  if(r.ok){toast(`Planning "${name}" sauvegardé dans Médias`,'ok');loadPlaylists();}
  else toast('Erreur sauvegarde','err');
});
document.getElementById('btnSchedule').addEventListener('click',async()=>{
  const accIds=getSelAccIds();
  if(!photos.length||!accIds.length)return;
  const btn=document.getElementById('btnSchedule');btn.disabled=true;btn.textContent='Programmation…';
  try{
    const r=await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({photos:photos.map(p=>({filename:p.filename,scheduled_at:p.dt})),account_ids:accIds})});
    if(!r.ok)throw new Error((await r.json()).detail);
    const d=await r.json();
    toast(`✅ ${d.count} story(s) programmée(s)`,'ok');
    photos=[];renderPhotos();loadScheduled();
  }catch(e){toast(`Erreur: ${e.message}`,'err');}
  finally{btn.disabled=false;btn.innerHTML='📅 Programmer';updateSchedBtn();}
});

// ── Scheduled list ─────────────────────────────────────────────────────────
// ── Mode sélection ────────────────────────────────────────────────────────────
let _selMode=false;
let _selIds=new Set();

document.getElementById('btnSelMode').addEventListener('click',()=>{
  _selMode=!_selMode;
  _selIds.clear();
  document.getElementById('btnSelMode').textContent=_selMode?'Annuler':'Sélectionner';
  document.getElementById('btnSelMode').style.background=_selMode?'rgba(139,92,246,.2)':'';
  loadScheduled();
});

function _updateSelBar(){
  const bar=document.getElementById('selActionBar');
  if(!bar)return;
  const n=_selIds.size;
  bar.style.display=n>0?'flex':'none';
  const countEl=bar.querySelector('.sel-bar-count');
  if(countEl)countEl.textContent=n+' sélectionnée'+(n>1?'s':'');
}

async function loadScheduled(){
  if(!accounts.length) await loadAccounts();
  const r=await fetch('/api/scheduled?t='+Date.now());const list=await r.json();
  const el=document.getElementById('slist');
  const pending=list.filter(s=>s.status==='pending').length;
  const doneCount=list.filter(s=>s.status==='done').length;
  document.getElementById('mPending').textContent=pending;
  document.getElementById('mDone').textContent=doneCount;
  const b=document.getElementById('badgePending');b.textContent=pending;b.style.display=pending?'':'none';
  if(!list.length){el.innerHTML='<div class="no-rp">Aucune story programmée</div>';return;}
  const bmap={pending:'bp En attente',posting:'bs Envoi…',done:'bd Envoyé',error:'be Erreur',partial:'bpar Partiel'};
  const _sp={pending:0,posting:0,partial:1,error:1,done:2};
  const sorted=list.slice().sort((a,b)=>{const pa=_sp[a.status]??1,pb=_sp[b.status]??1;if(pa!==pb)return pa-pb;return a.scheduled_at.localeCompare(b.scheduled_at);});
  const toShow=_schedFilter==='done'
    ?sorted.filter(s=>s.status==='done'||s.status==='partial'||s.status==='error').sort((a,b)=>b.scheduled_at.localeCompare(a.scheduled_at)).slice(0,150)
    :sorted.filter(s=>s.status==='pending'||s.status==='posting');
  if(!toShow.length){el.innerHTML=`<div class="no-rp">${_schedFilter==='done'?'Aucune story publiée':'Aucune story en attente'}</div>`;return;}
  const items=toShow.map(s=>{
    const[bc,bl]=(bmap[s.status]||'bp ?').split(' ');
    const accList=(s.account_ids||[]).map(id=>{const a=accounts.find(x=>x.id===id);return a?(a.name||a.phone):id;});
    const accCount=accList.length;
    const accBadge=accCount?`<span class="acc-badge" data-tooltip="${accList.join('\n').replace(/"/g,'&quot;')}"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>${accCount} compte${accCount>1?'s':''} connecté${accCount>1?'s':''}</span>`:'<span style="font-size:.72rem;color:var(--t3)">—</span>';
    const plB=s.playlist_name?`<div class="spl">🎵 ${s.playlist_name}</div>`:'';
    const noteB=s.note?`<div class="snote">📝 ${s.note}</div>`:'';
    const isPending=s.status==='pending';
    const cbHtml=(_selMode&&isPending)?`<input type="checkbox" class="sitem-cb" data-cbid="${s.id}" ${_selIds.has(s.id)?'checked':''}>`:'';
    const noteBtn=(!_selMode&&isPending)?`<button class="snote-btn" data-id="${s.id}" data-note="${s.note||''}">📝</button>`:'';
    const delBtn=(!_selMode&&isPending)?`<button class="sdel2" data-id="${s.id}">✕</button>`:'';
    let errTip='';
    if((s.status==='error'||s.status==='partial')&&s.results){
      const _emap=[
        [/premium account is required/i,'Compte Telegram Premium requis pour poster des stories'],
        [/sendstoryrequest/i,'Compte Telegram Premium requis pour poster des stories'],
        [/PREMIUM_ACCOUNT_REQUIRED/i,'Compte Telegram Premium requis'],
        [/FLOOD_WAIT_(\d+)/i,(m,n)=>`Limite atteinte — réessayer dans ${Math.ceil(n/60)} min`],
        [/flood.wait/i,'Limite Telegram atteinte — attendre quelques minutes'],
        [/AUTH_KEY_UNREGISTERED|SESSION_REVOKED|session.*expir/i,'Session expirée — reconnecter le compte'],
        [/USER_DEACTIVATED/i,'Compte Telegram désactivé'],
        [/PHONE_NUMBER_BANNED/i,'Numéro banni par Telegram'],
        [/CHAT_WRITE_FORBIDDEN/i,'Permission refusée sur ce canal'],
        [/fichier introuvable/i,'Fichier média introuvable'],
        [/upload.*cloudinary.*fail|cloudinary.*échou/i,'Échec upload du fichier'],
        [/connection.*reset|network|timeout|timed out/i,'Erreur réseau — connexion interrompue'],
        [/locked/i,'Compte temporairement bloqué par Telegram'],
        [/Too many requests/i,'Trop de requêtes — Telegram a bloqué temporairement'],
      ];
      function _simplErr(raw){
        if(!raw)return'?';
        for(const[pat,repl]of _emap){
          const m=String(raw).match(pat);
          if(m)return typeof repl==='function'?repl(...m):repl;
        }
        if(String(raw).length>80)return String(raw).slice(0,80)+'…';
        return raw;
      }
      const lines=Object.entries(s.results).map(([k,v])=>{
        const icon=v.status==='done'?'✓':v.status==='error'?'✗':'⚠';
        const name=v.username||(k==='_'?'':k);
        const raw=v.msg||v.error||v.status||'?';
        const msg=_simplErr(raw);
        return name?`${icon} ${name}: ${msg}`:`${icon} ${msg}`;
      });
      errTip=lines.join('\n');
    }
    const badgeTip=errTip?` data-tooltip="${errTip.replace(/"/g,'&quot;')}"`:''
    return `<div class="sitem${_selIds.has(s.id)?' sitem-sel':''}" data-sid="${s.id}">
      ${cbHtml}
      <img class="sthumb" src="/uploads/${s.filename}" onerror="this.style.display='none'">
      <div class="sinfo"><div class="sdate">📅 ${fmt(s.scheduled_at)}</div>${plB}${accBadge}${noteB}</div>
      <div class="sright"><span class="badge ${bc}"${badgeTip}>${bl}</span>${noteBtn}${delBtn}</div>
    </div>`;
  }).join('');
  // Barre d'action sticky (toujours présente quand mode sélection actif)
  const selBarHtml=_selMode?`<div class="sel-bar" id="selActionBar" style="display:${_selIds.size>0?'flex':'none'}">
    <span class="sel-bar-count">${_selIds.size} sélectionnée${_selIds.size>1?'s':''}</span>
    <button class="btn btn-xs" id="btnSelAll">Tout</button>
    <button class="btn btn-xs" id="btnBulkResch">📅 Date</button>
    <button class="btn btn-xs btn-danger" id="btnBulkDel">🗑 Suppr.</button>
  </div>`:'';
  el.innerHTML=items+selBarHtml;
  // Checkboxes
  if(_selMode){
    el.querySelectorAll('.sitem-cb').forEach(cb=>{
      cb.addEventListener('change',()=>{
        const id=cb.dataset.cbid;
        const row=cb.closest('.sitem');
        if(cb.checked){_selIds.add(id);row.classList.add('sitem-sel');}
        else{_selIds.delete(id);row.classList.remove('sitem-sel');}
        _updateSelBar();
      });
    });
    // Sélectionner en cliquant la ligne entière
    el.querySelectorAll('.sitem[data-sid]').forEach(row=>{
      row.style.cursor='pointer';
      row.addEventListener('click',e=>{
        if(e.target.classList.contains('sitem-cb'))return;
        const id=row.dataset.sid;
        const cb=row.querySelector('.sitem-cb');
        if(!cb)return;
        cb.checked=!cb.checked;cb.dispatchEvent(new Event('change'));
      });
    });
    // Tout sélectionner
    const btnAll=document.getElementById('btnSelAll');
    if(btnAll)btnAll.addEventListener('click',()=>{
      const allPending=list.filter(s=>s.status==='pending');
      const allSelected=allPending.every(s=>_selIds.has(s.id));
      if(allSelected){_selIds.clear();}
      else{allPending.forEach(s=>_selIds.add(s.id));}
      loadScheduled();
    });
    // Suppression en masse
    const btnDel=document.getElementById('btnBulkDel');
    if(btnDel)btnDel.addEventListener('click',async()=>{
      if(!_selIds.size)return;
      if(!confirm(`Supprimer ${_selIds.size} story${_selIds.size>1?'s':''} ?`))return;
      const r2=await fetch('/api/scheduled/bulk-delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[..._selIds]})});
      const d=await r2.json();
      toast(`🗑 ${d.deleted} supprimée${d.deleted>1?'s':''}`,d.deleted?'ok':'err');
      _selIds.clear();loadScheduled();
    });
    // Reprogrammer en masse
    const btnResch=document.getElementById('btnBulkResch');
    if(btnResch)btnResch.addEventListener('click',()=>{
      if(!_selIds.size)return;
      const today=new Date().toISOString().slice(0,10);
      document.getElementById('bulkDateInp').value=today;
      document.getElementById('bulkRescheduleErr').textContent='';
      document.getElementById('bulkRescheduleSub').textContent=`Change la date de ${_selIds.size} story${_selIds.size>1?'s':''} (l'heure reste inchangée).`;
      document.getElementById('overlayBulkReschedule').classList.remove('hidden');
    });
  }
  // Boutons existants (hors mode sélection)
  el.querySelectorAll('.sdel2').forEach(b=>b.addEventListener('click',async e=>{
    e.stopPropagation();if(!confirm('Annuler ?'))return;
    await fetch(`/api/scheduled/${b.dataset.id}`,{method:'DELETE'});toast('Annulé');loadScheduled();
  }));
  el.querySelectorAll('.snote-btn').forEach(b=>b.addEventListener('click',e=>{
    e.stopPropagation();
    const s=list.find(x=>x.id===b.dataset.id);
    document.getElementById('noteSub').textContent=fmt(s?.scheduled_at||'');
    document.getElementById('noteInp').value=b.dataset.note||'';
    document.getElementById('noteErr').textContent='';
    document.getElementById('overlayNote').dataset.sid=b.dataset.id;
    document.getElementById('overlayNote').classList.remove('hidden');
    setTimeout(()=>document.getElementById('noteInp').focus(),50);
  }));
}

// Note modal
document.getElementById('overlayNote').addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.classList.add('hidden');});
document.getElementById('noteInp').addEventListener('keydown',e=>{if(e.key==='Enter')document.getElementById('btnNoteOk').click();});
document.getElementById('btnNoteOk').addEventListener('click',async()=>{
  const note=document.getElementById('noteInp').value.trim();
  const sid=document.getElementById('overlayNote').dataset.sid;
  const btn=document.getElementById('btnNoteOk');btn.disabled=true;
  try{
    await fetch(`/api/scheduled/${sid}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({note})});
    toast('📝 Remarque sauvegardée','ok');
    document.getElementById('overlayNote').classList.add('hidden');loadScheduled();
  }catch(e){document.getElementById('noteErr').textContent=e.message;}
  finally{btn.disabled=false;}
});

// Bulk reschedule modal
document.getElementById('overlayBulkReschedule').addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.classList.add('hidden');});
document.getElementById('btnBulkRescheduleOk').addEventListener('click',async()=>{
  const newDate=document.getElementById('bulkDateInp').value;
  if(!newDate){document.getElementById('bulkRescheduleErr').textContent='Choisis une date';return;}
  const btn=document.getElementById('btnBulkRescheduleOk');btn.disabled=true;
  try{
    const r=await fetch('/api/scheduled/bulk-reschedule',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ids:[..._selIds],date:newDate})});
    const d=await r.json();
    toast(`📅 ${d.rescheduled} story${d.rescheduled>1?'s':''} reprogrammée${d.rescheduled>1?'s':''}`,d.rescheduled?'ok':'err');
    document.getElementById('overlayBulkReschedule').classList.add('hidden');
    _selIds.clear();loadScheduled();
  }catch(e){document.getElementById('bulkRescheduleErr').textContent=e.message;}
  finally{btn.disabled=false;}
});

// ── Clone posts ────────────────────────────────────────────────────────────
function openCloneModal(){
  const el=document.getElementById('cloneAccs');
  el.innerHTML=accounts.map(a=>`
    <label class="l-acc"><input type="checkbox" data-id="${a.id}" ${!a.connected?'disabled':''}>
    <div class="l-acc-dot" style="background:${a.connected?'var(--green)':'#333'}"></div>
    <span class="l-acc-name">${a.name||a.phone}${!a.connected?' (déconnecté)':''}</span></label>`).join('');
  el.querySelectorAll('.l-acc').forEach(l=>{const cb=l.querySelector('input');cb.addEventListener('change',()=>l.classList.toggle('sel',cb.checked));});
  document.getElementById('cloneErr').textContent='';
  document.getElementById('overlayClone').classList.remove('hidden');
}
document.getElementById('btnClone').addEventListener('click',openCloneModal);
document.getElementById('btnCloneRP').addEventListener('click',openCloneModal);
document.getElementById('overlayClone').addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.classList.add('hidden');});
document.getElementById('btnCloneOk').addEventListener('click',async()=>{
  const accIds=[...document.querySelectorAll('#cloneAccs input:checked')].map(i=>i.dataset.id);
  if(!accIds.length){document.getElementById('cloneErr').textContent='Sélectionne au moins un compte';return;}
  const btn=document.getElementById('btnCloneOk');btn.disabled=true;
  try{
    const r=await fetch('/api/scheduled/clone-to-accounts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_ids:accIds})});
    if(!r.ok)throw new Error((await r.json()).detail);
    const d=await r.json();toast(`✅ ${d.count} post(s) ajouté(s)`,'ok');
    document.getElementById('overlayClone').classList.add('hidden');loadScheduled();
  }catch(e){document.getElementById('cloneErr').textContent=e.message;}
  finally{btn.disabled=false;}
});

// ── Médias (2 colonnes TG / Snap) ─────────────────────────────────────────
let mdCurrentPl=null,mdCurrentType=null,mdPhotos=[],mdDragSrc=null;

function showPlView(view){ // compatibilité avec le code existant launch modal
  ['mediaListView','mediaDetailView'].forEach(id=>{
    const el=document.getElementById(id);if(el)el.style.display=id===view?'':'none';
  });
}

// ── Médias : charger les 4 colonnes ────────────────────────────────────────
async function loadPlaylists(){
  const [rTg,rSn,rIg,rFb,rOld]=await Promise.all([
    fetch('/api/tg/plannings'),fetch('/api/snap/plannings'),
    fetch('/api/ig/plannings'),fetch('/api/fb/plannings'),fetch('/api/playlists')]);
  const tgList=await rTg.json(), snList=await rSn.json(),
        igList=await rIg.json(), fbList=await rFb.json(), oldList=await rOld.json();
  const today=new Date();
  const legacyTg=oldList.map(pl=>({
    id:pl.id, name:pl.name+'  (legacy)', count:pl.entries.length, _legacy:true,
    photos:(pl.entries||[]).map(e=>{
      const d=new Date(today);d.setDate(d.getDate()+(e.day_offset||0));
      const pad=n=>String(n).padStart(2,'0');
      const dt=`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${e.time||'12:00'}:00`;
      return {filename:e.filename,url:`/uploads/${e.filename}`,dt};
    })
  }));
  const allTg=[...legacyTg,...tgList];
  document.getElementById('mPlaylists').textContent=allTg.length+snList.length+igList.length+fbList.length;
  renderMediaCol('tgMediaCol',allTg,'tg');
  renderMediaCol('snapMediaCol',snList,'snap');
  renderMediaCol('igMediaCol',igList,'ig');
  renderMediaCol('fbMediaCol',fbList,'fb');
}

const _plIcons={
  tg:`<svg width="22" height="22" viewBox="0 0 240 240"><circle cx="120" cy="120" r="120" fill="#29a9e0"/><path fill="#fff" d="M20.665 100.68c49.238-21.462 82.064-35.607 98.477-42.437 46.905-19.52 56.629-22.918 62.959-23.04 1.396-.024 4.52.322 6.547 1.97 1.707 1.389 2.177 3.262 2.405 4.576.229 1.315.512 4.306.284 6.647-2.548 26.78-13.558 91.763-19.161 121.77-2.369 12.696-7.038 16.951-11.561 17.36-9.826.906-17.294-6.492-26.828-12.73-14.913-9.766-23.33-15.844-37.82-25.386-16.718-11.016-5.882-17.068 3.638-26.978 2.49-2.583 45.749-41.925 46.575-45.503.104-.447.201-2.113-1.28-2.994-1.481-.88-3.666-.577-5.243-.339-2.233.336-37.78 24.014-106.64 70.58-10.091 6.929-19.232 10.308-27.424 10.132-9.025-.193-26.383-5.108-39.284-9.306-15.832-5.148-28.405-7.875-27.324-16.619.565-4.561 6.867-9.225 18.905-14.003z"/></svg>`,
  snap:`<svg width="22" height="22" viewBox="0 0 48 48"><rect width="48" height="48" rx="9" fill="#FFFC00"/><path fill="#000" d="M24 7c-5.3 0-9.5 4.1-9.5 9.2v1.4c-1 .3-2.2.6-3 .6h-.5c-.11-.02-.2.07-.17.18.28.7 1.46 1.37 2.24 1.65.07.02.13.09.14.17.38 1.76 1.08 3.23 2.1 4.35-1.33.75-2.66 1.55-2.66 2.92 0 .98.84 1.73 2.57 2.18.17.05.3.18.31.35.21.98.58 1.91 1.06 2.47-.47.2-.9.4-.9.7 0 .54.83 1.03 2.33 1.03h1.25c.82.76 1.94 1.22 3.3 1.22s2.48-.46 3.3-1.22h1.25c1.5 0 2.33-.49 2.33-1.03 0-.3-.43-.5-.9-.7.48-.56.85-1.49 1.06-2.47.01-.17.14-.3.31-.35 1.73-.45 2.57-1.2 2.57-2.18 0-1.37-1.33-2.17-2.66-2.92 1.02-1.12 1.72-2.59 2.1-4.35.01-.08.07-.15.14-.17.78-.28 1.96-.95 2.24-1.65.03-.11-.06-.2-.17-.18h-.05c-.78 0-1.9-.27-3-.6v-1.4C33.5 11.1 29.3 7 24 7z"/></svg>`,
  ig:`<svg width="22" height="22" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" fill="url(#igG2)"/><defs><linearGradient id="igG2" x1="0" y1="24" x2="24" y2="0"><stop offset="0%" stop-color="#f09433"/><stop offset="50%" stop-color="#dc2743"/><stop offset="100%" stop-color="#bc1888"/></linearGradient></defs><rect x="2" y="2" width="20" height="20" rx="5" stroke="#fff" stroke-width="1.5"/><circle cx="12" cy="12" r="4.5" stroke="#fff" stroke-width="1.5"/><circle cx="17.5" cy="6.5" r="1" fill="#fff"/></svg>`,
  fb:`<svg width="22" height="22" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" fill="#1877F2"/><path fill="#fff" d="M15.12 12.78h-2.1v7.22h-3V12.78H8.5V10.1h1.52V8.38C10.02 6.4 11.1 5 13.38 5c.97 0 2 .1 2 .1v2.2h-1.13c-.84 0-1.13.52-1.13 1.08V10.1h2.23l-.23 2.68z"/></svg>`
};
const _plCopyTargets={tg:['snap','ig','fb'],snap:['tg','ig','fb'],ig:['tg','snap','fb'],fb:['tg','snap','ig']};
const _plCopyLabels={tg:'Telegram',snap:'Snapchat',ig:'Instagram',fb:'Facebook'};

function renderMediaCol(colId,list,type){
  const col=document.getElementById(colId);
  if(!list.length){col.innerHTML='<div style="color:var(--t3);font-size:.72rem;padding:10px 0">Aucune playlist</div>';return;}
  col.innerHTML=list.map(pl=>`
    <div style="background:var(--c2);border:1px solid ${pl._legacy?'#3a3000':'var(--b1)'};border-radius:12px;padding:12px 14px;margin-bottom:9px;display:flex;align-items:center;gap:10px;transition:opacity .15s,transform .15s"
         data-plid="${pl.id}" data-pltype="${type}" class="md-pl-row">
      <div class="md-pl-handle" title="Glisser pour réordonner" style="color:#444;font-size:18px;cursor:grab;flex-shrink:0;padding:0 2px;user-select:none;touch-action:none;line-height:1" onmouseenter="this.style.color='#888'" onmouseleave="this.style.color='#444'">⠿</div>
      <div style="width:36px;height:36px;border-radius:8px;background:#111;display:flex;align-items:center;justify-content:center;flex-shrink:0;cursor:pointer">
        ${_plIcons[type]||''}
      </div>
      <div style="flex:1;min-width:0;cursor:pointer">
        <div style="font-size:.86rem;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${pl._legacy?pl.name.replace('  (legacy)',''):pl.name}</div>
        <div style="font-size:.68rem;color:var(--t3);margin-top:2px">${pl.count} photo(s)${pl._legacy?' · <span style="color:#f5c518">legacy</span>':''}</div>
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
        <div style="position:relative">
          <button class="btn btn-xs md-copy-btn" data-plid="${pl.id}" data-pltype="${type}" title="Copier vers…" style="padding:5px 10px;font-size:.7rem;background:rgba(99,102,241,.12);border:1px solid rgba(99,102,241,.3);color:#a5b4fc;border-radius:7px;display:flex;align-items:center;gap:5px;white-space:nowrap;font-weight:600;transition:background .15s,border-color .15s" onmouseover="this.style.background='rgba(99,102,241,.22)';this.style.borderColor='rgba(99,102,241,.5)'" onmouseout="this.style.background='rgba(99,102,241,.12)';this.style.borderColor='rgba(99,102,241,.3)'"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M8 16H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2"/><rect x="8" y="8" width="12" height="12" rx="2"/></svg>Copier</button>
          <div class="md-copy-menu" data-forpl="${pl.id}" style="display:none;position:absolute;right:0;top:32px;background:#141418;border:1px solid #222;border-radius:10px;z-index:100;min-width:150px;box-shadow:0 12px 32px rgba(0,0,0,.7);padding:5px">
            ${_plCopyTargets[type].map(t=>`<div class="md-copy-item" data-plid="${pl.id}" data-srctype="${type}" data-desttype="${t}" style="padding:9px 12px;font-size:.76rem;cursor:pointer;border-radius:7px;display:flex;align-items:center;gap:9px;color:var(--t2)">${_plIcons[t]}<span style="font-weight:600">${_plCopyLabels[t]}</span></div>`).join('')}
          </div>
        </div>
        <button style="width:30px;height:30px;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.05);border:1px solid #222;border-radius:7px;cursor:pointer;color:#888;font-size:15px;transition:background .15s,color .15s" class="md-pl-open" title="Ouvrir" onmouseover="this.style.background='rgba(255,255,255,.1)';this.style.color='#fff'" onmouseout="this.style.background='rgba(255,255,255,.05)';this.style.color='#888'">›</button>
      </div>
    </div>`).join('');
  // Ouvrir playlist
  col.querySelectorAll('.md-pl-row').forEach(row=>{
    row.querySelector('.md-pl-open').addEventListener('click',()=>{
      const pl=list.find(p=>p.id===row.dataset.plid);
      if(pl)openMediaDetail(pl,row.dataset.pltype);
    });
    row.querySelector('div[style*="flex:1"]').addEventListener('click',()=>{
      const pl=list.find(p=>p.id===row.dataset.plid);
      if(pl)openMediaDetail(pl,row.dataset.pltype);
    });
    row.querySelector('div[style*="width:36px"]').addEventListener('click',()=>{
      const pl=list.find(p=>p.id===row.dataset.plid);
      if(pl)openMediaDetail(pl,row.dataset.pltype);
    });
  });
  // Menu copier
  col.querySelectorAll('.md-copy-btn').forEach(btn=>{
    btn.addEventListener('click',e=>{
      e.stopPropagation();
      document.querySelectorAll('.md-copy-menu').forEach(m=>m.style.display='none');
      const menu=col.querySelector(`.md-copy-menu[data-forpl="${btn.dataset.plid}"]`);
      if(menu)menu.style.display=menu.style.display==='none'?'block':'none';
    });
  });
  col.querySelectorAll('.md-copy-item').forEach(item=>{
    item.addEventListener('mouseenter',()=>item.style.background='rgba(255,255,255,.06)');
    item.addEventListener('mouseleave',()=>item.style.background='');
    item.addEventListener('click',e=>{
      e.stopPropagation();
      item.closest('.md-copy-menu').style.display='none';
      const pl=list.find(p=>p.id===item.dataset.plid);
      if(pl)copyPlaylistTo(pl,item.dataset.desttype);
    });
  });
  document.addEventListener('click',()=>document.querySelectorAll('.md-copy-menu').forEach(m=>m.style.display='none'),{once:false,capture:false});

  // ── Drag-and-drop réordonnancement ─────────────────────────────────────────
  const apiReorder = {tg:'/api/tg/plannings/reorder',snap:'/api/snap/plannings/reorder',ig:'/api/ig/plannings/reorder',fb:'/api/fb/plannings/reorder'}[type]||'/api/tg/plannings/reorder';
  let _plDragSrc=null, _plDragClone=null, _plDropIndicator=null;

  col.querySelectorAll('.md-pl-handle').forEach(handle=>{
    handle.addEventListener('pointerdown',e=>{
      e.preventDefault();e.stopPropagation();
      const row=handle.closest('.md-pl-row');
      if(!row)return;
      _plDragSrc=row;
      const rect=row.getBoundingClientRect();
      _plDragClone=row.cloneNode(true);
      _plDragClone.style.cssText=`position:fixed;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;z-index:9999;pointer-events:none;opacity:.9;box-shadow:0 16px 40px rgba(0,0,0,.7);border-radius:12px;transform:scale(1.03)`;
      document.body.appendChild(_plDragClone);
      row.style.opacity='.25';
      _plDropIndicator=document.createElement('div');
      _plDropIndicator.style.cssText='height:3px;background:var(--purple);border-radius:2px;margin-bottom:9px;display:none';
      handle.setPointerCapture(e.pointerId);

      handle.addEventListener('pointermove',onMove);
      handle.addEventListener('pointerup',onUp,{once:true});

      function onMove(e){
        if(!_plDragClone)return;
        const rect2=_plDragSrc.getBoundingClientRect();
        _plDragClone.style.top=(parseFloat(_plDragClone.style.top)+(e.clientY-rect2.top-rect2.height/2)*0.5)+'px';

        // Trouver la ligne cible
        const rows=[...col.querySelectorAll('.md-pl-row')].filter(r=>r!==_plDragSrc);
        let target=null,before=true;
        for(const r of rows){
          const rr=r.getBoundingClientRect();
          if(e.clientY<rr.top+rr.height/2){target=r;before=true;break;}
          target=r;before=false;
        }
        col.querySelectorAll('.md-drop-ind').forEach(d=>d.remove());
        _plDropIndicator=document.createElement('div');
        _plDropIndicator.className='md-drop-ind';
        _plDropIndicator.style.cssText='height:3px;background:var(--purple);border-radius:2px;margin:-4px 0 6px';
        if(target){
          if(before) col.insertBefore(_plDropIndicator,target);
          else target.after(_plDropIndicator);
        } else {
          col.appendChild(_plDropIndicator);
        }
      }

      function onUp(e){
        handle.removeEventListener('pointermove',onMove);
        if(_plDragClone){_plDragClone.remove();_plDragClone=null;}
        col.querySelectorAll('.md-drop-ind').forEach(d=>d.remove());
        if(_plDragSrc)_plDragSrc.style.opacity='';

        // Trouver la position de dépôt
        const rows=[...col.querySelectorAll('.md-pl-row')].filter(r=>r!==_plDragSrc);
        let target=null,before=true;
        for(const r of rows){
          const rr=r.getBoundingClientRect();
          if(e.clientY<rr.top+rr.height/2){target=r;before=true;break;}
          target=r;before=false;
        }
        if(target){
          if(before) col.insertBefore(_plDragSrc,target);
          else target.after(_plDragSrc);
        } else {
          col.appendChild(_plDragSrc);
        }

        // Sauvegarder le nouvel ordre
        const ids=[...col.querySelectorAll('.md-pl-row')].map(r=>r.dataset.plid).filter(Boolean);
        fetch(apiReorder,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})})
          .then(async r=>{
            if(r.ok){toast('Ordre sauvegardé','ok');}
            else{const t=await r.text().catch(()=>'');console.error('[REORDER]',r.status,t);toast('Erreur sauvegarde ordre','err');}
          })
          .catch(e=>{console.error('[REORDER]',e);toast('Erreur sauvegarde ordre','err');});
        _plDragSrc=null;
      }
    });
  });
}

async function copyPlaylistTo(pl,destType){
  const name=pl.name.replace(' (legacy)','');
  const photos=(pl.photos||[]).map(p=>({filename:p.filename,url:p.url,dt:p.dt||''}));
  const apiMap={tg:'/api/tg/plannings',snap:'/api/snap/plannings',ig:'/api/ig/plannings',fb:'/api/fb/plannings'};
  const api=apiMap[destType]||'/api/tg/plannings';
  const r=await fetch(api,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name+' (copie)',photos})});
  if(r.ok){toast(`✅ Copié vers ${_plCopyLabels[destType]}`,'ok');loadPlaylists();}
  else toast('Erreur copie','err');
}

// ── Création de playlist avec IA ─────────────────────────────────────────────
let _cplType='tg', _cplPhotos=[], _cplSchedule=[];

function openCreatePlaylist(type){
  _cplType=type; _cplPhotos=[]; _cplSchedule=[];
  document.getElementById('cplName').value='';
  document.getElementById('cplPhotoGrid').innerHTML='';
  document.getElementById('cplPreview').style.display='none';
  document.getElementById('cplBtnConfirm').style.display='none';
  document.getElementById('cplBtnSaveOnly').style.display='none';
  document.getElementById('cplStep1').style.display='';
  document.getElementById('cplStep2').style.display='none';
  document.getElementById('cplBtnNext').style.opacity='.4';
  document.getElementById('cplBtnNext').style.pointerEvents='none';
  // Date début = aujourd'hui
  document.getElementById('cplStartDate').value=new Date().toISOString().slice(0,10);
  // Icon & couleur selon type
  const icon=document.getElementById('cplIcon');
  if(type==='tg'){
    icon.style.background='#1a3a5c';
    icon.innerHTML='<svg width="20" height="20" viewBox="0 0 24 24" fill="#2CA5E0"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>';
    document.getElementById('cplTitle').textContent='Nouvelle playlist Telegram';
  } else if(type==='ig'){
    icon.style.background='#2a0a2a';
    icon.innerHTML='<svg width="20" height="20" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" fill="url(#igG3)"/><defs><linearGradient id="igG3" x1="0" y1="24" x2="24" y2="0"><stop offset="0%" stop-color="#f09433"/><stop offset="50%" stop-color="#dc2743"/><stop offset="100%" stop-color="#bc1888"/></linearGradient></defs><rect x="2" y="2" width="20" height="20" rx="5" stroke="#fff" stroke-width="1.5"/><circle cx="12" cy="12" r="4.5" stroke="#fff" stroke-width="1.5"/><circle cx="17.5" cy="6.5" r="1" fill="#fff"/></svg>';
    document.getElementById('cplTitle').textContent='Nouvelle playlist Instagram';
  } else if(type==='fb'){
    icon.style.background='#0a1a3a';
    icon.innerHTML='<svg width="20" height="20" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" fill="#1877F2"/><path fill="#fff" d="M15.12 12.78h-2.1v7.22h-3V12.78H8.5V10.1h1.52V8.38C10.02 6.4 11.1 5 13.38 5c.97 0 2 .1 2 .1v2.2h-1.13c-.84 0-1.13.52-1.13 1.08V10.1h2.23l-.23 2.68z"/></svg>';
    document.getElementById('cplTitle').textContent='Nouvelle playlist Facebook';
  } else {
    icon.style.background='#3a3000';
    icon.innerHTML='<svg width="20" height="20" viewBox="0 0 48 48"><rect width="48" height="48" rx="9" fill="#FFFC00"/><path fill="#000" d="M24 7c-5.3 0-9.5 4.1-9.5 9.2v1.4c-1 .3-2.2.6-3 .6h-.5c-.11-.02-.2.07-.17.18.28.7 1.46 1.37 2.24 1.65.07.02.13.09.14.17.38 1.76 1.08 3.23 2.1 4.35-1.33.75-2.66 1.55-2.66 2.92 0 .98.84 1.73 2.57 2.18.17.05.3.18.31.35.21.98.58 1.91 1.06 2.47-.47.2-.9.4-.9.7 0 .54.83 1.03 2.33 1.03h1.25c.82.76 1.94 1.22 3.3 1.22s2.48-.46 3.3-1.22h1.25c1.5 0 2.33-.49 2.33-1.03 0-.3-.43-.5-.9-.7.48-.56.85-1.49 1.06-2.47.01-.17.14-.3.31-.35 1.73-.45 2.57-1.2 2.57-2.18 0-1.37-1.33-2.17-2.66-2.92 1.02-1.12 1.72-2.59 2.1-4.35.01-.08.07-.15.14-.17.78-.28 1.96-.95 2.24-1.65.03-.11-.06-.2-.17-.18h-.05c-.78 0-1.9-.27-3-.6v-1.4C33.5 11.1 29.3 7 24 7z"/></svg>';
    document.getElementById('cplTitle').textContent='Nouvelle playlist Snapchat';
  }
  document.getElementById('cplSub').textContent='Étape 1 sur 2 — Photos';
  document.getElementById('createPlModal').classList.add('open');
}

function closeCreatePlaylist(){
  document.getElementById('createPlModal').classList.remove('open');
}

// Drag & drop + input file
(function(){
  const drop=document.getElementById('cplDrop');
  const fi=document.getElementById('cplFileIn');
  drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('drag-over');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('drag-over'));
  drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('drag-over');cplHandleFiles(e.dataTransfer.files);});
  fi.addEventListener('change',()=>cplHandleFiles(fi.files));
})();

async function cplHandleFiles(files){
  for(const f of files){
    const url=await new Promise(res=>{const r=new FileReader();r.onload=e=>res(e.target.result);r.readAsDataURL(f);});
    // Upload sur le serveur
    const fd=new FormData(); fd.append('file',f);
    const resp=await fetch('/api/upload',{method:'POST',body:fd}).catch(()=>null);
    if(resp&&resp.ok){
      const d=await resp.json();
      _cplPhotos.push({filename:d.filename,url:`/uploads/${d.filename}`,preview:url});
    }
  }
  _cplRenderPhotoGrid();
}

function _cplRenderPhotoGrid(){
  const grid=document.getElementById('cplPhotoGrid');
  grid.innerHTML=_cplPhotos.map((p,i)=>`
    <div style="position:relative;width:72px;height:72px">
      <img src="${p.preview||p.url}" style="width:72px;height:72px;border-radius:7px;object-fit:cover;border:2px solid var(--b1)">
      <button onclick="_cplRemovePhoto(${i})" style="position:absolute;top:-5px;right:-5px;width:18px;height:18px;border-radius:50%;background:#e23744;border:none;color:#fff;font-size:10px;cursor:pointer;display:flex;align-items:center;justify-content:center;line-height:1">✕</button>
    </div>`).join('');
  const btn=document.getElementById('cplBtnNext');
  if(_cplPhotos.length>0){btn.style.opacity='1';btn.style.pointerEvents='';}
  else{btn.style.opacity='.4';btn.style.pointerEvents='none';}
}

function _cplRemovePhoto(i){_cplPhotos.splice(i,1);_cplRenderPhotoGrid();}

function cplGoStep2(){
  if(!_cplPhotos.length){toast('Ajoute au moins une photo','err');return;}
  if(!document.getElementById('cplName').value.trim()){
    document.getElementById('cplName').focus();toast('Donne un nom à la playlist','err');return;
  }
  document.getElementById('cplStep1').style.display='none';
  document.getElementById('cplStep2').style.display='';
  document.getElementById('cplSub').textContent='Étape 2 sur 2 — Programmation IA';
  document.getElementById('cplPhotoSummary').innerHTML=
    `<b>${_cplPhotos.length} photo(s)</b> prêtes à programmer · La playlist se nommera <b>"${document.getElementById('cplName').value.trim()}"</b>`;
  document.getElementById('cplPreview').style.display='none';
  document.getElementById('cplBtnConfirm').style.display='none';
  document.getElementById('cplBtnSaveOnly').style.display='none';
}

function cplGoBack(){
  document.getElementById('cplStep2').style.display='none';
  document.getElementById('cplStep1').style.display='';
  document.getElementById('cplSub').textContent='Étape 1 sur 2 — Photos';
}

function cplRunAI(){
  const startDate=new Date(document.getElementById('cplStartDate').value+'T00:00:00');
  const days=parseInt(document.getElementById('cplDays').value)||30;
  const jitter=parseInt(document.querySelector('[name=cplJitter]:checked')?.value||'15');
  const slots=[...document.querySelectorAll('#cplTimeSlots input:checked')].map(x=>parseInt(x.value));
  if(!slots.length){toast('Sélectionne au moins un créneau horaire','err');return;}

  // Algorithme IA : répartir les photos uniformément sur la période
  const n=_cplPhotos.length;
  const totalSlots=days*slots.length;
  // Choisir 1 slot tous les X pour couvrir la période
  const step=Math.max(1,Math.floor(totalSlots/n));
  _cplSchedule=[];
  let slotIdx=0;
  for(let i=0;i<n;i++){
    const dayIdx=Math.floor(slotIdx/slots.length);
    const timeIdx=slotIdx%slots.length;
    if(dayIdx>=days)break;
    const d=new Date(startDate);
    d.setDate(d.getDate()+dayIdx);
    const h=slots[timeIdx];
    // Décalage aléatoire
    const offsetMin=jitter>0?Math.floor(Math.random()*jitter*2)-jitter:0;
    d.setHours(h,Math.max(0,Math.min(59,offsetMin+30)),0,0);
    const dtStr=_localDtStr(d);  // heure locale (pas UTC)
    _cplSchedule.push({...(_cplPhotos[i]),dt:dtStr});
    slotIdx+=step;
  }

  // Aperçu
  const prev=document.getElementById('cplPreviewList');
  const todayStr=new Date().toISOString().slice(0,10);
  prev.innerHTML=_cplSchedule.map((s,i)=>{
    const dt=new Date(s.dt);
    const dayLabel=dt.toLocaleDateString('fr-FR',{weekday:'short',day:'numeric',month:'short'});
    const timeLabel=dt.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
    return `<div style="display:flex;align-items:center;gap:10px;padding:5px 6px;border-radius:7px;background:${i%2===0?'transparent':'rgba(124,58,237,.04)'}">
      <img src="${s.preview||s.url}" style="width:34px;height:34px;border-radius:5px;object-fit:cover;flex-shrink:0">
      <div style="flex:1;font-size:.72rem;color:var(--t2)">Photo ${i+1}</div>
      <div style="font-size:.72rem;font-weight:700;color:var(--t1)">${dayLabel}</div>
      <div style="font-size:.7rem;color:var(--purple);font-weight:700;min-width:38px;text-align:right">${timeLabel}</div>
    </div>`;
  }).join('');

  document.getElementById('cplPreview').style.display='';
  document.getElementById('cplBtnConfirm').style.display='';
  document.getElementById('cplBtnSaveOnly').style.display='';
  toast(`✨ Planning généré : ${_cplSchedule.length} story${_cplSchedule.length>1?'s':''} sur ${days} jours`,'ok');
}

async function cplSaveOnly(){
  // Sauvegarder sans programmer
  const name=document.getElementById('cplName').value.trim();
  if(!name)return;
  const _plApi={tg:'/api/tg/plannings',snap:'/api/snap/plannings',ig:'/api/ig/plannings',fb:'/api/fb/plannings'};
  const api=_plApi[_cplType]||'/api/snap/plannings';
  const photos=(_cplSchedule.length?_cplSchedule:_cplPhotos).map(p=>({filename:p.filename,url:p.url,dt:p.dt||''}));
  const r=await fetch(api,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,photos})});
  if(r.ok){toast(`Playlist "${name}" sauvegardée`,'ok');closeCreatePlaylist();loadPlaylists();}
  else toast('Erreur sauvegarde','err');
}

async function cplConfirm(){
  if(!_cplSchedule.length){toast('Génère d\'abord le planning IA','err');return;}
  const name=document.getElementById('cplName').value.trim();
  if(!name)return;
  // 1. Sauvegarder la playlist
  const _plApi2={tg:'/api/tg/plannings',snap:'/api/snap/plannings',ig:'/api/ig/plannings',fb:'/api/fb/plannings'};
  const api=_plApi2[_cplType]||'/api/snap/plannings';
  const r=await fetch(api,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,photos:_cplSchedule.map(p=>({filename:p.filename,url:p.url,dt:p.dt||''}))} )});
  if(!r.ok){toast('Erreur sauvegarde','err');return;}
  // 2. Charger dans l'onglet correspondant
  if(_cplType==='tg'){
    photos=_cplSchedule.map(p=>({filename:p.filename,url:p.url,dt:p.dt}));
    renderPhotos();closeCreatePlaylist();navigateTo('schedule');
    toast(`✅ Planning chargé ! Sélectionne tes comptes et clique Programmer`,'ok');
  } else if(_cplType==='ig'){
    igPhotos=_cplSchedule.map(p=>({filename:p.filename,url:`/uploads/${p.filename}`,dt:p.dt||''}));
    renderIgPhotos();closeCreatePlaylist();navigateTo('instagram');
    toast(`✅ Planning Instagram chargé ! Sélectionne tes comptes`,'ok');
  } else if(_cplType==='fb'){
    fbPhotos=_cplSchedule.map(p=>({filename:p.filename,url:`/uploads/${p.filename}`,dt:p.dt||''}));
    renderFbPhotos();closeCreatePlaylist();navigateTo('facebook');
    toast(`✅ Planning Facebook chargé ! Sélectionne tes comptes`,'ok');
  } else {
    snapPhotos=_cplSchedule.map(p=>({filename:p.filename,url:p.url,dt:p.dt||''}));
    renderSnapPhotos();closeCreatePlaylist();navigateTo('snapchat');
    toast(`✅ Planning Snapchat chargé ! Sélectionne tes comptes`,'ok');
  }
  loadPlaylists();
}

function openMediaDetail(pl,type){
  mdCurrentPl={...pl};mdCurrentType=type;
  mdPhotos=pl.photos.map(p=>({...p}));
  const displayName=pl._legacy?pl.name.replace('  (legacy)',''):pl.name;
  document.getElementById('mdTitle').textContent=displayName;
  const badge=document.getElementById('mdBadge');
  if(type==='tg'){badge.textContent=pl._legacy?'Telegram (ancienne)':'Telegram';badge.style.background='#1a3a5c';badge.style.color='#2AABEE';}
  else if(type==='ig'){badge.textContent='Instagram';badge.style.background='#2a0a2a';badge.style.color='#c084fc';}
  else if(type==='fb'){badge.textContent='Facebook';badge.style.background='#0a1a3a';badge.style.color='#60a5fa';}
  else{badge.textContent='Snapchat';badge.style.background='#3a3000';badge.style.color='#f5c518';}
  const _loadLabels={tg:'📱 Charger dans Telegram',ig:'📸 Charger dans Instagram',fb:'👍 Charger dans Facebook',snap:'👻 Charger dans Snapchat'};
  document.getElementById('mdBtnLoad').textContent=_loadLabels[type]||_loadLabels.snap;
  renderMdGrid();
  document.getElementById('mediaListView').style.display='none';
  document.getElementById('mediaDetailView').style.display='';
}

document.getElementById('mdBtnBack').addEventListener('click',()=>{
  document.getElementById('mediaDetailView').style.display='none';
  document.getElementById('mediaListView').style.display='';
});

document.getElementById('mdTitle').addEventListener('click',()=>{
  if(!mdCurrentPl) return;
  const titleEl=document.getElementById('mdTitle');
  const currentName=mdCurrentPl.name;
  const inp=document.createElement('input');
  inp.value=currentName;
  inp.style.cssText='background:#1a1a1a;border:1px solid #444;color:#fff;border-radius:5px;padding:3px 8px;font-size:.88rem;font-weight:700;width:220px;outline:none';
  titleEl.innerHTML='';
  titleEl.appendChild(inp);
  inp.focus();inp.select();
  const save=async()=>{
    const newName=inp.value.trim();
    if(!newName||newName===currentName){
      titleEl.innerHTML=currentName+'<span style="font-size:.7rem;opacity:.4;font-weight:400">✏️</span>';
      return;
    }
    const apiMap={tg:'/api/tg/plannings',snap:'/api/snap/plannings',ig:'/api/ig/plannings',fb:'/api/fb/plannings'};
    const base=apiMap[mdCurrentType]||'/api/tg/plannings';
    const r=await fetch(`${base}/${mdCurrentPl.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:newName})});
    if(r.ok){
      mdCurrentPl.name=newName;
      titleEl.innerHTML=newName+'<span style="font-size:.7rem;opacity:.4;font-weight:400">✏️</span>';
      loadPlaylists();
      toast('✅ Playlist renommée','ok');
    } else {
      titleEl.innerHTML=currentName+'<span style="font-size:.7rem;opacity:.4;font-weight:400">✏️</span>';
      toast('Erreur renommage','err');
    }
  };
  inp.addEventListener('keydown',e=>{if(e.key==='Enter')save();if(e.key==='Escape'){titleEl.innerHTML=currentName+'<span style="font-size:.7rem;opacity:.4;font-weight:400">✏️</span>';}});
  inp.addEventListener('blur',save);
});

document.getElementById('mdBtnDelete').addEventListener('click',async()=>{
  if(!confirm('Supprimer ce planning définitivement ?'))return;
  const _apiMap={tg:'/api/tg/plannings',ig:'/api/ig/plannings',fb:'/api/fb/plannings',snap:'/api/snap/plannings'};
  const api=mdCurrentPl._legacy?`/api/playlists`:(_apiMap[mdCurrentType]||'/api/snap/plannings');
  await fetch(`${api}/${mdCurrentPl.id}`,{method:'DELETE'});
  toast('Planning supprimé');
  document.getElementById('mediaDetailView').style.display='none';
  document.getElementById('mediaListView').style.display='';
  loadPlaylists();
});

document.getElementById('mdBtnSave').addEventListener('click',async()=>{
  // Sauvegarde toujours dans le nouveau format TG (migration automatique des anciennes)
  const _apiMap2={tg:'/api/tg/plannings',ig:'/api/ig/plannings',fb:'/api/fb/plannings',snap:'/api/snap/plannings'};
  const api=_apiMap2[mdCurrentType]||'/api/snap/plannings';
  // Si ancienne playlist, supprimer l'originale en même temps
  if(mdCurrentPl._legacy) await fetch(`/api/playlists/${mdCurrentPl.id}`,{method:'DELETE'});
  else await fetch(`${api}/${mdCurrentPl.id}`,{method:'DELETE'});
  const saveName=mdCurrentPl._legacy?mdCurrentPl.name.replace('  (legacy)',''):mdCurrentPl.name;
  const r=await fetch(api,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:saveName,photos:mdPhotos.map(p=>({filename:p.filename,url:p.url,dt:p.dt}))})});
  if(r.ok){
    toast('Modifications sauvegardées','ok');
    const d=await r.json();mdCurrentPl.id=d.id;mdCurrentPl._legacy=false;
  } else toast('Erreur sauvegarde','err');
  loadPlaylists();
});

document.getElementById('mdBtnLoad').addEventListener('click',()=>{
  if(mdCurrentType==='tg'){
    photos=mdPhotos.map(p=>({filename:p.filename,url:p.url,dt:p.dt}));
    renderPhotos();navigateTo('schedule');
    toast('Planning chargé dans Telegram','ok');
  } else if(mdCurrentType==='ig'){
    igPhotos=mdPhotos.map(p=>({filename:p.filename,url:`/uploads/${p.filename}`,dt:p.dt||''}));
    renderIgPhotos();navigateTo('instagram');
    toast('Planning chargé dans Instagram','ok');
  } else if(mdCurrentType==='fb'){
    fbPhotos=mdPhotos.map(p=>({filename:p.filename,url:`/uploads/${p.filename}`,dt:p.dt||''}));
    renderFbPhotos();navigateTo('facebook');
    toast('Planning chargé dans Facebook','ok');
  } else {
    snapPhotos=mdPhotos.map(p=>({filename:p.filename,url:p.url,dt:p.dt||''}));
    renderSnapPhotos();navigateTo('snapchat');
    toast('Planning chargé dans Snapchat','ok');
  }
});

document.getElementById('mdAddFi').addEventListener('change',async function(){
  const files=[...this.files];this.value='';if(!files.length)return;
  for(const f of files){
    const fd=new FormData();fd.append('file',f);
    try{
      const r=await fetch('/api/upload',{method:'POST',body:fd});
      const d=await r.json();
      if(d.url)mdPhotos.push({filename:d.filename,url:d.url,dt:''});
    }catch(e){toast('Erreur upload','err');}
  }
  renderMdGrid();
});

// ── Playlist grid : event delegation + DOM reorder (pas de re-render au drop) ─
let _mdDrag=null;

// IntersectionObserver — charge les images seulement quand elles entrent dans le viewport
const _mdImgObserver=new IntersectionObserver((entries)=>{
  for(const e of entries){
    if(!e.isIntersecting)continue;
    const img=e.target;
    const src=img.dataset.lazySrc;  // data-lazy-src → dataset.lazySrc
    if(src){img.src=src;delete img.dataset.lazySrc;}
    _mdImgObserver.unobserve(img);
  }
},{rootMargin:'300px'});

// Pixel transparent 1×1 utilisé comme placeholder
const _MD_BLANK='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

function _buildMdCard(p,i){
  const card=document.createElement('div');
  card.className='md-card';card.dataset.idx=i;
  const ext=(p.filename||'').split('.').pop().toLowerCase();
  const isVid=['mp4','mov','webm','avi','m4v'].includes(ext);
  // Pas d'event listeners ici — tout passe par la délégation sur #mdGrid
  card.innerHTML=`
    <div class="md-card-media">
      ${isVid
        ?`<video src="${p.url}" style="width:100%;height:100%;object-fit:cover;background:#111" preload="none"></video>`
        :`<img src="${_MD_BLANK}" data-lazy-src="${p.url}" style="width:100%;height:100%;object-fit:cover;background:#1a1a1a" onerror="this.style.opacity='.15'">`}
      <button class="md-card-del" data-del="1">✕</button>
      <div class="md-card-handle" title="Déplacer">⠿</div>
      <div class="md-card-num">${i+1}</div>
    </div>
    <div style="padding:6px 8px">
      <div style="font-size:.58rem;color:var(--t3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px">${p.filename||''}</div>
      <input type="datetime-local" value="${(p.dt||'').slice(0,16)}" data-dtidx="1" style="width:100%;background:var(--c1);border:1px solid var(--b2);color:var(--t1);border-radius:5px;padding:3px 5px;font-size:.63rem;color-scheme:dark">
    </div>`;
  // Observer l'image pour chargement différé
  if(!isVid){
    const img=card.querySelector('img');
    if(img)_mdImgObserver.observe(img);
  }
  return card;
}

// Met à jour data-idx et numéros de toutes les cartes du grid (opération légère)
function _mdReindex(){
  document.querySelectorAll('#mdGrid [data-idx]').forEach((c,i)=>{
    c.dataset.idx=i;
    const n=c.querySelector('.md-card-num');if(n)n.textContent=i+1;
    const inp=c.querySelector('[data-dtidx]');if(inp)inp.dataset.dtidx=i;
  });
}

// Rendu initial (skeleton + batch) — appelé UNIQUEMENT à l'ouverture ou après ajout/suppression
function renderMdGrid(){
  const grid=document.getElementById('mdGrid');
  if(!mdPhotos.length){grid.innerHTML='<div style="color:var(--t3);font-size:.72rem;grid-column:1/-1;padding:20px;text-align:center">Aucune photo dans cette playlist</div>';return;}
  const SKEL=Math.min(mdPhotos.length,8);
  grid.innerHTML=Array(SKEL).fill(0).map(()=>`<div style="background:var(--c2);border-radius:9px;overflow:hidden"><div class="skel" style="height:180px;border-radius:0"></div><div style="padding:6px 8px"><div class="skel" style="height:9px;border-radius:3px;margin-bottom:6px;width:70%"></div><div class="skel" style="height:22px;border-radius:4px"></div></div></div>`).join('');
  const frag=document.createDocumentFragment();
  let idx=0;const BATCH=20;
  function batch(){
    const end=Math.min(idx+BATCH,mdPhotos.length);
    for(let i=idx;i<end;i++) frag.appendChild(_buildMdCard(mdPhotos[i],i));
    idx=end;
    if(idx<mdPhotos.length) requestAnimationFrame(batch);
    else{grid.innerHTML='';grid.appendChild(frag);}
  }
  requestAnimationFrame(batch);
}

// Event delegation : 1 listener pour toute la grille
(function(){
  const grid=document.getElementById('mdGrid');
  // Suppression
  grid.addEventListener('click',e=>{
    const del=e.target.closest('.md-card-del');
    if(!del)return;
    e.stopPropagation();
    const card=del.closest('[data-idx]');
    if(!card)return;
    const i=parseInt(card.dataset.idx);
    mdPhotos.splice(i,1);
    card.remove();
    _mdReindex();
  });
  // Changement de date
  grid.addEventListener('change',e=>{
    const inp=e.target.closest('[data-dtidx]');
    if(!inp)return;
    const card=inp.closest('[data-idx]');
    if(!card)return;
    const i=parseInt(card.dataset.idx);
    mdPhotos[i].dt=inp.value+':00';
  });
  // Démarrage drag via poignée
  grid.addEventListener('pointerdown',e=>{
    const handle=e.target.closest('.md-card-handle');
    if(!handle)return;
    const card=handle.closest('[data-idx]');
    if(!card)return;
    _mdStartDrag(e,parseInt(card.dataset.idx),card);
  });
})();

function _mdStartDrag(e,srcIdx,card){
  e.preventDefault();e.stopPropagation();
  const rect=card.getBoundingClientRect();
  const clone=card.cloneNode(true);
  clone.style.cssText=`position:fixed;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;z-index:9999;pointer-events:none;border-radius:9px;box-shadow:0 28px 70px rgba(0,0,0,.75);opacity:.97;transform:scale(1.06) rotate(1.8deg);will-change:left,top`;
  document.body.appendChild(clone);
  card.style.cssText='opacity:.2;transform:scale(.96);transition:opacity .15s,transform .15s';
  // Cache positions une seule fois
  const cachedRects=[...document.querySelectorAll('#mdGrid [data-idx]')].map(c=>({
    el:c,idx:parseInt(c.dataset.idx),r:c.getBoundingClientRect()
  }));
  _mdDrag={srcIdx,clone,card,ox:e.clientX-rect.left,oy:e.clientY-rect.top,lastTarget:srcIdx,cachedRects};
  document.addEventListener('pointermove',_mdOnMove,{passive:false});
  document.addEventListener('pointerup',_mdOnEnd,{once:true});
}

function _mdOnMove(e){
  if(!_mdDrag)return;e.preventDefault();
  const{clone,ox,oy,cachedRects}=_mdDrag;
  clone.style.left=(e.clientX-ox)+'px';clone.style.top=(e.clientY-oy)+'px';
  let target=_mdDrag.srcIdx;
  for(const{el,idx,r} of cachedRects){
    if(el===_mdDrag.card)continue;
    if(e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom){target=idx;break;}
  }
  if(target!==_mdDrag.lastTarget){
    cachedRects.forEach(({el})=>el.classList.remove('md-drop-target'));
    const tc=cachedRects.find(({idx})=>idx===target);
    if(tc&&tc.el!==_mdDrag.card)tc.el.classList.add('md-drop-target');
    _mdDrag.lastTarget=target;
  }
}

function _mdOnEnd(){
  if(!_mdDrag)return;
  document.removeEventListener('pointermove',_mdOnMove);
  const{srcIdx,clone,card,lastTarget,cachedRects}=_mdDrag;
  cachedRects.forEach(({el})=>el.classList.remove('md-drop-target'));
  const destIdx=lastTarget;
  const destCardCache=cachedRects.find(({idx})=>idx===destIdx);
  if(destCardCache&&destIdx!==srcIdx){
    const r=destCardCache.r;
    clone.style.transition='left .22s cubic-bezier(.4,0,.2,1),top .22s cubic-bezier(.4,0,.2,1),opacity .2s,transform .2s';
    clone.style.left=r.left+'px';clone.style.top=r.top+'px';
    clone.style.opacity='0';clone.style.transform='scale(.95)';
  } else {
    clone.style.transition='opacity .15s,transform .15s';
    clone.style.opacity='0';clone.style.transform='scale(.95)';
  }
  setTimeout(()=>{
    clone.remove();card.style.cssText='';
    if(destIdx!==srcIdx){
      // 1. Mettre à jour le tableau mdPhotos
      const _refDt=mdPhotos[destIdx]?mdPhotos[destIdx].dt:null;
      const moved=mdPhotos.splice(srcIdx,1)[0];
      const insertAt=srcIdx>destIdx?destIdx+1:destIdx;
      mdPhotos.splice(insertAt,0,moved);
      // 2. Déplacer le nœud DOM — AUCUN re-render, les images ne rechargent pas
      const destDomCard=destCardCache.el;
      destDomCard.after(card); // insère card après destDomCard
      // 3. Renuméroter (très rapide, juste text + dataset)
      _mdReindex();
      // 4. Auto-date
      if(_refDt){
        try{
          const refD=new Date(_refDt);
          if(!isNaN(refD)){
            refD.setHours(refD.getHours()+1);
            const _p2=n=>String(n).padStart(2,'0');
            const movedNewIdx=parseInt(card.dataset.idx);
            mdPhotos[movedNewIdx].dt=refD.getFullYear()+'-'+_p2(refD.getMonth()+1)+'-'+_p2(refD.getDate())+'T'+_p2(refD.getHours())+':'+_p2(refD.getMinutes())+':00';
            const inp=card.querySelector('[data-dtidx]');
            if(inp)inp.value=mdPhotos[movedNewIdx].dt.slice(0,16);
            toast('Date auto : '+refD.toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}));
          }
        }catch(_){}
      }
    }
    _mdDrag=null;
    // PAS de renderMdGrid() ici — le DOM est déjà à jour
  },230);
}

// ── Snapchat sub-tabs ──────────────────────────────────────────────────────
function switchSnapTab(tab){
  document.querySelectorAll('.snap-tab').forEach(t=>t.classList.toggle('active',t.dataset.snap===tab));
  document.querySelectorAll('.snap-subview').forEach(v=>v.classList.toggle('active',v.id==='snap'+(tab==='stories'?'Stories':'Spotlight')));
  const isSpotlight = tab==='spotlight';
  // Panneau droit : basculer entre Stories et Spotlights
  const slist=document.getElementById('slist');
  const splRpList=document.getElementById('splRpList');
  const rpSchedTabs=document.getElementById('rpSchedTabs');
  const rpSplTabs=document.getElementById('rpSplTabs');
  const rpTitle=document.getElementById('rpTitle');
  const btnSnapDeleteAll=document.getElementById('btnSnapDeleteAll');
  const btnSelMode=document.getElementById('btnSelMode');
  const btnCloneRP=document.getElementById('btnCloneRP');
  const btnSplRpRefresh=document.getElementById('btnSplRpRefresh');
  if(isSpotlight){
    slist.style.display='none';
    splRpList.style.display='';
    rpSchedTabs.style.display='none';
    rpSplTabs.style.display='grid';
    rpTitle.textContent='🎬 Spotlights';
    btnSnapDeleteAll.style.display='none';
    btnSelMode.style.display='none';
    btnCloneRP.style.display='none';
    btnSplRpRefresh.style.display='';
    renderSplAccChecks();loadSplPool();loadSplList();
  } else {
    slist.style.display='';
    splRpList.style.display='none';
    rpSchedTabs.style.display='grid';
    rpSplTabs.style.display='none';
    rpTitle.textContent='👻 Snapchat';
    btnSnapDeleteAll.style.display='';
    btnSelMode.style.display='';
    btnCloneRP.style.display='';
    btnSplRpRefresh.style.display='none';
    loadSnapScheduled();
  }
}

// ── Spotlight ──────────────────────────────────────────────────────────────
let splVideos=[];
function renderSplAccChecks(){
  const el=document.getElementById('splAccChecks');
  if(!el)return;
  if(!snapAccounts.length){el.innerHTML='<div class="no-acc-warn">Aucun compte Snap configuré</div>';return;}
  // Mémorise les IDs déjà cochés avant de re-rendre
  const prevChecked=new Set([...el.querySelectorAll('input:checked')].map(i=>i.dataset.id));
  el.innerHTML=snapAccounts.map(a=>`
    <label class="acc-check${(prevChecked.size===0||prevChecked.has(a.id))?' sel':''}">
      <input type="checkbox" data-id="${a.id}" ${(prevChecked.size===0||prevChecked.has(a.id))?'checked':''}>
      <div class="acc-check-dot" style="background:#f5c518"></div>
      <span class="acc-check-name">${a.username}</span></label>`).join('');
  el.querySelectorAll('.acc-check').forEach(l=>{const cb=l.querySelector('input');cb.addEventListener('change',()=>{l.classList.toggle('sel',cb.checked);updateSplBtn();});});
  updateSplBtn();
}
function getSplSelIds(){return[...document.querySelectorAll('#splAccChecks input:checked')].map(i=>i.dataset.id);}
function updateSplBtn(){
  const n=getSplSelIds().length;
  document.getElementById('splBtnSchedule').disabled=n===0;
  const total=parseInt(document.getElementById('splCount').value)||0;
  const perAcc=n>0?Math.floor(total/n):0;
  const rem=n>0?total%n:0;
  document.getElementById('splCountInfo').textContent=
    n>0?`→ ${perAcc}${rem>0?' ou '+(perAcc+1):''} vidéo(s) par compte (${n} compte${n>1?'s':''})`:'— sélectionne des comptes';
}
document.getElementById('splCount').addEventListener('input',updateSplBtn);

// ── Spotlight dossiers locaux ────────────────────────────────────────────────
const _VIDEO_EXTS_SPL = new Set(['.mp4','.mov','.moov','.avi','.m4v','.3gp','.webm','.mkv']);
let _splSrcDir = null;
let _splDstDir = null;
let _splAllHandles = [];

// ── IndexedDB : persistance des dossiers Spotlight par profil ────────────────
const _splDB = (()=>{
  return new Promise((res,rej)=>{
    const req = indexedDB.open('splFolders',1);
    req.onupgradeneeded = e => e.target.result.createObjectStore('dirs');
    req.onsuccess = e => res(e.target.result);
    req.onerror   = ()=> rej();
  });
})();

async function _splSaveHandle(key, handle){
  try{
    const db = await _splDB;
    const tx = db.transaction('dirs','readwrite');
    tx.objectStore('dirs').put(handle, key);
  }catch(_){}
}

async function _splLoadHandle(key){
  try{
    const db = await _splDB;
    return await new Promise((res,rej)=>{
      const tx = db.transaction('dirs','readonly');
      const req = tx.objectStore('dirs').get(key);
      req.onsuccess = ()=> res(req.result||null);
      req.onerror   = ()=> res(null);
    });
  }catch(_){ return null; }
}

async function _splRestoreFolders(){
  const pid = _activeProfileId||'default';
  const [srcH, dstH] = await Promise.all([
    _splLoadHandle('src_'+pid), _splLoadHandle('dst_'+pid)
  ]);
  if(srcH){
    // Vérifier/demander la permission silencieusement
    try{
      const perm = await srcH.queryPermission({mode:'readwrite'});
      if(perm==='granted'||perm==='prompt'){
        _splSrcDir = srcH;
        document.getElementById('splPickSrc').textContent='📥 '+srcH.name;
        document.getElementById('splPickDst').disabled=false;
      }
    }catch(_){}
  }
  if(dstH){
    try{
      const perm = await dstH.queryPermission({mode:'readwrite'});
      if(perm==='granted'||perm==='prompt'){
        _splDstDir = dstH;
        document.getElementById('splPickDst').textContent='📤 '+dstH.name;
      }
    }catch(_){}
  }
  if(_splSrcDir) await _splScanDir();
}

async function _splScanDir(){
  _splAllHandles = [];
  const st = document.getElementById('splFolderStatus');
  const dbg = document.getElementById('splDebugInfo');
  if(!_splSrcDir){st.textContent='';if(dbg)dbg.style.display='none';return;}
  // Demander la permission si nécessaire (ne pas bloquer si refusée — la lecture peut quand même fonctionner)
  try{
    const perm = await _splSrcDir.requestPermission({mode:'readwrite'});
    if(perm!=='granted'){
      st.textContent='⚠️ Permission refusée — essai de lecture en lecture seule…';
      st.style.color='#f5c518';
    }
  }catch(_){}
  // Scan récursif (3 niveaux)
  let _allFound = [], _skippedExts = {};
  async function _scanDir(dir, depth){
    try{
      for await(const [name,h] of dir.entries()){
        if(h.kind==='file'){
          const dotIdx = name.lastIndexOf('.');
          const ext = dotIdx>=0 ? name.slice(dotIdx).toLowerCase() : '';
          if(_VIDEO_EXTS_SPL.has(ext)){
            _splAllHandles.push(h);
            _allFound.push(name);
          } else {
            _skippedExts[ext||'(sans ext)'] = (_skippedExts[ext||'(sans ext)']||0)+1;
          }
        } else if(h.kind==='directory' && depth < 3){
          try{ await _scanDir(h, depth+1); }catch(_){}
        }
      }
    }catch(e){ if(dbg){dbg.style.display='';dbg.textContent='Erreur scan: '+e.message;} }
  }
  await _scanDir(_splSrcDir, 1);
  const dstName = _splDstDir ? ' · 📤 dest: '+_splDstDir.name : ' · ⚠️ choisir dossier dest.';
  st.textContent = `📥 ${_splAllHandles.length} vidéo(s) dans "${_splSrcDir.name}"${dstName}`;
  st.style.color = _splAllHandles.length>0 ? '#6fcf6f' : '#e23744';
  // Debug: si 0 vidéos trouvées, montrer ce qui a été trouvé
  if(dbg){
    const skippedList = Object.entries(_skippedExts).map(([k,v])=>`${k}(${v})`).join(', ');
    const totalOther = Object.values(_skippedExts).reduce((a,b)=>a+b,0);
    if(_splAllHandles.length===0 && totalOther>0){
      dbg.style.display='';
      dbg.textContent=`⚠️ Aucune vidéo reconnue. Fichiers trouvés : ${skippedList}`;
    } else if(_splAllHandles.length>0){
      dbg.style.display='';
      dbg.textContent=`✓ Vidéos: ${_allFound.slice(0,3).join(', ')}${_allFound.length>3?` +${_allFound.length-3} autres`:''}`;
    } else {
      dbg.style.display='';
      dbg.textContent='⚠️ Dossier vide ou aucun fichier détecté.';
    }
  }
  updateSplBtn();
}

document.getElementById('splPickSrc').addEventListener('click',async()=>{
  try{
    _splSrcDir = await window.showDirectoryPicker({mode:'readwrite',startIn:'downloads'});
    document.getElementById('splPickSrc').textContent='📥 '+_splSrcDir.name;
    document.getElementById('splPickDst').disabled=false;
    await _splSaveHandle('src_'+(_activeProfileId||'default'), _splSrcDir);
    await _splScanDir();
  }catch(e){if(e.name!=='AbortError')toast('Erreur: '+e.message,'err');}
});

// Sélection de fichiers individuels (alternative si le dossier pose problème)
document.getElementById('splPickFiles').addEventListener('click',async()=>{
  try{
    const files = await window.showOpenFilePicker({
      multiple: true,
      types:[{description:'Vidéos',accept:{'video/*':['.mp4','.mov','.moov','.avi','.m4v','.3gp','.webm','.mkv']}}]
    });
    if(!files||!files.length) return;
    _splAllHandles = files;
    _splSrcDir = null; // pas de dossier source, fichiers directs
    const st = document.getElementById('splFolderStatus');
    const dbg = document.getElementById('splDebugInfo');
    st.textContent = `📥 ${files.length} vidéo(s) sélectionnée(s) manuellement`;
    st.style.color = '#6fcf6f';
    if(dbg){dbg.style.display='';dbg.textContent=files.slice(0,3).map(f=>f.name).join(', ')+(files.length>3?` +${files.length-3} autres`:'');}
    document.getElementById('splPickDst').disabled=false;
    document.getElementById('splPickSrc').textContent='📁 Choisir dossier source';
    updateSplBtn();
  }catch(e){if(e.name!=='AbortError')toast('Erreur: '+e.message,'err');}
});

document.getElementById('splPickDst').addEventListener('click',async()=>{
  try{
    _splDstDir = await window.showDirectoryPicker({mode:'readwrite',startIn:'downloads'});
    document.getElementById('splPickDst').textContent='📤 '+_splDstDir.name;
    await _splSaveHandle('dst_'+(_activeProfileId||'default'), _splDstDir);
    await _splScanDir();
  }catch(e){if(e.name!=='AbortError')toast('Erreur: '+e.message,'err');}
});

async function loadSplPool(){
  try{
    const [rPool,rDates,rBlocked]=await Promise.all([
      fetch('/api/snap/spotlight/pool'),
      fetch('/api/snap/spotlight/next-dates'),
      fetch('/api/snap/spotlight/blocked-until')
    ]);
    const d=await rPool.json(), dates=await rDates.json(), blocked=await rBlocked.json();
    const info=document.getElementById('splPoolInfo');
    document.getElementById('splMPool').textContent=d.count;

    let poolHtml='';
    if(d.error){
      poolHtml=`<div style="color:#e23744;margin-bottom:8px">&#x26A0;&#xFE0F; Dossier introuvable : <code style="font-size:.65rem">${d.path}</code></div>`;
    } else {
      poolHtml=`<div style="margin-bottom:8px">&#x1F4C2; <b>${d.count} vidéo(s)</b> dans le pool &nbsp;<span style="color:#444;font-size:.65rem">${d.path}</span></div>`;
    }
    if(dates.length){
      poolHtml+=`<div style="font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#555;margin-bottom:5px">Prochaines dates libres par compte</div>`;
      poolHtml+=`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:5px">`;
      for(const acc of dates){
        const lastStr=acc.last_scheduled?`<span style="color:#555">dernier: ${acc.last_scheduled}</span>`:'<span style="color:#555">aucun encore</span>';
        const manualBadge=acc.manual_until?`<span style="color:#f59e0b;font-size:.58rem"> (bloqué manuel)</span>`:'';
        poolHtml+=`<div style="background:#111;border:1px solid #1e1e1e;border-radius:6px;padding:6px 9px">
          <div style="font-size:.7rem;font-weight:700;color:#ddd;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">@${acc.username}</div>
          <div style="font-size:.65rem;color:#f5c518;margin-top:2px">&#x25B6; prochain libre : <b>${acc.next_free}</b>${manualBadge}</div>
          <div style="font-size:.6rem;margin-top:1px">${lastStr} &nbsp;·&nbsp; <span style="color:#555">${acc.scheduled_count} prog.</span></div>
        </div>`;
      }
      poolHtml+='</div>';
    }
    info.innerHTML=poolHtml;
    info.style.borderColor=d.error?'#e23744':'#2a2f3a';

    updateSplBtn();
  }catch(e){document.getElementById('splPoolInfo').textContent='Erreur chargement pool';}
}

document.getElementById('splBtnSchedule').addEventListener('click',async()=>{
  const accIds=getSplSelIds();
  const total=parseInt(document.getElementById('splCount').value)||1;
  if(!accIds.length)return;
  const btn=document.getElementById('splBtnSchedule');
  btn.disabled=true;

  // Fichiers disponibles localement (dossier OU sélection manuelle)
  if(_splAllHandles.length > 0){
    if(_splAllHandles.length < total){
      toast(`Seulement ${_splAllHandles.length} vidéo(s) disponible(s), ${total} demandée(s)`,'err');
      updateSplBtn();btn.innerHTML='&#x1F3AC; Programmer les Spotlight';return;
    }
    const shuffled=[..._splAllHandles].sort(()=>Math.random()-0.5);
    const picked=shuffled.slice(0,total);
    btn.innerHTML='&#x23F3; Lecture des vidéos...';
    const fd=new FormData();
    try{
      for(const h of picked){const f=await h.getFile();fd.append('files',f,h.name);}
      btn.innerHTML='&#x23F3; Upload vers VPS...';
      const ru=await fetch('/api/snap/spotlight/pool/upload',{method:'POST',body:fd});
      const du=await ru.json();
      if(!ru.ok) throw new Error(du.detail||'Erreur upload');
      btn.innerHTML='&#x23F3; Programmation...';
      const rs=await fetch('/api/snap/spotlight',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({account_ids:accIds,total_videos:total})});
      if(!rs.ok)throw new Error((await rs.json()).detail||'Erreur programmation');
      const ds=await rs.json();
      // Déplacer vers dossier dest si disponible
      if(_splSrcDir && _splDstDir){
        btn.innerHTML='&#x23F3; Déplacement vers DEJA POSTEES...';
        let moved=0;
        for(const h of picked){
          try{
            const f=await h.getFile();
            const buf=await f.arrayBuffer();
            const dstFh=await _splDstDir.getFileHandle(h.name,{create:true});
            const wr=await dstFh.createWritable();await wr.write(buf);await wr.close();
            await _splSrcDir.removeEntry(h.name);
            moved++;
          }catch(e){console.warn('Move failed:',h.name,e);}
        }
        toast(`&#x2705; ${ds.count} Spotlight programmé(s) · ${moved} vidéo(s) déplacée(s) vers "${_splDstDir.name}"`,'ok');
        await _splScanDir();
      } else {
        // Sélection manuelle : retirer les fichiers uploadés de la liste locale
        const pickedNames=new Set(picked.map(h=>h.name));
        _splAllHandles=_splAllHandles.filter(h=>!pickedNames.has(h.name));
        const st=document.getElementById('splFolderStatus');
        if(st) st.textContent=`📥 ${_splAllHandles.length} vidéo(s) restante(s)`;
        toast(`&#x2705; ${ds.count} Spotlight programmé(s) · ${picked.length} vidéo(s) envoyée(s)`,'ok');
      }
      loadSplPool();loadSplList();
    }catch(e){toast(`Erreur: ${e.message}`,'err');}
    finally{updateSplBtn();btn.innerHTML='&#x1F3AC; Programmer les Spotlight';}
    return;
  }

  // Aucun fichier local → pool VPS existant
  btn.innerHTML='&#x23F3; Envoi en cours...';
  try{
    const r=await fetch('/api/snap/spotlight',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({account_ids:accIds,total_videos:total})});
    if(!r.ok)throw new Error((await r.json()).detail||'Erreur');
    const d=await r.json();
    toast(`&#x2705; ${d.count} Spotlight programmé(s) ! (${d.pool_remaining} restants dans le pool)`,'ok');
    loadSplPool();loadSplList();
  }catch(e){toast(`Erreur: ${e.message}`,'err');}
  finally{updateSplBtn();btn.innerHTML='&#x1F3AC; Programmer les Spotlight';}
});

let _splFilter='all';
function _setSplFilter(f){
  _splFilter=f;
  document.querySelectorAll('[data-splf]').forEach(b=>b.classList.toggle('sched-tab-act',b.dataset.splf===f));
  _renderSplListFromCache();
}

function _splStatusInfo(s){
  const now=new Date();
  const dt=new Date(s.scheduled_at);
  if(s.status==='error') return {cls:'be',lbl:'Erreur'};
  if(s.status==='done')  return {cls:'bd',lbl:'Envoyé'};
  // scheduled ou pending : différencier futur / passé
  if(dt>now) return {cls:'bp',lbl:'Programmé'};
  return {cls:'bp',lbl:'En attente'};
}

let _splListCache=[];
function _renderSplListFromCache(){
  const _splSp={pending:0,scheduled:0,posting:0,error:1,done:2};
  let list=_splListCache;
  if(_splFilter==='pending') list=list.filter(s=>s.status!=='done'&&s.status!=='error');
  else if(_splFilter==='done') list=list.filter(s=>s.status==='done'||s.status==='error');
  const html = list.length===0
    ? `<div class="empty"><div class="empty-ico">&#x1F3AC;</div>Aucun Spotlight${_splFilter!=='all'?' dans cette catégorie':' programmé'}</div>`
    : list.slice().sort((a,b)=>{const pa=_splSp[a.status]??1,pb=_splSp[b.status]??1;if(pa!==pb)return pa-pb;return a.scheduled_at.localeCompare(b.scheduled_at);}).map(s=>{
        const si=_splStatusInfo(s);
        const thumb=s.thumb_url
          ? `<img src="${s.thumb_url}" style="width:52px;height:68px;border-radius:8px;object-fit:cover;flex-shrink:0" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
          + `<div style="width:52px;height:68px;border-radius:8px;background:#1a1a1a;display:none;align-items:center;justify-content:center;font-size:22px;flex-shrink:0">&#x1F3AC;</div>`
          : `<div style="width:52px;height:68px;border-radius:8px;background:#1a1a1a;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0">&#x1F3AC;</div>`;
        return `<div class="sitem">
          <div style="display:flex;position:relative;flex-shrink:0">${thumb}</div>
          <div class="sinfo">
            <div class="sdate">&#x1F4C5; ${fmt(s.scheduled_at)}</div>
            <div class="saccs" style="color:#f5c518">@${s.username}</div>
            <div style="font-size:.62rem;color:var(--t3);margin-top:1px">&#x1F3AF; Spotlight</div>
          </div>
          <div class="sright">
            <span class="badge ${si.cls}">${si.lbl}</span>
            <button class="sdel2" data-id="${s.id}">&#x2715;</button>
          </div>
        </div>`;
      }).join('');
  [document.getElementById('splList'), document.getElementById('splRpList')].forEach(el=>{
    if(!el)return;
    el.innerHTML=html;
    el.querySelectorAll('.sdel2').forEach(b=>b.addEventListener('click',async()=>{
      if(!confirm('Supprimer ?'))return;
      await fetch(`/api/snap/spotlight/${b.dataset.id}`,{method:'DELETE'});toast('Supprimé');loadSplList();
    }));
  });
}

async function loadSplList(){
  const r=await fetch('/api/snap/spotlight');const list=await r.json();
  _splListCache=list;
  document.getElementById('splMTotal').textContent=list.length;
  document.getElementById('splMDone').textContent=list.filter(s=>s.status==='done').length;
  document.getElementById('splMErr').textContent=list.filter(s=>s.status==='error').length;
  _renderSplListFromCache();
}
document.getElementById('splBtnRefresh').addEventListener('click',loadSplList);
document.getElementById('btnSplRpRefresh').addEventListener('click',loadSplList);
document.getElementById('btnRpRefresh').addEventListener('click',()=>{
  if(currentPage==='instagram')loadIgScheduled();
  else if(currentPage==='facebook')loadFbScheduled();
});

// ── Stats ──────────────────────────────────────────────────────────────────

// ── Moteur graphique Canvas ────────────────────────────────────────────────
const LC_COLORS=['#8b5cf6','#f59e0b','#22c55e','#3b82f6','#ef4444','#06b6d4','#ec4899','#a3e635','#fb923c','#818cf8'];

const LC_WIN=25; // points visibles par défaut

function lcDrawChart(canvasEl, tooltipEl, seriesData, labels, panOffset){
  if(!canvasEl)return;
  const box=canvasEl.parentElement;
  const dpr=window.devicePixelRatio||1;
  const W=box.clientWidth||600, H=box.clientHeight||440;
  canvasEl.width=W*dpr; canvasEl.height=H*dpr;
  canvasEl.style.width=W+'px'; canvasEl.style.height=H+'px';
  const ctx=canvasEl.getContext('2d');
  ctx.scale(dpr,dpr);

  // Windowed slice
  const totalPts=labels.length;
  const winSize=Math.min(totalPts,LC_WIN);
  if(panOffset===undefined) panOffset=canvasEl._panOffset||0;
  panOffset=Math.max(0,Math.min(panOffset,totalPts-winSize));
  canvasEl._panOffset=panOffset;
  const startIdx=panOffset;
  const endIdx=startIdx+winSize;
  const visLabels=labels.slice(startIdx,endIdx);
  const visSeries=seriesData.map(s=>({...s,values:s.values.slice(startIdx,endIdx)}));

  const pl={top:24,right:150,bottom:44,left:58};
  const cW=W-pl.left-pl.right, cH=H-pl.top-pl.bottom;

  if(!visLabels.length){
    ctx.fillStyle='#0f0f0f';ctx.fillRect(0,0,W,H);
    ctx.fillStyle='rgba(255,255,255,.2)';ctx.font='14px system-ui';
    ctx.textAlign='center';ctx.fillText('Aucune donnée — clique Actualiser',W/2,H/2);
    canvasEl._lcData={pl,cW,cH,labels:visLabels,seriesData:visSeries,maxV:1,fullLabels:labels,fullSeries:seriesData};
    return;
  }

  const allVals=visSeries.flatMap(s=>s.values);
  const maxV=Math.max(...allVals,1);

  ctx.fillStyle='#0f0f0f';ctx.fillRect(0,0,W,H);

  // Grid + Y labels
  const gridN=6;
  for(let i=0;i<=gridN;i++){
    const y=pl.top+cH*i/gridN;
    ctx.strokeStyle='rgba(255,255,255,.06)';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(pl.left,y);ctx.lineTo(pl.left+cW,y);ctx.stroke();
    const val=Math.round(maxV*(1-i/gridN));
    ctx.fillStyle='rgba(255,255,255,.32)';ctx.font='11px system-ui';
    ctx.textAlign='right';ctx.fillText(val,pl.left-8,y+4);
  }

  // X axis labels — every other if many points
  const xStep=Math.max(1,Math.floor(visLabels.length/8));
  ctx.fillStyle='rgba(255,255,255,.38)';ctx.font='11px system-ui';ctx.textAlign='center';
  visLabels.forEach((lbl,i)=>{
    if(i%xStep!==0&&i!==visLabels.length-1)return;
    const x=pl.left+(visLabels.length===1?cW/2:(i/(visLabels.length-1))*cW);
    ctx.fillText(lbl.slice(5,10),x,H-pl.bottom+16);
  });

  // Area fill under each line
  visSeries.forEach((s,si)=>{
    const col=LC_COLORS[si%LC_COLORS.length];
    ctx.save();ctx.globalAlpha=0.08;ctx.fillStyle=col;
    ctx.beginPath();
    s.values.forEach((v,i)=>{
      const x=pl.left+(visLabels.length===1?cW/2:(i/(visLabels.length-1))*cW);
      const y=pl.top+(1-v/maxV)*cH;
      if(i===0)ctx.moveTo(x,y); else ctx.lineTo(x,y);
    });
    const lastX=pl.left+(visLabels.length===1?cW/2:((visLabels.length-1)/(visLabels.length-1))*cW);
    ctx.lineTo(lastX,pl.top+cH);ctx.lineTo(pl.left,pl.top+cH);ctx.closePath();ctx.fill();
    ctx.restore();
  });

  // Lines + dots
  visSeries.forEach((s,si)=>{
    const col=LC_COLORS[si%LC_COLORS.length];
    ctx.strokeStyle=col;ctx.lineWidth=2.8;
    ctx.shadowColor=col;ctx.shadowBlur=10;
    ctx.beginPath();
    s.values.forEach((v,i)=>{
      const x=pl.left+(visLabels.length===1?cW/2:(i/(visLabels.length-1))*cW);
      const y=pl.top+(1-v/maxV)*cH;
      if(i===0){ctx.moveTo(x,y);}
      else{
        const pi=visLabels.length===1?cW/2:((i-1)/(visLabels.length-1))*cW;
        const px=pl.left+pi, py=pl.top+(1-s.values[i-1]/maxV)*cH;
        const mx=(px+x)/2;
        ctx.bezierCurveTo(mx,py,mx,y,x,y);
      }
    });
    ctx.stroke();ctx.shadowBlur=0;
    s.values.forEach((v,i)=>{
      if(v===0)return;
      const x=pl.left+(visLabels.length===1?cW/2:(i/(visLabels.length-1))*cW);
      const y=pl.top+(1-v/maxV)*cH;
      ctx.fillStyle=col;ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();
      ctx.strokeStyle='#0f0f0f';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.stroke();
    });
  });

  // Legend
  visSeries.forEach((s,si)=>{
    const col=LC_COLORS[si%LC_COLORS.length];
    const yl=pl.top+si*20;
    if(yl>H-pl.bottom-12)return;
    ctx.fillStyle=col;ctx.beginPath();ctx.arc(W-pl.right+16,yl+6,6,0,Math.PI*2);ctx.fill();
    ctx.fillStyle='rgba(255,255,255,.75)';ctx.font='11.5px system-ui';
    ctx.textAlign='left';ctx.fillText(s.name.slice(0,15),W-pl.right+28,yl+10);
  });

  // Scroll progress bar at bottom
  if(totalPts>winSize){
    const barH=4,barY=H-6;
    ctx.fillStyle='rgba(255,255,255,.08)';ctx.beginPath();ctx.roundRect(pl.left,barY,cW,barH,2);ctx.fill();
    const ratio=winSize/totalPts;
    const barW=cW*ratio;
    const barX=pl.left+(cW-barW)*(panOffset/(totalPts-winSize));
    ctx.fillStyle='rgba(139,92,246,.6)';ctx.beginPath();ctx.roundRect(barX,barY,barW,barH,2);ctx.fill();
  }

  canvasEl._lcData={pl,cW,cH,labels:visLabels,seriesData:visSeries,maxV,fullLabels:labels,fullSeries:seriesData};
  // Bind events (only once)
  if(!canvasEl._lcBound){
    canvasEl._lcBound=true;
    canvasEl.addEventListener('wheel',lcWheel,{passive:false});
    canvasEl.addEventListener('mousedown',lcDragStart);
    canvasEl.addEventListener('mousemove',e=>{lcHover(canvasEl,tooltipEl,e);lcDragMove(canvasEl,tooltipEl,e);});
    canvasEl.addEventListener('mouseup',lcDragEnd);
    canvasEl.addEventListener('mouseleave',()=>{
      if(tooltipEl)tooltipEl.style.opacity='0';
      lcDragEnd();
      const d=canvasEl._lcData;
      if(d)lcDrawChart(canvasEl,null,d.fullSeries,d.fullLabels,canvasEl._panOffset);
    });
  }
}

function lcWheel(e){
  e.preventDefault();
  const canvas=e.currentTarget;
  const d=canvas._lcData;if(!d)return;
  const delta=Math.sign(e.deltaY);
  const newPan=Math.max(0,Math.min(canvas._panOffset+delta, d.fullLabels.length-LC_WIN));
  if(newPan!==canvas._panOffset){
    const tip=canvas.parentElement.querySelector('.lc-tooltip');
    lcDrawChart(canvas,tip,d.fullSeries,d.fullLabels,newPan);
  }
}

let _lcDrag={active:false,startX:0,startPan:0,canvas:null};
function lcDragStart(e){
  _lcDrag={active:true,startX:e.clientX,startPan:e.currentTarget._panOffset||0,canvas:e.currentTarget};
  e.currentTarget.parentElement.classList.add('dragging');
}
function lcDragMove(canvas,tip,e){
  if(!_lcDrag.active||_lcDrag.canvas!==canvas)return;
  const d=canvas._lcData;if(!d||!d.fullLabels)return;
  const dx=e.clientX-_lcDrag.startX;
  const pxPerPt=d.cW/Math.max(1,Math.min(d.fullLabels.length,LC_WIN)-1);
  const shift=Math.round(-dx/pxPerPt);
  const newPan=Math.max(0,Math.min(_lcDrag.startPan+shift,d.fullLabels.length-LC_WIN));
  if(newPan!==canvas._panOffset){
    lcDrawChart(canvas,tip,d.fullSeries,d.fullLabels,newPan);
  }
}
function lcDragEnd(){
  if(_lcDrag.active&&_lcDrag.canvas){
    _lcDrag.canvas.parentElement.classList.remove('dragging');
  }
  _lcDrag.active=false;
}

function lcHover(canvas,tip,e){
  if(_lcDrag.active)return;
  const d=canvas._lcData;if(!d||!tip)return;
  const rect=canvas.getBoundingClientRect();
  const mx=e.clientX-rect.left;
  const {pl,cW,labels,seriesData,maxV,cH,fullSeries,fullLabels}=d;
  if(labels.length===0)return;
  const idx=Math.round((mx-pl.left)/cW*(labels.length-1));
  const ci=Math.max(0,Math.min(idx,labels.length-1));
  const x=pl.left+(labels.length===1?cW/2:(ci/(labels.length-1))*cW);
  lcDrawChart(canvas,null,fullSeries,fullLabels,canvas._panOffset);
  const ctx=canvas.getContext('2d');
  // lcDrawChart already applied ctx.scale(dpr,dpr) — do NOT scale again
  ctx.strokeStyle='rgba(255,255,255,.3)';ctx.lineWidth=1;ctx.setLineDash([5,4]);
  ctx.beginPath();ctx.moveTo(x,pl.top);ctx.lineTo(x,pl.top+cH);ctx.stroke();
  ctx.setLineDash([]);
  const rows=seriesData.map((s,si)=>({name:s.name,val:s.values[ci]||0,col:LC_COLORS[si%LC_COLORS.length]}))
    .filter(r=>r.val>0).sort((a,b)=>b.val-a.val);
  const total=rows.reduce((s,r)=>s+r.val,0);
  tip.innerHTML=`<div class="lc-tooltip-date">${labels[ci]}</div>
    <div class="lc-tooltip-total">Total : ${total.toLocaleString('fr-FR')}</div>
    ${rows.map(r=>`<div class="lc-tooltip-row"><div class="lc-tooltip-dot" style="background:${r.col}"></div><div class="lc-tooltip-name">${r.name}</div><div class="lc-tooltip-val">${r.val}</div></div>`).join('')}`;
  let lx=e.clientX-rect.left+14, ly=e.clientY-rect.top-20;
  if(lx+160>rect.width-pl.right)lx=e.clientX-rect.left-170;
  tip.style.left=lx+'px';tip.style.top=Math.max(0,ly)+'px';tip.style.opacity='1';
}

let statsPlatform='telegram';
let _statsDateRange='last_7';

function getDateRange(key){
  const now=new Date();
  const today=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  const ms=86400000;
  switch(key){
    case 'today':      return{from:today,to:new Date(today.getTime()+ms)};
    case 'yesterday':  return{from:new Date(today.getTime()-ms),to:today};
    case 'last_7':     return{from:new Date(today.getTime()-6*ms),to:new Date(today.getTime()+ms)};
    case 'this_week':  {const dow=(today.getDay()+6)%7;return{from:new Date(today.getTime()-dow*ms),to:new Date(today.getTime()+ms)};}
    case 'last_week':  {const dow=(today.getDay()+6)%7;const ws=new Date(today.getTime()-dow*ms);return{from:new Date(ws.getTime()-7*ms),to:ws};}
    case 'this_month': return{from:new Date(now.getFullYear(),now.getMonth(),1),to:new Date(today.getTime()+ms)};
    case 'last_month': return{from:new Date(now.getFullYear(),now.getMonth()-1,1),to:new Date(now.getFullYear(),now.getMonth(),1)};
    case 'this_year':  return{from:new Date(now.getFullYear(),0,1),to:new Date(today.getTime()+ms)};
    case 'last_year':  return{from:new Date(now.getFullYear()-1,0,1),to:new Date(now.getFullYear(),0,1)};
    default:           return null;
  }
}

function inDateRange(dateStr){
  const range=getDateRange(_statsDateRange);
  if(!range||!dateStr)return true;
  const d=new Date(dateStr);
  return d>=range.from && d<range.to;
}

document.querySelectorAll('.dr-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.dr-btn').forEach(b=>b.classList.remove('dr-active'));
    btn.classList.add('dr-active');
    _statsDateRange=btn.dataset.dr;
    loadStats();
  });
});
let _tgScheduled=[], _snapScheduled=[];

function switchStatsPlatform(p){
  statsPlatform=p;
  document.getElementById('sptTg').classList.toggle('active',p==='telegram');
  document.getElementById('sptSnap').classList.toggle('active',p==='snapchat');
  loadStats();
  renderStatsOverview();
  // Trigger chart redraw after display change (canvas needs dimensions)
  setTimeout(()=>{
    if(p==='telegram'){
      const canvas=document.getElementById('lcTgCanvas');
      const tip=document.getElementById('lcTgTooltip');
      if(canvas&&canvas._lcData){lcDrawChart(canvas,tip,canvas._lcData.seriesData,canvas._lcData.labels);}
    } else {
      const canvas=document.getElementById('lcSnapCanvas');
      const tip=document.getElementById('lcSnapTooltip');
      if(canvas&&canvas._lcData){lcDrawChart(canvas,tip,canvas._lcData.seriesData,canvas._lcData.labels);}
    }
  },50);
  if(p==='telegram'){
    document.getElementById('statsNote').style.display='';
    document.getElementById('statsDetailTitle').textContent='📊 Détail Telegram';
  } else {
    document.getElementById('statsNote').style.display='none';
    document.getElementById('statsDetailTitle').textContent='📊 Détail Snapchat';
  }
}

function renderStatsOverview(){
  const list=statsPlatform==='telegram'?_tgScheduled:_snapScheduled;
  const done=list.filter(s=>s.status==='done'||s.status==='partial').length;
  const err=list.filter(s=>s.status==='error').length;
  document.getElementById('sovTotal').textContent=list.length;
  document.getElementById('sovDone').textContent=done;
  document.getElementById('sovErr').textContent=err;
  document.getElementById('sovViews').textContent='…';
  document.getElementById('sptTgSub').textContent=_tgScheduled.length+' posts';
  document.getElementById('sptSnapSub').textContent=_snapScheduled.length+' posts';
  // Show/hide charts based on platform
  document.getElementById('lcTgWrap').style.display=statsPlatform==='telegram'?'':'none';
  document.getElementById('lcSnapWrap').style.display=statsPlatform==='snapchat'?'':'none';
}

function buildTgChartData(viewsList){
  // Aggregate total views per day (sum all accounts)
  const byDay={};
  viewsList.forEach(s=>{
    const day=(s.sent_at||'').slice(0,10);if(!day)return;
    const total=(s.accounts||[]).reduce((sum,a)=>sum+(a.views||0),0);
    byDay[day]=(byDay[day]||0)+total;
  });
  const _tk=new Date().toISOString().slice(0,10);if(!(_tk in byDay))byDay[_tk]=0;
  const labels=Object.keys(byDay).sort();
  const series=labels.length?[{name:'Vues totales',values:labels.map(d=>byDay[d]||0)}]:[];
  return{labels,series};
}

function buildSnapChartData(snapList){
  // Aggregate total posts sent per day
  const sent=snapList.filter(s=>s.status==='done'||s.status==='partial');
  const byDay={};
  sent.forEach(s=>{
    const day=(s.scheduled_at||'').slice(0,10);if(!day)return;
    const count=Object.values(s.results||{}).filter(r=>r.status==='done').length||1;
    byDay[day]=(byDay[day]||0)+count;
  });
  const _tk=new Date().toISOString().slice(0,10);if(!(_tk in byDay))byDay[_tk]=0;
  const labels=Object.keys(byDay).sort();
  const series=labels.length?[{name:'Posts envoyés',values:labels.map(d=>byDay[d]||0)}]:[];
  return{labels,series};
}

async function loadStats(){
  const el=document.getElementById('statsList');
  const btn=document.getElementById('btnRefreshStats');
  el.innerHTML='<div class="empty"><div class="empty-ico">⏳</div>Chargement des statistiques…</div>';
  if(btn)btn.classList.add('btn-spinning');
  try{
    const [tgR,snapR,splR]=await Promise.all([
      fetch('/api/scheduled'),
      fetch('/api/snap/scheduled'),
      fetch('/api/snap/spotlight')
    ]);
    _tgScheduled=await tgR.json();
    const _stories=await snapR.json();
    const _spotlight=await splR.json();
    // Normaliser spotlight pour qu'il ait le même format que les stories
    const _splNorm=_spotlight.map(s=>({
      ...s,
      scheduled_at: s.scheduled_at,
      _type:'spotlight',
      results: s.results||{}
    }));
    _snapScheduled=[..._stories,..._splNorm];
    renderStatsOverview();

    if(statsPlatform==='telegram'){
      // Charger l'historique ET les vues live en parallèle
      const [histR, liveR] = await Promise.all([
        fetch('/api/stats/history'),
        fetch('/api/stats/live').catch(()=>null)
      ]);
      const hist=await histR.json();
      const liveData=liveR&&liveR.ok ? await liveR.json().catch(()=>[]) : [];

      // KPI total vues sauvegardées (filtré par plage de dates)
      const histFiltered=_statsDateRange==='all'?hist:hist.filter(s=>inDateRange(s.scheduled_at));
      let totalViews=0, totalReactions=0, totalStories=0;
      histFiltered.forEach(s=>{
        s.accounts.forEach(a=>{
          totalViews+=(a.views||0);
          totalReactions+=(a.reactions||0);
        });
        if(s.accounts.length) totalStories++;
      });
      document.getElementById('sovViews').textContent=totalViews.toLocaleString('fr-FR');
      document.getElementById('sovViewsLbl').textContent=totalReactions>0?`Vues · ${totalReactions.toLocaleString('fr-FR')} likes`:'Vues totales (historique)';

      // Chart par jour
      setTimeout(()=>{
        const byDay={};
        // Pré-remplir tous les jours de la plage avec 0 (évite les trous)
        if(_statsDateRange!=='all'){
          const rng=getDateRange(_statsDateRange);
          if(rng){
            for(let d=new Date(rng.from);d<rng.to;d=new Date(d.getTime()+86400000)){
              byDay[d.toISOString().slice(0,10)]=0;
            }
          }
        }
        histFiltered.forEach(s=>{
          const day=(s.scheduled_at||'').slice(0,10); if(!day)return;
          s.accounts.forEach(a=>{ byDay[day]=(byDay[day]||0)+(a.views||0); });
        });
        // Toujours inclure aujourd'hui (même sans données)
        const _todayKey=new Date().toISOString().slice(0,10);
        if(!(_todayKey in byDay)) byDay[_todayKey]=0;
        const labels=Object.keys(byDay).sort();
        const series=labels.length?[{name:'Vues totales',values:labels.map(d=>byDay[d]||0)}]:[];
        const canvas=document.getElementById('lcTgCanvas');
        const tip=document.getElementById('lcTgTooltip');
        const sub=document.getElementById('lcTgSub');
        if(sub)sub.textContent=totalStories+' stories envoyées · mis à jour '+new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
        if(canvas){canvas._panOffset=Math.max(0,labels.length-LC_WIN);lcDrawChart(canvas,tip,series,labels);}
        const hint=document.getElementById('lcTgHint');
        if(hint)hint.style.display=labels.length>LC_WIN?'':'none';
      },60);

      // Helpers
      const todayStr=new Date().toISOString().slice(0,10);
      const yestStr=new Date(Date.now()-86400000).toISOString().slice(0,10);
      function dayLabel(d){
        if(d===todayStr)return"Aujourd'hui";
        if(d===yestStr)return'Hier';
        if(d==='unknown')return'Date inconnue';
        return new Date(d).toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'});
      }

      // Grouper par jour (données déjà filtrées)
      const byDayMap={};
      histFiltered.forEach(s=>{
        const day=(s.scheduled_at||'').slice(0,10)||'unknown';
        if(!byDayMap[day])byDayMap[day]=[];
        byDayMap[day].push(s);
      });
      const days=Object.keys(byDayMap).sort().reverse();

      // Section "En direct" — stories actives en ce moment sur Telegram
      let liveHtml='';
      if(liveData&&liveData.length){
        const activeStories=liveData.filter(s=>!s.error);
        const errorAccs=liveData.filter(s=>s.error);
        if(activeStories.length){
          const totalLiveViews=activeStories.reduce((s,x)=>s+(x.views||0),0);
          liveHtml=`<div style="margin-bottom:18px">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
              <div class="live-dot"></div>
              <div style="font-size:.78rem;font-weight:800;color:var(--t1)">En direct — stories actives maintenant</div>
              <div style="flex:1;height:1px;background:var(--b1)"></div>
              <div style="font-size:.65rem;color:var(--t3)">${activeStories.length} story${activeStories.length>1?'s':''} · ${totalLiveViews.toLocaleString('fr-FR')} vues</div>
            </div>
            <div style="display:flex;flex-direction:column;gap:5px">`;
          // Grouper par story_id (plusieurs comptes peuvent avoir la même story)
          const byStory={};
          activeStories.forEach(s=>{
            const key=s.story_id||s.acc_id;
            if(!byStory[key])byStory[key]=[];
            byStory[key].push(s);
          });
          Object.values(byStory).forEach(rows=>{
            const first=rows[0];
            const totalV=rows.reduce((s,x)=>s+(x.views||0),0);
            const totalR=rows.reduce((s,x)=>s+(x.reactions||0),0);
            const pubAt=first.date?new Date(first.date).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}):'—';
            const expAt=first.expire?new Date(first.expire).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}):'—';
            // Trouver la photo via story_id dans _tgScheduled
            let thumbUrl='';
            if(first.story_id&&_tgScheduled){
              for(const sch of _tgScheduled){
                const res=sch.results||{};
                for(const r of Object.values(res)){
                  if(r.story_id===first.story_id&&sch.filename){
                    thumbUrl=`/uploads/${sch.filename}`;break;
                  }
                }
                if(thumbUrl)break;
              }
            }
            liveHtml+=`<div class="live-story-row">
              ${thumbUrl?`<img src="${thumbUrl}" style="width:38px;height:38px;border-radius:6px;object-fit:cover;flex-shrink:0;margin-right:8px" onerror="this.style.display='none'">`:
                `<div style="width:38px;height:38px;border-radius:6px;background:#1a1a1a;flex-shrink:0;margin-right:8px;display:flex;align-items:center;justify-content:center;font-size:.9rem">📷</div>`}
              <div style="flex:1;min-width:0">
                <div style="font-size:.72rem;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${rows.map(r=>r.acc_name).join(' · ')}</div>
                <div style="font-size:.63rem;color:var(--t3)">publiée ${pubAt} · expire ${expAt}</div>
              </div>
              <div style="text-align:right;flex-shrink:0">
                <div class="live-views-num">${totalV.toLocaleString('fr-FR')}</div>
                <div style="font-size:.6rem;color:var(--t3)">vues${totalR>0?' · '+totalR+' ❤️':''}</div>
              </div>
            </div>`;
          });
          if(errorAccs.length){
            liveHtml+=`<div style="font-size:.62rem;color:#555;padding:4px 8px">⚠️ ${errorAccs.length} compte${errorAccs.length>1?'s':''} inaccessible${errorAccs.length>1?'s':''} (session expirée ?)</div>`;
          }
          liveHtml+='</div></div>';
        } else if(errorAccs.length){
          liveHtml=`<div style="font-size:.68rem;color:#f87171;padding:8px 10px;background:rgba(248,113,113,.08);border-radius:8px;margin-bottom:12px">⚠️ Impossible de récupérer les vues live — ${errorAccs.length} compte${errorAccs.length>1?'s':''} inaccessible${errorAccs.length>1?'s':''} (session Telegram expirée ?)</div>`;
        } else {
          liveHtml=`<div style="font-size:.7rem;color:var(--t3);padding:6px 0 12px">🌙 Aucune story active en ce moment</div>`;
        }
      }

      if(!days.length){
        el.innerHTML=liveHtml+'<div class="empty"><div class="empty-ico">📊</div>Aucune story envoyée pour l\'instant</div>';
      } else {
        let html=liveHtml;
        days.forEach(day=>{
          const daySt=byDayMap[day];
          const dayViews=daySt.reduce((s,x)=>s+x.accounts.reduce((a,b)=>a+(b.views||0),0),0);
          const dayAccCount=daySt.reduce((s,x)=>s+x.accounts.length,0);
          html+=`<div style="margin-bottom:22px">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              <div style="font-size:.82rem;font-weight:800;text-transform:capitalize;color:var(--t1)">${dayLabel(day)}</div>
              <div style="flex:1;height:1px;background:var(--b1)"></div>
              <div style="font-size:.68rem;color:var(--t3);white-space:nowrap">${daySt.length} story${daySt.length>1?'s':''} · ${dayViews.toLocaleString('fr-FR')} vues · ${dayAccCount} envois</div>
            </div>
            <div style="display:flex;flex-direction:column;gap:8px">`;
          daySt.forEach(s=>{
            const thumb=s.filename?`<img src="/uploads/${s.filename}" class="stat-thumb" onerror="this.style.display='none'">`
              :`<div class="stat-thumb" style="background:linear-gradient(135deg,#1a1a2e,#0d1b2a);display:flex;align-items:center;justify-content:center"><svg width="28" height="28" viewBox="0 0 24 24" fill="rgba(255,255,255,.4)"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg></div>`;
            const stViews=s.accounts.reduce((a,b)=>a+(b.views||0),0);
            const stReact=s.accounts.reduce((a,b)=>a+(b.reactions||0),0);
            const hasViews=s.accounts.some(a=>a.views!=null);
            html+=`<div class="stat-card" style="flex-direction:column;align-items:stretch;padding:12px 14px">
              <div style="display:flex;gap:12px;align-items:flex-start">
                ${thumb}
                <div style="flex:1;min-width:0">
                  ${s.playlist_name?`<div style="font-size:.62rem;color:var(--purple);font-weight:700;margin-bottom:3px">${s.playlist_name}</div>`:''}
                  <div style="font-size:.72rem;color:var(--t3);margin-bottom:6px">📅 ${fmt(s.scheduled_at)}</div>
                  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:baseline">
                    <div class="stat-views-big">${hasViews?stViews.toLocaleString('fr-FR'):'—'}<span>vue${stViews>1?'s':''}</span></div>
                    ${stReact>0?`<div style="font-size:1rem;font-weight:800;color:#f472b6">${stReact.toLocaleString('fr-FR')}<span style="font-size:.6rem;color:var(--t2);margin-left:2px">likes</span></div>`:''}
                  </div>
                </div>
              </div>
              ${s.accounts.length>1?`<div style="margin-top:10px;display:flex;flex-direction:column;gap:4px;border-top:1px solid var(--b1);padding-top:8px">
                ${s.accounts.map(a=>{
                  const av=a.views||0; const ar=a.reactions||0; const af=a.forwards||0;
                  const bar=hasViews&&stViews>0?Math.round((av/stViews)*100):0;
                  return `<div style="display:flex;align-items:center;gap:8px">
                    <div style="font-size:.72rem;color:var(--t2);width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex-shrink:0">${a.acc_name}</div>
                    <div class="bar-track" style="flex:1"><div class="bar-fill" style="width:${bar}%;background:var(--purple)"></div></div>
                    <div style="font-size:.7rem;font-weight:700;color:var(--t1);width:36px;text-align:right;flex-shrink:0">${a.views!=null?av.toLocaleString('fr-FR'):'—'}</div>
                    ${ar>0?`<div style="font-size:.65rem;color:#f472b6;flex-shrink:0">+${ar}❤️</div>`:''}
                  </div>`;
                }).join('')}
              </div>`:''}
              ${!hasViews?`<div style="font-size:.65rem;color:#555;margin-top:6px;border-top:1px solid var(--b1);padding-top:6px">⏳ Vues pas encore sauvegardées — elles se sauvegardent automatiquement pendant les 48h suivant l'envoi</div>`:''}
            </div>`;
          });
          html+='</div></div>';
        });
        el.innerHTML=html;
      }
    } else {
      // S'assurer que snapAccounts est chargé pour afficher les usernames
      // Charger les vraies données OneUp Analytics
      el.innerHTML='<div class="empty"><div class="empty-ico">⏳</div>Chargement des données Snapchat…</div>';
      const ouAnalytics=await fetch('/api/snap/oneup-analytics').then(r=>r.json()).catch(()=>null);
      if(ouAnalytics&&ouAnalytics.accounts){
        _renderSnapOneUpFull(el, ouAnalytics.accounts);
        // Totaux pour l'overview
        let totalPosts=0;
        ouAnalytics.accounts.forEach(acc=>{
          if(acc.posts&&acc.posts.success) totalPosts+=(acc.posts.data.posts||[]).length;
        });
        document.getElementById('sovViews').textContent=totalPosts||'—';
        document.getElementById('sovViewsLbl').textContent='Posts publiés';
      } else {
        // Fallback données locales
        if(!snapAccounts.length) await loadSnapAccounts();
        let snapFiltered=_snapScheduled.filter(s=>inDateRange(s.scheduled_at));
        if(!snapFiltered.length&&_statsDateRange!=='all') snapFiltered=_snapScheduled;
        _renderSnapLocalStats(el, snapFiltered, false);
      }
    }
    // Last update timestamp
    const lu=document.getElementById('statsLastUpdate');
    if(lu)lu.textContent='Màj '+new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  }catch(e){
    el.innerHTML=`<div class="empty" style="color:#f87171">Erreur : ${e.message}</div>`;
  }finally{
    if(btn)btn.classList.remove('btn-spinning');
  }
}
function _renderSnapLocalStats(el, snapFiltered, fallback){
  const snap=snapFiltered.filter(s=>s.status==='done'||s.status==='partial'||s.status==='pending');
  if(!snap.length){
    el.innerHTML='<div class="empty"><div class="empty-ico">👻</div>Aucune donnée Snapchat disponible</div>';
    return;
  }
  // Map id → username depuis snapAccounts
  const accMap={};
  (snapAccounts||[]).forEach(a=>accMap[a.id]=a.username);

  function getAccNames(s){
    // Spotlight a déjà username directement
    if(s.username) return[s.username];
    if(s.account_id) return[accMap[s.account_id]||s.account_id];
    if(s.account_ids&&s.account_ids.length) return s.account_ids.map(id=>accMap[id]||id);
    return[];
  }

  function getThumbUrl(s){
    // Utiliser cloudinary_url pour générer une miniature (premier frame)
    if(s.cloudinary_url){
      return s.cloudinary_url.replace('/video/upload/','/video/upload/so_0,w_120,h_200,c_fill,f_jpg/').replace(/\.(mp4|mov|avi|mkv|m4v|webm)$/i,'.jpg');
    }
    if(s.filename) return '/uploads/'+s.filename;
    return null;
  }

  const byDay={};
  snap.forEach(s=>{
    const day=(s.scheduled_at||'').slice(0,10)||'unknown';
    if(!byDay[day])byDay[day]=[];
    byDay[day].push(s);
  });
  const days=Object.keys(byDay).sort().reverse();
  const todayStr=new Date().toISOString().slice(0,10);
  const yestStr=new Date(Date.now()-86400000).toISOString().slice(0,10);
  function dayLabel(d){
    if(d===todayStr)return"Aujourd'hui";
    if(d===yestStr)return'Hier';
    if(d==='unknown')return'Date inconnue';
    const dt=new Date(d);
    return (dt>new Date()?'📅 ':'')+dt.toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'})+(dt>new Date()?' (à venir)':'');
  }
  let html=fallback?`<div style="background:#1a1200;border:1px solid #3a2a00;border-radius:8px;padding:8px 12px;margin-bottom:12px;font-size:.73rem;color:#fbbf24">
    ⚠️ Aucun contenu dans la période — affichage de tout l'historique disponible
  </div>`:'';

  days.forEach(day=>{
    const items=byDay[day];
    html+=`<div style="margin-bottom:20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <div style="font-size:.82rem;font-weight:800;text-transform:capitalize;color:var(--t1)">${dayLabel(day)}</div>
        <div style="flex:1;height:1px;background:var(--b1)"></div>
        <div style="font-size:.68rem;color:var(--t3)">${items.length} post${items.length>1?'s':''}</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">`;
    items.forEach(s=>{
      const isSpotlight=s._type==='spotlight';
      const accs=getAccNames(s);
      const accHtml=accs.length
        ?accs.map(u=>`<span style="background:#ffffff10;border-radius:5px;padding:2px 7px;font-size:.7rem;font-weight:700;color:var(--t1)">@${u}</span>`).join(' ')
        :'';
      const badge=isSpotlight
        ?`<span style="background:#f5c51825;color:#f5c518;border-radius:4px;font-size:.6rem;font-weight:700;padding:1px 6px">SPOTLIGHT</span>`
        :`<span style="background:#2CA5E020;color:#2CA5E0;border-radius:4px;font-size:.6rem;font-weight:700;padding:1px 6px">STORY</span>`;
      const statusBadge=s.status==='done'?'<span style="color:var(--green);font-size:.65rem">✅ Envoyé</span>'
        :s.status==='partial'?'<span style="color:#f59e0b;font-size:.65rem">⚡ Partiel</span>'
        :'<span style="color:var(--t3);font-size:.65rem">🕐 Programmé</span>';
      const thumbUrl=getThumbUrl(s);
      const thumb=thumbUrl
        ?`<img class="stat-thumb" src="${thumbUrl}" onerror="this.outerHTML='<div class=\\'stat-thumb\\' style=\\'background:#111;display:flex;align-items:center;justify-content:center;font-size:22px\\'>${isSpotlight?'🎬':'👻'}</div>'">`
        :`<div class="stat-thumb" style="background:#111;display:flex;align-items:center;justify-content:center;font-size:22px">${isSpotlight?'🎬':'👻'}</div>`;
      html+=`<div class="stat-card">
        ${thumb}
        <div class="stat-info" style="flex:1;min-width:0">
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:5px">${badge}${statusBadge}</div>
          <div style="margin-bottom:5px;display:flex;flex-wrap:wrap;gap:4px">${accHtml}</div>
          <div class="stat-date">🕐 ${fmt(s.scheduled_at)}</div>
          <div style="display:flex;gap:16px;align-items:baseline;margin-top:5px;flex-wrap:wrap">
            <div style="font-size:1.3rem;font-weight:800;color:#555;line-height:1">—<span style="font-size:.65rem;color:#444;font-weight:500;margin-left:4px">vues (non dispo via API)</span></div>
          </div>
        </div>
      </div>`;
    });
    html+='</div></div>';
  });
  el.innerHTML=html;
}

function _renderSnapOneUpFull(el, accounts){
  const allPosts=[];
  const warnings=[];
  accounts.forEach(acc=>{
    if(acc.posts_error&&acc.posts_error.includes('expired')){
      warnings.push(`⚠️ <b>@${acc.username}</b> — token expiré, reconnecte ce compte dans OneUp`);
    }
    // Construire un Set des IDs Spotlight pour ce compte
    const spotlightIds=new Set();
    if(acc.spotlight&&acc.spotlight.success){
      (acc.spotlight.data.posts||[]).forEach(p=>spotlightIds.add(p.id));
    }
    if(acc.posts&&acc.posts.success){
      (acc.posts.data.posts||[]).forEach(p=>{
        allPosts.push({...p, _username: acc.username, _isSpotlight: spotlightIds.has(p.id)});
      });
    }
  });

  if(!allPosts.length&&!warnings.length){
    el.innerHTML='<div class="empty"><div class="empty-ico">👻</div>Aucun post Snapchat trouvé</div>';
    return;
  }

  const byDay={};
  allPosts.forEach(p=>{
    const day=(p.published_at||'').slice(0,10)||'unknown';
    if(!byDay[day])byDay[day]=[];
    byDay[day].push(p);
  });
  const days=Object.keys(byDay).sort().reverse();
  const todayStr=new Date().toISOString().slice(0,10);
  const yestStr=new Date(Date.now()-86400000).toISOString().slice(0,10);

  function dayLbl(d){
    if(d===todayStr)return"Aujourd'hui";
    if(d===yestStr)return'Hier';
    if(d==='unknown')return'Date inconnue';
    return new Date(d).toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'});
  }

  const nSpotlight=allPosts.filter(p=>p._isSpotlight).length;
  const nStory=allPosts.length-nSpotlight;

  let html='';
  if(warnings.length){
    html+=`<div style="background:#1a0a0a;border:1px solid #5a1a1a;border-radius:8px;padding:8px 12px;margin-bottom:12px;font-size:.73rem;color:#f87171">${warnings.join('<br>')}</div>`;
  }
  html+=`<div style="font-size:.7rem;color:var(--t3);margin-bottom:10px;padding:5px 8px;background:var(--c2);border-radius:6px">
    📡 Données OneUp — ${nStory} story${nStory>1?'s':''}${nSpotlight?` · ${nSpotlight} spotlight` :''} · vues non exposées par l'API Snapchat
  </div>`;

  days.forEach(day=>{
    const items=byDay[day];
    html+=`<div style="margin-bottom:20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <div style="font-size:.82rem;font-weight:800;text-transform:capitalize;color:var(--t1)">${dayLbl(day)}</div>
        <div style="flex:1;height:1px;background:var(--b1)"></div>
        <div style="font-size:.68rem;color:var(--t3)">${items.length} post${items.length>1?'s':''}</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">`;
    items.forEach(p=>{
      const screenshots=p.stats&&p.stats.screenshots||0;
      const shares=p.stats&&p.stats.shares||0;
      const thumb=p.thumbnail_url
        ?`<img class="stat-thumb" src="${p.thumbnail_url}" onerror="this.style.background='#111'">`
        :`<div class="stat-thumb" style="background:#111;display:flex;align-items:center;justify-content:center;font-size:22px">👻</div>`;
      const timeStr=p.published_at?p.published_at.slice(11,16):'';
      const badge=p._isSpotlight
        ?`<span style="background:#ff660025;color:#f97316;border-radius:4px;font-size:.6rem;font-weight:700;padding:1px 6px">SPOTLIGHT</span>`
        :`<span style="background:#FFFC0025;color:#d4c200;border-radius:4px;font-size:.6rem;font-weight:700;padding:1px 6px">STORY</span>`;
      html+=`<div class="stat-card">
        ${thumb}
        <div class="stat-info" style="flex:1;min-width:0">
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:4px">
            ${badge}
            <span style="background:#ffffff10;border-radius:5px;padding:2px 7px;font-size:.7rem;font-weight:700;color:var(--t1)">@${p._username}</span>
            ${timeStr?`<span style="font-size:.63rem;color:var(--t3)">🕐 ${timeStr}</span>`:''}
          </div>
          <div style="display:flex;gap:14px;align-items:baseline;margin-top:6px;flex-wrap:wrap">
            <div style="font-size:.72rem;color:#555;font-style:italic">vues N/A — API Snap</div>
            ${screenshots?`<div style="font-size:.85rem;font-weight:700;color:var(--t2)">${screenshots}<span style="font-size:.6rem;margin-left:3px">📸</span></div>`:''}
            ${shares?`<div style="font-size:.85rem;font-weight:700;color:var(--t2)">${shares}<span style="font-size:.6rem;margin-left:3px">↗</span></div>`:''}
          </div>
          ${p.permalink?`<a href="${p.permalink}" target="_blank" style="font-size:.63rem;color:#6d28d9;margin-top:4px;display:block;text-decoration:none">Voir sur Snapchat ↗</a>`:''}
        </div>
      </div>`;
    });
    html+='</div></div>';
  });
  el.innerHTML=html;
}

function _renderSnapOneUpStats(el,posts){
  if(!posts.length){
    el.innerHTML='<div class="empty"><div class="empty-ico">👻</div>Aucune publication trouvée sur One Up pour cette période</div>';
    return;
  }
  el.innerHTML=posts.map(p=>{
    const dt=p.scheduled_date_time||p.created_at||'';
    const img=p.image_url||p.thumbnail_url||p.media_url||'';
    const accs=(p.social_network_ids||[]).length||(p.accounts||[]).length||1;
    const views=p.views!=null?Number(p.views):null;
    const viewsHtml=views!=null
      ?`<div class="stat-views-big">${views.toLocaleString('fr-FR')}<span>vue${views>1?'s':''}</span></div>`
      :`<div style="font-size:.63rem;color:#555;margin-top:3px">Vues non exposées par One Up</div>`;
    return `<div class="stat-card">
      ${img?`<img class="stat-thumb" src="${img}" onerror="this.style.opacity='.15'">`
           :`<div class="stat-thumb" style="background:#111;display:flex;align-items:center;justify-content:center;font-size:22px">👻</div>`}
      <div class="stat-info">
        <div class="stat-date">🕐 ${dt?fmt(dt):'—'}</div>
        ${viewsHtml}
        <div style="font-size:.68rem;color:var(--t2);margin-top:4px">${accs} compte(s) · One Up</div>
      </div>
    </div>`;
  }).join('');
}

document.getElementById('btnRefreshStats').addEventListener('click',loadStats);
setInterval(()=>{if(currentPage==='stats')loadStats();},60000);

// ── Revenue ────────────────────────────────────────────────────────────────
let _revenues=[];
async function loadRevenue(){
  const r=await fetch('/api/revenue');
  _revenues=await r.json();
  renderRevenue();
}
function renderRevenue(){
  const total=_revenues.reduce((s,e)=>s+e.amount,0);
  const now=new Date();
  const monthStr=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
  const monthRev=_revenues.filter(e=>e.date.startsWith(monthStr)).reduce((s,e)=>s+e.amount,0);
  const days=new Set(_revenues.map(e=>e.date)).size||1;
  const avg=total/days;
  const fmt2=v=>v.toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})+' €';
  const el=id=>document.getElementById(id);
  if(el('revTotal'))el('revTotal').textContent=fmt2(total);
  if(el('revMonth'))el('revMonth').textContent=fmt2(monthRev);
  if(el('revAvg'))el('revAvg').textContent=fmt2(avg);
  if(el('revTx'))el('revTx').textContent=_revenues.length;
  if(el('revLastUpdate'))el('revLastUpdate').textContent='Màj '+new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
  // Chart
  setTimeout(()=>{
    const byDay={};
    _revenues.forEach(e=>{byDay[e.date]=(byDay[e.date]||0)+e.amount;});
    const labels=Object.keys(byDay).sort();
    const series=labels.length?[{name:'Revenus (€)',values:labels.map(d=>byDay[d]||0)}]:[];
    const canvas=el('revCanvas');const tip=el('revTooltip');
    const sub=el('revChartSub');
    if(sub)sub.textContent=labels.length+' jours · '+fmt2(total)+' total';
    if(canvas){canvas._panOffset=Math.max(0,labels.length-LC_WIN);lcDrawChart(canvas,tip,series,labels);}
  },100);
  // List
  const list=el('revList');
  if(!list)return;
  if(!_revenues.length){list.innerHTML='<div class="empty"><div class="empty-ico">💵</div>Aucun revenu enregistré</div>';return;}
  list.innerHTML=[..._revenues].sort((a,b)=>b.date.localeCompare(a.date)).map(e=>`
    <div style="background:var(--c2);border:1px solid var(--b1);border-radius:10px;padding:12px 14px;margin-bottom:8px;display:flex;align-items:center;gap:12px">
      <div style="font-size:1.6rem">💵</div>
      <div style="flex:1;min-width:0">
        <div style="font-size:.9rem;font-weight:800;color:#22c55e">${e.amount.toLocaleString('fr-FR',{minimumFractionDigits:2})} €</div>
        <div style="font-size:.76rem;color:var(--t2);margin-top:2px">${e.source||'—'}${e.note?' · '+e.note:''}</div>
        <div style="font-size:.68rem;color:var(--t3);margin-top:1px">📅 ${e.date}</div>
      </div>
      <button class="btn btn-xs" style="background:#3a1a1a;color:#f87171;border:1px solid #5a2020" onclick="deleteRevenue('${e.id}')">🗑</button>
    </div>`).join('');
}
async function addRevenue(){
  const date=document.getElementById('revDate').value;
  const amount=parseFloat(document.getElementById('revAmount').value||0);
  const source=document.getElementById('revSource').value.trim();
  const note=document.getElementById('revNote').value.trim();
  if(!date||!amount){toast('Date et montant requis','err');return;}
  await fetch('/api/revenue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date,amount,source,note})});
  document.getElementById('revAmount').value='';
  document.getElementById('revSource').value='';
  document.getElementById('revNote').value='';
  await loadRevenue();
  toast('Revenu ajouté');
}
async function deleteRevenue(id){
  if(!confirm('Supprimer cette entrée ?'))return;
  await fetch('/api/revenue/'+id,{method:'DELETE'});
  await loadRevenue();
  toast('Supprimé');
}
// Pre-fill today's date in revenue form
window.addEventListener('DOMContentLoaded',()=>{
  const d=document.getElementById('revDate');
  if(d)d.value=new Date().toISOString().slice(0,10);

  // ── Stripe success redirect ───────────────────────────────────────────────
  const params=new URLSearchParams(window.location.search);
  if(params.get('checkout')==='success'){
    const sid=params.get('sid');
    const pid=params.get('pid');
    if(sid&&pid){
      fetch(`/api/stripe/verify-session?sid=${encodeURIComponent(sid)}&pid=${encodeURIComponent(pid)}`)
        .then(r=>r.json()).then(d=>{
          if(d.ok){
            const info={starter:{badge:'⚡',name:'Starter'},pro:{badge:'🚀',name:'Pro'},business:{badge:'🏢',name:'Business'}}[d.plan]||{};
            const msg=`${info.badge||'✅'} Forfait ${info.name||d.plan} activé ! Bienvenue.`;
            setTimeout(()=>alert(msg),500);
          }
          window.history.replaceState({},'','/');
        }).catch(()=>{window.history.replaceState({},'','/');});
    }
  }
});

// ── Status badge ───────────────────────────────────────────────────────────
async function refreshStatus(){
  try{
    const r=await fetch('/api/status');const s=await r.json();
    document.getElementById('sbDot').className=s.pending?'sb-dot orange':'sb-dot';
    document.getElementById('sbText').textContent=s.pending?`${s.pending} en attente`:`${s.accounts} comptes · ${s.playlists} playlists`;
  }catch{}
}


// ── Snapchat ───────────────────────────────────────────────────────────────
let snapPhotos=[],snapDragSrc=null,snapAccounts=[];
async function loadSnapAccounts(){
  const r=await fetch('/api/snap/accounts');snapAccounts=await r.json();
  const el=document.getElementById('snapAccChecks');
  el.innerHTML=snapAccounts.map(a=>`
    <label class="acc-check sel">
      <input type="checkbox" data-id="${a.id}" checked>
      <img src="/api/social/avatar/snap/${encodeURIComponent(a.username)}"
           style="width:22px;height:22px;border-radius:50%;object-fit:cover;flex-shrink:0"
           onerror="this.style.display='none'">
      <span class="acc-check-name">${a.username}</span>
    </label>`).join('');
  el.querySelectorAll('.acc-check').forEach(l=>{
    const cb=l.querySelector('input');
    cb.addEventListener('change',()=>{l.classList.toggle('sel',cb.checked);updateSnapBtn();});
  });
  updateSnapBtn();
  // Mettre à jour les checkboxes Spotlight aussi (même liste de comptes)
  renderSplAccChecks();
}
function getSnapSelIds(){return [...document.querySelectorAll('#snapAccChecks input:checked')].map(i=>i.dataset.id);}
function updateSnapBtn(){document.getElementById('snapBtnSchedule').disabled=!(snapPhotos.length>0&&getSnapSelIds().length>0);}
const snapUz=document.getElementById('snapUz'),snapFi=document.getElementById('snapFi');
snapUz.addEventListener('dragover',e=>{e.preventDefault();snapUz.classList.add('over');});
snapUz.addEventListener('dragleave',()=>snapUz.classList.remove('over'));
snapUz.addEventListener('drop',e=>{e.preventDefault();snapUz.classList.remove('over');uploadSnapFiles([...e.dataTransfer.files]);});
snapFi.addEventListener('change',()=>{uploadSnapFiles([...snapFi.files]);snapFi.value='';});
async function uploadSnapFiles(files){
  const valids=files.filter(f=>f.type.startsWith('image/')||f.type.startsWith('video/'));
  if(!valids.length){toast('Aucun fichier valide','err');return;}
  toast(`Upload de ${valids.length} fichier(s)...`);
  let n=0;
  for(const f of valids){
    const fd=new FormData();fd.append('file',f);
    try{
      const r=await fetch('/api/upload',{method:'POST',body:fd});
      if(!r.ok)continue;
      const d=await r.json();
      const isVid=f.type.startsWith('video/');
      snapPhotos.push({filename:d.filename,url:d.url,dt:defDt((snapPhotos.length+1)*3600000),isVideo:isVid,analyse:null});
      n++;
    }catch{}
  }
  renderSnapPhotos();
  if(n){
    toast(`${n} fichier(s) ajouté(s)`,'ok');
    document.getElementById('snapAnalyzeBar').style.display='block';
  }
}

// ─── Analyse IA ─────────────────────────────────────────────────────────────
const AMBIANCE_EMOJI={detente:'😌',sortie:'🎉',apero:'🍺',repas:'🍽️',sport:'💪',plage:'🏖️',maison:'🏠',fete:'🎊',autre:'📸'};
const MOMENT_LABEL={matin:'🌅 Matin',apres_midi:'☀️ Après-midi',soir:'🌆 Soir',nuit:'🌙 Nuit',interieur_neutre:'🏠 Intérieur'};

document.getElementById('snapBtnAnalyze').addEventListener('click',async()=>{
  if(!snapPhotos.length)return;
  const btn=document.getElementById('snapBtnAnalyze');
  const status=document.getElementById('snapAnalyzeStatus');
  btn.disabled=true;btn.innerHTML='⏳ Analyse en cours...';
  status.textContent=`0 / ${snapPhotos.length} photos analysées`;
  try{
    const filenames=snapPhotos.map(p=>p.filename);
    const r=await fetch('/api/snap/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filenames})});
    if(!r.ok)throw new Error('Analyse échouée');
    const results=await r.json();
    results.forEach(res=>{
      const idx=snapPhotos.findIndex(p=>p.filename===res.filename);
      if(idx>=0){snapPhotos[idx].dt=res.suggested_dt;snapPhotos[idx].analyse=res.analyse;}
    });
    status.textContent=`✅ ${results.length} photos analysées — horaires mis à jour, tu peux corriger ci-dessous`;
    renderSnapPhotos();
    toast('Analyse IA terminée — vérifie les horaires','ok');
  }catch(e){
    status.textContent='⚠️ Erreur analyse — horaires manuels utilisés';
    toast('Erreur analyse IA','err');
  }finally{btn.disabled=false;btn.innerHTML='&#x1F9E0; Ré-analyser avec l\'IA';}
});

function renderSnapPhotos(){
  const list=document.getElementById('snapPlist'),noP=document.getElementById('snapNoP');
  list.innerHTML='';noP.style.display=snapPhotos.length?'none':'block';updateSnapBtn();
  if(snapPhotos.length){document.getElementById('snapAnalyzeBar').style.display='block';document.getElementById('snapBtnSavePl').disabled=false;}
  else{document.getElementById('snapBtnSavePl').disabled=true;}
  // Grille de cartes (style preview_planning.py)
  list.style.cssText='display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;margin-top:10px';
  snapPhotos.forEach((p,i)=>{
    const card=document.createElement('div');
    card.style.cssText='background:#111;border:1px solid #222;border-radius:10px;overflow:hidden;position:relative';
    // Aperçu
    const media=p.isVideo
      ?`<div style="height:213px;background:#000;display:flex;align-items:center;justify-content:center;font-size:36px">&#x1F3AC;</div>`
      :`<img src="${p.url}" style="width:100%;height:213px;object-fit:cover;display:block">`;
    // Badge IA
    let iaBadge='';
    if(p.analyse){
      const a=p.analyse;const emojis=[];
      if(a.fait_la_fete||a.alcool_visible)emojis.push('🍺');
      else if(a.ambiance&&AMBIANCE_EMOJI[a.ambiance])emojis.push(AMBIANCE_EMOJI[a.ambiance]);
      if(a.fatigue)emojis.push('😴');if(a.nourriture_presente)emojis.push('🍽️');
      const label=MOMENT_LABEL[a.moment_journee]||'';
      iaBadge=`<div style="font-size:.6rem;color:#a5b4fc;margin:2px 0">${emojis.join('')} ${label}</div>`;
    }
    card.innerHTML=`
      ${media}
      <div style="padding:7px 8px">
        <div style="font-size:.65rem;color:#666;word-break:break-all;margin-bottom:5px">${p.filename}</div>
        ${iaBadge}
        <input type="datetime-local" data-idx="${i}" value="${p.dt}"
          style="width:100%;background:#0a0a0a;color:#fff;border:1px solid #2d323d;border-radius:6px;padding:6px 7px;font-size:.75rem;color-scheme:dark">
      </div>
      <button data-idx="${i}" style="position:absolute;top:5px;right:5px;background:rgba(0,0,0,.6);border:none;color:#fff;border-radius:50%;width:22px;height:22px;font-size:12px;cursor:pointer;display:flex;align-items:center;justify-content:center">&#x2715;</button>`;
    card.querySelector('input[type=datetime-local]').addEventListener('change',e=>{snapPhotos[+e.target.dataset.idx].dt=e.target.value;});
    card.querySelector('button').addEventListener('click',e=>{e.stopPropagation();snapPhotos.splice(i,1);renderSnapPhotos();if(!snapPhotos.length)document.getElementById('snapAnalyzeBar').style.display='none';});
    list.appendChild(card);
  });
}
document.getElementById('snapBtnClear').addEventListener('click',()=>{snapPhotos=[];renderSnapPhotos();toast('Vide');document.getElementById('snapAnalyzeBar').style.display='none';});

function loadSnapPlannings(){if(currentPage==='playlists')loadPlaylists();}

document.getElementById('snapBtnSavePl').addEventListener('click',async()=>{
  if(!snapPhotos.length)return;
  const name=prompt('Nom du planning :','Planning '+(new Date().toLocaleDateString('fr-FR')));
  if(!name)return;
  const snaps=snapPhotos.map(p=>({filename:p.filename,url:p.url,dt:p.dt,isVideo:p.isVideo,analyse:p.analyse||null}));
  const r=await fetch('/api/snap/plannings',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,photos:snaps})});
  if(r.ok){toast(`Planning "${name}" sauvegardé dans Médias`,'ok');loadPlaylists();}
  else toast('Erreur sauvegarde','err');
});
document.getElementById('snapBtnSchedule').addEventListener('click',async()=>{
  const accIds=getSnapSelIds();
  if(!snapPhotos.length||!accIds.length)return;
  const btn=document.getElementById('snapBtnSchedule');
  btn.disabled=true;btn.textContent='Envoi en cours...';
  try{
    const r=await fetch('/api/snap/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({photos:snapPhotos.map(p=>({filename:p.filename,scheduled_at:p.dt})),account_ids:accIds})});
    if(!r.ok)throw new Error((await r.json()).detail);
    const d=await r.json();
    toast(`${d.count} post(s) Snapchat programmes !`,'ok');
    snapPhotos=[];renderSnapPhotos();loadSnapScheduled();
  }catch(e){toast(`Erreur: ${e.message}`,'err');}
  finally{btn.disabled=!snapPhotos.length;btn.innerHTML='&#x1F47B; Programmer';}
});
async function loadSnapScheduled(){
  const r=await fetch('/api/snap/scheduled');const list=await r.json();
  const el=document.getElementById('slist');
  const b=document.getElementById('badgeSnap');
  b.textContent=list.length;b.style.display=list.length?'':'none';
  document.getElementById('snapMPending').textContent=list.filter(s=>s.status==='pending').length;
  document.getElementById('snapMDone').textContent=list.filter(s=>s.status==='done').length;
  document.getElementById('snapMErr').textContent=list.filter(s=>s.status==='error').length;
  if(!list.length){el.innerHTML='<div class="empty"><div class="empty-ico">&#x1F47B;</div>Aucun post Snapchat programme</div>';return;}
  const bmap={pending:'bp En attente',done:'bd Envoye',error:'be Erreur',partial:'bpar Partiel'};
  const _ssp={pending:0,posting:0,partial:1,error:1,done:2};
  const _snapSorted=list.slice().sort((a,b)=>{const pa=_ssp[a.status]??1,pb=_ssp[b.status]??1;if(pa!==pb)return pa-pb;return a.scheduled_at.localeCompare(b.scheduled_at);});
  const _snapToShow=_schedFilter==='done'
    ?_snapSorted.filter(s=>s.status==='done').reverse().slice(0,100)
    :_snapSorted.filter(s=>s.status!=='done');
  if(!_snapToShow.length){el.innerHTML=`<div class="empty"><div class="empty-ico">&#x1F47B;</div>${_schedFilter==='done'?'Aucun post publié':'Aucun post en attente'}</div>`;return;}
  el.innerHTML=_snapToShow.map(s=>{
    const[bc,bl]=(bmap[s.status]||'bp ?').split(' ');
    const accsHtml=(()=>{
      const res=s.results||{};
      if(Object.keys(res).length){
        return Object.values(res).map(rv=>`<span style="font-size:.6rem;color:${rv.status==='done'?'var(--green)':'var(--red)'}">@${rv.username}</span>`).join(' ');
      }
      return (s.account_ids||[]).map(id=>{const a=snapAccounts.find(x=>x.id===id);return`<span style="font-size:.6rem;color:#888">@${a?a.username:id.slice(0,8)}</span>`;}).join(' ');
    })();
    return `<div class="sitem">
      <img class="sthumb" src="/uploads/${s.filename}" onerror="this.style.opacity='.2'">
      <div class="sinfo"><div class="sdate">&#x1F4C5; ${fmt(s.scheduled_at)}</div><div style="margin-top:2px;display:flex;gap:3px;flex-wrap:wrap">${accsHtml||'---'}</div></div>
      <div class="sright"><span class="badge ${bc}">${bl}</span>
        <button class="sdel2" data-id="${s.id}">&#x2715;</button></div>
    </div>`;
  }).join('');
  el.querySelectorAll('.sdel2').forEach(b=>b.addEventListener('click',async()=>{
    if(!confirm('Supprimer ?'))return;
    await fetch(`/api/snap/scheduled/${b.dataset.id}`,{method:'DELETE'});toast('Supprime');loadSnapScheduled();
  }));
}
// Tout supprimer (pending uniquement)
document.getElementById('btnSnapDeleteAll').addEventListener('click',async()=>{
  const pending=document.getElementById('snapMPending').textContent;
  if(!confirm(`Supprimer toutes les publications Snapchat en attente (${pending}) ?\nCette action est irréversible.`))return;
  const r=await fetch('/api/snap/scheduled',{method:'DELETE'});
  if(r.ok){
    const d=await r.json();
    toast(`🗑️ ${d.deleted} publication(s) supprimée(s)`,'ok');
    loadSnapScheduled();
  } else toast('Erreur suppression','err');
});
// snapBtnRefresh removed — list is now in right panel
// snap click handled in nav


// ── Instagram ─────────────────────────────────────────────────────────────────
let igPhotos=[],igAccounts=[];

async function loadIgAccounts(){
  igAccounts=await fetch('/api/instagram/accounts').then(r=>r.json()).catch(()=>[]);
  document.getElementById('igMAccounts').textContent=igAccounts.length||'—';
  const el=document.getElementById('igAccChecks');
  if(!igAccounts.length){el.innerHTML='<div class="no-acc-warn">Aucun compte Instagram — configure-les dans Réglages → profil → instagram_accounts</div>';return;}
  el.innerHTML=igAccounts.map(a=>`
    <label class="acc-check sel">
      <input type="checkbox" data-id="${a.id}" checked>
      <img src="/api/social/avatar/ig/${encodeURIComponent(a.username)}?uid=${encodeURIComponent(a.id)}"
           style="width:22px;height:22px;border-radius:50%;object-fit:cover;flex-shrink:0"
           onerror="this.style.display='none'">
      <span class="acc-check-name">@${a.username}</span>
    </label>`).join('');
  el.querySelectorAll('input[type=checkbox]').forEach(cb=>cb.addEventListener('change',updateIgBtn));
  updateIgBtn();
}

function getIgAccIds(){return[...document.querySelectorAll('#igAccChecks input:checked')].map(x=>x.dataset.id);}
function updateIgBtn(){
  const ok=igPhotos.length>0&&getIgAccIds().length>0;
  document.getElementById('igBtnSchedule').disabled=!ok;
  document.getElementById('igBtnSavePl').disabled=igPhotos.length===0;
}

async function loadIgScheduled(){
  const list=await fetch('/api/instagram/scheduled').then(r=>r.json()).catch(()=>[]);
  const el=document.getElementById('igRpList');
  const pending=list.filter(s=>s.status==='pending').length;
  const done=list.filter(s=>s.status==='done').length;
  const err=list.filter(s=>s.status==='error'||s.status==='partial').length;
  document.getElementById('igMPending').textContent=pending||'—';
  document.getElementById('igMDone').textContent=done||'—';
  document.getElementById('igMErr').textContent=err||'—';
  if(!list.length){el.innerHTML='<div class="empty"><div class="empty-ico">📸</div>Aucun post programmé</div>';return;}
  const _igSp={pending:0,posting:0,partial:1,error:1,done:2};
  const _igSorted=list.slice().sort((a,b)=>{const pa=_igSp[a.status]??1,pb=_igSp[b.status]??1;if(pa!==pb)return pa-pb;return a.scheduled_at.localeCompare(b.scheduled_at);});
  const _igToShow=_schedFilter==='done'
    ?_igSorted.filter(s=>s.status==='done').reverse().slice(0,100)
    :_igSorted.filter(s=>s.status!=='done');
  if(!_igToShow.length){el.innerHTML=`<div class="empty"><div class="empty-ico">📸</div>${_schedFilter==='done'?'Aucun post publié':'Aucun post en attente'}</div>`;return;}
  el.innerHTML=_igToShow.map(s=>{
    const accNames=(s.account_ids||[]).map(id=>{const a=igAccounts.find(x=>x.id===id);return a?'@'+a.username:id;}).join(', ');
    const statusColor={pending:'var(--yellow)',done:'var(--green)',error:'var(--red)',partial:'orange',posting:'var(--purple)'}[s.status]||'var(--t3)';
    return `<div class="sitem">
      <img src="/uploads/${s.filename}" class="sthumb" onerror="this.style.opacity='.2'" style="width:64px;height:84px;object-fit:cover;border-radius:9px;flex-shrink:0">
      <div class="sinfo">
        <div style="font-size:.82rem;font-weight:700">${fmt(s.scheduled_at)}</div>
        <div style="font-size:.7rem;color:var(--t3);margin-top:2px">${accNames}</div>
        ${s.caption?`<div style="font-size:.68rem;color:var(--t3);font-style:italic;margin-top:2px">"${s.caption.slice(0,40)}…"</div>`:''}
        <div style="font-size:.68rem;margin-top:4px"><span style="color:${statusColor};font-weight:700">${s.status}</span></div>
      </div>
      <button class="btn btn-xs btn-danger" onclick="deleteIgScheduled('${s.id}')" style="flex-shrink:0;align-self:center">✕</button>
    </div>`;
  }).join('');
}

async function deleteIgScheduled(id){
  if(!confirm('Supprimer ce post programmé ?'))return;
  await fetch(`/api/instagram/scheduled/${id}`,{method:'DELETE'});
  loadIgScheduled();
}

document.getElementById('igFi').addEventListener('change',async function(){
  for(const f of this.files){
    const fd=new FormData();fd.append('file',f);
    const r=await fetch('/api/upload',{method:'POST',body:fd}).catch(()=>null);
    if(r&&r.ok){const d=await r.json();igPhotos.push({filename:d.filename,url:`/uploads/${d.filename}`});}
  }
  renderIgPhotos();this.value='';
});
document.getElementById('igUz').addEventListener('click',()=>document.getElementById('igFi').click());
document.getElementById('igUz').addEventListener('dragover',e=>{e.preventDefault();document.getElementById('igUz').style.borderColor='#833ab4';});
document.getElementById('igUz').addEventListener('dragleave',()=>document.getElementById('igUz').style.borderColor='');
document.getElementById('igUz').addEventListener('drop',async e=>{
  e.preventDefault();document.getElementById('igUz').style.borderColor='';
  for(const f of e.dataTransfer.files){
    const fd=new FormData();fd.append('file',f);
    const r=await fetch('/api/upload',{method:'POST',body:fd}).catch(()=>null);
    if(r&&r.ok){const d=await r.json();igPhotos.push({filename:d.filename,url:`/uploads/${d.filename}`});}
  }
  renderIgPhotos();
});

function renderIgPhotos(){
  const el=document.getElementById('igPlist');
  const noP=document.getElementById('igNoP');
  if(!igPhotos.length){el.innerHTML='';noP.style.display='';updateIgBtn();return;}
  noP.style.display='none';
  el.innerHTML=igPhotos.map((p,i)=>`
    <div class="pitem">
      <img src="${p.url}" class="pthumb">
      <div class="pinfo"><div class="pdt">${p.dt?fmt(p.dt):'—'}</div></div>
      <button class="pdel" onclick="igPhotos.splice(${i},1);renderIgPhotos()">✕</button>
    </div>`).join('');
  updateIgBtn();
}

document.getElementById('igBtnClear').addEventListener('click',()=>{igPhotos=[];renderIgPhotos();toast('Vidé');});

// Mode date Instagram
document.querySelectorAll('input[name=igDateMode]').forEach(r=>{
  r.addEventListener('change',()=>{
    document.getElementById('igDateInput').style.display=r.value==='manual'?'':'none';
  });
});

// Mode date Facebook
document.querySelectorAll('input[name=fbDateMode]').forEach(r=>{
  r.addEventListener('change',()=>{
    document.getElementById('fbDateInput').style.display=r.value==='manual'?'':'none';
  });
});

function _igGetStartDt(offset=0){
  const mode=document.querySelector('input[name=igDateMode]:checked')?.value||'auto';
  if(mode==='manual'){
    const v=document.getElementById('igDateInput').value;
    if(v){const d=new Date(v);d.setMinutes(d.getMinutes()+offset);return _localDtStr(d);}
  }
  const now=new Date();now.setMinutes(now.getMinutes()+5+offset);
  return _localDtStr(now);
}

function _fbGetStartDt(offset=0){
  const mode=document.querySelector('input[name=fbDateMode]:checked')?.value||'auto';
  if(mode==='manual'){
    const v=document.getElementById('fbDateInput').value;
    if(v){const d=new Date(v);d.setMinutes(d.getMinutes()+offset);return _localDtStr(d);}
  }
  const now=new Date();now.setMinutes(now.getMinutes()+5+offset);
  return _localDtStr(now);
}

document.getElementById('igBtnSchedule').addEventListener('click',async()=>{
  const accIds=getIgAccIds();
  const caption=document.getElementById('igCaption').value.trim();
  if(!igPhotos.length||!accIds.length)return;
  let ok=0,err=0,offset=0;
  for(const p of igPhotos){
    const dt=p.dt||_igGetStartDt(offset);
    offset+=accIds.length; // +1 min par compte par photo
    const r=await fetch('/api/instagram/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filename:p.filename,scheduled_at:dt,account_ids:accIds,caption})});
    if(r.ok)ok++;else err++;
  }
  if(ok)toast(`✅ ${ok} post(s) Instagram programmé(s)`,'ok');
  if(err)toast(`❌ ${err} erreur(s)`,'err');
  igPhotos=[];renderIgPhotos();loadIgScheduled();
});

document.getElementById('igBtnSavePl').addEventListener('click',async()=>{
  if(!igPhotos.length)return;
  const name=prompt('Nom de la playlist Instagram :');
  if(!name)return;
  const r=await fetch('/api/ig/plannings',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,photos:igPhotos.map(p=>({filename:p.filename,url:p.url,dt:p.dt||''}))})});
  if(r.ok){toast('Playlist sauvegardée dans Médias','ok');loadPlaylists();}
  else toast('Erreur sauvegarde','err');
});


// ── Hover preview ──────────────────────────────────────────────────────────
const popup=document.getElementById('imgPreview');
const popImg=document.getElementById('imgPreviewImg');
const popDate=document.getElementById('imgPreviewDate');
let popTimer=null;
document.addEventListener('mouseover',e=>{
  const thumb=e.target.closest('.sthumb');
  if(!thumb)return;
  clearTimeout(popTimer);
  const src=thumb.src||thumb.getAttribute('src')||'';
  const dateEl=thumb.closest('.sitem')?.querySelector('.sdate');
  popImg.src=src;
  popDate.textContent=dateEl?dateEl.textContent.replace('📅','').trim():'';
  positionPopup(e);
  popup.classList.add('visible');
});
document.addEventListener('mousemove',e=>{
  if(popup.classList.contains('visible'))positionPopup(e);
});
document.addEventListener('mouseout',e=>{
  if(!e.target.closest('.sthumb'))return;
  clearTimeout(popTimer);
  popTimer=setTimeout(()=>popup.classList.remove('visible'),80);
});
function positionPopup(e){
  const W=window.innerWidth,H=window.innerHeight;
  const pw=190,ph=340;
  let x=e.clientX+18,y=e.clientY-pw/2;
  if(x+pw>W-10)x=e.clientX-pw-18;
  if(y<10)y=10;
  if(y+ph>H-10)y=H-ph-10;
  popup.style.left=x+'px';popup.style.top=y+'px';
}

// ── Facebook ──────────────────────────────────────────────────────────────
let fbPhotos=[],fbAccounts=[];

async function loadFbAccounts(){
  fbAccounts=await fetch('/api/facebook/accounts').then(r=>r.json()).catch(()=>[]);
  document.getElementById('fbMAccounts').textContent=fbAccounts.length||'—';
  const el=document.getElementById('fbAccChecks');
  if(!fbAccounts.length){el.innerHTML='<div class="no-acc-warn">Aucun compte Facebook — configure-les dans Réglages → profil → facebook_accounts</div>';return;}
  el.innerHTML=fbAccounts.map(a=>`
    <label class="acc-check sel">
      <input type="checkbox" data-id="${a.id}" checked>
      <img src="/api/social/avatar/fb/${encodeURIComponent(a.username)}?uid=${encodeURIComponent(a.id)}"
           style="width:22px;height:22px;border-radius:50%;object-fit:cover;flex-shrink:0"
           onerror="this.style.display='none'">
      <span class="acc-check-name">${a.username}</span>
    </label>`).join('');
  el.querySelectorAll('input[type=checkbox]').forEach(cb=>cb.addEventListener('change',updateFbBtn));
  updateFbBtn();
}
function getFbAccIds(){return[...document.querySelectorAll('#fbAccChecks input:checked')].map(x=>x.dataset.id);}
function updateFbBtn(){
  const ok=fbPhotos.length>0&&getFbAccIds().length>0;
  document.getElementById('fbBtnSchedule').disabled=!ok;
  document.getElementById('fbBtnSavePl').disabled=!fbPhotos.length;
}
function renderFbPhotos(){
  const list=document.getElementById('fbPlist');
  const noP=document.getElementById('fbNoP');
  const savePl=document.getElementById('fbBtnSavePl');
  list.innerHTML='';
  noP.style.display=fbPhotos.length?'none':'block';
  if(savePl)savePl.disabled=!fbPhotos.length;
  updateFbBtn();
  if(!fbPhotos.length)return;
  list.style.cssText='display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;margin-top:10px';
  fbPhotos.forEach((p,i)=>{
    const card=document.createElement('div');
    card.style.cssText='background:#111;border:1px solid #1a3a6e;border-radius:10px;overflow:hidden;position:relative';
    const media=p.isVideo
      ?`<div style="height:213px;background:#000;display:flex;align-items:center;justify-content:center;font-size:36px">&#x1F3AC;</div>`
      :`<img src="${p.url}" style="width:100%;height:213px;object-fit:cover;display:block">`;
    card.innerHTML=`
      ${media}
      <div style="padding:7px 8px">
        <div style="font-size:.65rem;color:#666;word-break:break-all">${p.filename}</div>
      </div>
      <button data-idx="${i}" style="position:absolute;top:5px;right:5px;background:rgba(0,0,0,.6);border:none;color:#fff;border-radius:50%;width:22px;height:22px;font-size:12px;cursor:pointer;display:flex;align-items:center;justify-content:center">&#x2715;</button>`;
    card.querySelector('button').addEventListener('click',e=>{e.stopPropagation();fbPhotos.splice(i,1);renderFbPhotos();});
    list.appendChild(card);
  });
}
async function loadFbScheduled(){
  const list=await fetch('/api/facebook/scheduled').then(r=>r.json()).catch(()=>[]);
  const el=document.getElementById('fbRpList');
  const pending=list.filter(s=>s.status==='pending').length;
  const done=list.filter(s=>s.status==='done').length;
  const err=list.filter(s=>s.status==='error'||s.status==='partial').length;
  document.getElementById('fbMPending').textContent=pending||'—';
  document.getElementById('fbMDone').textContent=done||'—';
  document.getElementById('fbMErr').textContent=err||'—';
  if(!list.length){el.innerHTML='<div class="empty"><div class="empty-ico">&#x1F4D8;</div>Aucun post programmé</div>';return;}
  const _fbSp={pending:0,posting:0,partial:1,error:1,done:2};
  const sorted=list.slice().sort((a,b)=>{const pa=_fbSp[a.status]??1,pb=_fbSp[b.status]??1;if(pa!==pb)return pa-pb;return a.scheduled_at.localeCompare(b.scheduled_at);});
  const toShow=_schedFilter==='done'
    ?sorted.filter(s=>s.status==='done').reverse().slice(0,100)
    :sorted.filter(s=>s.status!=='done');
  if(!toShow.length){el.innerHTML=`<div class="empty"><div class="empty-ico">&#x1F4D8;</div>${_schedFilter==='done'?'Aucun post publié':'Aucun post en attente'}</div>`;return;}
  const bmap={pending:'bp En attente',posting:'bs Envoi…',done:'bd Publié',error:'be Erreur',partial:'bpar Partiel'};
  el.innerHTML=toShow.map(s=>{
    const[bc,bl]=(bmap[s.status]||'bp ?').split(' ');
    const accNames=(s.account_ids||[]).map(id=>{const a=fbAccounts.find(x=>x.id===id);return a?a.username:id;}).join(', ');
    const statusColor={pending:'var(--yellow)',done:'var(--green)',error:'var(--red)',partial:'orange',posting:'var(--purple)'}[s.status]||'var(--t3)';
    return `<div class="sitem">
      <img src="/uploads/${s.filename}" class="sthumb" onerror="this.style.opacity='.2'" style="width:64px;height:84px;object-fit:cover;border-radius:9px;flex-shrink:0">
      <div class="sinfo">
        <div style="font-size:.82rem;font-weight:700">${fmt(s.scheduled_at)}</div>
        <div style="font-size:.7rem;color:var(--t3);margin-top:2px">${accNames}</div>
        ${s.caption?`<div style="font-size:.68rem;color:var(--t3);font-style:italic;margin-top:2px">"${s.caption.slice(0,40)}…"</div>`:''}
        <div style="font-size:.68rem;margin-top:4px"><span style="color:${statusColor};font-weight:700">${s.status}</span></div>
      </div>
      ${s.status==='pending'?`<button class="btn btn-xs btn-danger" onclick="deleteFbScheduled('${s.id}')" style="flex-shrink:0;align-self:center">✕</button>`:''}
    </div>`;
  }).join('');
}
async function deleteFbScheduled(id){
  if(!confirm('Supprimer ce post programmé ?'))return;
  await fetch(`/api/facebook/scheduled/${id}`,{method:'DELETE'});
  loadFbScheduled();
}

// Upload zone Facebook
document.getElementById('fbFi').addEventListener('change',async function(){
  for(const f of this.files){
    const fd=new FormData();fd.append('file',f);
    const r=await fetch('/api/upload',{method:'POST',body:fd}).catch(()=>null);
    if(r&&r.ok){const d=await r.json();fbPhotos.push({filename:d.filename,url:`/uploads/${d.filename}`,isVideo:/\.(mp4|mov|avi)$/i.test(d.filename)});}
  }
  renderFbPhotos();this.value='';
});
document.getElementById('fbUz').addEventListener('click',()=>document.getElementById('fbFi').click());
document.getElementById('fbUz').addEventListener('dragover',e=>{e.preventDefault();document.getElementById('fbUz').style.borderColor='#1877F2';});
document.getElementById('fbUz').addEventListener('dragleave',()=>document.getElementById('fbUz').style.borderColor='');
document.getElementById('fbUz').addEventListener('drop',async e=>{
  e.preventDefault();document.getElementById('fbUz').style.borderColor='';
  for(const f of e.dataTransfer.files){
    const fd=new FormData();fd.append('file',f);
    const r=await fetch('/api/upload',{method:'POST',body:fd}).catch(()=>null);
    if(r&&r.ok){const d=await r.json();fbPhotos.push({filename:d.filename,url:`/uploads/${d.filename}`,isVideo:/\.(mp4|mov|avi)$/i.test(d.filename)});}
  }
  renderFbPhotos();
});

document.getElementById('fbBtnClear').addEventListener('click',()=>{fbPhotos=[];renderFbPhotos();toast('Vidé');});

document.getElementById('fbBtnSavePl').addEventListener('click',async()=>{
  if(!fbPhotos.length)return;
  const name=prompt('Nom de la playlist Facebook :');
  if(!name)return;
  const r=await fetch('/api/fb/plannings',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,photos:fbPhotos.map(p=>({filename:p.filename,url:p.url,dt:p.dt||''}))})});
  if(r.ok){toast('Playlist sauvegardée dans Médias','ok');loadPlaylists();}
  else toast('Erreur sauvegarde','err');
});

document.getElementById('fbBtnSchedule').addEventListener('click',async()=>{
  const accIds=getFbAccIds();
  if(!fbPhotos.length||!accIds.length)return;
  const caption=document.getElementById('fbCaption').value.trim();
  const btn=document.getElementById('fbBtnSchedule');
  btn.disabled=true;btn.textContent='⏳ Envoi…';
  let ok=0,err=0,offset=0;
  for(const p of fbPhotos){
    const dt=p.dt||_fbGetStartDt(offset);
    offset+=accIds.length;
    const r=await fetch('/api/facebook/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filename:p.filename,scheduled_at:dt,account_ids:accIds,caption})}).then(r=>r.json()).catch(()=>({ok:false}));
    if(r.ok)ok++;else err++;
  }
  toast(ok?`✅ ${ok} post${ok>1?'s':''} programmé${ok>1?'s':''}`:err+' erreur(s)',ok?'ok':'err');
  fbPhotos=[];renderFbPhotos();loadFbScheduled();
  btn.disabled=false;btn.textContent='📘 Programmer';
});

// Datetime par défaut
document.getElementById('fbDateInput').value=defDt();

// ── Init ───────────────────────────────────────────────────────────────────
loadProfiles();
loadAccounts();loadScheduled();loadPlaylists();refreshStatus();document.getElementById('rightPanel').style.display='';
setInterval(()=>{
  if(currentPage==='schedule')loadScheduled();
  else if(currentPage==='snapchat')loadSnapScheduled();
  else if(currentPage==='instagram')loadIgScheduled();
  else if(currentPage==='facebook')loadFbScheduled();
  refreshStatus();
},15000);
setInterval(loadAccounts,60000);
</script>
</body>
</html>"""

if __name__=="__main__":
    import uvicorn
    uvicorn.run("story_scheduler:app",app_dir=str(BASE_DIR),host="0.0.0.0",port=8001,reload=False)
