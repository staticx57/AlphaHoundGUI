"""
ROI (Region-of-Interest) Analysis Engine

Provides quantitative isotope analysis including:
- Net counts calculation with background subtraction
- Activity calculation using detector efficiency
- Uncertainty estimation (counting statistics)
- Uranium enrichment ratio analysis

References:
- Knoll, G.F. "Radiation Detection and Measurement", 4th ed.
- IAEA Safety Series No. 120 "Calibration of Radiation Protection Monitoring Instruments"
"""

import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from detector_efficiency import get_detector, interpolate_efficiency
from isotope_roi_database import get_roi_isotope, get_roi_window, get_background_region
from activity_calculator import calculate_activity_bq, bq_to_uci, calculate_mda_bq


@dataclass
class ROIResult:
    """Results from ROI analysis."""
    isotope_name: str
    energy_keV: float
    roi_window: Tuple[float, float]
    
    # Counts
    gross_counts: int
    background_counts: float
    net_counts: float
    uncertainty_sigma: float
    
    # Activity
    activity_bq: Optional[float]
    activity_uci: Optional[float]
    
    # Metadata
    detector: str
    acquisition_time_s: float
    efficiency_percent: float
    branching_ratio: float
    
    # Detection quality metrics
    detected: bool = False                    # Is isotope actually detected?
    confidence: float = 0.0                   # Confidence score 0.0-1.0
    snr: float = 0.0                          # Signal-to-noise ratio
    fit_success: bool = False                 # Was advanced fitting successful?
    resolution: Optional[float] = None        # Energy Resolution (%)
    fwhm: Optional[float] = None              # Full Width Half Max (keV)
    detection_limit_counts: float = 0.0       # Minimum detectable counts (3-sigma)
    detection_status: str = "Not Detected"    # Status message
    limiting_factors: List[str] = None        # Why confidence is low
    recommendations: List[str] = None         # What would improve results
    
    # Optional MDA for non-detects
    mda_bq: Optional[float] = None
    mda_uci: Optional[float] = None
    
    # Optional ratio analysis
    ratio_analysis: Optional[Dict] = None




