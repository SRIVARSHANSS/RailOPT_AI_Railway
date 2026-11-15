"""REAL data Step 2: validate delay prediction on recorded DG -> MDU runs (Sept 2024).

    python -m ml.real_delay            (from backend/, after the Step 1 extract)

Design pre-registered in docs/ASSUMPTIONS.md 57-63 before any model was fitted. Writes
ml/reports/real/{metrics_real.json, model_card_real.md, predictions_real.csv}; the card is
generated from the JSON (never edit numbers by hand). Data label REAL. The SIMULATED Phase 4
models are untouched and were never trained on real data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from xgboost import XGBRegressor

BACKEND = Path(__file__).resolve().parents[1]
REAL_DIR = BACKEND / "data" / "real" / "dg_mdu"
OUT_DIR = BACKEND / "ml" / "reports" / "real"

TRAIN_END = "2024-09-22"          # DG dates <= this are training, later dates are test
CAP_MIN = 180.0
SUSPICIOUS_DG_MIN = 10            # Step 1 audit flag: MDU exactly 0 after DG dep >= 10
N_BOOT = 10_000
BOOT_SEED = 2024
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TYPES = ["EXPRESS", "SUPERFAST", "PREMIUM"]
METHODS = ["CARRY", "LINEAR", "RF", "XGB"]
METHOD_LABEL = {"CARRY": "B0 carry the DG delay", "LINEAR": "B1 linear regression",
                "RF": "Random forest", "XGB": "XGBoost"}
ANALYSES = {"main": "Main (39 flagged runs excluded)",
            "S1_include_flagged": "S1: flagged runs included",
            "S2_cap_180": "S2: main rows, delays capped at 180 min"}
SUBSETS = ["overall", "terminating", "through"]
DELAY_COLS = ["dg_dep_delay", "dg_arr_delay", "upstream_dep_delay", "mdu_arr_delay"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- data
def load_runs(real_dir: Path = REAL_DIR) -> pd.DataFrame:
    runs = pd.read_csv(real_dir / "runs.csv")
    trains = pd.read_csv(real_dir / "trains.csv")[["train_no", "train_type", "terminates_at_mdu"]]
    sched = pd.read_csv(real_dir / "schedule.csv", dtype=str)
    dg = sched[sched.station_code == "DG"].assign(train_no=lambda d: d.train_id.str[1:].astype(int))
    hm = dg.sched_dep.str.split(":", expand=True).astype(int)
    dg = dg.assign(dg_dep_hour=hm[0] + hm[1] / 60)[["train_no", "dg_dep_hour"]]
    df = runs.merge(trains, on="train_no").merge(dg, on="train_no")
    df["terminates"] = (df.terminates_at_mdu == "yes").astype(int)
    df["flagged"] = (df.mdu_arr_delay == 0) & (df.dg_dep_delay >= SUSPICIOUS_DG_MIN)
    df["split"] = np.where(df.dg_date <= TRAIN_END, "train", "test")
    return df.sort_values(["dg_date", "train_no"]).reset_index(drop=True)


def analysis_rows(df: pd.DataFrame, analysis: str) -> pd.DataFrame:
    d = df.copy() if analysis == "S1_include_flagged" else df[~df.flagged].copy()
    if analysis == "S2_cap_180":
        for c in DELAY_COLS:
            d[c] = d[c].clip(upper=CAP_MIN)
    return d.reset_index(drop=True)


def add_train_mean(tr: pd.DataFrame, te: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mean past MDU delay per train from TRAINING rows only; leave-one-out on training rows."""
    tr, te = tr.copy(), te.copy()
    g = tr.groupby("train_no").mdu_arr_delay
    s, n = g.transform("sum"), g.transform("count")
    glob = tr.mdu_arr_delay.mean()
    tr["train_mean_past_delay"] = np.where(n > 1, (s - tr.mdu_arr_delay) / (n - 1).clip(lower=1), glob)
    means = g.mean()
    te["train_mean_past_delay"] = te.train_no.map(means).fillna(glob)
    return tr, te


def features(d: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame({
        "dg_dep_delay": d.dg_dep_delay, "dg_arr_delay": d.dg_arr_delay,
        "upstream_dep_delay": d.upstream_dep_delay.fillna(d.dg_arr_delay),
        "terminates_at_mdu": d.terminates,
        "hour_sin": np.sin(2 * np.pi * d.dg_dep_hour / 24), "hour_cos": np.cos(2 * np.pi * d.dg_dep_hour / 24),
        "train_mean_past_delay": d.train_mean_past_delay,
    })
    for t in TYPES[1:]:
        X[f"type_{t}"] = (d.train_type == t).astype(int)
    for w in WEEKDAYS[1:]:
        X[f"dow_{w}"] = (d.weekday == w).astype(int)
    return X.astype(float)


def make(kind: str):
    if kind == "LINEAR":
        return LinearRegression()
    if kind == "RF":
        return RandomForestRegressor(n_estimators=500, min_samples_leaf=5, random_state=0, n_jobs=1)
    if kind == "XGB":
        return XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
                            colsample_bytree=0.8, random_state=0, n_jobs=1)
    raise ValueError(kind)


