"""
Spectrum Algebra Module

Operations for combining, comparing, and normalizing gamma spectra
with proper error propagation for counting statistics.
"""

import numpy as np
from typing import List, Tuple, Optional


def add_spectra(spectra: List[List[float]], weights: Optional[List[float]] = None) -> dict:
    """
    Add multiple spectra together with optional weighting.
    
    Args:
        spectra: List of count arrays to add
        weights: Optional weights for each spectrum (e.g., for time normalization)
    
    Returns:
        dict with:
            - counts: Summed counts
            - uncertainty: Combined Poisson uncertainty
    """
    if not spectra:
        return {'counts': [], 'uncertainty': []}
    
    # Ensure all spectra have the same length
    max_len = max(len(s) for s in spectra)
    padded = [np.pad(s, (0, max_len - len(s)), mode='constant') for s in spectra]
    
    if weights is None:
        weights = [1.0] * len(spectra)
    
    # Weighted sum
    result = np.zeros(max_len)
    variance = np.zeros(max_len)
    
    for spectrum, weight in zip(padded, weights):
        arr = np.array(spectrum, dtype=float)
        result += arr * weight
        # Poisson variance: σ² = N, weighted: σ² = w² * N
        variance += (weight ** 2) * arr
    
    uncertainty = np.sqrt(variance)
    
    return {
        'counts': result.tolist(),
        'uncertainty': uncertainty.tolist(),
        'operation': 'add',
        'num_spectra': len(spectra)
    }


def subtract_spectra(source: List[float], background: List[float], 
                     source_time: float = 1.0, bg_time: float = 1.0) -> dict:
    """
    Subtract background spectrum from source with proper normalization.
    
    Args:
        source: Source spectrum counts
        background: Background spectrum counts
        source_time: Source acquisition time (seconds)
        bg_time: Background acquisition time (seconds)
    
    Returns:
        dict with:
            - counts: Net counts (non-negative)
            - uncertainty: Combined uncertainty
            - scale_factor: Background scaling applied
    """
    src = np.array(source, dtype=float)
    bg = np.array(background, dtype=float)
    
    # Handle different lengths
    min_len = min(len(src), len(bg))
    src = src[:min_len]
    bg = bg[:min_len]
    
    # Time normalization
    scale = source_time / bg_time if bg_time > 0 else 1.0
    scaled_bg = bg * scale
    
    # Subtract
    net = src - scaled_bg
    
    # Uncertainty: sqrt(source + scale²*background)
    uncertainty = np.sqrt(src + (scale ** 2) * bg)
    
    # Non-negative result
    net = np.maximum(net, 0)
    
    return {
        'counts': net.tolist(),
        'uncertainty': uncertainty.tolist(),
        'scale_factor': scale,
        'operation': 'subtract'
    }


def normalize_spectrum(counts: List[float], method: str = 'l1', 
                       live_time: Optional[float] = None) -> dict:
    """
    Normalize spectrum for comparison or ML processing.
    
    Args:
        counts: Spectrum counts
        method: Normalization method:
            - 'l1': Divide by sum (probability distribution)
            - 'l2': Divide by L2 norm (unit vector)
            - 'max': Divide by maximum value
            - 'cps': Divide by live time (counts per second)
    
    Returns:
        dict with normalized counts and normalization factor
    """
    arr = np.array(counts, dtype=float)
    
    if method == 'l1':
        factor = arr.sum()
        if factor == 0:
            factor = 1.0
    elif method == 'l2':
        factor = np.linalg.norm(arr)
        if factor == 0:
            factor = 1.0
    elif method == 'max':
        factor = arr.max()
        if factor == 0:
            factor = 1.0
    elif method == 'cps' and live_time is not None and live_time > 0:
        factor = live_time
    else:
        factor = 1.0
    
    normalized = (arr / factor).tolist()
    
    return {
        'counts': normalized,
        'normalization_factor': factor,
        'method': method
    }


def compare_spectra(spec1: List[float], spec2: List[float]) -> dict:
    """
    Compare two spectra using various metrics.
    
    Returns:
        dict with similarity metrics
    """
    a1 = np.array(spec1, dtype=float)
    a2 = np.array(spec2, dtype=float)
    
    # Align lengths
    min_len = min(len(a1), len(a2))
    a1 = a1[:min_len]
    a2 = a2[:min_len]
    
    # Normalize for comparison
    n1 = a1 / (a1.sum() + 1e-10)
    n2 = a2 / (a2.sum() + 1e-10)
    
    # Cosine similarity
    dot = np.dot(n1, n2)
    norm1 = np.linalg.norm(n1)
    norm2 = np.linalg.norm(n2)
    cosine = dot / (norm1 * norm2 + 1e-10)
    
    # Chi-squared
    chi2 = np.sum((n1 - n2) ** 2 / (n1 + n2 + 1e-10))
    
    # Correlation coefficient
    correlation = np.corrcoef(a1, a2)[0, 1] if len(a1) > 1 else 0.0
    
    return {
        'cosine_similarity': float(cosine),
        'chi_squared': float(chi2),
        'correlation': float(correlation) if not np.isnan(correlation) else 0.0,
        'length': min_len
    }


def rebin_spectrum(counts: List[float], energies: List[float], 
                   new_channels: int) -> Tuple[List[float], List[float]]:
    """
    Rebin spectrum to different number of channels.
    Useful for comparing spectra with different resolutions.
    
    Args:
        counts: Original counts
        energies: Original energy axis
        new_channels: Target number of channels
    
    Returns:
        Tuple of (new_counts, new_energies)
    """
    old_counts = np.array(counts, dtype=float)
    old_energies = np.array(energies, dtype=float)
    
    old_channels = len(old_counts)
    
    if new_channels >= old_channels:
        # No rebinning needed (or upsampling not supported)
        return counts, energies
    
    # Simple binning
    bin_size = old_channels // new_channels
    new_counts = []
    new_energies = []
    
    for i in range(new_channels):
        start = i * bin_size
        end = (i + 1) * bin_size if i < new_channels - 1 else old_channels
        new_counts.append(float(old_counts[start:end].sum()))
        new_energies.append(float(old_energies[start:end].mean()))
    
    return new_counts, new_energies
