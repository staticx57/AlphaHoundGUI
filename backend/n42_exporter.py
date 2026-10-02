"""
N42 XML Exporter for AlphaHoundGUI

Generates standards-compliant ANSI N42.42-2006 XML from spectrum data.
Compatible with AlphaHound device data and uploaded files.
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from typing import Dict, List, Optional


# Acquisition details carried in <SpectrumExtension><AcquisitionInfo> (not part of N42.42-2006, so
# readers that do not know the extension simply ignore it): metadata key -> (XML tag, numeric?)
ACQUISITION_FIELDS = {
    'device_duration_s': ('DeviceDurationS', True),
    'exposure_uSv': ('ExposureUSv', True),
    'mean_dose_rate_uSv_h': ('MeanDoseRateUSvH', True),
    'max_dose_rate_uSv_h': ('MaxDoseRateUSvH', True),
    'exposure_covered_s': ('ExposureCoveredS', True),
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
    if model:
        return {'manufacturer': metadata.get('instrument_manufacturer', 'Unknown'), 'model': model,
                'serial_number': serial}
    return {}  # fall back to the AlphaHound defaults (this app's native device)


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
    # Validate required fields
    if 'counts' not in spectrum_data or 'energies' not in spectrum_data:
        raise ValueError("Missing required fields: 'counts' and 'energies'")
    
    counts = spectrum_data['counts']
    energies = spectrum_data['energies']
    metadata = spectrum_data.get('metadata', {})
    
    if len(counts) != len(energies):
        raise ValueError(f"Counts ({len(counts)}) and energies ({len(energies)}) arrays must have same length")
    
    n_channels = len(counts)
    
    # Extract metadata with defaults
    live_time = metadata.get('live_time', 1.0)
    real_time = metadata.get('real_time', live_time)
    start_time = metadata.get('start_time') or datetime.now().isoformat()
    
    # Instrument information: explicit instrument_info wins, otherwise derive it from the
    # spectrum's metadata (a RadiaCode spectrum must not be saved as an AlphaHound)
    instrument_info = spectrum_data.get('instrument_info') or instrument_from_metadata(metadata)
    manufacturer = instrument_info.get('manufacturer', 'RadView Detection')
    model = instrument_info.get('model', 'AlphaHound')
    serial_number = instrument_info.get('serial_number', 'UNKNOWN')
    
    # Create XML structure with namespace
    ns = "http://physics.nist.gov/N42/2006/N42"
    ET.register_namespace('', ns)
    
    # Root element (standards-compliant)
    root = ET.Element('RadInstrumentData', {'xmlns': ns})
    
    # RadMeasurement container
    rad_measurement = ET.SubElement(root, "RadMeasurement")
    
    # Measurement metadata
    meas_class = ET.SubElement(rad_measurement, "MeasurementClassCode")
    meas_class.text = "Foreground"
    
    start_time_elem = ET.SubElement(rad_measurement, "StartTime")
    start_time_elem.text = str(start_time)
    
    real_time_elem = ET.SubElement(rad_measurement, "RealTime")
    real_time_elem.text = f"PT{real_time:.3f}S"  # ISO 8601 duration format
    
    # Spectrum element
    spectrum = ET.SubElement(rad_measurement, "Spectrum")
    
    # LiveTime
    live_time_elem = ET.SubElement(spectrum, "LiveTime")
    live_time_elem.text = f"PT{live_time:.3f}S"
    
    # Energy Calibration
    energy_cal = ET.SubElement(spectrum, "EnergyCalibration")
    cal_equation = ET.SubElement(energy_cal, "CalibrationEquation")
    cal_equation.text = "List"  # Full channel-to-energy mapping
    
    channel_energies = ET.SubElement(energy_cal, "ChannelEnergies")
    channel_energies.text = " ".join(f"{e:.5f}" for e in energies)
    
    # Channel Data
    channel_data = ET.SubElement(spectrum, "ChannelData", 
                                 NumberOfChannels=str(n_channels))
    channel_data.text = " ".join(str(int(c)) for c in counts)
    
    # Spectrum Type
    spectrum_type = ET.SubElement(spectrum, "SpectrumType")
    spectrum_type.text = "PHA"  # Pulse Height Analysis
    
    # Instrument Information
    instrument = ET.SubElement(spectrum, "InstrumentInformation")
    
    manuf = ET.SubElement(instrument, "Manufacturer")
    manuf.text = str(manufacturer)
    
    model_elem = ET.SubElement(instrument, "Model")
    model_elem.text = str(model)
    
    serial = ET.SubElement(instrument, "SerialNumber")
    serial.text = str(serial_number)
    
    # Optional extension data: acquisition details and isotope identification results
    isotopes = spectrum_data.get('isotopes') or []
    acquisition = {k: metadata[k] for k in ACQUISITION_FIELDS if metadata.get(k) not in (None, '')}
    if isotopes or acquisition:
        extension = ET.SubElement(spectrum, "SpectrumExtension")
        if acquisition:
            _add_acquisition_info(extension, acquisition)
        if isotopes:
            _add_isotope_identification(extension, isotopes)
    
    # Format XML with pretty printing
    xml_string = ET.tostring(root, encoding='unicode')
    dom = minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent="  ")
    
    # Remove extra blank lines (minidom adds them)
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    return '\n'.join(lines)


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
