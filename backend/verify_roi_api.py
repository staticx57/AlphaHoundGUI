
import requests
import json
import numpy as np

def verify_api():
    url = "http://localhost:3200/analyze/roi"
    
    # Generate synthetic single peak data
    energies = np.linspace(0, 3000, 1024).tolist()
    counts = np.zeros(1024)
    
    # Add Cs-137 Peak at 662 keV
    # Channel approx 662 / (3000/1024) = 226
    centroid_idx = int(662 / (3000/1024))
    for i in range(1024):
        counts[i] = 1000 * np.exp(-0.5 * ((i - centroid_idx) / 5)**2) + 10
        
    payload = {
        "energies": energies,
        "counts": counts.tolist(),
        "isotope": "Cs-137 (662 keV)",
        "detector": "AlphaHound CsI(Tl)",
        "acquisition_time_s": 300,
        "source_type": "auto"
    }
    
    try:
        print("Sending request to backend...")
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print("\n--- API Response Keys ---")
            keys = list(data.keys())
            print(f"Total keys: {len(keys)}")
            print(f"Keys: {keys}")
            
            print("\n--- Advanced Metrics ---")
            print(f"fit_success in response: {'fit_success' in data}")
            print(f"resolution in response: {'resolution' in data}")
            print(f"fwhm in response: {'fwhm' in data}")
            print(f"Fit Success value: {data.get('fit_success')}")
            print(f"Resolution value: {data.get('resolution')}")
            print(f"FWHM value: {data.get('fwhm')}")
            print(f"Uncertainty value: {data.get('uncertainty_sigma')}")
            
            if 'fit_success' in data and 'resolution' in data and 'fwhm' in data:
                print("\n✅ SUCCESS: All advanced metrics fields are present!")
            else:
                print("\n❌ FAILURE: Some advanced metrics fields are missing.")
        else:
            print(f"Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    verify_api()
