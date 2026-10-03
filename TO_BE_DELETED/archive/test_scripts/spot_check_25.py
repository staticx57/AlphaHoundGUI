"""
Spot check ML model with 25 diverse isotopes
"""
import requests
import numpy as np

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

def create_spectrum(peaks):
    """Create a synthetic spectrum with given peaks"""
    counts = np.random.poisson(5, n_channels).astype(float)
    for energy, intensity in peaks:
        add_peak(counts, energy, intensity)
    return [int(c) for c in counts]

def test_isotope(name, peaks, expected_isotopes):
    """Test a specific isotope pattern"""
    spectrum = create_spectrum(peaks)
    try:
        resp = requests.post(ENDPOINT, json={'counts': spectrum}, timeout=30)
        if resp.status_code == 200:
            preds = resp.json().get('predictions', [])
            if preds:
                top = preds[0]
                top_iso = top['isotope']
                top_conf = top['confidence']
                # Check if top prediction matches expected
                match = any(exp in top_iso for exp in expected_isotopes) or top_iso in expected_isotopes
                status = "✓" if match else "✗"
                return f"{status} {name}: {top_iso} ({top_conf:.1f}%)"
            return f"? {name}: No predictions"
        return f"✗ {name}: HTTP {resp.status_code}"
    except Exception as e:
        return f"✗ {name}: Error - {e}"

print("="*60)
print("ML MODEL SPOT CHECK - 25 ISOTOPES")
print("="*60)
print()

# Test cases: (name, [(energy_keV, intensity), ...], [acceptable_matches])
test_cases = [
    # Calibration Sources
    ("Cs-137", [(661.7, 200)], ["Cs-137"]),
    ("Co-60", [(1173.2, 150), (1332.5, 150)], ["Co-60"]),
    ("Na-22", [(511.0, 180), (1274.5, 120)], ["Na-22"]),
    ("Am-241", [(59.5, 200)], ["Am-241"]),
    ("Ba-133", [(81.0, 100), (356.0, 150), (302.9, 80)], ["Ba-133"]),
    
    # Natural Background
    ("K-40", [(1460.8, 100)], ["K-40"]),
    
    # U-238 Decay Chain
    ("Bi-214", [(609.3, 200), (1120.3, 100), (1764.5, 80)], ["Bi-214"]),
    ("Pb-214", [(295.2, 150), (351.9, 180), (241.0, 100)], ["Pb-214"]),
    ("Ra-226", [(186.2, 150)], ["Ra-226", "U-235"]),  # Ra-226/U-235 overlap at 186 keV
    
    # Th-232 Decay Chain
    ("Tl-208", [(583.2, 150), (2614.5, 80)], ["Tl-208"]),
    ("Ac-228", [(338.3, 120), (911.2, 150), (968.9, 100)], ["Ac-228"]),
    ("Pb-212", [(238.6, 150)], ["Pb-212"]),
    
    # U-235 Chain
    ("U-235", [(185.7, 150), (143.8, 100)], ["U-235", "Ra-226"]),
    
    # Medical Isotopes
    ("I-131", [(364.5, 180)], ["I-131"]),
    ("Tc-99m", [(140.5, 200)], ["Tc-99m"]),
    
    # Industrial/Rare Earth
    ("Eu-152", [(121.8, 100), (344.3, 150), (1408.0, 80)], ["Eu-152"]),
    ("Ir-192", [(296.0, 120), (308.0, 130), (468.0, 100), (604.4, 90)], ["Ir-192"]),
    
    # Fission Products
    ("Zr-95", [(724.2, 150), (756.7, 140)], ["Zr-95"]),
    ("Cs-134", [(604.7, 150), (795.9, 140)], ["Cs-134"]),
    ("La-140", [(1596.2, 120), (487.0, 100)], ["La-140"]),
    
    # Activation Products  
    ("Co-57", [(122.1, 180), (136.5, 100)], ["Co-57"]),
    ("Mn-54", [(834.8, 180)], ["Mn-54"]),
    ("Zn-65", [(1115.5, 150)], ["Zn-65"]),
    
    # Actinides
    ("Pu-239", [(51.6, 80), (129.3, 60), (375.0, 50)], ["Pu-239"]),
    ("Np-237", [(86.5, 120), (143.2, 100)], ["Np-237"]),
]

results = []
correct = 0
for name, peaks, expected in test_cases:
    result = test_isotope(name, peaks, expected)
    results.append(result)
    if result.startswith("✓"):
        correct += 1

for r in results:
    print(r)

print()
print("="*60)
accuracy = (correct / len(test_cases)) * 100
print(f"RESULTS: {correct}/{len(test_cases)} correct ({accuracy:.1f}% accuracy)")
print("="*60)
