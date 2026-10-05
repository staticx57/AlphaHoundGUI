"""InterSpec as the peak finder (spectroscopy/interspec_peaks.py). Skipped where InterSpec is not installed."""
import asyncio
import math
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

import spectrum_synth as ss
from spectroscopy import interspec_peaks
from spectroscopy.analysis_utils import analyze_spectrum_peaks

pytestmark = pytest.mark.skipif(not interspec_peaks.enabled(), reason="InterSpec is not installed")

CH = np.arange(1024)
AXIS = 15.0001 + 1.68372 * CH - 4.75865e-05 * CH ** 2 + 5.49654e-06 * CH ** 3        # the AlphaHound's own cubic axis
DETECTOR = "AlphaHound CsI(Tl)"
LINES = [(238.6, 40000.0), (661.7, 20000.0), (1460.8, 8000.0)]


def spectrum(seed=1, threshold_keV=None):
    counts = ss.make_spectrum(DETECTOR, LINES, AXIS, continuum=300.0, seed=seed)
    if threshold_keV:
        counts = np.random.default_rng(seed).binomial(counts.astype(np.int64), 1.0 / (1.0 + np.exp(-(AXIS - threshold_keV) / 3.0))).astype(float)
    return counts


def fwhm(e):
    return 0.10 * 662.0 * math.sqrt(e / 662.0)


def test_known_lines_are_found_where_they_are():
    peaks = interspec_peaks.find_peaks(AXIS, spectrum(), 0.10)
    for energy, _ in LINES:
        assert any(abs(p["energy"] - energy) < 0.25 * fwhm(energy) for p in peaks), (energy, [round(p["energy"]) for p in peaks])
    assert all(p["fitted_by"] == "InterSpec" and p["net_area"] > 0 and p["net_area_unc"] > 0 for p in peaks)


def test_the_threshold_turnover_is_not_a_peak():
    peaks = interspec_peaks.find_peaks(AXIS, spectrum(threshold_keV=24.0), 0.10)
    assert not [p for p in peaks if p["energy"] < 45], [round(p["energy"], 1) for p in peaks]


def test_concurrent_calls_do_not_collide():
    counts = [spectrum(seed) for seed in range(4)]
    with ThreadPoolExecutor(4) as pool:
        together = list(pool.map(lambda c: interspec_peaks.find_peaks(AXIS, c, 0.10), counts))
    alone = [interspec_peaks.find_peaks(AXIS, c, 0.10) for c in counts]
    assert [[round(p["energy"], 3) for p in a] for a in together] == [[round(p["energy"], 3) for p in a] for a in alone]


def test_an_analysis_with_interspec_leaves_the_event_loop_free():
    counts = spectrum()
    gaps = []

    async def ticker(stop):
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(0.02)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(ticker(stop))
        result = await asyncio.to_thread(analyze_spectrum_peaks, {"counts": counts.tolist(), "energies": AXIS.tolist(),
                                                                 "metadata": {"source": "AlphaHound Device"}}, True, 3600.0)
        stop.set()
        await task
        return result

    result = asyncio.run(scenario())
    assert result["analysis_mode"] == "interspec"
    assert max(gaps) < 0.25, f"the event loop stalled {max(gaps):.2f} s"


def test_builtin_is_one_setting_away(monkeypatch):
    monkeypatch.setenv("ALPHAHOUND_PEAKS", "builtin")
    result = analyze_spectrum_peaks({"counts": spectrum().tolist(), "energies": AXIS.tolist(), "metadata": {}}, True, 3600.0)
    assert result["analysis_mode"] != "interspec" and result["peaks"]


def test_a_missing_interspec_falls_back_to_the_builtin_detector(monkeypatch):
    monkeypatch.setenv("ALPHAHOUND_INTERSPEC_BATCH", r"C:\nowhere\InterSpec_batch.exe")
    result = analyze_spectrum_peaks({"counts": spectrum().tolist(), "energies": AXIS.tolist(), "metadata": {}}, True, 3600.0)
    assert result["analysis_mode"] != "interspec" and result["peaks"]
