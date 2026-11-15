"""Audit of the REAL DG -> MDU extract: coverage, missing data, observed delays.

    python -m app.services.realdata.audit              (from backend/, after extract)

Writes backend/data/real/dg_mdu/audit.json and audit.md. Every number is computed from the
extract files; audit.md is generated from audit.json (never edit it by hand).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.realdata import corridor as C
from app.services.realdata.extract import OUT_DIR, SEPT, WEEKDAYS

INTERMEDIATE = C.ORDER[1:-1]


def _dist(x: pd.Series) -> dict:
    x = x.dropna().astype(float)
    if x.empty:
        return {"n": 0}
    q = np.percentile(x, [10, 25, 50, 75, 90, 95])
    return {
        "n": int(len(x)), "mean": round(float(x.mean()), 2), "min": float(x.min()),
        "p10": float(q[0]), "p25": float(q[1]), "median": float(q[2]), "p75": float(q[3]),
        "p90": float(q[4]), "p95": float(q[5]), "max": float(x.max()),
        "share_on_time_le_0": round(float((x <= 0).mean()), 3),
        "share_le_5": round(float((x <= 5).mean()), 3),
        "share_gt_15": round(float((x > 15).mean()), 3),
        "share_gt_60": round(float((x > 60).mean()), 3),
        "histogram": {k: int(v) for k, v in pd.cut(
            x, [-1e9, 0, 5, 15, 30, 60, 120, 1e9],
            labels=["<=0", "1-5", "6-15", "16-30", "31-60", "61-120", ">120"]).value_counts(sort=False).items()},
    }


def audit(out_dir: Path = OUT_DIR) -> dict:
    trains = pd.read_csv(out_dir / "trains.csv")
    sched = pd.read_csv(out_dir / "schedule.csv")
    recs = pd.read_csv(out_dir / "records.csv")
    runs = pd.read_csv(out_dir / "runs.csv")
    excl = pd.read_csv(out_dir / "excluded_trains.csv")
    secs = pd.read_csv(out_dir / "sections.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    # --- timetable
    tt = {
        "regular_trains": int(len(trains)),
        "by_type": {k: int(v) for k, v in trains.train_type.value_counts().items()},
        "excluded": excl.to_dict("records"),
        "timetable_from_records_fallback": trains.loc[trains.timetable_source == "DATASET_RECORDS", "train_no"].tolist(),
        "cells": {k: int(v) for k, v in sched.time_source.value_counts().items()},
        "passenger_memu": "none in the dataset (it excludes local trains): known to run, "
                          "schedule not in the dataset, not modelled",
        "runs_on_weekday_counts": {w: int(sum(1 for r in trains.runs_on if r == "daily" or w in str(r).split(",")))
                                   for w in WEEKDAYS},
    }

    # --- coverage
    in_ds = sorted(set(recs.train_no))
    def group(st):
        return "DG" if st == "DG" else "MDU" if st == "MDU" else "intermediate"
    recs["group"] = recs.station_code.map(group)
    cov = {g: {"station_records": int((recs.group == g).sum()),
               "trains": int(recs.loc[recs.group == g, "train_no"].nunique()),
               "days": int(recs.loc[recs.group == g, "dg_date"].nunique())}
           for g in ("DG", "intermediate", "MDU")}
    cov["per_station"] = {s: int((recs.station_code == s).sum()) for s in C.ORDER}
    dg_dates = sorted(set(runs.dg_date))

    # --- missing: expected train-days from runs_on, and scheduled stops not recorded
    # journeys started 1-30 Sept; a train reaching DG the day after it starts has DG dates 2 Sept-1 Oct
    offset = (pd.to_datetime(runs.dg_date) - pd.to_datetime(runs.journey_date)).dt.days
    off_by_train = offset.groupby(runs.train_no).agg(lambda s: int(s.mode().iloc[0])).to_dict()
    expected = 0
    for _, tr in trains.iterrows():
        days = WEEKDAYS if tr.runs_on == "daily" else str(tr.runs_on).split(",")
        off = off_by_train.get(tr.train_no, 0)
        expected += sum(1 for d in SEPT if WEEKDAYS[(d + timedelta(days=off)).weekday()] in days)
    observed = int(len(runs))
    stops = sched[sched.time_source != "ESTIMATED"]
    exp_rows = got_rows = 0
    rec_keys = set(zip(recs.train_no, recs.dg_date, recs.station_code))
    for _, r in runs.iterrows():
        listed = stops[stops.train_id == f"R{r.train_no}"].station_code
        exp_rows += len(listed)
        got_rows += sum((r.train_no, r.dg_date, s) in rec_keys for s in listed)
    no_dg = int(runs.dg_dep_delay.isna().sum())
    no_mdu = int(runs.mdu_arr_delay.isna().sum())
    missing = {
        "expected_train_days_sept": int(expected), "observed_train_days_sept": observed,
        "missing_train_days": int(expected - observed),
        "missing_share": round((expected - observed) / expected, 3) if expected else None,
        "listed_stop_records_expected": int(exp_rows), "listed_stop_records_present": int(got_rows),
        "runs_without_dg_record": no_dg, "runs_without_mdu_record": no_mdu,
        "runs_with_upstream_record": int((runs.upstream_station.fillna("") != "").sum()),
        "note": "runs_on is DERIVED from the same records (>= half of a weekday's dates), so the "
                "expected count is a lower bound on what was scheduled.",
    }

    # --- delays
    dg = recs[recs.station_code == "DG"]
    mdu = recs[recs.station_code == "MDU"]
    term = set(trains.loc[trains.terminates_at_mdu == "yes", "train_no"])
    both = runs.dropna(subset=["dg_dep_delay", "mdu_arr_delay"])
    suspicious = both[(both.mdu_arr_delay == 0) & (both.dg_dep_delay >= 10)]
    delays = {
        "dg_departure": _dist(dg.dep_delay_min),
        "mdu_arrival": _dist(mdu.arr_delay_min),
        "mdu_arrival_terminating": _dist(mdu[mdu.train_no.isin(term)].arr_delay_min),
        "mdu_arrival_through": _dist(mdu[~mdu.train_no.isin(term)].arr_delay_min),
        "change_dg_to_mdu": _dist(both.mdu_arr_delay - both.dg_dep_delay),
        "early_running_recorded_as_zero": int(((recs.act_arr_min < recs.sched_arr_min) & (recs.ds_arr_delay == 0)).sum()),
        "suspicious_mdu_zero_after_dg_ge_10": {
            "runs": int(len(suspicious)), "of_runs_with_both": int(len(both)),
            "terminating_at_mdu": int(suspicious.train_no.isin(term).sum()),
            "note": "MDU arrival exactly on time although DG departure was >= 10 min late; "
                    "possibly filled with the scheduled time by the source. Flagged, not removed.",
        },
    }

    # --- consistency checks against ASSUMED minimum running times
    mr = dict(zip(zip(secs.from_station, secs.to_station), secs.min_run_min))
    def min_run(a, b):
        i, j = C.ORDER.index(a), C.ORDER.index(b)
        return sum(mr[(C.ORDER[k], C.ORDER[k + 1])] for k in range(i, j))
    fast = total = 0
    for (t, d), g in recs.groupby(["train_no", "dg_date"]):
        g = g.set_index("station_code")
        st = [s for s in C.ORDER if s in g.index]
        for a, b in zip(st, st[1:]):
            total += 1
            if g.loc[b, "act_arr_min"] - g.loc[a, "act_dep_min"] < min_run(a, b):
                fast += 1
    sched_fast = 0
    for tid, g in sched.groupby("train_id"):
        g = g.set_index("station_code")
        def t(s, col, day):
            hh, mm = map(int, str(g.loc[s, col]).split(":"))
            return int(g.loc[s, day]) * 1440 + hh * 60 + mm
        for a, b in zip(C.ORDER, C.ORDER[1:]):
            if t(b, "sched_arr", "arr_day") - t(a, "sched_dep", "dep_day") < mr[(a, b)] - 0.5:
                sched_fast += 1
    checks = {
        "recorded_runs_between_consecutive_recorded_stations": total,
        "recorded_runs_faster_than_assumed_min_run": fast,
        "scheduled_sections_faster_than_assumed_min_run": sched_fast,
        "clock_vs_delay_mismatches": int(recs.clock_mismatch.sum()),
    }

    out = {
        "data_label": C.DATA_LABEL, "corridor": "DG -> MDU", "manifest": manifest,
        "timetable": tt,
        "dataset": {"regular_trains_in_timetable": int(len(trains)),
                    "regular_trains_with_records": len(in_ds),
                    "train_days": int(len(runs)), "dg_dates": len(dg_dates),
                    "first_dg_date": dg_dates[0] if dg_dates else None,
                    "last_dg_date": dg_dates[-1] if dg_dates else None},
        "coverage": cov, "missing": missing, "delays": delays, "checks": checks,
    }
    (out_dir / "audit.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    (out_dir / "audit.md").write_text(render(out), encoding="utf-8")
    return out


def render(a: dict) -> str:
    tt, ds, cov, m, d, ch = a["timetable"], a["dataset"], a["coverage"], a["missing"], a["delays"], a["checks"]
    dgc = a["manifest"]["dg_chainage"]
    L = [
        "# REAL data audit - Dindigul (DG) -> Madurai (MDU)",
        "",
        "Data label: **REAL** (recorded Sept 2024 running data). Generated by "
        "`python -m app.services.realdata.audit` from audit.json; do not edit by hand.",
        f"Source: RSTGCN dataset (CC BY-SA 4.0), zip sha256 `{a['manifest']['source_zip_sha256'][:16]}...`, "
        f"checked {a['manifest']['date_checked']}. DG chainage {dgc['km']} km ({dgc['method']}: {dgc['note']}).",
        "",
        "## Timetable",
        f"- Regular trains DG -> MDU: **{tt['regular_trains']}** "
        f"({', '.join(f'{k} {v}' for k, v in tt['by_type'].items())}).",
        f"- Excluded: {len(tt['excluded'])} special trains (0xxxx): "
        f"{', '.join(str(e['train_no']) for e in tt['excluded'])}.",
        f"- Timetable from the records' scheduled times (route-file times degenerate): "
        f"{', '.join(map(str, tt['timetable_from_records_fallback'])) or 'none'}.",
        f"- Schedule cells: {', '.join(f'{k} {v}' for k, v in tt['cells'].items())}.",
        f"- Passenger/MEMU: {tt['passenger_memu']}.",
        "- Trains per DG weekday (runs_on DERIVED from records): "
        + ", ".join(f"{w} {n}" for w, n in tt["runs_on_weekday_counts"].items()) + ".",
        "",
        "## Dataset coverage",
        f"- Regular trains with records: **{ds['regular_trains_with_records']} of {ds['regular_trains_in_timetable']}**; "
        f"{ds['train_days']} train-days over {ds['dg_dates']} DG dates ({ds['first_dg_date']} .. {ds['last_dg_date']}).",
        "",
        "| Group | Station records | Trains | Days |", "|---|---:|---:|---:|",
    ]
    for g in ("DG", "intermediate", "MDU"):
        L.append(f"| {g} | {cov[g]['station_records']} | {cov[g]['trains']} | {cov[g]['days']} |")
    L += ["", "Per station: " + ", ".join(f"{s} {n}" for s, n in cov["per_station"].items())
          + " (VDP and SER are not a listed stop for any train).", "",
          "## Missing data",
          f"- Train-days in September: expected {m['expected_train_days_sept']}, recorded "
          f"{m['observed_train_days_sept']}, missing **{m['missing_train_days']} ({m['missing_share']:.1%})**. {m['note']}",
          f"- Listed-stop records on recorded days: {m['listed_stop_records_present']} of {m['listed_stop_records_expected']}.",
          f"- Recorded runs without a DG record: {m['runs_without_dg_record']}; without an MDU record: "
          f"{m['runs_without_mdu_record']}; with an upstream (pre-DG) record: {m['runs_with_upstream_record']}.",
          "", "## Observed delays (minutes, signed, recomputed from clock times)", "",
          "| Where | n | mean | median | p75 | p90 | p95 | max | <=0 | >15 | >60 |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k, lab in [("dg_departure", "DG departure"), ("mdu_arrival", "MDU arrival (all)"),
                   ("mdu_arrival_terminating", "MDU arrival, terminating"),
                   ("mdu_arrival_through", "MDU arrival, through"),
                   ("change_dg_to_mdu", "Change DG dep -> MDU arr")]:
        x = d[k]
        if not x["n"]:
            continue
        L.append(f"| {lab} | {x['n']} | {x['mean']} | {x['median']:g} | {x['p75']:g} | {x['p90']:g} | "
                 f"{x['p95']:g} | {x['max']:g} | {x['share_on_time_le_0']:.0%} | {x['share_gt_15']:.0%} | {x['share_gt_60']:.0%} |")
    s = d["suspicious_mdu_zero_after_dg_ge_10"]
    L += ["",
          f"- Histogram DG departure: {d['dg_departure']['histogram']}",
          f"- Histogram MDU arrival: {d['mdu_arrival']['histogram']}",
          f"- Early running recorded by the source as 0 delay: {d['early_running_recorded_as_zero']} records "
          "(signed delays above use the clock times).",
          f"- Flag: {s['runs']} of {s['of_runs_with_both']} runs arrive at MDU exactly on time after leaving DG "
          f">= 10 min late ({s['terminating_at_mdu']} of them terminate at MDU). {s['note']}",
          "", "## Consistency checks",
          f"- Recorded runs between consecutive recorded stations: {ch['recorded_runs_between_consecutive_recorded_stations']}; "
          f"faster than the ASSUMED minimum running time: {ch['recorded_runs_faster_than_assumed_min_run']}.",
          f"- Scheduled sections faster than the ASSUMED minimum running time: {ch['scheduled_sections_faster_than_assumed_min_run']}.",
          f"- Clock time vs dataset delay mismatches: {ch['clock_vs_delay_mismatches']}.", ""]
    return "\n".join(L)


def main() -> None:
    a = audit()
    print(render(a))


if __name__ == "__main__":
    main()
