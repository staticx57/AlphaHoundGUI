"""
ROI (Region-of-Interest) Analysis Engine

Provides quantitative isotope analysis including:
- Net counts calculation with background subtraction
- Activity calculation using detector efficiency
- Uncertainty estimation (counting statistics)
- Uranium enrichment ratio analysis

References:
- Knoll, G.F. "Radiation Detection and Measurement", 4th ed.
- IAEA Safety Series No. 120 "Calibration of Radiation Protection Monitoring Instruments"
"""

import math
from typing import Dict, List, NamedTuple, Sequence, Tuple, Optional

import numpy as np
from dataclasses import dataclass

from spectroscopy.detector_efficiency import get_detector, interpolate_efficiency
from spectroscopy.isotope_roi_database import get_roi_isotope
from spectroscopy.activity_calculator import calculate_activity_bq, bq_to_uci

import logging
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------------------------------------------------
# Window integration with a resolution-aware window and flanking background bands
#
# The old method summed a fixed window (about +-40 keV whatever the energy) and estimated the background from ONE band glued
# to the window. Measured on synthetic spectra with known peak areas it was biased low by 4 % at 662 keV, 15-20 % at 1.2-1.5 MeV
# and 30 % at 2.6 MeV: the window cut off the tails of the wider high-energy peaks, and the background band, starting where the
# window ended, caught the tails and inflated the background. It also scaled the band by keV width (a band of 17.2 channels
# counted as 17 or 18), took sqrt(gross + background) as the uncertainty whatever the band size, and tried to use a peak fit
# through an import that could never work (a relative import in a flat module, and an undefined name), swallowing the error.
#
# Now: the window is +-1 FWHM of the detector's resolution at that energy (98 % of a Gaussian peak, and the rest is corrected),
# the continuum under it is interpolated between two bands placed beyond the peak's tails, bands that would contain a
# neighbouring peak are dropped (the other side is used), and every count is weighted by how much of its channel lies inside
# the region, so widths in keV are exact.
# ----------------------------------------------------------------------------------------------------------------------

DEFAULT_RESOLUTION_662 = 0.10      # FWHM / E at 662 keV when the detector does not say
WINDOW_HALF_FWHM = 1.0             # window half-width, in FWHM
BAND_GAP_FWHM = 0.25               # gap between the window edge and a background band
BAND_WIDTH_FWHM = 0.6              # width of a background band
MIN_BAND_CHANNELS = 3
CLEARANCE_STEPS = (0.75, 0.35, 0.0)   # how far (in FWHM) a band must stay from a neighbouring peak; relaxed if no band qualifies
FWHM_PER_SIGMA = 2.354820045
RESOLVABLE_FWHM = 0.9                 # two lines closer than this (in FWHM) are one peak to the detector
# Systematic uncertainty of the continuum under a window, as a share of the background estimate, when it does not rest on two
# bands clear of neighbouring lines: one band must assume a flat continuum (+-30 to 50 % errors measured on sloping ones), two
# bands that touch a neighbour's tail are slightly high.
SYSTEMATIC_ONE_BAND = 0.5
SYSTEMATIC_RELAXED_BANDS = 0.1
MAX_FIT_CHI2 = 100.0                  # beyond this the model describes the region too badly to use at all


def expected_fwhm_keV(detector: Optional[Dict], energy_keV: float) -> float:
    """FWHM (keV) the detector should show at this energy: its stated resolution at 662 keV, scaled with sqrt(E)."""
    resolution = (detector or {}).get("energy_resolution_662keV") or DEFAULT_RESOLUTION_662
    return resolution * 662.0 * math.sqrt(max(energy_keV, 1.0) / 662.0)


def effective_branching_ratio(isotope: Dict, peak_keV: float, fwhm_keV: float, detector_name: str) -> Tuple[float, List[float]]:
    """
    The emission probability behind the peak. A scintillator cannot separate lines of one nuclide that lie closer than about a
    FWHM (Ac-228 911 / 965 / 969 keV, U-235 164 / 186 / 205 keV), so the counts under the peak come from all of them: using only
    the main line's probability overstated the activity by up to 50 % (Ac-228). The other lines are added in proportion to the
    detector's efficiency at their energy. Returns (effective probability, energies of the blended lines).
    """
    ratio = float(isotope["branching_ratio"])
    efficiency_at_peak = interpolate_efficiency(detector_name, peak_keV)
    blended: List[float] = []
    if efficiency_at_peak > 0:
        for energy, probability in isotope.get("companion_lines", ()):
            if abs(energy - peak_keV) < RESOLVABLE_FWHM * fwhm_keV:
                ratio += probability * interpolate_efficiency(detector_name, energy) / efficiency_at_peak
                blended.append(energy)
    return ratio, blended


def channel_edges(energies: np.ndarray) -> np.ndarray:
    """Boundaries between channels (midpoints of the centres, extended by half a channel at both ends)."""
    e = np.asarray(energies, dtype=float)
    mid = (e[1:] + e[:-1]) / 2.0
    return np.concatenate(([e[0] - (mid[0] - e[0])], mid, [e[-1] + (e[-1] - mid[-1])]))


def region_sum(edges: np.ndarray, counts: np.ndarray, lo: float, hi: float) -> Tuple[float, float, float]:
    """
    Counts, variance and covered fraction for the energy range [lo, hi]. A channel half inside counts half; the variance of a
    weighted Poisson sum is sum(w^2 * counts).
    """
    if not hi > lo:
        return 0.0, 0.0, 0.0
    left, right = edges[:-1], edges[1:]
    overlap = np.clip(np.minimum(right, hi) - np.maximum(left, lo), 0.0, None)
    weight = overlap / (right - left)
    total = float(np.sum(weight * counts))
    variance = float(np.sum(weight ** 2 * np.abs(counts)))
    return total, variance, float(np.sum(overlap) / (hi - lo))


def containment_fraction(half_width_keV: float, fwhm_keV: float) -> float:
    """Share of a Gaussian peak of this FWHM that lies within +- half_width of its centre."""
    sigma = fwhm_keV / FWHM_PER_SIGMA
    return math.erf(half_width_keV / (sigma * math.sqrt(2.0))) if sigma > 0 else 1.0


