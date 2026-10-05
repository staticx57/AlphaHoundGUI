"""
Automatic energy-axis correction from the lines of the source itself.

Scintillator gains drift (the AlphaHound read 5.7 % lower in October 2026 than in December 2025, at 28.8 deg C), and on top of that its
factory axis is not straight (2614 keV reads ~6.5 % low). Beyond ~5 % the full-spectrum template fit can no longer reach the right
calibration and slides a one-line template onto the wrong peak (fresh uranium's 186 keV onto thorium's drifted 239 keV). This module works
the other way round: it decides which known source the strongest peaks are BEFORE identification, from several lines at once, and maps the
axis back so the normal analysis runs on true energies.

How it decides, and why it does not alias:
- Hypotheses are sources with several clean lines (thorium, radium, Eu-152, Ba-133, Co-60 + K-40). A one-line source never anchors a
  correction, so the 186 keV slide cannot happen here.
- Each (hypothesis, gain, offset) is scored on both sides: recall (how many of the source's detectable lines sit on a measured peak) times
  precision (how much of the spectrum's significant peak signal those lines account for). Thorium can line up 239/338/583/727 keV on a
  radium source at gain 1.045, but then leaves 295, 1120 and 1764 keV unexplained.
- The winner is refitted on its matched lines and must explain each of them to within half a FWHM; it needs three lines, a clear margin over
  every other hypothesis, and a correction beyond the 2.5 % the calibration check already tolerates. Otherwise nothing is changed.
"""
import math
from typing import Dict, List, Optional, Sequence

import numpy as np

# Each hypothesis is a source with several lines: its full line list (keV, emission probability %) from the template fit, so both use the
# same nuclear data. A one-line source (Cs-137, Am-241, K-40 alone, fresh uranium's 186 keV) never anchors a correction.
def _hypotheses() -> Dict[str, Sequence]:
    from spectroscopy.source_templates import TEMPLATES
    return {
        "thorium_series": TEMPLATES["thorium_series"],
        "radium_series": TEMPLATES["radium_series"],
        "Eu-152": TEMPLATES["Eu-152"],
        "Ba-133": TEMPLATES["Ba-133"],          # from 160 keV up: its 81 keV line sits on the Pb/Bi X-rays of radium sources and shields
        "Co-60 + K-40": list(TEMPLATES["Co-60"]) + list(TEMPLATES["K-40"]),
    }


HYPOTHESES = _hypotheses()
LABELS = {"thorium_series": "thorium series", "radium_series": "radium series", "Eu-152": "Eu-152", "Ba-133": "Ba-133",
          "Co-60 + K-40": "Co-60 and K-40"}

MIN_PEAK_KEV = 150.0          # below: X-rays and backscatter, which no hypothesis models, and where a scintillator's axis bends away
                              # from any gain + offset (the AlphaHound reads Ac-228 129 keV ~7 % high while its higher lines read
                              # 3-8 % low). Anchored there, the thorium correction failed confirmation on 7 of 55 Takumar
                              # captures of 5 min to 8 h once InterSpec reported that line (measured 2026-10-05); was 100.
MIN_SIGNIFICANCE = 5.0        # fitted peak amplitude over its error, for a peak to count
DETECTABLE = 0.05             # a line counts in a hypothesis's recall when it is this share of its strongest line (intensity x efficiency)
CURVATURE_SLACK = 0.015       # a straight gain+offset cannot follow a scintillator's curved axis exactly: this share of the energy
GAIN_RANGE = (0.85, 1.15)
OFFSET_RANGE = (-30.0, 30.0)  # the axes seen first (AlphaHound, RadiaCode 102/103/110) were within +-15 keV; the AlphaHound at 28.8 deg C in
                              # October 2026 needs +20.8 keV on top of a 12 % gain error, which the old +-20 refused by 0.8 keV
OFFSET_PROVEN = 20.0          # beyond this the proposal has to be confirmed strongly (FAR_CONFIRM_Z): more freedom, more proof. Widening the
                              # range alone let a drifted Co-60 + Cs-137 source be "corrected" as Eu-152 (4 lines, offset 21-22 keV) on a
                              # fit z of 7.4, barely over the bar; the thorium capture that needs the range is confirmed at z 20.9
FAR_CONFIRM_Z = 15.0
MIN_LINES = 3
MARGIN = 1.3                  # best score over the best score of any other hypothesis
APPLY_SHIFT = 0.025           # the calibration check's warning threshold: smaller corrections are left to it


