
import numpy as np
from n42_exporter import generate_n42_xml
import os

def generate_cs137_spectrum():
    """
    Generates a synthetic N42 file with a perfect Cs-137 peak at 662 keV.
    Intended to trigger the Advanced Fitting Engine.
    """
    
    # 1. Setup Energy Calibration
    # 3.0 keV/channel (Standard for AlphaHound)
    n_channels = 1024
    slope = 3.0 
    intercept = 0.0
    energies = [slope * i + intercept for i in range(n_channels)]
    
    # 2. Build Spectrum
    counts = np.zeros(n_channels)
    
    # Background (Linear decreasing)
    # Starts at 50, ends at 5
    for i in range(n_channels):
        counts[i] = 50 - (45 * i / n_channels)
        
    # Add Noise (Poisson)
    counts = np.random.poisson(counts).astype(float)
    
    # Add Cs-137 Peak (662 keV)
    # Target Channel = 662 / 3.0 = 220.6
    centroid = 662.0
    sigma = 20.0  # ~7% resolution (FWHM ~47 keV)
    amplitude = 5000 # Strong peak
    
    for i, e in enumerate(energies):
        # Gaussian
        val = amplitude * np.exp(-0.5 * ((e - centroid) / sigma)**2)
        counts[i] += val
        
    # Final Poisson on total
    counts = np.random.poisson(counts)
    
    # 3. Export
    data = {
        'counts': counts.tolist(),
        'energies': energies,
        'metadata': {
            'live_time': 300.0,
            'real_time': 300.0,
            'start_time': '2024-12-16T12:00:00',
            'source': 'Synthetic Cs-137 Verification Source',
            'channels': n_channels
        },
        'instrument_info': {
            'manufacturer': 'AlphaHound',
            'model': 'Simulation',
            'serial_number': 'SIM-001'
        }
    }
    
    xml_content = generate_n42_xml(data)
    
    filename = "Cs137_Verification_Spectra.n42"
    with open(filename, "w") as f:
        f.write(xml_content)
        
    print(f"Generated: {os.path.abspath(filename)}")

if __name__ == "__main__":
    generate_cs137_spectrum()
