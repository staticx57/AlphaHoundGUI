"""calculate_mda honours its confidence level (it used to compute k for it and then always apply the 95 % limit, while echoing
the requested level back in the result)."""
import math
from statistics import NormalDist

import pytest

from spectroscopy.detector_efficiency import calculate_mda

ARGS = dict(background_counts=100.0, energy_keV=662, branching_ratio=0.851, live_time_s=600.0)


def test_default_is_the_familiar_95_percent_currie_limit():
    result = calculate_mda(**ARGS)
    assert result["valid"]
    assert result["detection_limit_counts"] == pytest.approx(2.71 + 4.65 * 10)
    assert result["confidence_level"] == 0.95


def test_explicit_95_percent_equals_the_default():
    assert calculate_mda(**ARGS, confidence_level=0.95) == calculate_mda(**ARGS)


@pytest.mark.parametrize("level", [0.90, 0.99, 0.999])
def test_other_levels_follow_currie_with_the_matching_quantile(level):
    k = NormalDist().inv_cdf(level)
    result = calculate_mda(**ARGS, confidence_level=level)
    assert result["detection_limit_counts"] == pytest.approx(k * k + 2 * math.sqrt(2) * k * 10, rel=1e-12)
    assert result["confidence_level"] == level


def test_the_limit_and_the_mda_rise_with_the_confidence_level():
    limits = [calculate_mda(**ARGS, confidence_level=c) for c in (0.90, 0.95, 0.99)]
    assert [r["detection_limit_counts"] for r in limits] == sorted(r["detection_limit_counts"] for r in limits)
    assert limits[0]["mda_bq"] < limits[1]["mda_bq"] < limits[2]["mda_bq"]


def test_ninety_nine_percent_is_about_forty_percent_higher_than_ninety_five_at_100_counts():
    ratio = calculate_mda(**ARGS, confidence_level=0.99)["detection_limit_counts"] / calculate_mda(**ARGS)["detection_limit_counts"]
    assert 1.3 < ratio < 1.5


@pytest.mark.parametrize("level", [0.0, 0.5, 1.0, 1.5, -0.1])
def test_a_confidence_level_outside_the_meaningful_range_is_rejected(level):
    result = calculate_mda(**ARGS, confidence_level=level)
    assert result["valid"] is False and result["mda_bq"] is None


def test_the_route_needs_the_lines_emission_probability():
    """It used to assume Cs-137's 0.85 for any energy: an MDA for Pb-212 238.6 keV (0.436) came out half the true value."""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    base = {"background_counts": 100.0, "energy_keV": 238.6, "live_time_s": 600.0, "detector": "AlphaHound CsI(Tl)"}
    assert client.post("/analyze/mda", json=base).status_code == 400
    with_br = client.post("/analyze/mda", json={**base, "branching_ratio": 0.436}).json()
    as_cs137 = client.post("/analyze/mda", json={**base, "branching_ratio": 0.851}).json()
    assert with_br["mda_bq"] / as_cs137["mda_bq"] == __import__("pytest").approx(0.851 / 0.436, rel=1e-6)
