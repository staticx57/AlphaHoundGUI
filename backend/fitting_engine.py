import numpy as np
from scipy.optimize import curve_fit
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

class AdvancedFittingEngine:
    """
    Advanced Fitting Engine for Gamma Spectroscopy.
    Integrates logic from PyGammaSpec (Robust Single-Fit) and GammaSpy (Composite Multiplet Fit).
    """

    @staticmethod
    def gaussian(x, amplitude, centroid, sigma):
        """Standard Gaussian function."""
        return amplitude * np.exp(-((x - centroid)**2) / (2 * sigma**2))

    @staticmethod
    def polynomial(x, *coeffs):
        """Polynomial baseline function (default order 1 = linear)."""
        return sum(c * x**i for i, c in enumerate(coeffs))

    @staticmethod
    def combined_model_linear(x, amplitude, centroid, sigma, b0, b1):
        """Gaussian + Linear Baseline (b1*x + b0)."""
        return amplitude * np.exp(-((x - centroid)**2) / (2 * sigma**2)) + (b1 * x + b0)

    @staticmethod
    def combined_model_flat(x, amplitude, centroid, sigma, b0):
        """Gaussian + Flat Baseline (b0)."""
        return amplitude * np.exp(-((x - centroid)**2) / (2 * sigma**2)) + b0

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
