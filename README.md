# SpecTrek 🚀

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

**SpecTrek** is a modern, web-based gamma spectroscopy analysis platform with intelligent isotope identification, decay chain detection, and real-time device integration.

## ✨ Key Features

### 📊 Advanced Analysis
- **Multi-Format Support**: N42/XML and CSV file parsing
- **Automated Peak Detection**: Using `scipy.signal.find_peaks`
- **Intelligent Isotope Identification**: 
  - **Simple Mode**: 30 hobby-focused isotopes (uranium glass, mantles, watches)
  - **Advanced Mode**: 100+ isotopes including fission products, activation products, rare earths, and transuranics
- **Decay Chain Detection**: Identifies natural decay series (U-238, U-235, Th-232) with confidence scoring
- **Natural Abundance Weighting**: Scientifically accurate ranking based on LBNL/NRC isotopic abundance data
- **Authoritative References**: Direct links to NNDC, IAEA, LBNL, USGS, NRC sources for each detected chain

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
  - localStorage persistence across sessions

### 🎨 Interactive Visualization
- **Dual Scale Support**: Linear/Logarithmic toggles
- **Advanced Zoom & Pan**: Mouse wheel, pinch, drag interactions
- **Peak Markers**: Automatic labeling with hover tooltips
- **4 Theme Options**: Dark (default), Light, Nuclear (radiation warning), Toxic (biohazard)
- **Multi-File Comparison**: Overlay up to 8 spectra with color coding

### 🔌 AlphaHound Device Integration
- **Direct Serial Communication**: With RadView Detection AlphaHound™ hardware
- **Real-Time Acquisition**: Watch spectrum build live with 2-second updates
- **Timed/Interruptible Counts**: Set duration (e.g., 5 minutes) with early stop capability
- **Live Dose Rate**: WebSocket streaming of μR/hr measurements
- **Automatic Analysis**: Peak detection & isotope ID on acquired data
- **Non-Blocking UI**: Control device while viewing/analyzing spectra

### 📤 Export & Reporting
- **Data Export**: JSON/CSV formats with full spectrum data
- **PDF Reports**: Professional reports including:
  - Spectrum plot visualization
  - Detected peaks table
  - Identified isotopes
  - Decay chains with confidence levels
  - Metadata and timestamps
- **History Management**: Save & reload previous analyses (last 10 files)

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
Double-click **`run.bat`** in the root directory - the application will automatically start and open in your browser at `http://localhost:8080`.

> **Note**: AlphaHound device is **optional** - the application works without hardware connected for N42/CSV file analysis.

### Manual Start
```bash
cd backend
python -m uvicorn main:app --reload --port 8080
```

Then navigate to `http://localhost:8080` and drag & drop an `.n42` or `.csv` file.

## Project Structure

```
N42 viewer/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── n42_parser.py        # Custom N42 XML parser
│   ├── peak_detection.py   # Peak finding algorithm
│   ├── isotope_database.py # Gamma-ray energy database
│   ├── requirements.txt     # Python dependencies
│   └── static/              # Frontend files
│       ├── index.html
│       ├── style.css
│       └── app.js
├── AlphaHound-main/        # AlphaHound integration (see Credits)
├── install_deps.bat        # One-time dependency installer
├── run.bat                 # Quick-start script (no venv required)
└── test.n42                # Sample spectrum file
```

## AlphaHound Integration

This project integrates with [AlphaHound Python Interface](https://github.com/NuclearGeekETH/) by [NuclearGeekETH](https://github.com/NuclearGeekETH) - a desktop GUI for controlling the [RadView Detection AlphaHound™](https://www.radviewdetection.com/) gamma spectrometer.

The AlphaHound interface provides:
- Live dose rate monitoring and logging
- Real-time gamma spectrum acquisition
- N42/CSV export compatibility with this viewer
- Serial communication with AlphaHound hardware

**See `AlphaHound-main/` folder for the full application.**

## Credits & Attribution

### This N42 Viewer
- Developed with FastAPI, Chart.js, scipy, and becquerel
- Custom N42 parser and isotope identification system

### AlphaHound Interface
- **Author**: [NuclearGeekETH](https://github.com/NuclearGeekETH)
- **Device**: [AlphaHound™ by RadView Detection](https://www.radviewdetection.com/)
- **License**: MIT License
- **Trademark Notice**: AlphaHound™ and RadView Detection are trademarks of their respective holders. The AlphaHound interface is an independent, third-party project not affiliated with or endorsed by RadView Detection.

Special thanks to Nick Conner at RadView Detection for creating the AlphaHound device.

## System Requirements

- **Python**: 3.10 or higher (tested on 3.10.11)
- **Operating System**: Windows (batch scripts), macOS/Linux compatible with manual commands
- **Hardware**: Optional - RadView Detection AlphaHound™ for live acquisition

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

**Specialized:**
- `becquerel` - Advanced gamma spectroscopy analysis (optional for CSV support)
- `pyserial` - Serial communication with AlphaHound device
- `websockets` - Real-time dose rate streaming
- `reportlab` - PDF report generation

### Frontend (CDN - No Installation Required)
- **Chart.js** - Interactive spectrum visualization
- **chartjs-plugin-zoom** - Zoom/pan capabilities

### Installation
All Python dependencies are automatically installed by running:
```bash
install_deps.bat
```

Or manually:
```bash
pip install -r backend/requirements.txt
```

## License

This viewer is provided under MIT License. See individual components for their respective licenses.

## Contributing

PRs and suggestions welcome! Please open an issue for bug reports or feature requests.

---

**Important Reminders:**
1. This is an educational tool - not for professional radiation safety work
2. Always verify isotope identifications with certified methods
3. Consult radiation safety professionals for any safety-related decisions
4. Comply with all applicable radiation regulations and licensing requirements
