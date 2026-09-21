from collections.abc import Sequence

from tashevnet.models import Health
from tashevnet.state import Observation, StateTracker

UP = (Health.UP, "Connectivity is healthy")
DOWN = (Health.DOWN, "Internet/WAN probes are unreachable")
SLOW = (Health.DEGRADED, "High line latency")


def feed(tracker: StateTracker, states: Sequence[tuple[Health, str]], start: int = 0):
    """Feed one observation per 5 seconds and collect the transitions."""
    transitions = []
    for offset, (health, reason) in enumerate(states):
        second = (start + offset) * 5
        stamp = f"2026-09-21T10:{second // 60:02d}:{second % 60:02d}+00:00"
        result = tracker.observe(Observation(health, reason, stamp))
        if result is not None:
            transitions.append(result)
    return transitions


def test_healthy_start_is_not_an_incident():
    tracker = StateTracker()
    assert feed(tracker, [UP] * 5) == []
    assert tracker.confirmed is not None and tracker.confirmed.health == Health.UP


def test_outage_is_reported_once_with_its_real_start_and_duration():
    tracker = StateTracker()
    transitions = feed(tracker, [UP] * 3 + [DOWN] * 10 + [UP] * 3)
    assert [t.current.health for t in transitions] == [Health.DOWN, Health.UP]
    down, back = transitions
    assert down.current.timestamp == "2026-09-21T10:00:15+00:00"  # first failed check
    assert back.current.timestamp == "2026-09-21T10:01:05+00:00"  # first clean check
    assert back.duration_seconds == 50


def test_single_failed_check_is_not_an_incident():
    tracker = StateTracker()
    assert feed(tracker, [UP] * 3 + [DOWN] + [UP] * 5) == []


def test_flapping_line_is_one_incident_not_a_stream():
    tracker = StateTracker()
    transitions = feed(tracker, [UP] * 3 + [DOWN, UP] * 10)
    assert [t.current.health for t in transitions] == [Health.DOWN]


def test_latency_jitter_around_threshold_is_one_incident():
    tracker = StateTracker()
    transitions = feed(tracker, [UP] * 3 + [SLOW, UP] * 10)
    assert [t.current.health for t in transitions] == [Health.DEGRADED]


def test_problem_right_after_start_is_reported():
    tracker = StateTracker()
    transitions = feed(tracker, [DOWN] * 3)
    assert len(transitions) == 1 and transitions[0].previous is None


def test_partial_recovery_keeps_the_incident_open():
    tracker = StateTracker()
    transitions = feed(tracker, [UP] * 3 + [DOWN] * 4 + [SLOW] * 4 + [UP] * 3)
    assert [t.current.health for t in transitions] == [Health.DOWN, Health.DEGRADED, Health.UP]
    assert transitions[1].duration_seconds is None
    assert transitions[2].duration_seconds == 40  # measured from the start of the DOWN


def test_new_reason_at_the_same_level_is_a_change():
    tracker = StateTracker()
    vpn = (Health.DOWN, "VPN is required but no active VPN interface was detected")
    transitions = feed(tracker, [UP] * 3 + [DOWN] * 3 + [vpn] * 3)
    assert [t.current.reason for t in transitions] == [DOWN[1], vpn[1]]


def test_immediate_mode_reports_every_change():
    tracker = StateTracker(alert_after=1, recover_after=1)
    transitions = feed(tracker, [UP, DOWN, UP])
    assert [t.current.health for t in transitions] == [Health.DOWN, Health.UP]
