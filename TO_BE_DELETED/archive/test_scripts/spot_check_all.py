"""
Spot check ML model with ALL isotopes from ISOTOPE_DATABASE_ADVANCED
"""
import requests
import numpy as np
import sys
sys.path.insert(0, '.')

from isotope_database import ISOTOPE_DATABASE_ADVANCED

ENDPOINT = 'http://localhost:8080/analyze/ml-identify'
n_channels = 1024
keV_per_channel = 3.0

def add_peak(counts, energy_keV, intensity=150):
    """Add a Gaussian-like peak at the specified energy"""
    channel = int(energy_keV / keV_per_channel)
    if 5 <= channel < n_channels - 5:
        width = 5
        start = max(0, channel - width // 2)
        end = min(n_channels, channel + width // 2 + 1)
        counts[start:end] += np.random.poisson(intensity, end - start)

def create_spectrum(energies):
    """Create a synthetic spectrum with peaks at given energies"""
    counts = np.random.poisson(5, n_channels).astype(float)
    for energy in energies:
        # Intensity based on energy
        intensity = max(50, 300 - energy / 10)
        add_peak(counts, energy, int(intensity))
    return [int(c) for c in counts]

def test_isotope(name, energies):
    """Test a specific isotope"""
    if not energies:  # Skip isotopes with no gamma emissions
        return None, "SKIP", 0
    
    spectrum = create_spectrum(energies)
    try:
        resp = requests.post(ENDPOINT, json={'counts': spectrum}, timeout=30)
        if resp.status_code == 200:
            preds = resp.json().get('predictions', [])
            if preds:
                top = preds[0]
                top_iso = top['isotope']
                top_conf = top['confidence']
                match = (top_iso == name)
                return top_iso, "PASS" if match else "FAIL", top_conf
            return None, "NO_PRED", 0
        return None, f"HTTP_{resp.status_code}", 0
    except Exception as e:
        return None, f"ERROR", 0

print("="*70)
print("FULL ISOTOPE LIBRARY SPOT CHECK")
print(f"Testing {len(ISOTOPE_DATABASE_ADVANCED)} isotopes from IAEA/NNDC database")
print("="*70)
print()

# Test all isotopes
results = {"PASS": [], "FAIL": [], "SKIP": [], "NO_PRED": [], "ERROR": []}
total_tested = 0

for isotope, energies in sorted(ISOTOPE_DATABASE_ADVANCED.items()):
    predicted, status, confidence = test_isotope(isotope, energies)
    
    if status == "SKIP":
        results["SKIP"].append(isotope)
        continue
    
    total_tested += 1
    
    if status == "PASS":
        results["PASS"].append((isotope, confidence))
        print(f"✓ {isotope}: {confidence:.1f}%")
    elif status == "FAIL":
        results["FAIL"].append((isotope, predicted, confidence))
        print(f"✗ {isotope} → {predicted} ({confidence:.1f}%)")
    else:
        results[status].append(isotope)
        print(f"? {isotope}: {status}")

# Summary
print()
print("="*70)
print("SUMMARY")
print("="*70)

passed = len(results["PASS"])
failed = len(results["FAIL"])
skipped = len(results["SKIP"])
accuracy = (passed / total_tested * 100) if total_tested > 0 else 0

print(f"✓ PASSED:  {passed}")
print(f"✗ FAILED:  {failed}")
print(f"- SKIPPED: {skipped} (no gamma emissions)")
print()
print(f"ACCURACY: {passed}/{total_tested} = {accuracy:.1f}%")
print()

if results["FAIL"]:
    print("MISCLASSIFICATIONS:")
    for isotope, predicted, conf in results["FAIL"]:
        print(f"  {isotope} → {predicted} ({conf:.1f}%)")
