---
name: phack-taxonomy
description: Name and classify p-hacking strategies, and quantify what each one does to the false-positive rate. Covers the twelve-strategy compendium of Stefan and Schoenbrodt (2023) plus ten econometrics-specific degrees of freedom (clustering doctrine, fixed-effect structure, RDD bandwidth and kernel, IV instrument sets, staggered-DiD estimator choice, synthetic-control donor pools). Use when asked what p-hacking is, which strategy a particular analytical choice corresponds to, how much a given researcher degree of freedom inflates type I error, or to enumerate the ways a specific result could have been obtained.
---

# Strategy taxonomy

Read `references/taxonomy.md`. It is the substance of this skill: 22 strategies
across two layers, each with what is chosen, why it is defensible, and what it
costs in type I error.

## Quantifying a strategy

```bash
python scripts/phack_cli.py simulate --strategy 07_transformation --n-sims 4000
python scripts/phack_cli.py simulate --workflow 09_alternative_tests,01_selective_dv,11_subgroup
python scripts/phack_cli.py simulate --n-sims 4000            # all twelve
```

Data are generated under a true null, so `fpr_hacked` is the probability the
strategy manufactures a false positive. `fpr_original` is the calibration
check and should land on 0.05.

## Using it to classify

When someone describes an analytical choice, the useful question is not "is
this p-hacking?" — almost nothing is p-hacking in isolation. It is:

1. **Which axis of the grid is this?** Map it to a numbered strategy.
2. **Was it fixed before the outcome was seen?** A choice made ex ante is a
   design; the same choice made ex post is a degree of freedom spent.
3. **How many alternatives were available and how many were tried?** This is
   the multiplicity that inference has to pay for.
4. **Is the alternative set disclosed?** A disclosed search is a multiverse
   analysis. An undisclosed one is a p-hacked result.

Only question 2 and question 4 separate legitimate work from misconduct.
Questions 1 and 3 are just accounting — and the accounting is what this suite
automates.

## What not to conclude

A high false-positive rate for a strategy does not mean anyone using that
strategy is hacking. Outlier exclusion, covariate adjustment and imputation are
all *necessary* in real data. The rates in the table are what happens when the
choice is made **after** seeing the result, repeatedly, and reported as one.
