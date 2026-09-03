"""
Detection: given a *collection* of reported test statistics, is this literature
(or this agent's output) p-hacked?

Implements the testable implications of no-p-hacking on the p-curve from
Elliott, Kudrin & Wuethrich (2022, Econometrica) -- non-increasing density,
continuity at the threshold -- plus the classical p-curve tools of Simonsohn,
Nelson & Simmons and the caliper test of Gerber & Malhotra.

Every test here is a test of the *distribution across studies*. None of them
can convict a single paper; that is a property of the method, not a limitation
of the implementation, and the report says so.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = ["binomial_test", "fisher_test", "stouffer_test", "lcm_test",
           "discontinuity_test", "caliper_test", "pcurve_power", "report"]


def _significant(p, alpha):
    p = np.asarray(p, float)
    p = p[np.isfinite(p)]
    return p[(p > 0) & (p < alpha)]


# --------------------------------------------------------------------------
# 1. Binomial: under no p-hacking the p-curve is non-increasing, so among
#    significant results at least half should fall below alpha/2.
# --------------------------------------------------------------------------

def binomial_test(pvals, alpha=0.05) -> dict:
    ps = _significant(pvals, alpha)
    n = ps.size
    if n < 5:
        return {"test": "binomial", "n": int(n), "note": "too few significant results"}
    k = int(np.sum(ps < alpha / 2))
    # one-sided against p-hacking: TOO FEW small p-values (left-skew)
    p_left = stats.binomtest(k, n, 0.5, alternative="less").pvalue
    return {
        "test": "binomial", "n": int(n), "n_below_half_alpha": k,
        "share_below_half_alpha": k / n,
        "p_value": float(p_left),
        "reads": "small p_value => left-skewed p-curve => p-hacking / no evidential value",
    }


# --------------------------------------------------------------------------
# 2/3. Fisher and Stouffer aggregation of the *conditional* p-curve.
# --------------------------------------------------------------------------

def _pp(ps, alpha):
    """pp-values: position of each p within (0, alpha) under the null."""
    return np.clip(ps / alpha, 1e-12, 1 - 1e-12)


def fisher_test(pvals, alpha=0.05) -> dict:
    ps = _significant(pvals, alpha)
    if ps.size < 5:
        return {"test": "fisher", "n": int(ps.size), "note": "too few significant results"}
    pp = _pp(ps, alpha)
    chi = -2 * np.sum(np.log(pp))
    right = float(stats.chi2.sf(chi, 2 * ps.size))          # right-skew: evidential
    left = float(stats.chi2.cdf(chi, 2 * ps.size))          # left-skew: p-hacked
    return {"test": "fisher", "n": int(ps.size), "chi2": float(chi),
            "p_right_skew": right, "p_left_skew": left,
            "reads": "small p_left_skew => p-hacking; small p_right_skew => genuine effect"}


def stouffer_test(pvals, alpha=0.05) -> dict:
    ps = _significant(pvals, alpha)
    if ps.size < 5:
        return {"test": "stouffer", "n": int(ps.size), "note": "too few significant results"}
    z = stats.norm.ppf(_pp(ps, alpha))
    Z = float(np.sum(z) / np.sqrt(z.size))
    return {"test": "stouffer", "n": int(ps.size), "Z": Z,
            "p_right_skew": float(stats.norm.cdf(Z)),
            "p_left_skew": float(stats.norm.sf(Z))}


# --------------------------------------------------------------------------
# 4. Monotonicity via the least concave majorant (Elliott et al. 2022).
#    Under no p-hacking the density of p on (0, alpha) is non-increasing, so the
#    CDF is concave. Distance between the empirical CDF and its LCM is the
#    statistic; the null distribution is bootstrapped under the least favourable
#    null (uniform), which is the boundary of the concave cone.
# --------------------------------------------------------------------------

def _lcm(x, y):
    """Least concave majorant of the points (x, y), returned at the x grid."""
    pts = [(x[0], y[0])]
    for i in range(1, len(x)):
        while len(pts) >= 2:
            (x0, y0), (x1, y1) = pts[-2], pts[-1]
            if (y1 - y0) * (x[i] - x0) <= (y[i] - y0) * (x1 - x0):
                pts.pop()
            else:
                break
        pts.append((x[i], y[i]))
    px, py = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    return np.interp(x, px, py)


def lcm_test(pvals, alpha=0.05, B=2000, seed=0) -> dict:
    ps = np.sort(_significant(pvals, alpha))
    n = ps.size
    if n < 15:
        return {"test": "lcm_monotonicity", "n": int(n), "note": "too few significant results"}
    u = ps / alpha
    def stat(v):
        v = np.sort(v)
        m = v.size
        ecdf = np.arange(1, m + 1) / m
        return float(np.max(_lcm(v, ecdf) - ecdf) * np.sqrt(m))
    obs = stat(u)
    rng = np.random.default_rng(seed)
    null = np.array([stat(rng.uniform(size=n)) for _ in range(B)])
    return {"test": "lcm_monotonicity", "n": int(n), "stat": obs,
            "p_value": float((1 + np.sum(null >= obs)) / (B + 1)),
            "reads": "small p_value => p-curve is NOT non-increasing => p-hacking"}


# --------------------------------------------------------------------------
# 5. Discontinuity of the p-curve at the threshold (bunching just below 0.05).
# --------------------------------------------------------------------------

def _counterfactual_counts(x, cutoff, lo, hi, nbins, donut):
    """Poisson log-linear fit of the density away from the cutoff.

    A 50/50 null for bunching is only right when the underlying density is
    locally flat. Under a genuine effect the density of |z| RISES through 1.96,
    so a naive caliper test flags honest literatures. We instead fit a smooth
    counterfactual on bins outside a donut around the cutoff and compare the
    observed count in the donut against it.
    """
    x = x[(x >= lo) & (x <= hi)]
    edges = np.linspace(lo, hi, nbins + 1)
    counts, _ = np.histogram(x, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    outside = np.abs(centers - cutoff) > donut
    if outside.sum() < 4 or counts[outside].sum() < 10:
        return None
    # quadratic in the bin centre, fitted by Poisson IRLS on the outside bins
    Z = np.column_stack([np.ones(outside.sum()), centers[outside] - cutoff,
                         (centers[outside] - cutoff) ** 2])
    y = counts[outside].astype(float)
    beta = np.zeros(3)
    beta[0] = np.log(max(y.mean(), 1e-6))
    for _ in range(50):
        mu = np.clip(np.exp(Z @ beta), 1e-8, None)
        W = np.diag(mu)
        try:
            step = np.linalg.solve(Z.T @ W @ Z + 1e-8 * np.eye(3), Z.T @ (y - mu))
        except np.linalg.LinAlgError:
            return None
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    Zall = np.column_stack([np.ones(nbins), centers - cutoff, (centers - cutoff) ** 2])
    pred = np.exp(Zall @ beta)
    return counts, pred, centers, edges


def discontinuity_test(pvals, cutoff=0.05, window=0.04, nbins=16, donut=0.005) -> dict:
    """Excess mass just below the p-value threshold, against a smooth counterfactual."""
    p = np.asarray(pvals, float)
    p = p[np.isfinite(p)]
    res = _counterfactual_counts(p, cutoff, max(cutoff - window, 1e-6),
                                 cutoff + window, nbins, donut)
    if res is None:
        return {"test": "discontinuity", "note": "too few results near the cutoff"}
    counts, pred, centers, _ = res
    inner_below = (centers < cutoff) & (np.abs(centers - cutoff) <= donut)
    obs = float(counts[inner_below].sum())
    exp = float(pred[inner_below].sum())
    if exp < 5:
        return {"test": "discontinuity", "note": "counterfactual too thin to test"}
    pval = float(stats.poisson.sf(obs - 1, exp))
    return {"test": "discontinuity", "n": int(counts.sum()), "cutoff": cutoff,
            "observed_just_below": obs, "counterfactual_just_below": round(exp, 2),
            "excess_mass_ratio": round(obs / exp, 3), "p_value": pval,
            "reads": "excess_mass_ratio >> 1 with small p_value => bunching just below the threshold"}


# --------------------------------------------------------------------------
# 6. Caliper test on z-statistics (Gerber & Malhotra; Brodeur et al.).
# --------------------------------------------------------------------------

def caliper_test(zstats, center=1.96, caliper=0.20, window=1.0,
                 nbins=20, naive=True) -> dict:
    """Gerber-Malhotra caliper, reported both naively and against a counterfactual.

    The naive form tests share_above == 0.5 inside the caliper. That null is
    correct only if the density of |z| is locally flat, which it is not when a
    real effect is present. The counterfactual form is the one to trust.
    """
    z = np.abs(np.asarray(zstats, float))
    z = z[np.isfinite(z)]
    band = z[(z >= center - caliper) & (z <= center + caliper)]
    n = band.size
    out = {"test": "caliper", "n": int(n), "center": center, "caliper": caliper}
    if n < 20:
        return {**out, "note": "too few statistics in the caliper"}
    above = int(np.sum(band > center))
    if naive:
        out["naive_share_above"] = above / n
        out["naive_p_value"] = float(
            stats.binomtest(above, n, 0.5, alternative="greater").pvalue)
    res = _counterfactual_counts(z, center, center - window, center + window,
                                 nbins, caliper)
    if res is None:
        return {**out, "p_value": out.get("naive_p_value"),
                "note": "counterfactual unavailable; naive result reported"}
    counts, pred, centers, _ = res
    inner_above = (centers > center) & (np.abs(centers - center) <= caliper)
    obs = float(counts[inner_above].sum())
    exp = float(pred[inner_above].sum())
    if exp < 5:
        return {**out, "p_value": out.get("naive_p_value"),
                "note": "counterfactual too thin; naive result reported"}
    out.update({
        "observed_just_above": obs, "counterfactual_just_above": round(exp, 2),
        "excess_mass_ratio": round(obs / exp, 3),
        "p_value": float(stats.poisson.sf(obs - 1, exp)),
        "reads": "excess_mass_ratio >> 1 => statistics pushed over the significance line",
    })
    return out


# --------------------------------------------------------------------------
# 7. Simonsohn's p-curve power estimate.
# --------------------------------------------------------------------------

def pcurve_power(pvals, alpha=0.05) -> dict:
    ps = _significant(pvals, alpha)
    if ps.size < 5:
        return {"test": "pcurve_power", "n": int(ps.size), "note": "too few significant results"}
    zc = stats.norm.isf(alpha / 2)

    def loss(ncp):
        pp = stats.norm.sf(zc - ncp) + stats.norm.cdf(-zc - ncp)
        ppv = np.clip((stats.norm.sf(stats.norm.isf(ps / 2) - ncp)
                       + stats.norm.cdf(-stats.norm.isf(ps / 2) - ncp)) / pp, 1e-9, 1)
        return float(np.mean(ppv) - 0.5) ** 2

    grid = np.linspace(0, 6, 601)
    ncp = float(grid[np.argmin([loss(g) for g in grid])])
    power = float(stats.norm.sf(zc - ncp) + stats.norm.cdf(-zc - ncp))
    return {"test": "pcurve_power", "n": int(ps.size), "implied_ncp": ncp,
            "estimated_power": power,
            "reads": "power near alpha => the significant findings carry no evidential value"}


def report(pvals=None, zstats=None, alpha=0.05, seed=0) -> dict:
    """Run the full detection battery. Supply p-values, z-statistics, or both."""
    if pvals is None and zstats is None:
        raise ValueError("supply pvals or zstats")
    if pvals is None:
        pvals = 2 * stats.norm.sf(np.abs(np.asarray(zstats, float)))
    if zstats is None:
        zstats = stats.norm.isf(np.asarray(pvals, float) / 2)
    out = {
        "n_total": int(np.isfinite(np.asarray(pvals, float)).sum()),
        "n_significant": int(_significant(pvals, alpha).size),
        "tests": [
            binomial_test(pvals, alpha), fisher_test(pvals, alpha),
            stouffer_test(pvals, alpha), lcm_test(pvals, alpha, seed=seed),
            discontinuity_test(pvals), caliper_test(zstats),
            pcurve_power(pvals, alpha),
        ],
    }
    SHAPE = {"binomial", "fisher", "stouffer", "lcm_monotonicity"}
    def _flags(t):
        return ((isinstance(t.get("p_value"), float) and t["p_value"] < 0.05)
                or (isinstance(t.get("p_left_skew"), float) and t["p_left_skew"] < 0.05))
    flags = [t["test"] for t in out["tests"] if _flags(t)]
    shape_flags = [t for t in flags if t in SHAPE]
    bunch_flags = [t for t in flags if t not in SHAPE]
    out["n_tests_flagging"] = len(flags)
    out["flagged_by"] = flags
    out["shape_tests_flagging"] = shape_flags
    out["bunching_tests_flagging"] = bunch_flags
    # Shape tests carry clean nulls; bunching tests alone are weak evidence
    # because a rising density around the threshold mimics bunching.
    out["verdict"] = (
        "strong evidence of p-hacking / selective reporting"
        if len(shape_flags) >= 2 else
        "moderate evidence of p-hacking" if shape_flags and bunch_flags else
        "weak / ambiguous signal -- bunching only, shape tests clean"
        if bunch_flags else
        "some evidence of p-hacking" if shape_flags else
        "no distributional evidence of p-hacking")
    out["caveat"] = ("These are tests on the distribution across many studies. "
                     "They cannot establish that any individual result was p-hacked.")
    return out
