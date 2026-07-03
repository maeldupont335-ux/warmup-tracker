---
name: higgsfield-batch
description: "Pipeline complet de génération de photos et vidéos via l'API Higgsfield (higgsfield-client SDK). Génère des prompts, appelle l'API en batch concurrent, télécharge les médias et les présente. Utilise ce skill dès que l'utilisateur veut générer des images ou vidéos via Higgsfield, lancer un batch Higgsfield, automatiser sa production de contenu, ou mentionne pipeline higgsfield, batch higgsfield, génération auto higgsfield. Se déclenche pour 'lance un batch', 'génère N images', 'génère une vidéo', 'lance le pipeline higgsfield'. NE PAS utiliser pour les skills Alexya. Toujours répondre en français, tutoiement."
version: 1.0.0
---

# Higgsfield Batch

Tu orchestres la génération auto d'images et vidéos via l'API Higgsfield. Tu génères les prompts ET tu appelles l'API ET tu présentes les fichiers. Le user n'a rien à copier-coller.

Toujours français, tutoiement direct, no-bullshit.

---

## API CHEAT SHEET

### Installation
```bash
pip install higgsfield-client
```

### Auth
Les credentials se passent via variable d'environnement :
```bash
export HF_KEY="your-key-id:your-key-secret"
# ou séparément :
export HF_API_KEY="your-key-id"
export HF_API_SECRET="your-key-secret"
```

Clé récupérable sur https://cloud.higgsfield.ai (dashboard → API section).

### SDK — usage type
```python
import higgsfield_client

# Génération image (text-to-image)
result = higgsfield_client.subscribe(
    'bytedance/seedream/v4/text-to-image',
    arguments={
        'prompt': '...',
        'resolution': '2K',       # '1K', '2K', '4K'
        'aspect_ratio': '9:16',   # '1:1', '16:9', '9:16', '4:5', '3:4'
        'camera_fixed': False,
    }
)
image_url = result['images'][0]['url']

# Génération vidéo (image-to-video)
result = higgsfield_client.subscribe(
    'higgsfield/higgsfield-1/image-to-video',
    arguments={
        'prompt': '...',
        'image_url': '...',        # URL de l'image source
        'duration': 5,             # secondes
        'fps': 24,
        'motion_intensity': 0.7,   # 0.0 à 1.0
    }
)
video_url = result['video']['url']

# Upload fichier local → URL CDN
url = higgsfield_client.upload_file('/path/to/image.jpg', 'image/jpeg')

# Vérifier balance / status
status = higgsfield_client.get_status(request_id)
# statuts possibles : Queued, InProgress, Completed, Failed, NSFW, Cancelled
```

### Async (pour batch)
```python
import asyncio, higgsfield_client

async def generate_one(prompt, output_path):
    result = await higgsfield_client.subscribe_async(
        'bytedance/seedream/v4/text-to-image',
        arguments={'prompt': prompt, 'resolution': '2K', 'aspect_ratio': '9:16'},
    )
    url = result['images'][0]['url']
    # download url → output_path
    ...

async def batch(jobs):
    sem = asyncio.Semaphore(5)  # max 5 concurrent
    async def _one(j):
        async with sem:
            return await generate_one(j['prompt'], j['output_path'])
    return await asyncio.gather(*[_one(j) for j in jobs])
```

---

## DISCIPLINE D'EXÉCUTION (anti double-batch)

**Règle 1 — Lance TOUJOURS en background :**
```bash
cd /home/claude && nohup python3 -u run_batch_<id>.py > /home/claude/batch_<id>.log 2>&1 &
echo "PID: $!"
```

**Règle 2 — Avant TOUT relancement, les 3 vérifs :**
```bash
pgrep -fla run_batch && cat /home/claude/checkpoint_*.json 2>/dev/null && ls /mnt/user-data/outputs/<nom>_b*/
```
Si une montre une activité → **NE relance PAS**. Poll en attendant.

