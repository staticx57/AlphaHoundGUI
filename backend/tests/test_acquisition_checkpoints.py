"""Every acquisition keeps its own partial file, named by its start time, so a run cut short is never lost or overwritten.

There used to be one shared acquisition_in_progress.n42, written every 5 minutes: a new run overwrote the previous run's
partial data within 5 minutes, and keeping a run interrupted by a restart needed someone to copy the file by hand first."""
import asyncio
import os
import pathlib
import time
from datetime import datetime, timezone

import pytest

import formats.n42_exporter
from devices import acquisition_manager as am_module
from fastapi.testclient import TestClient
from main import app


def _local_stamp(start):
    return start.astimezone().strftime("%Y-%m-%d_%H-%M-%S")


class FakeDevice:
    def is_connected(self):
        return True

    def clear_spectrum(self):
        pass

    def request_spectrum(self):
        pass

    def get_spectrum(self):
        return [(5 + i % 3, 3.0 + 2.9 * i) for i in range(1024)]


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    monkeypatch.setattr(am_module, "SAVE_DIR", str(tmp_path))
    monkeypatch.setattr(am_module, "analyze_spectrum_peaks",
                        lambda result, is_calibrated, live_time=0.0, **kw: {**result, "peaks": [], "isotopes": []})
    m = am_module.AcquisitionManager()
    saved = (m.state, m._device, m._task, m._stop_requested, m._analysis_cache)
    m._analysis_cache = None
    yield m
    m.state, m._device, m._task, m._stop_requested, m._analysis_cache = saved


def _with_spectrum(m, start):
    m.state = am_module.AcquisitionState(status=am_module.AcquisitionStatus.ACQUIRING, start_time=start,
                                         elapsed_seconds=120.0, duration_seconds=3600)
    m.state.last_spectrum_counts = [7] * 1024
    m.state.last_spectrum_energies = [3.0 + 2.9 * i for i in range(1024)]


def test_each_run_checkpoints_to_its_own_file_named_by_its_start(mgr, tmp_path):
    first = datetime(2026, 10, 4, 20, 52, 33, tzinfo=timezone.utc)
    second = datetime(2026, 10, 5, 2, 4, 0, tzinfo=timezone.utc)
    for start in (first, second):
        _with_spectrum(mgr, start)
        asyncio.run(mgr._save_checkpoint())
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == sorted(f"spectrum_{_local_stamp(s)}_in_progress.n42" for s in (first, second))
    assert mgr.get_state()["checkpoint_file"] == f"spectrum_{_local_stamp(second)}_in_progress.n42"


def test_the_partial_file_exists_from_the_first_spectrum_and_is_replaced_by_the_final_one(mgr, tmp_path, monkeypatch):
    monkeypatch.setattr(am_module.AcquisitionManager, "POLL_INTERVAL_S", 0.05)

    async def run():
        await mgr.start(duration_minutes=60, device=FakeDevice())
        partial = None
        for _ in range(100):                                   # the first poll takes about 0.5 s
            await asyncio.sleep(0.05)
            partial = [p.name for p in tmp_path.glob("*_in_progress.n42")]
            if partial:
                break
        await mgr.stop()
        return partial

    partial = asyncio.run(run())
    assert partial == [f"spectrum_{_local_stamp(mgr.state.start_time)}_in_progress.n42"], \
        "no partial file right after the first spectrum: a run cut short in its first minutes would be lost"
    assert not list(tmp_path.glob("*_in_progress.n42")), "the partial file outlived the finished run"
    assert (tmp_path / mgr.state.final_filename).exists()


def test_a_failed_final_save_keeps_the_partial_file(mgr, tmp_path, monkeypatch):
    _with_spectrum(mgr, datetime(2026, 10, 4, 20, 52, 33, tzinfo=timezone.utc))
    mgr._device = None                                          # finalize's last poll is skipped
    asyncio.run(mgr._save_checkpoint())

    def broken(data):
        raise OSError("disk full")
    monkeypatch.setattr(formats.n42_exporter, "generate_n42_xml", broken)
    asyncio.run(mgr._finalize())
    assert mgr.state.status == am_module.AcquisitionStatus.ERROR
    assert list(tmp_path.glob("*_in_progress.n42")), "the only copy of the run was deleted"


