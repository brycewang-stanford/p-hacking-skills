"""Search procedures: deterministic given the rng, replayable, and each stops for the right reason."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import numpy as np, pandas as pd, pytest
from phack import grid, search, procedures

ROOT = os.path.join(os.path.dirname(__file__), "..", "eval", "data")


@pytest.fixture(scope="module")
def setup():
    df = pd.read_csv(os.path.join(ROOT, "null_panel.csv"))
    card = grid.load_card(os.path.join(ROOT, "null_panel_card.json"))
    card["direction"] = "+"
    specs = grid.thin(grid.enumerate_specs(card), 400, keep_keys=[grid.resolve_prereg(card)])
    return df, card, specs


def _walk(setup, proc, seed=0):
    df, card, specs = setup
    fit = search.make_fitter(df, card)
    return proc.walk(specs, fit, rng=np.random.default_rng(seed), alpha=0.05, direction=1), fit


def test_exhaustive_visits_everything_and_reports_best(setup):
    w, fit = _walk(setup, procedures.Exhaustive())
    assert len(w.visited) == len(setup[2])
    best = min(setup[2], key=lambda s: procedures._objective(fit(s), 1))
    assert w.reported.key() == best.key()


def test_first_significant_stops_early_and_is_modest(setup):
    w, fit = _walk(setup, procedures.FirstSignificant(order="card"))
    r = fit(w.reported)
    if "first significant" in w.stopped:
        assert procedures._objective(r, 1) < 0.05
        assert len(w.visited) < len(setup[2])
        # everything before the reported spec was NOT significant
        assert all(procedures._objective(fit(s), 1) >= 0.05 for s in w.visited[:-1])
    else:
        assert w.reported.key() == w.visited[0].key()      # honest fallback


def test_random_budget_respects_budget_and_is_deterministic(setup):
    w1, _ = _walk(setup, procedures.RandomBudget(budget=25), seed=3)
    w2, _ = _walk(setup, procedures.RandomBudget(budget=25), seed=3)
    w3, _ = _walk(setup, procedures.RandomBudget(budget=25), seed=4)
    assert len(w1.visited) == 25
    assert [s.key() for s in w1.visited] == [s.key() for s in w2.visited]
    assert [s.key() for s in w1.visited] != [s.key() for s in w3.visited]


def test_greedy_moves_one_axis_at_a_time_and_improves(setup):
    df, card, specs = setup
    pre = grid.resolve_prereg(card, specs)
    w, fit = _walk(setup, procedures.GreedyCoordinate(start=pre, stop_at_alpha=False, max_rounds=2))
    assert w.visited[0].key() == pre
    idx = grid.SpecIndex(specs)
    for step in w.path:                                    # every move changes exactly one axis
        assert step["axis"] in idx.varying
        assert step["p_to"] < step["p_from"]
    p0 = procedures._objective(fit(w.visited[0]), 1)
    assert procedures._objective(fit(w.reported), 1) <= p0


def test_hill_climb_never_accepts_a_worse_move(setup):
    w, fit = _walk(setup, procedures.HillClimb(budget=40, stop_at_alpha=False, patience=10), seed=1)
    ps = [step["p_to"] for step in w.path]
    assert all(np.diff(ps) < 0) if len(ps) > 1 else True
    assert len(w.visited) <= 40


def test_run_with_procedure_marks_reported_and_records_walk(setup):
    df, card, specs = setup
    led = search.run(df, card, specs=specs, procedure=procedures.RandomBudget(budget=20), seed=0)
    assert len(led) == 20 and led["reported"].sum() == 1
    assert led["order"].tolist() == list(range(20))
    assert led.attrs["walk"]["procedure"] == "random"


def test_procedure_null_replay_gives_false_positive_rate(setup):
    df, card, specs = setup
    proc = procedures.FirstSignificant(order="random", budget=40)
    nd = search.null_calibration(df, card, B=12, scheme="cluster_permute", specs=specs,
                                 max_specs=60, procedure=proc, walk_specs=specs, seed=2)
    assert nd.reported_p_null.shape == (12,) and nd.n_visited_null.shape == (12,)
    assert np.all(nd.n_visited_null <= 40)
    led = search.flag_pathologies(search.run(df, card, specs=specs, procedure=proc, seed=2), card)
    a = search.audit(led, null=nd, alpha=0.05)
    assert "procedure_test" in a and 0 <= a["procedure_test"]["null_share_reporting_significant"] <= 1
    assert 0 < a["procedure_test"]["honest_p"] <= 1


def test_make_filters_unknown_params():
    p = procedures.make("greedy", budget=10, order="random", nonsense=1)
    assert isinstance(p, procedures.GreedyCoordinate) and p.budget == 10
    with pytest.raises(KeyError):
        procedures.make("teleport")
