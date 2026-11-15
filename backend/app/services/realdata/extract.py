"""Extract the DG -> MDU corridor from the RSTGCN Sept 2024 dataset (REAL data).

    python -m app.services.realdata.extract            (from backend/)

Reads backend/data/real/raw/Indian-Railway-Network-and-Delays.zip (gitignored, CC BY-SA 4.0) and
writes the small corridor extract to backend/data/real/dg_mdu/. Nothing here is simulated.

Dataset conventions found while auditing (ASSUMPTIONS.md 53-56):
- `date` is the journey START date; stations after midnight belong to the next calendar day.
- delays are never negative (early running is recorded as 0); signed delays are recomputed here
  from the scheduled and actual clock times.
- some trains have degenerate times in train_routes_Sep2024.csv (every station at one clock
  time); their timetable comes from the scheduled times inside the running records instead.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from app.services.realdata import corridor as C

BACKEND = Path(__file__).resolve().parents[3]
RAW_ZIP = BACKEND / "data" / "real" / "raw" / "Indian-Railway-Network-and-Delays.zip"
OUT_DIR = BACKEND / "data" / "real" / "dg_mdu"
PREFIX = "Indian-Railway-Network-and-Delays/"
CHECKED = "2026-11-15"                 # date the sources were checked / downloaded
SEPT = [date(2024, 9, d) for d in range(1, 31)]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------- time helpers
def clock(s: str) -> int:
    """'08:05 PM' -> minutes after midnight."""
    t, ap = s.strip().split()
    h, m = (int(x) for x in t.split(":"))
    return (h % 12 + (12 if ap.upper() == "PM" else 0)) * 60 + m


def unroll(clocks: list[int]) -> list[int]:
    """Clock times in travel order -> absolute minutes from the journey start date (adds a day
    whenever the clock goes backwards)."""
    out, day, prev = [], 0, None
    for c in clocks:
        if prev is not None and c < prev:
            day += 1
        out.append(c + day * 1440)
        prev = c
    return out


def nearest(clock_min: int, target_abs: float) -> int:
    """The absolute minute congruent to clock_min (mod 1440) nearest to target_abs."""
    base = int(target_abs // 1440) * 1440
    cands = [base - 1440 + clock_min, base + clock_min, base + 1440 + clock_min]
    return min(cands, key=lambda v: abs(v - target_abs))


def hhmm(abs_min: float) -> tuple[str, int]:
    m = int(round(abs_min))
    return f"{(m % 1440) // 60:02d}:{m % 60:02d}", m // 1440


# ---------------------------------------------------------------- loading
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_raw(zip_path: Path = RAW_ZIP) -> tuple[pd.DataFrame, pd.DataFrame]:
    with zipfile.ZipFile(zip_path) as z:
        routes = pd.read_csv(io.BytesIO(z.read(PREFIX + "train_routes_Sep2024.csv")))
        recs = pd.read_csv(io.BytesIO(z.read(PREFIX + "train_routes_delays_Sep2024.csv")),
                           dtype={"date": str, "station": str})
    return routes, recs


# ---------------------------------------------------------------- timetable
def corridor_trains(routes: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Trains whose route visits DG and later MDU (direction DG -> MDU)."""
    out = {}
    for t, g in routes.groupby("trainNumber"):
        g = g.sort_values("stnSerialNumber").reset_index(drop=True)
        s = g.station_code.tolist()
        if "DG" in s and "MDU" in s and s.index("DG") < s.index("MDU"):
            out[int(t)] = g
    return out


def degenerate(g: pd.DataFrame) -> bool:
    return g.arrivalTime.nunique() == 1 and g.departureTime.nunique() == 1 and len(g) > 2


