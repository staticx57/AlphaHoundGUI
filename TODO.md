# TODO

## Completed ✅
- [x] **Advanced Analysis**:
    - ✅ Use `scipy.signal.find_peaks` for automatic peak detection and labeling.
    - ✅ Isotope identification database with 100+ isotopes (Simple: 30, Advanced: 100+)
    - ✅ Decay chain detection (U-238, U-235, Th-232 series)
    - ✅ Confidence scoring with natural abundance weighting
    - ✅ **Graphical Decay Chain Visualization**: Visual flow diagrams showing parent→daughter→stable sequences with detected members highlighted
- [x] **Export Options**:
    - ✅ Allow exporting parsed data to JSON or CSV from the UI.
    - ✅ Generate PDF reports with spectrum plot, peaks, isotopes, and decay chains
- [x] **UI Improvements**:
    - ✅ Add zoom/pan capabilities to the chart (using `chartjs-plugin-zoom`).
    - ✅ Light/Dark mode toggle with localStorage + Nuclear/Toxic bonus themes
    - ✅ Multi-file comparison (overlay multiple spectra)
    - ✅ **Dual Isotope Detection Panel**: Side-by-side Peak Matching (Legacy) vs AI Identification (ML)
    - ✅ **Graphical Confidence Bars**: Animated progress bars with color-coded confidence levels
    - ✅ **Professional Icon System**: SVG icons replacing all emojis with consistent styling
- [x] **Data Management**:
    - ✅ Save upload history to local storage
- [x] **AlphaHound Device Integration**:
    - ✅ Serial communication with RadView Detection AlphaHound™
    - ✅ Live dose rate monitoring via WebSocket
    - ✅ Real-time spectrum acquisition (Live Building) with timed/interruptible counts
    - ✅ Non-blocking Sidebar UI for device control
    - ✅ Integrated device control panel
    - ✅ **Device Panel Enhancement**:
        - ✅ Split layout (Controls Left / Data Right)
        - ✅ Consolidated inline controls for cleaner UI
        - ✅ Live 5-minute sparkline chart for dose rate history
- [x] **Advanced/Simple Mode Toggle**:
    - ✅ **Simple Mode** (default): Optimized thresholds (40% isotope, 30% chain) with hobby-focused library (uranium glass, mantles, radium watches, etc.)
    - ✅ **Advanced Mode**: User-adjustable confidence thresholds, energy tolerance settings, and expanded isotope library including:
        - ✅ Additional fission products (Ru-103, Zr-95, Ce-144, Mo-99, etc.)
        - ✅ Activation products (Sc-46, Cr-51, Ag-110m, Sb-124, etc.)
        - ✅ Rare earth isotopes (Eu-152/154/155, Gd-153, Tb-160, etc.)
        - ✅ Extended medical isotopes (Ga-67, In-111, Sm-153, Lu-177, etc.)
        - ✅ Nuclear reactor/waste products
        - ✅ Transuranics (Pu-238/239/240, Np-237, Am-243, Cm-244)
    - ✅ Settings panel (⚙️) for threshold customization (isotope min confidence, chain min confidence, peak matching tolerance)
    - ✅ localStorage persistence across sessions
- [x] **Decay Chain Detection**:
    - ✅ Identify typical radioactive decay chains in detected spectra
    - ✅ When daughter products are detected, suggest likely parent isotopes
    - ✅ U-238 chain (Pa-234m, Th-234, Ra-226, Pb-214, Bi-214, etc.)
    - ✅ U-235 chain (Actinium series with abundance weighting)
    - ✅ Th-232 chain (Tl-208, Ac-228, Pb-212, etc.)
    - ✅ Visual display of detected chain members with confidence levels
    - ✅ Authoritative source links (NNDC, IAEA, LBNL, USGS, NRC)
    - ✅ **Graphical flow diagrams** with color-coded detection status
- [x] **Natural Abundance Weighting**:
    - ✅ Research-based isotopic abundance from LBNL/NRC
    - ✅ U-238 (99.3%) correctly ranks above U-235 (0.72%) in natural samples
    - ✅ Intermediate filtering layer between detection and thresholding
