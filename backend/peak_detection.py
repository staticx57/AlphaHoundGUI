import numpy as np
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d

def detect_peaks(energies, counts, prominence_factor=0.01, distance=5):
    """
    Detect peaks in spectrum data, including shoulder peaks.
    
    Args:
        energies: Array of energy values
        counts: Array of count values
        prominence_factor: Minimum prominence as fraction of max counts (default 1%)
        distance: Minimum distance between peaks (in indices, default 5)
    
    Returns:
        List of dictionaries with peak information
    """
    try:
        counts_array = np.array(counts, dtype=float)
        energies_array = np.array(energies, dtype=float)
        
        if len(counts_array) == 0:
            return []
        
        max_count = np.max(counts_array)
        if max_count == 0:
            return []
        
        peaks_found = {}
        
        # === Pass 1: Standard peak detection ===
        # Use lower thresholds to catch more peaks
        min_height = max(3, max_count * 0.002)  # At least 3 counts or 0.2% of max
        min_prominence = max(2, max_count * 0.001)  # At least 2 counts or 0.1% of max
        
        peak_indices, _ = find_peaks(
            counts_array,
            prominence=min_prominence,
            distance=distance,
            height=min_height
        )
        
        for idx in peak_indices:
            peaks_found[idx] = {
                "energy": float(energies_array[idx]),
                "counts": float(counts_array[idx]),
                "index": int(idx)
            }
        
        # === Pass 2: Detect shoulder peaks using derivative ===
        # Smooth the spectrum and look for inflection points
        smoothed = gaussian_filter1d(counts_array, sigma=3)
        first_deriv = np.gradient(smoothed)
        second_deriv = np.gradient(first_deriv)
        
        # Find zero crossings in second derivative (inflection points)
        # These can indicate shoulder peaks
        for i in range(1, len(second_deriv) - 1):
            # Zero crossing from positive to negative in 2nd derivative
            if second_deriv[i-1] > 0 and second_deriv[i+1] < 0:
                # Check if this is on a significant slope (first derivative not too small)
                if abs(first_deriv[i]) > max_count * 0.0005:
                    # Check if counts at this point are significant
                    if counts_array[i] > max_count * 0.1:  # At least 10% of max
                        # Check distance from existing peaks
                        too_close = any(abs(i - existing) < distance for existing in peaks_found.keys())
                        if not too_close:
                            peaks_found[i] = {
                                "energy": float(energies_array[i]),
                                "counts": float(counts_array[i]),
                                "index": int(i),
                                "type": "shoulder"
                            }
        
        # === Pass 3: Look for local maxima in residuals ===
        # Subtract a smoothed baseline and find peaks in the difference
        baseline = gaussian_filter1d(counts_array, sigma=20)
        residual = counts_array - baseline
        
        residual_peaks, _ = find_peaks(
            residual,
            prominence=max(3, np.max(residual) * 0.01),
            distance=distance,
            height=0
        )
        
        for idx in residual_peaks:
            if counts_array[idx] > max_count * 0.05:  # At least 5% of max counts
                too_close = any(abs(idx - existing) < distance for existing in peaks_found.keys())
                if not too_close:
                    peaks_found[idx] = {
                        "energy": float(energies_array[idx]),
                        "counts": float(counts_array[idx]),
                        "index": int(idx),
                        "type": "residual"
                    }
        
        # Format and sort results
        peaks = list(peaks_found.values())
        peaks_sorted = sorted(peaks, key=lambda x: x['counts'], reverse=True)
        
        # Return top 40 peaks (increased from 30)
        return peaks_sorted[:40]
        
    except Exception as e:
        print(f"Peak detection error: {e}")
        import traceback
        traceback.print_exc()
        return []

