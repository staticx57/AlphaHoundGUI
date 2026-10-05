"""A live acquisition's spectrum is analysed in a worker thread, once per new spectrum.
The UI polls /device/acquisition/status every 2 s and each poll used to run the full analysis on the event loop.
By 1963 s into a 480 minute AlphaHound run (607k counts) one analysis took 2.0 s, the polls queued up behind each
other and the server stopped answering: the acquisition loop itself was starved and the UI looked crashed."""
import asyncio
import time
from datetime import datetime, timezone

import pytest

from devices import acquisition_manager as am_module
from routers import device as device_router


@pytest.fixture
def mgr():
    m = am_module.AcquisitionManager()
    saved = (m.state, m._is_calibrated, m._source_name, m._instrument, m._device, getattr(m, "_analysis_cache", None))
    m.state = am_module.AcquisitionState(status=am_module.AcquisitionStatus.ACQUIRING, elapsed_seconds=1963.0,
                                         start_time=datetime.now(timezone.utc),
                                         duration_seconds=480 * 60)
    m.state.last_spectrum_counts = [10] * 1024
    m.state.last_spectrum_energies = [float(i) for i in range(1024)]
    m._analysis_cache = None
    yield m
    m.state, m._is_calibrated, m._source_name, m._instrument, m._device, m._analysis_cache = saved


@pytest.fixture
def slow_analysis(monkeypatch):
    calls = []

    def fake(result, is_calibrated, live_time=0.0, **kw):
        calls.append(live_time)
        time.sleep(0.6)
        return {**result, "peaks": [{"energy": 661.7}], "isotopes": []}

    monkeypatch.setattr(am_module, "analyze_spectrum_peaks", fake)
    return calls


def _run_with_ticker(coro_fn):
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
        await asyncio.sleep(0.1)
        result = await coro_fn()
        stop.set()
        await task
        return result

    return asyncio.run(scenario()), gaps


def test_status_polls_do_not_block_the_event_loop(mgr, slow_analysis):
    async def three_tabs_polling():
        return await asyncio.gather(*(device_router.get_acquisition_status() for _ in range(3)))

    states, gaps = _run_with_ticker(three_tabs_polling)
    assert all(s["spectrum_data"]["peaks"] == [{"energy": 661.7}] for s in states)
    assert max(gaps) < 0.25, f"the event loop was blocked for {max(gaps):.2f} s by the acquisition status"
    assert len(slow_analysis) == 1, "concurrent polls of one spectrum must share a single analysis"


def test_an_unchanged_spectrum_is_not_analysed_again(mgr, slow_analysis):
    asyncio.run(device_router.get_acquisition_status())
    asyncio.run(device_router.get_acquisition_data())
    assert len(slow_analysis) == 1
    mgr.state.last_spectrum_counts = [11] * 1024          # the next spectrum from the device
    data = asyncio.run(device_router.get_acquisition_data())
    assert len(slow_analysis) == 2 and data["counts"][0] == 11


def test_a_checkpoint_does_not_block_the_event_loop(mgr, slow_analysis, tmp_path, monkeypatch):
    monkeypatch.setattr(am_module, "SAVE_DIR", str(tmp_path))
    _, gaps = _run_with_ticker(mgr._save_checkpoint)
    assert list(tmp_path.glob("spectrum_*_in_progress.n42"))
    assert max(gaps) < 0.25, f"the event loop was blocked for {max(gaps):.2f} s by the checkpoint"
