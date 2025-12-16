Python Radiation Analysis Packages Research
Research Date: December 16, 2025
Purpose: Identify additional Python packages to enhance AlphaHoundGUI features beyond the current becquerel and pyriid dependencies.

Current Dependencies
Package	Purpose	Status
becquerel	Spectrum parsing, nuclear data access, file format support	✅ In use
pyriid	ML-based isotope identification, synthetic spectrum generation	✅ In use
🔥 High-Priority Recommendations
1. SandiaSpecUtils
Install: pip install SandiaSpecUtils

Aspect	Details
Source	Sandia National Laboratories
Purpose	Universal spectrum file format conversion
Key Features	• Parses 100+ spectrum file formats (N42, SPE, SPC, CHN, CSV, PCF, DAT, etc.)
• Exports to 13 different formats
• Python bindings via nanobind
• Used by InterSpec and other Sandia tools
Relevance	Would dramatically expand file import compatibility beyond current CSV/N42 support
Integration Effort	🟢 Low - Drop-in replacement for manual parsers
# Example usage
from SpecUtils import SpecFile
spec = SpecFile("unknown_format.spe")
counts = spec.get_gamma_counts()
energies = spec.get_channel_energies()
2. irrad_spectroscopy
Install: pip install irrad_spectroscopy (or clone from GitHub)

Aspect	Details
Source	CERN / SiLab
Purpose	Gamma/X-ray spectroscopy analysis
Key Features	• Isotope identification
• Activity determination (Bq) ← Major enhancement
• Spectral dose calculations
• >90% activity reconstruction accuracy (tested)
Relevance	Would add proper activity calculations and dose rate computation from spectra
Integration Effort	🟡 Medium - Requires detector efficiency calibration data
# Activity calculation example
from irrad_spectroscopy import get_activity
activity_bq = get_activity(
    peak_net_counts=1250,
    efficiency=0.15,
    branching_ratio=0.85,
    live_time=300  # seconds
)
3. Curie
Install: pip install curie

Aspect	Details
Source	J.T. Morrell (jtmorrell/curie)
Purpose	Gamma-ray activation analysis
Key Features	• Bateman equation solver for decay chains ← Major enhancement
• HPGe-quality peak fitting
• Energy/efficiency calibration
• Attenuation coefficient database
• Stopping power calculations
Relevance	Would enhance decay chain calculations and add decay time predictions
Integration Effort	🟡 Medium - Complements existing decay chain detection
# Bateman equation solver for decay series
from curie import Bateman
b = Bateman(['U-238', 'Th-234', 'Pa-234m', 'U-234'])
activity = b.activity(t=3600, units='hours')  # Activity after 1 hour
4. radiacode (Future Device Support)
Install: pip install radiacode

Aspect	Details
Source	Open-source community
Purpose	Radiacode 10x detector integration
Key Features	• USB and Bluetooth connectivity
• Real-time dose rate monitoring
• 1024-channel spectrum acquisition
• Calibration constant access (a0, a1, a2)
Relevance	Already planned in TODO.md - would add Radiacode 103/103G/110 support
Integration Effort	🟡 Medium - Similar pattern to AlphaHound integration
from radiacode import RadiaCode
rc = RadiaCode()  # USB connection
spectrum = rc.spectrum()
dose_rate = rc.dose_rate()
🟡 Medium-Priority Packages
5. npat (Nuclear Physics Analysis Tools)
Install: pip install npat

Aspect	Details
Purpose	Nuclear data access and activation analysis
Key Features	• Cross-section libraries
• Isotopic/decay data access
• Energy/efficiency calibration tools
Use Case	Access to ENDF nuclear data; alternative to IAEA/NNDC APIs
Note	Last updated Feb 2020 - may have compatibility issues
6. PyGammaSpec
Install: Clone from GitHub (no pip package)

Aspect	Details
Purpose	Gamma spectroscopy data manipulation and plotting
Key Features	• Spectrum loading/saving
• Plotting utilities
• Simple analysis tools
Use Case	Additional plotting options and data manipulation
Note	Updated May 2024; simpler than becquerel
7. GammaSpy
Install: Clone from GitHub

Aspect	Details
Purpose	Peak visualization, finding, and fitting
Key Features	• Peak finding algorithms
• Gaussian/Voigt fitting
• Activity computation
• Automatic source determination
Use Case	Could replace/enhance current scipy.signal.find_peaks approach
🔵 Low-Priority / Specialized Packages
8. PyNE (Python for Nuclear Engineering)
Install: Complex - requires compilation

Aspect	Details
Purpose	Comprehensive nuclear engineering toolkit
Key Features	• ENSDF data access
• Material definitions
• Cross-section handling
Use Case	Overkill for gamma spectroscopy alone; useful if expanding to nuclear engineering simulations
Note	Heavy dependency with C++ components
9. Impulse MCA
Install: Clone from GitHub

Aspect	Details
Purpose	Sound card / MCA gamma spectrometry
Key Features	• Sound card spectrometer support
• Web-based interface
• Isotope identification
• 3D spectra recording
Use Case	Could add support for Gammaspectacular and similar DIY spectrometers
10. pyEGAF
Install: Clone from GitHub

Aspect	Details
Purpose	EGAF (Evaluated Gamma-ray Activation File) data access
Key Features	• Thermal neutron capture gamma data
• IAEA/NNDC data integration
Use Case	Specialized for neutron activation analysis
📊 Comparison Matrix
Package	Isotope ID	Activity Calc	Peak Fitting	File Formats	Decay Chains	Device Support
becquerel (current)	❌	❌	✅	✅	❌	❌
pyriid (current)	✅ ML	❌	❌	❌	❌	❌
SandiaSpecUtils	❌	❌	❌	✅✅✅	❌	❌
irrad_spectroscopy	✅	✅✅	❌	❌	❌	❌
Curie	❌	✅	✅	❌	✅✅	❌
radiacode	❌	❌	❌	❌	❌	✅✅
npat	❌	✅	✅	❌	❌	❌
GammaSpy	✅	✅	✅✅	❌	❌	❌
🎯 Recommended Integration Priority
Phase 1: Quick Wins
SandiaSpecUtils - Expands supported file formats from 2 to 100+
irrad_spectroscopy - Adds activity calculations (Bq/μCi) to ROI analysis
Phase 2: Enhanced Analysis
Curie - Bateman solver for decay predictions and decay chain time evolution
Phase 3: Device Expansion
radiacode - Already planned; enables Radiacode 103/103G/110 support
Phase 4: Optional Enhancements
GammaSpy - Alternative peak fitting algorithms
npat - Additional nuclear data sources
⚠️ Dependencies & Conflicts
Package	Key Dependencies	Potential Conflicts
SandiaSpecUtils	nanobind (C++ bindings)	None expected
irrad_spectroscopy	numpy, scipy, pyyaml	None expected
Curie	numpy, scipy, pandas	None expected
radiacode	hidapi (for USB)	May need libusb on Windows
PyNE	HDF5, MOAB (C++ libs)	Complex - compilation required
📝 Next Steps
 Test SandiaSpecUtils with existing N42/CSV test files
 Evaluate irrad_spectroscopy activity calculation accuracy with AlphaHound data
 Prototype Curie Bateman solver integration for decay chain visualization
 Continue Radiacode integration per existing plan
This research was conducted to identify packages complementary to (not replacing) the existing becquerel and pyriid integration.