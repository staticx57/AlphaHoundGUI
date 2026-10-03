import numpy as np
import math
from fitting_engine import AdvancedFittingEngine

def test_single_peak_fit():
    print("Testing AdvancedFittingEngine.fit_single_peak...")
    
    # 1. Synthesize Data
    # True Parameters
    A_true = 1000.0
    mu_true = 662.0
    sigma_true = 15.0 # FWHM ~35 keV
    bg_slope = -0.5
    bg_intercept = 1000.0 # Adjusted to ensure positive counts (1000 - 0.5*720 > 0)
    
    energies = np.linspace(600, 720, 121) # 600 to 720 keV, 1 keV steps
    
    # Generate Model
    # Gaussian
    y_gauss = A_true * np.exp(-((energies - mu_true)**2) / (2 * sigma_true**2))
    # Background
    y_bg = bg_slope * energies + bg_intercept
    # Total + Noise
    np.random.seed(42) # Deterministic noise
    noise = np.random.normal(0, np.sqrt(y_gauss + y_bg), len(energies))
    counts = y_gauss + y_bg + noise
    
    # 2. Perform Fit
    engine = AdvancedFittingEngine()
    result = engine.fit_single_peak(energies, counts, centroid_guess=660.0, roi_width_kev=50.0)
    
    if result is None:
        print("FAIL: Fit returned None")
        return

    print("Fit Successful!")
    print(f"Centroid: True={mu_true}, Fit={result.centroid:.2f}")
    print(f"Sigma:    True={sigma_true}, Fit={result.sigma:.2f}")
    print(f"Net Area: Approx={A_true * sigma_true * np.sqrt(2*np.pi):.1f}, Fit={result.net_area:.1f}")
    print(f"Resolution: {result.resolution:.2f}%")
    print(f"R-Squared: {result.r_squared:.4f}")
    print(f"Uncertainty: ±{result.uncertainty:.2f} (Net Area)")
    
    # 3. Assertions
    assert abs(result.centroid - mu_true) < 1.0, "Centroid error too high"
    assert abs(result.sigma - sigma_true) < 1.0, "Sigma error too high"
    assert result.resolution > 0, "Resolution should be positive"
    assert result.r_squared > 0.95, "R-Squared too low"
    assert result.uncertainty > 0, "Uncertainty should be calculated"
    
    print("PASS: Gaussian + Linear Background recovered correctly.")

if __name__ == "__main__":
    test_single_peak_fit()
