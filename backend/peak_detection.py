import numpy as np
from scipy.signal import find_peaks

def detect_peaks(energies, counts, prominence_factor=0.01, distance=10):
    """
    Detect peaks in spectrum data.
    
    Args:
        energies: Array of energy values
        counts: Array of count values
        prominence_factor: Minimum prominence as fraction of max counts (default 1%)
        distance: Minimum distance between peaks (in indices)
    
    Returns:
        List of dictionaries with peak information
    """
    try:
        counts_array = np.array(counts)
        energies_array = np.array(energies)
        
        # Use combined absolute and relative thresholds
        # This ensures we catch both strong and weak peaks
        max_count = np.max(counts_array)
        
        # Absolute minimum thresholds for real peaks (not noise)
        # Relative thresholds for spectra with very high counts
        min_height = max(5, max_count * 0.003)  # At least 5 counts or 0.3% of max
        min_prominence = max(3, max_count * 0.002)  # At least 3 counts or 0.2% of max
        
        # Find peaks with balanced thresholds
        peak_indices, properties = find_peaks(
            counts_array,
            prominence=min_prominence,
            distance=distance,
            height=min_height
        )
        
        # Format results
        peaks = []
        for idx in peak_indices:
            peaks.append({
                "energy": float(energies_array[idx]),
                "counts": float(counts_array[idx]),
                "index": int(idx)
            })
        
        # Sort by counts (descending) and return top 30 peaks
        peaks_sorted = sorted(peaks, key=lambda x: x['counts'], reverse=True)
        return peaks_sorted[:30]
        
    except Exception as e:
        print(f"Peak detection error: {e}")
        return []
