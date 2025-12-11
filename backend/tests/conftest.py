
import pytest
import sys
import os

# Add backend directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def sample_spectrum():
    """
    Returns a simple synthetic spectrum with a peak at index 50.
    """
    counts = [10] * 100
    # Add a Gaussian-like peak
    for i in range(45, 56):
        counts[i] += 100 - (abs(i - 50) * 10)
    
    energies = [i * 2.0 for i in range(100)] # Linear 2 keV per bin
    return energies, counts

@pytest.fixture
def mock_n42_content():
    return """<?xml version="1.0" encoding="UTF-8"?>
<RadInstrumentData xmlns="http://physics.nist.gov/N42/2006/N42">
  <RadMeasurement>
    <Spectrum>
      <ChannelData>10 20 30 100 30 20 10</ChannelData>
      <EnergyCalibration>
        <ChannelEnergies>0 2 4 6 8 10 12</ChannelEnergies>
      </EnergyCalibration>
    </Spectrum>
  </RadMeasurement>
</RadInstrumentData>
"""
