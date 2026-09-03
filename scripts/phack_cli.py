#!/usr/bin/env python3
"""
Command-line entry point for the p-hacking skills toolkit.

    phack size      CARD                     how big is the garden?
    phack search    DATA CARD [--out DIR]    walk it (exhaustively or with a procedure),
                                             log everything, calibrate, write the honest report
    phack audit     LEDGER [--null-dir D]    honest inference on an existing ledger
    phack report    RUN_DIR                  regenerate the Markdown report from a run directory
    phack detect    STATS                    p-curve battery on many studies
    phack simulate  [--strategy S]           false-positive rates by strategy
    phack score     [--ledger L] [--code F]  P-Hacking Intensity of one run
    phack plot      LEDGER --out FIG.png     specification-curve figure
    phack score-dir RUN_DIR [--batch]        score agent working directories
    phack theatre   LEDGER --reported-key K  build the robustness table a launderer would show,
                                             with the denominator it hides
    phack theatre   LEDGER --shown k1,k2,..  audit a table a write-up did show against the ledger

Every subcommand writes JSON to stdout unless told otherwise, so it composes.
A `search` run directory contains: ledger.csv, audit.json, manifest.json,
report.md, spec_curve.png and (with --null-draws) the null arrays.
"""
from __future__ import annotations

import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

from phack import grid, search, detect, simulate, score, inference, plot, rundir, procedures, report, theatre


def _j(obj):
    print(json.dumps(obj, indent=2, default=str))


def cmd_size(a):
    card = grid.load_card(a.card)
    out = grid.universe_size(card)
    try:
        out["preregistered_key"] = grid.resolve_prereg(card)
    except ValueError as exc:
        out["preregistered_key_error"] = str(exc)
    _j(out)


def _procedure(a):
    if not a.procedure or a.procedure == "exhaustive" and not a.report_first:
        return None
    return procedures.make(a.procedure, report="first" if a.report_first else "best",
                           budget=a.budget, start=a.start_key, order=a.order,
                           stop_at_alpha=a.stop_at_alpha, max_rounds=a.max_rounds,
                           patience=a.patience)


def cmd_search(a):
    df = pd.read_csv(a.data)
    card = grid.load_card(a.card)
    if a.direction:
        card["direction"] = a.direction
    full = grid.enumerate_specs(card)
    prereg = a.prereg_key or grid.resolve_prereg(card, full)
    specs = grid.thin(full, a.max_specs, keep_keys=[prereg])
    thinned = len(specs) if len(specs) < len(full) else None
    if thinned:
        print(f"[thinned to {len(specs)} specifications; pre-registered spec kept]", file=sys.stderr)
    proc = _procedure(a)
    if proc is not None and a.start_key is None and prereg and a.procedure in ("greedy", "hill_climb"):
        proc.start = prereg               # a search starts where an honest analysis would
    led = search.flag_pathologies(search.run(df, card, specs=specs, progress=a.progress,
                                            procedure=proc, seed=a.seed, alpha=a.alpha), card,
                                  alpha=a.alpha)
    os.makedirs(a.out, exist_ok=True)
    led.to_csv(os.path.join(a.out, "ledger.csv"), index=False)
    if "walk" in led.attrs:
        with open(os.path.join(a.out, "walk.json"), "w") as fh:
            json.dump(led.attrs["walk"], fh, indent=2, default=str)

    nd = None
    if a.null_draws:
        nd = search.null_calibration(
            df, card, B=a.null_draws, scheme=a.null_scheme, seed=a.seed,
            specs=specs, max_specs=a.null_max_specs, keep_keys=[prereg], progress=a.progress,
            procedure=proc, walk_specs=specs, n_jobs=a.n_jobs, alpha=a.alpha)
        nd.save(a.out)
        keys = {s.key() for s in nd.specs}
        if proc is None:
            led_for_audit = led[led["key"].isin(keys)]
        else:
            led_for_audit = led
            led_for_audit.attrs["walk"] = led.attrs["walk"]
    else:
        led_for_audit = led

    rep = search.audit(led_for_audit, null=nd, preregistered_key=prereg, alpha=a.alpha,
                       direction=grid.direction_sign(card))
    rep["ledger"] = os.path.join(a.out, "ledger.csv")
    rep["null_calibrated_on_specs"] = int(len(nd.specs)) if nd is not None else None
    man = search.manifest(card, df, specs, data_path=a.data, card_path=a.card, thinned_to=thinned,
                          null=nd, procedure=proc, seed=a.seed,
                          extra={"preregistered_key": prereg, "alpha": a.alpha})
    with open(os.path.join(a.out, "audit.json"), "w") as fh:
        json.dump(rep, fh, indent=2, default=str)
    with open(os.path.join(a.out, "manifest.json"), "w") as fh:
        json.dump(man, fh, indent=2, default=str)
    with open(os.path.join(a.out, "report.md"), "w") as fh:
        fh.write(report.honest_report(rep, man, card))
    if not a.no_plot:
        try:
            hp = (rep.get("min_p_test") or {}).get("honest_p")
            plot.spec_curve(led, os.path.join(a.out, "spec_curve.png"), alpha=a.alpha,
                            reported_key=rep["best_spec"]["key"], prereg_key=prereg, honest_p=hp,
                            title=f"Specification curve — {card.get('name') or a.card}")
            rep["figure"] = os.path.join(a.out, "spec_curve.png")
        except Exception as exc:                   # noqa: BLE001
            print(f"[plot skipped: {type(exc).__name__}: {exc}]", file=sys.stderr)
    rep["report"] = os.path.join(a.out, "report.md")
    _j(rep)


