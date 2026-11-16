"""Pages 5 and 11: Conflicts and Alerts (lists, history, acknowledge) and Reports (scenario PDF + CSV,
evaluation PDF, model PDF, audit CSV). Every number in a report must trace back to an API payload."""
import csv
import io
import re
import shutil

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.core import auth
from app.core.store import ScenarioStore, get_store
from app.main import app
from app.services import results
from app.services.explainer.recommendation import reason_text
from app.services.reports import results_pdf
from tests._authkit import audit_rows

STOPPAGE = {"event_type": "STOPPAGE", "train_id": "T101", "location": "S_BC", "start_time": "10:03",
            "duration_min": 15, "at": "10:03"}


@pytest.fixture
def client(monkeypatch):
    store = ScenarioStore()
    app.dependency_overrides[get_store] = lambda: store
    from app.services.realdata import replay
    monkeypatch.setattr(replay, "day_checks", lambda: [])
    with TestClient(app) as c:
        c.store = store
        yield c
    app.dependency_overrides.pop(get_store, None)


def as_role(role: str):
    app.dependency_overrides[auth.current_user] = lambda: auth.stand_in_user(role)


def t101_flow(c, accept: bool = True) -> str:
    assert c.post("/api/scenario/reset", json={"timetable": "reference"}).status_code == 200
    assert c.post("/api/events", json=STOPPAGE).status_code == 201
    rec = c.post("/api/optimize", json={"at": "10:05"}).json()["recommendation"]
    if accept:
        assert c.post(f"/api/recommendation/{rec['recommendation_id']}/decision",
                      json={"decision": "accept"}).status_code == 200
    return rec["recommendation_id"]


def pdf_pages(body: bytes) -> list[str]:
    return [pg.extract_text() for pg in PdfReader(io.BytesIO(body)).pages]


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def csv_records(text: str) -> list[dict]:
    assert text.startswith("﻿")
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


# ---- Conflicts and Alerts --------------------------------------------------------------------------
def test_history_names_the_event_and_the_decision(client):
    rid = t101_flow(client)
    body = client.get("/api/alerts", params={"at": "10:30"}).json()
    assert body["data_label"] == "SIMULATED"
    ep = next(e for e in body["history"] if e["key"] == "C:OVERLAP:S_BC:T101:T202")
    assert (ep["appeared"], ep["appeared_cause"]["kind"], ep["appeared_cause"]["ids"]) == ("10:03", "EVENT", ["E1"])
    assert (ep["cleared"], ep["cleared_cause"]["kind"], ep["cleared_cause"]["ids"]) == ("10:05", "DECISION", [rid])
    assert auth.stand_in_user("CONTROLLER").email in ep["cleared_cause"]["text"]
    assert not ep["active"]


def test_current_lists_are_the_conflicts_api(client):
    t101_flow(client, accept=False)
    alerts = client.get("/api/alerts", params={"at": "10:05"}).json()
    api = client.get("/api/conflicts", params={"at": "10:05"}).json()
    rows = [r for r in alerts["current"] if r["category"] in ("CONFLICT", "UNCERTAIN")]
    assert len(rows) == len(api["conflicts"]) > 0
    for r, c in zip(rows, api["conflicts"]):
        assert (r["section_id"], r["severity"], r["window_start"], r["minutes_short"]) == \
               (c["section_id"], c["severity"], c["window_start"], c["minutes_short"])
        assert r["explanation"] == reason_text(c)                         # the Phase 7 sentence
    watch = [r for r in alerts["current"] if r["category"] == "ML_WATCH"]
    assert [(r["trains"][0], r["section_id"]) for r in watch] == [(w["train_id"], w["section_id"]) for w in api["ml_watchlist"]]
    for r in watch:
        assert all("because" not in d["sentence"] for d in r["drivers"])
        assert str(r["prediction"]["conflict_probability"]) in r["explanation"]
    assert alerts["counts"]["CONFLICT"] == len([r for r in rows if r["category"] == "CONFLICT"])


def test_closure_is_known_from_its_posting_clock(client):
    client.post("/api/scenario/reset", json={"timetable": "reference"})
    closure = {"event_type": "TRACK_UNAVAILABLE", "location": "S_CD", "start_time": "10:28",
               "duration_min": 60, "at": "10:00"}
    r = client.post("/api/events", json=closure)
    assert r.status_code == 201, r.text
    body = client.get("/api/alerts", params={"at": "10:40"}).json()
    assert body["posting_clock_missing"] == []
    clash = [e for e in body["history"] if e["key"].startswith("C:CLOSURE:S_CD")]
    assert clash, body["history"]
    assert all((e["appeared"], e["appeared_cause"]["ids"]) == ("10:00", ["E1"]) for e in clash)
    block = next(e for e in body["history"] if e["key"] == "CL:E1")
    assert block["appeared"] == "10:28" and block["category"] == "CLOSURE"
    row = next(r for r in body["current"] if r["key"] == "CL:E1")
    assert "S_CD is closed (E1) from 10:28 to 11:28" in row["explanation"]
    # posted without a clock: counted as known from the start, and reported
    r = client.post("/api/events", json={**closure, "location": "S_AB", "start_time": "13:00", "at": None})
    assert r.status_code == 201, r.text
    assert client.get("/api/alerts", params={"at": "10:40"}).json()["posting_clock_missing"] == ["E2"]


