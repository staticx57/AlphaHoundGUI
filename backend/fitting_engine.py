import numpy as np
from scipy.optimize import curve_fit
from scipy.special import voigt_profile
from dataclasses import dataclass
from typing import Tuple, List, Optional, Dict

@dataclass
class FitResult:
    amplitude: float
    centroid: float
    sigma: float
    fwhm: float
    resolution: float  # FWHM / Centroid * 100 (%)
    net_area: float
    background_area: float
    baseline_coeffs: List[float]
    r_squared: float
    uncertainty: float = 0.0 # Placeholder for Phase 3
    gamma: Optional[float] = None  # Lorentzian width for Voigt fits
    peak_model: str = "gaussian"  # "gaussian" or "voigt"

class AdvancedFittingEngine:
    """
    Advanced Fitting Engine for Gamma Spectroscopy.
    Integrates logic from PyGammaSpec (Robust Single-Fit) and GammaSpy (Composite Multiplet Fit).
    
    Phase 5 Additions:
    - Voigt peak model (Gaussian × Lorentzian convolution)
    - Quadratic and exponential background models
    """

    @staticmethod
    def gaussian(x, amplitude, centroid, sigma):
        """Standard Gaussian function."""
        return amplitude * np.exp(-((x - centroid)**2) / (2 * sigma**2))

    @staticmethod
    def voigt(x, amplitude, centroid, sigma, gamma):
        """
        Voigt profile: convolution of Gaussian and Lorentzian.
        Better for low-energy peaks with Lorentzian tails.
        
        Args:
            sigma: Gaussian width (thermal broadening)
            gamma: Lorentzian width (natural line width)
        """
        return amplitude * voigt_profile(x - centroid, sigma, gamma)

    @staticmethod
    def polynomial(x, *coeffs):
        """Polynomial baseline function (default order 1 = linear)."""
        return sum(c * x**i for i, c in enumerate(coeffs))

    # === Linear Baseline Models ===
    @staticmethod
    def combined_model_linear(x, amplitude, centroid, sigma, b0, b1):
        """Gaussian + Linear Baseline (b1*x + b0)."""
        return amplitude * np.exp(-((x - centroid)**2) / (2 * sigma**2)) + (b1 * x + b0)

    @staticmethod
    def combined_model_flat(x, amplitude, centroid, sigma, b0):
        """Gaussian + Flat Baseline (b0)."""
        return amplitude * np.exp(-((x - centroid)**2) / (2 * sigma**2)) + b0

    # === Quadratic Baseline Model ===
    @staticmethod
    def combined_model_quadratic(x, amplitude, centroid, sigma, b0, b1, b2):
        """Gaussian + Quadratic Baseline (b0 + b1*x + b2*x²)."""
        gaussian = amplitude * np.exp(-((x - centroid)**2) / (2 * sigma**2))
        baseline = b0 + b1 * x + b2 * x**2
        return gaussian + baseline

    # === Exponential Baseline Model ===
    @staticmethod
    def combined_model_exponential(x, amplitude, centroid, sigma, b0, b1):
        """Gaussian + Exponential Baseline (b0 * exp(-b1*x)). Good for Compton continuum."""
        gaussian = amplitude * np.exp(-((x - centroid)**2) / (2 * sigma**2))
        baseline = b0 * np.exp(-b1 * x)
        return gaussian + baseline

    # === Voigt + Linear Baseline Model ===
    @staticmethod
    def voigt_model_linear(x, amplitude, centroid, sigma, gamma, b0, b1):
        """Voigt profile + Linear Baseline."""
        peak = amplitude * voigt_profile(x - centroid, sigma, gamma)
        baseline = b0 + b1 * x
        return peak + baseline

    # === Double Gaussian Model (GammaSpy) ===
    @staticmethod
    def double_gaussian_linear(x, amp1, cen1, sig1, amp2, cen2, sig2, b0, b1):
        """Double Gaussian peaks + Linear Baseline. For overlapping doublets."""
        g1 = amp1 * np.exp(-((x - cen1)**2) / (2 * sig1**2))
        g2 = amp2 * np.exp(-((x - cen2)**2) / (2 * sig2**2))
        baseline = b0 + b1 * x
        return g1 + g2 + baseline

    # === Auto ROI Detection (GammaSpy) ===
    @staticmethod
    def auto_find_roi(energies: np.ndarray, counts: np.ndarray, 
                      centroid: float, threshold: float = 0.05,
                      window_length: int = 7, tail_buffer_kev: float = 4.0):
        """
        Automatically find ROI boundaries using 2nd derivative analysis.
        Uses Savitzky-Golay filter to smooth data and find inflection points.
        
        Args:
            energies: Energy array
            counts: Counts array  
            centroid: Initial peak centroid guess (keV)
            threshold: 2nd derivative threshold (fraction of max)
            window_length: Savitzky-Golay window size (must be odd)
            tail_buffer_kev: Extra padding beyond detected boundaries
            
        Returns:
            (lower_bound, upper_bound) in keV
        """
        from scipy.signal import savgol_filter
        
        # Compute 2nd derivative
        if len(counts) < window_length:
            # Fallback to fixed ROI
            return (centroid - 15.0, centroid + 15.0)
            
        y_2div = savgol_filter(counts, window_length=window_length, polyorder=3, deriv=2)
        
        # Threshold based on peak max
        max_2div = np.max(np.abs(y_2div))
        abs_threshold = threshold * max_2div
        
        # Find index closest to centroid
        cen_idx = np.argmin(np.abs(energies - centroid))
        
        # Walk left from centroid until 2nd derivative exceeds threshold
        lower_idx = 0
        for i in range(cen_idx, -1, -1):
            if y_2div[i] > abs_threshold:
                lower_idx = i
                break
        
        # Walk right from centroid
        upper_idx = len(energies) - 1
        for i in range(cen_idx, len(energies)):
            if y_2div[i] > abs_threshold:
                upper_idx = i
                break
        
        # Add buffer
        lower_bound = max(0, energies[lower_idx] - tail_buffer_kev)
        upper_bound = min(energies[-1], energies[upper_idx] + tail_buffer_kev)
        
        return (lower_bound, upper_bound)

    def fit_single_peak_auto_roi(self, 
                                  energies: np.ndarray, 
                                  counts: np.ndarray, 
                                  centroid_guess: float,
                                  baseline_order: int = 1) -> Optional[FitResult]:
        """
        Fit single peak with automatically detected ROI boundaries.
        """
        lower, upper = self.auto_find_roi(energies, counts, centroid_guess)
        roi_width = (upper - lower) / 2
        return self.fit_single_peak(energies, counts, centroid_guess, 
                                     roi_width_kev=roi_width, baseline_order=baseline_order)

    def fit_doublet(self,
                    energies: np.ndarray,
                    counts: np.ndarray,
                    centroid1: float,
                    centroid2: float,
                    roi_width_kev: float = 30.0,
                    use_basin_hopping: bool = False) -> Optional[Tuple[FitResult, FitResult]]:
        """
        Fit two overlapping Gaussian peaks (doublet) simultaneously.
        Useful for e.g., U-235 (186 keV) + Ra-226 (186 keV) interference.
        
        Args:
            centroid1, centroid2: Initial centroids for both peaks
            use_basin_hopping: Use global optimization (slower, more robust)
        """
        try:
            # Select ROI
            cen_mid = (centroid1 + centroid2) / 2
            mask = (energies >= cen_mid - roi_width_kev) & (energies <= cen_mid + roi_width_kev)
            x_roi = energies[mask]
            y_roi = counts[mask]
            
            if len(x_roi) < 10:
                return None
            
            # Initial guesses
            amp_guess = np.max(y_roi) / 2
            sig_guess = 3.0
            b0_guess = np.min(y_roi)
            b1_guess = 0.0
            
            p0 = [amp_guess, centroid1, sig_guess, 
                  amp_guess, centroid2, sig_guess,
                  b0_guess, b1_guess]
            
            bounds = ([0, x_roi[0], 0.5, 0, x_roi[0], 0.5, -np.inf, -np.inf],
                      [np.inf, x_roi[-1], 20, np.inf, x_roi[-1], 20, np.inf, np.inf])
            
            if use_basin_hopping:
                from scipy.optimize import basinhopping
                
                def objective(params):
                    return np.sum((self.double_gaussian_linear(x_roi, *params) - y_roi)**2)
                
                result = basinhopping(objective, p0, minimizer_kwargs={"method": "L-BFGS-B"})
                popt = result.x
                # Estimate covariance from Hessian (if available)
                pcov = np.eye(len(popt))  # Placeholder
            else:
                popt, pcov = curve_fit(self.double_gaussian_linear, x_roi, y_roi, 
                                        p0=p0, bounds=bounds, maxfev=5000)
            
            # Extract results for each peak
            amp1, cen1, sig1, amp2, cen2, sig2, b0, b1 = popt
            
            sqrt2pi = np.sqrt(2 * np.pi)
            
            # Peak 1
            fwhm1 = 2.355 * sig1
            net_area1 = amp1 * sig1 * sqrt2pi
            
            # Peak 2
            fwhm2 = 2.355 * sig2
            net_area2 = amp2 * sig2 * sqrt2pi
            
            # Background
            bg_curve = b0 + b1 * x_roi
            bg_area = np.trapz(bg_curve, x_roi)
            
            # R-squared
            fit_curve = self.double_gaussian_linear(x_roi, *popt)
            residuals = y_roi - fit_curve
            ss_res = np.sum(residuals**2)
            ss_tot = np.sum((y_roi - np.mean(y_roi))**2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
            
            result1 = FitResult(
                amplitude=amp1, centroid=cen1, sigma=sig1,
                fwhm=fwhm1, resolution=(fwhm1/cen1)*100 if cen1 > 0 else 0,
                net_area=net_area1, background_area=bg_area/2,
                baseline_coeffs=[b0, b1], r_squared=r2,
                peak_model="double_gaussian"
            )
            
            result2 = FitResult(
                amplitude=amp2, centroid=cen2, sigma=sig2,
                fwhm=fwhm2, resolution=(fwhm2/cen2)*100 if cen2 > 0 else 0,
                net_area=net_area2, background_area=bg_area/2,
                baseline_coeffs=[b0, b1], r_squared=r2,
                peak_model="double_gaussian"
            )
            
            return (result1, result2)
            
        except Exception as e:
            print(f"[fit_doublet] Error: {e}")
            return None

    def fit_single_peak(self, 
                        energies: np.ndarray, 
                        counts: np.ndarray, 
                        centroid_guess: float, 
                        roi_width_kev: float = 20.0,
                        baseline_order: int = 1) -> Optional[FitResult]:
        """
        Performs a robust single-peak fit over a specific ROI.
        """
        # 1. Select ROI
        mask = (energies >= centroid_guess - roi_width_kev) & (energies <= centroid_guess + roi_width_kev)
        x_roi = energies[mask]
        y_roi = counts[mask]

        if len(x_roi) < 5:
            return None # Not enough data points

        # 2. Initial Guesses
        max_idx = np.argmax(y_roi)
        amp_guess = y_roi[max_idx] - np.min(y_roi)
        sigma_guess = roi_width_kev / 6.0
        
        # Baseline guess
        if len(x_roi) > 1:
            bg_slope = (y_roi[-1] - y_roi[0]) / (x_roi[-1] - x_roi[0])
            bg_intercept = y_roi[0] - bg_slope * x_roi[0]
        else:
            bg_slope = 0
            bg_intercept = y_roi[0]
        
        try:
            if baseline_order == 1:
                p0 = [amp_guess, centroid_guess, sigma_guess, bg_intercept, bg_slope]
                popt, pcov = curve_fit(self.combined_model_linear, x_roi, y_roi, p0=p0, maxfev=10000)
                
                amp_fit, cen_fit, sigma_fit = popt[0], popt[1], abs(popt[2])
                bg_coeffs = [popt[3], popt[4]] # [intercept, slope]
                
                # Reconstruct baseline for area calc
                bg_curve = popt[4] * x_roi + popt[3]
                fit_curve = self.combined_model_linear(x_roi, *popt)
                
            else:
                p0 = [amp_guess, centroid_guess, sigma_guess, np.min(y_roi)]
                popt, pcov = curve_fit(self.combined_model_flat, x_roi, y_roi, p0=p0, maxfev=10000)
                
                amp_fit, cen_fit, sigma_fit = popt[0], popt[1], abs(popt[2])
                bg_coeffs = [popt[3]]
                
                bg_curve = np.full_like(x_roi, popt[3])
                fit_curve = self.combined_model_flat(x_roi, *popt)

            # 4. Calculate Derived Metrics
            fwhm = 2.355 * sigma_fit
            resolution = (fwhm / cen_fit) * 100.0 if cen_fit > 0 else 0.0
            
            # Analytical Area of Gaussian = Amp * Sigma * sqrt(2*pi)
            # Analytical Area of Gaussian = Amp * Sigma * sqrt(2*pi)
            # This is the "Net Area" (excluding background)
            sqrt2pi = np.sqrt(2 * np.pi)
            net_area = amp_fit * sigma_fit * sqrt2pi
            
            # --- Uncertainty Propagation ---
            # Area N = A * s * sqrt(2pi)
            # Variance(N) = (dN/dA)^2 * Var(A) + (dN/ds)^2 * Var(s) + 2*(dN/dA)(dN/ds)*Cov(A,s)
            # dN/dA = s * sqrt(2pi)
            # dN/ds = A * sqrt(2pi)
            
            var_A = pcov[0,0]
            var_s = pcov[2,2]
            cov_As = pcov[0,2]
            
            dN_dA = sigma_fit * sqrt2pi
            dN_ds = amp_fit * sqrt2pi
            
            var_N = (dN_dA**2 * var_A) + (dN_ds**2 * var_s) + (2 * dN_dA * dN_ds * cov_As)
            area_uncertainty = np.sqrt(var_N)
            
            background_area = np.trapz(bg_curve, x_roi)

            # R-Squared
            residuals = y_roi - fit_curve
            ss_res = np.sum(residuals**2)
            ss_tot = np.sum((y_roi - np.mean(y_roi))**2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            return FitResult(
                amplitude=amp_fit,
                centroid=cen_fit,
                sigma=sigma_fit,
                fwhm=fwhm,
                resolution=resolution,
                net_area=net_area,
                background_area=background_area,
                baseline_coeffs=list(bg_coeffs),
                r_squared=r2,
                uncertainty=area_uncertainty
            )

        except Exception as e:
            # print(f"DEBUG: Fit failed for {centroid_guess}: {e}")
            return None

    def fit_multiplet(self,
                      energies: np.ndarray,
                      counts: np.ndarray,
                      centroids: List[float],
                      roi_width_kev: float = 30.0) -> Tuple[Optional[List[FitResult]], float]:
        """
        Fits multiple overlapping Gaussian peaks on a linear baseline.
        """
        num_peaks = len(centroids)
        if num_peaks == 0:
            return None, 0.0

        # 1. Define ROI around the whole group
        min_energy = min(centroids) - roi_width_kev
        max_energy = max(centroids) + roi_width_kev
        mask = (energies >= min_energy) & (energies <= max_energy)
        x_roi = energies[mask]
        y_roi = counts[mask]
        
        if len(x_roi) < 5 * num_peaks:
            return None, 0.0

        # 2. Define Dynamic Model
        # Params: [b0, b1, A1, c1, s1, A2, c2, s2, ...]
        def multiplet_model(x, *params):
            # Baseline: b1*x + b0
            y = params[1] * x + params[0]
            # Peaks
            for i in range(num_peaks):
                idx = 2 + i*3
                A, c, s = params[idx], params[idx+1], params[idx+2]
                y += self.gaussian(x, A, c, s)
            return y

        # 3. Initial Guesses
        # Baseline guess
        bg_slope = (y_roi[-1] - y_roi[0]) / (x_roi[-1] - x_roi[0])
        bg_intercept = y_roi[0] - bg_slope * x_roi[0]
        
        p0 = [bg_intercept, bg_slope]
        bounds_lower = [-np.inf, -np.inf]
        bounds_upper = [np.inf, np.inf]
        
        avg_sigma = roi_width_kev / 10.0 # Guess
        
        for c in centroids:
            # Find closest amp roughly
            idx = (np.abs(x_roi - c)).argmin()
            amp = y_roi[idx] - (bg_slope * c + bg_intercept)
            p0.extend([max(1, amp), c, avg_sigma])
            
            # Constrain centroid to be roughly near guess (± 5 keV)
            bounds_lower.extend([0, c - 5.0, 0.1])
            bounds_upper.extend([np.inf, c + 5.0, roi_width_kev])

        try:
            popt, pcov = curve_fit(multiplet_model, x_roi, y_roi, p0=p0, bounds=(bounds_lower, bounds_upper), maxfev=20000)
            
            # 4. Unpack Results
            bg_coeffs = [popt[0], popt[1]]
            results = []
            
            # Calculate total RSS for r-squared
            y_fit = multiplet_model(x_roi, *popt)
            residuals = y_roi - y_fit
            ss_res = np.sum(residuals**2)
            ss_tot = np.sum((y_roi - np.mean(y_roi))**2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
            
            bg_curve = bg_coeffs[1] * x_roi + bg_coeffs[0]
            background_area_total = np.trapz(bg_curve, x_roi)
            
            sqrt2pi = np.sqrt(2 * np.pi)

            for i in range(num_peaks):
                idx = 2 + i*3
                amp, cen, sigma = popt[idx], popt[idx+1], popt[idx+2]
                
                fwhm = 2.355 * sigma
                resolution = (fwhm / cen) * 100.0
                net_area = amp * sigma * sqrt2pi
                
                # Uncertainty Propagation
                var_A = pcov[idx, idx]
                var_s = pcov[idx+2, idx+2]
                cov_As = pcov[idx, idx+2]
                
                dN_dA = sigma * sqrt2pi
                dN_ds = amp * sqrt2pi
                
                var_N = (dN_dA**2 * var_A) + (dN_ds**2 * var_s) + (2 * dN_dA * dN_ds * cov_As)
                area_uncertainty = np.sqrt(var_N)
                
                res = FitResult(
                    amplitude=amp,
                    centroid=cen,
                    sigma=sigma,
                    fwhm=fwhm,
                    resolution=resolution,
                    net_area=net_area,
                    background_area=background_area_total / num_peaks, # Split bg
                    baseline_coeffs=bg_coeffs,
                    r_squared=r2,
                    uncertainty=area_uncertainty
                )
                results.append(res)
                
            return results, r2

        except Exception as e:
            print(f"DEBUG: Multiplet fit failed: {e}")
            return None, 0.0