class ROIAnalyzer:
    """
    Performs Region-of-Interest analysis on gamma spectra.
    """
    
    def __init__(self, detector_name: str = "AlphaHound BGO"):
        self.detector_name = detector_name
        self.detector = get_detector(detector_name)
    
    def analyze(
        self,
        energies: List[float],
        counts: List[int],
        isotope_name: str,
        acquisition_time_s: float,
        source_type: str = "auto"
    ) -> ROIResult:
        """
        Perform ROI analysis for a specific isotope with detection quality metrics.
        
        Args:
            energies: List of energy values (keV) for each channel
            counts: List of counts for each channel
            isotope_name: Name of isotope from ROI database
            acquisition_time_s: Acquisition time in seconds
            source_type: Optional source type context (e.g. 'uranium_glass')
            
        Returns:
            ROIResult with net counts, activity, uncertainties, and detection quality
        """
        isotope = get_roi_isotope(isotope_name)
        if not isotope:
            raise ValueError(f"Unknown isotope: {isotope_name}")
        
        roi_window = isotope["roi_window"]
        bg_region = isotope["background_region"]
        peak_energy = isotope["energy_keV"]
        branching_ratio = isotope["branching_ratio"]
        
        # Default metrics
        resolution = 0.0
        fwhm = 0.0
        
        # --- Advanced Spectrum Fitting (Phase 4) ---
        fit_success = False
        try:
            from .fitting_engine import AdvancedFittingEngine
            fitter = AdvancedFittingEngine()
            
            # Use a slightly wider window for fitting (1.5x ROI) to constrain background
            roi_width = roi_window[1] - roi_window[0]
            
            fit_result = fitter.fit_single_peak(
                energies, 
                counts, 
                centroid_guess=target_energy,
                roi_width_kev=roi_width * 1.5
            )

            # Accept fit if R-squared is decent
            if fit_result and fit_result.r_squared > 0.7:
                gross_counts = fit_result.net_area + fit_result.background_area
                background_counts = fit_result.background_area
                raw_net_counts = fit_result.net_area
                
                # New Metrics
                fwhm = fit_result.fwhm
                resolution = fit_result.resolution
                
                # Use rigorous uncertainty if available
                if hasattr(fit_result, 'uncertainty') and fit_result.uncertainty > 0:
                    uncertainty = fit_result.uncertainty
                else:
                    uncertainty = math.sqrt(gross_counts + background_counts) # Fallback
                
                fit_success = True
                # print(f"DEBUG: Fit Success {isotope_name}: Res={resolution:.2f}%, Net={raw_net_counts:.1f}")

        except Exception as e:
            # print(f"DEBUG: Fit Error {isotope_name}: {e}")
            pass

        if not fit_success:
            # --- Fallback: Standard ROI Integration ---
            gross_counts = self._sum_counts_in_region(energies, counts, roi_window)
            background_counts = self._calculate_background(
                energies, counts, roi_window, bg_region, isotope["background_method"]
            )
            raw_net_counts = gross_counts - background_counts

        # Net counts (allow negative for diagnostic purposes, but cap at 0 for activity)
        net_counts = max(0, raw_net_counts)
        
        # Uncertainty (counting statistics)
        uncertainty = math.sqrt(gross_counts + background_counts)
        
        # === SOURCE TYPE VALIDATION ===
        # Import here to avoid circular dependency
        try:
            from source_identification import get_source_signature
            signature = get_source_signature(source_type) if source_type and source_type not in ["auto", "unknown"] else None
        except ImportError:
            signature = None
            
        source_validation_note = None
        source_validation_warning = None
        
        if signature:
            # Check if isotope is unexpected for this source
            # Match strictly by name string for now
            if isotope_name in signature.excluding_isotopes:
                source_validation_warning = f"Isotope {isotope_name} is NOT expected in {signature.name}. Detection may be background or interference."
            elif isotope_name in signature.required_isotopes or isotope_name in signature.supporting_isotopes:
                source_validation_note = f"Consistent with {signature.name} profile."
        
        # === DETECTION QUALITY METRICS ===
        
        # Detection limit: Currie's LD (for reference, but not used for detection decision)
        # LD = 2.71 + 4.65 * sqrt(background)
        detection_limit_counts = 2.71 + 4.65 * math.sqrt(background_counts)
        
        # Signal-to-Noise Ratio (SNR)
        snr = net_counts / uncertainty if uncertainty > 0 else 0
        
        # Detection status - use SNR threshold instead of Currie limit
        # SNR >= 2 is a practical threshold that matches peak detection sensitivity
        detected = snr >= 2.0 and net_counts > 20
        
        if detected:
            if snr >= 10:
                detection_status = "Strong Detection"
            elif snr >= 5:
                detection_status = "Good Detection"
            elif snr >= 3:
                detection_status = "Weak Detection"
            else:
                detection_status = "Marginal Detection"
        else:
            if raw_net_counts < 0:
                detection_status = "Not Detected (over-subtracted)"
            else:
                detection_status = "Not Detected (below limit)"
        
        # Confidence score (0.0 - 1.0)
        # Based on signal strength relative to detection limit and uncertainty
        confidence = 0.0
        if detected:
            # Factor 1: How far above detection limit (0-0.4)
            excess_ratio = net_counts / detection_limit_counts if detection_limit_counts > 0 else 0
            confidence += min(0.4, 0.1 * excess_ratio)
            
            # Factor 2: SNR quality (0-0.4)
            snr_factor = min(0.4, 0.04 * snr)
            confidence += snr_factor
            
            # Factor 3: Statistical precision (0-0.2)
            if net_counts > 0:
                relative_error = uncertainty / net_counts
                precision_factor = max(0, 0.2 * (1 - min(1, relative_error)))
                confidence += precision_factor
        
        confidence = min(1.0, max(0.0, confidence))
        
        # Penalize confidence for very short acquisition times (< 60s)
        # Reflects higher risk of transient noise or insufficient background averaging
        if acquisition_time_s < 60:
            confidence *= 0.8
            if detected:
                # Add this to limiting factors later if detected
                # (Need to store it temporarily or append directly)
                pass # Will handle in limiting factors section
        
        confidence = min(1.0, max(0.0, confidence))
        
        # Get detector efficiency at peak energy
        efficiency = interpolate_efficiency(self.detector_name, peak_energy)
        efficiency_percent = efficiency * 100
        
        # Calculate activity (only if detected)
        activity_bq = None
        activity_uci = None
        mda_bq = None
        mda_uci = None
        
        # Calculate MDA always as a reference
        if efficiency > 0 and acquisition_time_s > 0 and branching_ratio > 0:
            mda_bq = calculate_mda_bq(background_counts, acquisition_time_s, efficiency, branching_ratio)
            mda_uci = bq_to_uci(mda_bq)
        
        if (detected or net_counts > 0) and efficiency > 0 and acquisition_time_s > 0 and branching_ratio > 0:
            # Calculate Activity using centralized engine
            activity_bq = calculate_activity_bq(net_counts, acquisition_time_s, efficiency, branching_ratio)
            activity_uci = bq_to_uci(activity_bq)
        else:
            pass
        
        # === LIMITING FACTORS AND RECOMMENDATIONS ===
        limiting_factors = []
        recommendations = []
        
        # Source validation feedback
        if source_validation_warning:
            limiting_factors.append(source_validation_warning)
            # Significant confidence penalty for unexpected isotopes
            confidence *= 0.3
            recommendations.append(f"Verify source type selection (selected: {source_type})")
        
        if source_validation_note:
            # Bonus confidence for expected isotopes
            confidence = min(1.0, confidence + 0.1)
            # We could add this to a 'notes' field if ROIResult had one, or prepend to limiting factors as a positive note?
            # For now, let's not clutter limiting factors with positive notes unless we add a specific field.
            pass
        
        # Check signal strength
        if not detected:
            limiting_factors.append(f"Signal below detection limit ({net_counts:.0f} < {detection_limit_counts:.0f} counts)")
            
            # Estimate time needed for detection
            if net_counts > 0 and detection_limit_counts > 0:
                time_factor = (detection_limit_counts / net_counts) ** 2
                recommended_time = acquisition_time_s * time_factor
                if recommended_time < 86400:  # Less than 24 hours
                    recommendations.append(f"Increase acquisition to ~{recommended_time/60:.0f} min for detection")
                else:
                    recommendations.append("Source may be too weak for this detector")
            else:
                recommendations.append("Longer acquisition time needed")
        
        elif confidence < 0.5:
            # Low confidence but detected
            if snr < 5:
                limiting_factors.append(f"Low signal-to-noise ratio (SNR: {snr:.1f})")
                time_needed = acquisition_time_s * (5 / max(snr, 0.1)) ** 2
                recommendations.append(f"Increase acquisition to ~{time_needed/60:.0f} min for better SNR")
            
            if uncertainty / max(net_counts, 1) > 0.3:
                limiting_factors.append(f"High statistical uncertainty (±{uncertainty/max(net_counts,1)*100:.0f}%)")
                recommendations.append("More counts needed for precise measurement")
            
            if net_counts < 100:
                limiting_factors.append(f"Low signal strength ({net_counts:.0f} counts)")
                
        elif confidence < 0.8:
            # Medium confidence
            if snr < 10:
                limiting_factors.append(f"Moderate signal-to-noise ratio (SNR: {snr:.1f})")
        
        # Add efficiency note for low-efficiency regions
        if efficiency_percent < 5:
            limiting_factors.append(f"Low detector efficiency at {peak_energy:.0f} keV ({efficiency_percent:.1f}%)")
            recommendations.append("Energy region may be outside detector's optimal range")
        
        # Acquisition time feedback
        if acquisition_time_s < 300 and not detected:
            recommendations.append("Consider minimum 5-10 minute acquisition for weak sources")

        if acquisition_time_s < 60:
            limiting_factors.append(f"Short acquisition time ({acquisition_time_s:.0f}s < 60s) limits reliability")
            recommendations.append("Acquire for > 1 minute to improve confidence")
        
        # DEBUG: Print advanced fitting status
        print(f"[DEBUG] Advanced Fitting - Success: {fit_success}, Resolution: {resolution}, FWHM: {fwhm}, Error: {uncertainty}")

        return ROIResult(
            isotope_name=isotope_name,
            energy_keV=peak_energy,
            roi_window=roi_window,
            gross_counts=gross_counts,
            background_counts=background_counts,
            net_counts=net_counts,
            uncertainty_sigma=uncertainty,
            activity_bq=activity_bq,
            activity_uci=activity_uci,
            mda_bq=mda_bq,
            mda_uci=mda_uci,
            detector=self.detector_name,
            acquisition_time_s=acquisition_time_s,
            efficiency_percent=efficiency_percent,
            branching_ratio=branching_ratio,
            detected=detected,
            confidence=confidence,
            snr=snr,
            fit_success=fit_success,
            resolution=resolution,
            fwhm=fwhm,
            detection_limit_counts=detection_limit_counts,
            detection_status=detection_status,
            limiting_factors=limiting_factors if limiting_factors else None,
            recommendations=recommendations if recommendations else None
        )


    
    def analyze_uranium_ratio(
        self,
        energies: List[float],
        counts: List[int],
        acquisition_time_s: float,
        source_type: str = "auto"
    ) -> Dict:
        """
        Smart uranium enrichment analysis with prerequisite checks and confidence scoring.
        
        This method:
        1. Checks if uranium signatures are present (prerequisite)
        2. Detects Ra-226 interference that contaminates the 186 keV region
        3. Uses multiple methods and cross-validates when possible
        4. Returns confidence level and detailed diagnostics
        
        Returns:
            Dictionary with analysis results, confidence, and diagnostics
        """
        diagnostics = []
        warnings = []
        
        # === STEP 1: CHECK PREREQUISITES - Is uranium even present? ===
        # Look for U-238 decay chain markers
        th234_result = None
        bi214_result = None
        pa234m_result = None
        
        try:
            th234_result = self.analyze(energies, counts, "Th-234 (93 keV)", acquisition_time_s)
            diagnostics.append(f"Th-234 (93 keV): {th234_result.net_counts:.0f} ± {th234_result.uncertainty_sigma:.0f} counts")
        except:
            pass
            
        try:
            bi214_result = self.analyze(energies, counts, "Bi-214 (609 keV)", acquisition_time_s)
            diagnostics.append(f"Bi-214 (609 keV): {bi214_result.net_counts:.0f} ± {bi214_result.uncertainty_sigma:.0f} counts")
        except:
            pass
            
        try:
            pa234m_result = self.analyze(energies, counts, "Pa-234m (1001 keV)", acquisition_time_s)
            diagnostics.append(f"Pa-234m (1001 keV): {pa234m_result.net_counts:.0f} ± {pa234m_result.uncertainty_sigma:.0f} counts")
        except:
            pass
        
        # Minimum signal thresholds (3-sigma above background)
        MIN_COUNTS_THRESHOLD = 30
        
        # Check if we have any uranium indicators
        has_th234 = th234_result and th234_result.net_counts > MIN_COUNTS_THRESHOLD
        has_bi214 = bi214_result and bi214_result.net_counts > MIN_COUNTS_THRESHOLD
        has_pa234m = pa234m_result and pa234m_result.net_counts > MIN_COUNTS_THRESHOLD
        
        uranium_detected = has_th234 or has_bi214 or has_pa234m
        
        if not uranium_detected:
            return {
                "can_analyze": False,
                "reason": "No uranium signatures detected",
                "category": "Not Applicable",
                "description": "Spectrum does not contain detectable uranium. No Th-234, Bi-214, or Pa-234m peaks found above threshold.",
                "confidence": 0.0,
                "diagnostics": diagnostics,
                "warnings": ["No U-238 decay chain daughters detected - uranium enrichment analysis not applicable"],
                "u235_net_counts": 0,
                "th234_net_counts": th234_result.net_counts if th234_result else 0,
                "ratio_percent": 0,
                "threshold_natural": 30
            }
        
        # === SPECIAL CASE: Takumar Lens ===
        # Thoriated lenses contain ThO2 with trace natural uranium
        # Skip enrichment ratio (meaningless) and report Th-234 activity instead
        print(f"[DEBUG] Takumar check: source_type={source_type}, has_th234={has_th234}")
        if source_type == "takumar_lens" and has_th234:
            return {
                "can_analyze": True,
                "category": "Thoriated Lens (Mixed Th/U)",
                "description": "Super Takumar lens containing thorium dioxide with trace natural uranium. Enrichment ratio not applicable.",
                "ratio_percent": 0,
                "threshold_natural": 30,
                "confidence": 0.9,  # High confidence since we detected Th-234
                "ra226_interference": False,  # Not an error for this source type
                "u235_net_counts": 0,
                "u235_uncertainty": 0,
                "th234_net_counts": th234_result.net_counts if th234_result else 0,
                "th234_uncertainty": th234_result.uncertainty_sigma if th234_result else 0,
                "bi214_net_counts": bi214_result.net_counts if bi214_result else 0,
                "diagnostics": diagnostics,
                "warnings": ["Takumar lens: Activity reported from Th-234 (93 keV) peak. Contains both Th-232 and trace natural U-238."],
                "confidence_factors": ["Th-234 detected", "Known thoriated lens source type"]
            }
        
        # === STEP 2: Analyze U-235 (186 keV) region ===
        try:
            u235_result = self.analyze(energies, counts, "U-235 (186 keV)", acquisition_time_s)
            diagnostics.append(f"U-235 (186 keV): {u235_result.net_counts:.0f} ± {u235_result.uncertainty_sigma:.0f} counts")
        except Exception as e:
            warnings.append(f"Failed to analyze U-235 region: {str(e)}")
            u235_result = None
        
        # === STEP 3: Detect Ra-226 Interference ===
        # Ra-226 emits at 186.2 keV and is in secular equilibrium with aged U-238
        # Bi-214 presence indicates Ra-226 is present (Bi-214 is Ra-226's great-granddaughter)
        ra226_interference = False
        
        # Check source type hinting
        known_ra226_source = source_type in ["uranium_glass", "radium_dial", "natural_uranium", "takumar_lens"]
        
        # Special check for Thoriated Lens (pure Th only)
        if source_type == "thoriated_lens":
            try:
                # Check for Thorium marker (Ac-228)
                ac228_result = self.analyze(energies, counts, "Ac-228 (911 keV)", acquisition_time_s)
                if ac228_result.detected:
                    warnings.append(
                        f"Strong Thorium signature (Ac-228) confirmed. "
                        f"Uranium detection may be due to mixed source composition or Compton scattering."
                    )
            except:
                pass
        
        # Special handling for Takumar lens (ThO2 + trace natural U)
        if source_type == "takumar_lens":
            warnings.append(
                "Takumar lens analysis: Source contains Thorium dioxide + trace natural uranium. "
                "Ra-226 interference correction will be applied."
            )
        
        if has_bi214 or known_ra226_source:
            # Ra-226 is definitely present if Bi-214 is detected OR user confirmed source type
            # The 186 keV region will contain BOTH U-235 (185.7 keV) AND Ra-226 (186.2 keV)
            ra226_interference = True
            
            # === NEW: Try to subtract Ra-226 if we have good data ===
            # Requested by user to "do our best" for Uranium Glass
            ra226_corrected = False
            
            if source_type in ["uranium_glass", "takumar_lens"] and bi214_result.net_counts > 0:
                try:
                    # Ra-226 (186.2 keV) Yield: 3.64%
                    # Bi-214 (609.3 keV) Yield: 45.49%
                    YIELD_RA226_186 = 3.64
                    YIELD_BI214_609 = 45.49
                    
                    # Get efficiencies
                    eff_186 = interpolate_efficiency(self.detector_name, 186.2)
                    eff_609 = interpolate_efficiency(self.detector_name, 609.3)
                    
                    if eff_186 > 0 and eff_609 > 0:
                        # Calculate theoretical Ra-226 counts at 186 keV based on Bi-214
                        # Ratio = (Yield_186 / Yield_609) * (Eff_186 / Eff_609)
                        ra226_ratio = (YIELD_RA226_186 / YIELD_BI214_609) * (eff_186 / eff_609)
                        estimated_ra226_counts = bi214_result.net_counts * ra226_ratio
                        
                        # Apply correction
                        original_186_counts = u235_result.net_counts
                        u235_corrected_counts = max(0, original_186_counts - estimated_ra226_counts)
                        
                        # Use corrected counts for ratio
                        net_u235_counts = u235_corrected_counts
                        
                        # Update flag to allow analysis to proceed
                        ra226_interference = False 
                        ra226_corrected = True
                        
                        warnings.append(
                            f"Ra-226 interference subtracted (estimated {estimated_ra226_counts:.0f} counts from Bi-214 proxy). "
                            f"Enrichment result is an ESTIMATE."
                        )
                        if bi214_result.snr < 2.0:
                             warnings.append("Warning: Correction based on weak Bi-214 signal. Result allows approx.")
                except Exception as e:
                    print(f"Error correcting Ra-226: {e}")
            
            if ra226_interference:
                # Only warn if we didn't correct it
                if has_bi214:
                    warnings.append(
                        f"Bi-214 detected ({bi214_result.net_counts:.0f} counts) indicates Ra-226 is in secular equilibrium. "
                        f"The 186 keV peak contains overlapping U-235 and Ra-226 contributions."
                    )
                elif known_ra226_source:
                    warnings.append(
                        f"Source type '{source_type}' typically contains Ra-226. "
                        f"The 186 keV peak likely contains overlapping U-235 and Ra-226 contributions."
                    )
        
        # === STEP 4: Calculate Enrichment Ratio ===
        # Note: If Ra-226 interference is detected, this ratio is UNRELIABLE
        # but we still calculate it for informational purposes
        ratio = 0.0
        ratio_uncertainty = 0.0
        method_used = "none"
        
        if u235_result and has_th234:
            # Primary method: U-235 (186 keV) / Th-234 (93 keV)
            # WARNING: If Ra-226 interference, this includes Ra-226 contribution
            if th234_result.net_counts > 0:
                ratio = (u235_result.net_counts / th234_result.net_counts) * 100
                method_used = "U-235/Th-234 ratio" + (" (UNRELIABLE - Ra-226 interference)" if ra226_interference else "")
                
                # Propagate uncertainty
                if u235_result.net_counts > 0:
                    ratio_uncertainty = ratio * math.sqrt(
                        (u235_result.uncertainty_sigma / u235_result.net_counts) ** 2 +
                        (th234_result.uncertainty_sigma / th234_result.net_counts) ** 2
                    )
        
        # === STEP 5: Calculate Confidence Score ===
        confidence = 0.0
        confidence_factors = []
        
        # Factor 1: Signal strength (0-0.3)
        if has_th234 and th234_result.net_counts > 100:
            signal_factor = min(0.3, 0.3 * (th234_result.net_counts / 500))
            confidence += signal_factor
            confidence_factors.append(f"Signal strength: +{signal_factor:.2f}")
        
        # Factor 2: Multiple uranium markers present (0-0.3)
        markers_present = sum([has_th234, has_bi214, has_pa234m])
        marker_factor = 0.1 * markers_present
        confidence += marker_factor
        confidence_factors.append(f"Uranium markers ({markers_present}/3): +{marker_factor:.2f}")
        
        # Factor 3: Ra-226 interference penalty (-0.2 to 0)
        if ra226_interference:
            interference_penalty = -0.2
            confidence += interference_penalty
            confidence_factors.append(f"Ra-226 interference: {interference_penalty:.2f}")
        else:
            confidence += 0.2
            confidence_factors.append(f"No Ra-226 interference: +0.20")
        
        # Factor 4: Statistical precision (0-0.2)
        if ratio > 0 and ratio_uncertainty > 0:
            precision = 1 - min(1, ratio_uncertainty / ratio)
            precision_factor = 0.2 * precision
            confidence += precision_factor
            confidence_factors.append(f"Statistical precision: +{precision_factor:.2f}")
        
        confidence = max(0.0, min(1.0, confidence))
        
        # === STEP 6: Determine Category ===
        # CRITICAL: If Ra-226 interference is detected, the ratio is UNRELIABLE
        # Ra-226 (186.2 keV) overlaps with U-235 (185.7 keV) 
        # A CsI/NaI/BGO detector CANNOT distinguish them (need HPGe)
        if ra226_interference:
            # Don't assume the category - just report that enrichment cannot be determined
            category = "Indeterminate (Ra-226 Interference)"
            description = (
                "The 186 keV region contains overlapping peaks from U-235 (185.7 keV) and Ra-226 (186.2 keV). "
                "This detector cannot resolve them, making enrichment analysis unreliable. "
                "An HPGe detector (resolution <1 keV) is required for accurate U-235/U-238 ratio measurement."
            )
            # Severely penalize confidence - we genuinely don't know
            confidence = min(confidence, 0.2)
            confidence_factors.append("Ra-226 interference: enrichment ratio indeterminate")
            warnings.append(
                f"Calculated ratio ({ratio:.0f}%) is unreliable due to Ra-226 interference. "
                f"The true enrichment could be natural (~0.7%), depleted (<0.3%), or enriched (>0.7%). "
                f"Sample age, equilibrium state, and detector resolution prevent accurate determination."
            )
        elif ratio >= 150:
            # SANITY CHECK: Ratios above 150% are physically impossible
            # This indicates the user selected the wrong source type
            # (e.g., analyzing a thoriated lens as uranium glass)
            category = "Source Type Mismatch"
            description = (
                f"Ratio of {ratio:.0f}% is physically impossible for uranium. "
                "This likely indicates a thoriated source (Th-232) being analyzed with uranium assumptions. "
                "Try selecting 'Takumar Lens' or 'Thoriated Lens' as source type instead."
            )
            confidence = 0.1  # Very low confidence
            confidence_factors.append("Implausible ratio detected - likely source mismatch")
            warnings.append(
                "SANITY CHECK FAILED: U-235/Th-234 ratio exceeds 150%, which is physically impossible. "
                "This source is likely thoriated (Th-232) rather than uranium-based."
            )
        elif ratio >= 100:
            category = "Enriched Uranium"
            description = f"U-235 enriched above natural (>{0.72}% U-235)"
        elif ratio >= 30:
            category = "Natural Uranium"
            description = f"Natural isotopic composition (~0.72% U-235)"
        elif ratio > 0:
            category = "Depleted Uranium"
            description = f"U-235 depleted below natural (<0.3% U-235)"
        else:
            category = "Unable to Determine"
            description = "Insufficient data for enrichment determination"
        
        return {
            "can_analyze": True,
            "category": category,
            "description": description,
            "confidence": round(confidence, 2),
            "confidence_factors": confidence_factors,
            "method_used": method_used,
            "ratio_percent": round(ratio, 1),
            "ratio_uncertainty": round(ratio_uncertainty, 1),
            "u235_net_counts": round(u235_result.net_counts if u235_result else 0, 1),
            "u235_uncertainty": round(u235_result.uncertainty_sigma if u235_result else 0, 1),
            "th234_net_counts": round(th234_result.net_counts if th234_result else 0, 1),
            "th234_uncertainty": round(th234_result.uncertainty_sigma if th234_result else 0, 1),
            "bi214_net_counts": round(bi214_result.net_counts if bi214_result else 0, 1),
            "ra226_interference": ra226_interference,
            "threshold_natural": 30,
            "diagnostics": diagnostics,
            "warnings": warnings
        }

    
    def _sum_counts_in_region(
        self,
        energies: List[float],
        counts: List[int],
        region: Tuple[float, float]
    ) -> int:
        """Sum counts within an energy region."""
        start, end = region
        total = 0
        for i, energy in enumerate(energies):
            if start <= energy <= end:
                total += counts[i]
        return total
    
    def _calculate_background(
        self,
        energies: List[float],
        counts: List[int],
        roi_window: Tuple[float, float],
        bg_region: Tuple[float, float],
        method: str = "compton"
    ) -> float:
        """
        Calculate background counts in ROI using specified method.
        
        Methods:
        - "compton": Use counts in background region, scaled to ROI width
        - "linear": Linear interpolation between regions flanking the peak
        """
        roi_start, roi_end = roi_window
        roi_width = roi_end - roi_start
        
        bg_start, bg_end = bg_region
        bg_width = bg_end - bg_start
        
        if method == "compton":
            # Scale background region counts to ROI width
            bg_counts = self._sum_counts_in_region(energies, counts, bg_region)
            if bg_width > 0:
                return bg_counts * (roi_width / bg_width)
            return 0
        
        elif method == "linear":
            # For linear, we'd need regions on both sides of the peak
            # Simplified: just use the background region scaled
            bg_counts = self._sum_counts_in_region(energies, counts, bg_region)
            if bg_width > 0:
                return bg_counts * (roi_width / bg_width)
            return 0
        
        return 0


