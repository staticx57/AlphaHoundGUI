"""Investigate why Bi-214 isn't being detected in community spectra."""
import numpy as np
from scipy.signal import find_peaks

# Load 14 hour radium dial watch (has most counts)
filepath = 'backend/data/acquisitions/community/14 hour spectrum of radium dial watch.csv'
counts = []
with open(filepath, 'r') as f:
    for line in f.readlines()[1:]:
        parts = line.strip().split(',')
        if len(parts) >= 2:
            try:
                counts.append(int(float(parts[0])))
            except: pass

# Apply 3 keV/channel calibration
energies = [i * 3.0 for i in range(len(counts))]
counts_arr = np.array(counts)

print("="*60)
print("INVESTIGATING Bi-214 DETECTION")
print("="*60)
print(f"File: 14 hour spectrum of radium dial watch.csv")
print(f"Total channels: {len(counts)}, Total counts: {sum(counts):,}")
print()

# Bi-214 gamma lines from our database
bi214_lines = [609.3, 1120.3, 1764.5]
print("=== Bi-214 Expected Peaks ===")
for line in bi214_lines:
    ch = int(line / 3.0)
    start = max(0, ch - 5)
    end = min(len(counts), ch + 6)
    region = counts_arr[start:end]
    
    print(f"\nBi-214 @ {line} keV (expected channel ~{ch}):")
    print(f"  Region ch {start}-{end}: {list(region)}")
    print(f"  Max in region: {max(region)} at channel {start + np.argmax(region)}")
    print(f"  Energy at max: {(start + np.argmax(region)) * 3.0:.1f} keV")

# Run peak detection with same params as main code
print("\n" + "="*60)
print("PEAK DETECTION RESULTS")
print("="*60)
height_thresh = max(50, np.max(counts_arr) * 0.01)
print(f"Height threshold used: {height_thresh}")

peaks_idx, props = find_peaks(counts_arr, height=height_thresh, prominence=height_thresh*0.5, distance=5)
print(f"Total peaks found: {len(peaks_idx)}")

# Show all detected peaks
print("\nAll detected peaks:")
for p in peaks_idx:
    energy = p * 3.0
    print(f"  Channel {p:4d} = {energy:7.1f} keV, counts: {counts_arr[p]:,}")

# Check which Bi-214 lines are near detected peaks
print("\n" + "="*60)
print("Bi-214 MATCHING")
print("="*60)
tolerance = 20  # keV
for line in bi214_lines:
    matches = [p for p in peaks_idx if abs(p * 3.0 - line) <= tolerance]
    if matches:
        for m in matches:
            print(f"  Bi-214 {line} keV: MATCHED peak at {m*3.0:.1f} keV")
    else:
        print(f"  Bi-214 {line} keV: NO MATCH FOUND")
        # Check why
        ch = int(line / 3.0)
        region_counts = counts_arr[max(0,ch-3):min(len(counts),ch+4)]
        print(f"    Region counts: {list(region_counts)}")
        print(f"    Max in region: {max(region_counts)} (threshold: {height_thresh})")
