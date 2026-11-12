"""Phase 3: rule-based conflict detector, on the real sample-corridor CSVs.

All results are SIMULATED.
"""
from app.services.conflicts import (
    CLOSURE,
    HEADWAY,
    OVERLAP,
    detect_conflicts,
    estimate_cascade,
    project_plan,
)
from app.services.network import parse_time as t
from app.services.simulator import Disruption, SimResult, find_violations
from app.services.simulator.engine import Occupancy

T101_STOPPAGE = Disruption("E1", "STOPPAGE", "T101", "S_BC", t("10:03"), 15)


# --- plan ------------------------------------------------------------------
def test_plan_matches_timetable_on_a_normal_day(net):
    plan = project_plan(net, t("09:00"))
    assert len(plan.trips) == 9
    trip = plan.trip("T202", "S_BC")
    assert (trip.entry, trip.exit) == (t("10:13"), t("10:27"))


def test_plan_applies_stoppage_to_own_train_but_nobody_waits(net):
    plan = project_plan(net, t("10:03"), [T101_STOPPAGE])
    t101 = plan.trip("T101", "S_BC")
    assert (t101.entry, t101.exit, t101.stopped_min) == (t("09:56"), t("10:23"), 15)
    # T101's own lateness carries on: 2 min dwell at C, then S_CD
    assert plan.trip("T101", "S_CD").entry == t("10:25")
    # T202 is NOT made to wait in the planned view
    assert plan.trip("T202", "S_BC").entry == t("10:13")


# --- detection ---------------------------------------------------------------
def test_normal_day_has_no_conflicts(net):
    assert detect_conflicts(net, project_plan(net, t("09:00"))) == []


def test_two_track_section_allows_two_overlapping_trains(net):
    plan = project_plan(net, t("09:00"))
    t101, t202 = plan.trip("T101", "S_AB"), plan.trip("T202", "S_AB")
    assert net.sections["S_AB"].tracks == 2
    assert t101.entry < t202.exit and t202.entry < t101.exit     # they really overlap
    assert [c for c in detect_conflicts(net, plan) if c.section_id == "S_AB"] == []


def test_t101_stoppage_gives_one_critical_overlap_with_t202(net):
    conflicts = detect_conflicts(net, project_plan(net, t("10:03"), [T101_STOPPAGE]))
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.section_id == "S_BC"
    assert c.trains == ("T101", "T202")
    assert c.conflict_type == OVERLAP
    assert c.window_start == t("10:13")          # T202 planned entry
    assert c.window_end == t("10:28")            # T101 clears 10:23 + 5 min headway
    assert c.minutes_short == 15
    assert c.time_to_conflict == 10
    assert c.severity == "CRITICAL"


def test_t303_is_not_a_direct_conflict_but_cascade_delays_it(net):
    conflicts = detect_conflicts(net, project_plan(net, t("10:03"), [T101_STOPPAGE]))
    assert all("T303" not in c.trains for c in conflicts)

    report = estimate_cascade(net, [T101_STOPPAGE], conflicts[0])
    assert report.source_train == "T101"
    assert [i.train_id for i in report.knock_on] == ["T202", "T303"]
    assert report.impact("T202").final_delay_min == 15
    assert report.impact("T303").final_delay_min == 13      # docs/ASSUMPTIONS.md
    assert report.impact("T303").wait_at_section_min == 13
    assert report.total_delay_min == 43
    assert "SIMULATED" in report.label


def test_headway_only_conflict(net):
    # T101 held 3 min at B: clears S_BC at 10:11, T202 enters 10:13 -> gap 2 < headway 5
    delay = Disruption("E2", "DELAY", "T101", "B", t("09:56"), 3)
    plan = project_plan(net, t("09:50"), [delay])
    assert plan.trip("T101", "S_BC").exit == t("10:11")

    conflicts = detect_conflicts(net, plan)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert (c.section_id, c.trains, c.conflict_type) == ("S_BC", ("T101", "T202"), HEADWAY)
    assert c.minutes_short == 3
    assert c.time_to_conflict == 23
    assert c.severity == "WARNING"


def test_track_closure_flags_t202(net):
    closure = Disruption("E3", "TRACK_UNAVAILABLE", None, "S_BC", t("10:10"), 20)
    conflicts = detect_conflicts(net, project_plan(net, t("10:00"), [closure]))
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_type == CLOSURE
    assert c.trains == (None, "T202")
    assert c.event_id == "E3"
    assert (c.window_start, c.window_end, c.minutes_short) == (t("10:13"), t("10:30"), 17)
    assert c.time_to_conflict == 13
    assert c.severity == "WARNING"      # more than 10 min ahead


def test_conflicts_already_over_are_not_reported(net):
    plan = project_plan(net, t("10:40"), [T101_STOPPAGE])
    assert detect_conflicts(net, plan) == []


# --- the shared interval logic still catches violations ---------------------------
def test_find_violations_still_flags_capacity_and_headway(net):
    bad = SimResult(occupancies=[
        Occupancy("T101", "S_BC", t("10:00"), t("10:00"), t("10:12")),
        Occupancy("T202", "S_BC", t("10:14"), t("10:14"), t("10:26")),   # only 2 min after T101
    ])
    problems = find_violations(net, bad)
    assert len(problems) == 1 and "T202" in problems[0]
