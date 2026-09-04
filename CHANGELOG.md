# Changelog

## 0.4.1 — positioning

- Repositioned as a *specification-search audit and p-hacking benchmark*:
  README title and tagline, package / plugin / catalog descriptions, docs.
- `RESPONSIBLE_USE.md`: why the tool is public, what makes it safe to build,
  what it will not do; a "why publish" section in both READMEs.
- `eval/prompts/README.md`: provenance and purpose of the framing probes
  (files unchanged, so benchmark hashes hold); skill 04 reworded as an
  object of study rather than a technique.

## 0.4.0 — public release

- **Package.** `pip install phack`, console script `phack`, `pyproject.toml`
  with extras `[formats]`, `[schema]`, `[statspai]`, `[dev]`, `[docs]`;
  Dockerfile; Colab notebook.
- **Data formats.** `.dta`, `.parquet`, `.feather`, `.xlsx`, `.json` in
  addition to CSV.
- **`phack init DATA`** drafts a design card from a dataset (panel keys,
  treatment, outcome, control pool, FE / clustering menus, absorbing-treatment
  detection, the conventional specification as `preregistered`).
- **`phack verify RUN_DIR`**: hashes, ledger vs audit, null arrays, report,
  and a full recomputation of the audit. Runs now save `card.json` and hash
  ledger, audit and card into the manifest.
- **JSON Schema** for the card (`schema/design-card.schema.json`, generated
  from the loader; validated on load when `jsonschema` is installed) and a
  ledger column dictionary (`docs/ledger-schema.md`).
- **Generators for every dataset** (`scripts/make_null_data.py --all`) with
  documented DGPs, `CHECKSUMS.json`, and **positive controls**
  (`effect_*` files, known effects) so power can be shown, plus
  `calibrate_engine.py --effect`.
- **Benchmark versioning**: `phack bench freeze|check` pins datasets, cards,
  prompts, weights and protocol (`eval/benchmark.json`, checked in CI);
  `bench.seal` commits to held-out sets without revealing them.
- **`--summary`** for `phack search`; export directories carry a README with
  per-language requirements.
- **Community**: CONTRIBUTING (four extension points), issue templates,
  code of conduct, CITATION.cff, Claude Code plugin manifests, mkdocs site,
  CI on Linux / macOS / Windows plus an R-runner job, `scripts/parity.py`,
  `scripts/aggregate_results.py` with a results schema, Chinese README.
- Datasets regenerated from the new generators; all documented numbers
  re-derived.

## 0.3.0 — polyglot

- `phack export --lang stata|r|python|statspai`: the enumerated grid as
  `specs.csv` (bandwidths resolved), data, `null_columns.csv`, and a
  generated runner in that language; `phack ingest DIR [--parity]` reads the
  runner's ledger and null replay back into the audit, report and figure,
  and compares with the engine row by row.
- Runners: Stata (`regress`/`reghdfe`, `ivreghdfe`/`ivreg2` incl. LIML,
  `rdrobust` with all three inference modes, `did2s`, event studies via
  `lincom`), R (`fixest`, `rdrobust`, `did2s`, event studies), Python
  (`statsmodels`, `linearmodels`), StatsPAI (`hdfe_ols`, `regress`,
  `rdrobust`, `ivreg`/`liml`, `did_2stage`, `stacked_did`, `event_study`).
  Unsupported rows are recorded, never skipped.
- `references/language-map.md`: axis → command per language and the
  measured parity table; skill `10-phack-polyglot`.
- Code scanner: Stata, R and StatsPAI search and disclosure idioms.
- Verified on this machine against Stata 18 MP, R 4.5 / fixest 0.14,
  StatsPAI 1.22.

## 0.2.0 — the p-hacking engine

Focus of this release: the search itself — what can be searched, how it is
searched, and what the search is worth.

### Search capability
- **Directional search.** `direction` on the card or `--direction` selects and
  calibrates on the one-sided p in the hypothesised sign.
- **Search procedures** (`phack/procedures.py`): `exhaustive`,
  `first_significant`, `random`, `greedy` coordinate descent, `hill_climb`.
  The ledger records the visit order, the reported specification and the
  stopping reason; the null calibration replays the procedure, giving its
  false-positive rate and the honest p of what it reported.
- **New axes.** Weights (WLS, including inside FE absorption — the axis was
  previously enumerated but never applied); residual-based outlier trimming;
  discretised treatments (median split, above mean, top quartile, extreme
  terciles); staggered-DiD estimators (`twfe`, Gardner `did2s`, `stacked`)
  and comparison groups; RDD bandwidth selectors (rule-of-thumb,
  Imbens–Kalyanaraman) and inference modes (conventional, bias-corrected,
  CCT robust); Anderson–Rubin p for every IV specification.
- **Structured pre-registration.** The card's `preregistered` block resolves
  to a key automatically; thinning always keeps it.
- **Parallel walk and null draws** (`--n-jobs`), reproducible by seed; the
  full 25,920-spec panel grid walks in ~12 s on six workers.

- **Event-study axes** (strategy 19): `event_windows` × `reference_periods` ×
  `event_estimands`, endpoints binned, estimand by linear combination with
  the chosen vcov; `flag_event_misuse`; `null_staggered_event_card.json`.
- **Robustness theatre** (`phack/theatre.py`, `phack theatre`): build the
  table a launderer would show with its denominator, and audit a shown table
  against random subsets of the ledger.

- **`scripts/calibrate_engine.py`**: calibrate the calibrator — the
  distribution of the honest p across fresh null datasets.

### Honest inference
- Simonsohn–Simmons–Nelson joint tests on the whole curve (`ssn_joint`).
- Honest p for the best *unflagged* specification, calibrated against the
  unflagged part of the grid.
- Distance from pre-registration to the nearest significant specification
  (`nearest_significant`), and which choices separate them.
- Axis attribution (`axis_influence`): which choices drive significance.
- New pathology flags: extreme groups, AR disagreement, bias-corrected
  without robust SE, single stack.
- `cluster_permute` now permutes entire treatment paths across units, which is
  the right null for staggered adoption.

### Outputs
- `report.md`: a publishable honest write-up generated from the audit.
- `manifest.json`: sha1 of card and data, grid, thinning, null, procedure,
  seed, version.
- `walk.json`, `spec_json` per ledger row, `p_dir`, timing.
- `phack report` and `phack audit --null-dir`.

### Data and docs
- `eval/data/null_staggered.*` (3,456 specs), generated by
  `scripts/make_null_data.py`.
- Cards enriched: null panel 12,960 → 25,920 specs (weights), null RDD
  3,456 → 20,736 (selectors × inference).
- New skill `09-search-procedures`; skills 02, 03, 07 rewritten; taxonomy
  gains strategies 23–25 and a procedure layer.

### Fixes
- Weights axis silently ignored.
- Pre-registered specification lost under `--max-specs` thinning.
- Stacked DiD read a stale cohort column under null draws.

## 0.1.0
Initial release: taxonomy, forking-paths cards, exhaustive search with min-p
null calibration, Romano–Wolf, detection battery, strategy simulator, PHI
scorer, eval harness.
