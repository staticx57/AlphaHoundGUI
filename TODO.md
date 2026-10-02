# TODO

## Open Tasks

### High Priority
- [ ] **Premium Branding Assets** *(Deferred - waiting for transparency support)*:
    - [ ] Create and integrate transparent PNG logo to replace rocket.svg
    - [ ] Create and integrate transparent PNG favicon
    - [ ] Create and integrate transparent PNG upload icon
    - [ ] Create and integrate transparent PNG banner
- [x] **Replace Remaining Emoji with SVG Icons**: ✅ Replaced ~40 emoji instances with SVG icons across index.html, main.js, ui.js, calibration.js, isotopes_ui.js, n42_editor.js (2026-01-01)
- [x] **Isotope Peak Visualization**: ✅ Implemented via `addIsotopeHighlight()` in `charts.js` - draws vertical reference lines on chart when isotope clicked.
- [x] **Chart Autoscale & Label Stacking**: ✅ Fixed autoscale toggle between peak-focused view and full spectrum, fixed overlapping annotation labels with vertical stacking (2025-12-22)
- [x] **Documentation Overhaul**: ✅ Major README update with Radiacode, XRF, SNIP, spectrum algebra, server-managed acquisitions (2025-12-22)

### Session handoff (2026-10-02, live RC-110 testing on Windows, branch fix/duplicate-route-registrations)
Last push: `3a8aa0d`. **Uncommitted** (all tests pass: 159 backend, 23 UI smoke, 34/34 theme sweep after the info-icon colour fix):
- Time fields: Acquisition/Live/Real/count_time were one wall-clock number copied 4x. UI now shows one "Acquisition Time" card (or separate Live/Real cards when they differ) with an ⓘ tooltip; acquisitions add `device_duration_s` (instrument-reported, Radiacode) and `time_notes`.
- Radiacode UI state: after Disconnect the Connect button still read "Connected"; a connection lost server-side (restart, BLE drop) was never noticed. Now `showRadiacodeDisconnectedUI()` resets both; 3 consecutive 400 "not connected" dose polls trigger it. Covered by ui_smoke section G.
- Untracked user data (not committed): `backend/data/acquisitions/spectrum_2026-10-02_{09-53-28,11-12-13,11-20-16}.n42` (RC-110 + Takumar lens; 09-53-28 carries the old wrong AlphaHound label).
Open items:
- [ ] (Total dose is now also shown next to the live dose rate: `rc-dose-total`.) Verify RC-110 end to end after a fresh connect: Dose row shows "(session)" total; compare with the device screen (device DS_uR register and RareData are not served by firmware 4.14 over BLE: see `/radiacode/diagnostics/dose-sources`).
- [x] Restore Radiacode UI state on page refresh while the server is still connected (`checkRadiacodeStatus`, ui_smoke section H).
- [x] Device alarm events: driver logs `Event` records; `GET /radiacode/events?since_id=` and `/radiacode/alarm-limits`; UI toasts new alarms. Verified on the RC-110 (2026-10-02): alarms are edge-triggered (fire when the dose rate crosses a limit, so a source already above the limit at connect gives none); pulling the lens away and back toasts each time. Alarm limits are API-only (no UI yet).
- [x] PyRIID / AI Identify: PyRIID dropped (pins numpy 1.26 / scipy 1.13 / TF 2.16, and was only an MLP wrapper here). `ml_analysis.py` now uses a scikit-learn MLP on a new physics-based synthesiser, resampling spectra onto the model grid with the device calibration. Real-spectra scorecard: `python backend/tests/ml_benchmark.py` (8/9 consistent; known miss: the weak community uranium-glaze CSV reads Tl-201 at <20%). Classes are named for what the spectrum shows (`Th-232 series`, `U-238 series`, `Ra-226 series`, `Cs-137 + Co-60`, ...), not for objects: a gamma spectrum cannot tell a thoriated lens from a mantle; use source-type analysis for that. Real-data augmentation is opt-in (`ML_USE_REAL_DATA=1`). Old PyRIID module and guides removed/archived.
- [ ] Tooling notes: servers are restarted with `powershell -File $TEMP/restart.ps1`-style (kill port 3200, start `python main.py` in backend); a restart drops the Radiacode BLE link. Browser tests: `python backend/tests/ui_smoke.py`, `ui_theme_sweep.py` (set PYTHONIOENCODING=utf-8 on Windows); real-spectrum benchmark: `python backend/tests/real_benchmark.py`.
### Pending Manual Verification (needs local browser / Radiacode hardware)
> Verified in headless Chrome with a mocked device (`python backend/tests/ui_smoke.py`, 15 checks): page load without JS errors, Radiacode tab layout/IDs, View Configuration + accumulated-dose elements present, AlphaHound dose readout + safety alert, connection-restore enabling controls, background load flow. Still needs real hardware / eyes: live Radiacode values, PDF download, exports, other themes and mobile widths, real-CSV peak comparison.

