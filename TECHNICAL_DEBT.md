# Technical Debt Report

**Date:** 2026-10-03
**Tests at the time of writing:** 646 backend tests pass; the headless-browser checks pass against the refactored server (smoke 162/162, theme and channel sweeps 34 combinations each with no issues, accessibility audit).

This replaces the 2025-12-16 report, whose figures had gone stale (it listed `routers/analysis.py` at 1,464 lines and
test coverage as unknown).

---

## Done in this pass

| Area | Change |
|------|--------|
| Error handling | The 15 bare `except:` clauses now name the exceptions they expect, and the handlers that swallowed errors silently log them at debug level (`analysis_utils`, `roi_analysis`, `routers/analysis`, `chn_spe_parser`, `alphahound_serial`). |
| Logging | `print()` calls in library modules (`peak_detection*`, `fitting_engine`, `multiplet_fitting`, `spectral_analysis`) are `logger` calls. |
| Frontend escaping | `static/js/html.js` adds `escapeHtml`; BLE device names, server error text and custom isotope names are escaped before they reach `innerHTML`. `tests/test_html_escape_js.py` fails if a raw `${err.message}`, `${device.name}` and similar returns to a template. |
| Frontend logging | `console.log` calls go through `static/js/log.js`, silent unless `localStorage.alphahoundDebug = '1'`. |
| `main.js` size | The toast helpers (`toast.js`) and the decay tool (`decay_tool.js`) moved out: 3,631 to 3,286 lines. |
| Long functions | Each was snapshotted on synthetic and real spectra first, refactored, and required to give identical output. `ROIAnalyzer.analyze_uranium_ratio` 320 to 214 lines (384 cases); `isotope_database.identify_isotopes` 242 to about 35 (scoring in `_score_isotope`, suppression and boost rules in `_apply_contextual_rules`, chain and weight tables at module level; 141 cases; its `[DEBUG ...]` messages now log at debug level, not info); `ROIAnalyzer.analyze` 255 to 165 (`_validated_spectrum`, `_source_validation`, `_detection_status`, `_detection_confidence`, `_limits_and_recommendations`; 882 cases over every ROI isotope, 3 detectors, 8 spectra, 3 source types, plus out-of-range and bad-input cases); `ml_analysis.MLIdentifier.lazy_train` 178 to 34 (`_training_isotopes`, `_synthesise_training_set`, `_with_real_spectra`; `SAMPLE_WEIGHTS` and `TRAINING_MIXTURES` are module constants; the trained weights of both models are bit-identical, and so are the opt-in real-data weights once NumPy's global generator is seeded); `csv_parser.parse_csv_spectrum` 172 to about 45 (`_manual_columns`, `_resolve_energies`, `_parse_csv_file`; 25 CSV shapes, identical output); `isotope_database.identify_decay_chains` 171 to 76 (`_match_chain_indicators`, `_chain_confidence_level`, `_peak_strength`; 673 runs); `source_identification.identify_source_type` 170 to 70 (`_measure_isotopes`, `_score_source`, `_confidence_level`, `ISOTOPES_TO_CHECK`; 80 runs over 8 source types and all confidence levels); `analysis_utils.analyze_spectrum_peaks` 226 to 138 (`_detect_peaks`, `_reconcile_with_template_fit`, `_assess_data_quality`; 74 runs). |
| CWT divide-by-zero warning | `find_peaks_cwt` divides by a noise percentile that is exactly 0 on a sparse spectrum (the ridge then counts as infinitely strong, which is the intended result), and numpy warned on every such upload. The warning is silenced with `np.errstate` around the call; peaks are identical on 16 runs (the real CSV spectra and synthetic ones); `test_real_csv.py` fails without the fix. |
| Becquerel in the CSV parser | `bq.Spectrum.from_file` cannot read `.csv` ("File type .csv can not be read"), so that branch never succeeded; the pandas path did all the work, yet a server without Becquerel refused every CSV upload. Removed: the parser no longer imports Becquerel (31 of 34 CSV cases identical, no successful parse changed, 3 error messages reworded), and `becquerel` is out of `backend/requirements.txt`, `requirements_lightweight.txt` and `install.bat`. It is only needed to run `tools/becquerel_comparison.py` (`pip install becquerel`). |
| ML real-data training not reproducible | `ml/ml_data_loader.py` drew the augmentation noise from NumPy's unseeded global generator and read files in filesystem order, so a model trained with `ML_USE_REAL_DATA=1` differed on every training. It uses a seeded `Generator` (`seed=12345`, passed through `load_real_training_data`) and sorted file order; `tests/test_ml_data_loader.py` trains twice end to end on labelled CSVs and expects identical weights (it fails on the old loader). |
| `main.js` (3,631 lines at the start of the session, now about 1,960) | `setupEventListeners` (1,116 lines) was split into 13 section functions and each moved into its own module (`device_tabs`, `exports_ui`, `analysis_panels`, `dose_alert_settings`, `radiacode_panel`, `settings_history`, `chart_controls`, `device_controls`, `comparison_background`, `snip_calibration`, `file_upload`, `ui_mode_listener`, `alphahound_panel`), each exporting `setupX(deps)`: shared state arrives through getters and setters, `ui`/`chartManager` and main.js functions are passed in, nothing is monkeypatched or imported under a second specifier. A script moved the text; ESLint `no-undef` found the errors the first versions of it made (spread references, and a call that still passed a deleted function) before any browser run. 18 lookups of elements that are no longer in `index.html` (and the 400 lines of handlers behind them: Radiacode disconnect / get-spectrum / clear / reset-dose, the top-bar port controls, the uranium-ratio button, ...) were deleted, and `LEGACY_NULL_GUARDED` is gone. |
| Frontend scope bug found by that check | `const originalHtml` was declared inside a `try` and read in its `catch` (Edit N42 Metadata): when the template request failed, the handler threw a ReferenceError and the button stayed disabled and dimmed on "Generating...". Fixed; smoke checks T1 and T2 fail without the fix (button stuck, `originalHtml is not defined`). CI now runs ESLint's `no-undef` over `backend/static/js` (all 25 modules clean), which catches this class without running the page. |
| CI | `.github/workflows/tests.yml` runs the backend suite and the frontend scope check on every push to `main` and every pull request (windows-latest, Python 3.12). Rehearsed in a clean clone with a fresh virtualenv built from `backend/requirements.txt`: 645 passed. |
| `.gitattributes` | LF in the repository, CRLF for batch files, binaries untouched (every tracked text file was already LF, so nothing was rewritten). |
| Two copies of `ui.js` and `charts.js` | `main.js` imported `./ui.js?v=3.0` and `./charts.js?v=4.6`; `calibration.js` and `estimator_ui.js` imported the plain names. The browser keys a module by its whole URL, so each loaded twice and two separate `ui` and `chartManager` existed (masked because `main.js` re-points `window.chartManager`). Removed the unused imports; `tests/test_frontend_imports.py` fails if a module is imported under two specifiers (it flags exactly the two conflicts on the earlier files). |
| Tests without monkeypatching | The two tests I had written that patched an environment variable, a module function and `tempfile` now pass the values in: `MLIdentifier(use_real_data=, real_data_dir=)` and `parse_csv_spectrum(..., temp_dir=)`. About 250 existing patches remain in the device tests, which isolate serial and BLE layers; they were not rewritten. |
| Temp-file leak | A CSV upload that was rejected left its temporary file in the temp directory (265 had piled up). The file is now removed on every path; `tests/test_csv_temp_cleanup.py` fails on the old code. |
| Repo layout | 19 unreferenced images and a scraped web page moved to `TO_BE_DELETED/` (`backend/static` 16 MB to 1.7 MB); the seven guides and notes that sat in the root moved to `docs/` with every link fixed (root: 22 to 15 tracked files); `tests/test_repo_layout.py` fails if new root files, backup/temp files, files over 800 KB, unreferenced images or broken document links appear (each rule verified to fire on a real offender). |
| Fixtures and user data | The real spectra the tests use moved from `backend/data/acquisitions/` to `backend/tests/data/real_spectra/`; `acquisitions/` (the user's own measurements, 70 files on disk) is ignored and untracked (the files stay on disk); a layout rule fails if any of it is tracked again. `spectrum_wrapper.py` (457 lines, imported by nothing) went to `TO_BE_DELETED/`; `generate_test_spectra.py` is in `tools/`. |
| Backend packages | The 43 modules that sat side by side in `backend/` are in five packages: `formats/` (9: parsers, N42 export and editor, PDF report), `spectroscopy/` (17: peaks, fitting, ROI, source identification), `nuclides/` (10: isotope database, chains, decay engines), `devices/` (5: drivers, acquisition) and `ml/` (2); `backend/` keeps `main.py` and `core.py`. 186 import lines rewritten by script (lazy imports and `try/except ImportError` ones included), an AST check finds no bare import of a moved module, the three `__file__`-based data paths were adjusted, and all eight analysis snapshots (isotopes, chains, pipeline, source identification, CSV, CWT peaks, ROI, ML weights) are byte-for-byte identical before and after. A layout rule fails if a module is added loose to `backend/`. |
| Browser tests on another port | The four `ui_*.py` scripts take the server from `ALPHAHOUND_URL` (default `http://localhost:3200`), so they can run against a second instance while a device is connected to the first. |
| Test layout | `test_fitting_engine.py` and `test_multiplet_fitting.py` were outside `tests/` and never ran; they are in `tests/` now. The print-driven `test_becquerel_comparison.py` is `tools/becquerel_comparison.py`. |
| Install files | `requirements_lightweight.txt` was missing `slowapi` (imported by `main.py`) and listed an unused `pillow`; `install_lightweight.bat` now installs from that file. The app imports cleanly with the optional packages absent. |

## Open: waiting on a person

| Item | Detail |
|------|--------|
| Dead files | Moved to `TO_BE_DELETED/` (see its README) because the tool could not delete them: root backups and run output, five unused modules, the old `backend/archive/` and the former `archive/` (42 PyRIID-era debug scripts, icon backups, printed results). Nothing references them. Delete with `git rm -r TO_BE_DELETED`. |
| Kept from the old `archive/` | `legacy/AlphaHound-main/` (upstream GUI, MIT licence), `docs/alphahound_probes/` (raw device captures), `docs/abundance_weighting_research.md`, and two real CSV spectra in `backend/tests/data/real_csv/` with `tests/test_real_csv.py`. |

## Found while refactoring

Fixed, each with tests in `tests/test_csv_columns.py` (they fail on the old parser):

- A one-column CSV was reported as calibrated with the counts used as the energy axis, and a headerless one lost its first value. Cause: pandas guessed the delimiter among all characters and split on a letter of the header. Detection is now limited to comma, semicolon, tab and space.
- A first line such as `Calibration: a0 a1` made the file fail to load (it was taken for the header). Calibration lines in the first 25 lines are now kept out of the table; the calibration is read from them as intended.

Still open:

- Real CSV coverage is two spectra (`tests/data/real_csv/`, `tests/test_real_csv.py`); more real exports from other tools and devices would harden the parser further.

## Open: structural

| Issue | Where | Notes |
|-------|-------|-------|
| Oversized functions | 15 functions over 100 lines, e.g. `ROIAnalyzer.analyze_uranium_ratio` (212) and `analyze` (165), `parse_n42` (166), `generate_pdf_report` (151), `upload_file` (145) | Split the same way as `analyze_uranium_ratio`: capture output on a set of synthetic spectra first, refactor, require an identical result. |
| `style.css` | 2,909 lines, plus `button-fixes.css` and `device_styles.css` overrides; 350 inline `style=` attributes in `index.html` | |
| Module pairs with similar names | Reviewed 2026-10-03 and **not merged**: they do different jobs. `peak_detection` is one basic `find_peaks` function (the fallback and the `/analyze/fit-peaks` route) beside the 500-line CWT pipeline in `peak_detection_enhanced`; `source_analysis` computes per-source quantities (radium mass, Cs-137 decay correction, ...) while `source_identification` classifies by signature; `isotope_database` matches gamma lines while `isotope_roi_database` defines ROI windows. Six parsers in `formats/` still share no interface. The decay modules are deliberately layered (`decay_data` -> `bateman` -> `decay_calculator` -> `decay_engine`, with `curie_*` as an optional engine). | |
| Remaining silent handlers | `except Exception: pass` around close/disconnect calls in `radiacode_*`, `curie_compat` | These are cleanup paths where there is nothing to do; left as they are. |
| Spurious peaks in the peak list | Noise spikes are reported next to real peaks (the synthetic Cs-137 file lists 1107 and 1890 keV, 11 and 5 net counts; its 471 keV entry is the Compton edge, a real feature that is not a gamma line). **Measured 2026-10-03 on 17 calibrated spectra (real and synthetic, 108 peaks), and deliberately not changed:** (1) fitted width against the detector's physical resolution does not discriminate: the median fitted width is 0.33 of the database FWHM and strong real peaks sit far below any cut (7,737 counts at 518 keV, ratio 0.15); (2) significance (net area / uncertainty) does not either: 3 of the 13 generator peaks have z 1.1 to 2.3, below spurious spikes, while non-line features reach z 9.5 and 43. Any cut that removes the spikes also removes real weak peaks, and there is no labelled ground truth for weak peaks to judge the trade. A start would be labelled weak-peak data, then a rule scored on it; a separate Compton-edge flag (position follows from the photopeak) would handle the 471 keV case. | |
| `innerHTML` | 68 uses; the untrusted-text sites are escaped, the rest build markup from numbers and constants | Prefer `textContent` / DOM construction for new code. |
| No authentication | The server binds `0.0.0.0:3200` for LAN access and exposes device control and file endpoints. Now stated plainly in the README ("Security" under LAN Access) with the loopback command; still no login | An opt-in token would be the next step. |
| Remaining `console.log` filter | `log.js` hides diagnostics by default; nothing yet shows them in the UI | |
| `ml_analysis` | Module-level `_ml_identifiers` cache; the first AI request after a restart trains the model on a request thread | |

## Documentation

`CHANGELOG.md` (about 800 lines) is history and is left as written; `TODO.md` mixes open items with long completed sections (its handoff notes were refreshed on 2026-10-03). A shorter, open-items-only `TODO.md` with the completed work moved into the CHANGELOG would be easier to keep current.

## Unused items: audit and recommendation (2026-10-03)

Nothing below has been deleted. Method: pyflakes (unused imports and locals), vulture for unused definitions with every hit then
searched for in all tracked files (Python, JavaScript, HTML, docs, scripts; framework-registered handlers excluded), ESLint
`no-unused-vars`, the live route table checked against the frontend, tools, tests and docs, CSS and HTML cross-checks, and the
requirements list against real imports. Each category states how sure the finding is.

### A. Remove: verified, mechanical, easy to undo with git

| Item | Detail |
|------|--------|
| 50 unused Python imports | pyflakes; none is re-exported (no other file imports the name from that module). 4 of them are the `try:` block in `routers/analysis.py` that sets `HAS_ENHANCED_ANALYSIS`, which nothing in that file reads (the real probe is in `analysis_utils`): delete the whole block. |
| Python leftovers inside functions | unused locals (`format_id`, `start_ch`, `end_ch`, `num_coeffs`, `ns`, `k_alpha`, `k_beta`, an unused `energies`), a `global _ml_identifiers` that assigns nothing, `sanitize_for_json` imported twice in `routers/device.py`, f-strings without placeholders. |
| Two functions named `get_detectors` | `routers/analysis.py` (`/detectors` and `/analyze/detectors`): both routes work, but the second definition shadows the first in the module. Rename the first (`list_detector_names`). |
| 1 dependency | `uncertainties` is imported by nothing; it was there for Becquerel. Remove it from `backend/requirements.txt`. Also declare `pydantic` (imported directly by five routers, today only present through FastAPI). |
| `install.bat` | A hand-typed package list without `radiacode`, `bleak`, `curie`, `radioactivedecay`, `SandiaSpecUtils` or `libusb-package`. `INSTALL.md` sends people to it, while the README correctly uses `install_deps.bat` (installs from `requirements.txt`). Delete it and point `INSTALL.md` at `install_deps.bat`. |
| 5 icons | `camera.svg`, `globe.svg`, `lightbulb.svg`, `radiation.svg`, `theme.svg` in `static/icons`: no markup, script or style names them, and no icon path is built dynamically. |
| 27 CSS selectors (12 classes) | `.card-bg` (13 per-theme overrides), `.high-confidence`, `.medium-confidence`, `.low-confidence`, `.device-header`, `.device-panel`, `.device-stats`, `.icon-btn` (+ light theme), `.icon-lg`, `.text-center`, `.feature-disabled-wrapper` (3 rules), `.radiacode-active`. Nothing builds these names at run time (checked). |
| JavaScript leftovers | `initDevice` (a function nothing calls), `acquisitionStartTime`, `lastCheckpointTime`, `CHECKPOINT_INTERVAL_MS` (assigned, never read), unused `api` imports in `calibration.js`, `isotopes_ui.js` and `ui.js`, unused locals in `charts.js` and `ui.js`. |

### B. Dead but deliberate-looking: remove after a glance (about 650 lines)

Each has no reference anywhere in code, tests or scripts. Most are leftovers of code that was since replaced.

| Where | What | Lines | Why I would remove it |
|-------|------|------:|-----------------------|
| `ml/ml_analysis.py` | `hybrid_identify`, `add_environmental_background`, `energy_to_channel_with_jitter`, `get_available_detectors`, `get_available_ml_models` | 185 | Left from the PyRIID-era design; only the CHANGELOG mentions them ("for future UI"). |
| `spectroscopy/peak_detection_enhanced.py` | `merge_with_existing_peaks`, `find_peaks_in_spectrum` | 100 | The upload pipeline (`analysis_utils`) replaced them. |
| `spectroscopy/roi_analysis.py` | `calculate_ra226_equilibrium_correction`, `_calculate_background` | 84 | Replaced by the rebuilt ROI engine and the equilibrium check. |
| `spectroscopy/multiplet_fitting.py` | `deconvolve_overlapping_peaks` | 67 | `enhance_peaks_with_multiplet_fitting` is the one in use. |
| `spectroscopy/confidence_scoring.py` | `calculate_halflife_penalty` | 45 | No caller. |
| `nuclides/isotope_validation.py` | `validate_isotope_detection`, `should_include_as_chain` | 59 | `generate_validation_rules` (used) stays. |
| `spectroscopy/spectrum_algebra.py` | `rebin_spectrum` | 35 | No route or caller. |
| `spectroscopy/activity_calculator.py` | `calculate_dose_rate_sv_h` (+ the `UCI_TO_BQ` constant) | 26 | Its own docstring says "Legacy function". |
| smaller | `curie_integration.get_isotope_half_life` (18), `fitting_engine.fit_single_peak_auto_roi` (12), `chain_detection_enhanced.DetectedChain` (12), `specutils_parser.is_supported_format` (10), `gauss_area.gaussian_area_counts` (3) | 55 | No caller. |
| API | 4 routes nothing calls, not even docs or tests: `POST /analyze/identify-source`, `POST /analyze/multiplet`, `GET /device/capabilities`, `GET /radiacode/configuration`; with them the unused client wrappers in `api.js` (`fitPeaks`, `exportPDF`, `checkRadiacodeAvailable`, `setSoundControl`, `setVibrationControl`, `getAvailableCommands`, `getSpectrumUnified`) and in `charts.js` (`decimateData`, `highlightMultipleROI`, `clearIsotopeHighlights`, `hideScrubber`) and `AlertCenter.isActive` | n/a | Only if the HTTP API is not meant as a public interface. 8 more routes appear only in docs and 12 only in tests; I would keep those. |
| `backend/tools/becquerel_comparison.py` | the research script behind the decision not to adopt Becquerel | 432 | The decision is made and the application no longer uses the library. |
| `docs/UI_MODE_TESTING.md` | a manual checklist from 2025-12 (v2.6); nothing links to it | 76 | The browser suite covers the settings and mode paths. |

### C. Looks unused, is not: keep

* `unpack_string`, `remaining` (`radiacode_bleak_transport.py`), `_seq`, `sender`, `prec`: they match an external library's interface or a callback signature.
* `python-multipart` (FastAPI uploads), `websockets` (uvicorn WebSocket support) and `pyusb` (the Radiacode USB driver imports `usb`) are indirect requirements.
* 26 JavaScript names are exported but only used inside their own file: the `export` is unneeded, nothing is dead.
* `data/idb/isotopes` (49 files read as a folder), `Cs137_Verification_Spectra.n42` (two tests), `docs/alphahound_probes/`.
* 5 of the 6 synthetic spectra in `backend/data/test_spectra/` are read by nothing but the generator that writes them. Keep them for the open "golden tests" item in `TODO.md`, or drop them and regenerate on demand.
* 2 element ids nothing references (`radiacode-settings-panel` carries a `data-device-feature` hook the code selects by attribute).

### D. Housekeeping found on the way

* `download_iaea_data.py` sits in the repository root and writes `backend/data/idb`: it belongs in `backend/tools/`.
* `ALPHAHOUND_DOSE_LOG` is read by `main.py` but documented only in the CHANGELOG; `REAL_BENCHMARK_EXTRA` (benchmark helper) is not documented anywhere.

## Manual verification backlog

`TODO.md` still lists about 25 items that need a person or hardware (live Radiacode and AlphaHound readings, themes on
a phone, screen readers). That is verification debt, not code debt, and nothing in this pass touched those paths.

## Good practices

- No `import *`; type hints and Pydantic validation on the API; rate limiting; CORS off by default.
- 641 backend tests plus browser checks (smoke, accessibility, theme sweep, channel sweep).
- Real-spectrum benchmarks (`tests/real_benchmark.py`, `tests/ml_benchmark.py`) guard the analysis numbers.
