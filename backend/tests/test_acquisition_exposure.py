"""Exposure during an acquisition = integrated instrument dose rate (valid for mixed sources)."""
import pytest

import acquisition_manager as am


@pytest.fixture
def mgr():
    m = am.AcquisitionManager()
    saved = (m.state, m._dose_rate_fn)
    m.state = am.AcquisitionState()
    m._dose_rate_fn = lambda: None
    yield m
    m.state, m._dose_rate_fn = saved


def test_constant_rate_integrates_to_rate_times_time(mgr):
    for i in range(0, 3601, 2):            # 1 hour of readings every 2 s at 3.6 uSv/h
        mgr.record_dose_rate(3.6, float(i))
    e = mgr.exposure_summary()
    assert e["exposure_uSv"] == pytest.approx(3.6, rel=1e-6)
    assert e["mean_dose_rate_uSv_h"] == pytest.approx(3.6)
    assert e["covered_seconds"] == pytest.approx(3600)


def test_trapezoid_on_ramp(mgr):
    mgr.record_dose_rate(0.0, 0.0)
    mgr.record_dose_rate(7.2, 10.0)        # linear ramp 0 -> 7.2 uSv/h over 10 s
    assert mgr.exposure_summary()["exposure_uSv"] == pytest.approx(0.5 * 7.2 * 10 / 3600)
    assert mgr.exposure_summary()["max_dose_rate_uSv_h"] == pytest.approx(7.2)


def test_gaps_and_bad_readings_are_not_integrated(mgr):
    mgr.record_dose_rate(1.0, 0.0)
    mgr.record_dose_rate(None, 2.0)        # missing reading
    mgr.record_dose_rate(float("nan"), 3.0)
    mgr.record_dose_rate(-5.0, 4.0)
    mgr.record_dose_rate(1.0, 100.0)       # 100 s gap > MAX_DOSE_GAP_S: not integrated
    e = mgr.exposure_summary()
    assert e["exposure_uSv"] == 0.0 and e["covered_seconds"] == 0.0 and e["samples"] == 2


def test_no_dose_source_means_no_exposure(mgr):
    mgr._dose_rate_fn = None
    mgr.record_dose_rate(1.0, 0.0)
    assert mgr.exposure_summary() is None


def test_exposure_formatting():
    assert am.format_exposure({"exposure_uSv": 0.0421, "mean_dose_rate_uSv_h": 0.25, "max_dose_rate_uSv_h": 0.9}) \
        == "42.1 nSv (mean 0.250, max 0.900 µSv/h)"
    assert am.format_exposure({"exposure_uSv": 2.5, "mean_dose_rate_uSv_h": 1, "max_dose_rate_uSv_h": 2}).startswith("2.500 µSv")


def test_alphahound_dose_rate_converted_from_urem(monkeypatch):
    from routers import device as d
    monkeypatch.setattr(d.alphahound_device, "is_connected", lambda: True)
    monkeypatch.setattr(d.alphahound_device, "get_dose_rate", lambda: 25.0)   # 25 uRem/h
    assert d.alphahound_dose_rate_uSv_h() == pytest.approx(0.25)


def test_radiacode_dose_rate_uses_newest_reading_and_caches(monkeypatch):
    import radiacode_driver as rd

    class Rt:
        def __init__(self, v):
            self.dose_rate = v

    monkeypatch.setattr(rd, "RealTimeData", Rt)
    batches = [[Rt(1e-5), Rt(3e-5)], []]

    class Dev:
        def data_buf(self):
            return batches.pop(0)

    drv = rd.RadiacodeDevice()
    drv._device = Dev()
    assert drv.get_dose_rate() == pytest.approx(0.3)   # newest of the batch, uSv/h
    assert drv.get_dose_rate() == pytest.approx(0.3)   # empty batch -> cached value


def test_radiacode_cumulative_dose_from_raredata(monkeypatch):
    import radiacode_driver as rd

    class Rt:
        def __init__(self, v):
            self.dose_rate = v

    class Rare:
        def __init__(self, d):
            self.dose = d

    monkeypatch.setattr(rd, "RealTimeData", Rt)
    monkeypatch.setattr(rd, "RareData", Rare)
    batches = [[Rt(1e-5), Rare(2.5e-4)], [Rt(1e-5)]]

    class Dev:
        def data_buf(self):
            return batches.pop(0)

    drv = rd.RadiacodeDevice()
    drv._device = Dev()
    assert drv.get_accumulated_dose() is None          # nothing received yet
    drv.get_dose_rate()
    assert drv.get_accumulated_dose_raw() == pytest.approx(2.5e-4)
    assert drv.get_accumulated_dose() == pytest.approx(2.5)   # same x10,000 scale as dose rate
    drv.get_dose_rate()                                 # batch without RareData keeps last value
    assert drv.get_accumulated_dose() == pytest.approx(2.5)


