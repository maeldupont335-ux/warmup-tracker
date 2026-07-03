from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class DayPlan:
    days: Tuple[int, int]
    session_duration: Tuple[int, int]          # minutes
    spotlight_videos: Optional[Tuple[int, int]]
    stories_friends: Optional[Tuple[int, int]]
    accept_friends_per_day: Optional[Tuple[int, int]]
    quick_add_per_session: Optional[Tuple[int, int]]
    open_convos: Optional[Tuple[int, int]]
    send_snaps: Optional[Tuple[int, int]]
    post_story: bool


WARMUP_PLANS = [
    DayPlan(
        days=(1, 2), session_duration=(5, 15),
        spotlight_videos=(3, 8), stories_friends=None,
        accept_friends_per_day=None, quick_add_per_session=None,
        open_convos=(1, 3), send_snaps=None, post_story=False,
    ),
    DayPlan(
        days=(3, 4), session_duration=(8, 20),
        spotlight_videos=(5, 10), stories_friends=None,
        accept_friends_per_day=(0, 10), quick_add_per_session=None,
        open_convos=(2, 4), send_snaps=None, post_story=False,
    ),
    DayPlan(
        days=(5, 6), session_duration=(10, 20),
        spotlight_videos=(5, 12), stories_friends=(2, 5),
        accept_friends_per_day=(0, 25), quick_add_per_session=(3, 5),
        open_convos=(2, 5), send_snaps=None, post_story=False,
    ),
    DayPlan(
        days=(7, 8), session_duration=(10, 25),
        spotlight_videos=(8, 15), stories_friends=(3, 8),
        accept_friends_per_day=(0, 35), quick_add_per_session=(5, 8),
        open_convos=(3, 6), send_snaps=(1, 2), post_story=True,
    ),
    DayPlan(
        days=(9, 10), session_duration=(12, 25),
        spotlight_videos=(8, 15), stories_friends=(5, 10),
        accept_friends_per_day=(0, 45), quick_add_per_session=(8, 12),
        open_convos=(3, 6), send_snaps=(1, 3), post_story=True,
    ),
    DayPlan(
        days=(11, 12), session_duration=(15, 25),
        spotlight_videos=(10, 15), stories_friends=(5, 12),
        accept_friends_per_day=(0, 55), quick_add_per_session=(12, 16),
        open_convos=(4, 7), send_snaps=(2, 4), post_story=True,
    ),
    DayPlan(
        days=(13, 15), session_duration=(15, 25),
        spotlight_videos=(10, 20), stories_friends=(8, 15),
        accept_friends_per_day=(0, 60), quick_add_per_session=(16, 20),
        open_convos=(4, 8), send_snaps=(2, 4), post_story=True,
    ),
]


def get_plan_for_day(day: int) -> DayPlan:
    for plan in WARMUP_PLANS:
        if plan.days[0] <= day <= plan.days[1]:
            return plan
    return WARMUP_PLANS[-1]
