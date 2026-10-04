"""
Spectrum export to formats other programs read, through SpecUtils (the library behind InterSpec): PCF (GADRAS) and CHN (Ortec).

Both store the energy calibration as a polynomial, so the lowest-degree polynomial that reproduces the application's energy axis
is fitted (the AlphaHound's axis is a cubic: a quadratic is 293 keV off). PCF holds a cubic; CHN holds only three coefficients, so
it refuses an axis a quadratic cannot reproduce rather than write a file that is wrong by keV. SpecUtils also offers deviation
pairs, but PCF converts the calibration to a full-range fraction on writing and the pairs come back wrong (measured: an axis 9 keV
off a quadratic reads back 11.7 keV off with them, 9.0 keV without), so they are not used. The error left is measured on the
calibration SpecUtils actually builds, and reported, never hidden.
"""
import datetime
import os
import tempfile
from typing import Dict, List, Optional

import numpy as np

try:
    import SpecUtils
    HAS_SPECUTILS = True
except ImportError:
    HAS_SPECUTILS = False

FORMATS = {
    # key: (SaveSpectrumAsType member, file extension, highest polynomial degree the file holds, largest error accepted in keV)
    "pcf": ("Pcf", ".pcf", 3, None),
    "chn": ("Chn", ".chn", 2, 1.0),
}
# a polynomial that is off by less than this (keV) is exact enough: no higher degree is tried
EXACT_ENOUGH_KEV = 0.05


class SpectrumExportError(ValueError):
    """The request cannot be written as a spectrum file (the caller's fault, not the server's)."""


class SpecUtilsUnavailable(RuntimeError):
    """The SpecUtils library is not installed on this server."""


def fit_calibration(energies: Optional[List[float]], channels: int, max_degree: int = 3) -> Dict:
    """
    The lowest-degree polynomial (up to max_degree) that reproduces the energy axis, and the largest error left on any channel,
    measured on the calibration SpecUtils builds from it (single precision, and it may refuse a polynomial that is not increasing).
    With no energy axis the channels themselves are the axis.
    """
    if not energies:
        return {"coefficients": [0.0, 1.0], "max_error_kev": 0.0, "calibrated": False}
    axis = np.asarray(energies, dtype=float)
    if axis.shape != (channels,) or not np.all(np.isfinite(axis)):
        raise SpectrumExportError("The energy axis must have one finite value per channel")
    if channels < 4 or float(np.ptp(axis)) == 0.0:
        raise SpectrumExportError("The energy axis does not span a range")
    index = np.arange(channels)
    best = None
    for degree in range(1, max_degree + 1):
        coefficients = [float(x) for x in np.polyfit(index, axis, degree)[::-1]]       # ascending: a0 + a1*x + a2*x^2 ...
        try:
            built = SpecUtils.EnergyCalibration.fromPolynomial(channels, coefficients)
        except RuntimeError:
            continue                                                                    # e.g. not increasing across the channels
        error = float(np.abs(np.asarray(built.channelEnergies())[:channels] - axis).max())
        if best is None or error < best["max_error_kev"]:
            best = {"coefficients": coefficients, "max_error_kev": error}
        if error <= EXACT_ENOUGH_KEV:
            break
    if best is None:
        raise SpectrumExportError(f"No polynomial of degree {max_degree} or lower reproduces this energy axis as an increasing calibration")
    best["calibrated"] = not bool(np.allclose(axis, index))
    return best


def _start_time(value) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def export_spectrum(data: Dict, fmt: str) -> Dict:
    """
    Write the spectrum in `data` (counts, energies, metadata with live_time/real_time/start_time/source) as PCF or CHN.

    Returns {"content": bytes, "extension": str, "calibration_max_error_kev": float, "calibrated": bool}.
    """
    if not HAS_SPECUTILS:
        raise SpecUtilsUnavailable("SpecUtils is not installed")
    if fmt not in FORMATS:
        raise SpectrumExportError(f"Unsupported export format: {fmt}")
    member, extension, max_degree, largest_error = FORMATS[fmt]

    counts = data.get("counts") or []
    if len(counts) < 3:
        raise SpectrumExportError("A spectrum needs at least three channels")
    metadata = data.get("metadata") or {}
    live = float(metadata.get("live_time") or metadata.get("acquisition_time") or 0.0)
    real = float(metadata.get("real_time") or metadata.get("acquisition_time") or live)
    try:
        cal = fit_calibration(data.get("energies"), len(counts), max_degree)
    except SpectrumExportError as e:
        raise SpectrumExportError(f"{e}. Export it as PCF or N42 instead." if max_degree < 3 else str(e))
    if largest_error is not None and cal["max_error_kev"] > largest_error:
        raise SpectrumExportError(
            f"{fmt.upper()} can only store a degree-{max_degree} energy calibration, which is up to {cal['max_error_kev']:.1f} keV off "
            f"this spectrum's energy axis. Export it as PCF or N42 instead.")

    measurement = SpecUtils.Measurement()
    measurement.setGammaCounts([float(c) for c in counts], live, real)
    measurement.setEnergyCalibration(SpecUtils.EnergyCalibration.fromPolynomial(len(counts), cal["coefficients"]))
    measurement.setSourceType(SpecUtils.SourceType.Foreground)
    title = str(data.get("filename") or metadata.get("filename") or metadata.get("source") or "spectrum")
    measurement.setTitle(title[:60])
    started = _start_time(metadata.get("start_time"))
    if started:
        measurement.setStartTime(started)

    spec_file = SpecUtils.SpecFile()
    spec_file.addMeasurement(measurement, True)
    if metadata.get("source"):
        spec_file.setInstrumentModel(str(metadata["source"]))

    with tempfile.TemporaryDirectory() as folder:           # SpecUtils will not overwrite, so it needs a path that does not exist yet
        path = os.path.join(folder, "spectrum" + extension)
        spec_file.writeToFile(path, list(spec_file.sampleNumbers()), list(spec_file.detectorNames()),
                              getattr(SpecUtils.SaveSpectrumAsType, member))
        with open(path, "rb") as f:
            content = f.read()

    return {"content": content, "extension": extension, "calibration_max_error_kev": cal["max_error_kev"],
            "calibrated": cal["calibrated"]}