def test_dose_counter_self_check(monkeypatch):
    """dose / duration should reproduce the mean dose rate when the x10,000 scale is right."""
    import radiacode_driver as rd

    class Rt:
        def __init__(self, v):
            self.dose_rate = v

    class Rare:
        def __init__(self, d, dur):
            self.dose, self.duration = d, dur

    monkeypatch.setattr(rd, "RealTimeData", Rt)
    monkeypatch.setattr(rd, "RareData", Rare)
    # 1.36 uSv/h for 600 s -> 0.2267 uSv -> raw 2.267e-5 in device units (roentgen)
    batches = [[Rt(1.36e-4), Rare(0.2267e-4, 600)]]

    class Dev:
        def data_buf(self):
            return batches.pop(0)

    drv = rd.RadiacodeDevice()
    drv._device = Dev()
    drv.get_dose_rate()
    info = drv.get_dose_counter_info()
    assert info["accumulation_seconds"] == 600
    assert info["implied_mean_rate_uSv_h"] == pytest.approx(1.36, rel=0.01)
    assert info["current_dose_rate_uSv_h"] == pytest.approx(1.36, rel=0.01)


@pytest.mark.parametrize("value,expected", [
    ("auto", "AUTO"), ("right", "RIGHT"), ("left", "LEFT"), ("normal", "RIGHT"), ("reversed", "LEFT"),
])
def test_display_direction_maps_to_device_enum(value, expected):
    """Orientation never worked: it imported DisplayDirection from the wrong module/members."""
    import radiacode_driver as rd
    sent = {}

    class Dev:
        def set_display_direction(self, d):
            sent["d"] = d

    drv = rd.RadiacodeDevice()
    drv._device = Dev()
    assert drv.set_display_direction(value) is True
    assert sent["d"].name == expected


def test_display_direction_rejects_unknown():
    import radiacode_driver as rd

    class Dev:
        def set_display_direction(self, d):
            raise AssertionError("must not be called")

    drv = rd.RadiacodeDevice()
    drv._device = Dev()
    assert drv.set_display_direction("sideways") is False


def test_dose_register_preferred_and_converted_from_microroentgen(monkeypatch):
    import radiacode_driver as rd

    class Dev:
        def _batch_read_vsfrs(self, regs):
            assert [r.name for r in regs] == ["DS_uR"]
            return [137]                     # 137 uR

        def data_buf(self):
            return []

    drv = rd.RadiacodeDevice()
    drv._device = Dev()
    assert drv.read_dose_register_uR() == 137
    info = drv.get_dose_counter_info()
    assert info["source"] == "DS_uR register"
    assert info["dose_uSv"] == pytest.approx(1.37)


def test_dose_register_failure_falls_back_to_raredata():
    import radiacode_driver as rd

    class Dev:
        def _batch_read_vsfrs(self, regs):
            raise ValueError("Unexpected validity flags")

    drv = rd.RadiacodeDevice()
    drv._device = Dev()
    drv._last_rare_dose_raw = 2.0e-4
    info = drv.get_dose_counter_info()
    assert info["register_uR"] is None and info["source"] == "RareData"
    assert info["dose_uSv"] == pytest.approx(2.0)


