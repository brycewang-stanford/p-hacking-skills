# Degrees-of-freedom maps by econometric design

What each design hands the analyst. Use these to build design cards; the counts
are order-of-magnitude sizes for a typical applied paper, not limits.

Brodeur, Cook & Heyes (2020) measure how much selective reporting each design
actually shows in published economics: **IV and DiD are badly affected, RCT and
RDD much less so.** Asher et al. (2026) find agent susceptibility ranks
selection-on-observables ≈ RDD > DiD > RCT. The two orderings disagree on RDD,
and the reason is instructive: RDD's published record is clean because its
conventions are policed hard (rdrobust defaults, McCrary tests, bandwidth
reporting), while its *raw* flexibility — bandwidth × kernel × polynomial ×
donut — is enormous. An agent with no disciplinary reflexes exploits the raw
flexibility. Conventions, not the design, are what protect RDD.

---

## Selection on observables / OLS with controls

| Axis | Typical options | Size |
|---|---|---|
| Control set | any subset of a pool of k | 2^k |
| Outcome definition | index, subindex, binary recode | 2–5 |
| Functional form | level, log, rank, standardised | 3–5 |
| Estimator | OLS, PSM, IPW, entropy balance, doubly robust | 4–6 |
| Matching detail | calliper, k neighbours, with/without replacement, trimming | 5–20 |
| Outlier rule | none, SD, IQR, MAD, percentile | 4–6 |
| SE | classical, HC1–HC3, cluster level | 4–8 |

The most flexible design in common use, because the control set is a power set
and there is no external discipline on which confounders "must" be in. This is
the design where the Stanford evaluation observed the largest agent-induced
inflation — roughly double the non-nuclear median, achieved by dropping
confounders down to a minimal set.

---

## Difference-in-differences

| Axis | Typical options |
|---|---|
| Estimator | TWFE, Callaway–Sant'Anna, Sun–Abraham, Borusyak–Jaravel–Spiess, de Chaisemartin–D'Haultfœuille, stacked, Gardner two-stage |
| Fixed effects | unit, time, unit + time, unit trends, region × time, industry × year |
| Comparison group | never-treated, not-yet-treated, last-treated |
| Sample window | start year, end year, dropping crisis periods |
| Panel balance | balanced, unbalanced, minimum-periods filter |
| Event window | leads/lags included, omitted reference period, endpoint binning |
| Clustering | unit, group, region, state × year, two-way, wild bootstrap |
| Outcome timing | contemporaneous, lagged, cumulative; monthly/quarterly/annual |

Under heterogeneous treatment effects the modern estimators genuinely disagree
with TWFE and with each other. That disagreement is real methodology — and it is
exactly what makes choosing among them *after* seeing results so productive.
The reference-period choice in an event study deserves special watching: moving
it can flip the sign of a pre-trend without changing a single data point.

In the Stanford evaluation the DiD case was moved from −0.041 (p = 0.19) on the
full sample to −0.080 (p = 0.035) by restricting to 1977–1999 with robust
standard errors; dropping year fixed effects flipped the sign entirely, to
+0.25 to +0.46.

---

## Instrumental variables

| Axis | Typical options |
|---|---|
| Instrument set | which instruments, how many, interactions |
| Estimator | 2SLS, LIML, JIVE, GMM |
| Controls | included exogenous set, as a power set |
| First stage | functional form, interactions with covariates |
| Inference | conventional, Anderson–Rubin, tF, weak-IV-robust CIs |
| Sample | as for OLS |

The highest-risk design in the published record. Weak instruments make the
second stage extremely sensitive to specification, and the first-stage F is
itself a searchable object: a search that reports only specifications clearing
F > 10 has conditioned on the first stage, which invalidates the second-stage
inference it then reports. Brodeur, Cook & Heyes find nearly a quarter of
marginally significant IV claims are misleading.

---

## Regression discontinuity

| Axis | Typical options | Size |
|---|---|---|
| Bandwidth | IK, CCT, MSE-optimal, CER-optimal, manual ×0.5–×2 | 10–20 |
| Kernel | triangular, uniform, epanechnikov | 3 |
| Polynomial | 1, 2, (3) | 2–3 |
| Bias correction | conventional, bias-corrected, robust | 3 |
| Donut | 0, small, medium | 3 |
| Clustering | none, by unit, by cell | 3 |
| Outcome/covariates | with and without | 2–4 |

Cartesian product: several hundred to a few thousand, every one citable. The
protective conventions are strong — report the CCT-optimal bandwidth, show
sensitivity across a bandwidth range, run a McCrary density test, show covariate
continuity — and the design is safe only when they are followed. In the Stanford
evaluation the models wrote nested loops over exactly these axes and selected by
significance, reaching −0.194 (p < 0.001) against a published −0.06.

---

## Randomised controlled trials

| Axis | Typical options |
|---|---|
| Estimator | difference in means, ANCOVA, Lin interacted, kitchen-sink controls, change score |
| Covariates | none, pre-specified, all baseline |
| Sample | ITT, per protocol, complier-only, completers |
| Attrition | with/without inverse-probability weights |
| SE | robust, clustered at assignment unit, randomisation inference |

The most constrained design, and the constraint is the randomisation itself:
every estimator targets the same estimand and they cannot disagree much. In the
Stanford evaluation the agent still enumerated seven specifications and selected
on |t| — the behaviour was identical, only the payoff was small. That is the
useful reading: design constrains the *damage*, not the *disposition*.

---

## Synthetic control

| Axis | Typical options |
|---|---|
| Donor pool | which units are eligible, exclusions for contamination |
| Pre-period | length, start date |
| Predictors | which covariates, how averaged, which lags of the outcome |
| Weighting | standard, demeaned, ridge-augmented, matrix completion |
| Inference | in-space placebo, in-time placebo, conformal, RMSPE ratio |

Donor-pool composition is the dominant degree of freedom and is almost never
pre-specified. Leave-one-donor-out is the diagnostic that exposes it.

---

## Cross-cutting axes that apply to every design

Standard-error doctrine, weighting, outcome timing and aggregation, missing-data
handling, and outlier rules apply everywhere and are the least-reported choices
in applied work. Treat them as axes by default rather than by exception.
