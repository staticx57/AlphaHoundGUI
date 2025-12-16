"""Test updated isotope detection with 6-hour uranium glass spectrum."""
import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

import numpy as np
from scipy.signal import find_peaks

# Import just the isotope detection (no csv_parser to avoid circular imports)
from isotope_database import identify_isotopes, identify_decay_chains

# Manually parse the CSV (Energy,Counts format with header)
csv_path = 'backend/data/acquisitions/spectrum_2025-12-12_08-41-27.csv'
counts = []
energies = []

with open(csv_path, 'r') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or 'Energy' in line:
            continue  # Skip header and comments
        parts = line.split(',')
        if len(parts) >= 2:
            try:
                energies.append(float(parts[0]))  # Energy first
                counts.append(int(float(parts[1])))  # Counts second
            except:
                pass

print(f"Loaded: {len(counts)} channels, {sum(counts)} total counts")

counts_arr = np.array(counts)

# Find peaks
peaks_idx, props = find_peaks(counts_arr, height=5, prominence=3, distance=5)
peaks = []
for idx in peaks_idx:
    peaks.append({'energy': energies[idx], 'counts': int(counts_arr[idx])})

print(f"Found {len(peaks)} peaks")

# Run isotope identification
isotopes = identify_isotopes(peaks, energy_tolerance=20.0, mode='simple')
print("\n=== ISOTOPE IDENTIFICATION (Top 10) ===")
for iso in isotopes[:10]:
    suppressed = ' [SUPPRESSED]' if iso.get('suppressed') else ''
    weight = iso.get('abundance_weight', 1.0)
    raw = iso.get('raw_confidence', iso['confidence'])
    print(f"{iso['isotope']:12} {iso['confidence']:6.1f}% (raw: {raw:.1f}%, weight: {weight}) [{iso['matches']}/{iso['total_lines']} peaks]{suppressed}")

# Run decay chain detection
chains = identify_decay_chains(peaks, isotopes, energy_tolerance=20.0)
print("\n=== DECAY CHAIN DETECTION ===")
for chain in chains:
    if chain['num_detected'] > 0:
        print(f"{chain['chain_name']:15} {chain['confidence']:5.1f}% - {chain['num_detected']}/{chain['num_key_isotopes']} indicators")

# Check U-235 vs U-238 ordering
print("\n=== U-235 vs U-238 RANKING ===")
u235_rank = None
u238_rank = None
for i, iso in enumerate(isotopes):
    if iso['isotope'] == 'U-235':
        u235_rank = i + 1
        print(f"U-235 rank: #{u235_rank} with {iso['confidence']:.1f}% confidence")
    elif iso['isotope'] == 'U-238':
        u238_rank = i + 1
        print(f"U-238 rank: #{u238_rank} with {iso['confidence']:.1f}% confidence")

if u235_rank and u238_rank:
    if u238_rank < u235_rank:
        print("\n[OK] SUCCESS: U-238 correctly ranks ABOVE U-235!")
    else:
        print("\n[!!] ISSUE: U-235 still ranks above U-238")
elif u238_rank and not u235_rank:
    print("\n[OK] SUCCESS: U-238 detected, U-235 not detected!")
elif not u238_rank and not u235_rank:
    print("\n[??] Neither U-238 nor U-235 detected in top results")
