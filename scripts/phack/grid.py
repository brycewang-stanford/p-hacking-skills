"""
Enumerate the specification universe ("garden of forking paths") from a design
card, and materialise each specification into an estimable design matrix.

The design card is JSON. Every key is a researcher degree of freedom drawn from
the taxonomy in references/taxonomy.md; leaving a key out collapses that
dimension to a single defensible default, which is how you encode a
pre-registered analysis.
"""
from __future__ import annotations

import itertools, json, hashlib
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from . import core

DEFAULTS = {
    "outcomes": None,            # list[str]; required
    "treatment": None,           # str; required
    "controls_pool": [],
    "control_policy": "nested",  # none | nested | all_subsets | leave_one_out
    "max_controls": None,
    "fixed_effects": [[]],       # list of lists of column names
    "vcov": ["hc1"],             # iid|hc0..hc3|cluster|twoway
    "cluster": [None],           # str, or [str,str] for twoway
    "outcome_transforms": ["level"],
    "treatment_transforms": ["level"],
    "outlier_rules": ["none"],
    "outlier_basis": "outcome",  # outcome | treatment | residual
    "imputation": ["listwise"],
    "subsamples": {},            # name -> pandas query string
    "weights": [None],
    "interactions": [[]],        # extra terms, each a list of "a*b" strings
    "lags": [0],                 # shift treatment by k periods (needs panel keys)
    "panel_unit": None,
    "panel_time": None,
    # --- RDD axes (design == "rdd"); treatment is 1{running >= cutoff}
    "running": None,
    "cutoff": 0.0,
    "bandwidth_multipliers": [1.0],   # multiples of the rule-of-thumb pilot
    "bandwidths": None,               # absolute bandwidths override multipliers
    "kernels": ["triangular"],
    "poly_orders": [1],
    "donuts": [0.0],
    # --- IV axes (design == "iv")
    "instruments_pool": [],
    "instrument_policy": "all",       # all | nested | all_subsets | leave_one_out
    "iv_estimators": ["2sls"],        # 2sls | liml
}

REQUIRED = ("outcomes", "treatment")


@dataclass
class Spec:
    """One point in the multiverse."""
    idx: int
    outcome: str
    treatment: str
    controls: tuple
    fe: tuple
    vcov: str
    cluster: object
    y_transform: str
    d_transform: str
    outlier_rule: str
    imputation: str
    subsample: str
    weight: object
    interactions: tuple
    lag: int
    bandwidth: object = None      # multiplier (float) or ("abs", value)
    kernel: str = "triangular"
    poly: int = 1
    donut: float = 0.0
    instruments: tuple = ()
    iv_estimator: str = "2sls"

    def label(self) -> str:
        bits = [
            f"y={self.outcome}:{self.y_transform}",
            f"d={self.treatment}:{self.d_transform}",
            f"ctl={len(self.controls)}",
            f"fe={'+'.join(self.fe) or 'none'}",
            f"se={self.vcov}{'/' + str(self.cluster) if self.cluster else ''}",
            f"out={self.outlier_rule}",
            f"imp={self.imputation}",
            f"sub={self.subsample}",
        ]
        if self.lag:
            bits.append(f"lag={self.lag}")
        if self.interactions:
            bits.append("int=" + ",".join(self.interactions))
        if self.weight:
            bits.append(f"w={self.weight}")
        if self.bandwidth is not None:
            bw = (f"{self.bandwidth[1]:g}abs" if isinstance(self.bandwidth, tuple)
                  else f"{self.bandwidth:g}x")
            bits.append(f"rdd=h{bw}/{self.kernel}/p{self.poly}/donut{self.donut:g}")
        if self.instruments:
            bits.append(f"iv={self.iv_estimator}:{'+'.join(self.instruments)}")
        return " | ".join(bits)

    def key(self) -> str:
        return hashlib.sha1(self.label().encode()).hexdigest()[:12]


def _control_sets(pool, policy, cap):
    pool = list(pool)
    if policy == "none" or not pool:
        return [tuple()]
    if policy == "nested":
        return [tuple(pool[:i]) for i in range(len(pool) + 1)]
    if policy == "leave_one_out":
        sets = [tuple(pool)]
        sets += [tuple(p for p in pool if p != drop) for drop in pool]
        sets.append(tuple())
        return sets
    if policy == "all_subsets":
        cap = len(pool) if cap is None else min(cap, len(pool))
        out = []
        for r in range(cap + 1):
            out.extend(itertools.combinations(pool, r))
        return out
    raise KeyError(f"unknown control_policy {policy!r}")