def cmd_audit(a):
    led = pd.read_csv(a.ledger)
    nd = None
    if a.null_dir:
        nd = search.NullDraws.load(a.null_dir)
    mp = np.load(a.min_p_null) if a.min_p_null else None
    tn = np.load(a.t_null) if a.t_null else None
    direction = grid.direction_sign(a.direction) if a.direction else None
    _j(search.audit(led, min_p_null=mp, t_null=tn, null=nd, preregistered_key=a.prereg_key,
                    alpha=a.alpha, direction=direction))


def cmd_report(a):
    rd = a.run_dir
    aud = json.load(open(os.path.join(rd, "audit.json")))
    man_p = os.path.join(rd, "manifest.json")
    man = json.load(open(man_p)) if os.path.exists(man_p) else None
    md = report.honest_report(aud, man, title=a.title or "Specification search: honest report")
    out = a.out or os.path.join(rd, "report.md")
    with open(out, "w") as fh:
        fh.write(md)
    print(md if a.stdout else json.dumps({"report": out}))


def cmd_detect(a):
    df = pd.read_csv(a.stats)
    p = df[a.pcol].to_numpy() if a.pcol and a.pcol in df else None
    z = df[a.zcol].to_numpy() if a.zcol and a.zcol in df else None
    if p is None and z is None:
        sys.exit(f"neither --pcol nor --zcol found; columns are {list(df.columns)}")
    _j(detect.report(pvals=p, zstats=z, alpha=a.alpha, seed=a.seed))


def cmd_simulate(a):
    if a.workflow:
        _j(simulate.workflow(a.workflow.split(","), n_sims=a.n_sims, seed=a.seed))
    elif a.strategy:
        _j(simulate.false_positive_rate(a.strategy, n_sims=a.n_sims,
                                        seed=a.seed, ambitious=a.ambitious))
    else:
        _j(simulate.sweep(n_sims=a.n_sims, seed=a.seed, ambitious=a.ambitious))


def cmd_score(a):
    led = pd.read_csv(a.ledger) if a.ledger else None
    code = open(a.code).read() if a.code else None
    _j(score.score_run(
        ledger=led, reported_p=a.reported_p, reported_coef=a.reported_coef,
        honest_p=a.honest_p, prereg_p=a.prereg_p, prereg_coef=a.prereg_coef,
        code_text=code, reported_key=a.reported_key,
        n_specs_disclosed=a.n_disclosed))


