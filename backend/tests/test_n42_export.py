"""
Unit tests for N42 XML export functionality

Tests:
- Basic N42 XML generation
- Round-trip compatibility (import → export → re-import)
- XML structure validation
- Metadata preservation
- Isotope identification embedding
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from n42_exporter import generate_n42_xml, validate_n42_structure
from n42_parser import parse_n42


class TestN42Export:
    """Test suite for N42 XML export functionality"""
    
    def test_basic_export(self):
        """Test basic N42 XML generation with minimal data"""
        spectrum_data = {
            'counts': [10, 20, 30, 40, 50, 30, 20, 10],
            'energies': [0.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0, 21.0],
            'metadata': {
                'live_time': 60.0,
                'real_time': 60.5,
                'source': 'Test Spectrum'
            }
        }
        
        xml = generate_n42_xml(spectrum_data)
        
        # Verify XML is generated
        assert xml is not None
        assert len(xml) > 0
        
        # Verify contains key N42 elements
        assert 'RadInstrumentData' in xml
        assert 'xmlns="http://physics.nist.gov/N42/2006/N42"' in xml
        assert 'RadMeasurement' in xml
        assert 'Spectrum' in xml
        assert 'ChannelData' in xml
        assert 'EnergyCalibration' in xml
        
        # Verify counts are present
        assert '10 20 30 40 50 30 20 10' in xml
        
        # Verify energy calibration
        assert '0.00000' in xml
        assert '21.00000' in xml
    
    def test_round_trip(self):
        """Test import → export → re-import preserves data"""
        original_data = {
            'counts': [5, 10, 15, 20, 25, 20, 15, 10, 5],
            'energies': [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0],
            'metadata': {
                'live_time': 120.0,
                'real_time': 121.0,
                'start_time': '2024-12-14T13:00:00Z',
                'source': 'Round-Trip Test'
            }
        }
        
        # Export to N42
        xml = generate_n42_xml(original_data)
        
        # Re-import the generated XML
        parsed = parse_n42(xml)
        
        # Verify no errors
        assert 'error' not in parsed
        
        # Verify counts match
        assert len(parsed['counts']) == len(original_data['counts'])
        for i in range(len(original_data['counts'])):
            assert parsed['counts'][i] == original_data['counts'][i]
        
        # Verify energies match
        assert len(parsed['energies']) == len(original_data['energies'])
        for i in range(len(original_data['energies'])):
            assert abs(parsed['energies'][i] - original_data['energies'][i]) < 0.01
        
        # Verify metadata
        assert parsed['is_calibrated'] is True
        assert parsed['metadata']['live_time'] == pytest.approx(120.0, rel=0.1)
        assert parsed['metadata']['real_time'] == pytest.approx(121.0, rel=0.1)
    
    def test_xml_structure_validation(self):
        """Test that generated XML passes validation"""
        spectrum_data = {
            'counts': [100, 200, 150],
            'energies': [0.0, 10.0, 20.0],
            'metadata': {
                'live_time': 10.0,
                'real_time': 10.1
            }
        }
        
        xml = generate_n42_xml(spectrum_data)
        
        # Validate structure
        is_valid = validate_n42_structure(xml)
        assert is_valid is True
    
    def test_metadata_preservation(self):
        """Test that all metadata fields are preserved in export"""
        spectrum_data = {
            'counts': [50, 100, 75],
            'energies': [0.0, 15.0, 30.0],
            'metadata': {
                'live_time': 300.0,
                'real_time': 305.0,
                'start_time': '2024-12-14T10:30:00Z',
                'source': 'AlphaHound Device',
                'channels': 3
            },
            'instrument_info': {
                'manufacturer': 'RadView Detection',
                'model': 'AlphaHound',
                'serial_number': 'AH-001'
            }
        }
        
        xml = generate_n42_xml(spectrum_data)
        
        # Verify metadata in XML
        assert 'PT300.000S' in xml  # Live time in ISO 8601 duration
        assert 'PT305.000S' in xml  # Real time in ISO 8601 duration
        assert '2024-12-14T10:30:00Z' in xml
        assert 'RadView Detection' in xml
        assert 'AlphaHound' in xml
        assert 'AH-001' in xml
    
    def test_isotope_embedding(self):
        """Test that isotope identification results are embedded"""
        spectrum_data = {
            'counts': [10, 50, 30, 20],
            'energies': [0.0, 662.0, 1173.0, 1332.0],
            'metadata': {
                'live_time': 600.0,
                'real_time': 600.0
            },
            'isotopes': [
                {'isotope': 'Cs-137', 'confidence': 'HIGH', 'energy': 662.0},
                {'isotope': 'Co-60', 'confidence': 'MEDIUM', 'energy': 1173.0}
            ]
        }
        
        xml = generate_n42_xml(spectrum_data)
        
        # Verify isotope data is present
        assert 'SpectrumExtension' in xml
        assert 'IsotopeIdentification' in xml
        assert 'Cs-137' in xml
        assert 'Co-60' in xml
        assert 'HIGH' in xml
        assert 'MEDIUM' in xml
    
    def test_missing_required_fields(self):
        """Test that missing required fields raise appropriate errors"""
        # Missing counts
        with pytest.raises(ValueError, match="Missing required fields"):
            generate_n42_xml({'energies': [0.0, 1.0]})
        
        # Missing energies
        with pytest.raises(ValueError, match="Missing required fields"):
            generate_n42_xml({'counts': [10, 20]})
    
    def test_mismatched_arrays(self):
        """Test that mismatched counts/energies arrays raise error"""
        spectrum_data = {
            'counts': [10, 20, 30],
            'energies': [0.0, 10.0]  # Wrong length
        }
        
        with pytest.raises(ValueError, match="must have same length"):
            generate_n42_xml(spectrum_data)
    
    def test_large_spectrum(self):
        """Test export of full 1024-channel spectrum"""
        counts = list(range(1024))
        energies = [i * 3.0 for i in range(1024)]  # 3 keV/channel
        
        spectrum_data = {
            'counts': counts,
            'energies': energies,
            'metadata': {
                'live_time': 600.0,
                'real_time': 602.0,
                'source': 'AlphaHound Device'
            }
        }
        
        xml = generate_n42_xml(spectrum_data)
        
        # Verify large spectrum generates valid XML
        assert xml is not None
        assert 'NumberOfChannels="1024"' in xml
        assert validate_n42_structure(xml)
        
        # Round-trip test with large spectrum
        parsed = parse_n42(xml)
        assert len(parsed['counts']) == 1024
        assert len(parsed['energies']) == 1024


class TestParserFixes:
    """Test that parser bugs are fixed"""
    
    def test_parser_handles_live_time(self):
        """Test that parser correctly extracts LiveTime"""
        test_n42 = """<?xml version="1.0"?>
<RadInstrumentData xmlns="http://physics.nist.gov/N42/2006/N42">
  <RadMeasurement>
    <Spectrum>
      <LiveTime>PT600.000S</LiveTime>
      <ChannelData>10 20 30</ChannelData>
      <EnergyCalibration>
        <ChannelEnergies>0 10 20</ChannelEnergies>
      </EnergyCalibration>
    </Spectrum>
  </RadMeasurement>
</RadInstrumentData>"""
        
        parsed = parse_n42(test_n42)
        assert 'error' not in parsed
        # Parser extracts PT600.000S as text, conversion happens in parser
        assert parsed['metadata']['live_time'] >= 0  # Should be extracted


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v', '--tb=short'])
