"""
Enhanced Peak Detection Module

Two-stage peak detection combining:
1. CWT (Continuous Wavelet Transform) for candidate detection (GammaSpy approach)
2. Gaussian fit validation (PyGammaSpec approach)

This provides more robust peak detection than simple prominence-based methods.
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from scipy.signal import find_peaks, find_peaks_cwt, savgol_filter
from scipy.optimize import curve_fit
import math


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
        net_area = amplitude * sigma * np.sqrt(2 * np.pi)
        
        # Estimate uncertainty (sqrt of gross counts in peak region)
        gross_counts = np.sum(y)
        bg_counts = np.sum(gaussian_with_baseline(x, 0, center, sigma, bg_slope, bg_intercept))
        uncertainty = np.sqrt(gross_counts + bg_counts)
        
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
        print(f"[CWT] Detection failed: {e}")
        return []


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
    min_r_squared: float = 0.7
) -> List[Dict]:
    """
    Enhanced two-stage peak detection.
    
    Stage 1: CWT-based candidate detection (with prominence fallback)
    Stage 2: Gaussian fit validation for each candidate
    
    Args:
        energies: Energy array (keV)
        counts: Count array
        min_energy: Minimum energy to consider (keV)
        max_energy: Maximum energy to consider (keV)
        validate_fits: If True, validate each candidate with Gaussian fit
        min_r_squared: Minimum R² for fit validation
        
    Returns:
        List of validated peak dictionaries
    """
    energies = np.array(energies)
    counts = np.array(counts)
    
    # Stage 1: Candidate detection
    # Try CWT first, fall back to prominence
    candidates = detect_peaks_cwt(energies, counts, min_energy, max_energy)
    
    if len(candidates) == 0:
        # Fallback to prominence-based detection
        candidates = detect_peaks_prominence(energies, counts, 0.02, min_energy, max_energy)
    
    if not validate_fits:
        # Return simple peak list without validation
        return [{'energy': e, 'fit_valid': False} for e in candidates]
    
    # Stage 2: Fit validation
    validated_peaks = []
    
    for candidate_energy in candidates:
        fit_result = fit_single_peak(energies, counts, candidate_energy)
        
        if fit_result is not None:
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
