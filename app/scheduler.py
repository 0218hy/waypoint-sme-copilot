"""The weekly Goal Keeper job on a timer (SPEC §7.2), with APScheduler.

The job ticks often (hourly by default) and the Goal Keeper decides what is due: each goal is checked
at most once per week of its life and emailed at most once per period of its chosen frequency, so a
tick that finds nothing new does nothing, and a missed week is caught up on the next tick.

On by default outside tests and demo mode (`WAYPOINT_SCHEDULER=1|0` overrides). The demo has its own
clock (`POST /api/demo/advance`), which runs the same job.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from app.services import AppServices

log = logging.getLogger(__name__)
JOB_ID = "goal_keeper_weekly"


def enabled(demo: bool) -> bool:
    flag = os.environ.get("WAYPOINT_SCHEDULER")
    if flag is not None:
        return flag == "1"
    testing = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
    return not demo and not testing


def interval_minutes() -> int:
    try:
        return max(1, int(os.environ.get("WAYPOINT_SCHEDULER_MINUTES", "60")))
    except ValueError:
        return 60


class WeeklyScheduler:
    def __init__(self, services: AppServices, minutes: int | None = None) -> None:
        self.services = services
        self.minutes = minutes or interval_minutes()
        self._sched: BackgroundScheduler | None = None
        self.last_run: dict[str, int] | None = None

    def job(self) -> dict[str, int]:
        result = self.services.run_scheduled()
        self.last_run = result
        log.info("goal keeper job: %s", result)
        return result

    def start(self) -> None:
        if self._sched is not None:
            return
        sched = BackgroundScheduler(timezone=UTC)
        sched.add_job(
            self.job,
            IntervalTrigger(minutes=self.minutes, timezone=UTC),
            id=JOB_ID,
            next_run_time=datetime.now(UTC),  # catch up at once after a restart
            max_instances=1,
            coalesce=True,
            misfire_grace_time=None,
            replace_existing=True,
        )
        sched.start()
        self._sched = sched
        log.info("goal keeper scheduler started (every %d minutes)", self.minutes)

    def run_now(self) -> None:
        """Bring the next tick forward to now (the scheduler runs it on its own thread)."""
        if self._sched is None:
            raise RuntimeError("scheduler not started")
        job = self._sched.get_job(JOB_ID)
        assert job is not None
        job.modify(next_run_time=datetime.now(UTC))
        self._sched.wakeup()

    @property
    def running(self) -> bool:
        return self._sched is not None and bool(self._sched.running)

    def shutdown(self) -> None:
        if self._sched is not None:
            self._sched.shutdown(wait=False)
            self._sched = None