- [ ] Radiacode tab renders with no layout regressions after removing the hidden duplicate `radiacode-quick-panel` (and its duplicate IDs) from `index.html`
- [ ] After connecting a Radiacode, Dose / SN / FW rows in Device Settings populate on first poll (~2s) instead of ~20s
- [ ] Accumulated dose row shows `accumulated_dose_uSv` from `/radiacode/info/extended` and formats μSv/mSv correctly
- [ ] "View Configuration" button appears in Device Settings (Radiacode only) and shows the configuration
- [ ] Browser console shows no new errors; Reset/Clear/Disconnect buttons still work
- [ ] Upload a real CSV spectrum and confirm peaks/isotopes look the same as before (parser-level detection removed; only automated tests ran, on tiny synthetic CSVs)
- [ ] `POST /upload` with a malformed CSV now returns 400 (was 500); confirm the UI shows a sensible error toast
- [ ] Full UI/UX visual sweep across themes and mobile widths (needs a real browser)
- [ ] Run a long upload/analysis while the live dose sparkline is running; confirm the sparkline no longer stalls (analysis and Radiacode routes now run in the threadpool)
- [ ] Confirm the UI still works with CORS off (same-origin, incl. from another LAN device); set `ALPHAHOUND_CORS_ORIGINS` if a separate frontend is used
- [ ] Refresh the page while an AlphaHound is connected; device should stay connected (10s WebSocket reconnect grace)
- [ ] ROI results show "activity ± uncertainty Bq" (new `activity_uncertainty_bq`, 1σ counting uncertainty; `main.js` ~line 1941) and render correctly when the field is absent
- [ ] PDF export button downloads a working report (`/export/pdf` was broken: missing import; also forced matplotlib to headless `Agg`)
- [ ] Dose-rate calculator in the UI still works (`/analyze/dose-rate` now enforces the validated request model: activity ≥ 0, distance 0.01–1000 m)
- [ ] Exports (N42/CSV/checkpoint) and N42 metadata editor still work after moving to `routers/export.py`
- [ ] Server console output looks sane after switching ~180 `print` calls to `logging` (set `ALPHAHOUND_LOG_LEVEL=DEBUG` for more); live-device log lines (Radiacode/AlphaHound) appear at the right levels
- [ ] With a real AlphaHound: `POST /device/spectrum` acquire works (was an UnboundLocalError; verified only with a mocked device)
- [ ] AlphaHound live dose: readout updates, sparkline moves, and the >2000 µRem/hr safety alert appears (`ui.js` was writing to nonexistent `dose-display`, so the WebSocket callback threw on every message; now points at `rc-dose-display`)
- [ ] Background subtraction: Load Background File / Use Current as BG shows the "● ACTIVE" badge and the Clear BG button, and refreshes the chart (previously threw on missing `bg-active-indicator`)
- [ ] Nothing depended on the deleted `js/main_restored_temp.js` (was unreferenced; recoverable from git history)

### ML & Analysis
- [ ] Collect real detector data for ML fine-tuning
- [ ] Update synthetic demo files to use realistic Poisson noise
- [ ] Train on weak source scenarios (low count rates)
- [ ] Add background-dominated mixture training

