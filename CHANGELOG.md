# CHANGELOG

## [Session 2026-01-04] - Theme Color System Overhaul

### Added
- **Complete Theme CSS Reference**: Created `complete_themes_css.md` with 35 proposed new themes:
  - 8 Sci-Fi themes (Alien Isolation, Pip-Boy, Blade Runner, Tron, Matrix, LCARS, Halo UNSC, Stranger Things)
  - 7 Vintage Test Equipment themes (Beckman, General Radio, Heathkit, Simpson, Lambda, Boonton, Wavetek)
  - 8 Vintage Computing themes (Apple II, C64, IBM 5150, Amiga, VT-100, BBC Micro, Atari ST, ZX Spectrum)
  - 6 Vintage Radiological themes (Canberra Packard, Bicron, TASC, Nuclear Data, Radiation Alert, Radon Scout)
  - 6 Vacuum Tube Display themes (Magic Eye, Dekatron, Numitron, VFD, Cold Cathode, Panaplex)

- **Theme-Responsive Chart Colors**: Main spectrum chart and zoom scrubber now dynamically update when theme changes
  - Added `hexToRgba()` helper method for proper color conversion with transparency
  - Chart line color, fill color, and scrubber mini-preview all use `--primary-color` CSS variable
  - `updateThemeColors()` method refreshes all chart colors on theme switch

- **Status/Confidence Color Variables**: Added theme-specific overrides for 5 vintage equipment themes:
  - Ludlum: Warm tan/orange earth tones (`#d4915c`, `#b87a4a`)
  - Eberline: Vintage orange/gold (`#e07b39`, `#c9a227`)
  - Fluke: Professional yellow/orange (`#ffc107`, `#ff9800`)
  - Keithley: Cool professional blue (`#4a90d9`, `#7eb8f0`)
  - Tektronix: Blue/cyan instrument tones (`#00a2e8`, `#66ccff`)

### Changed
- **`charts.js`**: 
  - Added `hexToRgba()` method for converting hex colors to rgba with opacity
  - `render()` now re-reads `--primary-color` from CSS at render time
  - `updateThemeColors()` now refreshes both main chart and zoom scrubber mini-preview
  - Chart dataset backgroundColor uses `hexToRgba(primaryColor, 0.1)` instead of invalid hex concatenation

- **`main.js`**:
  - Theme change handler now calls `chartManager.updateThemeColors()` before re-rendering
  - Bumped charts.js import version to 4.5 for cache busting

- **`style.css`**:
  - Fixed zoom scrubber selection overlay to use `color-mix(in srgb, var(--primary-color) 25%, transparent)`
  - Added `--status-detected`, `--status-stable`, `--confidence-high/medium/low`, `--xrf-high/medium/low` variables to 5 vintage themes

### Fixed
- **Chart Color Stuck on Initial Theme**: Charts now properly update colors when switching themes without page reload
- **Zoom Scrubber Color Mismatch**: Mini-preview now redraws with correct theme color on theme change
- **Green Confidence Bars in Vintage Themes**: Added theme-appropriate color overrides preventing fallback to green defaults

---

## [Session 2025-12-22] - ML Isotope Identification Improvements

### Added
- **Real Data Augmentation**: New `ml_data_loader.py` loads N42/SPE/CSV spectra with auto-labeling (220 augmented training samples from local data)
- **Environmental Background**: Training now includes K-40, Bi-214, Tl-208 environmental peaks to teach model background immunity
- **Calibration Jitter**: ±10% gain and ±5keV offset variation during training for detector drift robustness
- **Multi-Detector Profiles**: 8 detector configurations (AlphaHound CsI/BGO, Radiacode 103/103G/110/102, Generic NaI)
- **Hybrid Scoring**: New `hybrid_identify()` function combines ML (40%) + peak-matching (60%) for improved accuracy
- **`get_available_detectors()`** API function for UI detector selection

### Changed
- Training epochs increased from 25 to 50 for better convergence
- MLIdentifier constructor now accepts `detector` parameter
- Model cache now keyed by both model_type and detector

---

## [Session 2025-12-22] - Documentation Overhaul & Chart Fixes

