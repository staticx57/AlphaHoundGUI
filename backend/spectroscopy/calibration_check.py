"""
Is the energy axis right? Measure where known, well-separated lines of the sources in the spectrum actually sit.

The whole-spectrum template fit in source_templates.py also returns a gain and offset, but on real AlphaHound captures of a
thoriated lens it settled on "4-5 % low" while the individual lines were within 0.6 to 3 % of nominal and scattered both ways, and
applying its correction moved the 2615 keV line by 478 keV. A shift that is real moves every line the same way, so this check fits
single lines, accepts only clean ones, and reports a shift only when they agree.

A scintillator's response is not exactly proportional to energy, so a consistent offset of a percent or two is normal; the check
exists to find a gain that is clearly off (temperature drift, a wrong stored calibration), not to polish the last percent.
"""
import math
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import curve_fit

# Lines that stand clear of their neighbours at scintillator resolution, per source template (keV)
CLEAN_LINES: Dict[str, Sequence[float]] = {
    "thorium_series": (238.6, 583.2, 2614.5),
    "radium_series": (609.3, 1120.3, 1764.5, 2204.1),
    "K-40": (1460.8,),
    "Cs-137": (661.7,),
    "Co-60": (1173.2, 1332.5),
}

MIN_SIGNIFICANCE = 5.0        # fitted amplitude over its own uncertainty
MIN_AREA_COUNTS = 100.0
WINDOW_FWHM = 1.8             # half-width of the fitting window, in expected FWHMs
SIGMA_RANGE = (0.5, 2.0)      # accepted fitted width relative to the expected one
MAX_OFFSET_FWHM = 1.2         # a fit this far from the nominal energy (in expected FWHMs) is the edge of the window, not the line
CONSISTENT_REL = 0.01         # lines agree when they are within this fraction of the energy (or twice their error) of the fitted shift
WARN_SHIFT = 0.025            # a consistent shift of any clean line beyond this is reported as a calibration problem
MIN_SPAN = 1.5                # a gain AND offset are only separated when the lines span this energy ratio
MIN_LINES_FOR_OFFSET = 3      # two lines fit any gain+offset exactly, so they say nothing about consistency: they get a gain only


def _gauss(x, amplitude, mu, sigma, background, slope):
    return amplitude * np.exp(-0.5 * ((x - mu) / sigma) ** 2) + background + slope * (x - mu)


def measure_line(energies: np.ndarray, counts: np.ndarray, energy: float, resolution_662: float) -> Optional[Dict]:
    """Fit one line (Gaussian on a linear background); None when it is absent, too weak or not peak-shaped."""
    expected_fwhm = resolution_662 * 662.0 * math.sqrt(energy / 662.0)
    expected_sigma = expected_fwhm / 2.3548
    window = (energies > energy - WINDOW_FWHM * expected_fwhm) & (energies < energy + WINDOW_FWHM * expected_fwhm)
    if window.sum() < 8:
        return None
    x, y = energies[window], counts[window]
    background0 = float(np.percentile(y, 10))
    amplitude0 = float(y.max() - background0)
    if amplitude0 <= 0:
        return None
    try:
        p, cov = curve_fit(_gauss, x, y, p0=[amplitude0, float(x[int(np.argmax(y))]), expected_sigma, background0, 0.0],
                           sigma=np.sqrt(np.maximum(y, 1.0)), maxfev=5000)
    except (RuntimeError, ValueError):
        return None
    amplitude, mu, sigma = float(p[0]), float(p[1]), abs(float(p[2]))
    errors = np.sqrt(np.clip(np.diag(cov), 0, None))
    width = float(np.median(np.diff(x)))
    area = amplitude * sigma * math.sqrt(2 * math.pi) / max(width, 1e-9)
    inside = abs(mu - energy) <= MAX_OFFSET_FWHM * expected_fwhm
    if not (inside and amplitude > 0 and errors[0] > 0 and amplitude / errors[0] >= MIN_SIGNIFICANCE and area >= MIN_AREA_COUNTS
            and SIGMA_RANGE[0] * expected_sigma <= sigma <= SIGMA_RANGE[1] * expected_sigma):
        return None
    return {"nominal_kev": energy, "measured_kev": mu, "error_kev": float(errors[1]), "shift_percent": (mu - energy) / energy * 100.0,
            "area_counts": area}