def integrate_peak(energies: np.ndarray, counts: np.ndarray, peak_keV: float, fwhm_keV: float,
                   neighbors: Sequence[float] = (), min_energy_keV: float = 0.0,
                   fallback_band: Optional[Tuple[float, float]] = None) -> Dict:
    """
    Gross, background and net counts for one peak. Returns a dict with the window, the bands used, the sums and variances,
    the containment of the window, and notes about anything that limits the result.
    """
    edges = channel_edges(energies)
    local_width = float(np.median(np.diff(energies))) if len(energies) > 1 else 1.0
    valid_lo = max(float(edges[0]), float(min_energy_keV))
    valid_hi = float(edges[-1])
    notes: List[Tuple[str, str]] = []      # (kind, text): kinds "band" and "overlap" are dropped when a peak fit replaces the window

    half = max(WINDOW_HALF_FWHM * fwhm_keV, 1.5 * local_width)
    win_lo, win_hi = peak_keV - half, peak_keV + half
    window_valid = max(0.0, min(win_hi, valid_hi) - max(win_lo, valid_lo)) / (win_hi - win_lo)
    gross, gross_var, _ = region_sum(edges, counts, win_lo, win_hi)

    def band_ok(lo, hi, clearance):
        if lo < valid_lo or hi > valid_hi:
            return False
        return not any(lo - clearance * fwhm_keV <= n <= hi + clearance * fwhm_keV for n in neighbors if abs(n - peak_keV) > 0.5)

    gap = BAND_GAP_FWHM * fwhm_keV
    width = max(BAND_WIDTH_FWHM * fwhm_keV, MIN_BAND_CHANNELS * local_width)
    lower = (peak_keV - half - gap - width, peak_keV - half - gap)
    upper = (peak_keV + half + gap, peak_keV + half + gap + width)

    # Two bands (one each side) are worth far more than a clean single band: a band on both sides lets the continuum slope
    # through the window, a single one has to assume it flat, which fails on a shoulder (measured on a real Am-241 spectrum:
    # 14,000 net counts reported at 93 keV, where there is nothing, from the one band above the 59.5 keV peak's tail). So the
    # clearance from neighbouring lines is relaxed until both bands qualify, and only then is one band accepted.
    bands: List[Tuple[float, float]] = []
    clearance_used = None
    for clearance in CLEARANCE_STEPS:
        candidate = [b for b in (lower, upper) if band_ok(b[0], b[1], clearance)]
        if len(candidate) == 2:
            bands, clearance_used = candidate, clearance
            break
    if not bands:
        for clearance in CLEARANCE_STEPS:
            bands = [b for b in (lower, upper) if band_ok(b[0], b[1], clearance)]
            if bands:
                clearance_used = clearance
                break
    if bands and clearance_used < CLEARANCE_STEPS[0]:
        notes.append(("band", "A neighbouring peak is close to the background band, so the background may be slightly high."))
    strict = len(bands) == 2 and clearance_used == CLEARANCE_STEPS[0]

    background = background_var = 0.0
    if len(bands) == 2:
        densities = []
        for lo, hi in bands:
            total, var, _ = region_sum(edges, counts, lo, hi)
            densities.append((total / (hi - lo), var / (hi - lo) ** 2))
        # two bands at equal distance on either side: the continuum under the window is the mean of the two densities
        background = half * (densities[0][0] + densities[1][0])
        background_var = half ** 2 * (densities[0][1] + densities[1][1])
        method = "interpolated between a band on each side of the peak"
    elif len(bands) == 1:
        total, var, _ = region_sum(edges, counts, *bands[0])
        density, density_var = total / (bands[0][1] - bands[0][0]), var / (bands[0][1] - bands[0][0]) ** 2
        background = 2 * half * density
        background_var = (2 * half) ** 2 * density_var
        side = "below" if bands[0] is lower or bands[0] == lower else "above"
        method = f"one band {side} the peak (flat continuum assumed)"
        # How wrong "flat" can be is in the data: the band on the other side was set aside (a neighbouring line may sit in it),
        # but if the continuum were a straight line between the two, the window's background would differ from the flat guess
        # by half * (density difference). Taken as a systematic uncertainty, it is large exactly where the guess is shaky (the
        # shoulder of a strong peak) and negligible on a flat continuum.
        other = upper if side == "below" else lower
        if other[0] >= valid_lo and other[1] <= valid_hi:
            other_total, _, _ = region_sum(edges, counts, *other)
            density_difference = other_total / (other[1] - other[0]) - density
            background_var += (half * density_difference) ** 2
        notes.append(("band", f"Only one background band is usable (the other side is a neighbouring peak or outside the spectrum): "
                              f"the continuum under the peak is taken as flat from the band {side} it."))
    elif fallback_band is not None:
        lo, hi = fallback_band
        total, var, _ = region_sum(edges, counts, lo, hi)
        if hi > lo and window_valid > 0:
            scale = (2 * half) / (hi - lo)
            background, background_var = total * scale, var * scale ** 2
        method = "the database background region (no clean band on either side)"
        notes.append(("band", "No clean background band on either side of the peak: the fixed region from the isotope database was used."))
    else:
        method = "none"
        notes.append(("band", "No usable background region: the background is taken as zero, so the net counts are an upper bound."))

    systematic = 0.0 if strict else (SYSTEMATIC_RELAXED_BANDS if len(bands) == 2 else SYSTEMATIC_ONE_BAND)
    if background > 0 and systematic > 0:
        background_var += (systematic * background) ** 2
    c = containment_fraction(half, fwhm_keV)
    interferers = [n for n in neighbors if abs(n - peak_keV) > 0.5 and abs(n - peak_keV) <= half + 0.5 * fwhm_keV]
    separable = [n for n in interferers if abs(n - peak_keV) >= RESOLVABLE_FWHM * fwhm_keV]
    if interferers:
        notes.append(("overlap" if separable else "unresolved",
                      "A neighbouring peak at " + ", ".join(f"{n:g}" for n in interferers) + " keV overlaps the window: "
                      + ("if it is present in your spectrum the net counts include part of it (the peak fit below shows the difference)." if separable else
                         "it is closer than this detector can resolve, so the net counts include part of it.")))
    if window_valid < 0.999:
        where = "outside the spectrum" if window_valid <= 0.0 else "partly outside the spectrum or below the detector's energy threshold"
        notes.append(("range", f"The ROI window is {where} ({window_valid * 100:.0f}% of it usable)."))

    return {
        "window": (win_lo, win_hi), "bands": bands, "gross": gross, "gross_var": gross_var,
        "background": max(background, 0.0), "background_var": background_var, "net_raw": gross - background,
        "containment": c, "window_valid": window_valid, "method": method, "notes": notes, "fwhm": fwhm_keV,
        "separable_interferers": separable, "strict_bands": strict,
    }


def channel_width_at(energies: np.ndarray, energy_keV: float) -> float:
    """Width (keV) of the channels around this energy: the energy axis need not be linear (Radiacode spectra have a quadratic one)."""
    e = np.asarray(energies, dtype=float)
    if e.size < 2:
        return 1.0
    steps = np.diff(e)
    centres = (e[1:] + e[:-1]) / 2.0
    return float(np.interp(energy_keV, centres, steps))


