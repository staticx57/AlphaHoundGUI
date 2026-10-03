"""
Headless-browser UI smoke test (not collected by pytest).

Needs: pip install playwright, Google Chrome installed, and the server running
at http://localhost:3200 (python main.py). Mocks the AlphaHound device status and
dose WebSocket, so no hardware is required. Screenshots go to tests/ui_smoke_out/.

    python backend/tests/ui_smoke.py
"""
import json, os, re as _re, sys
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # card text contains symbols the Windows console codepage cannot print
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ui_smoke_out")
os.makedirs(OUT, exist_ok=True)
URL = os.environ.get("ALPHAHOUND_URL", "http://localhost:3200").rstrip("/") + "/"   # another port: ALPHAHOUND_URL
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
    # The page restores a live Radiacode connection on load, so a real device connected to the server
    # (or an AlphaHound) would leak into every test: mock "disconnected" for all contexts (page-level routes still override).
    _new_context = browser.new_context

    def _isolated_context(*args, **kwargs):
        ctx = _new_context(*args, **kwargs)
        ctx.route("**/radiacode/status", lambda route, request: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"connected": False, "available": True, "device_info": None, "last_error": None})))
        ctx.route("**/device/status", lambda route, request: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"connected": False, "dose_rate": None, "temperature": None, "comp_factor": None, "cps": None})))
        return ctx
    browser.new_context = _isolated_context

    # A. Plain load
    errs = []
    ctx, page = new_page(browser, errs)
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(OUT, "a_load.png"))
    check("A page loads without JS errors", not errs, "; ".join(errs[:3]))
    check("A disconnected label reads 'Not connected'", page.inner_text("#device-conn-label") == "Not connected")
    check("A controls that need a device are collapsed while nothing is connected",
          not page.is_visible("#btn-start-acquire") and not page.is_visible("#btn-reset-dose"))

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
        ws.send(json.dumps({"dose_rate": 2500.0}))      # an alert needs two readings above the limit in a row

    page.route_web_socket("**/ws/dose", ws_handler)
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(OUT, "b_dose.png"))
    text = page.inner_text("#rc-dose-display")
    check("B dose readout updated", "2.50 mRem/h" in text, text)
    alert_visible = page.evaluate(
        "() => { const a=document.getElementById('safety-alert'); return !!a && !a.hidden }")
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
    # G. Radiacode connection state: Disconnect resets the button; a lost connection is noticed
    import json as _json
    def rc_page(dose_ok_count):
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        state = {"dose_calls": 0}
        pg.route("**/radiacode/connect", lambda route, request: route.fulfill(
            status=200, content_type="application/json", body=_json.dumps({"device_info": {"model": "RadiaCode-110"}})))
        pg.route("**/radiacode/disconnect", lambda route, request: route.fulfill(
            status=200, content_type="application/json", body="{}"))
        pg.route("**/radiacode/info/extended", lambda route, request: route.fulfill(
            status=200, content_type="application/json", body="{}"))

        def dose(route, request):
            state["dose_calls"] += 1
            if state["dose_calls"] <= dose_ok_count:
                route.fulfill(status=200, content_type="application/json", body=_json.dumps({"dose_rate_uSv_h": 1.2}))
            else:
                route.fulfill(status=400, content_type="application/json", body=_json.dumps({"detail": "Radiacode not connected"}))
        pg.route("**/radiacode/dose", dose)
        pg.goto(URL, wait_until="networkidle")
        pg.click("#tab-radiacode")
        pg.click("#btn-connect-radiacode")
        pg.wait_for_function("document.getElementById('device-conn-label').textContent === 'Connected'", timeout=8000)
        return ctx, pg

    ctx_g, pg = rc_page(dose_ok_count=10_000)
    check("G connected state shown", pg.inner_text("#device-conn-label") == "Connected")
    pg.once("dialog", lambda d: d.accept())
    pg.click("#btn-disconnect-device")
    pg.wait_for_function("document.getElementById('device-conn-label').textContent === 'Not connected'", timeout=8000)
    check("G after Disconnect the Connect button reads 'Connect' and is visible",
          pg.inner_text("#btn-connect-radiacode") == "Connect" and pg.is_visible("#btn-connect-radiacode"))
    check("G after Disconnect the Disconnect button is hidden", not pg.is_visible("#btn-disconnect-device"))
    ctx_g.close()

    ctx_g, pg = rc_page(dose_ok_count=2)
    pg.wait_for_function("document.getElementById('device-conn-label').textContent === 'Not connected'", timeout=20000)
    check("G lost connection (server says 'not connected') resets the UI by itself",
          pg.inner_text("#btn-connect-radiacode") == "Connect" and pg.inner_text("#rc-dose-display") == "--")
    ctx_g.close()
    # H. Page refresh while the server is still connected to a Radiacode restores the UI
    ctx_h = browser.new_context(viewport={"width": 1400, "height": 1000})
    ph = ctx_h.new_page()
    ph.route("**/radiacode/status", lambda route, request: route.fulfill(
        status=200, content_type="application/json",
        body=_json.dumps({"connected": True, "available": True, "device_info": {"model": "RadiaCode-110"}, "last_error": None})))
    ph.route("**/radiacode/dose", lambda route, request: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps({"dose_rate_uSv_h": 0.12})))
    ph.route("**/radiacode/info/extended", lambda route, request: route.fulfill(
        status=200, content_type="application/json", body="{}"))
    ph.route("**/radiacode/alarm-limits", lambda route, request: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(
            {"l1_dose_rate": 0.5, "l2_dose_rate": 1.0, "l1_count_rate": 100, "l2_count_rate": 200, "count_unit": "cps",
             "l1_dose": None, "l2_dose": None, "dose_unit": "Sv"})))
    ph.goto(URL, wait_until="networkidle")
    ph.wait_for_function("document.getElementById('device-conn-label').textContent === 'Connected'", timeout=8000)
    check("H refresh restores connected state", ph.inner_text("#device-conn-label") == "Connected")
    ph.click("#tab-radiacode")
    check("H refresh shows Disconnect and hides Connect",
          ph.is_visible("#btn-disconnect-device") is True and not ph.is_visible("#btn-connect-radiacode"))
    ph.wait_for_function("document.getElementById('rc-dose-display').textContent !== '--'", timeout=8000)
    check("H refresh resumes dose polling", ph.inner_text("#rc-dose-display") != "--")
    ph.wait_for_function("document.getElementById('rc-alarm-limits').textContent.includes('Dose rate')", timeout=8000)
    limits_text = ph.text_content("#rc-alarm-limits")
    check("H the device's own alarm limits are shown (read-only) in the diagnostics",
          "0.50" in limits_text and "1.00" in limits_text and "100 cps / 200 cps" in limits_text, limits_text)
    ph.wait_for_function("document.getElementById('rc-dose-total').textContent !== 'Total --'", timeout=8000)
    check("H total dose is visible without opening Device Settings",
          ph.is_visible("#rc-dose-total") and "Total" in ph.inner_text("#rc-dose-total"), ph.inner_text("#rc-dose-total"))
    ctx_h.close()
    # I. AlphaHound (mocked): connect, details panel, CPS, sparkline, display replica, probe, disconnect
    import threading as _threading
    import time as _time
    ctx_i = browser.new_context(viewport={"width": 1400, "height": 1000})
    pi = ctx_i.new_page()
    errs_i = []
    pi.on("pageerror", lambda e: errs_i.append(f"pageerror: {e}"))
    pi.on("console", lambda m: errs_i.append(f"console.error: {m.text}") if m.type == "error" else None)
    ah = {"connected": False, "disconnect_calls": 0, "next_calls": 0, "details_status": 200, "clear_calls": 0}

    def _json_route(pattern, handler):
        pi.route(pattern, lambda route, request: handler(route, request))

    def _ok(route, body, status=200):
        route.fulfill(status=status, content_type="application/json", body=_json.dumps(body))

    _json_route("**/device/status", lambda r, q: _ok(r, {"connected": ah["connected"], "dose_rate": 70.0 if ah["connected"] else None,
                                                         "temperature": 29.5, "comp_factor": 0.95, "cps": None}))
    _json_route("**/device/ports", lambda r, q: _ok(r, {"ports": [{"device": "COM8", "description": "USB Serial Device (COM8)"}]}))

    def _connect(r, q):
        ah["connected"] = True
        _ok(r, {"status": "connected", "port": "COM8"})
    _json_route("**/device/connect", _connect)

    def _disconnect(r, q):
        ah["connected"] = False
        ah["disconnect_calls"] += 1
        _ok(r, {"status": "disconnected"})
    _json_route("**/device/disconnect", _disconnect)

    def _details(r, q):
        if ah["details_status"] != 200:
            _ok(r, {"detail": "Device not connected"}, ah["details_status"])
        else:
            _ok(r, {"model": "AlphaHound", "port": "COM8", "baudrate": 115200, "dose_rate_uRem_h": 70.0, "dose_rate_uSv_h": 0.7, "dose_rate_avg_uRem_h": 64.5,
                    "temperature": 29.5, "comp_factor": 0.95067, "cps": None, "cps_polling": True, "dose_log_entries": 42})
    _json_route("**/device/details", _details)

    def _next(r, q):
        ah["next_calls"] += 1
        _ok(r, {"status": "ok", "action": "display_next"})
    _json_route("**/device/display/next", _next)
    _json_route("**/device/probe", lambda r, q: _ok(r, {"command": "P", "lines": ["CPS:270.25,162.53,6.87,770.13"]}))
    def _clear(r, q):
        ah["clear_calls"] += 1
        _ok(r, {"status": "ok", "cleared": 42})
    _json_route("**/device/dose/log/clear", _clear)

    def _ws(w):
        def run():
            n = 0
            while True:
                try:
                    w.send(_json.dumps({"dose_rate": 60.0 + (n % 10), "dose_rate_avg": 64.5,
                                        "cps": {"gamma": 270.0 + n, "beta": 150.5, "alpha": 6.25, "dose": 770.0, "total": 426.75, "age_s": 0.2}}))
                    n += 1
                    _time.sleep(0.3)
                except Exception:
                    return
        _threading.Thread(target=run, daemon=True).start()
    pi.route_web_socket("**/ws/dose", _ws)
    pi.on("dialog", lambda d: (errs_i.append("native dialog: " + d.message), d.dismiss()))   # the page must not use alert()/confirm()

    pi.goto(URL, wait_until="networkidle")
    check("I before connecting the AlphaHound panels are hidden",
          not pi.is_visible("#alphahound-details-panel") and not pi.is_visible("#btn-disconnect-alphahound"))
    pi.select_option("#port-select", "COM8")
    pi.click("#btn-connect-device")
    pi.wait_for_function("document.getElementById('device-conn-label').textContent === 'Connected'", timeout=8000)
    pi.wait_for_function("/^[0-9]/.test(document.getElementById('ah-cps-gamma').textContent)", timeout=8000)
    check("I a Disconnect button is visible once connected", pi.is_visible("#btn-disconnect-alphahound"))
    check("I the empty connection box is hidden while connected", not pi.is_visible("#device-connection-box"))
    check("I the title row carries the port chip", "COM8" in pi.inner_text("#ah-title-chip") and pi.is_visible("#ah-title-chip"),
          pi.inner_text("#ah-title-chip"))
    pi.click("#tab-radiacode")
    check("I on the Radiacode tab the connection box is back and the AlphaHound Disconnect button is not shown",
          pi.is_visible("#device-connection-box") and not pi.is_visible("#btn-disconnect-alphahound"))
    pi.click("#tab-alphahound")
    check("I back on the AlphaHound tab the box is hidden again", not pi.is_visible("#device-connection-box")
          and pi.is_visible("#btn-disconnect-alphahound"))
    pi.set_viewport_size({"width": 1280, "height": 800})
    pi.wait_for_timeout(400)
    bottoms = pi.evaluate("""() => ({ acquire: document.getElementById('btn-start-acquire').getBoundingClientRect().bottom,
                                      live: document.querySelector('.device-live-data').getBoundingClientRect().bottom,
                                      height: innerHeight })""")
    check("I the whole device area fits a 1280x800 window", bottoms["acquire"] <= 800 and bottoms["live"] <= 800, str(bottoms))
    for width in (1000, 800):
        pi.set_viewport_size({"width": width, "height": 800})
        pi.wait_for_timeout(300)
        check(f"I no horizontal overflow at {width}px", pi.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    pi.set_viewport_size({"width": 1400, "height": 1000})
    pi.wait_for_timeout(300)
    check("I the details panel is visible", pi.is_visible("#alphahound-details-panel"))
    check("I port and log size come from /device/details",
          "COM8" in pi.inner_text("#ah-port") and "42" in pi.inner_text("#ah-log-count"), pi.inner_text("#ah-port"))
    cps_vals = pi.evaluate("""() => ['gamma', 'beta', 'alpha', 'total'].map(k => parseFloat(document.getElementById('ah-cps-' + k).textContent))""")
    check("I gamma/beta/alpha/total CPS are shown",
          cps_vals[0] >= 270 and abs(cps_vals[1] - 150.5) < 0.01 and abs(cps_vals[2] - 6.25) < 0.01
          and abs(cps_vals[3] - (cps_vals[0] + cps_vals[1] + cps_vals[2])) < 0.02,   # the gamma channel moves in the mock; the total is the sum
          str(cps_vals))
    check("I real-time dose is shown", "\u00b5Rem" in pi.inner_text("#rc-dose-display") and pi.inner_text("#rc-dose-display")[:2].strip().isdigit(),
          pi.inner_text("#rc-dose-display"))
    spark_js = """() => { const c = document.getElementById('rcDoseRateChart'); const ch = window.Chart && Chart.getChart(c);
                          return ch ? ch.data.datasets[0].data.filter(v => v !== null).length : -1 }"""
    pi.wait_for_function(f"({spark_js})() >= 3", timeout=6000)
    spark_points = pi.evaluate(spark_js)
    check("I the live dose sparkline is drawing for the AlphaHound", spark_points >= 2, str(spark_points))
    chart_js = """() => { const ch = window.Chart && Chart.getChart(document.getElementById('ch-chart'));
                          return ch ? ch.data.datasets.map(d => d.data.filter(p => p && p.y !== null).length) : [-1] }"""
    pi.wait_for_function(f"({chart_js})().length === 3 && ({chart_js})().every(n => n >= 3)", timeout=8000)
    check("I the channel history chart has gamma / beta / alpha lines", pi.evaluate(chart_js)[:3] and all(n >= 3 for n in pi.evaluate(chart_js)),
          str(pi.evaluate(chart_js)))
    look = pi.evaluate("""() => { const ch = Chart.getChart(document.getElementById('ch-chart'));
          return { colors: ch.data.datasets.map(d => d.borderColor), dashes: ch.data.datasets.map(d => (d.borderDash || []).join(',')) } }""")
    check("I the three channels differ by colour and by line pattern (not colour alone)",
          len(set(look["colors"])) == 3 and len(set(look["dashes"])) == 3, str(look))
    cards = pi.evaluate("""() => [...document.querySelectorAll('.ch-card')].map(c => ({
          ch: c.dataset.channel, fill: c.querySelector('.ch-meter-fill').style.width,
          avg: c.querySelector('[data-ch=avg]').textContent, peak: c.querySelector('[data-ch=peak]').textContent }))""")
    check("I each channel card shows a meter, a 1-minute average and a peak",
          len(cards) == 3 and all(c["fill"] not in ("", "0%") and c["avg"] != "--" and c["peak"] != "--" for c in cards), str(cards))
    share = pi.evaluate("""() => ['gamma', 'beta', 'alpha'].map(k => parseFloat(document.querySelector('[data-mix=' + k + ']').style.flexGrow))""")
    check("I the share-of-counts bar adds up to the whole", abs(sum(share) - 1) < 0.01, str(share))
    pi.click("[data-ch-unit-btn=CPM]")
    check("I the CPM switch converts the readings (x60)", abs(float(pi.inner_text("#ah-cps-beta").replace(",", "")) - 9030) < 1, pi.inner_text("#ah-cps-beta"))
    check("I the unit choice is a pressed toggle", pi.get_attribute("[data-ch-unit-btn=CPM]", "aria-pressed") == "true")
    pi.click("[data-ch-unit-btn=CPS]")
    pi.click("[data-ch-scale=log]")
    check("I the history chart can switch to a log axis", pi.evaluate("Chart.getChart(document.getElementById('ch-chart')).options.scales.y.type") == "logarithmic")
    pi.click("[data-ch-scale=linear]")
    pi.click("[data-ch-window='60']")
    check("I the history window can be shortened", pi.evaluate("Chart.getChart(document.getElementById('ch-chart')).options.scales.x.min") == -60)
    pi.click("[data-ch-window='300']")
    check("I the smoothed dose is shown", "64.5" in pi.inner_text("#ah-dose-avg") and "0.65" in pi.inner_text("#ah-dose-avg"), pi.inner_text("#ah-dose-avg"))
    check("I the display replica offers every mode and four slots",
          pi.evaluate("document.getElementById('ah-screen-mode').options.length") == 12
          and pi.evaluate("document.getElementById('ah-screen-slot').options.length") == 4)
    check("I the replica starts on slot M1", pi.input_value("#ah-screen-slot") == "1")
    pi.select_option("#ah-screen-mode", "4")
    pi.wait_for_timeout(600)
    lit = pi.evaluate("""() => { const c = document.getElementById('ah-screen'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
                                  let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] > 100) n++; return n / (d.length / 4) }""")
    check("I the replica draws the ABY split screen", lit > 0.05, f"{lit:.3f} of the pixels lit")
    check("I the replica is rendered at 4x (512 px)", pi.evaluate("document.getElementById('ah-screen').width") == 512)
    pi.click("#btn-screen-next")
    pi.wait_for_function("document.getElementById('ah-screen-slot').value === '2'", timeout=4000)
    check("I the replica's arrow presses the device's display button and steps to the next SLOT",
          ah["next_calls"] == 1 and pi.input_value("#ah-screen-mode") == "9", pi.input_value("#ah-screen-mode"))
    pi.select_option("#ah-screen-slot", "3")
    check("I picking a slot shows the mode that slot holds", pi.input_value("#ah-screen-mode") == "1")
    pi.select_option("#ah-screen-mode", "12")
    pi.select_option("#ah-screen-slot", "1")
    check("I changing a slot's mode leaves the other slots alone",
          pi.input_value("#ah-screen-mode") == "4" and ah["next_calls"] == 1)
    pi.select_option("#ah-screen-slot", "3")
    check("I the new mode was kept in that slot", pi.input_value("#ah-screen-mode") == "12")
    pi.reload(wait_until="networkidle")
    pi.wait_for_function("document.getElementById('ah-screen-slot').value === '3'", timeout=8000)
    check("I the slots and the current slot are remembered across a reload",
          pi.input_value("#ah-screen-mode") == "12")
    pi.click(".ah-probe summary")
    pi.select_option("#ah-probe-cmd", "P")
    pi.click("#btn-probe")
    pi.wait_for_function("document.getElementById('ah-probe-output').textContent.includes('CPS:')", timeout=4000)
    check("I probe shows the raw reply", "270.25" in pi.inner_text("#ah-probe-output"))
    pi.click("#btn-dose-clear")
    pi.wait_for_selector(".app-dialog", state="visible", timeout=4000)
    check("I Clear dose log asks in an in-page dialog that names the action",
          "Clear" in pi.inner_text(".app-dialog-title") and pi.is_visible(".app-dialog-danger"))
    check("I a dangerous action focuses Cancel, so Enter does not confirm it",
          pi.evaluate("document.activeElement && document.activeElement.classList.contains('app-dialog-cancel')"))
    pi.keyboard.press("Escape")
    pi.wait_for_selector(".app-dialog", state="detached", timeout=4000)
    check("I Esc cancels without clearing", ah["clear_calls"] == 0)
    pi.click("#btn-dose-clear")
    pi.wait_for_selector(".app-dialog", state="visible", timeout=4000)
    pi.click(".app-dialog-ok")
    pi.wait_for_function("document.querySelector('.toast')?.textContent?.includes('cleared')", timeout=4000)
    check("I confirming clears the log and shows a toast", ah["clear_calls"] == 1)
    pi.click("#btn-disconnect-alphahound")
    pi.wait_for_function("document.getElementById('device-conn-label').textContent === 'Not connected'", timeout=8000)
    check("I Disconnect calls the server and restores the connect controls",
          ah["disconnect_calls"] == 1 and pi.is_visible("#btn-connect-device") and not pi.is_visible("#btn-disconnect-alphahound"))
    check("I the details panel is hidden again", not pi.is_visible("#alphahound-details-panel"))
    check("I the channel panel is cleared on disconnect", pi.evaluate("""() => { const ch = Chart.getChart(document.getElementById('ch-chart'));
          return document.getElementById('ah-cps-gamma').textContent === '--' && (!ch || ch.data.datasets.every(d => d.data.length === 0)) }"""))
    check("I the replica shows NO DEVICE when disconnected", pi.evaluate("""() => { const c = document.getElementById('ah-screen');
          const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0;
          for (let i = 0; i < d.length; i += 4) if (d[i] > 100) n++; return n / (d.length / 4) < 0.06 }"""))
    check("I the connection box and Connect button are back after disconnecting",
          pi.is_visible("#device-connection-box") and pi.is_visible("#btn-connect-device") and not pi.is_visible("#ah-title-chip"))
    check("I no JS errors during the AlphaHound flow", not errs_i, "; ".join(errs_i[:3]))
    ctx_i.close()

    # J. A connection that disappears behind the page's back is noticed (details keep answering 400)
    ctx_j = browser.new_context(viewport={"width": 1400, "height": 1000})
    pj = ctx_j.new_page()
    pj.clock.install()
    state_j = {"connected": True}
    pj.route("**/device/status", lambda route, request: route.fulfill(status=200, content_type="application/json", body=_json.dumps(
        {"connected": state_j["connected"], "dose_rate": 70.0, "temperature": 29.5, "comp_factor": 0.95, "cps": None})))
    pj.route("**/device/details", lambda route, request: route.fulfill(status=400, content_type="application/json",
                                                                      body=_json.dumps({"detail": "Device not connected"})))
    pj.route_web_socket("**/ws/dose", lambda w: None)
    pj.goto(URL, wait_until="domcontentloaded")
    pj.wait_for_function("document.getElementById('device-conn-label').textContent === 'Connected'", timeout=8000)
    pj.clock.run_for(17000)
    pj.wait_for_function("document.getElementById('device-conn-label').textContent === 'Not connected'", timeout=8000)
    check("J three 'not connected' answers reset the AlphaHound UI", pj.is_visible("#btn-connect-device"))
    ctx_j.close()
    # K. A spectrum whose calibration starts above zero: round axis ticks, no negative zoom label, readable start time
    import pathlib as _pl
    sys.path.insert(0, str(_pl.Path(HERE).parent))
    from formats.n42_exporter import generate_n42_xml as _gen
    _offset_file = os.path.join(OUT, "offset_axis.n42")
    _energies = [5.56 + 2.364 * i + 0.000378 * i * i for i in range(1024)]
    _counts = [int(2000 * 2.718 ** (-i / 150) + 900 * 2.718 ** (-((i - 255) / 7) ** 2) + 30) for i in range(1024)]
    open(_offset_file, "w", encoding="utf-8").write(_gen({
        "counts": _counts, "energies": _energies,
        "metadata": {"live_time": 600.0, "real_time": 600.0, "start_time": "2026-10-02T17:43:30.903564+00:00"}}))
    ctx_k = browser.new_context(viewport={"width": 1400, "height": 900})
    pk = ctx_k.new_page()
    errs_k = []
    pk.on("pageerror", lambda e: errs_k.append(f"pageerror: {e}"))
    pk.on("dialog", lambda d: (errs_k.append("native dialog: " + d.message), d.dismiss()))
    pk.goto(URL, wait_until="networkidle")
    pk.set_input_files("#file-input", _offset_file)
    pk.wait_for_selector("#dashboard", state="visible", timeout=20000)
    pk.wait_for_function("window.Chart && Chart.getChart(document.getElementById('spectrumChart'))", timeout=10000)
    pk.wait_for_timeout(800)
    ticks = pk.evaluate("() => Chart.getChart(document.getElementById('spectrumChart')).scales.x.ticks.map(t => t.value)")
    step = ticks[1] - ticks[0] if len(ticks) > 1 else 0
    check("K the energy axis ticks are round numbers (100, 200, ...) not offsets from the axis minimum",
          len(ticks) >= 4 and step in (10, 20, 25, 50, 100, 200, 250, 500) and all(abs(t / step - round(t / step)) < 1e-9 for t in ticks),
          str(ticks[:6]))
    check("K the axis has no negative tick", all(t >= 0 for t in ticks))
    check("K the zoom bar does not start at a negative energy", not pk.inner_text("#zoom-min-label").strip().startswith("-"),
          pk.inner_text("#zoom-min-label"))
    start_card = pk.evaluate("""() => { const c = [...document.querySelectorAll('.stat-card')].find(e => /start time/i.test(e.textContent));
                                       return c ? c.querySelector('.stat-value').textContent.trim() : null }""")
    check("K the start time is shown as a readable local time, not ISO text",
          start_card is not None and "T17" not in start_card and "+00:00" not in start_card and len(start_card) < 28, str(start_card))
    check("K no native dialogs and no JS errors while loading a spectrum", not errs_k, "; ".join(errs_k[:3]))
    ctx_k.close()

    # L. Phone width: tabs side by side, no horizontal overflow
    ctx_l = browser.new_context(viewport={"width": 390, "height": 844})
    pl = ctx_l.new_page()
    pl.goto(URL, wait_until="networkidle")
    tops = pl.evaluate("""() => ['tab-alphahound', 'tab-radiacode'].map(id => Math.round(document.getElementById(id).getBoundingClientRect().top))""")
    check("L on a phone the device tabs sit side by side", abs(tops[0] - tops[1]) < 4, str(tops))
    check("L no horizontal overflow at 390px", pl.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    check("L the port list uses short names",
          all(len(o) < 32 for o in pl.evaluate("[...document.querySelectorAll('#port-select option')].map(o => o.textContent)")))
    ctx_l.close()

    # M. Result summary above the chart, peaks beside identification, one request per AI run, AI answer tied to its spectrum
    ctx_m = browser.new_context(viewport={"width": 1400, "height": 1000})
    pm = ctx_m.new_page()
    errs_m = []
    ai_calls = {"n": 0}
    pm.on("pageerror", lambda e: errs_m.append(f"pageerror: {e}"))
    pm.on("dialog", lambda d: (errs_m.append("native dialog: " + d.message), d.dismiss()))

    def _ai(route, request):
        ai_calls["n"] += 1
        route.fulfill(status=200, content_type="application/json", body=_json.dumps(
            {"predictions": [{"isotope": "Cs-137", "confidence": 88.0, "method": "mlp"}, {"isotope": "Ba-133", "confidence": 6.0, "method": "mlp"}],
             "quality": "good"}))
    pm.route("**/analyze/ml-identify", _ai)
    pm.goto(URL, wait_until="networkidle")
    pm.set_input_files("#file-input", SPEC)
    pm.wait_for_selector("#result-summary", state="visible", timeout=20000)
    pm.wait_for_function("window.Chart && Chart.getChart(document.getElementById('spectrumChart'))", timeout=10000)
    check("M the headline names the isotope", pm.inner_text("#rs-name").strip() == "Cs-137", pm.inner_text("#rs-name"))
    # the peak count on the card must agree with the table (the number itself depends on detection details)
    check("M the headline shows confidence and the supporting numbers",
          "95" in pm.inner_text("#rs-conf") and pm.inner_text("#rs-peaks").strip() == str(pm.locator("#peaks-tbody tr").count()) and pm.inner_text("#rs-counts").strip() != "--"
          and "cps" in pm.inner_text("#rs-rate") and "min" in pm.inner_text("#rs-live"),
          " | ".join(pm.inner_text(i).strip() for i in ("#rs-conf", "#rs-peaks", "#rs-counts", "#rs-rate", "#rs-live")))
    pos = pm.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
        return { summaryBottom: r('#result-summary').bottom, chartTop: r('.chart-container').top,
                 peaksLeft: r('#peaks-container').left, peaksTop: r('#peaks-container').top, peaksRight: r('#peaks-container').right,
                 isoLeft: r('#isotopes-container').left, isoTop: r('#isotopes-container').top } }""")
    check("M the headline sits above the chart", pos["summaryBottom"] <= pos["chartTop"], str(pos))
    check("M peaks and identification sit side by side on a wide screen",
          abs(pos["peaksTop"] - pos["isoTop"]) < 4 and pos["peaksRight"] <= pos["isoLeft"], str(pos))
    text = pm.inner_text("body")
    check("M the labels say what they mean (Experimental, Line Matching; no WIP / Legacy)",
          "experimental" in text.lower() and "line matching" in text.lower()
          and not _re.search(r"\bwip\b", text.lower()) and "legacy" not in text.lower())
    heads = pm.evaluate("[...document.querySelectorAll('#peaks-table thead th')].map(t => t.textContent.trim())")
    check("M the peaks table has energy, counts, FWHM and matches", len(heads) == 4 and "FWHM" in heads[2] and "Matches" in heads[3], str(heads))
    matches = pm.evaluate("""() => [...document.querySelectorAll('#peaks-tbody tr')].map(r => r.querySelector('.peak-matches').textContent.trim())""")
    # exactly one row carries the Cs-137 label; how many noise peaks a synthetic spectrum yields is not the point
    check("M the 662 keV peak is labelled Cs-137 and unrelated peaks are not", matches.count("Cs-137") == 1 and len(matches) >= 4, str(matches))
    pm.click("#peaks-tbody tr:nth-child(4)")
    marked = pm.evaluate("""() => ({ roi: !!window.chartManager.annotations.roiHighlight, pressed: document.querySelector('#peaks-tbody tr:nth-child(4)').getAttribute('aria-pressed') })""")
    check("M clicking a peak row marks that peak on the chart", marked["roi"] and marked["pressed"] == "true", str(marked))
    pm.click("#peaks-tbody tr:nth-child(4)")
    check("M clicking it again clears the mark", not pm.evaluate("!!window.chartManager.annotations.roiHighlight"))
    pm.focus("#peaks-tbody tr:nth-child(2)")
    pm.keyboard.press("Enter")
    check("M the rows work from the keyboard", pm.evaluate("!!window.chartManager.annotations.roiHighlight"))
    pm.keyboard.press("Enter")
    check("M the AI answer starts as not run", "Not run" in pm.inner_text("#rs-ai-text") and "Not run yet" in pm.inner_text("#ml-isotopes-list"))
    pm.click("#btn-run-ml")
    pm.wait_for_function("document.getElementById('rs-ai-text').textContent.includes('Cs-137')", timeout=8000)
    check("M one click sends one AI request", ai_calls["n"] == 1, str(ai_calls["n"]))
    check("M the headline shows the AI answer and whether it agrees with line matching",
          "88" in pm.inner_text("#rs-ai-text") and "agrees" in pm.inner_text("#rs-ai-verdict"),
          pm.inner_text("#rs-ai-text") + " / " + pm.inner_text("#rs-ai-verdict"))
    check("M the AI list shows both predictions", pm.locator("#ml-isotopes-list .ai-pred").count() == 2)
    check("M the analysis panel was left alone by the isotopes-box button", "Run Peak Fitting" in pm.inner_text("#analysis-results") or "Click" in pm.inner_text("#analysis-results"))
    pm.click("#btn-rs-ai")
    pm.wait_for_timeout(600)
    check("M the summary button runs it again", ai_calls["n"] == 2, str(ai_calls["n"]))
    pm.set_input_files("#file-input", _offset_file)
    pm.wait_for_function("document.getElementById('rs-ai-text').textContent.includes('Not run')", timeout=10000)
    check("M loading a different spectrum drops the old AI answer", "Not run yet" in pm.inner_text("#ml-isotopes-list"))
    pm.set_viewport_size({"width": 800, "height": 900})
    pm.wait_for_timeout(300)
    pos = pm.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
        return { peaksTop: r('#peaks-container').top, isoTop: r('#isotopes-container').top, over: document.documentElement.scrollWidth - innerWidth } }""")
    check("M below 900 px peaks and identification stack", pos["isoTop"] > pos["peaksTop"], str(pos))
    pm.set_viewport_size({"width": 390, "height": 844})
    pm.wait_for_timeout(300)
    check("M no horizontal overflow with a result on a phone", pm.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    phone = pm.evaluate("""() => { const q = (x) => document.querySelector(x); const cards = [...document.querySelectorAll('#metadata-panel .stat-card')];
        const tops = new Set(cards.map((c) => Math.round(c.getBoundingClientRect().top)));
        const area = q('#peaks-scroll-area'); const table = q('#peaks-table');
        return { chartH: Math.round(q('#spectrumChart').getBoundingClientRect().height), rows: tops.size, cards: cards.length,
                 tableFits: table.scrollWidth <= area.clientWidth + 2 } }""")
    check("M on a phone the spectrum is tall enough to read", phone["chartH"] >= 200, str(phone))
    check("M on a phone the metadata cards sit two per row", phone["rows"] <= (phone["cards"] + 1) // 2, str(phone))
    check("M on a phone the peaks table fits without sideways scrolling", phone["tableFits"], str(phone))
    check("M no JS errors or native dialogs", not errs_m, "; ".join(errs_m[:3]))
    ctx_m.close()

    # N. Alerts and the dose-unit preference (AlphaHound mocked: dose ~0.65 uSv/h, ~430 cps)
    import sys as _sys
    _sys.path.insert(0, HERE)
    from ah_mock import install as _install_ah
    ctx_n = browser.new_context(viewport={"width": 1400, "height": 1000})
    pn = ctx_n.new_page()
    errs_n = []
    pn.on("pageerror", lambda e: errs_n.append(f"pageerror: {e}"))
    pn.on("dialog", lambda d: (errs_n.append("native dialog: " + d.message), d.dismiss()))
    pn.add_init_script("""
        if (!localStorage.getItem('alertSettings')) {
            localStorage.setItem('alertSettings', JSON.stringify({ doseEnabled: true, doseUSvH: 0.5, cpsEnabled: true, cps: 300 }));
        }
        window.__beeps = 0;
        window.AudioContext = class {
            constructor() { this.currentTime = 0; this.destination = {}; }
            createOscillator() { window.__beeps++; return { frequency: {}, connect() { return { connect() {} }; }, start() {}, stop() {} }; }
            createGain() { return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() { return { connect() {} }; } }; }
        };
    """)
    _install_ah(pn, burst=0)
    pn.goto(URL, wait_until="networkidle")
    pn.select_option("#port-select", "COM8")
    pn.click("#btn-connect-device")
    pn.wait_for_function("document.getElementById('device-conn-label').textContent === 'Connected'", timeout=8000)
    pn.wait_for_function("(() => { const a = document.getElementById('safety-alert'); return !!a && !a.hidden })()", timeout=10000)
    banner = pn.inner_text("#safety-alert")
    check("N a dose above the user's limit raises the banner (two readings in a row)", "High dose rate" in banner, banner)
    check("N the count-rate limit raises its own line", "High count rate" in banner and "cps" in banner, banner)
    check("N the banner is a live alert region and the readout is tinted",
          pn.get_attribute("#safety-alert", "role") == "alert" and "dose-alert" in pn.get_attribute("#rc-dose-display", "class"))
    check("N the banner offers a Dismiss button that is reachable", pn.is_visible("#safety-alert .safety-dismiss"))
    pn.click("#safety-alert .safety-dismiss")
    pn.wait_for_timeout(1400)
    check("N a dismissed banner stays away while the same alert continues", pn.evaluate("document.getElementById('safety-alert').hidden"))
    pn.click("#btn-settings")
    check("N Settings shows the limits in the unit on screen (uRem/h by default for the AlphaHound)",
          abs(float(pn.input_value("#pref-alert-dose-value")) - 50) < 0.01 and "Rem" in pn.inner_text("#pref-alert-dose-unit"),
          pn.input_value("#pref-alert-dose-value") + " " + pn.inner_text("#pref-alert-dose-unit"))
    pn.click("#pref-alert-sound")
    pn.fill("#pref-alert-dose-value", "1000")
    pn.press("#pref-alert-dose-value", "Tab")
    pn.wait_for_function("!document.getElementById('rc-dose-display').classList.contains('dose-alert')", timeout=5000)
    check("N raising the dose limit ends that alert at once", True)
    pn.click("#pref-alert-cps")
    pn.wait_for_function("document.getElementById('safety-alert').hidden", timeout=5000)
    check("N switching the count alert off clears the banner", True)
    pn.select_option("#pref-dose-unit", "uSv")
    pn.wait_for_function("document.getElementById('rc-dose-display').textContent.includes('Sv/h')", timeout=6000)
    check("N the dose unit preference changes the live readout", "µSv/h" in pn.inner_text("#rc-dose-display"), pn.inner_text("#rc-dose-display"))
    pn.wait_for_function("document.getElementById('ah-dose').textContent.trim().startsWith('0.')", timeout=6000)
    check("N ... and the details panel shows the chosen unit first and the other in brackets",
          pn.inner_text("#ah-dose").count("Rem") == 1 and pn.inner_text("#ah-dose").index("Sv") < pn.inner_text("#ah-dose").index("Rem"),
          pn.inner_text("#ah-dose"))
    check("N the limit field converts with the unit (1000 uRem/h = 10 uSv/h)",
          abs(float(pn.input_value("#pref-alert-dose-value")) - 10) < 0.001 and "Sv" in pn.inner_text("#pref-alert-dose-unit"),
          pn.input_value("#pref-alert-dose-value"))
    pn.fill("#pref-alert-dose-value", "0.3")
    pn.press("#pref-alert-dose-value", "Tab")
    pn.wait_for_function("(() => { const a = document.getElementById('safety-alert'); return !a.hidden })()", timeout=6000)
    check("N lowering the limit raises a new alert, which shows the dose in the chosen unit",
          "Sv/h" in pn.inner_text("#safety-alert") and "Rem" not in pn.inner_text("#safety-alert"), pn.inner_text("#safety-alert"))
    check("N the beep plays when an alert starts and sound is on", pn.evaluate("window.__beeps") >= 2, str(pn.evaluate("window.__beeps")))
    saved = pn.evaluate("({ unit: localStorage.getItem('doseUnit'), alerts: JSON.parse(localStorage.getItem('alertSettings')) })")
    check("N the choices are remembered", saved["unit"] == "uSv" and abs(saved["alerts"]["doseUSvH"] - 0.3) < 1e-9 and saved["alerts"]["sound"] is True
          and saved["alerts"]["cpsEnabled"] is False, str(saved))
    pn.click("#btn-alert-reset")
    check("N Reset restores the defaults", pn.input_value("#pref-dose-unit") == "auto" and pn.is_checked("#pref-alert-dose")
          and not pn.is_checked("#pref-alert-sound") and abs(float(pn.input_value("#pref-alert-dose-value")) - 2000) < 0.01,
          pn.input_value("#pref-alert-dose-value"))
    check("N no JS errors or native dialogs", not errs_n, "; ".join(errs_n[:3]))
    ctx_n.close()

    # O. Robustness: no internet, PDF download, unreadable files, Settings persistence, calculators, upload while streaming
    ctx_o = browser.new_context(viewport={"width": 1400, "height": 1000})
    external = []

    def _gate(route, request):
        if request.url.startswith(URL.rstrip("/")) or request.url.startswith(("data:", "blob:")):
            route.fallback()
        else:
            external.append(request.url)
            route.abort()
    ctx_o.route("**/*", _gate)               # an offline machine, or a LAN client without internet
    po = ctx_o.new_page()
    errs_o = []
    po.on("pageerror", lambda e: errs_o.append(f"pageerror: {e}"))
    po.on("dialog", lambda d: (errs_o.append("native dialog: " + d.message), d.dismiss()))
    po.goto(URL, wait_until="load")
    po.set_input_files("#file-input", SPEC)
    po.wait_for_selector("#dashboard", state="visible", timeout=20000)
    po.wait_for_function("window.Chart && Chart.getChart(document.getElementById('spectrumChart'))", timeout=10000)
    check("O the charting libraries come from the app, so charts work with no internet",
          not any(("jsdelivr" in u or "cdnjs" in u) for u in external), ", ".join(external[:3]))
    with po.expect_download(timeout=20000) as dl:
        po.click("#btn-export-pdf")
    download = dl.value
    with open(download.path(), "rb") as fh:
        head = fh.read(8)
    check("O PDF export downloads a real PDF file", head.startswith(b"%PDF-") and download.suggested_filename.endswith("_report.pdf"),
          f"{download.suggested_filename} {head!r}")
    check("O ... without opening a pop-up tab", len(ctx_o.pages) == 1)
    with po.expect_response(lambda r: r.url.endswith("/upload"), timeout=20000) as bad:
        po.set_input_files("#file-input", files=[{"name": "words.csv", "mimeType": "text/csv", "buffer": b"this,is,not\nnumbers,at,all\n"}])
    check("O an unreadable CSV is refused with a client error", bad.value.status == 400, str(bad.value.status))
    po.wait_for_function("document.getElementById('drop-zone').textContent.includes('Error')", timeout=5000)
    shown = po.inner_text("#drop-zone")
    check("O the drop zone says what was wrong and offers to try again", "not a number" in shown and po.locator("#drop-zone #file-input").count() == 1, shown[:120])
    po.set_input_files("#file-input", SPEC)
    po.wait_for_function("document.getElementById('rs-name').textContent.trim() === 'Cs-137'", timeout=20000)
    check("O after the failed upload a good file loads normally", True)
    # Settings persist across a reload (the Estimator lives in Expert mode: the simple layout hides the analysis tools)
    po.click("#btn-settings")
    po.check("input[name=ui-mode][value=expert]")
    po.click("#btn-apply-settings")
    po.reload(wait_until="load")
    po.click("#btn-settings")
    check("O the UI mode chosen in Settings is still selected after a reload", po.is_checked("input[name=ui-mode][value=expert]")
          and po.evaluate("JSON.parse(localStorage.getItem('analysisSettings')).uiMode") == "expert")
    po.click("#close-settings")
    # the calculators in the Estimator
    po.set_input_files("#file-input", SPEC)
    po.wait_for_selector("#dashboard", state="visible", timeout=20000)
    po.click("#btn-analysis")
    po.click("#btn-estimator-tool")
    po.wait_for_selector("#estimator-modal", state="visible")
    po.click("#tab-time-est")
    po.fill("#est-cpm", "1000")
    po.click("#btn-calc-time")
    po.wait_for_selector("#time-est-result", state="visible", timeout=5000)
    check("O the time calculator gives an answer", any(ch.isdigit() for ch in po.inner_text("#est-duration-result")), po.inner_text("#est-duration-result"))
    po.click("#tab-mda")
    po.click("#btn-calc-mda")
    po.wait_for_selector("#mda-result", state="visible", timeout=5000)
    check("O the MDA calculator gives an answer in Bq", "Bq" in po.inner_text("#mda-value") and any(ch.isdigit() for ch in po.inner_text("#mda-value")), po.inner_text("#mda-value"))
    po.keyboard.press("Escape")
    po.wait_for_function("getComputedStyle(document.getElementById('estimator-modal')).display === 'none'", timeout=3000)
    check("O Esc closes the Estimator", True)
    check("O no JS errors or native dialogs in these flows", not errs_o, "; ".join(errs_o[:3]))
    ctx_o.close()

    # P. A spectrum upload while the AlphaHound is streaming: the live sparkline keeps going and the page does not stall
    ctx_p = browser.new_context(viewport={"width": 1400, "height": 1000})
    pp = ctx_p.new_page()
    errs_p = []
    pp.on("pageerror", lambda e: errs_p.append(f"pageerror: {e}"))
    _install_ah(pp, burst=0)
    pp.goto(URL, wait_until="networkidle")
    pp.select_option("#port-select", "COM8")
    pp.click("#btn-connect-device")
    pp.wait_for_function("document.getElementById('device-conn-label').textContent === 'Connected'", timeout=8000)
    spark = """() => { const ch = window.Chart && Chart.getChart(document.getElementById('rcDoseRateChart'));
                       return ch ? ch.data.datasets[0].data.filter(v => v !== null).length : -1 }"""
    pp.wait_for_function(f"({spark})() >= 3", timeout=8000)
    before = pp.evaluate(spark)
    pp.evaluate("""() => { window.__gap = 0; let last = performance.now();
                           setInterval(() => { const n = performance.now(); window.__gap = Math.max(window.__gap, n - last - 100); last = n; }, 100); }""")
    pp.set_input_files("#file-input", SPEC)
    pp.wait_for_selector("#dashboard", state="visible", timeout=20000)
    pp.wait_for_timeout(2500)
    after = pp.evaluate(spark)
    check("P the live dose sparkline keeps drawing while a spectrum is uploaded", after > before or after >= 5, f"{before} -> {after}")
    check("P the page did not stall during the upload (longest main-thread pause under 1.5 s)", pp.evaluate("window.__gap") < 1500, str(pp.evaluate("window.__gap")))
    check("P the AlphaHound is still shown as connected", pp.inner_text("#device-conn-label") == "Connected")
    check("P no JS errors", not errs_p, "; ".join(errs_p[:3]))
    ctx_p.close()

    # Q. Metadata cards: readable labels, units in the values, related numbers in one card (was "MEAN DOSE RATE USV H", "0.123456")
    sys.path.insert(0, os.path.join(HERE, ".."))
    from formats.n42_exporter import generate_n42_xml as _gen_n42
    _meta = {"source": "AlphaHound AB+G", "instrument_model": "AlphaHound", "start_time": "2026-10-02T17:43:30.903564+00:00",
             "live_time": 300.0, "real_time": 300.0, "acquisition_time": 300.0, "device_duration_s": 298.4,
             "exposure_uSv": 0.123456, "mean_dose_rate_uSv_h": 1.482912, "max_dose_rate_uSv_h": 3.250001, "exposure_covered_s": 299.7,
             "exposure_method": "integrated instrument dose rate", "exposure_during_acquisition": "123.5 nSv (mean 1.483, max 3.250 \u00b5Sv/h)",
             "mean_cps_gamma": 271.456789, "mean_cps_beta": 150.5, "mean_cps_alpha": 6.25, "max_cps_total": 480.0}
    _counts = [int(30 * 2.718 ** (-i / 200) + (400 if 300 < i < 330 else 0)) for i in range(1024)]
    _meta_file = os.path.join(OUT, "acquisition_metadata.n42")
    with open(_meta_file, "w", encoding="utf-8") as fh:
        fh.write(_gen_n42({"counts": _counts, "energies": [i * 2.0 for i in range(1024)], "metadata": _meta, "filename": "acq.n42", "is_calibrated": True}))
    ctx_q = browser.new_context(viewport={"width": 1400, "height": 1000})
    pq = ctx_q.new_page()
    errs_q = []
    pq.on("pageerror", lambda e: errs_q.append(f"pageerror: {e}"))
    pq.goto(URL, wait_until="networkidle")
    pq.set_input_files("#file-input", _meta_file)
    pq.wait_for_selector("#metadata-panel .stat-card", state="visible", timeout=20000)
    cards = pq.evaluate("""() => [...document.querySelectorAll('#metadata-panel .stat-card')].map(c => ({
        label: c.querySelector('.stat-label').textContent.replace('\u24d8', '').trim(), text: c.innerText.replace(/\s+/g, ' ') }))""")
    labels = [c["label"] for c in cards]
    alltext = " ".join(c["text"] for c in cards)
    check("Q no card label shows a raw key or a mangled unit", not any(("_" in l) or l.upper().endswith((" USV H", " USV", " S")) for l in labels), str(labels))
    check("Q the dose figure is one card with mean and max rates in readable units",
          any(c["label"] == "Dose this acquisition" and "123.5 nSv" in c["text"] and "1.48 \u00b5Sv/h" in c["text"] and "3.25 \u00b5Sv/h" in c["text"] for c in cards),
          alltext[:300])
    check("Q the count rates are one card with the three channels", any(c["label"].startswith("Mean count rate") and "271.5" in c["text"] and "150.5" in c["text"] and "6.25" in c["text"] for c in cards))
    check("Q numbers are rounded (no 6-digit decimals)", not any(len(tok.split(".")[-1]) >= 5 for tok in alltext.replace(",", " ").split() if "." in tok and tok.replace(".", "").isdigit()), alltext[:200])
    check("Q the manufacturer is named instead of Unknown", "RadView Detection" in alltext and "Unknown" not in alltext, alltext[:200])
    check("Q the card count dropped from 15 to a handful", len(cards) <= 8, str(len(cards)))
    pq.click("#btn-settings")
    pq.select_option("#pref-dose-unit", "uRem")
    pq.wait_for_function("document.querySelector('#metadata-panel .stat-card[data-key=exposure]').innerText.includes('Rem')", timeout=4000)
    check("Q the dose unit preference redraws the cards", "\u00b5Rem/h" in pq.inner_text("#metadata-panel .stat-card[data-key=exposure]"),
          pq.inner_text("#metadata-panel .stat-card[data-key=exposure]"))
    check("Q no JS errors", not errs_q, "; ".join(errs_q[:3]))
    ctx_q.close()

    # R. The zoom bar and the chart agree: the preview is drawn in energy (a real calibration is not linear), handles sit on the
    # selection edges, the chart shows exactly the selected window, and a live update keeps the window the user chose
    _quad = [5.5 + 2.4 * i + 0.0004 * i * i for i in range(1024)]            # offset and a quadratic term, like a real Radiacode calibration
    _peak_ch = 300
    _quad_counts = [int(20 + 60 * 2.718 ** (-i / 150) + (900 if abs(i - _peak_ch) < 6 else 0) + (500 if abs(i - 700) < 8 else 0)) for i in range(1024)]
    _quad_file = os.path.join(OUT, "quadratic_calibration.n42")
    with open(_quad_file, "w", encoding="utf-8") as fh:
        fh.write(_gen_n42({"counts": _quad_counts, "energies": _quad, "metadata": {"source": "synthetic", "live_time": 600.0, "real_time": 600.0},
                           "filename": "quad.n42", "is_calibrated": True}))
    ctx_r = browser.new_context(viewport={"width": 1400, "height": 1000})
    pr = ctx_r.new_page()
    errs_r = []
    pr.on("pageerror", lambda e: errs_r.append(f"pageerror: {e}"))
    pr.goto(URL, wait_until="networkidle")
    pr.set_input_files("#file-input", _quad_file)
    pr.wait_for_selector("#zoom-scrubber", state="visible", timeout=20000)
    pr.wait_for_timeout(1500)
    geo = pr.evaluate("""() => { const cm = window.chartManager; const e = cm.fullEnergies, c = cm.fullCounts;
        const cv = document.getElementById('scrubber-preview'); const W = cv.width, H = cv.height;
        const img = cv.getContext('2d').getImageData(0, 0, W, H).data;
        const top = new Array(W).fill(H);
        for (let x = 0; x < W; x++) for (let y = 0; y < H; y++) { if (img[(y * W + x) * 4 + 3] > 200) { top[x] = y; break; } }
        const peaks = [300, 700].map((ch) => { let bx = -1, best = H;
            const lo = Math.floor(e[ch - 20] / cm.fullMaxEnergy * W), hi = Math.ceil(e[ch + 20] / cm.fullMaxEnergy * W);
            for (let x = lo; x <= hi; x++) if (top[x] < best) { best = top[x]; bx = x; }
            const flat = []; for (let x = lo; x <= hi; x++) if (top[x] <= best + 1) flat.push(x);   // a peak is a plateau of columns: use its middle
            bx = flat.length ? Math.round((flat[0] + flat[flat.length - 1]) / 2) : bx;
            return { seen: bx, byEnergy: Math.round(e[ch] / cm.fullMaxEnergy * W), byChannel: Math.round(ch / c.length * W) }; });
        return { W, peaks } }""")
    check("R the zoom bar preview draws each peak where its ENERGY is (not its channel number)",
          all(abs(pk["seen"] - pk["byEnergy"]) <= 8 and abs(pk["seen"] - pk["byEnergy"]) < abs(pk["seen"] - pk["byChannel"]) for pk in geo["peaks"])
          and all(abs(pk["byChannel"] - pk["byEnergy"]) > 20 for pk in geo["peaks"]), str(geo))   # a peak is a plateau of columns: a few px of slack
    pr.evaluate("""() => { const lo = document.getElementById('zoom-min'), hi = document.getElementById('zoom-max');
        lo.value = 20; lo.dispatchEvent(new Event('input')); hi.value = 60; hi.dispatchEvent(new Event('input')); }""")
    pr.wait_for_timeout(300)
    sync = pr.evaluate("""() => { const cm = window.chartManager; const x = cm.chart.scales.x;
        const sel = document.getElementById('scrubber-selection').getBoundingClientRect(); const bar = document.getElementById('scrubber-preview').getBoundingClientRect();
        const row = document.getElementById('zoom-min').getBoundingClientRect(); const centre = (v) => row.left + 8 + v / 100 * (row.width - 16) - bar.left;
        return { chartMin: x.min, chartMax: x.max, wantMin: 0.2 * cm.fullMaxEnergy, wantMax: 0.6 * cm.fullMaxEnergy,
                 selLeft: sel.left - bar.left, selRight: sel.right - bar.left, handleMin: centre(20), handleMax: centre(60) } }""")
    check("R the chart shows exactly the window the handles select", abs(sync["chartMin"] - sync["wantMin"]) < 1 and abs(sync["chartMax"] - sync["wantMax"]) < 1, str(sync))
    check("R the handles sit on the selection edges", abs(sync["selLeft"] - sync["handleMin"]) <= 1.5 and abs(sync["selRight"] - sync["handleMax"]) <= 1.5, str(sync))
    # a live update (same spectrum, more counts) keeps the chosen window; a new spectrum starts from the auto view
    kept = pr.evaluate("""() => { const cm = window.chartManager; const x = cm.chart.scales.x; const before = [x.min, x.max];
        const more = cm.fullCounts.map((v) => v + 5);
        cm.preserveZoom = true; cm.render(cm.fullEnergies, more, []); cm.showScrubber(cm.fullEnergies, more);
        const after = [cm.chart.scales.x.min, cm.chart.scales.x.max];
        const sliders = [parseFloat(document.getElementById('zoom-min').value), parseFloat(document.getElementById('zoom-max').value)];
        return { before, after, sliders, want: [20, 60] } }""")
    check("R a live update keeps the window the user chose (chart and handles)",
          abs(kept["after"][0] - kept["before"][0]) < 1 and abs(kept["after"][1] - kept["before"][1]) < 1
          and abs(kept["sliders"][0] - 20) < 0.5 and abs(kept["sliders"][1] - 60) < 0.5, str(kept))
    fresh = pr.evaluate("""() => { const cm = window.chartManager; const before = [cm.chart.scales.x.min, cm.chart.scales.x.max];
        cm.preserveZoom = false; cm.userZoom = null; cm.render(cm.fullEnergies, cm.fullCounts, []);
        return { before, after: [cm.chart.scales.x.min, cm.chart.scales.x.max] } }""")
    check("R without a live update the chart returns to its auto view", abs(fresh["after"][1] - fresh["before"][1]) > 50, str(fresh))
    # a real mouse drag of the left handle: chart and handle agree, and the handles cannot cross
    pr.locator("#zoom-min").scroll_into_view_if_needed()
    pr.wait_for_timeout(300)
    box = pr.locator("#zoom-min").bounding_box()
    bar = pr.locator("#scrubber-preview").bounding_box()
    y = box["y"] + box["height"] / 2
    pr.mouse.move(box["x"] + 8 + 0.0 * (box["width"] - 16), y)
    pr.mouse.down()
    pr.mouse.move(bar["x"] + bar["width"] * 0.9, y, steps=10)      # far past the right handle
    pr.mouse.up()
    pr.wait_for_timeout(300)
    drag = pr.evaluate("""() => { const cm = window.chartManager; const lo = parseFloat(document.getElementById('zoom-min').value), hi = parseFloat(document.getElementById('zoom-max').value);
        return { lo, hi, chartMin: cm.chart.scales.x.min, chartMax: cm.chart.scales.x.max, wantMin: lo / 100 * cm.fullMaxEnergy, wantMax: hi / 100 * cm.fullMaxEnergy } }""")
    check("R dragging the left handle past the right one is stopped, and the chart matches the handles",
          drag["lo"] <= drag["hi"] - 1.99 and abs(drag["chartMin"] - drag["wantMin"]) < 1 and abs(drag["chartMax"] - drag["wantMax"]) < 1, str(drag))
    check("R no JS errors in the zoom bar flows", not errs_r, "; ".join(errs_r[:3]))
    ctx_r.close()

    # S. Decay prediction: any isotope, any duration unit, curves that start where they should, the engine named, errors in words
    ctx_s = browser.new_context(viewport={"width": 1400, "height": 1000})
    ps = ctx_s.new_page()
    errs_s = []
    ps.on("pageerror", lambda e: errs_s.append(f"pageerror: {e}"))
    ps.on("dialog", lambda d: (errs_s.append("native dialog: " + d.message), d.dismiss()))
    ps.add_init_script("""localStorage.setItem('analysisSettings', JSON.stringify({ mode: 'simple', uiMode: 'expert', isotope_min_confidence: 40,
        chain_min_confidence: 30, energy_tolerance: 20, chain_min_isotopes_medium: 3, chain_min_isotopes_high: 4, max_isotopes: 5 }))""")
    ps.goto(URL, wait_until="networkidle")
    ps.set_input_files("#file-input", SPEC)
    ps.wait_for_selector("#dashboard", state="visible", timeout=20000)
    ps.click("#btn-analysis")
    ps.click("#btn-decay-tool")
    ps.wait_for_selector("#decay-modal", state="visible")
    ps.wait_for_function("document.querySelectorAll('#decay-isotope-list option').length > 40", timeout=8000)
    check("S the isotope field offers every isotope the engines know (and takes any typed name)",
          ps.get_attribute("#decay-isotope", "list") == "decay-isotope-list" and ps.evaluate("document.querySelectorAll('#decay-isotope-list option').length") > 40)
    engines = ps.evaluate("[...document.querySelectorAll('#decay-engine-select option')].map(o => o.value)")
    check("S the engine menu lists only real engines (no PyNE stand-in)", engines == ["auto", "builtin", "radioactivedecay", "curie"], str(engines))
    ps.fill("#decay-isotope", "cs137")
    ps.fill("#decay-activity", "10000")
    ps.fill("#decay-duration", "400")
    ps.click("#btn-run-decay")      # opening the modal already drew the default (U-238), so wait for OUR curve
    ps.wait_for_function("window.Chart && Chart.getChart(document.getElementById('decayChart'))?.data.datasets[0].label === 'Cs-137'", timeout=10000)
    chart = ps.evaluate("""() => { const c = Chart.getChart(document.getElementById('decayChart'));
        return { labels: c.data.datasets.map(d => d.label), first: c.data.datasets[0].data[0], last: c.data.datasets[0].data.slice(-1)[0],
                 lengths: [...new Set(c.data.datasets.map(d => d.data.length))], dashes: c.data.datasets.slice(0, 3).map(d => (d.borderDash || []).join(',')),
                 colors: [...new Set(c.data.datasets.map(d => d.borderColor))].length, x: c.data.labels.slice(-1)[0] } }""")
    check("S a loosely typed isotope (cs137) runs and shows the parent and its daughter", chart["labels"][:2] == ["Cs-137", "Ba-137m"], str(chart))
    check("S the parent starts at the requested activity and decays over 13 half-lives (it used to start at 0)",
          abs(chart["first"] - 10000) < 1 and 0.9 < chart["last"] < 1.2 and len(chart["lengths"]) == 1, str(chart))
    check("S the lines differ by pattern as well as colour", len(set(chart["dashes"])) == len(chart["dashes"]) and chart["colors"] == len(chart["labels"]), str(chart["dashes"]))
    info = ps.inner_text("#decay-info")
    check("S the page says which engine and data produced the curves", "Computed with" in info and "nuclide" in info and ("ICRP" in info or "ENSDF" in info), info)
    ps.fill("#decay-isotope", "tc99m")
    ps.fill("#decay-duration", "24")
    ps.select_option("#decay-duration-unit", "hours")
    ps.click("#btn-run-decay")
    ps.wait_for_function("Chart.getChart(document.getElementById('decayChart')).data.datasets[0].label === 'Tc-99m'", timeout=8000)
    hours = ps.evaluate("""() => { const c = Chart.getChart(document.getElementById('decayChart')); const d = c.data.datasets[0].data;
        return { last: c.data.labels.slice(-1)[0], ratio: d[d.length - 1] / d[0] } }""")
    check("S hours work: 24 h of Tc-99m is four half-lives and the axis says hours", " h" in hours["last"] and 0.05 < hours["ratio"] < 0.08, str(hours))
    ps.fill("#decay-isotope", "Xx-999")
    ps.click("#btn-run-decay")
    ps.wait_for_function("document.querySelector('.toast')?.textContent?.includes('Xx-999')", timeout=6000)
    check("S an unknown isotope is explained in a message (not a flat line)", ps.inner_text("#decay-info").strip() == "")
    ps.select_option("#decay-duration-unit", "years")
    ps.fill("#decay-isotope", "U-238")
    ps.fill("#decay-duration", "1000000")
    ps.click("#btn-run-decay")
    ps.wait_for_function("Chart.getChart(document.getElementById('decayChart')).data.datasets[0].label === 'U-238'", timeout=8000)
    ps.select_option("#theme-select", "oscilloscope")
    ps.wait_for_timeout(500)
    themed = ps.evaluate("""() => { const c = Chart.getChart(document.getElementById('decayChart'));
        return { width: c.data.datasets[0].borderWidth, glow: c.options.plugins.themeGlow.blur, n: c.data.datasets.length,
                 want: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--ch-line-w')) } }""")
    check("S the chart is redrawn in the new theme's character when the theme changes", abs(themed["width"] - themed["want"]) < 0.01 and themed["glow"] > 0 and themed["n"] >= 12, str(themed))
    ps.keyboard.press("Escape")
    ps.wait_for_function("getComputedStyle(document.getElementById('decay-modal')).display === 'none'", timeout=3000)
    check("S no JS errors or native dialogs in the decay modal", not errs_s, "; ".join(errs_s[:3]))
    ctx_s.close()

    # T. Edit N42 Metadata: when the template request fails, the button comes back (the catch used to throw a ReferenceError
    #    because the saved label was declared inside the try, leaving the button disabled and "Generating...")
    ctx_t = browser.new_context(viewport={"width": 1400, "height": 1000})
    pt = ctx_t.new_page()
    errs_t = []
    pt.on("pageerror", lambda e: errs_t.append(f"pageerror: {e}"))
    pt.on("dialog", lambda d: (errs_t.append("native dialog: " + d.message), d.dismiss()))
    pt.route("**/export/n42", lambda route, request: route.abort())
    pt.goto(URL, wait_until="networkidle")
    rows = "\n".join(f"{3.0 + 7.4 * i:.2f},{30 + (400 if 80 < i < 90 else 0)}" for i in range(128))
    pt.set_input_files("#file-input", files=[{"name": "edit_me.csv", "mimeType": "text/csv", "buffer": ("Energy (keV),Counts\n" + rows + "\n").encode()}])
    pt.wait_for_selector("#result-summary", state="visible", timeout=20000)
    label_before = pt.evaluate("document.getElementById('btn-edit-n42').innerHTML")
    pt.evaluate("document.getElementById('btn-edit-n42').click()")      # a CSV has no raw XML, so the template is requested
    pt.wait_for_timeout(1500)
    after = pt.evaluate("""() => { const b = document.getElementById('btn-edit-n42');
        return { disabled: b.disabled, html: b.innerHTML, opacity: b.style.opacity } }""")
    check("T a failed metadata-template request gives the Edit button back",
          not after["disabled"] and after["html"] == label_before and after["opacity"] in ("", "1"), str(after)[:200])
    check("T and raises no uncaught error", not any("not defined" in e for e in errs_t), "; ".join(errs_t[:3]))
    ctx_t.close()
    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
