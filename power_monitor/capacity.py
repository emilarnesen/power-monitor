"""Elvia's capacity charge (kapasitetsledd).

The monthly step is set by the average of the three highest hourly consumptions in the month,
each on a different day. These helpers answer: where are we now, and would the current hour
move us into a higher step?
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    min_kwh: float
    max_kwh: float | None  # None for the top step
    monthly_nok: float


def top3_average(daily_peaks: dict[str, float]) -> float:
    """Average of the three highest daily peaks (fewer early in the month)."""
    top = sorted(daily_peaks.values(), reverse=True)[:3]
    return sum(top) / len(top) if top else 0.0


def with_hour(daily_peaks: dict[str, float], day: str, kwh: float) -> dict[str, float]:
    """Daily peaks if the given day had an hour of kwh."""
    peaks = dict(daily_peaks)
    peaks[day] = max(peaks.get(day, 0.0), kwh)
    return peaks


def step_for(steps: list[Step], kwh: float) -> Step | None:
    for step in sorted(steps, key=lambda s: s.min_kwh):
        if kwh >= step.min_kwh and (step.max_kwh is None or kwh < step.max_kwh):
            return step
    return None


def project_hour(energy_so_far_kwh: float, power_w: float, seconds_left: float) -> float:
    """Energy the current hour ends at if power stays where it is."""
    return energy_so_far_kwh + power_w / 1000 * seconds_left / 3600
