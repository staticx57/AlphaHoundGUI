import xml.etree.ElementTree as ET
import numpy as np
import re

def parse_iso8601_duration(duration_str: str) -> float:
    """
    Parse ISO 8601 duration format (e.g., 'PT60.000S') to seconds.
    Returns 0.0 if parsing fails.
    """
    if not duration_str:
        return 0.0
    try:
        # Handle direct numeric values
        return float(duration_str)
    except ValueError:
        pass
    
    # Parse ISO 8601 duration format: PT[hours]H[minutes]M[seconds]S
    match = re.match(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?', duration_str)
    if match:
        hours = float(match.group(1) or 0)
        minutes = float(match.group(2) or 0)
        seconds = float(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds
    return 0.0

# Namespace configurations tried in turn: N42 2006, N42 2011, then no namespace at all
_NAMESPACES = [
    {'n42': 'http://physics.nist.gov/N42/2006/N42'},
    {'n42': 'http://physics.nist.gov/N42/2011/N42'},
    {},
]


def _find_element(element, paths, ns):
    """Try multiple paths to find an element."""
    for path in paths if isinstance(paths, list) else [paths]:
        if ns:
            result = element.find(path, ns)
        else:
            # no namespace: strip the prefix
            clean_path = path.replace('n42:', '')
            result = element.find(clean_path)
            if result is None:
                # also try the last path segment anywhere below
                result = element.find('.//' + clean_path.split('/')[-1])
        if result is not None:
            return result
    return None


def _find_text(element, paths, ns):
    """Try multiple paths to find element text."""
    elem = _find_element(element, paths, ns)
    return elem.text if elem is not None else None


def _find_spectrum(root):
    """The Spectrum element and the namespace configuration that found it (None, last configuration if there is none)."""
    spectrum = None
    ns = _NAMESPACES[-1]
    for ns in _NAMESPACES:
        spectrum = _find_element(root, ['.//n42:Spectrum', './/Spectrum'], ns)
        if spectrum is not None:
            break
    return spectrum, ns


def _find_in_spectrum_or_root(spectrum, root, name, ns):
    """An element looked for inside the Spectrum first, then anywhere in the document."""
    elem = _find_element(spectrum, [f'n42:{name}', name], ns)
    if elem is None:
        elem = _find_element(root, [f'.//n42:{name}', f'.//{name}'], ns)
    return elem


def _read_energies(spectrum, root, counts, ns):
    """The energy axis: a ChannelEnergies list, else polynomial coefficients; an empty list when there is neither."""
    energy_cal_elem = _find_in_spectrum_or_root(spectrum, root, 'EnergyCalibration', ns)
    energies = []
    if energy_cal_elem is not None:
        channel_energies_elem = _find_element(energy_cal_elem, ['n42:ChannelEnergies', 'ChannelEnergies'], ns)
        if channel_energies_elem is not None:
            energies = np.fromstring(channel_energies_elem.text, sep=' ', dtype=float)
        else:
            coefs_elem = _find_element(energy_cal_elem, ['n42:CoefficientValues', 'CoefficientValues', 'n42:Coefficients', 'Coefficients'], ns)
            if coefs_elem is not None:
                coefs = np.fromstring(coefs_elem.text, sep=' ', dtype=float)
                if len(coefs) >= 2:
                    channels = np.arange(len(counts))
                    energies = sum(c * (channels ** i) for i, c in enumerate(coefs))
    return energies


def _read_times(spectrum, rad_measurement, root, ns):
    """(live time s, real time s, start time text), each looked for in the places exporters put them."""
    live_time_str = _find_text(spectrum, ['n42:LiveTime', 'LiveTime'], ns)
    if not live_time_str and rad_measurement is not None:
        live_time_str = _find_text(rad_measurement, ['n42:LiveTime', 'LiveTime'], ns)

    real_time_str = None
    if rad_measurement is not None:
        real_time_str = _find_text(rad_measurement, ['n42:RealTime', 'RealTime'], ns)
    if not real_time_str:
        real_time_str = _find_text(spectrum, ['n42:RealTime', 'RealTime'], ns)
    if not real_time_str:
        real_time_str = _find_text(root, ['.//n42:RealTime', './/RealTime'], ns)

    start_time = None
    if rad_measurement is not None:
        start_time = _find_text(rad_measurement, ['n42:StartTime', 'StartTime'], ns)
    if not start_time:
        start_time = _find_text(root, ['.//n42:StartTime', './/StartTime', './/n42:MeasurementTime', './/MeasurementTime'], ns)
    return parse_iso8601_duration(live_time_str), parse_iso8601_duration(real_time_str), start_time


def _read_instrument(spectrum, root, ns):
    """(source label, manufacturer, model) from the instrument information, 'N42 File' when there is none."""
    instrument_elem = _find_element(spectrum, ['n42:InstrumentInformation', 'InstrumentInformation'], ns)
    if instrument_elem is None:
        instrument_elem = _find_element(root, ['.//n42:InstrumentInformation', './/InstrumentInformation',
                                               './/n42:RadInstrumentInformation', './/RadInstrumentInformation'], ns)
    source = "N42 File"
    manufacturer = None
    model = None
    if instrument_elem is not None:
        manufacturer = _find_text(instrument_elem, ['n42:Manufacturer', 'Manufacturer',
                                                    'n42:RadInstrumentManufacturerName', 'RadInstrumentManufacturerName'], ns)
        model = _find_text(instrument_elem, ['n42:Model', 'Model',
                                             'n42:RadInstrumentModelName', 'RadInstrumentModelName'], ns)
        if model:
            source = f"{manufacturer} {model}" if manufacturer else model
        elif manufacturer:
            source = manufacturer
    return source, manufacturer, model


def _read_acquisition(spectrum, ns):
    """Acquisition details written by n42_exporter (device duration, exposure, time notes)."""
    acquisition = {}
    info = _find_element(spectrum, ['.//n42:AcquisitionInfo', './/AcquisitionInfo'], ns)
    if info is not None:
        from formats.n42_exporter import ACQUISITION_FIELDS
        for key, (tag, numeric) in ACQUISITION_FIELDS.items():
            text = _find_text(info, [f'n42:{tag}', tag], ns)
            if text is None or not text.strip():
                continue
            try:
                acquisition[key] = float(text) if numeric else text.strip()
            except ValueError:
                pass
    return acquisition


def parse_n42(file_content: str):
    """
    Parses N42 XML content and returns a dictionary with spectrum data.
    Gracefully handles both standards-compliant and legacy/partial formats.
    """
    try:
        root = ET.fromstring(file_content)

        spectrum, ns = _find_spectrum(root)
        if spectrum is None:
            return {"error": "No Spectrum element found"}

        # RadMeasurement: the parent of Spectrum
        rad_measurement = _find_element(root, ['.//n42:RadMeasurement', './/RadMeasurement'], ns)

        channel_data_elem = _find_in_spectrum_or_root(spectrum, root, 'ChannelData', ns)
        if channel_data_elem is None:
            return {"error": "No ChannelData found"}
        counts = np.fromstring(channel_data_elem.text, sep=' ', dtype=int)

        energies = _read_energies(spectrum, root, counts, ns)
        live_time_val, real_time_val, start_time = _read_times(spectrum, rad_measurement, root, ns)
        source, manufacturer, model = _read_instrument(spectrum, root, ns)
        acquisition = _read_acquisition(spectrum, ns)

        # calibrated only when there is one energy per channel; otherwise channel numbers stand in
        is_calibrated = len(energies) > 0 and len(energies) == len(counts)
        if len(energies) == 0:
            energies = np.arange(len(counts)).tolist()

        return {
            "counts": counts.tolist(),
            "energies": energies.tolist() if isinstance(energies, np.ndarray) else energies,
            "is_calibrated": is_calibrated,
            "metadata": {
                "source": source,
                "live_time": live_time_val,
                "real_time": real_time_val,
                "start_time": start_time,
                "channels": len(counts),
                "manufacturer": manufacturer,
                "model": model,
                **acquisition
            }
        }

    except ET.ParseError as e:
        return {"error": f"XML Parse Error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected Error: {str(e)}"}
