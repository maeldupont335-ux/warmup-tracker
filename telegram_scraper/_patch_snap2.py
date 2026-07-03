path = r'C:\Users\MAEL\Downloads\higgsfield-batch\higgsfield-batch\telegram_scraper\story_scheduler.py'
with open(path, encoding='utf-8') as f:
    content = f.read()

# ══════════════════════════════════════════════════════════════════════════════
# 1. BACKEND — Story convert 9:16 + offset + Spotlight route
# ══════════════════════════════════════════════════════════════════════════════

BACKEND_ADDITIONS = r"""
SNAP_SPOTLIGHT_FILE = _DATA_DIR / "snap_spotlight.json"
_snap_spotlight: list[dict] = _load_json(SNAP_SPOTLIGHT_FILE, [])

def _story_convert(src: Path) -> Path:
    """Recadre en 9:16 COVER 1080x1920 — retourne le path de la version convertie."""
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

@app.delete("/api/snap/spotlight/{sid}")
async def delete_snap_spotlight(sid: str):
    global _snap_spotlight
    _snap_spotlight = [s for s in _snap_spotlight if s["id"] != sid]
    _save_json(SNAP_SPOTLIGHT_FILE, _snap_spotlight)
    return {"ok": True}

@app.post("/api/snap/spotlight")
async def schedule_spotlight(req: dict = Body(...)):
    import random as _rnd
    videos       = req.get("videos", [])         # [{filename}]
    account_ids  = req.get("account_ids", [])
    posts_per    = int(req.get("posts_per_account", 1))
    start_date   = req.get("start_date", "")     # "YYYY-MM-DD"
    if not videos:    raise HTTPException(400, "Aucune vidéo")
    if not account_ids: raise HTTPException(400, "Aucun compte sélectionné")
    if not start_date:  raise HTTPException(400, "Date de début requise")

    from datetime import timedelta as _td
    loop = asyncio.get_event_loop()
    base = datetime.fromisoformat(start_date)
    n_acc = len(account_ids)
    added = 0

    # Répartition round-robin des vidéos entre comptes
    # Chaque compte reçoit posts_per vidéos — on boucle sur la liste si besoin
    for ai, acc_id in enumerate(account_ids):
        acc = next((a for a in SNAP_ACCOUNTS if a["id"] == acc_id), None)
        uname = acc["username"] if acc else acc_id
        acc_results = {}

        for k in range(posts_per):
            # Vidéo : round-robin sur la liste uploadée
            vidx = (ai * posts_per + k) % len(videos)
            filename = videos[vidx]["filename"]
            filepath = UPLOAD_DIR / filename
            if not filepath.exists():
                continue

            # Date : 1 post/jour par compte, heure aléatoire 8h-21h
            jour = base + _td(days=k)
            h = _rnd.randint(8, 20)
            m = _rnd.randint(0, 59)
            dt_post = jour.replace(hour=h, minute=m, second=0, microsecond=0)
            # Offset 25 min entre comptes le même jour
            dt_post += _td(minutes=ai * 25)
            dt_str = dt_post.isoformat()

            sid = uuid.uuid4().hex[:8]
            entry = {
                "id": sid, "filename": filename,
                "scheduled_at": dt_str,
                "account_id": acc_id, "username": uname,
                "status": "pending", "result": {},
            }
            _snap_spotlight.append(entry)
            _save_json(SNAP_SPOTLIGHT_FILE, _snap_spotlight)

            # Upload Cloudinary
            with concurrent.futures.ThreadPoolExecutor() as pool:
                media_url = await loop.run_in_executor(pool, _cloudinary_upload, filepath, True)
            if not media_url:
                entry["status"] = "error"; entry["result"] = {"msg": "Cloudinary failed"}
                _save_json(SNAP_SPOTLIGHT_FILE, _snap_spotlight); continue

            entry["cloudinary_url"] = media_url
            with concurrent.futures.ThreadPoolExecutor() as pool:
                ok, msg = await loop.run_in_executor(pool, _oneup_spotlight, media_url, acc_id, dt_str, "")
            entry["status"] = "done" if ok else "error"
            entry["result"] = {"status": "done" if ok else "error", "msg": msg}
            _save_json(SNAP_SPOTLIGHT_FILE, _snap_spotlight)
            if ok: added += 1

    return {"ok": True, "count": added}
"""

# Insérer avant la route index
OLD_INDEX_ROUTE = "# ─────────────────────────────────────────────────────────────────────────────\n@app.get(\"/\", response_class=HTMLResponse)"
assert OLD_INDEX_ROUTE in content, "index route not found"
content = content.replace(OLD_INDEX_ROUTE, BACKEND_ADDITIONS + "\n" + OLD_INDEX_ROUTE)

