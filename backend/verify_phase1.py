
import requests
import json
import os

BASE_URL = "http://127.0.0.1:8080"
TEST_FILE = "../test.n42"

def verify():
    print("1. Testing Upload...")
    if not os.path.exists(TEST_FILE):
        print(f"Error: {TEST_FILE} not found")
        return

    with open(TEST_FILE, 'rb') as f:
        files = {'file': (os.path.basename(TEST_FILE), f)}
        try:
            res = requests.post(f"{BASE_URL}/upload", files=files)
            if res.status_code != 200:
                print(f"Upload failed: {res.text}")
                return
            
            data = res.json()
            print(f"Upload success! Found {len(data['peaks'])} peaks.")
            
            print("2. Testing Peak Fitting...")
            payload = {
                "energies": data["energies"],
                "counts": data["counts"],
                "peaks": data["peaks"]
            }
            
            res_fit = requests.post(f"{BASE_URL}/analyze/fit-peaks", json=payload)
            if res_fit.status_code != 200:
                print(f"Fitting failed: {res_fit.text}")
                return
                
            fits = res_fit.json().get("fits", [])
            print(f"Fitting success! Fitted {len(fits)} peaks.")
            if fits:
                print("Sample Fit:", fits[0])
                
        except Exception as e:
            print(f"Request error: {e}")

if __name__ == "__main__":
    verify()
