"""Browser check: an acquisition runs on the server, and the page shows it wherever and whenever it is opened.

    python tests/ui_acquisition_views.py          (needs the server; ALPHAHOUND_URL for another port)

Covers: a reload during a run shows it again; uploading a file or opening a saved run during a run shows that file and
leaves the run going (it used to offer "Stop recording", which ended an 8 hour run); Back to acquisition returns, or says
where the spectrum went once the run has ended; Acquire while a run is going attaches to it; History lists the runs the
server saved. The AlphaHound and the acquisition endpoints are mocked: no device needed, nothing is started or stopped.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ah_mock import install  # noqa: E402

URL = os.environ.get("ALPHAHOUND_URL", "http://localhost:3200").rstrip("/") + "/"
SPEC = os.path.join(HERE, "..", "data", "test_spectra", "synthetic_cesium137.n42")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not ok else ""))


def ok_json(route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


RUNS = [
    {"name": "spectrum_2026-10-04_22-03-00_in_progress.n42", "kind": "in_progress", "size_bytes": 27834,
     "modified": "2026-10-05T02:10:00+00:00"},
    {"name": "spectrum_2026-10-04_20-52-33_interrupted_3827s.n42", "kind": "interrupted", "size_bytes": 27834,
     "modified": "2026-10-05T01:56:00+00:00"},
    {"name": "spectrum_2026-10-03_10-16-41.n42", "kind": "complete", "size_bytes": 15423,
     "modified": "2026-10-03T14:16:41+00:00"},
]

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("dialog", lambda d: (errors.append("native dialog: " + d.message), d.dismiss()))

    # what a saved run opens to: the server's own analysis of a test spectrum
    with open(SPEC, "rb") as f:
        analysed = ctx.request.post(URL + "upload", multipart={
            "file": {"name": "saved.n42", "mimeType": "application/xml", "buffer": f.read()}}).text()

    ah = install(page)
    ah["connected"] = True
    acq = {"active": True, "polls": 0, "stops": 0}
    opened = []

    def status(route, request):
        acq["polls"] += 1
        ok_json(route, {"status": "acquiring" if acq["active"] else "complete", "is_active": acq["active"],
                        "elapsed_seconds": 1234.0, "duration_seconds": 28800.0,
                        "start_time": "2026-10-05T02:03:00+00:00", "exposure": None})

    def stop(route, request):
        acq["stops"] += 1
        ok_json(route, {"success": True, "final_filename": "stopped.n42"})

    def open_run(route, request):
        opened.append(request.url.rsplit("/", 1)[1])
        route.fulfill(status=200, content_type="application/json", body=analysed)

    page.route("**/device/acquisition/status", status)
    page.route("**/device/acquisition/stop", stop)
    page.route("**/device/acquisition/start", lambda r, q: ok_json(r, {"detail": "Acquisition already in progress"}, 400))
    page.route("**/device/acquisitions", lambda r, q: ok_json(r, {"runs": RUNS}))
    page.route("**/device/acquisitions/*", open_run)

    showing_run = "document.getElementById('btn-stop-acquire').style.display === 'block'"
    back_shown = "getComputedStyle(document.getElementById('btn-resume-acquisition')).display !== 'none'"

    # 1. a reload while the server acquires
    page.goto(URL, wait_until="load")
    try:
        page.wait_for_function(showing_run, timeout=10000)
    except Exception:
        pass
    check("a page opened during an acquisition shows it: Stop button, timer, status polling",
          page.is_visible("#btn-stop-acquire") and page.is_visible("#acquisition-status") and acq["polls"] >= 1,
          f"polls={acq['polls']}")
    check("its duration box shows the running acquisition's length (480 min)", page.input_value("#count-time") == "480",
          page.input_value("#count-time"))

    # 2. a file uploaded by mistake during the run
    page.set_input_files("#file-input", SPEC)
    try:
        page.wait_for_function(back_shown, timeout=15000)
        page.wait_for_selector("#result-summary", state="visible", timeout=20000)
    except Exception:
        pass
    polls = acq["polls"]
    page.wait_for_timeout(4500)
    check("uploading a file during a run shows the file and leaves the run going (no stop, no question)",
          acq["stops"] == 0 and page.is_visible("#result-summary") and page.is_visible("#btn-resume-acquisition")
          and not page.is_visible("#btn-stop-acquire") and acq["polls"] == polls,
          f"stops={acq['stops']} polls {polls}->{acq['polls']} back={page.is_visible('#btn-resume-acquisition')}")

    page.click("#btn-resume-acquisition") if page.is_visible("#btn-resume-acquisition") else None
    try:
        page.wait_for_function(showing_run, timeout=10000)
    except Exception:
        pass
    check("Back to acquisition shows the live run again",
          page.is_visible("#btn-stop-acquire") and not page.is_visible("#btn-resume-acquisition"))

    # 3. History lists the server's runs; opening one during the run keeps the run going
    page.click("#btn-history")
    try:
        page.wait_for_selector("#saved-runs-list .saved-run", timeout=10000)
    except Exception:
        pass
    labels = page.eval_on_selector_all("#saved-runs-list .saved-run", "els => els.map(e => e.innerText.replace(/\\s+/g, ' ').trim())")
    check("History lists the runs saved on the server, newest first, with their state",
          len(labels) == 3 and "In progress" in labels[0] and "Interrupted" in labels[1] and "3827s" in labels[1]
          and "Complete" in labels[2], str(labels))
    if labels:
        page.click("#saved-runs-list .saved-run >> nth=2")
    try:
        page.wait_for_function("document.getElementById('history-modal').style.display === 'none'", timeout=15000)
    except Exception:
        pass
    check("opening a saved run during a run loads it and leaves the run going",
          opened == ["spectrum_2026-10-03_10-16-41.n42"] and acq["stops"] == 0 and page.is_visible("#btn-resume-acquisition"),
          f"opened={opened} stops={acq['stops']}")

    # 4. the run ends while the page shows a file
    acq["active"] = False
    if page.is_visible("#btn-resume-acquisition"):
        page.click("#btn-resume-acquisition")
    try:
        page.wait_for_function(f"!({back_shown})", timeout=10000)
    except Exception:
        pass
    check("Back to acquisition after the run ended says where its spectrum is",
          not page.is_visible("#btn-resume-acquisition") and "Saved on the server" in page.inner_text("body"))

    # 5. Acquire while a run is already going (another tab, a script) attaches to it
    acq["active"] = True
    page.evaluate("document.getElementById('btn-start-acquire').click()")
    try:
        page.wait_for_function(showing_run, timeout=10000)
    except Exception:
        pass
    check("Acquire while one is already running shows that one instead of an error",
          page.is_visible("#btn-stop-acquire") and acq["stops"] == 0)

    check("no JS errors or native dialogs", not errors, "; ".join(errors[:3]))
    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
