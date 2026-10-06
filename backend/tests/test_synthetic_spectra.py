"""
Golden tests on the synthetic spectrum generator: each file's intended peaks dominate, the noise is Poisson, and the analysis names the intended
source, with nothing artificial beside it, for several noise seeds. The generator is a test tool, not a measurement: what is asserted here is that
the app finds what was put in, not that it is right about the world.
"""
import logging
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import generate_test_spectra as gen  # noqa: E402

from spectroscopy.analysis_utils import analyze_spectrum_peaks  # noqa: E402

SEEDS = (1, 2)

# name -> (isotopes that must be listed, every isotope that may be listed, the decay chains that must be reported, the only chains allowed)
EXPECTED = {
    "synthetic_smoke_detector": ({"Am-241"}, {"Am-241"}, set(), set()),
    "synthetic_cobalt60": ({"Co-60"}, {"Co-60"}, set(), set()),
    "synthetic_cesium137": ({"Cs-137"}, {"Cs-137"}, set(), set()),
    "synthetic_potassium_k40": ({"K-40"}, {"K-40"}, set(), set()),
    "synthetic_radium_dial": ({"Bi-214"}, {"Bi-214", "Pb-214", "Ra-226", "U-238", "U-234", "Th-234"}, {"U-238"}, {"U-238"}),
    "synthetic_uranium_ore": ({"Bi-214", "Pb-214"}, {"Bi-214", "Pb-214", "Ra-226", "U-238", "U-234", "Th-234", "U-235", "Pa-234m"}, {"U-238"}, {"U-238"}),
}


def analyse(name):
    logging.disable(logging.CRITICAL)
    try:
        return analyze_spectrum_peaks(gen.spectrum_dict(name), True, gen.DEFAULT_LIVE_TIME)
    finally:
        logging.disable(logging.NOTSET)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_the_analysis_names_the_intended_source_and_nothing_else(name, seed):
    gen.seed(seed)
    result = analyse(name)
    must, may, chains_must, chains_may = EXPECTED[name]
    listed = {i["isotope"] for i in result["isotopes"] if not i.get("suppressed")}
    chains = {c["parent"] for c in result["decay_chains"]}
    assert must <= listed, f"{name} seed {seed}: missing {must - listed}, listed {listed}"
    assert listed <= may, f"{name} seed {seed}: unexpected {listed - may}"
    assert chains_must <= chains <= chains_may, f"{name} seed {seed}: chains {chains}"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_the_intended_peak_is_the_strongest_net_peak_found(name):
    """'Dominates': the strongest peak the finder reports sits on one of the lines that were put in, within a resolution width."""
    gen.seed(7)
    result = analyse(name)
    strongest = max(result["peaks"], key=lambda p: p.get("net_area", 0))
    put_in = {
        "synthetic_smoke_detector": [60], "synthetic_cobalt60": [1173, 1332], "synthetic_cesium137": [662], "synthetic_potassium_k40": [1461],
        "synthetic_radium_dial": [352, 609, 295], "synthetic_uranium_ore": [93, 352, 609],
    }[name]
    assert min(abs(strongest["energy"] - e) for e in put_in) < gen.fwhm_keV(strongest["energy"]), (name, strongest["energy"])


def test_the_same_seed_gives_the_same_spectrum_and_different_seeds_do_not():
    gen.seed(5)
    a = gen.generate_cesium137()
    gen.seed(5)
    b = gen.generate_cesium137()
    gen.seed(6)
    c = gen.generate_cesium137()
    assert (a == b).all() and not (a == c).all()


def test_the_noise_is_poisson_not_truncated():
    """Counts scatter with variance equal to their mean, and their mean is the expectation (a float truncated to int first lies low by 0.5)."""
    gen.seed(11)
    expectation = np.full(200_000, 3.4)
    drawn = gen.apply_poisson_noise(expectation)
    assert drawn.mean() == pytest.approx(3.4, abs=0.02)
    assert drawn.var() == pytest.approx(3.4, rel=0.03)


def test_the_compton_edge_is_smeared_not_a_hard_step():
    """The shelf falls across about a resolution width at the edge: neighbouring channels differ by a small fraction of the shelf height."""
    counts = np.zeros(gen.CHANNELS)
    gen.add_compton_continuum(counts, 662, 100_000)
    edge = int(round(gen.energy_to_channel(2 * 662 ** 2 / (511 + 2 * 662))))
    steps = np.abs(np.diff(counts[edge - 20: edge + 20]))
    assert steps.max() < 0.25 * counts[edge - 20]
