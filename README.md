# RadTrace 🚀

![RadTrace Banner](backend/static/docs/banner.png)

> [!CAUTION]
> **RADIATION SAFETY NOTICE & DISCLAIMER**
> 
> This software is provided for **EDUCATIONAL AND RESEARCH PURPOSES ONLY**. It is NOT a professional radiation analysis tool and should NOT be used for:
> - Safety-critical applications or emergency response
> - Regulatory compliance or reporting to authorities
> - Medical diagnosis, treatment, or patient care decisions  
> - Professional radiological assessments or surveys
> - Homeland security or detection of illicit materials
> 
> **CRITICAL WARNINGS:**
> - ⚠️ **Always follow proper radiation safety protocols** - Use ALARA (As Low As Reasonably Achievable) principles
> - ⚠️ **Equipment calibration required** - Use only professionally calibrated and maintained detection equipment
> - ⚠️ **Seek professional expertise** - Consult qualified health physicists or radiation safety officers for analysis
> - ⚠️ **Results may be inaccurate** - Isotope identification results may contain errors; verify with certified laboratory methods
> - ⚠️ **No liability** - The developers assume NO LIABILITY for any consequences of using this software or relying on its output
> - ⚠️ **Licensing required** - Ensure you have proper training, permits, and licenses before handling radioactive materials
> 
> **This tool provides automated suggestions only.** Human verification by qualified professionals is required for any safety-related decisions.
> 
> If you are working with radiation sources, ensure compliance with local regulations (NRC, EPA, state, or equivalent authorities).

**RadTrace** is a modern, web-based gamma spectroscopy analysis platform with intelligent isotope identification, decay chain detection, XRF element analysis, and real-time multi-device integration.

## ✨ Key Features

### 📊 Advanced Analysis
- **Universal File Support**: Analysis of 100+ spectrum formats (N42, CSV, SPE, CNF, MCA, etc.) via `SandiaSpecUtils` integration.
- **Decay Chain Prediction**: 
  - **Hybrid Engine**: Uses authoritative `curie` library data with a custom Bateman solver fallback.
  - **Interactive Visualization**: Models daughter product buildup (U-238, Th-232 chains) over time with log-scale charts.
- **XRF Element Identification**: K-shell fluorescence pattern matching for material composition analysis.
- **Dose Rate Calculator**: Estimates gamma dose rates (μSv/h) from activity using rigorous nuclear data.
- **Natural Abundance Weighting**: Scientifically accurate ranking based on LBNL/NRC isotopic abundance data
- **Authoritative References**: Direct links to NNDC, IAEA, LBNL, USGS, NRC sources for each detected chain
- **SNIP Background Filtering**: Automatic Compton continuum removal using industry-standard SNIP algorithm
- **Spectrum Algebra**: Add, subtract, normalize, and compare spectra with proper Poisson error propagation
- **ML Integration (PyRIID)**:
  - Neural network trained on 90+ isotopes from IAEA/NNDC databases
  - Multi-isotope mixture recognition (UraniumGlass, ThoriumMantle, MedicalWaste, IndustrialGauge, etc.)
  - ~1500 training samples with realistic Poisson statistics
  - Best suited for real detector data
  - **📖 See [PYRIID_GUIDE.md](PYRIID_GUIDE.md) for detailed usage and extension guide**
- **Dual Detection Panel**: Side-by-side comparison of Peak Matching (legacy) vs AI Identification (ML)
- **Dual-Mode Analysis Engine**:
  - **Live Acquisition**: Uses "Gold Standard" checks (30% confidence) to prevent false positives in live data.
  - **File Analysis**: Uses "Robust" checks (1% confidence, 30 keV tolerance) for uploaded CSV/N42 files to handle uncalibrated or noisy community data.

### 🛡️ Stability & Reliability
- **Server-Managed Acquisitions**: Timing managed by Python backend - survives browser tab throttling, display sleep, and tab closure.
- **Acquisition Recovery**: Automatic checkpoint saves every 5 minutes during long acquisitions with crash recovery.
- **Device Write Retry**: Serial operations retry 3 times before disconnecting to handle transient USB timeouts.
- **Auto-Reconnect**: Automatically recovers connection if server restarts.
- **Resource Efficient**: Pauses heavy rendering when tab is backgrounded.
- **Data Safeguards**: Prevents accidental tab closure during active recordings.

### ⚙️ Simple & Advanced Modes
- **Simple Mode** (Default):
  - Optimized thresholds (40% isotope, 30% chain)
  - Curated library for hobbyist applications
  - Minimal false positives
