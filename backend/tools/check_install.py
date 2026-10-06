"""
What this installation can do: the Python version, the packages the app cannot start without, the optional ones and what each adds, and
whether the InterSpec peak finder is found. Run by the install and run scripts (install_deps.bat, install_lightweight.bat, run.bat):

    python backend/tools/check_install.py            # full report
    python backend/tools/check_install.py --quiet    # only problems; exit code 1 when the app cannot start

Packages are looked up without importing them (a numpy import alone takes a second), so this answers at once.
"""
import importlib.util
import os
import sys

MIN_PYTHON = (3, 11)       # scipy 1.16 and scikit-learn 1.8, the oldest versions the tests ran against, need 3.11

# (import name, pip name): the app does not start without these (requirements_lightweight.txt, which backend/requirements.txt includes)
REQUIRED = [
    ("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("multipart", "python-multipart"), ("websockets", "websockets"),
    ("slowapi", "slowapi"), ("pydantic", "pydantic"), ("serial", "pyserial"), ("numpy", "numpy"), ("scipy", "scipy"),
    ("pandas", "pandas"), ("matplotlib", "matplotlib"), ("reportlab", "reportlab"),
]

# (import name, pip name, what it adds): all in backend/requirements.txt; the app starts without them and says so
OPTIONAL = [
    ("sklearn", "scikit-learn", "AI identification"),
    ("radioactivedecay", "radioactivedecay", "exact decay chains and decay prediction (built-in tables without it)"),
    ("curie", "curie", "shielding and emissions calculators, X-ray data"),
    ("SpecUtils", "SandiaSpecUtils", "reading and writing other spectrum formats (PCF, ...)"),
    ("radiacode", "radiacode", "the Radiacode device"),
    ("bleak", "bleak", "the Radiacode over Bluetooth"),
    ("libusb_package", "libusb-package", "the Radiacode over USB on Windows"),
]


def present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def interspec():
    """(found, path) of the optional InterSpec peak finder."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, here)
    try:
        from spectroscopy import interspec_peaks
        return interspec_peaks.enabled(), interspec_peaks.batch_path() or os.environ.get("ALPHAHOUND_INTERSPEC_BATCH", interspec_peaks.DEFAULT_BATCH)
    except Exception:
        return False, ""


def main(argv=None) -> int:
    quiet = "--quiet" in (argv if argv is not None else sys.argv[1:])
    problems = []
    lines = []
    version = ".".join(str(v) for v in sys.version_info[:3])
    if sys.version_info[:2] < MIN_PYTHON:
        problems.append(f"Python {version} is too old: {'.'.join(map(str, MIN_PYTHON))} or newer is needed")
    lines.append(f"Python {version}: " + ("ok" if sys.version_info[:2] >= MIN_PYTHON else "TOO OLD"))

    missing = [pip for module, pip in REQUIRED if not present(module)]
    if missing:
        problems.append("missing required packages: " + ", ".join(missing) + " (run install_lightweight.bat or install_deps.bat)")
    lines.append(f"Required packages: {len(REQUIRED) - len(missing)} of {len(REQUIRED)} present" + (f" (missing: {', '.join(missing)})" if missing else ""))

    for module, pip, adds in OPTIONAL:
        lines.append(f"  {'present' if present(module) else 'absent '}  {pip:<18} {adds}")

    found, path = interspec()
    lines.append("Peak finder: " + (f"InterSpec ({path})" if found else
                                    "the built-in detector (InterSpec not found; optional, see INSTALL.md: ALPHAHOUND_INTERSPEC_BATCH)"))

    if quiet:
        for problem in problems:
            print("PROBLEM: " + problem)
    else:
        print("\n".join(lines))
        for problem in problems:
            print("PROBLEM: " + problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
