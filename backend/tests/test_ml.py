"""Phase 4: ML models. A small 300-run SIMULATED dataset keeps these fast."""
import json
from pathlib import Path

import pytest

from app.services.datagen import generate, plan_features
from app.services.network import format_time, load_network
from app.services.network import parse_time as t
from app.services.predictor import Predictor
from app.services.simulator import Disruption
from ml.features import load_rows, split_by_run
from ml.train import MODEL_FILES, sha256_file, train

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "data"
GENERATED = DATA / "generated"
MODELS = BACKEND / "ml" / "models"
REPORTS = BACKEND / "ml" / "reports"
N_ITER = 3


@pytest.fixture(scope="module")
def small_csv(tmp_path_factory):
    path = tmp_path_factory.mktemp("ml") / "rows300.csv"
    generate(300, 42).to_csv(path, index=False)
    return path


@pytest.fixture(scope="module")
def trained(small_csv, tmp_path_factory):
    out = tmp_path_factory.mktemp("run1")
    metrics = train(small_csv, out / "models", out / "reports", seed=42, n_iter=N_ITER, verbose=False)
    return metrics, out


def _without_timing(m: dict) -> dict:
    return {k: v for k, v in m.items() if k != "training_seconds"}


def test_split_has_no_run_overlap_and_keeps_run_order(small_csv):
    split = split_by_run(load_rows(small_csv))
    ids = split.run_ids()
    assert not ids["train"] & ids["val"]
    assert not ids["train"] & ids["test"]
    assert not ids["val"] & ids["test"]
    assert max(ids["train"]) < min(ids["val"]) and max(ids["val"]) < min(ids["test"])
    # runs whose trains had all entered their sections by state time produce no rows
    n = sum(len(v) for v in ids.values())
    assert [len(v) for v in ids.values()] == [round(n * 0.70), round(n * 0.15), n - round(n * 0.70) - round(n * 0.15)]


def test_training_is_reproducible_with_the_same_seed(trained, small_csv, tmp_path):
    first, _ = trained
    again = train(small_csv, tmp_path / "models", tmp_path / "reports", seed=42, n_iter=N_ITER, verbose=False)
    assert _without_timing(again) == _without_timing(first)


def test_model_card_numbers_come_from_metrics(trained):
    metrics, out = trained
    card = (out / "reports" / "model_card.md").read_text(encoding="utf-8")
    assert "SIMULATED" in card
    best = metrics["conflict"]["models"][metrics["conflict"]["best_model"]]
    assert f"{best['test']['recall']:.3f}" in card
    assert f"{metrics['delay']['baselines']['deterministic_projection']['test']['mae']:.3f}" in card


def test_predictor_returns_valid_and_stable_output(trained, small_csv):
    _, out = trained
    predictor = Predictor(out / "models")
    df = load_rows(small_csv)
    for _, row in df.sample(50, random_state=0).iterrows():
        features = row.to_dict()
        a, b = predictor.predict(features), predictor.predict(features)
        assert a == b
        assert 0.0 <= a["conflict_probability"] <= 1.0
        assert a["predicted_delay_min"] >= 0.0
        assert a["conflict_predicted"] == (a["conflict_probability"] >= a["threshold"])
        assert len(a["top_drivers"]) == 3
        assert all(d["direction"] in {"raises", "lowers"} for d in a["top_drivers"])


def test_saved_model_beats_rule_recall_at_equal_precision():
    """The shipped model (ml/reports/metrics.json) vs the rule at equal validation precision.

    The hashes tie the saved numbers to the dataset and model files on disk,
    so this can never pass on stale metrics.
    """
    for path in (REPORTS / "metrics.json", GENERATED / "training_rows.csv",
                 *(MODELS / f for f in MODEL_FILES)):
        if not path.exists():
            pytest.skip(f"{path.name} missing: run the generator and `python -m ml.train` first")
    metrics = json.loads((REPORTS / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["hashes"]["dataset_sha256"] == sha256_file(GENERATED / "training_rows.csv"), \
        "training_rows.csv changed since training: re-run python -m ml.train"
    for name in MODEL_FILES:
        assert metrics["hashes"]["models_sha256"][name] == sha256_file(MODELS / name), \
            f"{name} does not match metrics.json: re-run python -m ml.train"

    eq = metrics["conflict"]["operating_points"]["equal_to_rule_precision"]
    print(f"\n[SIMULATED, shipped model] validation at the rule's precision {eq['rule_val_precision']:.3f}: "
          f"rule recall {eq['rule_val_recall']:.3f}, model recall {eq['val']['recall']:.3f}")
    assert eq["val"] is not None, "model never reaches the rule's precision"
    assert eq["val"]["precision"] >= eq["rule_val_precision"]
    assert eq["val"]["recall"] > eq["rule_val_recall"]


def test_small_data_head_to_head_report(trained):
    """Report only: the same comparison for the 300-run, minimally tuned test model."""
    metrics, _ = trained
    eq = metrics["conflict"]["operating_points"]["equal_to_rule_precision"]
    model_recall = f"{eq['val']['recall']:.3f}" if eq["val"] else "n/a"
    print(f"\n[SIMULATED, 300 runs, {N_ITER} configs] validation at the rule's precision "
          f"{eq['rule_val_precision']:.3f}: rule recall {eq['rule_val_recall']:.3f}, model recall {model_recall}")


def test_t101_reference_scenario_report(trained):
    """Report only: T202 on S_BC, full day, T101 stops in B-C at 10:03 for 15 min."""
    _, out = trained
    net = load_network(DATA, timetable="full_day")
    stoppage = Disruption("E1", "STOPPAGE", "T101", "S_BC", t("10:03"), 15)
    rows = plan_features(net, t("10:03"), [stoppage], stoppage)
    row = next(r for r in rows if r["train_id"] == "T202" and r["section_id"] == "S_BC")
    result = Predictor(out / "models").predict(row)
    print(f"\n[SIMULATED, 300-run test model] T202 on S_BC at {format_time(t('10:03'))}: "
          f"rule flag {row['rule_flags_conflict']}, "
          f"conflict probability {result['conflict_probability']:.3f}, "
          f"predicted delay {result['predicted_delay_min']:.1f} min, "
          f"deterministic projection {row['baseline_projected_delay_min']} min")
    for d in result["top_drivers"]:
        print(f"   {d['feature']} = {d['value']}: {d['direction']} conflict risk (SHAP {d['shap']:+.3f})")
    assert 0.0 <= result["conflict_probability"] <= 1.0
