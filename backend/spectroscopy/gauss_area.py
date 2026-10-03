"""
Gaussian peak areas in COUNTS.

The peak fits here run against an energy axis in keV on data that is counts per CHANNEL. For a Gaussian
A * exp(-(E - E0)^2 / (2 s^2)) sampled every `w` keV, the counts in the peak are the sum over channels, which is
A * s * sqrt(2 pi) / w, not A * s * sqrt(2 pi) (that integral is in counts * keV per channel). Writing the area as
A * s * sqrt(2 pi) overstated every fitted net area (and its uncertainty) by the channel width, about 2 to 3 for the supported
instruments. These helpers keep the conversion in one place.
"""

import numpy as np

def channel_width_kev(energies) -> float:
    """Typical channel width (keV per channel) of an energy axis; 1.0 if it cannot be determined."""
    x = np.asarray(energies, dtype=float)
    if x.size < 2:
        return 1.0
    steps = np.diff(x)
    steps = steps[steps > 0]
    return float(np.median(steps)) if steps.size else 1.0