# ══════════════════════════════════════════════════════════════════════════════
# 2. FIX schedule_snap — +1 min offset + conversion 9:16
# ══════════════════════════════════════════════════════════════════════════════
OLD_SNAP_LOOP = """        entry["cloudinary_url"] = media_url
        results = {}
        for acc_id in account_ids:
            acc   = next((a for a in SNAP_ACCOUNTS if a["id"] == acc_id), None)
            uname = acc["username"] if acc else acc_id
            with concurrent.futures.ThreadPoolExecutor() as pool:
                ok, msg = await loop.run_in_executor(
                    pool, _oneup_schedule, media_url, is_video, acc_id, scheduled_at)
            results[acc_id] = {
                "username": uname, "status": "done" if ok else "error",
                "msg": msg,
            }"""

NEW_SNAP_LOOP = """        # Conversion 9:16 pour les images
        if not is_video:
            converted = _story_convert(filepath)
            if converted != filepath:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    media_url = await loop.run_in_executor(pool, _cloudinary_upload, converted, False)
                if not media_url:
                    entry["status"] = "error"; entry["error"] = "Cloudinary (story) failed"
                    _save_json(SNAP_SCHED_FILE, _snap_scheduled); continue

        entry["cloudinary_url"] = media_url
        results = {}
        for n_acc, acc_id in enumerate(account_ids):
            acc   = next((a for a in SNAP_ACCOUNTS if a["id"] == acc_id), None)
            uname = acc["username"] if acc else acc_id
            # +1 min par compte pour éviter détection doublon
            from datetime import timedelta as _tdd
            try: dt_offset = (datetime.fromisoformat(scheduled_at) + _tdd(minutes=n_acc)).isoformat()
            except: dt_offset = scheduled_at
            with concurrent.futures.ThreadPoolExecutor() as pool:
                ok, msg = await loop.run_in_executor(
                    pool, _oneup_schedule, media_url, is_video, acc_id, dt_offset)
            results[acc_id] = {
                "username": uname, "status": "done" if ok else "error",
                "msg": msg,
            }"""

assert OLD_SNAP_LOOP in content, "snap loop not found"
content = content.replace(OLD_SNAP_LOOP, NEW_SNAP_LOOP)

# ══════════════════════════════════════════════════════════════════════════════
# 3. CSS — onglets Stories / Spotlight dans la page Snapchat
# ══════════════════════════════════════════════════════════════════════════════
SNAP_TAB_CSS = """
/* Snapchat sub-tabs */
.snap-tabs{display:flex;gap:0;margin-bottom:14px;background:var(--c2);border:1px solid var(--b1);border-radius:10px;padding:3px}
.snap-tab{flex:1;padding:8px 14px;border-radius:8px;border:none;background:transparent;color:var(--t2);font-size:.82rem;font-weight:600;cursor:pointer;transition:.15s;text-align:center}
.snap-tab:hover{color:var(--t1)}
.snap-tab.active{background:#1c1c1c;color:var(--t1);box-shadow:0 1px 4px rgba(0,0,0,.4)}
.snap-tab.active[data-snap="spotlight"]{color:#f5c518}
.snap-subview{display:none}.snap-subview.active{display:block}
.spl-count-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.spl-count-row label{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--t2);white-space:nowrap}
.spl-count-inp{width:70px;background:var(--c2);border:1px solid var(--b2);border-radius:7px;padding:7px 10px;color:var(--t1);font-size:.9rem;font-weight:700;text-align:center;outline:none}
.spl-count-inp:focus{border-color:#f5c518}
.spl-date-inp{flex:1;background:var(--c2);border:1px solid var(--b2);border-radius:7px;padding:7px 10px;color:var(--t1);font-size:.82rem;outline:none;color-scheme:dark}
.spl-date-inp:focus{border-color:#f5c518}
"""
content = content.replace('\n/* ── Line charts', SNAP_TAB_CSS + '\n/* __ lc_ph')
content = content.replace('/* __ lc_ph', '/* __ Line charts')

# ══════════════════════════════════════════════════════════════════════════════
# 4. HTML — remplace page Snapchat avec 2 onglets
# ══════════════════════════════════════════════════════════════════════════════
OLD_SNAP_PAGE_START = "        <!-- PAGE : Snapchat -->\n        <div class=\"page\" id=\"page-snapchat\">"
assert OLD_SNAP_PAGE_START in content, "snap page start not found"