def test_session_dose_integrates_new_readings_and_resets(monkeypatch):
    import radiacode_driver as rd

    class Rt:
        def __init__(self, v):
            self.dose_rate = v

    monkeypatch.setattr(rd, "RealTimeData", Rt)
    clock = {"t": 1000.0}
    monkeypatch.setattr(rd.time, "monotonic", lambda: clock["t"])

    class Dev:
        def __init__(self):
            self.queue = []
            self.resets = 0

        def data_buf(self):
            q, self.queue = self.queue, []
            return q

        def dose_reset(self):
            self.resets += 1

    dev = Dev()
    drv = rd.RadiacodeDevice()
    drv._device = dev
    for i in range(0, 3601, 2):                       # 1 h at 3.6 uSv/h, a reading every 2 s
        clock["t"] = 1000.0 + i
        dev.queue = [Rt(3.6e-4)]
        drv.get_dose_rate()
    s = drv.get_session_dose()
    assert s["dose_uSv"] == pytest.approx(3.6, rel=1e-3) and s["covered_seconds"] == pytest.approx(3600)

    # cached repeats (no new record) must not add dose
    clock["t"] += 5
    drv.get_dose_rate()
    assert drv.get_session_dose()["dose_uSv"] == pytest.approx(3.6, rel=1e-3)

    # a long gap is not integrated; Reset Dose clears the session and resets the device
    clock["t"] += 600
    dev.queue = [Rt(3.6e-4)]
    drv.get_dose_rate()
    assert drv.get_session_dose()["dose_uSv"] == pytest.approx(3.6, rel=1e-3)
    assert drv.reset_dose() is True and dev.resets == 1
    assert drv.get_session_dose()["dose_uSv"] == 0.0


def test_time_metadata_explained_and_includes_device_duration():
    m = am.AcquisitionManager()
    saved = (m.state, m._device)
    try:
        m.state = am.AcquisitionState(elapsed_seconds=90.0, device_duration_s=89.4,
                                      last_spectrum_counts=[1] * 8, last_spectrum_energies=[float(i) for i in range(8)])
        md = m._time_metadata()
        assert md["device_duration_s"] == 89.4
        assert "dead time" in md["time_notes"] and "wall-clock" in md["time_notes"]
        m.state.device_duration_s = None
        assert "device_duration_s" not in m._time_metadata()
    finally:
        m.state, m._device = saved


def test_radiacode_adapter_exposes_device_duration(monkeypatch):
    from routers import device as d
    monkeypatch.setattr(d.radiacode_device, "get_spectrum",
                        lambda: ([1, 2, 3], [1.0, 2.0, 3.0], {"duration_s": 61.5, "calibration_source": "device"}))
    dev = d.RadiacodeAcquisitionDevice()
    assert dev.get_spectrum() == [(1, 1.0), (2, 2.0), (3, 3.0)]
    assert dev.device_duration_s == 61.5


def test_radiacode_logs_device_events_and_flags_alarms(monkeypatch):
    import radiacode_driver as rd

    class Ev:
        def __init__(self, name, param=0):
            self.event = type("E", (), {"name": name})()
            self.dt = None
            self.event_param1 = param
            self.flags = 0

    monkeypatch.setattr(rd, "Event", Ev)
    batches = [[Ev("DOSE_RATE_ALARM1"), Ev("DOSE_RESET")], [Ev("CHARGE_START")]]

    class Dev:
        def data_buf(self):
            return batches.pop(0)

    drv = rd.RadiacodeDevice()
    drv._device = Dev()
    drv.get_dose_rate()
    evs = drv.get_events()
    assert [(e["name"], e["alarm"]) for e in evs] == [("DOSE_RATE_ALARM1", True), ("DOSE_RESET", False)]
    drv.get_dose_rate()
    assert [e["name"] for e in drv.get_events(since_id=2)] == ["CHARGE_START"]


def test_radiacode_alarm_limits_read_register_by_register(monkeypatch):
    import radiacode_driver as rd

    class V:
        CR_LEV1_cp10s, CR_LEV2_cp10s, DR_LEV1_uR_h, DR_LEV2_uR_h = 1, 2, 3, 4
        DS_LEV1_uR, DS_LEV2_uR, DS_UNITS, CR_UNITS = 5, 6, 7, 8

    values = {1: 100, 2: 200, 3: 2000, 4: 4000, 5: 1_000_000, 6: 2_000_000, 7: 0, 8: 0}

    class Dev:
        def _batch_read_vsfrs(self, regs):
            assert len(regs) == 1            # BLE rejects the 8-register batch
            if regs[0] == 6:
                raise IOError("unsupported")
            return [values[regs[0]]]

    monkeypatch.setattr(rd, "VSFR", V)
    drv = rd.RadiacodeDevice()
    assert drv.get_alarm_limits() is None
    drv._device = Dev()
    lim = drv.get_alarm_limits()
    assert lim["l1_dose_rate"] == 2000 and lim["l2_dose_rate"] == 4000
    assert lim["l1_count_rate"] == 10.0 and lim["count_unit"] == "cps"
    assert lim["l1_dose"] == 1.0 and lim["l2_dose"] is None and lim["dose_unit"] == "R"
