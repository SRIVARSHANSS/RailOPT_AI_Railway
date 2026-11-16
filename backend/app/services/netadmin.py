"""Network and train management (Phase 8, admin): view every corridor, edit the custom one.

* reference / full_day: the committed SIMULATED CSVs, read-only here (tests, demo numbers and the
  evaluation hashes depend on them).
* custom: an admin-editable SIMULATED corridor stored in the database (custom_* tables), seeded
  from full_day; load it with POST /api/scenario/reset {"timetable": "custom"}.
* dg_mdu: the REAL corridor, read-only, shown with its sources.

Edits and CSV imports replace one table at a time, and are validated together with the other
three tables: all rows are accepted or none, and every problem is reported with its row
(1-based data row; `line` = the CSV line, header = line 1) and column.
Plain Python (no FastAPI)."""
from __future__ import annotations

import csv
import io
import json
import re
import tempfile
from pathlib import Path

from sqlalchemy import delete, select

from app.db import models as m
from app.services.network.model import DEFAULT_DATA_DIR, REAL_DATA_DIR, TIMETABLES, load_network

COLUMNS = {
    "stations": ["station_code", "station_name", "km_from_start", "platforms", "is_junction"],
    "sections": ["section_id", "from_station", "to_station", "length_km", "tracks", "min_run_min",
                 "min_headway_min", "status"],
    "trains": ["train_id", "train_no", "train_name", "train_type", "priority", "runs_on"],
    "schedule": ["train_id", "station_code", "stop_seq", "sched_arr", "sched_dep"],
}
MODELS = {"stations": m.CustomStation, "sections": m.CustomSection, "trains": m.CustomTrain,
          "schedule": m.CustomStop}
TYPE_PRIORITY = {"EXPRESS": 1, "PASSENGER": 2, "FREIGHT": 3}    # SIMULATED types (ASSUMPTIONS 24, 66)
CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,19}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_ROWS = 2000
SEED = "full_day"
EDITABLE = "custom"
SIMULATED_SOURCE = ("SIMULATED sample corridor A-B-C-D (assumed values, docs/ASSUMPTIONS.md); "
                    "not a real railway.")


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------
def _csv_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def csv_tables(name: str) -> dict[str, list[dict]]:
    """The committed CSV tables of a timetable (all columns, as text)."""
    trains_file, schedule_file = TIMETABLES[name]
    folder = REAL_DATA_DIR if name == "dg_mdu" else DEFAULT_DATA_DIR
    return {"stations": _csv_rows(folder / "stations.csv"), "sections": _csv_rows(folder / "sections.csv"),
            "trains": _csv_rows(folder / trains_file), "schedule": _csv_rows(folder / schedule_file)}


def db_tables(db) -> dict[str, list[dict]]:
    """The custom corridor; seeded from full_day on first use."""
    out = {}
    for kind, model in MODELS.items():
        rows = db.scalars(select(model).order_by(model.pos)).all()
        out[kind] = [{c: getattr(r, c) for c in COLUMNS[kind]} for r in rows]
    if not any(out.values()):
        seed = {k: [{c: r.get(c, "") or "" for c in COLUMNS[k]} for r in v] for k, v in csv_tables(SEED).items()}
        for kind, rows in seed.items():
            _write(db, kind, rows)
        db.commit()
        return seed
    return out


def _write(db, kind: str, rows: list[dict]) -> None:
    model = MODELS[kind]
    db.execute(delete(model))
    for k, r in enumerate(rows, start=1):
        db.add(model(pos=k, **{c: (r.get(c) or "").strip() for c in COLUMNS[kind]}))


