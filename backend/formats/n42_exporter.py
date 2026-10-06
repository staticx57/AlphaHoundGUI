"""
N42 XML Exporter for AlphaHoundGUI

Generates standards-compliant ANSI N42.42-2006 XML from spectrum data.
Compatible with AlphaHound device data and uploaded files.
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from typing import Dict, List


# Acquisition details carried in <SpectrumExtension><AcquisitionInfo> (not part of N42.42-2006, so
# readers that do not know the extension simply ignore it): metadata key -> (XML tag, numeric?)
ACQUISITION_FIELDS = {
    'device_duration_s': ('DeviceDurationS', True),
    'temperature_c': ('TemperatureC', True),
    'temperature_min_c': ('TemperatureMinC', True),
    'temperature_max_c': ('TemperatureMaxC', True),
    'compensation_factor': ('CompensationFactor', True),
    'exposure_uSv': ('ExposureUSv', True),
    'mean_dose_rate_uSv_h': ('MeanDoseRateUSvH', True),
    'max_dose_rate_uSv_h': ('MaxDoseRateUSvH', True),
    'exposure_covered_s': ('ExposureCoveredS', True),
    'mean_cps_gamma': ('MeanGammaCps', True),
    'mean_cps_beta': ('MeanBetaCps', True),
    'mean_cps_alpha': ('MeanAlphaCps', True),
    'max_cps_total': ('MaxTotalCps', True),
    'exposure_method': ('ExposureMethod', False),
    'exposure_during_acquisition': ('ExposureSummary', False),
    'time_notes': ('TimeNotes', False),
}


def instrument_from_metadata(metadata: dict) -> dict:
    """Best-effort {manufacturer, model, serial_number} from spectrum metadata."""
    import re
    metadata = metadata or {}
    model = metadata.get('instrument_model')
    source = str(metadata.get('source') or '')
    serial = metadata.get('serial_number') or 'UNKNOWN'
    if not model:
        m = re.search(r'\((RadiaCode-[^)]+)\)', source, re.IGNORECASE)
        if m:
            model = m.group(1)
        elif 'radiacode' in source.lower():
            model = 'RadiaCode'
    if model and 'radiacode' in str(model).lower():
        return {'manufacturer': 'RadiaCode', 'model': model, 'serial_number': serial}
    if model and 'alphahound' in str(model).lower():
        return {'manufacturer': metadata.get('instrument_manufacturer', 'RadView Detection'), 'model': model,
                'serial_number': serial}
    if model:
        return {'manufacturer': metadata.get('instrument_manufacturer', 'Unknown'), 'model': model,
                'serial_number': serial}
    return {}  # fall back to the AlphaHound defaults (this app's native device)


N42_NAMESPACE = "http://physics.nist.gov/N42/2006/N42"


def _prepare_export(spectrum_data: Dict) -> Dict:
    """Validate the input and resolve everything the XML needs: arrays, times (with their defaults) and instrument identity."""
    if 'counts' not in spectrum_data or 'energies' not in spectrum_data:
        raise ValueError("Missing required fields: 'counts' and 'energies'")

    counts = spectrum_data['counts']
    energies = spectrum_data['energies']
    metadata = spectrum_data.get('metadata', {})

    if len(counts) != len(energies):
        raise ValueError(f"Counts ({len(counts)}) and energies ({len(energies)}) arrays must have same length")

    live_time = metadata.get('live_time', 1.0)
    real_time = metadata.get('real_time', live_time)
    start_time = metadata.get('start_time') or datetime.now().isoformat()

    # Explicit instrument_info wins, otherwise derive it from the spectrum's metadata
    # (a RadiaCode spectrum must not be saved as an AlphaHound)
    instrument_info = spectrum_data.get('instrument_info') or instrument_from_metadata(metadata)
    return {
        'counts': counts,
        'energies': energies,
        'metadata': metadata,
        'live_time': live_time,
        'real_time': real_time,
        'start_time': start_time,
        'manufacturer': instrument_info.get('manufacturer', 'RadView Detection'),
        'model': instrument_info.get('model', 'AlphaHound'),
        'serial_number': instrument_info.get('serial_number', 'UNKNOWN'),
    }


ENERGY_CALIBRATION_ID = "EnergyCalibration-1"


def channel_edges(energies) -> List[float]:
    """The channel boundaries N42-2012 wants (EnergyBoundaryValues): halfway between neighbouring channel energies, the outer two extrapolated.
    One more value than there are channels."""
    energies = [float(e) for e in energies]
    return ([energies[0] - (energies[1] - energies[0]) / 2] + [(a + b) / 2 for a, b in zip(energies, energies[1:])]
            + [energies[-1] + (energies[-1] - energies[-2]) / 2])


def _build_tree(prepared: Dict, spectrum_data: Dict) -> ET.Element:
    """The N42 element tree: measurement times, the spectrum with its calibration, the instrument and the optional extension."""
    ET.register_namespace('', N42_NAMESPACE)
    root = ET.Element('RadInstrumentData', {'xmlns': N42_NAMESPACE})
    # The calibration as N42-2012 states it, for other software (InterSpec / SpecUtils ignored the List/ChannelEnergies pair below and showed
    # a default 0-3000 keV axis): an identified EnergyCalibration with channel boundaries halfway between the channel energies
    energies = [float(e) for e in prepared['energies']]
    if len(energies) > 1:
        edges = channel_edges(energies)
        standard_cal = ET.SubElement(root, "EnergyCalibration", id=ENERGY_CALIBRATION_ID)
        ET.SubElement(standard_cal, "EnergyBoundaryValues").text = " ".join(f"{e:.5f}" for e in edges)
    rad_measurement = ET.SubElement(root, "RadMeasurement")

    ET.SubElement(rad_measurement, "MeasurementClassCode").text = "Foreground"
    ET.SubElement(rad_measurement, "StartTime").text = str(prepared['start_time'])
    ET.SubElement(rad_measurement, "RealTime").text = f"PT{prepared['real_time']:.3f}S"   # ISO 8601 duration

    spectrum = ET.SubElement(rad_measurement, "Spectrum")
    if len(energies) > 1:
        spectrum.set("energyCalibrationReference", ENERGY_CALIBRATION_ID)
    ET.SubElement(spectrum, "LiveTime").text = f"PT{prepared['live_time']:.3f}S"

    energy_cal = ET.SubElement(spectrum, "EnergyCalibration")
    ET.SubElement(energy_cal, "CalibrationEquation").text = "List"   # full channel-to-energy mapping
    ET.SubElement(energy_cal, "ChannelEnergies").text = " ".join(f"{e:.5f}" for e in prepared['energies'])

    channel_data = ET.SubElement(spectrum, "ChannelData", NumberOfChannels=str(len(prepared['counts'])))
    channel_data.text = " ".join(str(int(c)) for c in prepared['counts'])
    ET.SubElement(spectrum, "SpectrumType").text = "PHA"   # pulse height analysis

    instrument = ET.SubElement(spectrum, "InstrumentInformation")
    ET.SubElement(instrument, "Manufacturer").text = str(prepared['manufacturer'])
    ET.SubElement(instrument, "Model").text = str(prepared['model'])
    ET.SubElement(instrument, "SerialNumber").text = str(prepared['serial_number'])

    # Optional extension data: acquisition details and isotope identification results
    metadata = prepared['metadata']
    isotopes = spectrum_data.get('isotopes') or []
    acquisition = {k: metadata[k] for k in ACQUISITION_FIELDS if metadata.get(k) not in (None, '')}
    if isotopes or acquisition:
        extension = ET.SubElement(spectrum, "SpectrumExtension")
        if acquisition:
            _add_acquisition_info(extension, acquisition)
        if isotopes:
            _add_isotope_identification(extension, isotopes)
    return root


def _pretty_print(root: ET.Element) -> str:
    """Indented XML without the blank lines minidom adds."""
    pretty_xml = minidom.parseString(ET.tostring(root, encoding='unicode')).toprettyxml(indent="  ")
    return '\n'.join(line for line in pretty_xml.split('\n') if line.strip())


def generate_n42_xml(spectrum_data: Dict) -> str:
    """
    Generate N42-compliant XML from spectrum data.

    Args:
        spectrum_data: Dictionary containing:
            - counts: list[int] - Channel counts
            - energies: list[float] - Energy calibration (keV)
            - metadata: dict with optional fields:
                - live_time: float (seconds)
                - real_time: float (seconds)
                - start_time: str (ISO 8601) or None
                - source: str (data source description)
                - channels: int
            - peaks: list[dict] (optional)
            - isotopes: list[dict] (optional)
            - instrument_info: dict (optional):
                - manufacturer: str
                - model: str
                - serial_number: str

    Returns:
        str: Formatted N42 XML string

    Raises:
        ValueError: If required fields are missing
    """
    prepared = _prepare_export(spectrum_data)
    return _pretty_print(_build_tree(prepared, spectrum_data))


def _add_acquisition_info(extension: ET.Element, values: Dict):
    """Write the ACQUISITION_FIELDS present in values under <AcquisitionInfo>."""
    info = ET.SubElement(extension, "AcquisitionInfo")
    for key, (tag, numeric) in ACQUISITION_FIELDS.items():
        if key in values:
            ET.SubElement(info, tag).text = repr(float(values[key])) if numeric else str(values[key])


def _add_isotope_identification(extension: ET.Element, isotopes: List[Dict]):
    """
    Add isotope identification results to the SpectrumExtension (non-standard but useful).
    
    Args:
        extension: SpectrumExtension XML element
        isotopes: List of identified isotopes with confidence scores
    """
    for isotope in isotopes[:10]:  # Limit to top 10
        isotope_id = ET.SubElement(extension, "IsotopeIdentification")
        
        name = ET.SubElement(isotope_id, "IsotopeName")
        name.text = str(isotope.get('isotope', 'Unknown'))
        
        confidence = ET.SubElement(isotope_id, "Confidence")
        confidence.text = str(isotope.get('confidence', 'Unknown'))
        
        if 'energy' in isotope:
            energy = ET.SubElement(isotope_id, "EnergyKeV")
            energy.text = str(isotope['energy'])


def validate_n42_structure(xml_string: str) -> bool:
    """
    Basic validation that XML is well-formed and has required N42 elements.
    
    Args:
        xml_string: N42 XML string to validate
    
    Returns:
        bool: True if valid structure
    
    Raises:
        ValueError: If validation fails with reason
    """
    try:
        root = ET.fromstring(xml_string)
        
        # Check root element
        if 'RadInstrumentData' not in root.tag:
            raise ValueError("Root element must be RadInstrumentData")
        
        # Check for required measurement
        ns = {'n42': 'http://physics.nist.gov/N42/2006/N42'}
        rad_meas = root.find('n42:RadMeasurement', ns)
        if rad_meas is None:
            raise ValueError("Missing RadMeasurement element")
        
        # Check for spectrum
        spectrum = rad_meas.find('n42:Spectrum', ns)
        if spectrum is None:
            raise ValueError("Missing Spectrum element")
        
        # Check for channel data
        channel_data = spectrum.find('n42:ChannelData', ns)
        if channel_data is None:
            raise ValueError("Missing ChannelData element")
        
        return True
        
    except ET.ParseError as e:
        raise ValueError(f"XML parsing failed: {e}")
