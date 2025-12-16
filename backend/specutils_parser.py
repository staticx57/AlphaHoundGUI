
"""
SandiaSpecUtils Parser Wrapper
"""
import os
import logging
from typing import Dict, List, Optional, Tuple

# Try to import SandiaSpecUtils
try:
    import SandiaSpecUtils
    HAS_SPECUTILS = True
except ImportError:
    HAS_SPECUTILS = False

logger = logging.getLogger(__name__)

def is_supported_format(filename: str) -> bool:
    """Check if file extension is supported by generic parser."""
    ext = os.path.splitext(filename)[1].lower()
    # List of formats SandiaSpecUtils typically supports
    # N42, CNF, SPC, CHN, DAT, SPE, etc.
    supported = [
        '.n42', '.cnf', '.spc', '.chn', '.dat', '.spe', 
        '.mca', '.pcf', '.tka', '.xml', '.csv'
    ]
    return ext in supported

def parse_spectrum_generic(file_path: str) -> Optional[Dict]:
    """
    Parse a spectrum file using SandiaSpecUtils.
    
    Returns standard dictionary:
    {
        "counts": List[int],
        "energy_calibration": {
            "slope": float,
            "intercept": float,
            "quadratic": float
        },
        "live_time": float,
        "real_time": float,
        "start_time": str,
        "metadata": Dict
    }
    """
    if not HAS_SPECUTILS:
        logger.warning("SandiaSpecUtils not installed")
        return None

    try:
        # Load spectrum
        # Note: SpecUtils might return a list of spectra or a single object
        spectrum = SandiaSpecUtils.Spectrum(file_path)
        
        # Determine attributes (API variation handling)
        counts = getattr(spectrum, 'Counts', [])
        live_time = getattr(spectrum, 'LiveTime', 0.0)
        real_time = getattr(spectrum, 'RealTime', 0.0)
        start_time = getattr(spectrum, 'StartTime', "")
        
        # Energy Calibration
        # Usually stored as Coefficients [intercept, slope, quad]
        coeffs = getattr(spectrum, 'EnergyCoefficients', [0, 1, 0])
        calibration = {
            "intercept": coeffs[0] if len(coeffs) > 0 else 0,
            "slope": coeffs[1] if len(coeffs) > 1 else 1,
            "quadratic": coeffs[2] if len(coeffs) > 2 else 0
        }
        
        # Metadata
        metadata = {
            "sample_id": getattr(spectrum, 'SampleID', "Unknown"),
            "operator": getattr(spectrum, 'Operator', "Unknown"),
            "description": getattr(spectrum, 'Description', ""),
            "detector_id": getattr(spectrum, 'DetectorID', "")
        }
        
        return {
            "counts": list(counts),
            "energy_calibration": calibration,
            "live_time": float(live_time),
            "real_time": float(real_time),
            "start_time": str(start_time),
            "metadata": metadata
        }
        
    except Exception as e:
        logger.error(f"Failed to parse with SandiaSpecUtils: {e}")
        return None
