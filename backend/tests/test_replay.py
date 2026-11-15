"""REAL recorded-day replay (Step 3), DG -> MDU, demo day 2024-09-12.

Labels: REAL while the recording is untouched; "HYPOTHETICAL on a real recorded day" once a
hypothetical event or a decision exists. Movement before the event stays as recorded."""
import json
import shutil

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.store import ScenarioStore, get_store
from app.main import app
from app.services import live
from app.services.network.model import REAL_DATA_DIR
from app.services.realdata import calibrate as CAL
from app.services.realdata.replay import (DEMO_DAY, HYPOTHETICAL_LABEL, check_day, forecast, frozen_movement,
                                          get_day, with_headway)
from app.services.simulator import simulate
from app.services.simulator.checks import loop_violations

pytestmark = pytest.mark.skipif(not (REAL_DATA_DIR / "records.csv").exists(), reason="REAL extract missing")

STOP = {"event_type": "STOPPAGE", "train_id": "R22627", "location": "S_ABI_KQN", "start_time": "08:53",
        "duration_min": 25}
T = 8 * 60 + 53


@pytest.fixture()
def client():
    store = ScenarioStore()
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_demo_day_reproduces_the_recording_exactly():
    day = get_day(DEMO_DAY)
    chk = check_day(day)
    assert chk["reproduced_exactly"] and chk["violations"] == 0 and chk["unresolved"] == 0
    assert chk["weekday"] == "Thu" and chk["trains"] == 22
    assert any(o["overtaking"] == "R22627" and o["overtaken"] == "R16343" for o in day.recorded_overtakes)
    # every recorded time is kept as recorded
    recs = pd.read_csv(REAL_DATA_DIR / "records.csv")
    recs = recs[recs.dg_date == DEMO_DAY]
    calls = {(c.train_id, c.station): c for c in day.recorded.calls}
    for r in recs.itertuples():
        tid = f"R{r.train_no}"
        if (tid, r.station_code) in day.interpolated and not day.interpolated[(tid, r.station_code)]:
            c = calls[(tid, r.station_code)]
            assert (c.arr in (None, r.act_arr_min)) and (c.dep in (None, r.act_dep_min))
    # no overtaking where there is no free loop, anywhere in the recorded movement
    assert loop_violations(day.movement, day.recorded) == []


def test_reset_replay_labels_and_header(client):
    r = client.post("/api/scenario/reset", json={"timetable": "dg_mdu", "mode": "replay", "date": DEMO_DAY})
    assert r.status_code == 200
    body = r.json()
    assert body["data_label"] == "REAL" and body["mode"] == "replay"
    assert body["replay"]["header"] == "REAL RECORDED MOVEMENTS - 2024-09-12 - RSTGCN Sept 2024 (CC BY-SA 4.0)"
    assert body["replay"]["divergence"] is None
    s = client.get("/api/state", params={"at": "08:30"}).json()
    assert s["data_label"] == "REAL" and s["kpis"]["conflicts"] == 0          # recorded reality: no FIRM conflict
    c = client.get("/api/conflicts", params={"at": "08:30"}).json()
    assert all(x["certainty"] == "ESTIMATED" for x in c["conflicts"]) and "SIMULATED" in c["ml_note"]
    assert client.post("/api/scenario/reset", json={"timetable": "dg_mdu", "mode": "replay",
                                                    "date": "2024-08-01"}).status_code == 422
    assert client.post("/api/scenario/reset", json={"timetable": "dg_mdu"}).status_code == 422
    assert client.post("/api/scenario/reset", json={"timetable": "reference"}).json()["data_label"] == "SIMULATED"


