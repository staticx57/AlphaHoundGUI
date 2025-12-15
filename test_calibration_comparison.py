"""Compare PyRIID ML accuracy between 3 keV/channel and 7.4 keV/channel calibrations."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import numpy as np

# Parse the 6-hour uranium glass CSV
csv_path = 'backend/data/acquisitions/spectrum_2025-12-12_08-41-27.csv'
counts = []
energies = []

with open(csv_path, 'r') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or 'Energy' in line:
            continue
        parts = line.split(',')
        if len(parts) >= 2:
            try:
                energies.append(float(parts[0]))
                counts.append(int(float(parts[1])))
            except:
                pass

print(f"Loaded: {len(counts)} channels, {sum(counts)} total counts")
print(f"Energy range: {energies[0]:.1f} - {energies[-1]:.1f} keV")
print(f"Actual keV/channel: {(energies[-1] - energies[0]) / len(energies):.2f}")

# Import ML
try:
    from ml_analysis import MLIdentifier
    HAS_ML = True
except ImportError as e:
    print(f"Cannot import ML: {e}")
    HAS_ML = False

if HAS_ML:
    print("\n" + "="*60)
    print("TEST 1: PyRIID with 3 keV/channel (current setting)")
    print("="*60)
    
    ml_3kev = MLIdentifier()
    ml_3kev.keV_per_channel = 3.0
    ml_3kev.lazy_train()
    results_3kev = ml_3kev.identify(counts, top_k=5)
    
    print("\nTop 5 ML predictions (3 keV/channel):")
    for r in results_3kev:
        print(f"  {r['isotope']:20} {r['confidence']:5.1f}%")
    
    # Check for uranium identification
    u_found_3kev = [r for r in results_3kev if 'Uranium' in r['isotope'] or 'U-2' in r['isotope']]
    bi214_found_3kev = [r for r in results_3kev if 'Bi-214' in r['isotope']]
    
    print("\n" + "="*60)
    print("TEST 2: PyRIID with 7.4 keV/channel (device actual)")
    print("="*60)
    
    # Reset and retrain with 7.4 keV
    ml_7kev = MLIdentifier()
    ml_7kev.keV_per_channel = 7.4
    ml_7kev.is_trained = False
    ml_7kev.model = None
    ml_7kev.lazy_train()
    results_7kev = ml_7kev.identify(counts, top_k=5)
    
    print("\nTop 5 ML predictions (7.4 keV/channel):")
    for r in results_7kev:
        print(f"  {r['isotope']:20} {r['confidence']:5.1f}%")
    
    # Compare
    print("\n" + "="*60)
    print("COMPARISON SUMMARY")
    print("="*60)
    
    def find_uranium_glass(results):
        for r in results:
            if 'UraniumGlass' in r['isotope']:
                return r['confidence']
            if 'Bi-214' in r['isotope']:  # Key indicator
                return r['confidence']
        return 0
    
    score_3kev = find_uranium_glass(results_3kev)
    score_7kev = find_uranium_glass(results_7kev)
    
    print(f"3 keV/channel: UraniumGlass/Bi-214 confidence = {score_3kev:.1f}%")
    print(f"7.4 keV/channel: UraniumGlass/Bi-214 confidence = {score_7kev:.1f}%")
    
    if score_7kev > score_3kev:
        print("\n--> 7.4 keV/channel is MORE ACCURATE for this spectrum")
    elif score_3kev > score_7kev:
        print("\n--> 3 keV/channel is MORE ACCURATE for this spectrum")
    else:
        print("\n--> Both calibrations perform similarly")
