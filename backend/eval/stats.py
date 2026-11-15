"""Statistics for the evaluation: bootstrap CIs and paired comparisons (seeded, reproducible)."""
from __future__ import annotations

import numpy as np
from scipy.stats import wilcoxon

BOOTSTRAP = 10_000
CI = 0.95


def bootstrap_ci(x, stat=np.mean, n: int = BOOTSTRAP, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI over scenarios (resampled with replacement)."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    values = stat(x[idx], axis=1)
    lo, hi = np.quantile(values, [(1 - CI) / 2, 1 - (1 - CI) / 2])
    return (float(lo), float(hi))


def describe(x, seed: int = 0) -> dict:
    x = np.asarray(x, dtype=float)
    return {"mean": float(np.mean(x)), "mean_ci": bootstrap_ci(x, np.mean, seed=seed),
            "median": float(np.median(x)), "median_ci": bootstrap_ci(x, np.median, seed=seed)}


def paired(method, baseline, seed: int = 0) -> dict:
    """Per-scenario comparison, diff = method - baseline (negative = method better).
    Significant = the 95% bootstrap CI of the mean difference excludes 0."""
    m, b = np.asarray(method, dtype=float), np.asarray(baseline, dtype=float)
    d = m - b
    lo, hi = bootstrap_ci(d, np.mean, seed=seed)
    nonzero = d[d != 0]
    p = float(wilcoxon(nonzero).pvalue) if len(nonzero) >= 1 and np.any(nonzero) else 1.0
    return {
        "n": int(len(d)),
        "wins": int(np.sum(d < 0)), "ties": int(np.sum(d == 0)), "losses": int(np.sum(d > 0)),
        "mean_diff": float(np.mean(d)), "mean_diff_ci": (lo, hi),
        "median_diff": float(np.median(d)),
        "wilcoxon_p": p,
        "significant": bool(lo > 0 or hi < 0),
    }
