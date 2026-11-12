"""Phase 2: variability + synthetic training-data generator.

Everything here is SIMULATED on the sample corridor.
"""
import random
import time
from pathlib import Path

import pandas as pd
import pytest

from app.services.conflicts import detect_conflicts, project_plan
from app.services.datagen import COLUMNS, generate, iter_runs
from app.services.datagen.generator import FEATURES, LABELS
from app.services.network import load_network
from app.services.network import parse_time as t
from app.services.simulator import DEFAULT_VARIABILITY, Disruption, find_violations, simulate

DATA = Path(__file__).resolve().parents[1] / "data"
T101_STOPPAGE = [Disruption("E1", "STOPPAGE", "T101", "S_BC", t("10:03"), 15)]


@pytest.fixture(scope="module")
def full():
    return load_network(DATA, timetable="full_day")


@pytest.fixture(scope="module")
def df200():
    return generate(200, 42)


# --- full-day timetable --------------------------------------------------------
def test_full_day_has_10_to_12_trains_and_keeps_the_reference_three(full):
    ref = load_network(DATA)
    assert 10 <= len(full.trains) <= 12
    for tid in ["T101", "T202", "T303"]:
        assert full.trains[tid] == ref.trains[tid]
        assert full.schedules[tid] == ref.schedules[tid]
    assert {full.trains[x].train_type for x in full.trains} == {"EXPRESS", "PASSENGER", "FREIGHT"}


def test_full_day_normal_day_is_conflict_free(full):
    assert detect_conflicts(full, project_plan(full, t("05:00"))) == []
    result = simulate(full)
    assert all(o.wait == 0 for o in result.occupancies)
    assert result.metrics()["total_delay_min"] == 0
    assert find_violations(full, result) == []


def test_unknown_timetable_is_rejected():
    with pytest.raises(ValueError):
        load_network(DATA, timetable="weekend")


# --- simulator randomness --------------------------------------------------------
def test_rng_none_reproduces_phase1_t101_results(full, net):
    for network in (net, full):
        result = simulate(network, T101_STOPPAGE, rng=None)
        assert {x: result.final_delay(x) for x in ["T101", "T202", "T303"]} == {
            "T101": 15, "T202": 15, "T303": 13}


def test_rng_only_ever_slows_trains_within_the_assumed_ranges(full):
    base = {(o.train_id, o.section_id): o.exit - o.entry for o in simulate(full).occupancies}
    limits = dict(DEFAULT_VARIABILITY.run_slowdown_max)
    for seed in range(20):
        for o in simulate(full, rng=random.Random(seed)).occupancies:
            planned = base[(o.train_id, o.section_id)]
            run = o.exit - o.entry
            assert planned <= run <= round(planned * (1 + limits[full.trains[o.train_id].train_type])) + 1
            assert run >= full.sections[o.section_id].min_run_min


def test_random_runs_never_break_capacity_headway_or_closures(full):
    for sample, result in iter_runs(300, 7, full):
        assert find_violations(full, result, sample.all_events) == [], sample.run_id


# --- generated table ----------------------------------------------------------------
def test_same_seed_identical_different_seed_different():
    a, b, c = generate(40, 123), generate(40, 123), generate(40, 124)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(c)


def test_columns_exactly_as_specified_and_no_nan(df200):
    assert list(df200.columns) == COLUMNS == ["run_id", *FEATURES, *LABELS]
    assert not df200.isna().any().any()
    assert (df200["time_to_section_min"] > 0).all()
    assert df200["run_id"].str.fullmatch(r"R\d{5}").all()
    assert set(df200["label_conflict"]) <= {0, 1}
    assert set(df200["rule_flags_conflict"]) <= {0, 1}


def test_conflict_rate_on_200_runs_is_plausible(df200):
    rate = df200["label_conflict"].mean()
    assert 0.05 <= rate <= 0.60


def test_200_runs_finish_in_under_30_seconds():
    started = time.perf_counter()
    generate(200, 99)
    assert time.perf_counter() - started < 30
