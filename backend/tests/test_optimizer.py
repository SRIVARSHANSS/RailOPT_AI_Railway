"""Phase 5: CP-SAT optimizer, strategies and baselines. All results SIMULATED."""
from pathlib import Path

import pytest

from app.services.network import load_network
from app.services.network import parse_time as t
from app.services.optimizer import compare, run_strategy
from app.services.optimizer.solver import STRATEGIES
from app.services.simulator import Disruption, simulate

DATA = Path(__file__).resolve().parents[1] / "data"
T101_STOPPAGE = [Disruption("E1", "STOPPAGE", "T101", "S_BC", t("10:03"), 15)]
STRATEGY_NAMES = [s.name for s in STRATEGIES]


def toy_network(tmp_path, trains: list[tuple]) -> object:
    """Two stations X-Y, one 1-track section: 10 min run, 5 min headway.

    trains: (train_id, type, priority, dep 'HH:MM', arr 'HH:MM')
    """
    (tmp_path / "stations.csv").write_text(
        "station_code,station_name,km_from_start,platforms,is_junction\nX,X,0,2,yes\nY,Y,10,2,yes\n")
    (tmp_path / "sections.csv").write_text(
        "section_id,from_station,to_station,length_km,tracks,min_run_min,min_headway_min,status\n"
        "S_XY,X,Y,10,1,10,5,open\n")
    (tmp_path / "trains.csv").write_text(
        "train_id,train_no,train_name,train_type,priority,runs_on\n"
        + "".join(f"{tid},{tid},{tid},{typ},{prio},daily\n" for tid, typ, prio, _, _ in trains))
    (tmp_path / "schedule.csv").write_text(
        "train_id,station_code,stop_seq,sched_arr,sched_dep\n"
        + "".join(f"{tid},X,1,,{dep}\n{tid},Y,2,{arr},\n" for tid, _, _, dep, arr in trains))
    return load_network(tmp_path)


@pytest.fixture(scope="module")
def ref_results():
    return compare(load_network(DATA), t("10:03"), T101_STOPPAGE)


@pytest.fixture(scope="module")
def full_results():
    return compare(load_network(DATA, timetable="full_day"), t("10:03"), T101_STOPPAGE)


# --- toy case solved by hand ---------------------------------------------------------
def test_toy_case_matches_hand_solution(tmp_path):
    # Q (freight, weight 1) is scheduled first; P (express, weight 3) two minutes later.
    # Timetable order: Q 10:00-10:10, P waits to 10:15 -> 13 min late x 3 = 39.
    # Resequenced:     P 10:02-10:12, Q held to 10:17 -> 17 min late x 1 = 17.
    net = toy_network(tmp_path, [("Q", "FREIGHT", 3, "10:00", "10:10"),
                                 ("P", "EXPRESS", 1, "10:02", "10:12")])
    hold = run_strategy(net, t("09:55"), [], "HOLD")
    reseq = run_strategy(net, t("09:55"), [], "RESEQUENCE")
    assert hold.status == reseq.status == "OPTIMAL"
    assert hold.delays == {"P": 13, "Q": 0} and hold.weighted_delay == 39
    assert reseq.delays == {"P": 0, "Q": 17} and reseq.weighted_delay == 17
    assert reseq.actions == ["hold Q at X until 10:17 (ready 10:00, +17 min)"]
    assert reseq.violations == [] and reseq.mismatches == []


def test_priority_dispatch_lets_the_express_go_first(tmp_path):
    # R occupies S_XY 10:00-10:10 (free 10:15). Q waits from 10:05, P from 10:08.
    net = toy_network(tmp_path, [("R", "PASSENGER", 2, "10:00", "10:10"),
                                 ("Q", "FREIGHT", 3, "10:05", "10:15"),
                                 ("P", "EXPRESS", 1, "10:08", "10:18")])
    fcfs = simulate(net, dispatch="fcfs")
    prio = simulate(net, dispatch="priority")
    assert fcfs.occupancy("Q", "S_XY").entry == t("10:15")      # first come, first served
    assert prio.occupancy("P", "S_XY").entry == t("10:15")      # express overtakes at the signal
    assert prio.occupancy("Q", "S_XY").entry == t("10:30")
    assert prio.occupancy("Q", "S_XY").requested == t("10:05")  # wait still counted from ready time


