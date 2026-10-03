# CHANGELOG

## [Session 2026-10-03 evening] - Technical debt and repository sprawl

### Changed - layout
- **Backend modules are in packages.** `formats/`, `spectroscopy/`, `nuclides/`, `devices/`, `ml/`; `backend/` keeps `main.py` and `core.py`. Imports read `from spectroscopy.roi_analysis import ...`. Output of every analysis path is unchanged (8 snapshots, byte for byte); tests, tools and the guides' code samples use the new paths.
- **Test fixtures and user data are separate.** The real spectra the tests use are in `backend/tests/data/real_spectra/` (and two real CSVs in `real_csv/`); `backend/data/acquisitions/`, where the app saves the user's own measurements, is ignored and no longer tracked.
- **Root cleaned up.** The seven guides and notes moved to `docs/` (links fixed), 19 unreferenced images (15 MB) and dead files moved to `TO_BE_DELETED/` (delete with `git rm -r TO_BE_DELETED`); the upstream GUI is kept in `legacy/` for its licence.
- `tests/test_repo_layout.py` fails on new root files, backup/temp files, tracked files over 800 KB, unreferenced images, broken document links, tracked user acquisitions and loose backend modules.

### Fixed
- CSV: a one-column file read as calibrated with the counts on the energy axis; a headerless one lost its first value; a `Calibration:` first line made the file fail to load; a rejected upload left a temporary file behind.
- A scipy divide-by-zero warning on sparse spectra (CWT peak detection), without changing any peak.
- Untrusted text (Bluetooth device names, server errors, custom isotope names) is HTML-escaped before it reaches `innerHTML`.

### Refactored (outputs proved identical against snapshots taken first)
`analyze_uranium_ratio`, `ROIAnalyzer.analyze`, `identify_isotopes`, `identify_decay_chains`, `identify_source_type`, `analyze_spectrum_peaks`, `parse_csv_spectrum` and `MLIdentifier.lazy_train` were split into small functions; `main.js` lost its toast and decay-tool code to `toast.js` and `decay_tool.js`.

### Note
The browser smoke test's peak-count checks pinned 6 peaks for a synthetic Cs-137 file whose extra peaks are noise; the count changed to 5 in the ROI review commit. The checks now compare the summary card with the table instead of a fixed number.

## [Session 2026-10-03 PM] - ROI and decay-chain review, library audit

Everything below was measured before it was changed: synthetic spectra with known peak areas and activities on every detector profile (AlphaHound CsI(Tl) and BGO, Radiacode 103 / 103G / 110), Monte Carlo runs for bias and pull, and probes on the labelled real spectra of both device families (`tests/real_benchmark.py` cases). 607 backend tests pass on the installed libraries and on the newest releases of every dependency; the headless-browser smoke test passes 160/160.

### Fixed - ROI (`roi_analysis.py`)
- **The background estimate was wrong on a sloping continuum.** A band was dropped whenever the database listed a *possible* neighbouring line near it, even if that line was not in the spectrum, and one band can only assume a flat continuum: errors of +-30 to 50 % (BGO Cs-137 +42 %, Co-60 1173 keV -45 %). The estimator is now: two background bands clear of neighbours (window integration), otherwise a Gaussian fit with a linear baseline (neighbouring lines get amplitudes of their own, the peak's own amplitude may be negative so an empty region gives a net near zero with an honest uncertainty, the width is held at the detector's expected value unless the peak is clear at 4 sigma), and only if that fails a relaxed two-band window, then one band. Monte Carlo pull width is ~1.0; the remaining 1-4 % low bias (up to ~8 % for BGO at 1 MeV) is the linear baseline on a very convex continuum, and a parabolic baseline was measured and rejected (it doubles the scatter).
- **A false detection on a real source**: the real Am-241 spectrum (Radiacode 103) gave "Th-234 93 keV detected, 14,402 net counts". The fit is no longer rejected for strong, non-Gaussian peaks (its uncertainty is scaled by sqrt(chi2/dof) instead), and a single-band window carries a systematic uncertainty taken from the density on the rejected side, so a shoulder reads "not measurable" (14,402 +- 317,318).
- **Activity overstated by lines of the same nuclide blended into the peak.** Ac-228 911 keV read 59.6 Bq for a true 40 Bq (+49 %) because the 965 and 969 keV lines of the same nuclide fall inside the peak at scintillator resolution. The activity now uses an effective emission probability that adds the same-nuclide lines closer than 0.9 FWHM, weighted by the detector's relative efficiency (`companion_lines` in `isotope_roi_database.py`: Ac-228 911, U-235 186, Bi-214 609, Pb-214 352). The result carries `effective_branching_ratio` and says which lines were counted.
- **Channel width at the peak, not the median of the spectrum**: a Radiacode spectrum has a quadratic energy axis (2.7 keV per channel at 100 keV, 3.4 at 2.6 MeV), so the net area from a fit was off by up to 25 % away from the middle.
- **Fractional counts were truncated** by the API (`int(c)`), which turned a background-subtracted spectrum of 0.4 counts per channel into zeros. The four ROI / uranium / source-identification routes now pass floats.
- **Uranium ratio**: the Ra-226 share of the 186 keV peak was computed and then never used, so "uranium glass" gave the same ratio as "auto"; it is now subtracted, with the Bi-214 counting error and a 25 % model allowance in the uncertainty. A "uranium glass" run without a Bi-214 peak crashed (`None.net_counts`); peaks are "present" only when significant (SNR >= 2) and above 30 counts, not on a bare count threshold. The ratio-only button also never sent the source type.
- **Fit areas were counts x keV per channel.** `fitting_engine.py`, `multiplet_fitting.py`, `peak_detection_enhanced.py` and `spectral_analysis.py` computed a Gaussian's area as A*sigma*sqrt(2 pi) with sigma in keV and A in counts per channel, overstating every fitted net area (and its uncertainty) by the channel width (2-3x). `gauss_area.py` holds the conversion; baseline areas are sums over channels instead of `np.trapz` (removed in newer numpy).
- **ROI panel**: shows the detection status, the background method and a plain-text list of limitations (blended or unresolved neighbouring lines, how the background was found); the detector preselects from the loaded file (`detector_profile`: AlphaHound CsI / BGO, Radiacode 103 / 103G / 110) instead of always offering the AlphaHound.

