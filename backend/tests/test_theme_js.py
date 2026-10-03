"""Themed charts: palette generation (palette.js), the theme's chart character (chart_theme.js) and the channel panel
logic (channels.js), run under Node, plus a check of every theme block in style.css.

Skipped when Node is not installed. Drawing itself is covered by the browser smoke test and the theme sweep."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js"
CSS = pathlib.Path(__file__).resolve().parents[1] / "static" / "style.css"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

STUBS = """
const vars = globalThis.__vars = {};
globalThis.document = { documentElement: {} };
globalThis.getComputedStyle = () => ({ getPropertyValue: (n) => (n in vars ? vars[n] : '') });
const store = globalThis.__store = {};
globalThis.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
"""


def run_js(tmp_path, body):
    script = tmp_path / "t.mjs"
    script.write_text(
        STUBS +
        f"const palette = await import('{(JS / 'palette.js').as_uri()}');\n"
        f"const theme = await import('{(JS / 'chart_theme.js').as_uri()}');\n"
        f"const channels = await import('{(JS / 'channels.js').as_uri()}');\n"
        "const out = {};\n" + body + "\nconsole.log(JSON.stringify(out));\nprocess.exit(0);\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


# --------------------------------------------------------------------------------------------- themes in style.css

def theme_variables():
    """{theme: {custom property: value}} for the default theme and every [data-theme] block.

    Handles selector lists and several blocks per theme: :root rules form the base, a theme's own rules override it
    (they come later in the file at the same specificity, which is how the cascade resolves them too)."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)   # comments sit in front of selectors
    base, own = {}, {}
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        decl = {k: v.strip() for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", m.group(2))}
        if not decl:
            continue
        for selector in m.group(1).split(","):
            selector = selector.strip()
            if selector == ":root":
                base.update(decl)
            else:
                t = re.fullmatch(r'\[data-theme="([a-z0-9-]+)"\]', selector)
                if t:
                    own.setdefault(t.group(1), {}).update(decl)
    themes = {"dark": dict(base)}
    for name, decl in own.items():
        themes[name] = {**base, **decl}
    return themes


def test_every_theme_is_found():
    themes = theme_variables()
    assert len(themes) == 17, sorted(themes)
    for name, v in themes.items():
        for key in ("--primary-color", "--secondary-color", "--accent-color", "--bg-color"):
            assert re.match(r"^#[0-9a-fA-F]{6}$", v.get(key, "")), (name, key, v.get(key))


def test_character_tokens_are_sane_for_every_theme():
    for name, v in theme_variables().items():
        line = float(v["--ch-line-w"])
        assert 1 <= line <= 3.5, (name, line)
        assert 0 <= float(v["--ch-glow"]) <= 16, name
        assert 0 <= float(v["--ch-tension"]) <= 0.5, name
        assert v["--ch-step"] in ("0", "1"), name
        assert re.match(r"^(0|none|\d+([ ,]+\d+)*)$", v["--ch-grid-dash"]), (name, v["--ch-grid-dash"])
        assert v["--ch-font"], name


def test_themes_differ_in_character_not_only_colour():
    themes = theme_variables()
    looks = {name: (v["--ch-line-w"], v["--ch-glow"], v["--ch-tension"], v["--ch-step"], v["--ch-grid-dash"], v["--ch-font"], v.get("--ch-radius"))
             for name, v in themes.items()}
    assert len(set(looks.values())) >= 10, f"themes share too much character: {len(set(looks.values()))} distinct looks"
    assert themes["oscilloscope"]["--ch-glow"] != "0" and themes["nixie"]["--ch-glow"] != "0"   # the phosphor / tube themes glow
    assert themes["civildefense"]["--ch-step"] == "1"                                              # blocky histogram
    assert themes["light"]["--ch-glow"] == "0"                                                     # light theme never glows


def test_channel_palette_is_distinct_and_readable_in_every_theme(tmp_path):
    themes = theme_variables()
    inputs = {n: {"primary": v["--primary-color"], "secondary": v["--secondary-color"], "accent": v["--accent-color"], "bg": v["--bg-color"]}
              for n, v in themes.items()}
    out = run_js(tmp_path, f"""
        const inputs = {json.dumps(inputs)};
        out.res = {{}};
        for (const [name, t] of Object.entries(inputs)) {{
            const p = palette.channelPalette(t);
            const bg = palette.parseColor(t.bg);
            const c = ['gamma', 'beta', 'alpha'].map((k) => palette.parseColor(p[k]));
            out.res[name] = {{
                colors: p,
                contrast: c.map((x) => palette.contrastRatio(x, bg)),
                dist: [palette.colorDistance(c[0], c[1]), palette.colorDistance(c[0], c[2]), palette.colorDistance(c[1], c[2])],
            }};
        }}
    """)
    for name, r in out["res"].items():
        assert len(set(r["colors"].values())) == 3, (name, r["colors"])
        assert min(r["contrast"]) >= 2.9, (name, r["contrast"])      # readable on the theme's own background
        assert min(r["dist"]) >= 0.85, (name, r["dist"])             # told apart without the line pattern


def test_multi_hue_themes_keep_their_own_colours(tmp_path):
    """A theme that already has three distinct colours (cyberpunk) must not be recoloured."""
    out = run_js(tmp_path, """
        out.p = palette.channelPalette({ primary: '#fcee09', secondary: '#ff006e', accent: '#00f5ff', bg: '#0d0208' });
    """)
    assert out["p"] == {"gamma": "#fcee09", "beta": "#ff006e", "alpha": "#00f5ff"}


def test_color_helpers(tmp_path):
    out = run_js(tmp_path, """
        out.a = palette.parseColor('#0af'); out.b = palette.parseColor('#33ff66'); out.c = palette.parseColor('rgb(10, 20, 30)');
        out.d = palette.parseColor('rgba(10, 20, 30, 0.5)'); out.e = palette.parseColor('nonsense'); out.f = palette.parseColor(null);
        out.hex = palette.toHex({ r: 255.4, g: -3, b: 16 });
        const hsl = palette.rgbToHsl({ r: 200, g: 100, b: 50 }); const back = palette.hslToRgb(hsl);
        out.round = [Math.round(back.r), Math.round(back.g), Math.round(back.b)];
        out.bw = palette.contrastRatio({ r: 0, g: 0, b: 0 }, { r: 255, g: 255, b: 255 });
        out.same = palette.contrastRatio({ r: 9, g: 9, b: 9 }, { r: 9, g: 9, b: 9 });
        out.lift = palette.contrastRatio(palette.ensureContrast({ r: 20, g: 20, b: 20 }, { r: 10, g: 10, b: 10 }, 3), { r: 10, g: 10, b: 10 });
        out.darken = palette.contrastRatio(palette.ensureContrast({ r: 240, g: 240, b: 240 }, { r: 250, g: 250, b: 250 }, 3), { r: 250, g: 250, b: 250 });
    """)
    assert out["a"] == {"r": 0, "g": 170, "b": 255} and out["b"] == {"r": 51, "g": 255, "b": 102}
    assert out["c"] == {"r": 10, "g": 20, "b": 30} and out["d"] == {"r": 10, "g": 20, "b": 30}
    assert out["e"] is None and out["f"] is None
    assert out["hex"] == "#ff0010"
    assert out["round"] == [200, 100, 50]
    assert round(out["bw"]) == 21 and out["same"] == 1
    assert out["lift"] >= 3 and out["darken"] >= 3                # lightens on dark themes, darkens on light ones


def test_screen_palette_follows_the_theme(tmp_path):
    out = run_js(tmp_path, """
        out.green = palette.screenPalette({ primary: '#33ff66' }); out.blue = palette.screenPalette({ primary: '#00a2e8' });
        out.device = palette.DEVICE_SCREEN_PALETTE;
    """)
    assert out["green"]["fg"] != out["blue"]["fg"] and out["green"]["dim"] != out["blue"]["dim"]
    assert out["device"]["fg"] == "#d6f2ff"
    for key in ("fg", "dim", "ghost", "soft", "mid"):
        assert out["green"][key] and out["blue"][key]


def test_read_theme_colors_uses_the_custom_properties(tmp_path):
    out = run_js(tmp_path, """
        out.empty = palette.readThemeColors();
        Object.assign(__vars, { '--primary-color': ' #112233 ', '--secondary-color': '#445566', '--accent-color': '#778899', '--bg-color': '#000' });
        out.set = palette.readThemeColors();
    """)
    assert out["empty"]["primary"] == "#38bdf8" and out["empty"]["bg"] == "#0f172a"      # sensible fallbacks
    assert out["set"]["primary"] == "#112233" and out["set"]["accent"] == "#778899" and out["set"]["bg"] == "#000"


# --------------------------------------------------------------------------------------------- chart_theme.js

def test_chart_theme_reads_the_character_tokens(tmp_path):
    out = run_js(tmp_path, """
        out.dflt = theme.chartTheme();
        Object.assign(__vars, { '--ch-line-w': '2.5', '--ch-glow': '12', '--ch-tension': '0', '--ch-step': '1',
                                '--ch-grid-dash': '2 4', '--ch-font': '"Courier New", monospace', '--border-color': '#222' });
        out.nixie = theme.chartTheme();
        out.dash = [theme.parseDash('2 3'), theme.parseDash('0'), theme.parseDash('none'), theme.parseDash(''), theme.parseDash('4,2'), theme.parseDash(null)];
        out.tok = [theme.parseToken('1.75', 9), theme.parseToken('9px', 0), theme.parseToken('x', 7), theme.parseToken(undefined, 3)];
        out.alpha = [theme.withAlpha('#ff8000', 0.25), theme.withAlpha('rgb(1,2,3)', 0.5), theme.withAlpha(null, 1)];
    """)
    d, n = out["dflt"], out["nixie"]
    assert d["lineWidth"] == 1.75 and d["glow"] == 0 and d["stepped"] is False and d["gridDash"] == []
    assert n["lineWidth"] == 2.5 and n["glow"] == 12 and n["tension"] == 0 and n["stepped"] is True
    assert n["gridDash"] == [2, 4] and n["font"].startswith('"Courier New"') and n["grid"] == "#222"
    assert out["dash"] == [[2, 3], [], [], [], [4, 2], []]
    assert out["tok"] == [1.75, 9, 7, 3]
    assert out["alpha"] == ["rgba(255, 128, 0, 0.25)", "rgb(1,2,3)", None]


def test_glow_plugin_only_draws_a_shadow_when_asked(tmp_path):
    out = run_js(tmp_path, """
        const calls = [];
        const ctx = { save: () => calls.push('save'), restore: () => calls.push('restore'), shadowBlur: 0, shadowColor: '' };
        const mk = (blur) => ({ ctx, options: { plugins: { themeGlow: { blur } } }, data: { datasets: [{ borderColor: '#0f0' }] } });
        const args = { index: 0, meta: { type: 'line' } };
        theme.themeGlowPlugin.beforeDatasetDraw(mk(0), args); theme.themeGlowPlugin.afterDatasetDraw(mk(0), args);
        out.off = calls.slice();
        theme.themeGlowPlugin.beforeDatasetDraw(mk(8), args);
        out.on = [calls.slice(), ctx.shadowBlur, ctx.shadowColor];
        theme.themeGlowPlugin.afterDatasetDraw(mk(8), args);
        out.balanced = calls.slice();
        theme.themeGlowPlugin.beforeDatasetDraw(mk(8), { index: 0, meta: { type: 'bar' } });
        out.bar = calls.length;
    """)
    assert out["off"] == []                                          # glow 0: the context is untouched
    assert out["on"] == [["save"], 8, "#0f0"]
    assert out["balanced"] == ["save", "restore"] and out["bar"] == 2   # balanced save/restore, lines only


# --------------------------------------------------------------------------------------------- channels.js

def test_log_meter_and_rate_formatting(tmp_path):
    out = run_js(tmp_path, """
        const c = channels;
        out.frac = [0, 0.5, 1, 10, 100, 10000, 1e6, -4, NaN].map(c.logFraction);
        out.cps = [c.formatChannelRate(0, 'CPS'), c.formatChannelRate(12.345, 'CPS'), c.formatChannelRate(2220.4, 'CPS'), c.formatChannelRate(null, 'CPS')];
        out.cpm = [c.formatChannelRate(2.5, 'CPM'), c.formatChannelRate(1000, 'CPM'), c.formatChannelRate(undefined, 'CPM')];
        out.mix = [c.composition({ gamma: 6, beta: 3, alpha: 1 }), c.composition({ gamma: 0, beta: 0, alpha: 0 }), c.composition(null), c.composition({ gamma: -2, beta: 4, alpha: 'x' })];
    """)
    assert out["frac"] == [0, 0, 0, 0.25, 0.5, 1, 1, 0, 0]
    assert out["cps"] == ["0.00", "12.35", "2,220", "--"]
    assert out["cpm"] == ["150", "60,000", "--"]
    assert out["mix"][0] == {"gamma": 0.6, "beta": 0.3, "alpha": 0.1}
    assert out["mix"][1] == out["mix"][2] == {"gamma": 0, "beta": 0, "alpha": 0}
    assert out["mix"][3] == {"gamma": 0, "beta": 1, "alpha": 0}


def test_window_statistics_and_series(tmp_path):
    out = run_js(tmp_path, """
        const c = channels;
        const now = 100000;
        const hist = [];
        for (let i = 0; i < 100; i++) hist.push({ t: now - (99 - i) * 1000, gamma: i, beta: 10, alpha: i % 2 });
        out.mean = [c.meanOf(hist, now, 10, 'gamma'), c.meanOf(hist, now, 100, 'beta'), c.meanOf([], now, 10, 'gamma'), c.meanOf(hist, now + 10 ** 7, 10, 'gamma')];
        out.peak = [c.peakOf(hist, now, 10, 'gamma'), c.peakOf(hist, now, 100, 'alpha'), c.peakOf([], now, 10, 'gamma')];
        const s = c.windowSeries(hist, now, 60);
        out.series = [s.x.length, s.x[s.x.length - 1], s.x[0], s.gamma[s.gamma.length - 1], s.beta[0]];
        const dense = []; for (let i = 0; i < 1800; i++) dense.push({ t: now - (1799 - i) * 1000, gamma: 5, beta: 1, alpha: 0 });
        const d = c.windowSeries(dense, now, 1800, 240);
        out.dense = [d.x.length <= 240, d.x[d.x.length - 1], d.gamma.every((v) => v === 5)];
        out.empty = c.windowSeries([], now, 60);
    """)
    assert out["mean"][0] == pytest.approx(94.5 + 0.0, abs=0.51) and out["mean"][1] == 10 and out["mean"][2] is None and out["mean"][3] is None
    assert out["peak"] == [99, 1, None]
    n, last, first, gamma_last, beta_first = out["series"]
    assert n == 61 and last == 0 and first == -60 and gamma_last == 99 and beta_first == 10      # newest sample is the last point
    assert out["dense"] == [True, 0, True]                                                          # a 30-minute window stays small
    assert out["empty"] == {"x": [], "gamma": [], "beta": [], "alpha": []}


def test_channel_panel_collects_history_and_remembers_choices(tmp_path):
    out = run_js(tmp_path, """
        const nothing = { querySelector: () => null, querySelectorAll: () => [] };
        const panel = new channels.ChannelPanel(nothing);
        out.initial = [panel.unit, panel.windowS, panel.scale];
        const t0 = 1_000_000;
        for (let i = 0; i < 5; i++) panel.update({ gamma: 100 + i, beta: 10, alpha: 1 }, t0 + i * 1000);
        out.n = panel.history.length; out.last = panel.last;
        panel.update({ gamma: 1, beta: 1, alpha: 1 }, t0 + 10 * 3600 * 1000);                    // 10 h later: the old samples age out
        out.afterGap = panel.history.length;
        panel.setUnit('CPM'); panel.setWindow(60); panel.setWindow(7); panel.setScale('log');
        out.chosen = [panel.unit, panel.windowS, panel.scale, __store.ahRateUnit, __store.ahChWindow, __store.ahChScale];
        const again = new channels.ChannelPanel(nothing);
        out.restored = [again.unit, again.windowS, again.scale];
        panel.showNoData(); out.keepsHistory = panel.history.length;
        panel.reset(); out.reset = [panel.history.length, panel.last];
        panel.update(null); out.nullOk = panel.history.length;
        panel.destroy(); again.destroy();
    """)
    assert out["initial"] == ["CPS", 300, "linear"]
    assert out["n"] == 5 and out["last"]["gamma"] == 104
    assert out["afterGap"] == 1
    assert out["chosen"] == ["CPM", 60, "log", "CPM", "60", "log"]            # an unknown window (7) is ignored
    assert out["restored"] == ["CPM", 60, "log"]
    assert out["keepsHistory"] == 1 and out["reset"] == [0, None] and out["nullOk"] == 0


def test_channel_panel_publishes_theme_colours_per_theme(tmp_path):
    out = run_js(tmp_path, """
        const style = {}; const props = {};
        const root = { querySelector: (s) => (s === '.ch-panel' ? { style: { setProperty: (k, v) => { props[k] = v; } } } : null), querySelectorAll: () => [] };
        Object.assign(__vars, { '--primary-color': '#33ff66', '--secondary-color': '#00cc44', '--accent-color': '#33ff66', '--bg-color': '#0a0f0a' });
        const panel = new channels.ChannelPanel(root);
        out.osc = { ...props };
        Object.assign(__vars, { '--primary-color': '#fcee09', '--secondary-color': '#ff006e', '--accent-color': '#00f5ff', '--bg-color': '#0d0208' });
        panel.refreshTheme();
        out.cyber = { ...props };
        panel.destroy();
    """)
    assert set(out["osc"]) == {"--ch-gamma", "--ch-beta", "--ch-alpha"}
    assert len(set(out["osc"].values())) == 3                        # a single-hue theme still gets three distinct colours
    assert out["cyber"] == {"--ch-gamma": "#fcee09", "--ch-beta": "#ff006e", "--ch-alpha": "#00f5ff"}   # refreshed on theme switch
