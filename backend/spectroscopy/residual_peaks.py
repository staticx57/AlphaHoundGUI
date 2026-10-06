"""
Unassigned excesses: structure in a spectrum that the fitted peaks do not explain.

A scintillator spectrum is more than its photopeaks: iodine escape peaks (28.6 keV below a line), Compton backscatter humps (a photon turned
through ~180 degrees reaches the crystal with E / (1 + 2E/511)), the low-energy threshold, and sometimes an unresolved line. The peak search
finds none of these as peaks when they sit as a low shelf beside a very large peak, yet on a long capture they are plainly there: the
125-160 keV bump of an 8-hour thoriated lens is 26 standard errors over the continuum, and the 195-205 keV one beside it up to 32.

So this module shows them and does NOT use them. They are returned apart from `peaks` and never reach isotope identification: a bump at
140 keV matched Tc-99m (140.5), U-235 (143.8), Co-57 (136.5) and Tl-201 (135) in earlier experiments, which is exactly what the template fit
and the peak validation were built to keep out. The chart draws them as hollow rings and the peak table lists them as "unassigned".

How: the fitted peaks (Gaussians from their net areas and widths) are subtracted; around every channel a Gaussian of the detector's expected
width is fitted together with a linear continuum, weighted by the counting error plus a 2 % systematic on the counts there (the big peaks are not
exact Gaussians). An excess counts at 15 standard errors or more, above 100 keV, and not within three quarters of a width of a fitted peak
(that is the peak's own shape misfit).

Measured on 33 labelled spectra (tests/scoring_eval.py): 0-4 per thorium spectrum, median 1; a smooth continuum with Poisson noise gives none.
"""
import math
from typing import Dict, List, Optional, Sequence

import numpy as np

MIN_Z = 15.0                 # standard errors over the continuum
MIN_ENERGY_KEV = 100.0       # below: X-rays, backscatter of the low lines and the detector threshold dominate
MAX_ENERGY_KEV = 2000.0
SYSTEMATIC = 0.02            # relative error of the model of the large peaks, added to the counting error
PEAK_EXCLUSION = 0.75        # widths: an excess this close to a fitted peak is that peak's own shape misfit
MAX_MARKERS = 4              # the strongest few: more is a spectrum with structure everywhere, which a marker does not help


def _fwhm(r662: float, energy: float) -> float:
    return r662 * 662.0 * math.sqrt(max(energy, 1.0) / 662.0)


def _fitted_peaks_model(E: np.ndarray, dE: np.ndarray, peaks: Sequence[Dict]) -> np.ndarray:
    model = np.zeros_like(E)
    for p in peaks:
        sigma = float(p.get("fwhm") or 0.0) / 2.3548
        area = p.get("net_area")
        if sigma <= 0 or not area:
            continue
        model += float(area) * dE / (sigma * math.sqrt(2.0 * math.pi)) * np.exp(-0.5 * ((E - float(p["energy"])) / sigma) ** 2)
    return model


def find_unassigned_excess(energies, counts, peaks: Sequence[Dict], r662: float, edge_kev: float = 0.0) -> List[Dict]:
    """
    The excesses over the fitted peaks and a local continuum, strongest first, at most MAX_MARKERS, as
    {energy, significance, contrast, amplitude, fwhm_expected}; `contrast` is the excess over the counts there (0.08 = 8 %).
    """
    E = np.asarray(energies, dtype=float)
    c = np.asarray(counts, dtype=float)
    if E.size < 64 or E.size != c.size or not np.any(c > 0):
        return []
    dE = np.gradient(E)
    residual = c - _fitted_peaks_model(E, dE, peaks)
    low = max(MIN_ENERGY_KEV, edge_kev + 15.0)
    found = []
    for k in np.nonzero((E >= low) & (E <= MAX_ENERGY_KEV))[0]:
        e0 = float(E[k])
        fwhm = _fwhm(r662, e0)
        sigma = fwhm / 2.3548
        window = np.abs(E - e0) <= 2.0 * fwhm
        if window.sum() < 8:
            continue
        x = E[window] - e0
        y = residual[window]
        counts_here = np.maximum(c[window], 1.0)
        weight = 1.0 / (counts_here + (SYSTEMATIC * counts_here) ** 2)
        basis = np.vstack([np.exp(-0.5 * (x / sigma) ** 2), np.ones_like(x), x]).T
        try:
            covariance = np.linalg.inv((basis.T * weight) @ basis)
        except np.linalg.LinAlgError:
            continue
        beta = covariance @ ((basis.T * weight) @ y)
        amplitude, error = float(beta[0]), math.sqrt(max(float(covariance[0, 0]), 0.0))
        if amplitude <= 0 or error <= 0:
            continue
        z = amplitude / error
        if z >= MIN_Z:
            found.append((z, e0, amplitude, amplitude / max(float(c[k]), 1.0), fwhm))
    found.sort(key=lambda t: -t[0])
    kept: List[Dict] = []
    for z, e0, amplitude, contrast, fwhm in found:
        near_peak = any(abs(e0 - float(p["energy"])) <= PEAK_EXCLUSION * max(fwhm, float(p.get("fwhm") or 0.0)) for p in peaks)
        if near_peak or any(abs(e0 - k["energy"]) <= fwhm for k in kept):
            continue
        kept.append({"energy": round(e0, 1), "significance": round(z, 1), "contrast": round(contrast, 3), "amplitude": round(amplitude, 1),
                     "fwhm_expected": round(fwhm, 1)})
        if len(kept) >= MAX_MARKERS:
            break
    return sorted(kept, key=lambda k: k["energy"])