- [x] **Stability Fixes**:
    - ✅ Fix persistent serial disconnection issues (killed zombie processes, simplified serial loop).
    - ✅ Fixed real-time acquisition timer overshoot (300/300 exact)
    - ✅ Fixed PDF export Content-Disposition header for proper downloads
    - ✅ **Auto-Reconnect**: Automatically recovers WebSocket connection causing dose rate display to resume after network/server interruption.
    - ✅ **Visibility Optimization**: Pauses chart rendering when tab is hidden to reduce CPU usage.
    - ✅ **Unload Safeguards**: Prompts user before closing tab if recording is in progress.
    - ✅ **Memory Protection**: Caps comparison mode to 8 spectra to prevent browser crashes.
    - ⚠️ **COUNT TIME (Partial)**: Fixed metadata display formatting (`replaceAll()` for proper key formatting) - **Still needs**: Backend must capture/store actual acquisition duration
- [x] **Deployment Improvements**:
    - ✅ Remove virtual environment requirement
    - ✅ Create simplified one-click launch process
    - ✅ Support running without AlphaHound device connected
    - ✅ **LAN Access**: Configured server for network access (host="0.0.0.0", port 3200)
- [x] **Refactor threshold filtering to application layer**:
    - ✅ Moved confidence threshold filtering from `isotope_database.py` to `main.py`
    - ✅ `identify_isotopes()` and `identify_decay_chains()` return ALL matches
    - ✅ Application layer applies filtering based on Simple/Advanced mode
    - ✅ Runtime threshold adjustment without modifying core detection logic
- [x] **ML Integration (PyRIID)**:
    - ✅ PyRIID 2.2.0 integration with MLPClassifier
    - ✅ Training on 90+ isotopes from IAEA/NNDC authoritative database
    - ✅ Multi-isotope mixture support (7 realistic sources):
        - ✅ UraniumGlass, ThoriumMantle, MedicalWaste, IndustrialGauge, CalibrationSource, NaturalBackground
    - ✅ `/analyze/ml-identify` API endpoint
    - ✅ Frontend "AI Identify" button with loading states
    - ✅ ~2168 training samples (1782 single + 386 mixtures) with abundance weighting
    - ✅ **AlphaHound Detector Tuning**: Energy-dependent FWHM (10% at 662 keV) matching CsI(Tl) resolution
    - ✅ **IAEA Intensity Data**: 49 isotopes with 2,499 gamma lines from IAEA LiveChart API
    - ✅ **Intensity-Weighted Training**: Synthetic peaks scaled by IAEA gamma intensities
    - ✅ **Comprehensive Documentation**: See [PYRIID_GUIDE.md](PYRIID_GUIDE.md) and [PYRIID_ENHANCEMENT_PLAN.md](PYRIID_ENHANCEMENT_PLAN.md)
    - ⚠️ **Note**: ML marked as WIP - Peak Matching is currently more accurate for uranium detection
- [x] **Peak Detection Enhancement**:
    - ✅ Fixed overly strict threshold (was 5% of max, now max(5, 0.3% of max))
    - ✅ Now detects 20+ peaks (was only 3)
    - ✅ Pb-214, Bi-214, Th-234 now visible in UI
- [x] **U-235/U-238 Prioritization**:
    - ✅ U-238 now ranks #2 at 100% confidence
    - ✅ U-235 suppressed to #26 at 0.1% when U-238 chain detected
    - ✅ Abundance weighting in `isotope_database.py`
- [x] **Auto-Save CSV on Acquisition**:
    - ✅ Automatically saves spectrum to CSV upon acquisition completion
   - ✅ Saves to `data/acquisitions/` directory
    - ✅ Filename format: `spectrum_YYYY-MM-DD_HH-MM-SS.csv`
    - ✅ Toast notification shows saved filename

## Future Enhancements

### Bugs\n- [x] ✅ **Missing Advanced Controls**: Settings modal now has working Simple/Advanced toggle, slider handlers, Apply/Reset buttons

