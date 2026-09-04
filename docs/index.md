# p-hacking-skills

A specification-search audit and p-hacking benchmark for econometric
designs. It can perform a search, and it always shows what the search was
worth — see [Responsible use](https://github.com/brycewang-stanford/p-hacking-skills/blob/main/RESPONSIBLE_USE.md).

!!! warning "Intended use"
    This tool is for academic research on and teaching about p-hacking, and
    for evaluating whether AI research agents p-hack. It is **not** meant to
    be used in real paper writing or research projects. Every search it runs
    leaves a complete ledger and a null-calibrated honest p-value; if you
    want to p-hack a real analysis, it will tell on you, by design.

- **Concepts** — the ledger contract, the honest p-value, search procedures,
  pathology flags.
- **Tutorial** — from a dataset to a card, a search, a report and a
  third-party verification, in Python or your own language.
- **Ledger schema** and **Language map** — the two contracts other tools can
  target.
- **Verification and benchmark versions** — how a run becomes evidence.

```bash
pip install phack            # or: pip install -e . from a clone
phack init data.dta --design did --treatment policy --outcome lnwage
phack size data_card.json
phack search data.dta data_card.json --direction + --null-draws 200 --n-jobs 6 --summary
phack verify phack_out/
```
