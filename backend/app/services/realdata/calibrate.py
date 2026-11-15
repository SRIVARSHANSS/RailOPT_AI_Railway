"""Headway calibration on REAL recorded days (DG -> MDU), analysis only.

    python -m app.services.realdata.calibrate        (from backend/)

Builds every train's actual section occupancies from the recorded times (entry = departure
from the section's first station, exit = arrival at its last station). Stations a train does
not list are INTERPOLATED on km between its recorded neighbours. Runs the Phase 3 conflict
detector (`detect_conflicts`, same interval logic as the simulator's safety checks) over the
whole month on one continuous timeline, for each candidate headway, and splits every
"conflict" into RECORDED (both timestamps that define the gap are recorded) and ESTIMATED.
Also counts the order changes (overtakes) between consecutive sections at each station.
Writes backend/data/real/dg_mdu/calibration.json. Data label REAL.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from app.services.conflicts.detector import Plan, detect_conflicts
from app.services.realdata import corridor as C
from app.services.realdata.extract import OUT_DIR
from app.services.simulator.engine import Occupancy

CANDIDATES = [0, 1, 2, 3, 4, 5]
EPOCH = date(2024, 9, 1)


def occupancies(out_dir: Path = OUT_DIR, drop_flagged: bool = True):
    """Actual section occupancies on one continuous minute timeline (0 = 1 Sept 00:00).
    Returns (occupancies, recorded) where recorded[(train_key, station, 'arr'|'dep')] is True when
    that timestamp is a recorded value, not interpolated."""
    recs = pd.read_csv(out_dir / "records.csv")
    runs = pd.read_csv(out_dir / "runs.csv")
    st = pd.read_csv(out_dir / "stations.csv").set_index("station_code")
    km = st.km_from_start.to_dict()
    flagged = set()
    if drop_flagged:
        f = runs[(runs.mdu_arr_delay == 0) & (runs.dg_dep_delay >= 10)]
        flagged = set(zip(f.train_no, f.dg_date))
    occ, recorded, times = [], {}, {}
    for (t, d), g in recs.groupby(["train_no", "dg_date"]):
        base = (date.fromisoformat(d) - EPOCH).days * 1440
        key = f"{t}@{d}"
        g = g.set_index("station_code")
        pts = {s: (base + g.loc[s, "act_arr_min"], base + g.loc[s, "act_dep_min"]) for s in C.ORDER if s in g.index}
        if (t, d) in flagged:
            pts.pop("MDU", None)             # MDU time suspected filled with the schedule
        rec = set(pts)
        known = [s for s in C.ORDER if s in pts]
        for s in C.ORDER:
            if s in pts:
                continue
            prev = [k for k in known if C.ORDER.index(k) < C.ORDER.index(s)]
            nxt = [k for k in known if C.ORDER.index(k) > C.ORDER.index(s)]
            if not prev or not nxt:
                continue                      # no anchor on one side: leave out
            a, b = prev[-1], nxt[0]
            x = pts[a][1] + (pts[b][0] - pts[a][1]) * (km[s] - km[a]) / (km[b] - km[a])
            pts[s] = (x, x)
        for s in pts:
            recorded[(key, s, "arr")] = s in rec
            recorded[(key, s, "dep")] = s in rec
        times[key] = pts
        for a, b in zip(C.ORDER, C.ORDER[1:]):
            if a in pts and b in pts:
                occ.append(Occupancy(key, f"S_{a}_{b}", round(pts[a][1]), round(pts[a][1]), round(pts[b][0]), 0))
    return occ, recorded, times


def calibrate(out_dir: Path = OUT_DIR) -> dict:
    occ, recorded, times = occupancies(out_dir)
    secs = {r["section_id"]: r for r in pd.read_csv(out_dir / "sections.csv").to_dict("records")}
    first = {sid: sid.split("_")[1] for sid in secs}
    last = {sid: sid.split("_")[2] for sid in secs}
    trains = {o.train_id: SimpleNamespace(priority=1) for o in occ}
    out = {"data_label": C.DATA_LABEL, "occupancies": len(occ),
           "train_days": len(times), "candidates": {}}
    for h in CANDIDATES:
        net = SimpleNamespace(
            sections={sid: SimpleNamespace(tracks=1, min_headway_min=h) for sid in secs},
            trains=trains)
        conflicts = detect_conflicts(net, Plan(-10**9, occ, []))
        rows = defaultdict(lambda: {"RECORDED": 0, "ESTIMATED": 0})
        by_type = defaultdict(lambda: {"RECORDED": 0, "ESTIMATED": 0})
        for c in conflicts:
            e, l = c.trains
            rec = recorded[(e, last[c.section_id], "arr")] and recorded[(l, first[c.section_id], "dep")]
            k = "RECORDED" if rec else "ESTIMATED"
            rows[c.section_id][k] += 1
            by_type[c.conflict_type][k] += 1
        out["candidates"][h] = {
            "total": len(conflicts),
            "recorded": sum(r["RECORDED"] for r in rows.values()),
            "estimated": sum(r["ESTIMATED"] for r in rows.values()),
            "by_type": dict(by_type), "by_section": {s: rows[s] for s in secs if s in rows},
        }
    # recorded gaps: later entry - earlier exit on each section, only where both ends are recorded
    gaps = []
    by_sec = defaultdict(list)
    for o in occ:
        by_sec[o.section_id].append(o)
    for sid, os_ in by_sec.items():
        os_.sort(key=lambda o: (o.entry, o.train_id))
        for e, l in zip(os_, os_[1:]):
            if recorded[(e.train_id, last[sid], "arr")] and recorded[(l.train_id, first[sid], "dep")]:
                gaps.append({"section": sid, "gap": l.entry - e.exit, "earlier": e.train_id, "later": l.train_id})
    g = pd.DataFrame(gaps)
    out["recorded_gaps"] = {
        "pairs": int(len(g)),
        "min": None if g.empty else float(g.gap.min()),
        "smallest": g.nsmallest(8, "gap").to_dict("records") if not g.empty else [],
        "negative": int((g.gap < 0).sum()) if not g.empty else 0,
    }
    respected = [h for h in CANDIDATES if out["candidates"][h]["recorded"] == 0]
    out["largest_headway_respected_by_recorded_pairs"] = max(respected) if respected else None
    # order changes between consecutive sections at each intermediate station
    ov = defaultdict(lambda: {"RECORDED": 0, "ESTIMATED": 0})
    for i in range(1, len(C.ORDER) - 1):
        x = C.ORDER[i]
        sin, sout = f"S_{C.ORDER[i - 1]}_{x}", f"S_{x}_{C.ORDER[i + 1]}"
        arr = {o.train_id: o.exit for o in by_sec[sin]}
        dep = {o.train_id: o.entry for o in by_sec[sout]}
        both = sorted(set(arr) & set(dep), key=lambda k: arr[k])
        for a_i in range(len(both)):
            for b_i in range(a_i + 1, len(both)):
                a, b = both[a_i], both[b_i]       # a arrived first
                if arr[a] < arr[b] and dep[b] < dep[a] and arr[b] < dep[a]:
                    rec = recorded[(a, x, "dep")] and recorded[(b, x, "dep")]
                    ov[x]["RECORDED" if rec else "ESTIMATED"] += 1
    out["overtakes_by_station"] = {x: ov[x] for x in C.ORDER[1:-1]}
    (out_dir / "calibration.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(json.dumps(calibrate(), indent=2, default=str))