### High Priority
- [x] ✅ **Energy Calibration Verified**:
    - ✅ **Device sends 1024 channels @ ~7.39 keV/channel** (15-7572 keV range)
    - ✅ **Tested with 6-hour uranium glass spectrum** (190,623 counts)
    - ✅ **Device calibration is CORRECT** - accurately identifies U-238, Th-234 without false U-235 detection
    - ✅ **3 keV/channel assumption was WRONG** - would cause false U-235 identification (75% confidence)
    - ✅ **No changes needed** - keep existing device calibration as-is
- [x] ✅ **Application Rebranding (SpecTrek → RadTrace)**:
    - [x] ✅ Bulk find/replace "SpecTrek" with "RadTrace" across all files
    - [x] ✅ Find and replace remaining emoji in UI with CSS/SVG
    - [x] ✅ Update README.md with new name
    - [x] ✅ Update page title and meta tags
- [ ] **Premium Branding Assets**:
    - [ ] Create and integrate transparent PNG logo to replace rocket.svg
    - [ ] Create and integrate transparent PNG favicon
    - [ ] Create and integrate transparent PNG upload icon
    - [ ] Create and integrate transparent PNG banner
- [x] ✅ **COUNT TIME Fix (Complete)**:
    - [x] Backend: Capture actual acquisition duration from frontend
    - [x] Backend: Pass duration to `count_time_minutes` in metadata
    - [x] ✅ Frontend: Display formatting fixed (`replaceAll()`)
- [x] ✅ **Mobile/Responsive UI**:
    - [x] ✅ Rework layout for phone screen widths (responsive breakpoints)
    - [x] ✅ Collapsible panels for small screens
    - [x] ✅ Touch-optimized controls for device acquisition
    - [x] ✅ Simplified navigation for mobile browsers
- [x] ✅ **Premium Icon System v2**:
    - [x] ✅ Professional SVG icons already implemented
- [x] ✅ **Blue/Purple Sci-Fi Theme**:
    - [x] ✅ Design and implement additional theme option
    - [x] ✅ Futuristic color palette with blue/purple gradients
    - [x] ✅ Glowing effects and tech-inspired UI elements
    - [x] ✅ Update theme selector to include new option
- [x] ✅ **Cyberpunk 2077 Theme**:
    - [x] ✅ Neon yellow/cyan color palette with dark backgrounds
    - [x] ✅ Glitch effects and holographic UI elements
    - [x] ✅ Pink/magenta accent colors
    - [x] ✅ Retro-futuristic typography and styling
- [x] ✅ **Theme-Aware Toast Notifications**:
    - [x] ✅ Update toast colors to match current theme (Dark/Light/Nuclear/Toxic/Sci-Fi/Cyberpunk)
    - [x] ✅ Add theme-specific styling for success/warning/info toasts
    - [x] ✅ Ensure proper contrast in all theme modes

### ML & Analysis
- [x] **ML Improvements**:
    - [x] Confidence thresholding (5%+ minimum to display)
    - [x] Hybrid filtering (suppress ML conflicts with Peak Matching HIGH confidence)
    - [x] Quality badges (good/moderate/low_confidence/no_match)
    - [ ] Collect real detector data for ML fine-tuning
    - [ ] Update synthetic demo files to use realistic Poisson noise
    - [ ] Train on weak source scenarios (low count rates)
    - [ ] Add background-dominated mixture training

### Features
- [x] **Custom Isotope Definitions**:
    - [x] Allow users to add custom isotopes to the database via UI
    - [x] Import/export custom isotope libraries (bulk JSON)
- [x] **Energy Calibration UI**:
    - ✅ Interactive peak marking for calibration
    - ✅ Linear calibration (Slope/Intercept)
- [x] **Background Subtraction**:
    - ✅ Load background spectrum and subtract from samples
    - ✅ Real-time net counts display