def load_card(path_or_dict) -> dict:
    card = dict(DEFAULTS)
    raw = path_or_dict
    if not isinstance(raw, dict):
        with open(raw) as fh:
            raw = json.load(fh)
    unknown = set(raw) - set(DEFAULTS) - {"name", "notes", "design", "seed", "preregistered"}
    design = raw.get("design", "ols")
    if design == "rdd" and not raw.get("running"):
        raise ValueError("design 'rdd' needs a 'running' column")
    if design == "iv" and not raw.get("instruments_pool"):
        raise ValueError("design 'iv' needs a non-empty 'instruments_pool'")
    if unknown:
        raise KeyError(f"unknown design-card keys: {sorted(unknown)}")
    card.update(raw)
    card.setdefault("design", "ols")
    if card["design"] == "rdd" and not card.get("treatment"):
        card["treatment"] = "__rdd_D__"
    for r in REQUIRED:
        if not card.get(r):
            raise ValueError(f"design card must set {r!r}")
    if isinstance(card["outcomes"], str):
        card["outcomes"] = [card["outcomes"]]
    return card


def _instrument_sets(pool, policy):
    pool = list(pool)
    if policy == "all":
        return [tuple(pool)]
    sets = _control_sets(pool, policy, None)
    return [z for z in sets if len(z) > 0]


def enumerate_specs(card: dict) -> list[Spec]:
    ctl_sets = _control_sets(card["controls_pool"], card["control_policy"], card["max_controls"])
    design = card.get("design", "ols")
    if design == "rdd":
        bws = ([("abs", float(b)) for b in card["bandwidths"]] if card["bandwidths"]
               else [float(m) for m in card["bandwidth_multipliers"]])
        rdd_axes = list(itertools.product(bws, card["kernels"], card["poly_orders"], card["donuts"]))
    else:
        rdd_axes = [(None, "triangular", 1, 0.0)]
    if design == "iv":
        iv_axes = list(itertools.product(_instrument_sets(card["instruments_pool"], card["instrument_policy"]),
                                         card["iv_estimators"]))
    else:
        iv_axes = [((), "2sls")]
    subs = card["subsamples"] or {"full": None}
    if "full" not in subs:
        subs = {"full": None, **subs}
    axes = itertools.product(
        card["outcomes"], ctl_sets,
        [tuple(f) for f in card["fixed_effects"]],
        card["vcov"], card["cluster"],
        card["outcome_transforms"], card["treatment_transforms"],
        card["outlier_rules"], card["imputation"],
        list(subs), card["weights"],
        [tuple(i) for i in card["interactions"]], card["lags"],
        rdd_axes, iv_axes,
    )
    specs, i = [], 0
    seen = set()
    for (y, ctl, fe, vc, cl, yt, dt, orule, imp, sub, w, ints, lag, rd, iv) in axes:
        if design == "rdd" and (fe or vc == "twoway"):
            continue                      # local polynomial: no FE, no two-way
        if design == "iv" and vc in ("twoway", "hc2", "hc3"):
            continue
        # a cluster variable is meaningless unless a clustered vcov was asked for
        if vc in ("cluster", "twoway") and cl is None:
            continue
        if vc not in ("cluster", "twoway") and cl is not None:
            continue
        if vc == "twoway" and not isinstance(cl, (list, tuple)):
            continue
        if vc == "cluster" and isinstance(cl, (list, tuple)):
            continue
        s = Spec(i, y, card["treatment"], ctl, fe, vc,
                 tuple(cl) if isinstance(cl, list) else cl,
                 yt, dt, orule, imp, sub, w, ints, lag,
                 bandwidth=rd[0], kernel=rd[1], poly=rd[2], donut=rd[3],
                 instruments=tuple(iv[0]), iv_estimator=iv[1])
        if s.key() in seen:
            continue
        seen.add(s.key())
        specs.append(s)
        i += 1
    return specs


def universe_size(card: dict) -> dict:
    """Report the size of the garden before walking it."""
    specs = enumerate_specs(card)
    dims = {
        "outcomes": len(card["outcomes"]),
        "control_sets": len(_control_sets(card["controls_pool"], card["control_policy"], card["max_controls"])),
        "fixed_effects": len(card["fixed_effects"]),
        "vcov_x_cluster": len({(s.vcov, s.cluster) for s in specs}),
        "outcome_transforms": len(card["outcome_transforms"]),
        "treatment_transforms": len(card["treatment_transforms"]),
        "outlier_rules": len(card["outlier_rules"]),
        "imputation": len(card["imputation"]),
        "subsamples": max(len(card["subsamples"] or {}), 1) + (0 if "full" in (card["subsamples"] or {}) else 1) - (1 if not card["subsamples"] else 0),
        "weights": len(card["weights"]),
        "interactions": len(card["interactions"]),
        "lags": len(card["lags"]),
    }
    if card.get("design") == "rdd":
        dims.update(bandwidths=len(card["bandwidths"] or card["bandwidth_multipliers"]),
                    kernels=len(card["kernels"]), poly_orders=len(card["poly_orders"]),
                    donuts=len(card["donuts"]))
    if card.get("design") == "iv":
        dims.update(instrument_sets=len(_instrument_sets(card["instruments_pool"], card["instrument_policy"])),
                    iv_estimators=len(card["iv_estimators"]))
    return {"n_specs": len(specs), "dimensions": dims}


