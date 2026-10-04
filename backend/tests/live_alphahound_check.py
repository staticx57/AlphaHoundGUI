"""
Checks that need a connected AlphaHound, run through the real UI and API. Read-only: nothing here clears the device's spectrum or
starts a timed acquisition (the details of what is checked are the items in TODO.md that were waiting for hardware).

    python tests/live_alphahound_check.py        (server running with the AlphaHound connected; about 4 minutes)

Environment: ALPHAHOUND_URL (default http://127.0.0.1:3200), LIVE_SHOTS (folder for the screenshots, default the temp folder).
It writes and removes one N42 checkpoint under backend/data, and sets then removes two localStorage keys in its own browser profile.
"""
import os
import pathlib
import socket
import sys
import tempfile
import threading
import time

import httpx
from playwright.sync_api import sync_playwright

B = os.environ.get("ALPHAHOUND_URL", "http://127.0.0.1:3200").rstrip("/")
S = os.environ.get("LIVE_SHOTS", tempfile.gettempdir())
HERE = pathlib.Path(__file__).resolve().parent
PORT = B.rsplit(":", 1)[-1]
http = httpx.Client(timeout=60)
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def new_page(browser, errors, base=B):
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
    page.on("dialog", lambda d: (errors.append("native dialog: " + d.message), d.dismiss()))
    page.goto(base + "/", wait_until="load")
    return ctx, page


def text(page, sel):
    return page.inner_text(sel).strip()


