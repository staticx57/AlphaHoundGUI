"""
Synthetic N42 Test Spectra Generator

Generates realistic synthetic gamma spectra for testing source identification
and ROI analysis. Creates N42 v2006 format files with proper metadata.

IMPORTANT: These are SYNTHETIC spectra for testing purposes only.
They simulate typical detector responses but are NOT real measurements.
"""

import numpy as np
from datetime import datetime
import os

# Configuration
CHANNELS = 1024
KEV_PER_CHANNEL = 3.0  # 3 keV/channel calibration
MAX_ENERGY = CHANNELS * KEV_PER_CHANNEL  # 3072 keV
DEFAULT_LIVE_TIME = 600.0  # 10 minutes

# CsI(Tl) detector FWHM model: ~10% at 662 keV, energy dependent
def fwhm_keV(energy_keV: float) -> float:
    """Calculate FWHM for CsI(Tl) detector (energy dependent)."""
    return 0.10 * energy_keV * np.sqrt(662 / max(energy_keV, 10))


def energy_to_channel(energy_keV: float) -> int:
    """Convert energy to channel number."""
    return int(round(energy_keV / KEV_PER_CHANNEL))


def add_gaussian_peak(counts: np.ndarray, energy_keV: float, peak_area: float, fwhm: float = None):
    """Add a Gaussian peak to the spectrum at the specified energy."""
    if fwhm is None:
        fwhm = fwhm_keV(energy_keV)
    
    sigma = fwhm / 2.355  # FWHM to sigma conversion
    center_channel = energy_to_channel(energy_keV)
    
    if center_channel < 0 or center_channel >= CHANNELS:
        return  # Peak outside spectrum range
    
    # Calculate peak contribution for each channel (±5 sigma)
    half_width = int(10 * sigma / KEV_PER_CHANNEL) + 5
    for ch in range(max(0, center_channel - half_width), min(CHANNELS, center_channel + half_width)):
        ch_energy = ch * KEV_PER_CHANNEL
        gaussian = np.exp(-0.5 * ((ch_energy - energy_keV) / sigma) ** 2)
        counts[ch] += peak_area * gaussian / (sigma * np.sqrt(2 * np.pi)) * KEV_PER_CHANNEL


def add_compton_continuum(counts: np.ndarray, peak_energy_keV: float, peak_area: float):
    """
    Add the Compton shelf below a photopeak. The edge is smeared over the detector's resolution at the edge, as a real one is: a hard step
    makes the peak finder report a "peak" just under it, which no real spectrum has to that degree.
    """
    edge_energy = 2 * peak_energy_keV * peak_energy_keV / (511 + 2 * peak_energy_keV)
    width = max(fwhm_keV(edge_energy) / 2.355, KEV_PER_CHANNEL)
    energies = np.arange(CHANNELS) * KEV_PER_CHANNEL
    shelf = np.exp(-energies / peak_energy_keV) / (1.0 + np.exp((energies - edge_energy) / (0.6 * width)))
    counts += peak_area * 0.05 * shelf


def add_background(counts: np.ndarray, level: float = 20):
    """Add exponential background."""
    counts += level * np.exp(-np.arange(CHANNELS) * KEV_PER_CHANNEL / 800)


def apply_poisson_noise(counts: np.ndarray) -> np.ndarray:
    """Poisson statistical noise on the expected counts (a float expectation: truncating it to an integer first biases every channel low)."""
    return RNG.poisson(np.maximum(counts, 0))


RNG = np.random.default_rng()


def seed(value=None):
    """Make the noise reproducible (tests); with no value it is fresh each run."""
    global RNG
    RNG = np.random.default_rng(value)


def write_n42(filepath: str, counts: np.ndarray, source_name: str, live_time: float = DEFAULT_LIVE_TIME):
    """Write spectrum to N42 v2006 format."""
    # Generate channel energies
    channel_energies = " ".join([f"{ch * KEV_PER_CHANNEL:.5f}" for ch in range(CHANNELS)])
    channel_data = " ".join([str(int(c)) for c in counts])
    
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    
    n42_content = f'''<?xml version="1.0" ?>
<RadInstrumentData xmlns="http://physics.nist.gov/N42/2006/N42">
  <RadMeasurement>
    <MeasurementClassCode>Foreground</MeasurementClassCode>
    <StartTime>{timestamp}</StartTime>
    <RealTime>PT{live_time:.3f}S</RealTime>
    <Remarks>SYNTHETIC TEST SPECTRUM - {source_name} - NOT A REAL MEASUREMENT</Remarks>
    <Spectrum>
      <LiveTime>PT{live_time:.3f}S</LiveTime>
      <EnergyCalibration>
        <CalibrationEquation>List</CalibrationEquation>
        <ChannelEnergies>{channel_energies}</ChannelEnergies>
      </EnergyCalibration>
      <ChannelData NumberOfChannels="{CHANNELS}">{channel_data}</ChannelData>
      <SpectrumType>PHA</SpectrumType>
      <InstrumentInformation>
        <Manufacturer>RadTrace</Manufacturer>
        <Model>Synthetic Test Generator</Model>
        <SerialNumber>SYNTHETIC-001</SerialNumber>
      </InstrumentInformation>
    </Spectrum>
  </RadMeasurement>
</RadInstrumentData>
'''
    
    with open(filepath, 'w') as f:
        f.write(n42_content)
    print(f"Created: {filepath}")


# === Spectrum Generators ===

