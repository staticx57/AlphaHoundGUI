
import numpy as np
import sys

# Mock becquerel if not installed to avoid script crashing in this environment check
# (But user said they installed it globally. I should rely on that or my venv if I reinstall it)
# I'll assume I need to reinstall it in venv or just check the code structure if I can't run it.
# Actually, I removed it from requirements.txt, so I need to put it back if I want to use it.
# For this test, I'll try to import and if it works, great.

try:
    import becquerel as bq
    
    # Create dummy data
    counts = np.array([10, 20, 30, 40, 50])
    energies = np.array([100, 200, 300, 400, 500])
    
    # Try to instantiate Spectrum
    try:
        spec = bq.Spectrum(counts=counts, bin_edges=energies, live_time=100)
        print("Success: Instantiated from counts/bin_edges")
        print(spec)
    except Exception as e1:
        print(f"Failed init 1: {e1}")
        
    try:
        spec = bq.Spectrum(counts=counts, energies=energies, live_time=100) # Guessing signature
        print("Success: Instantiated from counts/energies")
        print(spec)
    except Exception as e2:
        print(f"Failed init 2: {e2}")

except ImportError:
    print("Becquerel not installed in this environment")