def test_acknowledge_is_logged_and_dimmed(client):
    t101_flow(client)
    key = "C:OVERLAP:S_BC:T101:T202"
    r = client.post("/api/alerts/ack", json={"key": key, "at": "10:30"})
    assert r.status_code == 200, r.text
    me = auth.stand_in_user("CONTROLLER").email
    assert r.json()["acknowledged"]["by"] == me
    rows = [a for a in audit_rows(action="ALERT_ACKNOWLEDGED") if a.detail["key"] == key
            and a.detail["scenario"] == client.store.run_ref]
    assert len(rows) == 1 and rows[0].email == me and rows[0].detail["at"] == "10:30"
    assert client.post("/api/alerts/ack", json={"key": key, "at": "10:30"}).status_code == 200
    assert len([a for a in audit_rows(action="ALERT_ACKNOWLEDGED") if a.detail.get("scenario") == client.store.run_ref]) == 1
    hist = client.get("/api/alerts", params={"at": "10:30"}).json()["history"]
    assert next(e for e in hist if e["key"] == key)["acknowledged"]["by"] == me
    assert client.post("/api/alerts/ack", json={"key": "C:NOPE:X:Y:Z", "at": "10:30"}).status_code == 404
    # a reset starts a new run: nothing is acknowledged there
    t101_flow(client)
    assert all(e["acknowledged"] is None for e in client.get("/api/alerts", params={"at": "10:30"}).json()["history"])


@pytest.mark.parametrize("role,alerts,ack,scenario_report,results_reports", [
    ("CONTROLLER", 200, 200, 200, 403),
    ("ANALYST", 200, 403, 200, 200),
    ("ADMIN", 403, 403, 200, 200),
])
def test_page_permissions_per_role(client, role, alerts, ack, scenario_report, results_reports):
    t101_flow(client)
    as_role(role)
    assert client.get("/api/alerts", params={"at": "10:30"}).status_code == alerts
    assert client.post("/api/alerts/ack", json={"key": "C:OVERLAP:S_BC:T101:T202", "at": "10:30"}).status_code == ack
    assert client.get("/api/reports/scenario.csv", params={"at": "10:30"}).status_code == scenario_report
    assert client.get("/api/reports/model.pdf").status_code == results_reports
    assert client.get("/api/admin/audit.csv").status_code == (200 if role == "ADMIN" else 403)


# ---- scenario report ---------------------------------------------------------------------------------
def test_scenario_report_matches_the_api(client):
    t101_flow(client)
    scn = client.get("/api/scenario", params={"at": "10:30"}).json()
    state = client.get("/api/state", params={"at": "10:30"}).json()
    rows = csv_records(client.get("/api/reports/scenario.csv", params={"at": "10:30"}).text)
    get = lambda sec, item, field: next(r["value"] for r in rows  # noqa: E731
                                        if (r["section"], r["item"], r["field"]) == (sec, item, field))
    assert get("meta", "", "scenario_version") == scn["scenario_version"]
    assert get("meta", "", "data_label") == "SIMULATED"
    assert get("meta", "", "generated_by") == auth.stand_in_user("CONTROLLER").email
    assert get("meta", "", "corridor") == "A → B → C → D"
    for k, v in state["kpis"].items():
        assert get("kpis", "10:30", k) == str(v)
    for t in state["trains"]:
        assert get("train", t["train_id"], "delay_at_clock_min") == str(t["current_delay_min"])
    for e in scn["events"]:
        assert get("event", e["event_id"], "start_time") == e["start_time"]
    for i, d in enumerate(scn["decision_log"], 1):
        assert get("decision", str(i), "decided_by") == d["decided_by"]
    rec = client.store.recommendations["R1"]
    assert get("recommendation", "R1", "plain_text") == rec.payload["explanation"]["plain_text"]
    assert any(r["section"] == "alert" and r["field"] == "cleared_cause" and "R1" in r["value"] for r in rows)

    body = client.get("/api/reports/scenario.pdf", params={"at": "10:30"})
    assert body.status_code == 200 and body.headers["content-type"] == "application/pdf"
    pages = pdf_pages(body.content)
    text = squash("".join(pages))
    for page in pages:
        assert "Data: SIMULATED" in page                                     # footer on every page
    for needle in [scn["scenario_version"], "10:30", auth.stand_in_user("CONTROLLER").email,
                   *(str(v) for v in state["kpis"].values()),
                   *(f"{t['train_id']}" for t in state["trains"])]:
        assert squash(needle) in text, needle
    for line in rec.payload["explanation"]["plain_text"].splitlines():
        assert squash(line) in text, line                                    # the full Phase 7 text
    assert len(audit_rows(action="REPORT_EXPORTED")) >= 2


