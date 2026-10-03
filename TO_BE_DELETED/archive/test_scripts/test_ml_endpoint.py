"""
Quick test script to verify the ML PyRIID endpoint is working
"""
import requests
import json
import numpy as np

# Create a test spectrum with a Cs-137 like peak at channel 662
# (matching the training data in ml_analysis.py)
counts = np.zeros(1024)
# Add background
counts += np.random.poisson(8, 1024)
# Add a Gaussian peak at channel 662 (Cs-137 signature)
peak_center = 662
peak_width = 5
peak_height = 250
x = np.arange(1024)
counts += peak_height * np.exp(-0.5 * ((x - peak_center) / peak_width) ** 2)

# Convert to list of integers
counts_list = [int(c) for c in counts]

print("Testing ML Identification Endpoint...")
print(f"Spectrum: {len(counts_list)} channels")
print(f"Peak at channel {peak_center}")
print()

try:
    response = requests.post(
        'http://localhost:8080/analyze/ml-identify',
        json={'counts': counts_list},
        timeout=30
    )
    
    print(f"Status Code: {response.status_code}")
    print()
    
    if response.status_code == 200:
        result = response.json()
        print("✓ SUCCESS - ML Endpoint is working!")
        print()
        print("Predictions:")
        if 'predictions' in result and result['predictions']:
            for pred in result['predictions']:
                print(f"  - {pred.get('isotope', 'Unknown')}: {pred.get('confidence', 0):.2f}% ({pred.get('method', 'N/A')})")
        else:
            print("  No predictions returned (might need more realistic spectrum)")
    elif response.status_code == 501:
        print("⚠ PyRIID Not Installed")
        print(f"Message: {response.json().get('detail', 'No detail')}")
    else:
        print(f"✗ ERROR")
        print(f"Response: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("✗ ERROR: Could not connect to server")
    print("Make sure the backend is running on http://localhost:8080")
except Exception as e:
    print(f"✗ ERROR: {e}")