def _fwhm(r662: float, energy: float) -> float:
    return r662 * 662.0 * math.sqrt(max(energy, 1.0) / 662.0)


def measure_peaks(energies, counts, r662: float) -> List[Dict]:
    """Significant peaks above MIN_PEAK_KEV on the raw axis: centroid, FWHM and significance from the Gaussian fit
    (InterSpec's when installed, spectroscopy/interspec_peaks.py; else the search below)."""
    from spectroscopy import interspec_peaks
    if interspec_peaks.enabled():
        found = interspec_peaks.find_peaks(energies, counts, r662, min_energy=MIN_PEAK_KEV)
        if found is not None:
            return [{"energy": p["energy"], "error": p["energy_unc"], "fwhm": p["fwhm"], "significance": p["significance"]}
                    for p in found if p["significance"] >= MIN_SIGNIFICANCE]
    from spectroscopy.spectral_analysis import snip_background, fit_gaussian
    E = np.asarray(energies, dtype=float)
    c = np.asarray(counts, dtype=float)
    kernel = np.ones(5) / 5.0
    net = np.convolve(c - np.asarray(snip_background(c, iterations=24), dtype=float), kernel, mode="same")
    noise = np.sqrt(np.maximum(np.convolve(c, kernel, mode="same"), 1.0) / 5.0)
    # candidates: the highest point within half a FWHM on each side, clearly above the noise (raw local maxima are noise spikes
    # on the flanks of the biggest peaks, and crowd out the smaller real ones)
    candidates = []
    for k in np.argsort(-net):
        if net[k] <= 3.0 * noise[k] or len(candidates) >= 40:
            break
        if E[k] < MIN_PEAK_KEV:
            continue
        half = 0.5 * _fwhm(r662, E[k])
        if all(abs(E[k] - x) > half for x in candidates):
            window = (E >= E[k] - half) & (E <= E[k] + half)
            if net[k] >= net[window].max():
                candidates.append(float(E[k]))
    peaks = []
    # Fitted on a 5-channel average: long captures show channel-to-channel ripple from the ADC far above counting noise (a 48 h
    # RadiaCode-102 capture alternates by +-15 %), and a fit on raw counts locks onto single channels. The average is symmetric, so centroids
    # (all a calibration needs) stay where they are; its counts are 5x correlated, so the significance is taken from the raw-count scale.
    smooth = np.convolve(c, kernel, mode="same")
    for fit in fit_gaussian(E, smooth, candidates):
        significance = fit["amplitude"] / fit["amplitude_unc"] / math.sqrt(5.0) if fit["amplitude_unc"] > 0 else 0.0
        expected = _fwhm(r662, fit["energy"])
        if significance < MIN_SIGNIFICANCE or fit["energy"] < MIN_PEAK_KEV or not 0.5 * expected <= fit["fwhm"] <= 2.5 * expected:
            continue
        if any(abs(fit["energy"] - p["energy"]) < 0.5 * _fwhm(r662, fit["energy"]) for p in peaks):
            continue   # two candidates converged on one peak
        peaks.append({"energy": fit["energy"], "error": max(fit["energy_unc"], 0.0), "fwhm": fit["fwhm"], "significance": significance})
    return peaks


def _detectable_lines(name: str, detector: str, r662: float) -> List[float]:
    """
    The energies a detector of this resolution would show as separate peaks: lines closer than 0.8 FWHM merge into one at their
    efficiency-weighted centroid (thorium's 911 + 965 + 969 keV is one peak near 935 keV on a scintillator), and groups below DETECTABLE of
    the strongest are left out.
    """
    from spectroscopy.detector_efficiency import interpolate_efficiency
    lines = sorted((e, i * (interpolate_efficiency(detector, e) or 1e-3)) for e, i in HYPOTHESES[name])
    groups = []
    for e, w in lines:
        if groups:
            ge, gw = groups[-1]
            if e - ge < 0.8 * _fwhm(r662, 0.5 * (e + ge)):
                groups[-1] = ((ge * gw + e * w) / (gw + w), gw + w)
                continue
        groups.append((e, w))
    top = max(w for _, w in groups)
    return [round(e, 1) for e, w in groups if w >= DETECTABLE * top]


