"""
Isotope ROI (Region-of-Interest) Database for Quantitative Analysis

Contains ROI definitions for common isotopes including:
- Energy windows for peak integration
- Background regions for continuum subtraction
- Branching ratios from NNDC/IAEA
- Half-lives and decay information

Data sources:
- NNDC ENSDF: https://www.nndc.bnl.gov/ensdf/
- IAEA NDS: https://www-nds.iaea.org/
- LBNL Isotopes Project: https://ie.lbl.gov/education/isotopes.htm
"""

from typing import Dict, Optional, Tuple

ISOTOPE_ROI_DATABASE = {
    # === Uranium Series ===
    "U-235 (186 keV)": {
        "isotope": "U-235",
        "energy_keV": 185.7,
        "roi_window": (165, 205),
        "branching_ratio": 0.572,  # 57.2% intensity
        "half_life_years": 7.04e8,
        "background_region": (210, 250),
        "background_method": "compton",
        "related_peaks": ["Ra-226 (186.2 keV)"],  # Potential interference
        "notes": "Primary U-235 gamma. Overlaps with Ra-226 at 186.2 keV.",
        "source": "NNDC ENSDF"
    },
    "Th-234 (93 keV)": {
        "isotope": "Th-234",
        "energy_keV": 92.6,
        "roi_window": (75, 110),
        "branching_ratio": 0.055,  # 5.5% intensity
        "half_life_years": 0.066,  # 24.1 days
        "background_region": (55, 75),
        "background_method": "compton",
        "related_peaks": ["Pa-234m (98.4 keV)"],
        "notes": "U-238 daughter. Used for uranium ratio analysis.",
        "source": "IAEA NDS"
    },
    "Pa-234m (1001 keV)": {
        "isotope": "Pa-234m",
        "energy_keV": 1001.0,
        "roi_window": (970, 1030),
        "branching_ratio": 0.0084,  # 0.84% intensity
        "half_life_years": 2.2e-6,  # 1.17 minutes
        "background_region": (1030, 1080),
        "background_method": "compton",
        "related_peaks": [],
        "notes": "High-energy U-238 daughter peak. Clean signature.",
        "source": "NNDC ENSDF"
    },
    
    # === Thorium Series ===
    "Tl-208 (2614 keV)": {
        "isotope": "Tl-208",
        "energy_keV": 2614.5,
        "roi_window": (2570, 2660),
        "branching_ratio": 0.359,  # 35.9% intensity (via Bi-212 branching)
        "half_life_years": 5.8e-6,  # 3.05 minutes
        "background_region": (2660, 2720),
        "background_method": "linear",
        "related_peaks": [],
        "notes": "Diagnostic peak for Th-232 series. Highest natural gamma.",
        "source": "NNDC ENSDF"
    },
    "Ac-228 (911 keV)": {
        "isotope": "Ac-228",
        "energy_keV": 911.2,
        "roi_window": (880, 940),
        "branching_ratio": 0.258,  # 25.8% intensity
        "half_life_years": 7.0e-4,  # 6.15 hours
        "background_region": (940, 990),
        "background_method": "compton",
        "related_peaks": ["Ac-228 (969 keV)"],
        "notes": "Strong Th-232 series indicator.",
        "source": "NNDC ENSDF"
    },
    
    # === Calibration Sources ===
    "Cs-137 (662 keV)": {
        "isotope": "Cs-137",
        "energy_keV": 661.7,
        "roi_window": (620, 700),
        "branching_ratio": 0.851,  # 85.1% intensity
        "half_life_years": 30.17,
        "background_region": (700, 750),
        "background_method": "compton",
        "related_peaks": [],
        "notes": "Standard calibration source. Long half-life.",
        "source": "NNDC ENSDF"
    },
    "Co-60 (1173 keV)": {
        "isotope": "Co-60",
        "energy_keV": 1173.2,
        "roi_window": (1130, 1210),
        "branching_ratio": 0.9985,  # 99.85% intensity
        "half_life_years": 5.27,
        "background_region": (1210, 1260),
        "background_method": "linear",
        "related_peaks": ["Co-60 (1332 keV)"],
        "notes": "First Co-60 gamma. Always paired with 1332 keV.",
        "source": "NNDC ENSDF"
    },
    "Co-60 (1332 keV)": {
        "isotope": "Co-60",
        "energy_keV": 1332.5,
        "roi_window": (1290, 1370),
        "branching_ratio": 0.9998,  # 99.98% intensity
        "half_life_years": 5.27,
        "background_region": (1370, 1420),
        "background_method": "linear",
        "related_peaks": ["Co-60 (1173 keV)"],
        "notes": "Second Co-60 gamma. Always paired with 1173 keV.",
        "source": "NNDC ENSDF"
    },
    "Am-241 (60 keV)": {
        "isotope": "Am-241",
        "energy_keV": 59.5,
        "roi_window": (50, 70),
        "branching_ratio": 0.359,  # 35.9% intensity
        "half_life_years": 432.2,
        "background_region": (70, 85),
        "background_method": "compton",
        "related_peaks": [],
        "notes": "Low-energy calibration source. Common in smoke detectors.",
        "source": "NNDC ENSDF"
    },
    
    # === Natural Background ===
    "K-40 (1461 keV)": {
        "isotope": "K-40",
        "energy_keV": 1460.8,
        "roi_window": (1420, 1500),
        "branching_ratio": 0.1067,  # 10.67% intensity
        "half_life_years": 1.25e9,
        "background_region": (1500, 1550),
        "background_method": "linear",
        "related_peaks": [],
        "notes": "Natural potassium. Present in all living tissue.",
        "source": "IAEA NDS"
    },
    
    # === U-238 Daughters ===
    "Bi-214 (609 keV)": {
        "isotope": "Bi-214",
        "energy_keV": 609.3,
        "roi_window": (580, 640),
        "branching_ratio": 0.461,  # 46.1% intensity
        "half_life_years": 3.8e-5,  # 19.9 minutes
        "background_region": (640, 690),
        "background_method": "compton",
        "related_peaks": ["Bi-214 (1120 keV)", "Bi-214 (1764 keV)"],
        "notes": "Strongest U-238 chain indicator.",
        "source": "NNDC ENSDF"
    },
    "Pb-214 (352 keV)": {
        "isotope": "Pb-214",
        "energy_keV": 351.9,
        "roi_window": (330, 375),
        "branching_ratio": 0.371,  # 37.1% intensity
        "half_life_years": 5.1e-5,  # 26.8 minutes
        "background_region": (375, 410),
        "background_method": "compton",
        "related_peaks": ["Pb-214 (295 keV)"],
        "notes": "U-238 series marker.",
        "source": "NNDC ENSDF"
    },
}


def get_roi_isotope(name: str) -> Optional[Dict]:
    """Get ROI configuration for an isotope."""
    return ISOTOPE_ROI_DATABASE.get(name)


def get_roi_isotope_names() -> list:
    """Get list of available isotopes with ROI definitions."""
    return list(ISOTOPE_ROI_DATABASE.keys())


def get_roi_window(isotope_name: str) -> Optional[Tuple[float, float]]:
    """Get the ROI energy window for an isotope."""
    isotope = get_roi_isotope(isotope_name)
    return isotope["roi_window"] if isotope else None


def get_background_region(isotope_name: str) -> Optional[Tuple[float, float]]:
    """Get the background region for an isotope."""
    isotope = get_roi_isotope(isotope_name)
    return isotope["background_region"] if isotope else None
