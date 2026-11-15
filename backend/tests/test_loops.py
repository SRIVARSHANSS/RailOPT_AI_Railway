"""Loops and overtaking (REAL corridor rule, ASSUMPTIONS.md 65): a train can only be overtaken at
a station with a free loop. Tiny hand-made networks: A -> X -> B, one track per section."""
import pytest

from app.services.network.model import Section, StopTime, Station, Train, build_network
from app.services.optimizer import solve
from app.services.optimizer.strategies import run_strategy
from app.services.simulator import Disruption, find_violations, simulate
from app.services.simulator.checks import loop_violations


def net(loops_x: int | None, trains: dict[str, tuple[int, list[tuple]]]):
    stations = {"A": Station("A", "A", 0, 2, True, 4), "X": Station("X", "X", 10, 2, False, loops_x),
                "B": Station("B", "B", 20, 2, True, 4)}
    sections = {"S_AX": Section("S_AX", "A", "X", 10, 1, 5, 0, "open"),
                "S_XB": Section("S_XB", "X", "B", 10, 1, 5, 0, "open")}
    tr, sch = {}, {}
    for tid, (prio, stops) in trains.items():
        tr[tid] = Train(tid, tid, tid, {1: "PREMIUM", 2: "SUPERFAST", 3: "EXPRESS"}[prio], prio, "daily")
        sch[tid] = [StopTime(s, k + 1, a, d) for k, (s, a, d) in enumerate(stops)]
    return build_network(stations, sections, tr, sch)


SLOW = (3, [("A", None, 600), ("X", 605, 630), ("B", 635, None)])          # stands 25 min at X
FAST = (1, [("A", None, 606), ("X", 611, 611), ("B", 616, None)])          # passes X
SLOW2 = (3, [("A", None, 607), ("X", 612, 640), ("B", 645, None)])


def calls(res, tid):
    return {c.station: c for c in res.calls if c.train_id == tid}


def overtakes_at_x(res):
    xs = [c for c in res.calls if c.station == "X"]
    return [(b.train_id, a.train_id) for a in xs for b in xs if a.arr < b.arr and b.dep < a.dep]


def test_no_loop_no_overtake():
    n = net(0, {"SLOW": SLOW, "FAST": FAST})
    res = simulate(n)
    assert overtakes_at_x(res) == [] and find_violations(n, res) == []
    assert calls(res, "FAST")["X"].arr >= calls(res, "SLOW")["X"].dep       # waited until SLOW left X
    assert calls(res, "FAST")["B"].arr > calls(res, "SLOW")["B"].arr


def test_free_loop_allows_overtake():
    n = net(1, {"SLOW": SLOW, "FAST": FAST})
    res = simulate(n)
    assert overtakes_at_x(res) == [("FAST", "SLOW")] and find_violations(n, res) == []
    assert calls(res, "FAST")["B"].arr == 616                                 # on time


def test_one_loop_two_standing_trains_blocks_the_third():
    n = net(1, {"SLOW": SLOW, "SLOW2": SLOW2, "FAST": (1, [("A", None, 613), ("X", 618, 618), ("B", 623, None)])})
    res = simulate(n)
    assert find_violations(n, res) == []
    assert calls(res, "FAST")["X"].arr >= calls(res, "SLOW")["X"].dep       # waited for a free line
    two = net(2, {"SLOW": SLOW, "SLOW2": SLOW2, "FAST": (1, [("A", None, 613), ("X", 618, 618), ("B", 623, None)])})
    assert calls(simulate(two), "FAST")["B"].arr == 623                       # two loops: passes both


def test_checker_flags_an_overtake_without_a_loop():
    res = simulate(net(1, {"SLOW": SLOW, "FAST": FAST}))                      # overtakes at X
    msgs = loop_violations(net(0, {"SLOW": SLOW, "FAST": FAST}), res)
    assert any("overtook SLOW at X with 0 loop(s)" in m for m in msgs)
    assert loop_violations(net(None, {"SLOW": SLOW, "FAST": FAST}), res) == []   # not modelled -> no rule


@pytest.mark.parametrize("loops_x", [0, 1])
def test_resequence_never_overtakes_without_a_free_loop(loops_x):
    # SLOW is delayed at X: re-sequencing would like FAST to pass it there
    trains = {"SLOW": (3, [("A", None, 600), ("X", 605, 607), ("B", 612, None)]), "FAST": FAST}
    n = net(loops_x, trains)
    known = [Disruption("E1", "DELAY", "SLOW", "X", 606, 20)]
    sol = solve(n, 600, known, "RESEQUENCE")
    assert sol.status == "OPTIMAL"
    r = run_strategy(n, 600, known, "RESEQUENCE")
    assert r.violations == []
    if loops_x == 0:
        assert overtakes_at_x(r.replay) == []
    else:
        assert overtakes_at_x(r.replay) == [("FAST", "SLOW")]
