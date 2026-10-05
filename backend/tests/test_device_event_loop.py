"""AlphaHound request handlers keep the event loop free: spectrum analysis and serial I/O run in worker threads.

Found after a 480 minute acquisition went unresponsive (see test_acquisition_event_loop.py): the same pattern, slow work
inside an `async def` handler, also sat in the spectrum endpoints (the auto-refresh timer calls one of them) and in every
handler that writes to the serial port. A write has no upper bound without a write timeout, so a stalled USB link would
have frozen the whole server."""
import asyncio
import time

import pytest

import main
from devices import acquisition_manager as am_module
from devices import alphahound_serial
from routers import device as device_router

SLOW = 0.6
LIMIT = 0.25


def _spectrum():
    return [(10 + (i % 7), 3.0 + 2.9 * i) for i in range(1024)]


@pytest.fixture
def ah(monkeypatch):
    """The real AlphaHound driver object with its I/O replaced: every serial call takes SLOW seconds."""
    dev = device_router.alphahound_device
    calls = []

    def slow(name, result=None):
        def call(*args, **kwargs):
            calls.append(name)
            time.sleep(SLOW)
            return result
        return call

    monkeypatch.setattr(dev, "is_connected", lambda: True)
    monkeypatch.setattr(dev, "get_spectrum", lambda: _spectrum())
    for name in ("request_spectrum", "clear_spectrum", "send_command"):
        monkeypatch.setattr(dev, name, slow(name))
    monkeypatch.setattr(dev, "connect", slow("connect", True))
    monkeypatch.setattr(dev, "disconnect", slow("disconnect"))
    monkeypatch.setattr(dev, "list_ports", slow("list_ports", []))
    return calls


@pytest.fixture
def slow_analysis(monkeypatch):
    def fake(result, is_calibrated, live_time=0.0, **kw):
        time.sleep(SLOW)
        return {**result, "peaks": [], "isotopes": [], "decay_chains": []}
    monkeypatch.setattr(device_router, "analyze_spectrum_peaks", fake)


def max_stall(make_coro):
    """Runs make_coro() next to a 20 ms ticker and returns (result, the longest gap between ticks)."""
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
        result = await make_coro()
        stop.set()
        await task
        return result

    result = asyncio.run(scenario())
    return result, max(gaps)


def test_current_spectrum_reads_and_analyses_off_the_loop(ah, slow_analysis):
    result, stall = max_stall(device_router.get_current_spectrum)
    assert len(result["counts"]) == 1024 and "request_spectrum" in ah
    assert stall < LIMIT, f"GET /device/spectrum/current blocked the event loop for {stall:.2f} s"


def test_get_spectrum_button_reads_and_analyses_off_the_loop(ah, slow_analysis):
    req = device_router.SpectrumRequest(count_minutes=0)
    result, stall = max_stall(lambda: device_router.acquire_spectrum(req))
    assert len(result["counts"]) == 1024
    assert stall < LIMIT, f"POST /device/spectrum blocked the event loop for {stall:.2f} s"


@pytest.mark.parametrize("name,call", [
    ("clear_spectrum", lambda: device_router.clear_spectrum()),
    ("send_command", lambda: device_router.change_display_mode("next")),
    ("connect", lambda: device_router.connect_device(device_router.ConnectRequest(port="COM8"))),
    ("disconnect", lambda: device_router.disconnect_device()),
    ("list_ports", lambda: device_router.list_serial_ports()),
])
def test_serial_handlers_do_not_block_the_loop(ah, monkeypatch, name, call):
    if name == "connect":                                   # otherwise it answers "already connected" without I/O
        monkeypatch.setattr(device_router.alphahound_device, "is_connected", lambda: False)
    _, stall = max_stall(call)
    assert name in ah
    assert stall < LIMIT, f"{name} blocked the event loop for {stall:.2f} s"


def test_the_port_is_opened_with_a_write_timeout(monkeypatch):
    opened = {}

    class FakeSerial:
        is_open = True

        def __init__(self, port, baudrate, **kwargs):
            opened.update(kwargs)

        def close(self):
            pass

    class NoThread:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

    monkeypatch.setattr(alphahound_serial.serial, "Serial", FakeSerial)
    monkeypatch.setattr(alphahound_serial.threading, "Thread", NoThread)
    dev = alphahound_serial.AlphaHoundDevice()
    assert dev.connect("COM99")
    assert opened.get("write_timeout") is not None and 0 < opened["write_timeout"] <= 5, \
        "without a write timeout a stalled USB link blocks write() forever"


class ClosingSocket:
    async def accept(self):
        pass

    async def send_json(self, data):
        from fastapi import WebSocketDisconnect
        raise WebSocketDisconnect()

    async def close(self):
        pass


@pytest.fixture
def last_tab_closes(monkeypatch):
    released = []
    dev = main.alphahound_device
    monkeypatch.setattr(main, "KEEP_CONNECTED", False)
    monkeypatch.setattr(main, "WS_DISCONNECT_GRACE_S", 0)
    monkeypatch.setattr(dev, "is_connected", lambda: True)
    monkeypatch.setattr(dev, "get_dose_rate", lambda: 1.0)
    monkeypatch.setattr(dev, "get_cps", lambda: None)
    monkeypatch.setattr(dev, "get_dose_rate_avg", lambda: None)
    monkeypatch.setattr(dev, "disconnect", lambda *a, **k: released.append(True))
    main.active_websockets.clear()
    mgr = am_module.AcquisitionManager()
    saved = mgr.state
    yield mgr, released
    mgr.state = saved


def test_closing_the_last_tab_still_releases_an_idle_device(last_tab_closes):
    mgr, released = last_tab_closes
    mgr.state = am_module.AcquisitionState(status=am_module.AcquisitionStatus.IDLE)
    asyncio.run(main.websocket_dose_stream(ClosingSocket()))
    assert released == [True]


def test_the_device_is_kept_while_an_acquisition_runs(last_tab_closes):
    """A stalled server drops every tab's WebSocket at once; that must not cut the device out of a running acquisition."""
    mgr, released = last_tab_closes
    mgr.state = am_module.AcquisitionState(status=am_module.AcquisitionStatus.ACQUIRING)
    asyncio.run(main.websocket_dose_stream(ClosingSocket()))
    assert released == []