OLD_SNAP_PAGE_END = "        </div>\n\n        <!-- PAGE : Comptes -->"

idx_start = content.find(OLD_SNAP_PAGE_START)
idx_end   = content.find("        <!-- PAGE : Comptes -->")
old_snap_block = content[idx_start:idx_end]

NEW_SNAP_PAGE = """        <!-- PAGE : Snapchat -->
        <div class="page" id="page-snapchat">

          <!-- Onglets Stories / Spotlight -->
          <div class="snap-tabs">
            <button class="snap-tab active" data-snap="stories" onclick="switchSnapTab('stories')">📸 Stories</button>
            <button class="snap-tab" data-snap="spotlight" onclick="switchSnapTab('spotlight')">🎬 Spotlight</button>
          </div>

          <!-- ── VUE STORIES ───────────────────────────────────── -->
          <div class="snap-subview active" id="snapStories">
            <div class="metrics" style="margin-bottom:12px">
              <div class="metric"><div class="metric-val" id="snapMPending">—</div><div class="metric-lbl">En attente</div></div>
              <div class="metric"><div class="metric-val" id="snapMDone">—</div><div class="metric-lbl">Envoyées</div></div>
              <div class="metric"><div class="metric-val" id="snapMErr">—</div><div class="metric-lbl">Erreurs</div></div>
              <div class="metric"><div class="metric-val">6</div><div class="metric-lbl">Comptes</div></div>
            </div>
            <div class="panel">
              <div class="panel-hd"><div class="panel-title" style="color:#f5c518">👻 Programmer des stories Snapchat</div></div>
              <div class="uz" id="snapUz" style="border-color:#f5c51830">
                <input type="file" id="snapFi" accept="image/*,video/*" multiple>
                <div class="uz-ico">👻</div>
                <div class="uz-txt"><b>Photos / vidéos</b> — converties automatiquement en 9:16</div>
              </div>
              <div class="plist" id="snapPlist"></div>
              <div class="no-p" id="snapNoP">Aucune photo ajoutée</div>
              <div class="acc-section">
                <div class="acc-section-lbl">Comptes Snapchat :</div>
                <div class="acc-checks" id="snapAccChecks"><div class="no-acc-warn">Chargement…</div></div>
              </div>
              <div style="display:flex;gap:6px;margin-top:12px">
                <button class="btn btn-danger" id="snapBtnSchedule" disabled style="flex:1;background:#f5c518;border-color:#f5c518;color:#000">👻 Programmer (+1 min/compte)</button>
                <button class="btn" id="snapBtnClear">🗑</button>
              </div>
              <div style="margin-top:8px;padding:7px 10px;background:rgba(245,197,24,.06);border:1px solid rgba(245,197,24,.15);border-radius:6px;font-size:.67rem;color:#aaa">
                ✅ Conversion 9:16 automatique · +1 min entre chaque compte · Cloudinary → One Up
              </div>
            </div>
          </div>

          <!-- ── VUE SPOTLIGHT ─────────────────────────────────── -->
          <div class="snap-subview" id="snapSpotlight">
            <div class="metrics" style="margin-bottom:12px">
              <div class="metric"><div class="metric-val" id="splMTotal">—</div><div class="metric-lbl">Total programmés</div></div>
              <div class="metric"><div class="metric-val" id="splMDone">—</div><div class="metric-lbl">Envoyés</div></div>
              <div class="metric"><div class="metric-val" id="splMErr">—</div><div class="metric-lbl">Erreurs</div></div>
              <div class="metric"><div class="metric-val" style="color:#f5c518">🎬</div><div class="metric-lbl">Vidéos seulement</div></div>
            </div>
            <div class="panel">
              <div class="panel-hd"><div class="panel-title" style="color:#f5c518">🎬 Programmer des Spotlight</div></div>
              <div class="uz" id="splUz" style="border-color:#f5c51830">
                <input type="file" id="splFi" accept="video/*" multiple>
                <div class="uz-ico">🎬</div>
                <div class="uz-txt"><b>Vidéos uniquement</b> · Format 9:16 recommandé (1080×1920)</div>
              </div>
              <div class="plist" id="splPlist"></div>
              <div class="no-p" id="splNoP">Aucune vidéo ajoutée</div>

              <div class="spl-count-row" style="margin-top:12px">
                <label>Posts / compte</label>
                <input class="spl-count-inp" type="number" id="splCount" min="1" max="25" value="1">
                <label>Date début</label>
                <input class="spl-date-inp" type="date" id="splDate">
              </div>

              <div class="acc-section">
                <div class="acc-section-lbl">Comptes qui reçoivent les Spotlight :</div>
                <div class="acc-checks" id="splAccChecks"><div class="no-acc-warn">Chargement…</div></div>
              </div>
              <div style="display:flex;gap:6px;margin-top:12px">
                <button class="btn btn-danger" id="splBtnSchedule" disabled style="flex:1;background:#f5c518;border-color:#f5c518;color:#000">🎬 Programmer les Spotlight</button>
                <button class="btn" id="splBtnClear">🗑</button>
              </div>
              <div style="margin-top:8px;padding:7px 10px;background:rgba(245,197,24,.06);border:1px solid rgba(245,197,24,.15);border-radius:6px;font-size:.67rem;color:#aaa">
                ⚡ 1 post/jour/compte · heure aléatoire 8h-21h · 25 min entre comptes · max 25 posts One Up
              </div>
            </div>

            <!-- Historique Spotlight -->
            <div class="panel" style="margin-top:12px">
              <div class="panel-hd"><div class="panel-title">📋 Historique Spotlight</div><button class="btn btn-xs" id="splBtnRefresh">🔄</button></div>
              <div id="splList"><div class="empty"><div class="empty-ico">🎬</div>Aucun Spotlight programmé</div></div>
            </div>
          </div>

        </div>

"""
content = content[:idx_start] + NEW_SNAP_PAGE + content[idx_end:]