def sources(name: str) -> dict:
    if name == "dg_mdu":
        manifest = REAL_DATA_DIR / "manifest.json"
        lic = REAL_DATA_DIR.parent / "LICENSE-DATA"
        return {"data_label": "REAL", "editable": False,
                "summary": "REAL recorded corridor Dindigul -> Madurai (RSTGCN Sept 2024, CC BY-SA 4.0). "
                           "Read-only. Chainage of DG is DERIVED; platforms, loops, minimum running time and "
                           "priorities are ASSUMED; headway is CALIBRATED (docs/ASSUMPTIONS.md 47-71, "
                           "docs/DATA_SOURCES.md).",
                "manifest": json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else None,
                "licence": lic.read_text(encoding="utf-8") if lic.exists() else None,
                "source_columns": ["chainage_source", "platforms_source", "loops_source", "min_run_source",
                                   "headway_source", "priority_source", "timetable_source", "source",
                                   "time_source"]}
    if name == EDITABLE:
        return {"data_label": "SIMULATED", "editable": True,
                "summary": SIMULATED_SOURCE + " Editable copy (seeded from full_day), stored in the database. "
                           "Load it with Reset -> custom. The ML models are not applied to it."}
    return {"data_label": "SIMULATED", "editable": False,
            "summary": SIMULATED_SOURCE + f" Committed file ({name}); read-only because the tests, the demo "
                                          "and the evaluation depend on it. Edit the 'custom' copy instead."}


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------
def parse_csv(kind: str, text: str) -> tuple[list[dict], list[dict]]:
    """CSV text -> rows; header problems are reported on line 1."""
    errors: list[dict] = []
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in COLUMNS[kind] if c not in header]
    unknown = [c for c in header if c not in COLUMNS[kind]]
    if missing or unknown:
        msg = "; ".join(filter(None, [missing and f"missing column(s): {', '.join(missing)}",
                                      unknown and f"unknown column(s): {', '.join(unknown)}"]))
        return [], [err(kind, 0, None, None, f"Header: {msg}. Expected: {', '.join(COLUMNS[kind])}.")]
    rows = []
    for r in reader:
        rows.append({c: (r.get(c) or "").strip() for c in COLUMNS[kind]})
        if len(rows) > MAX_ROWS:
            return [], [err(kind, 0, None, None, f"More than {MAX_ROWS} rows.")]
    if not rows:
        errors.append(err(kind, 0, None, None, "The file has a header but no rows."))
    return rows, errors


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def err(table: str, row: int, column: str | None, value, message: str) -> dict:
    return {"table": table, "row": row, "line": row + 1, "column": column,
            "value": None if value is None else str(value), "message": message}


def _int(v, lo=None, hi=None):
    try:
        n = int(str(v).strip())
    except ValueError:
        return None
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        return None
    return n


def _float(v, lo=None):
    try:
        x = float(str(v).strip())
    except ValueError:
        return None
    return None if lo is not None and x < lo else x


def _minutes(v: str) -> int | None:
    return int(v[:2]) * 60 + int(v[3:]) if TIME.match(v) else None


