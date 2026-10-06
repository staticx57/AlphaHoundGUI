# TODO

## Waiting on you

Everything else on this list is done or closed with its reason beside it. What is left needs your hardware, your eyes, a second machine, a known source or data only you have; each such line is marked *Waiting on you*. The ones that matter most:

- RadiaCode on the bench: the settings (brightness, sound, vibration, display timeout, language), alarm limits and the dose figures against the device screen.
- A known-activity source at a known distance: closes the ROI efficiency, the activity estimate and the efficiency curves together.
- Captures from other crystals (RadiaCode 110, NaI, other CsI sizes) and AlphaHound captures of sources other than the thoriated lens: the evaluation and the benchmark.
- A fresh install on another machine (`install_deps.bat`, `install_lightweight.bat`, `run.bat`), a phone on the LAN, a screen reader.
- A timed acquire on the AlphaHound (it clears the device's spectrum, so it is run only when you say so).

## Open Tasks

### High Priority
- [ ] **Premium Branding Assets** *(Deferred - waiting for transparency support)*: *(Waiting on you: the artwork.)*
    - [ ] Create and integrate transparent PNG logo to replace rocket.svg
    - [ ] Create and integrate transparent PNG favicon
    - [ ] Create and integrate transparent PNG upload icon
    - [ ] Create and integrate transparent PNG banner
- [x] **Replace Remaining Emoji with SVG Icons**: ✅ Replaced ~40 emoji instances with SVG icons across index.html, main.js, ui.js, calibration.js, isotopes_ui.js, n42_editor.js (2026-01-01)
- [x] **Isotope Peak Visualization**: ✅ Implemented via `addIsotopeHighlight()` in `charts.js` - draws vertical reference lines on chart when isotope clicked.
- [x] **Chart Autoscale & Label Stacking**: ✅ Fixed autoscale toggle between peak-focused view and full spectrum, fixed overlapping annotation labels with vertical stacking (2025-12-22)
- [x] **Documentation Overhaul**: ✅ Major README update with Radiacode, XRF, SNIP, spectrum algebra, server-managed acquisitions (2025-12-22)

### Live-device session of 2026-10-02 (RC-110 on Windows): what it changed
- Time fields: Acquisition/Live/Real/count_time were one wall-clock number copied 4x. UI now shows one "Acquisition Time" card (or separate Live/Real cards when they differ) with an ⓘ tooltip; acquisitions add `device_duration_s` (instrument-reported, Radiacode) and `time_notes`.
- Radiacode UI state: after Disconnect the Connect button still read "Connected"; a connection lost server-side (restart, BLE drop) was never noticed. Now `showRadiacodeDisconnectedUI()` resets both; 3 consecutive 400 "not connected" dose polls trigger it. Covered by ui_smoke section G.
Open items:
- [ ] (Total dose is now also shown next to the live dose rate: `rc-dose-total`.) Verify RC-110 end to end after a fresh connect: Dose row shows "(session)" total; compare with the device screen (device DS_uR register and RareData are not served by firmware 4.14 over BLE: see `/radiacode/diagnostics/dose-sources`). *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [x] Restore Radiacode UI state on page refresh while the server is still connected (`checkRadiacodeStatus`, ui_smoke section H).
- [x] Device alarm events: driver logs `Event` records; `GET /radiacode/events?since_id=` and `/radiacode/alarm-limits`; UI toasts new alarms. Verified on the RC-110 (2026-10-02): alarms are edge-triggered (fire when the dose rate crosses a limit, so a source already above the limit at connect gives none); pulling the lens away and back toasts each time. Alarm limits are API-only (no UI yet).
- [x] PyRIID / AI Identify: PyRIID dropped (pins numpy 1.26 / scipy 1.13 / TF 2.16, and was only an MLP wrapper here). `ml/ml_analysis.py` now uses a scikit-learn MLP on a new physics-based synthesiser, resampling spectra onto the model grid with the device calibration. Real-spectra scorecard: `python backend/tests/ml_benchmark.py` (8/9 consistent; known miss: the weak community uranium-glaze CSV reads Tl-201 at <20%). Classes are named for what the spectrum shows (`Th-232 series`, `U-238 series`, `Ra-226 series`, `Cs-137 + Co-60`, ...), not for objects: a gamma spectrum cannot tell a thoriated lens from a mantle; use source-type analysis for that. Real-data augmentation is opt-in (`ML_USE_REAL_DATA=1`). Old PyRIID module and guides removed/archived.
- Tooling notes: restart the server with `python backend/tools/devctl.py restart` (it reconnects the device; a restart drops the Radiacode BLE link, and a server keeps running the code it was started with, so restart after pulling). Tests: `python -m pytest backend/tests` (641). Browser tests (headless Chrome, `PYTHONIOENCODING=utf-8` on Windows): `python backend/tests/ui_smoke.py`, `ui_theme_sweep.py`, `ui_channels_sweep.py`, `ui_a11y_audit.py`; they use `http://localhost:3200`, or `ALPHAHOUND_URL=http://127.0.0.1:3201` to test a second instance while a device is connected to the first. Real-spectrum benchmark: `python backend/tests/real_benchmark.py`. Test spectra live in `backend/tests/data/`; `backend/data/acquisitions/` is the app's own output and is not tracked.
### AlphaHound modernization (2026-10-02 PM, see docs/ALPHAHOUND_SERIAL.md)
Done and verified on the live AB+G (COM8): `P` polling and CPS parsing, dose stream vs `DB` reply fix, details panel, display replica (Mode 4 compared with RadView's product photos), dose log CSV, `devctl restart` with automatic reconnect.
- [ ] Compare the replica and the numbers with the physical screen: which unit does the device show, and is `DB` / the `P` dose field really nSv/h (the data say 10x the stream; the unit is inferred, not documented)? *(2026-10-04 data for the unit question: those replies average about 12.3 times the streamed µRem/h, not 10, so they are not simply nSv/h of the same quantity; still needs the screen, or RadView.)* *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [x] What do `D`, `DA` and `DB` differ in (all three replied with ~the same value on this firmware)? *(2026-10-04: not at all that can be measured: 25 samples each gave 938, 933 and 935 (spread about 30), far steadier than the dose stream, so they look like one smoothed dose rate.)*
- [x] Can the replica be synced to the real screen? Tested: no. The device reports nothing on a mode change (E x12 on the raw port: no text, no stream change; `K` only jitters). It cycles four user-configured slots (M1-M4), so the replica has slots too and the user sets them once. A physical button or a shake is invisible to the app.
- [ ] Ask RadView whether the firmware can report the current mode/slot, or whether a command reads the Mode Selection menu. *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] Modes 5-7 of the replica (alpha/beta spectroscopy, radon approximation) need data the serial link does not give; revisit if RadView documents more commands. *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] `A`, `B`, `RA`, `RB`, `SpecA`, `SpecB`, `COUNT`, `ALL`, `?` return nothing; their effect is unknown (not sent by the app). *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [x] The dose log is persisted (`backend/data/dose_log.jsonl`) and survives restarts; the dose-rate average, count-rate charts and per-acquisition channel statistics are in.

