"""Browser check: Spectral Analysis > Estimator, its projection, and the Compare view.

    python tests/ui_compare_estimator.py          (needs the server; ALPHAHOUND_URL for another port)

Found 2026-10-05 (reported as "Estimator then Compare puts peaks off the peaks on the chart"):
- the main chart, redrawn after the comparison view, kept that view's category axis: its peak markers (energies) were read as
  channel positions, a marker for 246 keV drawn near 600 keV on an AlphaHound, and the chart kept the projection's name;
- the comparison view plotted every spectrum channel by channel against the first one's energies, so a spectrum with another
  calibration had its peaks at the wrong energies;
- the Estimator's projection opened the comparison view without the current spectrum, and the next press of Compare closed it;
- a spectrum without a live time was projected as if it were 1 second long; the MDA assumed Cs-137's emission probability.
"""
import json
import math
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
URL = os.environ.get("ALPHAHOUND_URL", "http://localhost:3200").rstrip("/") + "/"
ALPHAHOUND = os.path.join(HERE, "data", "real_spectra", "spectrum_takumar_8hr_reference.n42")
RADIACODE = os.path.join(HERE, "data", "radiacode_fisicas", "Th-232.xml")
NO_LIVE_TIME = os.path.join(HERE, "data", "real_spectra", "spectrum_2025-12-12_08-41-27.csv")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not ok else ""))


CHART = """() => {
  const ch = Chart.getChart(document.getElementById('spectrumChart'));
  const ann = Object.values((ch.options.plugins.annotation || {}).annotations || {});
  return {xType: ch.scales.x.type, xMax: ch.scales.x.max,
          datasets: ch.data.datasets.map(d => ({label: d.label, points: d.data.map(p => typeof p === 'object' ? [p.x, p.y] : [null, p])})),
          markers: ann.filter(a => a.type === 'point').map(a => a.xValue)};
}"""


def peak_near(points, lo, hi):
    """Energy of the highest point between lo and hi keV."""
    inside = [(y, x) for x, y in points if x is not None and lo <= x <= hi]
    return max(inside)[1] if inside else None


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1500, "height": 1000})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("dialog", lambda d: (errors.append("native dialog: " + d.message), d.dismiss()))
    page.add_init_script("localStorage.setItem('analysisSettings', JSON.stringify({uiMode: 'expert'}))")
    for pattern, body in (("**/device/status", {"connected": False}), ("**/radiacode/status", {"connected": False, "available": True})):
        page.route(pattern, lambda r, q, b=body: r.fulfill(status=200, content_type="application/json", body=json.dumps(b)))
    page.goto(URL, wait_until="load")
    page.set_input_files("#file-input", ALPHAHOUND)
    page.wait_for_selector("#result-summary", state="visible", timeout=60000)
    page.wait_for_timeout(1000)
    before = page.evaluate(CHART)

    # Estimator > projection
    page.click("#btn-analysis"); page.wait_for_timeout(300)
    page.click("#btn-estimator-tool"); page.wait_for_timeout(300)
    page.fill("#est-target-time", "60")
    page.click("#btn-calc-projection")
    factor = page.inner_text("#est-factor")
    page.click("#btn-show-projection"); page.wait_for_timeout(800)
    view = page.evaluate(CHART)
    labels = [d["label"] for d in view["datasets"]]
    check("the projection is shown next to the current spectrum", labels[:1] == ["Current"] and any(l.startswith("Projection") for l in labels), str(labels))
    check("its label carries the factor the Estimator shows", any(factor.replace("x", "") in l for l in labels), f"{factor} vs {labels}")
    check("the comparison view has an energy axis", view["xType"] == "linear", view["xType"])
    check("and shows the range with counts in it, not the whole 0-8000 keV axis", view["xMax"] < 4000, view["xMax"])

    # Compare closes the view: the main chart again, with its peak markers on its peaks
    page.click("#btn-compare"); page.wait_for_timeout(800)
    after = page.evaluate(CHART)
    check("closing Compare gives the main chart back: energy axis, the measured spectrum, no overlays",
          after["xType"] == "linear" and [d["label"] for d in after["datasets"]] == ["Counts"], f"{after['xType']} {[d['label'] for d in after['datasets']]}")
    check("its peak markers are where they were before the comparison", after["markers"] == before["markers"] and len(after["markers"]) > 3,
          f"{before['markers'][:4]} -> {after['markers'][:4]}")
    pts = after["datasets"][0]["points"]
    off = []
    for m in after["markers"]:
        if m is None or m < 150:
            continue
        top = peak_near(pts, m - 30, m + 30)
        if top is not None and abs(top - m) > 30:
            off.append((round(m), round(top)))
    check("every marker sits on a local maximum of the spectrum (within 30 keV)", not off, str(off))
    check("the overlay counter says no spectra are loaded", page.inner_text("#overlay-count").startswith("0"), page.inner_text("#overlay-count"))

    # Compare with a spectrum of another calibration (a RadiaCode): the same line lines up
    page.click("#btn-compare"); page.wait_for_timeout(500)
    page.set_input_files("#compare-file-input", RADIACODE)
    page.wait_for_function("Chart.getChart(document.getElementById('spectrumChart')).data.datasets.length >= 2", timeout=60000)
    both = page.evaluate(CHART)
    tops = [peak_near(d["points"], 200, 280) for d in both["datasets"]]
    check("an AlphaHound and a RadiaCode spectrum show the 238 keV line at nearly the same energy (within 15 keV)",
          None not in tops and abs(tops[0] - tops[-1]) < 15, str(tops))

    # A spectrum without a live time is not projected as if it were 1 s long
    page.click("#btn-compare"); page.wait_for_timeout(300)
    page.set_input_files("#file-input", NO_LIVE_TIME)
    page.wait_for_timeout(4000)
    page.click("#btn-estimator-tool"); page.wait_for_timeout(300)
    page.fill("#est-target-time", "60")
    page.click("#btn-calc-projection"); page.wait_for_timeout(300)
    shown = page.inner_text("#est-factor")
    check("without a live time the Estimator says so instead of projecting from 1 second", "3600" not in shown and "x" not in shown.lower().replace("—", ""),
          shown)
    page.click("#close-estimator")

    # MDA: the emission probability is sent, not assumed to be Cs-137's
    sent = []
    page.route("**/analyze/mda", lambda r, q: (sent.append(json.loads(q.post_data)), r.continue_()))
    page.click("#btn-estimator-tool"); page.wait_for_timeout(300)
    page.click("#tab-mda")
    page.fill("#est-mda-energy", "238.6")
    page.fill("#est-mda-br", "43.6")
    page.click("#btn-calc-mda"); page.wait_for_timeout(1500)
    check("the MDA request carries the emission probability entered (Pb-212 238.6 keV: 43.6 %)",
          sent and math.isclose(sent[-1].get("branching_ratio", -1), 0.436, rel_tol=1e-6), str(sent[-1:] if sent else "no request"))

    check("no JS errors or native dialogs", not errors, "; ".join(errors[:3]))
    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
