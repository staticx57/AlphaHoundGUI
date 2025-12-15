# CHANGELOG

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
