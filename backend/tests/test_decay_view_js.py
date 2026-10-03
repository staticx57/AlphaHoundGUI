"""Decay modal helpers (static/js/decay_view.js) and the many-series colour palette (palette.js seriesPalette) under Node."""
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
        f"import * as v from '{(JS / 'decay_view.js').as_uri()}';\nimport * as p from '{(JS / 'palette.js').as_uri()}';\nconst out = {{}};\n"
        + body + "\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_duration_units(tmp_path):
    out = run_js(tmp_path, """
        out.d = [v.durationToDays(100, 'years'), v.durationToDays(24, 'hours'), v.durationToDays(90, 'minutes'), v.durationToDays(86400, 'seconds'),
                 v.durationToDays(3, 'days'), v.durationToDays(1, 'fortnights'), v.durationToDays('2.5', 'years')];
        out.units = v.DURATION_UNITS;
    """)
    assert out["d"][:5] == [36525, 1, pytest.approx(0.0625), 1, 3]
    assert out["d"][5] is None                                   # NaN: an unknown unit is not silently a number
    assert out["d"][6] == pytest.approx(913.125)
    assert out["units"] == ["seconds", "minutes", "hours", "days", "years"]


def test_activity_formatting(tmp_path):
    out = run_js(tmp_path, """
        out.f = [0, 1000, 1234.5678, 5e6, 2.5e9, 7e12, 12.3456, 0.0123, 4.5e-7, 3e-10, 1e-12, NaN, null, -1500].map(v.formatBq);
    """)
    assert out["f"] == ["0 Bq", "1 kBq", "1.235 kBq", "5 MBq", "2.5 GBq", "7 TBq", "12.35 Bq", "12.3 mBq", "450 nBq", "0.3 nBq", "0.001 nBq", "--", "--", "-1.5 kBq"]


def test_what_is_said_under_the_chart(tmp_path):
    out = run_js(tmp_path, """
        out.full = v.describeDecayResult({ engine_used: 'radioactivedecay', engine_version: '0.6.1', data_source: 'ICRP Publication 107',
            isotopes: ['Cs-137', 'Ba-137m'], omitted: [], warnings: [] });
        out.omitted = v.describeDecayResult({ engine_used: 'builtin', isotopes: ['U-238'], omitted: ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
            warnings: ['The curie engine is not available here; the builtin engine was used instead.'] });
        out.one = v.describeDecayResult({ engine_used: 'curie', isotopes: ['Co-60'] });
        out.none = v.describeDecayResult(null);
    """)
    assert out["full"]["info"] == "Computed with radioactivedecay 0.6.1 · data: ICRP Publication 107 · 2 nuclides shown"
    assert out["omitted"]["info"].endswith("8 below 0.1 % of the start left out (A, B, C, D, E, F, +2 more)")
    assert out["omitted"]["warnings"] == ["The curie engine is not available here; the builtin engine was used instead."]
    assert out["one"]["info"] == "Computed with curie · 1 nuclide shown"
    assert out["none"] == {"info": "", "warnings": []}


def test_log_axis_values_and_range(tmp_path):
    out = run_js(tmp_path, """
        out.log = v.forLogAxis([0, 5, 0.001, -1, null, NaN, 1e-30]);
        out.range = v.activityAxisRange({ initial_activity: 1000, series: { P: [1000, 500], D: [0, 800, 300] } });
        out.rangeBad = [v.activityAxisRange(null), v.activityAxisRange({ initial_activity: 0, series: {} })];
        out.none = v.forLogAxis(null);
    """)
    assert out["log"] == [None, 5, 0.001, None, None, None, 1e-30]
    assert out["range"] == {"min": 0.001, "max": 1500}
    assert out["rangeBad"] == [{"min": 1e-6, "max": 1.5}, {"min": 1e-6, "max": 1.5}]
    assert out["none"] == []


THEMES = {
    "dark": ("#38bdf8", "#818cf8", "#38bdf8", "#0f172a"), "light": ("#0ea5e9", "#6366f1", "#0ea5e9", "#f8fafc"),
    "oscilloscope": ("#33ff66", "#00cc44", "#33ff66", "#0a0f0a"), "nixie": ("#ff6a00", "#ff9500", "#ff7700", "#1a1410"),
    "cyberpunk": ("#fcee09", "#ff006e", "#00f5ff", "#0d0208"), "hp": ("#d4a574", "#e8c49a", "#d4a574", "#2a2320"),
    "victoreen": ("#7cb68a", "#9ed4aa", "#7cb68a", "#1e2420"), "tektronix": ("#00a2e8", "#66ccff", "#00a2e8", "#1a2530"),
}


def test_many_series_get_distinct_readable_colours_in_every_theme(tmp_path):
    out = run_js(tmp_path, f"""
        const themes = {json.dumps({k: dict(zip(("primary", "secondary", "accent", "bg"), v)) for k, v in THEMES.items()})};
        out.res = {{}};
        for (const [name, t] of Object.entries(themes)) {{
            const bg = p.parseColor(t.bg);
            const cols = p.seriesPalette(t, 15);
            const rgb = cols.map(p.parseColor);
            let minDist = Infinity;
            for (let i = 0; i < rgb.length; i++) for (let j = i + 1; j < rgb.length; j++) minDist = Math.min(minDist, p.colorDistance(rgb[i], rgb[j]));
            out.res[name] = {{ n: cols.length, unique: new Set(cols).size, minContrast: Math.min(...rgb.map((c) => p.contrastRatio(c, bg))), minDist,
                              first3: cols.slice(0, 3), channel: Object.values(p.channelPalette(t)) }};
        }}
        out.few = [p.seriesPalette(themes.dark, 0), p.seriesPalette(themes.dark, 1).length, p.seriesPalette(themes.dark, 2).length];
    """)
    for name, r in out["res"].items():
        assert r["n"] == 15 and r["unique"] == 15, (name, r)
        assert r["minContrast"] >= 2.9, (name, r["minContrast"])          # readable on the theme's background
        assert r["minDist"] >= 0.12, (name, r["minDist"])                 # no two lines the same colour (line patterns help beyond this)
        assert r["first3"] == r["channel"], name                          # the first three are the gamma / beta / alpha colours
    assert out["few"] == [[], 1, 2]
