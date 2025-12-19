"""
N42 Metadata Editor Module

Provides functionality to edit and inject metadata into N42 XML files.
Handles timestamps, sample info, operator details, and other standard N42.42 fields.
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from typing import Dict, Optional, List
import copy


class N42MetadataEditor:
    """
    Editor for N42 XML file metadata.
    
    Supports reading, modifying, and writing N42 metadata fields including:
    - Timestamps (StartTime, RealTime, LiveTime)
    - Instrument information (Manufacturer, Model, SerialNumber)
    - Sample information (MeasuredItemDescription)
    - Geographic location (GeoLocation)
    - Remarks/Comments
    - Operator information
    """
    
    # Standard N42.42 namespace
    NS = "http://physics.nist.gov/N42/2006/N42"
    
    def __init__(self, xml_content: str = None):
        """
        Initialize editor with optional existing N42 XML content.
        
        Args:
            xml_content: Existing N42 XML string to edit, or None for new
        """
        self.original_content = xml_content
        self.tree = None
        self.root = None
        
        if xml_content:
            self._parse(xml_content)
    
    def _parse(self, content: str):
        """Parse N42 XML content."""
        ET.register_namespace('', self.NS)
        self.root = ET.fromstring(content)
        self.tree = ET.ElementTree(self.root)
    
    def get_current_metadata(self) -> Dict:
        """
        Extract current metadata from the N42 file.
        
        Returns:
            Dict with all readable metadata fields
        """
        if self.root is None:
            return {}
        
        metadata = {}
        ns = {'n42': self.NS}
        
        # Find RadMeasurement
        rad_meas = self.root.find('.//n42:RadMeasurement', ns)
        if rad_meas is None:
            rad_meas = self.root.find('.//RadMeasurement')
        
        if rad_meas is not None:
            # StartTime
            start = rad_meas.find('n42:StartTime', ns)
            if start is None:
                start = rad_meas.find('StartTime')
            if start is not None:
                metadata['start_time'] = start.text
            
            # RealTime
            real = rad_meas.find('n42:RealTime', ns)
            if real is None:
                real = rad_meas.find('RealTime')
            if real is not None:
                metadata['real_time'] = real.text
            
            # MeasurementClassCode
            mcc = rad_meas.find('n42:MeasurementClassCode', ns)
            if mcc is None:
                mcc = rad_meas.find('MeasurementClassCode')
            if mcc is not None:
                metadata['measurement_class'] = mcc.text
        
        # Find Spectrum for LiveTime
        spectrum = self.root.find('.//n42:Spectrum', ns)
        if spectrum is None:
            spectrum = self.root.find('.//Spectrum')
        
        if spectrum is not None:
            live = spectrum.find('n42:LiveTime', ns)
            if live is None:
                live = spectrum.find('LiveTime')
            if live is not None:
                metadata['live_time'] = live.text
        
        # Instrument Info
        inst = self.root.find('.//n42:InstrumentInformation', ns)
        if inst is None:
            inst = self.root.find('.//InstrumentInformation')
        
        if inst is not None:
            for field in ['Manufacturer', 'Model', 'SerialNumber']:
                elem = inst.find(f'n42:{field}', ns) or inst.find(field)
                if elem is not None:
                    metadata[field.lower()] = elem.text
        
        # Remarks
        for remark in self.root.findall('.//n42:Remark', ns) + self.root.findall('.//Remark'):
            if remark.text:
                metadata.setdefault('remarks', []).append(remark.text)
        
        return metadata
    
    def set_timestamp(self, timestamp: datetime = None):
        """
        Set or update the StartTime field.
        
        Args:
            timestamp: Datetime object (defaults to now if None)
        """
        if self.root is None:
            return
        
        if timestamp is None:
            timestamp = datetime.now()
        
        ns = {'n42': self.NS}
        rad_meas = self.root.find('.//n42:RadMeasurement', ns)
        if rad_meas is None:
            rad_meas = self.root.find('.//RadMeasurement')
        
        if rad_meas is not None:
            start = rad_meas.find('n42:StartTime', ns)
            if start is None:
                start = rad_meas.find('StartTime')
            if start is None:
                # Create new StartTime element
                start = ET.SubElement(rad_meas, 'StartTime')
            
            start.text = timestamp.isoformat()
    
    def set_live_time(self, seconds: float):
        """Set live time in seconds."""
        if self.root is None:
            return
        
        ns = {'n42': self.NS}
        spectrum = self.root.find('.//n42:Spectrum', ns)
        if spectrum is None:
            spectrum = self.root.find('.//Spectrum')
        
        if spectrum is not None:
            live = spectrum.find('n42:LiveTime', ns)
            if live is None:
                live = spectrum.find('LiveTime')
            if live is None:
                live = ET.SubElement(spectrum, 'LiveTime')
            
            live.text = f"PT{seconds:.3f}S"
    
    def set_real_time(self, seconds: float):
        """Set real time in seconds."""
        if self.root is None:
            return
        
        ns = {'n42': self.NS}
        rad_meas = self.root.find('.//n42:RadMeasurement', ns)
        if rad_meas is None:
            rad_meas = self.root.find('.//RadMeasurement')
        
        if rad_meas is not None:
            real = rad_meas.find('n42:RealTime', ns)
            if real is None:
                real = rad_meas.find('RealTime')
            if real is None:
                real = ET.SubElement(rad_meas, 'RealTime')
            
            real.text = f"PT{seconds:.3f}S"
    
    def set_instrument_info(self, manufacturer: str = None, model: str = None, 
                            serial_number: str = None):
        """Set instrument information fields."""
        if self.root is None:
            return
        
        ns = {'n42': self.NS}
        spectrum = self.root.find('.//n42:Spectrum', ns)
        if spectrum is None:
            spectrum = self.root.find('.//Spectrum')
        
        if spectrum is None:
            return
        
        # Find or create InstrumentInformation
        inst = spectrum.find('n42:InstrumentInformation', ns)
        if inst is None:
            inst = spectrum.find('InstrumentInformation')
        if inst is None:
            inst = ET.SubElement(spectrum, 'InstrumentInformation')
        
        if manufacturer:
            elem = inst.find('n42:Manufacturer', ns) or inst.find('Manufacturer')
            if elem is None:
                elem = ET.SubElement(inst, 'Manufacturer')
            elem.text = manufacturer
        
        if model:
            elem = inst.find('n42:Model', ns) or inst.find('Model')
            if elem is None:
                elem = ET.SubElement(inst, 'Model')
            elem.text = model
        
        if serial_number:
            elem = inst.find('n42:SerialNumber', ns) or inst.find('SerialNumber')
            if elem is None:
                elem = ET.SubElement(inst, 'SerialNumber')
            elem.text = serial_number
    
    def add_remark(self, text: str):
        """Add a remark/comment to the file."""
        if self.root is None or not text:
            return
        
        remark = ET.SubElement(self.root, 'Remark')
        remark.text = text
    
    def set_sample_description(self, description: str):
        """Set MeasuredItemDescription field."""
        if self.root is None:
            return
        
        ns = {'n42': self.NS}
        rad_meas = self.root.find('.//n42:RadMeasurement', ns)
        if rad_meas is None:
            rad_meas = self.root.find('.//RadMeasurement')
        
        if rad_meas is not None:
            # Find or create MeasuredItemInformation
            item_info = rad_meas.find('n42:MeasuredItemInformation', ns)
            if item_info is None:
                item_info = rad_meas.find('MeasuredItemInformation')
            if item_info is None:
                item_info = ET.SubElement(rad_meas, 'MeasuredItemInformation')
            
            desc = item_info.find('n42:MeasuredItemDescription', ns)
            if desc is None:
                desc = item_info.find('MeasuredItemDescription')
            if desc is None:
                desc = ET.SubElement(item_info, 'MeasuredItemDescription')
            
            desc.text = description
    
    def set_geolocation(self, latitude: float, longitude: float, 
                         elevation_m: float = None):
        """Set geographic location."""
        if self.root is None:
            return
        
        ns = {'n42': self.NS}
        rad_meas = self.root.find('.//n42:RadMeasurement', ns)
        if rad_meas is None:
            rad_meas = self.root.find('.//RadMeasurement')
        
        if rad_meas is not None:
            # Find or create GeoLocation
            geo = rad_meas.find('n42:GeoLocation', ns)
            if geo is None:
                geo = rad_meas.find('GeoLocation')
            if geo is None:
                geo = ET.SubElement(rad_meas, 'GeoLocation')
            
            lat_elem = geo.find('Latitude') or ET.SubElement(geo, 'Latitude')
            lat_elem.text = str(latitude)
            
            lon_elem = geo.find('Longitude') or ET.SubElement(geo, 'Longitude')
            lon_elem.text = str(longitude)
            
            if elevation_m is not None:
                elev = geo.find('Elevation') or ET.SubElement(geo, 'Elevation')
                elev.text = str(elevation_m)
    
    def to_xml(self) -> str:
        """
        Export the modified N42 XML as a formatted string.
        
        Returns:
            Pretty-printed N42 XML string
        """
        if self.root is None:
            return ""
        
        xml_string = ET.tostring(self.root, encoding='unicode')
        dom = minidom.parseString(xml_string)
        pretty_xml = dom.toprettyxml(indent="  ")
        
        # Remove extra blank lines
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        return '\n'.join(lines)


def create_n42_from_template(
    counts: List[int],
    energies: List[float],
    metadata: Dict = None
) -> str:
    """
    Create a new N42 file from scratch with provided data and metadata.
    
    Args:
        counts: Spectrum channel counts
        energies: Energy calibration values
        metadata: Optional metadata dict with fields like:
            - start_time: ISO datetime string
            - live_time: Live time in seconds
            - real_time: Real time in seconds
            - manufacturer: Instrument manufacturer
            - model: Instrument model
            - serial_number: Serial number
            - sample_description: Description of measured item
            - remarks: List of remarks
            
    Returns:
        N42 XML string
    """
    from n42_exporter import generate_n42_xml
    
    metadata = metadata or {}
    
    spectrum_data = {
        'counts': counts,
        'energies': energies,
        'metadata': {
            'live_time': metadata.get('live_time', 1.0),
            'real_time': metadata.get('real_time', metadata.get('live_time', 1.0)),
            'start_time': metadata.get('start_time'),
        },
        'instrument_info': {
            'manufacturer': metadata.get('manufacturer', 'RadView Detection'),
            'model': metadata.get('model', 'AlphaHound'),
            'serial_number': metadata.get('serial_number', 'UNKNOWN'),
        }
    }
    
    # Generate base N42
    xml_content = generate_n42_xml(spectrum_data)
    
    # Apply additional metadata using editor
    if any(k in metadata for k in ['sample_description', 'remarks', 'latitude', 'longitude']):
        editor = N42MetadataEditor(xml_content)
        
        if 'sample_description' in metadata:
            editor.set_sample_description(metadata['sample_description'])
        
        if 'remarks' in metadata:
            for remark in metadata['remarks'] if isinstance(metadata['remarks'], list) else [metadata['remarks']]:
                editor.add_remark(remark)
        
        if 'latitude' in metadata and 'longitude' in metadata:
            editor.set_geolocation(metadata['latitude'], metadata['longitude'],
                                   metadata.get('elevation'))
        
        xml_content = editor.to_xml()
    
    return xml_content