### Technical Debt
- [x] Light theme XRF section contrast fixed (CSS vars `--xrf-text/--xrf-accent`; confidence badge now follows theme switches)
- [x] Isotope confidence bars and decay-chain cards now follow theme switches (`getThemeColors()` returns CSS var references; covered by `ui_smoke.py` section E). Note: only valid for CSS contexts, not canvas/Chart.js
- [ ] Sweep (`backend/tests/ui_theme_sweep.py`) checks only overflow/contrast/JS errors on 17 themes × 2 viewports; extend to the Radiacode tab, modals and the 35 proposed themes
- [x] Uncalibrated spectra (e.g. community `Data,Energy` CSVs whose Energy column is just 0,1,2…) no longer get isotope/chain matching on channel numbers; peaks are kept, a `warnings` entry is returned and shown as a toast (`analysis_utils.py`; tests in `test_api_endpoints.py`, `ui_smoke.py` section F)
- [x] **Series discrimination fixed with a full-spectrum template fit** (`backend/source_templates.py`, wired into `analysis_utils.analyze_spectrum_peaks`): NNLS fit of radium-series / fresh-uranium / thorium-series / K-40 / Cs-137 / Co-60 templates using per-detector resolution and efficiency on the spectrum's real (nonlinear) axis, with bounded gain/offset/resolution search and smooth continuum terms. It now decides which U-238/Th-232 chains are reported, confirms single sources, and demotes isotopes whose peaks other sources already explain. Real-data benchmark (`backend/tests/real_benchmark.py`, `test_real_benchmark.py`): 15/24 → 35/35 checks on 11 labelled real spectra (RadiaCode-103 ×4 vendored under MIT, AlphaHound ×5, RadiaCode-110 ×2 local-only). Thresholds (z ≥ 10, fraction ≥ 0.07) were set from these same 11 spectra: true series ≥ z 12.5 / f 0.09, wrong series ≤ z 7.3 / f 0.05.
- [x] RadiaCode/BecqMoni XML (`<ResultDataFile>`) uploads now parse (`radiacode_xml_parser.py`; previously 400); CSVs with `# key,value` metadata lines now parse (previously 500)
- [x] Result `warnings` include an energy-calibration check when identified sources anchor the fit and it shifts lines by >2.5 % at 662 keV (RadiaCode test unit reads ~3 % low)
- [ ] Grow the labelled real benchmark (more AlphaHound captures with known sources, a RadiaCode Cs-137/K-40/Co-60, mixed sources, background-only) and re-check the fit thresholds; ask the RadiaCode-110 file author (HighWay777/RadiaCode-Spectrometer) about a licence so those can be committed
- [ ] Fit range starts at 120 keV: below it (X-rays, Am-241 59.5, Th-234 63/93) the isotope list still relies on line matching (e.g. U-234 credited from a 36 keV bump). Consider a low-energy model or explicit X-ray templates
- [ ] Remove the old 60 keV tolerance widening in `chain_detection_enhanced.match_peaks_to_chain` (it no longer decides reported chains, but its member lists are still displayed)
- [ ] Real CSVs that yield no peaks at all: `Orange Fiestaware Saucer`, `Orange Red Wing Chevron Salt Cellar`, `Uraninite Ore`, `…BCV U Glass Brick` (`Data,Energy`; counts plateau ~2200 across ~200–350 keV and the energy axis reaches ~14.6 MeV). Check whether these are a different detector/format or a parsing/peak-detection problem.
- [ ] Build a small labelled benchmark of real, calibrated spectra (known source → expected isotopes/chains, plus must-not-detect) before changing chain thresholds; get ground-truth calibration for the Takumar captures first
- [ ] Fix/validate `generate_test_spectra.py` so each synthetic file's intended peaks dominate; then add golden tests (expected isotopes, no spurious chains)
- [ ] Remove dead frontend code for elements that no longer exist (see `LEGACY_NULL_GUARDED` in `backend/tests/test_frontend_ids.py`: `*-top` controls, `btn-rc-*`, etc.), then empty that allowlist
- [ ] **ROI advanced peak fitting never runs**: `roi_analysis.py` (~line 119) does `from .fitting_engine import ...` (relative import fails outside a package) and references undefined `target_energy`; the surrounding `except` swallows it so ROI always falls back to simple counting. Fixing changes ROI results, so validate against reference spectra first.
- [ ] Replace remaining `print` calls in multi-line/other statements and the `[Tag]` message prefixes now duplicated by logger names
- [x] Split `routers/analysis.py` (1500+ lines) into `analysis.py`, `export.py`, `nuclear.py` (same 37 routes)
- [ ] Split `static/js/main.js` (3,100 lines) into feature modules *(needs browser to verify)*
- [ ] Add unit tests for frontend JavaScript modules
- [x] Add unit tests for backend API endpoints ✅ (`backend/tests/test_api_endpoints.py`; 59 tests pass)
- [ ] Implement TypeScript for type safety
- [x] **Centralize Peak Detection** ✅ (csv_parser.py no longer detects peaks/isotopes; all formats go through `analyze_spectrum_peaks()` in `analysis_utils.py`) — original note: Remove `detect_peaks()` calls from individual parsers (csv_parser.py, etc.) and have all peak detection happen in `_analyze_spectrum_peaks()` in `analysis.py`. This ensures consistent detection across all file formats (N42, CSV, CHN, SPE, SPC, PCF, etc.) and simplifies threshold tuning.

