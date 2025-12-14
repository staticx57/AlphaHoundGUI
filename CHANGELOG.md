# CHANGELOG

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
