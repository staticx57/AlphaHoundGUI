"""
Multi-Peak Fitting Module

Handles overlapping peaks (multiplets) using simultaneous Gaussian fitting.
Based on GammaSpy's approach but simplified for our use case.

Key use cases:
- U-235 (185.7 keV) / Ra-226 (186.2 keV) overlap
- Pb-212 (238.6 keV) / Pb-214 (241.9 keV) near-overlap
- Any complex regions with multiple peaks
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from scipy.optimize import curve_fit, minimize
from scipy.integrate import quad
from dataclasses import dataclass
import warnings


@dataclass
class MultipletFitResult:
    """Result of a multi-peak fit."""
    success: bool
    peaks: List[Dict]  # Individual peak parameters
    residual: float
    r_squared: float
    total_area: float
    background_params: Tuple[float, float]  # (slope, intercept)
    
    
def gaussian(x, amplitude, center, sigma):
    """Single Gaussian peak."""
    return amplitude * np.exp(-((x - center) ** 2) / (2 * sigma ** 2))


def multi_gaussian_linear_bg(x, *params):
    """
    Multiple Gaussians on a linear background.
    
    Parameters are ordered as:
    [bg_slope, bg_intercept, amp1, center1, sigma1, amp2, center2, sigma2, ...]
    """
    bg_slope, bg_intercept = params[0], params[1]
    result = bg_slope * x + bg_intercept
    
    # Add each Gaussian (3 params per peak)
    n_peaks = (len(params) - 2) // 3
    for i in range(n_peaks):
        base_idx = 2 + i * 3
        amp = params[base_idx]
        center = params[base_idx + 1]
        sigma = params[base_idx + 2]
        result = result + gaussian(x, amp, center, sigma)
    
    return result


def estimate_initial_params(
    energies: np.ndarray,
    counts: np.ndarray,
    peak_centers: List[float]
) -> List[float]:
    """
    Estimate initial parameters for multi-peak fit.
    
    Args:
        energies: Energy array
        counts: Count array
        peak_centers: Approximate peak center energies
        
    Returns:
        Initial parameter list
    """
    # Background estimate from edges
    n_edge = max(5, len(energies) // 10)
    left_bg = np.mean(counts[:n_edge])
    right_bg = np.mean(counts[-n_edge:])
    
    bg_slope = (right_bg - left_bg) / (energies[-1] - energies[0])
    bg_intercept = left_bg - bg_slope * energies[0]
    
    params = [bg_slope, bg_intercept]
    
    # Estimate each peak
    for center in peak_centers:
        # Find nearest point
        idx = np.argmin(np.abs(energies - center))
        
        # Amplitude (subtract background)
        bg_at_center = bg_slope * center + bg_intercept
        amplitude = max(1, counts[idx] - bg_at_center)
        
        # Sigma estimate (assume ~3% resolution for scintillators)
        sigma = center * 0.03 / 2.355
        
        params.extend([amplitude, center, sigma])
    
    return params


def get_parameter_bounds(
    peak_centers: List[float],
    window_width: float
) -> Tuple[List[float], List[float]]:
    """
    Get bounds for curve fitting.
    
    Args:
        peak_centers: Expected peak centers
        window_width: Total energy window width
        
    Returns:
        Tuple of (lower_bounds, upper_bounds)
    """
    lower = [-np.inf, 0]  # bg_slope, bg_intercept
    upper = [np.inf, np.inf]
    
    for center in peak_centers:
        # Amplitude: 0 to infinity
        lower.append(0)
        upper.append(np.inf)
        
        # Center: allow some movement
        lower.append(center - 10)
        upper.append(center + 10)
        
        # Sigma: reasonable range for scintillators
        lower.append(1.0)  # At least 1 keV
        upper.append(center * 0.15 / 2.355)  # Max ~15% resolution
    
    return (lower, upper)


def fit_multiplet(
    energies: List[float],
    counts: List[int],
    peak_centers: List[float],
    window_margin: float = 40.0
) -> Optional[MultipletFitResult]:
    """
    Fit multiple overlapping peaks simultaneously.
    
    Args:
        energies: Full energy array (keV)
        counts: Full count array
        peak_centers: List of expected peak centers (keV)
        window_margin: Margin around peaks to include (keV)
        
    Returns:
        MultipletFitResult or None if fit failed
    """
    energies = np.array(energies)
    counts = np.array(counts)
    
    if len(peak_centers) == 0:
        return None
    
    # Define fitting window
    window_min = min(peak_centers) - window_margin
    window_max = max(peak_centers) + window_margin
    
    mask = (energies >= window_min) & (energies <= window_max)
    x = energies[mask]
    y = counts[mask]
    
    if len(x) < 10:
        return None
    
    # Initial parameters
    p0 = estimate_initial_params(x, y, peak_centers)
    bounds = get_parameter_bounds(peak_centers, window_max - window_min)
    
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            
            popt, pcov = curve_fit(
                multi_gaussian_linear_bg,
                x, y,
                p0=p0,
                bounds=bounds,
                maxfev=10000
            )
        
        # Calculate fit quality
        y_fit = multi_gaussian_linear_bg(x, *popt)
        residuals = y - y_fit
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Extract individual peak results
        bg_slope, bg_intercept = popt[0], popt[1]
        peaks = []
        total_area = 0
        
        n_peaks = (len(popt) - 2) // 3
        for i in range(n_peaks):
            base_idx = 2 + i * 3
            amp = popt[base_idx]
            center = popt[base_idx + 1]
            sigma = popt[base_idx + 2]
            
            # Calculate area (integral of Gaussian)
            area = amp * sigma * np.sqrt(2 * np.pi)
            total_area += area
            
            # Calculate FWHM and resolution
            fwhm = 2.355 * sigma
            resolution = (fwhm / center) * 100 if center > 0 else 0
            
            # Estimate uncertainty (simplified)
            # Diagonal of covariance matrix for amplitude
            try:
                amp_var = pcov[base_idx, base_idx]
                area_uncertainty = np.sqrt(amp_var) * sigma * np.sqrt(2 * np.pi)
            except:
                area_uncertainty = np.sqrt(area)  # Poisson fallback
            
            peaks.append({
                'center': center,
                'original_guess': peak_centers[i] if i < len(peak_centers) else center,
                'amplitude': amp,
                'sigma': sigma,
                'fwhm': fwhm,
                'resolution': resolution,
                'area': area,
                'uncertainty': area_uncertainty
            })
        
        return MultipletFitResult(
            success=True,
            peaks=peaks,
            residual=np.sqrt(ss_res / len(x)),
            r_squared=r_squared,
            total_area=total_area,
            background_params=(bg_slope, bg_intercept)
        )
        
    except Exception as e:
        print(f"[Multiplet Fit] Failed: {e}")
        return None


def deconvolve_overlapping_peaks(
    energies: List[float],
    counts: List[int],
    known_overlaps: Optional[Dict[float, List[Tuple[str, float]]]] = None
) -> List[Dict]:
    """
    Automatically detect and deconvolve overlapping peak regions.
    
    Args:
        energies: Energy array
        counts: Count array
        known_overlaps: Dictionary mapping approximate energy to 
                       list of (isotope_name, exact_energy) tuples
                       
    Returns:
        List of deconvolved peak results
    """
    # Default known overlapping regions
    if known_overlaps is None:
        known_overlaps = {
            186.0: [('U-235', 185.7), ('Ra-226', 186.2)],
            240.0: [('Pb-212', 238.6), ('Pb-214', 241.9)],
            295.0: [('Pb-214', 295.2), ('Bi-214', 295.2)],  # Same but for different chains
        }
    
    results = []
    
    for approx_energy, constituents in known_overlaps.items():
        # Check if there's significant signal in this region
        energies_arr = np.array(energies)
        counts_arr = np.array(counts)
        
        mask = (energies_arr >= approx_energy - 30) & (energies_arr <= approx_energy + 30)
        if not np.any(mask):
            continue
        
        region_max = np.max(counts_arr[mask])
        region_mean = np.mean(counts_arr[mask])
        
        # Skip if no clear peak
        if region_max < region_mean * 1.5:
            continue
        
        # Extract peak centers for fitting
        peak_centers = [energy for _, energy in constituents]
        
        # Fit multiplet
        fit_result = fit_multiplet(energies, counts, peak_centers)
        
        if fit_result and fit_result.success and fit_result.r_squared > 0.6:
            # Map results back to isotopes
            for i, (isotope, expected_energy) in enumerate(constituents):
                if i < len(fit_result.peaks):
                    peak = fit_result.peaks[i]
                    results.append({
                        'isotope': isotope,
                        'expected_energy': expected_energy,
                        'fitted_energy': peak['center'],
                        'area': peak['area'],
                        'uncertainty': peak['uncertainty'],
                        'fwhm': peak['fwhm'],
                        'resolution': peak['resolution'],
                        'from_multiplet': True,
                        'multiplet_r_squared': fit_result.r_squared
                    })
    
    return results


def fit_186_kev_region(
    energies: List[float],
    counts: List[int]
) -> Optional[Dict]:
    """
    Special handler for the U-235/Ra-226 overlap at 186 keV.
    
    Args:
        energies: Energy array
        counts: Count array
        
    Returns:
        Dictionary with deconvolved U-235 and Ra-226 areas
    """
    # Try two-peak fit
    fit_result = fit_multiplet(energies, counts, [185.7, 186.2])
    
    if fit_result is None or not fit_result.success:
        # Try single peak as fallback
        fit_result = fit_multiplet(energies, counts, [186.0])
        if fit_result and fit_result.success:
            return {
                'success': True,
                'single_peak': True,
                'combined_area': fit_result.peaks[0]['area'],
                'u235_area': None,
                'ra226_area': None,
                'note': 'Peaks not resolved - combined area reported'
            }
        return None
    
    # Check if we could actually resolve them
    if len(fit_result.peaks) < 2:
        return None
    
    peak1, peak2 = fit_result.peaks[0], fit_result.peaks[1]
    
    # Assign based on which is closer to expected energies
    if abs(peak1['center'] - 185.7) < abs(peak2['center'] - 185.7):
        u235_peak, ra226_peak = peak1, peak2
    else:
        u235_peak, ra226_peak = peak2, peak1
    
    return {
        'success': True,
        'single_peak': False,
        'u235_energy': u235_peak['center'],
        'u235_area': u235_peak['area'],
        'u235_uncertainty': u235_peak['uncertainty'],
        'ra226_energy': ra226_peak['center'],
        'ra226_area': ra226_peak['area'],
        'ra226_uncertainty': ra226_peak['uncertainty'],
        'separation_kev': abs(u235_peak['center'] - ra226_peak['center']),
        'r_squared': fit_result.r_squared,
        'resolvable': abs(u235_peak['center'] - ra226_peak['center']) > 1.0
    }


# Integration with existing peak detection
def enhance_peaks_with_multiplet_fitting(
    energies: List[float],
    counts: List[int],
    peaks: List[Dict]
) -> List[Dict]:
    """
    Enhance peak list by attempting multiplet fitting for known overlap regions.
    
    Args:
        energies: Energy array
        counts: Count array
        peaks: Existing peak list
        
    Returns:
        Enhanced peak list with deconvolution results
    """
    enhanced_peaks = peaks.copy()
    
    # Check for 186 keV region
    has_186 = any(abs(p.get('energy', 0) - 186) < 10 for p in peaks)
    if has_186:
        result = fit_186_kev_region(energies, counts)
        if result and result.get('success'):
            # Update or add peaks
            for p in enhanced_peaks:
                if abs(p.get('energy', 0) - 186) < 10:
                    p['multiplet_result'] = result
                    if not result['single_peak']:
                        p['deconvolved_u235_area'] = result.get('u235_area')
                        p['deconvolved_ra226_area'] = result.get('ra226_area')
    
    return enhanced_peaks
