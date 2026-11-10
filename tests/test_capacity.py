from power_monitor.capacity import Step, hour_limit, project_hour, step_for, top3_average, with_hour
from power_monitor.grafana import line

STEPS = [Step(0, 2, 150), Step(2, 5, 250), Step(5, 10, 420), Step(10, 15, 585), Step(100, None, 6800)]


def test_top3_average_uses_three_highest_days():
    assert top3_average({"01": 5, "02": 9, "03": 10, "04": 8}) == 9


def test_top3_average_early_in_month():
    assert top3_average({"01": 4}) == 4
    assert top3_average({}) == 0


def test_with_hour_only_raises_that_days_peak():
    peaks = {"01": 10.35, "02": 9.75, "03": 9.66}
    assert with_hour(peaks, "03", 9.0)["03"] == 9.66
    assert top3_average(with_hour(peaks, "10", 10.3)) > 10


def test_step_for_boundaries():
    assert step_for(STEPS, 9.99).monthly_nok == 420
    assert step_for(STEPS, 10).monthly_nok == 585
    assert step_for(STEPS, 250).monthly_nok == 6800


def test_hour_limit_new_day_must_beat_third_place():
    # Top 3 is 10.35, 9.75, 9.66 (avg 9.92). A new day replaces 9.66; the average reaches 10
    # when the new hour is 3 * 10 - 10.35 - 9.75 = 9.90.
    peaks = {"01": 10.35, "02": 9.75, "03": 9.66, "04": 5.0}
    assert abs(hour_limit(peaks, "10", 10.0001) - 9.9001) < 0.001


def test_hour_limit_day_already_in_top3():
    # Day 03 already counts with 9.66; raising it to 9.90 reaches the 10 kWh step.
    peaks = {"01": 10.35, "02": 9.75, "03": 9.66}
    assert abs(hour_limit(peaks, "03", 10.0001) - 9.9001) < 0.001


def test_hour_limit_none_without_higher_step():
    assert hour_limit({"01": 5}, "02", None) is None


def test_project_hour():
    # 2 kWh so far, 6 kW for the last 30 minutes -> 5 kWh
    assert project_hour(2, 6000, 1800) == 5


def test_line_skips_empty_fields():
    assert line({"power_w": 2600, "x": None}, {"phase": "L1"}) == "power_monitor,phase=L1 power_w=2600.0"
    assert line({"x": None}) is None