status0 = http.get(B + "/device/status").json()
check("the AlphaHound is connected and streaming before the checks", status0.get("connected") and (status0.get("cps") or {}).get("age_s", 99) < 5, str(status0)[:120])

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)

    # A. the live panel: numbers agree with the API and move
    errs = []
    ctx, page = new_page(browser, errs)
    page.wait_for_function("document.getElementById('ah-port').textContent.trim() !== '--'", timeout=20000)
    doses, gammas, totals = set(), set(), set()
    agree = []
    for _ in range(12):
        page.wait_for_timeout(1500)
        doses.add(text(page, "#ah-dose")); gammas.add(text(page, "#ah-cps-gamma")); totals.add(text(page, "#ah-cps-total"))
        api = http.get(B + "/device/status").json()["cps"]
        ui = float(text(page, "#ah-cps-gamma"))
        agree.append(abs(ui - api["gamma"]) <= max(0.35 * api["gamma"], 15))
    check("A the device panel shows port, temperature and compensation", all(text(page, f"#ah-{k}") not in ("--", "") for k in ("port", "temp", "comp")),
          f"{text(page, '#ah-port')} | {text(page, '#ah-temp')} | {text(page, '#ah-comp')}")
    check("A the dose readout and the gamma/total rates change while watching (not frozen)", len(doses) >= 4 and len(gammas) >= 4 and len(totals) >= 4,
          f"{len(doses)} / {len(gammas)} / {len(totals)} distinct values in 18 s")
    check("A the gamma rate on screen agrees with the API within counting noise", sum(agree) >= 10, f"{sum(agree)}/12 samples")
    check("A no JS errors while the live panel runs", not errs, "; ".join(errs[:3]))
    page.screenshot(path=f"{S}/live_panel.png", full_page=False)

    # B. a reload keeps the device connected and the page restores its state
    stayed = []
    t_end = time.time() + 14
    page.reload(wait_until="load")
    while time.time() < t_end:
        stayed.append(bool(http.get(B + "/device/status").json().get("connected")))
        time.sleep(0.5)
    page.wait_for_function("document.getElementById('ah-port').textContent.trim() !== '--'", timeout=15000)
    check("B reloading the page does not drop the AlphaHound (10 s grace, then back on screen)", all(stayed) and len(stayed) > 20, f"{sum(stayed)}/{len(stayed)} polls connected")
    ctx.close()

    # C. a long analysis does not stall the live dose stream
    from websockets.sync.client import connect
    stamps = []
    stop = threading.Event()

    def listen():
        try:
            with connect(B.replace("http", "ws", 1) + "/ws/dose", open_timeout=10) as ws:
                while not stop.is_set():
                    try:
                        ws.recv(timeout=2)
                        stamps.append(time.time())
                    except TimeoutError:
                        stamps.append(None)
        except Exception as e:
            stamps.append(("error", str(e)))

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(8)
    quiet = [s for s in stamps if isinstance(s, float)]
    quiet_gaps = [b - a for a, b in zip(quiet, quiet[1:])]
    mark = len(stamps)
    rows = "\n".join(f"{3.0 + 2.9 * i:.2f},{50 + (800 if 200 < i < 215 else 0) + (i * 7) % 40}" for i in range(1024))
    big = ("Energy (keV),Counts\n" + rows + "\n").encode()
    xml = (HERE / "data" / "radiacode_fisicas" / "Th-232.xml").read_bytes()
    load_end = time.time() + 12
    done = []

    def hammer(i):
        while time.time() < load_end:
            r = httpx.post(B + "/upload", files={"file": ("load.csv", big, "text/csv")} if i % 2 else {"file": ("Th-232.xml", xml, "application/xml")}, timeout=120)
            done.append(r.status_code)

    workers = [threading.Thread(target=hammer, args=(i,)) for i in range(4)]
    [w.start() for w in workers]
    [w.join() for w in workers]
    time.sleep(1)
    stop.set(); t.join(timeout=5)
    under = [s for s in stamps[mark:] if isinstance(s, float)]
    under_gaps = [b - a for a, b in zip(under, under[1:])]
    check("C the dose stream keeps flowing during heavy uploads (largest gap under load < 2 s)",
          len(done) >= 8 and all(c == 200 for c in done) and under_gaps and max(under_gaps) < 2.0,
          f"{len(done)} uploads; quiet: {len(quiet)} msgs, max gap {max(quiet_gaps):.2f}s; under load: {len(under)} msgs, max gap {max(under_gaps):.2f}s")

    # D. alerts on real readings (banner only: sound and notifications need a person)
    errs = []
    ctx, page = new_page(browser, errs)
    page.evaluate("localStorage.setItem('alertSettings', JSON.stringify({doseEnabled: true, doseUSvH: 0.05, cpsEnabled: false, cps: 1000, sound: false, notify: false}))")
    page.reload(wait_until="load")
    page.wait_for_selector(".safety-banner:not([hidden])", timeout=25000)
    banner = page.inner_text(".safety-banner")
    check("D a dose limit below the real reading raises the banner", "DOSE" in banner.upper(), banner.replace("\n", " ")[:100])
    page.screenshot(path=f"{S}/live_alert.png")
    page.evaluate("localStorage.setItem('alertSettings', JSON.stringify({doseEnabled: true, doseUSvH: 20, cpsEnabled: false, cps: 1000, sound: false, notify: false}))")
    page.reload(wait_until="load")
    page.wait_for_function("document.getElementById('ah-port').textContent.trim() !== '--'", timeout=15000)
    page.wait_for_timeout(4000)
    check("D with the default 20 uSv/h limit the banner is gone", page.locator(".safety-banner:not([hidden])").count() == 0)
    check("D no JS errors in the alert flow", not errs, "; ".join(errs[:3]))
    page.evaluate("localStorage.removeItem('alertSettings')")

    # E. dose unit preference
    readings = {}
    for pref in ("uSv", "uRem"):
        page.evaluate(f"localStorage.setItem('doseUnit', '{pref}')")
        page.reload(wait_until="load")
        page.wait_for_function("document.getElementById('ah-dose').textContent.trim() !== '--'", timeout=20000)
        page.wait_for_timeout(2500)
        readings[pref] = text(page, "#ah-dose")
    check("E the unit preference changes the dose readout (uSv/h vs uRem/h)", "Sv" in readings["uSv"] and "Rem" in readings["uRem"], str(readings))
    page.evaluate("localStorage.removeItem('doseUnit')")

    # F. background subtraction on a live spectrum (Get Current reads the device; it does not clear it)
    page.reload(wait_until="load")
    page.wait_for_function("document.getElementById('ah-port').textContent.trim() !== '--'", timeout=15000)
    page.click("#btn-get-current")
    page.wait_for_selector("#result-summary", state="visible", timeout=40000)
    page.wait_for_function("window.Chart && Chart.getChart(document.getElementById('spectrumChart'))", timeout=10000)
    counts_before = http.post(B + "/device/spectrum", json={"count_minutes": 0}).json()["counts"]
    page.evaluate("document.getElementById('btn-set-current-bg').click()")
    page.wait_for_function("getComputedStyle(document.getElementById('bg-active-indicator')).display !== 'none'", timeout=10000)
    check("F Use Current as BG on a live spectrum shows the ACTIVE badge", True)
    page.evaluate("document.getElementById('btn-clear-bg').click()")
    page.wait_for_function("getComputedStyle(document.getElementById('bg-active-indicator')).display === 'none'", timeout=10000)
    check("F Clear BG removes it", True)
    counts_after = http.post(B + "/device/spectrum", json={"count_minutes": 0}).json()["counts"]
    check("F the device's own spectrum was not cleared by any of this", sum(counts_after) >= sum(counts_before) > 1000, f"{sum(counts_before)} -> {sum(counts_after)} counts")
    page.screenshot(path=f"{S}/live_spectrum.png")
    check("F no JS errors in the live spectrum flow", not errs, "; ".join(errs[:3]))
    ctx.close()

    # G. from another address on the LAN (same-origin, no CORS configured)
    lan_ip = socket.gethostbyname(socket.gethostname())
    errs = []
    try:
        ctx, page = new_page(browser, errs, base=f"http://{lan_ip}:{PORT}")
        page.wait_for_function("document.getElementById('ah-port').textContent.trim() !== '--'", timeout=25000)
        check(f"G the app works from the LAN address {lan_ip} (device panel populated, no console errors)", not errs and text(page, "#ah-port") != "--", "; ".join(errs[:3]))
        ctx.close()
    except Exception as e:
        check(f"G the app works from the LAN address {lan_ip}", False, str(e)[:160])
    browser.close()

# H. checkpoint export round trip (writes a file under backend/data, then deletes it)
d = http.post(B + "/device/spectrum", json={"count_minutes": 0}).json()
r = http.post(B + "/export/n42-checkpoint", json={"counts": d["counts"], "energies": d["energies"], "metadata": d["metadata"]})
check("H the N42 checkpoint is written", r.status_code == 200 and r.json().get("success", True), r.text[:100])
r2 = http.delete(B + "/export/n42-checkpoint")
check("H and deleted again", r2.status_code == 200, r2.text[:100])

# I. the server log
log = pathlib.Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or ".") / "alphahound_server.log"   # where devctl restart writes it
if not log.exists():
    print("SKIP I the server log is not at", log, "(the server was not started by devctl)")
    lines = []
else:
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
levels = {}
for line in lines:
    for lvl in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        if f" {lvl} " in line or f"{lvl}:" in line or f"[{lvl}]" in line:
            levels[lvl] = levels.get(lvl, 0) + 1
errors = [l for l in lines if "ERROR" in l or "Traceback" in l]
if lines:
    check("I the server log has no errors or tracebacks in its last 400 lines", not errors, f"levels {levels}; " + (errors[0][:150] if errors else ""))

bad = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(bad)}/{len(results)} passed")
sys.exit(1 if bad else 0)
