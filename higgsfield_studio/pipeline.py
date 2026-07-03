"""
Pipeline de traitement — Higgsfield Studio
Gère l'upload vers Higgsfield CDN + génération via Kling 3.0 / Seedance 2.0
"""

import asyncio
import os
import subprocess
from pathlib import Path

import httpx
import higgsfield_client  # pip install higgsfield-client

# ── Credentials ───────────────────────────────────────────────────────────────
HF_KEY = os.environ.get(
    "HF_KEY",
    "660744e6-d19f-4048-92f3-c9c608639a0b"
    ":cc61021dd15bc0930cf61c6edb9dfed4312bc260f8b7dabd728195fb1a523f78",
)
os.environ["HF_KEY"] = HF_KEY

OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# ── Prompt de remplacement de personne ────────────────────────────────────────
SWAP_PROMPT = (
    "Replace only the person in the scene with the person from the reference photo. "
    "Keep the background, environment, location, camera angle, framing, composition, "
    "lighting, shadows, depth of field, colors, outfit style, pose, facial direction, "
    "body position, image quality, and all surrounding objects exactly identical to "
    "the original. The new person must naturally fit into the scene with realistic "
    "proportions, lighting, skin tones, and perspective. Do not modify the décor, "
    "furniture, walls, floor, accessories, camera settings, or atmosphere. "
    "Preserve every visual detail of the original except for the identity of the person. "
    "Use the reference photo as the identity source. Match facial features, body shape, "
    "skin tone, hairstyle, and overall appearance of the reference person. "
    "Photorealistic, seamless face and body replacement, ultra realistic, natural "
    "integration, high detail, professional photography. "
    "Identity swap only. Background lock. Composition lock. Pose lock. Lighting lock. "
    "Environment lock. Camera lock."
)


def extract_first_frame(video_path: str, output_jpg: str) -> bool:
    """Extrait la première frame d'une vidéo en JPEG."""
    # Essai 1 — OpenCV
    try:
        import cv2  # type: ignore
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()
        if ret:
            cv2.imwrite(output_jpg, frame)
            return True
    except Exception:
        pass

    # Essai 2 — ffmpeg en ligne de commande
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vframes", "1", output_jpg],
            capture_output=True,
            timeout=30,
        )
        if r.returncode == 0 and Path(output_jpg).exists():
            return True
    except Exception:
        pass

    return False


def _upload(path: str, mime: str) -> str:
    """Upload un fichier local sur le CDN Higgsfield, retourne l'URL CDN."""
    return higgsfield_client.upload_file(path, mime)


def _video_mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".m4v": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".webm": "video/webm",
    }.get(ext, "video/mp4")


async def _download_video(url: str, dest: Path) -> None:
    """Télécharge une vidéo depuis une URL CDN vers un fichier local."""
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


# ── Seedance 2.0 — Video reference + identité ─────────────────────────────────
async def process_seedance(
    job_id: str,
    photo_path: str,
    video_path: str,
    duration: int,
    resolution: str,
    jobs: dict,
    save_fn,
) -> None:
    """
    Seedance 2.0 : passe la vidéo source + la photo de référence.
    Le modèle transfère le mouvement de la vidéo en appliquant l'identité de la photo.
    """
    try:
        # ── Étape 1 : upload photo
        _set(jobs, job_id, status="uploading", log="Envoi de la photo de référence vers Higgsfield…")
        save_fn()
        photo_url = await asyncio.to_thread(_upload, photo_path, "image/jpeg")

        # ── Étape 2 : upload vidéo source
        _set(jobs, job_id, log="Photo envoyée. Envoi de la vidéo source…")
        save_fn()
        video_url = await asyncio.to_thread(_upload, video_path, _video_mime(video_path))

        # ── Étape 3 : génération
        _set(jobs, job_id, status="generating", log="Génération Seedance 2.0 en cours…")
        save_fn()

        result = await asyncio.to_thread(
            higgsfield_client.subscribe,
            "seedance_2_0",
            arguments={
                "prompt": SWAP_PROMPT,
                "medias": [
                    {"url": photo_url, "role": "image"},   # identité
                    {"url": video_url, "role": "video"},   # motion / scène
                ],
                "resolution": resolution,
                "mode": "std",
                "duration": duration,
            },
        )

        await _finish(job_id, result, jobs, save_fn)

    except Exception as exc:
        _set(jobs, job_id, status="error", log=f"Erreur : {exc}")
        save_fn()


# ── Kling 3.0 — Motion transfer avec photo de départ ─────────────────────────
async def process_kling(
    job_id: str,
    photo_path: str,
    video_path: str,
    duration: int,
    jobs: dict,
    save_fn,
) -> None:
    """
    Kling 3.0 : utilise la photo comme start_image (identité).
    Extrait la dernière frame de la vidéo pour guider la fin du mouvement.
    """
    try:
        # ── Étape 1 : upload photo de référence
        _set(jobs, job_id, status="uploading", log="Envoi de la photo de référence…")
        save_fn()
        photo_url = await asyncio.to_thread(_upload, photo_path, "image/jpeg")

        # ── Étape 2 : extraire + uploader 1re frame de la vidéo
        _set(jobs, job_id, log="Extraction de la première frame de la vidéo…")
        save_fn()
        frame_jpg = str(OUTPUTS_DIR / f"{job_id}_frame.jpg")
        frame_ok = await asyncio.to_thread(extract_first_frame, video_path, frame_jpg)

        medias = [{"url": photo_url, "role": "start_image"}]
        if frame_ok:
            frame_url = await asyncio.to_thread(_upload, frame_jpg, "image/jpeg")
            medias.append({"url": frame_url, "role": "end_image"})
            _set(jobs, job_id, log="Frame extraite. Génération Kling 3.0 en cours…")
        else:
            _set(jobs, job_id, log="Génération Kling 3.0 en cours (sans frame vidéo)…")
        save_fn()

        # ── Étape 3 : génération
        _set(jobs, job_id, status="generating")
        save_fn()

        result = await asyncio.to_thread(
            higgsfield_client.subscribe,
            "kling3_0",
            arguments={
                "prompt": SWAP_PROMPT,
                "medias": medias,
                "mode": "pro",
                "duration": duration,
                "sound": "off",
            },
        )

        # Nettoyage frame temporaire
        if frame_ok:
            try:
                Path(frame_jpg).unlink()
            except Exception:
                pass

        await _finish(job_id, result, jobs, save_fn)

    except Exception as exc:
        _set(jobs, job_id, status="error", log=f"Erreur : {exc}")
        save_fn()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _set(jobs: dict, job_id: str, **kwargs):
    jobs[job_id].update(kwargs)


async def _finish(job_id: str, result: dict, jobs: dict, save_fn):
    """Récupère l'URL vidéo du résultat et télécharge le fichier."""
    video_cdn = (
        result.get("video", {}).get("url")
        or result.get("url")
        or result.get("video_url")
    )
    if not video_cdn:
        raise ValueError(f"Pas d'URL vidéo dans la réponse : {result}")

    _set(jobs, job_id, log="Téléchargement de la vidéo générée…")
    save_fn()

    dest = OUTPUTS_DIR / f"{job_id}.mp4"
    await _download_video(video_cdn, dest)

    _set(
        jobs, job_id,
        status="completed",
        output_url=f"/outputs/{job_id}.mp4",
        cdn_url=video_cdn,
        log="Vidéo générée avec succès !",
    )
    save_fn()