def _match(lines, gain, offset, peak_e, r662, tol_extra=CURVATURE_SLACK):
    """One-to-one assignment of lines (predicted at gain*E+offset) to peaks; returns [(line, peak index)]."""
    pairs, used = [], set()
    for line in lines:
        p = gain * line + offset
        tol = math.hypot(0.5 * _fwhm(r662, p), tol_extra * p)
        d = np.abs(peak_e - p)
        order = [j for j in np.argsort(d) if j not in used and d[j] <= tol]
        if order:
            used.add(order[0])
            pairs.append((line, int(order[0])))
    return pairs


def _score(lines, pairs, weights):
    recall = len(pairs) / len(lines)
    precision = sum(weights[j] for _, j in pairs) / weights.sum()
    return recall * precision


def _refit(pairs, peaks, r662):
    """true = a + b * measured (gain-only when the lines are too close together to separate an offset); None if any line is off by more
    than half its FWHM, so lines that do not agree on one mapping are never averaged into one."""
    measured = np.array([peaks[j]["energy"] for _, j in pairs])
    nominal = np.array([line for line, _ in pairs])
    if len(pairs) >= MIN_LINES and nominal.max() / nominal.min() >= 1.5:
        b, a = np.polyfit(measured, nominal, 1)
    else:
        a, b = 0.0, float(np.median(nominal / measured))
    if b <= 0:
        return None
    residual = np.abs(a + b * measured - nominal)
    if np.any(residual > np.array([0.5 * _fwhm(r662, n) + 2.0 * peaks[j]["error"] for n, (_, j) in zip(nominal, pairs)])):
        return None
    return float(a), float(b), float(residual.max())


TEMPLATE_OF = {"thorium_series": "thorium_series", "radium_series": "radium_series", "Eu-152": "Eu-152", "Ba-133": "Ba-133",
               "Co-60 + K-40": "Co-60"}
CANDIDATES_PER_SOURCE = 3     # distinct calibrations per hypothesis handed to the spectrum fit
FIT_MARGIN = 1.5              # the winner's spectrum-fit z over the best z any other hypothesis reaches on its own corrected axis
RAW_MARGIN = 1.25             # ... and over the z its source already has on the uncorrected axis (else the axis is good enough as it is)


def _candidates(lines, peak_e, weights, r662):
    """The best-scoring (score, gain, offset, pairs) of one hypothesis, a few distinct gains, strongest first."""
    found = []
    for g in np.arange(GAIN_RANGE[0], GAIN_RANGE[1] + 1e-9, 0.005):
        for o in np.arange(OFFSET_RANGE[0], OFFSET_RANGE[1] + 1e-9, 5.0):
            pairs = _match(lines, g, o, peak_e, r662)
            if len(pairs) >= MIN_LINES:
                found.append((_score(lines, pairs, weights), float(g), float(o), pairs))
    found.sort(key=lambda t: -t[0])
    chosen = []
    for cand in found:
        if cand[0] < 0.6 * found[0][0] or len(chosen) >= CANDIDATES_PER_SOURCE:
            break
        if all(abs(cand[1] - c[1]) >= 0.015 for c in chosen):
            chosen.append(cand)
    return chosen


CONFIRM_Z = 7.0               # on its corrected axis the proposed source must reach this significance ...
CONFIRM_LEAD = 1.5            # ... and lead every other template by this factor (a weak capture's source can sit just under the bar
                              # for reporting it, z 9 of 10 on a 90-minute thoriated lens, while being plainly the source)


def _confirmation(fit, template: str) -> float:
    """The template's z when the fit on the corrected axis confirms it as the source, else 0."""
    z = fit["sources"][template]["z"]
    others = max((v["z"] for k, v in fit["sources"].items() if k != template), default=0.0)
    if fit["sources"][template]["present"] or (z >= CONFIRM_Z and z >= CONFIRM_LEAD * others):
        return float(z)
    return 0.0


