"""
Full-spectrum template fit for natural-series / common-source discrimination.

Why: at scintillator resolution (AlphaHound CsI ~10 %, RadiaCode ~7-8.5 % FWHM at 662 keV)
the strongest U-238 (radium) and Th-232 series lines come in near-coincident pairs
(238.6/242.0, 338.3/351.9, 583.2/609.3 keV). Line-by-line peak matching cannot tell them
apart, which produced both-chains-detected false positives on real captures from both
devices. What does separate them is the whole pattern of relative intensities, so each
source is modelled as a template of Gaussian lines (detector resolution + efficiency, on
the spectrum's actual - possibly nonlinear - energy axis) and the templates are fitted
together with non-negative least squares to the background-subtracted spectrum. Broad
smooth terms absorb the Compton/backscatter residue; a gain/offset/resolution search
absorbs typical calibration error (RadiaCode factory calibration was ~3 % low on the test
data) but is bounded to physically believable shifts, otherwise a single-line template can be
slid onto an unrelated strong peak. A series is reported only when its amplitude is significant after inflating the
errors by the fit's reduced chi-square.

Thresholds (PRESENT_Z, PRESENT_FRACTION) were set between the largest false-series score
and the smallest true-series score on 11 labelled real spectra (tests/real_benchmark.py):
wrong series reached at most z=7.3 / f=0.05, true series at least z=12.5 / f=0.09.
"""
from typing import Dict, Optional, Sequence

import numpy as np
from scipy.optimize import nnls

from spectroscopy.detector_efficiency import interpolate_efficiency, DETECTOR_DATABASE

PRESENT_Z = 10.0
PRESENT_FRACTION = 0.07
# An artificial source is one or a few lines: next to a stronger source its share of the counts is small (Co-60 beside Cs-137: 0.053 at
# z = 30). On the labelled real spectra true artificial sources had z >= 30 and a share >= 0.053, false ones z <= 5.7 and <= 0.008.
PRESENT_FRACTION_ARTIFICIAL = 0.02
ARTIFICIAL_TEMPLATES = ("Cs-137", "Co-60", "Eu-152", "Ba-133")
HIGH_Z = 25.0
HIGH_FRACTION = 0.15

EMIN_KEV = 120.0     # below: X-rays, backscatter and detector threshold effects dominate
EMAX_KEV = 3000.0

_TL208_BR = 0.359    # Bi-212 -> Tl-208 branching
_U235_ACT = 0.046    # U-235 / U-238 activity ratio in natural uranium

# (energy keV, emission probability %) - NNDC/IAEA values, rounded; lines >= ~1 % and >= 120 keV
TEMPLATES: Dict[str, Sequence] = {
    # U-238 series below Ra-226 (radium in equilibrium: ores, radium dials, aged material)
    "radium_series": [(186.2, 3.6), (242.0, 7.3), (295.2, 18.4), (351.9, 35.6), (609.3, 45.5), (768.4, 4.9),
                      (934.1, 3.1), (1120.3, 14.9), (1238.1, 5.8), (1377.7, 4.0), (1729.6, 2.9), (1764.5, 15.3),
                      (2204.1, 4.9)],
    # Chemically purified natural uranium (glazes, uranium glass): Th-234/Pa-234m + U-235, no radium daughters
    "fresh_uranium": [(143.8, 11.0 * _U235_ACT), (163.3, 5.1 * _U235_ACT), (185.7, 57.2 * _U235_ACT),
                      (205.3, 5.0 * _U235_ACT), (766.4, 0.32), (1001.0, 0.84)],
    "thorium_series": [(129.1, 2.4), (209.3, 3.9), (238.6, 43.6), (241.0, 4.1), (270.2, 3.5), (300.1, 3.3),
                       (328.0, 3.0), (338.3, 11.3), (463.0, 4.4), (510.8, 22.6 * _TL208_BR),
                       (583.2, 85.0 * _TL208_BR), (727.3, 6.7), (794.9, 4.3), (860.6, 12.5 * _TL208_BR),
                       (911.2, 25.8), (964.8, 5.0), (969.0, 15.8), (1588.2, 3.2), (1620.5, 1.5),
                       (2614.5, 99.8 * _TL208_BR)],
    "K-40": [(1460.8, 10.7)],
    "Cs-137": [(661.7, 85.1)],
    "Co-60": [(1173.2, 99.9), (1332.5, 100.0)],
    # Calibration sources whose lines fall on natural-series lines at scintillator resolution: without their own templates the thorium
    # template took a real Eu-152 source (244.7/344.3/964.1 keV on 238.6/338.3/969.0) and reported the Th-232 series
    "Eu-152": [(121.8, 28.5), (244.7, 7.6), (344.3, 26.6), (411.1, 2.2), (444.0, 3.1), (778.9, 12.9), (867.4, 4.2), (964.1, 14.5),
               (1085.8, 10.1), (1112.1, 13.7), (1408.0, 20.9)],
    "Ba-133": [(160.6, 0.6), (223.2, 0.5), (276.4, 7.2), (302.9, 18.3), (356.0, 62.1), (383.8, 8.9)],
}