def route_schedule(g: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """station -> (arr_abs, dep_abs) from the route file, minutes from journey start midnight."""
    seq = []
    for _, r in g.iterrows():
        seq += [clock(r.arrivalTime), clock(r.departureTime)]
    ab = unroll(seq)
    return {st: (ab[2 * i], ab[2 * i + 1]) for i, st in enumerate(g.station_code)}


def records_schedule(g: pd.DataFrame, recs_t: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """Fallback for degenerate route times: modal scheduled times per station in the records,
    put in route order and unrolled."""
    seq, stations = [], []
    for st in g.station_code:
        r = recs_t[recs_t.station == st]
        if r.empty:
            continue
        stations.append(st)
        seq += [clock(r.sch_arr.mode().iloc[0]), clock(r.sch_dep.mode().iloc[0])]
    ab = unroll(seq)
    return {st: (ab[2 * i], ab[2 * i + 1]) for i, st in enumerate(stations)}


def build_timetable(routes: pd.DataFrame, recs: pd.DataFrame, km: dict[str, float]):
    trains, sched, excluded, abs_sched = [], [], [], {}
    for t, g in sorted(corridor_trains(routes).items()):
        name = str(g.trainName.iloc[0]).strip()
        ttype = C.train_type(t, name)
        if ttype == "SPECIAL":
            excluded.append({"train_no": t, "train_name": name, "reason": "special train (0xxxx), not a regular service"})
            continue
        if degenerate(g):
            full = records_schedule(g, recs[recs.train == t])
            source = "DATASET_RECORDS"
        else:
            full = route_schedule(g)
            source = "DATASET_ROUTE"
        listed = [s for s in C.ORDER if s in full]
        if "DG" not in listed or "MDU" not in listed:
            excluded.append({"train_no": t, "train_name": name, "reason": "no usable DG/MDU times in the dataset"})
            continue
        abs_sched[t] = full
        terminal = g.station_code.iloc[-1] == "MDU"
        dg_day = full["DG"][1] // 1440
        base = dg_day * 1440
        rows = {}
        for st in C.ORDER:
            if st in full:
                a, d = full[st]
                stops = d > a or st in ("DG", "MDU")
                rows[st] = dict(arr=a, dep=d, src=source, stops=stops)
        # ESTIMATED passing times: linear in km between the neighbouring listed stations
        for st in C.ORDER:
            if st in rows:
                continue
            i = C.ORDER.index(st)
            prev = next(s for s in reversed(C.ORDER[:i]) if s in rows)
            nxt = next(s for s in C.ORDER[i + 1:] if s in rows)
            t0, t1 = rows[prev]["dep"], rows[nxt]["arr"]
            x = t0 + (t1 - t0) * (km[st] - km[prev]) / (km[nxt] - km[prev])
            rows[st] = dict(arr=x, dep=x, src="ESTIMATED", stops=False)
        for seq, st in enumerate(C.ORDER, 1):
            r = rows[st]
            arr, arr_day = hhmm(r["arr"] - base)
            dep, dep_day = hhmm(r["dep"] - base)
            first, last = st == "DG", st == "MDU"
            sched.append({
                "train_id": f"R{t}", "station_code": st, "stop_seq": seq,
                "sched_arr": arr, "sched_dep": "" if (last and terminal) else dep,
                "arr_day": arr_day, "dep_day": "" if (last and terminal) else dep_day,
                "stops": "yes" if r["stops"] else "no", "time_source": r["src"],
            })
        trains.append({
            "train_id": f"R{t}", "train_no": t, "train_name": name, "train_type": ttype,
            "priority": C.PRIORITY[ttype], "runs_on": "", "terminates_at_mdu": "yes" if terminal else "no",
            "timetable_source": source, "source": "RSTGCN train_routes_Sep2024.csv",
            "date_checked": CHECKED,
        })
    return trains, sched, excluded, abs_sched


# ---------------------------------------------------------------- running records
def build_records(recs: pd.DataFrame, abs_sched: dict[int, dict], routes_by_train: dict[int, pd.DataFrame]):
    rows, runs = [], []
    rec = recs[recs.train.isin(list(abs_sched))]
    for (t, jd), g in rec.groupby(["train", "date"]):
        full = abs_sched[t]
        order = routes_by_train[t].station_code.tolist()
        g = g.assign(_o=g.station.map({s: i for i, s in enumerate(order)})).sort_values("_o")
        start = date.fromisoformat(jd)
        dg_day = full["DG"][1] // 1440
        dg_date = start + timedelta(days=int(dg_day))
        base = dg_day * 1440
        per = {}
        for _, r in g.iterrows():
            st = r.station
            if st not in full:
                continue
            sa = nearest(clock(r.sch_arr), full[st][0])
            sd = nearest(clock(r.sch_dep), full[st][1])
            aa = nearest(clock(r.act_arr), sa + r.arr_delay)
            ad = nearest(clock(r.act_dep), sd + r.dep_delay)
            per[st] = dict(sa=sa, aa=aa, sd=sd, ad=ad, ds_ad=r.arr_delay, ds_dd=r.dep_delay)
        cor = [s for s in C.ORDER if s in per]
        if not cor:
            continue
        for st in cor:
            p = per[st]
            rows.append({
                "train_no": t, "journey_date": jd, "dg_date": dg_date.isoformat(), "station_code": st,
                "sched_arr_min": p["sa"] - base, "act_arr_min": p["aa"] - base,
                "sched_dep_min": p["sd"] - base, "act_dep_min": p["ad"] - base,
                "arr_delay_min": p["aa"] - p["sa"], "dep_delay_min": p["ad"] - p["sd"],
                "ds_arr_delay": p["ds_ad"], "ds_dep_delay": p["ds_dd"],
                "clock_mismatch": int(abs((p["aa"] - p["sa"]) - p["ds_ad"]) > 1 and p["ds_ad"] > 0),
            })
        # upstream: last recorded station before DG on this train's route
        up = None
        if "DG" in order:
            before = [s for s in order[: order.index("DG")] if s in g.station.values]
            if before:
                u = g[g.station == before[-1]].iloc[0]
                up = (before[-1], float(u.dep_delay))
        dg, mdu = per.get("DG"), per.get("MDU")
        runs.append({
            "train_no": t, "journey_date": jd, "dg_date": dg_date.isoformat(),
            "weekday": WEEKDAYS[dg_date.weekday()],
            "dg_arr_delay": None if dg is None else dg["aa"] - dg["sa"],
            "dg_dep_delay": None if dg is None else dg["ad"] - dg["sd"],
            "mdu_arr_delay": None if mdu is None else mdu["aa"] - mdu["sa"],
            "upstream_station": up[0] if up else "", "upstream_dep_delay": up[1] if up else None,
            "corridor_stations_recorded": len(cor),
        })
    return rows, runs


def derive_runs_on(runs: list[dict], trains: list[dict], abs_sched: dict) -> None:
    """runs_on (DG weekdays) DERIVED from the records: a weekday counts when the train was
    recorded on at least half of that weekday's dates in the month."""
    seen = defaultdict(set)
    for r in runs:
        seen[r["train_no"]].add(r["dg_date"])
    for tr in trains:
        t = tr["train_no"]
        dg_day = abs_sched[t]["DG"][1] // 1440
        possible = Counter(WEEKDAYS[(d + timedelta(days=int(dg_day))).weekday()] for d in SEPT)
        got = Counter(WEEKDAYS[date.fromisoformat(d).weekday()] for d in seen[t])
        days = [w for w in WEEKDAYS if possible[w] and got[w] / possible[w] >= 0.5]
        tr["runs_on"] = "daily" if len(days) == 7 else ",".join(days)


# ---------------------------------------------------------------- write
def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or (list(rows[0]) if rows else [])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def extract(zip_path: Path = RAW_ZIP, out_dir: Path = OUT_DIR) -> dict:
    routes, recs = load_raw(zip_path)
    by_train = corridor_trains(routes)
    dg_abi = [g.set_index("station_code").distance for g in by_train.values()
              if {"DG", "ABI"} <= set(g.station_code)]
    dg_abi_km = Counter(float(s["ABI"] - s["DG"]) for s in dg_abi).most_common(1)[0][0]
    dg = C.derive_dg_chainage(dg_abi_km)
    km = C.km_from_dg(dg)

    trains, sched, excluded, abs_sched = build_timetable(routes, recs, km)
    rows, runs = build_records(recs, abs_sched, by_train)
    derive_runs_on(runs, trains, abs_sched)

    out_dir.mkdir(parents=True, exist_ok=True)
    ch = C.chainages(dg)
    write_csv(out_dir / "stations.csv", [{
        "station_code": s, "station_name": C.STATION_NAMES[s], "km_from_start": km[s],
        "platforms": C.ASSUMED_PLATFORMS[s], "is_junction": "yes" if s in C.JUNCTIONS else "no",
        "chainage_km": ch[s].km, "chainage_source": ch[s].method, "platforms_source": "ASSUMED",
    } for s in C.ORDER])
    write_csv(out_dir / "sections.csv", [dict(r, run_headway_source="ASSUMED") for r in C.sections(km)])
    write_csv(out_dir / "trains.csv", trains)
    write_csv(out_dir / "schedule.csv", sched)
    write_csv(out_dir / "records.csv", rows)
    write_csv(out_dir / "runs.csv", runs)
    write_csv(out_dir / "excluded_trains.csv", excluded, ["train_no", "train_name", "reason"])
    manifest = {
        "data_label": C.DATA_LABEL, "corridor": C.CORRIDOR_ID, "direction": "DG -> MDU",
        "source_zip": zip_path.name, "source_zip_sha256": sha256(zip_path),
        "source_files": ["train_routes_Sep2024.csv", "train_routes_delays_Sep2024.csv"],
        "date_checked": CHECKED, "period": "2024-09-01..2024-09-30 (journey start dates)",
        "dg_chainage": {"km": dg.km, "method": dg.method, "note": dg.note},
        "licence": "CC BY-SA 4.0 (see LICENSE-DATA)",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"trains": trains, "schedule": sched, "records": rows, "runs": runs,
            "excluded": excluded, "km": km, "dg": dg, "manifest": manifest}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", type=Path, default=RAW_ZIP)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    a = ap.parse_args()
    res = extract(a.zip, a.out)
    print(f"REAL corridor extract written to {a.out}: {len(res['trains'])} trains, "
          f"{len(res['records'])} station records, {len(res['runs'])} train-days")


if __name__ == "__main__":
    main()
