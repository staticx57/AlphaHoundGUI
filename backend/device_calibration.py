"""
Energy-axis handling for AlphaHound spectra.

The AlphaHound streams ``count,energy`` for every channel, and its energy axis is
NONLINEAR (about 15 keV at channel 0, ~1.7 keV/ch at the low end, ~19 keV/ch at the
top, ~7572 keV at channel 1023). Replacing it with a linear axis shifts every peak
(e.g. Th-232 lines no longer match), so the device's own energies are used whenever
they are usable, with a linear fallback only as a last resort.
"""
import math
from typing import List, Sequence, Tuple

FALLBACK_KEV_PER_CHANNEL = 3.0
SOURCE_DEVICE = "device"
SOURCE_FALLBACK = "fallback_linear_3.0_keV_per_channel"


def energies_from_device_spectrum(spectrum: Sequence[Tuple[float, float]]) -> Tuple[List[float], str]:
    """
    Return (energies_keV, source) for a list of (count, energy) tuples from the device.

    ``source`` is SOURCE_DEVICE when the device-reported axis is valid (finite, strictly
    increasing, non-negative, spanning a positive range), otherwise SOURCE_FALLBACK.
    """
    n = len(spectrum)
    device = [float(e) for _, e in spectrum]
    valid = (
        n >= 2
        and all(math.isfinite(e) and e >= 0 for e in device)
        and all(b > a for a, b in zip(device, device[1:]))
    )
    if valid:
        return device, SOURCE_DEVICE
    return [i * FALLBACK_KEV_PER_CHANNEL for i in range(n)], SOURCE_FALLBACK


def fallback_warning() -> str:
    return ("Device did not report a valid energy axis; assumed a linear "
            f"{FALLBACK_KEV_PER_CHANNEL} keV/channel. Peak energies may be wrong - calibrate before identifying isotopes.")