- **Advanced Mode**:
  - User-adjustable confidence thresholds
  - Configurable energy tolerance
  - Expanded 100+ isotope library
  - Custom threshold fine-tuning via ⚙️ Settings panel
  - localStorage persistence across sessions

### 🎨 Interactive Visualization
- **Dual Scale Support**: Linear/Logarithmic toggles
- **Advanced Zoom & Pan**: Mouse wheel, pinch, drag interactions
- **Peak Markers**: Automatic labeling with hover tooltips and stacked annotations
- **Auto-Scale Toggle**: Smart zoom to detected peaks with full spectrum reset
- **Graphical Confidence Bars**: Animated progress bars with color-coded confidence levels (green=HIGH, yellow=MEDIUM, red=LOW)
- **6 Theme Options**: Dark (default), Light, Nuclear, Toxic, Sci-Fi, Cyberpunk
- **Multi-File Comparison**: Overlay up to 8 spectra with color coding
- **Professional Icon System**: Custom SVG icons with consistent styling

### 🔌 Device Integration

#### AlphaHound™ (RadView Detection)
- **Direct Serial Communication**: With RadView Detection AlphaHound™ hardware
- **Real-Time Acquisition**: Watch spectrum build live with 2-second updates
- **Timed/Interruptible Counts**: Set duration (e.g., 5 minutes) with early stop capability
- **Live Dose Rate**: WebSocket streaming of μR/hr measurements with 5-minute history sparkline
- **Temperature Display**: Device temperature shown alongside dose rate
- **Display Mode Control**: Remote control of device display via ◀/▶ buttons
- **Automatic Analysis**: Peak detection & isotope ID on acquired data
- **Non-Blocking UI**: Control device while viewing/analyzing spectra
- **Split Panel Layout**: Optimized control grouping with dedicated live data visualization

#### Radiacode 103/103G/110
- **USB Connection**: Works on all platforms (Windows, macOS, Linux)
- **Bluetooth/BLE**: Cross-platform support via `bleak` library (Windows, macOS, Linux)
- **BLE Device Scanning**: Discover nearby Radiacode devices automatically
- **Real-Time Dose Rate**: μSv/h streaming with live updates
- **Spectrum Acquisition**: 1024-channel spectrum with device calibration
- **Device Control**: Clear spectrum, reset dose accumulator
- **Model Detection**: Automatic identification of RC-103, RC-103G, RC-110

| Feature | AlphaHound CsI(Tl) | Radiacode 103 | Radiacode 103G | Radiacode 110 |
|---------|-------------------|---------------|----------------|---------------|
| **Scintillator** | CsI(Tl) 1.1 cm³ | CsI(Tl) 1 cm³ | GAGG 1 cm³ | CsI(Tl) 3 cm³ |
| **FWHM @ 662 keV** | 10% | 8.4% | 7.4% | 8.4% |
| **Sensitivity** | 48 cps/µSv/h | 30 cps/µSv/h | 40 cps/µSv/h | 77 cps/µSv/h |
| **Connection** | USB Serial | USB + Bluetooth | USB + Bluetooth | USB + Bluetooth |

### 🔬 Region-of-Interest (ROI) Analysis
- **Advanced Mode Feature**: Precise quantitative analysis of specific spectral regions
- **Activity Calculation**: Automatic estimation in Bq and μCi based on detector efficiency
- **Background Subtraction**: Net counts calculation with uncertainty estimation
- **Uranium Enrichment**: Automatic 186 keV / 93 keV ratio analysis to classify Natural/Depleted/Enriched Uranium
- **Source Type Identification**: Auto-suggests common sources (Uranium Glass, Thoriated Lenses, Radium Dials, Smoke Detectors)
- **Ra-226 Interference Handling**: Smart handling of overlapping Ra-226 at 186 keV

### 📤 Export & Reporting
- **Data Export**: JSON/CSV formats with full spectrum data
- **N42 Export**: Standards-compliant N42.42-2006 XML with isotope identification results
- **Auto-Save**: Automatic N42 saves to `data/acquisitions/` after device captures
- **PDF Reports**: Professional reports including:
  - Spectrum plot visualization
  - Detected peaks table
  - Identified isotopes
  - Decay chains with confidence levels
  - Metadata and timestamps
- **History Management**: Save & reload previous analyses (last 10 files)

## 📸 Screenshot

![RadTrace User Interface](backend/static/docs/ui_mockup.png)