def test_held_train_does_not_block_a_train_released_earlier(tmp_path):
    net = toy_network(tmp_path, [("Q", "FREIGHT", 3, "10:00", "10:10"),
                                 ("P", "EXPRESS", 1, "10:02", "10:12")])
    result = simulate(net, holds={("Q", "S_XY"): t("10:17")})
    assert result.occupancy("P", "S_XY").entry == t("10:02")
    assert result.occupancy("Q", "S_XY").entry == t("10:17")


# --- T101 reference ---------------------------------------------------------------------
def test_t101_every_strategy_is_optimal_with_a_clean_replay(ref_results):
    _print("T101 reference", ref_results)
    for r in ref_results:
        assert r.violations == [], r.name
        if r.kind == "strategy":
            assert r.status == "OPTIMAL", f"{r.name}: {r.status} {r.message}"


def test_t101_combined_is_best_on_weighted_delay(ref_results):
    combined = next(r for r in ref_results if r.name == "COMBINED")
    for r in ref_results:
        assert combined.weighted_delay <= r.weighted_delay, r.name


def test_solver_and_replay_times_agree(ref_results, full_results):
    for r in ref_results + full_results:
        if r.kind == "strategy":
            assert r.mismatches == [], r.name
            for trip in r.solve.trips:
                occ = r.replay.occupancy(trip.train_id, trip.section_id)
                assert (occ.entry, occ.exit) == (trip.entry, trip.exit)


def test_closure_is_never_used_and_no_train_departs_early():
    net = load_network(DATA)
    closure = [Disruption("E3", "TRACK_UNAVAILABLE", None, "S_BC", t("10:10"), 20)]
    for r in compare(net, t("10:05"), closure):
        assert r.violations == [], r.name
        if r.kind == "strategy":
            assert r.status == "OPTIMAL", r.name
        for o in r.replay.occupancies:
            if o.section_id == "S_BC":
                assert o.exit <= t("10:10") or o.entry >= t("10:30"), (r.name, o)
        for c in r.replay.calls:
            if c.dep is not None and c.sched_dep is not None:
                assert c.dep >= c.sched_dep, (r.name, c)


def test_full_day_solves_optimally_in_under_5_seconds(full_results):
    _print("full day", full_results)
    for r in full_results:
        assert r.violations == [], r.name
        if r.kind == "strategy":
            assert r.status == "OPTIMAL", f"{r.name}: {r.status} {r.message}"
            assert r.solve_seconds < 5, r.name


def test_impossible_input_returns_infeasible_not_a_crash():
    net = load_network(DATA)
    # main line closed far beyond the 24 h planning window; no reroute allowed
    closure = [Disruption("E9", "TRACK_UNAVAILABLE", None, "S_BC", t("10:10"), 2000)]
    r = run_strategy(net, t("10:09"), closure, "RESEQUENCE")
    assert r.status == "INFEASIBLE"
    assert "planning window" in r.message
    assert r.replay is None and r.actions == []
    combined = run_strategy(net, t("10:09"), closure, "COMBINED")
    print(f"\n[SIMULATED] same closure, COMBINED: {combined.status}, actions {combined.actions}")


def test_risk_buffers_keep_the_plan_valid():
    net = load_network(DATA)
    r = run_strategy(net, t("10:03"), T101_STOPPAGE, "COMBINED", risk_buffers={("T303", "S_BC"): 1})
    assert r.status == "OPTIMAL" and r.violations == [] and r.mismatches == []


def _print(title, results):
    print(f"\n[SIMULATED] {title}")
    for r in results:
        print(f"  {r.name:<18}{r.status:<10} weighted {r.weighted_delay} total {r.total_delay} "
              f"solve {r.solve_seconds} actions {r.actions}")