def generate_smoke_detector():
    """Generate Am-241 smoke detector spectrum (60 keV)."""
    counts = np.zeros(CHANNELS)
    add_background(counts, level=15)
    add_gaussian_peak(counts, 60, 5000)  # Am-241 60 keV
    add_gaussian_peak(counts, 26, 1000)  # Am-241 26 keV (Np X-ray)
    counts = apply_poisson_noise(counts)
    return counts


def generate_radium_dial():
    """Generate Ra-226 radium dial spectrum (Bi-214, Pb-214, NO Th-234)."""
    counts = np.zeros(CHANNELS)
    add_background(counts, level=25)
    
    # Ra-226 daughters (no Th-234 because Ra-226 was chemically separated)
    add_gaussian_peak(counts, 352, 2000)   # Pb-214
    add_compton_continuum(counts, 352, 2000)
    add_gaussian_peak(counts, 295, 1200)   # Pb-214
    add_gaussian_peak(counts, 609, 3500)   # Bi-214
    add_compton_continuum(counts, 609, 3500)
    add_gaussian_peak(counts, 1120, 800)   # Bi-214
    add_gaussian_peak(counts, 1764, 600)   # Bi-214
    
    counts = apply_poisson_noise(counts)
    return counts


def generate_potassium_background():
    """Generate K-40 natural background spectrum (1461 keV)."""
    counts = np.zeros(CHANNELS)
    add_background(counts, level=30)
    
    add_gaussian_peak(counts, 1461, 1500)  # K-40
    add_compton_continuum(counts, 1461, 1500)
    
    # Some natural Ra-226 daughters from environment
    add_gaussian_peak(counts, 609, 200)   # Bi-214 (trace)
    add_gaussian_peak(counts, 352, 150)   # Pb-214 (trace)
    
    counts = apply_poisson_noise(counts)
    return counts


def generate_cobalt60():
    """Generate Co-60 source spectrum (1173/1332 keV dual peaks)."""
    counts = np.zeros(CHANNELS)
    add_background(counts, level=20)
    
    add_gaussian_peak(counts, 1173, 4000)  # Co-60
    add_compton_continuum(counts, 1173, 4000)
    add_gaussian_peak(counts, 1332, 4000)  # Co-60
    add_compton_continuum(counts, 1332, 4000)
    
    counts = apply_poisson_noise(counts)
    return counts


def generate_uranium_ore():
    """Generate uranium ore spectrum (full U-238 chain + U-235)."""
    counts = np.zeros(CHANNELS)
    add_background(counts, level=30)
    
    # U-238 chain in secular equilibrium
    add_gaussian_peak(counts, 93, 3000)    # Th-234 (major U-238 marker)
    add_gaussian_peak(counts, 63, 800)     # Th-234 secondary
    add_gaussian_peak(counts, 352, 2500)   # Pb-214
    add_compton_continuum(counts, 352, 2500)
    add_gaussian_peak(counts, 295, 1500)   # Pb-214
    add_gaussian_peak(counts, 609, 4000)   # Bi-214 (strongest)
    add_compton_continuum(counts, 609, 4000)
    add_gaussian_peak(counts, 1120, 1200)  # Bi-214
    add_gaussian_peak(counts, 1764, 800)   # Bi-214
    add_gaussian_peak(counts, 1001, 700)   # Pa-234m
    
    # U-235 (0.72% natural abundance - weak but visible)
    add_gaussian_peak(counts, 186, 400)    # U-235 (main line)
    add_gaussian_peak(counts, 144, 150)    # U-235
    add_gaussian_peak(counts, 163, 100)    # U-235
    
    counts = apply_poisson_noise(counts)
    return counts


def generate_cesium137():
    """Generate Cs-137 source spectrum (662 keV)."""
    counts = np.zeros(CHANNELS)
    add_background(counts, level=20)
    
    add_gaussian_peak(counts, 662, 8000)   # Cs-137
    add_compton_continuum(counts, 662, 8000)
    add_gaussian_peak(counts, 32, 1500)    # Ba-137 X-ray
    
    counts = apply_poisson_noise(counts)
    return counts


GENERATORS = {
    "synthetic_smoke_detector": (generate_smoke_detector, "Am-241 Smoke Detector"),
    "synthetic_radium_dial": (generate_radium_dial, "Ra-226 Radium Dial"),
    "synthetic_potassium_k40": (generate_potassium_background, "K-40 Natural Background"),
    "synthetic_cobalt60": (generate_cobalt60, "Co-60 Source"),
    "synthetic_uranium_ore": (generate_uranium_ore, "Uranium Ore (Natural U)"),
    "synthetic_cesium137": (generate_cesium137, "Cs-137 Source"),
}


def spectrum_dict(name: str) -> dict:
    """The named spectrum as the parsers return one (counts, energies, calibrated), for tests and tools that skip the file."""
    counts = GENERATORS[name][0]()
    return {"counts": [int(c) for c in counts], "energies": [ch * KEV_PER_CHANNEL for ch in range(CHANNELS)], "is_calibrated": True,
            "metadata": {"live_time": DEFAULT_LIVE_TIME}}


def main():
    """Generate all synthetic test spectra."""
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "test_spectra")
    os.makedirs(output_dir, exist_ok=True)

    print("Generating synthetic test spectra...")
    print("=" * 50)
    print("IMPORTANT: These are SYNTHETIC spectra for testing")
    print("           They are NOT real measurements!")
    print("=" * 50)

    for name, (generate, source_name) in GENERATORS.items():
        write_n42(os.path.join(output_dir, name + ".n42"), generate(), source_name)

    print()
    print("All synthetic test spectra created successfully!")
    print(f"Location: {output_dir}")


if __name__ == "__main__":
    main()
