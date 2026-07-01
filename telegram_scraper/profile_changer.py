"""
profile_changer.py — Applique photo, prénom, @username et bio sur Telegram Web K
Usage : python profile_changer.py <profile_id> [--silent]

Flow Telegram Web K :
  1. Hamburger (haut-gauche) → Settings
  2. Photo : clic avatar → Upload Photo → file chooser → confirmer crop
  3. Nom : clic crayon (haut-droite) → 1er input = prénom, 2e input = nom (clear) → sauver
  4. Bio / username : même formulaire d'édition
"""

import asyncio
import base64
import os
import sys
import json
import tempfile
import requests
from playwright.async_api import async_playwright

# ── Config ──────────────────────────────────────────────────
SUPABASE_URL  = "https://pirlgavzihmnwmqlyeir.supabase.co"
SUPABASE_KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBpcmxnYXZ6aWhtbndtcWx5ZWlyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3MzQxMTAsImV4cCI6MjA5NTMxMDExMH0.0QdskD9IBsx1rUZ_7Sljb8DshovkQMJIhmnAM-Zc6Ps"
SUPABASE_HDRS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
}

ADSPOWER_API   = "http://local.adspower.net:50325"
ADSPOWER_KEY   = "942d5c4fa00deedac520c3310912ee6100795935b355b33b"
DASHBOARD_URL  = "https://warmup-tracker.onrender.com"
DASHBOARD_TOKEN = "Compte.1"


def _report_result(profile_id: str, ok: bool, error: str = "", error_type: str = ""):
    """
    Envoie le résultat au dashboard.
    error_type: "" | "not_connected" | "upload_failed" | "adspower"
    """
    try:
        requests.post(
            f"{DASHBOARD_URL}/api/setup/apply-result",
            json={"token": DASHBOARD_TOKEN, "profile_id": profile_id,
                  "ok": ok, "error": error, "error_type": error_type},
            timeout=8,
        )
    except Exception:
        pass  # Ne pas bloquer si le dashboard est injoignable


# ── AdsPower helpers ─────────────────────────────────────────

def start_browser(profile_id: str) -> str:
    launch_args = json.dumps(["--window-size=1100,750", "--window-position=60,40"])
    r = requests.get(
        f"{ADSPOWER_API}/api/v1/browser/start",
        params={"user_id": profile_id, "api_key": ADSPOWER_KEY,
                "launch_args": launch_args},
        headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
        timeout=15,
    )
    data = r.json()
    if data.get("code") != 0:
        raise Exception(f"AdsPower erreur : {data.get('msg')}")
    return data["data"]["ws"]["puppeteer"]


def stop_browser(profile_id: str):
    try:
        requests.get(
            f"{ADSPOWER_API}/api/v1/browser/stop",
            params={"user_id": profile_id, "api_key": ADSPOWER_KEY},
            headers={"Authorization": f"Bearer {ADSPOWER_KEY}"},
            timeout=10,
        )
    except Exception:
        pass


# ── Supabase helpers ─────────────────────────────────────────

def load_config(profile_id: str) -> dict | None:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/profile_setup",
        headers=SUPABASE_HDRS,
        params={"profile_id": f"eq.{profile_id}", "select": "*"},
        timeout=10,
    )
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return None


# ── Telegram helpers ─────────────────────────────────────────

async def wait_telegram(page) -> bool:
    """
    Attend que Telegram Web K soit prêt (connecté).
    Stratégies dans l'ordre :
      1. Chatlist visible (idéal)
      2. Sidebar gauche présente + pas sur écran de login
    """
    for _ in range(30):
        # Priorité 1 : la chatlist est visible — cas idéal
        try:
            if await page.locator(
                ".chatlist-chat, li.chatlist-chat, .conversations-all, "
                ".chat-list, .sidebar-left-content"
            ).first.is_visible(timeout=800):
                return True
        except Exception:
            pass

        # Priorité 2 : sidebar gauche chargée → Telegram est ouvert
        # (peut être sur un canal, un chat, les settings — pas la chatlist)
        try:
            if await page.locator(
                ".sidebar-left, .sidebar-left-header, "
                ".input-search, .el-container"
            ).first.is_visible(timeout=800):
                # S'assurer qu'on n'est PAS sur l'écran de connexion
                on_login = await page.evaluate("""
                    () => {
                        const sels = ['.auth-pages', '.page-sign', '.page-auth',
                                      'form[action*="auth"]'];
                        if (sels.some(s => document.querySelector(s))) return true;
                        const txt = (document.body.innerText || '').toLowerCase();
                        return ['your phone number', 'sign in to telegram',
                                'log in with phone'].some(w => txt.includes(w));
                    }
                """)
                if not on_login:
                    return True
        except Exception:
            pass

        await page.wait_for_timeout(1000)
    return False


