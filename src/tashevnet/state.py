from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from .models import SEVERITY, Health


@dataclass(slots=True, frozen=True)
class Observation:
    health: Health
    reason: str
    timestamp: str

    @property
    def level(self) -> int:
        return SEVERITY[self.health]


@dataclass(slots=True, frozen=True)
class Transition:
    previous: Observation | None
    current: Observation
    # Set when the connection returns to normal: how long the incident lasted.
    duration_seconds: float | None = None


class StateTracker:
    """Turns noisy per-check results into confirmed state changes.

    A problem becomes an incident once it shows up in `alert_after` of the last
    `window` checks, so a single lost packet is not an incident, while a line that
    flaps between good and bad still is. Leaving an incident needs `window` clean
    checks in a row. Each confirmed change is reported once.
    """

    def __init__(self, alert_after: int = 2, recover_after: int = 3) -> None:
        self.alert_after = max(1, alert_after)
        self.window_size = max(self.alert_after, recover_after, 1)
        self._window: deque[Observation] = deque(maxlen=self.window_size)
        self.confirmed: Observation | None = None
        self.incident_started_at: str | None = None

    def observe(self, obs: Observation) -> Transition | None:
        self._window.append(obs)
        window = list(self._window)
        levels = sorted((item.level for item in window), reverse=True)
        current = self.confirmed.level if self.confirmed else 0

        if len(window) >= self.alert_after:
            target = levels[self.alert_after - 1]
            if target > current:
                return self._escalate(window, target)

        if self.confirmed is None:
            # Start-up: accept a healthy baseline quietly once enough checks agree.
            recent = window[-self.alert_after :]
            if len(recent) == self.alert_after and all(item.level == 0 for item in recent):
                self.confirmed = Observation(obs.health, obs.reason, recent[0].timestamp)
            return None

        if len(window) == self.window_size and levels[0] < current:
            return self._settle(window, levels[self.alert_after - 1])

        recent = window[-self.alert_after :]
        if (
            obs.level == current
            and obs.reason != self.confirmed.reason
            and len(recent) == self.alert_after
            and all(item.level == obs.level and item.reason == obs.reason for item in recent)
        ):
            return self._move(Observation(obs.health, obs.reason, recent[0].timestamp))
        return None

    def _escalate(self, window: list[Observation], target: int) -> Transition:
        started = next(item for item in window if item.level >= target)
        latest = next(item for item in reversed(window) if item.level == target)
        if self.confirmed is None or self.confirmed.level == 0:
            self.incident_started_at = started.timestamp
        return self._move(Observation(latest.health, latest.reason, started.timestamp))

    def _settle(self, window: list[Observation], target: int) -> Transition:
        latest = next(item for item in reversed(window) if item.level == target)
        since = window[0].timestamp
        duration = None
        if target == 0 and self.incident_started_at:
            duration = seconds_between(self.incident_started_at, since)
            self.incident_started_at = None
        return self._move(Observation(latest.health, latest.reason, since), duration)

    def _move(self, new: Observation, duration: float | None = None) -> Transition:
        previous, self.confirmed = self.confirmed, new
        return Transition(previous, new, duration)


def seconds_between(start: str, end: str) -> float | None:
    try:
        return max(0.0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
    except (TypeError, ValueError):
        return None
