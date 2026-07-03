import random
import time
from datetime import datetime, timedelta
from typing import Callable, Dict

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from loguru import logger

from config import SESSION_WINDOWS


def _random_time_in_window(start_hour: int, end_hour: int) -> datetime:
    """Random time within window, never on the exact hour mark."""
    now = datetime.now()
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)

    total_seconds = int((end - start).total_seconds())
    offset = random.randint(90, total_seconds - 90)
    target = start + timedelta(seconds=offset)

    # Avoid landing exactly on the hour
    if target.minute == 0:
        target += timedelta(minutes=random.randint(4, 19))

    return target


class WarmupScheduler:
    def __init__(self, session_callback: Callable[[str], None]):
        self._scheduler = BackgroundScheduler()
        self._callback = session_callback
        self._next: Dict[str, datetime] = {}

    def schedule_today(self):
        """Schedule morning and evening sessions for today."""
        for name, (start_h, end_h) in SESSION_WINDOWS.items():
            run_at = _random_time_in_window(start_h, end_h)
            if run_at <= datetime.now():
                logger.debug(f"Fenêtre {name} déjà passée pour aujourd'hui")
                continue

            job_id = f"{name}_{run_at.date()}"
            self._scheduler.add_job(
                self._callback,
                trigger=DateTrigger(run_date=run_at),
                args=[name],
                id=job_id,
                replace_existing=True,
            )
            self._next[name] = run_at
            logger.info(f"Session {name} planifiée à {run_at.strftime('%H:%M')}")

    def start(self):
        self._scheduler.start()
        self.schedule_today()

    def stop(self):
        self._scheduler.shutdown(wait=False)

    def get_next_sessions(self) -> Dict[str, datetime]:
        return dict(self._next)

    def run_blocking(self):
        """Block forever, rescheduling daily sessions at midnight."""
        self.start()
        try:
            while True:
                now = datetime.now()
                # Reschedule for next day just after midnight
                if now.hour == 0 and now.minute < 2:
                    self.schedule_today()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Scheduler arrêté")
            self.stop()