def auto_calibrate(energies, counts, detector: str, r662: float, peaks: Optional[List[Dict]] = None) -> Dict:
    """
    Decide whether the axis needs correcting and how. Returns {"applied": bool, "reason": str, and when a correction was considered:
    "source", "lines": [{"nominal_kev", "measured_kev"}], "correction": {"offset_keV", "gain"} (true = offset_keV + gain * measured),
    "max_shift_percent", "fit_z", "runner_up", "message"}. `energies` is never modified.

    Line matching only PROPOSES corrections (several per multi-line source); the full-spectrum template fit, run on each corrected axis,
    DECIDES: a correction is applied when its own source is confirmed there, clearly ahead of every other proposal and of what the
    uncorrected axis shows. Radium and thorium lines are close to scaled copies of each other (609/583, 352/338, 242/239 keV), so the lines
    alone cannot always tell them apart under an unknown gain; the whole-spectrum pattern can.
    """
    from spectroscopy.source_templates import fit_source_templates
    E = np.asarray(energies, dtype=float)
    c = np.asarray(counts, dtype=float)
    peaks = measure_peaks(E, c, r662) if peaks is None else peaks
    if len(peaks) < MIN_LINES:
        return {"applied": False, "reason": "too few clear peaks"}
    peak_e = np.array([p["energy"] for p in peaks])
    # how much of the spectrum a hypothesis explains: square-root weights, so one dominant peak does not decide alone
    weights = np.sqrt(np.array([p["significance"] for p in peaks]))
    metadata = {"detector": detector}

    proposals = {}
    for name in HYPOTHESES:
        lines = _detectable_lines(name, detector, r662)
        if len(lines) >= MIN_LINES:
            cands = _candidates(lines, peak_e, weights, r662)
            if cands:
                proposals[name] = cands
    if not proposals:
        return {"applied": False, "reason": "no known multi-line source fits the peaks"}
    top_score = max(c[0][0] for c in proposals.values())

    raw_fit = fit_source_templates(E, c, metadata)
    judged = []   # (z, name, a, b, pairs, score)
    for name, cands in proposals.items():
        if cands[0][0] < 0.5 * top_score:
            continue
        for score, g, o, pairs in cands:
            refit = _refit(pairs, peaks, r662)
            if refit is None:
                continue
            a, b, _ = refit
            if not (OFFSET_RANGE[0] <= -a / b <= OFFSET_RANGE[1] and GAIN_RANGE[0] <= 1.0 / b <= GAIN_RANGE[1]):
                continue
            corrected = a + b * E
            if np.any(np.diff(corrected) <= 0):
                continue
            fit = fit_source_templates(corrected, c, metadata)
            if not fit:
                continue
            confirmed = _confirmation(fit, TEMPLATE_OF[name])
            if abs(a / b) > OFFSET_PROVEN and confirmed < FAR_CONFIRM_Z:
                continue
            judged.append((confirmed, name, a, b, pairs, score))
    if not judged or max(j[0] for j in judged) <= 0:
        return {"applied": False, "reason": "no proposed correction is confirmed by the spectrum fit"}

    judged.sort(key=lambda j: -j[0])
    z, name, a, b, pairs, score = judged[0]
    others = [j for j in judged if j[1] != name and j[0] > 0]
    raw_z = raw_fit["sources"][TEMPLATE_OF[name]]["z"] if raw_fit and raw_fit["sources"][TEMPLATE_OF[name]]["present"] else 0.0
    lines_used = sorted(({"nominal_kev": line, "measured_kev": round(peaks[j]["energy"], 1)} for line, j in pairs),
                        key=lambda m: m["nominal_kev"])
    result = {"applied": False, "source": name, "score": round(float(score), 3), "fit_z": round(float(z), 1), "raw_fit_z": round(float(raw_z), 1),
              "lines": lines_used, "correction": {"offset_keV": round(a, 3), "gain": round(b, 5)},
              "runner_up": {"source": others[0][1], "fit_z": round(float(others[0][0]), 1)} if others else None}
    if others and z < FIT_MARGIN * others[0][0]:
        return {**result, "reason": f"ambiguous: {LABELS[name]} and {LABELS[others[0][1]]} both fit"}
    if raw_z and z < RAW_MARGIN * raw_z:
        return {**result, "reason": "the uncorrected axis already fits about as well"}

    span = np.linspace(max(min(m["measured_kev"] for m in lines_used), 100.0), max(m["measured_kev"] for m in lines_used), 50)
    shift = np.abs((a + b * span) - span) / np.maximum(a + b * span, 1.0)
    result["max_shift_percent"] = round(float(shift.max()) * 100.0, 2)
    if shift.max() <= APPLY_SHIFT:
        return {**result, "reason": "axis already within 2.5 %"}

    listed = ", ".join(f"{m['nominal_kev']:g} keV (was {m['measured_kev']:.0f})" for m in lines_used[:4])
    direction = "up" if b * 662.0 + a > 662.0 else "down"
    result.update(
        applied=True, reason="corrected",
        message=(f"Energy axis corrected automatically: the {LABELS[name]} lines {listed} sat up to {result['max_shift_percent']:.1f}% off, "
                 f"so energies were moved {direction} (gain {b:.3f}, offset {a:+.1f} keV) before analysis. Undo restores the original axis."),
    )
    return result
