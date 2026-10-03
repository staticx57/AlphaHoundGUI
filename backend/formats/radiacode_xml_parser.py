"""
Parser for RadiaCode / BecqMoni XML spectrum exports (<ResultDataFile>).

This is the standard "Export spectrum" format of the RadiaCode apps:

    ResultDataFile/ResultDataList/ResultData
        DeviceConfigReference/Name        e.g. RadiaCode-103
        StartTime / EndTime
        EnergySpectrum
            SerialNumber
            EnergyCalibration/Coefficients/Coefficient  (a0, a1, a2: E = a0 + a1*ch + a2*ch^2)
            MeasurementTime                              (seconds)
            Spectrum/DataPoint                           (one count per channel)
        BackgroundEnergySpectrum                         (optional, ignored)
"""
import math
import xml.etree.ElementTree as ET


def is_radiacode_xml(text: str) -> bool:
    return "<ResultDataFile" in text[:2000]


def _text(node, path, default=None):
    el = node.find(path)
    return el.text.strip() if el is not None and el.text else default


def parse_radiacode_xml(text: str) -> dict:
    """Return the same shape as parse_n42(): counts, energies, is_calibrated, metadata (or {'error': ...})."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return {"error": f"Invalid RadiaCode XML: {e}"}

    result_data = root.find("./ResultDataList/ResultData")
    if result_data is None:
        return {"error": "RadiaCode XML has no ResultData"}
    spectrum = result_data.find("EnergySpectrum")
    if spectrum is None:
        return {"error": "RadiaCode XML has no EnergySpectrum"}

    try:
        counts = [float(dp.text) for dp in spectrum.findall("./Spectrum/DataPoint")]
    except (TypeError, ValueError):
        return {"error": "RadiaCode XML has non-numeric DataPoint values"}
    if not counts:
        return {"error": "RadiaCode XML has no Spectrum/DataPoint values"}

    try:
        coeffs = [float(c.text) for c in spectrum.findall("./EnergyCalibration/Coefficients/Coefficient")]
    except (TypeError, ValueError):
        coeffs = []
    coeffs = (coeffs + [0.0, 0.0, 0.0])[:3] if coeffs else []
    is_calibrated = bool(coeffs) and all(math.isfinite(c) for c in coeffs) and coeffs[1] > 0
    if is_calibrated:
        a0, a1, a2 = coeffs
        energies = [a0 + a1 * ch + a2 * ch * ch for ch in range(len(counts))]
    else:
        energies = list(range(len(counts)))

    measurement_time = _text(spectrum, "MeasurementTime")
    try:
        live_time = float(measurement_time) if measurement_time is not None else 0.0
    except ValueError:
        live_time = 0.0

    metadata = {
        "source": "RadiaCode XML",
        "instrument_model": _text(result_data, "./DeviceConfigReference/Name"),
        "serial_number": _text(spectrum, "SerialNumber"),
        "spectrum_name": _text(spectrum, "SpectrumName"),
        "start_time": _text(result_data, "StartTime"),
        "end_time": _text(result_data, "EndTime"),
        "live_time": live_time,
        "real_time": live_time,
        "channels": len(counts),
    }
    if is_calibrated:
        metadata["calibration"] = {"a0": coeffs[0], "a1": coeffs[1], "a2": coeffs[2]}

    return {
        "counts": counts,
        "energies": energies,
        "is_calibrated": is_calibrated,
        "metadata": metadata,
    }