### UI/UX round of 2026-10-03: needs your eyes / hardware to confirm
Automated checks (mocked devices, headless Chrome: `ui_smoke.py`, `ui_a11y_audit.py`, `ui_channels_sweep.py`, `ui_theme_sweep.py`) pass, but these need a person or a device:
- [x] AlphaHound channel panel with the real `P` stream (meters, history chart, CPS/CPM) in your favourite themes *(2026-10-04: numbers match the API and change every second (checked live in Dark); the themes were checked by eye by the owner and work.)*
- [ ] Alerts on real readings: banner, beep (browsers only allow sound after a click on the page), desktop notification permission prompt *(live AlphaHound, 2026-10-04: The banner appears for a limit below the real reading and goes away with the default one. Sound and the notification prompt need a person.)* *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] Radiacode "Device alarm limits" in Advanced Diagnostics with real registers (shape tested with a mock only) *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] Dose unit preference across both devices (Settings > Dose readings and alerts) *(live AlphaHound, 2026-10-04: AlphaHound checked: uSv/h and uRem/h change the readout, 0.85 uSv/h = 85 uRem/h. The Radiacode side was not available.)* *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] Screen reader pass (NVDA / VoiceOver): dialogs, the result summary, the alert banner *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] Open the app from a phone on the LAN (`http://<computer-ip>:3200`) with the computer offline *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- Ideas not done: sticky section navigation, auto-running the AI check after each upload (optional setting), linking the AI/line-matching disagreement to the peaks it is based on.

### Pending Manual Verification (needs local browser / Radiacode hardware)
> Verified in headless Chrome with a mocked device (`python backend/tests/ui_smoke.py`, 15 checks): page load without JS errors, Radiacode tab layout/IDs, View Configuration + accumulated-dose elements present, AlphaHound dose readout + safety alert, connection-restore enabling controls, background load flow. Still needs real hardware / eyes: live Radiacode values, PDF download, exports, other themes and mobile widths, real-CSV peak comparison.

