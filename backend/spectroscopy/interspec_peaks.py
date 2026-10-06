"""
Peak search and fit by InterSpec (Sandia National Laboratories, LGPL-2.1), run as a separate program:
`InterSpec_batch --batch-peak-fit --fit-all-peaks`.

The spectrum is written to a temporary N42, InterSpec finds and fits every peak and writes a CSV, and its rows become the
application's peak dicts (the fields spectroscopy/peak_detection_enhanced.py returns). Measured 2026-10-05 against the built-in
detector on synthetic AlphaHound spectra with known peaks: it finds overlapping and shoulder peaks the built-in one misses, takes
about 40 ms per spectrum plus ~0.5 s to start, and its stated area uncertainties are 2-7x too small for weak or overlapping peaks
(quantities that need an honest uncertainty come from the ROI engine).

Every analysis runs in a worker thread, and waiting for the process holds neither the event loop nor the GIL. Each call has its
own temporary folder, so concurrent analyses do not collide.

Settings (environment):
  ALPHAHOUND_PEAKS=builtin           use the built-in detector even when InterSpec is there
  ALPHAHOUND_INTERSPEC_BATCH=<path>  InterSpec_batch.exe; keep the path short (InterSpec trips over Windows' 260-character limit)
Without InterSpec the built-in detector is used.
"""
import csv
import logging
import math
import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# where INSTALL.md says to unpack it: under the user's home folder, which keeps the path short (it was this account's folder, so on any other
# account InterSpec was silently not found and the built-in detector used)
DEFAULT_BATCH = os.path.join(os.path.expanduser("~"), "tools", "InterSpec", "InterSpec-win32-x64_WebView2_v1.0.14", "InterSpec_batch.exe")
TIMEOUT_S = 60.0
FWHM_PER_SIGMA = 2.354820045
SOURCE = "InterSpec"


def _hidden() -> Dict:
    """Arguments that keep InterSpec_batch (a console program) out of sight on Windows. The server runs detached, without a
    console, so Windows gave every run a new console window over the user's desktop."""
    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0                                  # SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": info}


def batch_path() -> Optional[str]:
    path = os.environ.get("ALPHAHOUND_INTERSPEC_BATCH", DEFAULT_BATCH)
    return path if path and os.path.isfile(path) else None


def enabled() -> bool:
    """InterSpec is the peak finder when it is installed, unless ALPHAHOUND_PEAKS=builtin."""
    return os.environ.get("ALPHAHOUND_PEAKS", "").strip().lower() != "builtin" and batch_path() is not None


def threshold_edge_keV(energies, counts) -> float:
    """
    Where the detector's lower threshold stops cutting counts. Below it the spectrum rises from nearly nothing to a turnover,
    which InterSpec (like the built-in detector) reports as a peak: 31.8 keV, 54 % wide, on the AlphaHound. 0 when the spectrum
    has no such roll-off at its bottom.
    """
    E = np.asarray(energies, dtype=float)
    c = np.asarray(counts, dtype=float)
    if c.size < 32:
        return 0.0
    sm = np.convolve(c, np.ones(5) / 5.0, mode="same")
    bottom = sm[2: max(8, c.size // 10)]
    if bottom.size == 0 or bottom.max() <= 0 or sm[2] > 0.25 * bottom.max():
        return 0.0
    i = 2
    while i + 1 < c.size and sm[i + 1] >= sm[i]:
        i += 1
    return float(E[i])


def _float(cell) -> Optional[float]:
    try:
        value = float(str(cell).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def find_peaks(energies, counts, r662: float, live_time: float = 0.0, min_energy: float = 0.0) -> Optional[List[Dict]]:
    """
    InterSpec's peaks, sorted by energy: energy, energy_unc, fwhm, fwhm_expected (the detector's, from r662), sigma, resolution,
    net_area, net_area_unc / uncertainty, significance / snr (net area over its uncertainty), chi2_red, fit_valid, counts (the
    spectrum at the peak: where a chart marker goes), fitted_by. None when InterSpec is missing or failed (the caller falls back).
    """
    from formats.n42_exporter import generate_n42_xml

    exe = batch_path()
    E = np.asarray(energies, dtype=float)
    c = np.asarray(counts, dtype=float)
    if exe is None:
        return None
    if E.size < 16 or E.size != c.size or not np.any(c > 0):
        return []
    work = tempfile.mkdtemp(prefix="isp_")
    try:
        spectrum = os.path.join(work, "s.n42")
        live = float(live_time) if live_time and live_time > 0 else 1.0
        with open(spectrum, "w", encoding="utf-8") as f:
            f.write(generate_n42_xml({"counts": c.tolist(), "energies": E.tolist(),
                                      "metadata": {"live_time": live, "real_time": live, "source": "AlphaHoundGUI"}}))
        done = subprocess.run([exe, "--batch-peak-fit", "--fit-all-peaks", "--input-file", spectrum, "--out-dir", work,
                               "--overwrite-output-files", "--file-report-template", "none", "--summary-report-template", "none"],
                              capture_output=True, text=True, timeout=TIMEOUT_S, cwd=os.path.dirname(exe), **_hidden())
        result = os.path.join(work, "s.n42.CSV")
        if not os.path.exists(result):
            logger.warning("InterSpec wrote no peaks (exit %s): %s", done.returncode, (done.stderr or done.stdout)[-300:])
            return None
        with open(result, encoding="utf-8", errors="replace") as f:
            rows = list(csv.reader(f))
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("InterSpec peak fit failed: %s", exc)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)

    edge = threshold_edge_keV(E, c)
    peaks: List[Dict] = []
    for row in rows[2:]:                     # two header rows; columns: centroid, net area, its uncertainty, CPS, FWHM, FWHM %, chi2/dof
        energy, area, unc, fwhm, chi2 = (_float(row[i]) if len(row) > i else None for i in (0, 1, 2, 4, 6))
        if energy is None or area is None or fwhm is None or fwhm <= 0 or energy < min_energy:
            continue
        f_exp = r662 * 662.0 * math.sqrt(max(energy, 1.0) / 662.0)
        if energy - min(fwhm, f_exp) < edge:
            continue
        unc = unc if unc and unc > 0 else math.sqrt(max(area, 1.0))
        k = int(np.argmin(np.abs(E - energy)))
        peaks.append({
            # the CSV gives no centroid uncertainty: the counting-statistics one, sigma / sqrt(net area)
            "energy": energy, "energy_unc": fwhm / FWHM_PER_SIGMA / math.sqrt(max(area, 1.0)),
            "fwhm": fwhm, "fwhm_expected": f_exp, "sigma": fwhm / FWHM_PER_SIGMA,
            "resolution": fwhm / energy * 100.0 if energy > 0 else None,
            "net_area": area, "net_area_unc": unc, "uncertainty": unc, "significance": area / unc, "snr": area / unc,
            "chi2_red": chi2, "fit_valid": True, "counts": float(c[k]), "display_energy": energy, "fitted_by": SOURCE,
        })
    return sorted(peaks, key=lambda p: p["energy"])
