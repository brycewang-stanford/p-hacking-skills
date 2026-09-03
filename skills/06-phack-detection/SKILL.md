---
name: phack-detection
description: Test whether a body of reported results shows p-hacking or selective reporting, using the p-curve battery. Implements the binomial, Fisher, Stouffer and least-concave-majorant monotonicity tests of Elliott, Kudrin and Wuethrich (2022), plus threshold-bunching tests calibrated against a smooth counterfactual density and Simonsohn's p-curve power estimate. Use when asked whether a literature, a journal, a research design, an author or a set of agent runs shows evidence of p-hacking or publication bias.
---

# Detecting p-hacking in a collection of results

## What can and cannot be established

Every test here is a test on the **distribution across many results**. None of
them can establish that any individual paper was p-hacked, and the report says
so on every run. Treat a flag as a reason to look, never as a finding about a
person.

## The theory in one paragraph

Elliott, Kudrin & Wüthrich (2022) show that in the absence of p-hacking the
density of p-values across studies is **non-increasing** on (0, α), and for
tests based on asymptotically normal statistics it is also **continuous** and
bounded above. p-hacking breaks these: it moves mass from just above the
threshold to just below, producing a hump, a discontinuity, or a
non-monotonicity. Each testable implication gives a test.

## Running

```bash
python scripts/phack_cli.py detect stats.csv --pcol p --zcol z
```

Input is one row per reported result. Supply p-values, z-statistics, or both;
whichever is missing is derived.

## The battery

**Shape tests** — clean nulls, trust these:

| Test | Null | Small p-value means |
|---|---|---|
| `binomial` | ≥ half of significant p-values fall below α/2 | left-skewed p-curve; no evidential value |
| `fisher` | p-curve is uniform or right-skewed | left skew |
| `stouffer` | as Fisher, normal aggregation | left skew |
| `lcm_monotonicity` | density non-increasing on (0, α) | the curve humps; bootstrapped against the least favourable null |

**Bunching tests** — weaker, read with care:

| Test | What it compares |
|---|---|
| `discontinuity` | mass just below p = .05 against a Poisson log-linear counterfactual fitted outside a donut |
| `caliper` | mass just above z = 1.96 against the same kind of counterfactual |

**Why the counterfactual matters.** The classical caliper test asks whether more
than half the statistics in a window around 1.96 lie above it. That null is
right only when the density is locally *flat*. When a real effect is present the
density of |z| is *rising* through 1.96, so an honest literature fails the naive
test. On simulated honest data with a true effect, the naive caliper reports 65%
above and p = .011 — a false positive. The counterfactual version reports
p = .11 and correctly declines to flag. Both are printed; `naive_share_above` is
kept for comparability with the published literature, but `p_value` is the
counterfactual one.

**`pcurve_power`** estimates the average power behind the significant results.
A value near α means the significant findings carry no evidential value at all.

## Reading the verdict

The verdict weights shape tests above bunching tests, because only the shape
tests have clean nulls:

- **strong evidence** — two or more shape tests flag
- **moderate** — one shape test plus bunching
- **weak / ambiguous — bunching only** — this is the interesting case. It is
  what a *mixed* literature looks like: genuine effects dilute the shape tests
  while threshold-seeking still leaves a bunching signature. In simulation, a
  literature that is 5/6 null with mild threshold-pushing shows excess mass of
  2.3× at the caliper while every shape test comes back clean.
- **no distributional evidence** — the tests found nothing; this is not proof of
  absence, particularly with few results

## Validation

The battery is calibrated on simulated data with known ground truth:

| Data | Shape tests | Bunching | Estimated power | Verdict |
|---|---|---|---|---|
| honest, real effect | clean | clean | 0.80 | no evidence |
| p-hacked, true null | all four flag | both flag | 0.05 | strong evidence |
| mixed | clean | both flag | 0.30 | weak / ambiguous |

Reproduce from `tests/test_detect.py`.

## Sample-size guidance

The shape tests need at least ~15 significant results and are underpowered
below ~50. The bunching tests need enough mass near the threshold to fit a
counterfactual and return a note rather than a p-value when they do not. Elliott
et al. and the follow-up work on when p-hacking is detectable are clear that
none of these tests has much power against *mild* hacking; a clean report from a
small collection means very little.
