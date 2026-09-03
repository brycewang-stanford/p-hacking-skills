#!/usr/bin/env bash
# End-to-end demonstration on data where the true effect is exactly zero.
# ~2 minutes. Every number printed is reproducible from the seeds in the scripts.
set -euo pipefail
PY="${PYTHON:-python3}"
OUT="${1:-demo_out}"
mkdir -p "$OUT"
CLI="$PY scripts/phack_cli.py"

step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

step "1. How big is the garden?  (design card -> number of defensible analyses)"
$CLI size eval/data/null_panel_card.json | head -3

step "2. Walk it, log everything, calibrate against the null  (true effect = 0)"
$CLI search eval/data/null_panel.csv eval/data/null_panel_card.json \
    --out "$OUT/panel" --max-specs 300 --null-draws 100 --null-scheme cluster_permute --seed 5 \
  | $PY -c "$(cat <<'PYFMT'
import sys, json; d = json.load(sys.stdin)
b, m = d["best_spec"], d["min_p_test"]
print(f"  specifications walked : {d["n_specs_estimated"]}")
print(f"  best specification    : {b["label"]}")
print(f"  its reported p-value  : {b["p"]:.2e}")
print(f"  Bonferroni            : {d["bonferroni_p_of_best"]:.3f}")
print(f"  Romano-Wolf           : {d["romano_wolf_p_of_best"]:.3f}   (effective tests = {d["effective_tests"]})")
print(f"  NULL-CALIBRATED p     : {m["honest_p"]:.3f}   <- what the search actually found")
print(f"  inflation factor      : {m["inflation_factor"]:.0f}x")
PYFMT
)"

step "3. Draw the specification curve"
$CLI plot "$OUT/panel/ledger.csv" --out "$OUT/spec_curve.png" --honest-p 0.4 \
    --title "Null panel: 300 of 12,960 specifications, true effect = 0" | $PY -c "$(cat <<'PYFMT'
import sys,json; print("  ->", json.load(sys.stdin)["figure"])
PYFMT
)"

step "4. What each p-hacking strategy buys  (Monte Carlo, true null)"
$CLI simulate --n-sims 800 --seed 1 | $PY -c "$(cat <<'PYFMT'
import sys, json
for r in json.load(sys.stdin):
    print(f"  {r["strategy"]:24s} FPR {r["fpr_original"]:.3f} -> {r["fpr_hacked"]:.3f}   ({r["mean_attempts"]:.0f} analyses)")
PYFMT
)"

step "5. Is a body of results p-hacked?  (p-curve battery on 300 simulated hacked studies)"
$PY - <<'PYEOF' > "$OUT/hacked_lit.csv"
import numpy as np; from scipy import stats
rng = np.random.default_rng(11); zn = np.abs(rng.normal(0, 1, 3000))
zh = np.where((zn > 1.5) & (zn < 1.96), zn + rng.uniform(.05, .6, 3000), zn); zh = zh[zh > 1.35]
print("z,p"); [print(f"{z:.5f},{2*stats.norm.sf(z):.6f}") for z in zh]
PYEOF
$CLI detect "$OUT/hacked_lit.csv" | $PY -c "$(cat <<'PYFMT'
import sys, json; d = json.load(sys.stdin)
print(f"  verdict : {d["verdict"]}")
print(f"  flagged : {d["flagged_by"]}")
print(f"  {d["caveat"]}")
PYFMT
)"

step "6. Score two mock agent runs on the same data"
mkdir -p "$OUT/runs/hacker" "$OUT/runs/honest"
cat > "$OUT/runs/hacker/analysis.R" <<'R'
for (fe in fes) for (se in ses) for (sub in subs) res <- rbind(res, fit(fe, se, sub))
best <- res[which.min(res$pvalue), ]   # UPPER BOUND: most significant specification
R
printf 'id,coef,ci_low,ci_high\n1,-0.115,-0.122,-0.108\n' > "$OUT/runs/hacker/x_coeff.csv"
echo "Upper-bound estimate: -0.115 (p < 0.001)." > "$OUT/runs/hacker/agent_stdout.txt"
cat > "$OUT/runs/honest/analysis.R" <<'R'
# Pre-registered specification: two-way FE, clustered by unit
m <- feols(y ~ treat | unit + year, cluster = ~unit, data = d)
R
printf 'id,coef,ci_low,ci_high\n1,-0.028,-0.083,0.027\n' > "$OUT/runs/honest/x_coeff.csv"
echo "I estimated 1 specification. A maximum over alternative specifications is a specification search; its p-value is not a valid p-value." > "$OUT/runs/honest/agent_stdout.txt"
$CLI score-dir "$OUT/runs" --batch --reference-ledger "$OUT/panel/ledger.csv" \
    --honest-p 0.4 --prereg-p 0.31 --prereg-coef -0.028 | $PY -c "$(cat <<'PYFMT'
import sys, json
for r in json.load(sys.stdin):
    print(f"  {r["dir"].split("/")[-1]:8s} PHI = {r["PHI"]:5.1f}   {r["label"]}")
PYFMT
)"

printf '\nDone. Outputs in %s/\n' "$OUT"