- [x] **UI Icon Polish**:
    - ✅ Replace all emoji icons with professional SVG/PNG assets
    - ✅ Icons needed: 📜 History, ⚙️ Settings, 🌓 Theme, 🔌 Device, 🔄 Refresh, ▶️ Play, ⏹️ Stop, 📂 Upload, 📄 PDF, 📊 Compare, 🔬 Analysis, 🚀 Rocket, 📥 Import, 📤 Export
    - ✅ Add favicon to browser tab
    - ✅ Consistent icon styling across all buttons
    - ✅ Custom Isotopes modal: SVG icons for Import/Export
- [x] **ROI Analysis (Advanced Mode)**:
    - ✅ ROI Analysis with activity calculation (Bq/μCi)
    - ✅ Uranium enrichment ratio analysis (Natural/Depleted/Enriched)
    - ✅ **Source Identification** (NEW):
      - ✅ Auto-detect common sources (Uranium Glass, Thoriated Lenses, Radium Dials)
      - ✅ User-driven assumption handling ("Source Type" dropdown)
      - ✅ Systematic validation of detected isotopes against source profile
    - ✅ **Ra-226 Interference Handling**:
      - ✅ Explicit warnings for overlapping 186 keV peaks (U-235 vs Ra-226)
      - ✅ Context-aware "Indeterminate" classification when appropriate
    - [x] Isotope ROI database with NNDC/IAEA branching ratios
    

## Technical Debt
- [x] **Code Quality**:
    - [x] Add JSDoc comments for main.js and api.js functions
    - [x] Refactor `main.js` to use ES6 modules
    - [ ] Add unit tests for frontend JavaScript modules
    - [ ] Add unit tests for backend API endpoints
    - [ ] Implement TypeScript for type safety
- [x] **Input Validation**:
    - [x] Add Pydantic Field validators with type hints
    - [x] Add file size and extension validation
    - [x] Add port sanitization for device connection
    - [x] Add range checks for acquisition duration
- [ ] **Performance Optimization**:
    - [ ] Lazy load Chart.js and other heavy libraries
    - [ ] Implement WebWorkers for ML training
    - [ ] Optimize large spectrum rendering
    - [ ] Add service worker for offline capability
- [x] **Security**:
    - [x] Implement rate limiting for API endpoints (slowapi)
    - [ ] ~~Add CSRF protection~~ (Moved to Low Priority - not relevant for local app)
    - [ ] ~~Add authentication for LAN access~~ (Moved to Low Priority - optional)
- [x] ✅ Refactor `main.py` to move CSV handling logic into its own module `csv_parser.py` or similar.

- [x] **v2.0 Analysis Robustness (Completed)**:
    - ✅ **Robust Upload Support**: Implemented `UPLOAD_SETTINGS` (1% confidence, 30keV tolerance) for CSV/N42 uploads.
    - ✅ **Dual-Mode Engine**: Live Acquisition uses Strict settings (30%) to filter U-235; Uploads use Robust settings.
    - ✅ **UI Fixes**: Resolved metadata text overlap with CSS `word-break`.
    - ✅ **Verified**: Confirmed correct filtering of U-235 (7% weighted) vs U-238 (53% weighted) in live data.

## Low Priority / Future

- [ ] **Radiacode Device Integration** (10-15 hours):
    - [ ] Add `radiacode` Python library dependency
    - [ ] Create `radiacode_driver.py` with USB/Bluetooth support
    - [ ] Add Radiacode 103/103G/110 to detector efficiency database
    - [ ] Create `/radiacode/*` API endpoints (connect, dose, spectrum)
    - [ ] Add device selector UI (AlphaHound vs Radiacode)
    - [ ] Tune ML for Radiacode FWHM profiles (7.4%-8.4%)
    - **Reference**: See [RADIACODE_INTEGRATION_PLAN.md](RADIACODE_INTEGRATION_PLAN.md)

- [x] ✅ **N42 File Format Support (Complete)**:
    - [x] ✅ Research N42 (ANSI N42.42) file format specification
    - [x] ✅ Document N42 XML schema and required elements
    - [x] ✅ Implement N42 exporter for acquired spectra (`backend/n42_exporter.py`)
    - [x] ✅ Add N42 export button to UI with theme-aware styling
    - [x] ✅ Enhanced N42 parser with multi-namespace and graceful fallbacks
    - [x] ✅ Extract instrument info (SOURCE shows "RadView Detection AlphaHound")
    - [x] ✅ ISO 8601 duration parsing for LiveTime/RealTime
    - [x] ✅ Standards-compliant output verified against N42.42-2006 schema

