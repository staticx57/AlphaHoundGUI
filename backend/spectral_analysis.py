
import numpy as np
import scipy.optimize
from scipy.signal import find_peaks

def fit_gaussian(energies, counts, peak_centers, window_width=10):
    """
    Fit Gaussian profiles to peaks in the spectrum.
    
    Args:
        energies (array-like): Energy array
        counts (array-like): Counts array
        peak_centers (list): List of estimated peak energies
        window_width (float): Energy window (+/-) to fit around each peak
        
    Returns:
        list: List of dictionaries containing fit results for each peak
    """
    fit_results = []
    
    energies = np.array(energies)
    counts = np.array(counts)
    
    for center in peak_centers:
        # Define window around peak
        mask = (energies >= center - window_width) & (energies <= center + window_width)
        x_window = energies[mask]
        y_window = counts[mask]
        
        if len(x_window) < 5:
            continue
            
        # Initial guesses: amplitude, mean, stddev, background offset
        p0 = [np.max(y_window), center, 1.0, np.min(y_window)]
        
        try:
            # Gaussian function + constant background
            def gaussian_bg(x, a, mu, sigma, c):
                return a * np.exp(-(x - mu)**2 / (2 * sigma**2)) + c
            
            # Bounds: [min_amp, min_mu, min_sigma, min_bg], [max_amp, max_mu, max_sigma, max_bg]
            # Enforce positive amplitude, center within window, width positive but not huge, background positive
            bounds = (
                [0, center - window_width, 0.01, 0],
                [np.inf, center + window_width, window_width * 2, np.inf]
            )
            
            popt, pcov = scipy.optimize.curve_fit(gaussian_bg, x_window, y_window, p0=p0, bounds=bounds)
            
            amplitude, mean, sigma, bg = popt
            fwhm = 2.355 * sigma
            net_area = amplitude * sigma * np.sqrt(2 * np.pi)
            
            fit_results.append({
                "energy": float(mean),
                "centroid_channel": float(np.interp(mean, energies, np.arange(len(energies)))),
                "fwhm": float(abs(fwhm)),
                "amplitude": float(amplitude),
                "net_area": float(net_area),
                "background_level": float(bg),
                "chi_squared": float(np.sum((y_window - gaussian_bg(x_window, *popt))**2) / (len(x_window) - 4))
            })
        except Exception as e:
            # Fit failed, skip this peak
            print(f"Fit failed for peak at {center}: {e}")
            continue
            
    return fit_results

def calculate_resolution(peaks):
    """
    Calculate energy resolution (R = FWHM / Energy) for a list of fitted peaks.
    """
    results = []
    for p in peaks:
        if p['energy'] > 0:
            r = (p['fwhm'] / p['energy']) * 100 # Percent
            results.append({
                "energy": p['energy'],
                "resolution_percent": r
            })
    return results

def calibrate_energy(channels, known_energies, known_channels):
    """
    Perform linear energy calibration.
    E = A * channel + B
    """
    if len(known_energies) < 2:
        return None
        
    slope, intercept = np.polyfit(known_channels, known_energies, 1)
    
    calibrated_energies = slope * np.array(channels) + intercept
    return calibrated_energies.tolist(), {"slope": slope, "intercept": intercept}