# --------------------------------------------------------------------------
# Materialisation: Spec -> (y, X, cluster, k_absorbed)
# --------------------------------------------------------------------------

def build(df: pd.DataFrame, spec: Spec, card: dict):
    d = df
    if spec.subsample != "full":
        q = (card["subsamples"] or {})[spec.subsample]
        d = d.query(q)
    design = card.get("design", "ols")
    needed = [spec.outcome, *spec.controls, *spec.fe]
    if design == "rdd":
        needed.append(card["running"])
    else:
        needed.append(spec.treatment)
    needed += list(spec.instruments)
    if spec.cluster:
        needed += list(spec.cluster) if isinstance(spec.cluster, tuple) else [spec.cluster]
    if spec.weight:
        needed.append(spec.weight)
    for term in spec.interactions:
        needed.extend(term.split("*"))
    needed = [c for c in dict.fromkeys(needed) if c is not None]
    missing = [c for c in needed if c not in d.columns]
    if missing:
        raise KeyError(f"spec {spec.idx} references absent columns {missing}")
    d = d.loc[:, needed]

    if design == "rdd":
        d = d.assign(**{spec.treatment: (d[card["running"]] >= card["cutoff"]).astype(float)})
    numeric = [c for c in (spec.outcome, spec.treatment, *spec.controls, *spec.instruments) if c in d]
    d = core.impute(d, numeric, spec.imputation)

    if spec.lag:
        if not (card["panel_unit"] and card["panel_time"]):
            raise ValueError("lags require panel_unit and panel_time on the card")
        base = df.sort_values([card["panel_unit"], card["panel_time"]])
        lagged = base.groupby(card["panel_unit"])[spec.treatment].shift(spec.lag)
        d = d.assign(**{spec.treatment: lagged.reindex(d.index)})

    d = d.dropna()
    if len(d) < 10:
        raise ValueError(f"spec {spec.idx} left {len(d)} rows")

    y = core.apply_transform(d[spec.outcome], spec.y_transform)
    dd = core.apply_transform(d[spec.treatment], spec.d_transform)

    basis = {"outcome": y, "treatment": dd}.get(card["outlier_basis"], y)
    keep = ~core.flag_outliers(basis, spec.outlier_rule)
    y, dd, d = y[keep], dd[keep], d.loc[keep]

    cols = [dd.to_numpy(dtype=float)]
    for c in spec.controls:
        cols.append(d[c].to_numpy(dtype=float))
    for term in spec.interactions:
        a, b = term.split("*")
        cols.append(d[a].to_numpy(dtype=float) * d[b].to_numpy(dtype=float))
    X = np.column_stack(cols)
    yv = y.to_numpy(dtype=float)

    if design == "rdd":
        x = d[card["running"]].to_numpy(dtype=float)
        h = (spec.bandwidth[1] if isinstance(spec.bandwidth, tuple)
             else spec.bandwidth * core.rot_bandwidth(x - card["cutoff"]))
        ctl = X[:, 1:] if X.shape[1] > 1 else None
        return {"design": "rdd", "y": yv, "x": x, "h": h, "controls": ctl,
                "cluster": _cl(d, spec), "kernel": spec.kernel, "poly": spec.poly,
                "donut": spec.donut, "cutoff": card["cutoff"], "vcov": spec.vcov}
    if design == "iv":
        Z = np.column_stack([d[z].to_numpy(dtype=float) for z in spec.instruments])
        ctl = X[:, 1:] if X.shape[1] > 1 else None
        if spec.fe:                       # absorb FE from y, d, Z, controls alike
            blocks = [yv[:, None], X, Z]
            M, ka = core.absorb(np.column_stack(blocks), [d[f].to_numpy() for f in spec.fe])
            yv, X, Z = M[:, 0], M[:, 1:1 + X.shape[1]], M[:, 1 + X.shape[1]:]
            ctl = X[:, 1:] if X.shape[1] > 1 else None
        return {"design": "iv", "y": yv, "d": X[:, 0], "Z": Z, "controls": ctl,
                "cluster": _cl(d, spec), "vcov": spec.vcov, "estimator": spec.iv_estimator}

    groups = [d[f].to_numpy() for f in spec.fe]
    if groups:
        M, ka = core.absorb(np.column_stack([yv, X]), groups)
        yv, X = M[:, 0], M[:, 1:]
    else:
        X = np.column_stack([np.ones(len(yv)), X])
        ka = 0
        return yv, X, _cl(d, spec), ka, 1
    return yv, X, _cl(d, spec), ka, 0


def _cl(d, spec):
    if spec.cluster is None:
        return None
    if isinstance(spec.cluster, tuple):
        return (d[spec.cluster[0]].to_numpy(), d[spec.cluster[1]].to_numpy())
    return d[spec.cluster].to_numpy()
