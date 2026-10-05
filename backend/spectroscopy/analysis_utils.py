"""
Shared analysis utilities for spectrum processing.
Unifies the analysis pipeline across file uploads (N42/CSV) and live devices (AlphaHound/Radiacode).
"""

import math
import re
from spectroscopy.peak_detection import detect_peaks
from nuclides.isotope_database import identify_isotopes, identify_decay_chains
from core import DEFAULT_SETTINGS, UPLOAD_SETTINGS, apply_abundance_weighting, apply_confidence_filtering

# Enhanced analysis modules (with fallback)
try:
    from spectroscopy.peak_detection_enhanced import detect_peaks_enhanced
    from nuclides.chain_detection_enhanced import identify_decay_chains_enhanced
    from spectroscopy.confidence_scoring import enhance_isotope_identifications
    from spectroscopy.multiplet_fitting import enhance_peaks_with_multiplet_fitting
    HAS_ENHANCED_ANALYSIS = True
except ImportError:
    HAS_ENHANCED_ANALYSIS = False

import logging
logger = logging.getLogger(__name__)

def sanitize_for_json(obj):
    """Recursively sanitize object for JSON serialization."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(i) for i in obj]
    elif hasattr(obj, 'item'):  # Numpy scalars
        val = obj.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    elif hasattr(obj, 'tolist'):  # Numpy arrays
        return sanitize_for_json(obj.tolist())
    return obj

def _detect_peaks(result: dict, energies, counts, use_enhanced: bool) -> list:
    """
    Detect the peaks, with fallbacks: enhanced detection, then the standard detector, then whatever the parser
    already found. Records which one answered in result["analysis_mode"] and stores the peaks in result["peaks"].
    """
    # Preserve any peaks already detected by the parser
    parser_peaks = result.get("peaks", [])

    # InterSpec, when installed (spectroscopy/interspec_peaks.py); the built-in detectors below stay as the fallback
    from spectroscopy import interspec_peaks
    if interspec_peaks.enabled():
        from spectroscopy.source_templates import resolve_detector, _resolution, detector_min_energy
        metadata = result.get("metadata")
        peaks = interspec_peaks.find_peaks(energies, counts, _resolution(resolve_detector(metadata)),
                                           min_energy=detector_min_energy(metadata))
        if peaks:
            result["analysis_mode"] = "interspec"
            result["peaks"] = peaks
            return peaks
    
    # Use enhanced peak detection if available
    if use_enhanced and HAS_ENHANCED_ANALYSIS:
        try:
            try:
                from spectroscopy.source_templates import resolve_detector, _resolution
                r662 = _resolution(resolve_detector(result.get("metadata")))
            except Exception:
                r662 = None
            peaks = detect_peaks_enhanced(energies, counts, validate_fits=True, resolution_662=r662)
            result["analysis_mode"] = "enhanced"
            
            # If enhanced returns 0 but parser found peaks, fall back to basic
            if not peaks and parser_peaks:
                peaks = detect_peaks(energies, counts)
                result["analysis_mode"] = "standard_fallback"
        except Exception as e:
            logger.warning(f"[Analysis] Enhanced detection failed, falling back: {e}")
            peaks = detect_peaks(energies, counts)
            result["analysis_mode"] = "standard"
    else:
        peaks = detect_peaks(energies, counts)
        result["analysis_mode"] = "standard"
    
    # Final fallback: if still no peaks but parser had some, use parser peaks
    if not peaks and parser_peaks:
        peaks = parser_peaks
        result["analysis_mode"] = "parser_preserved"
    
    result["peaks"] = peaks
    return peaks


def _fit_templates(result: dict, energies, counts):
    """The full-spectrum template fit (None when it cannot be made)."""
    try:
        from spectroscopy.source_templates import fit_source_templates
        return fit_source_templates(energies, counts, result.get("metadata"))
    except Exception as e:
        logger.warning(f"[Analysis] Source template fit failed: {e}")
        return None


def _reconcile_with_template_fit(result: dict, energies, counts, peaks, decay_chains, isotopes, current_settings: dict, fit):
    """
    Apply the full-spectrum template fit: it decides whether the U-238 / Th-232 series are really present,
    and can report a clearly-off energy calibration. Returns the (decay_chains, isotopes) to report.
    """
    try:
        from spectroscopy.source_templates import reconcile_with_fit
        if fit:
            result["source_fit"] = fit
            # Where the clean lines of the sources found actually sit: reports a clearly-off energy calibration. (The fit's own gain
            # estimate is not used for this: on real AlphaHound captures it reported 4-5 % low when the lines were within 1-3 %.)
            try:
                from spectroscopy.calibration_check import check_calibration
                from spectroscopy.source_templates import _resolution
                present = [name for name, src in fit["sources"].items() if src["present"]]
                check = check_calibration(energies, counts, present, _resolution(fit["detector"]))
                if check["lines"]:
                    result["calibration_check"] = check
                if check["message"]:
                    result["warnings"] = result.get("warnings", []) + [check["message"]]
            except Exception as e:
                logger.warning(f"[Analysis] Calibration check failed: {e}")
            decay_chains, isotopes = reconcile_with_fit(
                fit, decay_chains, isotopes, current_settings.get("isotope_min_confidence", 30.0), peaks)
    except Exception as e:
        logger.warning(f"[Analysis] Source template fit failed: {e}")
    return decay_chains, isotopes


def _assess_data_quality(peaks, energies, counts, live_time: float) -> dict:
    """Statistics and acquisition-time warnings, plus the Cs-137 minimum detectable activity when the time is known."""
    # Assess data quality
    max_peak_counts = max((p.get('counts', 0) for p in peaks), default=0)
    time_is_known = live_time > 1.0
    
    data_quality = {
        "low_statistics": max_peak_counts < 500,
        "short_acquisition": time_is_known and live_time < 60.0,
        "max_peak_counts": int(max_peak_counts),
        "warnings": []
    }
    
    if data_quality["low_statistics"]:
        data_quality["warnings"].append(f"Low statistics: max peak has only {int(max_peak_counts)} counts.")
    if data_quality["short_acquisition"]:
        data_quality["warnings"].append(f"Short acquisition time ({live_time:.0f}s).")
    
    # Calculate MDA for key isotopes (Cs-137 as reference)
    try:
        from spectroscopy.detector_efficiency import calculate_mda
        background_counts = 0
        for i, e in enumerate(energies):
            if 650 <= e <= 680 and i < len(counts):
                background_counts += counts[i]
        
        if live_time > 1.0 and background_counts >= 0:
            cs137_mda = calculate_mda(
                background_counts=background_counts,
                energy_keV=662,
                branching_ratio=0.851,
                live_time_s=live_time
            )
            if cs137_mda.get('valid'):
                data_quality["mda_cs137"] = {
                    "value_bq": cs137_mda['mda_bq'],
                    "readable": cs137_mda['mda_readable'],
                    "detection_limit_counts": cs137_mda['detection_limit_counts']
                }
    except Exception:
        logger.debug('MDA estimate skipped', exc_info=True)
    return data_quality


def _annotate_detector(result: dict, is_calibrated: bool):
    """Which detector profile describes this spectrum (the ROI panel preselects it) and its lower display limit."""
    try:
        from spectroscopy.source_templates import resolve_detector, estimate_resolution_662, HPGE, HPGE_MAX_RESOLUTION
        metadata = result.get("metadata") or {}
        text = " ".join(str(v) for v in metadata.values() if isinstance(v, str)).lower()
        # A file that names no known detector is analysed at the resolution its peaks show: germanium spectra from generic formats were
        # analysed as an AlphaHound CsI (10 %) and read as Na-22, with no natural series
        if is_calibrated and not any(k in text for k in ("alphahound", "radiacode", "bgo", "hpge", "germanium")):
            r662 = estimate_resolution_662(result["energies"], result["counts"])
            if r662 is not None:
                result["measured_resolution_662"] = round(r662, 4)
                if r662 < HPGE_MAX_RESOLUTION:
                    result["metadata"] = {**metadata, "detector_type": f"{HPGE}: peaks {r662 * 100:.2f} % FWHM at 662 keV"}
        result["detector_profile"] = resolve_detector(result.get("metadata"))
    except Exception as e:
        logger.debug(f"[Analysis] Detector profile not resolved: {e}")

    # The detector's specified threshold: channels below it hold electronic noise (e.g. the large pile in a RadiaCode's first channels)
    if is_calibrated:
        try:
            from spectroscopy.source_templates import detector_min_energy
            result["display_min_keV"] = detector_min_energy(result.get("metadata"))
        except Exception:
            logger.debug('display_min_keV not set', exc_info=True)


def _identify(peaks, current_settings: dict, use_enhanced: bool, detector=None):
    """Line-matching isotope identification and decay-chain detection (enhanced when available, with the basic one as fallback)."""
    all_isotopes = identify_isotopes(
        peaks,
        energy_tolerance=current_settings['energy_tolerance'],
        mode=current_settings.get('mode', 'simple'),
        detector=detector,
    )

    if use_enhanced and HAS_ENHANCED_ANALYSIS:
        try:
            all_chains = identify_decay_chains_enhanced(
                peaks,
                energy_tolerance=current_settings['energy_tolerance'],
                min_score=0.25
            )
            # Also enhance isotope confidence scores
            all_isotopes = enhance_isotope_identifications(all_isotopes, peaks)
        except Exception as e:
            logger.warning(f"[Analysis] Enhanced chain detection failed: {e}")
            all_chains = identify_decay_chains(
                peaks, all_isotopes,
                energy_tolerance=current_settings['energy_tolerance']
            )
    else:
        all_chains = identify_decay_chains(
            peaks, all_isotopes,
            energy_tolerance=current_settings['energy_tolerance']
        )
    return all_isotopes, all_chains


def _series_parent_entries(decay_chains, isotopes):
    """
    A series parent with no gamma line of its own (Th-232, U-238) has no independent evidence: every line its entry lists belongs to a
    daughter. So it is a verdict on the series, not a measurement: it takes the confidence of the best daughter in the table (never more,
    never less), it is listed whenever the series is reported, and it is flagged role=series so it sorts ahead of that daughter.

    Without this, whether the parent outranked its daughters depended on how its borrowed lines happened to score: first on 6 of 9
    thorium spectra, behind Ac-228 on two, behind Tl-208 on one; U-238 behind its daughters on every uranium one.
    """
    from spectroscopy.source_templates import SERIES_MEMBERS
    out = [dict(i) for i in isotopes]
    for chain in decay_chains:
        parent = chain.get("parent")
        if parent not in SERIES_MEMBERS:
            continue
        daughters = set(SERIES_MEMBERS[parent]) - {parent}
        direct = [i for i in out if i.get("isotope") in daughters and not i.get("suppressed")]
        if not direct:
            continue
        best = max(direct, key=lambda i: i.get("confidence", 0))
        entry = next((i for i in out if i.get("isotope") == parent), None)
        if entry is None:
            # no line of its own: the counts are those of the member its verdict rests on ("2/4 lines of its members matched")
            entry = {"isotope": parent, "matches": best.get("matches", 0), "total_lines": best.get("total_lines", 0), "matched_peaks": [],
                     "expected_peaks": [], "abundance_weight": 1.0}
            out.append(entry)
        entry.update(confidence=best["confidence"], role="series", series_basis=best["isotope"], suppressed=False)
    out.sort(key=lambda i: (i.get("confidence", 0), i.get("role") == "series"), reverse=True)
    return out


def _attach_member_status(decay_chains, isotopes):
    """Decide, in ONE place, what the chain card says about every member, so the card and the isotope table cannot disagree.

    The table can judge a nuclide only if it is in ISOTOPE_DATABASE; the chain engine matches lines for every member (Th-228 and Ra-224
    are not in the database). So: a member the table can judge takes the table's verdict, with its line count (listed: detected;
    absent or suppressed: not ticked, whatever the chain's line matching says); one it cannot judge keeps the chain's own line matches,
    counted the same way. A member with no gamma line of its own (Ra-228, Rn-220) that feeds a ticked one further down is inferred.

    chain['member_status'] = {nuclide: {'state': 'detected' | 'inferred', 'matches', 'total_lines', 'source', 'from'}}
    """
    from nuclides.isotope_database import ISOTOPE_DATABASE
    from nuclides.chain_detection_enhanced import get_expected_spectrum
    listed = {i.get("isotope"): i for i in isotopes if not i.get("suppressed")}
    for chain in decay_chains:
        members = [entry["nuclide"] for entry in chain.get("chain_sequence", [])]
        expected = get_expected_spectrum(chain.get("parent"))
        by_lines = chain.get("detected_members", {})
        status = {}
        for name in members:
            if name in listed:
                status[name] = {"state": "detected", "matches": listed[name].get("matches"), "total_lines": listed[name].get("total_lines"),
                                "source": "isotope table"}
            elif name in by_lines and name not in ISOTOPE_DATABASE:
                status[name] = {"state": "detected", "matches": len(by_lines[name]), "total_lines": len(expected.get(name, [])),
                                "source": "chain lines"}
        feeder = {entry["nuclide"]: entry.get("feeder") for entry in chain.get("chain_sequence", [])}
        for name in [m for m in members if status.get(m, {}).get("state") == "detected"]:
            ancestor = feeder.get(name)                       # walk up the real feeding links (a sibling branch like Po-212 is not an ancestor)
            while ancestor:
                if ancestor not in status and ancestor not in expected:
                    status[ancestor] = {"state": "inferred", "from": name}
                ancestor = feeder.get(ancestor)
        chain["member_status"] = status


def _add_equilibrium_status(decay_chains, result: dict, energies, counts, live_time: float):
    """Secular equilibrium of each reported series, measured on the spectrum with the ROI engine (the peak list is too coarse)."""
    try:
        from nuclides.chain_detection_enhanced import check_secular_equilibrium
        from spectroscopy.source_templates import resolve_detector
        detector = resolve_detector(result.get("metadata"))
        for chain in decay_chains:
            chain["equilibrium_status"] = check_secular_equilibrium(
                chain.get("detected_members", {}), chain.get("parent"), energies, counts, detector, live_time)
    except Exception as e:
        logger.warning(f"[Analysis] Equilibrium check failed: {e}")


def _add_xrf_detections(result: dict, peaks):
    """X-ray fluorescence lines among the low-energy peaks."""
    try:
        from nuclides.nuclear_data import detect_xrf_peaks
        peak_energies = [p.get('energy', 0) for p in peaks if p.get('energy', 0) < 100]
        if peak_energies:
            xrf_results = detect_xrf_peaks(peak_energies)
            if xrf_results:
                result["xrf_detections"] = xrf_results
    except Exception:
        logger.debug('XRF detection skipped', exc_info=True)


def _auto_calibrate(result: dict, energies, counts):
    """
    Correct a clearly drifted axis from the lines of the source itself (spectroscopy/auto_calibration.py). Returns the energies to analyse:
    a new list when a correction was applied (the original is kept in result['original_energies'] for Undo), else `energies` unchanged.
    """
    try:
        from spectroscopy.auto_calibration import auto_calibrate
        from spectroscopy.source_templates import _resolution, is_germanium
        detector = result.get("detector_profile")
        if not detector or is_germanium(detector):
            return energies
        outcome = auto_calibrate(energies, counts, detector, _resolution(detector))
    except Exception as e:
        logger.warning(f"[Analysis] Automatic axis correction failed: {e}")
        return energies
    result["auto_calibration"] = outcome
    if not outcome.get("applied"):
        return energies
    a, b = outcome["correction"]["offset_keV"], outcome["correction"]["gain"]
    corrected = [a + b * float(e) for e in energies]
    result["original_energies"] = list(energies)
    result["energies"] = corrected
    # the same convention as a manual correction (true = (measured - offset) / gain), marked as automatic
    result["metadata"] = {**(result.get("metadata") or {}),
                          "energy_correction": {"gain": 1.0 / b, "offset_keV": -a / b, "automatic": True, "source": outcome["source"]}}
    result["warnings"] = result.get("warnings", []) + [outcome["message"]]
    return corrected


PLACEHOLDER_AXIS_WARNING = (
    "This file says it was recorded by {device}, but its energy axis is exactly 3 keV per channel from zero (0, 3, 6 ... keV): "
    "the placeholder that older AlphaHoundGUI builds saved instead of the detector's own axis, so the energies are probably "
    "wrong (on one such file a thoriated lens read as Eu-152). Isotope and decay-chain identification is skipped. The counts "
    "are fine: repair the file with the real axis of the device it came from (backend/tools/recalibrate_n42.py with a spectrum "
    "CSV from that device), or assign the energies here with Open Calibration Tool.")


def claimed_detector(metadata) -> str:
    """The real detector a file says it was recorded by ("RadView Detection AlphaHound"), or "" when it names none or says it
    is simulated or synthetic. Taken only from what the file states: a file's device is never assumed."""
    m = metadata or {}
    named = " ".join(str(m.get(k) or "").strip() for k in ("manufacturer", "model")).strip()
    return "" if not named or re.search(r"simulat|synthetic|generator", named, re.I) else named


