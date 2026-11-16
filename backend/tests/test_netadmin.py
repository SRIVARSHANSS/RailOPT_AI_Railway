"""Phase 8: network and train management - validation, CSV import with row-level errors, the
custom corridor in a scenario, and the read-only corridors (REAL shown with its sources)."""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.core.auth import stand_in_user
from app.core import auth
from app.core.store import ScenarioStore, get_store
from app.db.session import session_factory
from app.main import app
from app.services import netadmin
from app.services.network.model import REAL_DATA_DIR


@pytest.fixture()
def admin_client():
    store = ScenarioStore(custom_loader=netadmin.custom_network)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[auth.current_user] = lambda: stand_in_user("ADMIN")
    with session_factory()() as db:
        netadmin.reset_custom(db)
    with TestClient(app) as c:
        c.store = store
        yield c
    app.dependency_overrides.pop(get_store, None)


def to_csv(kind, rows):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=netadmin.COLUMNS[kind], lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def committed(name="full_day"):
    return {k: [{c: r.get(c, "") or "" for c in netadmin.COLUMNS[k]} for r in v]
            for k, v in netadmin.csv_tables(name).items()}


def test_committed_corridors_are_valid():
    assert netadmin.validate(committed("reference")) == []
    assert netadmin.validate(committed("full_day")) == []


@pytest.mark.parametrize("kind,row,col,value,expect", [
    ("stations", 2, "km_from_start", "-3", "km_from_start must be a number >= 0."),
    ("stations", 1, "is_junction", "maybe", "is_junction must be yes or no."),
    ("sections", 2, "to_station", "Z", "Unknown station Z."),
    ("sections", 1, "tracks", "0", "tracks must be a whole number from 1 to 4."),
    ("sections", 2, "status", "closed", "status must be open or standby"),
    ("trains", 1, "priority", "3", "EXPRESS trains have priority 1"),
    ("trains", 1, "train_type", "BULLET", "train_type must be EXPRESS, PASSENGER or FREIGHT."),
    ("schedule", 2, "sched_arr", "25:61", "sched_arr must be HH:MM"),
    ("schedule", 1, "station_code", "Q", "Unknown station Q."),
])
def test_row_level_errors(kind, row, col, value, expect):
    tables = committed()
    if kind == "trains":
        row = next(i for i, r in enumerate(tables["trains"], 1) if r["train_type"] == "EXPRESS")
    tables[kind][row - 1][col] = value
    errors = netadmin.validate(tables)
    hit = [e for e in errors if e["table"] == kind and e["row"] == row and e["column"] == col]
    assert hit and expect in hit[0]["message"], errors[:3]
    assert hit[0]["line"] == row + 1                                  # CSV line (header = line 1)


def test_schedule_below_minimum_running_time():
    tables = committed("reference")
    t101 = [r for r in tables["schedule"] if r["train_id"] == "T101"]
    t101[1]["sched_arr"] = "09:40"                                    # A dep 09:38 -> B arr 09:40: 2 min < 16
    errors = netadmin.validate(tables)
    assert any("below the section's minimum running time of 16 min" in e["message"] for e in errors)


def test_csv_import_rejects_and_saves_nothing(admin_client):
    before = admin_client.get("/api/admin/network/custom").json()["tables"]["stations"]
    bad = to_csv("stations", [{**before[0], "platforms": "x"}, *before[1:]])
    r = admin_client.post("/api/admin/network/custom/stations/import", json={"csv": bad})
    assert r.status_code == 422
    body = r.json()["detail"]
    assert "nothing was saved" in body["message"]
    assert body["errors"][0] == {"table": "stations", "row": 1, "line": 2, "column": "platforms", "value": "x",
                                 "message": "platforms must be a whole number from 1 to 20."}
    assert admin_client.get("/api/admin/network/custom").json()["tables"]["stations"] == before
    header = admin_client.post("/api/admin/network/custom/stations/import",
                               json={"csv": "station_code,name\nA,x\n"}).json()["detail"]["errors"][0]
    assert header["line"] == 1 and "missing column(s)" in header["message"] and "unknown column(s): name" in header["message"]


def test_csv_import_and_custom_scenario(admin_client):
    tables = admin_client.get("/api/admin/network/custom").json()["tables"]
    sections = [dict(s) for s in tables["sections"]]
    for s in sections:
        if s["section_id"] == "S_BC":
            s["min_headway_min"] = "7"
    r = admin_client.post("/api/admin/network/custom/sections/import", json={"csv": to_csv("sections", sections)})
    assert r.status_code == 200, r.text
    assert next(s for s in r.json()["tables"]["sections"] if s["section_id"] == "S_BC")["min_headway_min"] == "7"
    # the custom corridor runs as a SIMULATED scenario, with the ML models off
    app.dependency_overrides[auth.current_user] = lambda: stand_in_user("CONTROLLER")
    sc = admin_client.post("/api/scenario/reset", json={"timetable": "custom"}).json()
    assert sc["timetable"] == "custom" and sc["data_label"] == "SIMULATED"
    assert admin_client.store.network().sections["S_BC"].min_headway_min == 7
    c = admin_client.get("/api/conflicts", params={"at": "10:00"}).json()
    assert "custom corridor" in c["ml_note"]
    # while the scenario runs on it, the custom corridor cannot be edited
    app.dependency_overrides[auth.current_user] = lambda: stand_in_user("ADMIN")
    r = admin_client.put("/api/admin/network/custom/sections", json={"rows": sections})
    assert r.status_code == 409 and "Reset the scenario" in r.json()["detail"]
    admin_client.store.reset("reference")


def test_edit_table_validates_whole_corridor(admin_client):
    stations = admin_client.get("/api/admin/network/custom").json()["tables"]["stations"]
    r = admin_client.put("/api/admin/network/custom/stations", json={"rows": stations[:-1]})   # drop D
    assert r.status_code == 422
    errs = r.json()["detail"]["errors"]
    assert any(e["table"] == "sections" and e["message"] == "Unknown station D." for e in errs)
    assert any(e["table"] == "schedule" and e["message"] == "Unknown station D." for e in errs)


def test_read_only_corridors(admin_client):
    ref = admin_client.get("/api/admin/network/reference").json()
    assert ref["editable"] is False and ref["data_label"] == "SIMULATED"
    assert admin_client.put("/api/admin/network/reference/stations", json={"rows": []}).status_code in (404, 405)
    if (REAL_DATA_DIR / "stations.csv").exists():
        real = admin_client.get("/api/admin/network/dg_mdu").json()
        assert real["editable"] is False and real["data_label"] == "REAL"
        assert "CC BY-SA 4.0" in real["summary"] and real["licence"]
        assert real["tables"]["stations"][0]["chainage_source"] in ("DERIVED", "MAP_2024")
        assert admin_client.put("/api/admin/network/dg_mdu/stations", json={"rows": []}).status_code in (404, 405)


def test_reset_custom_reseeds(admin_client):
    stations = admin_client.get("/api/admin/network/custom").json()["tables"]["stations"]
    stations[0]["station_name"] = "Renamed A"
    assert admin_client.put("/api/admin/network/custom/stations", json={"rows": stations}).status_code == 200
    again = admin_client.post("/api/admin/network/custom/reset").json()
    assert again["tables"]["stations"][0]["station_name"] == committed()["stations"][0]["station_name"]