def check_calibration(energies: Sequence[float], counts: Sequence[float], present_sources: Sequence[str],
                      resolution_662: float = 0.10) -> Dict:
    """
    Measure the clean lines of every source in `present_sources` and decide whether they show a consistent shift.

    Returns {"lines": [...], "shift_percent": median or None, "consistent": bool, "correction": {"gain", "offset_keV"} or None,
    "message": str or None}. `correction` maps a measured energy back: true = (measured - offset_keV) / gain; it is given only when the
    lines agree with a straight-line shift. With three or more lines spanning enough energy that is a gain and an offset; with fewer, or
    lines close together, it is a gain alone, so two lines that disagree are reported as inconsistent rather than fitted exactly.
    """
    e, c = np.asarray(energies, dtype=float), np.asarray(counts, dtype=float)
    lines: List[Dict] = []
    seen = set()
    for source in present_sources:
        for line in CLEAN_LINES.get(source, ()):
            if line not in seen:
                seen.add(line)
                m = measure_line(e, c, line, resolution_662)
                if m:
                    m["source"] = source
                    lines.append(m)
    lines.sort(key=lambda m: m["nominal_kev"])
    result = {"lines": lines, "shift_percent": None, "consistent": False, "correction": None, "message": None}
    if not lines:
        return result

    nominal = np.array([m["nominal_kev"] for m in lines])
    measured = np.array([m["measured_kev"] for m in lines])
    errors = np.array([m["error_kev"] for m in lines])
    result["shift_percent"] = float(np.median((measured - nominal) / nominal) * 100.0)

    # a straight-line map true -> measured: measured = gain * true + offset (gain only when the lines do not span enough energy)
    span = nominal.max() / nominal.min()
    if len(lines) >= MIN_LINES_FOR_OFFSET and span >= MIN_SPAN:
        gain, offset = np.polyfit(nominal, measured, 1)
    else:
        gain, offset = float(np.median(measured / nominal)), 0.0
    residual = np.abs(measured - (gain * nominal + offset))
    tolerance = np.maximum(CONSISTENT_REL * nominal, 2.0 * errors)
    result["consistent"] = bool(np.all(residual <= tolerance))
    shifts = (measured - nominal) / nominal
    worst = int(np.argmax(np.abs(shifts)))
    listed = ", ".join(f"{m['nominal_kev']:g} keV at {m['measured_kev']:.0f}" for m in lines[:3])
    if result["consistent"]:
        result["correction"] = {"gain": float(gain), "offset_keV": float(offset)}
        if abs(shifts[worst]) > WARN_SHIFT:
            direction = "low" if np.all(shifts < 0) else "high" if np.all(shifts > 0) else "tilted"
            result["message"] = (f"Energy calibration looks {direction}, by up to {abs(shifts[worst]) * 100:.1f}% ({listed}). "
                                 f"Recalibrate, or correct with gain {gain:.3f} and offset {offset:.1f} keV.")
    elif abs(shifts[worst]) > WARN_SHIFT and (np.all(shifts < -CONSISTENT_REL) or np.all(shifts > CONSISTENT_REL)):
        # Every line clearly moved the same way, by different fractions (a gain drift on a nonlinear axis): the axis is off, but no
        # straight line maps it back, so there is a warning and no correction to apply.
        direction = "low" if shifts[worst] < 0 else "high"
        result["message"] = (f"Energy calibration looks {direction}, by {abs(shifts).min() * 100:.1f} to {abs(shifts).max() * 100:.1f}% "
                             f"({listed}). The lines do not agree on one gain and offset, so assign the energies from known "
                             f"lines with Open Calibration Tool.")
    return result
