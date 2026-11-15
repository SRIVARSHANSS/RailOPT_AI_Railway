"""REAL data Step 2: DG -> MDU delay model validation (pre-registered, ASSUMPTIONS.md 57-63)."""
import json

import numpy as np
import pandas as pd
import pytest

from ml import real_delay as R


def _need():
    if not (R.REAL_DIR / "runs.csv").exists():
        pytest.skip("REAL extract missing: run python -m app.services.realdata.extract")


def test_split_is_by_date_and_flags_match_the_audit():
    _need()
    df = R.load_runs()
    assert (df[df.split == "train"].dg_date <= R.TRAIN_END).all()
    assert (df[df.split == "test"].dg_date > R.TRAIN_END).all()
    audit = json.loads((R.REAL_DIR / "audit.json").read_text(encoding="utf-8"))
    assert int(df.flagged.sum()) == audit["delays"]["suspicious_mdu_zero_after_dg_ge_10"]["runs"]
    assert len(R.analysis_rows(df, "main")) == len(df) - int(df.flagged.sum())
    assert len(R.analysis_rows(df, "S1_include_flagged")) == len(df)
    assert R.analysis_rows(df, "S2_cap_180")[R.DELAY_COLS].max().max() <= R.CAP_MIN


def test_train_mean_uses_training_rows_only_and_leave_one_out():
    tr = pd.DataFrame({"train_no": [1, 1, 1, 2], "mdu_arr_delay": [0.0, 10.0, 20.0, 7.0]})
    te = pd.DataFrame({"train_no": [1, 2, 3], "mdu_arr_delay": [999.0, 999.0, 999.0]})
    a, b = R.add_train_mean(tr, te)
    assert a.train_mean_past_delay.tolist() == [15.0, 10.0, 5.0, pytest.approx(37 / 4)]  # own row out; lone train -> global
    assert b.train_mean_past_delay.tolist() == [10.0, 7.0, pytest.approx(37 / 4)]       # test targets never used
    assert not any("train_no" == c for c in R.features(a.assign(
        dg_dep_delay=0, dg_arr_delay=0, upstream_dep_delay=0, terminates=0, dg_dep_hour=10,
        train_type="EXPRESS", weekday="Mon")).columns)                                    # no train-number one-hot


def test_metrics_and_paired_bootstrap():
    y = np.array([0.0, 2.0, 4.0, 6.0])
    m = R._metrics(y, y + np.array([1.0, -1.0, 1.0, -1.0]))
    assert m.tolist() == [1.0, 1.0, pytest.approx(1 - 4 / 20), 1.0]
    pred = pd.DataFrame({"train_no": [1, 1, 2, 2, 3, 3] * 5, "terminates": [0, 1] * 15,
                         "mdu_arr_delay": np.arange(30.0)})
    pred["pred_CARRY"] = pred.mdu_arr_delay + 5
    for k in ("LINEAR", "RF", "XGB"):
        pred[f"pred_{k}"] = pred.mdu_arr_delay + 1
    r = R.evaluate(pred, n_boot=500)
    d = r["overall"]["methods"]["XGB"]["mae_minus_carry"]
    assert d["value"] == pytest.approx(-4) and d["better"] and d["better_clustered"]
    assert r["terminating"]["n"] + r["through"]["n"] == r["overall"]["n"]


def test_committed_report_matches_a_fresh_run(tmp_path):
    _need()
    stored = R.OUT_DIR / "metrics_real.json"
    if not stored.exists():
        pytest.skip("metrics_real.json missing: run python -m ml.real_delay")
    s = R.run(out_dir=tmp_path)
    assert s == json.loads(stored.read_text(encoding="utf-8"))                 # deterministic, inputs unchanged
    assert (tmp_path / "model_card_real.md").read_text(encoding="utf-8") == \
        (R.OUT_DIR / "model_card_real.md").read_text(encoding="utf-8")
    assert s["data_label"] == "REAL" and "not trained on real data" in s["note"]
    for a in R.ANALYSES:
        for k in R.METHODS:
            assert s["analyses"][a]["metrics"]["overall"]["methods"][k]["mae"]["value"] >= 0