- [x] **Tuning & Calibration (Dec 2025)**:
    - ✅ **Intensity-Weighted Scoring**: Solved misidentification of Thorium (Pb-212) as Uranium (Pb-214) by penalizing missing diagnostic peaks.
    - ✅ **Strict Chain Triggers**: Enforced >40% confidence threshold for flagging Uranium/Thorium chains.
    - ✅ **Calibration Correction**: Validated that 3.0 keV/channel provides correct peak alignment (overriding device's 7.4 default).
    - ✅ **Configuration Update**: Updated `ml_analysis.py` and `device.py` to enforce 3.0 keV scaling.
    - ✅ **Bug Fixes**: Resolved "Spread Syntax" chart crash and Auto-BG floating peak artifacts.

- [x] **Advanced Spectrum Analysis (PyGammaSpec/GammaSpy)**:
    - [x] **Detector Health**: Implement FWHM% and Energy Resolution calculation for every peak (from PyGammaSpec).
    - [x] **Robust Single-Fit**: Port `curve_fit` logic for simultaneous specialized Baseline + Gaussian fit (from PyGammaSpec).
    - [x] **Composite Fitting**: Create `FitModel` class for Multi-Peak/Multiplet analysis (from GammaSpy).
    - [x] **Uncertainty Engine**: Implement rigorous Jacobian-based error propagation for Bq activity (from GammaSpy).

## Next Steps
- [x] **Universal Spectrum Support**:
    - ✅ Integrated `SandiaSpecUtils` for 100+ file formats (.spc, .pcf, .dat, etc.)
- [x] **Activity & Dose Calculator**:
    - ✅ Implemented Bq/μCi conversion (backend + frontend display fixed)
    - ✅ Added Gamma Dose Rate estimation in μSv/h
    - ✅ Fixed Ra-226 interference with "Forced Subtraction" for Uranium Glass
- [x] **Decay Prediction Engine**:
    - ✅ Hybrid backend: `curie` authoritative data + Custom Bateman Solver fallback
    - ✅ Interactive UI: Log-scale Chart.js visualization of daughter buildup
    - ✅ Smart Workflow: Auto-populates activity from ROI analysis results
- [x] **ROI Analysis Tuning**: 
    - ✅ Fixed activity unit conversion (1000x error)
    - ✅ Refined thresholds and subtraction logic

## Next Steps
- [x] **Replace New Emoji Icons with SVG**: ✅ Device control buttons replaced with inline SVGs
- [ ] **RadView Clarification**: Get response on 7.4 keV vs 3.0 keV discrepancy (see `radview_questions.md`)
- [ ] **Dead Time Logic**: Implement dead-time correction if device doesn't support it internally
- [ ] **Temperature Compensation**: ✅ Temperature now captured from spectrum metadata - consider using for gain stabilization
- [ ] **Validate Takumar Lens in Frontend**: Add "Takumar Lens (Th+U)" to ROI Source Type dropdown - backend signature exists but not in frontend

## Advanced Mode Feature Gating
- [ ] **Three-Tier Mode System**:
  - **Simple Mode**: Basic spectrum display, auto-identification, peaks/isotopes only
  - **Advanced Mode**: ROI analysis, decay chain prediction, background subtraction, calibration
  - **Expert Mode**: Multiplet deconvolution, Voigt fitting, auto ROI, basin hopping, line search APIs
- [ ] **Systematically identify features per mode**:
  - Simple: Spectrum chart, peak list, isotope ID, confidence scores
  - Advanced: + ROI panel, decay prediction, background subtraction, calibration, custom isotopes
  - Expert: + Multiplet, Voigt fits, auto-ROI, gamma/X-ray line search, decay chain spectrum
- [ ] **UI Toggle**: Add mode selector to settings (dropdown or tabs)
- [ ] **Reduce clutter**: Progressively reveal panels based on mode