# Which decay chain each template supports
SERIES_TO_CHAIN = {"radium_series": "U-238", "fresh_uranium": "U-238", "thorium_series": "Th-232"}


def resolve_detector(metadata: Optional[dict]) -> str:
    """Map spectrum metadata to a DETECTOR_DATABASE key (defaults to the AlphaHound CsI)."""
    text = " ".join(str(v) for v in (metadata or {}).values() if isinstance(v, str)).lower()
    if "radiacode" in text:
        if "103g" in text:
            return "Radiacode 103G"
        if "110" in text:
            return "Radiacode 110"
        return "Radiacode 103"
    if "bgo" in text:
        return "AlphaHound BGO"
    if "hpge" in text or "germanium" in text:
        return HPGE
    return "AlphaHound CsI(Tl)"


HPGE = "HPGe (generic)"
HPGE_MAX_RESOLUTION = 0.03   # FWHM/E at 662 keV: germanium is ~0.2-0.5 %, the best scintillators ~6 %


def is_germanium(detector: str) -> bool:
    return _resolution(detector) < HPGE_MAX_RESOLUTION


def estimate_resolution_662(energies, counts, max_peaks: int = 6) -> Optional[float]:
    """
    The detector's FWHM/E scaled to 662 keV (FWHM taken proportional to sqrt(E)), measured on the strongest clear peaks above 100 keV;
    None when no peak can be measured. Lets a file that names no detector be analysed at the resolution it was really taken with.
    """
    from spectroscopy.spectral_analysis import snip_background, _measured_fwhm
    E = np.asarray(energies, dtype=float)
    c = np.asarray(counts, dtype=float)
    if E.size < 64 or E.size != c.size:
        return None
    net = c - np.asarray(snip_background(c, iterations=24), dtype=float)
    inner = np.arange(1, E.size - 1)
    maxima = inner[(net[inner] > net[inner - 1]) & (net[inner] >= net[inner + 1]) & (E[inner] >= 100.0)
                   & (net[inner] > 5.0 * np.sqrt(np.maximum(c[inner], 1.0)))]
    ratios = []
    for k in maxima[np.argsort(-net[maxima])][:4 * max_peaks]:
        measured = _measured_fwhm(E, net, c, float(E[k]), 0.0)
        if measured and measured[1] > 0:
            ratios.append(measured[1] / (662.0 * np.sqrt(E[k] / 662.0)))
        if len(ratios) >= max_peaks:
            break
    return float(np.median(ratios)) if ratios else None


def detector_min_energy(metadata: Optional[dict]) -> float:
    """Lowest energy the resolved detector is specified for (keV); below it is noise/threshold."""
    det = DETECTOR_DATABASE.get(resolve_detector(metadata), {})
    return float(det.get("min_energy_keV", 20))


def _resolution(detector: str) -> float:
    return float(DETECTOR_DATABASE.get(detector, {}).get("energy_resolution_662keV", 0.10))


