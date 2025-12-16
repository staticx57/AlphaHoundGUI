
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
            print(json.dumps(list(data.keys()), indent=2))
            
            print("\n--- Advanced Metrics ---")
            print(f"Fit Success: {data.get('fit_success')}")
            print(f"Resolution: {data.get('resolution')}")
            print(f"FWHM: {data.get('fwhm')}")
            print(f"Uncertainty: {data.get('uncertainty_sigma')}")
            
            if data.get('fit_success') and data.get('resolution'):
                print("\nSUCCESS: Advanced metrics are present and populated.")
            else:
                print("\nFAILURE: Advanced metrics missing or fit failed.")
        else:
            print(f"Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    verify_api()