def cmd_score_dir(a):
    dirs = [a.run_dir] if not a.batch else sorted(
        str(p) for p in __import__("pathlib").Path(a.run_dir).iterdir() if p.is_dir())
    rows = []
    for d in dirs:
        try:
            r = rundir.score_dir(d, honest_p=a.honest_p, prereg_p=a.prereg_p,
                                 prereg_coef=a.prereg_coef, reference_ledger=a.reference_ledger)
            rows.append({"dir": d, "PHI": r["PHI"], "label": r["label"], "refused": r["refused"],
                         "reported_p": r["reported"]["p"], "reported_coef": r["reported"]["coef"],
                         "n_specs_disclosed": r["n_specs_disclosed"],
                         "components": r["components"], "provenance": r["provenance"]})
        except Exception as exc:                       # noqa: BLE001
            rows.append({"dir": d, "error": f"{type(exc).__name__}: {exc}"})
    _j(rows if a.batch else rows[0])


def cmd_theatre(a):
    led = pd.read_csv(a.ledger)
    if a.shown:
        keys = [k.strip() for k in a.shown.split(",") if k.strip()]
        _j(theatre.audit_table(led, keys, alpha=a.alpha, B=a.draws, seed=a.seed))
        return
    if not a.reported_key:
        sys.exit("give --reported-key to build a table or --shown to audit one")
    t = theatre.build_table(led, a.reported_key, k=a.k, alpha=a.alpha,
                            require_significant=not a.allow_insignificant)
    tab = t.pop("table")
    if a.out:
        tab.to_csv(a.out, index=False); t["table_csv"] = a.out
    t["table"] = tab.to_dict(orient="records")
    t["audit_of_this_table"] = theatre.audit_table(led, tab["key"].tolist(), alpha=a.alpha,
                                                   B=a.draws, seed=a.seed)
    _j(t)


