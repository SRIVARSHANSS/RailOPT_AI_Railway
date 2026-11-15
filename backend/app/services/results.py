"""Stored results for the Analytics and Model Insights pages (read-only, no new computation).

Reads eval/reports/eval_summary.json (+ eval_results.csv) and ml/reports/metrics.json
(+ feature_importance.csv) and checks they still match the files they were computed from,
like tests/test_ml.py: if the results CSV or the model files changed since the run, the
status is "outdated" and the page asks for a rerun. All data SIMULATED.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
EVAL_DIR = BACKEND / "eval" / "reports"
ML_REPORTS = BACKEND / "ml" / "reports"
MODEL_DIR = BACKEND / "ml" / "models"
DATASET = BACKEND / "data" / "generated" / "training_rows.csv"
MODEL_FILES = ("preprocess.joblib", "delay_model.joblib", "conflict_model.joblib")
EVAL_COMMAND = "python -m eval.run_eval --scenarios 200 --seed 2026"
TRAIN_COMMAND = "python -m ml.train"
PHASE10 = ["NO_REPLANNING", "PRIORITY_DISPATCH", "SINGLE_SHOT", "DYNAMIC", "DYNAMIC_ML"]
PREREGISTERED_10B = ["DYNAMIC_ML_B2", "DYNAMIC_ML_B3", "DYNAMIC_ML_PROP", "DYNAMIC_ML_TRIGGER"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _model_problems(expected: dict[str, str], model_dir: Path) -> list[str]:
    out = []
    for name in MODEL_FILES:
        path = model_dir / name
        if not path.exists():
            out.append(f"model file {name} is missing")
        elif expected.get(name) != sha256(path):
            out.append(f"model file {name} changed since these results were computed")
    return out


# ---------------------------------------------------------------------------
# evaluation (Phase 10 / 10b)
# ---------------------------------------------------------------------------
def _quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def reduction_distribution(rows: list[dict], methods: list[str], bins: int = 14) -> dict:
    """Per-scenario weighted delay saved vs no re-planning, summarised for a chart
    (quartiles, Tukey whiskers, histogram). Reads stored rows; computes nothing new."""
    out = {}
    for setting in ("deterministic", "robustness"):
        by = {}
        for r in rows:
            if r["setting"] == setting:
                by.setdefault(r["method"], {})[int(r["scenario_index"])] = float(r["weighted_delay"])
        base = by.get("NO_REPLANNING", {})
        series = {m: [base[i] - v for i, v in sorted(by[m].items()) if i in base] for m in methods if m in by}
        values = [x for xs in series.values() for x in xs]
        if not values:
            continue
        lo, hi = min(values), max(values)
        width = (hi - lo) / bins or 1.0
        edges = [lo + k * width for k in range(bins + 1)]
        setting_out = {"edges": edges, "methods": {}}
        for m, xs in series.items():
            q1, med, q3 = _quantile(xs, 0.25), _quantile(xs, 0.5), _quantile(xs, 0.75)
            iqr = q3 - q1
            counts = [0] * bins
            for x in xs:
                counts[min(bins - 1, int((x - lo) / width))] += 1
            setting_out["methods"][m] = {
                "n": len(xs), "mean": sum(xs) / len(xs), "q1": q1, "median": med, "q3": q3,
                "whisker_low": min(x for x in xs if x >= q1 - 1.5 * iqr),
                "whisker_high": max(x for x in xs if x <= q3 + 1.5 * iqr),
                "min": min(xs), "max": max(xs),
                "improved": sum(x > 0 for x in xs), "unchanged": sum(x == 0 for x in xs), "worse": sum(x < 0 for x in xs),
                "histogram": counts,
            }
        out[setting] = setting_out
    return out


def ml_conclusion(summary: dict) -> dict | None:
    """The plain finding about feeding ML risk into the optimizer, derived from the summary."""
    det = summary.get("settings", {}).get("deterministic", {}).get("variants_vs_dynamic")
    if not det:
        return None
    variants = list(det)
    better = [m for m in variants for st in ("deterministic", "robustness")
              if summary["settings"][st]["variants_vs_dynamic"][m]["weighted_delay"]["significant"]
              and summary["settings"][st]["variants_vs_dynamic"][m]["weighted_delay"]["mean_diff"] < 0]
    worse = sorted({m for m in variants for st in ("deterministic", "robustness")
                    if summary["settings"][st]["variants_vs_dynamic"][m]["weighted_delay"]["significant"]
                    and summary["settings"][st]["variants_vs_dynamic"][m]["weighted_delay"]["mean_diff"] > 0})
    pre = [m for m in variants if m in PREREGISTERED_10B]
    others = len(variants) - len(pre)
    origin = f"{len(pre)} pre-registered in Phase 10b" + (" + the Phase 10 ablation" if others == 1 else
                                                         f" + {others} from Phase 10" if others else "")
    if better:
        text = (f"ML provides early warning; feeding its risk into the optimizer improved plans in "
                f"{len(set(better))} of {len(variants)} variants ({origin}).")
    else:
        text = (f"ML provides early warning; feeding its risk into the optimizer did not improve plans in "
                f"{len(variants)} variants ({origin}).")
    return {"text": text, "variants": variants, "preregistered": pre, "improved": sorted(set(better)),
            "significantly_worse": worse, "reference": "DYNAMIC"}


def evaluation_view(eval_dir: Path = EVAL_DIR, model_dir: Path = MODEL_DIR) -> dict:
    summary_path, csv_path = eval_dir / "eval_summary.json", eval_dir / "eval_results.csv"
    if not summary_path.exists():
        return {"status": "missing", "reasons": ["eval_summary.json not found"], "command": EVAL_COMMAND,
                "summary": None, "distribution": None, "conclusion": None, "solver_totals": None}
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    reasons = []
    prov = summary.get("provenance")
    if not prov:
        reasons.append("the summary has no provenance hashes (written by an older run)")
    else:
        if not csv_path.exists():
            reasons.append("eval_results.csv is missing")
        elif sha256(csv_path) != prov["results_csv_sha256"]:
            reasons.append("eval_results.csv changed since the summary was written")
        reasons += _model_problems(prov.get("models_sha256", {}), model_dir)
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8"))) if csv_path.exists() else []
    methods = [m for m in summary["settings"]["deterministic"]["methods"] if m != "NO_REPLANNING"]
    solver = summary.get("solver", {})

    def total(ms):
        xs = [solver[m] for m in ms if m in solver]
        return {"solves": sum(x["solves"] for x in xs), "optimal": sum(x["optimal"] for x in xs),
                "feasible": sum(x["feasible"] for x in xs),
                "solve_s_mean": (sum(x["solve_s_mean"] * x["solves"] for x in xs) / max(1, sum(x["solves"] for x in xs))),
                "solve_s_max": max((x["solve_s_max"] for x in xs), default=0.0)}

    return {"status": "outdated" if reasons else "ok", "reasons": reasons, "command": EVAL_COMMAND,
            "summary": summary, "distribution": reduction_distribution(rows, methods) if rows else None,
            "conclusion": ml_conclusion(summary),
            "solver_totals": {"phase10": total([m for m in PHASE10 if m in solver]),
                              "variants_10b": total([m for m in PREREGISTERED_10B if m in solver])}}


# ---------------------------------------------------------------------------
# models (Phase 4)
# ---------------------------------------------------------------------------
def model_view(reports: Path = ML_REPORTS, model_dir: Path = MODEL_DIR, dataset: Path = DATASET,
               eval_dir: Path = EVAL_DIR) -> dict:
    metrics_path, fi_path = reports / "metrics.json", reports / "feature_importance.csv"
    if not metrics_path.exists():
        return {"status": "missing", "reasons": ["metrics.json not found"], "command": TRAIN_COMMAND,
                "metrics": None, "feature_importance": [], "dataset_check": None, "evaluation": None}
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    hashes = metrics.get("hashes", {})
    reasons = _model_problems(hashes.get("models_sha256", {}), model_dir)
    if not dataset.exists():
        dataset_check = "not present locally (gitignored); model files checked instead"
    elif sha256(dataset) != hashes.get("dataset_sha256"):
        dataset_check = "changed"
        reasons.append("training_rows.csv changed since the models were trained")
    else:
        dataset_check = "verified"
    fi = []
    if fi_path.exists():
        fi = [{"model": r["model"], "feature": r["feature"], "mean_abs_shap": float(r["mean_abs_shap"])}
              for r in csv.DictReader(open(fi_path, encoding="utf-8"))]
    else:
        reasons.append("feature_importance.csv is missing")
    ev = evaluation_view(eval_dir, model_dir)
    evaluation = None
    if ev["summary"]:
        evaluation = {"status": ev["status"], "conclusion": ev["conclusion"],
                      "settings": {st: {"variants_vs_dynamic": ev["summary"]["settings"][st].get("variants_vs_dynamic", {}),
                                        "methods": {m: ev["summary"]["settings"][st]["methods"][m]["weighted_delay"]
                                                    for m in ev["summary"]["settings"][st]["methods"]}}
                                   for st in ("deterministic", "robustness")}}
    return {"status": "outdated" if reasons else "ok", "reasons": reasons, "command": TRAIN_COMMAND,
            "metrics": metrics, "feature_importance": fi, "dataset_check": dataset_check, "evaluation": evaluation}
