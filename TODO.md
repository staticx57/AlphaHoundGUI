# TODO

## Completed ✅
- [x] **Advanced Analysis**:
    - ✅ Use `scipy.signal.find_peaks` for automatic peak detection and labeling.
    - ✅ Isotope identification database with 30+ isotopes
- [x] **Export Options**:
    - ✅ Allow exporting parsed data to JSON or CSV from the UI.
- [x] **UI Improvements**:
    - ✅ Add zoom/pan capabilities to the chart (using `chartjs-plugin-zoom`).
    - ✅ Light/Dark mode toggle with localStorage
    - ✅ Multi-file comparison (overlay multiple spectra)
- [x] **Data Management**:
    - ✅ Save upload history to local storage
- [x] **AlphaHound Device Integration**:
    - ✅ Serial communication with RadView Detection AlphaHound™
    - ✅ Live dose rate monitoring via WebSocket
    - ✅ Real-time spectrum acquisition (Live Building)
    - ✅ Non-blocking Sidebar UI for device control
    - ✅ Integrated device control panel

## Future Enhancements
- [ ] **Advanced/Simple Mode Toggle**:
    - **Simple Mode** (default): Current optimized thresholds (40% isotope, 30% chain) with hobby-focused library (uranium glass, lantern mantles, radium watches, etc.)
    - **Advanced Mode**: User-adjustable confidence thresholds, energy tolerance settings, and expanded isotope library including:
        - Additional fission products and activation products
        - Rare earth isotopes
        - Extended medical isotopes
        - Nuclear reactor/waste products
        - Custom isotope definitions
    - Settings panel for threshold customization (isotope min confidence, chain min confidence, peak matching tolerance)
- [ ] **Decay Chain Detection**:
    - Identify typical radioactive decay chains in detected spectra
    - When daughter products are detected, suggest likely parent isotopes
    - Example: Uranium glass (U-238 chain) → Pa-234m, Th-234, Ra-226, Pb-214, Bi-214
    - Help users understand the full decay series present in a sample
    - Visual display of detected chain members and missing expected peaks
- [ ] **Advanced ML Integration**:
    - Integrate `PyRIID` for machine-learning based isotope identification.
    - *Note: Requires Python < 3.11 (Incompatible with current 3.13 env)*
- [x] **Additional Export Options**:
    - ✅ Generate PDF reports of the spectrum.
- [x] **Stability Fixes**:
    - ✅ Fix persistent serial disconnection issues (killed zombie processes, simplified serial loop).
- [x] **Deployment Improvements**:
    - ✅ Remove virtual environment requirement
    - ✅ Create simplified one-click launch process
    - ✅ Support running without AlphaHound device connected

## Technical Debt
- [ ] **Refactor threshold filtering to application layer**:
    - Move confidence threshold filtering from `isotope_database.py` functions to `main.py` endpoint handlers
    - `identify_isotopes()` and `identify_decay_chains()` should return ALL matches
    - Application layer (`/upload`, `/device/spectrum` endpoints) applies filtering based on mode:
        - **Simple mode**: Default thresholds (40% isotope, 30% chain)
        - **Advanced mode**: User-configurable thresholds from settings
    - Benefits: Allows runtime threshold adjustment without modifying core detection logic
- [ ] Add unit tests for the frontend javascript.
- [x] ✅ Refactor `main.py` to move CSV handling logic into its own module `csv_parser.py` or similar.
