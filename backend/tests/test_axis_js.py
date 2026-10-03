"""Energy-axis helpers (static/js/axis.js) run under Node. Skipped when Node is not installed."""
import json
import pathlib
import shutil
import subprocess

import pytest

MODULE = pathlib.Path(__file__).resolve().parents[1] / "static" / "js" / "axis.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(tmp_path, body):
    script = tmp_path / "t.mjs"
    script.write_text(f"import * as m from '{MODULE.as_uri()}';\nconst out = {{}};\n{body}\nconsole.log(JSON.stringify(out));\n",
                      encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_ticks_are_round_even_when_the_axis_starts_at_an_offset(tmp_path):
    out = run_js(tmp_path, "out.t = m.roundTicks(-31, 1713.3); out.u = m.roundTicks(5.56, 2500);")
    assert out["t"] == [0, 200, 400, 600, 800, 1000, 1200, 1400, 1600]     # not 169.2, 369.2, ...
    assert out["u"][0] == 500 and out["u"][-1] == 2500 and all(v % 500 == 0 for v in out["u"])


def test_ticks_adapt_to_a_zoomed_range(tmp_path):
    out = run_js(tmp_path, "out.a = m.roundTicks(560, 620); out.b = m.roundTicks(0, 3000); out.c = m.roundTicks(100, 112);")
    assert out["a"] == [560, 570, 580, 590, 600, 610, 620]
    assert out["b"][:3] == [0, 500, 1000] and out["b"][-1] == 3000
    assert out["c"] == [100, 102, 104, 106, 108, 110, 112]


def test_ticks_are_never_negative_and_float_noise_is_removed(tmp_path):
    out = run_js(tmp_path, "out.a = m.roundTicks(-500, 100); out.b = m.roundTicks(0, 0.5);")
    assert min(out["a"]) >= 0
    assert out["b"] == [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]   # 0.30000000000000004 would fail this


def test_degenerate_ranges_give_no_ticks(tmp_path):
    out = run_js(tmp_path, "out.a = m.roundTicks(5, 5); out.b = m.roundTicks(10, 0); out.c = m.roundTicks(NaN, 3); out.d = m.roundTicks(0, Infinity);")
    assert out == {"a": [], "b": [], "c": [], "d": []}


def test_nice_step_and_label(tmp_path):
    out = run_js(tmp_path, """
        out.s = [m.niceStep(1000, 8), m.niceStep(1713, 8), m.niceStep(60, 8), m.niceStep(0, 8), m.niceStep(-3, 8)];
        out.l = [m.formatKeV(-31.4), m.formatKeV(1712.6), m.formatKeV(null), m.formatKeV('abc')];
    """)
    assert out["s"] == [100, 200, 10, 1, 1]
    assert out["l"] == ["0 keV", "1713 keV", "0 keV", "0 keV"]