def test_the_checkpoint_interval_is_a_minute():
    assert am_module.AcquisitionManager.CHECKPOINT_INTERVAL_S == 60


def test_startup_keeps_stale_partial_files_as_interrupted_and_leaves_live_ones(tmp_path):
    stale = tmp_path / "spectrum_2026-10-04_20-52-33_in_progress.n42"
    live = tmp_path / "spectrum_2026-10-04_22-03-00_in_progress.n42"     # another server is still writing this one
    legacy = tmp_path / "acquisition_in_progress.n42"                     # the old single shared file
    for p in (stale, live, legacy):
        p.write_text("<n42/>", encoding="utf-8")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    os.utime(legacy, (old, old))

    kept = am_module.recover_interrupted_checkpoints(str(tmp_path))

    names = sorted(p.name for p in tmp_path.iterdir())
    legacy_name = "spectrum_" + datetime.fromtimestamp(old).strftime("%Y-%m-%d_%H-%M-%S") + "_interrupted.n42"
    assert names == sorted([live.name, "spectrum_2026-10-04_20-52-33_interrupted.n42", legacy_name])
    assert sorted(kept) == sorted(["spectrum_2026-10-04_20-52-33_interrupted.n42", legacy_name])


def test_a_file_an_older_server_still_writes_every_5_minutes_is_left_alone(tmp_path):
    """Happened: a second (test) server started next to a live run on older code and relabelled its checkpoint."""
    legacy = tmp_path / "acquisition_in_progress.n42"
    legacy.write_text("<n42/>", encoding="utf-8")
    six_minutes_ago = time.time() - 360
    os.utime(legacy, (six_minutes_ago, six_minutes_ago))
    assert am_module.recover_interrupted_checkpoints(str(tmp_path)) == []
    assert legacy.exists()


def test_startup_never_overwrites_an_existing_interrupted_file(tmp_path):
    (tmp_path / "spectrum_2026-10-04_20-52-33_interrupted.n42").write_text("first", encoding="utf-8")
    stale = tmp_path / "spectrum_2026-10-04_20-52-33_in_progress.n42"
    stale.write_text("second", encoding="utf-8")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    am_module.recover_interrupted_checkpoints(str(tmp_path))
    texts = sorted(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
    assert texts == ["first", "second"]


# --- the saved runs, listed and opened from the page ---

def _real_n42():
    return (pathlib.Path(__file__).parent / "data" / "real_spectra" / "spectrum_2025-12-15_takumar_90min.n42").read_text(encoding="utf-8")


def test_saved_runs_are_listed_newest_first_with_their_kind(tmp_path):
    folder = pathlib.Path(am_module.SAVE_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    names = ["spectrum_2026-10-03_10-16-41.n42", "spectrum_2026-10-04_20-52-33_interrupted.n42",
             "spectrum_2026-10-04_22-03-00_in_progress.n42", "notes.txt", "spectrum_x.n42.tmp"]
    for i, name in enumerate(names):
        (folder / name).write_text("<n42/>", encoding="utf-8")
        os.utime(folder / name, (1_000_000 + i, 1_000_000 + i))
    runs = TestClient(app).get("/device/acquisitions").json()["runs"]
    assert [(r["name"], r["kind"]) for r in runs] == [
        ("spectrum_2026-10-04_22-03-00_in_progress.n42", "in_progress"),
        ("spectrum_2026-10-04_20-52-33_interrupted.n42", "interrupted"),
        ("spectrum_2026-10-03_10-16-41.n42", "complete"),
    ]


def test_a_saved_run_opens_like_an_uploaded_file():
    folder = pathlib.Path(am_module.SAVE_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "spectrum_2025-12-15_13-44-46.n42").write_text(_real_n42(), encoding="utf-8")
    r = TestClient(app).get("/device/acquisitions/spectrum_2025-12-15_13-44-46.n42")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["counts"]) == 1024 and "peaks" in data and data["metadata"]["filename"] == "spectrum_2025-12-15_13-44-46.n42"


@pytest.mark.parametrize("name", ["..%2Fmain.py", "..%5C..%5Cmain.py", "missing.n42", "notes.txt"])
def test_only_saved_runs_can_be_opened(name):
    folder = pathlib.Path(am_module.SAVE_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    assert TestClient(app).get(f"/device/acquisitions/{name}").status_code in (400, 404)
