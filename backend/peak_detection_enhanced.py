"""
Enhanced Peak Detection Module

Two-stage peak detection combining:
1. CWT (Continuous Wavelet Transform) for candidate detection (GammaSpy approach)
2. Gaussian fit validation (PyGammaSpec approach)

This provides more robust peak detection than simple prominence-based methods.
"""

import numpy as np
from gauss_area import channel_width_kev
from typing import List, Dict, Optional, Tuple
from scipy.signal import find_peaks, find_peaks_cwt, savgol_filter
from scipy.optimize import curve_fit
import math

import logging
logger = logging.getLogger(__name__)


def gaussian_with_baseline(x, amplitude, center, sigma, bg_slope, bg_intercept):
    """Gaussian peak on a linear baseline."""
    gaussian = amplitude * np.exp(-((x - center) ** 2) / (2 * sigma ** 2))
    baseline = bg_slope * x + bg_intercept
    return gaussian + baseline


def fit_single_peak(
    energies: np.ndarray,
    counts: np.ndarray,
    center_guess: float,
    window_kev: float = 30.0
) -> Optional[Dict]:
    """
    Fit a Gaussian + linear baseline to a single peak region.
    
    Args:
        energies: Energy array (keV)
        counts: Count array
        center_guess: Approximate peak center (keV)
        window_kev: Width of fitting window (keV)
        
    Returns:
        Dictionary with fit results or None if fit failed
    """
    # Extract fitting region
    mask = (energies >= center_guess - window_kev/2) & (energies <= center_guess + window_kev/2)
    if np.sum(mask) < 10:
        return None
    
    x = energies[mask]
    y = counts[mask]
    
    # Initial guesses
    max_idx = np.argmax(y)
    amplitude_guess = y[max_idx] - np.min(y)
    center_guess_refined = x[max_idx]
    sigma_guess = window_kev / 6  # ~FWHM/2.355
    bg_slope_guess = 0
    bg_intercept_guess = np.min(y)
    
    try:
        popt, pcov = curve_fit(
            gaussian_with_baseline,
            x, y,
            p0=[amplitude_guess, center_guess_refined, sigma_guess, bg_slope_guess, bg_intercept_guess],
            bounds=(
                [0, center_guess - window_kev/2, 0.5, -np.inf, 0],
                [np.inf, center_guess + window_kev/2, window_kev/2, np.inf, np.inf]
            ),
            maxfev=5000
        )
        
        amplitude, center, sigma, bg_slope, bg_intercept = popt
        
        # Calculate fit quality metrics
        y_fit = gaussian_with_baseline(x, *popt)
        residuals = y - y_fit
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Calculate FWHM and resolution
        fwhm = 2.355 * sigma
        resolution = (fwhm / center) * 100 if center > 0 else 0
        
        # Calculate net area (integral of Gaussian only)
        # in counts: sigma is in keV and amplitude in counts per channel, so divide by the channel width
        net_area = amplitude * sigma * np.sqrt(2 * np.pi) / channel_width_kev(x)
        
        # Estimate uncertainty (sqrt of gross counts in peak region)
        gross_counts = np.sum(y)
        bg_counts = np.sum(gaussian_with_baseline(x, 0, center, sigma, bg_slope, bg_intercept))
        # the fitted baseline can dip below zero across the window (a negative slope, unbounded): a variance cannot, and
        # sqrt of a negative made the uncertainty NaN (which is not valid JSON in an API response)
        uncertainty = np.sqrt(max(float(gross_counts), 0.0) + max(float(bg_counts), 0.0))
        
        return {
            'energy': float(center),
            'amplitude': float(amplitude),
            'sigma': float(sigma),
            'fwhm': float(fwhm),
            'resolution': float(resolution),
            'net_area': float(net_area),
            'uncertainty': float(uncertainty),
            'r_squared': float(r_squared),
            'bg_slope': float(bg_slope),
            'bg_intercept': float(bg_intercept),
            'fit_valid': bool(r_squared > 0.7 and 0.5 < resolution < 25),  # Scintillator range
            'counts': float(y[max_idx]) if max_idx < len(y) else 0.0  # Add counts for compatibility
        }
        
    except Exception as e:
        return None


