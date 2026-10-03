"""Cross-reference community spectra: Expected isotopes vs Peak Matching results."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import numpy as np
from scipy.signal import find_peaks
from isotope_database import identify_isotopes, identify_decay_chains

# Community spectra and expected isotopes based on filename
COMMUNITY_SPECTRA = {
    "14 hour spectrum of radium dial watch.csv": {
        "expected": ["Ra-226", "Pb-214", "Bi-214"],
        "chain": "U-238 Chain (Radium)"
    },
    "7.5 x 4 Deep Red Uranium Glaze Bowl.csv": {
        "expected": ["U-238", "Bi-214", "Pb-214", "Ra-226"],
        "chain": "U-238 Chain (Uranium Glaze)"
    },
    "Orange Fiestaware Saucer.csv": {
        "expected": ["U-238", "Bi-214", "Pb-214"],
        "chain": "U-238 Chain (Fiestaware)"
    },
    "Orange Red Wing Chevron Salt Cellar.csv": {
        "expected": ["U-238", "Bi-214", "Pb-214"],
        "chain": "U-238 Chain (Uranium Glaze)"
    },
    "Uraninite Ore.csv": {
        "expected": ["U-238", "Bi-214", "Pb-214", "Ra-226", "Pa-234m"],
        "chain": "U-238 Chain (Mineral Ore)"
    },
    "Uranium glass 9 hours.csv": {
        "expected": ["U-238", "Bi-214", "Pb-214", "Th-234"],
        "chain": "U-238 Chain (Vaseline Glass)"
    }
}

def parse_csv(filepath):
    """Parse CSV file, auto-detecting format."""
    counts = []
    channels = []
    
    with open(filepath, 'r', errors='ignore') as f:
        lines = f.readlines()
    
    # Check header to determine format
    header = lines[0].lower().strip() if lines else ""
    
    # Community format: "Data,Energy" where Data=Counts, Energy=Channel#
    if 'data' in header or (len(lines) > 1 and lines[1].split(',')[1].strip().isdigit()):
        print(f"  Format: Data,Channel (community style)")
        for line in lines[1:]:  # Skip header
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) >= 2:
                try:
                    counts.append(int(float(parts[0])))
                    channels.append(int(float(parts[1])))
                except:
                    pass
        
        # Apply calibration: ~3 keV/channel for these files (likely Radiacode or similar)
        # Try to auto-detect based on channel count
        n_channels = max(channels) + 1 if channels else len(counts)
        if n_channels > 2000:  # Likely 4096 channel detector
            kev_per_channel = 0.75  # Typical for high-res NaI
        elif n_channels > 1000:  # Likely 1024 or 2048 channel
            kev_per_channel = 3.0  # Typical for NaI/CsI
        else:
            kev_per_channel = 3.0  # Default
        
        energies = [ch * kev_per_channel for ch in range(len(counts))]
        print(f"  Channels: {len(counts)}, keV/ch: {kev_per_channel}")
        
    else:
        # AlphaHound format: "Energy (keV),Counts"
        print(f"  Format: Energy,Counts (AlphaHound style)")
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) >= 2:
                try:
                    energies.append(float(parts[0]))
                    counts.append(int(float(parts[1])))
                except:
                    pass
    
    return counts, energies

def analyze_spectrum(filepath):
    """Analyze a spectrum file and return isotope matches."""
    counts, energies = parse_csv(filepath)
    
    if len(counts) < 10:
        return None, None, f"Too few data points ({len(counts)})"
    
    counts_arr = np.array(counts)
    total_counts = sum(counts)
    
    print(f"  Total counts: {total_counts:,}")
    print(f"  Energy range: {energies[0]:.1f} - {energies[-1]:.1f} keV")
    
    # Find peaks - adjust threshold based on total counts
    if total_counts > 100000:
        height_thresh = max(50, np.max(counts_arr) * 0.01)
    else:
        height_thresh = max(5, np.max(counts_arr) * 0.02)
    
    peaks_idx, _ = find_peaks(counts_arr, height=height_thresh, prominence=height_thresh*0.5, distance=5)
    
    peaks = []
    for idx in peaks_idx:
        if idx < len(energies):
            peaks.append({'energy': energies[idx], 'counts': int(counts_arr[idx])})
    
    print(f"  Peaks found: {len(peaks)}")
    
    if len(peaks) == 0:
        return [], [], None
    
    # Run isotope identification
    isotopes = identify_isotopes(peaks, energy_tolerance=20.0, mode='simple')
    chains = identify_decay_chains(peaks, isotopes, energy_tolerance=20.0)
    
    return isotopes, chains, None

# Main analysis
print("="*80)
print("COMMUNITY SPECTRA CROSS-REFERENCE ANALYSIS")
print("="*80)

base_path = "backend/data/acquisitions/community"
results = []

for filename, expected_info in COMMUNITY_SPECTRA.items():
    filepath = os.path.join(base_path, filename)
    
    if not os.path.exists(filepath):
        print(f"\n[MISSING] {filename}")
        continue
    
    print(f"\n{'='*80}")
    print(f"FILE: {filename}")
    print(f"EXPECTED: {', '.join(expected_info['expected'])} ({expected_info['chain']})")
    print("-"*80)
    
    isotopes, chains, error = analyze_spectrum(filepath)
    
    if error:
        print(f"ERROR: {error}")
        continue
    
    # Check for expected isotopes
    found_isotopes = [iso['isotope'] for iso in isotopes[:15]] if isotopes else []
    expected_set = set(expected_info['expected'])
    
    # Count matches
    matches = []
    misses = []
    for exp in expected_info['expected']:
        if exp in found_isotopes:
            rank = found_isotopes.index(exp) + 1
            conf = next(i['confidence'] for i in isotopes if i['isotope'] == exp)
            matches.append(f"{exp} (#{rank}, {conf:.1f}%)")
        else:
            misses.append(exp)
    
    # Check for U-235 false positive
    u235_found = any(iso['isotope'] == 'U-235' for iso in (isotopes[:10] if isotopes else []))
    
    print(f"TOP 10 DETECTED:")
    if isotopes:
        for i, iso in enumerate(isotopes[:10]):
            marker = " <-- EXPECTED" if iso['isotope'] in expected_set else ""
            suppressed = " [SUPPRESSED]" if iso.get('suppressed') else ""
            print(f"  {i+1:2}. {iso['isotope']:12} {iso['confidence']:6.1f}%{suppressed}{marker}")
    else:
        print("  (none)")
    
    print(f"\nMATCHES: {', '.join(matches) if matches else 'NONE'}")
    print(f"MISSING: {', '.join(misses) if misses else 'All found!'}")
    
    if u235_found:
        u235_conf = next(i['confidence'] for i in isotopes if i['isotope'] == 'U-235')
        print(f"WARNING: U-235 false positive detected at {u235_conf:.1f}%")
    else:
        print("U-235: Correctly NOT in top 10 (Good!)")
    
    # Decay chain detection
    print(f"\nDECAY CHAINS:")
    if chains:
        for chain in chains[:3]:
            if chain['num_detected'] > 0:
                print(f"  {chain['chain_name']:15} {chain['confidence']:5.1f}% ({chain['num_detected']}/{chain['num_key_isotopes']} indicators)")
    else:
        print("  (none detected)")
    
    # Score
    score = len(matches) / len(expected_info['expected']) * 100 if expected_info['expected'] else 0
    results.append({
        'file': filename,
        'score': score,
        'matches': len(matches),
        'expected': len(expected_info['expected']),
        'u235_fp': u235_found
    })

# Summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"{'File':<50} {'Score':>10} {'U-235 FP':>12}")
print("-"*80)
for r in results:
    fp = "YES (BAD)" if r['u235_fp'] else "No (Good)"
    print(f"{r['file']:<50} {r['score']:>8.0f}% {fp:>12}")

total_score = sum(r['score'] for r in results) / len(results) if results else 0
total_fp = sum(1 for r in results if r['u235_fp'])
print("-"*80)
print(f"{'AVERAGE':<50} {total_score:>8.0f}%")
print(f"U-235 False Positives: {total_fp}/{len(results)}")
