"""GET /api/evaluation and /api/model: stored results, hash-checked, never recomputed. SIMULATED."""
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import results


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _need(*paths):
    for p in paths:
        if not p.exists():
            pytest.skip(f"{p.name} missing: run the evaluation / `python -m ml.train` first")


def test_evaluation_endpoint_returns_the_stored_summary(client):
    _need(results.EVAL_DIR / "eval_summary.json", results.MODEL_DIR / "conflict_model.joblib")
    body = client.get("/api/evaluation").json()
    assert body["data_label"] == "SIMULATED"
    assert body["status"] == "ok", body["reasons"]
    stored = json.loads((results.EVAL_DIR / "eval_summary.json").read_text(encoding="utf-8"))
    assert body["summary"] == stored                                     # passed through unchanged
    # solver totals are sums of the stored per-method numbers
    p10 = [m for m in results.PHASE10 if m in stored["solver"]]
    assert body["solver_totals"]["phase10"]["solves"] == sum(stored["solver"][m]["solves"] for m in p10)
    assert body["solver_totals"]["phase10"]["optimal"] == sum(stored["solver"][m]["optimal"] for m in p10)
    # the conclusion counts exactly the variants in the summary
    c = body["conclusion"]
    assert c["variants"] == list(stored["settings"]["deterministic"]["variants_vs_dynamic"])
    assert f"{len(c['variants'])} variants" in c["text"]
    # distribution: counts per method add up to the scenarios
    n = stored["config"]["scenarios"]
    for setting in ("deterministic", "robustness"):
        for m, d in body["distribution"][setting]["methods"].items():
            assert d["improved"] + d["unchanged"] + d["worse"] == n == sum(d["histogram"])
            assert d["whisker_low"] <= d["q1"] <= d["median"] <= d["q3"] <= d["whisker_high"]


def test_model_endpoint_returns_metrics_and_importance(client):
    _need(results.ML_REPORTS / "metrics.json", results.MODEL_DIR / "conflict_model.joblib")
    body = client.get("/api/model").json()
    assert body["data_label"] == "SIMULATED"
    assert body["status"] == "ok", body["reasons"]
    stored = json.loads((results.ML_REPORTS / "metrics.json").read_text(encoding="utf-8"))
    assert body["metrics"] == stored
    assert {r["model"] for r in body["feature_importance"]} == {"delay", "conflict"}
    assert body["evaluation"]["conclusion"]["text"]


def test_evaluation_outdated_when_results_or_models_change(tmp_path):
    _need(results.EVAL_DIR / "eval_summary.json", results.MODEL_DIR / "conflict_model.joblib")
    ev, models = tmp_path / "eval", tmp_path / "models"
    shutil.copytree(results.EVAL_DIR, ev)
    shutil.copytree(results.MODEL_DIR, models)
    assert results.evaluation_view(ev, models)["status"] == "ok"

    with open(ev / "eval_results.csv", "a", encoding="utf-8") as f:
        f.write("\n")
    out = results.evaluation_view(ev, models)
    assert out["status"] == "outdated" and any("eval_results.csv changed" in r for r in out["reasons"])

    shutil.copy(results.EVAL_DIR / "eval_results.csv", ev / "eval_results.csv")
    with open(models / "conflict_model.joblib", "ab") as f:
        f.write(b"x")
    out = results.evaluation_view(ev, models)
    assert out["status"] == "outdated" and any("conflict_model.joblib changed" in r for r in out["reasons"])


def test_model_outdated_and_missing(tmp_path):
    _need(results.ML_REPORTS / "metrics.json", results.MODEL_DIR / "conflict_model.joblib")
    models = tmp_path / "models"
    shutil.copytree(results.MODEL_DIR, models)
    (models / "delay_model.joblib").unlink()
    out = results.model_view(results.ML_REPORTS, models, tmp_path / "no_dataset.csv", results.EVAL_DIR)
    assert out["status"] == "outdated" and any("delay_model.joblib is missing" in r for r in out["reasons"])
    assert out["dataset_check"].startswith("not present locally")

    empty = tmp_path / "empty"
    empty.mkdir()
    assert results.model_view(empty, models, tmp_path / "x.csv", empty)["status"] == "missing"
    assert results.evaluation_view(empty, models)["status"] == "missing"
