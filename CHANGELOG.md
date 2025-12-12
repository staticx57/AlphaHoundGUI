# CHANGELOG

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
