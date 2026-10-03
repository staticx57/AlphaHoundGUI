"""
Shared analysis utilities for spectrum processing.
Unifies the analysis pipeline across file uploads (N42/CSV) and live devices (AlphaHound/Radiacode).
"""

import math
from typing import List, Optional, Dict
from peak_detection import detect_peaks
from isotope_database import identify_isotopes, identify_decay_chains
from core import DEFAULT_SETTINGS, UPLOAD_SETTINGS, apply_abundance_weighting, apply_confidence_filtering
from spectral_analysis import fit_gaussian

# Enhanced analysis modules (with fallback)
try:
    from peak_detection_enhanced import detect_peaks_enhanced
    from chain_detection_enhanced import identify_decay_chains_enhanced
    from confidence_scoring import enhance_isotope_identifications
    from multiplet_fitting import enhance_peaks_with_multiplet_fitting
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
    
    # Use enhanced peak detection if available
    if use_enhanced and HAS_ENHANCED_ANALYSIS:
        try:
            try:
                from source_templates import resolve_detector, _resolution
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


def _reconcile_with_template_fit(result: dict, energies, counts, peaks, decay_chains, isotopes, current_settings: dict):
    """
    Fit the whole spectrum with source templates: it decides whether the U-238 / Th-232 series are really present,
    and can report a clearly-off energy calibration. Returns the (decay_chains, isotopes) to report.
    """
    try:
        from source_templates import fit_source_templates, reconcile_with_fit
        fit = fit_source_templates(energies, counts, result.get("metadata"))
        if fit:
            result["source_fit"] = fit
            # If identified sources anchor the fit, report a clearly-off energy calibration
            if any(src["present"] for src in fit["sources"].values()):
                shift = fit["gain"] + fit["offset_keV"] / 662.0 - 1.0
                if abs(shift) > 0.025:
                    result["warnings"] = result.get("warnings", []) + [
                        f"Energy calibration looks about {abs(shift) * 100:.1f}% {'low' if shift < 0 else 'high'} "
                        "(identified lines sit at shifted energies). Recalibrate for accurate peak energies."
                    ]
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
        from detector_efficiency import calculate_mda
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


def analyze_spectrum_peaks(result: dict, is_calibrated: bool, live_time: float = 0.0, use_enhanced: bool = True) -> dict:
    """
    Common analysis pipeline for all spectrum sources.
    Detects peaks, identifies isotopes, and finds decay chains.
    
    Args:
        result: Parsed spectrum dict with 'counts' and 'energies'
        is_calibrated: Whether the spectrum has energy calibration
        live_time: Acquisition time in seconds
        use_enhanced: Whether to use enhanced analysis modules if available
    
    Returns:
        Updated result dict with 'peaks', 'isotopes', 'decay_chains', and 'analysis_mode'
    """
    if not result.get("counts") or not result.get("energies"):
        return result
    
    energies = result["energies"]
    counts = result["counts"]

    # Which detector profile (efficiency, resolution) describes this spectrum: the ROI panel preselects it
    try:
        from source_templates import resolve_detector
        result["detector_profile"] = resolve_detector(result.get("metadata"))
    except Exception as e:
        logger.debug(f"[Analysis] Detector profile not resolved: {e}")

    # Lower display limit: the detector's specified threshold (channels below it hold
    # electronic noise, e.g. the large pile in a RadiaCode's first channels).
    if is_calibrated:
        try:
            from source_templates import detector_min_energy
            result["display_min_keV"] = detector_min_energy(result.get("metadata"))
        except Exception:
            logger.debug('display_min_keV not set', exc_info=True)
    
    peaks = _detect_peaks(result, energies, counts, use_enhanced)

    # Without an energy calibration the "energies" are channel numbers, so matching them
    # against gamma-line keV values only produces spurious isotopes/chains. Keep the peaks
    # (useful for calibrating) but skip identification and tell the user why.
    if not is_calibrated:
        result["isotopes"] = []
        result["decay_chains"] = []
        result["warnings"] = result.get("warnings", []) + [
            "No energy calibration: isotope and decay-chain identification skipped. "
            "Energies are channel numbers or an assumed 3 keV/channel; use Calibrate to assign real energies."
        ]
        return result

    if not peaks:
        result["isotopes"] = []
        result["decay_chains"] = []
        return result
    
    # Select settings based on calibration and acquisition time
    if is_calibrated and live_time > 30.0:
        current_settings = DEFAULT_SETTINGS
    else:
        current_settings = UPLOAD_SETTINGS
    
    # Identify isotopes
    all_isotopes = identify_isotopes(
        peaks, 
        energy_tolerance=current_settings['energy_tolerance'], 
        mode=current_settings.get('mode', 'simple')
    )
    
    # Use enhanced chain detection if available
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
    
    weighted_chains = apply_abundance_weighting(all_chains)
    # The simple-mode isotope cap is applied after the spectrum fit below: capping first lets isotopes
    # of a series the fit later rules out (e.g. U-238 daughters on a thorium source) use up the slots
    # and push out the real ones.
    isotopes, decay_chains = apply_confidence_filtering(
        all_isotopes, weighted_chains, {**current_settings, "max_isotopes": 10**6})

    decay_chains, isotopes = _reconcile_with_template_fit(
        result, energies, counts, peaks, decay_chains, isotopes, current_settings)

    # Secular equilibrium of each reported series, measured on the spectrum with the ROI engine (the peak list is too coarse)
    try:
        from chain_detection_enhanced import check_secular_equilibrium
        from source_templates import resolve_detector
        detector = resolve_detector(result.get("metadata"))
        for chain in decay_chains:
            chain["equilibrium_status"] = check_secular_equilibrium(
                chain.get("detected_members", {}), chain.get("parent"), energies, counts, detector, live_time)
    except Exception as e:
        logger.warning(f"[Analysis] Equilibrium check failed: {e}")

    if current_settings.get("mode") == "simple":
        isotopes = sorted(isotopes, key=lambda i: i.get("confidence", 0), reverse=True)[:current_settings.get("max_isotopes", 999)]

    # Try multiplet fitting for better peak deconvolution
    if use_enhanced and HAS_ENHANCED_ANALYSIS:
        try:
            peaks = enhance_peaks_with_multiplet_fitting(energies, counts, peaks)
            result["peaks"] = peaks
        except Exception as e:
            logger.warning(f"[Analysis] Multiplet fitting failed: {e}")
    
    result["isotopes"] = isotopes
    result["decay_chains"] = decay_chains
    
    # Add XRF detection for low-energy peaks
    try:
        from nuclear_data import detect_xrf_peaks
        peak_energies = [p.get('energy', 0) for p in peaks if p.get('energy', 0) < 100]
        if peak_energies:
            xrf_results = detect_xrf_peaks(peak_energies)
            if xrf_results:
                result["xrf_detections"] = xrf_results
    except Exception:
        logger.debug('XRF detection skipped', exc_info=True)
    
    result["data_quality"] = _assess_data_quality(peaks, energies, counts, live_time)
    return sanitize_for_json(result)
