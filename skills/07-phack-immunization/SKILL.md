---
name: phack-immunization
description: Make an empirical analysis robust to specification search, before or after the fact. Covers pre-registration and pre-analysis plans, specification-curve reporting with joint inference, Romano-Wolf and effective-multiplicity corrections, randomisation and permutation inference, split-sample and holdout designs, and honest reporting templates. Use when asked how to protect an analysis against p-hacking, how to correct inference after a search has happened, how to write a pre-analysis plan, or how to report a multiverse credibly.
---

# Immunising an analysis

Two situations, two answers.

## A. Before the data are analysed

**Pre-specify one specification, and pre-specify the grid around it.**

A pre-analysis plan that names a single specification is good. One that also
names the *set* of defensible alternatives is better, because it converts every
later robustness check from a discretionary choice into a committed one. Write
the design card (`02-forking-paths`) as part of the plan and deposit it.

Contents that matter, in order of how often they are omitted:

1. primary outcome, named singly, with its exact construction
2. the estimating equation, including fixed effects and the clustering level
3. sample inclusion rules and the exact date window
4. the outlier rule and the missing-data rule
5. the subgroups to be examined, and that they are secondary
6. the multiplicity correction to be applied across outcomes and subgroups
7. what would count as a null result

**Split the sample.** Where N allows, hold out a confirmation sample and lock
it. Explore freely in the training half; the held-out half gets exactly one
analysis, the one that exploration selected. This converts a search into a
legitimate two-stage design and is by far the strongest available protection.

**Blind the analysis.** Analyse with the treatment label permuted, fix every
analytical choice, then unblind. Everything decided under blinding is
pre-specified by construction.

## B. After a search has happened

The search is not the problem. Reporting one point from it as a confirmatory
test is. Four escalating repairs:

### 1. Report the curve, not the point
Median coefficient, interquartile range, share significant, share flipping sign,
and the full ledger in a repository. `phack search` emits all of this.

### 2. Correct for multiplicity, using the dependence
Bonferroni over S specifications is valid but badly conservative, because
specifications reuse the same rows. Use **Romano–Wolf stepdown**, which
bootstraps the joint distribution of the family and controls FWER while
exploiting the correlation. `effective_tests` (Li & Ji) tells you how much
over-correction you avoided — three hundred specifications routinely behave like
eight.

### 3. Calibrate the whole search
The strongest repair. Re-run the *identical* search on data where the null holds
by construction, and report the share of null datasets on which the search found
something at least as significant. That is `min_p_test.honest_p`, and it needs
no assumption about how the specifications are correlated because it re-runs the
procedure rather than modelling it.

```bash
python scripts/phack_cli.py search DATA CARD --null-draws 500 --null-scheme cluster_permute
```

Pick the null scheme to match the design — `cluster_permute` for a panel with
unit-level treatment, `permute_within_time` for within-period assignment. A
mis-specified null gives a too-tight reference distribution and an honest
p-value that is not honest.

### 4. Randomisation inference for the reported specification
Where treatment assignment is known, permutation inference on the single
reported specification is exact and assumption-free about the error structure.
It does not fix multiplicity — combine it with 2 or 3.

## Reporting template

> We estimated the effect under S = 1,248 defensible specifications, enumerated
> in advance and listed in the replication package. The pre-registered
> specification gives β̂ = −0.041 (SE 0.031, p = 0.19). Across the family the
> median estimate is −0.038, the interquartile range is [−0.061, −0.016], 22%
> of specifications are significant at 5%, and 9% change sign. The most
> significant specification gives β̂ = −0.080 (p = 0.035); calibrated against
> 500 permutations of treatment across units, the probability that a search of
> this family finds a result at least this significant under the null is 0.41.
> We therefore do not treat the result as evidence of a non-zero effect.

That paragraph is publishable and it is honest. The temptation it resists is
reporting only the sixth sentence.

## What immunisation cannot do

None of this makes a fragile result robust. It makes fragility *visible* and
correctly priced. If the honest p-value is 0.41, the analysis has not found an
effect, and the right conclusion is that the design cannot resolve one — which
is itself worth reporting, and which pre-registration makes publishable.