### Changed
- **README.md Major Overhaul**: Comprehensive update reflecting all recent features:
  - Added Radiacode 103/103G/110 device integration section with device comparison table
  - Added XRF element identification feature
  - Added SNIP background filtering description
  - Added spectrum algebra features
  - Documented server-managed acquisitions with crash recovery
  - Updated project structure with new backend files
  - Added bleak dependency for cross-platform BLE
  - Updated credits with radiacode SDK attribution

- **RADIACODE_INTEGRATION_PLAN.md**: Updated completion status:
  - Marked all success criteria as completed
  - Updated platform support table showing cross-platform BLE via bleak

- **TODO.md**: Updated task tracking:
  - Added "Replace Remaining Emoji with SVG Icons" task (~40 instances)
  - Added "Chart Autoscale & Label Stacking" as completed
  - Added "Documentation Overhaul" as completed

### Fixed
- **Chart Autoscale**: Spectrum chart autoscale toggle now correctly switches between peak-focused zoom and full spectrum view
- **Annotation Label Stacking**: XRF and isotope peak labels now stack vertically to prevent overlapping

---

## [Released - Session 2025-12-16] - Decay Prediction & Universal File Support

### Added
- **Decay Prediction System (Hybrid Engine)**
  - **Interactive UI**: "⏳ Decay Prediction" tool in Analysis panel with log-scale visualization.
  - **Hybrid Backend**:
    - **Primary**: Uses `curie` (nuclear-curie) for authoritative half-life and decay data (Integrated & Verified).
    - **Fallback**: Custom Bateman Solver (Python) ensures functionality even without C++ dependencies.
  - **Features**: U-238 and Th-232 chain simulation, user-definable activity/duration.
  - **Endpoint**: `/analyze/decay-prediction`.

- **Universal Spectrum Support (SandiaSpecUtils)**
  - Integrated `SandiaSpecUtils` wrapper to handle 100+ file formats.
  - Supports: `.spc`, `.pcf`, `.mca`, `.dat`, `.cnf` and many legacy formats.
  - Seamless fallback: Backend automatically tries generic parser if native N42/CSV fails.

- **Activity & Dose Rate Calculator**
  - **Centralized Logic**: New `activity_calculator.py` module for rigorous physics math.
  - **Features**: 
    - Bq/μCi conversion (fixed 1000x scaling bug).
    - Gamma Dose Rate estimation from activity and distance.
    - MDA (Minimum Detectable Activity) calculations.
  - **Refactor**: ROI analysis now uses this shared engine for consistent results.

- **UI & UX Polish**
  - **Smart Activity Population**: Decay Prediction tool automatically pulls "Initial Activity" (Bq) from the last performed ROI Analysis.
  - **Chart Visualization**: Decay chart now uses clean scientific notation (e.g., `1e-5`, `100`) on the logarithmic Y-axis to prevent label clutter.
  - **Layout Fixes**: Improved responsiveness of ROI Analysis panel to prevent input field overlap on smaller screens.

### Fixed
- **Activity Unit Display**: Fixed frontend bug where μCi values were erroneously multiplied by 1000.
- **Ra-226 Interference**: 
    - Implemented "Forced Subtraction" for Uranium Glass mode.
    - System now attempts to estimate and subtract Ra-226 contribution from 186 keV peak even with weak Bi-214 signals.

---

## [Unreleased - Session 2025-12-16] - Source Identification & ROI V2

### Added
- **Source Type Identification**
  - **Auto-Suggest**: Rule-based identification of common sources (Uranium Glass, Thoriated Lenses, Radium Dials, Smoke Detectors).
  - **User-Driven Context**: New "Source Type" dropdown in ROI Analysis panel allows users to specify what they are measuring.
  - **Systematic Validation**: Checks detected isotopes against the expected profile of the selected source.
    - Warns if unexpected isotopes are analyzed (e.g., U-235 in a Thoriated Lens).
    - Prevents misleading "Natural Uranium" classification for mixed/Thoriated sources.

- **Enhanced ROI Analysis**
  - **Context-Aware Logic**: Uses source type selection to inform analysis assumptions.
  - **Ra-226 Interference Handling**:
    - "Standard Analysis" (Default): Flags interference only if Bi-214 is detected.
    - "Uranium Glass" Mode: Proactively assumes Ra-226 interference (secular equilibrium) and warns about U-235 enrichment uncertainty.
  - **Diagnostic Feedback**: Detailed feedback on *why* a result is indeterminate (e.g., "Overlapping peaks", "Low SNR").