def detect_peaks_cwt(
    energies: np.ndarray,
    counts: np.ndarray,
    min_energy: float = 30.0,
    max_energy: float = 3000.0,
    widths: Optional[np.ndarray] = None,
    min_snr: float = 2.0
) -> List[float]:
    """
    Detect peak candidates using Continuous Wavelet Transform.
    
    This is more robust for noisy spectra than simple prominence detection.
    
    Args:
        energies: Energy array (keV)
        counts: Count array
        min_energy: Minimum energy to consider (keV)
        max_energy: Maximum energy to consider (keV)
        widths: CWT widths to use (default: auto-scaled)
        min_snr: Minimum signal-to-noise ratio
        
    Returns:
        List of candidate peak energies (keV)
    """
    # Create mask for energy range
    mask = (energies >= min_energy) & (energies <= max_energy)
    masked_counts = counts.copy()
    masked_counts[~mask] = 0
    
    # Auto-scale widths based on expected resolution (~8-15% FWHM for scintillators)
    if widths is None:
        # Width in channels, assuming ~3 keV/channel
        widths = np.arange(2, 20)
    
    try:
        # CWT peak detection
        peak_indices = find_peaks_cwt(
            masked_counts,
            widths=widths,
            min_snr=min_snr,
            noise_perc=10
        )
        
        # Convert indices to energies
        peak_energies = [energies[i] for i in peak_indices if mask[i]]
        return sorted(peak_energies)
        
    except Exception as e:
        logger.warning(f"[CWT] Detection failed: {e}")
        return []


def detect_peaks_resolution_aware(
    energies: np.ndarray,
    net_counts: np.ndarray,
    gross_counts: np.ndarray,
    r662: float,
    min_energy: float = 30.0,
    max_energy: float = 3000.0,
    k_sigma: float = 5.0,
) -> List[float]:
    """
    Detector-aware candidate search that complements the fixed-width CWT.

    The CWT widths are fixed in channels, so broad scintillator peaks on a shoulder (e.g.
    Ac-228 338 keV next to Pb-212 239 keV on a RadiaCode) can be missed. Here the spectrum
    is smoothed with a Gaussian matched to the detector resolution at each energy, and a
    local maximum is kept only if
      - its prominence exceeds k_sigma x the Poisson noise of the smoothed estimate, and
      - it keeps >= 65 % of its height when smoothed at the full detector sigma (rejects spikes).
    """
    from scipy.signal import find_peaks, peak_prominences

    E = np.asarray(energies, dtype=float)
    net = np.asarray(net_counts, dtype=float)
    gross = np.maximum(np.asarray(gross_counts, dtype=float), 0.0)
    n = E.size
    if n < 16:
        return []
    dE = np.maximum(np.gradient(E), 1e-6)
    fwhm_keV = r662 * 662.0 * np.sqrt(np.clip(E, 1.0, None) / 662.0)
    fwhm_ch = fwhm_keV / dE
    sig_ch = np.clip(0.5 * fwhm_ch / 2.355, 0.7, 30.0)   # smooth at half the peak sigma

    smooth = np.empty(n)
    smooth_full = np.empty(n)
    noise = np.empty(n)
    idx = np.arange(n)
    for i in range(n):
        s = sig_ch[i]
        lo, hi = max(0, int(i - 3 * s)), min(n, int(i + 3 * s) + 1)
        w = np.exp(-0.5 * ((idx[lo:hi] - i) / s) ** 2)
        w /= w.sum()
        smooth[i] = np.dot(w, net[lo:hi])
        noise[i] = np.sqrt(max(np.dot(w * w, gross[lo:hi]), 1.0))   # std of the weighted mean
        s2 = 2.0 * s                                                  # full detector sigma
        lo2, hi2 = max(0, int(i - 3 * s2)), min(n, int(i + 3 * s2) + 1)
        w2 = np.exp(-0.5 * ((idx[lo2:hi2] - i) / s2) ** 2)
        smooth_full[i] = np.dot(w2 / w2.sum(), net[lo2:hi2])

    in_range = (E >= min_energy) & (E <= max_energy)
    peaks, _ = find_peaks(smooth)
    peaks = peaks[in_range[peaks]]
    if peaks.size == 0:
        return []
    prom = peak_prominences(smooth, peaks)[0]
    # Spike rejection: going from half to full detector sigma keeps ~80 % of a real peak's height
    # (sigma_p / sqrt(sigma_p^2 + sigma_s^2)) but only ~50 % of a one-channel spike's. Unlike a
    # half-height width test this also works for peaks sitting on the shoulder of a bigger one.
    height_kept = smooth_full[peaks] / np.maximum(smooth[peaks], 1e-12)
    keep = (prom >= k_sigma * noise[peaks]) & (smooth[peaks] > 0) & (height_kept >= 0.65)
    return sorted(float(E[i]) for i in peaks[keep])