def validate(tables: dict[str, list[dict]]) -> list[dict]:
    """Every problem in a corridor (row-level), or [] when it is valid."""
    E: list[dict] = []

    st = {}
    for i, r in enumerate(tables["stations"], start=1):
        code = r.get("station_code", "")
        if not CODE.match(code):
            E.append(err("stations", i, "station_code", code, "Code must be 1-20 capital letters, digits or _, starting with a letter."))
        elif code in st:
            E.append(err("stations", i, "station_code", code, f"Duplicate station {code}."))
        if not r.get("station_name"):
            E.append(err("stations", i, "station_name", "", "Name is required."))
        km = _float(r.get("km_from_start"), 0)
        if km is None:
            E.append(err("stations", i, "km_from_start", r.get("km_from_start"), "km_from_start must be a number >= 0."))
        if _int(r.get("platforms"), 1, 20) is None:
            E.append(err("stations", i, "platforms", r.get("platforms"), "platforms must be a whole number from 1 to 20."))
        if (r.get("is_junction") or "").lower() not in ("yes", "no"):
            E.append(err("stations", i, "is_junction", r.get("is_junction"), "is_junction must be yes or no."))
        if CODE.match(code):
            st.setdefault(code, km)
    kms = [k for k in st.values() if k is not None]
    if len(kms) != len(set(kms)):
        E.append(err("stations", 0, "km_from_start", None, "Two stations have the same km_from_start."))

    secs = {}
    for i, r in enumerate(tables["sections"], start=1):
        sid = r.get("section_id", "")
        if not CODE.match(sid):
            E.append(err("sections", i, "section_id", sid, "Section id must be 1-20 capital letters, digits or _."))
        elif sid in secs:
            E.append(err("sections", i, "section_id", sid, f"Duplicate section {sid}."))
        a, b = r.get("from_station", ""), r.get("to_station", "")
        for col, code in (("from_station", a), ("to_station", b)):
            if code not in st:
                E.append(err("sections", i, col, code, f"Unknown station {code}."))
        if a in st and b in st and st[a] is not None and st[b] is not None and st[b] <= st[a]:
            E.append(err("sections", i, "to_station", b, f"{b} must lie further along the line than {a} (one direction, increasing km)."))
        if _float(r.get("length_km"), 0.1) is None:
            E.append(err("sections", i, "length_km", r.get("length_km"), "length_km must be a number > 0."))
        if _int(r.get("tracks"), 1, 4) is None:
            E.append(err("sections", i, "tracks", r.get("tracks"), "tracks must be a whole number from 1 to 4."))
        run = _int(r.get("min_run_min"), 1, 600)
        if run is None:
            E.append(err("sections", i, "min_run_min", r.get("min_run_min"), "min_run_min must be a whole number of minutes >= 1."))
        if _int(r.get("min_headway_min"), 0, 60) is None:
            E.append(err("sections", i, "min_headway_min", r.get("min_headway_min"), "min_headway_min must be a whole number from 0 to 60."))
        status = (r.get("status") or "").lower()
        if status not in ("open", "standby"):
            E.append(err("sections", i, "status", r.get("status"), "status must be open or standby (standby = alternate line)."))
        if CODE.match(sid):
            secs.setdefault(sid, {"a": a, "b": b, "run": run, "status": status, "row": i})
    mains = {(s["a"], s["b"]): s for s in secs.values() if s["status"] == "open"}
    for sid, s in secs.items():
        if s["status"] == "standby" and (s["a"], s["b"]) not in mains:
            E.append(err("sections", s["row"], "status", "standby", f"Standby section {sid} needs an open section {s['a']}-{s['b']} beside it."))
    pairs = {}
    for sid, s in secs.items():
        if s["status"] == "open":
            if (s["a"], s["b"]) in pairs:
                E.append(err("sections", s["row"], "section_id", sid, f"Two open sections between {s['a']} and {s['b']}."))
            pairs[(s["a"], s["b"])] = s

    trains = {}
    for i, r in enumerate(tables["trains"], start=1):
        tid = r.get("train_id", "")
        if not CODE.match(tid):
            E.append(err("trains", i, "train_id", tid, "Train id must be 1-20 capital letters, digits or _."))
        elif tid in trains:
            E.append(err("trains", i, "train_id", tid, f"Duplicate train {tid}."))
        for col in ("train_no", "train_name", "runs_on"):
            if not r.get(col):
                E.append(err("trains", i, col, "", f"{col} is required."))
        ttype = (r.get("train_type") or "").upper()
        if ttype not in TYPE_PRIORITY:
            E.append(err("trains", i, "train_type", r.get("train_type"), "train_type must be EXPRESS, PASSENGER or FREIGHT."))
        prio = _int(r.get("priority"), 1, 3)
        if prio is None:
            E.append(err("trains", i, "priority", r.get("priority"), "priority must be 1, 2 or 3."))
        elif ttype in TYPE_PRIORITY and prio != TYPE_PRIORITY[ttype]:
            E.append(err("trains", i, "priority", r.get("priority"),
                         f"{ttype} trains have priority {TYPE_PRIORITY[ttype]} (objective weights by priority, ASSUMPTIONS 24)."))
        if CODE.match(tid):
            trains.setdefault(tid, i)

    stops: dict[str, list] = {}
    for i, r in enumerate(tables["schedule"], start=1):
        tid, code = r.get("train_id", ""), r.get("station_code", "")
        if tid not in trains:
            E.append(err("schedule", i, "train_id", tid, f"Unknown train {tid}."))
        if code not in st:
            E.append(err("schedule", i, "station_code", code, f"Unknown station {code}."))
        seq = _int(r.get("stop_seq"), 1, 99)
        if seq is None:
            E.append(err("schedule", i, "stop_seq", r.get("stop_seq"), "stop_seq must be a whole number >= 1."))
        times = {}
        for col in ("sched_arr", "sched_dep"):
            v = r.get(col, "")
            if v and _minutes(v) is None:
                E.append(err("schedule", i, col, v, f"{col} must be HH:MM (00:00-23:59) or empty."))
            times[col] = _minutes(v) if v else None
        if times["sched_arr"] is not None and times["sched_dep"] is not None and times["sched_dep"] < times["sched_arr"]:
            E.append(err("schedule", i, "sched_dep", r.get("sched_dep"), "Departure is before arrival."))
        if tid in trains and seq is not None:
            stops.setdefault(tid, []).append((seq, i, code, times["sched_arr"], times["sched_dep"]))
    for tid, row in trains.items():
        if tid not in stops:
            E.append(err("trains", row, "train_id", tid, f"{tid} has no schedule rows."))
    for tid, ss in stops.items():
        ss.sort()
        seqs = [s[0] for s in ss]
        if seqs != list(range(1, len(ss) + 1)):
            E.append(err("schedule", ss[0][1], "stop_seq", ",".join(map(str, seqs)), f"{tid}: stop_seq must run 1, 2, 3 ... without gaps or repeats."))
            continue
        if len(ss) < 2:
            E.append(err("schedule", ss[0][1], "train_id", tid, f"{tid} needs at least two stops."))
            continue
        if ss[0][4] is None:
            E.append(err("schedule", ss[0][1], "sched_dep", "", f"{tid}: the first stop needs a departure time."))
        if ss[-1][3] is None:
            E.append(err("schedule", ss[-1][1], "sched_arr", "", f"{tid}: the last stop needs an arrival time."))
        for k, s in enumerate(ss):
            if 0 < k < len(ss) - 1 and (s[3] is None or s[4] is None):
                E.append(err("schedule", s[1], "sched_arr" if s[3] is None else "sched_dep", "",
                             f"{tid}: an intermediate stop needs both times."))
        for p, n in zip(ss, ss[1:]):
            sec = pairs.get((p[2], n[2]))
            if sec is None:
                E.append(err("schedule", n[1], "station_code", n[2], f"{tid}: no open section from {p[2]} to {n[2]}."))
                continue
            if p[4] is not None and n[3] is not None:
                if n[3] < p[4]:
                    E.append(err("schedule", n[1], "sched_arr", None, f"{tid}: arrives at {n[2]} before leaving {p[2]}."))
                elif sec["run"] is not None and n[3] - p[4] < sec["run"]:
                    E.append(err("schedule", n[1], "sched_arr", None,
                                 f"{tid}: {p[2]}->{n[2]} is timetabled in {n[3] - p[4]} min, below the section's minimum running time of {sec['run']} min."))
    if not E:
        try:
            from app.services.simulator import simulate
            simulate(network_from_tables(tables))
        except Exception as exc:          # the model refuses the corridor: report it, accept nothing
            E.append(err("schedule", 0, None, None, f"The simulator rejects this corridor: {exc}"))
    return E


