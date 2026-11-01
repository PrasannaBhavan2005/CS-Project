"""Statistics for paired comparisons (CLAUDE.md "Experiments").

- paired Wilcoxon signed-rank test per comparison, Holm correction over the
  declared primary comparisons;
- TOST equivalence test on paired differences with a margin relative to the
  reference mean (5% in the proposal);
- 95% percentile bootstrap CIs of the mean paired difference.

Runs are paired by run_id (same clip and trace offsets for every config).
"""

import numpy as np
from scipy import stats


def paired(a, b):
    """a, b: dicts run_id -> value. Returns arrays over the common run ids."""
    ids = sorted(set(a) & set(b))
    return np.array([a[i] for i in ids], float), np.array([b[i] for i in ids], float), ids


def wilcoxon_p(x, y):
    """Two-sided paired Wilcoxon signed-rank p-value (exact for small n)."""
    d = np.asarray(x) - np.asarray(y)
    if np.all(d == 0):
        return 1.0
    return float(stats.wilcoxon(x, y, zero_method="wilcox", alternative="two-sided").pvalue)


def holm(pvals):
    """Holm-adjusted p-values, same order as the input."""
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adj[i] = running
    return adj.tolist()


def tost_paired(x, y, margin_frac=0.05, ref=None, alpha=0.05):
    """Equivalence of paired means within +-margin_frac * mean(ref).

    Two one-sided paired t-tests on d = x - y. Returns (p, equivalent).
    """
    d = np.asarray(x, float) - np.asarray(y, float)
    ref = np.asarray(y if ref is None else ref, float)
    delta = margin_frac * abs(ref.mean())
    n = len(d)
    se = d.std(ddof=1) / np.sqrt(n)
    if se == 0:
        p = 0.0 if abs(d.mean()) < delta else 1.0
        return p, p < alpha
    p_lower = 1 - stats.t.cdf((d.mean() + delta) / se, n - 1)  # H0: mean <= -delta
    p_upper = stats.t.cdf((d.mean() - delta) / se, n - 1)      # H0: mean >= +delta
    p = max(p_lower, p_upper)
    return float(p), bool(p < alpha)


def bootstrap_ci(x, y=None, n_boot=10_000, level=0.95, seed=7):
    """Percentile bootstrap CI of mean(x) or of the mean paired difference."""
    v = np.asarray(x, float) if y is None else np.asarray(x, float) - np.asarray(y, float)
    rng = np.random.default_rng(seed)
    means = rng.choice(v, size=(n_boot, len(v)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(v.mean()), float(lo), float(hi)
