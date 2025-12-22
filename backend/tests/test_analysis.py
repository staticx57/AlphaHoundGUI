
import pytest
import numpy as np
from backend.spectral_analysis import fit_gaussian, calibrate_energy, subtract_background, calculate_resolution

def test_subtract_background():
    source = [100, 200, 300]
    bg = [10, 20, 30]
    
    # Normal subtraction
    result = subtract_background(source, bg, scaling_factor=1.0)
    assert result['net_counts'] == [90, 180, 270]
    
    # With scaling
    result_scaled = subtract_background(source, bg, scaling_factor=2.0)
    assert result_scaled['net_counts'] == [80, 160, 240]
    
    # Clamping
    high_bg = [200, 200, 200]
    result_clamp = subtract_background(source, high_bg, scaling_factor=1.0)
    assert result_clamp['net_counts'] == [0, 0, 100]

def test_calibrate_energy():
    channels = [10, 20, 30]
    known_energies = [30, 50, 70] # E = 2*Ch + 10
    
    calibrated, params = calibrate_energy(channels, known_energies, channels)
    
    assert params['slope'] == pytest.approx(2.0, abs=0.01)
    assert params['intercept'] == pytest.approx(10.0, abs=0.01)
    assert calibrated[0] == pytest.approx(30.0, abs=0.01)

def test_fit_gaussian(sample_spectrum):
    energies, counts = sample_spectrum
    peak_center = 100.0 # 50 * 2.0
    
    # Pass estimated center
    results = fit_gaussian(energies, counts, [peak_center], window_width=20)
    
    assert len(results) == 1
    fit = results[0]
    assert fit['energy'] == pytest.approx(100.0, abs=2.0) # Should be close
    assert fit['amplitude'] > 50
    assert fit['fwhm'] > 0

def test_calculate_resolution():
    peaks = [
        {'energy': 662.0, 'fwhm': 46.0}, # ~7%
        {'energy': 0.0, 'fwhm': 10.0}     # Should be ignored or handled
    ]
    
    res = calculate_resolution(peaks)
    assert len(res) == 1
    assert res[0]['resolution_percent'] == pytest.approx(6.95, abs=0.1)
