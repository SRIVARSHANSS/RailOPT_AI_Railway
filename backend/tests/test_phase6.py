"""Phase 6: what-if on a copy, stale plans, re-optimization from the current state,
and closures on occupied sections. All results SIMULATED (what-if: also HYPOTHETICAL)."""
import re

import pytest
from fastapi.testclient import TestClient

from app.core.store import ScenarioStore, get_store
from app.main import app
from app.services.network import format_time
from app.services.optimizer import compare
from app.services.simulator import simulate

STOPPAGE = {"event_type": "STOPPAGE", "train_id": "T101", "location": "S_BC", "start_time": "10:03", "duration_min": 15}
CLEAR = re.compile(r"after it clears \((\d\d:\d\d)\)")


@pytest.fixture
def ctx():
    store = ScenarioStore()
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c, store
    app.dependency_overrides.clear()


def t(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def started(sim, at):
    return {(o.train_id, o.section_id): (o.entry, o.exit) for o in sim.occupancies if o.entry <= at}


def optimize_and_check(c, store, at: int, label: str):
    """Re-optimize at `at`; every replay must be clean and keep started trips as the accepted plan made them."""
    net = store.network()
    known = store.known_events(at)
    resp = c.post("/api/optimize", json={"at": format_time(at)}).json()
    current = simulate(net, known, route_overrides=store.route_overrides, holds=store.holds)
    fixed = started(current, at)
    print(f"\n[SIMULATED] {label} - optimize at {format_time(at)}, re-planning from {resp['replanning_from']}")
    for row in resp["results"]:
        print(f"  {row['name']:<18} {row['status']:<9} weighted {row['weighted_delay']} total {row['total_delay']} "
              f"delays {row['delays']} actions {row['actions']}")
        assert row["violations"] in (0, None), row
        if row["kind"] == "strategy":
            assert row["status"] in ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "MODEL_INVALID")
    # inspect every replay: trips already started are exactly as the accepted plan made them
    for r in compare(net, at, known, base_holds=store.holds or None, base_overrides=store.route_overrides or None):
        if r.replay is None:
            continue
        assert r.violations == [], (r.name, r.violations)
        for (train, sec), times in fixed.items():
            occ = r.replay.occupancy(train, sec)
            assert (occ.entry, occ.exit) == times, (r.name, train, sec)
    rec = resp["recommendation"]
    print(f"  recommended {rec['strategy']} ({rec['status']}): {rec['explanation']['expected_impact']}")
    return rec


def test_three_event_reoptimization(ctx):
    c, store = ctx
    c.post("/api/scenario/reset", json={"timetable": "reference"})

    # 1) T101 stoppage, accept the recommendation
    c.post("/api/events", json=STOPPAGE)
    r1 = optimize_and_check(c, store, t("10:03"), "event 1: T101 stoppage")
    c.post(f"/api/recommendation/{r1['recommendation_id']}/decision", json={"decision": "accept"})
    assert store.plan_status(t("10:03"))["stale"] is False

    # 2) T202 leaves C 5 min late (delay at its departure time under the accepted plan)
    dep_c = store.actual().call("T202", "C").dep
    print(f"\n[SIMULATED] T202 departs C at {format_time(dep_c)} under {r1['strategy']}")
    resp = c.post("/api/events", json={"event_type": "DELAY", "train_id": "T202", "location": "C",
                                        "start_time": format_time(dep_c), "duration_min": 5})
    assert resp.status_code == 201
    assert c.get("/api/state", params={"at": format_time(dep_c - 1)}).json()["plan"]["stale"] is False
    plan = c.get("/api/state", params={"at": format_time(dep_c)}).json()["plan"]
    assert plan["stale"] is True and plan["new_events"] == ["E2"] and plan["applied"] == r1["recommendation_id"]
    r2 = optimize_and_check(c, store, dep_c, "event 2: T202 +5 at C")
    c.post(f"/api/recommendation/{r2['recommendation_id']}/decision", json={"decision": "accept"})
    assert store.decision_log[-1]["replaces"] == r1["recommendation_id"]
    assert store.plan_status(dep_c)["stale"] is False

    # 3) closure on S_CD (planned maintenance: known when posted), at 11:00 or the first clear minute
    t3 = dep_c + 7
    closure = {"event_type": "TRACK_UNAVAILABLE", "train_id": None, "location": "S_CD", "start_time": "11:00", "duration_min": 20}
    resp = c.post("/api/events", json=closure)
    if resp.status_code == 422:
        print(f"\n[SIMULATED] closure rejected: {resp.json()['detail']}")
        closure["start_time"] = CLEAR.search(resp.json()["detail"]).group(1)
        resp = c.post("/api/events", json=closure)
    assert resp.status_code == 201
    assert store.plan_status(t3)["stale"] is True
    r3 = optimize_and_check(c, store, t3, f"event 3: S_CD closed {closure['start_time']} for 20 min")
    c.post(f"/api/recommendation/{r3['recommendation_id']}/decision", json={"decision": "accept"})

    final = store.actual()
    print(f"\n[SIMULATED] final delays: { {x: final.final_delay(x) for x in sorted(store.network().trains)} }")
    print(f"[SIMULATED] decision log: {[(d['recommendation_id'], d['strategy'], d['replaces']) for d in store.decision_log]}")