def fit_predict(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    tr, te = d[d.split == "train"], d[d.split == "test"]
    tr, te = add_train_mean(tr, te)
    Xtr, Xte = features(tr), features(te)
    out = te[["train_no", "dg_date", "train_type", "terminates", "dg_dep_delay", "mdu_arr_delay"]].copy()
    out["pred_CARRY"] = te.dg_dep_delay.values
    importance = {}
    for k in METHODS[1:]:
        m = make(k).fit(Xtr, tr.mdu_arr_delay)
        out[f"pred_{k}"] = m.predict(Xte)
        if k == "LINEAR":
            importance[k] = dict(zip(Xtr.columns, np.round(m.coef_, 4)))
        else:
            importance[k] = dict(zip(Xtr.columns, np.round(m.feature_importances_.astype(float), 4)))
    return out.reset_index(drop=True), {"n_train": int(len(tr)), "n_test": int(len(te)),
                                        "train_trains": int(tr.train_no.nunique()),
                                        "test_trains": int(te.train_no.nunique()),
                                        "test_trains_unseen": int((~te.train_no.isin(tr.train_no)).sum()),
                                        "importance": importance}


# ---------------------------------------------------------------- metrics
def _metrics(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    """MAE, RMSE, R2, MedAE along the last axis (works on bootstrap stacks)."""
    e = p - y
    mae = np.abs(e).mean(-1)
    rmse = np.sqrt((e ** 2).mean(-1))
    sst = ((y - y.mean(-1, keepdims=True)) ** 2).sum(-1)
    r2 = 1 - (e ** 2).sum(-1) / np.where(sst > 0, sst, np.nan)
    medae = np.median(np.abs(e), -1)
    return np.stack([mae, rmse, r2, medae], -1)


NAMES = ["mae", "rmse", "r2", "medae"]


def evaluate(pred: pd.DataFrame, seed: int = BOOT_SEED, n_boot: int = N_BOOT) -> dict:
    rng = np.random.default_rng(seed)
    res = {}
    for sub in SUBSETS:
        p = pred if sub == "overall" else pred[pred.terminates == (1 if sub == "terminating" else 0)]
        n = len(p)
        if n < 2:
            res[sub] = {"n": n}
            continue
        y = p.mdu_arr_delay.to_numpy(float)
        idx = rng.integers(0, n, size=(n_boot, n))
        # clustered by train: resample trains, take all their test rows
        tn = p.train_no.to_numpy()
        trains = np.unique(tn)
        rows_of = [np.flatnonzero(tn == t) for t in trains]
        cl = [np.concatenate([rows_of[j] for j in rng.integers(0, len(trains), len(trains))]) for _ in range(min(n_boot, 2000))]
        r = {"n": n, "trains": int(len(trains)), "methods": {}}
        carry = p.pred_CARRY.to_numpy(float)
        for k in METHODS:
            pk = p[f"pred_{k}"].to_numpy(float)
            point = _metrics(y, pk)
            boot = _metrics(y[idx], pk[idx])
            lo, hi = np.nanpercentile(boot, [2.5, 97.5], axis=0)
            m = {nm: {"value": round(float(point[i]), 3), "ci": [round(float(lo[i]), 3), round(float(hi[i]), 3)]}
                 for i, nm in enumerate(NAMES)}
            if k != "CARRY":
                d = np.abs(pk[idx] - y[idx]).mean(1) - np.abs(carry[idx] - y[idx]).mean(1)
                dl, dh = np.percentile(d, [2.5, 97.5])
                dc = np.array([np.abs(pk[c] - y[c]).mean() - np.abs(carry[c] - y[c]).mean() for c in cl])
                cl_lo, cl_hi = np.percentile(dc, [2.5, 97.5])
                diff = float(np.abs(pk - y).mean() - np.abs(carry - y).mean())
                m["mae_minus_carry"] = {
                    "value": round(diff, 3), "ci": [round(float(dl), 3), round(float(dh), 3)],
                    "ci_train_clustered": [round(float(cl_lo), 3), round(float(cl_hi), 3)],
                    "better": bool(dh < 0), "worse": bool(dl > 0),
                    "better_clustered": bool(cl_hi < 0),
                }
            r["methods"][k] = m
        res[sub] = r
    return res


def run(real_dir: Path = REAL_DIR, out_dir: Path = OUT_DIR, n_boot: int = N_BOOT) -> dict:
    df = load_runs(real_dir)
    audit = json.loads((real_dir / "audit.json").read_text(encoding="utf-8"))
    flagged_expected = audit["delays"]["suspicious_mdu_zero_after_dg_ge_10"]["runs"]
    assert int(df.flagged.sum()) == flagged_expected, "flag definition drifted from the Step 1 audit"
    results, preds = {}, []
    for a in ANALYSES:
        d = analysis_rows(df, a)
        pred, info = fit_predict(d)
        results[a] = {"label": ANALYSES[a], **info, "metrics": evaluate(pred, n_boot=n_boot)}
        preds.append(pred.assign(analysis=a))
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_all = pd.concat(preds, ignore_index=True)
    pred_all.round(3).to_csv(out_dir / "predictions_real.csv", index=False)
    summary = {
        "data_label": "REAL",
        "note": "Recorded Sept 2024 running data, DG -> MDU (RSTGCN dataset, CC BY-SA 4.0). "
                "The SIMULATED Phase 4 models were not trained on real data and are unchanged.",
        "design": "docs/ASSUMPTIONS.md 57-63 (pre-registered)",
        "split": {"train": f"DG dates <= {TRAIN_END}", "test": f"DG dates > {TRAIN_END}"},
        "rows_total": int(len(df)), "flagged_runs": int(df.flagged.sum()),
        "flagged_in_test": int((df.flagged & (df.split == "test")).sum()),
        "bootstrap": {"resamples": n_boot, "seed": BOOT_SEED, "clustered_resamples": min(n_boot, 2000)},
        "inputs": {f: sha256(real_dir / f) for f in ("runs.csv", "trains.csv", "schedule.csv")},
        "methods": METHOD_LABEL, "analyses": results,
    }
    summary["conclusion"] = conclusion(summary)
    (out_dir / "metrics_real.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "model_card_real.md").write_text(render(summary), encoding="utf-8")
    return summary


def conclusion(s: dict) -> dict:
    """Plain verdict from the numbers: does any ML model beat carry on MAE (whole CI below 0)?"""
    main = s["analyses"]["main"]["metrics"]["overall"]["methods"]
    better = [k for k in ("RF", "XGB") if main[k]["mae_minus_carry"]["better"]]
    worse = [k for k in ("RF", "XGB") if main[k]["mae_minus_carry"]["worse"]]
    if better:
        parts = []
        for k in better:
            d = main[k]["mae_minus_carry"]
            robust = "also" if d["better_clustered"] else "but not"
            parts.append(
                f"{METHOD_LABEL[k]} beat the carry-the-DG-delay baseline on test MAE in the main analysis "
                f"({main[k]['mae']['value']:.2f} vs {main['CARRY']['mae']['value']:.2f} min; difference "
                f"{d['value']:+.2f} min, 95% CI [{d['ci'][0]:+.2f}, {d['ci'][1]:+.2f}]), {robust} under the "
                f"train-clustered check [{d['ci_train_clustered'][0]:+.2f}, {d['ci_train_clustered'][1]:+.2f}].")
        sens = []
        for a in ("S1_include_flagged", "S2_cap_180"):
            m = s["analyses"][a]["metrics"]["overall"]["methods"]
            b = [METHOD_LABEL[k] for k in ("RF", "XGB") if m[k]["mae_minus_carry"]["better"]]
            sens.append(f"{s['analyses'][a]['label']}: {', '.join(b) if b else 'no ML model'} better")
        gain = max(-main[k]["mae_minus_carry"]["value"] for k in better)
        size = "under one minute" if gain < 1 else f"{gain:.1f} min"
        text = " ".join(parts) + f" The gain is {size} per train on average. Sensitivity - " + "; ".join(sens) + "."
    else:
        text = ("Neither ML model beat the carry-the-DG-delay baseline significantly on test MAE in the "
                "main analysis" + (f"; {' and '.join(METHOD_LABEL[k] for k in worse)} did significantly worse" if worse else "")
                + ". On this corridor the DG departure delay is the prediction to beat.")
    return {"ml_better_than_carry": better, "ml_worse_than_carry": worse, "text": text}


# ---------------------------------------------------------------- card
def _v(m, k, d=2):
    x = m[k]
    return f"{x['value']:.{d}f} [{x['ci'][0]:.{d}f}, {x['ci'][1]:.{d}f}]"


def render(s: dict) -> str:
    main = s["analyses"]["main"]
    L = [
        "# RailOpt AI - real-data model card (DG -> MDU delay)",
        "",
        "**REAL data: recorded running times, Sept 2024, Dindigul -> Madurai** (RSTGCN dataset, "
        "CC BY-SA 4.0; see docs/DATA_SOURCES.md). Generated by `python -m ml.real_delay` from "
        "`metrics_real.json`; do not edit numbers by hand.",
        "",
        "The SIMULATED models of Phase 4 (`model_card.md`) were **not trained on real data** and are "
        "unchanged. This card only validates whether delay at Madurai can be predicted from what is "
        "known when a train leaves Dindigul.",
        "",
        "## Conclusion", "", s["conclusion"]["text"], "",
        "## Design (pre-registered, docs/ASSUMPTIONS.md 57-63)",
        "- Target: arrival delay at MDU (min). Known at DG departure: DG departure and arrival delay, "
        "upstream departure delay, train type, terminates_at_MDU, scheduled DG hour (sin/cos), day of "
        "week, the train's mean past MDU delay (training dates only, leave-one-out on training rows).",
        f"- Split by date: train {s['split']['train']}, test {s['split']['test']}. "
        f"Main analysis: {main['n_train']} train rows, {main['n_test']} test rows "
        f"({main['test_trains']} trains; {main['test_trains_unseen']} test rows from trains unseen in training).",
        f"- {s['flagged_runs']} runs flagged in the Step 1 audit (MDU exactly on time after DG >= 10 min late; "
        f"{s['flagged_in_test']} in the test dates) are excluded from the main analysis; S1 includes them.",
        "- Methods, fixed without tuning: " + "; ".join(s["methods"].values()) + ".",
        f"- 95% CIs: percentile bootstrap over test rows ({s['bootstrap']['resamples']} resamples, seed "
        f"{s['bootstrap']['seed']}); the MAE difference vs carry is paired. A train-clustered bootstrap "
        f"({s['bootstrap']['clustered_resamples']} resamples) is shown as a check.",
        "",
    ]
    for a, res in s["analyses"].items():
        L += [f"## {res['label']}", ""]
        for sub in SUBSETS:
            r = res["metrics"][sub]
            if "methods" not in r:
                L += [f"**{sub}**: {r['n']} test rows, too few to score.", ""]
                continue
            L += [f"**{sub.capitalize()}** ({r['n']} test rows, {r['trains']} trains)", "",
                  "| Method | MAE | RMSE | R2 | Median abs error | MAE - carry [95% CI] | clustered CI |",
                  "|---|---|---|---|---|---|---|"]
            for k in METHODS:
                m = r["methods"][k]
                if k == "CARRY":
                    dcol, ccol = "-", "-"
                else:
                    dd = m["mae_minus_carry"]
                    tag = " better" if dd["better"] else " worse" if dd["worse"] else " n.s."
                    dcol = f"{dd['value']:+.2f} [{dd['ci'][0]:+.2f}, {dd['ci'][1]:+.2f}]{tag}"
                    ccol = f"[{dd['ci_train_clustered'][0]:+.2f}, {dd['ci_train_clustered'][1]:+.2f}]"
                L.append(f"| {METHOD_LABEL[k]} | {_v(m, 'mae')} | {_v(m, 'rmse')} | {_v(m, 'r2', 3)} | "
                         f"{_v(m, 'medae')} | {dcol} | {ccol} |")
            L.append("")
    imp = main["importance"]
    L += ["## What the models used (main analysis)", "",
          "| Feature | Linear coef | RF importance | XGB importance |", "|---|---:|---:|---:|"]
    for f in imp["RF"]:
        L.append(f"| {f} | {imp['LINEAR'][f]:+.3f} | {imp['RF'][f]:.3f} | {imp['XGB'][f]:.3f} |")
    L += ["", "## Limits",
          "- One month, one direction of one corridor, 44 trains; the test set is one week, so the CIs are wide.",
          "- Rows of the same train are correlated; the row bootstrap understates uncertainty (see the clustered CI).",
          "- The flag used to exclude runs is defined from the target; the main analysis therefore removes cases "
          "where the carry baseline fails badly. S1 shows the effect.",
          "- The source never records an actual time earlier than scheduled, so early running is invisible.",
          "- Passenger/MEMU and freight trains are not in the data.", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="REAL data Step 2: DG -> MDU delay model validation.")
    ap.add_argument("--boot", type=int, default=N_BOOT)
    a = ap.parse_args()
    s = run(n_boot=a.boot)
    print(render(s))


if __name__ == "__main__":
    main()
