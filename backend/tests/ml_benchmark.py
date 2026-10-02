"""
ML identifier scorecard on the same labelled real spectra as real_benchmark.py.

Ground truth is the physical source (see real_benchmark.CASES). A prediction counts as consistent
if the top class is an isotope/mixture of the expected series (or the expected isotope), and is
inconsistent if it is a member of a forbidden series or an unrelated artificial isotope.

Run: python tests/ml_benchmark.py            (trains the model first: ~20 s)
"""
import contextlib
import io
import logging
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests"))
import real_benchmark as rb  # noqa: E402

U238 = {"U-238", "Th-234", "Pa-234m", "U-234", "Ra-226", "Pb-214", "Bi-214", "Pb-210", "UraniumGlass",
        "UraniumGlassWeak", "UraniumMineral", "RadiumDial", "U-235", "Th-231", "Th-227", "Ra-223"}
TH232 = {"Th-232", "Ac-228", "Pb-212", "Bi-212", "Tl-208", "ThoriumMantle"}
SERIES = {"U-238": U238, "Th-232": TH232}


def verdict(case, preds):
    _, _, _, _, want_chains, bad_chains, want_iso = case
    top = [p["isotope"] for p in preds[:3]]
    if not top:
        return False, top
    good = set().union(*(SERIES[c] for c in want_chains)) if want_chains else set(want_iso)
    bad = set().union(*(SERIES[c] for c in bad_chains)) if bad_chains else set()
    if want_chains:
        ok = top[0] in good and not (set(top[:1]) & bad)
    else:
        ok = top[0] in good if good else top[0] not in bad
    return ok, top


def run(detector_for=None, use_energies=True):
    logging.disable(logging.CRITICAL)
    from ml_analysis import get_ml_identifier
    rows, ok_n, n = [], 0, 0
    for case in rb.CASES:
        if not case[3].exists():
            continue
        with contextlib.redirect_stdout(io.StringIO()):
            parsed = rb.load(case[2], case[3])
        det = (detector_for or (lambda c: "alphahound"))(case)
        ml = get_ml_identifier("hobby", det)
        preds = ml.identify(parsed["counts"], top_k=3, energies=parsed.get("energies") if use_energies else None)
        ok, top = verdict(case, preds)
        n += 1
        ok_n += ok
        print(f"{'PASS' if ok else 'FAIL'}  {case[0]:18} {det:14} top3={[(p['isotope'], p['confidence']) for p in preds]}")
    print(f"\n{ok_n}/{n} consistent (energies={'on' if use_energies else 'off'})")
    logging.disable(logging.NOTSET)
    return ok_n, n


if __name__ == "__main__":
    dev = lambda c: "radiacode_103" if c[1] == "RadiaCode-103" else "alphahound"
    run(dev, True)
    run(dev, False)