# ---------------------------------------------------------------------------
# network
# ---------------------------------------------------------------------------
def network_from_tables(tables: dict[str, list[dict]]):
    """Build a RailNetwork from tables through the same loader as the committed CSVs."""
    with tempfile.TemporaryDirectory() as d:
        for kind, file in (("stations", "stations.csv"), ("sections", "sections.csv"),
                           ("trains", "trains.csv"), ("schedule", "schedule.csv")):
            with (Path(d) / file).open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=COLUMNS[kind])
                w.writeheader()
                for r in tables[kind]:
                    w.writerow({c: r.get(c, "") for c in COLUMNS[kind]})
        return load_network(d, timetable="reference")


def custom_network():
    """The custom corridor as a RailNetwork (ScenarioStore.custom_loader)."""
    from app.db.session import session_factory
    with session_factory()() as db:
        return network_from_tables(db_tables(db))


def replace_table(db, kind: str, rows: list[dict]) -> tuple[bool, list[dict], dict]:
    """Validate the custom corridor with `kind` replaced; write it only when valid."""
    tables = db_tables(db)
    tables[kind] = [{c: (r.get(c) or "").strip() if isinstance(r.get(c), str) or r.get(c) is None
                     else str(r.get(c)) for c in COLUMNS[kind]} for r in rows]
    errors = validate(tables)
    if errors:
        db.rollback()
        return False, errors, tables
    _write(db, kind, tables[kind])
    db.commit()
    return True, [], tables


def reset_custom(db) -> dict:
    """Copy full_day into the custom corridor again."""
    for model in MODELS.values():
        db.execute(delete(model))
    db.commit()
    return db_tables(db)