### Changed
- **ROI UI Layout**
  - Compact grid layout for better space utilization.
  - "Standard Analysis" is now the default mode (no assumptions).
  - Minimized info banners to reduce clutter.

---

## [Unreleased - Session 2025-12-15 PM] - Server-Side Acquisition Management

### Added
- **Server-Side Acquisition Timer (Critical Robustness Feature)**
  - Root cause of unfinalized acquisitions: Browser JS timer throttled during display sleep
  - Solution: Acquisition timing now managed entirely by Python backend
  - Survives browser tab throttling, display sleep, and tab closure
  - New module: `backend/acquisition_manager.py` with `AcquisitionManager` singleton
  - New endpoints:
    - `POST /device/acquisition/start` - Start managed acquisition
    - `GET /device/acquisition/status` - Poll current state (includes spectrum data)
    - `POST /device/acquisition/stop` - Stop and finalize
    - `GET /device/acquisition/data` - Get latest spectrum data
    - `GET /device/spectrum/current` - Get cumulative device spectrum

- **Cumulative Spectrum Endpoint**
  - `GET /device/spectrum/current` - Get whatever's on the device without clearing
  - Useful for checking device accumulation or resuming after browser disconnect
  - Based on legacy AlphaHound `G` command behavior

### Changed
- **`main.js`**: `startAcquisition()` now uses server API instead of `setInterval`
- **`api.js`**: Added `startManagedAcquisition()`, `getAcquisitionStatus()`, `stopManagedAcquisition()`, `getAcquisitionData()`
- Frontend now polls server for status; timing accuracy independent of browser

## [Unreleased - Session 2025-12-15 PM2] - Serial Command Discovery & UI Enhancements

### Discovered (via serial probing)
- **Undocumented AlphaHound serial commands:**
  - `E` - Cycle display mode FORWARD
  - `Q` - Cycle display mode BACKWARD
  - `K` - Get device config (actThresh, NoiseFloor)
  - `L` - Get activity threshold
  - `DB` - **Correct dose rate** (matches device display)
  - Device uses single-character command parsing
- Full documentation: `docs/ALPHAHOUND_SERIAL_COMMANDS.md`

### Added
- **Display Mode Control UI**
  - ◀/▶ buttons in device panel to cycle display modes remotely
  - New endpoint: `POST /device/display/{next|prev}`
  - Uses newly discovered `E` and `Q` commands

- **Get Current Spectrum Button**
  - Downloads cumulative spectrum without clearing device
  - Useful for checking accumulation or recovering after disconnect

- **Clear Spectrum Button**
  - Manually reset device spectrum with confirmation dialog
  - New endpoint: `POST /device/clear`
  - Uses `W` command (tested and confirmed)

- **Temperature Display**
  - Shows device temperature (🌡️) next to dose rate
  - Updated from spectrum metadata (Temp field)

- **Server-Managed Acquisition Indicators**
  - "SERVER-MANAGED" badge when acquisition is running
  - Info message: "You can close this tab and it will continue"

### Fixed
- **Dose rate now uses `DB` command** instead of `D`
  - Statistical analysis confirmed D/DA/DB are identical
  - `DB` chosen as it synchronized best with device display

---

## [Unreleased - Session 2025-12-15] - Acquisition Resilience & Reference Links

### Fixed
- **8-Hour Acquisition Limit Bug (Critical)**
  - Root cause: `MAX_ACQUISITION_MINUTES = 60` caused 422 validation error for 480-minute capture
  - Fix: Increased limit to 1440 (24 hours) in `backend/routers/device.py`
  - Long acquisitions now complete and auto-save correctly

### Added
- **Acquisition Crash Recovery**
  - Periodic checkpoint saves every 5 minutes during acquisition
  - Single overwriting file: `data/acquisitions/acquisition_in_progress.n42`
  - If acquisition fails, checkpoint contains all data up to last save
  - Automatic cleanup after successful completion
  - New endpoints: `POST /export/n42-checkpoint`, `DELETE /export/n42-checkpoint`

- **Device Write Retry Logic**
  - Serial write operations now retry 3 times before disconnecting
  - Prevents transient USB timeouts from killing long acquisitions
  - All device log messages now include timestamps for debugging

