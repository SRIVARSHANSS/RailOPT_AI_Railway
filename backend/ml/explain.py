"""SHAP explanations, summed back from encoded columns to original features."""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap


def make_explainer(model):
    return shap.TreeExplainer(model)


def shap_matrix(explainer, X: np.ndarray) -> np.ndarray:
    """SHAP values (n_rows, n_encoded_columns). For classifiers: the positive class.

    XGBoost classifiers are explained in log-odds; random forests in probability.
    """
    values = explainer.shap_values(X)
    if isinstance(values, list):          # older SHAP: one array per class
        values = values[1]
    values = np.asarray(values)
    if values.ndim == 3:                  # newer SHAP: (rows, columns, classes)
        values = values[:, :, 1]
    return values


def per_feature(values: np.ndarray, source: list[str]) -> pd.DataFrame:
    """Sum SHAP columns that come from the same original feature."""
    df = pd.DataFrame(values, columns=range(values.shape[1]))
    return df.T.groupby(np.asarray(source)).sum().T


def global_importance(values: np.ndarray, source: list[str]) -> pd.Series:
    """Mean |SHAP| per original feature, largest first."""
    return per_feature(values, source).abs().mean().sort_values(ascending=False)


def top_k(values_row: np.ndarray, source: list[str], raw: dict, k: int = 3) -> list[dict]:
    summed = per_feature(values_row.reshape(1, -1), source).iloc[0]
    order = summed.abs().sort_values(ascending=False).index[:k]
    return [{
        "feature": f,
        "value": raw.get(f),
        "shap": float(summed[f]),
        "direction": "raises" if summed[f] > 0 else "lowers",
    } for f in order]
