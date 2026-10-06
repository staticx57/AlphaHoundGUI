"""
Energy axes of known detector families, for spectra that arrive as channel numbers only (a community CSV with `Data,Energy` whose Energy column is
0, 1, 2 ..., a CHN or SPE without a calibration).

A preset is a polynomial, energy = a0 + a1 * channel + a2 * channel^2 + ..., good for the detector family and approximate for a unit: the
six RadiaCode calibrations measured here differ from the preset by up to 11 keV below 300 keV and by up to 2.6 % above (a1 2.35-2.47 keV/channel,
a0 from -11 to +8 keV), and AlphaHound axes differ between units. That is close enough to start the identification, and the automatic axis correction (auto_calibration.py) refines what is left. Nothing here
claims to be a unit's own calibration: a file that carries one is always used as it is.

`suggest` ranks the presets by how well the spectrum fits the known-source templates on each axis, so the page can preselect the right one: two
real community captures of a RadiaCode (a 9-hour uranium glass, a 14-hour radium dial) read U-238 at 95 % and 83 % on the RadiaCode preset and nothing
useful on the AlphaHound one.
"""
from typing import Dict, List, Optional, Sequence

# Measured, not assumed:
#  AlphaHound: a cubic through the axis the unit sent (tests/data/real_spectra/spectrum_2025-12-12_08-41-27.csv); max error 0.0 keV over 1024 channels.
#  RadiaCode: close to the mean of the six distinct calibrations in the 26 RadiaCode spectra in tests/data (a0 -11.4..+8.1, a1 2.35..2.47, a2 3.6e-4..4.4e-4).
PRESETS: List[Dict] = [
    {"key": "radiacode", "name": "RadiaCode 102 / 103 / 110 (typical axis, 1024 channels)", "channels": 1024,
     "coefficients": [0.0, 2.38, 4.0e-4], "detector": "Radiacode 103",
     "note": "Units differ from this by up to 11 keV at low energies and up to 3 % at high ones; the automatic axis correction refines the rest."},
    {"key": "alphahound", "name": "AlphaHound (typical axis, 1024 channels)", "channels": 1024,
     "coefficients": [15.0001, 1.68372, -4.75865e-05, 5.49654e-06], "detector": "AlphaHound CsI(Tl)",
     "note": "The axis of the unit it was measured on, 15 to 7572 keV, a cubic in the channel; axes differ between units."},
]

MAX_DEGREE = 5


def energies(coefficients: Sequence[float], channels: int) -> List[float]:
    """energy = sum(a_k * channel^k) for channel 0 .. channels-1; raises ValueError for a bad polynomial or one that is not increasing."""
    coefficients = [float(c) for c in coefficients]
    if not coefficients or len(coefficients) > MAX_DEGREE + 1:
        raise ValueError(f"give 1 to {MAX_DEGREE + 1} coefficients")
    if channels < 2:
        raise ValueError("fewer than two channels")
    axis = []
    for channel in range(channels):
        value = 0.0
        for coefficient in reversed(coefficients):          # Horner
            value = value * channel + coefficient
        axis.append(value)
    if any(b <= a for a, b in zip(axis, axis[1:])):
        raise ValueError("the energies do not increase with the channel")
    if axis[-1] <= 0:
        raise ValueError("the last channel has no positive energy")
    return axis


def linear(kev_per_channel: float, offset_kev: float = 0.0) -> List[float]:
    """Coefficients of a straight axis."""
    return [float(offset_kev), float(kev_per_channel)]


def preset(key: str) -> Optional[Dict]:
    return next((p for p in PRESETS if p["key"] == key), None)


def presets_for(channels: int) -> List[Dict]:
    """The presets that describe a spectrum of this many channels."""
    return [p for p in PRESETS if p["channels"] == channels]


def suggest(counts: Sequence[float]) -> List[Dict]:
    """
    The presets for this channel count, best first: {key, name, score, source}. The score is the significance (z) of the best-fitting known source
    on that axis (source_templates.fit_source_templates); 0 when nothing fits or the fit is not possible. The caller decides what a score
    is worth: below ~10 no source is present on that axis.
    """
    from spectroscopy.source_templates import fit_source_templates
    ranked = []
    for p in presets_for(len(counts)):
        try:
            fit = fit_source_templates(energies(p["coefficients"], len(counts)), list(counts), {"detector": p["detector"]})
        except Exception:
            fit = None
        best = max(((v["z"], k) for k, v in (fit or {}).get("sources", {}).items()), default=(0.0, None))
        ranked.append({"key": p["key"], "name": p["name"], "score": round(float(best[0]), 1), "source": best[1]})
    return sorted(ranked, key=lambda r: -r["score"])