def _template_matrix(E, dE, names, detector, r662, gain, offset):
    cols = []
    for name in names:
        col = np.zeros_like(E)
        for line, intensity in TEMPLATES[name]:
            mu = line * gain + offset
            sigma = r662 * 662.0 * np.sqrt(line / 662.0) / 2.355
            eff = interpolate_efficiency(detector, line) or 1e-3
            col += (intensity / 100.0) * eff * np.exp(-0.5 * ((E - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi)) * dE
        cols.append(col)
    return np.array(cols).T


MAX_REL_SHIFT = 0.07      # largest believable calibration error (fraction of energy) ...
MAX_ABS_SHIFT_KEV = 12.0  # ... plus a fixed term, checked across the fitted range


def _plausible_calibration(gain, offset):
    """Reject gain/offset pairs that would move lines further than a real miscalibration does."""
    return all(abs(gain * e + offset - e) <= MAX_REL_SHIFT * e + MAX_ABS_SHIFT_KEV for e in (200.0, 600.0, 1500.0, 2600.0))


def _continuum_basis(E):
    centers = np.geomspace(EMIN_KEV, EMAX_KEV, 14)
    return np.array([np.exp(-0.5 * ((E - c) / (0.25 * c / 2.355)) ** 2) for c in centers]).T


def _ba133_confirmed(E, c, sources, r662) -> bool:
    """
    Ba-133's lines in the fitted range (276-384 keV) coincide with Pb-214's (242-352 keV) and lie close to Eu-152's 344 keV at scintillator
    resolution: on the labelled real spectra its template reached z 16-20 on radium sources and on an Eu-152 source. What tells it apart
    lies outside the fit: with the radium series present the range cannot separate it, and a real source shows its 81 keV line (33 %).
    """
    if sources["radium_series"]["present"]:
        return False
    from spectroscopy.calibration_check import measure_line
    return measure_line(E, c, 81.0, r662) is not None


def fit_source_templates(energies, counts, metadata: Optional[dict] = None) -> Optional[dict]:
    """
    Fit all templates; return {"detector", "gain", "offset_keV", "resolution_scale",
    "sources": {name: {"z", "fraction", "present", "high"}}, "chains": {"U-238": {...}, "Th-232": {...}}}
    or None when the spectrum has too little usable range/signal.
    """
    from spectroscopy.spectral_analysis import snip_background

    E = np.asarray(energies, dtype=float)
    c = np.asarray(counts, dtype=float)
    if E.size != c.size or E.size < 64:
        return None
    mask = (E >= EMIN_KEV) & (E <= EMAX_KEV)
    if mask.sum() < 32:
        return None

    net = c - np.asarray(snip_background(c, iterations=24), dtype=float)
    dE = np.gradient(E)
    Em, dEm, netm = E[mask], dE[mask], net[mask]
    if np.maximum(netm, 0).sum() <= 0:
        return None
    w = 1.0 / np.sqrt(np.maximum(c[mask], 1.0))
    detector = resolve_detector(metadata)
    r662 = _resolution(detector)
    if is_germanium(detector):
        # the search steps (2 % in gain, +-15 % in width) are built for scintillator peaks; at germanium resolution the lines
        # identify themselves and the line matcher (with a germanium tolerance) does the work
        return None
    names = list(TEMPLATES)
    continuum = _continuum_basis(Em)

    def solve(gain, offset, rscale):
        A = np.hstack([_template_matrix(Em, dEm, names, detector, r662 * rscale, gain, offset), continuum])
        amps, rnorm = nnls(A * w[:, None], netm * w)
        return rnorm, amps, A

    # Coarse-to-fine search over calibration error and resolution mismatch
    best = None
    for rscale in (0.85, 1.0, 1.2):
        for offset in (-30.0, -15.0, 0.0, 15.0, 30.0):
            for gain in np.arange(0.90, 1.1001, 0.02):
                if not _plausible_calibration(gain, offset):
                    continue
                r = solve(gain, offset, rscale)
                if best is None or r[0] < best[0][0]:
                    best = (r, gain, offset, rscale)
    _, g0, o0, rs = best
    for offset in np.arange(o0 - 10.0, o0 + 10.01, 5.0):
        for gain in np.arange(g0 - 0.02, g0 + 0.0201, 0.005):
            if not _plausible_calibration(gain, offset):
                continue
            r = solve(gain, offset, rs)
            if r[0] < best[0][0]:
                best = (r, gain, offset, rs)
    (rnorm, amps, A), gain, offset, rs = best

    Aw = A * w[:, None]
    active = amps > 0
    z = np.zeros_like(amps)
    if active.any():
        try:
            cov = np.linalg.inv(Aw[:, active].T @ Aw[:, active])
            z[active] = amps[active] / np.sqrt(np.clip(np.diag(cov), 1e-30, None))
        except np.linalg.LinAlgError:
            pass
    dof = max(int(mask.sum()) - int(active.sum()), 1)
    z = z / np.sqrt(max(rnorm ** 2 / dof, 1.0))
    positive = np.maximum(netm, 0).sum()

    sources = {}
    for i, name in enumerate(names):
        frac = float((A[:, i] * amps[i]).sum() / positive)
        sources[name] = {
            "z": round(float(z[i]), 2),
            "fraction": round(frac, 4),
            "present": bool(z[i] >= PRESENT_Z and frac >= (PRESENT_FRACTION_ARTIFICIAL if name in ARTIFICIAL_TEMPLATES else PRESENT_FRACTION)),
            "high": bool(z[i] >= HIGH_Z and frac >= HIGH_FRACTION),
        }
    if sources["Ba-133"]["present"] and not _ba133_confirmed(E, c, sources, r662):
        sources["Ba-133"].update(present=False, high=False)

    chains = {}
    for name, chain in SERIES_TO_CHAIN.items():
        s = sources[name]
        cur = chains.setdefault(chain, {"present": False, "high": False, "z": 0.0, "fraction": 0.0, "via": []})
        cur["present"] |= s["present"]
        cur["high"] |= s["high"]
        cur["z"] = max(cur["z"], s["z"])
        cur["fraction"] = round(cur["fraction"] + s["fraction"], 4)
        if s["present"]:
            cur["via"].append(name)

    return {
        "detector": detector,
        "gain": round(float(gain), 4),
        "offset_keV": round(float(offset), 1),
        "resolution_scale": rs,
        "sources": sources,
        "chains": chains,
    }


# Isotopes that only make sense when their parent series is present
SERIES_MEMBERS = {
    "U-238": ["U-238", "Th-234", "Pa-234m", "U-234", "Th-230", "Ra-226", "Rn-222", "Po-218", "Pb-214",
              "Bi-214", "Po-214", "Pb-210", "Bi-210", "Po-210",
              # U-235 always accompanies natural uranium
              "U-235", "Th-231", "Pa-231", "Ac-227", "Th-227", "Ra-223", "Rn-219"],
    "Th-232": ["Th-232", "Ra-228", "Ac-228", "Th-228", "Ra-224", "Rn-220", "Po-216", "Pb-212", "Bi-212",
               "Tl-208", "Po-212"],
}


def _fallback_chain_entry(parent):
    """Minimal chain record in the format the UI renders, for a series the fit supports
    but line matching did not list."""
    try:
        from nuclides.chain_detection_enhanced import KNOWN_CHAINS, get_chain_sequence_info, check_secular_equilibrium
        info = KNOWN_CHAINS.get(parent, {})
        sequence = get_chain_sequence_info(parent)
        equilibrium = check_secular_equilibrium({}, parent)
    except Exception:
        info, sequence, equilibrium = {}, [], None
    return {
        "chain_name": info.get("name", f"{parent} Decay Chain"),
        "parent": parent,
        "confidence": 0.0,
        "confidence_level": "MEDIUM",
        "detected_members": {},
        "num_detected": 0,
        "num_key_isotopes": 0,
        "required_found": True,
        "abundance_weight": 1.0,
        "suppress_when_natural": False,
        "applications": [],
        "references": [],
        "notes": "",
        "color": info.get("color", "#6b7280"),
        "chain_type": info.get("type", "natural"),
        "enhanced": True,
        "chain_sequence": sequence,
        "equilibrium_status": equilibrium,
    }


RADIUM_AND_BELOW = ["Ra-226", "Rn-222", "Po-218", "Pb-214", "Bi-214", "Po-214", "Pb-210", "Bi-210", "Po-210"]

SINGLE_SOURCE_TEMPLATES = ("K-40", "Cs-137", "Co-60", "Eu-152", "Ba-133")


def _match_tolerance(energy, detector):
    """
    Line-position tolerance: half FWHM, the calibration error and a small floor, in quadrature: ~4 % and 5 keV for a scintillator, 0.5 %
    and 1 keV for germanium (a 30 keV window there spans a dozen peaks: environmental HPGe spectra matched 511 keV plus a line near
    1274 keV and read as Na-22).
    """
    fwhm = _resolution(detector) * 662.0 * np.sqrt(max(energy, 1.0) / 662.0)
    calibration, floor = (0.005, 1.0) if is_germanium(detector) else (0.04, 5.0)
    return float(np.sqrt((0.5 * fwhm) ** 2 + (calibration * energy) ** 2 + floor ** 2))


EXPLAIN_Z = 5.0   # a template this significant explains peaks away, even below the bar for reporting it


def _explained_by_fit(observed_kev, fit):
    """
    True if a peak at observed_kev is covered by a line of a source the fit found present, or used with a clear significance (z >= 5).
    Explaining a peak away only removes isotopes outside the templates: the weak uranium glazes (fresh-uranium z 5.7-7.8) had their U-235
    lines (143.8/163.3 keV) reported as Tl-201 (135/167 keV). A real Tl-201 source beside such a uranium signal would be missed the same way.
    """
    g, o, det = fit["gain"], fit["offset_keV"], fit["detector"]
    for name, src in fit["sources"].items():
        if not (src["present"] or src["z"] >= EXPLAIN_Z):
            continue
        for line, _ in TEMPLATES[name]:
            if abs(observed_kev - (g * line + o)) <= _match_tolerance(line, det):
                return True
    return False


def _has_own_evidence(iso, fit, peaks, natural_present):
    """An isotope outside the fitted templates must show a line the fit does not already explain."""
    matched = iso.get("matched_peaks") or []
    if not matched:
        return False
    expected = iso.get("expected_peaks") or []
    strongest = max(expected, key=lambda e: e.get("intensity", 0) or 0)["energy"] if expected else None
    strongest_matched = strongest is not None and any(abs(m["expected"] - strongest) < 1e-6 for m in matched)

    unexplained_high = [m for m in matched
                        if m["expected"] >= EMIN_KEV and not _explained_by_fit(m["observed"], fit)]
    if natural_present:
        # In a natural U/Th sample a single coincidental line (e.g. Tl-201 167 keV next to the
        # 186 keV Ra-226/U-235 line) is not enough: require two independent unexplained lines.
        if len({round(m["expected"], 1) for m in unexplained_high}) >= 2:
            return True
    elif unexplained_high and (strongest_matched or len(unexplained_high) >= 2):
        return True

    # Low-energy-only emitters (e.g. Am-241 59.5 keV) cannot be checked by the fit range:
    # accept them only without a natural series (whose X-rays sit there) and when their peak
    # is the dominant peak of the spectrum.
    if not natural_present and strongest_matched and peaks:
        top = max(peaks, key=lambda p: p.get("counts", 0) or 0)
        return any(abs(m["observed"] - top.get("energy", -1e9)) < 1.0 for m in matched)
    return False


CONTRADICTION_MIN_KEV = 300.0         # fresh uranium's lines are below 210 keV (and a weak 1001 keV): it explains nothing above this
CONTRADICTION_SIGNIFICANCE = 5.0
CONTRADICTION_PEAKS = 2


def discount_contradicted_fresh_uranium(fit, peaks) -> Optional[str]:
    """
    Withdraw a fresh-uranium verdict that the spectrum's own peaks contradict, and return a warning; None when it stands.

    On a drifted axis the automatic correction can miss, and the template fit, unable to line up the real source, then picks the
    nearest alias: a thoriated lens 8 % low read as fresh uranium (U-235 and a U-238 chain, with no U-235 line in the peaks). Real
    fresh uranium (glazes, uranium glass) leaves almost nothing above 300 keV, so two or more significant peaks there that no source
    of the fit explains mean the verdict is an alias, not a source.
    """
    if not fit:
        return None
    sources = fit.get("sources") or {}
    fresh = sources.get("fresh_uranium")
    if not fresh or not fresh.get("present") or (sources.get("radium_series") or {}).get("present"):
        return None
    unexplained = []
    for p in peaks or []:
        energy = p.get("energy") or 0.0
        # a fit that failed validation is no evidence: the built-in detector keeps such peaks with an uncertainty ~6x too small,
        # which turned three invalid fits on a real uranium glaze (FiestaWare) into "significant" contradictions
        if energy < CONTRADICTION_MIN_KEV or p.get("fit_valid") is False:
            continue
        significance = p.get("significance")
        if significance is None:
            area, unc = p.get("net_area"), p.get("net_area_unc") or p.get("uncertainty")
            significance = area / unc if area and unc else None
        if significance is not None and significance < CONTRADICTION_SIGNIFICANCE:
            continue
        if not _explained_by_fit(energy, fit):
            unexplained.append(energy)
    if len(unexplained) < CONTRADICTION_PEAKS:
        return None
    fresh["present"] = False
    fresh["discounted"] = f"peaks at {', '.join(f'{e:.0f}' for e in unexplained[:4])} keV fit no source of the fit"
    for chain in (fit.get("chains") or {}).values():
        if "fresh_uranium" in chain.get("via", []):
            chain["via"] = [v for v in chain["via"] if v != "fresh_uranium"]
            if not chain["via"]:
                chain["present"] = False
    return ("The spectrum's peaks above 300 keV (" + ", ".join(f"{e:.0f}" for e in unexplained[:4]) + " keV) fit no known source at "
            "this energy calibration, so it is not called uranium. The calibration may be off: check it with Calibrate.")


def restore_confirmed_series(fit, isotopes):
    """
    Lift the line matcher's 'a man-made source dominates' demotion from members of a series the full-spectrum fit confirms. One
    coincidental line decided it (I-131 364.5 keV on the Pb-214 352 keV peak of a uraninite ore demoted every radium daughter); the fit
    weighs the whole spectrum and is what decides the series. Returns the isotope list with those members at their unsuppressed score.
    """
    if not fit:
        return isotopes
    confirmed = {p for p, v in fit["chains"].items() if v["present"]}
    out = []
    for iso in isotopes:
        if (iso.get("suppressed") and iso.get("suppression_reason") == "manmade_source_detected"
                and iso.get("unsuppressed_confidence") is not None
                and any(iso.get("isotope") in SERIES_MEMBERS[p] for p in confirmed)):
            iso = {**iso, "confidence": iso["unsuppressed_confidence"], "suppressed": False,
                   "suppression_reason": None, "restored_by": "spectrum_fit"}
        out.append(iso)
    return out


def reconcile_with_fit(fit, decay_chains, isotopes, isotope_min_confidence=30.0, peaks=None):
    """
    Make the reported chains/isotopes agree with the full-spectrum fit:
    - drop a U-238 / Th-232 chain the fit does not support;
    - add one the fit supports but line matching missed;
    - set the confidence level from the fit's significance;
    - demote (and drop below threshold) isotopes of a series the fit rules out.
    Returns (decay_chains, isotopes).
    """
    if not fit:
        return decay_chains, isotopes
    verdict = fit["chains"]
    out = []
    listed = set()
    for chain in decay_chains:
        parent = chain.get("parent")
        if parent not in verdict:
            out.append(chain)
            continue
        v = verdict[parent]
        if not v["present"]:
            continue
        listed.add(parent)
        out.append(_apply_fit_confidence(chain, v))
    for parent, v in verdict.items():
        if v["present"] and parent not in listed:
            out.append(_apply_fit_confidence(_fallback_chain_entry(parent), v))
    out.sort(key=lambda c: c.get("confidence", 0), reverse=True)

    ruled_out = {p for p, v in verdict.items() if not v["present"]}
    # Uranium without its radium daughters (glazes, uranium glass): the 186 keV peak is U-235, not Ra-226, and Pb-214/Bi-214 are absent
    fresh_only = fit["sources"]["fresh_uranium"]["present"] and not fit["sources"]["radium_series"]["present"]
    natural_present = any(v["present"] for v in verdict.values())
    series_members = {m for members in SERIES_MEMBERS.values() for m in members}
    kept, names = [], set()
    for iso in isotopes:
        name = iso.get("isotope")
        reason = None
        if fresh_only and name in RADIUM_AND_BELOW:
            reason = "uranium_without_radium_daughters"
        elif any(name in SERIES_MEMBERS[p] for p in ruled_out):
            reason = "series_not_supported_by_spectrum_fit"
        elif name in SINGLE_SOURCE_TEMPLATES:
            if not fit["sources"][name]["present"]:
                reason = "not_supported_by_spectrum_fit"
        elif name not in series_members and not _has_own_evidence(iso, fit, peaks or [], natural_present):
            reason = "peaks_explained_by_other_sources"
        iso = dict(iso)
        if reason:
            iso["confidence"] = min(iso.get("confidence", 0), 20.0)
            iso["suppressed"] = True
            iso["suppression_reason"] = reason
            if iso["confidence"] < isotope_min_confidence:
                continue
        elif name in SINGLE_SOURCE_TEMPLATES:
            iso["confidence"] = max(iso.get("confidence", 0), 95.0 if fit["sources"][name]["high"] else 80.0)
            iso["spectrum_fit"] = fit["sources"][name]
        kept.append(iso)
        names.add(name)

    # Uranium the fit confirms without radium: its 186 keV line is U-235's (the line list leaves 185.7 keV out, as Ra-226's 186.2 sits on it)
    if fresh_only and "U-235" not in names:
        src = fit["sources"]["fresh_uranium"]
        u235 = [(e, i / _U235_ACT) for e, i in TEMPLATES["fresh_uranium"] if e < 300.0]
        kept.append({
            "isotope": "U-235", "confidence": 95.0 if src["high"] else 80.0, "matches": len(u235), "total_lines": len(u235),
            "matched_peaks": [], "expected_peaks": [{"energy": e, "intensity": i} for e, i in u235],
            "abundance_weight": 1.0, "suppressed": False, "spectrum_fit": src,
        })
        names.add("U-235")

    # A source the fit confirms must be listed even if line matching missed it
    for name in SINGLE_SOURCE_TEMPLATES:
        src = fit["sources"][name]
        if src["present"] and name not in names:
            kept.append({
                "isotope": name, "confidence": 95.0 if src["high"] else 80.0, "matches": len(TEMPLATES[name]),
                "total_lines": len(TEMPLATES[name]), "matched_peaks": [],
                "expected_peaks": [{"energy": e, "intensity": i} for e, i in TEMPLATES[name]],
                "abundance_weight": 1.0, "suppressed": False, "spectrum_fit": src,
            })
    kept.sort(key=lambda i: i.get("confidence", 0), reverse=True)
    return out, kept


def _apply_fit_confidence(chain, verdict):
    chain = dict(chain)
    level = "HIGH" if verdict["high"] else "MEDIUM"
    conf = float(chain.get("confidence", 0) or 0)
    # keep the numeric score inside the band of the level the fit assigns
    chain["confidence"] = max(70.0, min(conf, 100.0)) if level == "HIGH" else max(40.0, min(conf, 69.0))
    chain["confidence_level"] = level
    chain["spectrum_fit"] = {"z": verdict["z"], "fraction": verdict["fraction"], "via": verdict["via"]}
    note = f"Confirmed by full-spectrum fit ({', '.join(verdict['via'])}; z={verdict['z']:.0f})"
    chain["notes"] = f"{chain.get('notes', '')}; {note}".strip("; ")
    return chain
