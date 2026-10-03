"""
AlphaHound channel panel x theme sweep (not collected by pytest): every theme at desktop and phone width.

Connects a mocked AlphaHound (ah_mock.py), lets the channel history fill, then for each theme checks that the panel is
themed beyond colour (the chart's line weight, glow, smoothing, stepping, font and grid dash match the theme's --ch-*
tokens), that the three channel colours differ and stay readable, that nothing overflows, and that no JS error occurs.
Screenshots of the panel go to tests/ui_smoke_out/channels/.

Needs playwright + Chrome and the server running at http://localhost:3200.

    python backend/tests/ui_channels_sweep.py [--quick]
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ah_mock import install  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ui_smoke_out", "channels")
os.makedirs(OUT, exist_ok=True)
URL = "http://localhost:3200/"
QUICK = "--quick" in sys.argv

METRICS = r"""
() => {
  const css = getComputedStyle(document.documentElement);
  const tok = (n) => css.getPropertyValue(n).trim();
  const panel = document.querySelector('.ch-panel');
  const ps = getComputedStyle(panel);
  const chart = Chart.getChart(document.getElementById('ch-chart'));
  const ds = chart.data.datasets;
  const parse = (s) => { const m = s.match(/rgba?\(([^)]+)\)/) || []; const p = (m[1] || '').split(',').map(parseFloat); return p.length >= 3 ? p.slice(0, 3) : null; };
  const hex = (h) => { h = h.trim(); if (h[0] !== '#') return parse(h); return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); };
  const lum = (c) => { const a = c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2]; };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const m = getComputedStyle(e).backgroundColor.match(/rgba?\(([^)]+)\)/); if (m) { const p = m[1].split(',').map(parseFloat); if (p.length < 4 || p[3] > 0.5) return p.slice(0, 3); } } return [0, 0, 0]; };
  const readings = [...document.querySelectorAll('.ch-reading b')].map((b) => ({ ratio: +ratio(parse(getComputedStyle(b).color), bgOf(b)).toFixed(2) }));
  const colors = ['gamma', 'beta', 'alpha'].map((k) => ps.getPropertyValue('--ch-' + k).trim());
  const opts = chart.options;
  const font = opts.scales.x.ticks.font.family;
  const pr = panel.getBoundingClientRect();
  return {
    colors, readings: readings.map((r) => r.ratio),
    chartColors: ds.map((d) => d.borderColor), dashes: ds.map((d) => (d.borderDash || []).join(',')),
    lineWidth: ds[0].borderWidth, tension: ds[0].tension, stepped: ds[0].stepped, glow: opts.plugins.themeGlow.blur,
    gridDash: (opts.scales.x.grid.borderDash || []).join(' '), font,
    tokens: { lineW: parseFloat(tok('--ch-line-w')), glow: parseFloat(tok('--ch-glow')), tension: parseFloat(tok('--ch-tension')),
              step: parseFloat(tok('--ch-step')), dash: tok('--ch-grid-dash'), font: tok('--ch-font') },
    overflow: document.documentElement.scrollWidth - innerWidth,
    panelRight: Math.round(pr.right), panelWidth: Math.round(pr.width), viewport: innerWidth,
    points: ds.map((d) => d.data.filter((p) => p && p.y !== null).length),
  };
}
"""


def main():
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for vp_name, vp in (("desktop", {"width": 1400, "height": 1000}), ("phone", {"width": 390, "height": 844})):
            ctx = browser.new_context(viewport=vp)
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
            page.on("console", lambda m: errs.append(f"console.error: {m.text}") if m.type == "error" else None)
            install(page, burst=0)
            page.route("**/radiacode/status", lambda r, q: r.fulfill(status=200, content_type="application/json",
                       body=json.dumps({"connected": False, "available": True, "device_info": None, "last_error": None})))
            page.goto(URL, wait_until="networkidle")
            themes = page.eval_on_selector_all("#theme-select option", "els => els.map(e => e.value)")
            page.select_option("#port-select", "COM8")
            page.click("#btn-connect-device")
            page.wait_for_function("document.getElementById('device-conn-label').textContent === 'Connected'", timeout=8000)
            fill = 8 if QUICK else 40
            page.wait_for_function(
                "(() => { const c = Chart.getChart(document.getElementById('ch-chart')); return !!c && c.data.datasets[0].data.length >= %d })()" % fill,
                timeout=120000)
            for t in themes:
                errs.clear()
                page.select_option("#theme-select", t)
                page.wait_for_timeout(400)
                m = page.evaluate(METRICS)
                m["errors"] = list(errs)
                report[f"{vp_name}/{t}"] = m
                panel = page.locator(".ch-panel")
                panel.scroll_into_view_if_needed()
                panel.screenshot(path=os.path.join(OUT, f"{vp_name}_{t}.png"))
                if vp_name == "desktop" and t in ("dark", "oscilloscope", "nixie", "light"):
                    page.locator("#alphahound-details-panel").screenshot(path=os.path.join(OUT, f"{vp_name}_{t}_details.png"))
            ctx.close()
        browser.close()

    json.dump(report, open(os.path.join(OUT, "report.json"), "w"), indent=1)
    bad = 0
    for k, m in report.items():
        tk = m["tokens"]
        issues = []
        if len(set(m["colors"])) != 3: issues.append(f"channel colours not distinct {m['colors']}")
        if m["chartColors"] != m["colors"]: issues.append(f"chart colours {m['chartColors']} != panel {m['colors']}")
        if len(set(m["dashes"])) != 3: issues.append(f"line patterns not distinct {m['dashes']}")
        if min(m["readings"]) < 3: issues.append(f"low reading contrast {m['readings']}")
        if abs(m["lineWidth"] - tk["lineW"]) > 0.01: issues.append(f"line width {m['lineWidth']} vs token {tk['lineW']}")
        if abs(m["glow"] - tk["glow"]) > 0.01: issues.append(f"glow {m['glow']} vs token {tk['glow']}")
        if abs(m["tension"] - tk["tension"]) > 0.01: issues.append(f"tension {m['tension']} vs token {tk['tension']}")
        if bool(m["stepped"]) != (tk["step"] == 1): issues.append(f"stepped {m['stepped']} vs token {tk['step']}")
        want_dash = "" if tk["dash"] in ("0", "none") else " ".join(tk["dash"].replace(",", " ").split())
        if m["gridDash"] != want_dash: issues.append(f"grid dash '{m['gridDash']}' vs token '{want_dash}'")
        if m["font"].replace('"', "").replace("'", "") != tk["font"].replace('"', "").replace("'", ""):
            issues.append(f"font {m['font']!r} vs token {tk['font']!r}")
        if m["overflow"] > 2 or m["panelRight"] > m["viewport"] + 2: issues.append(f"overflow {m['overflow']} / panel right {m['panelRight']}")
        if min(m["points"]) < 3: issues.append(f"chart has no data {m['points']}")
        if m["errors"]: issues.append("errors " + "; ".join(m["errors"][:2]))
        if issues:
            bad += 1
            print(k, "->", " | ".join(issues))
    print(f"\n{len(report)} combos, {bad} with issues")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