async def _click_first_visible(page, selectors: list, timeout_ms: int = 2000) -> bool:
    """Clic sur le premier sélecteur visible parmi la liste."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=timeout_ms):
                await el.click()
                return True
        except Exception:
            continue
    return False


# ── Étape 1 : Ouvrir Settings ────────────────────────────────

async def open_settings(page) -> bool:
    """
    Ouvre le panneau Settings de Telegram Web K.
    Stratégies (dans l'ordre) :
      1. Hamburger (.btn-icon) → clic sur l'item "Settings" dans le menu
      2. Scan JS de tous les boutons visibles pour trouver le hamburger
      3. Scan JS du menu ouvert pour trouver "Settings"
      4. Fallback : clic sur le nom/avatar en haut à gauche de la sidebar
    """
    import tempfile, os as _os
    print("  [->] Ouverture Settings...", flush=True)

    # ── Helper : vérifier si le panneau Settings est ouvert ───
    async def settings_open() -> bool:
        # Sélecteurs STRICTS uniquement — éviter les faux positifs sur le chatlist
        # (pas de .tabs-container, .shared-media, .profile-container qui matchent ailleurs)
        for sel in [
            ".settings-container",
            ".settings-main",
            "[class*='settings-main']",
            "[class*='settings-container']",
            ".edit-profile-container",
            "form.edit-peer-profile",
            ".sidebar-left.settings",
            "[class*='sidebar-left'][class*='setting']",
        ]:
            try:
                if await page.locator(sel).first.is_visible(timeout=400):
                    return True
            except Exception:
                pass
        # Vérification JS : avatar sans "dialog-avatar" (chatlist) dans la zone Settings
        try:
            result = await page.evaluate("""
                () => {
                    // Un avatar dans les Settings n'a PAS la classe dialog-avatar
                    const av = document.querySelector(
                        '.settings-main-profile .avatar, .profile-big .avatar'
                    );
                    return av ? av.getBoundingClientRect().width > 0 : false;
                }
            """)
            if result:
                return True
        except Exception:
            pass
        return False

    # ── Helper : fermer le panneau Settings via son bouton close ──
    # Escape ne ferme PAS Settings dans Telegram Web K — il faut le bouton ×.
    async def _close_settings_panel():
        closed = await page.evaluate("""
            () => {
                const sels = [
                    '.sidebar-close-button.is-visible',
                    '.sidebar-close-button',
                    'button[class*="sidebar-close"]',
                ];
                for (const sel of sels) {
                    const el = document.querySelector(sel);
                    if (!el) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width > 0) { el.click(); return true; }
                }
                return false;
            }
        """)
        await page.wait_for_timeout(700)
        if not closed:
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(400)
            except Exception:
                pass

    # ── Retour à la chatlist SANS recharger la page ────────────
    # page.goto() sur Telegram Web K (SPA) force un reload complet → page blanche.
    # On ne reload QUE si on n'est pas du tout sur Telegram.
    current_url = page.url
    if "web.telegram.org" not in current_url:
        try:
            await page.goto("https://web.telegram.org/k/",
                            wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
        except Exception:
            pass
    else:
        # Fermeture agressive de tout panneau secondaire jusqu'au chatlist
        # (Settings, profil, recherche, etc.) — peu importe l'état actuel.
        for _attempt in range(12):
            # Vérifier si on est déjà sur le chatlist (hamburger avec is-visible)
            on_chatlist = await page.evaluate("""
                () => {
                    const el = document.querySelector('button.sidebar-tools-button');
                    return el ? el.className.includes('is-visible') : false;
                }
            """)
            if on_chatlist:
                break

            # Tenter de fermer via tous les boutons close/back possibles
            closed = await page.evaluate("""
                () => {
                    const SELS = [
                        '.sidebar-close-button.is-visible',
                        '.sidebar-close-button',
                        'button[class*="sidebar-close"]',
                        '.sidebar-back-button.is-visible',
                        '.sidebar-back-button',
                        'button[class*="sidebar-back"]',
                        '.btn-icon.tgico-close',
                        '.btn-icon.tgico-back',
                    ];
                    for (const sel of SELS) {
                        const el = document.querySelector(sel);
                        if (!el) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width > 0) { el.click(); return sel; }
                    }
                    return null;
                }
            """)
            if not closed:
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
            await page.wait_for_timeout(400)

    await page.wait_for_timeout(400)

    # ── PRÉ-ÉTAPE : fermer tout panneau secondaire (back button) ──
    # Si Telegram affiche un panneau secondaire (recherche, contact…)
    # le hamburger est caché derrière le back-button.
    # On vérifie d'abord si le hamburger est déjà visible ; si non, on clique le back-button.
    # On s'arrête dès que le hamburger est visible (pas besoin de continuer).
    for _ in range(6):
        # Arrêter immédiatement si le hamburger est déjà visible
        hamburger_visible = await page.evaluate("""
            () => {
                const NEVER = ['close','back','tgico-close','tgico-back','search','input-search'];
                const sels = [
                    'button.sidebar-tools-button', 'button[class*="sidebar-tools"]',
                    'button.tgico-menu',            'button[class*="tgico-menu"]',
                ];
                return sels.some(sel =>
                    Array.from(document.querySelectorAll(sel)).some(el => {
                        const cls = (el.className || '').toLowerCase();
                        if (NEVER.some(w => cls.includes(w))) return false;
                        return el.getBoundingClientRect().width > 0;
                    })
                );
            }
        """)
        if hamburger_visible:
            break
        closed = await page.evaluate("""
            () => {
                const BACK_SELS = [
                    '.sidebar-back-button.is-visible',
                    '[class*="sidebar-back-button"][class*="is-visible"]',
                    '.sidebar-back-button',
                ];
                for (const sel of BACK_SELS) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0) { el.click(); return true; }
                    }
                }
                return false;
            }
        """)
        if not closed:
            break
        print("  [->] Back-button → retour chatlist", flush=True)
        await page.wait_for_timeout(500)

    await page.wait_for_timeout(400)

    # ── Attente que le hamburger principal soit pleinement visible (is-visible) ──
    # La classe "is-visible" est ajoutée par Telegram Web K seulement quand on est
    # sur le chatlist principal. Sans elle, le bouton trouvé est celui du panneau
    # Settings/secondaire — cliquer dessus ouvre un mauvais menu.
    for _ in range(12):  # max 3 s
        _is_vis = await page.evaluate("""
            () => {
                const el = document.querySelector('button.sidebar-tools-button');
                return el ? el.className.includes('is-visible') : false;
            }
        """)
        if _is_vis:
            break
        await page.wait_for_timeout(250)

    # ── Étape 1 : clic sur le hamburger ───────────────────────
    hamburger_ok = False

    # ══════════════════════════════════════════════════════════════
    # D'après les logs de debug, le hamburger dans cette version de
    # Telegram Web K est un <button> avec les classes :
    #   "btn-icon rp btn-menu-toggle sidebar-tools-button is-visible"
    # Le sélecteur précédent (tgico-menu, sidebar-open-button) ne matchait pas.
    # ══════════════════════════════════════════════════════════════

    # ── Stratégie 0 : sélecteurs CSS connus (button tag) ─────────
    burger_js = await page.evaluate("""
        () => {
            const NEVER = ['close','back','tgico-close','tgico-back',
                           'search','input-search'];
            const BURGER_SELS = [
                // Classe exacte connue des logs
                'button.sidebar-tools-button',
                'button[class*="sidebar-tools"]',
                // Variantes anciennes
                'button.tgico-menu',
                'button[class*="tgico-menu"]',
                'button.sidebar-open-button',
                'button[class*="sidebar-open"]',
                // Fallback : btn-menu-toggle visible (exclu close/back)
                'button.btn-menu-toggle',
                'button[class*="btn-menu-toggle"]',
            ];
            for (const sel of BURGER_SELS) {
                const candidates = Array.from(document.querySelectorAll(sel))
                    .filter(el => {
                        const cls = (el.className || '').toLowerCase();
                        if (NEVER.some(w => cls.includes(w))) return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0;   // visible uniquement
                    });
                if (candidates.length > 0) {
                    const el = candidates[0];
                    const r  = el.getBoundingClientRect();
                    return {found: true, x: r.left+r.width/2, y: r.top+r.height/2,
                            cls: el.className, sel};
                }
            }
            return {found: false};
        }
    """)
    if isinstance(burger_js, dict) and burger_js.get("found"):
        cx, cy = burger_js["x"], burger_js["y"]
        print(f"  [->] Hamburger CSS @ ({cx:.0f},{cy:.0f}) "
              f"cls={burger_js.get('cls','')[:70]}", flush=True)
        # Clic JS d'abord (plus fiable que mouse.click pour déclencher les handlers)
        await page.evaluate("""
            () => {
                const el = document.querySelector('button.sidebar-tools-button');
                if (el) {
                    el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true}));
                    el.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true, cancelable:true}));
                    el.dispatchEvent(new MouseEvent('click',     {bubbles:true, cancelable:true}));
                }
            }
        """)
        await page.wait_for_timeout(100)
        # Aussi mouse.click physique comme backup
        await page.mouse.click(cx, cy)
        hamburger_ok = True
        print(f"  [OK] Hamburger cliqué (CSS)", flush=True)

    # ── Stratégie 1 : elementFromPoint — gère aussi les <div> ────
    # Le bouton peut être un <div class="btn-icon ..."> pas forcément <button>
    if not hamburger_ok:
        found_coord = await page.evaluate("""
            () => {
                const BAD = ['search','input-search','tgico-search',
                             'close','back','tgico-back','tgico-close',
                             'sidebar-back'];
                const POSITIONS = [
                    [22,28],[22,32],[15,28],[15,35],[20,28],[30,32],[36,28]
                ];
                for (const [x, y] of POSITIONS) {
                    const el = document.elementFromPoint(x, y);
                    if (!el) continue;
                    // Chercher l'ancêtre bouton — <button> OU <div class="btn-icon">
                    const btn = el.closest('button') ||
                                el.closest('.btn-icon') ||
                                el.closest('[class*="sidebar-tools"]') ||
                                el.closest('[class*="tgico-menu"]');
                    if (!btn) continue;
                    const cls = (btn.className || '').toLowerCase();
                    if (BAD.some(w => cls.includes(w))) continue;
                    const r = btn.getBoundingClientRect();
                    if (r.width === 0) continue;
                    return {found: true, srcX: x, srcY: y,
                            x: r.left+r.width/2, y: r.top+r.height/2,
                            cls: btn.className.slice(0,70)};
                }
                return {found: false};
            }
        """)
        if isinstance(found_coord, dict) and found_coord.get("found"):
            cx, cy = found_coord["x"], found_coord["y"]
            print(f"  [->] Hamburger elementFromPoint ({found_coord.get('srcX')},{found_coord.get('srcY')}) "
                  f"→ ({cx:.0f},{cy:.0f}) cls={found_coord.get('cls','')[:70]}", flush=True)
            await page.mouse.click(cx, cy)
            hamburger_ok = True
            print(f"  [OK] Hamburger cliqué (elementFromPoint)", flush=True)

    # ── Stratégie 2 : Playwright force=True ──────────────────────
    if not hamburger_ok:
        for sel in [
            "button.sidebar-tools-button",
            "button[class*='sidebar-tools']",
            "button.tgico-menu", "button[class*='tgico-menu']",
            "button.btn-menu-toggle:not(.sidebar-close-button)",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(force=True)
                    hamburger_ok = True
                    print(f"  [OK] Hamburger cliqué CSS force ({sel})", flush=True)
                    break
            except Exception:
                continue

    if hamburger_ok:
        # IMPORTANT : chercher l'item Settings dans le menu AVANT de vérifier settings_open()
        # (settings_open() donnait un faux positif sur le chatlist)
        settings_clicked = False

        for _retry in range(3):
            # Attendre que le menu apparaisse avec wait_for_selector (plus réactif qu'un délai fixe)
            menu_detected = False
            try:
                await page.wait_for_selector(
                    '.btn-menu.active, .btn-menu[class*="active"], .btn-menu-overlay',
                    state="visible", timeout=2000
                )
                menu_detected = True
            except Exception:
                pass

            if not menu_detected:
                await page.wait_for_timeout(300)

            # Debug : dump du contenu du menu au 1er essai
            if _retry == 0:
                _menu_dump = await page.evaluate("""
                    () => {
                        const info = {menus: [], items: []};
                        document.querySelectorAll('[class*="btn-menu"]').forEach(el => {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0)
                                info.menus.push({cls: el.className.slice(0,60), w: Math.round(r.width), h: Math.round(r.height)});
                        });
                        document.querySelectorAll('.btn-menu-item, [class*="menu-item"]').forEach(el => {
                            if (el.offsetParent !== null)
                                info.items.push((el.textContent||'').trim().slice(0,30));
                        });
                        return info;
                    }
                """)
                print(f"  [i] Menu dump : {_menu_dump}", flush=True)

            # 1. Chercher l'item Settings dans le menu déroulant — PRIORITÉ
            found = await page.evaluate("""
                () => {
                    // Dump de tous les items du menu pour debug
                    function _dumpMenu(c) {
                        if (!c || c.getBoundingClientRect().width === 0) return null;
                        const items = Array.from(c.querySelectorAll('.btn-menu-item, li, [class*="menu-item"]'));
                        return items.map(i => (i.textContent||'').trim().slice(0,25)).filter(t => t.length > 0);
                    }
                    function _tryContainer(c) {
                        if (!c) return null;
                        const r = c.getBoundingClientRect();
                        if (r.width === 0) return null;
                        const items = c.querySelectorAll('.btn-menu-item, li, [class*="menu-item"]');
                        for (const it of items) {
                            if (it.querySelector('.icon-settings,.tgico-settings,[class*="icon-settings"],[class*="tgico-settings"]')) {
                                it.click();
                                return 'icon: ' + (it.textContent || '').trim().slice(0, 20);
                            }
                        }
                        for (const it of items) {
                            const t = (it.textContent || '').trim().toLowerCase();
                            if (t.length < 40 && (t.includes('setting') || t.includes('paramètre') || t.includes('настройк'))) {
                                it.click();
                                return 'text: ' + t.slice(0, 20);
                            }
                        }
                        return null;
                    }
                    // Sélecteurs connus du menu hamburger Telegram Web K
                    const MENU_CONTAINERS = [
                        '.btn-menu.active',
                        'div[class*="btn-menu"][class*="active"]',
                        '.popup-menu',
                        '.menu-open',
                        // Le menu peut être un frère du bouton hamburger
                        '.sidebar-tools-button + .btn-menu',
                        'button.sidebar-tools-button ~ .btn-menu',
                    ];
                    for (const s of MENU_CONTAINERS) {
                        const el = document.querySelector(s);
                        if (el) {
                            const dump = _dumpMenu(el);
                            if (dump && dump.length > 0) {
                                console.log('[DEBUG menu]', JSON.stringify(dump));
                            }
                            const f = _tryContainer(el);
                            if (f) return f;
                        }
                    }
                    // Fallback global : tous les éléments btn-menu-item visibles
                    const all = document.querySelectorAll('.btn-menu-item, [class*="menu-item"]');
                    for (const el of all) {
                        if (el.offsetParent === null) continue;
                        const t = (el.textContent || '').trim();
                        if (t.length > 40) continue;
                        if (t.toLowerCase().includes('setting') || t.toLowerCase().includes('paramètre')) {
                            el.click();
                            return 'global: ' + t;
                        }
                    }
                    return null;
                }
            """)

            if found:
                settings_clicked = True
                print(f"  [OK] Settings via JS : '{found}'", flush=True)
                break

            # 2. Vérifier si Settings s'est ouvert SANS menu intermédiaire
            #    (seulement avec sélecteurs stricts, pas de faux positifs)
            if await settings_open():
                print("  [OK] Panneau Settings ouvert directement", flush=True)
                return True

            # Re-cliquer hamburger SEULEMENT si menu fermé (sinon on le fermerait!)
            if _retry < 2:
                menu_still_open = await page.evaluate("""
                    () => {
                        const m = document.querySelector('.btn-menu.active, .btn-menu-overlay');
                        return m ? m.getBoundingClientRect().width > 0 : false;
                    }
                """)
                if not menu_still_open:
                    print(f"  [i] Re-clic hamburger ({_retry + 2}/3)...", flush=True)
                    await page.evaluate("""
                        () => {
                            const el = document.querySelector('button.sidebar-tools-button');
                            if (el) {
                                el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true}));
                                el.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true, cancelable:true}));
                                el.dispatchEvent(new MouseEvent('click',     {bubbles:true, cancelable:true}));
                            }
                        }
                    """)

        if settings_clicked:
            await page.wait_for_timeout(2000)
            if await settings_open():
                print("  [OK] Panneau Settings confirmé ouvert", flush=True)
            else:
                print("  [i] Settings cliqué (panneau non confirmé)", flush=True)
            return True

    # ── Fallback : clic sur le profil / nom d'utilisateur en haut ─
    print("  [i] Menu hamburger sans succès — tentative clic profil...", flush=True)
    profile_clicked = await _click_first_visible(page, [
        ".sidebar-left-header .info",
        ".sidebar-left-header .user-title",
        ".sidebar-left-header .details",
        ".sidebar-left .row-name",
        ".sidebar-left .profile",
        ".profile-mini-app",
        ".user-info",
    ])
    if profile_clicked:
        await page.wait_for_timeout(1800)
        print("  [OK] Profil/nom cliqué (fallback)", flush=True)
        if await settings_open():
            return True

    # ── Screenshot de debug ────────────────────────────────────
    try:
        tmp = _os.path.join(tempfile.gettempdir(), "tg_settings_debug.png")
        await page.screenshot(path=tmp)
        print(f"  [i] Screenshot debug : {tmp}", flush=True)
    except Exception:
        pass

    print("  [!] Impossible d'ouvrir les Settings — tentative continuée quand même", flush=True)
    return False


# ── Étape 2 : Ouvrir le mode édition (crayon haut-droite) ────

async def open_edit_mode(page) -> bool:
    """
    Clique sur le bouton crayon ✏ dans le header Settings.
    D'après les logs : le crayon a la classe 'btn-icon rp' (sans classe spéciale),
    contrairement au close ('sidebar-close-button') et au menu ('btn-menu-toggle').
    """
    await page.wait_for_timeout(2000)

    # ── Stratégie 1 : CSS directs ─────────────────────────────
    pencil_ok = await _click_first_visible(page, [
        "button.btn-icon.tgico-edit",
        "button[class*='tgico-edit']",
        "button[class*='tgico-pen']",
        "button.btn-icon[title*='Edit']",
        "button.btn-icon[aria-label*='Edit']",
    ])
    if pencil_ok:
        await page.wait_for_timeout(1500)
        print("  [OK] Mode édition activé (CSS)", flush=True)
        return True

    # ── Stratégie 2 : JS — btn-icon en haut, exclu close/menu ─
    # Le header Settings a : ← (back) | ⊞ QR (x≈252) | ✏ crayon (x≈296) | ⋮ menu (exclu)
    # Le crayon est le bouton NON-EXCLU le PLUS À DROITE dans le header.
    # IMPORTANT : ne PAS prendre le premier par ordre DOM (c'est le QR code, pas le crayon).
    result = await page.evaluate("""
        () => {
            const EXCLUDE = [
                'sidebar-close-button', 'btn-menu-toggle', 'sidebar-tools-button',
                'input-search', 'sidebar-emoji-status', 'back-button',
                'endcall', 'topbar-call', 'call-button', 'topbar-btn',
                'close', 'tgico-close', 'tgico-back',
                'tgico-qr',  // QR code button
            ];
            const candidates = Array.from(document.querySelectorAll('button.btn-icon'))
                .filter(b => {
                    if (b.offsetParent === null) return false;
                    const cls = b.className || '';
                    if (EXCLUDE.some(ex => cls.includes(ex))) return false;
                    // Exclure les boutons contenant un SVG ou icon QR (heuristic)
                    if (b.querySelector('[class*="qr"]')) return false;
                    return true;
                })
                .sort((a, b) => {
                    const ra = a.getBoundingClientRect();
                    const rb = b.getBoundingClientRect();
                    // Même rangée (y diff < 15px) → prendre le PLUS À DROITE (crayon, pas QR)
                    if (Math.abs(ra.top - rb.top) < 15) {
                        return rb.left - ra.left;  // droite en premier
                    }
                    return ra.top - rb.top;  // sinon rangée la plus haute
                });
            if (candidates.length > 0) {
                candidates[0].click();
                const r = candidates[0].getBoundingClientRect();
                return 'pencil: ' + candidates[0].className + ' @(' + Math.round(r.left+r.width/2) + ',' + Math.round(r.top+r.height/2) + ')';
            }
            return null;
        }
    """)
    if result:
        await page.wait_for_timeout(1500)
        print(f"  [OK] Mode édition activé (JS: {result})", flush=True)
        return True

    print("  [!] Bouton crayon non trouvé", flush=True)
    return False


# ── Étape 3 : Remplir prénom / nom / bio ─────────────────────

async def fill_name_bio(page, first_name: str, bio: str) -> bool:
    """
    Remplit prénom (1er champ), vide nom (2e champ), remplit bio.
    Telegram Web K utilise des div[contenteditable] et non des <input>.
    """
    await page.wait_for_timeout(800)

    # Sélecteur unifié : div contenteditable ET input classique
    field_sel = (
        "div.input-field-input[contenteditable='true'], "
        "div[contenteditable='true'].input-field-input, "
        "div.input-field-input[contenteditable], "
        "input.input-field-input, "
        "input[type='text']:not([type='hidden'])"
    )
    fields = page.locator(field_sel)

    visible_fields = []
    cnt = await fields.count()
    for i in range(cnt):
        el = fields.nth(i)
        try:
            if await el.is_visible(timeout=400):
                visible_fields.append(el)
        except Exception:
            pass

    print(f"  [i] {len(visible_fields)} champ(s) visibles dans le formulaire", flush=True)

    # Helper : lire la valeur d'un champ (input ou contenteditable)
    async def _read(el):
        try:
            return await el.input_value()
        except Exception:
            try:
                return await el.inner_text()
            except Exception:
                return ""

    # Helper : écrire dans un champ
    async def _write(el, text: str):
        await el.click()
        await page.wait_for_timeout(100)
        await page.keyboard.press("Control+a")
        await page.wait_for_timeout(80)
        if text:
            await page.keyboard.type(text, delay=25)
        else:
            await page.keyboard.press("Delete")
        await page.wait_for_timeout(300)

    # ── 1er champ = Prénom ──────────────────────────────────────
    if first_name and visible_fields:
        try:
            await _write(visible_fields[0], first_name)
            print(f"  [OK] Prénom : {first_name}", flush=True)
        except Exception as e:
            print(f"  [!] Erreur prénom : {e}", flush=True)

    # ── 2e champ = Nom (à vider) ────────────────────────────────
    if len(visible_fields) >= 2:
        try:
            current_val = (await _read(visible_fields[1])).strip()
            if current_val:
                await _write(visible_fields[1], "")
                print(f"  [OK] Nom de famille effacé (était : {current_val})", flush=True)
            else:
                print("  [i] Nom de famille déjà vide", flush=True)
        except Exception as e:
            print(f"  [!] Erreur suppression nom : {e}", flush=True)

    # ── Bio : textarea OU div contenteditable ───────────────────
    if bio:
        bio_sel = (
            "div.input-field-input[contenteditable='true']:last-of-type, "
            "div[contenteditable='true']:last-of-type, "
            "textarea.input-field-textarea, textarea"
        )
        bios = page.locator(bio_sel)
        bio_cnt = await bios.count()
        wrote_bio = False
        for i in range(bio_cnt):
            ta = bios.nth(i)
            try:
                if await ta.is_visible(timeout=400):
                    await _write(ta, bio)
                    print(f"  [OK] Bio : {bio[:50]}{'…' if len(bio)>50 else ''}", flush=True)
                    wrote_bio = True
                    break
            except Exception:
                continue
        # Fallback : 3e champ visible (souvent la bio)
        if not wrote_bio and len(visible_fields) >= 3:
            try:
                await _write(visible_fields[2], bio)
                print(f"  [OK] Bio (champ 3) : {bio[:50]}", flush=True)
            except Exception as e:
                print(f"  [!] Erreur bio : {e}", flush=True)

    return True


async def fill_username(page, username: str) -> bool:
    """
    Remplit le champ @username.
    Dans Telegram Web K, le username se modifie via une ligne cliquable
    qui ouvre un formulaire séparé.
    """
    if not username:
        return True
    username = username.strip().lstrip("@")

    # 1. Chercher un input/div username direct dans le formulaire actuel
    username_selectors = [
        "input[name='username']",
        "input[placeholder*='username']",
        "input[placeholder*='Username']",
        "input[placeholder*='@']",
        "div.input-field-input[contenteditable][placeholder*='username']",
        "div.input-field-input[contenteditable][placeholder*='Username']",
    ]
    for sel in username_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=800):
                await el.click()
                await page.keyboard.press("Control+a")
                await page.wait_for_timeout(100)
                await page.keyboard.type(username, delay=25)
                await page.wait_for_timeout(1500)  # attendre validation serveur
                print(f"  [OK] @Username : @{username}", flush=True)
                return True
        except Exception:
            continue

    # 2. Telegram Web K : le username est souvent une ligne cliquable séparée
    #    Chercher une ligne qui contient "@" ou "username" pour l'ouvrir
    row_selectors = [
        ".profile-info-row[data-peer-property='username']",
        ".row[onclick*='username']",
        ".sidebar-left-section-content .row",
    ]
    for sel in row_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=600):
                await el.click()
                await page.wait_for_timeout(1500)
                # Chercher l'input qui vient d'apparaître
                for inp_sel in ["input[name='username']", "input[placeholder*='username']",
                                "div.input-field-input[contenteditable]"]:
                    try:
                        inp = page.locator(inp_sel).first
                        if await inp.is_visible(timeout=1000):
                            await inp.click()
                            await page.keyboard.press("Control+a")
                            await page.keyboard.type(username, delay=25)
                            await page.wait_for_timeout(1500)
                            print(f"  [OK] @Username via row : @{username}", flush=True)
                            return True
                    except Exception:
                        continue
        except Exception:
            continue

    print("  [i] Champ @username non trouvé — à modifier manuellement", flush=True)
    return False


async def save_edit(page) -> bool:
    """
    Clique sur le bouton Done bleu (cercle bas-droite) pour sauvegarder le profil.
    Ce bouton est souvent opacity:0 → on utilise force=True.
    """
    await page.wait_for_timeout(800)

    EXCLUDE_CLS = ["rotation-wheel", "discard", "cancel", "sidebar-close",
                   "btn-menu-toggle", "input-search", "back-button", "tgico-close"]

    # ── Stratégie 1 : Sélecteurs CSS avec force=True ─────────────
    SAVE_SELS = [
        # Bouton cercle bleu bas-droite (même classe que _confirm_crop)
        ".btn-new-menu.btn-circle.btn-corner",
        ".btn-circle.btn-corner.z-depth-1",
        ".btn-circle.btn-corner",
        ".btn-corner.z-depth-1",
        # Bouton check spécifique au formulaire d'édition
        "button.btn-icon.tgico-check",
        "button[class*='tgico-check']",
        ".tgico-check",
        ".btn-circle-border",
        "button.btn-primary",
    ]
    for sel in SAVE_SELS:
        try:
            btn = page.locator(sel).first
            # Normal d'abord
            try:
                if await btn.is_visible(timeout=800):
                    cls = (await btn.get_attribute("class") or "").lower()
                    if not any(w in cls for w in EXCLUDE_CLS):
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        print(f"  [OK] Sauvegardé ({sel})", flush=True)
                        return True
            except Exception:
                pass
            # Force (bypass opacity:0)
            cnt = await btn.count()
            if cnt > 0:
                cls = (await btn.get_attribute("class") or "").lower()
                if not any(w in cls for w in EXCLUDE_CLS):
                    await btn.click(force=True)
                    await page.wait_for_timeout(2000)
                    print(f"  [OK] Sauvegardé (force: {sel})", flush=True)
                    return True
        except Exception:
            continue

    # ── Stratégie 2 : JS — btn-circle/btn-corner dans bas-droite ──
    done = await page.evaluate("""
        () => {
            const BAD = ['rotation-wheel','discard','cancel','sidebar-close',
                         'btn-menu-toggle','tgico-close','input-search'];
            const W = window.innerWidth, H = window.innerHeight;
            const all = Array.from(document.querySelectorAll(
                'button, [class*="btn-circle"], [class*="btn-corner"], [class*="tgico-check"]'
            ));
            // 1. Chercher dans le quart bas-droit
            for (const el of all) {
                if (el.offsetParent === null) continue;
                const cls = (el.className || '').toLowerCase();
                if (BAD.some(w => cls.includes(w))) continue;
                const r = el.getBoundingClientRect();
                if (r.left > W * 0.4 && r.top > H * 0.5) {
                    if (cls.includes('circle') || cls.includes('corner') ||
                        cls.includes('check') || cls.includes('done')) {
                        el.click();
                        return 'quad-br: ' + el.className;
                    }
                }
            }
            // 2. Fallback : le plus bas-droite (côté droit seulement)
            let best = null, bestScore = -1;
            for (const el of all) {
                if (el.offsetParent === null) continue;
                const cls = (el.className || '').toLowerCase();
                if (BAD.some(w => cls.includes(w))) continue;
                const r = el.getBoundingClientRect();
                if (r.left < W * 0.3) continue;
                const score = r.right + r.bottom;
                if (score > bestScore) { bestScore = score; best = el; }
            }
            if (best) { best.click(); return 'br: ' + best.className; }
            return null;
        }
    """)
    if done:
        await page.wait_for_timeout(2000)
        print(f"  [OK] Sauvegardé JS ({done[:60]})", flush=True)
        return True

    # ── Stratégie 3 : Coordonnées bas-droite ─────────────────────
    try:
        vw = await page.evaluate("window.innerWidth")
        vh = await page.evaluate("window.innerHeight")
        for rx, ry in [(0.96, 0.93), (0.40, 0.93), (0.95, 0.90)]:
            x, y = int(vw * rx), int(vh * ry)
            await page.mouse.click(x, y)
            await page.wait_for_timeout(1800)
            # Vérifier que le formulaire d'édition s'est fermé
            edit_gone = True
            for s in ["form.edit-peer-profile", ".edit-profile-container",
                      "[class*='edit-profile']"]:
                try:
                    if await page.locator(s).first.is_visible(timeout=400):
                        edit_gone = False
                        break
                except Exception:
                    pass
            if edit_gone:
                print(f"  [OK] Sauvegardé (coord {x},{y})", flush=True)
                return True
    except Exception:
        pass

    # ── Stratégie 4 : Enter ───────────────────────────────────────
    try:
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1500)
        print("  [OK] Sauvegardé (Enter)", flush=True)
        return True
    except Exception:
        pass

    return False


# ── Étape 4 : Upload photo de profil ─────────────────────────

async def upload_profile_photo(page, photo_path: str) -> bool:
    """
    Upload la photo de profil depuis la page Settings.
    Le bouton caméra (profile-change-avatar) n'apparaît QUE lors du survol de l'avatar.
    Stratégies (ordre) :
      1. Hover Playwright sur l'avatar → bouton caméra apparaît → clic + file chooser
      2. Déplacement souris JS → même logique caméra
      3. Clic direct avatar → option menu "Upload Photo"
      4. Injection directe sur input[type=file]
    """
    if not photo_path or not os.path.isfile(photo_path):
        return True

    print("  [->] Upload photo de profil...", flush=True)
    await page.wait_for_timeout(800)

    UPLOAD_TEXTS = [
        "Upload Photo", "Set Photo", "Set a Photo", "Choose Photo",
        "Set Profile Photo", "Upload photo", "Change Photo", "Add Photo",
        "Charger une photo", "Changer la photo", "Définir une photo",
    ]
    # Sélecteurs JS (querySelector, pas is_visible — bypass opacity:0)
    CAMERA_JS_SELS = [
        # Boutons caméra spécifiques — NE PAS inclure [class*='profile-avatar']
        # car ça matche 'profile-avatars-container' (le conteneur, pas le bouton)
        "button.profile-change-avatar",
        "[class*='profile-change-avatar']",
        ".profile-change-avatar",
        "button[class*='tgico-cameraadd']",
        ".tgico-cameraadd",
        ".avatar-edit",
        "[class*='avatar-edit']",
        "[class*='profile-change']",
        ".btn-icon[class*='camera']",
        "label[for*='avatar']",
        "label[for*='photo']",
    ]
    AVATAR_SELS = [
        ".settings-main-profile .avatar",
        ".settings-main .avatar",
        ".profile-photo .avatar",
        ".settings-profile .avatar",
        ".avatar.avatar-full",
        "[class*='settings'] .avatar",
        ".userpic",
    ]

    # Helper : après clic caméra, gérer file chooser ou menu contextuel
    async def _after_camera() -> bool:
        await page.wait_for_timeout(900)
        # Par texte connu
        for txt in UPLOAD_TEXTS:
            try:
                opt = page.get_by_text(txt).first
                if await opt.is_visible(timeout=500):
                    print(f"  [->] Option menu : '{txt}'", flush=True)
                    async with page.expect_file_chooser(timeout=8000) as fc_info:
                        await opt.click()
                    fc = await fc_info.value
                    await fc.set_files(photo_path)
                    await page.wait_for_timeout(2500)
                    print(f"  [OK] Fichier envoyé via '{txt}'", flush=True)
                    await _confirm_crop(page)
                    return True
            except Exception:
                continue
        # JS : scan de tout popup/menu visible contenant "photo" ou "upload"
        menu_found = await page.evaluate("""
            () => {
                const POPUP_SELS = [
                    '.popup', '.dialog', '[class*="popup-box"]',
                    '.btn-menu.active', '[class*="btn-menu active"]',
                    '[class*="contextmenu"]', '[class*="context-menu"]',
                ];
                for (const pSel of POPUP_SELS) {
                    const popup = document.querySelector(pSel);
                    if (!popup || popup.getBoundingClientRect().width === 0) continue;
                    const items = popup.querySelectorAll('button, li, div[class*="item"], [onclick]');
                    for (const item of items) {
                        const t = (item.textContent || '').trim().toLowerCase();
                        if (t.length > 50) continue;
                        if (t.includes('photo') || t.includes('upload') ||
                            t.includes('image') || t.includes('change') ||
                            t.includes('set') || t.includes('choose') ||
                            t.includes('ajouter') || t.includes('changer') ||
                            t.includes('choisir') || t.includes('modifier')) {
                            item.click();
                            return t.slice(0, 30);
                        }
                    }
                }
                return null;
            }
        """)
        if menu_found:
            print(f"  [->] Option menu JS : '{menu_found}'", flush=True)
            await page.wait_for_timeout(1000)
            try:
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    pass
                fc = await fc_info.value
                await fc.set_files(photo_path)
                await page.wait_for_timeout(2500)
                print(f"  [OK] Fichier envoyé via menu JS", flush=True)
                await _confirm_crop(page)
                return True
            except Exception:
                pass
        # NE PAS presser Escape ici — cela fermerait Settings!
        # Seulement si un popup est vraiment ouvert
        try:
            has_popup = await page.evaluate("""
                () => ['.popup-container', '.media-viewer', '[class*="media-viewer"]']
                    .some(s => { const e = document.querySelector(s);
                                 return e && e.getBoundingClientRect().width > 0; })
            """)
            if has_popup:
                await page.keyboard.press("Escape")
        except Exception:
            pass
        return False

    # ── Stratégie -2 : input[type=file] en mode édition (le plus direct) ────
    # En mode édition Telegram Web K, il y a souvent un input file dédié au profil
    edit_input = await page.evaluate("""
        () => {
            // Cherche input file dans le contexte du formulaire d'édition
            const editCtx = document.querySelector(
                '.edit-profile-container, form.edit-peer-profile, [class*="edit-profile"]'
            );
            const inputs = (editCtx || document).querySelectorAll('input[type="file"]');
            for (const inp of inputs) {
                // L'input existe même s'il est caché
                return {found: true, id: inp.id, name: inp.name,
                        accept: inp.accept, cls: inp.className};
            }
            return {found: false};
        }
    """)
    if edit_input.get("found"):
        print(f"  [->] Input file mode édition détecté (accept={edit_input.get('accept','')})", flush=True)
        # Rendre l'input visible et injecter directement
        try:
            await page.evaluate("""
                () => {
                    const inp = (document.querySelector('.edit-profile-container,form.edit-peer-profile') || document)
                        .querySelector('input[type="file"]');
                    if (inp) {
                        inp.style.cssText = 'display:block!important;opacity:1!important;'
                            + 'visibility:visible!important;position:fixed;top:0;left:0;width:1px;height:1px;';
                        inp.removeAttribute('hidden');
                    }
                }
            """)
            edit_inp_loc = page.locator('.edit-profile-container input[type="file"], form.edit-peer-profile input[type="file"], input[type="file"]').first
            await edit_inp_loc.set_input_files(photo_path)
            await page.wait_for_timeout(3000)
            # Vérifier que l'éditeur crop a ouvert
            _crop_ok = False
            for _cs in [".media-editor", "[class*='media-editor']", ".crop-container", "[class*='avatar-edit']"]:
                try:
                    if await page.locator(_cs).first.is_visible(timeout=600):
                        _crop_ok = True
                        break
                except Exception:
                    pass
            if _crop_ok:
                print(f"  [OK] Photo injectée en mode édition", flush=True)
                await _confirm_crop(page)
                return True
            else:
                print(f"  [i] Input édition : pas d'éditeur crop ouvert", flush=True)
        except Exception as e:
            print(f"  [i] Input édition erreur : {e}", flush=True)

    # ── Stratégie -1 : profile-avatars-container + hover → file chooser ─────
    # Dans cette version de Telegram Web K, c'est le conteneur principal
    # qui gère l'upload photo quand on le clique avec les bons events.
    print("  [->] Stratégie profile-avatars-container...", flush=True)
    pac_info = await page.evaluate("""
        () => {
            const sels = [
                '.profile-avatars-container',
                '[class*="profile-avatars-container"]',
                '.settings-main-profile .avatar',
                '.settings-main .avatar',
            ];
            for (const sel of sels) {
                const el = document.querySelector(sel);
                if (el && el.offsetParent !== null) {
                    const r = el.getBoundingClientRect();
                    return {found: true, sel,
                            cx: r.left + r.width / 2,
                            cy: r.top  + r.height / 2,
                            cls: el.className.slice(0, 80)};
                }
            }
            return {found: false};
        }
    """)
    if pac_info.get("found"):
        pcx, pcy = pac_info["cx"], pac_info["cy"]
        print(f"  [->] Container trouvé : {pac_info.get('cls','')[:60]} @ ({pcx:.0f},{pcy:.0f})", flush=True)
        # Dispatch hover events pour activer la caméra
        await page.mouse.move(pcx, pcy)
        await page.evaluate("""
            () => {
                const sel = '.profile-avatars-container, [class*="profile-avatars-container"]';
                const el = document.querySelector(sel);
                if (el) {
                    el.dispatchEvent(new MouseEvent('mouseover', {bubbles: true, cancelable: true}));
                    el.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true, cancelable: true}));
                }
            }
        """)
        await page.wait_for_timeout(600)

        # Chercher un bouton caméra qui vient d'apparaître
        cam_appeared = await page.evaluate("""
            () => {
                for (const sel of ['.profile-change-avatar', '[class*="profile-change"]',
                                   '.tgico-cameraadd', '[class*="cameraadd"]',
                                   '.avatar-edit', '[class*="avatar-edit"]']) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const r = el.getBoundingClientRect();
                        return {found: true, cls: el.className.slice(0, 60),
                                cx: r.left + r.width/2, cy: r.top + r.height/2};
                    }
                }
                return {found: false};
            }
        """)
        if cam_appeared.get("found"):
            ccx, ccy = cam_appeared["cx"], cam_appeared["cy"]
            print(f"  [->] Bouton caméra apparu : {cam_appeared.get('cls','')[:50]}", flush=True)
            try:
                async with page.expect_file_chooser(timeout=4000) as fc_info:
                    await page.mouse.click(ccx, ccy)
                fc = await fc_info.value
                await fc.set_files(photo_path)
                await page.wait_for_timeout(2500)
                print(f"  [OK] Photo envoyée via bouton caméra", flush=True)
                await _confirm_crop(page)
                return True
            except Exception:
                if await _after_camera():
                    return True

        # Clic direct sur le container avec file chooser
        try:
            async with page.expect_file_chooser(timeout=4000) as fc_info:
                await page.mouse.click(pcx, pcy)
            fc = await fc_info.value
            await fc.set_files(photo_path)
            await page.wait_for_timeout(2500)
            print(f"  [OK] Photo envoyée via profile-avatars-container", flush=True)
            await _confirm_crop(page)
            return True
        except Exception:
            print(f"  [i] Container : pas de file chooser direct", flush=True)
            await page.wait_for_timeout(600)
            if await _after_camera():
                return True

    # ── Stratégie 0 : JS click direct (bouton est opacity:0 sans hover CSS) ──
    # expect_file_chooser doit wrapper l'évaluation JS pour capturer le chooser
    print("  [->] Tentative JS click caméra (bypass opacity:0)...", flush=True)
    for js_sel in CAMERA_JS_SELS:
        # Nettoyage des quotes pour JS inline
        js_sel_escaped = js_sel.replace("'", "\\'")
        try:
            async with page.expect_file_chooser(timeout=3000) as fc_info:
                clicked = await page.evaluate(f"""
                    () => {{
                        const btn = document.querySelector('{js_sel_escaped}');
                        if (btn) {{ btn.click(); return btn.className; }}
                        return null;
                    }}
                """)
            if clicked:
                fc = await fc_info.value
                await fc.set_files(photo_path)
                await page.wait_for_timeout(2500)
                print(f"  [OK] File chooser via JS caméra", flush=True)
                await _confirm_crop(page)
                return True
        except Exception:
            # Pas de file chooser → menu ?
            if clicked:
                print(f"  [->] Caméra JS cliquée ({clicked[:50]}) — recherche menu...", flush=True)
                if await _after_camera():
                    return True

    # ── Stratégie 1 : Hover + force=True click (bypass is_visible) ────
    for av_sel in AVATAR_SELS:
        try:
            av = page.locator(av_sel).first
            if not await av.is_visible(timeout=1200):
                continue
            print(f"  [->] Hover avatar ({av_sel}) + force click caméra...", flush=True)
            await av.hover()
            await page.wait_for_timeout(600)

            for js_sel in CAMERA_JS_SELS:
                try:
                    cam = page.locator(js_sel).first
                    # force=True : clic même si opacity:0 (CSS hover non déclenché)
                    try:
                        async with page.expect_file_chooser(timeout=3000) as fc_info:
                            await cam.click(force=True)
                        fc = await fc_info.value
                        await fc.set_files(photo_path)
                        await page.wait_for_timeout(2500)
                        print(f"  [OK] File chooser via force click ({js_sel})", flush=True)
                        await _confirm_crop(page)
                        return True
                    except Exception:
                        if await _after_camera():
                            return True
                except Exception:
                    continue
        except Exception:
            continue

    # ── Stratégie 2 : mouse.move → JS click caméra ────────────
    print("  [i] Essai mouse.move + JS click caméra...", flush=True)
    av_info = await page.evaluate("""
        () => {
            const sels = [
                '.settings-main-profile .avatar', '.settings-main .avatar',
                '.avatar.avatar-full', '[class*="settings"] .avatar',
                '.userpic', '.avatar',
            ];
            for (const sel of sels) {
                const el = document.querySelector(sel);
                if (el && el.offsetParent !== null) {
                    const r = el.getBoundingClientRect();
                    return {found: true, sel,
                            cx: r.left + r.width / 2,
                            cy: r.top  + r.height / 2};
                }
            }
            return {found: false};
        }
    """)
    if av_info.get("found"):
        cx, cy = av_info["cx"], av_info["cy"]
        print(f"  [->] mouse.move ({cx:.0f}, {cy:.0f})", flush=True)
        await page.mouse.move(cx, cy)
        await page.wait_for_timeout(600)

        # Debug : lister les éléments cliquables proches de l'avatar
        _near = await page.evaluate(f"""
            () => {{
                const cx = {cx}, cy = {cy};
                return Array.from(document.querySelectorAll(
                    'button, label, [onclick], [class*="camera"], [class*="avatar"], [class*="profile"]'
                )).filter(el => {{
                    if (el.offsetParent === null) return false;
                    const r = el.getBoundingClientRect();
                    return Math.abs(r.left+r.width/2-cx)<150 && Math.abs(r.top+r.height/2-cy)<150;
                }}).map(el => {{
                    const r = el.getBoundingClientRect();
                    return {{t:el.tagName, cls:el.className.slice(0,60),
                            x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)}};
                }}).slice(0,8);
            }}
        """)
        if _near:
            print(f"  [i] DOM près avatar : {_near}", flush=True)

        for js_sel in CAMERA_JS_SELS:
            js_sel_escaped = js_sel.replace("'", "\\'")
            try:
                async with page.expect_file_chooser(timeout=3000) as fc_info:
                    clicked = await page.evaluate(f"""
                        () => {{
                            const btn = document.querySelector('{js_sel_escaped}');
                            if (btn) {{ btn.click(); return btn.className; }}
                            return null;
                        }}
                    """)
                if clicked:
                    fc = await fc_info.value
                    await fc.set_files(photo_path)
                    await page.wait_for_timeout(2500)
                    print(f"  [OK] File chooser après mouse.move", flush=True)
                    await _confirm_crop(page)
                    return True
            except Exception:
                if clicked:
                    if await _after_camera():
                        return True

        # Fallback : clic coord avatar — le clic peut ouvrir un file chooser directement
        print(f"  [i] Clic coord avatar ({cx:.0f}, {cy:.0f})", flush=True)
        try:
            async with page.expect_file_chooser(timeout=4000) as fc_info:
                await page.mouse.click(cx, cy)
            fc = await fc_info.value
            await fc.set_files(photo_path)
            await page.wait_for_timeout(2500)
            print(f"  [OK] File chooser direct (clic avatar coord)", flush=True)
            await _confirm_crop(page)
            return True
        except Exception:
            # Pas de file chooser direct → peut-être un menu
            await page.wait_for_timeout(1200)
            if await _after_camera():
                return True

    # ── Stratégie 3 : Clic avatar CSS — avec capture file chooser direct ────
    print("  [i] Clic direct avatar CSS...", flush=True)
    for av_sel in AVATAR_SELS:
        try:
            av = page.locator(av_sel).first
            if not await av.is_visible(timeout=800):
                continue
            try:
                async with page.expect_file_chooser(timeout=4000) as fc_info:
                    await av.click()
                fc = await fc_info.value
                await fc.set_files(photo_path)
                await page.wait_for_timeout(2500)
                print(f"  [OK] File chooser direct CSS ({av_sel})", flush=True)
                await _confirm_crop(page)
                return True
            except Exception:
                await page.wait_for_timeout(600)
                if await _after_camera():
                    return True
        except Exception:
            continue
    # JS fallback sans file chooser
    js_clicked = await page.evaluate("""
        () => {
            const sels = ['.settings-main-profile .avatar', '.settings-main .avatar',
                          '.avatar.avatar-full', '.avatar', '.userpic'];
            for (const sel of sels) {
                const el = document.querySelector(sel);
                if (el && el.offsetParent !== null) { el.click(); return true; }
            }
            return false;
        }
    """)
    if js_clicked and await _after_camera():
        return True

    # ── Stratégie 4 : injection directe input[type=file] ─────
    print("  [i] Injection directe sur input[type=file]...", flush=True)
    try:
        nb = await page.evaluate("""
            () => {
                const inputs = document.querySelectorAll('input[type="file"]');
                inputs.forEach(inp => {
                    inp.style.cssText = 'display:block!important;opacity:1!important;'
                        + 'visibility:visible!important;position:fixed;top:0;left:0;width:1px;height:1px;';
                    inp.removeAttribute('hidden');
                });
                return inputs.length;
            }
        """)
        print(f"  [i] {nb} input(s) file déverrouillés", flush=True)
        file_inputs = page.locator("input[type='file']")
        cnt = await file_inputs.count()
        for i in range(cnt):
            try:
                await file_inputs.nth(i).set_input_files(photo_path)
                await page.wait_for_timeout(3000)
                # Vérifier que l'éditeur crop s'est ouvert — sinon c'était le mauvais input
                _crop_ok = False
                for _cs in [".media-editor", "[class*='media-editor']",
                             ".crop-container", "[class*='avatar-edit']", ".popup"]:
                    try:
                        if await page.locator(_cs).first.is_visible(timeout=600):
                            _crop_ok = True
                            break
                    except Exception:
                        pass
                if _crop_ok:
                    print(f"  [OK] Photo injectée via input #{i}", flush=True)
                    await _confirm_crop(page)
                    return True
                else:
                    print(f"  [i] Input #{i} : pas d'éditeur crop (mauvais input)", flush=True)
            except Exception as e:
                print(f"  [i] Input #{i} : {e}", flush=True)
    except Exception as e:
        print(f"  [i] Injection directe erreur : {e}", flush=True)

    # Screenshot debug
    try:
        tmp = os.path.join(tempfile.gettempdir(), "tg_photo_debug.png")
        await page.screenshot(path=tmp)
        print(f"  [i] Screenshot debug : {tmp}", flush=True)
    except Exception:
        pass

    print("  [!] Upload photo échoué", flush=True)
    return False


async def _confirm_crop(page):
    """
    Confirme l'éditeur photo / recadrage.
    Le bouton Done est un CERCLE BLEU en bas-à-droite — souvent opacity:0 → force=True.
    """
    await page.wait_for_timeout(2000)

    # Sortie rapide : si pas d'éditeur ouvert, il n'y a rien à confirmer
    # (évite les faux positifs quand l'injection a été faite dans le mauvais input)
    _early_ok = False
    for _ecs in [".media-editor", "[class*='media-editor']", ".crop-container",
                 "[class*='avatar-edit']"]:
        try:
            if await page.locator(_ecs).first.is_visible(timeout=500):
                _early_ok = True
                break
        except Exception:
            pass
    if not _early_ok:
        print("  [i] Pas d'éditeur crop visible — rien à confirmer", flush=True)
        return

    EXCLUDE_CLS = [
        "rotation-wheel", "discard", "cancel", "sidebar-close",
        "btn-menu-toggle", "input-search", "back-button", "tgico-close", "tgico-back",
    ]
    EXCLUDE_TXT = ["discard", "cancel", "annuler", "fermer", "close", "delete"]

    # Helper : vérifie si l'éditeur média est encore ouvert
    async def _editor_still_open() -> bool:
        for sel in [".media-editor", "[class*='media-editor']", ".crop-container"]:
            try:
                if await page.locator(sel).first.is_visible(timeout=400):
                    return True
            except Exception:
                pass
        return False

    # Helper : tente un clic (normal puis force) sur un sélecteur
    async def _try_click(sel: str) -> bool:
        try:
            btn = page.locator(sel).first
            # Tentative normale
            try:
                if await btn.is_visible(timeout=800):
                    cls = (await btn.get_attribute("class") or "").lower()
                    txt = (await btn.inner_text()).strip().lower()
                    if any(w in txt for w in EXCLUDE_TXT): return False
                    if any(w in cls for w in EXCLUDE_CLS): return False
                    await btn.click()
                    return True
            except Exception:
                pass
            # Tentative force (bypass opacity:0 / visibility:hidden)
            cnt = await btn.count()
            if cnt > 0:
                cls = (await btn.get_attribute("class") or "").lower()
                if any(w in cls for w in EXCLUDE_CLS): return False
                await btn.click(force=True)
                return True
        except Exception:
            pass
        return False

    # ── Stratégie 0 : Dialog "Discard" → cliquer CANCEL ──────────
    for discard_label in ["Discard Changes", "Discard changes", "Discard"]:
        try:
            if await page.get_by_text(discard_label).first.is_visible(timeout=700):
                for cancel_lbl in ["CANCEL", "Cancel", "Annuler", "No"]:
                    try:
                        c = page.get_by_text(cancel_lbl, exact=True).first
                        if await c.is_visible(timeout=600):
                            await c.click()
                            await page.wait_for_timeout(800)
                            print("  [OK] Dialog Discard annulé", flush=True)
                            break
                    except Exception:
                        continue
                break
        except Exception:
            continue

    await page.wait_for_timeout(400)

    # ── Stratégie 1 : Coordonnées — le bouton Done bleu est TOUJOURS bas-droite ──
    # C'est la stratégie la plus fiable (confirmée par les logs).
    try:
        vw = await page.evaluate("window.innerWidth")
        vh = await page.evaluate("window.innerHeight")
        for rx, ry in [(0.96, 0.93), (0.95, 0.90), (0.97, 0.95), (0.93, 0.88)]:
            x, y = int(vw * rx), int(vh * ry)
            await page.mouse.click(x, y)
            await page.wait_for_timeout(2500)
            if not await _editor_still_open():
                print(f"  [OK] Crop confirmé (coord {x},{y})", flush=True)
                return
    except Exception as e:
        print(f"  [i] Erreur coordonnées : {e}", flush=True)

    # ── Stratégie 2 : Sélecteurs CSS du bouton Done bleu (fallback) ──
    # → force=True pour bypasser opacity:0
    DONE_SELS = [
        ".media-editor__done",
        "[class*='media-editor__done']",
        ".btn-new-menu.btn-circle.btn-corner",
        ".btn-circle.btn-corner.z-depth-1",
        ".btn-circle.btn-corner",
        ".btn-corner.z-depth-1",
        "button[class*='tgico-check']:not([class*='rotation'])",
        ".media-editor .btn-circle",
        ".btn-circle-border",
        ".btn-circle",
    ]
    for sel in DONE_SELS:
        clicked = await _try_click(sel)
        if clicked:
            await page.wait_for_timeout(3000)
            if not await _editor_still_open():
                print(f"  [OK] Crop confirmé CSS ({sel})", flush=True)
                return
            print(f"  [i] {sel} cliqué — éditeur encore ouvert", flush=True)

    # ── Stratégie 3 : JS — chercher btn-circle/btn-corner excluant rotation-wheel ──
    done = await page.evaluate("""
        () => {
            const BAD_CLS = ['rotation-wheel','discard','cancel','sidebar-close',
                              'btn-menu-toggle','tgico-close','tgico-back','input-search'];
            const BAD_TXT = ['discard','cancel','annuler','close','delete'];
            const W = window.innerWidth, H = window.innerHeight;

            // Chercher TOUS les éléments (pas seulement <button>)
            const all = Array.from(document.querySelectorAll(
                'button, .btn-circle, .btn-corner, [class*="btn-circle"], [class*="btn-corner"]'
            ));

            for (const el of all) {
                if (el.offsetParent === null) continue;
                const cls = (el.className || '').toLowerCase();
                const txt = (el.innerText || el.textContent || '').toLowerCase().trim();
                if (BAD_CLS.some(w => cls.includes(w))) continue;
                if (BAD_TXT.some(w => txt.includes(w))) continue;
                const r = el.getBoundingClientRect();
                // Le Done button est dans le quart bas-droit
                if (r.left > W * 0.5 && r.top > H * 0.5) {
                    if (cls.includes('circle') || cls.includes('corner') || cls.includes('check')) {
                        el.click();
                        return 'quad-br: ' + el.className;
                    }
                }
            }

            // Fallback : élément le plus bas-droite excluant tout ce qui est dangereux
            let best = null, bestScore = -1;
            for (const el of all) {
                if (el.offsetParent === null) continue;
                const cls = (el.className || '').toLowerCase();
                const txt = (el.innerText || el.textContent || '').toLowerCase().trim();
                if (BAD_CLS.some(w => cls.includes(w))) continue;
                if (BAD_TXT.some(w => txt.includes(w))) continue;
                const r = el.getBoundingClientRect();
                if (r.left < W * 0.3) continue; // ignorer côté gauche
                const score = r.right + r.bottom;
                if (score > bestScore) { bestScore = score; best = el; }
            }
            if (best) { best.click(); return 'br-fallback: ' + best.className; }
            return null;
        }
    """)
    if done:
        await page.wait_for_timeout(3000)
        if not await _editor_still_open():
            print(f"  [OK] Crop confirmé JS ({done})", flush=True)
            return

    # ── Stratégie 4 : Enter ───────────────────────────────────────
    try:
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2500)
        if not await _editor_still_open():
            print("  [OK] Crop confirmé (Enter)", flush=True)
            return
    except Exception:
        pass

    # ── Debug : screenshot + log tous les boutons ─────────────────
    try:
        info = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button,[class*="btn-circle"],[class*="btn-corner"]'))
                .filter(b => b.offsetParent !== null)
                .map(b => { const r=b.getBoundingClientRect();
                    return {cls:b.className.slice(0,60), top:Math.round(r.top),
                            left:Math.round(r.left), right:Math.round(r.right), bottom:Math.round(r.bottom)}; })
        """)
        print(f"  [i] Éléments visibles éditeur : {info}", flush=True)
        import tempfile as _t, os as _o
        dbg = _o.path.join(_t.gettempdir(), "tg_crop_debug.png")
        await page.screenshot(path=dbg)
        print(f"  [i] Screenshot : {dbg}", flush=True)
    except Exception:
        pass
    print("  [!] Crop non confirmé", flush=True)


