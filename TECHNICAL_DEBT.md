# Technical Debt Report

**Date:** 2026-10-03
**Branch:** `chore/technical-debt-cleanup`
**Tests at the time of writing:** 639 backend tests pass; the headless-browser smoke test (`backend/tests/ui_smoke.py`) passes 160/160.

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
| Temp-file leak | A CSV upload that was rejected left its temporary file in the temp directory (265 had piled up). The file is now removed on every path; `tests/test_csv_temp_cleanup.py` fails on the old code. |
| Repo layout | 19 unreferenced images and a scraped web page moved to `TO_BE_DELETED/` (`backend/static` 16 MB to 1.7 MB); the seven guides and notes that sat in the root moved to `docs/` with every link fixed (root: 22 to 15 tracked files); `tests/test_repo_layout.py` fails if new root files, backup/temp files, files over 800 KB, unreferenced images or broken document links appear (each rule verified to fire on a real offender). |
| Fixtures and user data | The real spectra the tests use moved from `backend/data/acquisitions/` to `backend/tests/data/real_spectra/`; `acquisitions/` (the user's own measurements, 70 files on disk) is ignored and untracked (the files stay on disk); a layout rule fails if any of it is tracked again. `spectrum_wrapper.py` (457 lines, imported by nothing) went to `TO_BE_DELETED/`; `generate_test_spectra.py` is in `tools/`. |
| Test layout | `test_fitting_engine.py` and `test_multiplet_fitting.py` were outside `tests/` and never ran; they are in `tests/` now. The print-driven `test_becquerel_comparison.py` is `tools/becquerel_comparison.py`. |
| Install files | `requirements_lightweight.txt` was missing `slowapi` (imported by `main.py`) and listed an unused `pillow`; `install_lightweight.bat` now installs from that file. The app imports cleanly with the optional packages absent. |

## Open: needs a decision

| Item | Detail |
|------|--------|
| Dead files | Moved to `TO_BE_DELETED/` (see its README) because the tool could not delete them: root backups and run output, four unused modules, the old `backend/archive/` and the former `archive/` (42 PyRIID-era debug scripts, icon backups, printed results). Nothing references them. Delete with `git rm -r TO_BE_DELETED`. |
| Kept from the old `archive/` | `legacy/AlphaHound-main/` (upstream GUI, MIT licence), `docs/alphahound_probes/` (raw device captures), `docs/abundance_weighting_research.md`, and two real CSV spectra in `backend/tests/data/real_csv/` with `tests/test_real_csv.py`. |

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
| Oversized functions | 20 functions over 100 lines, e.g. `ROIAnalyzer.analyze_uranium_ratio` (212) and `analyze` (165), `parse_n42` (166), `generate_pdf_report` (151), `upload_file` (145) | Split the same way as `analyze_uranium_ratio`: capture output on a set of synthetic spectra first, refactor, require an identical result. |
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
