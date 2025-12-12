"""
Direct test of ML module with spectrum data
"""
import numpy as np
import sys
sys.path.insert(0, '.')

from ml_analysis import get_ml_identifier

# Create test spectrum - same as test_ml_endpoint.py
counts = np.zeros(1024)
counts += np.random.poisson(8, 1024)
peak_center = 662
peak_width = 5
peak_height = 250
x = np.arange(1024)
counts += peak_height * np.exp(-0.5 * ((x - peak_center) / peak_width) ** 2)
counts_list = [int(c) for c in counts]

print(f"Test spectrum: {len(counts_list)} channels")
print(f"Peak at channel {peak_center}")
print(f"First 10 counts: {counts_list[:10]}")

# Get ML identifier
ml = get_ml_identifier()
if ml is None:
    print("ML not available!")
else:
    print("\nCalling ml.identify()...")
    try:
        results = ml.identify(counts_list, top_k=5)
        print(f"\nResults: {results}")
        if results:
            print("\nPredictions:")
            for r in results:
                print(f"  {r['isotope']}: {r['confidence']:.2f}% ({r['method']})")
        else:
            print("No predictions returned")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