def test_hypothetical_stoppage_keeps_history_and_labels_decisions(client):
    client.post("/api/scenario/reset", json={"timetable": "dg_mdu", "mode": "replay", "date": DEMO_DAY})
    recorded = {(c.train_id, c.station): c for c in get_day(DEMO_DAY).recorded.calls}
    e = client.post("/api/events", json=STOP)
    assert e.status_code == 201 and e.json()["data_label"] == HYPOTHETICAL_LABEL
    o = client.post("/api/optimize", json={"at": "08:53"}).json()
    assert o["data_label"] == HYPOTHETICAL_LABEL
    assert [r["name"] for r in o["results"]] == ["NO_REPLANNING", "PRIORITY_DISPATCH", "HOLD", "RESEQUENCE"]
    assert {u["name"] for u in o["unavailable"]} == {"REROUTE", "COMBINED"}
    assert all("No alternate line" in u["reason"] for u in o["unavailable"])
    assert all(r["violations"] == 0 for r in o["results"] if r["weighted_delay"] is not None)
    assert o["sensitivity"]["headway_min"] == 0 and o["sensitivity"]["alt_headway_min"] == 4
    assert o["recommendation"]["strategy"] == "RESEQUENCE"
    d = client.post(f"/api/recommendation/{o['recommendation']['recommendation_id']}/decision",
                    json={"decision": "accept"}).json()
    assert d["data_label"] == HYPOTHETICAL_LABEL
    # history before the stoppage is exactly as recorded; the new movement has no loop violation
    store = app.dependency_overrides[get_store]()
    actual = store.actual()
    for c in actual.calls:
        r = recorded[(c.train_id, c.station)]
        for got, rec in ((c.arr, r.arr), (c.dep, r.dep)):
            if rec is not None and rec < T:
                assert got == rec, (c.train_id, c.station)
    assert loop_violations(frozen_movement(store.day, T), actual) == []
    tl = client.get("/api/timeline").json()
    assert tl["data_label"] == HYPOTHETICAL_LABEL and tl["before_plan"] is not None
    assert client.get("/api/scenario").json()["replay"]["divergence"] == "08:53"


def test_forecast_knows_only_the_past():
    day = get_day(DEMO_DAY)
    at = 8 * 60
    fnet = forecast(day, at)
    rec = {(c.train_id, c.station): c for c in day.recorded.calls}
    tt = day.timetable.schedules["R20627"]                      # departs DG ~10:00, after `at`
    f = fnet.schedules["R20627"]
    assert f[0].sched_dep == tt[0].sched_dep + round(day.upstream["R20627"])   # carried, not the recorded DG time
    assert rec[("R20627", "DG")].dep > at
    done = fnet.schedules["R11021"]                              # already at MDU by 08:00 -> recorded
    assert done[-1].sched_arr == rec[("R11021", "MDU")].arr


def test_headway_sensitivity_reports_both_rankings():
    store = ScenarioStore()
    store.reset("dg_mdu", "replay", DEMO_DAY)
    store.add_event("STOPPAGE", "R22627", "S_ABI_KQN", T, 25)
    net = store.planning_network(T)
    known = store.known_events(T)
    a = live.optimize_view(net, T, known)
    b = live.optimize_view(with_headway(net, 4), T, known)
    assert a["ranking"] and b["ranking"] and set(a["ranking"]) == set(b["ranking"]) == {"HOLD", "RESEQUENCE"}
    assert all(s.min_headway_min == 4 for s in with_headway(net, 4).sections.values())
    assert all(s.min_headway_min == 0 for s in net.sections.values())


def test_calibration_report_matches_a_fresh_run(tmp_path):
    stored = REAL_DATA_DIR / "calibration.json"
    if not stored.exists():
        pytest.skip("run python -m app.services.realdata.calibrate")
    shutil.copytree(REAL_DATA_DIR, tmp_path / "dg_mdu")
    out = json.loads(json.dumps(CAL.calibrate(tmp_path / "dg_mdu"), default=str))
    assert out == json.loads(stored.read_text(encoding="utf-8"))
    assert out["recorded_gaps"]["pairs"] == 75 and out["largest_headway_respected_by_recorded_pairs"] == 0


def test_api_boots_on_the_real_demo_day(monkeypatch):
    from app.core.store import boot_store
    monkeypatch.delenv("RAILOPT_BOOT", raising=False)
    s = boot_store()
    assert s.is_replay and s.timetable == "dg_mdu" and s.replay_date == DEMO_DAY
    assert s.label() == "REAL" and s.revision == 0
    monkeypatch.setenv("RAILOPT_BOOT", "simulated")
    s = boot_store()
    assert not s.is_replay and s.timetable == "reference" and s.label() == "SIMULATED"
