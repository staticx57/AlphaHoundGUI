import numpy as np
from scipy.signal import find_peaks

def detect_peaks(energies, counts, prominence_factor=0.05, distance=10):
    """
    Detect peaks in spectrum data.
    
    Args:
        energies: Array of energy values
        counts: Array of count values
        prominence_factor: Minimum prominence as fraction of max counts
        distance: Minimum distance between peaks (in indices)
    
    Returns:
        List of dictionaries with peak information
    """
    try:
        counts_array = np.array(counts)
        energies_array = np.array(energies)
        
        # Calculate prominence threshold
        max_count = np.max(counts_array)
        prominence = max_count * prominence_factor
        
        # Find peaks
        peak_indices, properties = find_peaks(
            counts_array,
            prominence=prominence,
            distance=distance,
            height=max_count * 0.01  # Minimum height 1% of max
        )
        
        # Format results
        peaks = []
        for idx in peak_indices:
            peaks.append({
                "energy": float(energies_array[idx]),
                "counts": float(counts_array[idx]),
                "index": int(idx)
            })
        
        # Sort by counts (descending) and return top 20
        peaks_sorted = sorted(peaks, key=lambda x: x['counts'], reverse=True)
        return peaks_sorted[:20]
        
    except Exception as e:
        print(f"Peak detection error: {e}")
        return []
