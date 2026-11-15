"""Phase 10 evaluation, fast version (10 scenarios). All results SIMULATED."""
import pytest

from app.services.datagen.generator import TIMETABLE
from app.services.network import load_network
from eval.evaluation import (
    METHODS, TRAINING_SEED, decision_points, evaluate_scenario, fingerprint, known_at, known_from,
    make_scenarios, training_fingerprints,
)

N, SEED = 10, 2026


@pytest.fixture(scope="module")
def net():
    return load_network(timetable=TIMETABLE)


@pytest.fixture(scope="module")
def predictor():
    from app.services.predictor import get_predictor
    try:
        return get_predictor()
    except Exception as exc:           # models are gitignored: trained by `python -m ml.train`
        pytest.skip(f"trained models needed for DYNAMIC_ML ({exc})")


@pytest.fixture(scope="module")
def evaluated(net, predictor):
    out = []
    for i, s in enumerate(make_scenarios(N, SEED, net)):
        rows, plans = evaluate_scenario(net, s, i, SEED, predictor)     # asserts zero violations
        out.append((s, rows, plans))
    return out


def _numbers(rows):
    """Everything except wall-clock solve time."""
    return [{k: v for k, v in r.items() if k != "solve_s_total"} for r in rows]


def test_reproducible_with_the_same_seed(net, predictor, evaluated):
    again = make_scenarios(N, SEED, net)
    assert [fingerprint(s) for s in again] == [fingerprint(s) for s, _, _ in evaluated]
    for i in (0, 4):
        rows, _ = evaluate_scenario(net, again[i], i, SEED, predictor)
        assert _numbers(rows) == _numbers(evaluated[i][1])
    assert [fingerprint(s) for s in make_scenarios(N, SEED + 1, net)] != [fingerprint(s) for s, _, _ in evaluated]


def test_every_method_and_setting_has_a_row_and_zero_violations(evaluated):
    for s, rows, _ in evaluated:
        assert {(r["method"], r["setting"]) for r in rows} == {(m, x) for m in METHODS for x in ("deterministic", "robustness")}
        assert all(r["label"] == "SIMULATED" for r in rows)
    # evaluate_scenario asserts find_violations == [] on the deterministic replay and all 5 seeded replays


def test_no_scenario_overlaps_the_training_data(net, evaluated):
    assert SEED != TRAINING_SEED
    train = training_fingerprints(net)
    assert len(train) > 2900                     # the 3000 training scenarios were rebuilt
    assert not [s.run_id for s, _, _ in evaluated if fingerprint(s) in train]


def test_time_aware_knowledge(evaluated):
    for s, _, _ in evaluated:
        for d in s.disruptions:
            if d.event_type == "TRACK_UNAVAILABLE":
                assert known_from(d) == max(6 * 60, d.start - 30)
            else:
                assert known_from(d) == d.start
        t0 = decision_points(s)[0]
        assert all(known_from(d) <= t0 for d in known_at(s, t0))
        assert all(d in known_at(s, t0) for d in s.starting_delays)


def test_optimal_single_shot_never_worse_than_no_replanning_on_known_events(evaluated):
    exceptions, checked = [], 0
    for s, rows, plans in evaluated:
        g = next(p for p in plans if p.method == "SINGLE_SHOT").guarantee
        if g["status"] != "OPTIMAL":
            continue
        checked += 1
        if g["worse_on_known"]:
            exceptions.append((s.run_id, g))
    print(f"\n[SIMULATED] OPTIMAL single-shot solves checked: {checked}, exceptions: {exceptions}")
    assert checked > 0
    assert exceptions == []