- **NNDC Reference Links for Isotopes**
  - Each identified isotope now has a clickable "📚 NNDC" link
  - Links directly to NNDC NuDat3 decay data page
  - Example: Cs-137 links to `https://www.nndc.bnl.gov/nudat3/decaysearchdirect.jsp?nuc=137Cs`

- **Authoritative Source References for Decay Chains**
  - Decay chain cards now display NNDC, IAEA, and other reference links
  - U-238, Th-232, U-235 chains include 3 authoritative sources each
  - Links open in new tab for easy research

- **SNIP Background Filtering** (NEW)
  - "🔻 Auto Remove BG" button in Analysis → Background Subtraction
  - Removes Compton continuum without requiring separate background file
  - Uses industry-standard SNIP (Sensitive Nonlinear Iterative Peak) algorithm
  - Re-runs peak detection and isotope ID on cleaner data
  - Improves detection of weak peaks buried in continuum

## [Unreleased]

### Added
- **UI Enhancements**: Added a toggle button and scrollable area for the "Detected Peaks" table to improve dashboard usability with many peaks.
- **Spectrum Algebra**: Added UI controls for adding, subtracting, and comparing spectra.
- **ML Quality Badges**: Added visual indicators for ML confidence (High/Medium/Low) and suppression status.
- **Responsive Charts**: Enabled pinch-to-zoom and touch gestures for mobile users. Added `Hammer.js` and optimized touch interactions.

### Fixed
- **Chart Auto-Scale**: Tuned autoscale algorithm to prevent aggressive cropping of high-energy data. Now prioritizes full data visibility over noise reduction.
- **N42 Import/Export**: Fixed a critical bug where acquisition time (Live Time/Real Time) was lost when re-importing auto-saved files. Corrected the JSON payload structure in `main.js`.
- **Peak Matching**: Restored legacy peak matching functionality and integrated it with ML predictions for hybrid filtering.

- **CHN/SPE File Import** (NEW)
  - Support for Ortec CHN (binary) and Maestro SPE (ASCII) formats
  - Automatic energy calibration extraction
  - Full analysis pipeline on import (peaks, isotopes, chains)
  - New: `backend/chn_spe_parser.py`

- **Spectrum Algebra** (NEW)
  - Add, subtract, normalize, compare spectra
  - Proper Poisson error propagation
  - Live time normalization support
  - Endpoint: `POST /analyze/spectrum-algebra`
  - New: `backend/spectrum_algebra.py`

- **ONNX/TFLite Model Export** (NEW)
  - Export trained ML models for mobile/edge deployment
  - ONNX format for desktop inference
  - TFLite format for Android/iOS apps
  - Endpoint: `POST /analyze/export-model`

- **Anomaly Detection** (NEW)
  - Flag unusual spectra that don't match training data
  - Multi-factor scoring: ML confidence, peak/BG ratio, entropy
  - Endpoint: `POST /analyze/anomaly-detection`

- **Poisson Peak Fitting** (NEW)
  - Maximum likelihood estimation for low-count peaks
  - Proper counting statistics uncertainty
  - More robust than least-squares for weak signals
  - New: `poisson_peak_fit()` in `spectral_analysis.py`

- **ML Hybrid Filtering** (NEW)
  - Confidence thresholding: 5% minimum to display predictions
  - Hybrid filtering: Suppresses medical isotopes when natural chains detected
  - Quality badges: "✓ High Confidence", "⚠ Moderate", "⚠ Low Confidence"
  - Suppressed predictions shown dimmed with "(suppressed)" label

### Changed
- **`alphahound_serial.py`**: `_write()` method now has retry loop with exponential backoff
- **`ui.js`**: Added `getNNDCUrl()` helper, enhanced `renderIsotopes()` and `renderDecayChains()`
- **`spectral_analysis.py`**: Added `snip_background()` and `poisson_peak_fit()` functions
- **`analysis.py`**: 6 new endpoints for SNIP, ML export, spectrum algebra, anomaly detection
- **`ml_analysis.py`**: Added `export_model()`, `_export_onnx()`, `_export_tflite()` methods
- **`main.js`**: ML predictions now show quality badges and suppression indicators
- **`isotope_database.py`**: Major peak matching improvements:
  - Contextual suppression: Medical/fission isotopes suppressed when natural decay chains detected
  - Single-line isotopes capped at 60% confidence (prevents 1/1 = 100% false positives)
  - Peak count penalty: 30% penalty for single matches, 10% bonus for 3+ matches
  - All decay chains (U-238, Th-232, U-235) now properly defined and tracked