### Performance Optimization
- [x] Analysis + Radiacode routes moved off the event loop (sync handlers run in threadpool)
- [ ] Lazy load Chart.js and other heavy libraries *(Deferred: already loaded with `defer`; modules use the globals at init, so lazy loading needs a browser to verify)*
- [ ] Implement WebWorkers for ML training
- [ ] Optimize large spectrum rendering
- [ ] Add service worker for offline capability

### Device & Calibration
- [ ] **RadView Clarification**: Get response on 7.4 keV vs 3.0 keV discrepancy (see `radview_questions.md`)
- [ ] **Dead Time Logic**: Implement dead-time correction if device doesn't support it internally
- [ ] **Temperature Compensation**: Temperature captured - consider using for gain stabilization
- [ ] **CSV/XML Energy Interpolation**: Implement energy-per-channel interpolation for imported CSV and XML files lacking energy data (e.g., legacy formats with only channel numbers). Support presets for known detectors (Radiacode models, AlphaHound profiles), custom detector coefficients, or manual keV/channel entry.

### Radiacode Device Features (Available in radiacode library, not yet exposed)
- [ ] **Device Settings Panel**: Add UI for Radiacode device configuration:
    - [ ] `set_display_brightness(0-9)` - Display brightness control
    - [ ] `set_sound_on(bool)` - Enable/disable device sound alerts
    - [ ] `set_vibro_on(bool)` - Enable/disable device vibration
    - [ ] `set_display_off_time(seconds)` - Auto-shutdown duration
    - [ ] `set_language('en'/'ru')` - Device language setting
- [ ] **Accumulated Dose Display**: Show total accumulated dose from `data_buf()` RealTimeData
- [ ] **Device Info Display**: Show serial number and firmware version in connection panel
- [ ] **Configuration Readout**: Expose `configuration()` output for debugging/advanced users

### ROI Enhancements ✅
- [x] **Auto-populate ROI acquisition time**: Pulls from N42/CSV metadata (live_time/real_time/acquisition_time)
- [x] **Change ROI time unit to minutes**: Accepts fractional minutes (e.g., 1.5) for consistency with acquisition UI

### Source-Specific Analysis Enhancements ✅ (Implemented in `source_analysis.py`)

#### Thoriated Lens (Th-232)
- [x] ThO₂ mass estimation from Th-234 activity - `analyze_thoriated_lens()`
- [x] Secular equilibrium check (Pb-212/Th-234 ratio) - `chain_detection_enhanced.py`
- [x] Pb-212 (239 keV), Tl-208 (583 keV) in isotope database - `isotope_database.py`

