
import numpy as np
from spectroscopy.gauss_area import channel_width_kev
import scipy.optimize

import logging
logger = logging.getLogger(__name__)

FIT_HALF_WINDOW_FWHM = 1.5   # half-width of the fitting window, in measured FWHMs of the peak
MIN_SIDE_CHANNELS = 3        # channels the window holds on each side of the centre at least


def _measured_fwhm(energies, net, gross, center, search_kev):
    """
    (index of the peak's maximum, its FWHM in keV, the largest half-window that stays clear of neighbouring peaks or None) from the
    background-subtracted spectrum, or None when no peak can be measured there. Measured from the data, so it holds for any detector: a
    CsI line 60 keV wide and a germanium line 1.6 keV wide alike.
    """
    smooth = np.convolve(net, np.ones(3) / 3.0, mode="same")
    noise = np.sqrt(np.maximum(np.convolve(gross, np.ones(3) / 3.0, mode="same"), 1.0) / 3.0)   # 1 sigma of the 3-channel mean
    near = np.where(np.abs(energies - center) <= search_kev)[0]
    if near.size == 0:
        near = np.array([int(np.argmin(np.abs(energies - center)))])
    k = int(near[np.argmax(smooth[near])])
    if near.size >= 3 and k in (near[0], near[-1]):
        k = int(np.argmin(np.abs(energies - center)))   # the highest point in reach is a neighbour's flank: measure the shoulder itself
    half = smooth[k] / 2.0
    if half <= 0:
        return None

    def walk(step):
        """
        (distance in keV, reached half maximum) on one side. Walking stops at the half-maximum crossing, or at a valley: a rise of more than
        3 sigma above the lowest point so far, once the curve has fallen below 90 % of the maximum: the flank of a neighbouring peak (counting
        noise alone, also at the top of the peak, does not stop it). At a valley the
        distance is to its lowest point, so a peak sitting between others is not measured as one wide peak.
        """
        i, low_i = k, k
        while 0 < i + step < len(smooth) and smooth[i] > half and abs(i - k) < 200:
            i += step
            if smooth[i] < smooth[low_i]:
                low_i = i
            if smooth[low_i] < 0.9 * smooth[k] and smooth[i] - smooth[low_i] > 3.0 * noise[i]:
                return abs(energies[low_i] - energies[k]), False
        if smooth[i] > half:
            return None
        crossing = float(np.interp(half, [smooth[i], smooth[i - step]], [energies[i], energies[i - step]]))
        return abs(crossing - energies[k]), True

    sides = [w for w in (walk(-1), walk(1)) if w and w[0] > 0]
    crossed = [d for d, reached in sides if reached]
    valleys = [d for d, reached in sides if not reached]
    clear = min(valleys) if valleys else None
    if len(crossed) == 2:
        # a peak is symmetric: a flank much longer than the other runs into something else (continuum left in the net, a neighbour)
        fwhm = sum(crossed) if max(crossed) <= 1.5 * min(crossed) else 2.0 * min(crossed)
    elif crossed:
        fwhm = 2.0 * crossed[0]
    elif len(valleys) == 2:
        fwhm = sum(valleys) / 2.8      # between two neighbours the valley lies about 1.4 FWHM from each centre
    else:
        return None
    if clear is not None:
        fwhm = min(fwhm, clear)        # a neighbour's valley closer than one FWHM means the peak is narrower than the walk said
    return k, fwhm, clear


