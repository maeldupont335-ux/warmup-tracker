"""
Higgsfield Studio — Mini-site de remplacement de personne par IA
  GET  /          → page Upload (importer photo + vidéo)
  GET  /results   → page Résultats (galerie des vidéos modifiées)
  POST /api/jobs  → créer un job (multipart: photo + video + options)
  GET  /api/jobs  → liste des jobs
  GET  /api/jobs/{id} → statut d'un job
  DELETE /api/jobs/{id} → supprimer un job
"""

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
import higgsfield_client  # noqa — init credentials
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline import process_kling, process_seedance

# ── Config ────────────────────────────────────────────────────────────────────
HF_KEY = os.environ.get(
    "HF_KEY",
    "660744e6-d19f-4048-92f3-c9c608639a0b"
    ":cc61021dd15bc0930cf61c6edb9dfed4312bc260f8b7dabd728195fb1a523f78",
)
os.environ["HF_KEY"] = HF_KEY

ROOT = Path(__file__).parent
UPLOAD_PHOTOS = ROOT / "uploads" / "photos"
UPLOAD_VIDEOS = ROOT / "uploads" / "videos"
OUTPUTS_DIR   = ROOT / "outputs"
JOBS_FILE     = ROOT / "jobs.json"

for d in [UPLOAD_PHOTOS, UPLOAD_VIDEOS, OUTPUTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")

# ── Job store (JSON file) ─────────────────────────────────────────────────────
_jobs: dict = {}

def load_jobs():
    global _jobs
    if JOBS_FILE.exists():
        try:
            _jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        except Exception:
            _jobs = {}

def save_jobs():
    JOBS_FILE.write_text(json.dumps(_jobs, indent=2, default=str), encoding="utf-8")

load_jobs()

# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Higgsfield Studio")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")
app.mount("/uploads", StaticFiles(directory=str(ROOT / "uploads")), name="uploads")


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE UPLOAD  (/
# ═══════════════════════════════════════════════════════════════════════════════

UPLOAD_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Higgsfield Studio — Upload</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#0a0a0f;color:#e2e8f0;min-height:100vh;padding:0}
.layout{display:flex;min-height:100vh}
/* Sidebar */
.sidebar{width:220px;background:#060609;border-right:1px solid #1a1a2e;
  display:flex;flex-direction:column;flex-shrink:0;padding:0}
.logo{padding:24px 20px 20px;border-bottom:1px solid #1a1a2e}
.logo-badge{display:inline-flex;align-items:center;gap:10px}
.logo-icon{width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#7c3aed,#4f46e5);
  display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0}
.logo-name{font-size:.92rem;font-weight:800;color:#f0f0f0;letter-spacing:.03em}
.logo-sub{font-size:.6rem;color:#444;text-transform:uppercase;letter-spacing:.1em;margin-top:2px}
.nav{padding:16px 12px;flex:1;display:flex;flex-direction:column;gap:3px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;
  color:#555;font-size:.88rem;font-weight:600;text-decoration:none;transition:all .15s;
  border:none;background:none;cursor:pointer;width:100%;text-align:left}
.nav-item:hover{background:#12121f;color:#aaa}
.nav-item.active{background:rgba(124,58,237,.15);color:#a78bfa;
  border-right:3px solid #7c3aed;border-radius:8px 0 0 8px}
.nav-ico{width:18px;height:18px;flex-shrink:0;display:flex;align-items:center;justify-content:center}
/* Main */
.main{flex:1;overflow-y:auto;padding:36px 40px;max-width:960px}
h1{font-size:1.7rem;font-weight:800;color:#f8fafc;margin-bottom:6px}
.subtitle{color:#555;font-size:.88rem;margin-bottom:32px}
/* Cards */
.card{background:#0f0f1a;border:1px solid #1a1a2e;border-radius:16px;padding:28px;margin-bottom:24px}
.card-title{font-size:.7rem;font-weight:800;color:#4f46e5;text-transform:uppercase;
  letter-spacing:.12em;margin-bottom:18px;display:flex;align-items:center;gap:8px}
.card-title::before{content:'';width:3px;height:14px;background:#7c3aed;border-radius:99px;flex-shrink:0}
/* Drop zones */
.drop-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}
@media(max-width:640px){.drop-grid{grid-template-columns:1fr}}
.drop-zone{border:2px dashed #2a2a3e;border-radius:14px;padding:32px 20px;
  text-align:center;cursor:pointer;transition:all .2s;position:relative;
  background:#080810}
.drop-zone:hover,.drop-zone.dragover{border-color:#7c3aed;background:rgba(124,58,237,.06)}
.drop-zone.has-file{border-color:#22c55e;border-style:solid;background:rgba(34,197,94,.04)}
.drop-icon{font-size:2rem;margin-bottom:10px;opacity:.5}
.drop-label{font-size:.88rem;font-weight:600;color:#888;margin-bottom:4px}
.drop-hint{font-size:.72rem;color:#444}
.drop-file-name{font-size:.82rem;color:#22c55e;font-weight:600;margin-top:8px;
  word-break:break-all}
.drop-preview{max-width:100%;max-height:140px;border-radius:8px;margin-top:10px;object-fit:cover}
.drop-video-preview{max-width:100%;max-height:140px;border-radius:8px;margin-top:10px}
input[type=file]{display:none}
/* Options */
.options-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:24px}
@media(max-width:640px){.options-grid{grid-template-columns:1fr}}
.opt-group{display:flex;flex-direction:column;gap:6px}
.opt-label{font-size:.68rem;font-weight:700;color:#3b5278;text-transform:uppercase;letter-spacing:.1em}
.opt-select,.opt-input{background:#060609;border:1px solid #1a1a2e;border-radius:8px;
  padding:10px 12px;color:#e2e8f0;font-size:.88rem;width:100%;
  appearance:none;-webkit-appearance:none}
.opt-select:focus,.opt-input:focus{outline:none;border-color:#7c3aed}
/* Model cards */
.model-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px}
.model-card{border:2px solid #1a1a2e;border-radius:12px;padding:16px;cursor:pointer;
  transition:all .15s;background:#080810;position:relative}
.model-card:hover{border-color:#4f46e5;background:#0c0c18}
.model-card.selected{border-color:#7c3aed;background:rgba(124,58,237,.08)}
.model-card input[type=radio]{position:absolute;opacity:0}
.model-name{font-size:.9rem;font-weight:700;color:#e2e8f0;margin-bottom:4px;
  display:flex;align-items:center;gap:8px}
.model-badge{font-size:.58rem;font-weight:700;padding:2px 7px;border-radius:99px;
  text-transform:uppercase;letter-spacing:.06em}
.badge-rec{background:#1e1b4b;color:#a78bfa;border:1px solid #4f46e5}
.badge-best{background:#052e16;color:#86efac;border:1px solid #166534}
.model-desc{font-size:.75rem;color:#555;line-height:1.5}
/* Submit */
.btn-submit{background:linear-gradient(135deg,#7c3aed,#4f46e5);border:none;
  border-radius:10px;padding:14px 32px;color:#fff;font-size:.95rem;font-weight:700;
  cursor:pointer;width:100%;transition:all .2s;letter-spacing:.02em}
.btn-submit:hover{opacity:.9;transform:translateY(-1px)}
.btn-submit:disabled{opacity:.4;cursor:not-allowed;transform:none}
/* Progress */
.progress-bar-wrap{background:#1a1a2e;border-radius:99px;height:6px;margin-top:16px;overflow:hidden;display:none}
.progress-bar{height:100%;background:linear-gradient(90deg,#7c3aed,#4f46e5);
  border-radius:99px;width:0%;transition:width .4s ease;animation:indeterminate 1.5s ease infinite}
@keyframes indeterminate{0%{width:0%;margin-left:0}50%{width:60%;margin-left:20%}100%{width:0%;margin-left:100%}}
/* Toast */
.toast{display:none;position:fixed;bottom:24px;right:24px;padding:14px 24px;
  border-radius:10px;font-weight:600;font-size:.88rem;z-index:999;
  box-shadow:0 8px 32px rgba(0,0,0,.4)}
.toast.success{background:#052e16;border:1px solid #166534;color:#86efac}
.toast.error{background:#450a0a;border:1px solid #991b1b;color:#fca5a5}
/* Job queue preview */
.queue-preview{margin-top:20px}
.queue-item{display:flex;align-items:center;gap:12px;padding:10px 14px;
  background:#080810;border:1px solid #1a1a2e;border-radius:10px;margin-bottom:8px}
.q-status{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.q-status.generating{background:#7c3aed;animation:pulse .8s ease infinite}
.q-status.uploading{background:#f59e0b;animation:pulse .8s ease infinite}
.q-status.completed{background:#22c55e}
.q-status.error{background:#ef4444}
.q-status.pending{background:#334155}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.q-name{font-size:.82rem;color:#aaa;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.q-log{font-size:.72rem;color:#555;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
</head>
<body>
<div class="layout">
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="logo">
      <div class="logo-badge">
        <div class="logo-icon">🎬</div>
        <div>
          <div class="logo-name">HG Studio</div>
          <div class="logo-sub">AI Video Lab</div>
        </div>
      </div>
    </div>
    <nav class="nav">
      <a href="/" class="nav-item active">
        <span class="nav-ico">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7">
            <path d="M2 12V6l6-4 6 4v6a1 1 0 01-1 1H3a1 1 0 01-1-1z"/>
          </svg>
        </span>
        Upload
      </a>
      <a href="/results" class="nav-item">
        <span class="nav-ico">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7">
            <polygon points="5,2 14,8 5,14"/>
          </svg>
        </span>
        Résultats
      </a>
    </nav>
  </aside>

  <!-- Main -->
  <main class="main">
    <h1>Remplacement de personne IA</h1>
    <p class="subtitle">Importe une photo de référence + une vidéo source → l'IA remplace la personne en conservant la scène</p>

    <!-- Drop zones -->
    <div class="card">
      <div class="card-title">Médias source</div>
      <div class="drop-grid">
        <!-- Photo -->
        <div class="drop-zone" id="drop-photo" onclick="document.getElementById('input-photo').click()">
          <div class="drop-icon">🖼️</div>
          <div class="drop-label">Photo de référence</div>
          <div class="drop-hint">JPG / PNG — la personne à intégrer</div>
          <div class="drop-file-name" id="photo-name"></div>
          <img class="drop-preview" id="photo-preview" style="display:none">
          <input type="file" id="input-photo" accept="image/jpeg,image/png,image/webp">
        </div>
        <!-- Vidéo -->
        <div class="drop-zone" id="drop-video" onclick="document.getElementById('input-video').click()">
          <div class="drop-icon">🎥</div>
          <div class="drop-label">Vidéo source</div>
          <div class="drop-hint">MP4 / MOV / AVI — la scène originale</div>
          <div class="drop-file-name" id="video-name"></div>
          <video class="drop-video-preview" id="video-preview" style="display:none" muted controls></video>
          <input type="file" id="input-video" accept="video/mp4,video/quicktime,video/avi,video/webm,.mp4,.mov,.avi">
        </div>
      </div>
    </div>

    <!-- Choix du modèle -->
    <div class="card">
      <div class="card-title">Modèle IA</div>
      <div class="model-grid">
        <label class="model-card selected" id="mc-seedance">
          <input type="radio" name="model" value="seedance_2_0" checked>
          <div class="model-name">Seedance 2.0 <span class="model-badge badge-best">Recommandé</span></div>
          <div class="model-desc">Passe la vidéo entière en référence + photo pour l'identité. Meilleure cohérence de mouvement et de scène.</div>
        </label>
        <label class="model-card" id="mc-kling">
          <input type="radio" name="model" value="kling3_0">
          <div class="model-name">Kling 3.0 <span class="model-badge badge-rec">Motion</span></div>
          <div class="model-desc">Motion transfer cinématographique. Utilise la photo comme image de départ pour générer un video créatif.</div>
        </label>
      </div>
    </div>

    <!-- Options -->
    <div class="card">
      <div class="card-title">Options</div>
      <div class="options-grid">
        <div class="opt-group">
          <label class="opt-label">Durée (secondes)</label>
          <select class="opt-select" id="opt-duration">
            <option value="5">5 s</option>
            <option value="8" selected>8 s</option>
            <option value="10">10 s</option>
            <option value="15">15 s</option>
          </select>
        </div>
        <div class="opt-group" id="opt-res-wrap">
          <label class="opt-label">Résolution (Seedance)</label>
          <select class="opt-select" id="opt-resolution">
            <option value="720p" selected>720p</option>
            <option value="1080p">1080p</option>
            <option value="480p">480p</option>
          </select>
        </div>
        <div class="opt-group">
          <label class="opt-label">Nom du job (optionnel)</label>
          <input class="opt-input" type="text" id="opt-name" placeholder="ex: Shooting plage">
        </div>
      </div>
    </div>

    <!-- Submit -->
    <button class="btn-submit" id="btn-submit" onclick="submitJob()">
      🚀 Lancer la génération
    </button>
    <div class="progress-bar-wrap" id="progress-wrap">
      <div class="progress-bar" id="progress-bar"></div>
    </div>

    <!-- Queue preview -->
    <div class="queue-preview" id="queue-preview"></div>
  </main>
</div>

<div class="toast" id="toast"></div>

<script>
let photoFile = null, videoFile = null;

// ── Drag & drop ──────────────────────────────────────────────────────────────
function setupDrop(zoneId, inputId, type) {
  const zone  = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f, type);
  });
  input.addEventListener('change', () => { if (input.files[0]) handleFile(input.files[0], type); });
}

function handleFile(file, type) {
  if (type === 'photo') {
    photoFile = file;
    document.getElementById('photo-name').textContent = file.name;
    document.getElementById('drop-photo').classList.add('has-file');
    const preview = document.getElementById('photo-preview');
    preview.src = URL.createObjectURL(file);
    preview.style.display = 'block';
  } else {
    videoFile = file;
    document.getElementById('video-name').textContent = file.name;
    document.getElementById('drop-video').classList.add('has-file');
    const preview = document.getElementById('video-preview');
    preview.src = URL.createObjectURL(file);
    preview.style.display = 'block';
  }
}

setupDrop('drop-photo', 'input-photo', 'photo');
setupDrop('drop-video', 'input-video', 'video');

// ── Model selection ──────────────────────────────────────────────────────────
document.querySelectorAll('input[name=model]').forEach(radio => {
  radio.closest('.model-card').addEventListener('click', () => {
    document.querySelectorAll('.model-card').forEach(c => c.classList.remove('selected'));
    radio.closest('.model-card').classList.add('selected');
    radio.checked = true;
    document.getElementById('opt-res-wrap').style.opacity =
      radio.value === 'seedance_2_0' ? '1' : '.4';
  });
});

// ── Submit ───────────────────────────────────────────────────────────────────
async function submitJob() {
  if (!photoFile) return toast('Importe une photo de référence', 'error');
  if (!videoFile) return toast('Importe une vidéo source', 'error');

  const model    = document.querySelector('input[name=model]:checked').value;
  const duration = parseInt(document.getElementById('opt-duration').value);
  const resolution = document.getElementById('opt-resolution').value;
  const name     = document.getElementById('opt-name').value.trim();

  const btn = document.getElementById('btn-submit');
  btn.disabled = true;
  btn.textContent = '⏳ Envoi en cours…';
  document.getElementById('progress-wrap').style.display = 'block';

  const fd = new FormData();
  fd.append('photo', photoFile);
  fd.append('video', videoFile);
  fd.append('model', model);
  fd.append('duration', duration);
  fd.append('resolution', resolution);
  if (name) fd.append('name', name);

  try {
    const r    = await fetch('/api/jobs', { method: 'POST', body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Erreur serveur');
    toast('Job lancé ! Suivi dans Résultats.', 'success');
    // Reset
    photoFile = videoFile = null;
    document.getElementById('photo-name').textContent = '';
    document.getElementById('video-name').textContent = '';
    document.getElementById('photo-preview').style.display = 'none';
    document.getElementById('video-preview').style.display = 'none';
    document.getElementById('drop-photo').classList.remove('has-file');
    document.getElementById('drop-video').classList.remove('has-file');
    document.getElementById('opt-name').value = '';
    pollQueue();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '🚀 Lancer la génération';
    document.getElementById('progress-wrap').style.display = 'none';
  }
}

// ── Queue preview ────────────────────────────────────────────────────────────
async function pollQueue() {
  try {
    const r = await fetch('/api/jobs');
    const jobs = await r.json();
    const active = Object.values(jobs).filter(j => j.status !== 'completed');
    const el = document.getElementById('queue-preview');
    if (!active.length) { el.innerHTML = ''; return; }
    el.innerHTML = active.reverse().slice(0, 5).map(j => `
      <div class="queue-item">
        <div class="q-status ${j.status}"></div>
        <div class="q-name">${j.name || j.id.slice(0,8)}</div>
        <div class="q-log">${j.log || j.status}</div>
      </div>`).join('');
    if (active.some(j => ['generating','uploading','pending'].includes(j.status)))
      setTimeout(pollQueue, 4000);
  } catch(e) {}
}

pollQueue();

// ── Toast ────────────────────────────────────────────────────────────────────
function toast(msg, type='success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type}`;
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3500);
}
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE RÉSULTATS  (/results)
# ═══════════════════════════════════════════════════════════════════════════════

RESULTS_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Higgsfield Studio — Résultats</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#0a0a0f;color:#e2e8f0;min-height:100vh}
.layout{display:flex;min-height:100vh}
.sidebar{width:220px;background:#060609;border-right:1px solid #1a1a2e;
  display:flex;flex-direction:column;flex-shrink:0}
.logo{padding:24px 20px 20px;border-bottom:1px solid #1a1a2e}
.logo-badge{display:inline-flex;align-items:center;gap:10px}
.logo-icon{width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#7c3aed,#4f46e5);
  display:flex;align-items:center;justify-content:center;font-size:1.1rem}
.logo-name{font-size:.92rem;font-weight:800;color:#f0f0f0;letter-spacing:.03em}
.logo-sub{font-size:.6rem;color:#444;text-transform:uppercase;letter-spacing:.1em;margin-top:2px}
.nav{padding:16px 12px;flex:1;display:flex;flex-direction:column;gap:3px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;
  color:#555;font-size:.88rem;font-weight:600;text-decoration:none;transition:all .15s}
.nav-item:hover{background:#12121f;color:#aaa}
.nav-item.active{background:rgba(124,58,237,.15);color:#a78bfa;
  border-right:3px solid #7c3aed;border-radius:8px 0 0 8px}
.nav-ico{width:18px;height:18px;flex-shrink:0;display:flex;align-items:center;justify-content:center}
.main{flex:1;overflow-y:auto;padding:36px 40px}
h1{font-size:1.7rem;font-weight:800;color:#f8fafc;margin-bottom:6px}
.subtitle{color:#555;font-size:.88rem;margin-bottom:32px;display:flex;align-items:center;gap:12px}
.btn-refresh{background:none;border:1px solid #1a1a2e;border-radius:7px;
  padding:5px 14px;color:#555;font-size:.78rem;cursor:pointer;transition:all .15s}
.btn-refresh:hover{border-color:#7c3aed;color:#a78bfa}
/* Stats bar */
.stats{display:flex;gap:20px;margin-bottom:28px}
.stat{background:#0f0f1a;border:1px solid #1a1a2e;border-radius:12px;
  padding:14px 20px;text-align:center;min-width:90px}
.stat-val{font-size:1.6rem;font-weight:800;color:#f8fafc;line-height:1}
.stat-val.purple{color:#a78bfa}
.stat-val.green{color:#22c55e}
.stat-val.amber{color:#fbbf24}
.stat-val.red{color:#f87171}
.stat-lbl{font-size:.62rem;color:#444;text-transform:uppercase;letter-spacing:.08em;margin-top:4px}
/* Grid */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px}
/* Job card */
.job-card{background:#0f0f1a;border:1px solid #1a1a2e;border-radius:16px;overflow:hidden;
  transition:border-color .2s}
.job-card:hover{border-color:#2a2a3e}
.job-card.completed{border-color:#1a2e1a}
.job-card.error{border-color:#2e1a1a}
.job-card.generating,.job-card.uploading{border-color:#1a1a3e;
  animation:border-pulse 2s ease infinite}
@keyframes border-pulse{0%,100%{border-color:#1a1a3e}50%{border-color:#4f46e5}}
/* Video thumb */
.thumb-wrap{width:100%;aspect-ratio:9/16;background:#060609;position:relative;overflow:hidden;max-height:200px}
.thumb-wrap video{width:100%;height:100%;object-fit:cover}
.thumb-placeholder{width:100%;height:100%;display:flex;align-items:center;justify-content:center;
  flex-direction:column;gap:8px}
.thumb-placeholder .icon{font-size:2rem;opacity:.25}
.thumb-placeholder .status-text{font-size:.75rem;color:#444}
.spinner{width:28px;height:28px;border:3px solid #1a1a2e;border-top-color:#7c3aed;
  border-radius:50%;animation:spin .8s linear infinite;margin:0 auto}
@keyframes spin{to{transform:rotate(360deg)}}
/* Card body */
.card-body{padding:14px 16px}
.card-name{font-size:.88rem;font-weight:700;color:#e2e8f0;margin-bottom:6px;
  display:flex;align-items:center;justify-content:space-between;gap:8px}
.badge{display:inline-block;padding:2px 9px;border-radius:99px;
  font-size:.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;flex-shrink:0}
.badge.completed{background:#052e16;color:#86efac;border:1px solid #166534}
.badge.generating{background:#1e1b4b;color:#a78bfa;border:1px solid #4f46e5}
.badge.uploading{background:#1c1506;color:#fde68a;border:1px solid #d97706}
.badge.error{background:#450a0a;color:#fca5a5;border:1px solid #991b1b}
.badge.pending{background:#1e293b;color:#64748b;border:1px solid #334155}
.card-log{font-size:.72rem;color:#475569;margin-bottom:10px;min-height:18px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-meta{font-size:.68rem;color:#334155;margin-bottom:12px}
/* Actions */
.card-actions{display:flex;gap:8px}
.btn-dl{background:linear-gradient(135deg,#7c3aed,#4f46e5);border:none;border-radius:8px;
  padding:8px 16px;color:#fff;font-size:.78rem;font-weight:700;cursor:pointer;
  text-decoration:none;flex:1;text-align:center;transition:opacity .15s}
.btn-dl:hover{opacity:.85}
.btn-del{background:#1a0a0a;border:1px solid #2e1a1a;border-radius:8px;
  padding:8px 12px;color:#674141;font-size:.78rem;cursor:pointer;transition:all .15s}
.btn-del:hover{background:#2e1a1a;color:#fca5a5}
/* Empty state */
.empty{text-align:center;padding:80px 20px;color:#334155}
.empty-icon{font-size:3rem;opacity:.3;margin-bottom:16px}
.empty-text{font-size:.95rem;margin-bottom:8px}
.empty-hint{font-size:.8rem;color:#1e293b}
</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="logo">
      <div class="logo-badge">
        <div class="logo-icon">🎬</div>
        <div>
          <div class="logo-name">HG Studio</div>
          <div class="logo-sub">AI Video Lab</div>
        </div>
      </div>
    </div>
    <nav class="nav">
      <a href="/" class="nav-item">
        <span class="nav-ico">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7">
            <path d="M2 12V6l6-4 6 4v6a1 1 0 01-1 1H3a1 1 0 01-1-1z"/>
          </svg>
        </span>
        Upload
      </a>
      <a href="/results" class="nav-item active">
        <span class="nav-ico">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7">
            <polygon points="5,2 14,8 5,14"/>
          </svg>
        </span>
        Résultats
      </a>
    </nav>
  </aside>

  <main class="main">
    <h1>Vidéos générées</h1>
    <div class="subtitle">
      <span id="last-refresh">–</span>
      <button class="btn-refresh" onclick="loadJobs()">↺ Actualiser</button>
    </div>

    <div class="stats" id="stats"></div>
    <div class="grid"  id="grid"></div>
  </main>
</div>

<script>
let _autoRefresh = null;

async function loadJobs() {
  try {
    const r    = await fetch('/api/jobs');
    const jobs = await r.json();
    render(jobs);
    document.getElementById('last-refresh').textContent =
      'Actualisé à ' + new Date().toLocaleTimeString('fr-FR');

    const hasActive = Object.values(jobs).some(j =>
      ['pending','uploading','generating'].includes(j.status));
    if (hasActive && !_autoRefresh) {
      _autoRefresh = setInterval(loadJobs, 5000);
    } else if (!hasActive && _autoRefresh) {
      clearInterval(_autoRefresh);
      _autoRefresh = null;
    }
  } catch(e) {
    console.error(e);
  }
}

function render(jobs) {
  const list = Object.values(jobs).reverse();

  // Stats
  const counts = {total:list.length, completed:0, generating:0, error:0};
  list.forEach(j => {
    if (j.status === 'completed') counts.completed++;
    else if (['generating','uploading'].includes(j.status)) counts.generating++;
    else if (j.status === 'error') counts.error++;
  });
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="stat-val">${counts.total}</div><div class="stat-lbl">Total</div></div>
    <div class="stat"><div class="stat-val green">${counts.completed}</div><div class="stat-lbl">Terminés</div></div>
    <div class="stat"><div class="stat-val purple">${counts.generating}</div><div class="stat-lbl">En cours</div></div>
    <div class="stat"><div class="stat-val red">${counts.error}</div><div class="stat-lbl">Erreurs</div></div>
  `;

  if (!list.length) {
    document.getElementById('grid').innerHTML = `
      <div class="empty" style="grid-column:1/-1">
        <div class="empty-icon">🎬</div>
        <div class="empty-text">Aucun job pour l'instant</div>
        <div class="empty-hint"><a href="/" style="color:#4f46e5">Lance ton premier job →</a></div>
      </div>`;
    return;
  }

  document.getElementById('grid').innerHTML = list.map(j => {
    const isActive = ['pending','uploading','generating'].includes(j.status);
    const thumb = j.status === 'completed' && j.output_url
      ? `<video src="${j.output_url}" muted loop playsinline
           onmouseover="this.play()" onmouseout="this.pause();this.currentTime=0"></video>`
      : isActive
        ? `<div class="thumb-placeholder"><div class="spinner"></div>
           <div class="status-text">${j.log || j.status}…</div></div>`
        : `<div class="thumb-placeholder">
           <div class="icon">${j.status === 'error' ? '❌' : '⏳'}</div>
           <div class="status-text">${j.status}</div></div>`;

    const actions = j.status === 'completed' && j.output_url
      ? `<a class="btn-dl" href="${j.output_url}" download>⬇ Télécharger</a>
         <button class="btn-del" onclick="deleteJob('${j.id}')">✕</button>`
      : j.status === 'error'
        ? `<button class="btn-del" style="flex:1" onclick="deleteJob('${j.id}')">✕ Supprimer</button>`
        : `<div style="flex:1;font-size:.72rem;color:#4f46e5">Génération en cours…</div>`;

    const modelLabel = j.model === 'kling3_0' ? 'Kling 3.0' : 'Seedance 2.0';

    return `<div class="job-card ${j.status}">
      <div class="thumb-wrap">${thumb}</div>
      <div class="card-body">
        <div class="card-name">
          <span>${j.name || j.id.slice(0,8)}</span>
          <span class="badge ${j.status}">${j.status}</span>
        </div>
        <div class="card-log">${j.log || '—'}</div>
        <div class="card-meta">${modelLabel} · ${j.duration}s · ${j.created || ''}</div>
        <div class="card-actions">${actions}</div>
      </div>
    </div>`;
  }).join('');
}

async function deleteJob(id) {
  if (!confirm('Supprimer ce job ?')) return;
  await fetch('/api/jobs/' + id, { method: 'DELETE' });
  loadJobs();
}

loadJobs();
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def page_upload():
    return HTMLResponse(UPLOAD_HTML)


@app.get("/results", response_class=HTMLResponse)
def page_results():
    return HTMLResponse(RESULTS_HTML)


@app.get("/api/jobs")
def api_list_jobs():
    return JSONResponse(_jobs)


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return JSONResponse(_jobs[job_id])


@app.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job introuvable")
    job = _jobs.pop(job_id)
    save_jobs()
    # Supprime le fichier de sortie si existant
    out = OUTPUTS_DIR / f"{job_id}.mp4"
    if out.exists():
        try:
            out.unlink()
        except Exception:
            pass
    return JSONResponse({"ok": True})


@app.post("/api/jobs")
async def api_create_job(
    background_tasks: BackgroundTasks,
    photo: UploadFile = File(...),
    video: UploadFile = File(...),
    model: str = Form("seedance_2_0"),
    duration: int = Form(8),
    resolution: str = Form("720p"),
    name: str = Form(""),
):
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="La photo doit être une image")
    if not video.content_type or not video.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Le fichier vidéo est invalide")
    if model not in ("seedance_2_0", "kling3_0"):
        raise HTTPException(status_code=400, detail="Modèle invalide")
    if not (3 <= duration <= 15):
        raise HTTPException(status_code=400, detail="Durée entre 3 et 15 secondes")

    job_id = uuid.uuid4().hex[:12]
    now    = _now()

    # Sauvegarde des fichiers uploadés
    photo_ext = Path(photo.filename or "photo.jpg").suffix or ".jpg"
    video_ext = Path(video.filename or "video.mp4").suffix or ".mp4"
    photo_path = str(UPLOAD_PHOTOS / f"{job_id}{photo_ext}")
    video_path = str(UPLOAD_VIDEOS / f"{job_id}{video_ext}")

    with open(photo_path, "wb") as f:
        f.write(await photo.read())
    with open(video_path, "wb") as f:
        f.write(await video.read())

    # Création du job
    _jobs[job_id] = {
        "id":         job_id,
        "name":       name or Path(video.filename or "video").stem,
        "model":      model,
        "duration":   duration,
        "resolution": resolution,
        "status":     "pending",
        "log":        "En attente de traitement…",
        "created":    now,
        "photo_path": photo_path,
        "video_path": video_path,
        "output_url": None,
        "cdn_url":    None,
    }
    save_jobs()

    # Lance le traitement en arrière-plan
    if model == "kling3_0":
        background_tasks.add_task(
            process_kling,
            job_id, photo_path, video_path, duration, _jobs, save_jobs,
        )
    else:
        background_tasks.add_task(
            process_seedance,
            job_id, photo_path, video_path, duration, resolution, _jobs, save_jobs,
        )

    return JSONResponse({"ok": True, "job_id": job_id})