### Fixed - decay chains (`chain_detection_enhanced.py`)
- **Branches were drawn as a sequence**: Po-212 appeared to decay into Tl-208. `get_chain_sequence_info` now records the feeder of every member (`feeder`, `branching_from_feeder`, `is_branch`, and `branching_to_next` = None between siblings); the diagram shows Bi-212 -> Po-212 (64.1 %) "or" Tl-208 (35.9 %) (`chainLink` in `summary.js`).
- **The secular-equilibrium check could never run**: it read peak counts that were never supplied, so it always answered "insufficient peak counts". The peak list is not good enough to measure it (the Bi-214 609 keV peak area was 14.7k against 36.7k from the ROI fit on the same spectrum, and the 60 keV matching tolerance paired the Fiestaware 184 keV peak with Pb-214's 242 keV line, which gave false "disequilibrium"). It now measures Bi-214/Pb-214 (U-238) and Ac-228/Tl-208 (Th-232) with the ROI engine on the spectrum and answers consistent (within x2.5), clearly not (beyond x6, also when one member is absent at its detection limit), or unknown. Validated on synthetic series at known activities for both device families.
- Each gamma line takes the closest peak within the tolerance instead of the first in list order; `get_chain_summary` read keys that do not exist; `print` debug output became logging; bare `except` blocks now log.

### Fixed - libraries and dependencies
- **`backend/requirements.txt` (used by `install_deps.bat`) lacked bleak, curie, radioactivedecay and SandiaSpecUtils**: a fresh install silently lost Bluetooth and fell back to reduced decay data. It is now complete, with lower bounds at the versions tested, the root `requirements.txt` includes it, and `backend/requirements-dev.txt` lists the test dependencies.
- **Bluetooth scan**: it read `BLEDevice.rssi` and `BLEDevice.metadata`, which bleak removed, so signal strength was always empty and the search by Radiacode service UUID never matched (already broken on bleak 2.0). It uses `discover(return_adv=True)` and the advertisement data now (`tests/test_radiacode_ble_scan.py`, run against bleak's own data classes).
- **NaN peak uncertainty**: `sqrt(gross + baseline)` with a baseline that dips below zero (seen on the Fiestaware spectrum) gave NaN, which is not valid JSON; both terms are clamped.
- FastAPI: startup uses a lifespan (`on_event` is deprecated); Pydantic: `.dict()` became `.model_dump()` (removed in V3). Two unclosed file handles closed.
- Audit of the newest releases (numpy 2.5.3, scipy 1.18, pandas 3.0, starlette 1.7, fastapi 0.142, reportlab 5.0, bleak 3.0, curie 0.3.1, scikit-learn 1.9): nothing else needed changing. curie 0.3 carries a newer ENSDF evaluation in which Th-234 also feeds the Pa-234 ground state directly (0.68 %), so its Pa-234/Pa-234m ratio is 0.0085 instead of 0.0016; that is a data difference, documented in `test_decay_engine.py`. A timing race in `test_alphahound_driver.py` (it asserted the spectrum right after the temperature arrived) was fixed.

### Added
- Tests: `test_roi_analysis.py` (87: accuracy on every ROI line for five detector profiles, resolvable pairs, a quadratic axis, 7.4 keV per channel, no-peak and flat spectra, ROI outside the spectrum, activity arithmetic, the uranium ratio, the API), `test_decay_chains.py` (branching, matching, equilibrium verdicts on synthetic series, identification end to end, real uploads), `test_radiacode_ble_scan.py`, `test_startup.py`, a `chainLink` test in `test_summary_js.py`, and the shared generator `tests/spectrum_synth.py`.

### Known limits
- Lines of a *different* nuclide inside the window (Cs-137 beside Bi-214 609 keV, Ac-228 338 keV on Pb-214 352 keV) cannot be separated at these resolutions; the ROI result warns, but still reports a detection.
- The equilibrium check compares two radon daughters (U-238) or Ac-228 and Tl-208 (Th-232), with generic efficiencies; it cannot say anything about Ra-226 against U-238.
- Radiacode alarm limits are still read-only (`set_alarm_limits` is not exposed).

## [Session 2026-10-03] - Themed charts, channel panel, short-window layout

### Added
- **Radiation channels panel** (`static/js/channels.js`): one card per channel with the live rate, a log-scale meter with a peak-hold marker, the 1-minute average and the peak; a share-of-counts bar; a history chart with 1 / 5 / 30 minute windows, a linear or log axis, and a CPS / CPM toggle (the choice is remembered, and the replica follows the unit). It replaces three mini-charts that copied the manufacturer's viewer.
- **Themes now change how charts are drawn, not only their colours.** Each theme sets chart-character tokens (`--ch-font`, `--ch-radius`, `--ch-line-w`, `--ch-glow`, `--ch-tension`, `--ch-step`, `--ch-grid-dash`, `--ch-meter-mask`, `--ch-reading-glow` in `style.css`) which `chart_theme.js` reads: the oscilloscope theme draws a thin glowing trace over a dotted graticule with a segmented LED meter in a monospaced font, the Nixie theme draws thick warm lines with a strong glow and rounded tubes, the civil-defence theme draws a blocky stepped histogram, the instrument themes (Tektronix, Keithley, Fluke, ...) are crisp and monospaced, and the light theme never glows. The spectrum, comparison and dose sparkline charts use the same tokens (grid colour and dash, tick fonts, tooltips, line weight, glow), and all of them refresh when the theme is switched.
- **Channel colours come from the theme** (`palette.js`): gamma = the theme's primary colour, beta = secondary, alpha = accent; when a single-hue theme gives colours that are too alike (oscilloscope: all greens, Nixie: all oranges) they are moved apart by the smallest change in lightness, saturation and hue that makes them distinguishable and keeps at least 3:1 contrast on the theme's background. A theme that already has three colours (cyberpunk) is left untouched. Each channel also has its own line pattern (solid, dashed, dotted), so nothing relies on colour alone.
- **Replica colours** option: a tint of the active theme (default) or the hardware's own white-blue.
- `tests/ui_channels_sweep.py` (every theme at desktop and phone width: the chart really uses each theme's tokens, colours are distinct and readable, no overflow or JS errors) and `tests/ah_mock.py` (a mocked AlphaHound for browser tests); `tests/test_theme_js.py` (palette, chart theme and channel logic under Node, plus a check of all 17 theme blocks in `style.css`).

- **Result summary above the chart** (`static/js/summary.js`): the most likely isotope with its confidence, the other candidates, peak count, total counts, mean rate and collection time, plus a data-quality flag and the AI second opinion (agrees / partly agrees / differs from line matching). The answer used to sit about 1,500 px down the page.
- **Peaks table** now shows FWHM and the isotope each peak was matched to; rows are buttons (mouse or keyboard) that mark the peak on the chart.

- **Dose unit preference** (Settings): each device's own unit (the default, as before), or µSv/h or µRem/h everywhere: the live readout, the AlphaHound details, accumulated and session doses. Values scale to nSv / µSv / mSv (µRem / mRem) as they grow, so 2500 µRem/h reads "2.50 mRem/h" (`static/js/units.js`).
- **Configurable alerts** (Settings, `static/js/alerts.js`): a dose-rate limit and an AlphaHound total count-rate limit, a beep and a desktop notification (page in the background), a Dismiss button, and a Test button. Both devices feed the same monitor (before, only the AlphaHound did, with a fixed 2000 µRem/h limit; that is still the default: 20 µSv/h). An alert starts after two readings above the limit (or one above twice the limit) and ends below 80 % of it, so a value at the threshold does not flicker; the banner shows the dose in the chosen unit and the distance at which a point source would fall back to the limit.
- **Accessibility** (`static/js/a11y.js`, audited by `tests/ui_a11y_audit.py`): every dialog is a labelled `aria-modal` dialog that takes focus when opened, keeps Tab inside, closes on Esc and returns focus; a skip link; all controls have names; decorative icons have empty alt text; canvases are described (the spectrum chart gets a sentence with its peaks); a visible focus ring everywhere; animations stop with "reduce motion".

### Changed
- **Peaks and identification sit side by side** on wide screens and stack below 900 px. "Legacy" is now "IAEA / NNDC lines", "WIP" is "Experimental", and the tip box became a caption.
- **Short desktop windows** (a laptop at 1280x800 or 1366x768): the page header and top margin shrink and the history chart scales with the window height, so the whole device area fits without scrolling.
- The AlphaHound dose readout formats follow the device (whole uRem/h, two-decimal uSv); the JS test helpers decode Node's output as UTF-8.

### Decay calculation engines (reviewed and rebuilt)
Findings of the review, all confirmed by measurement before changing anything:
- **The default engine drew wrong curves over long durations.** radioactivedecay's series dropped a nuclide at every time point where it was under 0.1 % of the starting activity and padded the gaps at the front, so the curve shifted: Cs-137 over 301 years started at 0 and ended at 2.1 Bq instead of 1000 to 1; Mo-99 over 30 days and I-131 over 200 days were wrong the same way. Every series now has every point; negligible nuclides are left out whole and listed.
- **"Curie" and "PyNE" were not engines.** Both ran the built-in solver and Curie stamped its name on the result. PyNE is gone (it was never installed, and cannot be installed on Windows without a compiler). **Curie is now real**: ENSDF half-lives and branching fractions read from Curie's database and solved with the shared solver. radioactivedecay (ICRP-107) stays the default.
- **The built-in solver treated most isotopes as stable.** It knew 15 isotopes, so Co-60, Sr-90 and Am-241 were drawn as a flat line, only U-238 and Th-232 had daughters, and branching was ignored (Tl-208 came out 2.8 times too high). It is now a general Bateman solver with branching (80-digit decimal arithmetic, so a chain with 23 orders of magnitude between its half-lives keeps full precision) over 161 nuclides from 57 parents, generated from ICRP-107 by `backend/tools/generate_decay_table.py` into `decay_data.py`. The three engines agree to 5-6 digits on U-238 (all 15 nuclides including the Pa-234 and Po-214 branches), Th-232, Cs-137, Sr-90, Co-60, Am-241 and Ra-226; the differences between ICRP-107 and ENSDF data (up to about 1 %) are the only ones left. A parent the built-in table lacks is refused with a message instead of a flat line.
- **Curie failed on random threads.** It opens its SQLite connection in the first thread that asks and sqlite3 refuses use from another thread, but the web server answers from a pool of threads: the next request often failed ("SQLite objects created in a thread can only be used in that same thread"). `curie_compat.py` opens the connections for any thread and serializes the lookups. The existing Curie X-ray / gamma-line integration (`curie_integration.py`) had the same bug and swallowed it: gamma lines from Curie quietly came back empty on some threads.
- **Half-life lookups of radioactivedecay and Curie always returned nothing** (calls to `rd.Nuclides` and `curie.Decay`, which do not exist, and Curie's half_life method used as a number, hidden by bare excepts).
- **The API accepted anything.** Unknown isotope: 200 with a flat line; negative duration: 200 with the activity growing; zero activity: empty result; huge duration: a crash with a non-JSON 500. All of these are 400 with a message now; `/analyze/isotope-info` (which always answered 500: it imported functions that did not exist) works and returns half-life, daughters with branching, decay modes and the chain.
- **Decay Prediction window**: type any isotope ("cs137", "Tc99m", "137Cs" all work; 57 are offered in the list), choose seconds to years, see which engine and data produced the curves and what was left out, an engine that is unavailable is replaced with a visible note; the chart follows the theme (line weight, glow, grid, font), zeros are gaps on the log axis, lines differ by pattern as well as colour, and the time axis uses the duration's own unit.
- Tests: 140 for the engines (textbook formula, equal half-lives, branching and rejoining branches against an independent numerical integration, every engine over 15 cases including the 301-year Cs-137 regression, cross-engine agreement, Curie from worker threads, input validation, the API) plus Node tests for the window's helpers and the many-series palette.

### Fixed
- **The zoom bar and the chart disagreed.** The sliders and the chart work in energy, but the mini preview was drawn by channel number, so with a real (non-linear) calibration every peak sat in the wrong place on the bar (the 236 keV peak of a Radiacode spectrum at 9.4 % of the bar instead of 8.4 %, growing towards high energies): handles set "on the peaks" selected a different window than the chart showed. The preview is now drawn in energy, keeping the tallest channel per pixel so narrow peaks survive. Also: the handle centres, the blue selection box and the chart range now coincide (the handles' travel is half a handle shorter than the bar, and range inputs carry a 2 px default margin); dragging a handle past the other no longer moves the chart to the unclamped position first; and a window you chose with the zoom bar, the mouse wheel or panning now survives live-acquisition updates instead of snapping back to the auto range every refresh. Reset Zoom, the Auto-Scale button and loading a new spectrum still start from the auto view.
- **Metadata cards read like raw keys** ("MEAN DOSE RATE USV H", "EXPOSURE COVERED S", "0.123456", "271.456789"; the capitals CSS also turns a unit into nonsense, µSv/h into ΜSV/H). Labels are now words, units sit in the values, numbers are rounded, the six cards about one dose figure are one "Dose this acquisition" card (mean and max rate as rows), the three channel count rates plus the peak are one card, and the dose follows the unit preference. A source that only repeated manufacturer + model and a serial number of "UNKNOWN" are no longer shown, an AlphaHound's manufacturer is RadView Detection instead of "Unknown", and card text is set as text (a file's metadata can no longer inject HTML). Fifteen cards became seven for a live AlphaHound capture (`static/js/metadata_cards.js`).
- **No internet, no charts.** The charting libraries came from CDNs, so on an offline machine or a LAN client without internet the spectrum never drew. Chart.js 4.5.1, the zoom and annotation plugins and Hammer.js are now served from `static/vendor/` (versions in its README); the Inter font loads without blocking the page and falls back to the system font.
- **PDF export** opened a new tab with `window.open()` after waiting for the server (blocked as a pop-up by many browsers, and the URL was revoked after one second); it now downloads `<name>_report.pdf`.
- **Unreadable uploads** are client errors: a CSV with text where counts belong used to come back as a "spectrum" of strings (HTTP 200), and an unparseable `.txt` / CHN / SPE file answered 500. Both answer 400 with a message that names the problem, and the drop zone shows it.
- **The MDA calculator used a native `prompt()`** (the last one in the app) for the isotope energy and silently did nothing when prompts are blocked; it has an Isotope Energy field now, and its errors are toasts instead of replacing the upload drop zone.
- **Radiacode alarm limits** (`GET /radiacode/alarm-limits`, previously without any UI): the device's own level 1 / level 2 thresholds are shown read-only in Advanced Diagnostics.
- **AI Identify sent two requests per click** from the isotopes box (a forwarded click also triggered the analysis-panel handler, which overwrote the peak-fit results). All AI buttons share one request path now.
- **A stale AI answer stayed on screen after loading another spectrum**; it is cleared for a new spectrum and marked outdated while a live acquisition keeps growing.

## [Session 2026-10-02 PM] - AlphaHound modernization: CPS channels, display replica, remote control

### Added
- **Gamma / beta / alpha count rates** from the device's `P` command (the manufacturer's AlphaView page uses it): `GET /device/cps`, `cps` in `/device/status` and the dose WebSocket, shown in a new AlphaHound details panel.
- **Display replica**: the AB+G's 128x128 OLED redrawn in the browser, with its modes (1-7, 9-12) built from the data the serial link carries. Modes 5-7 say what they would need. See `docs/ALPHAHOUND_SERIAL.md`.
- **AlphaHound details panel**: port, temperature, compensation factor, dose (uRem/h and uSv/h), CPS per channel, dose-log size, spectrum auto-refresh, a read-only command probe (`POST /device/probe`).
- **Dose log**: one averaged row per second with the gamma/beta/alpha CPS, `GET /device/dose/log(.csv)`, clear with `POST /device/dose/log/clear`, buttons in the panel.
- **Disconnect button for the AlphaHound** (the only Disconnect button lived in the hidden Radiacode row), and the page notices a connection that disappears (three "not connected" answers).
- **`backend/tools/devctl.py`**: connect / disconnect / restart / ensure / probe from the command line, for unattended work. Server opt-ins `ALPHAHOUND_AUTOCONNECT_PORT` and `ALPHAHOUND_KEEP_CONNECTED`.
- Port errors are readable (409 "in use by another program") instead of a bare 500.

- **Radiation channels panel** for gamma, beta and alpha in the details panel (our own, themed presentation, see the next section), and a 5 s **smoothed dose** next to the raw reading (`dose_rate_avg` in `/device/status`, `/device/details` and the WebSocket).
- **Dose log survives restarts**: kept in `backend/data/dose_log.jsonl` (loaded at startup, trimmed when it grows far past 100 000 rows; `ALPHAHOUND_DOSE_LOG=off` keeps it in memory only).
- **Channel statistics per acquisition**: mean gamma / beta / alpha CPS and peak total CPS are recorded during an AlphaHound acquisition, shown in the metadata panel, returned in `/device/acquisition/status` (`channels`) and written to the N42 `AcquisitionInfo`.

- **Self-healing connection** (opt-in, on by default for `devctl`-started servers): a watchdog reconnects the AlphaHound after a USB drop or a silent device; a deliberate Disconnect is respected. `GET /device/health`.
- **Display replica follows the device's real behaviour**: four configurable mode slots (E/Q step through them), the guide's mode set (Rolling = alpha + beta, ABY AVG, LP Spark, Sleep digits, G-Force), the check/X rule. Tested: the device reports nothing when its mode changes, so the slots must be set once by hand.
- **Display quality and layout**: the replica renders at 4x with an OLED pixel grid, a bezel and device-style buttons; the empty connection box is hidden while connected (Disconnect and a port chip move into the title row); the readings are two columns; the whole device area fits a 1280x800 window.

### Fixed
- **Real-time dose spikes**: the device streams its own dose value (~5 per second) and answers `D`/`DA`/`DB` and `P` with values ~10x larger (nSv/h scale). The driver treated every bare number as the dose, so each `DB` reply briefly put a 10x spike in the readout. `DB` is now only a fallback for firmware without the stream.
- **Dead dose sparkline for the AlphaHound** (the chart was created without a canvas).
- **Spectrum request that is never answered** stalled all polling for good; it now times out after 10 s.
- Temperature and compensation factor are fetched once after connecting (the device only reports them with a spectrum).

## [Session 2026-10-02] - PyRIID removal, ML rework, N42 acquisition info, Radiacode fixes

### Changed
- **PyRIID removed**: its numpy 1.26 / scipy 1.13 / TensorFlow 2.16 pins conflict with this app. `ml_analysis.py` now uses a scikit-learn MLP; `riid` and `tensorflow` dropped from requirements. Old guides moved to `archive/planning_docs/`; see `ML_GUIDE.md`.
- **ML training rework**: one calibration error per training spectrum (was per line), physics-based synthesiser, natural series trained as mixtures, spectra resampled onto the model energy grid from the device calibration, classes named for what a spectrum shows (`Th-232 series`, ...). Real-spectra scorecard: `backend/tests/ml_benchmark.py`.
- **Isotope cap applied after the spectrum fit**: false U-238 daughters no longer push real Pb-212 / Tl-208 out of the list.

### Added
- **N42 acquisition info**: exposure, device duration and time notes are written to `<SpectrumExtension><AcquisitionInfo>` and read back by the parser.
- **Radiacode**: UI state restored after page refresh; device alarm events logged (`GET /radiacode/events`) and toasted; alarm limits (`GET /radiacode/alarm-limits`, read register by register because the batch read fails over BLE); total dose shown next to the live dose rate; connect step timings logged.

### Fixed
- Radiacode connect button read "Connected" after Disconnect; a lost connection was never noticed.
- `DS_uR` warning logged once per connection instead of every poll.
- `ui_smoke.py` no longer depends on a real Radiacode being (dis)connected on the server.

## [Session 2026-08-31] - Radiacode BLE Scan Fix (Windows)

### Fixed
- **Windows BLE Scan/Connect Silently Failing**: `pyserial`'s Windows USB-detection backend imports `pythoncom`/`win32com`, which puts the process in STA COM mode. Bleak's WinRT backend refuses to run BLE callbacks on an STA thread unless explicitly allowed, so `radiacode_bleak_transport.py`'s scan returned `[]` and connect attempts raised `Device ... was not found` even with a Radiacode device in range. Fixed by calling `bleak.backends.winrt.util.allow_sta()` at import time (Windows only).
- **Broken Test Imports**: `backend/tests/test_analysis.py`, `test_isotope.py`, and `test_parsers.py` imported modules as `backend.<module>` instead of `<module>`, breaking the test suite when run from `backend/`. Fixed imports so the 20-test suite runs and passes.

### Documentation
- Documented the Curie nuclear-database zero-size DB issue and manual-download workaround in `README.md` and `INSTALL.md`.
- Documented the Windows BLE/pywin32 STA conflict and its fix in `README.md`.

---

## [Session 2026-01-04] - Theme Color System Overhaul

### Added
- **Complete Theme CSS Reference**: Created `complete_themes_css.md` with 35 proposed new themes:
  - 8 Sci-Fi themes (Alien Isolation, Pip-Boy, Blade Runner, Tron, Matrix, LCARS, Halo UNSC, Stranger Things)
  - 7 Vintage Test Equipment themes (Beckman, General Radio, Heathkit, Simpson, Lambda, Boonton, Wavetek)
  - 8 Vintage Computing themes (Apple II, C64, IBM 5150, Amiga, VT-100, BBC Micro, Atari ST, ZX Spectrum)
  - 6 Vintage Radiological themes (Canberra Packard, Bicron, TASC, Nuclear Data, Radiation Alert, Radon Scout)
  - 6 Vacuum Tube Display themes (Magic Eye, Dekatron, Numitron, VFD, Cold Cathode, Panaplex)

- **Theme-Responsive Chart Colors**: Main spectrum chart and zoom scrubber now dynamically update when theme changes
  - Added `hexToRgba()` helper method for proper color conversion with transparency
  - Chart line color, fill color, and scrubber mini-preview all use `--primary-color` CSS variable
  - `updateThemeColors()` method refreshes all chart colors on theme switch

- **Status/Confidence Color Variables**: Added theme-specific overrides for 5 vintage equipment themes:
  - Ludlum: Warm tan/orange earth tones (`#d4915c`, `#b87a4a`)
  - Eberline: Vintage orange/gold (`#e07b39`, `#c9a227`)
  - Fluke: Professional yellow/orange (`#ffc107`, `#ff9800`)
  - Keithley: Cool professional blue (`#4a90d9`, `#7eb8f0`)
  - Tektronix: Blue/cyan instrument tones (`#00a2e8`, `#66ccff`)

### Changed
- **`charts.js`**: 
  - Added `hexToRgba()` method for converting hex colors to rgba with opacity
  - `render()` now re-reads `--primary-color` from CSS at render time
  - `updateThemeColors()` now refreshes both main chart and zoom scrubber mini-preview
  - Chart dataset backgroundColor uses `hexToRgba(primaryColor, 0.1)` instead of invalid hex concatenation

- **`main.js`**:
  - Theme change handler now calls `chartManager.updateThemeColors()` before re-rendering
  - Bumped charts.js import version to 4.5 for cache busting

- **`style.css`**:
  - Fixed zoom scrubber selection overlay to use `color-mix(in srgb, var(--primary-color) 25%, transparent)`
  - Added `--status-detected`, `--status-stable`, `--confidence-high/medium/low`, `--xrf-high/medium/low` variables to 5 vintage themes

### Fixed
- **Chart Color Stuck on Initial Theme**: Charts now properly update colors when switching themes without page reload
- **Zoom Scrubber Color Mismatch**: Mini-preview now redraws with correct theme color on theme change
- **Green Confidence Bars in Vintage Themes**: Added theme-appropriate color overrides preventing fallback to green defaults

---

## [Session 2025-12-22] - ML Isotope Identification Improvements

### Added
- **Real Data Augmentation**: New `ml_data_loader.py` loads N42/SPE/CSV spectra with auto-labeling (220 augmented training samples from local data)
- **Environmental Background**: Training now includes K-40, Bi-214, Tl-208 environmental peaks to teach model background immunity
- **Calibration Jitter**: ±10% gain and ±5keV offset variation during training for detector drift robustness
- **Multi-Detector Profiles**: 8 detector configurations (AlphaHound CsI/BGO, Radiacode 103/103G/110/102, Generic NaI)
- **Hybrid Scoring**: New `hybrid_identify()` function combines ML (40%) + peak-matching (60%) for improved accuracy
- **`get_available_detectors()`** API function for UI detector selection

### Changed
- Training epochs increased from 25 to 50 for better convergence
- MLIdentifier constructor now accepts `detector` parameter
- Model cache now keyed by both model_type and detector

---

## [Session 2025-12-22] - Documentation Overhaul & Chart Fixes

### Changed
- **README.md Major Overhaul**: Comprehensive update reflecting all recent features:
  - Added Radiacode 103/103G/110 device integration section with device comparison table
  - Added XRF element identification feature
  - Added SNIP background filtering description
  - Added spectrum algebra features
  - Documented server-managed acquisitions with crash recovery
  - Updated project structure with new backend files
  - Added bleak dependency for cross-platform BLE
  - Updated credits with radiacode SDK attribution

- **RADIACODE_INTEGRATION_PLAN.md**: Updated completion status:
  - Marked all success criteria as completed
  - Updated platform support table showing cross-platform BLE via bleak

- **TODO.md**: Updated task tracking:
  - Added "Replace Remaining Emoji with SVG Icons" task (~40 instances)
  - Added "Chart Autoscale & Label Stacking" as completed
  - Added "Documentation Overhaul" as completed

### Fixed
- **Chart Autoscale**: Spectrum chart autoscale toggle now correctly switches between peak-focused zoom and full spectrum view
- **Annotation Label Stacking**: XRF and isotope peak labels now stack vertically to prevent overlapping

---

## [Released - Session 2025-12-16] - Decay Prediction & Universal File Support

### Added
- **Decay Prediction System (Hybrid Engine)**
  - **Interactive UI**: "⏳ Decay Prediction" tool in Analysis panel with log-scale visualization.
  - **Hybrid Backend**:
    - **Primary**: Uses `curie` (nuclear-curie) for authoritative half-life and decay data (Integrated & Verified).
    - **Fallback**: Custom Bateman Solver (Python) ensures functionality even without C++ dependencies.
  - **Features**: U-238 and Th-232 chain simulation, user-definable activity/duration.
  - **Endpoint**: `/analyze/decay-prediction`.

- **Universal Spectrum Support (SandiaSpecUtils)**
  - Integrated `SandiaSpecUtils` wrapper to handle 100+ file formats.
  - Supports: `.spc`, `.pcf`, `.mca`, `.dat`, `.cnf` and many legacy formats.
  - Seamless fallback: Backend automatically tries generic parser if native N42/CSV fails.

- **Activity & Dose Rate Calculator**
  - **Centralized Logic**: New `activity_calculator.py` module for rigorous physics math.
  - **Features**: 
    - Bq/μCi conversion (fixed 1000x scaling bug).
    - Gamma Dose Rate estimation from activity and distance.
    - MDA (Minimum Detectable Activity) calculations.
  - **Refactor**: ROI analysis now uses this shared engine for consistent results.

- **UI & UX Polish**
  - **Smart Activity Population**: Decay Prediction tool automatically pulls "Initial Activity" (Bq) from the last performed ROI Analysis.
  - **Chart Visualization**: Decay chart now uses clean scientific notation (e.g., `1e-5`, `100`) on the logarithmic Y-axis to prevent label clutter.
  - **Layout Fixes**: Improved responsiveness of ROI Analysis panel to prevent input field overlap on smaller screens.

### Fixed
- **Activity Unit Display**: Fixed frontend bug where μCi values were erroneously multiplied by 1000.
- **Ra-226 Interference**: 
    - Implemented "Forced Subtraction" for Uranium Glass mode.
    - System now attempts to estimate and subtract Ra-226 contribution from 186 keV peak even with weak Bi-214 signals.

---

## [Unreleased - Session 2025-12-16] - Source Identification & ROI V2

### Added
- **Source Type Identification**
  - **Auto-Suggest**: Rule-based identification of common sources (Uranium Glass, Thoriated Lenses, Radium Dials, Smoke Detectors).
  - **User-Driven Context**: New "Source Type" dropdown in ROI Analysis panel allows users to specify what they are measuring.
  - **Systematic Validation**: Checks detected isotopes against the expected profile of the selected source.
    - Warns if unexpected isotopes are analyzed (e.g., U-235 in a Thoriated Lens).
    - Prevents misleading "Natural Uranium" classification for mixed/Thoriated sources.

- **Enhanced ROI Analysis**
  - **Context-Aware Logic**: Uses source type selection to inform analysis assumptions.
  - **Ra-226 Interference Handling**:
    - "Standard Analysis" (Default): Flags interference only if Bi-214 is detected.
    - "Uranium Glass" Mode: Proactively assumes Ra-226 interference (secular equilibrium) and warns about U-235 enrichment uncertainty.
  - **Diagnostic Feedback**: Detailed feedback on *why* a result is indeterminate (e.g., "Overlapping peaks", "Low SNR").

### Changed
- **ROI UI Layout**
  - Compact grid layout for better space utilization.
  - "Standard Analysis" is now the default mode (no assumptions).
  - Minimized info banners to reduce clutter.

---

## [Unreleased - Session 2025-12-15 PM] - Server-Side Acquisition Management

### Added
- **Server-Side Acquisition Timer (Critical Robustness Feature)**
  - Root cause of unfinalized acquisitions: Browser JS timer throttled during display sleep
  - Solution: Acquisition timing now managed entirely by Python backend
  - Survives browser tab throttling, display sleep, and tab closure
  - New module: `backend/acquisition_manager.py` with `AcquisitionManager` singleton
  - New endpoints:
    - `POST /device/acquisition/start` - Start managed acquisition
    - `GET /device/acquisition/status` - Poll current state (includes spectrum data)
    - `POST /device/acquisition/stop` - Stop and finalize
    - `GET /device/acquisition/data` - Get latest spectrum data
    - `GET /device/spectrum/current` - Get cumulative device spectrum

- **Cumulative Spectrum Endpoint**
  - `GET /device/spectrum/current` - Get whatever's on the device without clearing
  - Useful for checking device accumulation or resuming after browser disconnect
  - Based on legacy AlphaHound `G` command behavior

### Changed
- **`main.js`**: `startAcquisition()` now uses server API instead of `setInterval`
- **`api.js`**: Added `startManagedAcquisition()`, `getAcquisitionStatus()`, `stopManagedAcquisition()`, `getAcquisitionData()`
- Frontend now polls server for status; timing accuracy independent of browser

## [Unreleased - Session 2025-12-15 PM2] - Serial Command Discovery & UI Enhancements

### Discovered (via serial probing)
- **Undocumented AlphaHound serial commands:**
  - `E` - Cycle display mode FORWARD
  - `Q` - Cycle display mode BACKWARD
  - `K` - Get device config (actThresh, NoiseFloor)
  - `L` - Get activity threshold
  - `DB` - **Correct dose rate** (matches device display)
  - Device uses single-character command parsing
- Full documentation: `docs/ALPHAHOUND_SERIAL_COMMANDS.md`

### Added
- **Display Mode Control UI**
  - ◀/▶ buttons in device panel to cycle display modes remotely
  - New endpoint: `POST /device/display/{next|prev}`
  - Uses newly discovered `E` and `Q` commands

- **Get Current Spectrum Button**
  - Downloads cumulative spectrum without clearing device
  - Useful for checking accumulation or recovering after disconnect

- **Clear Spectrum Button**
  - Manually reset device spectrum with confirmation dialog
  - New endpoint: `POST /device/clear`
  - Uses `W` command (tested and confirmed)

- **Temperature Display**
  - Shows device temperature (🌡️) next to dose rate
  - Updated from spectrum metadata (Temp field)

- **Server-Managed Acquisition Indicators**
  - "SERVER-MANAGED" badge when acquisition is running
  - Info message: "You can close this tab and it will continue"

### Fixed
- **Dose rate now uses `DB` command** instead of `D`
  - Statistical analysis confirmed D/DA/DB are identical
  - `DB` chosen as it synchronized best with device display

---

## [Unreleased - Session 2025-12-15] - Acquisition Resilience & Reference Links

### Fixed
- **8-Hour Acquisition Limit Bug (Critical)**
  - Root cause: `MAX_ACQUISITION_MINUTES = 60` caused 422 validation error for 480-minute capture
  - Fix: Increased limit to 1440 (24 hours) in `backend/routers/device.py`
  - Long acquisitions now complete and auto-save correctly

### Added
- **Acquisition Crash Recovery**
  - Periodic checkpoint saves every 5 minutes during acquisition
  - Single overwriting file: `data/acquisitions/acquisition_in_progress.n42`
  - If acquisition fails, checkpoint contains all data up to last save
  - Automatic cleanup after successful completion
  - New endpoints: `POST /export/n42-checkpoint`, `DELETE /export/n42-checkpoint`

- **Device Write Retry Logic**
  - Serial write operations now retry 3 times before disconnecting
  - Prevents transient USB timeouts from killing long acquisitions
  - All device log messages now include timestamps for debugging

- **NNDC Reference Links for Isotopes**
  - Each identified isotope now has a clickable "📚 NNDC" link
  - Links directly to NNDC NuDat3 decay data page
  - Example: Cs-137 links to `https://www.nndc.bnl.gov/nudat3/decaysearchdirect.jsp?nuc=137Cs`

- **Authoritative Source References for Decay Chains**
  - Decay chain cards now display NNDC, IAEA, and other reference links
  - U-238, Th-232, U-235 chains include 3 authoritative sources each
  - Links open in new tab for easy research

- **SNIP Background Filtering** (NEW)
  - "🔻 Auto Remove BG" button in Analysis → Background Subtraction
  - Removes Compton continuum without requiring separate background file
  - Uses industry-standard SNIP (Sensitive Nonlinear Iterative Peak) algorithm
  - Re-runs peak detection and isotope ID on cleaner data
  - Improves detection of weak peaks buried in continuum

## [Unreleased]

### Added
- **UI Enhancements**: Added a toggle button and scrollable area for the "Detected Peaks" table to improve dashboard usability with many peaks.
- **Spectrum Algebra**: Added UI controls for adding, subtracting, and comparing spectra.
- **ML Quality Badges**: Added visual indicators for ML confidence (High/Medium/Low) and suppression status.
- **Responsive Charts**: Enabled pinch-to-zoom and touch gestures for mobile users. Added `Hammer.js` and optimized touch interactions.

### Fixed
- **Chart Auto-Scale**: Tuned autoscale algorithm to prevent aggressive cropping of high-energy data. Now prioritizes full data visibility over noise reduction.
- **N42 Import/Export**: Fixed a critical bug where acquisition time (Live Time/Real Time) was lost when re-importing auto-saved files. Corrected the JSON payload structure in `main.js`.
- **Peak Matching**: Restored legacy peak matching functionality and integrated it with ML predictions for hybrid filtering.

- **CHN/SPE File Import** (NEW)
  - Support for Ortec CHN (binary) and Maestro SPE (ASCII) formats
  - Automatic energy calibration extraction
  - Full analysis pipeline on import (peaks, isotopes, chains)
  - New: `backend/chn_spe_parser.py`

- **Spectrum Algebra** (NEW)
  - Add, subtract, normalize, compare spectra
  - Proper Poisson error propagation
  - Live time normalization support
  - Endpoint: `POST /analyze/spectrum-algebra`
  - New: `backend/spectrum_algebra.py`

- **ONNX/TFLite Model Export** (NEW)
  - Export trained ML models for mobile/edge deployment
  - ONNX format for desktop inference
  - TFLite format for Android/iOS apps
  - Endpoint: `POST /analyze/export-model`

- **Anomaly Detection** (NEW)
  - Flag unusual spectra that don't match training data
  - Multi-factor scoring: ML confidence, peak/BG ratio, entropy
  - Endpoint: `POST /analyze/anomaly-detection`

- **Poisson Peak Fitting** (NEW)
  - Maximum likelihood estimation for low-count peaks
  - Proper counting statistics uncertainty
  - More robust than least-squares for weak signals
  - New: `poisson_peak_fit()` in `spectral_analysis.py`

- **ML Hybrid Filtering** (NEW)
  - Confidence thresholding: 5% minimum to display predictions
  - Hybrid filtering: Suppresses medical isotopes when natural chains detected
  - Quality badges: "✓ High Confidence", "⚠ Moderate", "⚠ Low Confidence"
  - Suppressed predictions shown dimmed with "(suppressed)" label

### Changed
- **`alphahound_serial.py`**: `_write()` method now has retry loop with exponential backoff
- **`ui.js`**: Added `getNNDCUrl()` helper, enhanced `renderIsotopes()` and `renderDecayChains()`
- **`spectral_analysis.py`**: Added `snip_background()` and `poisson_peak_fit()` functions
- **`analysis.py`**: 6 new endpoints for SNIP, ML export, spectrum algebra, anomaly detection
- **`ml_analysis.py`**: Added `export_model()`, `_export_onnx()`, `_export_tflite()` methods
- **`main.js`**: ML predictions now show quality badges and suppression indicators
- **`isotope_database.py`**: Major peak matching improvements:
  - Contextual suppression: Medical/fission isotopes suppressed when natural decay chains detected
  - Single-line isotopes capped at 60% confidence (prevents 1/1 = 100% false positives)
  - Peak count penalty: 30% penalty for single matches, 10% bonus for 3+ matches
  - All decay chains (U-238, Th-232, U-235) now properly defined and tracked
- **Detected Peaks Table**: Completely redesigned with sticky headers, backdrop blur, hover effects, and right-aligned numerical data (v6 CSS).
- **Isotope Identification**: Implemented intensity-weighted scoring to prioritize diagnostic peaks (fixes weak Pb-212/Pb-214 confusion).
- **Decay Chain Logic**: Enforced stricter confidence threshold (>40%) for flagging Uranium/Thorium chains.
- **Detector Calibration**: Reconfigured backend to enforce 3.0 keV/channel (replacing device's 7.4 default) for accurate peak alignment.

### Fixed
- **Page Load Crash**: Fixed `main.js` syntax error (extra brace) that prevented application load.
- **Auto-BG Chart Sync**: Fixed visual issue where peaks appeared disconnected from the spectrum after background removal.
- **Chart Render Crash**: Fixed "Spread syntax" error when rendering invalid or background-subtracted data (validation added to `charts.js`).

---

## [Unreleased - Session 2025-12-14 Late] - ML Model Selection & N42 Auto-Save

### Added
- **Compton Continuum Simulation** (ml_analysis.py)
  - `add_compton_continuum()` method for realistic CsI(Tl) detector response
  - Calculates Compton edge and distributes ~35% of peak counts to continuum
  - Applied to all synthetic training peaks

- **Selectable ML Model Types**
  - `HOBBY_ISOTOPES` list with 35 common isotopes (uranium glass, mantles, calibration)
  - `ML_MODEL_TYPES` config: hobby (35 isotopes, 30 samples) vs comprehensive (95+, 15 samples)
  - `get_ml_identifier(model_type)` caches separate instances per model
  - `get_available_ml_models()` for future settings UI integration

- **N42 Auto-Save Format** (default)
  - New `/export/n42-auto` endpoint replaces `/export/csv-auto`
  - Auto-saves to `data/acquisitions/spectrum_YYYY-MM-DD_HH-MM-SS.n42`
  - Includes peaks, isotopes, live_time, real_time in saved files
  - Standards-compliant N42.42 format for better portability

### Fixed
- **N42 Auto-Save Import Error**
  - Fixed wrong function name: `create_n42_xml` → `generate_n42_xml`
  - Auto-save now works correctly after server restart

---

## [Unreleased - Session 2025-12-14 PM] - PyRIID Enhancement & Peak Detection Fix

### Added
- **IAEA Data Integration**
  - Downloaded 49 isotope gamma data files from IAEA LiveChart API
  - 2,499 gamma lines with intensity data (e.g., Bi-214 @ 609 keV = 45.44%)
  - New `backend/iaea_parser.py` for parsing IAEA CSV format
  - Isotope database now loads IAEA intensity data on startup

- **Authoritative Data Scripts**
  - `download_iaea_data.py` - Downloads gamma data for priority isotopes
  - Data stored in `backend/data/idb/isotopes/`

### Fixed
- **Peak Detection Threshold Too Strict (Critical)**
  - Before: Only 3 peaks detected (prominence_factor=0.05 was 5% of max)
  - After: 20+ peaks detected with new balanced thresholds
  - Changed to `max(5, max_count * 0.003)` for height, `max(3, max_count * 0.002)` for prominence
  - File: `backend/peak_detection.py`

- **U-235/U-238 Prioritization**
  - U-238 now ranks #2 at 100% (was incorrectly below U-235)
  - U-235 now ranks #26 at 0.1% with suppression when U-238 chain detected
  - Added abundance weighting to `backend/isotope_database.py`

### Changed
- **ML Training Data** (backend/ml_analysis.py)
  - Synthetic peaks now use IAEA intensity weighting
  - Calibration updated to 7.4 keV/channel (AlphaHound actual)
  - Imports `get_gamma_intensity()` for realistic peak heights

- **AI Identification UI Label**
  - Added "WIP" badge to indicate ML model is still experimental
  - Peak Matching remains the recommended method

### Verified
- Community spectra test: 5/6 files correctly suppress U-235
- All 6 files detect U-238 at 60%+ confidence
- Bi-214, Pb-214, Th-234 now visible in UI

---

## [Unreleased - Session 2025-12-14] - N42 Export & Parser Improvements

### Added
- **N42 XML Export (Complete Implementation)**
  - Standards-compliant N42.42-2006 XML export from device acquisitions
  - Full 1024-channel spectrum with energy calibration
  - Proper ISO 8601 duration format (`PT60.000S`) for LiveTime/RealTime
  - Isotope identification results included as SpectrumExtension
  - Instrument information (manufacturer, model, serial number)
  - "Export N42" button in controls bar

- **Enhanced N42 Parser (Graceful Fallbacks)**
  - Multi-namespace support (N42.42-2006, N42.42-2011, no-namespace)
  - ISO 8601 duration parsing (`PT##H##M##.###S` → seconds)
  - Extracts instrument info for proper SOURCE display (e.g., "RadView Detection AlphaHound")
  - Searches multiple element locations for legacy file compatibility
  - Coefficient-based energy calibration support
  - Creates default channel array if no energies found

- **Improved Auto-Scale (Chart)**
  - 99% cumulative count algorithm for smarter X-axis trimming
  - 15% right buffer + 5% left buffer for visual appeal
  - Y-axis scaled to visible data region only
  - Minimum zoom: 200 keV or 10% of full range
  - Peak protection: never clips detected peaks

### Fixed
- **N42 Export "cannot serialize 100 (type int)" error**
  - All XML text values now wrapped with `str()` to prevent integer serialization
  - Affects: isotope confidence, energy values, timestamps, instrument info

- **422 Unprocessable Entity error**
  - Added `N42ExportRequest` Pydantic model for proper request validation
  - Replaced generic `dict` type hint with structured model

- **N42 Parser timing extraction**
  - LiveTime extracted from `<Spectrum>` element
  - RealTime extracted from `<RadMeasurement>` element
  - Proper ISO 8601 duration parsing (was failing on `PT1.000S`)

### Changed
- **Export Buttons Styling**
  - Export PDF and Export N42 now both use `.btn-accent` class
  - Consistent appearance that adapts to all themes
  - Removed hardcoded inline styles

- **Backend API**
  - `/export/n42` endpoint uses Pydantic model validation
  - Uses `model_dump()` instead of deprecated `dict()`

### Technical Notes
- N42 exporter: `backend/n42_exporter.py` (200 lines)
- N42 parser: `backend/n42_parser.py` (175 lines)  
- Auto-scale: `backend/static/js/charts.js` (lines 24-78)
- Request model: `backend/routers/analysis.py` (lines 80-88)

---

## [Unreleased - Session 2025-12-12] - Project Cleanup & Maintenance

### Changed
- **Project Directory Cleanup**
  - Archived 49+ files (~7.6 MB) to organized subdirectories
  - Created structured archive organization:
    - `archive/test_scripts/` - 31 test/debug/check scripts
    - `archive/backup_files/` - 1 backup file (app.js.bak)
    - `archive/icon_backups/` - 12 old PNG/JPG icons
    - `archive/sample_data/` - 1 test CSV file
    - `archive/planning_docs/` - 2 research documents
  - Reduced backend directory from 48 to 17 Python files
  - Reduced root directory from 18 to 15 files
  - Improved project navigation and maintainability
  - All files preserved in archive (no deletions)

---

## [Unreleased - Session 2025-12-12] - Technical Debt & Feature Polish


### Added
- **Rate Limiting (Security)**
  - Integrated `slowapi` middleware for API rate limiting
  - Default: 60 requests per minute per IP address
  - Protects against API abuse and denial-of-service

- **Custom Isotope Import/Export**
  - `GET /isotopes/custom/export` - Download all custom isotopes as JSON
  - `POST /isotopes/custom/import` - Import isotopes from JSON file
  - UI buttons: "📥 Import JSON" and "📤 Export JSON" in Custom Isotopes modal
  - Supports bulk import/export for library sharing

- **Apache License 2.0**
  - Created `LICENSE` file with full Apache 2.0 text
  - Added `.github/FUNDING.yml` stub for GitHub Sponsors

### Fixed
- **COUNT TIME Metadata Bug**
  - Fixed Pydantic type annotation (`Optional[float]`) for `actual_duration_s`
  - Frontend now passes actual elapsed time to backend on acquisition completion
  - Metadata `count_time_minutes` now shows real duration, not requested duration

### Changed
- **README.md Updates**
  - Added ROI Analysis credits to NuclearGeekETH (same author as AlphaHound connector)
  - Updated image paths to relative format for GitHub compatibility
  - Updated license section to Apache 2.0

- **Device Panel Enhancement**
  - Split layout with controls left, live data right
  - Consolidated inline controls for cleaner UI
  - Added 5-minute dose rate sparkline chart

- **ML AlphaHound Tuning**
  - Energy-dependent FWHM matching CsI(Tl) resolution (10% at 662 keV)
  - Scintillator resolution model: FWHM(E) = 0.10 × E × √(662/E)
  - Improved training spectra realism for better AlphaHound data recognition

- **UI Polish (2025-12-12)**
  - Replaced emoji with SVG icons in Custom Isotopes modal (Import/Export)
  - Fixed Custom Isotopes modal layout with proper grid alignment
  - Increased modal width to 650px for better spacing
  - Fixed COUNT TIME precision to 2 decimal places (was showing 15+ decimals)
  - Changed metadata "TOOL" field to "SOURCE" with user-friendly values:
    - "CSV File" or "CSV File (Becquerel)"
    - "N42 File"
    - "AlphaHound Device"

### Documentation
- **PYRIID_GUIDE.md**: Comprehensive 400+ line guide covering:
  - How PyRIID works (architecture, training, prediction)
  - AlphaHound detector tuning details
  - 10 ways users can extend/enhance ML functionality
  - Usage instructions and best practices

### Dependencies Added
- `slowapi` - Rate limiting for FastAPI endpoints

---

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
