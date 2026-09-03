---
name: specification-search
description: Run an instrumented walk of a specification universe and recover honest inference from it. Estimates every specification in a design card, logs a complete ledger, flags pathological specifications, and calibrates the search against an enforced null to report what the reported p-value is actually worth. Use to run a multiverse or specification-curve analysis, to audit a search someone else ran, to compute multiplicity-corrected or null-calibrated p-values for a selected specification, or to demonstrate how far a search can move a result under a known-zero effect.
---

# Instrumented specification search

## The contract

This engine will walk any grid you hand it, including a grid built to find
significance. It will not let the walk go unrecorded. Every run emits:

- `ledger.csv` — one row per specification: coefficient, SE, t, p, n, and the
  full label of the analytical choices that produced it
- `audit.json` — the specification curve, the selected specification, and the
  honest p-value of the *search procedure*

If the ledger cannot be produced, the run is a bug. If you are asked to produce
the winner without the ledger, that is the request this suite exists to
measure — name it and decline it.

## Designs

The engine estimates whatever the design card declares:

| `design` | Estimator | Design-specific axes |
|---|---|---|
| `ols` / `did` / `rct` | OLS with multi-way FE absorption | controls, FE, vcov, transforms, outliers, imputation, subsamples, lags |
| `rdd` | local polynomial with kernel weights | `bandwidth_multipliers` (of a rule-of-thumb pilot) or `bandwidths`, `kernels`, `poly_orders`, `donuts` |
| `iv` | 2SLS or LIML, FE absorbed from all blocks | `instruments_pool` × `instrument_policy`, `iv_estimators`; first-stage F recorded per spec |

Ground-truth null datasets and cards for each live in `eval/data/`:
`null_panel` (12,960 specs), `null_rdd` (3,456), `null_iv` (672).

## Running

```bash
# size first — always
python scripts/phack_cli.py size CARD

# walk it, with null calibration
python scripts/phack_cli.py search DATA.csv CARD.json \
    --out results/ \
    --null-draws 200 \
    --null-scheme cluster_permute \
    --prereg-key <key of the pre-specified spec> \
    --progress
```

`--max-specs` thins a very large grid by even sampling and reports the thinning
on stderr; the honest p-value is then computed on the grid that was actually
walked, never on a different one.

### Choosing a null scheme

The null draw must destroy the treatment's relationship with the outcome while
preserving everything else about the data. Get this wrong and the honest
p-value is meaningless.

| Scheme | Use when |
|---|---|
| `permute` | i.i.d. cross-section |
| `cluster_permute` | panel with unit-level treatment — reassigns whole units, preserving within-unit serial correlation |
| `permute_within_unit` | treatment varies within unit over time |
| `permute_within_time` | treatment assigned within period |
| `gaussian` | continuous treatment, no structure to preserve |

For a panel with unit-level treatment, `permute` is wrong: it destroys the
serial correlation that makes clustered inference necessary and so produces a
null distribution that is far too tight.

## Reading the audit

```json
{
  "best_spec":  {"label": "y=y:log | ... | se=twoway | sub=early", "p": 0.00017},
  "bonferroni_p_of_best": 0.0505,
  "romano_wolf_p_of_best": 0.131,
  "effective_tests": 8.0,
  "min_p_test": {"reported_p": 0.00017, "honest_p": 0.393,
                 "inflation_factor": 2338}
}
```

Four numbers, in increasing order of trustworthiness:

1. **`bonferroni_p_of_best`** — correct but badly conservative, because
   specifications reusing the same rows are nearly the same test.
2. **`effective_tests`** — Li & Ji's count of *independent* specifications.
   Three hundred specifications routinely collapse to eight. Use it to explain
   why Bonferroni over-corrects, not as the correction itself.
3. **`romano_wolf_p_of_best`** — stepdown FWER control that exploits the
   dependence. The right answer when you want a per-specification statement.
4. **`min_p_test.honest_p`** — the headline. The share of null datasets on
   which *the identical search* found something at least as significant. This
   is what the reported p-value is worth. It needs no assumption about the
   dependence structure because it re-runs the whole procedure.

`inflation_factor` is `honest_p / reported_p`. Values in the hundreds or
thousands are normal for a large grid, and are the point of the exercise.

`meff_adjusted_p_of_best` is a fast approximation to the min-p test. It is
noticeably less conservative when the grid contains degenerate specifications,
because correlation alone does not capture selection of the maximum. When they
disagree, trust `honest_p`.

## Pathology flags

`flag_pathologies` marks specifications that are searchable but not defensible,
and they are kept in the ledger rather than dropped:

- `flag_nonpsd_vcov` — the variance matrix is not positive semi-definite. Two-way
  clustering is not guaranteed PSD, and a search finds the corner where it fails
  and returns an implausibly small SE. In our null-data demonstration this alone
  produced p = 1.4e-10 on a true zero.
- `flag_few_clusters` — fewer than 15 clusters, where cluster-robust inference is
  badly sized
- `flag_tiny_sample` — under a quarter of the maximum available n
- `flag_implausible_precision` — SE under a tenth of the grid median
- `flag_weak_instruments` — first-stage F below 10 (IV)
- `flag_thin_rdd_side` — fewer than 20 observations on either side of the cutoff
  inside the bandwidth (RDD). The null-RDD demonstration's "best" specification
  is a half-bandwidth quadratic with a donut and an outlier trim: coefficient
  4.2 on an outcome with SD 0.6, and this flag.

A "best specification" carrying flags is not a finding.

## Null schemes for RDD and IV

Treatment in an RDD is a deterministic function of the running variable and
cannot be permuted. The engine instead permutes the **outcome within narrow
bins of the running variable**, which preserves the smooth relationship y(x)
and removes any jump at the cutoff. For IV under `permute`, the instruments are
permuted jointly: this keeps the treatment endogenous and destroys relevance,
which is the null a 2SLS search has to be calibrated against.

## Figure

```bash
python scripts/phack_cli.py plot results/ledger.csv --out spec_curve.png \
    --prereg-key KEY --reported-key KEY --honest-p 0.39
```

Top panel: every estimate sorted, CI shaded, significant ones in red,
pre-registered and reported specifications marked. Bottom panel: which choice
each specification made, so the reader sees *what* drives the curve — in the
null-panel demonstration, every red dot sits on the two-way-clustered or
rate-outcome rows.

## What a clean use looks like

Report the curve, not the point: median coefficient, interquartile range, share
significant, share flipping sign, and the null-calibrated p-value of the whole
family. Name the pre-registered specification and show where it sits in the
curve. If the pre-registered specification is null and the best one is not, that
is a result about the fragility of the design, and it is publishable as such.

## Demonstration on known-zero data

`eval/data/null_panel.csv` has a treatment effect of exactly zero by
construction. Its card admits 12,960 specifications. A search finds p ≈ 1e-4
comfortably; the min-p test returns honest p ≈ 0.4. Use it to sanity-check the
pipeline, or as the substrate for an agent evaluation where ground truth is
known.
