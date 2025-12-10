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
- [ ] **Advanced ML Integration**:
    - Integrate `PyRIID` for machine-learning based isotope identification.
    - *Note: Requires Python < 3.11 (Incompatible with current 3.13 env)*
- [x] **Additional Export Options**:
    - ✅ Generate PDF reports of the spectrum.
- [x] **Stability Fixes**:
    - ✅ Fix persistent serial disconnection issues (killed zombie processes, simplified serial loop).

## Technical Debt
- [ ] Add unit tests for the frontend javascript.
- [ ] Refactor `main.py` to move CSV handling logic into its own module `csv_parser.py` or similar.

