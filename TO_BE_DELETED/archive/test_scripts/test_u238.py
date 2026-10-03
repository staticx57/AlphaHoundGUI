"""
Test U-238 identification with the new comprehensive ML model
"""
import requests
import numpy as np

# Create a U-238 decay chain spectrum with characteristic peaks
# Based on authoritative IAEA/NNDC data:
# - Th-234: 63.3 keV
# - Pa-234m: 1001.0 keV, 766.4 keV  
# - Bi-214: 609.3 keV, 1120.3 keV, 1764.5 keV
# - Pb-214: 295.2 keV, 351.9 keV, 241.0 keV

n_channels = 1024
keV_per_channel = 3.0  # Same as ML training

def add_peak(counts, energy_keV, intensity=150):
    channel = int(energy_keV / keV_per_channel)
    if 5 <= channel < n_channels - 5:
        width = 5
        start = max(0, channel - width // 2)
        end = min(n_channels, channel + width // 2 + 1)
        counts[start:end] += np.random.poisson(intensity, end - start)

# Base background
counts = np.random.poisson(8, n_channels).astype(float)

# Add U-238 decay chain peaks
print("Creating U-238 decay chain spectrum with characteristic peaks:")
print("  - Th-234: 63 keV")
add_peak(counts, 63.3, 100)
print("  - Th-234 (weak): 49.5 keV")
add_peak(counts, 49.55, 50)
print("  - Pa-234m: 1001 keV")
add_peak(counts, 1001.0, 80)
print("  - Pa-234m: 766 keV")
add_peak(counts, 766.4, 70)
print("  - Bi-214: 609 keV (strongest)")
add_peak(counts, 609.3, 180)
print("  - Bi-214: 1120 keV")
add_peak(counts, 1120.3, 90)
print("  - Bi-214: 1764 keV")
add_peak(counts, 1764.5, 60)
print("  - Pb-214: 295 keV")
add_peak(counts, 295.2, 100)
print("  - Pb-214: 352 keV")
add_peak(counts, 351.9, 110)
print("  - Ra-226: 186 keV")
add_peak(counts, 186.2, 90)

counts_list = [int(c) for c in counts]

print(f"\nSpectrum: {len(counts_list)} channels")
print(f"Total counts: {sum(counts_list)}")
print()

try:
    print("Testing ML Identification Endpoint...")
    response = requests.post(
        'http://localhost:8080/analyze/ml-identify',
        json={'counts': counts_list},
        timeout=120  # Training may take longer with more isotopes
    )
    
    print(f"Status Code: {response.status_code}")
    print()
    
    if response.status_code == 200:
        result = response.json()
        print("✓ SUCCESS - ML Endpoint is working!")
        print()
        if 'predictions' in result and result['predictions']:
            print("Predictions (should identify U-238 chain isotopes):")
            for pred in result['predictions']:
                isotope = pred.get('isotope', 'Unknown')
                conf = pred.get('confidence', 0)
                # Highlight U-238 chain isotopes (with hyphens as in database)
                chain_isotopes = ['U-238', 'Th-234', 'Pa-234m', 'U-234', 'Bi-214', 'Pb-214', 'Ra-226', 'Rn-222', 'Po-214']
                marker = " *** U-238 CHAIN ***" if isotope in chain_isotopes else ""
                print(f"  - {isotope}: {conf:.2f}%{marker}")
        else:
            print("  No predictions returned")
    else:
        print(f"✗ ERROR: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("✗ ERROR: Could not connect to server")
except Exception as e:
    print(f"✗ ERROR: {e}")