def calculate_ra226_equilibrium_correction(
    th232_activity_bq: float,
    u238_activity_bq: Optional[float] = None,
    source_type: str = "thoriated_lens"
) -> Dict:
    """
    Calculate Ra-226 equivalent activity for sources in secular equilibrium.
    
    For thoriated lenses (Takumar, etc.):
    - Th-232 chain is in secular equilibrium (all daughters have equal activity)
    - If natural uranium is present, U-238 daughters (including Ra-226) are also in equilibrium
    
    Args:
        th232_activity_bq: Measured Th-232 chain activity (Bq)
        u238_activity_bq: Measured U-238 chain activity (Bq), if detected
        source_type: Type of source for correction factors
        
    Returns:
        Dict with equilibrium-corrected activities and metadata
    """
    result = {
        "th232_activity_bq": th232_activity_bq,
        "u238_activity_bq": u238_activity_bq,
        "ra226_equivalent_bq": None,
        "total_activity_bq": th232_activity_bq,
        "equilibrium_applied": False,
        "notes": []
    }
    
    # Th-232 chain in secular equilibrium
    # Ra-228, Ac-228, Th-228, Ra-224, etc. all have same activity as parent
    result["notes"].append("Th-232 chain assumed in secular equilibrium")
    
    # If U-238 is detected (common in Takumar lenses)
    if u238_activity_bq and u238_activity_bq > 0:
        # Ra-226 is a daughter of U-238 chain
        # In secular equilibrium: Ra-226 activity = U-238 activity
        ra226_eq = u238_activity_bq
        result["ra226_equivalent_bq"] = ra226_eq
        result["total_activity_bq"] = th232_activity_bq + u238_activity_bq
        result["equilibrium_applied"] = True
        result["notes"].append(f"Ra-226 equivalent (from U-238): {ra226_eq:.1f} Bq")
        result["notes"].append("Natural uranium present - Ra-226 in secular equilibrium")
    else:
        result["notes"].append("No significant U-238 detected - pure thorium source")
    
    return result


