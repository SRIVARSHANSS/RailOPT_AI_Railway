"""REAL data, Step 1: DG -> MDU corridor, timetable and running-record extract (RSTGCN Sept 2024).

Unit tests use tiny hand-made frames; the extract tests read the committed files in
backend/data/real/dg_mdu/; the reproducibility test needs the raw zip (gitignored) and skips without it.
"""
import filecmp
import json
import shutil

import pandas as pd
import pytest

from app.services.network.model import DEFAULT_DATA_DIR, load_network
from app.services.realdata import audit as A
from app.services.realdata import corridor as C
from app.services.realdata import extract as X

REAL = X.OUT_DIR


def test_clock_unroll_and_nearest():
    assert X.clock("12:05 AM") == 5 and X.clock("12:30 PM") == 750 and X.clock("11:59 PM") == 1439
    assert X.unroll([23 * 60, 23 * 60 + 40, 10, 55]) == [1380, 1420, 1450, 1495]   # crosses midnight
    assert X.nearest(5, 1440 + 2) == 1445 and X.nearest(1435, 1440 + 2) == 1435


def test_corridor_geometry():
    dg = C.derive_dg_chainage(11)
    assert dg.method == "DERIVED" and dg.km == pytest.approx(433.02)
    km = C.km_from_dg(dg)
    assert km["DG"] == 0 and list(km) == C.ORDER and km["MDU"] == pytest.approx(494.95 - 433.02)
    secs = C.sections(km)
    assert len(secs) == 7 and all(s["tracks"] == 1 for s in secs)
    assert sum(s["length_km"] for s in secs) == pytest.approx(km["MDU"], abs=0.02)
    assert all(s["min_run_min"] >= 1 for s in secs)


def test_train_type_rules():
    assert C.train_type(6011, "Tbm-ncj Sf Tod Special") == "SPECIAL"
    assert C.train_type(12637, "Pandian Sf Express") == "SUPERFAST"
    assert C.train_type(20665, "Ten Vandebharat") == "PREMIUM"
    assert C.train_type(20627, "Ms Ncj Vb Express") == "PREMIUM"
    assert C.train_type(16127, "Ms Guruvayur Express") == "EXPRESS"


def _routes(rows):
    return pd.DataFrame(rows, columns=["stnSerialNumber", "trainNumber", "trainName", "station_code",
                                       "station_name", "distance", "arrivalTime", "departureTime"])


def test_timetable_estimates_between_listed_stops_and_crosses_midnight():
    km = C.km_from_dg(C.derive_dg_chainage(11))
    routes = _routes([
        (1, 12999, "Test Sf Express", "TPJ", "x", 0, "10:00 PM", "10:00 PM"),
        (2, 12999, "Test Sf Express", "DG", "x", 90, "11:50 PM", "11:52 PM"),
        (3, 12999, "Test Sf Express", "SDN", "x", 130, "12:30 AM", "12:31 AM"),
        (4, 12999, "Test Sf Express", "MDU", "x", 152, "01:10 AM", "01:10 AM"),
    ])
    recs = pd.DataFrame(columns=["train", "date", "station", "sch_arr", "act_arr", "arr_delay",
                                 "sch_dep", "act_dep", "dep_delay"])
    trains, sched, excl, _ = X.build_timetable(routes, recs, km)
    assert len(trains) == 1 and not excl and trains[0]["terminates_at_mdu"] == "yes"
    s = {r["station_code"]: r for r in sched}
    assert [s[x]["time_source"] for x in C.ORDER] == ["DATASET_ROUTE", "ESTIMATED", "ESTIMATED", "ESTIMATED",
                                                       "DATASET_ROUTE", "ESTIMATED", "ESTIMATED", "DATASET_ROUTE"]
    assert s["SDN"]["stops"] == "yes" and s["KQN"]["stops"] == "no"
    assert s["SDN"]["arr_day"] == 1 and s["MDU"]["sched_dep"] == ""           # after midnight; terminal
    # ESTIMATED KQN lies on the straight line DG dep (23:52) -> SDN arr (00:30) by km
    t = 23 * 60 + 52 + 38 * km["KQN"] / km["SDN"]
    assert s["KQN"]["sched_arr"] == f"{int(round(t)) % 1440 // 60:02d}:{int(round(t)) % 60:02d}"


