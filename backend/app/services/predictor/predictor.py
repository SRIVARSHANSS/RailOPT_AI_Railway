"""Delay and conflict predictor (Phase 4).

Loads the saved preprocessing pipeline and models once and scores one
(train, upcoming section) feature row, as produced by
`app.services.datagen.plan_features`.

Models are trained on SIMULATED data. The predictor advises a human
controller; it does not decide or act on anything.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd

from app.services.datagen.generator import FEATURES
from ml.explain import make_explainer, shap_matrix, top_k

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[3] / "ml" / "models"
SIMULATED_NOTE = "model trained on SIMULATED data"


class Predictor:
    def __init__(self, model_dir: str | Path = DEFAULT_MODEL_DIR):
        model_dir = Path(model_dir)
        self.pre = joblib.load(model_dir / "preprocess.joblib")
        delay = joblib.load(model_dir / "delay_model.joblib")
        conflict = joblib.load(model_dir / "conflict_model.joblib")
        self.delay_model, self.delay_name = delay["model"], delay["name"]
        self.conflict_model, self.conflict_name = conflict["model"], conflict["name"]
        self.threshold = float(conflict["threshold"])     # recall >= 0.80 operating point
        self._delay_explainer = make_explainer(self.delay_model)
        self._conflict_explainer = make_explainer(self.conflict_model)

    def _frame(self, features: dict) -> pd.DataFrame:
        missing = [f for f in FEATURES if f not in features]
        if missing:
            raise ValueError(f"missing features: {missing}")
        return pd.DataFrame([{f: features[f] for f in FEATURES}])

    def predict(self, features: dict, k: int = 3) -> dict:
        X = self.pre.transform(self._frame(features))
        delay = float(self.delay_model.predict(X)[0])
        proba = float(self.conflict_model.predict_proba(X)[0, 1])
        conflict_shap = shap_matrix(self._conflict_explainer, X)[0]
        delay_shap = shap_matrix(self._delay_explainer, X)[0]
        return {
            "predicted_delay_min": max(0.0, delay),          # a delay below zero is not meaningful
            "conflict_probability": min(1.0, max(0.0, proba)),
            "conflict_predicted": proba >= self.threshold,
            "top_drivers": top_k(conflict_shap, self.pre.source, features, k),
            "delay_top_drivers": top_k(delay_shap, self.pre.source, features, k),
            "threshold": self.threshold,
            "note": SIMULATED_NOTE,
        }

    def top_drivers(self, features: dict, k: int = 3) -> list[dict]:
        """Top k features behind the conflict prediction for one row, with direction."""
        X = self.pre.transform(self._frame(features))
        return top_k(shap_matrix(self._conflict_explainer, X)[0], self.pre.source, features, k)


_default: Predictor | None = None


def get_predictor() -> Predictor:
    """The default predictor, loaded once from backend/ml/models."""
    global _default
    if _default is None:
        _default = Predictor()
    return _default


def predict(features: dict) -> dict:
    return get_predictor().predict(features)


def top_drivers(row: dict, k: int = 3) -> list[dict]:
    return get_predictor().top_drivers(row, k)