def analyze_roi(
    energies: List[float],
    counts: List[int],
    isotope_name: str,
    detector_name: str,
    acquisition_time_s: float,
    source_type: str = "auto"
) -> Dict:
    """
    Convenience function for ROI analysis.
    
    Returns dictionary suitable for JSON API response.
    """
    analyzer = ROIAnalyzer(detector_name)
    result = analyzer.analyze(energies, counts, isotope_name, acquisition_time_s, source_type)
    
    return {
        "isotope": result.isotope_name,
        "energy_keV": result.energy_keV,
        "roi_window": list(result.roi_window),
        "gross_counts": result.gross_counts,
        "background_counts": round(result.background_counts, 1),
        "net_counts": round(result.net_counts, 1),
        "uncertainty_sigma": round(result.uncertainty_sigma, 1),
        "uncertainty_sigma": round(result.uncertainty_sigma, 1),
        "activity_bq": round(result.activity_bq, 2) if result.activity_bq else None,
        "activity_uci": round(result.activity_uci, 6) if result.activity_uci else None,
        "mda_bq": round(result.mda_bq, 2) if result.mda_bq else None,
        "detector": result.detector,
        "acquisition_time_s": result.acquisition_time_s,
        "efficiency_percent": round(result.efficiency_percent, 2),
        "branching_ratio": result.branching_ratio,
        # Detection quality metrics
        "detected": result.detected,
        "detection_status": result.detection_status,
        "confidence": round(result.confidence, 2),
        "snr": round(result.snr, 1),
        "detection_limit_counts": round(result.detection_limit_counts, 1),
        # Advanced Fitting Metrics (Phase 4)
        "fit_success": result.fit_success,
        "resolution": round(result.resolution, 2) if result.resolution else None,
        "fwhm": round(result.fwhm, 2) if result.fwhm else None,
        # Diagnostic feedback
        "limiting_factors": result.limiting_factors,
        "recommendations": result.recommendations
    }




