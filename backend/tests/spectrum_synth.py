"""
Synthetic gamma spectra with known content, for the ROI and decay-chain tests.

Counts in a line = activity (Bq) * branching ratio * detector efficiency * live time, spread over a Gaussian whose width follows
the detector's resolution (FWHM proportional to sqrt(E)), on an exponential continuum, with Poisson noise from a fixed seed.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detector_efficiency import DETECTOR_DATABASE, interpolate_efficiency  # noqa: E402

# (energy keV, emission probability per decay of that nuclide) for the strong lines of each series
URANIUM_SERIES = {
    "Th-234": [(92.6, 0.055)],
    "Pa-234m": [(1001.0, 0.0084)],
    "Ra-226": [(186.2, 0.0364)],
    "Pb-214": [(241.9, 0.073), (295.2, 0.193), (351.9, 0.371)],
    "Bi-214": [(609.3, 0.461), (665.5, 0.0153), (768.4, 0.0489), (1120.3, 0.15), (1764.5, 0.154)],
}
THORIUM_SERIES = {
    "Ac-228": [(338.3, 0.113), (911.2, 0.258), (964.8, 0.0499), (969.0, 0.158)],
    "Pb-212": [(238.6, 0.436)],
    # Tl-208 is 35.94 % of the chain: its lines are quoted per chain decay (0.359 = 99.8 % of 36 %)
    "Tl-208": [(583.2, 0.305), (2614.5, 0.359)],
}


def linear_axis(n=1024, top=3000.0):
    return (np.arange(n) + 0.5) * top / n


def make_spectrum(detector, peaks, energies, continuum=300.0, seed=1):
    """Counts per channel for (energy, area-in-counts) peaks on an exponential continuum, with Poisson noise."""
    rng = np.random.default_rng(seed)
    resolution = DETECTOR_DATABASE[detector]["energy_resolution_662keV"]
    width = np.gradient(energies)
    y = continuum * np.exp(-energies / 700.0) * width / 3.0
    for energy, area in peaks:
        sigma = resolution * 662.0 * math.sqrt(energy / 662.0) / 2.3548
        y = y + area * width / (sigma * math.sqrt(2 * math.pi)) * np.exp(-0.5 * ((energies - energy) / sigma) ** 2)
    return rng.poisson(y).astype(float)


def series_spectrum(detector, series, activity_bq, live_time_s=3600.0, scale=None, continuum=300.0, seed=1, energies=None):
    """
    A spectrum of a decay series at `activity_bq` per member, optionally with some members scaled (e.g. {"Pb-214": 0.1}).
    Returns (energies, counts).
    """
    energies = linear_axis() if energies is None else energies
    scale = scale or {}
    peaks = []
    for nuclide, lines in series.items():
        for energy, probability in lines:
            area = activity_bq * scale.get(nuclide, 1.0) * probability * interpolate_efficiency(detector, energy) * live_time_s
            peaks.append((energy, area))
    return energies, make_spectrum(detector, peaks, energies, continuum=continuum, seed=seed)
