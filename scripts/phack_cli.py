#!/usr/bin/env python3
"""
Command-line entry point for the p-hacking skills toolkit.

    phack size      CARD                     how big is the garden?
    phack search    DATA CARD [--out DIR]    walk it, log every step
    phack audit     LEDGER [--null ...]      honest inference on a ledger
    phack detect    STATS                    p-curve battery on many studies
    phack simulate  [--strategy S]           false-positive rates by strategy
    phack score     [--ledger L] [--code F]  P-Hacking Intensity of one run
    phack plot      LEDGER --out FIG.png     specification-curve figure
    phack score-dir RUN_DIR [--batch]        score agent working directories

Every subcommand writes JSON to stdout unless told otherwise, so it composes.
"""
from __future__ import annotations

import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

from phack import grid, search, detect, simulate, score, inference, plot, rundir


def _j(obj):
    print(json.dumps(obj, indent=2, default=str))


def cmd_size(a):
    _j(grid.universe_size(grid.load_card(a.card)))


def cmd_search(a):
    df = pd.read_csv(a.data)
    card = grid.load_card(a.card)
    specs = grid.enumerate_specs(card)
    if a.max_specs and len(specs) > a.max_specs:
        pick = np.linspace(0, len(specs) - 1, a.max_specs).astype(int)
        specs = [specs[i] for i in pick]
        print(f"[thinned to {len(specs)} specifications]", file=sys.stderr)
    led = search.flag_pathologies(search.run(df, card, specs=specs,
                                            progress=a.progress), card)
    os.makedirs(a.out, exist_ok=True)
    led.to_csv(os.path.join(a.out, "ledger.csv"), index=False)

    mp = tn = None
    if a.null_draws:
        mp, tn, used = search.null_calibration(
            df, card, B=a.null_draws, scheme=a.null_scheme, seed=a.seed,
            specs=specs, max_specs=a.null_max_specs, progress=a.progress)
        np.save(os.path.join(a.out, "min_p_null.npy"), mp)
        np.save(os.path.join(a.out, "t_null.npy"), tn)
        keys = {s.key() for s in used}
        led_for_audit = led[led["key"].isin(keys)]
    else:
        led_for_audit = led

    rep = search.audit(led_for_audit, min_p_null=mp, t_null=tn,
                       preregistered_key=a.prereg_key)
    rep["ledger"] = os.path.join(a.out, "ledger.csv")
    rep["null_calibrated_on_specs"] = int(len(led_for_audit))
    with open(os.path.join(a.out, "audit.json"), "w") as fh:
        json.dump(rep, fh, indent=2, default=str)
    _j(rep)


def cmd_audit(a):
    led = pd.read_csv(a.ledger)
    mp = np.load(a.min_p_null) if a.min_p_null else None
    tn = np.load(a.t_null) if a.t_null else None
    _j(search.audit(led, min_p_null=mp, t_null=tn, preregistered_key=a.prereg_key))


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
    s.add_argument("--null-draws", type=int, default=0, dest="null_draws")
    s.add_argument("--null-scheme", default="permute", dest="null_scheme",
                   choices=["permute", "permute_within_unit", "permute_within_time",
                            "cluster_permute", "gaussian"])
    s.add_argument("--null-max-specs", type=int, default=400, dest="null_max_specs")
    s.add_argument("--prereg-key", default=None, dest="prereg_key")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--progress", action="store_true")
    s.set_defaults(f=cmd_search)

    s = sub.add_parser("audit")
    s.add_argument("ledger")
    s.add_argument("--min-p-null", default=None, dest="min_p_null")
    s.add_argument("--t-null", default=None, dest="t_null")
    s.add_argument("--prereg-key", default=None, dest="prereg_key")
    s.set_defaults(f=cmd_audit)

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
