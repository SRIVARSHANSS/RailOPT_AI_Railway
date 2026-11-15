"""GET /api/timeline for the time-distance chart. All data SIMULATED."""
import pytest
from fastapi.testclient import TestClient

from app.core.store import ScenarioStore, get_store
from app.main import app
from app.services.simulator import simulate

STOPPAGE = {"event_type": "STOPPAGE", "train_id": "T101", "location": "S_BC", "start_time": "10:03", "duration_min": 15}
BLOCK = {"event_type": "TRACK_UNAVAILABLE", "train_id": None, "location": "S_BC", "start_time": "10:30", "duration_min": 20}


@pytest.fixture
def ctx():
    store = ScenarioStore()
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c, store
    app.dependency_overrides.clear()


def rows(tl, key):
    return {(r["train_id"], r["section_id"]): r for r in tl[key]}


def accept_reroute(c):
    rec = c.post("/api/optimize", json={"at": "10:03"}).json()["recommendation"]
    assert rec["strategy"] == "REROUTE"
    c.post(f"/api/recommendation/{rec['recommendation_id']}/decision", json={"decision": "accept"})
    return rec["recommendation_id"]


def test_timeline_without_plan_has_no_before_rows_and_matches_the_simulator(ctx):
    c, store = ctx
    c.post("/api/events", json=STOPPAGE)
    tl = c.get("/api/timeline").json()
    assert tl["data_label"] == "SIMULATED"
    assert tl["before_plan"] is None and tl["previous_plan"] is None and tl["closures"] == []

    actual = rows(tl, "actual")
    sim = simulate(store.network(), store.events)
    for o in sim.occupancies:
        r = actual[(o.train_id, o.section_id)]
        assert (r["entry_min"], r["exit_min"], r["wait_min"], r["stopped_min"]) == (o.entry, o.exit, o.wait, o.stopped_min)
    # T101 stands still in B-C exactly for the stoppage, and its delay is shown at C
    t101 = actual[("T101", "S_BC")]
    assert t101["stops"] == [{"start_min": 10 * 60 + 3, "end_min": 10 * 60 + 18}]
    assert t101["delay_min"] == 15 and not t101["alternate"]
    # no re-planning: T202 waits at the signal at B
    assert actual[("T202", "S_BC")]["wait_min"] > 0
    # the planned timetable is on time
    assert all(r["delay_min"] in (0, None) and r["wait_min"] == 0 for r in tl["planned"])


def test_before_and_after_the_accepted_reroute(ctx):
    c, _ = ctx
    c.post("/api/events", json=STOPPAGE)
    rec_id = accept_reroute(c)
    tl = c.get("/api/timeline").json()
    before, after = rows(tl, "before_plan"), rows(tl, "actual")
    assert tl["applied_recommendation"] == rec_id and tl["previous_plan"] is None
    # before: T202 queues behind T101 on S_BC; after: it runs on the alternate line, no wait
    assert before[("T202", "S_BC")]["wait_min"] > 0 and ("T202", "S_BC_ALT") not in before
    alt = after[("T202", "S_BC_ALT")]
    assert alt["alternate"] and alt["wait_min"] == 0 and ("T202", "S_BC") not in after
    assert after[("T202", "S_CD")]["delay_min"] < before[("T202", "S_CD")]["delay_min"]
    assert after[("T303", "S_CD")]["delay_min"] <= before[("T303", "S_CD")]["delay_min"]
    print(f"\n[SIMULATED] T202 at D: {before[('T202', 'S_CD')]['delay_min']} min late before the plan, "
          f"{after[('T202', 'S_CD')]['delay_min']} after")


def test_closures_are_blocks_and_before_plan_uses_the_replaced_plan(ctx):
    c, _ = ctx
    c.post("/api/events", json=STOPPAGE)
    r1 = accept_reroute(c)
    c.post("/api/events", json=BLOCK)
    tl = c.get("/api/timeline").json()
    assert tl["closures"] == [{"event_id": "E2", "section_id": "S_BC", "from_km": 22.0, "to_km": 40.0,
                               "start_min": 630, "end_min": 650, "start": "10:30", "end": "10:50"}]
    rec = c.post("/api/optimize", json={"at": "10:25"}).json()["recommendation"]
    c.post(f"/api/recommendation/{rec['recommendation_id']}/decision", json={"decision": "accept"})
    tl = c.get("/api/timeline").json()
    assert tl["previous_plan"] == r1
    before, after = rows(tl, "before_plan"), rows(tl, "actual")
    # before = R1: T202 already on the alternate line, T303 held until the block ends
    assert ("T202", "S_BC_ALT") in before and before[("T303", "S_BC")]["entry_min"] >= 650
    # after = R2: T303 follows T202 onto the alternate line
    assert after[("T303", "S_BC_ALT")]["alternate"]
    # a rejected recommendation does not change which plan is "before"
    rec3 = c.post("/api/optimize", json={"at": "10:26"}).json()["recommendation"]
    c.post(f"/api/recommendation/{rec3['recommendation_id']}/decision", json={"decision": "reject"})
    assert c.get("/api/timeline").json()["previous_plan"] == r1
