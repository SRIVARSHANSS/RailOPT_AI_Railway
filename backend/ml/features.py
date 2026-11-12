"""Data loading, run-based split and the shared preprocessing pipeline.

The same fitted `Preprocessor` is saved with the models and used by both
training and the live predictor, so encoding never drifts between them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from app.services.datagen.generator import BASELINES, FEATURES, LABELS

CATEGORICAL = ["train_type", "section_id", "preceding_train_type", "disruption_type"]
GAP_FEATURE = "headway_gap_min"
GAP_CAP_MIN = 120      # 999 means "no train ahead"; cap it so it cannot dominate linear models

SPLIT_FRACTIONS = (0.70, 0.15, 0.15)


def cap_gap(x):
    """Module-level (picklable) transform: cap the headway gap at GAP_CAP_MIN."""
    return np.minimum(np.asarray(x, dtype=float), GAP_CAP_MIN)


# ---------------------------------------------------------------------------
# data + split
# ---------------------------------------------------------------------------
def load_rows(csv_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    missing = set(["run_id", *FEATURES, *BASELINES, *LABELS]) - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path} is missing columns {sorted(missing)}")
    return df


@dataclass
class Split:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame

    def run_ids(self) -> dict[str, set[str]]:
        return {name: set(part["run_id"]) for name, part in
                (("train", self.train), ("val", self.val), ("test", self.test))}


def split_by_run(df: pd.DataFrame) -> Split:
    """First 70 % of runs (in run order) = train, next 15 % = val, last 15 % = test."""
    runs = sorted(df["run_id"].unique())
    n = len(runs)
    n_train = int(round(n * SPLIT_FRACTIONS[0]))
    n_val = int(round(n * SPLIT_FRACTIONS[1]))
    groups = {
        "train": set(runs[:n_train]),
        "val": set(runs[n_train:n_train + n_val]),
        "test": set(runs[n_train + n_val:]),
    }
    split = Split(*(df[df["run_id"].isin(groups[g])].reset_index(drop=True)
                    for g in ("train", "val", "test")))
    ids = split.run_ids()
    assert not (ids["train"] & ids["val"] or ids["train"] & ids["test"] or ids["val"] & ids["test"]), \
        "a run_id appears in two splits"
    assert all(ids.values()), "every split needs at least one run"
    return split


# ---------------------------------------------------------------------------
# preprocessing
# ---------------------------------------------------------------------------
class Preprocessor:
    """One-hot categoricals, capped + scaled headway gap, scaled numerics.

    `source` maps every output column back to the original feature name, so
    SHAP values of one-hot columns can be summed per feature.
    """

    def __init__(self, features: list[str]):
        self.features = list(features)
        cats = [f for f in self.features if f in CATEGORICAL]
        nums = [f for f in self.features if f not in CATEGORICAL and f != GAP_FEATURE]
        parts = [("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cats)]
        if GAP_FEATURE in self.features:
            parts.append(("gap", Pipeline([("cap", FunctionTransformer(cap_gap)),
                                           ("scale", StandardScaler())]), [GAP_FEATURE]))
        parts.append(("num", StandardScaler(), nums))
        self.ct = ColumnTransformer(parts)
        self._cats, self._nums = cats, nums
        self.source: list[str] = []

    def fit(self, df: pd.DataFrame) -> "Preprocessor":
        self.ct.fit(df[self.features])
        enc = self.ct.named_transformers_["cat"]
        source = [f for f, cats in zip(self._cats, enc.categories_) for _ in cats]
        if GAP_FEATURE in self.features:
            source.append(GAP_FEATURE)
        self.source = source + self._nums
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        return self.ct.transform(df[self.features])

    @property
    def output_names(self) -> list[str]:
        return list(self.ct.get_feature_names_out())