#### Smoke Detector (Am-241)
- [x] Compare to standard detector activity (~37 kBq) - `analyze_smoke_detector()`
- [ ] Age estimation from Pu-241 ingrowth *(Deferred - requires long-term tracking)*

#### Radium Dial (Ra-226)
- [x] Dose rate estimation (μSv/hr at contact and distance) - `activity_calculator.py`
- [x] Radium mass estimation from Bi-214 activity - `analyze_radium_dial()`
- [ ] Age verification via Pb-210 equilibrium *(Deferred - Pb-210 not easily detectable)*

#### Cesium-137
- [x] Decay-corrected activity estimation - `analyze_cesium137()`
- [x] Half-life remaining display - `analyze_cesium137()`

#### Potassium-40 (Natural Background)
- [x] Potassium mass estimation from K-40 activity - `analyze_potassium40()`
- [x] Compare to human body K-40 content (~4,400 Bq) - `HUMAN_BODY_K40` constant

#### Cobalt-60
- [x] Age/decay estimation (5.27 yr half-life) - `analyze_cobalt60()`
- [x] Original source strength calculation - `analyze_cobalt60()`

#### Universal
- [x] Dose rate estimation for all source types - `activity_calculator.py`

### New Source Types ✅ (2025-12-17)
- [x] **Uranium Ore** - Full U-238 chain + U-235 detection
- [x] **Cesium-137 Source** - 662 keV calibration source
- [x] **Cobalt-60 Source** - 1173/1332 keV dual peaks
- [x] **Synthetic Test Spectra** - 6 N42 files in `backend/data/test_spectra/`

### Low Priority / Future
- [x] **Radiacode Device Integration** ✅ Implemented in `radiacode_driver.py` + `routers/device_radiacode.py` - USB connection, spectrum, dose rate polling
- [x] **Radiacode Bluetooth on Windows**: ✅ Implemented using `bleak` library. Added BLE device scanning, device selection dropdown, and cross-platform BLE connectivity (Windows/macOS/Linux).
- [x] **Radiacode BLE Scan Fix (Windows)**: Fixed `pyserial`/`pywin32` COM STA conflict that silently broke BLE scan/connect on Windows (`allow_sta()` in `radiacode_bleak_transport.py`).

---

## Completed ✅

### Core Features
- [x] **Advanced Analysis**: Peak detection, isotope identification (100+ isotopes), decay chain detection, confidence scoring, graphical decay chain visualization
- [x] **Export Options**: JSON, CSV, PDF reports, N42 format
- [x] **UI Improvements**: Zoom/pan, themes (Light/Dark/Nuclear/Toxic/Sci-Fi/Cyberpunk), multi-file comparison, dual isotope detection panel, graphical confidence bars, professional SVG icons
- [x] **Data Management**: Upload history in localStorage
- [x] **AlphaHound Device Integration**: Serial communication, live dose rate, real-time spectrum acquisition, device control panel with sparkline chart
- [x] **Advanced/Simple Mode Toggle**: Three-tier system (Simple/Advanced/Expert) with threshold customization
- [x] **Decay Chain Detection**: U-238, U-235, Th-232 chains with graphical flow diagrams
- [x] **Natural Abundance Weighting**: U-238 correctly ranks above U-235 in natural samples

### Stability & Deployment
- [x] **Stability Fixes**: Serial disconnection fixes, acquisition timer, PDF headers, auto-reconnect, visibility optimization, unload safeguards, memory protection
- [x] **Deployment Improvements**: One-click launch, LAN access (0.0.0.0:3200), no device required
- [x] **Input Validation**: Pydantic validators, file validation, port sanitization
- [x] **Security**: Rate limiting with slowapi

### ML Integration
- [x] **PyRIID Integration**: MLPClassifier, 90+ isotopes, IAEA intensity data, 2168+ training samples
- [x] **Peak Detection Enhancement**: Improved threshold, 20+ peaks detected
- [x] **U-235/U-238 Prioritization**: Abundance weighting in isotope_database.py

