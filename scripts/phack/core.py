"""
Estimation core for the p-hacking skills toolkit.

Deliberately small and dependency-light: OLS with multi-way fixed-effect
absorption, HC0-HC3 robust and one/two-way cluster-robust variance, plus the
data transforms that the p-hacking literature identifies as researcher degrees
of freedom (Stefan & Schoenbrodt 2023, strategies 4/6/7/8/10).

Everything returns a plain dict so results are trivially serialisable into the
specification ledger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

__all__ = [
    "TRANSFORMS", "OUTLIER_RULES", "apply_transform", "flag_outliers",
    "absorb", "fit_ols", "impute",
]

# --------------------------------------------------------------------------
# Variable transforms (researcher degree of freedom: "variable transformation")
# --------------------------------------------------------------------------

def _log(x: np.ndarray) -> np.ndarray:
    shift = 0.0
    finite = x[np.isfinite(x)]
    if finite.size and finite.min() <= 0:
        shift = 1.0 - finite.min()
    return np.log(x + shift)


TRANSFORMS = {
    "level":  lambda x: x,
    "log":    _log,
    "log1p":  lambda x: np.log1p(np.clip(x, -0.999999, None)),
    "sqrt":   lambda x: np.sqrt(np.clip(x - np.nanmin(x), 0, None)),
    "std":    lambda x: (x - np.nanmean(x)) / (np.nanstd(x, ddof=1) or 1.0),
    "rank":   lambda x: stats.rankdata(x, nan_policy="omit") / np.sum(np.isfinite(x)),
    "inv":    lambda x: 1.0 / np.where(np.abs(x) < 1e-9, np.nan, x),
    "square": lambda x: x ** 2,
    "winsor1": lambda x: np.clip(x, np.nanpercentile(x, 1), np.nanpercentile(x, 99)),
    "winsor5": lambda x: np.clip(x, np.nanpercentile(x, 5), np.nanpercentile(x, 95)),
}


def apply_transform(x: pd.Series, name: str) -> pd.Series:
    if name not in TRANSFORMS:
        raise KeyError(f"unknown transform {name!r}; known: {sorted(TRANSFORMS)}")
    return pd.Series(TRANSFORMS[name](x.to_numpy(dtype=float)), index=x.index)


# --------------------------------------------------------------------------
# Outlier rules (researcher degree of freedom: "outlier exclusion")
# --------------------------------------------------------------------------

def _sd(x, k):
    m, s = np.nanmean(x), np.nanstd(x, ddof=1)
    return np.abs(x - m) > k * s


def _iqr(x, k):
    q1, q3 = np.nanpercentile(x, 25), np.nanpercentile(x, 75)
    iqr = q3 - q1
    return (x < q1 - k * iqr) | (x > q3 + k * iqr)


def _mad(x, k):
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med)) * 1.4826
    return np.abs(x - med) > k * (mad or 1.0)


OUTLIER_RULES = {
    "none":  lambda x: np.zeros(len(x), dtype=bool),
    "sd2":   lambda x: _sd(x, 2.0),
    "sd2.5": lambda x: _sd(x, 2.5),
    "sd3":   lambda x: _sd(x, 3.0),
    "iqr1.5": lambda x: _iqr(x, 1.5),
    "iqr3":  lambda x: _iqr(x, 3.0),
    "mad3":  lambda x: _mad(x, 3.0),
    "pct1":  lambda x: (x < np.nanpercentile(x, 1)) | (x > np.nanpercentile(x, 99)),
    "pct5":  lambda x: (x < np.nanpercentile(x, 5)) | (x > np.nanpercentile(x, 95)),
}


def flag_outliers(x: pd.Series, rule: str) -> np.ndarray:
    if rule not in OUTLIER_RULES:
        raise KeyError(f"unknown outlier rule {rule!r}; known: {sorted(OUTLIER_RULES)}")
    return OUTLIER_RULES[rule](x.to_numpy(dtype=float))


# --------------------------------------------------------------------------
# Missing-data handling (researcher degree of freedom: "favourable imputation")
# --------------------------------------------------------------------------

def impute(df: pd.DataFrame, cols, method: str) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out or not out[c].isna().any():
            continue
        s = out[c]
        if method == "listwise":
            continue
        elif method == "mean":
            out[c] = s.fillna(s.mean())
        elif method == "median":
            out[c] = s.fillna(s.median())
        elif method == "zero":
            out[c] = s.fillna(0.0)
        elif method == "ffill":
            out[c] = s.ffill().bfill()
        elif method == "interp":
            out[c] = s.interpolate(limit_direction="both")
        else:
            raise KeyError(f"unknown imputation {method!r}")
    return out


# --------------------------------------------------------------------------
# Multi-way fixed-effect absorption by alternating projections
# --------------------------------------------------------------------------

def absorb(M: np.ndarray, groups: list[np.ndarray], tol=1e-9, maxiter=200):
    """Within-transform M on one or more grouping vectors.

    Returns (residualised M, number of absorbed parameters). One-way is exact
    in a single pass; multi-way iterates (Guimaraes-Portugal / Correia).
    """
    if not groups:
        return M, 0
    M = np.asarray(M, dtype=float).copy()
    codes = [pd.factorize(g)[0] for g in groups]
    ncat = [int(c.max()) + 1 for c in codes]
    for _ in range(maxiter):
        prev = M.copy()
        for c, k in zip(codes, ncat):
            sums = np.zeros((k, M.shape[1]))
            np.add.at(sums, c, M)
            counts = np.bincount(c, minlength=k).astype(float)[:, None]
            M -= sums[c] / counts[c]
        if len(codes) == 1 or np.max(np.abs(M - prev)) < tol:
            break
    # absorbed parameters: first FE full, subsequent ones minus the shared intercept
    k_absorbed = ncat[0] + sum(n - 1 for n in ncat[1:])
    return M, k_absorbed


# --------------------------------------------------------------------------
# OLS with robust / clustered variance
# --------------------------------------------------------------------------

def _meat_cluster(X: np.ndarray, u: np.ndarray, g: np.ndarray) -> np.ndarray:
    codes, uniq = pd.factorize(g)
    G = len(uniq)
    k = X.shape[1]
    meat = np.zeros((k, k))
    Xu = X * u[:, None]
    sums = np.zeros((G, k))
    np.add.at(sums, codes, Xu)
    meat = sums.T @ sums
    return meat, G


def fit_ols(y: np.ndarray, X: np.ndarray, *, vcov="hc1", cluster=None,
            k_absorbed=0, target=0):
    """OLS of y on X (X must already include a constant unless FE absorbed).

    vcov: 'iid' | 'hc0' | 'hc1' | 'hc2' | 'hc3' | 'cluster' | 'twoway'
    cluster: array, or (array, array) for two-way.
    target: column index of X whose coefficient is the estimand.
    """
    y = np.asarray(y, dtype=float).ravel()
    X = np.asarray(X, dtype=float)
    n, k = X.shape
    XtX = X.T @ X
    XtXi = np.linalg.pinv(XtX)
    beta = XtXi @ (X.T @ y)
    u = y - X @ beta
    dof = max(n - k - k_absorbed, 1)

    if vcov in ("cluster", "twoway"):
        if cluster is None:
            raise ValueError("cluster vcov requested without cluster variable")
        if vcov == "cluster":
            meat, G = _meat_cluster(X, u, np.asarray(cluster))
            adj = (G / max(G - 1, 1)) * ((n - 1) / dof)
            V = adj * (XtXi @ meat @ XtXi)
            g_eff = G
        else:
            g1, g2 = cluster
            g1, g2 = np.asarray(g1), np.asarray(g2)
            m1, G1 = _meat_cluster(X, u, g1)
            m2, G2 = _meat_cluster(X, u, g2)
            inter = pd.factorize(pd.Series(list(zip(g1, g2))))[0]
            m12, G12 = _meat_cluster(X, u, inter)
            Gm = min(G1, G2)
            adj = (Gm / max(Gm - 1, 1)) * ((n - 1) / dof)
            V = adj * (XtXi @ (m1 + m2 - m12) @ XtXi)
            g_eff = Gm
        dfree = max(g_eff - 1, 1)
    else:
        if vcov == "iid":
            s2 = (u @ u) / dof
            V = s2 * XtXi
        else:
            h = np.einsum("ij,jk,ik->i", X, XtXi, X)
            if vcov == "hc0":
                w = u ** 2
            elif vcov == "hc1":
                w = u ** 2 * (n / dof)
            elif vcov == "hc2":
                w = u ** 2 / np.clip(1 - h, 1e-10, None)
            elif vcov == "hc3":
                w = u ** 2 / np.clip(1 - h, 1e-10, None) ** 2
            else:
                raise KeyError(f"unknown vcov {vcov!r}")
            V = XtXi @ (X.T * w) @ X @ XtXi
        dfree = dof

    diag = np.diag(V)
    psd_ok = bool(np.all(diag > 0) and np.all(np.linalg.eigvalsh((V + V.T) / 2) > -1e-10))
    se = np.sqrt(np.clip(diag, 0, None))
    b = float(beta[target])
    s = float(se[target]) if se[target] > 0 else float("nan")
    t = b / s if s and np.isfinite(s) else float("nan")
    p = float(2 * stats.t.sf(abs(t), dfree)) if np.isfinite(t) else float("nan")
    crit = stats.t.ppf(0.975, dfree)
    return {
        "coef": b, "se": s, "t": t, "p": p,
        "ci_low": b - crit * s, "ci_high": b + crit * s,
        "n": int(n), "df": int(dfree), "k": int(k + k_absorbed),
        "resid_var": float((u @ u) / dof),
        "psd_ok": psd_ok,
    }


# --------------------------------------------------------------------------
# Regression discontinuity: local polynomial with kernel weights
# --------------------------------------------------------------------------

KERNELS = {
    "triangular":   lambda u: np.clip(1 - np.abs(u), 0, None),
    "uniform":      lambda u: (np.abs(u) <= 1).astype(float),
    "epanechnikov": lambda u: np.clip(0.75 * (1 - u ** 2), 0, None),
}


def rot_bandwidth(x: np.ndarray) -> float:
    """Silverman rule-of-thumb pilot bandwidth. Deliberately *not* rdrobust's
    MSE-optimal choice: the point of the grid is to walk multiples of a
    defensible pilot, and every multiple in [0.5, 2] is citable somewhere."""
    x = x[np.isfinite(x)]
    iqr = np.subtract(*np.percentile(x, [75, 25]))
    s = min(np.std(x, ddof=1), iqr / 1.349) if iqr > 0 else np.std(x, ddof=1)
    return float(1.84 * s * x.size ** (-0.2))


def fit_rdd(y, x, *, h, kernel="triangular", poly=1, donut=0.0, cutoff=0.0,
            controls=None, vcov="hc1", cluster=None):
    """Sharp RDD by weighted local polynomial. Estimand: jump at the cutoff."""
    y = np.asarray(y, float); x = np.asarray(x, float) - cutoff
    keep = (np.abs(x) <= h) & (np.abs(x) > donut) & np.isfinite(y) & np.isfinite(x)
    if keep.sum() < 4 * (poly + 1) + 2:
        raise ValueError(f"only {int(keep.sum())} observations inside bandwidth {h:.3g}")
    y, x = y[keep], x[keep]
    D = (x >= 0).astype(float)
    cols = [np.ones(x.size), D]
    for k in range(1, poly + 1):
        cols += [x ** k, D * x ** k]
    if controls is not None and np.size(controls):
        C = np.atleast_2d(np.asarray(controls, float))
        C = C.T if C.shape[0] != len(keep) else C
        cols += list(C[keep].T)
    X = np.column_stack(cols)
    w = KERNELS[kernel](x / h)
    sw = np.sqrt(w)
    cl = None if cluster is None else np.asarray(cluster)[keep]
    r = fit_ols(y * sw, X * sw[:, None], vcov=vcov, cluster=cl, target=1)
    r.update(n_left=int((D == 0).sum()), n_right=int(D.sum()), bandwidth=float(h))
    return r


# --------------------------------------------------------------------------
# Two-stage least squares
# --------------------------------------------------------------------------

def fit_2sls(y, d, Z, *, controls=None, vcov="hc1", cluster=None, estimator="2sls"):
    """IV for a single endogenous regressor d, instruments Z, exogenous controls.

    Returns the structural coefficient on d plus the first-stage F on the
    excluded instruments, which is itself a searchable object.
    """
    y = np.asarray(y, float); d = np.asarray(d, float)
    Z = np.atleast_2d(np.asarray(Z, float)); Z = Z.T if Z.shape[0] != y.size else Z
    n = y.size
    W = np.ones((n, 1))
    if controls is not None and np.size(controls):
        C = np.atleast_2d(np.asarray(controls, float)); C = C.T if C.shape[0] != n else C
        W = np.column_stack([W, C])
    X = np.column_stack([W, d])                 # structural regressors, d last
    Zf = np.column_stack([W, Z])                # full instrument matrix
    # first stage
    g, *_ = np.linalg.lstsq(Zf, d, rcond=None)
    dhat = Zf @ g
    u1 = d - dhat
    # F on excluded instruments: compare with restricted first stage on W only
    g0, *_ = np.linalg.lstsq(W, d, rcond=None)
    u0 = d - W @ g0
    q = Z.shape[1]; df2 = n - Zf.shape[1]
    F = float(((u0 @ u0 - u1 @ u1) / q) / ((u1 @ u1) / max(df2, 1)))
    if estimator == "liml":
        # k-class with kappa = smallest eigenvalue of the LIML problem
        Y = np.column_stack([y, d])
        MW = Y - W @ np.linalg.lstsq(W, Y, rcond=None)[0]
        MZ = Y - Zf @ np.linalg.lstsq(Zf, Y, rcond=None)[0]
        # smallest root of |Y'M_W Y - kappa Y'M_Z Y| = 0; generalised eigenproblem
        # rather than pinv(A) @ B, which returns garbage when Y'M_Z Y is singular
        from scipy import linalg as _sl
        ev = _sl.eigvals(MW.T @ MW, MZ.T @ MZ)
        ev = ev[np.isfinite(ev)].real
        kappa = float(ev.min()) if ev.size else 1.0
        kappa = max(kappa, 1.0)
    else:
        kappa = 1.0
    Xhat = np.column_stack([W, kappa * dhat + (1 - kappa) * d])
    XhX = Xhat.T @ X
    beta = np.linalg.solve(XhX, Xhat.T @ y)
    u = y - X @ beta
    k = X.shape[1]; dof = max(n - k, 1)
    A = np.linalg.inv(XhX)
    if vcov == "iid":
        V = (u @ u) / dof * A @ (Xhat.T @ Xhat) @ A.T
        dfree = dof
    elif vcov in ("hc0", "hc1"):
        scale = n / dof if vcov == "hc1" else 1.0
        V = scale * A @ (Xhat.T * (u ** 2)) @ Xhat @ A.T
        dfree = dof
    elif vcov == "cluster":
        meat, G = _meat_cluster(Xhat, u, np.asarray(cluster))
        V = (G / max(G - 1, 1)) * ((n - 1) / dof) * A @ meat @ A.T
        dfree = max(G - 1, 1)
    else:
        raise KeyError(f"2SLS supports iid/hc0/hc1/cluster, not {vcov!r}")
    j = k - 1
    b = float(beta[j]); s = float(np.sqrt(max(V[j, j], 0)))
    t = b / s if s > 0 else float("nan")
    crit = stats.t.ppf(0.975, dfree)
    return {"coef": b, "se": s, "t": t,
            "p": float(2 * stats.t.sf(abs(t), dfree)) if np.isfinite(t) else float("nan"),
            "ci_low": b - crit * s, "ci_high": b + crit * s, "n": int(n),
            "df": int(dfree), "k": int(k), "resid_var": float((u @ u) / dof),
            "psd_ok": bool(V[j, j] > 0), "first_stage_F": F, "n_instruments": int(q),
            "kappa": kappa}