# ══════════════════════════════════════════════════════════════════════════════
# 5. JS — switchSnapTab + Spotlight JS
# ══════════════════════════════════════════════════════════════════════════════

SPOTLIGHT_JS = r"""
// ── Snapchat sub-tabs ──────────────────────────────────────────────────────
function switchSnapTab(tab){
  document.querySelectorAll('.snap-tab').forEach(t=>t.classList.toggle('active',t.dataset.snap===tab));
  document.querySelectorAll('.snap-subview').forEach(v=>v.classList.toggle('active',v.id==='snap'+(tab==='stories'?'Stories':'Spotlight')));
  if(tab==='spotlight'){
    if(!splAccounts.length)loadSplAccounts();
    loadSplList();
  }
}

// ── Spotlight ──────────────────────────────────────────────────────────────
let splVideos=[],splAccounts=[];
function loadSplAccounts(){
  // Réutilise les mêmes comptes que snapchat
  if(snapAccounts.length){splAccounts=snapAccounts;renderSplAccChecks();return;}
  fetch('/api/snap/accounts').then(r=>r.json()).then(list=>{splAccounts=list;renderSplAccChecks();});
}
function renderSplAccChecks(){
  const el=document.getElementById('splAccChecks');
  el.innerHTML=splAccounts.map(a=>`
    <label class="acc-check sel"><input type="checkbox" data-id="${a.id}" checked>
    <div class="acc-check-dot" style="background:#f5c518"></div>
    <span class="acc-check-name">${a.username}</span></label>`).join('');
  el.querySelectorAll('.acc-check').forEach(l=>{const cb=l.querySelector('input');cb.addEventListener('change',()=>{l.classList.toggle('sel',cb.checked);updateSplBtn();});});
  updateSplBtn();
}
function getSplSelIds(){return [...document.querySelectorAll('#splAccChecks input:checked')].map(i=>i.dataset.id);}
function updateSplBtn(){document.getElementById('splBtnSchedule').disabled=!(splVideos.length>0&&getSplSelIds().length>0);}

const splUz=document.getElementById('splUz'),splFi=document.getElementById('splFi');
splUz.addEventListener('dragover',e=>{e.preventDefault();splUz.classList.add('over');});
splUz.addEventListener('dragleave',()=>splUz.classList.remove('over'));
splUz.addEventListener('drop',e=>{e.preventDefault();splUz.classList.remove('over');uploadSplFiles([...e.dataTransfer.files]);});
splFi.addEventListener('change',()=>{uploadSplFiles([...splFi.files]);splFi.value='';});

async function uploadSplFiles(files){
  const vids=files.filter(f=>f.type.startsWith('video/'));
  if(!vids.length){toast('Vidéos uniquement pour le Spotlight','err');return;}
  toast(`Upload de ${vids.length} vidéo(s)...`);
  let n=0;
  for(const f of vids){
    const fd=new FormData();fd.append('file',f);
    try{
      const r=await fetch('/api/upload',{method:'POST',body:fd});
      if(!r.ok)continue;
      const d=await r.json();splVideos.push({filename:d.filename,url:d.url});n++;
    }catch{}
  }
  renderSplList2();if(n)toast(`${n} vidéo(s) ajoutée(s)`,'ok');
}
function renderSplList2(){
  const list=document.getElementById('splPlist'),noEl=document.getElementById('splNoP');
  list.innerHTML='';noEl.style.display=splVideos.length?'none':'';updateSplBtn();
  splVideos.forEach((v,i)=>{
    const row=document.createElement('div');row.className='prow';
    row.innerHTML=`<span class="dh">&#x2823;</span><span class="pord">${i+1}</span>
      <div style="width:36px;height:36px;border-radius:4px;background:#1a1a1a;display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0">🎬</div>
      <div class="pdt" style="flex:1;font-size:.75rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 4px">${v.filename}</div>
      <button class="pdel" data-idx="${i}">&#x2715;</button>`;
    row.querySelector('.pdel').addEventListener('click',e=>{e.stopPropagation();splVideos.splice(i,1);renderSplList2();});
    list.appendChild(row);
  });
}
document.getElementById('splBtnClear').addEventListener('click',()=>{splVideos=[];renderSplList2();toast('Vidé');});

// Date par défaut = demain
(()=>{const d=new Date();d.setDate(d.getDate()+1);const p=n=>String(n).padStart(2,'0');document.getElementById('splDate').value=`${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;})();

document.getElementById('splBtnSchedule').addEventListener('click',async()=>{
  const accIds=getSplSelIds();const count=parseInt(document.getElementById('splCount').value)||1;
  const startDate=document.getElementById('splDate').value;
  if(!splVideos.length||!accIds.length||!startDate)return;
  const btn=document.getElementById('splBtnSchedule');btn.disabled=true;btn.textContent='⏳ Envoi en cours...';
  try{
    const r=await fetch('/api/snap/spotlight',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({videos:splVideos,account_ids:accIds,posts_per_account:count,start_date:startDate})});
    if(!r.ok)throw new Error((await r.json()).detail);
    const d=await r.json();
    toast(`✅ ${d.count} Spotlight programmés !`,'ok');
    splVideos=[];renderSplList2();loadSplList();
  }catch(e){toast(`Erreur: ${e.message}`,'err');}
  finally{btn.disabled=!splVideos.length;btn.innerHTML='🎬 Programmer les Spotlight';}
});

async function loadSplList(){
  const r=await fetch('/api/snap/spotlight');const list=await r.json();
  const el=document.getElementById('splList');
  document.getElementById('splMTotal').textContent=list.length;
  document.getElementById('splMDone').textContent=list.filter(s=>s.status==='done').length;
  document.getElementById('splMErr').textContent=list.filter(s=>s.status==='error').length;
  if(!list.length){el.innerHTML='<div class="empty"><div class="empty-ico">🎬</div>Aucun Spotlight programmé</div>';return;}
  const bmap={pending:'bp',done:'bd',error:'be'};
  el.innerHTML=list.slice().reverse().map(s=>`
    <div class="sitem">
      <div style="width:52px;height:68px;border-radius:8px;background:#1a1a1a;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0">🎬</div>
      <div class="sinfo">
        <div class="sdate">📅 ${fmt(s.scheduled_at)}</div>
        <div class="saccs">@${s.username}</div>
        <div class="spl" style="font-size:.65rem">🎯 Spotlight</div>
      </div>
      <div class="sright">
        <span class="badge ${bmap[s.status]||'bp'}">${s.status==='done'?'Envoyé':s.status==='error'?'Erreur':'Attente'}</span>
        <button class="sdel2" data-id="${s.id}">&#x2715;</button>
      </div>
    </div>`).join('');
  el.querySelectorAll('.sdel2').forEach(b=>b.addEventListener('click',async()=>{
    if(!confirm('Supprimer ?'))return;
    await fetch(`/api/snap/spotlight/${b.dataset.id}`,{method:'DELETE'});toast('Supprimé');loadSplList();
  }));
}
document.getElementById('splBtnRefresh').addEventListener('click',loadSplList);
"""

OLD_SNAP_INIT = "// ── Snapchat ───────────────────────────────────────────────────────────────"
assert OLD_SNAP_INIT in content, "Snapchat JS section not found"
content = content.replace(OLD_SNAP_INIT, SPOTLIGHT_JS + "\n" + OLD_SNAP_INIT)

# Fix date par défaut splDate — init auto (déjà dans le JS ci-dessus, pas de doublon)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Done. Lines: {len(content.splitlines())}")
print(f"schedule_spotlight: {'schedule_spotlight' in content}")
print(f"_story_convert: {'_story_convert' in content}")
print(f"snapSpotlight: {'snapSpotlight' in content}")
print(f"switchSnapTab: {'switchSnapTab' in content}")