def merge_candidates(primary: List[float], extra: List[float], r662: float) -> List[float]:
    """Add extra candidates that are not within half an FWHM of an existing one."""
    out = list(primary)
    for e in extra:
        half = 0.5 * r662 * 662.0 * np.sqrt(max(e, 1.0) / 662.0)
        if all(abs(e - p) > half for p in out):
            out.append(e)
    return sorted(out)


def detect_peaks_prominence(
    energies: np.ndarray,
    counts: np.ndarray,
    prominence_fraction: float = 0.02,
    min_energy: float = 30.0,
    max_energy: float = 3000.0
) -> List[float]:
    """
    Detect peak candidates using scipy's find_peaks with prominence.
    
    Fallback method when CWT fails.
    
    Args:
        energies: Energy array (keV)
        counts: Count array  
        prominence_fraction: Minimum prominence as fraction of max counts
        min_energy: Minimum energy to consider (keV)
        max_energy: Maximum energy to consider (keV)
        
    Returns:
        List of candidate peak energies (keV)
    """
    # Create mask for energy range
    mask = (energies >= min_energy) & (energies <= max_energy)
    
    # Calculate prominence threshold
    max_count = np.max(counts[mask]) if np.any(mask) else 1
    prominence = max_count * prominence_fraction
    
    # Find peaks
    peak_indices, properties = find_peaks(
        counts,
        prominence=prominence,
        distance=5  # Minimum distance between peaks in channels
    )
    
    # Filter by energy range and return energies
    peak_energies = [energies[i] for i in peak_indices if mask[i]]
    return sorted(peak_energies)


def detect_peaks_enhanced(
    energies: List[float],
    counts: List[int],
    min_energy: float = 30.0,
    max_energy: float = 3000.0,
    validate_fits: bool = True,
    min_r_squared: float = 0.7,
    apply_snip: bool = True,
    snip_iterations: int = 24,
    resolution_662: Optional[float] = None
) -> List[Dict]:
    """
    Enhanced two-stage peak detection.
    
    Stage 0 (optional): SNIP background removal for high-count spectra
    Stage 1: CWT-based candidate detection (with prominence fallback)
    Stage 2: Gaussian fit validation for each candidate
    
    Args:
        energies: Energy array (keV)
        counts: Count array
        min_energy: Minimum energy to consider (keV)
        max_energy: Maximum energy to consider (keV)
        validate_fits: If True, validate each candidate with Gaussian fit
        min_r_squared: Minimum R² for fit validation
        apply_snip: If True, remove Compton continuum before peak finding
        snip_iterations: SNIP iterations (higher = smoother background)
        resolution_662: detector FWHM fraction at 662 keV; enables the detector-aware
                        search that complements the fixed-width CWT
        
    Returns:
        List of validated peak dictionaries
    """
    energies = np.array(energies)
    counts = np.array(counts)
    
    # Stage 0: Apply SNIP background removal for better peak detection
    # This removes the Compton continuum, making peaks stand out at true energies
    # Only for high-count spectra where Compton continuum distorts peak finding
    if apply_snip and np.max(counts) > 10000:
        try:
            from spectral_analysis import snip_background
            background = snip_background(counts, iterations=snip_iterations)
            net_counts = np.maximum(counts - background, 0)
            logger.debug(f"[Peak] Applied SNIP: max counts {np.max(counts):.0f} -> net {np.max(net_counts):.0f}")
            counts_for_detection = net_counts
        except Exception as e:
            logger.debug(f"[Peak] SNIP failed, using raw counts: {e}")
            counts_for_detection = counts
    else:
        counts_for_detection = counts
    
    # Stage 1: Candidate detection (use SNIP-processed counts)
    # Try CWT first, fall back to prominence
    candidates = detect_peaks_cwt(energies, counts_for_detection, min_energy, max_energy)
    
    if len(candidates) == 0:
        # Fallback to prominence-based detection
        candidates = detect_peaks_prominence(energies, counts_for_detection, 0.02, min_energy, max_energy)

    # Detector-aware search for broad / shoulder peaks the fixed-width CWT misses
    if resolution_662:
        try:
            net_for_search = counts_for_detection
            if net_for_search is counts:
                from spectral_analysis import snip_background
                net_for_search = counts - np.asarray(snip_background(counts, iterations=snip_iterations))
            extra = detect_peaks_resolution_aware(energies, net_for_search, counts, resolution_662,
                                                  min_energy, max_energy)
            candidates = merge_candidates(list(candidates), extra, resolution_662)
        except Exception as e:
            logger.debug(f"[Peak] Resolution-aware search failed: {e}")
    
    if not validate_fits:
        # Return simple peak list without validation
        return [{'energy': e, 'fit_valid': False} for e in candidates]
    
    # Stage 2: Fit validation (use SNIP-processed counts if available)
    validated_peaks = []
    
    # Debug: show candidates before fitting
    logger.debug(f"[Peak] Candidates BEFORE fitting: {[f'{e:.1f}' for e in candidates[:15]]}")
    
    for candidate_energy in candidates:
        # Use SNIP-processed counts for fitting if SNIP was applied
        fit_result = fit_single_peak(energies, counts_for_detection, candidate_energy)
        
        if fit_result is not None:
            # Store original candidate for chain detection (uses fitted center)
            # Also add display_energy at actual local maximum for chart markers
            # Find the actual peak position in raw counts for display
            window_mask = np.abs(energies - candidate_energy) <= 40  # Wide window to catch visual peaks
            if np.any(window_mask):
                window_idx = np.where(window_mask)[0]
                local_max_idx = window_idx[np.argmax(counts[window_idx])]
                fit_result['display_energy'] = float(energies[local_max_idx])
                # IMPORTANT: Also update counts to match the local max, so marker sits on tip
                fit_result['counts'] = float(counts[local_max_idx])
            else:
                fit_result['display_energy'] = candidate_energy
            
            # Accept if fit quality is good
            if fit_result['r_squared'] >= min_r_squared:
                validated_peaks.append(fit_result)
            elif fit_result['net_area'] > 100:
                # Accept weaker fits if signal is strong
                fit_result['fit_valid'] = False
                validated_peaks.append(fit_result)
    
    # Sort by energy
    validated_peaks.sort(key=lambda x: x['energy'])
    
    return validated_peaks


