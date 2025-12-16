import sys
import os
import numpy as np
from scipy.signal import find_peaks

# Ensure we can import from backend root
sys.path.append(os.getcwd())

import n42_parser
try:
    from isotope_database import identify_isotopes
except ImportError:
    print("Error importing isotope_database. Make sure you are running from 'backend' directory.")
    sys.exit(1)

def get_peaks(energies, counts):
    """Detect peaks using parameters from peak_detection.py"""
    counts_array = np.array(counts)
    
    # Parameters from peak_detection.py
    max_count = np.max(counts_array)
    min_height = max(5, max_count * 0.003)
    min_prominence = max(3, max_count * 0.002)
    distance = 10
    
    indices, _ = find_peaks(
        counts_array,
        prominence=min_prominence,
        distance=distance,
        height=min_height
    )
    
    formatted = []
    for idx in indices:
        formatted.append({
            'energy': energies[idx],
            'counts': float(counts_array[idx]),
            'index': int(idx)
        })
    return formatted

def run_comparison():
    # File path relative to backend
    filepath = 'data/acquisitions/spectrum_2025-12-15_14-15-26.n42'
    
    if not os.path.exists(filepath):
        # SEARCH recursively if not found
        for root, dirs, files in os.walk('.'):
            if 'spectrum_2025-12-15_14-15-26.n42' in files:
                filepath = os.path.join(root, 'spectrum_2025-12-15_14-15-26.n42')
                break
    
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    print(f"Analyzing file: {filepath}")
    
    with open(filepath, 'r') as f:
        content = f.read()
        
    data = n42_parser.parse_n42(content)
    if 'counts' not in data:
        print("Failed to parse counts from N42.")
        return
        
    counts = data['counts']
    
    # === Test 3.0 keV/channel ===
    energies_3 = [i * 3.0 for i in range(len(counts))]
    peaks_3 = get_peaks(energies_3, counts)
    isotopes_3 = identify_isotopes(peaks_3)
    
    # === Test 7.4 keV/channel ===
    energies_74 = [i * 7.4 for i in range(len(counts))]
    peaks_74 = get_peaks(energies_74, counts)
    isotopes_74 = identify_isotopes(peaks_74)
    
    print(f"\n{'='*20} COMPARISON RESULTS {'='*20}")
    print(f"Total Counts: {sum(counts)}")
    print(f"Channels: {len(counts)}")
    
    def print_results(cal_name, results_list, peaks):
        # Convert list to dict for lookup
        results = {r['isotope']: r for r in results_list}
        
        print(f"\n--- {cal_name} ---")
        print(f"Detected Peaks: {len(peaks)}")
        
        # Check specific isotopes of interest
        thorium = results.get('Th-232')
        uranium = results.get('U-238')
        pb212 = results.get('Pb-212') # Thorium daughter
        pb214 = results.get('Pb-214') # Uranium daughter
        
        # Helper to format output
        def fmt(res):
            if not res: return "Not Detected"
            base = f"{res['confidence']:.1f}% ({res['matches']} matches)"
            if res.get('matched_peaks'):
                 peaks_str = ", ".join([f"{p['expected']:.1f}keV" for p in res['matched_peaks']])
                 base += f" [Matches: {peaks_str}]"
            return base

        print(f"Th-232 (Chain): {fmt(thorium)}")
        print(f"Pb-212 (Th-232): {fmt(pb212)}")
        print(f"U-238 (Chain):  {fmt(uranium)}")
        print(f"Pb-214 (U-238):  {fmt(pb214)}")
        
        print("\nTop 5 Identities:")
        # Filter out suppressed
        active_isos = [i for i in results.values()]
        sorted_isos = sorted(active_isos, key=lambda x: x['confidence'], reverse=True)[:5]
        for iso in sorted_isos:
             print(f"  {iso['isotope']}: {iso['confidence']:.1f}% ({iso['matches']} matches)")

    print_results("Calibration: 3.0 keV/Channel", isotopes_3, peaks_3)
    print_results("Calibration: 7.4 keV/Channel", isotopes_74, peaks_74)

if __name__ == "__main__":
    run_comparison()
