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
