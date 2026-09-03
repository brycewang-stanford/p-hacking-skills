"""
Walk the specification universe, log every step, and calibrate the walk.

Two entry points:
  run()               -- fit every specification, return the ledger
  null_calibration()  -- re-run the *identical* search under an enforced null,
                         giving the reference distribution of min-p and the
                         t-statistic null matrix that Romano-Wolf needs.

Nothing here is hidden: a search that cannot produce a complete ledger is a
bug, not a feature.
"""
from __future__ import annotations

import time
import numpy as np
import pandas as pd

from . import core, grid, inference


def _fit_spec(df, spec, card):
    built = grid.build(df, spec, card)
    if isinstance(built, dict):
        if built["design"] == "rdd":
            return core.fit_rdd(built["y"], built["x"], h=built["h"], kernel=built["kernel"],
                                poly=built["poly"], donut=built["donut"], cutoff=built["cutoff"],
                                controls=built["controls"], vcov=built["vcov"],
                                cluster=built["cluster"])
        return core.fit_2sls(built["y"], built["d"], built["Z"], controls=built["controls"],
                             vcov=built["vcov"], cluster=built["cluster"],
                             estimator=built["estimator"])
    y, X, cl, ka, has_const = built
    target = 1 if has_const else 0
    return core.fit_ols(y, X, vcov=spec.vcov, cluster=cl,
                        k_absorbed=ka, target=target)


def run(df: pd.DataFrame, card: dict, *, specs=None, progress=False) -> pd.DataFrame:
    """Fit every specification. Failures are recorded, never silently dropped."""
    specs = specs if specs is not None else grid.enumerate_specs(card)
    rows = []
    t0 = time.time()
    for s in specs:
        rec = {
            "idx": s.idx, "key": s.key(), "label": s.label(),
            "outcome": s.outcome, "n_controls": len(s.controls),
            "controls": "+".join(s.controls) or "none",
            "fe": "+".join(s.fe) or "none", "vcov": s.vcov,
            "cluster": str(s.cluster), "y_transform": s.y_transform,
            "d_transform": s.d_transform, "outlier_rule": s.outlier_rule,
            "imputation": s.imputation, "subsample": s.subsample, "lag": s.lag,
            "bandwidth": (s.bandwidth[1] if isinstance(s.bandwidth, tuple) else s.bandwidth),
            "kernel": s.kernel if s.bandwidth is not None else None,
            "poly": s.poly if s.bandwidth is not None else None,
            "donut": s.donut if s.bandwidth is not None else None,
            "instruments": "+".join(s.instruments) or None,
            "iv_estimator": s.iv_estimator if s.instruments else None,
        }
        try:
            rec.update(_fit_spec(df, s, card))
            rec["status"] = "ok"
        except Exception as exc:                       # noqa: BLE001
            rec.update({"coef": np.nan, "se": np.nan, "t": np.nan, "p": np.nan,
                        "ci_low": np.nan, "ci_high": np.nan, "n": 0,
                        "psd_ok": False,
                        "status": f"error: {type(exc).__name__}: {exc}"})
        rows.append(rec)
        if progress and len(rows) % 250 == 0:
            print(f"  {len(rows)}/{len(specs)} specs  ({time.time()-t0:.1f}s)", flush=True)
    led = pd.DataFrame(rows)
    led["abs_t"] = led["t"].abs()
    return led


def flag_pathologies(ledger: pd.DataFrame, card: dict) -> pd.DataFrame:
    """Mark specifications that are searchable but not defensible.

    A search that reports one of these as its headline is not merely p-hacked,
    it is wrong. Keeping them in the ledger and flagged is the honest move;
    silently dropping them hides a real failure mode of automated search.
    """
    led = ledger.copy()
    ok = led["status"] == "ok"
    few_clusters = led["df"].fillna(1e9) < 15
    led["flag_nonpsd_vcov"] = ok & ~led.get("psd_ok", True).fillna(False)
    led["flag_few_clusters"] = ok & few_clusters & led["vcov"].isin(["cluster", "twoway"])
    led["flag_tiny_sample"] = ok & (led["n"] < 0.25 * led["n"].max())
    led["flag_implausible_precision"] = ok & (
        led["se"] < 0.1 * led.loc[ok, "se"].median())
    if "first_stage_F" in led:
        led["flag_weak_instruments"] = ok & (led["first_stage_F"].fillna(np.inf) < 10)
    if "n_left" in led:
        led["flag_thin_rdd_side"] = ok & ((led["n_left"].fillna(np.inf) < 20) |
                                          (led["n_right"].fillna(np.inf) < 20))
    led["n_flags"] = led.filter(like="flag_").sum(axis=1)
    return led


# --------------------------------------------------------------------------
# Null calibration
# --------------------------------------------------------------------------

