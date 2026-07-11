import random
import time
from typing import Callable, Optional

from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from loguru import logger

from config import BUNDLE_ID
from actions.human import (
    delay, tap_delay, short_delay, long_pause,
    random_swipe_duration, random_watch_time, random_story_time, should_pause,
)


class SnapchatDriver:
    def __init__(self, driver: webdriver.Remote):
        self.driver = driver
        self._w: Optional[int] = None
        self._h: Optional[int] = None

    # ------------------------------------------------------------------ #
    # Propriétés écran
    # ------------------------------------------------------------------ #

    @property
    def W(self) -> int:
        if not self._w:
            sz = self.driver.get_window_size()
            self._w, self._h = sz["width"], sz["height"]
        return self._w

    @property
    def H(self) -> int:
        if not self._h:
            sz = self.driver.get_window_size()
            self._w, self._h = sz["width"], sz["height"]
        return self._h

    # ------------------------------------------------------------------ #
    # Helpers bas niveau
    # ------------------------------------------------------------------ #

    def _tap(self, x: float, y: float):
        self.driver.execute_script("mobile: tap", {"x": int(x), "y": int(y)})

    def _swipe(self, sx: float, sy: float, ex: float, ey: float, ms: int = None):
        self.driver.swipe(int(sx), int(sy), int(ex), int(ey), ms or random_swipe_duration())

    def _swipe_up(self):
        cx = self.W * 0.5
        self._swipe(cx, self.H * 0.70, cx, self.H * 0.30)

    def _swipe_down(self):
        cx = self.W * 0.5
        self._swipe(cx, self.H * 0.30, cx, self.H * 0.70)

    def _find(self, *locators):
        """Essaie chaque (By, value) dans l'ordre, retourne le premier trouvé."""
        for by, value in locators:
            try:
                return self.driver.find_element(by, value)
            except (NoSuchElementException, WebDriverException):
                continue
        return None

    def _find_name(self, *names: str):
        for name in names:
            el = self._find((AppiumBy.ACCESSIBILITY_ID, name))
            if el:
                return el
        return None

    def _back(self):
        el = self._find_name("back", "Back", "Retour")
        if el:
            el.click()
        else:
            self._tap(self.W * 0.05, self.H * 0.07)

    def _username_near_button(self, btn) -> Optional[str]:
        try:
            cell = btn.find_element(AppiumBy.XPATH, "./ancestor::XCUIElementTypeCell[1]")
            texts = cell.find_elements(AppiumBy.CLASS_NAME, "XCUIElementTypeStaticText")
            for t in texts:
                val = (t.get_attribute("value") or t.get_attribute("name") or "").strip()
                if val and len(val) > 1:
                    return val.lower()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ #
    # Session & device
    # ------------------------------------------------------------------ #

    def check_battery(self) -> int:
        try:
            info = self.driver.execute_script("mobile: batteryInfo")
            return int(info.get("level", 1.0) * 100)
        except Exception:
            return 100

    def open_snapchat(self):
        try:
            self.driver.activate_app(BUNDLE_ID)
        except Exception:
            pass
        delay(5, 10)
        logger.info("Snapchat ouvert")

    # ------------------------------------------------------------------ #
    # Navigation onglets
    # ------------------------------------------------------------------ #

    def _go_tab(self, names: list, fallback_x: float):
        el = self._find_name(*names)
        if el:
            el.click()
        else:
            self._tap(self.W * fallback_x, self.H * 0.935)
        delay(1, 3)

    def go_to_camera(self):
        self._go_tab(["Camera", "Appareil photo"], 0.50)

    def go_to_chat(self):
        self._go_tab(["Chat", "Messages"], 0.28)

    def go_to_spotlight(self):
        self._go_tab(["Spotlight & Snap Map", "Discover", "Spotlight"], 0.72)

    def go_to_add_friends(self):
        self._go_tab(["Profile", "Profil"], 0.10)
        delay(0.8, 2)
        el = self._find_name("Add Friends", "Ajouter des amis")
        if el:
            el.click()
        delay(1, 3)

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #

    def browse_spotlight(self, n: int):
        logger.info(f"Spotlight: {n} vidéos")
        self.go_to_spotlight()
        delay(2, 5)

        for i in range(n):
            watch = random_watch_time(8, 45)
            logger.debug(f"  Vidéo {i+1}/{n} — {watch:.1f}s")

            if i > 0 and random.random() < 0.10:
                self._swipe_down()
                delay(3, 8)

            time.sleep(watch)

            if should_pause(0.10):
                long_pause()

            if i < n - 1:
                self._swipe_up()
                delay(0.5, 2)

        logger.info("Spotlight terminé")

    def browse_friend_stories(self, n: int):
        logger.info(f"Stories amis: {n}")
        self.go_to_chat()
        delay(1, 3)

        for i in range(n):
            self._tap(self.W * (0.10 + (i % 5) * 0.15), self.H * 0.12)
            delay(0.8, 2)
            time.sleep(random_story_time())

            if random.random() < 0.70:
                self._tap(self.W * 0.75, self.H * 0.50)
                tap_delay()
            else:
                self._swipe(self.W * 0.80, self.H * 0.50, self.W * 0.20, self.H * 0.50)
                delay(0.5, 1.5)

            short_delay()

        self._back()
        logger.info("Stories terminées")

    def accept_friend_requests(self, max_count: int, name_filter: Callable[[str], bool]) -> int:
        if max_count == 0:
            return 0
        logger.info(f"Acceptation amis: max {max_count}")
        self.go_to_add_friends()

        el = self._find_name("Added Me", "Mes amis ajoutés")
        if el:
            el.click()
            delay(1, 3)

        accepted = 0
        for _ in range(max_count * 4):
            if accepted >= max_count:
                break

            buttons = self.driver.find_elements(
                AppiumBy.XPATH,
                "//XCUIElementTypeButton[@name='Accept' or @name='Accept friend request']"
            )
            if not buttons:
                break

            progressed = False
            for btn in buttons:
                if accepted >= max_count:
                    break
                username = self._username_near_button(btn)
                if username is not None and not name_filter(username):
                    logger.debug(f"Rejeté: {username}")
                    continue
                try:
                    btn.click()
                    accepted += 1
                    progressed = True
                    logger.info(f"Accepté: {username or '?'} ({accepted}/{max_count})")
                    delay(3, 15)
                except Exception as e:
                    logger.warning(f"Échec: {e}")

            if not progressed:
                self._swipe_up()
                delay(1, 2)

        logger.info(f"Total acceptés: {accepted}")
        return accepted

    def quick_add_friends(self, n: int, name_filter: Callable[[str], bool]) -> int:
        if n == 0:
            return 0
        logger.info(f"Ajout rapide: {n}")
        self.go_to_add_friends()

        el = self._find_name("Quick Add", "Ajout rapide")
        if el:
            el.click()
            delay(1, 2)

        added = 0
        for _ in range(15):
            if added >= n:
                break

            buttons = self.driver.find_elements(
                AppiumBy.XPATH,
                "//XCUIElementTypeButton[@name='Add' or @name='Add friend']"
            )
            if not buttons:
                break

            progressed = False
            for btn in buttons:
                if added >= n:
                    break
                username = self._username_near_button(btn)
                if username is not None and not name_filter(username):
                    logger.debug(f"Sauté: {username}")
                    continue
                try:
                    btn.click()
                    added += 1
                    progressed = True
                    logger.info(f"Ajouté: {username or '?'} ({added}/{n})")
                    delay(5, 20)
                except Exception as e:
                    logger.warning(f"Échec: {e}")

            if not progressed or added < n:
                self._swipe_up()
                delay(1, 3)

        logger.info(f"Total ajoutés: {added}")
        return added

    def browse_conversations(self, n: int):
        logger.info(f"Conversations: {n}")
        self.go_to_chat()
        delay(1, 3)

        for _ in range(n):
            self._tap(self.W * 0.50, self.H * (0.30 + random.random() * 0.35))
            delay(1, 2)
            time.sleep(random.uniform(5, 20))

            if random.random() < 0.25:
                self._tap(self.W * 0.50, self.H * 0.93)
                delay(1, 3)

            self._back()
            delay(2, 6)

            if should_pause(0.08):
                long_pause()

        logger.info("Conversations terminées")

    def send_snap(self, n_recipients: int):
        logger.info(f"Envoi snap à {n_recipients} amis")
        self.go_to_camera()
        delay(1, 3)

        shutter = self._find_name("Shutter", "Déclencheur")
        if shutter:
            shutter.click()
        else:
            self._tap(self.W * 0.50, self.H * 0.83)
        delay(1, 3)

        send_to = self._find_name("Send To", "Envoyer à")
        if not send_to:
            logger.warning("Bouton Send To introuvable")
            return
        send_to.click()
        delay(1, 2)

        for i in range(n_recipients):
            self._tap(self.W * 0.50, self.H * (0.25 + i * 0.08))
            delay(0.5, 1.5)

        delay(3, 8)

        send_btn = self._find_name("Send", "Envoyer")
        if send_btn:
            send_btn.click()
        delay(2, 5)
        logger.info("Snap envoyé")

    def post_story(self):
        logger.info("Post story")
        self.go_to_camera()
        delay(1, 3)

        shutter = self._find_name("Shutter", "Déclencheur")
        if shutter:
            shutter.click()
        else:
            self._tap(self.W * 0.50, self.H * 0.83)
        delay(1, 3)

        send_to = self._find_name("Send To", "Envoyer à")
        if not send_to:
            logger.warning("Bouton Send To introuvable")
            return
        send_to.click()
        delay(1, 2)

        my_story = self._find_name("My Story", "Ma story")
        if my_story:
            my_story.click()
            delay(1, 2)

        send_btn = self._find_name("Send", "Envoyer")
        if send_btn:
            send_btn.click()
        delay(2, 5)
        logger.info("Story postée")

    def micro_activity(self):
        if random.random() < 0.5:
            self._swipe_up() if random.random() < 0.5 else self._swipe_down()
        else:
            delay(2, 6)