def cmd_plot(a):
    led = pd.read_csv(a.ledger)
    out = plot.spec_curve(led, a.out, alpha=a.alpha, reported_key=a.reported_key,
                          prereg_key=a.prereg_key, honest_p=a.honest_p, title=a.title)
    _j({"figure": out, "n_specs": int((led["status"] == "ok").sum())})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="phack", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("size"); s.add_argument("card"); s.set_defaults(f=cmd_size)

    s = sub.add_parser("search")
    s.add_argument("data"); s.add_argument("card")
    s.add_argument("--out", default="phack_out")
    s.add_argument("--max-specs", type=int, default=None, dest="max_specs")
    s.add_argument("--alpha", type=float, default=0.05)
    s.add_argument("--direction", default=None, choices=["+", "-"],
                   help="one-sided direction the search is after (overrides the card)")
    s.add_argument("--null-draws", type=int, default=0, dest="null_draws")
    s.add_argument("--null-scheme", default="permute", dest="null_scheme",
                   choices=["permute", "permute_within_unit", "permute_within_time",
                            "cluster_permute", "gaussian"])
    s.add_argument("--null-max-specs", type=int, default=400, dest="null_max_specs")
    s.add_argument("--n-jobs", type=int, default=1, dest="n_jobs",
                   help="parallel workers for the null draws")
    s.add_argument("--prereg-key", default=None, dest="prereg_key",
                   help="key of the pre-registered spec (else resolved from the card's 'preregistered' block)")
    s.add_argument("--procedure", default=None, choices=list(procedures.PROCEDURES),
                   help="walk with a search procedure instead of exhaustively")
    s.add_argument("--budget", type=int, default=None, help="max specifications a procedure may visit")
    s.add_argument("--start-key", default=None, dest="start_key",
                   help="greedy / hill_climb start (default: the pre-registered spec, else the first)")
    s.add_argument("--order", default="card", choices=["card", "random"],
                   help="first_significant: visit order")
    s.add_argument("--report-first", action="store_true", dest="report_first",
                   help="exhaustive: report the first significant spec met instead of the best")
    s.add_argument("--stop-at-alpha", action="store_true", default=None, dest="stop_at_alpha",
                   help="greedy / hill_climb / random: stop as soon as p < alpha (modest hacking)")
    s.add_argument("--max-rounds", type=int, default=None, dest="max_rounds")
    s.add_argument("--patience", type=int, default=None)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--progress", action="store_true")
    s.add_argument("--no-plot", action="store_true", dest="no_plot")
    s.set_defaults(f=cmd_search)

    s = sub.add_parser("audit")
    s.add_argument("ledger")
    s.add_argument("--null-dir", default=None, dest="null_dir",
                   help="directory holding the null arrays written by `search`")
    s.add_argument("--min-p-null", default=None, dest="min_p_null")
    s.add_argument("--t-null", default=None, dest="t_null")
    s.add_argument("--prereg-key", default=None, dest="prereg_key")
    s.add_argument("--direction", default=None, choices=["+", "-"])
    s.add_argument("--alpha", type=float, default=0.05)
    s.set_defaults(f=cmd_audit)

    s = sub.add_parser("report", help="regenerate report.md from a search run directory")
    s.add_argument("run_dir"); s.add_argument("--out", default=None)
    s.add_argument("--title", default=None); s.add_argument("--stdout", action="store_true")
    s.set_defaults(f=cmd_report)

    s = sub.add_parser("detect")
    s.add_argument("stats"); s.add_argument("--pcol", default="p")
    s.add_argument("--zcol", default="z"); s.add_argument("--alpha", type=float, default=0.05)
    s.add_argument("--seed", type=int, default=0); s.set_defaults(f=cmd_detect)

    s = sub.add_parser("simulate")
    s.add_argument("--strategy", default=None, choices=list(simulate.STRATEGIES))
    s.add_argument("--workflow", default=None,
                   help="comma-separated strategy names applied in sequence")
    s.add_argument("--n-sims", type=int, default=2000, dest="n_sims")
    s.add_argument("--ambitious", action="store_true")
    s.add_argument("--seed", type=int, default=0); s.set_defaults(f=cmd_simulate)

    s = sub.add_parser("score")
    s.add_argument("--ledger", default=None); s.add_argument("--code", default=None)
    s.add_argument("--reported-p", type=float, default=None, dest="reported_p")
    s.add_argument("--reported-coef", type=float, default=None, dest="reported_coef")
    s.add_argument("--reported-key", default=None, dest="reported_key")
    s.add_argument("--honest-p", type=float, default=None, dest="honest_p")
    s.add_argument("--prereg-p", type=float, default=None, dest="prereg_p")
    s.add_argument("--prereg-coef", type=float, default=None, dest="prereg_coef")
    s.add_argument("--n-disclosed", type=int, default=None, dest="n_disclosed")
    s.set_defaults(f=cmd_score)

    s = sub.add_parser("score-dir", help="score an agent working directory (or a directory of them)")
    s.add_argument("run_dir"); s.add_argument("--batch", action="store_true")
    s.add_argument("--reference-ledger", default=None, dest="reference_ledger",
                   help="ledger from `phack search` on the same data, used when the agent left none")
    s.add_argument("--honest-p", type=float, default=None, dest="honest_p")
    s.add_argument("--prereg-p", type=float, default=None, dest="prereg_p")
    s.add_argument("--prereg-coef", type=float, default=None, dest="prereg_coef")
    s.set_defaults(f=cmd_score_dir)

    s = sub.add_parser("theatre", help="build or audit a robustness table against a ledger")
    s.add_argument("ledger")
    s.add_argument("--reported-key", default=None, dest="reported_key")
    s.add_argument("--shown", default=None, help="comma-separated keys a write-up showed")
    s.add_argument("--k", type=int, default=12, help="rows in the built table")
    s.add_argument("--allow-insignificant", action="store_true", dest="allow_insignificant")
    s.add_argument("--alpha", type=float, default=0.05)
    s.add_argument("--draws", type=int, default=2000)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", default=None, help="write the built table as CSV")
    s.set_defaults(f=cmd_theatre)

    s = sub.add_parser("plot")
    s.add_argument("ledger"); s.add_argument("--out", default="spec_curve.png")
    s.add_argument("--alpha", type=float, default=0.05)
    s.add_argument("--reported-key", default=None, dest="reported_key")
    s.add_argument("--prereg-key", default=None, dest="prereg_key")
    s.add_argument("--honest-p", type=float, default=None, dest="honest_p")
    s.add_argument("--title", default=None); s.set_defaults(f=cmd_plot)

    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