### UI Features
- [x] **Custom Isotope Definitions**: Add via UI, import/export JSON
- [x] **Energy Calibration UI**: Interactive peak marking, linear calibration
- [x] **Background Subtraction**: Load/subtract background, SNIP auto-removal
- [x] **ROI Analysis**: Activity calculation (Bq/μCi), enrichment ratio, source identification, Ra-226 interference handling
- [x] **Theme-Aware Toast Notifications**: Match current theme colors
- [x] **Mobile/Responsive UI**: Responsive breakpoints, collapsible panels, touch-optimized controls

### Branding & Polish
- [x] **Application Rebranding**: SpecTrek → RadTrace
- [x] **Premium Icon System**: SVG icons replacing all emojis
- [x] **Blue/Purple Sci-Fi Theme**: Futuristic color palette, glowing effects
- [x] **Cyberpunk 2077 Theme**: Neon yellow/cyan, glitch effects

### Analysis & Calibration
- [x] **Energy Calibration Verified**: Device 7.39 keV/channel confirmed correct
- [x] **Tuning & Calibration**: Intensity-weighted scoring, strict chain triggers
- [x] **Advanced Spectrum Analysis**: FWHM%, Gaussian fitting, multiplet analysis, uncertainty engine
- [x] **v2.0 Analysis Robustness**: Dual-mode engine (Strict for live, Robust for uploads)

### Code Quality
- [x] **Test Infrastructure**: Fixed broken imports in `backend/tests/` enabling the suite of 20 unit tests to run and pass.
- [x] **Refactoring**: Application layer threshold filtering, CSV parser module, ES6 modules, JSDoc comments
- [x] **COUNT TIME Fix**: Backend capture + frontend display
- [x] **Auto-Save CSV**: Automatic saves to `data/acquisitions/`

### Advanced Mode Feature Gating (2025-12-16)
- [x] **Three-Tier Mode System**: Simple/Advanced/Expert in `main.js`
- [x] **UI Toggle**: Mode selector in Settings modal
- [x] **Wrapper IDs for BG/Calibration**: `calibration-section` and `background-section` IDs added

### Session 2025-12-16
- [x] **Takumar source_type passing**: Added field to `UraniumRatioRequest` model
- [x] **Auto-switch isotope for Takumar**: Frontend switches to Th-234 (93 keV)
- [x] **Sanity check for enrichment ratio**: Flag ratios >150% as mismatch
- [x] **Validate Takumar Lens in Frontend**: Added to ROI Source Type dropdown

### File Format Support
- [x] **N42 File Format**: Exporter, enhanced parser, ISO 8601 duration parsing
- [x] **Universal Spectrum Support**: SandiaSpecUtils for 100+ formats

### Activity & Decay
- [x] **Activity & Dose Calculator**: Bq/μCi conversion, γ dose rate (μSv/h)
- [x] **Decay Prediction Engine**: Curie + Bateman solver, interactive Chart.js visualization

### UI Themes (2026-01-04)
- [x] **Theme Color System Overhaul**: Charts and UI elements now fully theme-responsive
  - Added `hexToRgba()` helper for proper color conversion
  - Chart line, fill, and zoom scrubber update dynamically on theme switch
  - Fixed hardcoded cyan colors in charts.js
- [x] **Vintage Theme Color Overrides**: Added status/confidence colors to 5 themes:
  - Ludlum, Eberline, Fluke, Keithley, Tektronix
- [x] **35 New Theme Proposals**: Complete CSS in `complete_themes_css.md` (artifacts folder):
  - 8 Sci-Fi (Alien, Pip-Boy, Blade Runner, Tron, Matrix, LCARS, UNSC, Stranger Things)
  - 7 Test Equipment (Beckman, GenRad, Heathkit, Simpson, Lambda, Boonton, Wavetek)
  - 8 Computing (Apple II, C64, IBM 5150, Amiga, VT-100, BBC Micro, Atari ST, ZX Spectrum)
  - 6 Radiological (Canberra Packard, Bicron, TASC, Nuclear Data, Radiation Alert, Radon Scout)
  - 6 Vacuum Tube (Magic Eye, Dekatron, Numitron, VFD, Cold Cathode, Panaplex)