def fit_peak_group(energies: np.ndarray, counts: np.ndarray, peak_keV: float, neighbors: Sequence[float],
                   fwhm_keV: float, local_width: float) -> Dict:
    """
    Fit the peak together with the neighbouring peaks that fall in its neighbourhood: Gaussians whose widths follow the
    detector's sqrt(E) law from one shared resolution, at their nominal energies plus one common calibration shift, on a
    linear baseline, with Poisson weights. This is how to separate overlapping lines (the Co-60 pair, Bi-214 beside
    Cs-137, Ac-228 911 / 969 keV) and how to get a net area when no clean background band exists.

    The peak's own amplitude may be negative (a hole in the continuum is a result, not a failure), so an empty region gives a
    net near zero with an honest uncertainty instead of "no fit". The width and shift are fitted only when the peak is clear
    (4 sigma): below that they would chase noise and bias the net upwards, so the fit is repeated with the detector's expected
    width (and the shift found, if any).

    Returns {"success": False} or the net counts (the whole peak), their uncertainty, the measured FWHM (None when the width
    was held fixed), the baseline at the peak and the quality of the fit.
    """
    from scipy.optimize import curve_fit

    half_fit = 2.5 * fwhm_keV
    # lines closer than 0.9 FWHM cannot be told apart from the peak: with a free amplitude the fit would split one peak between
    # two Gaussians (measured: -24 % and wild scatter for a BGO Cs-137 peak with a 609 keV neighbour that was not there)
    group = [peak_keV] + sorted(n for n in neighbors if RESOLVABLE_FWHM * fwhm_keV <= abs(n - peak_keV) <= half_fit + 0.5 * fwhm_keV)
    lo = min(peak_keV - half_fit, min(group) - fwhm_keV)
    hi = max(peak_keV + half_fit, max(group) + fwhm_keV)
    mask = (energies >= lo) & (energies <= hi)
    x, y = energies[mask], counts[mask]
    n_params = 4 + len(group)
    if x.size < n_params + 6 or not local_width > 0:
        return {"success": False}

    sigma0 = fwhm_keV / FWHM_PER_SIGMA
    scale = math.sqrt(2.0 * math.pi) / local_width

    def model(xx, b0, b1, s, shift, *amps):
        out = b0 + b1 * (xx - peak_keV)
        for centre, amp in zip(group, amps):
            width = s * math.sqrt(max(centre, 1.0) / peak_keV)
            out = out + amp * np.exp(-0.5 * ((xx - centre - shift) / width) ** 2)
        return out

    floor = float(np.median(np.sort(y)[: max(3, y.size // 4)]))
    amps0 = []
    for centre in group:
        near = np.abs(x - centre) <= 0.5 * fwhm_keV
        amps0.append(max(1.0, float(np.max(y[near])) - floor) if np.any(near) else 1.0)
    amp_lower = [-np.inf] + [0.0] * (len(group) - 1)

    def run(fn, p0, lower, upper):
        # Poisson weights from the data are biased low at small counts (a channel that happened to read low gets more weight):
        # the second pass weighs with the first model
        weight = np.sqrt(np.maximum(y, 1.0))
        popt = pcov = None
        for _ in range(2):
            popt, pcov = curve_fit(fn, x, y, p0=p0, bounds=(lower, upper), sigma=weight, absolute_sigma=True, maxfev=20000)
            p0 = list(popt)
            weight = np.sqrt(np.maximum(fn(x, *popt), 1.0))
        if not (np.all(np.isfinite(popt)) and np.all(np.isfinite(pcov))):
            raise ValueError("fit has no finite covariance")
        chi2_red = float(np.sum(((y - fn(x, *popt)) / weight) ** 2) / max(1, x.size - len(popt)))
        return popt, pcov, chi2_red

    # --- free width and shift ---
    free = None
    try:
        popt, pcov, chi2_red = run(model, [floor, 0.0, sigma0, 0.0] + amps0,
                                   [-np.inf, -np.inf, 0.4 * sigma0, -0.4 * fwhm_keV] + amp_lower,
                                   [np.inf, np.inf, 2.5 * sigma0, 0.4 * fwhm_keV] + [np.inf] * len(group))
        s, amp = popt[2], popt[4]
        var = (s * scale) ** 2 * pcov[4, 4] + (amp * scale) ** 2 * pcov[2, 2] + 2 * (s * scale) * (amp * scale) * pcov[4, 2]
        # a fit that describes the data worse than their Poisson scatter allows (strong peaks are not exact Gaussians) has
        # its uncertainties scaled by sqrt(chi2 / dof): the Birge ratio
        free = {"popt": popt, "net": float(amp * s * scale), "sigma": float(math.sqrt(max(var, 0.0)) * math.sqrt(max(1.0, chi2_red))),
                "fwhm": float(s * FWHM_PER_SIGMA), "chi2_red": chi2_red, "b0_var": float(pcov[0, 0])}
    except Exception as exc:                                     # no convergence, singular covariance, ...
        logger.debug("ROI group fit (free width) failed: %s", exc)

    def result(popt, net, sigma, chi2_red, fwhm, shape):
        b0, shift = float(popt[0]), float(popt[3] if shape == "free" else 0.0)
        return {"success": True, "net": float(net), "sigma": float(sigma), "fwhm": fwhm, "shape": shape, "shift": shift,
                "chi2_red": chi2_red, "baseline_at_peak": b0, "group": group}

    if free and free["chi2_red"] < MAX_FIT_CHI2 and free["sigma"] > 0 and free["net"] >= 4.0 * free["sigma"] \
            and 0.5 * fwhm_keV <= free["fwhm"] <= 2.0 * fwhm_keV:
        out = result(free["popt"], free["net"], free["sigma"], free["chi2_red"], free["fwhm"], "free")
        out["baseline_var"] = free["b0_var"] * max(1.0, free["chi2_red"])
        return out

    # --- the detector's expected width; the shift only if the free fit found the peak at 3 sigma ---
    shift_fixed = 0.0
    if free and free["sigma"] > 0 and free["net"] >= 3.0 * free["sigma"]:
        shift_fixed = float(np.clip(free["popt"][3], -0.4 * fwhm_keV, 0.4 * fwhm_keV))

    def fixed_model(xx, b0, b1, *amps):
        return model(xx, b0, b1, sigma0, shift_fixed, *amps)

    try:
        popt, pcov, chi2_red = run(fixed_model, [floor, 0.0] + amps0, [-np.inf, -np.inf] + amp_lower, [np.inf] * (2 + len(group)))
    except Exception as exc:
        logger.debug("ROI group fit (fixed width) failed: %s", exc)
        return {"success": False}
    var = (sigma0 * scale) ** 2 * pcov[2, 2] * max(1.0, chi2_red)
    if not (chi2_red < MAX_FIT_CHI2 and var > 0):
        return {"success": False}
    out = result(popt, popt[2] * sigma0 * scale, math.sqrt(var), chi2_red, None, "fixed")
    out["shift"] = shift_fixed
    out["baseline_var"] = float(pcov[0, 0]) * max(1.0, chi2_red)
    return out


@dataclass
class ROIResult:
    """Results from ROI analysis."""
    isotope_name: str
    energy_keV: float
    roi_window: Tuple[float, float]
    
    # Counts
    gross_counts: int
    background_counts: float
    net_counts: float
    uncertainty_sigma: float
    
    # Activity
    activity_bq: Optional[float]
    activity_uci: Optional[float]
    
    # Metadata
    detector: str
    acquisition_time_s: float
    efficiency_percent: float
    branching_ratio: float
    effective_branching_ratio: Optional[float] = None   # including same-nuclide lines blended into the peak (what the activity uses)
    
    # Detection quality metrics
    detected: bool = False                    # Is isotope actually detected?
    confidence: float = 0.0                   # Confidence score 0.0-1.0
    snr: float = 0.0                          # Signal-to-noise ratio
    fit_success: bool = False                 # Was advanced fitting successful?
    resolution: Optional[float] = None        # Energy Resolution (%)
    fwhm: Optional[float] = None              # Full Width Half Max (keV)
    detection_limit_counts: float = 0.0       # Minimum detectable counts (3-sigma)
    detection_status: str = "Not Detected"    # Status message
    limiting_factors: List[str] = None        # Why confidence is low
    recommendations: List[str] = None         # What would improve results
    
    # Optional MDA for non-detects
    mda_bq: Optional[float] = None
    mda_uci: Optional[float] = None
    activity_uncertainty_bq: Optional[float] = None  # 1-sigma statistical (counting) uncertainty
    
    # Optional ratio analysis
    ratio_analysis: Optional[Dict] = None

    # How the number was obtained
    background_bands: Optional[List[Tuple[float, float]]] = None   # the continuum bands used
    background_method: str = ""
    containment: float = 1.0                  # share of the peak inside the window (net counts are corrected for it)
    expected_fwhm_keV: Optional[float] = None
    net_counts_in_window: Optional[float] = None   # gross - background, before the containment correction
    fit_net_counts: Optional[float] = None    # net counts from a Gaussian peak fit (a cross-check), if the fit worked
    warnings: Optional[List[str]] = None
    analysis_valid: bool = True               # False when the ROI lies outside the spectrum




def _validated_spectrum(energies, counts) -> Tuple[np.ndarray, np.ndarray]:
    """The spectrum as sorted float arrays; ValueError (a 400 for the API) when it cannot be analysed."""
    e_arr = np.asarray(energies, dtype=float)
    c_arr = np.asarray(counts, dtype=float)
    if e_arr.shape != c_arr.shape or e_arr.ndim != 1:
        raise ValueError(f"energies and counts must be lists of the same length ({e_arr.size} vs {c_arr.size}).")
    if e_arr.size < 10:
        raise ValueError("A spectrum needs at least 10 channels for ROI analysis.")
    if not (np.all(np.isfinite(e_arr)) and np.all(np.isfinite(c_arr))):
        raise ValueError("The spectrum contains values that are not numbers.")
    if np.any(np.diff(e_arr) <= 0):
        order = np.argsort(e_arr)
        e_arr, c_arr = e_arr[order], c_arr[order]
        if np.any(np.diff(e_arr) <= 0):
            raise ValueError("The energy axis has repeated values.")
    return e_arr, c_arr


def _source_validation(isotope_name: str, source_type: str) -> Tuple[Optional[str], Optional[str]]:
    """(note, warning): whether the isotope fits the selected source type's profile; both None for 'auto' or unknown types."""
    try:
        from spectroscopy.source_identification import get_source_signature
        signature = get_source_signature(source_type) if source_type and source_type not in ["auto", "unknown"] else None
    except ImportError:
        signature = None

    if signature:
        if isotope_name in signature.excluding_isotopes:
            return None, f"Isotope {isotope_name} is NOT expected in {signature.name}. Detection may be background or interference."
        if isotope_name in signature.required_isotopes or isotope_name in signature.supporting_isotopes:
            return f"Consistent with {signature.name} profile.", None
    return None, None


def _detection_status(analysis_valid: bool, detected: bool, snr: float, raw_net_counts: float) -> str:
    if not analysis_valid:
        return "Not analysable (ROI outside the spectrum)"
    if detected:
        if snr >= 10:
            return "Strong Detection"
        if snr >= 5:
            return "Good Detection"
        if snr >= 3:
            return "Weak Detection"
        return "Marginal Detection"
    if raw_net_counts < 0:
        return "Not Detected (over-subtracted)"
    return "Not Detected (below limit)"


def _detection_confidence(detected: bool, net_counts: float, detection_limit_counts: float, snr: float,
                          uncertainty: float, acquisition_time_s: float) -> float:
    """Confidence score (0.0 - 1.0): signal against the detection limit, SNR, and statistical precision."""
    confidence = 0.0
    if detected:
        excess_ratio = net_counts / detection_limit_counts if detection_limit_counts > 0 else 0
        confidence += min(0.4, 0.1 * excess_ratio)
        confidence += min(0.4, 0.04 * snr)
        if net_counts > 0:
            relative_error = uncertainty / net_counts
            confidence += max(0, 0.2 * (1 - min(1, relative_error)))
    confidence = min(1.0, max(0.0, confidence))
    if acquisition_time_s < 60:
        confidence *= 0.8   # a very short acquisition: higher risk of transient noise
    return min(1.0, max(0.0, confidence))


def _limits_and_recommendations(*, analysis_valid: bool, detected: bool, confidence: float, snr: float, net_counts: float,
                                uncertainty: float, detection_limit_counts: float, acquisition_time_s: float,
                                efficiency_percent: float, peak_energy: float, source_type: str,
                                source_validation_warning: Optional[str], source_validation_note: Optional[str]
                                ) -> Tuple[List[str], List[str], float]:
    """What limits the result and what to do about it: (limiting_factors, recommendations, adjusted confidence)."""
    limiting_factors: List[str] = []
    recommendations: List[str] = []

    if source_validation_warning:
        limiting_factors.append(source_validation_warning)
        confidence *= 0.3
        recommendations.append(f"Verify source type selection (selected: {source_type})")
    if source_validation_note:
        confidence = min(1.0, confidence + 0.1)

    if not analysis_valid:
        limiting_factors.append("The region of interest is outside the energy range of this spectrum.")
        recommendations.append("Choose an isotope whose peak lies inside the spectrum, or check that the spectrum is energy-calibrated.")
    elif not detected:
        limiting_factors.append(f"Signal below detection limit ({net_counts:.0f} < {detection_limit_counts:.0f} counts)")
        if net_counts > 0 and detection_limit_counts > 0:
            recommended_time = acquisition_time_s * (detection_limit_counts / net_counts) ** 2
            if recommended_time < 86400:
                recommendations.append(f"Increase acquisition to ~{recommended_time / 60:.0f} min for detection")
            else:
                recommendations.append("Source may be too weak for this detector")
        else:
            recommendations.append("Longer acquisition time needed")
    elif confidence < 0.5:
        if snr < 5:
            limiting_factors.append(f"Low signal-to-noise ratio (SNR: {snr:.1f})")
            time_needed = acquisition_time_s * (5 / max(snr, 0.1)) ** 2
            recommendations.append(f"Increase acquisition to ~{time_needed / 60:.0f} min for better SNR")
        if uncertainty / max(net_counts, 1) > 0.3:
            limiting_factors.append(f"High statistical uncertainty (±{uncertainty / max(net_counts, 1) * 100:.0f}%)")
            recommendations.append("More counts needed for precise measurement")
        if net_counts < 100:
            limiting_factors.append(f"Low signal strength ({net_counts:.0f} counts)")
    elif confidence < 0.8 and snr < 10:
        limiting_factors.append(f"Moderate signal-to-noise ratio (SNR: {snr:.1f})")

    if efficiency_percent < 5:
        limiting_factors.append(f"Low detector efficiency at {peak_energy:.0f} keV ({efficiency_percent:.1f}%)")
        recommendations.append("Energy region may be outside detector's optimal range")
    if acquisition_time_s < 300 and not detected and analysis_valid:
        recommendations.append("Consider minimum 5-10 minute acquisition for weak sources")
    if acquisition_time_s < 60:
        limiting_factors.append(f"Short acquisition time ({acquisition_time_s:.0f}s < 60s) limits reliability")
        recommendations.append("Acquire for > 1 minute to improve confidence")

    return limiting_factors, recommendations, confidence


class _PeakMeasurement(NamedTuple):
    """What the window integration and the peak fit say about one line (see _measure_peak)."""
    roi: dict
    notes: list
    containment: float
    window: tuple
    gross_counts: float
    background_counts: float
    background_var: float
    net_in_window: Optional[float]
    raw_net_counts: float
    uncertainty: float
    analysis_valid: bool
    fit_success: bool
    fit_net: Optional[float]
    fit_fwhm: Optional[float]
    fit_resolution: Optional[float]
    roi_method: str


def _measure_peak(e_arr, c_arr, isotope, peak_energy, expected_fwhm, min_energy) -> _PeakMeasurement:
    """
    Net counts of one line: a window integration with background bands, and a fit of the peak with its neighbours as a
    cross-check, as the measured resolution, and as the primary result when the window method cannot give a clean one.
    """

    roi = integrate_peak(e_arr, c_arr, peak_energy, expected_fwhm, isotope.get("neighbor_peaks_keV", ()),
                         min_energy, isotope.get("background_region"))
    notes: List[Tuple[str, str]] = list(roi["notes"])
    containment = roi["containment"]
    window = roi["window"]
    gross_counts = roi["gross"]
    background_counts = roi["background"]
    net_in_window = roi["net_raw"]
    sigma_window = math.sqrt(max(roi["gross_var"] + roi["background_var"], 0.0))
    raw_net_counts = net_in_window / containment                       # the whole peak, not just what fits the window
    uncertainty = sigma_window / containment
    analysis_valid = roi["window_valid"] >= 0.5

    # --- A fit of the peak with its neighbours: a cross-check, the measured resolution, and the primary result when the
    # window method cannot give a clean one ---
    neighbors = isotope.get("neighbor_peaks_keV", ())
    local_width = channel_width_at(e_arr, peak_energy)
    grp = fit_peak_group(e_arr, c_arr, peak_energy, neighbors, expected_fwhm, local_width) if analysis_valid else {"success": False}
    fit_success = bool(grp["success"])
    fit_net = grp.get("net") if fit_success else None
    fit_fwhm = grp.get("fwhm") if fit_success else None          # None when the fit held the width at the expected value
    fit_resolution = (fit_fwhm / peak_energy * 100.0) if fit_fwhm else None
    # The window method needs a continuum band on BOTH sides (measured on synthetic spectra: unbiased then, but +-30 % to +-50 %
    # with a single band on a sloping continuum). A band is dropped when a neighbouring line could lie in it, whether or not
    # that line is really in the spectrum, so in that case (and with no band at all) the fit, which gives each neighbour an
    # amplitude of its own, is the primary result.
    window_is_clean = roi["strict_bands"]
    background_var = roi["background_var"]
    if fit_success and not window_is_clean:
        half_window = (window[1] - window[0]) / 2.0
        channels_in_window = 2.0 * half_window / local_width
        raw_net_counts = grp["net"]
        uncertainty = grp["sigma"]
        background_counts = max(grp["baseline_at_peak"], 0.0) * channels_in_window
        background_var = grp["baseline_var"] * channels_in_window ** 2
        containment = 1.0
        net_in_window = None
        notes = [(k, t) for k, t in notes if k not in ("band", "overlap")]
        others = ", ".join(f"{g:g}" for g in grp["group"][1:])
        notes.append(("fit", "Net counts come from a fit of this peak" + (f" together with its neighbours ({others} keV)" if others else "")
                      + ", because background bands on both sides of it could not be used."))
        width_note = "measured width" if grp["shape"] == "free" else "expected width"
        roi_method = "peak fit" + (" with neighbouring lines" if others else "") + f" (linear baseline, {width_note})"
    else:
        roi_method = roi["method"]
        if fit_success and analysis_valid and abs(fit_net - raw_net_counts) > 3 * math.sqrt(uncertainty ** 2 + grp["sigma"] ** 2) and abs(fit_net - raw_net_counts) > 20:
            notes.append(("fit", f"The peak fit ({fit_net:.0f} counts) and the window integration ({raw_net_counts:.0f}) disagree: "
                                 "a neighbouring peak or an uneven continuum is likely affecting one of them."))

    return _PeakMeasurement(
        roi=roi, notes=notes, containment=containment, window=window, gross_counts=gross_counts,
        background_counts=background_counts, background_var=background_var, net_in_window=net_in_window,
        raw_net_counts=raw_net_counts, uncertainty=uncertainty, analysis_valid=analysis_valid,
        fit_success=fit_success, fit_net=fit_net, fit_fwhm=fit_fwhm, fit_resolution=fit_resolution,
        roi_method=roi_method)


def _activities(analysis_valid, efficiency, acquisition_time_s, branching_ratio, detection_limit_counts, detected,
                net_counts, uncertainty):
    """(activity Bq, activity uCi, activity uncertainty Bq, MDA Bq, MDA uCi); the activity only for a detected peak."""
    # Minimum detectable activity, always (the reference for a non-detection)
    activity_bq = activity_uci = activity_uncertainty_bq = mda_bq = mda_uci = None
    if analysis_valid and efficiency > 0 and acquisition_time_s > 0 and branching_ratio > 0:
        mda_bq = calculate_activity_bq(detection_limit_counts, acquisition_time_s, efficiency, branching_ratio)
        mda_uci = bq_to_uci(mda_bq)
        if detected:
            # an activity is only reported for a detected peak; for the rest, the upper limit is the MDA
            activity_bq = calculate_activity_bq(net_counts, acquisition_time_s, efficiency, branching_ratio)
            activity_uci = bq_to_uci(activity_bq)
            activity_uncertainty_bq = calculate_activity_bq(uncertainty, acquisition_time_s, efficiency, branching_ratio)
    return activity_bq, activity_uci, activity_uncertainty_bq, mda_bq, mda_uci


class ROIAnalyzer:
    """
    Performs Region-of-Interest analysis on gamma spectra.
    """
    
    def __init__(self, detector_name: str = "AlphaHound BGO"):
        self.detector_name = detector_name
        self.detector = get_detector(detector_name)
        if self.detector is None:
            raise ValueError(f"Unknown detector: {detector_name}")

    def analyze(
        self,
        energies: List[float],
        counts: List[float],
        isotope_name: str,
        acquisition_time_s: float,
        source_type: str = "auto"
    ) -> ROIResult:
        """
        ROI analysis of one isotope: net counts with a proper uncertainty, activity if the peak is detected, the minimum
        detectable activity, and what limits the result.

        Args:
            energies: energy (keV) of each channel (ascending)
            counts: counts in each channel (may be fractional, e.g. background-subtracted)
            isotope_name: name from the ROI database
            acquisition_time_s: live time in seconds
            source_type: optional source context (e.g. 'uranium_glass') used to judge whether the isotope is expected
        """
        isotope = get_roi_isotope(isotope_name)
        if not isotope:
            raise ValueError(f"Unknown isotope: {isotope_name}")

        e_arr, c_arr = _validated_spectrum(energies, counts)

        peak_energy = isotope["energy_keV"]
        expected_fwhm = expected_fwhm_keV(self.detector, peak_energy)
        branching_ratio, blended_lines = effective_branching_ratio(isotope, peak_energy, expected_fwhm, self.detector_name)
        min_energy = float(self.detector.get("min_energy_keV") or 0.0)

        (roi, notes, containment, window, gross_counts, background_counts, background_var, net_in_window,
         raw_net_counts, uncertainty, analysis_valid, fit_success, fit_net, fit_fwhm, fit_resolution,
         roi_method) = _measure_peak(e_arr, c_arr, isotope, peak_energy, expected_fwhm, min_energy)
        warnings: List[str] = [t for _, t in notes]

        # Net counts (negative is kept as raw for the status message, but cannot be an activity)
        net_counts = max(0.0, raw_net_counts)

        # Does the isotope fit the selected source type?
        source_validation_note, source_validation_warning = _source_validation(isotope_name, source_type)

        # === DETECTION QUALITY METRICS ===
        # Currie's detection limit for a background estimated from bands: with no peak the net counts have variance B + var(B),
        # and L_D = 2.71 + 3.29 * sigma0 (with equal-size bands this is the familiar 2.71 + 4.65 sqrt(B)).
        null_sigma = math.sqrt(background_counts + background_var)
        detection_limit_counts = (2.71 + 3.29 * null_sigma) / containment

        snr = net_counts / uncertainty if uncertainty > 0 else 0.0
        # SNR >= 2 is a practical threshold that matches peak detection sensitivity
        detected = analysis_valid and snr >= 2.0 and net_counts > 20

        detection_status = _detection_status(analysis_valid, detected, snr, raw_net_counts)

        confidence = _detection_confidence(detected, net_counts, detection_limit_counts, snr, uncertainty, acquisition_time_s)

        # Efficiency at the peak energy
        efficiency = interpolate_efficiency(self.detector_name, peak_energy)
        efficiency_percent = efficiency * 100

        # Minimum detectable activity, always (the reference for a non-detection)
        activity_bq, activity_uci, activity_uncertainty_bq, mda_bq, mda_uci = _activities(
            analysis_valid, efficiency, acquisition_time_s, branching_ratio, detection_limit_counts, detected,
            net_counts, uncertainty)
        if blended_lines:
            notes_line = ", ".join(f"{e:g}" for e in blended_lines)
            warnings.append(f"Other lines of this nuclide ({notes_line} keV) fall inside the peak at this detector's resolution; "
                            f"the activity uses the combined emission probability ({branching_ratio * 100:.1f} % instead of "
                            f"{isotope['branching_ratio'] * 100:.1f} %).")
        warnings.append("Efficiencies are generic estimates for this detector, not a calibration of your geometry: "
                        "treat Bq values as indicative and calibrate with a known source for accurate ones.")

        limiting_factors, recommendations, confidence = _limits_and_recommendations(
            analysis_valid=analysis_valid, detected=detected, confidence=confidence, snr=snr, net_counts=net_counts,
            uncertainty=uncertainty, detection_limit_counts=detection_limit_counts, acquisition_time_s=acquisition_time_s,
            efficiency_percent=efficiency_percent, peak_energy=peak_energy, source_type=source_type,
            source_validation_warning=source_validation_warning, source_validation_note=source_validation_note)

        return ROIResult(
            isotope_name=isotope_name,
            energy_keV=peak_energy,
            roi_window=window,
            gross_counts=gross_counts,
            background_counts=background_counts,
            net_counts=net_counts,
            uncertainty_sigma=uncertainty,
            activity_bq=activity_bq,
            activity_uci=activity_uci,
            activity_uncertainty_bq=activity_uncertainty_bq,
            mda_bq=mda_bq,
            mda_uci=mda_uci,
            detector=self.detector_name,
            acquisition_time_s=acquisition_time_s,
            efficiency_percent=efficiency_percent,
            branching_ratio=isotope["branching_ratio"],
            effective_branching_ratio=branching_ratio,
            detected=detected,
            confidence=confidence,
            snr=snr,
            fit_success=fit_success,
            resolution=fit_resolution,
            fwhm=fit_fwhm,
            detection_limit_counts=detection_limit_counts,
            detection_status=detection_status,
            limiting_factors=limiting_factors if limiting_factors else None,
            recommendations=recommendations if recommendations else None,
            background_bands=[tuple(b) for b in roi["bands"]],
            background_method=roi_method,
            containment=containment,
            expected_fwhm_keV=expected_fwhm,
            net_counts_in_window=net_in_window,
            fit_net_counts=fit_net,
            warnings=warnings,
            analysis_valid=analysis_valid,
        )


    # a marker counts as present when its peak is significant (SNR >= 2) and has enough counts: a bare count threshold
    # is crossed by noise on a busy continuum
    URANIUM_MARKER_MIN_COUNTS = 30

    @classmethod
    def _marker_present(cls, result) -> bool:
        return bool(result and result.detected and result.net_counts > cls.URANIUM_MARKER_MIN_COUNTS)

    def _measure_uranium_markers(self, energies, counts, acquisition_time_s):
        """
        ROI results for the U-238 series markers: Th-234 (93 keV), Bi-214 (609 keV) and Pa-234m (1001 keV).
        Returns (th234, bi214, pa234m, diagnostics); a marker that cannot be analysed is None.
        """
        diagnostics = []
        results = []
        for label in ("Th-234 (93 keV)", "Bi-214 (609 keV)", "Pa-234m (1001 keV)"):
            result = None
            try:
                result = self.analyze(energies, counts, label, acquisition_time_s)
                diagnostics.append(f"{label}: {result.net_counts:.0f} ± {result.uncertainty_sigma:.0f} counts")
            except Exception as exc:
                logger.warning("Uranium prerequisite check failed: %s", exc)
            results.append(result)
        return results[0], results[1], results[2], diagnostics

    def _bi214_is_radium(self, energies, counts, diagnostics) -> bool:
        """
        Does the counted 609 keV peak come from Bi-214 (radium)? At scintillator resolution Tl-208 583 keV (thorium) and Cs-137 662 keV fall
        inside the Bi-214 window, and the window cannot tell them apart: a thoriated lens and a Cs-137 check source were reported as holding
        Ra-226 in secular equilibrium. The full-spectrum template fit can: when it finds thorium or Cs-137 and no radium series, the peak is
        theirs, provided the peak also sits nearer their line than 609.3 keV (the fit alone can slide a one-line template onto an unrelated
        peak). In every other case (radium found, no fit, neither source, the peak where Bi-214 would be) the Bi-214 reading stands.
        """
        try:
            from spectroscopy.source_templates import fit_source_templates, _resolution
            from spectroscopy.calibration_check import measure_line
            fit = fit_source_templates(energies, counts, {"detector": self.detector_name})
            if not fit:
                return True
            peak = measure_line(np.asarray(energies, dtype=float), np.asarray(counts, dtype=float), 609.3, _resolution(self.detector_name))
        except Exception as exc:
            logger.warning("Template fit for the Bi-214 cross-check failed: %s", exc)
            return True
        sources = fit["sources"]
        if sources["radium_series"]["present"] or peak is None:
            return True
        at = peak["measured_kev"]
        others = []
        if sources["thorium_series"]["present"] and at < (583.2 + 609.3) / 2:
            others.append("Tl-208 583 keV (thorium)")
        if sources["Cs-137"]["present"] and at > (609.3 + 661.7) / 2:
            others.append("Cs-137 662 keV")
        if not others:
            return True
        diagnostics.append(f"609 keV region: the peak at {at:.0f} keV is {' and '.join(others)}, not Bi-214 (the spectrum fit finds no "
                           f"radium series)")
        return False

    @staticmethod
    def _no_uranium_result(diagnostics, th234_result) -> Dict:
        return {
            "can_analyze": False,
            "reason": "No uranium signatures detected",
            "category": "Not Applicable",
            "description": "Spectrum does not contain detectable uranium. No Th-234, Bi-214, or Pa-234m peaks found above threshold.",
            "confidence": 0.0,
            "diagnostics": diagnostics,
            "warnings": ["No U-238 decay chain daughters detected - uranium enrichment analysis not applicable"],
            "u235_net_counts": 0,
            "th234_net_counts": th234_result.net_counts if th234_result else 0,
            "ratio_percent": 0,
            "threshold_natural": 30
        }

    @staticmethod
    def _takumar_result(diagnostics, th234_result, bi214_result) -> Dict:
        """Thoriated lenses hold ThO2 with trace natural uranium: an enrichment ratio is meaningless, so the Th-234 activity is reported."""
        return {
            "can_analyze": True,
            "category": "Thoriated Lens (Mixed Th/U)",
            "description": "Super Takumar lens containing thorium dioxide with trace natural uranium. Enrichment ratio not applicable.",
            "ratio_percent": 0,
            "threshold_natural": 30,
            "confidence": 0.9,  # High confidence since we detected Th-234
            "ra226_interference": False,  # Not an error for this source type
            "u235_net_counts": 0,
            "u235_uncertainty": 0,
            "th234_net_counts": th234_result.net_counts if th234_result else 0,
            "th234_uncertainty": th234_result.uncertainty_sigma if th234_result else 0,
            "bi214_net_counts": bi214_result.net_counts if bi214_result else 0,
            "diagnostics": diagnostics,
            "warnings": ["Takumar lens: Activity reported from Th-234 (93 keV) peak. Contains both Th-232 and trace natural U-238."],
            "confidence_factors": ["Th-234 detected", "Known thoriated lens source type"]
        }

    def _ra226_interference(self, energies, counts, acquisition_time_s, source_type, has_bi214,
                            bi214_result, u235_result, u235_net, u235_sigma, warnings):
        """
        Does Ra-226 contaminate the 186 keV region? Ra-226 emits at 186.2 keV and is in secular equilibrium with aged
        U-238; Bi-214 (its great-granddaughter) shows it is there, as does a source type that normally holds radium.
        Subtracts the Ra-226 share when the source type allows it. Returns (ra226_interference, u235_net, u235_sigma);
        warnings are appended in place.
        """
        ra226_interference = False
        known_ra226_source = source_type in ["uranium_glass", "radium_dial", "natural_uranium", "takumar_lens"]

        # Thoriated lens (pure Th only): check the thorium marker (Ac-228)
        if source_type == "thoriated_lens":
            try:
                ac228_result = self.analyze(energies, counts, "Ac-228 (911 keV)", acquisition_time_s)
                if ac228_result.detected:
                    warnings.append(
                        "Strong Thorium signature (Ac-228) confirmed. "
                        "Uranium detection may be due to mixed source composition or Compton scattering."
                    )
            except Exception:
                logger.debug('Th-232 signature cross-check skipped', exc_info=True)

        # Takumar lens (ThO2 + trace natural U)
        if source_type == "takumar_lens":
            warnings.append(
                "Takumar lens analysis: Source contains Thorium dioxide + trace natural uranium. "
                "Ra-226 interference correction will be applied."
            )

        if has_bi214 or known_ra226_source:
            # Ra-226 is definitely present if Bi-214 is detected OR the user confirmed the source type: the 186 keV
            # region then holds BOTH U-235 (185.7 keV) AND Ra-226 (186.2 keV)
            ra226_interference = True

            # Try to subtract Ra-226 when the data allow it ("do our best" for uranium glass)
            if (source_type in ["uranium_glass", "takumar_lens"] and bi214_result is not None and u235_result is not None
                    and bi214_result.net_counts > 0):
                corrected = self._ra226_correction(u235_result, bi214_result, warnings)
                if corrected:
                    u235_net, u235_sigma = corrected
                    ra226_interference = False   # corrected, so the ratio may be used (as an estimate)

            if ra226_interference:
                # Only warn if we did not correct it
                if has_bi214:
                    warnings.append(
                        f"Bi-214 detected ({bi214_result.net_counts:.0f} counts) indicates Ra-226 is in secular equilibrium. "
                        f"The 186 keV peak contains overlapping U-235 and Ra-226 contributions."
                    )
                elif known_ra226_source:
                    warnings.append(
                        f"Source type '{source_type}' typically contains Ra-226. "
                        f"The 186 keV peak likely contains overlapping U-235 and Ra-226 contributions."
                    )
        return ra226_interference, u235_net, u235_sigma

    @staticmethod
    def _u235_th234_ratio(u235_result, u235_net, u235_sigma, th234_result, has_th234, ra226_interference):
        """
        The enrichment ratio U-235 (186 keV) / Th-234 (93 keV) in percent, its uncertainty and the method label.
        With Ra-226 interference the ratio includes the Ra-226 contribution (UNRELIABLE) but is still calculated for information.
        """
        ratio = 0.0
        ratio_uncertainty = 0.0
        method_used = "none"
        if u235_result and has_th234 and th234_result.net_counts > 0:
            ratio = (u235_net / th234_result.net_counts) * 100
            method_used = "U-235/Th-234 ratio" + (" (UNRELIABLE - Ra-226 interference)" if ra226_interference else "")
            if u235_net > 0:
                ratio_uncertainty = ratio * math.sqrt(
                    (u235_sigma / u235_net) ** 2 +
                    (th234_result.uncertainty_sigma / th234_result.net_counts) ** 2
                )
        return ratio, ratio_uncertainty, method_used

    def analyze_uranium_ratio(
        self,
        energies: List[float],
        counts: List[int],
        acquisition_time_s: float,
        source_type: str = "auto"
    ) -> Dict:
        """
        Smart uranium enrichment analysis with prerequisite checks and confidence scoring.

        This method:
        1. Checks if uranium signatures are present (prerequisite)
        2. Detects Ra-226 interference that contaminates the 186 keV region
        3. Uses multiple methods and cross-validates when possible
        4. Returns confidence level and detailed diagnostics

        Returns:
            Dictionary with analysis results, confidence, and diagnostics
        """
        warnings = []

        # Is uranium even present? Look for the U-238 series markers
        th234_result, bi214_result, pa234m_result, diagnostics = self._measure_uranium_markers(
            energies, counts, acquisition_time_s)
        has_th234 = self._marker_present(th234_result)
        has_bi214 = self._marker_present(bi214_result)
        has_pa234m = self._marker_present(pa234m_result)
        if has_bi214:
            has_bi214 = self._bi214_is_radium(energies, counts, diagnostics)

        if not (has_th234 or has_bi214 or has_pa234m):
            return self._no_uranium_result(diagnostics, th234_result)

        logger.debug(f"[DEBUG] Takumar check: source_type={source_type}, has_th234={has_th234}")
        if source_type == "takumar_lens" and has_th234:
            return self._takumar_result(diagnostics, th234_result, bi214_result)

        # The U-235 (186 keV) region
        try:
            u235_result = self.analyze(energies, counts, "U-235 (186 keV)", acquisition_time_s)
            diagnostics.append(f"U-235 (186 keV): {u235_result.net_counts:.0f} ± {u235_result.uncertainty_sigma:.0f} counts")
        except Exception as e:
            warnings.append(f"Failed to analyze U-235 region: {str(e)}")
            u235_result = None
        # the 186 keV net counts and their uncertainty as used for the ratio (the Ra-226 correction may reduce them)
        u235_net = u235_result.net_counts if u235_result else 0.0
        u235_sigma = u235_result.uncertainty_sigma if u235_result else 0.0

        ra226_interference, u235_net, u235_sigma = self._ra226_interference(
            energies, counts, acquisition_time_s, source_type, has_bi214,
            bi214_result, u235_result, u235_net, u235_sigma, warnings)

        ratio, ratio_uncertainty, method_used = self._u235_th234_ratio(
            u235_result, u235_net, u235_sigma, th234_result, has_th234, ra226_interference)

        confidence, confidence_factors = self._enrichment_confidence(
            th234_result, has_th234, markers=sum([has_th234, has_bi214, has_pa234m]),
            ra226_interference=ra226_interference, ratio=ratio, ratio_uncertainty=ratio_uncertainty)

        category, description, confidence = self._classify_enrichment(
            ratio, ra226_interference, confidence, confidence_factors, warnings)

        return {
            "can_analyze": True,
            "category": category,
            "description": description,
            "confidence": round(confidence, 2),
            "confidence_factors": confidence_factors,
            "method_used": method_used,
            "ratio_percent": round(ratio, 1),
            "ratio_uncertainty": round(ratio_uncertainty, 1),
            "u235_net_counts": round(u235_net, 1),
            "u235_uncertainty": round(u235_sigma, 1),
            "th234_net_counts": round(th234_result.net_counts if th234_result else 0, 1),
            "th234_uncertainty": round(th234_result.uncertainty_sigma if th234_result else 0, 1),
            "bi214_net_counts": round(bi214_result.net_counts if bi214_result else 0, 1),
            "ra226_interference": ra226_interference,
            "threshold_natural": 30,
            "diagnostics": diagnostics,
            "warnings": warnings
        }


    def _ra226_correction(self, u235_result, bi214_result, warnings: List[str]):
        """
        Subtract the Ra-226 share of the 186 keV peak, estimated from the Bi-214 609 keV peak (secular equilibrium).

        Returns (u235_net, u235_sigma) after the correction, or None when it cannot be made (no efficiency data, or an
        error). The explanatory warnings are appended here.
        """
        try:
            # Ra-226 (186.2 keV) yield 3.64 %, Bi-214 (609.3 keV) yield 45.49 %
            YIELD_RA226_186 = 3.64
            YIELD_BI214_609 = 45.49
            eff_186 = interpolate_efficiency(self.detector_name, 186.2)
            eff_609 = interpolate_efficiency(self.detector_name, 609.3)
            if eff_186 > 0 and eff_609 > 0:
                # theoretical Ra-226 counts at 186 keV from the Bi-214 counts: (yield_186 / yield_609) * (eff_186 / eff_609)
                ra226_ratio = (YIELD_RA226_186 / YIELD_BI214_609) * (eff_186 / eff_609)
                estimated_ra226_counts = bi214_result.net_counts * ra226_ratio
                # The estimate carries the Bi-214 counting error and a 25 % allowance for the line-yield / efficiency
                # model (equilibrium, generic efficiency)
                estimated_sigma = estimated_ra226_counts * math.sqrt(
                    (bi214_result.uncertainty_sigma / bi214_result.net_counts) ** 2 + 0.25 ** 2)
                u235_net = max(0.0, u235_result.net_counts - estimated_ra226_counts)
                u235_sigma = math.sqrt(u235_result.uncertainty_sigma ** 2 + estimated_sigma ** 2)
                warnings.append(
                    f"Ra-226 interference subtracted (estimated {estimated_ra226_counts:.0f} counts from Bi-214 proxy). "
                    f"Enrichment result is an ESTIMATE."
                )
                if bi214_result.snr < 2.0:
                    warnings.append("Warning: Correction based on weak Bi-214 signal. Result allows approx.")
                return u235_net, u235_sigma
        except Exception as e:
            logger.error(f"Error correcting Ra-226: {e}")
        return None

    @staticmethod
    def _enrichment_confidence(th234_result, has_th234: bool, markers: int, ra226_interference: bool,
                               ratio: float, ratio_uncertainty: float):
        """Confidence (0-1) in an enrichment ratio, and the list of factors that made it up."""
        confidence = 0.0
        confidence_factors = []

        # Factor 1: signal strength (0-0.3)
        if has_th234 and th234_result.net_counts > 100:
            signal_factor = min(0.3, 0.3 * (th234_result.net_counts / 500))
            confidence += signal_factor
            confidence_factors.append(f"Signal strength: +{signal_factor:.2f}")

        # Factor 2: several uranium markers present (0-0.3)
        marker_factor = 0.1 * markers
        confidence += marker_factor
        confidence_factors.append(f"Uranium markers ({markers}/3): +{marker_factor:.2f}")

        # Factor 3: Ra-226 interference penalty (-0.2 to +0.2)
        if ra226_interference:
            interference_penalty = -0.2
            confidence += interference_penalty
            confidence_factors.append(f"Ra-226 interference: {interference_penalty:.2f}")
        else:
            confidence += 0.2
            confidence_factors.append("No Ra-226 interference: +0.20")

        # Factor 4: statistical precision (0-0.2)
        if ratio > 0 and ratio_uncertainty > 0:
            precision = 1 - min(1, ratio_uncertainty / ratio)
            precision_factor = 0.2 * precision
            confidence += precision_factor
            confidence_factors.append(f"Statistical precision: +{precision_factor:.2f}")

        return max(0.0, min(1.0, confidence)), confidence_factors

    @staticmethod
    def _classify_enrichment(ratio: float, ra226_interference: bool, confidence: float,
                             confidence_factors: List[str], warnings: List[str]):
        """
        The category and description for a U-235/Th-234 ratio (percent), and the confidence adjusted for it.
        Appends to confidence_factors and warnings in place.
        """
        # If Ra-226 interferes, the ratio is unreliable: Ra-226 (186.2 keV) overlaps U-235 (185.7 keV), and a
        # CsI/NaI/BGO detector cannot separate them (that needs HPGe).
        if ra226_interference:
            category = "Indeterminate (Ra-226 Interference)"
            description = (
                "The 186 keV region contains overlapping peaks from U-235 (185.7 keV) and Ra-226 (186.2 keV). "
                "This detector cannot resolve them, making enrichment analysis unreliable. "
                "An HPGe detector (resolution <1 keV) is required for accurate U-235/U-238 ratio measurement."
            )
            confidence = min(confidence, 0.2)   # we genuinely do not know
            confidence_factors.append("Ra-226 interference: enrichment ratio indeterminate")
            warnings.append(
                f"Calculated ratio ({ratio:.0f}%) is unreliable due to Ra-226 interference. "
                f"The true enrichment could be natural (~0.7%), depleted (<0.3%), or enriched (>0.7%). "
                f"Sample age, equilibrium state, and detector resolution prevent accurate determination."
            )
        elif ratio >= 150:
            # Above 150 % is physically impossible: the wrong source type was chosen (e.g. a thoriated lens as uranium glass)
            category = "Source Type Mismatch"
            description = (
                f"Ratio of {ratio:.0f}% is physically impossible for uranium. "
                "This likely indicates a thoriated source (Th-232) being analyzed with uranium assumptions. "
                "Try selecting 'Takumar Lens' or 'Thoriated Lens' as source type instead."
            )
            confidence = 0.1
            confidence_factors.append("Implausible ratio detected - likely source mismatch")
            warnings.append(
                "SANITY CHECK FAILED: U-235/Th-234 ratio exceeds 150%, which is physically impossible. "
                "This source is likely thoriated (Th-232) rather than uranium-based."
            )
        elif ratio >= 100:
            category = "Enriched Uranium"
            description = f"U-235 enriched above natural (>{0.72}% U-235)"
        elif ratio >= 30:
            category = "Natural Uranium"
            description = "Natural isotopic composition (~0.72% U-235)"
        elif ratio > 0:
            category = "Depleted Uranium"
            description = "U-235 depleted below natural (<0.3% U-235)"
        else:
            category = "Unable to Determine"
            description = "Insufficient data for enrichment determination"
        return category, description, confidence

def analyze_roi(
    energies: List[float],
    counts: List[int],
    isotope_name: str,
    detector_name: str,
    acquisition_time_s: float,
    source_type: str = "auto"
) -> Dict:
    """
    Convenience function for ROI analysis.
    
    Returns dictionary suitable for JSON API response.
    """
    analyzer = ROIAnalyzer(detector_name)
    result = analyzer.analyze(energies, counts, isotope_name, acquisition_time_s, source_type)
    
    detected = result.detected
    return {
        "isotope": result.isotope_name,
        "energy_keV": result.energy_keV,
        "roi_window": [round(result.roi_window[0], 1), round(result.roi_window[1], 1)],
        "background_bands": [[round(lo, 1), round(hi, 1)] for lo, hi in (result.background_bands or [])],
        "background_method": result.background_method,
        "gross_counts": round(result.gross_counts, 1),
        "background_counts": round(result.background_counts, 1),
        "net_counts": round(result.net_counts, 1),
        "net_counts_in_window": round(result.net_counts_in_window, 1) if result.net_counts_in_window is not None else None,
        "containment": round(result.containment, 4),
        "uncertainty_sigma": round(result.uncertainty_sigma, 1),
        "activity_bq": round(result.activity_bq, 2) if result.activity_bq else None,
        "activity_uci": round(result.activity_uci, 6) if result.activity_uci else None,
        "activity_uncertainty_bq": round(result.activity_uncertainty_bq, 2) if result.activity_uncertainty_bq else None,
        "mda_bq": round(result.mda_bq, 2) if result.mda_bq else None,
        "mda_uci": round(result.mda_uci, 6) if result.mda_uci else None,
        "detector": result.detector,
        "acquisition_time_s": result.acquisition_time_s,
        "efficiency_percent": round(result.efficiency_percent, 2),
        "branching_ratio": result.branching_ratio,
        "effective_branching_ratio": round(result.effective_branching_ratio, 4) if result.effective_branching_ratio else result.branching_ratio,
        # Detection quality metrics
        "detected": detected,
        "analysis_valid": result.analysis_valid,
        "detection_status": result.detection_status,
        "confidence": round(result.confidence, 2),
        "snr": round(result.snr, 1),
        "detection_limit_counts": round(result.detection_limit_counts, 1),
        # Peak fit (a cross-check of the window integration, and the measured resolution)
        "fit_success": result.fit_success,
        "fit_net_counts": round(result.fit_net_counts, 1) if result.fit_net_counts is not None else None,
        "expected_fwhm_keV": round(result.expected_fwhm_keV, 1) if result.expected_fwhm_keV else None,
        "resolution": round(result.resolution, 2) if result.resolution else None,
        "fwhm": round(result.fwhm, 2) if result.fwhm else None,
        # Diagnostic feedback
        "limiting_factors": result.limiting_factors,
        "recommendations": result.recommendations,
        "warnings": result.warnings or [],
    }


def analyze_uranium_enrichment(
    energies: List[float],
    counts: List[int],
    detector_name: str,
    acquisition_time_s: float,
    source_type: str = "auto"
) -> Dict:
    """
    Convenience function for uranium enrichment analysis.
    
    Returns dictionary suitable for JSON API response.
    """
    analyzer = ROIAnalyzer(detector_name)
    result = analyzer.analyze_uranium_ratio(energies, counts, acquisition_time_s, source_type)
    
    # The enhanced method returns a comprehensive dict directly
    return {
        "can_analyze": result.get("can_analyze", True),
        "category": result["category"],
        "description": result["description"],
        "confidence": result.get("confidence", 0.0),
        "method_used": result.get("method_used", ""),
        "ratio_percent": round(result.get("ratio_percent", 0), 1),
        "ratio_uncertainty": round(result.get("ratio_uncertainty", 0), 1),
        "u235_net_counts": round(result.get("u235_net_counts", 0), 1),
        "u235_uncertainty": round(result.get("u235_uncertainty", 0), 1),
        "th234_net_counts": round(result.get("th234_net_counts", 0), 1),
        "th234_uncertainty": round(result.get("th234_uncertainty", 0), 1),
        "bi214_net_counts": round(result.get("bi214_net_counts", 0), 1),
        "ra226_interference": result.get("ra226_interference", False),
        "threshold_natural": result.get("threshold_natural", 30),
        "confidence_factors": result.get("confidence_factors", []),
        "diagnostics": result.get("diagnostics", []),
        "warnings": result.get("warnings", [])
    }
