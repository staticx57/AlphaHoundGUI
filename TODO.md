# TODO

## Open Tasks

### High Priority
- [ ] **Premium Branding Assets** *(Deferred - waiting for transparency support)*:
    - [ ] Create and integrate transparent PNG logo to replace rocket.svg
    - [ ] Create and integrate transparent PNG favicon
    - [ ] Create and integrate transparent PNG upload icon
    - [ ] Create and integrate transparent PNG banner

### ML & Analysis
- [ ] Collect real detector data for ML fine-tuning
- [ ] Update synthetic demo files to use realistic Poisson noise
- [ ] Train on weak source scenarios (low count rates)
- [ ] Add background-dominated mixture training

### Technical Debt
- [ ] Add unit tests for frontend JavaScript modules
- [ ] Add unit tests for backend API endpoints
- [ ] Implement TypeScript for type safety

### Performance Optimization
- [ ] Lazy load Chart.js and other heavy libraries
- [ ] Implement WebWorkers for ML training
- [ ] Optimize large spectrum rendering
- [ ] Add service worker for offline capability

### Device & Calibration
- [ ] **RadView Clarification**: Get response on 7.4 keV vs 3.0 keV discrepancy (see `radview_questions.md`)
- [ ] **Dead Time Logic**: Implement dead-time correction if device doesn't support it internally
- [ ] **Temperature Compensation**: Temperature captured - consider using for gain stabilization

### ROI Enhancements ✅
- [x] **Auto-populate ROI acquisition time**: Pulls from N42/CSV metadata (live_time/real_time/acquisition_time)
- [x] **Change ROI time unit to minutes**: Accepts fractional minutes (e.g., 1.5) for consistency with acquisition UI

### Source-Specific Analysis Enhancements

#### Thoriated Lens (Th-232)
- [ ] ThO₂ mass estimation from Th-234 activity
- [ ] Secular equilibrium check (Pb-212/Th-234 ratio)
- [ ] Add Pb-212 (239 keV), Tl-208 (583 keV) to isotope database

#### Smoke Detector (Am-241)
- [ ] Compare to standard detector activity (~37 kBq)
- [ ] Age estimation from Pu-241 ingrowth

#### Radium Dial (Ra-226)
- [ ] Dose rate estimation (μSv/hr at contact and distance)
- [ ] Radium mass estimation from Bi-214 activity
- [ ] Age verification via Pb-210 equilibrium

#### Cesium-137
- [ ] Decay-corrected activity estimation
- [ ] Half-life remaining display

#### Potassium-40 (Natural Background)
- [ ] Potassium mass estimation from K-40 activity
- [ ] Compare to human body K-40 content (~4,400 Bq)

#### Cobalt-60
- [ ] Age/decay estimation (5.27 yr half-life)
- [ ] Original source strength calculation

#### Universal
- [ ] Dose rate estimation for all source types

### New Source Types ✅ (2025-12-17)
- [x] **Uranium Ore** - Full U-238 chain + U-235 detection
- [x] **Cesium-137 Source** - 662 keV calibration source
- [x] **Cobalt-60 Source** - 1173/1332 keV dual peaks
- [x] **Synthetic Test Spectra** - 6 N42 files in `backend/data/test_spectra/`

### Low Priority / Future
- [ ] **Radiacode Device Integration** (10-15 hours) - See [RADIACODE_INTEGRATION_PLAN.md](RADIACODE_INTEGRATION_PLAN.md)

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
