import numpy as np
from fitting_engine import AdvancedFittingEngine

def test_multiplet_fit():
    print("Testing AdvancedFittingEngine.fit_multiplet...")
    
    # 1. Synthesize Multiplet Data (Two peaks close together)
    energies = np.linspace(600, 750, 151)
    
    # Peak 1
    A1, c1, s1 = 1000.0, 662.0, 10.0
    y1 = A1 * np.exp(-((energies - c1)**2) / (2 * s1**2))
    
    # Peak 2 (Overlapping - 28 keV away ~ 2.8 sigma)
    A2, c2, s2 = 800.0, 690.0, 12.0
    y2 = A2 * np.exp(-((energies - c2)**2) / (2 * s2**2))
    
    # Background
    bg_slope, bg_intercept = -0.5, 1000.0
    y_bg = bg_slope * energies + bg_intercept
    
    # Total
    counts = y1 + y2 + y_bg
    # Add noise
    np.random.seed(99)
    noise = np.random.normal(0, np.sqrt(counts), len(counts))
    counts += noise
    
    # 2. Perform Multiplet Fit
    engine = AdvancedFittingEngine()
    centroids_guess = [660.0, 695.0] # Slightly off guesses
    
    results, r2 = engine.fit_multiplet(energies, counts, centroids_guess, roi_width_kev=50.0)
    
    if results is None:
        print("FAIL: Multiplet Fit returned None")
        return

    print(f"Fit Successful! R2={r2:.4f}")
    assert len(results) == 2, "Should return 2 peak results"
    
    # Check Peak 1
    res1 = results[0]
    print(f"Peak 1: Centroid={res1.centroid:.2f} (True={c1}), Amp={res1.amplitude:.1f} (True={A1})")
    assert abs(res1.centroid - c1) < 2.0, "Peak 1 Centroid error"
    assert abs(res1.amplitude - A1) < 100.0, "Peak 1 Amp error"
    
    # Check Peak 2
    res2 = results[1]
    print(f"Peak 2: Centroid={res2.centroid:.2f} (True={c2}), Amp={res2.amplitude:.1f} (True={A2})")
    assert abs(res2.centroid - c2) < 2.0, "Peak 2 Centroid error"
    assert abs(res2.amplitude - A2) < 100.0, "Peak 2 Amp error"

    print("PASS: Multiplet deconvolution successful.")

if __name__ == "__main__":
    test_multiplet_fit()