*RadTrace's intuitive interface showing real-time spectrum analysis, decay chain detection, and isotope identification with confidence scoring.*

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd AlphaHoundGUI
   ```

2. **Install Dependencies** (one-time setup):
   ```bash
   install_deps.bat
   ```
   This installs all required packages to your system Python (no virtual environment needed).

## Usage

### Quick Start
Double-click **`run.bat`** in the root directory - the application will automatically start and open in your browser at `http://localhost:3200`.

> **Note**: Device hardware is **optional** - the application works without any device connected for N42/CSV file analysis.

### Manual Start
```bash
cd backend
python -m uvicorn main:app --reload --port 3200
```

Then navigate to `http://localhost:3200` and drag & drop an `.n42` or `.csv` file.

### LAN Access (Access from Other Devices)

To access the application from other devices on your network:

1. **Server is configured for LAN** by default (`host="0.0.0.0"` in `main.py`)
2. **Find your computer's IP address**:
   - Windows: `ipconfig` (look for IPv4 Address)
   - Mac/Linux: `ifconfig` or `ip addr`
3. **Access from other devices**: `http://<your-ip>:3200`
   - Example: `http://192.168.1.100:3200`
4. **Firewall**: Ensure port 3200 is open in your firewall

**Use Cases**:
- Control detector device remotely from tablet/phone
- View spectrum analysis from multiple screens
- Collaborative spectrum analysis with team members

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Theory of Operation](THEORY_OF_OPERATION.md) | System architecture, data flow, algorithms, and technical details |
| [Modularity Guide](MODULARITY_GUIDE.md) | How to extend the application: add devices, isotopes, analysis methods |
| [Calibration Guide](CALIBRATION_GUIDE.md) | Energy calibration, accuracy improvement, reference energy tables |
| [PyRIID Guide](PYRIID_GUIDE.md) | Machine learning integration with PyRIID from Sandia National Labs |
| [Radiacode Integration](RADIACODE_INTEGRATION_PLAN.md) | Radiacode device support details and implementation notes |
| [AlphaHound Commands](docs/ALPHAHOUND_SERIAL_COMMANDS.md) | Serial command reference for AlphaHound device |

## Project Structure

```
AlphaHoundGUI/
├── backend/
│   ├── main.py                    # FastAPI application entry point
│   ├── core.py                    # Shared settings and utilities
│   ├── routers/
│   │   ├── analysis.py            # File upload, peak detection, ML endpoints
│   │   ├── device.py              # AlphaHound device control
│   │   ├── device_radiacode.py    # Radiacode device control
│   │   └── isotopes.py            # Custom isotope CRUD
│   ├── alphahound_serial.py       # AlphaHound serial communication driver
│   ├── radiacode_driver.py        # Radiacode device driver (USB/BLE)
│   ├── radiacode_bleak_transport.py # BLE transport layer for Radiacode
│   ├── acquisition_manager.py     # Server-side acquisition timer
│   ├── isotope_database.py        # 100+ isotopes from IAEA/NNDC databases
│   ├── peak_detection.py          # scipy-based peak finding
│   ├── ml_analysis.py             # PyRIID ML integration
│   ├── spectral_analysis.py       # SNIP, Poisson fitting, advanced analysis
│   ├── spectrum_algebra.py        # Spectrum math operations
│   ├── n42_parser.py              # N42/XML file parser
│   ├── n42_exporter.py            # N42/XML file exporter
│   ├── csv_parser.py              # CSV file parser
│   ├── detector_efficiency.py     # Detector calibration data
│   ├── roi_analysis.py            # Region-of-interest analysis
│   ├── activity_calculator.py     # Activity & dose calculations
│   ├── report_generator.py        # PDF export
│   └── static/
│       ├── index.html             # Main HTML interface
│       ├── style.css              # Application styling
│       └── js/
│           ├── main.js            # Application logic
│           ├── api.js             # Backend API calls
│           ├── charts.js          # Chart.js configuration
│           └── ui.js              # UI rendering helpers
├── docs/
│   ├── ALPHAHOUND_SERIAL_COMMANDS.md  # Device command reference
│   └── ANALYSIS_CONDITIONS.md     # Analysis mode documentation
├── archive/                       # Archived data and scripts
├── THEORY_OF_OPERATION.md         # System architecture documentation
├── MODULARITY_GUIDE.md            # Extension guide for developers
├── CALIBRATION_GUIDE.md           # Calibration and accuracy guide
├── PYRIID_GUIDE.md                # ML integration documentation
├── RADIACODE_INTEGRATION_PLAN.md  # Radiacode device support
├── install_deps.bat               # One-time dependency installer
└── run.bat                        # Quick-start script
```

