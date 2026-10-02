"""AlphaHound serial driver against a fake serial port: existing behaviour must not regress,
and the new CPS / dose-log / probe / connect-error features must work."""
import threading
import time

import pytest

import alphahound_serial as ah


class FakeSerial:
    """Minimal pyserial stand-in. Replies are queued by `reply(cmd) -> bytes`."""

    def __init__(self, reply=None):
        self.is_open = True
        self._buf = b""
        self._lock = threading.Lock()
        self.writes = []                  # (monotonic time, bytes)
        self._reply = reply or (lambda cmd: b"")
        self.fail_writes = False

    @property
    def in_waiting(self):
        with self._lock:
            return len(self._buf)

    def read(self, n):
        with self._lock:
            out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def feed(self, data: bytes):
        with self._lock:
            self._buf += data

    def write(self, data):
        if self.fail_writes:
            raise IOError("write failed")
        self.writes.append((time.monotonic(), bytes(data)))
        self.feed(self._reply(bytes(data)))

    def close(self):
        self.is_open = False


def spectrum_reply(counts=3):
    lines = ["Full 1024-int Array received:", "Temp:28.62", "CompFactor:0.95", "Comp"]
    lines += [f"{counts},{10 + i * 1.77:.2f}" for i in range(1024)]
    return ("\n".join(lines) + "\n").encode()


def default_reply(cmd):
    if cmd == b"DB":
        return b"12.5\n"
    if cmd == b"P":
        return b"CPS:5.0,1.5,0.5,12.5\n"
    if cmd == b"G":
        return spectrum_reply()
    return b""


@pytest.fixture(autouse=True)
def quick_stream_detection(monkeypatch):
    monkeypatch.setattr(ah, "STREAM_DETECT_S", 0.1)
    monkeypatch.setattr(ah, "SPECTRUM_TIMEOUT_S", 0.6)


class Streamer:
    """Feeds one bare dose line every `period` seconds, like the device's own stream."""

    def __init__(self, fake, value=65.0, period=0.1):
        self.fake, self.value, self.period = fake, value, period
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            self.fake.feed((f"{self.value}" + chr(10)).encode())
            time.sleep(self.period)


@pytest.fixture
def dev():
    d = ah.AlphaHoundDevice()
    yield d
    d.stop_event.set()
    time.sleep(0.15)


def start(d, fake):
    d.serial_conn = fake
    d.stop_event.clear()
    t = threading.Thread(target=d._read_worker, daemon=True)
    t.start()
    return t