def test_degenerate_route_times_fall_back_to_record_schedule():
    km = C.km_from_dg(C.derive_dg_chainage(11))
    routes = _routes([(i + 1, 20999, "Test Sf Express", st, "x", d, "09:35 AM", "09:35 AM")
                      for i, (st, d) in enumerate([("CDG", 0), ("DG", 3000), ("MDU", 3066)])])
    recs = pd.DataFrame([
        (20999, "2024-09-02", "DG", "12:22 PM", "12:30 PM", 8.0, "12:25 PM", "12:33 PM", 8.0),
        (20999, "2024-09-02", "MDU", "01:50 PM", "01:55 PM", 5.0, "01:50 PM", "01:55 PM", 5.0),
    ], columns=["train", "date", "station", "sch_arr", "act_arr", "arr_delay", "sch_dep", "act_dep", "dep_delay"])
    trains, sched, _, _ = X.build_timetable(routes, recs, km)
    assert trains[0]["timetable_source"] == "DATASET_RECORDS"
    s = {r["station_code"]: r for r in sched}
    assert (s["DG"]["sched_dep"], s["MDU"]["sched_arr"]) == ("12:25", "13:50")


# ---------------------------------------------------------------- committed extract
def _need_extract():
    if not (REAL / "manifest.json").exists():
        pytest.skip("REAL extract missing: run python -m app.services.realdata.extract")


def test_extract_is_labelled_real_and_kept_apart_from_simulated():
    _need_extract()
    m = json.loads((REAL / "manifest.json").read_text(encoding="utf-8"))
    assert m["data_label"] == "REAL" and m["dg_chainage"]["method"] == "DERIVED"
    assert REAL.resolve().parent.name == "real" and REAL.resolve() != DEFAULT_DATA_DIR.resolve()
    assert len(load_network().trains) == 3                                  # simulated reference untouched
    assert (REAL.parent / "LICENSE-DATA").exists()
    st = pd.read_csv(REAL / "stations.csv")
    sec = pd.read_csv(REAL / "sections.csv")
    assert set(st.platforms_source) == {"ASSUMED"} and set(st.loops_source) == {"ASSUMED"}
    assert set(sec.min_run_source) == {"ASSUMED"} and set(sec.headway_source) == {"CALIBRATED"}
    assert (sec.min_headway_min == C.CALIBRATED_HEADWAY_MIN).all() and (sec.tracks == 1).all()
    assert set(pd.read_csv(REAL / "trains.csv").priority_source) == {"ASSUMED"}


def test_schedule_is_complete_monotonic_and_sourced():
    _need_extract()
    sched = pd.read_csv(REAL / "schedule.csv", dtype={"sched_dep": str, "dep_day": "Int64"})
    trains = pd.read_csv(REAL / "trains.csv")
    assert not trains.train_type.eq("SPECIAL").any()
    assert set(sched.time_source) <= {"DATASET_ROUTE", "DATASET_RECORDS", "ESTIMATED"}
    for tid, g in sched.groupby("train_id"):
        assert g.station_code.tolist() == C.ORDER
        assert g.set_index("station_code").loc[["DG", "MDU"], "time_source"].ne("ESTIMATED").all()
        t = []
        for _, r in g.iterrows():
            for col, day in (("sched_arr", "arr_day"), ("sched_dep", "dep_day")):
                if isinstance(r[col], str) and r[col]:
                    h, m = map(int, r[col].split(":"))
                    t.append(int(r[day]) * 1440 + h * 60 + m)
        assert t == sorted(t), tid


def test_records_are_consistent_with_the_source_delays():
    _need_extract()
    recs = pd.read_csv(REAL / "records.csv")
    runs = pd.read_csv(REAL / "runs.csv")
    assert recs.clock_mismatch.sum() == 0
    pos = recs.ds_arr_delay > 0
    assert (recs.arr_delay_min[pos] == recs.ds_arr_delay[pos]).all()
    assert set(runs.train_no) <= set(pd.read_csv(REAL / "trains.csv").train_no)
    assert len(runs) == len(runs.drop_duplicates(["train_no", "dg_date"]))


def test_audit_is_deterministic_and_matches_the_committed_report(tmp_path):
    _need_extract()
    if not (REAL / "audit.json").exists():
        pytest.skip("audit.json missing: run python -m app.services.realdata.audit")
    shutil.copytree(REAL, tmp_path / "dg_mdu")
    a = A.audit(tmp_path / "dg_mdu")
    assert a == json.loads((REAL / "audit.json").read_text(encoding="utf-8"))
    assert (tmp_path / "dg_mdu" / "audit.md").read_text(encoding="utf-8") == (REAL / "audit.md").read_text(encoding="utf-8")
    assert a["data_label"] == "REAL"


def test_extract_reproduces_the_committed_files(tmp_path):
    _need_extract()
    if not X.RAW_ZIP.exists():
        pytest.skip("raw RSTGCN zip not present (gitignored); see docs/DATA_SOURCES.md")
    X.extract(X.RAW_ZIP, tmp_path)
    for f in ("stations.csv", "sections.csv", "trains.csv", "schedule.csv", "records.csv", "runs.csv",
              "excluded_trains.csv", "manifest.json"):
        assert filecmp.cmp(tmp_path / f, REAL / f, shallow=False), f