def test_pdf_text_uses_dejavu_and_keeps_the_arrow(client):
    t101_flow(client)
    body = client.get("/api/reports/scenario.pdf", params={"at": "10:30"}).content
    assert "→" in "".join(pdf_pages(body))
    fonts = PdfReader(io.BytesIO(body)).pages[0]["/Resources"]["/Font"]
    names = {str(f.get_object()["/BaseFont"]) for f in fonts.values()}
    assert any("DejaVuSans" in n for n in names) and not any("Helvetica" in n for n in names), names


def test_real_day_labels_every_page(client):
    assert client.post("/api/scenario/reset", json={"timetable": "dg_mdu", "mode": "replay",
                                                    "date": "2024-09-12"}).status_code == 200
    pages = pdf_pages(client.get("/api/reports/scenario.pdf", params={"at": "09:00"}).content)
    assert all("Data: REAL" in pg for pg in pages)
    alerts = client.get("/api/alerts", params={"at": "09:00"}).json()
    assert alerts["data_label"] == "REAL"
    assert all(r["category"] != "ML_WATCH" for r in alerts["current"])      # ML is not applied to real days
    uncertain = [r for r in alerts["current"] if r["category"] == "UNCERTAIN"]
    assert all("uncertain" in r["explanation"] for r in uncertain)


# ---- evaluation and model reports ----------------------------------------------------------------------
def test_evaluation_report_numbers_come_from_the_summary(client):
    as_role("ANALYST")
    view = results.evaluation_view()
    assert view["status"] == "ok"
    r = client.get("/api/reports/evaluation.pdf")
    assert r.status_code == 200, r.text
    pages = pdf_pages(r.content)
    assert all("Data: SIMULATED" in pg for pg in pages)
    text = squash("".join(pages))
    s = view["summary"]
    assert squash(view["conclusion"]["text"]) in text
    for setting in ("deterministic", "robustness"):
        st = s["settings"][setting]
        for m in results_pdf.PHASE10:
            d = st["methods"][m]["weighted_delay"]
            assert squash(f"{d['mean']:.1f} [{d['mean_ci'][0]:.1f}, {d['mean_ci'][1]:.1f}]") in text, (setting, m)
            pv = st["paired_vs_no_replanning"].get(m, {}).get("weighted_delay")
            if pv:
                assert squash(f"{pv['wins']} / {pv['ties']} / {pv['losses']}") in text
        for m, v in st["variants_vs_dynamic"].items():
            p = v["weighted_delay"]
            assert squash(f"{p['mean_diff']:+.2f}".replace("+-", "-")) in text, m
    for limit in results.limits(s):
        assert squash(limit) in text


def test_stale_evaluation_refuses_export(client, tmp_path, monkeypatch):
    as_role("ANALYST")
    stale = tmp_path / "reports"
    shutil.copytree(results.EVAL_DIR, stale)
    with open(stale / "eval_results.csv", "a", encoding="utf-8") as f:
        f.write("\n")
    monkeypatch.setattr(results, "EVAL_DIR", stale)
    r = client.get("/api/reports/evaluation.pdf")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "outdated - rerun" in detail["message"] and detail["command"] in detail["message"]
    assert client.get("/api/reports").json()["evaluation"]["status"] == "outdated"


def test_model_report_has_both_cards_and_labels(client, tmp_path, monkeypatch):
    as_role("ADMIN")
    r = client.get("/api/reports/model.pdf")
    assert r.status_code == 200, r.text
    pages = pdf_pages(r.content)
    real_from = next(i for i, pg in enumerate(pages) if "real-data model card" in pg.lower() and "Data: REAL" in pg)
    assert all("Data: SIMULATED" in pg for pg in pages[:real_from])
    assert all("Data: REAL" in pg for pg in pages[real_from:])
    text = squash("".join(pages))
    real = (results_pdf.REAL_REPORTS / "model_card_real.md").read_text(encoding="utf-8")
    assert squash("4.18 vs 4.94") in text and "4.18 vs 4.94" in real    # a number straight from the card
    # an edited card is refused
    edited = tmp_path / "real"
    shutil.copytree(results_pdf.REAL_REPORTS, edited)
    (edited / "model_card_real.md").write_text(real.replace("4.18", "3.00"), encoding="utf-8")
    monkeypatch.setattr(results_pdf, "REAL_REPORTS", edited)
    r = client.get("/api/reports/model.pdf")
    assert r.status_code == 409 and "outdated - rerun" in r.json()["detail"]["message"]


def test_audit_csv_export(client):
    t101_flow(client)
    client.post("/api/alerts/ack", json={"key": "C:OVERLAP:S_BC:T101:T202", "at": "10:30"})
    as_role("ADMIN")
    r = client.get("/api/admin/audit.csv", params={"action": "ALERT_ACKNOWLEDGED"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = csv_records(r.text)
    assert rows and {x["action"] for x in rows} == {"ALERT_ACKNOWLEDGED"}
    assert any(client.store.run_ref in x["detail"] for x in rows)
