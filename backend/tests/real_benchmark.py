"""
Accuracy benchmark on REAL (non-synthetic) labelled spectra from both supported devices.

Ground truth comes from what each sample physically is (file names / dataset notes),
never from what the engine currently outputs:

  RadiaCode-103 (tests/data/radiacode_fisicas, MIT, github.com/Fisicas/radiacode-flight-spectroscopy)
    Am-241.xml                  Am-241 point source         -> Am-241; no decay chain
    Ra-226.xml                  radium source               -> U-238 (radium) series; no Th-232
    Th-232.xml                  thorium source              -> Th-232 series; no U-238
    U-238-U-235-FiestaWare.xml  uranium-glazed Fiestaware   -> U-238 series; no Th-232
  AlphaHound CsI(Tl) (backend/tests/data/real_spectra + backend/)
    Takumar lens x3 (re-calibrated to the device axis)   -> Th-232 series; no U-238
    Cs137_Verification_Spectra.n42                        -> Cs-137; no decay chain
    "7.5 x 4 Deep Red Uranium Glaze Bowl.csv" (community) -> U-238 series; no Th-232

Optional extra cases (not committed, unclear licence) are picked up from the directory in
$REAL_BENCHMARK_EXTRA if set: hw_thorium.csv / hw_uranium.csv (RadiaCode-110).

Run as a script for a scorecard:  python tests/real_benchmark.py
"""
import contextlib
import io
import logging
import os
import pathlib
import shutil
import sys
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tools"))

RC_DIR = BACKEND / "tests" / "data" / "radiacode_fisicas"
ACQ = BACKEND / "tests" / "data" / "real_spectra"   # real spectra kept as test fixtures
AXIS_CSV = ACQ / "spectrum_2025-12-12_08-41-27.csv"

# (case id, device, loader key, path, expected chains, forbidden chains, expected isotopes)
CASES = [
    ("rc103_am241", "RadiaCode-103", "rcxml", RC_DIR / "Am-241.xml", [], ["U-238", "Th-232"], ["Am-241"]),
    ("rc103_ra226", "RadiaCode-103", "rcxml", RC_DIR / "Ra-226.xml", ["U-238"], ["Th-232"], []),
    ("rc103_th232", "RadiaCode-103", "rcxml", RC_DIR / "Th-232.xml", ["Th-232"], ["U-238"], []),
    ("rc103_fiesta", "RadiaCode-103", "rcxml", RC_DIR / "U-238-U-235-FiestaWare.xml", ["U-238"], ["Th-232"], []),
    ("ah_takumar_90m", "AlphaHound", "n42_recal", ACQ / "spectrum_2025-12-15_takumar_90min.n42", ["Th-232"], ["U-238"], []),
    ("ah_takumar_8h", "AlphaHound", "n42_recal", ACQ / "spectrum_takumar_8hr_reference.n42", ["Th-232"], ["U-238"], []),
    ("ah_takumar_night", "AlphaHound", "n42_recal", ACQ / "takumar 942pm to 558am.n42", ["Th-232"], ["U-238"], []),
    ("ah_cs137", "AlphaHound", "n42", BACKEND / "Cs137_Verification_Spectra.n42", [], ["U-238", "Th-232"], ["Cs-137"]),
    ("ah_u_glaze", "AlphaHound", "csv", ACQ / "community" / "7.5 x 4 Deep Red Uranium Glaze Bowl.csv", ["U-238"], ["Th-232"], []),
]

_extra = os.environ.get("REAL_BENCHMARK_EXTRA")
if _extra:
    CASES += [
        ("rc110_thorium", "RadiaCode-110", "csv", pathlib.Path(_extra) / "hw_thorium.csv", ["Th-232"], ["U-238"], []),
        ("rc110_uranium", "RadiaCode-110", "csv", pathlib.Path(_extra) / "hw_uranium.csv", ["U-238"], ["Th-232"], []),
    ]


def load(kind, path):
    """Parse a spectrum file into the pipeline's input dict (no analysis yet)."""
    from formats.csv_parser import parse_csv_spectrum
    from formats.n42_parser import parse_n42
    from formats.radiacode_xml_parser import parse_radiacode_xml

    raw = path.read_bytes()
    if kind == "rcxml":
        return parse_radiacode_xml(raw.decode("utf-8"))
    if kind == "csv":
        return parse_csv_spectrum(raw, path.name)
    if kind == "n42":
        return parse_n42(raw.decode("utf-8"))
    if kind == "n42_recal":
        import recalibrate_n42 as rc
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "in.n42"
            shutil.copy(path, src)
            text = rc.recalibrate_text(src.read_text(encoding="utf-8"), rc.load_axis(AXIS_CSV))
            return parse_n42(text)
    raise ValueError(kind)


def analyze_case(case):
    from spectroscopy.analysis_utils import analyze_spectrum_peaks
    cid, device, kind, path, *_ = case
    with contextlib.redirect_stdout(io.StringIO()):
        parsed = load(kind, path)
        parsed.setdefault("metadata", {})
        parsed["metadata"].setdefault("instrument_model", device)
        live = float(parsed["metadata"].get("live_time") or 0)
        return analyze_spectrum_peaks(parsed, parsed.get("is_calibrated", True), live)


# Artificial/medical isotopes that must not be reported for a natural U/Th sample or a single
# different sealed source (they come from coincidental matches in the X-ray/backscatter region)
ARTIFICIAL = ["Tl-201", "Am-241", "Ba-133", "Co-60", "Cs-137", "I-131", "F-18", "Tc-99m", "Na-22",
              "Co-57", "Ga-67", "In-111", "Ir-192", "Eu-152", "Se-75", "Lu-177", "Sr-90"]


def score_case(case, result):
    cid, device, kind, path, want_chains, bad_chains, want_isotopes = case
    chains = {c["parent"]: c["confidence_level"] for c in result.get("decay_chains", [])}
    isotopes = [i["isotope"] for i in result.get("isotopes", [])]
    checks = []
    for c in want_chains:
        checks.append((f"chain {c} present", c in chains))
    for c in bad_chains:
        checks.append((f"chain {c} absent", c not in chains))
    for iso in want_isotopes:
        checks.append((f"isotope {iso} in top-3", iso in isotopes[:3]))
    spurious = [i for i in isotopes[:3] if i in ARTIFICIAL and i not in want_isotopes]
    checks.append((f"no spurious artificial isotope in top-3 {spurious}", not spurious))
    return checks, chains, isotopes


def run(verbose=True):
    logging.disable(logging.CRITICAL)
    total = passed = 0
    rows = []
    for case in CASES:
        if not case[3].exists():
            continue
        result = analyze_case(case)
        checks, chains, isotopes = score_case(case, result)
        total += len(checks)
        passed += sum(ok for _, ok in checks)
        rows.append((case, checks, chains, isotopes, result))
        if verbose:
            fails = [name for name, ok in checks if not ok]
            print(f"{'PASS' if not fails else 'FAIL'}  {case[0]:18} {case[1]:14} chains={chains} top-isotopes={isotopes[:3]}"
                  + (f"  <- {fails}" if fails else ""))
    if verbose:
        print(f"\n{passed}/{total} checks passed across {len(rows)} real spectra")
    logging.disable(logging.NOTSET)
    return passed, total, rows


if __name__ == "__main__":
    run()