# ── Orchestration principale ─────────────────────────────────

async def apply_changes(page, config: dict):
    first_name = (config.get("first_name") or "").strip()
    username   = (config.get("username")   or "").strip().lstrip("@")
    bio        = (config.get("bio")        or "").strip()
    photo_b64  = (config.get("photo_b64")  or "").strip()
    photo_nm   = (config.get("photo_name") or "photo.jpg").strip()

    print(f"\n{'='*56}", flush=True)
    print(f"  PROFIL → {config['profile_id']}", flush=True)
    if first_name: print(f"  Prénom    : {first_name}", flush=True)
    if username:   print(f"  @Username : @{username}", flush=True)
    if bio:        print(f"  Bio       : {bio[:50]}{'…' if len(bio)>50 else ''}", flush=True)
    if photo_b64:  print(f"  Photo     : {photo_nm}", flush=True)
    print(f"{'='*56}\n", flush=True)

    has_changes = any([first_name, username, bio, photo_b64])
    if not has_changes:
        print("  [i] Aucun changement à appliquer.", flush=True)
        return

    # ── Écrire la photo dans un fichier temporaire ─────────────
    photo_tmp = None
    if photo_b64:
        ext       = "jpg" if photo_nm.lower().endswith((".jpg", ".jpeg")) else "png"
        photo_tmp = os.path.join(tempfile.gettempdir(),
                                 f"tg_photo_{config['profile_id']}.{ext}")
        try:
            with open(photo_tmp, "wb") as fh:
                fh.write(base64.b64decode(photo_b64))
            print(f"  [OK] Photo temp : {photo_tmp}", flush=True)
        except Exception as e:
            print(f"  [!] Erreur écriture photo : {e}", flush=True)
            photo_tmp = None

    # ── Navigation vers Telegram Web K (sans reload si déjà là) ──
    current_url = page.url
    if "web.telegram.org" not in current_url:
        try:
            await page.goto("https://web.telegram.org/k/",
                            wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
        except Exception:
            pass
    else:
        # Déjà sur Telegram — juste fermer les panneaux ouverts
        for _ in range(2):
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(400)
            except Exception:
                pass
        await page.wait_for_timeout(800)

    if not await wait_telegram(page):
        raise Exception("__NOT_CONNECTED__")
    print("  [OK] Telegram connecté", flush=True)
    await page.wait_for_timeout(1000)

    # ── Ouvrir Settings ────────────────────────────────────────
    await open_settings(page)
    await page.wait_for_timeout(1500)

    # ── Entrer en mode édition D'ABORD ─────────────────────────
    edit_ok = await open_edit_mode(page)
    await page.wait_for_timeout(1000)

    # ── Upload photo EN MODE ÉDITION ───────────────────────────
    if photo_tmp:
        photo_ok = await upload_profile_photo(page, photo_tmp)
        try:
            os.remove(photo_tmp)
        except Exception:
            pass
        if not photo_ok:
            raise Exception("__UPLOAD_FAILED__")
        await page.wait_for_timeout(2000)

    # ── Édition prénom / nom / bio / username ──────────────────
    if first_name or bio or username:
        # Vérifier si le mode édition est encore actif (l'upload peut avoir fermé le formulaire)
        in_edit = False
        for sel in [".edit-profile-container", "form.edit-peer-profile",
                    "div.input-field-input[contenteditable='true']"]:
            try:
                if await page.locator(sel).first.is_visible(timeout=600):
                    in_edit = True
                    break
            except Exception:
                pass

        if not in_edit:
            # Mode édition fermé — vérifier que Settings est ouvert, sinon le rouvrir
            s_open = False
            for sel in [".settings-container", ".settings-main", "[class*='settings-main']"]:
                try:
                    if await page.locator(sel).first.is_visible(timeout=600):
                        s_open = True
                        break
                except Exception:
                    pass
            if not s_open:
                await open_settings(page)
                await page.wait_for_timeout(1500)
            edit_ok = await open_edit_mode(page)
            await page.wait_for_timeout(1000)
        else:
            edit_ok = True

        if edit_ok:
            if first_name or bio:
                await fill_name_bio(page, first_name, bio)
            if username:
                await fill_username(page, username)
            await save_edit(page)
        else:
            print("  [!] Mode édition non activé — nom/bio non modifiés", flush=True)

    await page.wait_for_timeout(2000)
    print(f"\n  ✅ Profil {config['profile_id']} mis à jour !", flush=True)
    print(f"{'='*56}\n", flush=True)


# ── Auto-close helper ────────────────────────────────────────

def _auto_close(seconds: int = 30):
    """Fermeture automatique après N secondes (Ctrl+C pour quitter immédiatement)."""
    import time
    try:
        for i in range(seconds, 0, -1):
            print(f"\r  ⏳ Fermeture automatique dans {i}s... (Ctrl+C pour quitter)", end="", flush=True)
            time.sleep(1)
        print(f"\r  ✓ Fermeture.                                              ", flush=True)
    except KeyboardInterrupt:
        pass


# ── Main ─────────────────────────────────────────────────────

async def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("[X] Usage : python profile_changer.py <profile_id> [--silent]")
        sys.exit(1)

    IS_SILENT  = "--silent" in sys.argv
    profile_id = sys.argv[1].strip()

    print(f"\n{'='*56}")
    print(f"  Profile Changer — {profile_id}")
    print(f"{'='*56}")

    # Charge la config depuis Supabase
    config = load_config(profile_id)
    if not config:
        print(f"[X] Aucune config trouvée pour {profile_id}")
        print("    → Configure le profil dans le dashboard onglet ⚙ Setup")
        if not IS_SILENT:
            _auto_close(30)
        sys.exit(1)

    print(f"[OK] Config chargée pour {profile_id}")

    # Démarre AdsPower
    print(f"[->] Démarrage du navigateur AdsPower ({profile_id})...")
    try:
        cdp_url = start_browser(profile_id)
    except Exception as e:
        err_msg = f"AdsPower introuvable : {e}"
        print(f"[X] Impossible de démarrer AdsPower : {e}")
        _report_result(profile_id, ok=False, error=err_msg, error_type="adspower")
        if not IS_SILENT:
            _auto_close(30)
        sys.exit(1)

    print(f"[OK] Navigateur démarré")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            page    = context.pages[0] if context.pages else await context.new_page()
            await page.bring_to_front()

            await apply_changes(page, config)

            # Fermeture propre
            try:
                await browser.disconnect()
            except AttributeError:
                try:
                    await browser.close()
                except Exception:
                    pass
            except Exception:
                pass

    except Exception as e:
        err_str = str(e)
        if "__NOT_CONNECTED__" in err_str:
            msg = "Telegram non connecté"
            etype = "not_connected"
            print(f"\n[X] {msg}", flush=True)
        elif "__UPLOAD_FAILED__" in err_str:
            msg = "Upload photo échoué"
            etype = "upload_failed"
            print(f"\n[X] {msg}", flush=True)
        else:
            msg = err_str[:200]
            etype = "error"
            print(f"\n[X] Erreur : {msg}", flush=True)
        _report_result(profile_id, ok=False, error=msg, error_type=etype)

    else:
        # Succès complet
        _report_result(profile_id, ok=True, error_type="")

    finally:
        stop_browser(profile_id)
        print(f"[OK] AdsPower fermé ({profile_id})")

    if not IS_SILENT:
        print(f"\n  ✅ Profil {profile_id} terminé !")
        _auto_close(30)


if __name__ == "__main__":
    asyncio.run(main())
