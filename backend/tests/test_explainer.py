"""Phase 7: template explanations. No LLM, no hand-typed numbers.

* every number in every generated sentence appears in the API payload it came from
* every model feature has a driver template; driver sentences explain the model's score
  ("Model risk raised/lowered by"), never a cause ("because")
* "optimal" only when the CP-SAT status is OPTIMAL
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.core.store import ScenarioStore, get_store
from app.main import app
from app.services.datagen.generator import FEATURES, NO_PRECEDING_GAP
from app.services.explainer import TEMPLATES, describe, driver_text, sentences
from app.services.explainer.recommendation import confidence
from app.services.network.model import REAL_DATA_DIR

NUM = re.compile(r"(?<![\w.:\-])-?\d+(?:\.\d+)?(?![\w:])")
TIME = re.compile(r"(?<![\w:])\d{1,2}:\d{2}(?![\w:])")
TEXT_KEYS = {"text", "sentence", "reason", "recommend", "counterfactual", "expected_impact", "solver",
             "confidence", "note", "plain_text", "summary", "items"}
STOP_T101 = {"event_type": "STOPPAGE", "train_id": "T101", "location": "S_BC", "start_time": "10:03",
             "duration_min": 15}
STOP_REAL = {"event_type": "STOPPAGE", "train_id": "R22627", "location": "S_ABI_KQN", "start_time": "08:53",
             "duration_min": 25}


@pytest.fixture()
def client():
    store = ScenarioStore()
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def sources(payload, numbers=None, times=None):
    """Numbers and HH:MM values of a payload, skipping the generated text itself."""
    numbers = set() if numbers is None else numbers
    times = set() if times is None else times
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in TEXT_KEYS:
                continue
            if isinstance(k, str) and NUM.fullmatch(k):
                numbers.add(abs(float(k)))
            sources(v, numbers, times)
    elif isinstance(payload, list):
        for v in payload:
            sources(v, numbers, times)
    elif isinstance(payload, bool) or payload is None:
        pass
    elif isinstance(payload, (int, float)):
        numbers.add(abs(float(payload)))
    elif isinstance(payload, str):           # data strings (actions, ids, times), never generated text
        times.update(TIME.findall(payload))
        numbers.update(abs(float(n)) for n in NUM.findall(TIME.sub(" ", payload)))
    return numbers, times


def assert_traceable(sentence: str, payload) -> None:
    numbers, times = sources(payload)
    for t in TIME.findall(sentence):
        assert t in times, (t, sentence)
    for n in NUM.findall(TIME.sub(" ", sentence)):
        assert abs(float(n)) in numbers, (n, sentence)


def check_optimize(o: dict) -> dict:
    expl = o["recommendation"]["explanation"]
    for s in sentences(expl):
        assert_traceable(s, o)
        if "optimal" in s.lower():
            assert o["recommendation"]["status"] == "OPTIMAL", s
    for s in sentences(expl):
        assert s in expl["plain_text"]
    others = {r["name"] for r in o["results"]} - {o["recommendation"]["strategy"]}
    assert {w["name"] for w in expl["why_not"]} == others | {u["name"] for u in o["unavailable"]}
    return expl


def check_drivers(conflicts_payload: dict) -> int:
    n = 0
    items = [c for c in conflicts_payload["conflicts"] if c["prediction"]] + conflicts_payload["ml_watchlist"]
    for item in items:
        drivers = item["top_drivers"] if "top_drivers" in item else item["prediction"]["top_drivers"]
        for d in drivers:
            assert d["sentence"].startswith("Model risk raised by: " if d["direction"] == "raises"
                                            else "Model risk lowered by: ")
            assert "because" not in d["sentence"].lower()
            assert_traceable(d["sentence"], d)
            n += 1
    return n


# ---- driver templates ---------------------------------------------------------------------
def test_every_feature_has_a_template():
    assert set(FEATURES) <= set(TEMPLATES)


@pytest.mark.parametrize("feature,value,expected", [
    ("headway_gap_min", -10, "it is planned to enter 10 min before the section clears"),
    ("headway_gap_min", 0, "it is planned to enter just as the section clears"),
    ("headway_gap_min", 4, "it is planned to enter 4 min after the section clears"),
    ("headway_gap_min", NO_PRECEDING_GAP, "no train is ahead of it on this section"),
    ("rule_flags_conflict", 1, "the rule-based detector also flags it"),
    ("rule_flags_conflict", 0, "the rule-based detector does not flag it"),
    ("current_delay_min", 0, "the train is on time"),
    ("current_delay_min", -2, "the train is 2 min early"),
    ("preceding_train_type", "NONE", "no train is ahead of it on this section"),
    ("trains_ahead_within_30min", 1, "1 other train enters this section within the half hour before it"),
])
def test_driver_text_examples(feature, value, expected):
    assert driver_text(feature, value) == expected


@pytest.mark.parametrize("feature", FEATURES)
@pytest.mark.parametrize("direction", ["raises", "lowers"])
def test_driver_sentences_explain_the_score_not_a_cause(feature, direction):
    for value in (0, 1, -7, 12, NO_PRECEDING_GAP, "EXPRESS", "NONE", "STOPPAGE", "S_BC"):
        try:
            d = describe({"feature": feature, "value": value, "shap": 0.1, "direction": direction})
        except (TypeError, ValueError):        # a numeric template given a word: not a real input
            continue
        assert "because" not in d["sentence"].lower()
        assert d["sentence"].startswith("Model risk raised by: " if direction == "raises"
                                        else "Model risk lowered by: ")
        assert_traceable(d["sentence"], {"value": value})


# ---- "optimal" only for OPTIMAL --------------------------------------------------------------
@pytest.mark.parametrize("status", ["FEASIBLE", "UNKNOWN", "INFEASIBLE"])
def test_optimal_only_when_status_is_optimal(status):
    assert "optimal" not in confidence(status, "HOLD").lower()
    sens = {"headway_min": 0, "alt_headway_min": 4, "recommended": "HOLD", "alt_recommended": "RESEQUENCE",
            "changed": True, "alt_ranking": ["RESEQUENCE", "HOLD"]}
    text = confidence(status, "HOLD", sens)
    assert "optimal" not in text.lower() and "Differs at headway 4 min" in text
    assert "optimal" in confidence("OPTIMAL", "HOLD").lower()


# ---- T101 reference scenario ------------------------------------------------------------------
def test_t101_explanation_is_traceable(client):
    client.post("/api/events", json=STOP_T101)
    o = client.post("/api/optimize", json={"at": "10:03"}).json()
    expl = check_optimize(o)
    assert o["recommendation"]["strategy"] == "REROUTE"
    assert "because T101 holds it" in expl["reason"]
    hold = next(w for w in expl["why_not"] if w["name"] == "HOLD")
    best = o["recommendation"]["weighted_delay"]
    assert hold["diff_weighted"] == hold["weighted_delay"] - best
    assert hold["text"] == f"HOLD: weighted delay {hold['weighted_delay']}, {hold['diff_weighted']} more than REROUTE."
    assert expl["constraints"]["respected"] and expl["constraints"]["violations"] == 0
    assert {a["item"] for a in expl["assumptions"]} == {1, 24, 3}
    assert {p["train_id"] for p in expl["per_train"]} <= set(o["recommendation"]["delays"])
    assert expl["plain_text"].startswith(f"RailOpt AI recommendation {o['recommendation']['recommendation_id']}")
    assert check_drivers(client.get("/api/conflicts", params={"at": "10:03"}).json()) > 0


def test_three_event_replan_is_traceable(client):
    client.post("/api/events", json=STOP_T101)
    o = client.post("/api/optimize", json={"at": "10:03"}).json()
    client.post(f"/api/recommendation/{o['recommendation']['recommendation_id']}/decision", json={"decision": "accept"})
    client.post("/api/events", json={"event_type": "DELAY", "train_id": "T202", "location": "A",
                                     "start_time": "10:05", "duration_min": 5})
    o2 = client.post("/api/optimize", json={"at": "10:05"}).json()
    if o2["recommendation"]:
        expl = check_optimize(o2)
        assert expl["counterfactual"].startswith(("Keeping the accepted plan", "Without re-planning"))


# ---- REAL recorded day ------------------------------------------------------------------------
@pytest.mark.skipif(not (REAL_DATA_DIR / "records.csv").exists(), reason="REAL extract missing")
def test_real_day_explanation_is_traceable(client):
    client.post("/api/scenario/reset", json={"timetable": "dg_mdu", "mode": "replay", "date": "2024-09-12"})
    client.post("/api/events", json=STOP_REAL)
    o = client.post("/api/optimize", json={"at": "08:53"}).json()
    expl = check_optimize(o)
    names = {a["name"]: a for a in expl["assumptions"]}
    assert names["min_headway_min"]["label"] == "CALIBRATED" and names["min_headway_min"]["value"] == 0
    assert names["loops"]["label"] == "ASSUMED" and names["priorities"]["label"] == "ASSUMED"
    assert any("free loop" in t for t in expl["constraints"]["items"])
    sens = o["sensitivity"]
    expected = (f"Same recommendation and ranking at headway {sens['alt_headway_min']} min" if not sens["changed"]
                else f"headway {sens['alt_headway_min']} min")
    assert expected in expl["confidence"]
    assert {w["name"] for w in expl["why_not"] if w["kind"] == "unavailable"} == {"REROUTE", "COMBINED"}
    c = client.get("/api/conflicts", params={"at": "08:53"}).json()
    assert check_drivers(c) == 0 and "not applied to REAL data" in c["ml_note"]
