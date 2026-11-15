"""CLI: Phase 10 evaluation on SIMULATED disruption scenarios.

Usage (from the backend folder):
    python -m eval.run_eval --scenarios 200 --seed 2026

Writes eval/reports/eval_results.csv (one row per scenario x method x setting),
eval_summary.json, eval_report.md (generated from the JSON) and two PNG charts.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from app.services.datagen.generator import TIMETABLE
from app.services.network import load_network
from eval.evaluation import (
    CLOSURE_NOTICE_MIN, METHODS, RAILOPT, REPLAYS, SIMULATED_NOTE, TRAINING_RUNS, TRAINING_SEED,
    evaluate_scenario, fingerprint, make_scenarios, training_fingerprints,
)
from eval.report import summarize, write_charts, write_report, write_summary
from eval.stats import BOOTSTRAP

REPORTS = Path(__file__).resolve().parent / "reports"
METHOD_TEXT = {
    "NO_REPLANNING": "first come, first served at the signals",
    "PRIORITY_DISPATCH": "the waiting train with the highest priority enters first",
    "SINGLE_SHOT": "COMBINED CP-SAT once, when the first disruption becomes known",
    "DYNAMIC": "COMBINED re-solved whenever a new event becomes known, on top of the current plan (started trips fixed, 120-min horizon)",
    "DYNAMIC_ML": "dynamic + ML risk buffers (+1 min headway on trips the conflict model flags)",
}


def run(n: int, seed: int, replays: int = REPLAYS, predictor=None, check_overlap: bool = True,
        progress: bool = False) -> tuple[list[dict], dict]:
    started = time.perf_counter()
    net = load_network(timetable=TIMETABLE)
    if predictor is None:
        from app.services.predictor import get_predictor
        predictor = get_predictor()        # raises if ml/models is missing: run `python -m ml.train`
    scenarios = make_scenarios(n, seed, net)

    overlap = None
    if check_overlap:
        train = training_fingerprints(net)
        overlap = sum(fingerprint(s) in train for s in scenarios)
        if overlap:
            raise SystemExit(f"{overlap} evaluation scenarios also occur in the training data - choose another seed")

    rows, solves, guarantee, ml_differ = [], {m: [] for m in RAILOPT}, [], 0
    for i, s in enumerate(scenarios):
        r, plans = evaluate_scenario(net, s, i, seed, predictor, METHODS, replays)
        rows += r
        by = {p.method: p for p in plans}
        for m in RAILOPT:
            solves[m] += [{**x, "scenario_id": s.run_id} for x in by[m].solves]
        guarantee.append({**by["SINGLE_SHOT"].guarantee, "scenario_id": s.run_id})
        ml_differ += (by["DYNAMIC_ML"].holds, by["DYNAMIC_ML"].overrides) != (by["DYNAMIC"].holds, by["DYNAMIC"].overrides)
        if progress and (i + 1) % 20 == 0:
            print(f"  {i + 1}/{n} scenarios, {time.perf_counter() - started:.0f} s", flush=True)

    types = Counter(d.event_type for s in scenarios for d in s.disruptions)
    config = {"scenarios": n, "seed": seed, "timetable": TIMETABLE, "replays": replays, "bootstrap": BOOTSTRAP,
              "closure_notice_min": CLOSURE_NOTICE_MIN, "methods": METHOD_TEXT}
    info = {"solves": solves, "guarantee": guarantee, "ml_plans_differ": ml_differ,
            "scenarios": {"trains": len(net.schedules), "training_runs": TRAINING_RUNS, "training_seed": TRAINING_SEED,
                          "overlap_with_training": overlap,
                          "disruptions_total": sum(types.values()),
                          "per_scenario": dict(sorted(Counter(len(s.disruptions) for s in scenarios).items())),
                          "types": dict(sorted(types.items()))}}
    summary = summarize(rows, info, config)
    summary["violations"] = 0                                   # evaluate_scenario asserts on every replay
    summary["replays_checked"] = n * len(METHODS) * (1 + replays)
    summary["runtime_s"] = time.perf_counter() - started
    return rows, summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Phase 10 evaluation (SIMULATED).")
    ap.add_argument("--scenarios", type=int, default=200)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--replays", type=int, default=REPLAYS)
    ap.add_argument("--out", type=Path, default=REPORTS)
    a = ap.parse_args(argv)
    if a.seed == TRAINING_SEED:
        raise SystemExit(f"seed {TRAINING_SEED} is the training seed - use another one")

    print(f"=== {SIMULATED_NOTE} ===\nevaluating {a.scenarios} scenarios, seed {a.seed}, {a.replays} replays ...", flush=True)
    rows, summary = run(a.scenarios, a.seed, a.replays, progress=True)
    a.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(a.out / "eval_results.csv", index=False)
    write_summary(summary, a.out / "eval_summary.json")
    summary = json.loads((a.out / "eval_summary.json").read_text(encoding="utf-8"))   # the report reads the JSON
    write_report(summary, a.out / "eval_report.md")
    write_charts(summary, rows, a.out)
    print(f"done in {summary['runtime_s']:.0f} s; wrote {a.out}")
    for setting in ("deterministic", "robustness"):
        print(f"\n[{setting}] weighted delay per scenario: mean [95% CI]")
        for m in METHODS:
            v = summary["settings"][setting]["methods"][m]["weighted_delay"]
            p = summary["settings"][setting]["paired_vs_no_replanning"].get(m, {}).get("weighted_delay")
            vs = "" if p is None else (f"  vs no re-planning W/T/L {p['wins']}/{p['ties']}/{p['losses']}, "
                                       f"diff {p['mean_diff']:.1f} [{p['mean_diff_ci'][0]:.1f}, {p['mean_diff_ci'][1]:.1f}]"
                                       f"{'' if p['significant'] else ' NOT significant'}")
            print(f"  {m:<18} {v['mean']:7.1f} [{v['mean_ci'][0]:.1f}, {v['mean_ci'][1]:.1f}]{vs}")


if __name__ == "__main__":
    main()
