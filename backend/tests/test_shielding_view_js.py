"""Shielding modal helpers (static/js/shielding_view.js) under Node."""
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
    script.write_text(f"import * as v from '{(JS / 'shielding_view.js').as_uri()}';\nconst out = {{}};\n" + body + "\nconsole.log(JSON.stringify(out));\n",
                      encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_lengths_use_the_unit_that_fits(tmp_path):
    out = run_js(tmp_path, "out.f = [0.0123, 0.55, 12.345, 154, 0, NaN, null, 1234].map(v.formatLength);")
    assert out["f"] == ["0.12 mm", "0.55 cm", "12.3 cm", "1.54 m", "0 cm", "--", "--", "12.3 m"]


def test_percentages_never_round_a_small_transmission_down_to_zero(tmp_path):
    out = run_js(tmp_path, "out.f = [1, 0.5, 0.2837, 0.05, 0.0123, 0.00045, 1e-7, 0, NaN].map(v.formatPercent);")
    assert out["f"] == ["100 %", "50 %", "28 %", "5 %", "1.23 %", "0.045 %", "< 0.001 %", "0 %", "--"]


def test_isotope_sentence_names_the_isotope_thickness_material_and_the_caveat(tmp_path):
    out = run_js(tmp_path, """
        out.s = v.describeShielding({ isotope: 'Cs-137', lines: [{}], thickness_cm: 1, transmission: 0.2837, material: 'lead' }, 'Lead');""")
    assert out["s"].startswith("Through 1 cm of lead, 28 % of Cs-137's gamma photons get through.")
    assert "Narrow beam" in out["s"] and "decay products that build up" in out["s"]


def test_energy_sentence_gives_the_layers_and_the_transmission_only_when_a_thickness_was_asked(tmp_path):
    out = run_js(tmp_path, """
        const base = { energy_kev: 662, half_value_layer_cm: 0.55, tenth_value_layer_cm: 1.83, material: 'lead' };
        out.without = v.describeShielding(base, 'Lead');
        out.with = v.describeShielding({ ...base, thickness_cm: 0.55, transmission: 0.5 }, 'Lead');
        out.none = v.describeShielding(null);""")
    assert out["without"].startswith("At 662 keV, lead halves the beam in 0.55 cm and cuts it to a tenth in 1.83 cm.")
    assert "cm lets" not in out["without"]
    assert "0.55 cm lets 50 % through." in out["with"]
    assert out["none"] == ""


def test_emissions_sentence_says_which_channels_and_what_they_need(tmp_path):
    out = run_js(tmp_path, """
        out.po = v.describeEmissions({ isotope: 'Po-210', channels: ['alpha', 'gamma'], min_intensity_percent: 1 });
        out.sr = v.describeEmissions({ isotope: 'Sr-90', channels: ['beta'], min_intensity_percent: 1 });
        out.cs = v.describeEmissions({ isotope: 'Cs-137', channels: ['beta', 'gamma'], min_intensity_percent: 1 });
        out.none = v.describeEmissions({ isotope: 'X-1', channels: [], min_intensity_percent: 1 });""")
    assert out["po"].startswith("Po-210 shows in the alpha and gamma channels: an alpha source must be within a few centimetres")
    assert out["sr"].startswith("Sr-90 shows in the beta channel: betas are stopped by a few millimetres of metal")
    assert "beta and gamma channels" in out["cs"]
    assert out["none"] == "X-1: no alpha, beta or gamma lines above 1 %."
