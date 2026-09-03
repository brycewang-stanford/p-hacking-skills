"""Detection battery is calibrated on known ground truth."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import numpy as np
from scipy import stats
from phack import detect


def _honest(seed=11, n=600, ncp=2.8):
    z = np.abs(np.random.default_rng(seed).normal(ncp, 1, n))
    return 2 * stats.norm.sf(z)


def _hacked(seed=11, n=3000):
    rng = np.random.default_rng(seed)
    zn = np.abs(rng.normal(0, 1, n))
    zh = np.where((zn > 1.5) & (zn < 1.96), zn + rng.uniform(.05, .6, n), zn)
    return 2 * stats.norm.sf(zh[zh > 1.35])


def test_honest_literature_not_flagged():
    r = detect.report(pvals=_honest(), seed=1)
    assert r["shape_tests_flagging"] == []
    assert r["bunching_tests_flagging"] == []          # counterfactual, not naive
    assert r["verdict"].startswith("no distributional")
    pw = [t for t in r["tests"] if t["test"] == "pcurve_power"][0]
    assert 0.7 < pw["estimated_power"] < 0.9         # true power at ncp 2.8 ~ .80


def test_naive_caliper_would_have_false_positived():
    cal = detect.caliper_test(stats.norm.isf(_honest() / 2))
    assert cal["naive_p_value"] < 0.05                 # the classic test fails here
    assert cal["p_value"] > 0.05                       # the counterfactual does not


def test_hacked_null_is_caught():
    r = detect.report(pvals=_hacked(), seed=1)
    assert len(r["shape_tests_flagging"]) >= 3
    assert r["verdict"].startswith("strong")
    pw = [t for t in r["tests"] if t["test"] == "pcurve_power"][0]
    assert pw["estimated_power"] < 0.10


def test_lcm_is_a_concave_majorant():
    x = np.linspace(0, 1, 50); y = np.sin(3 * x) + 0.2 * np.random.default_rng(0).normal(size=50)
    m = detect._lcm(x, y)
    assert np.all(m >= y - 1e-12)
    assert np.all(np.diff(m, 2) <= 1e-9)


def test_small_samples_return_notes_not_pvalues():
    r = detect.report(pvals=np.array([0.01, 0.02, 0.03]))
    for t in r["tests"]:
        assert "note" in t or "p_value" in t or "p_left_skew" in t