def test_whatif_leaves_the_live_store_byte_for_byte_unchanged(ctx):
    c, store = ctx
    c.post("/api/scenario/reset", json={"timetable": "reference"})
    c.post("/api/events", json=STOPPAGE)
    rec = c.post("/api/optimize", json={"at": "10:03"}).json()["recommendation"]
    c.post(f"/api/recommendation/{rec['recommendation_id']}/decision", json={"decision": "accept"})
    before = store.snapshot()
    n_recs = len(store.recommendations)

    resp = c.post("/api/whatif", json={"at": "10:05", "events": [
        {"event_type": "DELAY", "train_id": "T303", "location": "A", "start_time": "10:10", "duration_min": 20}]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_label"] == "SIMULATED" and body["scenario_label"] == "HYPOTHETICAL"
    assert [e["event_id"] for e in body["hypothetical_events"]] == ["H1"]
    assert "H1" in body["hypothetical"]["known_events"]          # known at `at` although it starts later
    assert "H1" not in body["current"]["known_events"]
    assert "recommendation_id" not in (body["hypothetical"]["recommendation"] or {})
    assert all(r["violations"] in (0, None) for side in ("current", "hypothetical") for r in body[side]["results"])

    assert store.snapshot() == before
    assert len(store.recommendations) == n_recs
    assert [e.event_id for e in store.events] == ["E1"]


def test_closure_on_an_occupied_section_is_rejected_with_the_clear_time(ctx):
    c, _ = ctx
    c.post("/api/scenario/reset", json={"timetable": "reference"})
    closure = {"event_type": "TRACK_UNAVAILABLE", "location": "S_BC", "start_time": "10:05", "duration_min": 10}
    resp = c.post("/api/events", json=closure)                    # T101 runs S_BC 09:56-10:08
    assert resp.status_code == 422
    assert resp.json()["detail"] == ("T101 is inside S_BC at 10:05; closing an occupied section isn't modelled - "
                                     "choose a start after it clears (10:08)")
    assert c.post("/api/events", json={**closure, "start_time": "10:08"}).status_code == 201


def test_whatif_rejects_a_closure_on_a_section_occupied_in_the_hypothesis(ctx):
    c, _ = ctx
    c.post("/api/scenario/reset", json={"timetable": "reference"})
    # in the hypothesis T101 stands in S_BC until 10:23, so a 10:20 closure would strand it
    resp = c.post("/api/whatif", json={"at": "10:00", "events": [
        STOPPAGE,
        {"event_type": "TRACK_UNAVAILABLE", "location": "S_BC", "start_time": "10:20", "duration_min": 10}]})
    assert resp.status_code == 422
    assert resp.json()["detail"].startswith("Hypothetical event 2: T101 is inside S_BC at 10:20")
    assert CLEAR.search(resp.json()["detail"]).group(1) == "10:23"
    ok = c.post("/api/whatif", json={"at": "10:00", "events": [
        {"event_type": "TRACK_UNAVAILABLE", "location": "S_BC", "start_time": "10:08", "duration_min": 10}]})
    assert ok.status_code == 200


def test_stale_flag_on_scenario_without_clock(ctx):
    c, _ = ctx
    c.post("/api/scenario/reset", json={"timetable": "reference"})
    c.post("/api/events", json=STOPPAGE)
    rec = c.post("/api/optimize", json={"at": "10:03"}).json()["recommendation"]
    c.post(f"/api/recommendation/{rec['recommendation_id']}/decision", json={"decision": "accept"})
    assert c.get("/api/scenario").json()["plan"]["stale"] is False
    c.post("/api/events", json={"event_type": "DELAY", "train_id": "T303", "location": "B", "start_time": "10:40", "duration_min": 5})
    plan = c.get("/api/scenario").json()["plan"]                  # without a clock every posted event counts
    assert plan["stale"] is True and plan["new_events"] == ["E2"]
    assert c.get("/api/scenario", params={"at": "10:30"}).json()["plan"]["stale"] is False


def test_demo_act2_maintenance_block_replan_beats_keeping_the_plan(ctx):
    """Demo act 2: after the accepted reroute, a planned block closes S_BC 10:30-10:50 (posted 10:25).
    Numbers are printed; the assertion is only that re-planning beats keeping the plan."""
    c, store = ctx
    c.post("/api/scenario/reset", json={"timetable": "reference"})
    c.post("/api/events", json=STOPPAGE)
    r1 = c.post("/api/optimize", json={"at": "10:03"}).json()["recommendation"]
    c.post(f"/api/recommendation/{r1['recommendation_id']}/decision", json={"decision": "accept"})

    block = {"event_type": "TRACK_UNAVAILABLE", "location": "S_BC", "start_time": "10:30", "duration_min": 20}
    assert c.post("/api/events", json=block).status_code == 201       # nobody inside S_BC at 10:30
    assert c.get("/api/state", params={"at": "10:25"}).json()["plan"]["stale"] is True

    rec = optimize_and_check(c, store, t("10:25"), "act 2: S_BC maintenance block 10:30-10:50")
    rows = {r["name"]: r for r in c.post("/api/optimize", json={"at": "10:25"}).json()["results"]}
    keep = rows["NO_REPLANNING"]["weighted_delay"]
    print(f"\n[SIMULATED] keep plan: weighted {keep} {rows['NO_REPLANNING']['delays']}; "
          f"re-plan {rec['strategy']}: weighted {rec['weighted_delay']} {rec['delays']}")
    assert rec["weighted_delay"] < keep

    c.post(f"/api/recommendation/{rec['recommendation_id']}/decision", json={"decision": "accept"})
    after = store.actual()
    on_alt = [o.train_id for o in after.occupancies if o.section_id == "S_BC_ALT"]
    print(f"[SIMULATED] after accept: S_BC_ALT used by {on_alt}, delays "
          f"{ {x: after.final_delay(x) for x in sorted(store.network().trains)} }")
    assert "T202" in on_alt                                          # the started reroute is kept

    # talking point: the T202 +5 delay at C afterwards needs no new intervention
    dep_c = after.call("T202", "C").dep
    c.post("/api/events", json={"event_type": "DELAY", "train_id": "T202", "location": "C",
                                "start_time": format_time(dep_c), "duration_min": 5})
    optimize_and_check(c, store, dep_c, "act 2 talking point: T202 +5 at C")


def test_watchlist_marks_risk_reduced_not_resolved_when_wait_shrinks(ctx):
    """Act 2: after the re-plan T303 still waits at B, but less than under the plan it replaced (R1)."""
    c, _ = ctx
    c.post("/api/scenario/reset", json={"timetable": "reference"})
    c.post("/api/events", json=STOPPAGE)
    r1 = c.post("/api/optimize", json={"at": "10:03"}).json()["recommendation"]
    c.post(f"/api/recommendation/{r1['recommendation_id']}/decision", json={"decision": "accept"})
    c.post("/api/events", json={"event_type": "TRACK_UNAVAILABLE", "location": "S_BC", "start_time": "10:30", "duration_min": 20})
    r2 = c.post("/api/optimize", json={"at": "10:25"}).json()["recommendation"]
    c.post(f"/api/recommendation/{r2['recommendation_id']}/decision", json={"decision": "accept"})

    body = c.get("/api/conflicts", params={"at": "10:25"}).json()
    if body["ml_note"] and "models not found" in body["ml_note"]:
        pytest.skip("trained models needed for the ML watchlist")
    t303 = next(w for w in body["ml_watchlist"] if w["train_id"] == "T303" and w["section_id"] == "S_BC")
    print(f"\n[SIMULATED] T303 wait before B-C: {t303['baseline_wait_min']} min under {r1['recommendation_id']} -> "
          f"{t303['plan_wait_min']} min with {r2['recommendation_id']}")
    assert t303["reduced_by_plan"] is True and t303["resolved_by_plan"] is False
    assert 0 < t303["plan_wait_min"] < t303["baseline_wait_min"]

    # act 1 keeps the green 'resolved' case: zero wait in the plan's replay
    c.post("/api/scenario/reset", json={"timetable": "reference"})
    c.post("/api/events", json=STOPPAGE)
    r = c.post("/api/optimize", json={"at": "10:03"}).json()["recommendation"]
    c.post(f"/api/recommendation/{r['recommendation_id']}/decision", json={"decision": "accept"})
    w = next(w for w in c.get("/api/conflicts", params={"at": "10:03"}).json()["ml_watchlist"] if w["train_id"] == "T303")
    assert w["resolved_by_plan"] is True and w["reduced_by_plan"] is False and w["plan_wait_min"] == 0


def test_scenario_version_changes_on_restart_reset_events_and_decisions(ctx):
    """Clients cache optimizer results against scenario_version; it must change whenever the
    server-side scenario could differ: a restart (new store), reset, event or decision."""
    c, store = ctx
    v0 = c.get("/api/scenario").json()["scenario_version"]
    assert c.get("/api/state", params={"at": "10:00"}).json()["scenario_version"] == v0
    assert c.get("/api/scenario").json()["scenario_version"] == v0          # reads do not bump it

    # "restart": a fresh store (as on API start) gets a new random boot id, even at the same revision
    restarted = ScenarioStore()
    assert restarted.version != store.version
    assert restarted.version.split("-")[0] != v0.split("-")[0]

    assert c.post("/api/events", json=STOPPAGE).status_code == 201
    v1 = c.get("/api/scenario").json()["scenario_version"]
    assert v1 != v0
    opt = c.post("/api/optimize", json={"at": "10:03"}).json()
    assert opt["scenario_version"] == v1                                     # optimizing does not change it
    assert c.get("/api/state", params={"at": "10:03"}).json()["scenario_version"] == v1

    dec = c.post(f"/api/recommendation/{opt['recommendation']['recommendation_id']}/decision",
                 json={"decision": "accept"}).json()
    v2 = dec["scenario_version"]
    assert v2 != v1 and c.get("/api/scenario").json()["scenario_version"] == v2

    c.post("/api/whatif", json={"at": "10:20", "events": [{**STOPPAGE, "train_id": "T202", "start_time": "10:15"}]})
    assert c.get("/api/scenario").json()["scenario_version"] == v2           # a what-if is not a change

    v3 = c.post("/api/scenario/reset", json={"timetable": "reference"}).json()["scenario_version"]
    assert v3 not in (v0, v1, v2)
    assert len({v0, v1, v2, v3}) == 4
