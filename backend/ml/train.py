"""Train the delay and conflict models on SIMULATED data (Phase 4).

Usage (from the backend folder):
    python -m ml.train                      # data/generated/training_rows.csv
    python -m ml.train --csv other.csv --n-iter 10

Order of work (the test split is touched once, at the very end):
1. split by run_id in run order: 70 % train, 15 % validation, 15 % test
2. fit the shared preprocessor on train only
3. baselines and models, tuned with a fixed random search on validation
4. pick the best model and decision thresholds on validation
5. ablation (best conflict model without rule_flags_conflict), on validation
6. score everything on test, once
7. SHAP global importance (validation rows), save models, metrics.json,
   feature_importance.csv and model_card.md (numbers come from metrics.json)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_curve,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.model_selection import ParameterSampler
from xgboost import XGBClassifier, XGBRegressor

from app.services.datagen.generator import FEATURES, SIMULATED_NOTE
from ml.explain import global_importance, make_explainer, shap_matrix
from ml.features import GAP_CAP_MIN, Preprocessor, load_rows, split_by_run

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_CSV = BACKEND / "data" / "generated" / "training_rows.csv"
DEFAULT_MODEL_DIR = BACKEND / "ml" / "models"
DEFAULT_REPORT_DIR = BACKEND / "ml" / "reports"

MIN_RECALL = 0.80
DELAY_LABEL, CONFLICT_LABEL = "label_delay_min", "label_conflict"
RULE_FEATURE = "rule_flags_conflict"

SEARCH = {
    "rf_reg": {"n_estimators": [100, 200], "max_depth": [8, 12, 16, None],
               "min_samples_leaf": [1, 3, 10], "max_features": ["sqrt", 0.5, 1.0]},
    "xgb_reg": {"n_estimators": [200, 400, 600], "max_depth": [3, 4, 6, 8],
                "learning_rate": [0.03, 0.05, 0.1], "subsample": [0.7, 0.9, 1.0],
                "colsample_bytree": [0.7, 0.9, 1.0], "min_child_weight": [1, 5]},
    "rf_clf": {"n_estimators": [100, 200], "max_depth": [8, 12, 16, None],
               "min_samples_leaf": [1, 3, 10], "max_features": ["sqrt", 0.5, 1.0]},
    "xgb_clf": {"n_estimators": [200, 400, 600], "max_depth": [3, 4, 6, 8],
                "learning_rate": [0.03, 0.05, 0.1], "subsample": [0.7, 0.9, 1.0],
                "colsample_bytree": [0.7, 0.9, 1.0], "min_child_weight": [1, 5]},
}


# ---------------------------------------------------------------------------
# model factories
# ---------------------------------------------------------------------------
def make_model(kind: str, params: dict, seed: int, pos_weight: float = 1.0):
    if kind == "rf_reg":
        return RandomForestRegressor(random_state=seed, n_jobs=-1, **params)
    if kind == "xgb_reg":
        return XGBRegressor(random_state=seed, n_jobs=-1, tree_method="hist", **params)
    if kind == "rf_clf":
        return RandomForestClassifier(random_state=seed, n_jobs=-1, class_weight="balanced", **params)
    if kind == "xgb_clf":
        return XGBClassifier(random_state=seed, n_jobs=-1, tree_method="hist", eval_metric="aucpr",
                             scale_pos_weight=pos_weight, **params)
    raise ValueError(kind)


def fit_model(kind: str, params: dict, seed: int, X, y, pos_weight: float = 1.0):
    """Fit in parallel, then predict single-threaded.

    A random forest with n_jobs > 1 sums its trees' predictions in thread
    completion order, which changes results in the last bits between runs.
    Prediction with n_jobs=1 makes metrics exactly reproducible.
    """
    model = make_model(kind, params, seed, pos_weight).fit(X, y)
    if kind.startswith("rf"):
        model.set_params(n_jobs=1)
    return model


MODEL_NAMES = {"rf_reg": "random_forest", "xgb_reg": "xgboost",
               "rf_clf": "random_forest", "xgb_clf": "xgboost"}


# ---------------------------------------------------------------------------
# metrics and thresholds
# ---------------------------------------------------------------------------
def reg_metrics(y, pred) -> dict:
    return {"mae": float(mean_absolute_error(y, pred)),
            "rmse": float(np.sqrt(mean_squared_error(y, pred))),
            "r2": float(r2_score(y, pred))}


def clf_metrics(y, score, threshold: float | None) -> dict:
    """threshold=None: `score` is already a 0/1 prediction (the rule baseline)."""
    pred = np.asarray(score) >= threshold if threshold is not None else np.asarray(score).astype(bool)
    return {"precision": float(precision_score(y, pred, zero_division=0)),
            "recall": float(recall_score(y, pred, zero_division=0)),
            "f1": float(f1_score(y, pred, zero_division=0)),
            "pr_auc": float(average_precision_score(y, score)),
            "threshold": threshold}


def threshold_for_recall(y, proba, min_recall: float = MIN_RECALL) -> float:
    """Best precision among thresholds with recall >= min_recall (ties: higher threshold)."""
    prec, rec, thr = precision_recall_curve(y, proba)
    prec, rec = prec[:-1], rec[:-1]
    ok = np.flatnonzero(rec >= min_recall)
    best = ok[np.lexsort((thr[ok], prec[ok]))[-1]]
    return float(thr[best])


def threshold_at_precision(y, proba, min_precision: float) -> float | None:
    """Best recall among thresholds with precision >= min_precision (ties: higher threshold)."""
    prec, rec, thr = precision_recall_curve(y, proba)
    prec, rec = prec[:-1], rec[:-1]
    ok = np.flatnonzero(prec >= min_precision)
    if ok.size == 0:
        return None
    best = ok[np.lexsort((thr[ok], rec[ok]))[-1]]
    return float(thr[best])


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------
def search(kind, Xtr, ytr, Xva, yva, n_iter, seed, pos_weight=1.0):
    """Fixed random search on validation. Returns (best_params, best_model, best_val_score, tried)."""
    is_clf = kind.endswith("clf")
    best = None
    tried = 0
    for params in ParameterSampler(SEARCH[kind], n_iter=n_iter, random_state=seed):
        model = fit_model(kind, params, seed, Xtr, ytr, pos_weight)
        if is_clf:
            score = average_precision_score(yva, model.predict_proba(Xva)[:, 1])      # higher is better
        else:
            score = -mean_absolute_error(yva, model.predict(Xva))                   # lower MAE is better
        tried += 1
        if best is None or score > best[2]:
            best = (params, model, score)
    return best[0], best[1], best[2], tried


def _clean(params: dict) -> dict:
    return {k: (v if not isinstance(v, np.generic) else v.item()) for k, v in params.items()}


# ---------------------------------------------------------------------------
# main training routine
# ---------------------------------------------------------------------------
def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


MODEL_FILES = ("preprocess.joblib", "delay_model.joblib", "conflict_model.joblib")
SMALL_CHECK_RUNS, SMALL_CHECK_N_ITER = 300, 3


def small_data_check(seed: int, runs: int = SMALL_CHECK_RUNS, n_iter: int = SMALL_CHECK_N_ITER) -> dict:
    """Head-to-head with the rule on a small dataset with minimal tuning (report only).

    Same generator and seed, so these are the first `runs` runs of the full dataset.
    """
    from app.services.datagen import generate

    with tempfile.TemporaryDirectory() as tmp:
        csv = Path(tmp) / "rows_small.csv"
        generate(runs, seed).to_csv(csv, index=False)
        m = train(csv, Path(tmp) / "models", Path(tmp) / "reports", seed=seed, n_iter=n_iter, verbose=False)
    eq = m["conflict"]["operating_points"]["equal_to_rule_precision"]
    return {"runs": runs, "n_iter_per_model": n_iter, "best_model": m["conflict"]["best_model"],
            "rule_val_precision": eq["rule_val_precision"], "rule_val_recall": eq["rule_val_recall"],
            "model_val_recall_at_rule_precision": eq["val"]["recall"] if eq["val"] else None}


def train(csv_path=DEFAULT_CSV, model_dir=DEFAULT_MODEL_DIR, report_dir=DEFAULT_REPORT_DIR,
          seed: int = 42, n_iter: int = 20, shap_rows: int = 2000, verbose: bool = True,
          small_check: bool = False) -> dict:
    """small_check: also run `small_data_check` and record it (the CLI does this)."""
    started = time.perf_counter()
    log = print if verbose else (lambda *a, **k: None)
    model_dir, report_dir = Path(model_dir), Path(report_dir)

    df = load_rows(csv_path)
    split = split_by_run(df)
    tr, va, te = split.train, split.val, split.test
    log(f"rows train/val/test: {len(tr)}/{len(va)}/{len(te)}")

    pre = Preprocessor(FEATURES).fit(tr)
    Xtr, Xva = pre.transform(tr), pre.transform(va)

    # ---- Task A: delay regression (validation only) -------------------------
    ytr_d, yva_d = tr[DELAY_LABEL].to_numpy(), va[DELAY_LABEL].to_numpy()
    linreg = LinearRegression().fit(Xtr, ytr_d)
    delay_models = {}
    for kind in ("rf_reg", "xgb_reg"):
        params, model, _score, tried = search(kind, Xtr, ytr_d, Xva, yva_d, n_iter, seed)
        delay_models[MODEL_NAMES[kind]] = {"kind": kind, "params": _clean(params), "model": model,
                                           "configs_tried": tried}
        log(f"delay {MODEL_NAMES[kind]}: {tried} configs, best {_clean(params)}")
    for m in delay_models.values():
        m["val"] = reg_metrics(yva_d, m["model"].predict(Xva))
    best_delay = min(delay_models, key=lambda n: delay_models[n]["val"]["mae"])

    # ---- Task B: conflict classification (validation only) ------------------
    ytr_c, yva_c = tr[CONFLICT_LABEL].to_numpy(), va[CONFLICT_LABEL].to_numpy()
    pos_weight = float((ytr_c == 0).sum() / max(1, (ytr_c == 1).sum()))
    rule_val = clf_metrics(yva_c, va[RULE_FEATURE].to_numpy(), None)

    logreg = LogisticRegression(max_iter=2000, class_weight="balanced").fit(Xtr, ytr_c)
    logreg_thr = threshold_for_recall(yva_c, logreg.predict_proba(Xva)[:, 1])

    conflict_models = {}
    for kind in ("rf_clf", "xgb_clf"):
        params, model, _score, tried = search(kind, Xtr, ytr_c, Xva, yva_c, n_iter, seed, pos_weight)
        proba = model.predict_proba(Xva)[:, 1]
        thr = threshold_for_recall(yva_c, proba)
        conflict_models[MODEL_NAMES[kind]] = {"kind": kind, "params": _clean(params), "model": model,
                                              "configs_tried": tried, "threshold": thr,
                                              "val": clf_metrics(yva_c, proba, thr)}
        log(f"conflict {MODEL_NAMES[kind]}: {tried} configs, best {_clean(params)}")
    best_conflict = max(conflict_models, key=lambda n: conflict_models[n]["val"]["pr_auc"])
    best = conflict_models[best_conflict]
    best_val_proba = best["model"].predict_proba(Xva)[:, 1]
    eq_thr = threshold_at_precision(yva_c, best_val_proba, rule_val["precision"])

    # ablation: same model type and params, without the rule feature
    no_rule = [f for f in FEATURES if f != RULE_FEATURE]
    pre_nr = Preprocessor(no_rule).fit(tr)
    Xtr_nr, Xva_nr = pre_nr.transform(tr), pre_nr.transform(va)
    model_nr = fit_model(best["kind"], best["params"], seed, Xtr_nr, ytr_c, pos_weight)
    proba_nr = model_nr.predict_proba(Xva_nr)[:, 1]
    thr_nr = threshold_for_recall(yva_c, proba_nr)
    eq_thr_nr = threshold_at_precision(yva_c, proba_nr, rule_val["precision"])

    # ---- TEST: touched once, here ----------------------------------------------
    Xte, Xte_nr = pre.transform(te), pre_nr.transform(te)
    yte_d, yte_c = te[DELAY_LABEL].to_numpy(), te[CONFLICT_LABEL].to_numpy()

    delay = {
        "label": DELAY_LABEL,
        "baselines": {
            "carry_known_delay": {"val": reg_metrics(yva_d, va["current_delay_min"]),
                                  "test": reg_metrics(yte_d, te["current_delay_min"])},
            "deterministic_projection": {"val": reg_metrics(yva_d, va["baseline_projected_delay_min"]),
                                         "test": reg_metrics(yte_d, te["baseline_projected_delay_min"])},
            "linear_regression": {"val": reg_metrics(yva_d, linreg.predict(Xva)),
                                  "test": reg_metrics(yte_d, linreg.predict(Xte))},
        },
        "models": {name: {"params": m["params"], "configs_tried": m["configs_tried"], "val": m["val"],
                          "test": reg_metrics(yte_d, m["model"].predict(Xte))}
                   for name, m in delay_models.items()},
        "best_model": best_delay,
        "selected_by": "lowest validation MAE",
    }

    best_test_proba = best["model"].predict_proba(Xte)[:, 1]
    proba_nr_test = model_nr.predict_proba(Xte_nr)[:, 1]
    rule_test = clf_metrics(yte_c, te[RULE_FEATURE].to_numpy(), None)

    def op(y_val, p_val, y_test, p_test, thr):
        if thr is None:
            return {"threshold": None, "val": None, "test": None,
                    "note": "no threshold reaches the rule's validation precision"}
        return {"threshold": thr, "val": clf_metrics(y_val, p_val, thr), "test": clf_metrics(y_test, p_test, thr)}

    conflict = {
        "label": CONFLICT_LABEL,
        "positive_rate": {"train": float(ytr_c.mean()), "val": float(yva_c.mean()), "test": float(yte_c.mean())},
        "baselines": {
            "rule_flags_conflict": {"val": rule_val, "test": rule_test},
            "logistic_regression": {"threshold": logreg_thr,
                                    "val": clf_metrics(yva_c, logreg.predict_proba(Xva)[:, 1], logreg_thr),
                                    "test": clf_metrics(yte_c, logreg.predict_proba(Xte)[:, 1], logreg_thr)},
        },
        "models": {name: {"params": m["params"], "configs_tried": m["configs_tried"],
                          "threshold": m["threshold"], "val": m["val"],
                          "test": clf_metrics(yte_c, m["model"].predict_proba(Xte)[:, 1], m["threshold"])}
                   for name, m in conflict_models.items()},
        "best_model": best_conflict,
        "selected_by": "highest validation PR-AUC",
        "operating_points": {
            "recall_at_least_0.80": {
                "rule": f"best validation precision subject to validation recall >= {MIN_RECALL}",
                **op(yva_c, best_val_proba, yte_c, best_test_proba, best["threshold"])},
            "equal_to_rule_precision": {
                "rule": "best validation recall subject to validation precision >= the rule's validation precision",
                "rule_val_precision": rule_val["precision"], "rule_val_recall": rule_val["recall"],
                **op(yva_c, best_val_proba, yte_c, best_test_proba, eq_thr)},
        },
        "ablation": {
            "model": best_conflict,
            "params": best["params"],
            "with_rule_flag": {
                "recall_at_least_0.80": op(yva_c, best_val_proba, yte_c, best_test_proba, best["threshold"]),
                "equal_to_rule_precision": op(yva_c, best_val_proba, yte_c, best_test_proba, eq_thr)},
            "without_rule_flag": {
                "recall_at_least_0.80": op(yva_c, proba_nr, yte_c, proba_nr_test, thr_nr),
                "equal_to_rule_precision": op(yva_c, proba_nr, yte_c, proba_nr_test, eq_thr_nr)},
        },
    }

    # ---- SHAP global importance on validation rows ------------------------------
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(va), size=min(shap_rows, len(va)), replace=False)
    importance = {}
    for task, model in (("delay", delay_models[best_delay]["model"]), ("conflict", best["model"])):
        values = shap_matrix(make_explainer(model), Xva[idx])
        importance[task] = global_importance(values, pre.source)

    # ---- save --------------------------------------------------------------------
    model_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pre, model_dir / "preprocess.joblib")
    joblib.dump({"model": delay_models[best_delay]["model"], "name": best_delay,
                 "params": delay_models[best_delay]["params"]}, model_dir / "delay_model.joblib")
    joblib.dump({"model": best["model"], "name": best_conflict, "params": best["params"],
                 "threshold": best["threshold"], "threshold_equal_rule_precision": eq_thr},
                model_dir / "conflict_model.joblib")

    rows = [{"model": task, "feature": f, "mean_abs_shap": float(v)}
            for task, series in importance.items() for f, v in series.items()]
    import pandas as pd  # local import keeps the module header short
    pd.DataFrame(rows).to_csv(report_dir / "feature_importance.csv", index=False)

    metrics = {
        "note": SIMULATED_NOTE,
        "data": {"csv": Path(csv_path).name, "rows": int(len(df)), "runs": int(df["run_id"].nunique()),
                 "runs_generated": int(df["run_id"].str[1:].astype(int).max()),
                 "split": {name: {"runs": int(part["run_id"].nunique()), "rows": int(len(part)),
                                  "first_run": str(part["run_id"].min()), "last_run": str(part["run_id"].max())}
                           for name, part in (("train", tr), ("val", va), ("test", te))},
                 "split_method": "by run_id in run order: first 70 % train, next 15 % validation, last 15 % test"},
        "seed": seed,
        "n_iter_per_model": n_iter,
        "features": FEATURES,
        "preprocessing": f"one-hot categoricals, headway_gap_min capped at {GAP_CAP_MIN} then scaled, "
                         "numerics scaled; fitted on train only",
        "final_models_trained_on": "train split only",
        "delay": delay,
        "conflict": conflict,
        "shap_global_importance": {task: {f: float(v) for f, v in s.items()} for task, s in importance.items()},
        "shap_rows": int(len(idx)),
        "training_seconds": round(time.perf_counter() - started, 1),
        # tie these numbers to the exact files: tests refuse stale metrics
        "hashes": {"dataset_sha256": sha256_file(csv_path),
                   "models_sha256": {f: sha256_file(model_dir / f) for f in MODEL_FILES}},
    }
    if small_check:
        log(f"small-data check: {SMALL_CHECK_RUNS} runs, {SMALL_CHECK_N_ITER} configs per model ...")
        metrics["small_data_check"] = small_data_check(seed)
    (report_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (report_dir / "model_card.md").write_text(render_model_card(metrics), encoding="utf-8")
    log(f"done in {metrics['training_seconds']} s")
    return metrics


# ---------------------------------------------------------------------------
# model card (every number read from the metrics dict)
# ---------------------------------------------------------------------------
def _f(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def render_model_card(m: dict) -> str:
    d, c = m["delay"], m["conflict"]
    sp = m["data"]["split"]
    out = [
        "# RailOpt AI - model card (Phase 4)",
        "",
        f"**{m['note']}.** These models are trained and evaluated only on simulated runs of the",
        "sample corridor. Nothing here is a measurement of real Indian Railways operations.",
        "All numbers below are generated from `metrics.json` (shown to 3 decimals).",
        "",
        "## Data and split",
        f"- {m['data']['rows']} rows from {m['data']['runs']} simulated runs (`{m['data']['csv']}`), seed {m['seed']}"
        f" ({m['data']['runs_generated']} runs generated; runs where every train had already entered its"
        f" sections at state time give no rows).",
        f"- Dataset SHA-256 `{m['hashes']['dataset_sha256']}`; model files hashed in `metrics.json`.",
        f"- Split: {m['data']['split_method']}. No run appears in two splits.",
    ]
    for name in ("train", "val", "test"):
        s = sp[name]
        out.append(f"  - {name}: {s['runs']} runs ({s['first_run']}-{s['last_run']}), {s['rows']} rows")
    out += [
        f"- Preprocessing: {m['preprocessing']}.",
        f"- Tuning: fixed random search, at most {m['n_iter_per_model']} configurations per model, "
        "scored on validation only. The test split was scored once, after all choices were made.",
        f"- Final models trained on: {m['final_models_trained_on']}. Training time: {m['training_seconds']} s.",
        "",
        "## Delay at destination (`label_delay_min`, minutes)",
        f"Best model: **{d['best_model']}** ({d['selected_by']}).",
        "",
        "| Method | Kind | Val MAE | Val RMSE | Val R2 | Test MAE | Test RMSE | Test R2 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, r in d["baselines"].items():
        out.append(f"| {name} | baseline | {_f(r['val']['mae'])} | {_f(r['val']['rmse'])} | {_f(r['val']['r2'])} "
                   f"| {_f(r['test']['mae'])} | {_f(r['test']['rmse'])} | {_f(r['test']['r2'])} |")
    for name, r in d["models"].items():
        out.append(f"| {name} | model | {_f(r['val']['mae'])} | {_f(r['val']['rmse'])} | {_f(r['val']['r2'])} "
                   f"| {_f(r['test']['mae'])} | {_f(r['test']['rmse'])} | {_f(r['test']['r2'])} |")
    out += [
        "",
        "`deterministic_projection` is the existing simulator run with no randomness on the events",
        "known at state time: what the rules plus the simulator predict without ML.",
        "",
        "## Conflict before the section (`label_conflict`)",
        f"Positive rate: train {_f(c['positive_rate']['train'])}, val {_f(c['positive_rate']['val'])}, "
        f"test {_f(c['positive_rate']['test'])}. Best model: **{c['best_model']}** ({c['selected_by']}).",
        "Each model's threshold: best validation precision with validation recall >= 0.80.",
        "",
        "| Method | Kind | Threshold | Val P | Val R | Val F1 | Val PR-AUC | Test P | Test R | Test F1 | Test PR-AUC |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    def row(name, kind, r):
        v, t = r["val"], r["test"]
        return (f"| {name} | {kind} | {_f(r.get('threshold'))} | {_f(v['precision'])} | {_f(v['recall'])} "
                f"| {_f(v['f1'])} | {_f(v['pr_auc'])} | {_f(t['precision'])} | {_f(t['recall'])} "
                f"| {_f(t['f1'])} | {_f(t['pr_auc'])} |")

    for name, r in c["baselines"].items():
        out.append(row(name, "baseline", r))
    for name, r in c["models"].items():
        out.append(row(name, "model", r))
    out += [
        "",
        "The rule baseline is a 0/1 flag, so its PR-AUC is the average precision of that flag.",
        "",
        f"### Operating points of the deployed model ({c['best_model']})",
        "",
        "| Operating point | Threshold | Val P | Val R | Val F1 | Test P | Test R | Test F1 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, o in c["operating_points"].items():
        if o["val"] is None:
            out.append(f"| {name} | n/a | {o['note']} | | | | | |")
            continue
        out.append(f"| {name} | {_f(o['threshold'])} | {_f(o['val']['precision'])} | {_f(o['val']['recall'])} "
                   f"| {_f(o['val']['f1'])} | {_f(o['test']['precision'])} | {_f(o['test']['recall'])} "
                   f"| {_f(o['test']['f1'])} |")
    eq = c["operating_points"]["equal_to_rule_precision"]
    rule = c["baselines"]["rule_flags_conflict"]
    out += [
        "",
        f"- `recall_at_least_0.80` is the threshold the predictor uses (a missed conflict is the costly error).",
        f"- `equal_to_rule_precision` is the head-to-head with the rule: at the rule's validation precision "
        f"({_f(eq['rule_val_precision'])}), the rule's validation recall is {_f(eq['rule_val_recall'])} and the "
        f"model's is {_f(eq['val']['recall'] if eq['val'] else None)}. On test the rule has precision "
        f"{_f(rule['test']['precision'])} / recall {_f(rule['test']['recall'])}; the model at this threshold has "
        f"{_f(eq['test']['precision'] if eq['test'] else None)} / {_f(eq['test']['recall'] if eq['test'] else None)}.",
    ]
    small = m.get("small_data_check")
    if small:
        share = small["runs"] / m["data"]["runs_generated"] if m["data"].get("runs_generated") else None
        pct = f"{share:.0%}" if share else f"{small['runs']} runs"
        mr, rr = small["model_val_recall_at_rule_precision"], small["rule_val_recall"]
        if mr is not None and mr > rr:
            out.append(f"- With {pct} of the data and minimal tuning the model also beat the rule "
                       f"(recall {_f(mr)} vs {_f(rr)}).")
        else:
            out.append(f"- With {pct} of the data and minimal tuning the model did not beat the rule "
                       f"(recall {_f(mr)} vs {_f(rr)}), so the result depends on data volume.")
    out += [
        "",
        f"### Ablation: {c['ablation']['model']} with and without `rule_flags_conflict` (same parameters)",
        "",
        "| Variant | Operating point | Threshold | Val P | Val R | Val F1 | Val PR-AUC | Test P | Test R | Test F1 | Test PR-AUC |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for variant in ("with_rule_flag", "without_rule_flag"):
        for name, o in c["ablation"][variant].items():
            if o["val"] is None:
                out.append(f"| {variant} | {name} | n/a | {o['note']} | | | | | | | |")
                continue
            v, t = o["val"], o["test"]
            out.append(f"| {variant} | {name} | {_f(o['threshold'])} | {_f(v['precision'])} | {_f(v['recall'])} "
                       f"| {_f(v['f1'])} | {_f(v['pr_auc'])} | {_f(t['precision'])} | {_f(t['recall'])} "
                       f"| {_f(t['f1'])} | {_f(t['pr_auc'])} |")
    out += ["", "## Global feature importance (mean |SHAP| on validation rows)", ""]
    for task, imp in m["shap_global_importance"].items():
        top = list(imp.items())[:6]
        out.append(f"- **{task}**: " + ", ".join(f"{f} {v:.3f}" for f, v in top))
    out += [
        "",
        f"Computed on {m['shap_rows']} validation rows. Delay SHAP is in minutes; conflict SHAP is in "
        "the model's raw output units (log-odds for XGBoost, probability for random forest).",
        "",
        "## Known limits",
        "- Trained on SIMULATED data from one sample corridor with assumed variability ranges",
        "  (docs/ASSUMPTIONS.md). Performance on real operations is unknown.",
        "- Conflicts caused by disruptions that start after state time are unforeseeable: the",
        "  features only contain what is known at state time, so some missed conflicts are expected.",
        "- The models advise a human controller. They do not control trains or signals.",
        "",
    ]
    return "\n".join(out)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Train delay + conflict models on SIMULATED data.")
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-iter", type=int, default=20)
    args = p.parse_args(argv)
    train(args.csv, seed=args.seed, n_iter=args.n_iter, small_check=True)


if __name__ == "__main__":
    main()
