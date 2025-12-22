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
    
    # Preserve any peaks already detected by the parser
    parser_peaks = result.get("peaks", [])
    
    # Use enhanced peak detection if available
    if use_enhanced and HAS_ENHANCED_ANALYSIS:
        try:
            peaks = detect_peaks_enhanced(energies, counts, validate_fits=True)
            result["analysis_mode"] = "enhanced"
            
            # If enhanced returns 0 but parser found peaks, fall back to basic
            if not peaks and parser_peaks:
                peaks = detect_peaks(energies, counts)
                result["analysis_mode"] = "standard_fallback"
        except Exception as e:
            print(f"[Analysis] Enhanced detection failed, falling back: {e}")
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
            print(f"[Analysis] Enhanced chain detection failed: {e}")
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
    isotopes, decay_chains = apply_confidence_filtering(all_isotopes, weighted_chains, current_settings)
    
    # Try multiplet fitting for better peak deconvolution
    if use_enhanced and HAS_ENHANCED_ANALYSIS:
        try:
            peaks = enhance_peaks_with_multiplet_fitting(energies, counts, peaks)
            result["peaks"] = peaks
        except Exception as e:
            print(f"[Analysis] Multiplet fitting failed: {e}")
    
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
    except Exception as e:
        pass
    
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
        pass
    
    result["data_quality"] = data_quality
    return sanitize_for_json(result)