def merge_with_existing_peaks(
    enhanced_peaks: List[Dict],
    existing_peaks: List[Dict],
    merge_tolerance: float = 10.0
) -> List[Dict]:
    """
    Merge enhanced peak results with existing peak data.
    
    Preserves existing peak metadata (like isotope assignments) while
    adding enhanced fitting information.
    
    Args:
        enhanced_peaks: Peaks from enhanced detection
        existing_peaks: Peaks from existing detection
        merge_tolerance: Energy tolerance for matching (keV)
        
    Returns:
        Merged peak list
    """
    merged = []
    
    for existing in existing_peaks:
        existing_energy = existing.get('energy', 0)
        
        # Find matching enhanced peak
        match = None
        for enhanced in enhanced_peaks:
            if abs(enhanced['energy'] - existing_energy) < merge_tolerance:
                match = enhanced
                break
        
        if match:
            # Merge data, preferring enhanced fit results
            merged_peak = existing.copy()
            merged_peak.update({
                'energy': match['energy'],  # Use fitted center
                'fwhm': match.get('fwhm'),
                'resolution': match.get('resolution'),
                'r_squared': match.get('r_squared'),
                'fit_valid': match.get('fit_valid', False),
                'enhanced_area': match.get('net_area')
            })
            merged.append(merged_peak)
        else:
            # Keep existing peak as-is
            merged.append(existing)
    
    # Add any enhanced peaks not in existing
    for enhanced in enhanced_peaks:
        enhanced_energy = enhanced['energy']
        if not any(abs(m.get('energy', 0) - enhanced_energy) < merge_tolerance for m in merged):
            merged.append(enhanced)
    
    return sorted(merged, key=lambda x: x.get('energy', 0))


# Convenience function matching existing API
def find_peaks_in_spectrum(
    energies: List[float],
    counts: List[int],
    prominence: float = 0.02,
    min_distance: int = 10,
    mode: str = 'enhanced'
) -> List[Dict]:
    """
    Find peaks in a gamma spectrum.
    
    This is the main entry point, compatible with existing code.
    
    Args:
        energies: Energy values (keV)
        counts: Count values
        prominence: Prominence threshold (fraction of max)
        min_distance: Minimum channel distance between peaks
        mode: 'enhanced' for two-stage, 'simple' for prominence only
        
    Returns:
        List of peak dictionaries
    """
    if mode == 'enhanced':
        peaks = detect_peaks_enhanced(energies, counts, validate_fits=True)
    else:
        # Simple mode - just prominence detection
        energies_arr = np.array(energies)
        counts_arr = np.array(counts)
        
        max_count = np.max(counts_arr)
        peak_indices, props = find_peaks(
            counts_arr,
            prominence=max_count * prominence,
            distance=min_distance
        )
        
        peaks = []
        for idx in peak_indices:
            peaks.append({
                'energy': energies_arr[idx],
                'counts': counts_arr[idx],
                'prominence': props['prominences'][peak_indices.tolist().index(idx)] if 'prominences' in props else 0,
                'fit_valid': False
            })
    
    return peaks