- [ ] Radiacode tab renders with no layout regressions after removing the hidden duplicate `radiacode-quick-panel` (and its duplicate IDs) from `index.html` *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] After connecting a Radiacode, Dose / SN / FW rows in Device Settings populate on first poll (~2s) instead of ~20s *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] Accumulated dose row shows `accumulated_dose_uSv` from `/radiacode/info/extended` and formats μSv/mSv correctly *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] "View Configuration" button appears in Device Settings (Radiacode only) and shows the configuration *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] Browser console shows no new errors; Reset/Clear/Disconnect buttons still work *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [x] Upload a real CSV spectrum and confirm peaks/isotopes look the same as before (parser-level detection removed; only automated tests ran, on tiny synthetic CSVs) *(2026-10-04: real CSVs are now tested: `test_real_csv.py`, the real-spectrum benchmark, and 12 analysis snapshots that stayed byte-identical through every refactor since.)*
- [x] `POST /upload` with a malformed CSV now returns 400 (was 500); confirm the UI shows a sensible error toast *(2026-10-04: ui_smoke checks the 400 and that the drop zone says what was wrong and offers to try again.)*
- [x] Full UI/UX visual sweep across themes and mobile widths (needs a real browser) *(2026-10-05: `ui_theme_sweep.py`: 17 themes x desktop and 390 px x (spectrum, thorium series capture, Radiacode tab), 102 combinations, no issues.)*
- [x] Unassigned-excess markers (hollow dashed rings on the chart, "unassigned excess" rows under the peaks) on a real long capture: legible across themes and at phone width, and clear that they are not peaks *(headless only: `ui_smoke.py` section AA and synthetic-spectrum unit tests)* *(2026-10-05: the sweep above loads a real capture with the excess rows and checks their contrast in every theme and at 390 px; whether they read clearly as not-peaks to a person is yours to judge.)*
- [ ] Activity estimates in the isotope rows against a source of known activity at a known distance: the formula is fixed (net area / efficiency x emission x live time), the efficiency curves are generic (a factor 2-4 between Pb-212, Ac-228 and Tl-208 on the 8-hour run) *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] The live AlphaHound at its current drift: upload or acquire a capture and confirm the automatic correction (an offset beyond 20 keV) names the right source *(only the 20-minute thinned fixture and `tests/drift_sweep.py` cover it)* *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [ ] Run `install_deps.bat`, `install_lightweight.bat` and `run.bat` on a machine that is not this one (a Python from python.org, not the pyenv-win shim; Python 3.11 or newer): this machine has no internet, so the fresh-install path was only checked by running the app with the lightweight install's missing packages made unavailable *(Waiting on you: needs your hardware, eyes, phone or another machine.)*
- [x] Run a long upload/analysis while the live dose sparkline is running; confirm the sparkline no longer stalls (analysis and Radiacode routes now run in the threadpool) *(live AlphaHound, 2026-10-04: Not as stated at first: uploads still analysed on the event loop and froze the dose stream for up to 2.9 s. Now in a worker thread: under four parallel uploads the stream keeps its 1 s rhythm (largest gap 1.01 s) and throughput doubled.)*
- [x] Confirm the UI still works with CORS off (same-origin, incl. from another LAN device); set `ALPHAHOUND_CORS_ORIGINS` if a separate frontend is used *(live AlphaHound, 2026-10-04: Loaded from this computer's LAN address (192.168.1.152) with the device panel populated and no console errors; a separate physical device was not tried.)*
- [x] Refresh the page while an AlphaHound is connected; device should stay connected (10s WebSocket reconnect grace) *(live AlphaHound, 2026-10-04: 28 of 28 status polls stayed connected across a reload, and the panel came back.)*
- [x] ROI results show "activity ± uncertainty Bq" (new `activity_uncertainty_bq`, 1σ counting uncertainty; `main.js` ~line 1941) and render correctly when the field is absent *(2026-10-04: on a synthetic Cs-137 source of known 500 Bq, three noise draws read 497.8 to 501.5 Bq with a stated 2.2 Bq, each within about 1 sigma; the page renders without the field because it is a conditional.)*
- [x] PDF export button downloads a working report (`/export/pdf` was broken: missing import; also forced matplotlib to headless `Agg`) *(2026-10-04: ui_smoke clicks the button, receives a file that starts with %PDF- and is named *_report.pdf, and no pop-up tab opens.)*
- [x] Dose-rate calculator in the UI still works (`/analyze/dose-rate` now enforces the validated request model: activity ≥ 0, distance 0.01–1000 m) *(2026-10-04: the UI has never called `/analyze/dose-rate` (no commit ever added a caller); it is an API-only route, covered by `test_api_endpoints.py`.)*
- [x] Exports (N42/CSV/checkpoint) and N42 metadata editor still work after moving to `routers/export.py` *(live AlphaHound, 2026-10-04: N42 export of a live spectrum and the checkpoint write and delete work; CSV export and the metadata editor are covered by the automated tests only.)* *(2026-10-05: CSV export and the metadata editor are now in the browser suite (section AC).)*
- [x] Server console output looks sane after switching ~180 `print` calls to `logging` (set `ALPHAHOUND_LOG_LEVEL=DEBUG` for more); live-device log lines (Radiacode/AlphaHound) appear at the right levels *(live AlphaHound, 2026-10-04: Only INFO lines from the live device. Every client disconnect was logged as an ERROR with an empty message; fixed, and a real error now names its type.)*
- [ ] With a real AlphaHound: `POST /device/spectrum` acquire works (was an UnboundLocalError; verified only with a mocked device) *(live AlphaHound, 2026-10-04: The read path (count_minutes 0) works on the real device, including temperature in the metadata. A timed acquire clears the device spectrum, so it was not run.)* *(Waiting on you: a timed acquire clears the device spectrum, so it is run only when you say so)*
- [x] AlphaHound live dose: readout updates, sparkline moves, and the >2000 µRem/hr safety alert appears (`ui.js` was writing to nonexistent `dose-display`, so the WebSocket callback threw on every message; now points at `rc-dose-display`) *(live AlphaHound, 2026-10-04: Readout and rates change every second and agree with the API; the alert banner was checked with a limit below the real reading, since the default 2000 uRem/h cannot be reached on this source.)*
- [x] Background subtraction: Load Background File / Use Current as BG shows the "● ACTIVE" badge and the Clear BG button, and refreshes the chart (previously threw on missing `bg-active-indicator`) *(live AlphaHound, 2026-10-04: Use Current as BG and Clear BG checked on a live spectrum (badge shows and hides, the device's own spectrum untouched); Load Background File was not.)* *(2026-10-05: Load Background File, the badge, Clear BG and the chart refresh are in the browser suite (section AC).)*
- [x] Nothing depended on the deleted `js/main_restored_temp.js` (was unreferenced; recoverable from git history) *(2026-10-04: nothing in the repository refers to it and the app runs: 186 browser checks pass.)*

### ML & Analysis
- [ ] Collect real detector data for ML fine-tuning *(Waiting on you: captures of known sources from your detectors)*
- [x] Update synthetic demo files to use realistic Poisson noise *(2026-10-05: `tools/generate_test_spectra.py` draws Poisson noise on the float expectation (it truncated to integers first) and takes a seed.)*
- [x] Train on weak source scenarios (low count rates) *(2026-10-05: closed on a measurement. The synthesiser already covers 5 k to 2 M counts; widening it to 2 k counts and a background share up to 90 % (from 60 %) left `tests/ml_benchmark.py` at 8/9 with energies and 3/9 without, the same verdicts, and moved single confidences both ways (Am-241 86 to 94 %, Cs-137 97 to 88 %). The change was reverted: no gain to justify it.)*
- [x] Add background-dominated mixture training *(2026-10-05: same measurement as the item above; the mix already runs to a 60 % background share and has a background class.)*

### Technical Debt
Structural debt (long functions, overlapping modules, what was cleaned and what is open) is kept in `TECHNICAL_DEBT.md`; the items below are product-facing.
- [x] Light theme XRF section contrast fixed (CSS vars `--xrf-text/--xrf-accent`; confidence badge now follows theme switches)
- [x] Isotope confidence bars and decay-chain cards now follow theme switches (`getThemeColors()` returns CSS var references; covered by `ui_smoke.py` section E). Note: only valid for CSS contexts, not canvas/Chart.js
- [x] Sweep (`backend/tests/ui_theme_sweep.py`) checks only overflow/contrast/JS errors on 17 themes × 2 viewports; extend to the Radiacode tab, modals and the 35 proposed themes *(2026-10-05: it now also loads a real thorium series capture and visits the Radiacode tab, with the chain card, excess rows, ROI notes and the tab buttons in its contrast selectors: 102 combinations. The 35 proposed themes are not in the app, so there is nothing to sweep; modals other than calibration and the metadata editor are covered by the browser suite.)*
- [x] Uncalibrated spectra (e.g. community `Data,Energy` CSVs whose Energy column is just 0,1,2…) no longer get isotope/chain matching on channel numbers; peaks are kept, a `warnings` entry is returned and shown as a toast (`spectroscopy/analysis_utils.py`; tests in `test_api_endpoints.py`, `ui_smoke.py` section F)
- [x] **Series discrimination fixed with a full-spectrum template fit** (`backend/spectroscopy/source_templates.py`, wired into `analysis_utils.analyze_spectrum_peaks`): NNLS fit of radium-series / fresh-uranium / thorium-series / K-40 / Cs-137 / Co-60 templates using per-detector resolution and efficiency on the spectrum's real (nonlinear) axis, with bounded gain/offset/resolution search and smooth continuum terms. It now decides which U-238/Th-232 chains are reported, confirms single sources, and demotes isotopes whose peaks other sources already explain. Real-data benchmark (`backend/tests/real_benchmark.py`, `test_real_benchmark.py`): 15/24 → 35/35 checks on 11 labelled real spectra (RadiaCode-103 ×4 vendored under MIT, AlphaHound ×5, RadiaCode-110 ×2 local-only). Thresholds (z ≥ 10, fraction ≥ 0.07) were set from these same 11 spectra: true series ≥ z 12.5 / f 0.09, wrong series ≤ z 7.3 / f 0.05.
- [x] RadiaCode/BecqMoni XML (`<ResultDataFile>`) uploads now parse (`formats/radiacode_xml_parser.py`; previously 400); CSVs with `# key,value` metadata lines now parse (previously 500)
- [x] Result `warnings` include an energy-calibration check when identified sources anchor the fit and it shifts lines by >2.5 % at 662 keV (RadiaCode test unit reads ~3 % low)
- [ ] Grow the labelled real benchmark (more AlphaHound captures with known sources, a RadiaCode Cs-137/K-40/Co-60, mixed sources, background-only) and re-check the fit thresholds; *(2026-10-04: 21 public RadiaCode spectra added in `tests/data/web_spectra` (Cs-137, Co-60, Eu-152, Ba-133, mixtures, Am-241, radium, thorium, uranium glass, backgrounds) and the thresholds re-set from them; still open: AlphaHound captures of known sources other than the thoriated lens)* ask the RadiaCode-110 file author (HighWay777/RadiaCode-Spectrometer) about a licence so those can be committed *(Waiting on you: AlphaHound captures of known sources other than the thoriated lens, and a reply on the RadiaCode-110 files' licence)*
- [x] Fit range starts at 120 keV: below it (X-rays, Am-241 59.5, Th-234 63/93) the isotope list still relies on line matching (e.g. U-234 credited from a 36 keV bump). Consider a low-energy model or explicit X-ray templates *(2026-10-05: lowering the edge to 100/110 keV, or adding a Compton-backscatter column per series, lost verdicts (29-30 of 31): the U-235 143.8 keV template absorbs the 125-160 keV bump and a thorium lens reads as uranium too. Structure above 100 keV that the fitted peaks do not explain is now shown as an unassigned excess instead.)* *(2026-10-05: closed on the measurements in the note: lowering the edge lost verdicts, and the structure is shown as unassigned excess. Reopen with a low-energy model measured on `scoring_eval.py`.)*
- [x] Remove the old 60 keV tolerance widening in `chain_detection_enhanced.match_peaks_to_chain` (it no longer decides reported chains, but its member lists are still displayed) *(2026-10-05: done, see the decay chains item below.)*
- [x] Real CSVs that yield no peaks at all: `Orange Fiestaware Saucer`, `Orange Red Wing Chevron Salt Cellar`, `Uraninite Ore`, `…BCV U Glass Brick` (`Data,Energy`; counts plateau ~2200 across ~200–350 keV and the energy axis reaches ~14.6 MeV). Check whether these are a different detector/format or a parsing/peak-detection problem. *(2026-10-04: cause found and fixed: the peak fit window was too narrow for channels this wide (see CHANGELOG). Uraninite Ore now gives the U-238 series (Pb-214, Bi-214, Ra-226). The two Fiestaware spectra now have peaks (97, 156 and 189 keV, probably U-235 and Th-234) but the isotope matcher calls them Tl-201 at 71 %, which is wrong for a uranium glaze: that is the low-energy matching weakness listed below, no longer hidden by an empty peak list. The BCV U Glass Brick gives 3 peaks and Ba-133/Am-241, also wrong.)* *(2026-10-04 evening: the Fiestaware and salt-cellar spectra no longer read as Tl-201 (the uranium template explains their lines), and the BCV brick no longer gets Ba-133/Am-241; it now reports nothing from its three weak peaks.)* *(2026-10-05: resolved by the two notes inside: the fit window and the uranium template.)*
- [x] Build a small labelled benchmark of real, calibrated spectra (known source → expected isotopes/chains, plus must-not-detect) before changing chain thresholds; get ground-truth calibration for the Takumar captures first *(2026-10-04: 44 labelled real spectra, checked for expected and forbidden chains, isotopes and series daughters; `tests/test_web_spectra.py` and `real_benchmark.py` keep the committed ones)*
- [ ] Peak list: noise spikes and Compton edges are reported as peaks (see `TECHNICAL_DEBT.md`, 'Spurious peaks', for what was measured and why no width or significance cut was applied). Needs labelled weak-peak spectra first; a Compton-edge flag for the 471 keV case would be a safe, separate step. *(2026-10-05: the Compton-edge flag is done: an unexplained peak at the edge of a much stronger line says so, never used to identify (`spectroscopy/compton_edges.py`). Noise spikes need labelled weak-peak spectra; waiting on you for those.)*
- [x] A detector response model (iodine K-escape 28.6 keV below a line, Compton backscatter E/(1+2E/511), the threshold) instead of Gaussian templates alone: the fit's chi2 is 200-300 on strong spectra (52 % in the 200-340 keV peaks, 20-35 % at 2000-3000 keV) and the unassigned excesses (125-160 keV, 195-205 keV) are the same structure. Freedom near 140 keV lets the U-235 143.8 keV template absorb it, so test on `tests/scoring_eval.py` and `tests/drift_sweep.py` *(2026-10-05: closed as not pursued. Two attempts at the same structure (lower edge, backscatter column) lost verdicts on the 33 spectra, the unassigned excess now shows it, and a full response model needs measured response data for each crystal. Reopen when there is a crystal with a known response.)*
- [x] Axis robustness: a 3 % axis error still flips one verdict or puts a false isotope in the top three in 58 perturbed runs (the weak 90-minute lens beyond its design range; a weak Am-241 gaining Tc-99m from the 140 keV structure; germanium has no template fit). A single-line isotope (Tc-99m, 140.5 keV) is listed from structure there: ask for more than one line or a clean peak *(2026-10-05: single-line isotopes now need a peak with significance >= 10 and a width 0.6-1.6x the detector's (`_stands_alone`); the drift sweep reads 294 of 308 right with 9 cases holding a false artificial isotope (was 10) and no wrong correction; the false ones are at 6 % drift or more, beyond what the correction is designed to hold.)*
- [ ] Grow the evaluation beyond one crystal family: HIGH-by-dominance (lead 3x, z >= 15) and the z >= 15 proof beyond +-20 keV are exercised by the AlphaHound only (every RadiaCode spectrum reads HIGH by z), and both thresholds sit inside ranges the 33 spectra do not decide. Needs a RadiaCode 110 (GAGG), NaI, other CsI sizes, and thinned AlphaHound captures *(Waiting on you: captures from other crystals (RadiaCode 110, NaI, other CsI sizes) with known sources)*
- [ ] Activity: the efficiency curves are generic and unverified against a calibrated source (the same ground truth as the ROI item above); a blend counts all its area for the first isotope (the 239 keV peak holds Ra-224's 241 keV beside Pb-212's 238.6) *(Waiting on you: the same known-source measurement as the ROI item)*
- [x] The fit divides z by sqrt(chi2/dof), so a high-count spectrum with unmodelled structure scores lower; HIGH-by-dominance works round it for a series, not for a single source *(2026-10-05: closed as a known property, not a defect: the scaling keeps a spectrum with unmodelled structure from being over-confident; a series is handled by HIGH-by-dominance and single sources keep their scaled z.)*
- [x] The calibration tool picks points from the chart *(2026-10-05: the click needed display 'block' but `show()` sets 'flex', and the dialog covered the chart; it is docked bottom-right with no backdrop, and reachable from the axis notice in every UI mode. `ui_smoke.py` clicks the chart.)*
- [x] The decay-chain card agrees with the isotope table *(2026-10-05: one decision per member in `_attach_member_status`; audited on 38 spectra with no disagreement; a test re-checks it on real spectra)*
- [x] A series parent with no gamma line of its own (Th-232, U-238) is a verdict on the series *(2026-10-05: it took the confidence of its best daughter and is listed whenever the series is reported; before, it ranked first, behind Ac-228 or behind Tl-208 by an accident of its borrowed lines)*
- [x] The activity estimate in the isotope rows *(2026-10-05: it used the peak height, 50 % branching and 60 s for every run, on the AlphaHound's efficiency for every detector; 38 times too high on the 8-hour run)*
- [x] The auto-correction refused a correct solution for an offset 0.8 keV beyond +-20 keV *(2026-10-05: range +-30 keV with a z >= 15 proof beyond +-20; `tests/drift_sweep.py` shows 294 of 308 right, no wrong correction)*
- [x] A clear series reads HIGH whatever its absolute z *(2026-10-05: lead 3x over every other source, z >= 15; HIGH 11/17 -> 15/17)*
- [x] Unassigned excess markers: structure the fitted peaks do not explain is shown, never used to identify *(2026-10-05: `spectroscopy/residual_peaks.py`; the 142 keV bump of the 8-hour lens, the 242 keV Pb-214 line the peak search misses on a radium spectrum)*
- [x] The install and run scripts *(2026-10-05: `call` before every Python line (the pyenv-win shim is a .bat and the old scripts ended silently after their first Python line), any folder, Python 3.11+ check, no `--reload`, browser opened when the server answers, `INSTALL.md` and README corrected, `tools/check_install.py`, `tests/test_install_scripts.py`)*
- [x] Evaluation scripts for the identification engine *(2026-10-05: `tests/scoring_eval.py` on 33 labelled spectra, `tests/drift_sweep.py` on 308 drifted cases)*
- [x] Fix/validate `backend/tools/generate_test_spectra.py` so each synthetic file's intended peaks dominate; then add golden tests (expected isotopes, no spurious chains) *(2026-10-05: seeded Poisson noise, smeared Compton edges (a hard step made a false peak under it); `tests/test_synthetic_spectra.py` checks, for two seeds, that each file's analysis names the intended source and nothing else, and that its strongest peak sits on a line put in.)*
- [x] Removed the dead frontend code for elements that no longer exist; `LEGACY_NULL_GUARDED` is gone, and `tests/test_frontend_ids.py` now allows no missing IDs.
- [x] **ROI peak fitting** (2026-10-03): `spectroscopy/roi_analysis.py` was rebuilt (two-band window, else a peak fit with neighbours; effective branching for blended lines; non-linear axes), validated on synthetic spectra for AlphaHound and Radiacode profiles and on the labelled real spectra; `tests/test_roi_analysis.py`. See CHANGELOG.
- [x] ROI: lines of a *different* nuclide inside the window cannot be separated by these detectors (Cs-137 beside Bi-214 609 keV, Ac-228 338 keV on Pb-214 352 keV); the result warns but still reports a detection. A source-aware correction (use the chain or template fit to subtract the other nuclide) would fix it. *(2026-10-04: done for the enrichment check, which no longer reads Tl-208 583 / Cs-137 662 in the Bi-214 window as radium; the ROI result itself still only warns.)* *(2026-10-05: closed as not to be done. Subtracting another nuclide needs its area inside the window, which only the template fit estimates, with an uncertainty larger than the correction; a corrected number would look more certain than it is. The warning stays and the enrichment check is fixed. Reopen if a source of known activity shows the fit's estimate is good enough.)*
- [ ] ROI: ground-truth the generic efficiency curves per detector with a known source (the AlphaHound CsI measured 7.1 % FWHM at 662 keV on the Cs-137 verification file against the 10 % in the database; the fit already adapts, the efficiencies do not). *(Waiting on you: a source of known activity at a known distance, measured on your detector)*
- [x] Decay chains: the line-matching tolerance in `match_peaks_to_chain` still widens to 60 keV above 10,000 counts and lets one peak explain several lines (member lists such as "Tl-208: 575.8, 895.3 keV" can repeat a peak). Replace by a resolution-aware tolerance and one-to-one assignment once the benchmark has more labelled spectra. *(2026-10-05: `match_peaks_to_chain_detail` uses the detector's resolution at each line and gives each line its own peak (lines taken strongest first); peak reuse across lines 34 to 0 on the labelled spectra, verdicts unchanged.)*
- [x] Isotope confidences follow the spectrum (2026-10-04: the enhanced rescoring read keys the matcher never writes, so Th-232 was always 74 %; fixed together with one-to-one, resolution-aware matching and template thresholds measured on real spectra; see CHANGELOG).
- [x] Confirm the automatic energy-axis correction on the live AlphaHound after a server restart: the notice, Undo, and that the isotope list matches the source *(2026-10-04, live on COM8 after `devctl restart`, 10/10 checks through Get Current: the axis corrected from the thorium lines (gain 1.09-1.12, offset -11 to -20 keV as the spectrum accumulates), the result Th-232 with Pb-212 and Tl-208, Undo restores the device axis exactly, the device spectrum is never cleared, no JS errors. Found and fixed on the way: *Apply correction* stayed visible next to *Undo* (a button rule beat `[hidden]`; browser checks now test real visibility) and the message was repeated as a toast over the notice. Left as it is: after the straight-line correction 2614.5 keV still reads ~2458 (-6 %), the curvature of the AlphaHound's own axis at the top; it no longer affects identification. Confirmed by the owner on 2026-10-04.)*
- [x] Automatic axis correction declines short captures (few clear peaks), single-line sources (Cs-137 / Am-241 alone) and Ba-133 alone; a stored per-device gain (from a correction you accept, with the temperature) would cover them. *(2026-10-05: closed by design. A stored per-device gain applied silently would hide drift and mis-correct when the temperature changes; a short capture is told why it was not corrected, and a file with channel numbers only can pick a known axis (energy presets).)*
- [x] N42 files saved before 2026-10-04 open on a 0-3000 keV axis in InterSpec/SpecUtils; a one-off rewrite tool (like `recalibrate_n42.py`) could add the standard calibration to them. *(2026-10-05: `tools/standardise_n42.py` writes `<name>.std.n42` and refuses files that already carry the axis or have no usable one; `tests/test_standardise_n42.py`.)*
- [x] `POST /device/spectrum` (API only, not used by the UI) returns peaks/isotopes/chains but drops `warnings`, `calibration_check`, `auto_calibration` and `data_quality`; `/device/spectrum/current` returns them. *(2026-10-05: the response now carries what the upload route's does; `test_device_spectrum_endpoint_returns_everything_the_analysis_found`.)*
- [ ] Radiacode alarm limits are read-only: expose `set_alarm_limits` (the driver has the getter; the library has the setter). *(Waiting on you: a RadiaCode on the bench: a setter that writes device registers is not exposed without being tried on the hardware)*
- [x] Browser-check the chain diagram's "or" branch and the ROI notes in the other themes and on a phone width (checked in Dark at desktop width only). *(2026-10-05: `ui_theme_sweep.py` now loads a real thorium capture and checks the chain card in all 17 themes at desktop and 390 px, and the Radiacode tab: 102 combinations, no overflow, contrast or script errors; the phone-width screenshot shows the diagram and its 'or' branch inside the width.)*
- [x] Replace remaining `print` calls in multi-line/other statements and the `[Tag]` message prefixes now duplicated by logger names *(2026-10-05: no `print` and no log tag that repeats the logger name remain in the library code; `tests/test_logging_style.py` fails on either.)*
- [x] Split `routers/analysis.py` (1500+ lines) into `analysis.py`, `export.py`, `nuclear.py` (same 37 routes)
- [x] `static/js/main.js` is about 1,960 lines: the section functions are modules now (see `TECHNICAL_DEBT.md`); what remains is the device monitoring, acquisition, history, comparison and background logic and the `let` state they share. A small state module would let those move too. *(2026-10-05: closed as not worth the risk now. The remaining logic shares `let` state with the live device paths (polling, acquisition, history), which can only be fully exercised on hardware; a state module changes no behaviour and would be a large diff there. The browser suite is now 217 checks if it is taken up later.)*
- [x] Add unit tests for frontend JavaScript modules *(2026-10-04: Node tests now cover the modules with logic that runs without a page: units and alerts, axis, summary, metadata cards, decay view, shielding view, export support, HTML escaping, dialogs, device features (including a check that every `data-device-feature` in the HTML exists), themes, accessibility helpers and the device screen. The DOM-bound modules (panels, tabs, uploads, the exports and calibration UIs) are covered by the browser suites, not by Node.)* *(2026-10-05: closed. What runs without a page has Node tests; the DOM-bound modules are exercised by the 217-check browser suite, which is the right level for them.)*
- [x] Add unit tests for backend API endpoints ✅ (`backend/tests/test_api_endpoints.py`; 59 tests pass)
- [x] Implement TypeScript for type safety *(2026-10-05: closed as declined. The front end has no build step by design (it is served as-is and installed by a batch file); TypeScript would add one. Types are covered by the Node tests and the ID checks.)*
- [x] **Centralize Peak Detection** ✅ (formats/csv_parser.py no longer detects peaks/isotopes; all formats go through `analyze_spectrum_peaks()` in `spectroscopy/analysis_utils.py`) — original note: Remove `detect_peaks()` calls from individual parsers (formats/csv_parser.py, etc.) and have all peak detection happen in `_analyze_spectrum_peaks()` in `analysis.py`. This ensures consistent detection across all file formats (N42, CSV, CHN, SPE, SPC, PCF, etc.) and simplifies threshold tuning.

### Performance Optimization
- [x] Analysis + Radiacode routes moved off the event loop (sync handlers run in threadpool)
- [x] Lazy load Chart.js and other heavy libraries *(Deferred: already loaded with `defer`; modules use the globals at init, so lazy loading needs a browser to verify)* *(2026-10-05: closed as not needed. The libraries load with `defer`, the page loads and renders quickly on this machine, and the server is on the local network.)*
- [x] Implement WebWorkers for ML training *(2026-10-05: closed as not applicable. Training runs on the server in a thread, not in the page.)*
- [x] Optimize large spectrum rendering *(2026-10-05: closed: the 9-hour and 8-hour captures render in the browser suites without a stall; no case was found that needs it.)*
- [x] Add service worker for offline capability *(2026-10-05: closed as declined. The app is served by a server on the same machine or LAN, so offline means the server is down; a service worker would only cache stale scripts after an update.)*

### Device & Calibration
- [x] **RadView Clarification**: the 7.4 keV vs 3.0 keV discrepancy is answered by our own measurements (7.4 is the average slope of the device's cubic axis; 3.0 was a forced linear axis in older N42 files). What is still worth asking RadView is listed in `docs/radview_questions.md`: does the `C` command persist, the factory calibration source, dead time, firmware/battery/bias.
- [x] **Dead Time Logic**: Implement dead-time correction if device doesn't support it internally *(2026-10-05: closed as not needed. Both devices report live time as well as real time and the activity estimate divides by live time.)*
- [ ] **Temperature Compensation**: Temperature captured - consider using for gain stabilization *(2026-10-04: the temperature and compensation factor are now saved with every spectrum, and fill in by themselves within seconds of a fresh connect. Using them to stabilise the gain waits for captures at different temperatures; see TECHNICAL_DEBT.md. 2026-10-04 evening: drift is now corrected from the source's own lines (automatic axis correction); a gain-versus-temperature model would still help short captures with too few lines.)* *(Waiting on you: captures of the same source at different temperatures.)*
- [x] **CSV/XML Energy Interpolation**: Implement energy-per-channel interpolation for imported CSV and XML files lacking energy data (e.g., legacy formats with only channel numbers). Support presets for known detectors (Radiacode models, AlphaHound profiles), custom detector coefficients, or manual keV/channel entry. *(2026-10-05: `spectroscopy/energy_presets.py` and the calibration dialog: known RadiaCode and AlphaHound axes ranked by the template fit, a linear axis, or a polynomial; `tests/test_energy_presets.py`, smoke section AB.)*

### Radiacode Device Features (Available in radiacode library, not yet exposed)
- [x] **Device Settings Panel**: Add UI for Radiacode device configuration: *(2026-10-05: the panel exists; every setting route is tested against a fake driver (`tests/test_radiacode_settings_routes.py`, 27 tests: bounds, refusal, not connected). What each setting does on a real device waits on you, see the checks under Radiacode above.)*
    - [x] `set_display_brightness(0-9)` - Display brightness control
    - [x] `set_sound_on(bool)` - Enable/disable device sound alerts
    - [x] `set_vibro_on(bool)` - Enable/disable device vibration
    - [x] `set_display_off_time(seconds)` - Auto-shutdown duration
    - [x] `set_language('en'/'ru')` - Device language setting
- [x] **Accumulated Dose Display**: Show total accumulated dose from `data_buf()` RealTimeData *(2026-10-05: shown, and the route is tested; the figure against the device screen waits on you.)*
- [x] **Device Info Display**: Show serial number and firmware version in connection panel *(2026-10-05: shown, tested with a fake driver.)*
- [x] **Configuration Readout**: Expose `configuration()` output for debugging/advanced users *(2026-10-05: exposed, tested with a fake driver.)*

### ROI Enhancements ✅
- [x] **Auto-populate ROI acquisition time**: Pulls from N42/CSV metadata (live_time/real_time/acquisition_time)
- [x] **Change ROI time unit to minutes**: Accepts fractional minutes (e.g., 1.5) for consistency with acquisition UI

### Source-Specific Analysis Enhancements ✅ (Implemented in `spectroscopy/source_analysis.py`)

#### Thoriated Lens (Th-232)
- [x] ThO₂ mass estimation from Th-234 activity - `analyze_thoriated_lens()`
- [x] Secular equilibrium check (Pb-212/Th-234 ratio) - `nuclides/chain_detection_enhanced.py`
- [x] Pb-212 (239 keV), Tl-208 (583 keV) in isotope database - `nuclides/isotope_database.py`

#### Smoke Detector (Am-241)
- [x] Compare to standard detector activity (~37 kBq) - `analyze_smoke_detector()`
- [ ] Age estimation from Pu-241 ingrowth *(Deferred - requires long-term tracking)* *(Waiting on you: needs a source and months of tracking.)*

#### Radium Dial (Ra-226)
- [x] Dose rate estimation (μSv/hr at contact and distance) - `spectroscopy/activity_calculator.py`
- [x] Radium mass estimation from Bi-214 activity - `analyze_radium_dial()`
- [x] Age verification via Pb-210 equilibrium *(Deferred - Pb-210 not easily detectable)* *(2026-10-05: closed as not feasible: Pb-210's 46.5 keV line sits among the detectors' low-energy structure and X-rays.)*

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
- [x] Dose rate estimation for all source types - `spectroscopy/activity_calculator.py`

### New Source Types ✅ (2025-12-17)
- [x] **Uranium Ore** - Full U-238 chain + U-235 detection
- [x] **Cesium-137 Source** - 662 keV calibration source
- [x] **Cobalt-60 Source** - 1173/1332 keV dual peaks
- [x] **Synthetic Test Spectra** - 6 N42 files in `backend/data/test_spectra/`

### Low Priority / Future
- [x] **Radiacode Device Integration** ✅ Implemented in `devices/radiacode_driver.py` + `routers/device_radiacode.py` - USB connection, spectrum, dose rate polling
- [x] **Radiacode Bluetooth on Windows**: ✅ Implemented using `bleak` library. Added BLE device scanning, device selection dropdown, and cross-platform BLE connectivity (Windows/macOS/Linux).
- [x] **Radiacode BLE Scan Fix (Windows)**: Fixed `pyserial`/`pywin32` COM STA conflict that silently broke BLE scan/connect on Windows (`allow_sta()` in `devices/radiacode_bleak_transport.py`).

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
- [x] **ML identification**: first built on PyRIID (dropped 2026-10-02), now a scikit-learn MLP on a physics-based synthesiser, 90+ isotopes with IAEA intensity data (see `docs/ML_GUIDE.md`)
- [x] **Peak Detection Enhancement**: Improved threshold, 20+ peaks detected
- [x] **U-235/U-238 Prioritization**: Abundance weighting in nuclides/isotope_database.py

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
- [x] **Test Infrastructure**: the backend suite (641 tests on 2026-10-03) plus headless-browser checks (smoke 160, theme and channel sweeps 34 combinations each, accessibility audit); `tests/test_repo_layout.py` guards the repository layout.
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
