"""Test ML identification on 6hr uranium glass spectrum."""
import sys
import os
sys.path.insert(0, 'backend')

import numpy as np
from scipy.signal import find_peaks

# Load spectrum
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

# Test ML identification
try:
    from ml_analysis import get_ml_identifier
    
    ml = get_ml_identifier()
    print("\n=== ML IDENTIFICATION ===")
    print("Training ML model (this may take a moment)...")
    
    results = ml.identify(counts, top_k=10)
    
    print(f"\nTop 10 ML predictions:")
    for i, r in enumerate(results[:10]):
        print(f"  {i+1}. {r['isotope']:20} {r['confidence']:6.1f}%")

    # Check for uranium-related predictions
    uranium_related = ['U-238', 'U-235', 'Bi-214', 'Pb-214', 'Ra-226', 'Th-234', 
                       'UraniumGlass', 'UraniumMineral', 'RadiumDial']
    found = []
    for r in results[:10]:
        if any(u in r['isotope'] for u in uranium_related):
            found.append(r['isotope'])
    
    if found:
        print(f"\nUranium-related in top 10: {', '.join(found)}")
    else:
        print("\n[!] No uranium-related isotopes in top 10 ML predictions")

except Exception as e:
    print(f"\n[ERROR] ML test failed: {e}")
    import traceback
    traceback.print_exc()
