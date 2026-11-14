"""Thin FastAPI layer: the T101 demo flow and the API rules. All data SIMULATED."""
import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_predictor_or_none
from app.core.store import ScenarioStore, get_store
from app.main import app

STOPPAGE = {"event_type": "STOPPAGE", "train_id": "T101", "location": "S_BC",
            "start_time": "10:03", "duration_min": 15}


@pytest.fixture
def client():
    store = ScenarioStore()                       # fresh in-memory scenario per test
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def labelled(resp):
    body = resp.json()
    assert body["data_label"] == "SIMULATED", body
    return body


def test_full_t101_flow(client):
    assert labelled(client.post("/api/scenario/reset", json={"timetable": "reference"}))["events"] == []
    created = labelled(client.post("/api/events", json=STOPPAGE))
    assert created["event"]["event_id"] == "E1"

    conflicts = labelled(client.get("/api/conflicts", params={"at": "10:03"}))
    t202 = [c for c in conflicts["conflicts"] if c["later_train"] == "T202"]
    assert len(t202) == 1
    assert (t202[0]["section_id"], t202[0]["earlier_train"], t202[0]["severity"]) == ("S_BC", "T101", "CRITICAL")
    if t202[0]["prediction"] is not None:                       # needs the trained models
        assert 0.0 <= t202[0]["prediction"]["conflict_probability"] <= 1.0
        assert len(t202[0]["prediction"]["top_drivers"]) == 3

    opt = labelled(client.post("/api/optimize", json={"at": "10:03"}))
    rows = {r["name"]: r for r in opt["results"]}
    assert rows["NO_REPLANNING"]["weighted_delay"] == 88
    rec = opt["recommendation"]
    assert rec["strategy"] == "REROUTE" and rec["status"] == "OPTIMAL"
    assert rec["weighted_delay"] == 53
    assert rec["actions"] == ["reroute T202 B->C via S_BC_ALT"]
    assert rec["explanation"]["delta_weighted_delay"] == 53 - 88
    assert "88" in rec["explanation"]["counterfactual"]
    assert all(r["violations"] == 0 for r in opt["results"] if r["violations"] is not None)

    decided = labelled(client.post(f"/api/recommendation/{rec['recommendation_id']}/decision",
                                   json={"decision": "accept"}))
    assert decided["applied_recommendation"] == rec["recommendation_id"]
    assert decided["decision_log"][-1]["decision"] == "accept"

    state = labelled(client.get("/api/state", params={"at": "10:20"}))
    trains = {t["train_id"]: t for t in state["trains"]}
    assert trains["T202"]["status"] == "in_section" and trains["T202"]["location"] == "S_BC_ALT"
    assert trains["T101"]["location"] == "S_BC"               # still stopped in B-C
    assert state["kpis"]["conflicts"] == 0                    # the accepted plan resolves it

    timeline = labelled(client.get("/api/timeline"))
    actual = {(r["train_id"], r["section_id"]) for r in timeline["actual"]}
    planned = {(r["train_id"], r["section_id"]) for r in timeline["planned"]}
    assert ("T202", "S_BC_ALT") in actual and ("T202", "S_BC") in planned


def test_stoppage_is_unknown_before_it_starts(client):
    client.post("/api/scenario/reset", json={"timetable": "reference"})
    client.post("/api/events", json=STOPPAGE)
    before = labelled(client.get("/api/conflicts", params={"at": "10:00"}))
    assert before["known_events"] == []
    assert all(c["later_train"] != "T202" for c in before["conflicts"])
    after = labelled(client.get("/api/conflicts", params={"at": "10:03"}))
    assert after["known_events"] == ["E1"]
    assert any(c["later_train"] == "T202" and c["severity"] == "CRITICAL" for c in after["conflicts"])
    # movement still uses every event: at 10:00 T101 is running normally, at 10:10 it is stopped late
    state = labelled(client.get("/api/state", params={"at": "10:10"}))
    t101 = next(t for t in state["trains"] if t["train_id"] == "T101")
    assert t101["location"] == "S_BC" and t101["current_delay_min"] > 0


