import random
import time
from typing import Optional, Tuple

from loguru import logger


def delay(min_s: float = 1.5, max_s: float = 8.0):
    """Gaussian-weighted random delay clamped to [min_s, max_s]."""
    mu = (min_s + max_s) / 2
    sigma = (max_s - min_s) / 4
    duration = random.gauss(mu, sigma)
    duration = max(min_s, min(max_s, duration))
    time.sleep(duration)


def short_delay():
    delay(1.5, 8.0)


def action_delay():
    delay(5.0, 25.0)


def tap_delay():
    delay(0.3, 1.2)


def long_pause():
    """Simulate holding the phone without doing anything (20-60 s)."""
    duration = random.uniform(20, 60)
    logger.debug(f"Pause humaine {duration:.1f}s")
    time.sleep(duration)


def random_swipe_duration() -> int:
    """Return swipe duration in ms with realistic speed distribution."""
    buckets = [
        (200, 400),    # fast
        (400, 800),    # medium
        (800, 1500),   # slow
        (1500, 2500),  # very slow
    ]
    weights = [0.30, 0.40, 0.20, 0.10]
    lo, hi = random.choices(buckets, weights=weights)[0]
    return random.randint(lo, hi)


def random_watch_time(min_s: float = 8, max_s: float = 45) -> float:
    return random.uniform(min_s, max_s)


def random_story_time() -> float:
    return random.uniform(5, 30)


def should_pause(probability: float = 0.15) -> bool:
    return random.random() < probability


def shuffle_actions(actions: list) -> list:
    """Shuffle action order; occasionally skip one to simulate inattention."""
    shuffled = actions.copy()
    random.shuffle(shuffled)
    if len(shuffled) > 2 and random.random() < 0.20:
        skip_idx = random.randint(0, len(shuffled) - 1)
        logger.debug(f"Action sautée (inattention simulée): {shuffled[skip_idx][0]}")
        shuffled.pop(skip_idx)
    return shuffled


def random_count(range_tuple: Optional[Tuple[int, int]]) -> int:
    if not range_tuple:
        return 0
    return random.randint(range_tuple[0], range_tuple[1])