def is_placeholder_axis(energies) -> bool:
    """The axis older builds saved instead of the device's: 0, 3, 6 ... keV (tools/recalibrate_n42.py repairs such files).
    Identified on it, a thoriated lens read Eu-152 + Na-22: the peaks sit at the wrong energies and no gain + offset fixes it."""
    return len(energies) >= 64 and all(abs(float(e) - 3.0 * i) < 1e-6 for i, e in enumerate(energies))


def analyze_spectrum_peaks(result: dict, is_calibrated: bool, live_time: float = 0.0, use_enhanced: bool = True,
                           auto_calibrate: bool = True) -> dict:
    """
    Common analysis pipeline for all spectrum sources.
    Detects peaks, identifies isotopes, and finds decay chains.

    Args:
        result: Parsed spectrum dict with 'counts' and 'energies'
        is_calibrated: Whether the spectrum has energy calibration
        live_time: Acquisition time in seconds
        use_enhanced: Whether to use enhanced analysis modules if available
        auto_calibrate: Correct a clearly drifted axis from the source's own lines first (off for an axis the user chose)

    Returns:
        Updated result dict with 'peaks', 'isotopes', 'decay_chains', and 'analysis_mode'
    """
    if not result.get("counts") or not result.get("energies"):
        return result

    energies = result["energies"]
    counts = result["counts"]
    # Only a file that says it came from a real detector is taken to carry the placeholder: simulated and generated spectra
    # (and CSVs, which name no instrument) can genuinely be calibrated at 3 keV per channel from zero
    device = claimed_detector(result.get("metadata"))
    placeholder = is_calibrated and bool(device) and is_placeholder_axis(energies)
    if placeholder:
        is_calibrated = False
        result["is_calibrated"] = False

    _annotate_detector(result, is_calibrated)
    if auto_calibrate and is_calibrated:
        energies = _auto_calibrate(result, energies, counts)
    peaks = _detect_peaks(result, energies, counts, use_enhanced)

    # Without an energy calibration the "energies" are channel numbers, so matching them
    # against gamma-line keV values only produces spurious isotopes/chains. Keep the peaks
    # (useful for calibrating) but skip identification and tell the user why.
    if not is_calibrated:
        result["isotopes"] = []
        result["decay_chains"] = []
        message = PLACEHOLDER_AXIS_WARNING.format(device=device) if placeholder else (
            "No energy calibration: isotope and decay-chain identification skipped. Energies are channel numbers or an "
            "assumed 3 keV/channel; assign real energies with Open Calibration Tool.")
        # the page shows this in the axis notice, with a button to the calibration tool: in Simple mode (the default) the
        # tool is on screen nowhere else, and the message used to send people to a "Calibrate" button that does not exist
        result["calibration_needed"] = {"message": message, "placeholder_axis": bool(placeholder), "device": device or None}
        result["warnings"] = result.get("warnings", []) + [message]
        return result

    if not peaks:
        result["isotopes"] = []
        result["decay_chains"] = []
        return result

    # Settings by acquisition time: a long calibrated acquisition is judged strictly, an upload or a short one leniently
    current_settings = DEFAULT_SETTINGS if live_time > 30.0 else UPLOAD_SETTINGS

    all_isotopes, all_chains = _identify(peaks, current_settings, use_enhanced, result.get("detector_profile"))

    weighted_chains = apply_abundance_weighting(all_chains)
    # The simple-mode isotope cap is applied after the spectrum fit below: capping first lets isotopes
    # of a series the fit later rules out (e.g. U-238 daughters on a thorium source) use up the slots
    # and push out the real ones.
    # The template fit decides the series: run it before the confidence filter, so members of a confirmed series that the line
    # matcher demoted on a single coincidental line are not filtered out first
    fit = _fit_templates(result, energies, counts)
    try:
        from spectroscopy.source_templates import discount_contradicted_fresh_uranium
        note = discount_contradicted_fresh_uranium(fit, peaks)
        if note:
            result["warnings"] = result.get("warnings", []) + [note]
    except Exception as e:
        logger.warning(f"[Analysis] Fresh-uranium check failed: {e}")
    try:
        from spectroscopy.source_templates import restore_confirmed_series
        all_isotopes = restore_confirmed_series(fit, all_isotopes)
    except Exception as e:
        logger.warning(f"[Analysis] Series restore failed: {e}")
    isotopes, decay_chains = apply_confidence_filtering(
        all_isotopes, weighted_chains, {**current_settings, "max_isotopes": 10**6})

    decay_chains, isotopes = _reconcile_with_template_fit(
        result, energies, counts, peaks, decay_chains, isotopes, current_settings, fit)
    _add_equilibrium_status(decay_chains, result, energies, counts, live_time)
    isotopes = _series_parent_entries(decay_chains, isotopes)
    _attach_member_status(decay_chains, isotopes)

    if current_settings.get("mode") == "simple":
        isotopes = sorted(isotopes, key=lambda i: i.get("confidence", 0), reverse=True)[:current_settings.get("max_isotopes", 999)]

    # Multiplet fitting for better peak deconvolution
    if use_enhanced and HAS_ENHANCED_ANALYSIS:
        try:
            peaks = enhance_peaks_with_multiplet_fitting(energies, counts, peaks)
            result["peaks"] = peaks
        except Exception as e:
            logger.warning(f"[Analysis] Multiplet fitting failed: {e}")

    result["isotopes"] = isotopes
    result["decay_chains"] = decay_chains

    _add_xrf_detections(result, peaks)
    result["data_quality"] = _assess_data_quality(peaks, energies, counts, live_time)
    return sanitize_for_json(result)
