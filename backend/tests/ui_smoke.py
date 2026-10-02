"""
Headless-browser UI smoke test (not collected by pytest).

Needs: pip install playwright, Google Chrome installed, and the server running
at http://localhost:3200 (python main.py). Mocks the AlphaHound device status and
dose WebSocket, so no hardware is required. Screenshots go to tests/ui_smoke_out/.

    python backend/tests/ui_smoke.py
"""
import json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ui_smoke_out")
os.makedirs(OUT, exist_ok=True)
URL = "http://localhost:3200/"
SPEC = os.path.join(HERE, "..", "data", "test_spectra", "synthetic_cesium137.n42")
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def new_page(browser, errors, status_connected=False):
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
    return ctx, page


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)

    # A. Plain load
    errs = []
    ctx, page = new_page(browser, errs)
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(OUT, "a_load.png"))
    check("A page loads without JS errors", not errs, "; ".join(errs[:3]))
    check("A disconnected label reads 'Not connected'", page.inner_text("#device-conn-label") == "Not connected")

    # C. Radiacode tab
    errs.clear()
    page.click("#tab-radiacode")
    page.wait_for_timeout(500)
    page.screenshot(path=os.path.join(OUT, "c_radiacode_tab.png"))
    check("C radiacode connection row visible", page.is_visible("#radiacode-connection-row"))
    check("C View Configuration button present in DOM", page.query_selector("#btn-view-config") is not None)
    check("C accumulated dose row present", page.query_selector("#rc-accumulated-dose") is not None)
    check("C no duplicate ids", page.evaluate(
        "() => { const ids=[...document.querySelectorAll('[id]')].map(e=>e.id); return ids.length===new Set(ids).size }"))
    check("C no JS errors on tab switch", not errs, "; ".join(errs[:3]))
    ctx.close()

    # B. AlphaHound live dose via mocked status + websocket
    errs = []
    ctx, page = new_page(browser, errs)
    page.route("**/device/status", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"connected": True, "temperature": None})))

    def ws_handler(ws):
        ws.send(json.dumps({"dose_rate": 2500.0}))

    page.route_web_socket("**/ws/dose", ws_handler)
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(OUT, "b_dose.png"))
    text = page.inner_text("#rc-dose-display")
    check("B dose readout updated", "2500" in text, text)
    alert_visible = page.evaluate(
        "() => { const a=document.getElementById('safety-alert'); return !!a && a.style.display!=='none' }")
    check("B high-dose safety alert shown", alert_visible)
    check("B restored connection enables controls + label", page.inner_text("#device-conn-label") == "Connected"
          and not page.evaluate("() => document.getElementById('unified-device-controls').classList.contains('device-disconnected')"))
    check("B no JS errors from dose callback", not any("textContent" in e or "null" in e for e in errs), "; ".join(errs[:3]))
    ctx.close()

    # D. Background load
    errs = []
    ctx, page = new_page(browser, errs)
    page.goto(URL, wait_until="networkidle")
    page.set_input_files("#file-input", SPEC)
    page.wait_for_selector("#dashboard", state="visible", timeout=20000)
    page.wait_for_timeout(1500)
    page.set_input_files("#bg-file-input", SPEC)
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(OUT, "d_background.png"), full_page=True)
    ind = page.evaluate("() => document.getElementById('bg-active-indicator')?.style.display")
    clr = page.evaluate("() => document.getElementById('btn-clear-bg')?.style.display")
    status = page.evaluate("() => document.getElementById('bg-status')?.textContent")
    check("D bg indicator shown", ind == "inline", str(ind))
    check("D Clear BG button shown", clr == "inline-block", str(clr))
    check("D bg status text", "Loaded" in (status or ""), status or "")
    check("D no JS errors during background load", not errs, "; ".join(errs[:3]))
    # E. Confidence colors follow theme switches made after results are rendered
    def conf_bg():
        return page.evaluate("""() => [...document.querySelectorAll('#isotopes-container [style*="var(--confidence-"], #decay-chains-list [style*="var(--confidence-"]')]
            .map(e => getComputedStyle(e).backgroundColor)""")
    page.select_option("#theme-select", "dark")
    page.wait_for_timeout(300)
    before = conf_bg()
    page.select_option("#theme-select", "light")
    page.wait_for_timeout(300)
    after = conf_bg()
    check("E confidence colors rendered via CSS vars", len(before) > 0, str(len(before)))
    check("E confidence colors change with theme", before != after, f"{before[:1]} -> {after[:1]}")
    # F. Uncalibrated upload: identification skipped and the user is told why
    import math
    ctx_f = browser.new_context(viewport={"width": 1400, "height": 1000})
    pf = ctx_f.new_page()
    rows = [int(20 + 900 * math.exp(-((i - 200) ** 2) / 50) + 400 * math.exp(-((i - 500) ** 2) / 120)) for i in range(1024)]
    csv = ("Data,Energy\n" + "\n".join(f"{v},{i}" for i, v in enumerate(rows)) + "\n").encode()
    pf.goto(URL, wait_until="networkidle")
    pf.set_input_files("#file-input", files=[{"name": "channels.csv", "mimeType": "text/csv", "buffer": csv}])
    pf.wait_for_selector("#dashboard", state="visible", timeout=20000)
    pf.wait_for_timeout(1000)
    toasts = pf.eval_on_selector_all(".toast", "els => els.map(e => e.textContent)")
    check("F uncalibrated upload shows calibration warning toast", any("calibration" in t.lower() for t in toasts), str(toasts)[:90])
    check("F no isotope/chain results for uncalibrated data",
          not pf.evaluate("() => { const c=document.getElementById('decay-chains-list'); return !!c && c.children.length>0 }"))
    ctx_f.close()
    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
