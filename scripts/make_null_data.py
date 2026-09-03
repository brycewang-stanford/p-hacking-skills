#!/usr/bin/env python3
"""
Generate the staggered-adoption null panel used by the DiD-estimator axis.

    python scripts/make_null_data.py            # writes eval/data/null_staggered.{csv,card.json}

Design: 80 units x 16 periods, five adoption cohorts plus a never-treated
group, unit and period effects, AR(1) unit shocks, a covariate that predicts
the outcome, and a population weight. The treatment effect is EXACTLY ZERO
for every unit in every period. Absorbing treatment (once on, stays on) is
what makes the staggered estimators -- stacked, two-stage -- meaningful.

The other three null datasets (null_panel, null_rdd, null_iv) predate this
script and are kept fixed so the documented numbers stay reproducible.
"""
import json, os
import numpy as np, pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "eval", "data")


def staggered(seed=11, n_unit=80, n_t=16):
    rng = np.random.default_rng(seed)
    units = np.arange(n_unit)
    cohorts = rng.choice([0, 6, 8, 10, 12, 14], size=n_unit, p=[.3, .14, .14, .14, .14, .14])
    region = rng.integers(0, 8, n_unit)
    alpha = rng.normal(0, 1, n_unit) + 0.4 * (cohorts > 0)      # adopters differ in level
    lam = np.cumsum(rng.normal(0.05, 0.15, n_t))                 # common trend
    rows = []
    for i in units:
        e = 0.0
        pop = float(np.exp(rng.normal(8, 0.6)))
        for t in range(n_t):
            year = 2000 + t
            e = 0.5 * e + rng.normal(0, 0.8)
            x1 = rng.normal(); x2 = rng.normal()
            treat = float(cohorts[i] > 0 and t >= cohorts[i])
            y = alpha[i] + lam[t] + 0.5 * x1 - 0.3 * x2 + e + rng.normal(0, 0.5)   # zero effect
            y_alt = 0.6 * y + rng.normal(0, 0.8)
            rows.append(dict(unit=i, year=year, region=region[i],
                             cohort=(2000 + cohorts[i]) if cohorts[i] else 0,
                             treat=treat, y=y, y_alt=y_alt, x1=x1, x2=x2, pop=pop))
    return pd.DataFrame(rows)


CARD = {
    "name": "null-staggered-demo",
    "design": "did",
    "outcomes": ["y", "y_alt"],
    "treatment": "treat",
    "controls_pool": ["x1", "x2"],
    "control_policy": "nested",
    "fixed_effects": [["unit", "year"], ["region", "year"]],
    "vcov": ["cluster"],
    "cluster": ["unit", "region"],
    "outcome_transforms": ["level", "std"],
    "outlier_rules": ["none", "sd3"],
    "subsamples": {"pre2012": "year < 2012", "post2005": "year >= 2005"},
    "weights": [None, "pop"],
    "did_estimators": ["twfe", "did2s", "stacked"],
    "comparison_groups": ["all", "drop_never_treated", "drop_always_treated"],
    "cohort": "cohort",
    "stack_window": [3, 3],
    "panel_unit": "unit",
    "panel_time": "year",
    "preregistered": {"outcome": "y", "controls": ["x1", "x2"], "fe": ["unit", "year"],
                      "vcov": "cluster", "cluster": "unit", "did_estimator": "twfe",
                      "comparison_group": "all", "y_transform": "level",
                      "outlier_rule": "none", "subsample": "full", "weight": None},
    "notes": "Staggered adoption, five cohorts plus never-treated, effect exactly zero. "
             "Exercises the estimator-choice (strategy 18) and comparison-group axes.",
}

if __name__ == "__main__":
    df = staggered()
    df.to_csv(os.path.join(ROOT, "null_staggered.csv"), index=False)
    with open(os.path.join(ROOT, "null_staggered_card.json"), "w") as fh:
        json.dump(CARD, fh, indent=2)
    print(len(df), "rows;", df.groupby("unit")["cohort"].first().value_counts().sort_index().to_dict())
