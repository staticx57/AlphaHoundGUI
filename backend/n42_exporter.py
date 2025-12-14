"""
N42 XML Exporter for AlphaHoundGUI

Generates standards-compliant ANSI N42.42-2006 XML from spectrum data.
Compatible with AlphaHound device data and uploaded files.
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from typing import Dict, List, Optional


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
    
    # Instrument information
    instrument_info = spectrum_data.get('instrument_info', {})
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
    
    # Optional: Add isotope identification results as custom data
    if 'isotopes' in spectrum_data and spectrum_data['isotopes']:
        _add_isotope_identification(spectrum, spectrum_data['isotopes'])
    
    # Format XML with pretty printing
    xml_string = ET.tostring(root, encoding='unicode')
    dom = minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent="  ")
    
    # Remove extra blank lines (minidom adds them)
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    return '\n'.join(lines)


def _add_isotope_identification(spectrum_elem: ET.Element, isotopes: List[Dict]):
    """
    Add isotope identification results as extension data (non-standard but useful).
    
    Args:
        spectrum_elem: Spectrum XML element
        isotopes: List of identified isotopes with confidence scores
    """
    # Create extension element for custom data
    extension = ET.SubElement(spectrum_elem, "SpectrumExtension")
    
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