def _draw_null(df, card, rng, scheme):
    d = df.copy()
    t = card["treatment"]
    if card.get("design") == "rdd":
        # Treatment is a deterministic function of the running variable, so it
        # cannot be permuted. Enforce the null by permuting the OUTCOME within
        # narrow bins of the running variable: this preserves the smooth
        # relationship y(x) and removes any jump at the cutoff.
        x = d[card["running"]].to_numpy(float)
        bins = pd.qcut(x, q=min(40, max(4, len(x) // 25)), labels=False, duplicates="drop")
        for oc in card["outcomes"]:
            d[oc] = d.groupby(bins)[oc].transform(lambda s: rng.permutation(s.to_numpy()))
        return d
    if card.get("design") == "iv" and scheme == "permute":
        # permute the instruments jointly (preserves d's endogeneity, kills relevance)
        idx = rng.permutation(len(d))
        for z in card["instruments_pool"]:
            d[z] = d[z].to_numpy()[idx]
        return d
    if scheme == "permute":
        d[t] = rng.permutation(d[t].to_numpy())
    elif scheme == "permute_within_unit":
        unit = card["panel_unit"]
        if not unit:
            raise ValueError("permute_within_unit needs panel_unit")
        d[t] = d.groupby(unit)[t].transform(lambda s: rng.permutation(s.to_numpy()))
    elif scheme == "permute_within_time":
        tt = card["panel_time"]
        if not tt:
            raise ValueError("permute_within_time needs panel_time")
        d[t] = d.groupby(tt)[t].transform(lambda s: rng.permutation(s.to_numpy()))
    elif scheme == "cluster_permute":
        unit = card["panel_unit"]
        if not unit:
            raise ValueError("cluster_permute needs panel_unit")
        ids = d[unit].unique()
        assign = dict(zip(ids, rng.permutation(
            d.groupby(unit)[t].first().reindex(ids).to_numpy())))
        d[t] = d[unit].map(assign)
    elif scheme == "gaussian":
        d[t] = rng.normal(size=len(d))
    else:
        raise KeyError(f"unknown null scheme {scheme!r}")
    return d


def null_calibration(df: pd.DataFrame, card: dict, *, B=200, scheme="permute",
                     seed=0, specs=None, max_specs=None, progress=False):
    """Re-run the search B times with the treatment made inert.

    Returns (min_p_null (B,), t_null (B,S), specs_used).
    `max_specs` thins the grid for speed; thinning is reported so the honest
    p-value is never quietly computed on a different search than the one run.
    """
    rng = np.random.default_rng(seed)
    specs = specs if specs is not None else grid.enumerate_specs(card)
    if max_specs and len(specs) > max_specs:
        pick = np.linspace(0, len(specs) - 1, max_specs).astype(int)
        specs = [specs[i] for i in pick]
    S = len(specs)
    min_p = np.full(B, np.nan)
    t_null = np.full((B, S), np.nan)
    for b in range(B):
        d = _draw_null(df, card, rng, scheme)
        ps, ts = [], []
        for s in specs:
            try:
                r = _fit_spec(d, s, card)
                ps.append(r["p"]); ts.append(r["t"])
            except Exception:                          # noqa: BLE001
                ps.append(np.nan); ts.append(np.nan)
        ps = np.asarray(ps, float)
        t_null[b] = ts
        min_p[b] = np.nanmin(ps) if np.isfinite(ps).any() else np.nan
        if progress and (b + 1) % 25 == 0:
            print(f"  null draw {b+1}/{B}", flush=True)
    return min_p, t_null, specs


def audit(ledger: pd.DataFrame, min_p_null=None, t_null=None,
          preregistered_key=None, alpha=0.05) -> dict:
    """Turn a ledger into the honest summary."""
    ok = ledger[ledger["status"] == "ok"]
    if ok.empty:
        return {"error": "no specification estimated successfully"}
    best = ok.loc[ok["p"].idxmin()]
    out = {
        "n_specs_enumerated": int(len(ledger)),
        "n_specs_estimated": int(len(ok)),
        "n_specs_failed": int((ledger["status"] != "ok").sum()),
        "best_spec": {
            "key": best["key"], "label": best["label"],
            "coef": float(best["coef"]), "se": float(best["se"]),
            "t": float(best["t"]), "p": float(best["p"]),
            "n": int(best["n"]),
            **({"first_stage_F": float(best["first_stage_F"])} if "first_stage_F" in best and pd.notna(best["first_stage_F"]) else {}),
            **({"bandwidth": float(best["bandwidth"])} if "bandwidth" in best and pd.notna(best["bandwidth"]) else {}),
        },
        "curve": inference.spec_curve_stats(ok["coef"], ok["p"], alpha=alpha),
        "bonferroni_p_of_best": float(min(best["p"] * len(ok), 1.0)),
        "sidak_p_of_best": float(1 - (1 - min(best["p"], 1.0)) ** len(ok)),
    }
    if preregistered_key is not None:
        pre = ok[ok["key"] == preregistered_key]
        if not pre.empty:
            pr = pre.iloc[0]
            out["preregistered"] = {
                "key": pr["key"], "label": pr["label"], "coef": float(pr["coef"]),
                "se": float(pr["se"]), "p": float(pr["p"]),
            }
            out["coef_inflation_vs_prereg"] = (
                float(best["coef"] / pr["coef"]) if pr["coef"] else float("inf"))
            out["log10_p_gain"] = float(
                -np.log10(max(best["p"], 1e-300)) + np.log10(max(pr["p"], 1e-300)))
    if min_p_null is not None:
        out["min_p_test"] = inference.min_p_test(float(best["p"]), min_p_null)
    if t_null is not None:
        keys = ok["key"].to_numpy()
        tobs = ok["t"].to_numpy()
        m = min(t_null.shape[1], len(tobs))
        rw = inference.romano_wolf(tobs[:m], t_null[:, :m])
        out["romano_wolf_p_of_best"] = float(rw[np.nanargmin(ok["p"].to_numpy()[:m])]) \
            if m else float("nan")
        out["n_specs_rw_survives"] = int(np.nansum(rw < alpha))
        meff = inference.effective_tests(t_null[:, :m])
        out["effective_tests"] = round(meff, 2)
        out["meff_adjusted_p_of_best"] = round(
            inference.meff_adjusted_p(float(best["p"]), meff), 6)
    return out
