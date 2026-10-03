"""Keyboard-trap logic (static/js/a11y.js) and the spectrum description (static/js/summary.js) under Node.

The dialog behaviour itself (focus in, Tab trap, Esc, focus back) is checked in a browser by ui_a11y_audit.py.
Skipped when Node is not installed."""
import json
import pathlib
import shutil
import subprocess

import pytest

JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(tmp_path, body):
    script = tmp_path / "t.mjs"
    script.write_text(
        f"import * as a from '{(JS / 'a11y.js').as_uri()}';\nimport * as s from '{(JS / 'summary.js').as_uri()}';\nconst out = {{}};\n"
        + body + "\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_tab_wraps_inside_a_trap(tmp_path):
    out = run_js(tmp_path, """
        const [x, y, z] = ['x', 'y', 'z'];
        const list = [x, y, z];
        out.forward = [a.nextFocus(list, x, false), a.nextFocus(list, y, false), a.nextFocus(list, z, false)];
        out.backward = [a.nextFocus(list, x, true), a.nextFocus(list, y, true), a.nextFocus(list, z, true)];
        out.outside = [a.nextFocus(list, 'elsewhere', false), a.nextFocus(list, 'elsewhere', true), a.nextFocus(list, null, false)];
        out.empty = [a.nextFocus([], x, false), a.nextFocus([], null, true)];
        out.single = [a.nextFocus(['only'], 'only', false), a.nextFocus(['only'], 'only', true)];
    """)
    assert out["forward"] == [None, None, "x"]            # only the last stop wraps; the browser handles the middle
    assert out["backward"] == ["z", None, None]
    assert out["outside"] == ["x", "z", "x"]              # focus outside the dialog is pulled back in
    assert out["empty"] == [None, None]
    assert out["single"] == ["only", "only"]


def test_spectrum_description_for_screen_readers(tmp_path):
    out = run_js(tmp_path, """
        const counts = new Array(1024).fill(2);
        out.full = s.describeSpectrum({ counts, peaks: [{ energy: 32.6 }, { energy: 665.4 }], metadata: { live_time: 600 } });
        out.many = s.describeSpectrum({ counts, peaks: Array.from({ length: 9 }, (_, i) => ({ energy: 100 * (i + 1) })), metadata: {} });
        out.none = s.describeSpectrum({ counts, peaks: [], metadata: {} });
        out.uncal = s.describeSpectrum({ counts, peaks: [{ energy: 311.2 }], metadata: {}, isCalibrated: false });
        out.one = s.describeSpectrum({ counts, peaks: [{ energy: 661.7 }], metadata: {} });
        out.empty = s.describeSpectrum({});
    """)
    assert out["full"] == "Gamma spectrum, 1024 channels, 2,048 counts collected over 10 min. 2 peaks, at 33 keV, 665 keV."
    assert out["many"].endswith("9 peaks, at 100 keV, 200 keV, 300 keV, 400 keV, 500 keV, 600 keV and 3 more.")
    assert out["none"].endswith("No peaks detected.") and "collected over" not in out["none"]
    assert "channel 311" in out["uncal"] and "keV" not in out["uncal"]
    assert "1 peak, at 662 keV." in out["one"]
    assert out["empty"] == "Gamma spectrum, 0 channels, 0 counts. No peaks detected."