def test_planned_closure_is_known_as_soon_as_it_is_posted(client):
    client.post("/api/scenario/reset", json={"timetable": "reference"})
    client.post("/api/events", json={"event_type": "TRACK_UNAVAILABLE", "location": "S_BC",
                                     "start_time": "10:10", "duration_min": 20})
    body = labelled(client.get("/api/conflicts", params={"at": "10:00"}))
    assert body["known_events"] == ["E1"]
    closure = [c for c in body["conflicts"] if c["conflict_type"] == "CLOSURE"]
    assert [(c["later_train"], c["section_id"]) for c in closure] == [("T202", "S_BC")]


def test_optimize_only_sees_known_events(client):
    client.post("/api/scenario/reset", json={"timetable": "reference"})
    client.post("/api/events", json=STOPPAGE)
    opt = labelled(client.post("/api/optimize", json={"at": "10:00"}))
    assert opt["known_events"] == []
    assert {r["name"]: r["weighted_delay"] for r in opt["results"]}["NO_REPLANNING"] == 0


def test_reject_leaves_the_plan_unchanged_and_is_logged(client):
    client.post("/api/scenario/reset", json={"timetable": "reference"})
    client.post("/api/events", json=STOPPAGE)
    rec = client.post("/api/optimize", json={"at": "10:03"}).json()["recommendation"]
    rid = rec["recommendation_id"]
    labelled(client.post(f"/api/recommendation/{rid}/decision", json={"decision": "reject"}))
    scenario = labelled(client.get("/api/scenario"))
    assert scenario["applied_recommendation"] is None and scenario["route_overrides"] == []
    assert scenario["decision_log"][-1]["decision"] == "reject"
    t202 = next(t for t in client.get("/api/state", params={"at": "10:20"}).json()["trains"]
                if t["train_id"] == "T202")
    assert t202["status"] == "waiting_at_signal"
    again = client.post(f"/api/recommendation/{rid}/decision", json={"decision": "accept"})
    assert again.status_code == 409 and labelled(again)
    assert client.post("/api/recommendation/R99/decision", json={"decision": "accept"}).status_code == 404


@pytest.mark.parametrize("event, fragment", [
    ({**STOPPAGE, "train_id": "T999"}, "unknown train"),
    ({**STOPPAGE, "location": "B"}, "must be a section"),
    ({**STOPPAGE, "train_id": None}, "needs a train_id"),
    ({"event_type": "DELAY", "train_id": "T202", "location": "D", "start_time": "10:00", "duration_min": 5},
     "DELAY location"),
])
def test_bad_events_are_rejected_with_a_clear_message(client, event, fragment):
    client.post("/api/scenario/reset", json={"timetable": "reference"})
    resp = client.post("/api/events", json=event)
    assert resp.status_code == 422
    assert fragment in labelled(resp)["detail"]


def test_schema_validation_errors_are_labelled(client):
    resp = client.post("/api/events", json={**STOPPAGE, "start_time": "25:99"})
    assert resp.status_code == 422 and labelled(resp)
    assert client.get("/api/state", params={"at": "noon"}).status_code == 422


def test_network_health_and_cors(client):
    assert labelled(client.get("/api/health"))["status"] == "ok"
    full = labelled(client.get("/api/network", params={"timetable": "full_day"}))
    assert len(full["trains"]) == 12
    assert {s["section_id"]: s["tracks"] for s in full["sections"]}["S_BC"] == 1
    pre = client.options("/api/state", headers={"Origin": "http://localhost:5173",
                                                "Access-Control-Request-Method": "GET"})
    assert pre.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_conflicts_work_without_models(client):
    app.dependency_overrides[get_predictor_or_none] = lambda: None
    client.post("/api/scenario/reset", json={"timetable": "reference"})
    client.post("/api/events", json=STOPPAGE)
    body = labelled(client.get("/api/conflicts", params={"at": "10:03"}))
    assert body["conflicts"][0]["prediction"] is None
    assert "models not found" in body["ml_note"]
