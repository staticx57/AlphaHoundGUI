# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added - v1.9 (Deployment Improvements)
- **Simplified Setup**:
  - Removed virtual environment requirement
  - Created `install_deps.bat` for one-time dependency installation
  - Created `run.bat` for simplified application startup
  - Dependencies now install to system Python user packages
- **Enhanced User Experience**:
  - No venv activation required - just run `run.bat`
  - Application works without AlphaHound device connected
  - Clearer error messages and installation feedback
- **Documentation Updates**:
  - Updated README.md with new installation instructions
  - Added deployment walkthrough


### Added - v1.0 (Initial Release)
- **Multi-Format Support**: Added robust handling for `.n42` (custom parser) and `.csv` (via `becquerel`) files.
- **Frontend**: Created a modern, responsive "Vanilla JS" frontend without build steps.
  - Interactive Chart.js integration.
  - Log/Linear scale switching.
  - Drag-and-drop file upload.
- **Backend**: FastAPI server with static file serving and error handling.
- **Parsers**:
  - `n42_parser.py`: Custom implementation to handle N42 XML structure independently of external libraries.
- **Documentation**: Initial `README.md`, `TODO.md`, and `CHANGELOG.md`.

### Added - v1.1 (Enhancements)
- **Advanced Analysis**:
  - Automatic peak detection using `scipy.signal.find_peaks`
  - Peak table display showing top detected peaks
  - Peak annotations on chart with visual markers
- **UI/UX Improvements**:
  - Chart zoom/pan capabilities using `chartjs-plugin-zoom`
  - Export to JSON feature
  - Export to CSV feature
  - Reset zoom button
  - Enhanced styling and layout
- **Backend Enhancements**:
  - `peak_detection.py` module for automated spectral analysis

### Added - v1.2 (Isotope Identification)
- **Isotope Database**:
  - Comprehensive gamma-ray energy database for 30+ common isotopes
  - Automatic isotope identification from detected peaks
  - Confidence scoring for isotope matches
  - Support for medical, industrial, natural background, and fission product isotopes
- **UI Enhancements**:
  - Isotope identification table with confidence levels
  - Color-coded confidence indicators (high/medium/low)
  - Matched gamma-ray lines display

### Added - v1.3 (UI & UX Enhancements)
- **Theme Toggle**:
  - Light/Dark mode switcher with localStorage persistence
  - Smooth transitions between themes
  - Automatically adapts chart colors to theme
- **File History**:
  - Local storage of last 10 uploaded files
  - Quick-access history modal
  - Preview of peaks and identified isotopes for each file
- **Improved UX**:
  - Header controls for easy access to theme and history
  - Modal interface for browsing file history
  - Enhanced responsive design

### Added - v1.4 (Safety & Integration)
- **Safety Warnings**:
  - Comprehensive radiation safety disclaimer in README
  - Critical warnings about professional use limitations
  - Regulatory compliance reminders
- **AlphaHound Integration**:
  - Integrated AlphaHound Python Interface by NuclearGeekETH
  - Full attribution and credit to original author
  - Compatible with N42 exports from AlphaHound device
  - Documentation of RadView Detection AlphaHound™ compatibility
- **Documentation Enhancements**:
  - Expanded README with safety-first approach
  - Clear project structure documentation
  - Detailed credit sections for all contributors

### Added - v1.5 (Multi-Spectrum Comparison)
- **Comparison Mode**:
  - Overlay multiple N42/CSV spectra on single chart
  - Compare up to 8 spectra simultaneously
  - Color-coded spectrum lines for easy identification
  - Add/remove spectra dynamically during comparison
  - Legend showing all loaded spectra
- **Enhanced Chart Features**:
  - Comparison mode maintains zoom/pan functionality
  - Works with both linear and logarithmic scales
  - Clear all overlays with one click
  - Automatic color assignment from palette

### Added - v1.6 (AlphaHound Device Integration)
- **Live Device Control**:
  - Direct serial communication with RadView Detection AlphaHound™
  - Port detection and connection management
  - Real-time dose rate monitoring via WebSocket
  - Live spectrum acquisition from hardware
- **Unified Interface**:
  - Integrated device control panel in web UI
  - Automatic peak detection and isotope ID on acquired spectra
  - Compare live device data with historical N42 files
  - Export device acquisitions as N42/CSV
- **Technical Implementation**:
  - `alphahound_serial.py` - Serial communication module
  - 8 RESTful API endpoints for device control
  - WebSocket streaming for live dose updates
  - Based on AlphaHound Python Interface by Nuclear GeekETH
- **Credits**:
  - AlphaHound interface logic by NuclearGeekETH
  - RadView Detection AlphaHound™ device support

### Added - v1.7 (Live Acquisition & UI Refactor)
- **Live Spectrum Building**:
  - Incremental graph updates (every 2s) during acquisition.
  - Watch peaks emerge in real-time.
- **Non-Blocking Sidebar**:
  - Replaced modal with slide-out sidebar for device control.
  - Allows full interaction with chart (zoom/pan) while device is connected/acquiring.
- **Performance**:
  - Increased serial baudrate to 115200 for faster data transfer.
- **Timed Acquisition Fixed**:
  - Robust handling of count duration with reliable auto-stop.

### Fixed
- Addressed environment constraints (missing Node.js) by pivoting to Vanilla JS.
- Addressed broken `becquerel` N42 support by implementing a custom fallback parser.
- Fixed static file serving routing conflicts in FastAPI.

### Added - v1.8 (Stability & Reporting)
- **PDF Reporting**:
  - Generate and download professional PDF reports using `reportlab`.
  - Content includes: Spectrum plot, Metadata, Peak Table, Isotopes, and Disclaimer.
- **Backend Refactoring**:
  - Extracted CSV parsing logic into modular `csv_parser.py` (Tech Debt).
  - Improved `main.py` readability.
- **Critical Stability Fixes**:
  - **Serial Connection**: Completely rewrote `alphahound_serial.py` to use a simplified, robust read loop.
  - **Zombie Killer**: Eliminated 10+ persistent background Python processes that were causing port conflicts (Moved server to Port 8081).
### Added - v2.0 (Analysis Robustness)
- **Robust Uncalibrated Support**:
  - Implemented smart detection for uploaded CSV/N42 files that lack energy calibration (channel-based).
  - Automatically applies relaxed thresholds (1% confidence, 30 keV tolerance) for uploads.
  - Ensures robust detection of Uranium Glass and other sources from community files.
- **Settings Separation**:
  - Live Acquisition now uses strict "Gold Standard" settings (30% confidence) to prevent false positives (like U-235).
  - File Uploads use permissive "Robust" settings to handle data quality variance.
- **UI Fixes**: 
  - Resolved text overlap in metadata panel for long filenames using CSS `word-break`.
- **Backend Refactoring**:
  - Updated `main.py` to route logic based on data source (Upload vs Live).
  - Simplified CSV parser pipeline to use full analysis stack.
