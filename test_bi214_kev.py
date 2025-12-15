"""Analyze keV-calibrated files for Bi-214 detection."""
import numpy as np
from scipy.signal import find_peaks

# Files with actual keV data (per user)
kev_files = [
    "Uraninite Ore.csv",
    "7.5 x 4 Deep Red Uranium Glaze Bowl.csv",
    "Orange Red Wing Chevron Salt Cellar.csv",
    "Orange Fiestaware Saucer.csv"
]

base_path = "backend/data/acquisitions/community"
bi214_lines = [609.3, 1120.3, 1764.5]

print("="*70)
print("Bi-214 ANALYSIS - keV CALIBRATED FILES ONLY")
print("="*70)

for filename in kev_files:
    filepath = f"{base_path}/{filename}"
    
    try:
        counts = []
        energies = []
        with open(filepath, 'r') as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    try:
                        counts.append(int(float(parts[0])))
                        energies.append(float(parts[1]))
                    except: pass
        
        counts_arr = np.array(counts)
        energies_arr = np.array(energies)
        
        print(f"\n{'='*70}")
        print(f"FILE: {filename}")
        print(f"Channels: {len(counts)}, Total counts: {sum(counts):,}")
        print(f"Energy range: {min(energies):.1f} - {max(energies):.1f} keV")
        
        # Check for Bi-214 peaks
        print(f"\nBi-214 Peak Regions:")
        for line_energy in bi214_lines:
            # Find closest channel to this energy
            if line_energy > max(energies):
                print(f"  {line_energy} keV: OUTSIDE DETECTOR RANGE (max {max(energies):.0f} keV)")
                continue
            
            ch = np.argmin(np.abs(energies_arr - line_energy))
            start = max(0, ch - 5)
            end = min(len(counts), ch + 6)
            
            region = counts_arr[start:end]
            max_idx = start + np.argmax(region)
            
            print(f"  {line_energy} keV (ch {ch}):")
            print(f"    Region counts: {list(region)}")
            print(f"    Max: {max(region)} at {energies[max_idx]:.1f} keV")
        
        # Find peaks with adjusted threshold
        height_thresh = max(5, np.percentile(counts_arr, 95) * 0.2)
        peaks_idx, _ = find_peaks(counts_arr, height=height_thresh, prominence=3, distance=5)
        
        print(f"\nPeak Detection (threshold={height_thresh:.0f}):")
        print(f"  Peaks found: {len(peaks_idx)}")
        
        # Check Bi-214 matches
        found_any = False
        for line_energy in bi214_lines:
            if line_energy > max(energies):
                continue
            matches = [p for p in peaks_idx if abs(energies[p] - line_energy) <= 20]
            if matches:
                for m in matches:
                    print(f"  MATCH: Bi-214 {line_energy} keV = peak at {energies[m]:.1f} keV")
                    found_any = True
        
        if not found_any:
            print("  NO Bi-214 peaks detected!")
            # Show what peaks ARE detected
            print("  Top 5 detected peaks:")
            sorted_peaks = sorted([(p, counts_arr[p]) for p in peaks_idx], key=lambda x: -x[1])[:5]
            for p, c in sorted_peaks:
                print(f"    {energies[p]:.1f} keV, counts: {c}")
                
    except Exception as e:
        print(f"\nERROR: {filename}: {e}")
