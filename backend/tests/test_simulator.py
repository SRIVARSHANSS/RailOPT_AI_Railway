"""Phase 1 tests. All scenarios are simulated on the sample corridor A-B-C-D."""
from app.services.network import parse_time
from app.services.simulator import Disruption, find_violations, simulate

T = parse_time


def stoppage_t101():
    return [Disruption("E1", "STOPPAGE", "T101", "S_BC", T("10:03"), 15)]


def test_normal_day_has_no_waits_delays_or_violations(net):
    result = simulate(net)
    assert all(o.wait == 0 for o in result.occupancies)
    assert result.metrics()["total_delay_min"] == 0
    assert find_violations(net, result) == []


def test_t101_stoppage_holds_t101_inside_b_c(net):
    result = simulate(net, stoppage_t101())
    occ = result.occupancy("T101", "S_BC")
    assert occ.stopped_min == 15
    assert occ.exit == T("10:23")          # 09:56 + 12 min run + 15 min stop


def test_t101_stoppage_cascades_to_t202_and_t303(net):
    events = stoppage_t101()
    result = simulate(net, events)

    t202 = result.occupancy("T202", "S_BC")
    assert t202.requested == T("10:13")
    assert t202.entry == T("10:28")        # T101 clears 10:23 + 5 min headway
    assert t202.wait == 15

    t303 = result.occupancy("T303", "S_BC")
    assert t303.entry == T("10:47")        # T202 clears 10:42 + 5 min headway
    assert t303.wait == 13

    assert {t: result.final_delay(t) for t in ["T101", "T202", "T303"]} == {
        "T101": 15, "T202": 15, "T303": 13}
    assert find_violations(net, result, events) == []


def test_extra_delay_event_holds_train_at_station(net):
    events = [Disruption("E2", "DELAY", "T202", "A", T("09:50"), 5)]
    result = simulate(net, events)
    assert result.call("T202", "A").dep == T("09:55")
    assert result.final_delay("T202") == 5
    assert find_violations(net, result, events) == []


def test_track_closure_blocks_entry(net):
    events = [Disruption("E3", "TRACK_UNAVAILABLE", None, "S_BC", T("10:10"), 20)]
    result = simulate(net, events)
    t202 = result.occupancy("T202", "S_BC")
    assert t202.entry >= T("10:30")        # cannot enter while the section is closed
    assert find_violations(net, result, events) == []


def test_reroute_override_uses_alternate_line(net):
    result = simulate(net, stoppage_t101(), route_overrides={("T202", "B"): "S_BC_ALT"})
    t202 = result.occupancy("T202", "S_BC_ALT")
    assert t202.wait == 0                  # alternate line is free
    assert t202.exit - t202.entry == 18    # 14 timetabled + 4 extra for the longer line


def test_controller_hold_is_respected(net):
    result = simulate(net, holds={("T303", "S_AB"): T("10:20")})
    assert result.occupancy("T303", "S_AB").entry == T("10:20")


def test_cascade_scenario_stoppage_delay_closure(net):
    """The re-optimization test sequence from the brief, simulated without re-planning."""
    events = stoppage_t101() + [
        Disruption("E2", "DELAY", "T202", "B", T("10:13"), 5),
        Disruption("E3", "TRACK_UNAVAILABLE", None, "S_CD", T("10:45"), 10),
    ]
    result = simulate(net, events)
    assert find_violations(net, result, events) == []
    assert result.metrics()["total_delay_min"] > 43   # worse than the stoppage alone


def test_platform_event_is_reported_not_silently_used(net):
    events = [Disruption("E4", "PLATFORM_UNAVAILABLE", None, "B", T("10:00"), 30)]
    result = simulate(net, events)
    assert any("platform model not built yet" in line for line in result.ignored_events)
