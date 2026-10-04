"""Which export formats can hold an energy axis (static/js/export_support.js) under Node."""
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
    script.write_text(f"import * as v from '{(JS / 'export_support.js').as_uri()}';\nconst out = {{}};\n" + body + "\nconsole.log(JSON.stringify(out));\n",
                      encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_linear_and_a_quadratic_axis_fit_exactly(tmp_path):
    out = run_js(tmp_path, """
        const ch = Array.from({ length: 1024 }, (_, i) => i);
        out.linear = v.quadraticMisfitKeV(ch.map((i) => 15 + 7.4 * i));
        out.quadratic = v.quadraticMisfitKeV(ch.map((i) => 8 + 2.5 * i + 1e-4 * i * i));""")
    assert out["linear"] < 1e-6 and out["quadratic"] < 1e-6


def test_the_alphahounds_cubic_axis_is_hundreds_of_kev_off_a_quadratic(tmp_path):
    """Same coefficients as the live device (and the Python tests); numpy says the quadratic misfit is 293 keV."""
    out = run_js(tmp_path, """
        const ch = Array.from({ length: 1024 }, (_, i) => i);
        const axis = ch.map((i) => 15.0001 + 1.68372 * i - 4.75865e-05 * i * i + 5.49654e-06 * i * i * i);
        out.misfit = v.quadraticMisfitKeV(axis);
        out.chn = v.chnAvailability(axis);""")
    assert out["misfit"] == pytest.approx(293, rel=0.03)
    assert out["chn"]["ok"] is False and "PCF or N42" in out["chn"]["reason"]


def test_missing_or_broken_axes_do_not_block_the_button(tmp_path):
    out = run_js(tmp_path, """
        out.a = [undefined, null, [], [1, 2, 3], [1, 2, NaN, 4, 5]].map((x) => v.chnAvailability(x).ok);""")
    assert out["a"] == [True] * 5


def test_the_threshold_is_the_servers(tmp_path):
    out = run_js(tmp_path, """
        const ch = Array.from({ length: 1024 }, (_, i) => i);
        out.limit = v.CHN_MAX_ERROR_KEV;
        out.ripple = [0.3, 3].map((a) => v.chnAvailability(ch.map((i) => 15 + 7.4 * i + a * Math.sin(i / 60))).ok);""")
    assert out["limit"] == 1.0 and out["ripple"] == [True, False]
