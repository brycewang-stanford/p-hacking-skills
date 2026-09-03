---
name: forking-paths
description: Map the garden of forking paths for a concrete econometric design and turn it into a machine-readable design card that the specification-search engine can walk. Use when asked how many defensible analyses a dataset or research design admits, to enumerate researcher degrees of freedom for a specific DiD, IV, RDD, synthetic-control, panel or cross-sectional study, to build or validate a design card, or to size a multiverse before running it.
---

# Mapping the garden

Before anything is estimated, work out how large the space of defensible
analyses is. That number is the multiplicity that honest inference has to pay
for, and it is almost always larger than researchers expect.

## Step 1 — read the design-specific map

`references/econ-dof-maps.md` lists, per design, the choices a referee would
accept without comment. Take only the ones that are genuinely defensible **for
this dataset**: a bandwidth grid is real for an RDD and meaningless for an RCT.

## Step 2 — write a design card

A design card is JSON. Each key is one axis of the grid; omitting a key
collapses that axis to a single default, which is how a pre-registered analysis
is encoded.

```json
{
  "name": "example-did",
  "design": "did",
  "outcomes": ["y", "y_alt"],
  "treatment": "treat",
  "controls_pool": ["x1", "x2", "x3", "x4"],
  "control_policy": "all_subsets",
  "fixed_effects": [[], ["unit"], ["unit", "year"], ["region", "year"]],
  "vcov": ["hc1", "cluster", "twoway"],
  "cluster": [null, "unit", "region", ["unit", "year"]],
  "outcome_transforms": ["level", "log", "std"],
  "outlier_rules": ["none", "sd3", "iqr1.5"],
  "imputation": ["listwise", "mean"],
  "subsamples": {"early": "year < 2010", "late": "year >= 2010"},
  "panel_unit": "unit",
  "panel_time": "year"
}
```

Full key reference: `grid.DEFAULTS` in `scripts/phack/grid.py`. The loader
rejects unknown keys rather than silently ignoring them, because a typo that
quietly drops an axis makes the multiplicity count wrong.

Constraints the enumerator enforces for you: a cluster variable only pairs with
a clustered `vcov`, a two-way `vcov` only with a pair of cluster variables, and
duplicate specifications are collapsed by content hash.

## Step 3 — size it before you walk it

```bash
python scripts/phack_cli.py size CARD
```

```
{"n_specs": 12960, "dimensions": {"outcomes": 3, "control_sets": 16, ...}}
```

Sizing is the deliverable on its own. A design admitting 12,960 defensible
analyses cannot support a 0.05 threshold on any single one of them: under the
null the smallest of ~13,000 correlated p-values is routinely below 0.001. Say
that number out loud before estimating anything.

## Step 4 — mark the pre-registered path

Pick the single specification you would have committed to in advance and record
its key. `phack search --prereg-key KEY` then reports how far the best
specification travelled from it, in both effect size and log p-value. Without
this anchor there is no way to distinguish a search from an analysis.

## Honest defaults when building a card

- **Include the ugly options.** A grid containing only the specifications you
  like understates multiplicity and overstates robustness.
- **Exclude the indefensible ones.** A grid padded with analyses no referee
  would accept inflates the correction and lets a weak result hide behind a
  large denominator. Both directions are cheating.
- **Weighting, timing and aggregation are axes too.** They are the most
  commonly forgotten and among the most consequential.
