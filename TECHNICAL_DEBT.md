# Technical Debt Report

**Date:** 2026-10-03
**Branch:** `chore/technical-debt-cleanup`
**Tests at the time of writing:** 629 backend tests pass; the headless-browser smoke test (`backend/tests/ui_smoke.py`) passes 160/160.

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
| Long functions | Each was snapshotted on synthetic and real spectra first, refactored, and required to give identical output. `ROIAnalyzer.analyze_uranium_ratio` 320 to 214 lines (384 cases); `isotope_database.identify_isotopes` 242 to about 35 (scoring in `_score_isotope`, suppression and boost rules in `_apply_contextual_rules`, chain and weight tables at module level; 141 cases; its `[DEBUG ...]` messages now log at debug level, not info); `ROIAnalyzer.analyze` 255 to 165 (`_validated_spectrum`, `_source_validation`, `_detection_status`, `_detection_confidence`, `_limits_and_recommendations`; 882 cases over every ROI isotope, 3 detectors, 8 spectra, 3 source types, plus out-of-range and bad-input cases); `ml_analysis.MLIdentifier.lazy_train` 178 to 34 (`_training_isotopes`, `_synthesise_training_set`, `_with_real_spectra`; `SAMPLE_WEIGHTS` and `TRAINING_MIXTURES` are module constants; the trained weights of both models are bit-identical, and so are the opt-in real-data weights once NumPy's global generator is seeded); `csv_parser.parse_csv_spectrum` 172 to about 45 (`_manual_columns`, `_resolve_energies`, `_parse_csv_file`; 25 CSV shapes, identical output); `analysis_utils.analyze_spectrum_peaks` 226 to 138 (`_detect_peaks`, `_reconcile_with_template_fit`, `_assess_data_quality`; 74 runs). |
| Temp-file leak | A CSV upload that was rejected left its temporary file in the temp directory (265 had piled up). The file is now removed on every path; `tests/test_csv_temp_cleanup.py` fails on the old code. |
| Test layout | `test_fitting_engine.py` and `test_multiplet_fitting.py` were outside `tests/` and never ran; they are in `tests/` now. The print-driven `test_becquerel_comparison.py` is `tools/becquerel_comparison.py`. |
| Install files | `requirements_lightweight.txt` was missing `slowapi` (imported by `main.py`) and listed an unused `pillow`; `install_lightweight.bat` now installs from that file. The app imports cleanly with the optional packages absent. |

## Open: needs a decision

| Item | Detail |
|------|--------|
| Dead files tracked in git | Root: `old_main_backup.js`, `head_charts.js.tmp`, `old_charts.js.tmp`, `older_charts.js.tmp`, `calibration_results.txt`, `scan_results.txt`, `ml_hobby_test.txt`, `test_output.txt`, `2025-12-19  11-03-17_174668s.csv`, `python packages research.md`. Backend: `3.1` (a pip log), `becquerel_test_output.txt`, `static/icons/upload_new.png.bakg`, `archive/`. Unused modules: `enhanced_analysis.py`, `radiacode_src.py` (a pasted library stub), `generate_testing_spectrum.py`, `verify_roi_api.py`. None are referenced by code. Deleting them was declined by the tool's permission check, so they are untouched. |
| Acquisition data not ignored | `backend/data/acquisitions/*.n42` is user data and shows as untracked. Add it to `.gitignore`. Also not done because of a permission denial. |
| `archive/` (8 MB) | Old scripts, legacy GUI, icon backups. Keep as history or remove; git history already holds it. |

## Found while refactoring

Fixed, each with tests in `tests/test_csv_columns.py` (they fail on the old parser):

- A one-column CSV was reported as calibrated with the counts used as the energy axis, and a headerless one lost its first value. Cause: pandas guessed the delimiter among all characters and split on a letter of the header. Detection is now limited to comma, semicolon, tab and space.
- A first line such as `Calibration: a0 a1` made the file fail to load (it was taken for the header). Calibration lines in the first 25 lines are now kept out of the table; the calibration is read from them as intended.

Still open:

- Becquerel cannot read `.csv` ("File type .csv can not be read"), so the pandas fallback is the only CSV parser that ever runs and the Becquerel branch in `_parse_csv_file` (and the `source` label "CSV File (Becquerel)") is dead code. Remove it, or restore a Becquerel read that works.
- `ml_data_loader.py` augments real spectra with unseeded `np.random` (`uniform`, `poisson`), so a model trained with `ML_USE_REAL_DATA=1` differs on every training; the default synthetic training is fully seeded and reproducible. Pass a `numpy.random.Generator` seeded like the synthesiser if reproducibility matters for that path.
- `tests/data/radiacode_fisicas/manual_primary_peaks.csv` is the only real CSV in the test data and it is a peak list, not a spectrum, so there is no real-spectrum CSV test.

## Open: structural

| Issue | Where | Notes |
|-------|-------|-------|
| Oversized functions | 23 functions over 100 lines, e.g. `ROIAnalyzer.analyze_uranium_ratio` (212) and `analyze` (165), `identify_decay_chains` (171), `source_identification.identify_source_type` (170) | Split the same way as `analyze_uranium_ratio`: capture output on a set of synthetic spectra first, refactor, require an identical result. |
| `setupEventListeners` in `main.js` | about 1,100 lines | One function wires nearly every control and shares module state; split by panel into modules that receive what they need. |
| `style.css` | 2,909 lines, plus `button-fixes.css` and `device_styles.css` overrides; 350 inline `style=` attributes in `index.html` | |
| Overlapping modules | `peak_detection` / `peak_detection_enhanced`; `source_analysis` / `source_identification`; `isotope_database` / `isotope_roi_database` / `nuclear_data` / `isotope_validation`; six parsers without a shared interface | The decay modules are deliberately layered (`decay_data` -> `bateman` -> `decay_calculator` -> `decay_engine`, with `curie_*` as an optional engine) and were rebuilt recently; leave them. |
| Flat `backend/` | about 50 modules; only the routers are a package | |
| Remaining silent handlers | `except Exception: pass` around close/disconnect calls in `radiacode_*`, `curie_compat` | These are cleanup paths where there is nothing to do; left as they are. |
| `innerHTML` | 68 uses; the untrusted-text sites are escaped, the rest build markup from numbers and constants | Prefer `textContent` / DOM construction for new code. |
| No authentication | The server binds `0.0.0.0:3200` for LAN access and exposes device control and file endpoints | Deliberate; document it, or add an opt-in token. |
| Remaining `console.log` filter | `log.js` hides diagnostics by default; nothing yet shows them in the UI | |
| `ml_analysis` | Module-level `_ml_identifiers` cache; the first AI request after a restart trains the model on a request thread | |

## Manual verification backlog

`TODO.md` still lists about 25 items that need a person or hardware (live Radiacode and AlphaHound readings, themes on
a phone, screen readers). That is verification debt, not code debt, and nothing in this pass touched those paths.

## Good practices

- No `import *`; type hints and Pydantic validation on the API; rate limiting; CORS off by default.
- 611 backend tests plus browser checks (smoke, accessibility, theme sweep, channel sweep).
- Real-spectrum benchmarks (`tests/real_benchmark.py`, `tests/ml_benchmark.py`) guard the analysis numbers.
