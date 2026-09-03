"""Strategy simulator recovers nominal alpha and the published ordering."""
import sys, os, warnings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import numpy as np, pytest
from phack import simulate as sim

warnings.filterwarnings("ignore")


@pytest.mark.parametrize("name", list(sim.STRATEGIES))
def test_nominal_alpha_recovered(name):
    r = sim.false_positive_rate(name, n_sims=600, seed=7)
    assert 0.02 <= r["fpr_original"] <= 0.09
    assert r["fpr_hacked"] >= r["fpr_original"] - 0.01


def test_modest_and_ambitious_reject_identically():
    a = sim.false_positive_rate("01_selective_dv", n_sims=500, seed=1)
    b = sim.false_positive_rate("01_selective_dv", n_sims=500, seed=1, ambitious=True)
    assert a["fpr_hacked"] == b["fpr_hacked"]
    assert b["mean_attempts"] >= a["mean_attempts"]


def test_strong_strategies_beat_weak_ones():
    strong = sim.false_positive_rate("07_transformation", n_sims=800, seed=2)["fpr_hacked"]
    weak = sim.false_positive_rate("05_covariates", n_sims=800, seed=2)["fpr_hacked"]
    assert strong > 0.15 > weak


def test_workflow_is_cumulative_with_diminishing_returns():
    w = sim.workflow(["09_alternative_tests", "01_selective_dv", "11_subgroup",
                      "04_outlier_exclusion"], n_sims=400, seed=5)
    c = w["cumulative_fpr"]
    assert all(np.diff(c) >= 0)
    assert c[-1] > 0.3
