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
| `setupEventListeners` (1,116 lines) | Split into 11 named functions along its section comments (`setupFileUpload`, `setupRadiacodeConnection`, `setupExports`, `setupSettingsAndHistory`, `setupDeviceControls`, `setupAnalysisPanels`, ...), called in the original order, every line moved unchanged; a scope check found no variable shared between sections. ESLint's `no-undef` gives the same result before and after the split, and the browser suite (162 checks, both sweeps, accessibility) passes. The file is still one module of about 3,300 lines: moving the sections into their own modules is the next step. |
| Frontend scope bug found by that check | `const originalHtml` was declared inside a `try` and read in its `catch` (Edit N42 Metadata): when the template request failed, the handler threw a ReferenceError and the button stayed disabled and dimmed on "Generating...". Fixed; smoke checks T1 and T2 fail without the fix (button stuck, `originalHtml is not defined`). CI now runs ESLint's `no-undef` over `backend/static/js` (all 25 modules clean), which catches this class without running the page. |
| CI | `.github/workflows/tests.yml` runs the backend suite and the frontend scope check on every push to `main` and every pull request (windows-latest, Python 3.12). Rehearsed in a clean clone with a fresh virtualenv built from `backend/requirements.txt`: 645 passed. |
| `.gitattributes` | LF in the repository, CRLF for batch files, binaries untouched (every tracked text file was already LF, so nothing was rewritten). |
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
| Overlapping modules | in `spectroscopy/`: `peak_detection` / `peak_detection_enhanced`, `source_analysis` / `source_identification`; in `nuclides/`: `isotope_database` / `isotope_roi_database` (in `spectroscopy/`) / `nuclear_data` / `isotope_validation`; in `formats/`: six parsers without a shared interface | The packages group them; merging each pair is a separate change with its own before/after check. The decay modules are deliberately layered (`decay_data` -> `bateman` -> `decay_calculator` -> `decay_engine`, with `curie_*` as an optional engine). |
| Remaining silent handlers | `except Exception: pass` around close/disconnect calls in `radiacode_*`, `curie_compat` | These are cleanup paths where there is nothing to do; left as they are. |
| Spurious peaks in the peak list | Noise spikes are reported next to real peaks (the synthetic Cs-137 file lists 1107 and 1890 keV, 11 and 5 net counts; its 471 keV entry is the Compton edge, a real feature that is not a gamma line). **Measured 2026-10-03 on 17 calibrated spectra (real and synthetic, 108 peaks), and deliberately not changed:** (1) fitted width against the detector's physical resolution does not discriminate: the median fitted width is 0.33 of the database FWHM and strong real peaks sit far below any cut (7,737 counts at 518 keV, ratio 0.15); (2) significance (net area / uncertainty) does not either: 3 of the 13 generator peaks have z 1.1 to 2.3, below spurious spikes, while non-line features reach z 9.5 and 43. Any cut that removes the spikes also removes real weak peaks, and there is no labelled ground truth for weak peaks to judge the trade. A start would be labelled weak-peak data, then a rule scored on it; a separate Compton-edge flag (position follows from the photopeak) would handle the 471 keV case. | |
| `innerHTML` | 68 uses; the untrusted-text sites are escaped, the rest build markup from numbers and constants | Prefer `textContent` / DOM construction for new code. |
| No authentication | The server binds `0.0.0.0:3200` for LAN access and exposes device control and file endpoints | Deliberate; document it, or add an opt-in token. |
| Remaining `console.log` filter | `log.js` hides diagnostics by default; nothing yet shows them in the UI | |
| `ml_analysis` | Module-level `_ml_identifiers` cache; the first AI request after a restart trains the model on a request thread | |

## Documentation

`CHANGELOG.md` (about 800 lines) is history and is left as written; `TODO.md` mixes open items with long completed sections (its handoff notes were refreshed on 2026-10-03). A shorter, open-items-only `TODO.md` with the completed work moved into the CHANGELOG would be easier to keep current.

## Manual verification backlog

`TODO.md` still lists about 25 items that need a person or hardware (live Radiacode and AlphaHound readings, themes on
a phone, screen readers). That is verification debt, not code debt, and nothing in this pass touched those paths.

## Good practices

- No `import *`; type hints and Pydantic validation on the API; rate limiting; CORS off by default.
- 641 backend tests plus browser checks (smoke, accessibility, theme sweep, channel sweep).
- Real-spectrum benchmarks (`tests/real_benchmark.py`, `tests/ml_benchmark.py`) guard the analysis numbers.