def wait_for(cond, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


# ---------- existing behaviour (must not regress) ----------

def test_dose_polling_uses_DB_and_parses_dose(dev):
    fake = FakeSerial(default_reply)
    start(dev, fake)
    assert wait_for(lambda: dev.get_dose_rate() == 12.5)
    assert any(w == b"DB" for _, w in fake.writes)


def test_dose_callback_fires(dev):
    seen = []
    dev.dose_callback = seen.append
    start(dev, FakeSerial(default_reply))
    assert wait_for(lambda: seen)
    assert seen[0] == 12.5


def test_spectrum_with_temperature_and_comp_factor(dev):
    fake = FakeSerial(default_reply)
    start(dev, fake)
    dev.request_spectrum()
    assert wait_for(lambda: len(dev.get_spectrum()) == 1024)
    spec = dev.get_spectrum()
    assert spec[0] == (3.0, 10.0) and spec[1][1] == pytest.approx(11.77)
    assert dev.get_temperature() == pytest.approx(28.62)
    assert dev.get_comp_factor() == pytest.approx(0.95)
    assert any(w == b"G" for _, w in fake.writes)


def test_clear_spectrum_sends_W_and_empties(dev):
    fake = FakeSerial(default_reply)
    dev.serial_conn = fake
    dev.spectrum = [(1.0, 1.0)]
    dev.clear_spectrum()
    assert dev.get_spectrum() == [] and fake.writes[-1][1] == b"W"


def test_send_command_writes_bytes(dev):
    fake = FakeSerial()
    dev.serial_conn = fake
    dev.send_command("E")
    dev.send_command("Q")
    assert [w for _, w in fake.writes] == [b"E", b"Q"]


def test_write_failure_retries_then_disconnects(dev, monkeypatch):
    monkeypatch.setattr(ah.time, "sleep", lambda s: None)
    fake = FakeSerial()
    fake.fail_writes = True
    dev.serial_conn = fake
    dev._write(b"DB")
    assert dev.serial_conn is None and not fake.is_open


def test_is_connected_and_disconnect_reset(dev):
    fake = FakeSerial()
    dev.serial_conn = fake
    dev.current_dose = 5.0
    dev.cps = {"gamma": 1.0, "beta": 0.0, "alpha": 0.0}
    assert dev.is_connected()
    dev.disconnect()
    assert not dev.is_connected() and dev.get_dose_rate() == 0.0 and dev.get_cps() is None


# ---------- CPS parsing ----------

@pytest.mark.parametrize("line,expected", [
    ("CPS:12.5,3.0,0.5", {"gamma": 12.5, "beta": 3.0, "alpha": 0.5}),
    ("CPS:1,2,3,4.5", {"gamma": 1.0, "beta": 2.0, "alpha": 3.0, "dose": 4.5}),
    ("CPS: 1 , 2 , 3 ", {"gamma": 1.0, "beta": 2.0, "alpha": 3.0}),
    ("CPS:1,2,3,abc", {"gamma": 1.0, "beta": 2.0, "alpha": 3.0}),
])
def test_parse_cps_line_valid(line, expected):
    assert ah.parse_cps_line(line) == expected


@pytest.mark.parametrize("line", ["", "12.5", "CPS:", "CPS:1,2", "CPS:a,b,c", "CPS:nan,1,2", "CPS:inf,1,2", "cps:1,2,3",
                                  "Temp:28.6", "0,10.00"])
def test_parse_cps_line_rejects(line):
    assert ah.parse_cps_line(line) is None


def test_get_cps_totals_and_goes_stale(dev):
    dev.cps = {"gamma": 5.0, "beta": 1.5, "alpha": 0.5}
    dev.cps_time = time.monotonic()
    cps = dev.get_cps()
    assert cps["total"] == pytest.approx(7.0) and cps["age_s"] >= 0
    dev.cps_time = time.monotonic() - 10
    assert dev.get_cps() is None
    assert dev.get_cps(max_age_s=60) is not None


# ---------- polling behaviour ----------

def test_P_is_polled_after_DB_and_never_back_to_back(dev):
    fake = FakeSerial(default_reply)
    start(dev, fake)
    assert wait_for(lambda: sum(1 for _, w in fake.writes if w == b"P") >= 2, timeout=5)
    cmds = [(t, w) for t, w in fake.writes if w in (b"DB", b"P")]
    assert any(w == b"DB" for _, w in cmds)
    for (t1, c1), (t2, c2) in zip(cmds, cmds[1:]):
        if c1 != c2:
            assert t2 - t1 >= 0.4, f"{c1}->{c2} only {t2 - t1:.2f}s apart"
    assert dev.get_cps()["gamma"] == 5.0 and dev.get_cps()["dose"] == 12.5


def test_poll_cps_can_be_disabled(dev):
    dev.poll_cps = False
    fake = FakeSerial(default_reply)
    start(dev, fake)
    assert wait_for(lambda: any(w == b"DB" for _, w in fake.writes))
    time.sleep(1.3)
    assert not any(w == b"P" for _, w in fake.writes)


def test_cps_line_inside_a_spectrum_is_not_a_channel_row(dev):
    rows = "\n".join(f"1,{10 + i}" for i in range(500)) + "\nCPS:9,9,9\n" + "\n".join(f"1,{600 + i}" for i in range(524)) + "\n"
    fake = FakeSerial(lambda cmd: (b"Comp\n" + rows.encode()) if cmd == b"G" else b"")
    start(dev, fake)
    dev.request_spectrum()
    assert wait_for(lambda: len(dev.get_spectrum()) == 1024)
    assert len(dev.get_spectrum()) == 1024 and dev.get_cps()["gamma"] == 9.0


def test_cps_callback_receives_reading(dev):
    got = []
    dev.cps_callback = got.append
    start(dev, FakeSerial(default_reply))
    assert wait_for(lambda: got)
    assert got[0]["total"] == pytest.approx(7.0)


# ---------- dose log ----------

def test_dose_log_records_readings_with_cps_and_clears(dev):
    start(dev, FakeSerial(default_reply))
    assert wait_for(lambda: len(dev.get_dose_log()) >= 2 and dev.get_cps(), timeout=6)
    log = dev.get_dose_log()
    assert all(row["dose_rate"] == 12.5 and row["time"] > 1e9 for row in log)
    assert any(row["gamma"] == 5.0 for row in log)
    n = dev.clear_dose_log()
    assert n >= 2 and len(dev.get_dose_log()) <= 1  # a new reading may land immediately


def test_dose_log_is_bounded(dev):
    from collections import deque
    dev.dose_log = deque(maxlen=5)
    for i in range(20):
        dev._log_dose(float(i), now=1000.0 + i * 2)   # two seconds apart: one row each
    assert [r["dose_rate"] for r in dev.get_dose_log()] == [15.0, 16.0, 17.0, 18.0, 19.0]


def test_dose_log_is_one_averaged_row_per_second(dev):
    for i, v in enumerate([60.0, 70.0, 80.0, 50.0, 90.0]):
        dev._log_dose(v, now=2000.0 + i * 0.2)        # five readings inside one second
    log = dev.get_dose_log()
    assert len(log) == 1 and log[0]["dose_rate"] == 60.0           # the first reading opens the window
    dev._log_dose(100.0, now=2001.5)
    log = dev.get_dose_log()
    assert len(log) == 2 and log[1]["dose_rate"] == pytest.approx((70 + 80 + 50 + 90 + 100) / 5)


# ---------- the device's own dose stream vs command replies ----------

def stream_reply(cmd):
    if cmd == b"P":
        return b"CPS:271.25,151.96,6.37,707.29" + bytes([10])   # the dose field is ~10x the streamed value
    if cmd in (b"D", b"DA", b"DB"):
        return b"710.23" + bytes([10])
    return b""


def test_stream_mode_never_polls_DB_and_keeps_the_streamed_dose(dev):
    fake = FakeSerial(stream_reply)
    streamer = Streamer(fake, 65.0)
    try:
        start(dev, fake)
        assert wait_for(lambda: sum(1 for _, w in fake.writes if w == b"P") >= 2, timeout=5)
        assert not any(w == b"DB" for _, w in fake.writes)
        assert dev.get_dose_rate() == 65.0                 # never the 700-scale values from P / D replies
        assert dev.get_cps()["dose"] == 707.29             # still available, untouched, from the tagged line
    finally:
        streamer.stop.set()


def test_firmware_without_a_stream_falls_back_to_polling_DB(dev):
    fake = FakeSerial(default_reply)                        # no unsolicited numbers at all
    start(dev, fake)
    assert wait_for(lambda: dev.get_dose_rate() == 12.5, timeout=5)
    assert any(w == b"DB" for _, w in fake.writes)


def test_probe_reply_does_not_disturb_the_dose_value(dev):
    fake = FakeSerial(stream_reply)
    streamer = Streamer(fake, 65.0)
    try:
        start(dev, fake)
        assert wait_for(lambda: dev.get_dose_rate() == 65.0)
        lines = dev.probe("DB", wait_s=0.5)
        assert "710.23" in lines                           # the raw reply is returned to the caller
        assert dev.get_dose_rate() == 65.0                 # but it never became the dose rate
    finally:
        streamer.stop.set()


def test_dose_callback_only_sees_stream_values_in_stream_mode(dev):
    seen = []
    dev.dose_callback = seen.append
    fake = FakeSerial(stream_reply)
    streamer = Streamer(fake, 65.0)
    try:
        start(dev, fake)
        assert wait_for(lambda: len(seen) >= 5)
        time.sleep(1.2)                                    # long enough for P replies to have arrived
    finally:
        streamer.stop.set()
    assert set(seen) == {65.0}


# ---------- probe ----------

def test_probe_returns_only_the_commands_reply_and_pauses_polling(dev):
    fake = FakeSerial(lambda cmd: {b"D": b"10.96\n", b"DA": b"9.36\n", b"DB": b"11.55\n"}.get(cmd, b""))
    start(dev, fake)
    assert wait_for(lambda: any(w == b"DB" for _, w in fake.writes))
    lines = dev.probe("DA", wait_s=0.5)
    assert lines == ["9.36"]
    t0 = next(t for t, w in fake.writes if w == b"DA")
    # no poll commands while the probe was running
    assert not [1 for t, w in fake.writes if w in (b"DB", b"P") and t0 - 0.35 < t < t0 + 0.5]
    assert not dev._poll_paused.is_set()


@pytest.mark.parametrize("bad", ["A", "B", "RA", "W", "G", "E", "X", ""])
def test_probe_rejects_commands_outside_the_whitelist(dev, bad):
    dev.serial_conn = FakeSerial()
    with pytest.raises(ValueError):
        dev.probe(bad)


def test_probe_requires_connection(dev):
    with pytest.raises(RuntimeError):
        dev.probe("D")


# ---------- connect errors ----------

def test_connect_permission_error_gives_clear_message(dev, monkeypatch):
    def boom(*a, **k):
        raise PermissionError(13, "Access is denied.", None, 5)
    monkeypatch.setattr(ah.serial, "Serial", boom)
    assert dev.connect("COM8") is False
    assert dev.port_busy and "COM8" in dev.get_last_error() and "in use" in dev.get_last_error()
    assert dev.serial_conn is None


def test_connect_other_error_is_reported_and_clears_flags(dev, monkeypatch):
    def boom(*a, **k):
        raise OSError("could not open port 'COM9': FileNotFoundError(2)")
    monkeypatch.setattr(ah.serial, "Serial", boom)
    assert dev.connect("COM9") is False
    assert not dev.port_busy and "COM9" in dev.get_last_error()

    class Ok(FakeSerial):
        pass
    monkeypatch.setattr(ah.serial, "Serial", lambda *a, **k: Ok(default_reply))
    assert dev.connect("COM9") is True
    assert dev.get_last_error() is None and not dev.port_busy
    dev.disconnect()


def test_temperature_and_comp_factor_arrive_without_anyone_asking_for_a_spectrum(dev):
    start(dev, FakeSerial(default_reply))
    assert wait_for(lambda: dev.get_temperature() is not None, timeout=4)
    assert dev.get_temperature() == pytest.approx(28.62) and dev.get_comp_factor() == pytest.approx(0.95)
    assert len(dev.get_spectrum()) == 1024


def test_an_unanswered_spectrum_request_does_not_stall_polling_forever(dev):
    fake = FakeSerial(lambda cmd: b"CPS:1,2,3,4" + bytes([10]) if cmd == b"P" else b"")   # G is never answered
    start(dev, fake)
    dev.request_spectrum()
    assert dev.collecting_spectrum
    assert wait_for(lambda: dev.get_cps() is not None, timeout=5)   # P polling resumed after the timeout