def fit_gaussian(energies, counts, peak_centers, window_width=10):
    """
    Fit Gaussian profiles to peaks in the spectrum.

    The window is set from each peak's own width (+-1.5 FWHM, measured at half maximum above the SNIP continuum), never narrower than
    +-window_width keV or 3 channels a side. A fixed +-10 keV window held less than one FWHM of a scintillator peak (25-130 keV), so every
    fit returned a sliver of the peak top: FWHMs of 0.1-0.7 % and areas 10-100 times too small, and on the AlphaHound's wide channels the
    peak was dropped altogether.

    Args:
        energies (array-like): Energy array
        counts (array-like): Counts array
        peak_centers (list): List of estimated peak energies
        window_width (float): Smallest half-width (keV) of the window fitted around each peak

    Returns:
        list: List of dictionaries containing fit results for each peak
    """
    fit_results = []

    energies = np.array(energies, dtype=float)
    counts = np.array(counts, dtype=float)
    net = counts - snip_background(counts, iterations=24)

    def gaussian_bg(x, a, mu, sigma, c, slope):
        """Gaussian on a straight-line background (the continuum under a wide peak is not flat)."""
        return a * np.exp(-(x - mu)**2 / (2 * sigma**2)) + c + slope * (x - mu)

    for center in peak_centers:
        nearest = int(np.argmin(np.abs(energies - center)))
        local_width = float(np.median(np.diff(energies[max(nearest - 2, 0):nearest + 3]))) if len(energies) > 1 else 1.0
        measured = _measured_fwhm(energies, net, counts, center, max(window_width, 2 * local_width))
        if measured:
            k, fwhm_guess, clear = measured
            peak_energy = float(energies[k])
            wanted = FIT_HALF_WINDOW_FWHM * fwhm_guess if clear is None else min(FIT_HALF_WINDOW_FWHM * fwhm_guess, clear)
            half_window = max(window_width, wanted, MIN_SIDE_CHANNELS * local_width)
        else:
            peak_energy = float(center)
            fwhm_guess = window_width
            half_window = max(window_width, MIN_SIDE_CHANNELS * local_width)
        sigma_guess = fwhm_guess / 2.355

        # Define window around peak
        mask = (energies >= peak_energy - half_window) & (energies <= peak_energy + half_window)
        x_window = energies[mask]
        y_window = counts[mask]

        if len(x_window) < 6:
            continue

        # Initial guesses: amplitude, mean, stddev, background level and slope
        edge = float(min(y_window[0], y_window[-1]))
        p0 = [max(float(np.max(y_window)) - edge, 1.0), peak_energy, sigma_guess, max(edge, 0.0), 0.0]

        try:
            # Positive amplitude, centre within half a FWHM of the maximum (not free to slide onto a neighbour), width within a factor 4
            # of the measured one
            shift = max(0.5 * fwhm_guess, local_width)
            bounds = (
                [0, peak_energy - shift, max(sigma_guess / 4.0, 0.01), -np.inf, -np.inf],
                [np.inf, peak_energy + shift, sigma_guess * 4.0, np.inf, np.inf]
            )
            p0[2] = min(max(p0[2], bounds[0][2]), bounds[1][2])

            popt, pcov = scipy.optimize.curve_fit(gaussian_bg, x_window, y_window, p0=p0, bounds=bounds,
                                                  sigma=np.sqrt(np.maximum(y_window, 1.0)), absolute_sigma=True, maxfev=10000)

            amplitude, mean, sigma, bg, _slope = popt
            # A result held at a limit (no peak left, centre or width at the edge of what was allowed) did not find this peak: a failed fit
            pinned = [abs(value - limit) <= 0.01 * (bounds[1][i] - bounds[0][i])
                      for value, limit, i in ((mean, bounds[0][1], 1), (mean, bounds[1][1], 1), (sigma, bounds[0][2], 2), (sigma, bounds[1][2], 2))]
            if amplitude <= 0 or any(pinned):
                logger.debug(f"Fit for the peak at {center} ended at a limit; skipped")
                continue
            fwhm = 2.355 * sigma
            net_area = amplitude * sigma * np.sqrt(2 * np.pi) / channel_width_kev(x_window)    # counts, not counts * keV per channel

            # Extract uncertainties from covariance matrix diagonal
            perr = np.sqrt(np.diag(pcov)) if pcov is not None else [0, 0, 0, 0, 0]
            amplitude_unc, mean_unc, sigma_unc, bg_unc = perr[:4]
            if not amplitude > 3.0 * amplitude_unc:
                logger.debug(f"Fit for the peak at {center} is not significant (amplitude {amplitude:.1f} +- {amplitude_unc:.1f}); skipped")
                continue
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
                "chi_squared": float(np.sum((y_window - gaussian_bg(x_window, *popt))**2) / (len(x_window) - 5))
            })
        except Exception as e:
            # Fit failed, skip this peak
            logger.warning(f"Fit failed for peak at {center}: {e}")
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