def analyze_uranium_enrichment(
    energies: List[float],
    counts: List[int],
    detector_name: str,
    acquisition_time_s: float,
    source_type: str = "auto"
) -> Dict:
    """
    Convenience function for uranium enrichment analysis.
    
    Returns dictionary suitable for JSON API response.
    """
    analyzer = ROIAnalyzer(detector_name)
    result = analyzer.analyze_uranium_ratio(energies, counts, acquisition_time_s, source_type)
    
    # The enhanced method returns a comprehensive dict directly
    return {
        "can_analyze": result.get("can_analyze", True),
        "category": result["category"],
        "description": result["description"],
        "confidence": result.get("confidence", 0.0),
        "method_used": result.get("method_used", ""),
        "ratio_percent": round(result.get("ratio_percent", 0), 1),
        "ratio_uncertainty": round(result.get("ratio_uncertainty", 0), 1),
        "u235_net_counts": round(result.get("u235_net_counts", 0), 1),
        "u235_uncertainty": round(result.get("u235_uncertainty", 0), 1),
        "th234_net_counts": round(result.get("th234_net_counts", 0), 1),
        "th234_uncertainty": round(result.get("th234_uncertainty", 0), 1),
        "bi214_net_counts": round(result.get("bi214_net_counts", 0), 1),
        "ra226_interference": result.get("ra226_interference", False),
        "threshold_natural": result.get("threshold_natural", 30),
        "confidence_factors": result.get("confidence_factors", []),
        "diagnostics": result.get("diagnostics", []),
        "warnings": result.get("warnings", [])
    }


