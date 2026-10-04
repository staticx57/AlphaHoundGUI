"""
Reader for the spectrum formats SpecUtils understands (PCF, SPC, CNF, TKA, N42 variants and many more).

SpecUtils is the Sandia library behind InterSpec. The pip package is called SandiaSpecUtils, but the module it installs is
`SpecUtils`; importing the package name (as this file once did) always failed, so none of these formats could be uploaded.
"""
import logging
import os
from typing import Dict, Optional

import numpy as np

try:
    import SpecUtils
    HAS_SPECUTILS = True
except ImportError:
    HAS_SPECUTILS = False

logger = logging.getLogger(__name__)

# Calibration models that mean "the file does not say": the energies are then not real keV
_NO_CALIBRATION = ('InvalidEquationType', 'UnspecifiedUsingDefaultPolynomial')


def _gamma_measurements(spec_file):
    """The spectra to total: the foreground ones if the file separates them from background, else all of them."""
    usable = [m for m in spec_file.measurements() if m.numGammaChannels() > 1]
    foreground = [m for m in usable if m.sourceType() != SpecUtils.SourceType.Background]
    return foreground or usable


def parse_spectrum_generic(file_path: str) -> Optional[Dict]:
    """
    Read any spectrum file SpecUtils can; None if the library is missing or the file is not a spectrum.

    A file with several spectra (time slices, detectors) is totalled, provided they share a channel count; the energy
    calibration is the first spectrum's. Returns the same shape the other parsers do:
    counts, energies (None when the file carries no calibration), energy_calibration (slope/intercept/quadratic),
    live_time, real_time, start_time and metadata.
    """
    if not HAS_SPECUTILS:
        logger.warning("SandiaSpecUtils not installed")
        return None

    try:
        spec_file = SpecUtils.SpecFile()
        spec_file.loadFile(file_path, SpecUtils.ParserType.Auto, os.path.splitext(file_path)[1])
        measurements = _gamma_measurements(spec_file)
        if not measurements:
            return None

        first = measurements[0]
        channels = first.numGammaChannels()
        same_size = [m for m in measurements if m.numGammaChannels() == channels]
        counts = np.sum([np.asarray(m.gammaCounts(), dtype=float) for m in same_size], axis=0)
        live_time = sum(m.liveTime() for m in same_size)
        real_time = sum(m.realTime() for m in same_size)

        energies = None
        calibration = {"slope": 1, "intercept": 0, "quadratic": 0}
        if first.energyCalibrationModel().name not in _NO_CALIBRATION:
            energies = [float(e) for e in first.channelEnergies()[:channels]]     # lower channel edges, as polynomial(channel)
            quadratic, slope, intercept = np.polyfit(np.arange(channels), energies, 2)
            calibration = {"slope": float(slope), "intercept": float(intercept), "quadratic": float(quadratic)}

        metadata = {
            "title": first.title(),
            "instrument_model": spec_file.instrumentModel(),
            "manufacturer": spec_file.manufacturer(),
            "spectra_totalled": len(same_size),
        }
        return {
            "counts": [int(round(c)) if float(c).is_integer() else float(c) for c in counts],
            "energies": energies,
            "energy_calibration": calibration,
            "live_time": float(live_time),
            "real_time": float(real_time),
            "start_time": str(first.startTime()),
            "metadata": metadata,
        }

    except Exception as e:
        logger.error(f"Failed to read {file_path} with SpecUtils: {e}")
        return None