## Credits & Attribution

### This Project (RadTrace)
- **Core Development**: FastAPI, Chart.js, scipy, matplotlib, reportlab
- **Custom Components**: 
  - N42/CSV parsers with fallback processing
  - Isotope identification system with 100+ isotopes from IAEA/NNDC databases
  - Decay chain detection algorithm with natural abundance weighting
  - Graphical visualization system (decay chains, confidence bars, dual detection panels)
  - XRF element identification engine
  - SNIP background filtering
  - Spectrum algebra operations
- **AI/ML Integration**: PyRIID 2.2.0 (Sandia National Laboratories)
- **Development Assistance**: Built with AI assistance from Google Gemini

### Machine Learning Framework
- **PyRIID** (Python Radioisotope Identification Dataset):
  - **Author**: Sandia National Laboratories
  - **License**: Apache 2.0
  - **Repository**: [https://github.com/sandialabs/PyRIID](https://github.com/sandialabs/PyRIID)
  - **Citation**: If you use PyRIID features in academic work, please cite:
    ```
    Darren Holland et al. (2024). PyRIID: Machine Learning-based 
    Radioisotope Identification. Sandia National Laboratories.
    ```
  - **Integration**: Neural network trained on 90+ isotopes with multi-isotope mixture support

### Device Integration
- **AlphaHound Interface**: [NuclearGeekETH](https://github.com/NuclearGeekETH)
  - Device: [AlphaHound™ by RadView Detection](https://www.radviewdetection.com/)
  - License: MIT License
  - ROI analysis with AlphaHound detector efficiency database
  - Trademark Notice: AlphaHound™ and RadView Detection are trademarks of their respective holders.
  
- **Radiacode SDK**: [cdump/radiacode](https://github.com/cdump/radiacode)
  - Devices: Radiacode 103, 103G, 110
  - License: MIT License
  - Community-developed Python library

### Special Thanks
- **Nick Conner** (RadView Detection) - For creating the AlphaHound device
- **Sandia National Laboratories** - For developing and open-sourcing PyRIID
- **cdump** - For the Radiacode Python library
- **IAEA, NNDC, LBNL, USGS** - For maintaining authoritative gamma-ray databases
- **Open Source Community** - FastAPI, numpy, scipy, Chart.js, TensorFlow, bleak contributors

## System Requirements

- **Python**: 3.10 or higher (tested on 3.10.11)
- **Operating System**: Windows (batch scripts), macOS/Linux compatible with manual commands
- **Hardware**: Optional - RadView Detection AlphaHound™ or Radiacode 103/103G/110 for live acquisition

## Dependencies

### Python Packages (Auto-installed via `install_deps.bat`)

**Core Framework:**
- `fastapi` - Modern web framework for building APIs
- `uvicorn` - Lightning-fast ASGI server
- `python-multipart` - File upload support

**Scientific Computing:**
- `numpy` - Numerical arrays and mathematical operations
- `scipy` - Peak detection algorithms
- `matplotlib` - Spectrum plotting for PDF reports

**Machine Learning (Optional - for AI Identification):**
- `riid` (PyRIID 2.2.0) - Machine learning isotope identification
- `tensorflow` - Neural network backend for ML classifier
- `pandas` - Data structures for ML training

**Device Integration:**
- `pyserial` - Serial communication with AlphaHound device
- `radiacode` - Radiacode device SDK (USB support)
- `bleak` - Cross-platform Bluetooth Low Energy for Radiacode BLE

**Specialized:**
- `SandiaSpecUtils` - Universal spectrum file format support (100+ formats)
- `websockets` - Real-time dose rate streaming
- `reportlab` - PDF report generation
- `slowapi` - API rate limiting

### Frontend (CDN - No Installation Required)
- **Chart.js** - Interactive spectrum visualization
- **chartjs-plugin-zoom** - Zoom/pan capabilities
- **Hammer.js** - Touch gestures for mobile

### Installation
All Python dependencies are automatically installed by running:
```bash
install_deps.bat
```

Or manually:
```bash
pip install -r requirements.txt
```

## License

This viewer is provided under **Apache License 2.0**. See `LICENSE` for details.

## Contributing

PRs and suggestions welcome! Please open an issue for bug reports or feature requests.

---

**Important Reminders:**
1. This is an educational tool - not for professional radiation safety work
2. Always verify isotope identifications with certified methods
3. Consult radiation safety professionals for any safety-related decisions
4. Comply with all applicable radiation regulations and licensing requirements
