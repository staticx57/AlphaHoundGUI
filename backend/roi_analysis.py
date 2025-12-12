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
        acquisition_time_s: float
    ) -> ROIResult:
        """
        Perform ROI analysis for a specific isotope.
        
        Args:
            energies: List of energy values (keV) for each channel
            counts: List of counts for each channel
            isotope_name: Name of isotope from ROI database
            acquisition_time_s: Acquisition time in seconds
            
        Returns:
            ROIResult with net counts, activity, and uncertainties
        """
        isotope = get_roi_isotope(isotope_name)
        if not isotope:
            raise ValueError(f"Unknown isotope: {isotope_name}")
        
        roi_window = isotope["roi_window"]
        bg_region = isotope["background_region"]
        peak_energy = isotope["energy_keV"]
        branching_ratio = isotope["branching_ratio"]
        
        # Calculate gross counts in ROI
        gross_counts = self._sum_counts_in_region(energies, counts, roi_window)
        
        # Calculate background
        background_counts = self._calculate_background(
            energies, counts, roi_window, bg_region, isotope["background_method"]
        )
        
        # Net counts
        net_counts = max(0, gross_counts - background_counts)
        
        # Uncertainty (counting statistics)
        uncertainty = math.sqrt(gross_counts + background_counts)
        
        # Get detector efficiency at peak energy
        efficiency = interpolate_efficiency(self.detector_name, peak_energy)
        efficiency_percent = efficiency * 100
        
        # Calculate activity
        activity_bq = None
        activity_uci = None
        
        if efficiency > 0 and acquisition_time_s > 0 and branching_ratio > 0:
            # Activity (Bq) = Net counts / (efficiency × time × branching ratio)
            activity_bq = net_counts / (efficiency * acquisition_time_s * branching_ratio)
            # Convert to μCi (1 Bq = 2.703e-5 μCi)
            activity_uci = activity_bq * 2.703e-5
        
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
            detector=self.detector_name,
            acquisition_time_s=acquisition_time_s,
            efficiency_percent=efficiency_percent,
            branching_ratio=branching_ratio
        )
    
    def analyze_uranium_ratio(
        self,
        energies: List[float],
        counts: List[int],
        acquisition_time_s: float
    ) -> Dict:
        """
        Analyze uranium enrichment using 186 keV / 93 keV ratio.
        
        The ratio of U-235 (186 keV) to Th-234 (93 keV) indicates:
        - ≥30%: Natural Uranium (~0.72% U-235)
        - <30%: Depleted Uranium (<0.3% U-235)
        - >100%: Enriched Uranium (>0.72% U-235)
        
        Returns:
            Dictionary with ratio analysis results
        """
        # Analyze both peaks
        u235_result = self.analyze(energies, counts, "U-235 (186 keV)", acquisition_time_s)
        th234_result = self.analyze(energies, counts, "Th-234 (93 keV)", acquisition_time_s)
        
        # Calculate ratio
        if th234_result.net_counts > 0:
            ratio = (u235_result.net_counts / th234_result.net_counts) * 100
            
            # Propagate uncertainty
            if u235_result.net_counts > 0:
                ratio_uncertainty = ratio * math.sqrt(
                    (u235_result.uncertainty_sigma / u235_result.net_counts) ** 2 +
                    (th234_result.uncertainty_sigma / th234_result.net_counts) ** 2
                )
            else:
                ratio_uncertainty = 0
        else:
            ratio = 0
            ratio_uncertainty = 0
        
        # Determine enrichment category
        if ratio >= 100:
            category = "Enriched Uranium"
            description = f"U-235 enriched above natural (>{0.72}% U-235)"
        elif ratio >= 30:
            category = "Natural Uranium"
            description = f"Natural isotopic composition (~0.72% U-235)"
        else:
            category = "Depleted Uranium"
            description = f"U-235 depleted below natural (<0.3% U-235)"
        
        return {
            "u235_net_counts": u235_result.net_counts,
            "u235_uncertainty": u235_result.uncertainty_sigma,
            "th234_net_counts": th234_result.net_counts,
            "th234_uncertainty": th234_result.uncertainty_sigma,
            "ratio_percent": ratio,
            "ratio_uncertainty": ratio_uncertainty,
            "category": category,
            "description": description,
            "threshold_natural": 30,  # ≥30% indicates natural
            "u235_result": u235_result,
            "th234_result": th234_result
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


def analyze_roi(
    energies: List[float],
    counts: List[int],
    isotope_name: str,
    detector_name: str,
    acquisition_time_s: float
) -> Dict:
    """
    Convenience function for ROI analysis.
    
    Returns dictionary suitable for JSON API response.
    """
    analyzer = ROIAnalyzer(detector_name)
    result = analyzer.analyze(energies, counts, isotope_name, acquisition_time_s)
    
    return {
        "isotope": result.isotope_name,
        "energy_keV": result.energy_keV,
        "roi_window": list(result.roi_window),
        "gross_counts": result.gross_counts,
        "background_counts": round(result.background_counts, 1),
        "net_counts": round(result.net_counts, 1),
        "uncertainty_sigma": round(result.uncertainty_sigma, 1),
        "activity_bq": round(result.activity_bq, 2) if result.activity_bq else None,
        "activity_uci": round(result.activity_uci, 6) if result.activity_uci else None,
        "detector": result.detector,
        "acquisition_time_s": result.acquisition_time_s,
        "efficiency_percent": round(result.efficiency_percent, 2),
        "branching_ratio": result.branching_ratio
    }


def analyze_uranium_enrichment(
    energies: List[float],
    counts: List[int],
    detector_name: str,
    acquisition_time_s: float
) -> Dict:
    """
    Convenience function for uranium enrichment analysis.
    
    Returns dictionary suitable for JSON API response.
    """
    analyzer = ROIAnalyzer(detector_name)
    result = analyzer.analyze_uranium_ratio(energies, counts, acquisition_time_s)
    
    return {
        "u235_net_counts": round(result["u235_net_counts"], 1),
        "u235_uncertainty": round(result["u235_uncertainty"], 1),
        "th234_net_counts": round(result["th234_net_counts"], 1),
        "th234_uncertainty": round(result["th234_uncertainty"], 1),
        "ratio_percent": round(result["ratio_percent"], 1),
        "ratio_uncertainty": round(result["ratio_uncertainty"], 1),
        "category": result["category"],
        "description": result["description"],
        "threshold_natural": result["threshold_natural"]
    }