- **Detected Peaks Table**: Completely redesigned with sticky headers, backdrop blur, hover effects, and right-aligned numerical data (v6 CSS).
- **Isotope Identification**: Implemented intensity-weighted scoring to prioritize diagnostic peaks (fixes weak Pb-212/Pb-214 confusion).
- **Decay Chain Logic**: Enforced stricter confidence threshold (>40%) for flagging Uranium/Thorium chains.
- **Detector Calibration**: Reconfigured backend to enforce 3.0 keV/channel (replacing device's 7.4 default) for accurate peak alignment.

### Fixed
- **Page Load Crash**: Fixed `main.js` syntax error (extra brace) that prevented application load.
- **Auto-BG Chart Sync**: Fixed visual issue where peaks appeared disconnected from the spectrum after background removal.
- **Chart Render Crash**: Fixed "Spread syntax" error when rendering invalid or background-subtracted data (validation added to `charts.js`).

---

## [Unreleased - Session 2025-12-14 Late] - ML Model Selection & N42 Auto-Save

### Added
- **Compton Continuum Simulation** (ml_analysis.py)
  - `add_compton_continuum()` method for realistic CsI(Tl) detector response
  - Calculates Compton edge and distributes ~35% of peak counts to continuum
  - Applied to all synthetic training peaks

- **Selectable ML Model Types**
  - `HOBBY_ISOTOPES` list with 35 common isotopes (uranium glass, mantles, calibration)
  - `ML_MODEL_TYPES` config: hobby (35 isotopes, 30 samples) vs comprehensive (95+, 15 samples)
  - `get_ml_identifier(model_type)` caches separate instances per model
  - `get_available_ml_models()` for future settings UI integration

- **N42 Auto-Save Format** (default)
  - New `/export/n42-auto` endpoint replaces `/export/csv-auto`
  - Auto-saves to `data/acquisitions/spectrum_YYYY-MM-DD_HH-MM-SS.n42`
  - Includes peaks, isotopes, live_time, real_time in saved files
  - Standards-compliant N42.42 format for better portability

### Fixed
- **N42 Auto-Save Import Error**
  - Fixed wrong function name: `create_n42_xml` → `generate_n42_xml`
  - Auto-save now works correctly after server restart

---

## [Unreleased - Session 2025-12-14 PM] - PyRIID Enhancement & Peak Detection Fix

### Added
- **IAEA Data Integration**
  - Downloaded 49 isotope gamma data files from IAEA LiveChart API
  - 2,499 gamma lines with intensity data (e.g., Bi-214 @ 609 keV = 45.44%)
  - New `backend/iaea_parser.py` for parsing IAEA CSV format
  - Isotope database now loads IAEA intensity data on startup

- **Authoritative Data Scripts**
  - `download_iaea_data.py` - Downloads gamma data for priority isotopes
  - Data stored in `backend/data/idb/isotopes/`

### Fixed
- **Peak Detection Threshold Too Strict (Critical)**
  - Before: Only 3 peaks detected (prominence_factor=0.05 was 5% of max)
  - After: 20+ peaks detected with new balanced thresholds
  - Changed to `max(5, max_count * 0.003)` for height, `max(3, max_count * 0.002)` for prominence
  - File: `backend/peak_detection.py`

- **U-235/U-238 Prioritization**
  - U-238 now ranks #2 at 100% (was incorrectly below U-235)
  - U-235 now ranks #26 at 0.1% with suppression when U-238 chain detected
  - Added abundance weighting to `backend/isotope_database.py`

### Changed
- **ML Training Data** (backend/ml_analysis.py)
  - Synthetic peaks now use IAEA intensity weighting
  - Calibration updated to 7.4 keV/channel (AlphaHound actual)
  - Imports `get_gamma_intensity()` for realistic peak heights

- **AI Identification UI Label**
  - Added "WIP" badge to indicate ML model is still experimental
  - Peak Matching remains the recommended method

### Verified
- Community spectra test: 5/6 files correctly suppress U-235
- All 6 files detect U-238 at 60%+ confidence
- Bi-214, Pb-214, Th-234 now visible in UI

---

## [Unreleased - Session 2025-12-14] - N42 Export & Parser Improvements

### Added
- **N42 XML Export (Complete Implementation)**
  - Standards-compliant N42.42-2006 XML export from device acquisitions
  - Full 1024-channel spectrum with energy calibration
  - Proper ISO 8601 duration format (`PT60.000S`) for LiveTime/RealTime
  - Isotope identification results included as SpectrumExtension
  - Instrument information (manufacturer, model, serial number)
  - "Export N42" button in controls bar

- **Enhanced N42 Parser (Graceful Fallbacks)**
  - Multi-namespace support (N42.42-2006, N42.42-2011, no-namespace)
  - ISO 8601 duration parsing (`PT##H##M##.###S` → seconds)
  - Extracts instrument info for proper SOURCE display (e.g., "RadView Detection AlphaHound")
  - Searches multiple element locations for legacy file compatibility
  - Coefficient-based energy calibration support
  - Creates default channel array if no energies found

- **Improved Auto-Scale (Chart)**
  - 99% cumulative count algorithm for smarter X-axis trimming
  - 15% right buffer + 5% left buffer for visual appeal
  - Y-axis scaled to visible data region only
  - Minimum zoom: 200 keV or 10% of full range
  - Peak protection: never clips detected peaks

### Fixed
- **N42 Export "cannot serialize 100 (type int)" error**
  - All XML text values now wrapped with `str()` to prevent integer serialization
  - Affects: isotope confidence, energy values, timestamps, instrument info

- **422 Unprocessable Entity error**
  - Added `N42ExportRequest` Pydantic model for proper request validation
  - Replaced generic `dict` type hint with structured model

- **N42 Parser timing extraction**
  - LiveTime extracted from `<Spectrum>` element
  - RealTime extracted from `<RadMeasurement>` element
  - Proper ISO 8601 duration parsing (was failing on `PT1.000S`)

### Changed
- **Export Buttons Styling**
  - Export PDF and Export N42 now both use `.btn-accent` class
  - Consistent appearance that adapts to all themes
  - Removed hardcoded inline styles

- **Backend API**
  - `/export/n42` endpoint uses Pydantic model validation
  - Uses `model_dump()` instead of deprecated `dict()`

### Technical Notes
- N42 exporter: `backend/n42_exporter.py` (200 lines)
- N42 parser: `backend/n42_parser.py` (175 lines)  
- Auto-scale: `backend/static/js/charts.js` (lines 24-78)
- Request model: `backend/routers/analysis.py` (lines 80-88)

---

## [Unreleased - Session 2025-12-12] - Project Cleanup & Maintenance

### Changed
- **Project Directory Cleanup**
  - Archived 49+ files (~7.6 MB) to organized subdirectories
  - Created structured archive organization:
    - `archive/test_scripts/` - 31 test/debug/check scripts
    - `archive/backup_files/` - 1 backup file (app.js.bak)
    - `archive/icon_backups/` - 12 old PNG/JPG icons
    - `archive/sample_data/` - 1 test CSV file
    - `archive/planning_docs/` - 2 research documents
  - Reduced backend directory from 48 to 17 Python files
  - Reduced root directory from 18 to 15 files
  - Improved project navigation and maintainability
  - All files preserved in archive (no deletions)

---

## [Unreleased - Session 2025-12-12] - Technical Debt & Feature Polish


### Added
- **Rate Limiting (Security)**
  - Integrated `slowapi` middleware for API rate limiting
  - Default: 60 requests per minute per IP address
  - Protects against API abuse and denial-of-service

- **Custom Isotope Import/Export**
  - `GET /isotopes/custom/export` - Download all custom isotopes as JSON
  - `POST /isotopes/custom/import` - Import isotopes from JSON file
  - UI buttons: "📥 Import JSON" and "📤 Export JSON" in Custom Isotopes modal
  - Supports bulk import/export for library sharing

- **Apache License 2.0**
  - Created `LICENSE` file with full Apache 2.0 text
  - Added `.github/FUNDING.yml` stub for GitHub Sponsors

### Fixed
- **COUNT TIME Metadata Bug**
  - Fixed Pydantic type annotation (`Optional[float]`) for `actual_duration_s`
  - Frontend now passes actual elapsed time to backend on acquisition completion
  - Metadata `count_time_minutes` now shows real duration, not requested duration

### Changed
- **README.md Updates**
  - Added ROI Analysis credits to NuclearGeekETH (same author as AlphaHound connector)
  - Updated image paths to relative format for GitHub compatibility
  - Updated license section to Apache 2.0

- **Device Panel Enhancement**
  - Split layout with controls left, live data right
  - Consolidated inline controls for cleaner UI
  - Added 5-minute dose rate sparkline chart

- **ML AlphaHound Tuning**
  - Energy-dependent FWHM matching CsI(Tl) resolution (10% at 662 keV)
  - Scintillator resolution model: FWHM(E) = 0.10 × E × √(662/E)
  - Improved training spectra realism for better AlphaHound data recognition

- **UI Polish (2025-12-12)**
  - Replaced emoji with SVG icons in Custom Isotopes modal (Import/Export)
  - Fixed Custom Isotopes modal layout with proper grid alignment
  - Increased modal width to 650px for better spacing
  - Fixed COUNT TIME precision to 2 decimal places (was showing 15+ decimals)
  - Changed metadata "TOOL" field to "SOURCE" with user-friendly values:
    - "CSV File" or "CSV File (Becquerel)"
    - "N42 File"
    - "AlphaHound Device"

### Documentation
- **PYRIID_GUIDE.md**: Comprehensive 400+ line guide covering:
  - How PyRIID works (architecture, training, prediction)
  - AlphaHound detector tuning details
  - 10 ways users can extend/enhance ML functionality
  - Usage instructions and best practices

### Dependencies Added
- `slowapi` - Rate limiting for FastAPI endpoints

---

## [Unreleased - Session 2025-12-11] - ML Integration & UI Enhancements

### Added
- **ML Integration (PyRIID 2.2.0)**
  - Neural network-based isotope identification
  - Training on 90+ isotopes from IAEA/NNDC authoritative databases
  - Multi-isotope mixture support (7 realistic source types):
    - UraniumGlass (U-238 chain with Bi-214 dominance)
    - UraniumGlassWeak (lower intensity variant)
    - ThoriumMantle (Th-232 chain with Tl-208 @2614 keV)
    - MedicalWaste (Tc-99m, I-131, Mo-99)
    - IndustrialGauge (Cs-137, Co-60)
    - CalibrationSource (Am-241, Ba-133, Cs-137, Co-60)
    - NaturalBackground (K-40, Bi-214, Tl-208)
  - ~1500 training samples (1350 single isotopes + 150 mixtures)
  - `/analyze/ml-identify` API endpoint
  - Best suited for real detector data with Poisson statistics

- **Graphical Decay Chain Visualization**
  - Visual flow diagrams showing parent → daughter → stable sequences
  - Color-coded detection status:
    - Green glow: Detected members with "✓ DETECTED" badge
    - Purple dashed border: Stable end products with "STABLE" badge
    - Dimmed grey: Undetected chain members
  - Horizontal scrolling for long decay chains
  - Legend explaining color codes
  - Supports all 3 natural chains (U-238, Th-232, U-235)

- **Dual Isotope Detection Panel**
  - Side-by-side comparison view:
    - **Peak Matching (Legacy)**: Traditional energy-based identification from IAEA/NNDC
    - **AI Identification (ML)**: PyRIID neural network pattern recognition
  - Each panel styled distinctly with appropriate visual cues
  - Info bar explaining detection methodologies

- **Graphical Confidence Bars**
  - Animated progress bars replacing static percentage text
  - Color-coded confidence levels:
    - Green (#10b981): HIGH confidence (>70%)
    - Yellow (#f59e0b): MEDIUM confidence (40-70%)
    - Red (#ef4444): LOW confidence (<40%)
    - Purple (#8b5cf6): ML predictions with gradient effects
  - Smooth CSS transitions for visual polish
  - Labels showing isotope name, confidence percentage, and detection method

- **UI/UX Enhancements**
  - "🤖 AI Identify" button in isotopes container
  - Loading states during ML training/prediction (~10-30s first run)
  - Informative messages about ML data requirements
  - Professional card-based layouts for isotope results
  - **Toast Notification System**: Non-blocking slide-in notifications with auto-dismiss

- **Auto-Save CSV Feature**
  - Automatically saves acquired spectra to CSV after completion
  - Saves to `backend/data/acquisitions/` directory
  - Timestamped filenames: `spectrum_YYYY-MM-DD_HH-MM-SS.csv`
  - Toast notification confirms save with filename
  - `/export/csv-auto` API endpoint

### Changed
- **Updated `ml_analysis.py`**:
  - Rewrote synthetic training data generation to use proper SampleSet structure
  - Fixed PyRIID 2.2.0 API compatibility (spectra as 2D DataFrame, 3-level MultiIndex for sources)
  - Enhanced training with realistic peak intensity ratios
  - Tuned mixture ratios based on authoritative gamma spectroscopy data

- **Updated `ui.js`**:
  - `renderIsotopes()`: Now populates `legacy-isotopes-list` with confidence bars
  - `renderDecayChains()`: Added graphical flow diagram generation
  - Added `getChainMembers()` helper method for complete decay sequences

- **Updated `main.js`**:
  - Added `btn-run-ml` click handler for AI Identify button
  - Enhanced ML results display with gradient confidence bars
  - Loading state management with button disable/enable

- **Updated `index.html`**:
  - Replaced simple isotope table with dual-panel detection layout
  - Added info bar explaining ML data requirements and limitations
  - Improved visual hierarchy and spacing

### Fixed
- PyRIID 2.2.0 compatibility issues:
  - Correct `spectra_type=3` (Gross) and `spectra_state=1` (Counts)
  - Proper 3-level MultiIndex for sources DataFrame: `('Radionuclide', 'Isotope', '')`
  - In-place prediction modification handling
  - Extraction of results from `prediction_probas` attribute
- **COUNT TIME Metadata Display**: Fixed `renderMetadata()` in `ui.js` to use `replaceAll()` instead of `replace()` for formatting keys, and added proper value formatting ("5 min" instead of "-")

### Known Issues & Limitations
- **ML Pattern Mismatch**: Synthetic demo files (constant background, sharp peaks) don't match ML training (Poisson noise, Gaussian peaks)
  - Workaround: ML works best with real detector data
  - Future: Update demo files to use realistic Poisson noise, or implement hybrid filtering
- **Confidence Thresholding**: ML currently shows all predictions regardless of confidence
  - Future: Add >90% confidence threshold or hybrid filtering with Peak Matching

### Documentation
- Updated `TODO.md` with ML accomplishments and future improvements
- Updated `README.md`:
  - Added ML Integration to features
  - Added Graphical Decay Chain Visualization to features
  - Added Dual Detection Panel and Confidence Bars to UI section
  - Expanded Dependencies section with PyRIID and TensorFlow
  - Enhanced Credits & Attribution with comprehensive acknowledgments:
    - Sandia National Laboratories (PyRIID)
    - IAEA, NNDC, LBNL, USGS (authoritative databases)
    - Google Gemini/Claude 4.5 Sonnet (development assistance)
- Created comprehensive `walkthrough.md` documenting:
  - ML integration process and challenges
  - PyRIID 2.2.0 API discoveries
  - Multi-isotope mixture rationale
  - Known limitations and recommendations

### Dependencies Added
- `riid` (PyRIID 2.2.0) - Machine learning isotope identification
- `tensorflow` - Neural network backend
- `pandas` - Data structures for ML

### Technical Notes
- ML training: 15-25 epochs on 1500 samples takes ~30-60s on first run
- Model cached in memory after training (no disk persistence)
- Training samples use synthetic spectra with Gaussian peak shapes and Poisson statistics
- Energy calibration: 3 keV/channel (typical NaI detector)
- Channel count: 1024 (0-3069 keV range)

### Testing
- ✅ Standalone ML test: 100% UraniumGlass identification
- ✅ Peak Matching: Correct on all test data
- ✅ Decay Chains: Correct detection and graphical visualization
- ⚠️ ML on synthetic demos: Pattern mismatch (expected behavior documented)

---

## Previous Versions
See `TODO.md` for history of completed features from earlier sessions.
