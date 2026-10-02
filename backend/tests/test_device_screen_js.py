"""Display replica logic (static/js/device_screen.js) run under Node: slots, stepping, formatting helpers.

Skipped when Node is not installed. The drawing itself is covered by the browser smoke test."""
import json
import pathlib
import shutil
import subprocess

import pytest

MODULE = pathlib.Path(__file__).resolve().parents[1] / "static" / "js" / "device_screen.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(tmp_path, body):
    script = tmp_path / "t.mjs"
    script.write_text(
        f"import * as m from '{MODULE.as_uri()}';\n"
        "const out = {};\n" + body + "\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_default_slots_and_wrapping_steps(tmp_path):
    out = run_js(tmp_path, """
        const s = new m.DeviceScreen(null);
        out.defaults = s.slots; out.first = s.mode.id; out.idx0 = s.slotIndex;
        out.fwd = []; for (let i = 0; i < 5; i++) { s.step(1); out.fwd.push(s.slotIndex); }
        out.back = []; for (let i = 0; i < 5; i++) { s.step(-1); out.back.push(s.slotIndex); }
    """)
    assert out["defaults"] == [4, 9, 1, 3] and out["first"] == 4 and out["idx0"] == 0
    assert out["fwd"] == [1, 2, 3, 0, 1]                       # the device's E button cycles its four slots
    assert out["back"] == [0, 3, 2, 1, 0]                      # Q goes the other way and wraps


def test_stepping_follows_the_slots_not_all_modes(tmp_path):
    out = run_js(tmp_path, """
        const s = new m.DeviceScreen(null);
        out.seen = []; for (let i = 0; i < 5; i++) { out.seen.push(s.mode.id); s.step(1); }
        out.allModes = m.SCREEN_MODES.length;
    """)
    assert out["seen"] == [4, 9, 1, 3, 4]                      # four stops, then back to the start
    assert out["allModes"] == 12


def test_set_mode_changes_only_the_current_slot(tmp_path):
    out = run_js(tmp_path, """
        const s = new m.DeviceScreen(null);
        s.step(1); const ok = s.setMode(11);
        out.ok = ok; out.slots = s.slots; out.mode = s.mode.id;
        out.badMode = s.setMode(99); out.badSlot = s.setSlot(4); out.badSlot2 = s.setSlot(-1);
        out.badSlotMode = s.setSlotMode(7, 4); out.slotsAfter = s.slots;
        out.setSlot = s.setSlot(3); out.idx = s.slotIndex; out.modeAtM4 = s.mode.id;
    """)
    assert out["ok"] is True and out["slots"] == [4, 11, 1, 3] and out["mode"] == 11
    assert out["badMode"] is False and out["badSlot"] is False and out["badSlot2"] is False
    assert out["badSlotMode"] is False and out["slotsAfter"] == [4, 11, 1, 3]
    assert out["setSlot"] is True and out["idx"] == 3 and out["modeAtM4"] == 3


def test_mode_change_callback_reports_mode_and_slot(tmp_path):
    out = run_js(tmp_path, """
        const s = new m.DeviceScreen(null); out.calls = [];
        s.onModeChange = (mode, slot) => out.calls.push([mode.id, slot]);
        s.step(1); s.setMode(2); s.setSlot(3);
    """)
    assert out["calls"] == [[9, 1], [2, 1], [3, 3]]


def test_sanitize_slots(tmp_path):
    out = run_js(tmp_path, """
        out.good = m.sanitizeSlots([1, 2, 3, 4]);
        out.strings = m.sanitizeSlots(['4', '9', '1', '3']);
        out.short = m.sanitizeSlots([1, 2]); out.unknown = m.sanitizeSlots([1, 2, 3, 8]);
        out.nul = m.sanitizeSlots(null); out.junk = m.sanitizeSlots('abcd');
    """)
    assert out["good"] == [1, 2, 3, 4] and out["strings"] == [4, 9, 1, 3]
    assert out["short"] == out["unknown"] == out["nul"] == out["junk"] == [4, 9, 1, 3]   # mode 8 does not exist


def test_sleep_dose_digits(tmp_path):
    out = run_js(tmp_path, """
        out.a = m.formatSleepDose(3, 'uRem'); out.b = m.formatSleepDose(358.4, 'uRem');
        out.c = m.formatSleepDose(null, 'uRem'); out.d = m.formatSleepDose(358, 'uSv');
        out.e = m.formatSleepDose(1234, 'uRem'); out.f = m.formatSleepDose(-5, 'uRem');
    """)
    assert out == {"a": "003", "b": "358", "c": "---", "d": "004", "e": "1234", "f": "000"}


def test_dose_and_rate_formatting(tmp_path):
    out = run_js(tmp_path, """
        out.d1 = m.formatDose(1.4, 'uRem'); out.d2 = m.formatDose(63.04, 'uRem'); out.d3 = m.formatDose(258, 'uRem');
        out.d4 = m.formatDose(140, 'uSv'); out.d5 = m.formatDose(null, 'uSv');
        out.r1 = m.formatRate(86.289); out.r2 = m.formatRate(2220.4); out.r3 = m.formatRate(null);
    """)
    assert out["d1"] == {"value": "1.40", "unit": "uRem/h"} and out["d2"] == {"value": "63.0", "unit": "uRem/h"}
    assert out["d3"] == {"value": "258", "unit": "uRem/h"} and out["d4"] == {"value": "1.40", "unit": "uSv"}
    assert out["d5"] == {"value": "--", "unit": "uSv"}
    assert out["r1"] == "86.29" and out["r2"] == "2220" and out["r3"] == "--"


def test_sparkle_density_window_average_and_binning(tmp_path):
    out = run_js(tmp_path, """
        out.z = m.sparkleDensity(0); out.neg = m.sparkleDensity(-3); out.hi = m.sparkleDensity(1e6);
        out.mid = m.sparkleDensity(100) > 0.6 && m.sparkleDensity(100) < 0.65;
        const hist = [{t: 0, total: 10}, {t: 5000, total: 20}, {t: 9000, total: 30}];
        out.avg = m.windowAverage(hist, 10000, 6); out.none = m.windowAverage(hist, 100000, 6);
        out.alpha = m.windowAverage([{t: 9000, alpha: 4}, {t: 9500, alpha: 6}], 10000, 5, (h) => h.alpha);
        const bins = m.binSpectrum([1, 2, 3, 4, 5, 6, 7, 8], 4);
        out.bins = bins; out.total = bins.reduce((a, b) => a + b, 0);
    """)
    assert out["z"] == 0 and out["neg"] == 0 and out["hi"] == pytest.approx(1.0) and out["mid"] is True
    assert out["avg"] == pytest.approx(25.0) and out["none"] is None and out["alpha"] == pytest.approx(5.0)
    assert out["bins"] == [3, 7, 11, 15] and out["total"] == 36


def test_readings_history_gets_alpha_beta_series(tmp_path):
    out = run_js(tmp_path, """
        const s = new m.DeviceScreen(null);
        s.setReadings({cps: {gamma: 100, beta: 30, alpha: 2}}, 1000);
        s.setReadings({dose: 66}, 2000);
        out.h = s.history; out.dose = s.dose;
    """)
    h = out["h"][0]
    assert len(out["h"]) == 1 and h["ab"] == 32 and h["total"] == 132 and out["dose"] == 66


def test_disconnecting_clears_the_data(tmp_path):
    out = run_js(tmp_path, """
        const s = new m.DeviceScreen(null);
        s.setConnected(true);
        s.setReadings({dose: 5, cps: {gamma: 1, beta: 1, alpha: 1}}, 1000); s.setSpectrum([1, 2, 3], null, 1000);
        s.setConnected(false);
        out.state = [s.dose, s.cps, s.history.length, s.spectrum, s.snapshots.length];
    """)
    assert out["state"] == [None, None, 0, None, 0]
