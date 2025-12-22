
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
            
            # Extract uncertainties from covariance matrix diagonal
            perr = np.sqrt(np.diag(pcov)) if pcov is not None else [0, 0, 0, 0]
            amplitude_unc, mean_unc, sigma_unc, bg_unc = perr
            fwhm_unc = 2.355 * sigma_unc
            # Propagate uncertainty for net_area = A * sigma * sqrt(2*pi)
            # Using quadrature: dA^2/A^2 + dS^2/S^2
            if amplitude > 0 and sigma > 0:
                net_area_unc = net_area * np.sqrt((amplitude_unc/amplitude)**2 + (sigma_unc/sigma)**2)
            else:
                net_area_unc = 0.0
            
            fit_results.append({
                "energy": float(mean),
                "energy_unc": float(mean_unc),
                "centroid_channel": float(np.interp(mean, energies, np.arange(len(energies)))),
                "fwhm": float(abs(fwhm)),
                "fwhm_unc": float(fwhm_unc),
                "amplitude": float(amplitude),
                "amplitude_unc": float(amplitude_unc),
                "net_area": float(net_area),
                "net_area_unc": float(net_area_unc),
                "background_level": float(bg),
                "background_unc": float(bg_unc),
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

def subtract_background(source_counts, background_counts=None, scaling_factor=1.0, use_snip=False, snip_iterations=24):
    """
    Subtract background spectrum from source spectrum.
    
    Args:
        source_counts (list): Counts from the sample source
        background_counts (list): Counts from the background noise (optional if use_snip=True)
        scaling_factor (float): Multiplier for background (e.g. time normalization)
        use_snip (bool): If True, estimate background using SNIP algorithm
        snip_iterations (int): Number of SNIP iterations (8-24 typical)
        
    Returns:
        dict: Contains net_counts, background, and metadata
    """
    src = np.array(source_counts, dtype=float)
    
    if use_snip or background_counts is None:
        # Use SNIP algorithm to estimate background
        bg = snip_background(src, iterations=snip_iterations)
    else:
        bg = np.array(background_counts, dtype=float) * scaling_factor
        # Ensure dimensions match
        length = min(len(src), len(bg))
        src = src[:length]
        bg = bg[:length]
    
    # Subtract
    net_counts = src - bg
    
    # Clamp negative values to 0
    net_counts[net_counts < 0] = 0
    
    return {
        'net_counts': net_counts.tolist(),
        'background': bg.tolist() if hasattr(bg, 'tolist') else list(bg),
        'gross_counts': src.tolist(),
        'algorithm': 'SNIP' if use_snip else 'subtraction',
        'iterations': snip_iterations if use_snip else None
    }


def snip_background(counts, iterations=24):
    """
    SNIP (Sensitive Nonlinear Iterative Peak) algorithm for background estimation.
    
    This is the industry-standard algorithm for gamma spectrum baseline removal.
    It uses iterative clipping in LLS (Log-Log-Square-root) space to estimate
    the slowly-varying Compton continuum while preserving peak shapes.
    
    Args:
        counts: Array of spectrum counts (1024 channels typical)
        iterations: Number of SNIP iterations (8-24 typical, higher = smoother)
    
    Returns:
        background: Estimated background array (same length as counts)
    
    Reference:
        C.G. Ryan et al., "SNIP, a statistics-sensitive background treatment
        for the quantitative analysis of PIXE spectra in geoscience applications"
        Nuclear Instruments and Methods B, 34 (1988) 396-402
    """
    counts = np.array(counts, dtype=float)
    n = len(counts)
    
    if n == 0:
        return np.array([])
    
    # LLS transform: v = log(log(sqrt(y+1)+1)+1)
    # This compresses the dynamic range and makes the algorithm more robust
    v = np.log(np.log(np.sqrt(counts + 1) + 1) + 1)
    
    # Make a working copy
    working = v.copy()
    
    # Iterative clipping from large window to small
    for p in range(iterations, 0, -1):
        for i in range(p, n - p):
            # Compare current point to average of neighbors at distance p
            avg = 0.5 * (working[i - p] + working[i + p])
            if working[i] > avg:
                working[i] = avg
    
    # Inverse LLS transform: y = (exp(exp(v)-1)-1)^2 - 1
    background = (np.exp(np.exp(working) - 1) - 1) ** 2 - 1
    
    # Ensure non-negative background
    background = np.maximum(background, 0)
    
    return background