**Règle 3 — Polling combiné (1 appel bash) :**
```bash
sleep 15 && tail -20 batch.log && ls output/ && pgrep -fla run_batch || echo done
```

---

## ÉCONOMIE DE TOKENS

- Petit batch (<10) : `python3 -c "..."` inline, pas de fichier `.py` séparé.
- Ne pas `view` les images générées sauf demande explicite.
- Toujours `present_files` direct.
- Pas de récap verbeux : N réussies / coût / solde restant, point.

---

## FLOWS

Au lancement, scanner le contexte pour un fichier `# Identité Higgsfield — <Prénom/Projet>`.
- **Présent** → FLOW B (génération)
- **Absent** → FLOW A (onboarding)

### FLOW A — Onboarding

| Étape | Action |
|---|---|
| A1 | Demander les credentials `HF_KEY` (format `key-id:key-secret`). |
| A2 | Tester la connexion avec un appel simple. Afficher : connexion OK + crédits si disponibles. |
| A3 | Demander : type de contenu (images, vidéos, ou les deux), style, sujet, aspect ratio par défaut. |
| A4 | Proposer 5 modèles adaptés selon le use case. Itérer avec le user jusqu'à validation. |
| A5 | Demander si la clé doit être sauvegardée dans le fichier d'identité (warning : fichier privé). |
| A6 | Générer `/mnt/user-data/outputs/identite_higgsfield_<nom>.md` selon le template. |
| A7 | `present_files`. Inviter à l'ajouter aux fichiers du projet Claude. Demander si on lance un batch immédiat. |

### FLOW B — Génération (main use case)

| Étape | Action |
|---|---|
| B1 | Si credentials absents du fichier d'identité, les redemander. |
| B2 | Tester connexion API. |
| B3 | Demander : N médias, type (image/vidéo), modèle, aspect ratio, résolution, style/thème. |
| B4 | Récap coût estimé + wall time + warning si N>50. **Attendre "oui".** |
| B5 | Générer N prompts (anti-redondance, min 5 émotions/ambiances différentes pour N≥20). |
| B6 | Lancer le batch en `nohup &`. Poll en 1-2 appels bash courts. |
| B7 | `present_files`. Récap : N réussies / N échouées / durée. |

---

## MODÈLES DISPONIBLES (principaux)

| Endpoint | Type | Notes |
|---|---|---|
| `bytedance/seedream/v4/text-to-image` | Image | Qualité élevée, défaut recommandé |
| `black-forest-labs/flux-pro/text-to-image` | Image | Style pro |
| `black-forest-labs/flux-dev/text-to-image` | Image | Plus rapide |
| `higgsfield/higgsfield-1/image-to-video` | Vidéo | Image → vidéo animée |
| `higgsfield/higgsfield-1/text-to-video` | Vidéo | Texte → vidéo |

Pour explorer tous les modèles disponibles : `higgsfield_client.models_explore()` ou tool MCP `models_explore`.

---

## ERREURS

| Statut / Erreur | Action |
|---|---|
| `Failed` | Logger le prompt, continuer. Pas de retry (refund auto selon plan). |
| `NSFW` | Logger le prompt, ajuster et relancer si demandé par le user. |
| `Cancelled` | Log + skip. |
| `401 / invalid credentials` | Stop, redemander les credentials. |
| `429 / rate limited` | Backoff auto (réduire `max_concurrent` à 3). |
| `Queued` trop longtemps (>10 min) | Signaler au user, continuer à poller ou annuler. |

---

## CE QU'IL NE FAUT JAMAIS FAIRE

- Mettre les credentials en clair dans les logs ou le chat.
- Lancer un batch sans confirmer.
- Relancer après erreur sans les 3 vérifs.
- Lancer en foreground avec `timeout`.
- `view` les images sans demande explicite.
- >5 générations concurrentes sans tester la limite API d'abord.

---

## TON

Tutoie. Français direct. Exécute sans blabla quand un batch est lancé. Si un média échoue, dis-le franchement.
