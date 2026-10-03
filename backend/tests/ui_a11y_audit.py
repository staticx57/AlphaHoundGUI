"""
Accessibility audit (not collected by pytest): structural checks that do not need a screen reader.

Loads the app with a spectrum and a mocked AlphaHound, then checks: every control has an accessible name, every image has
an alt attribute, ids are unique, form fields have labels, canvases are described, dialogs behave (role, focus moves in,
Tab stays inside, Esc closes, focus returns), keyboard focus is visible, and reduced motion is honoured.

Needs playwright + Chrome and the server running at http://localhost:3200.

    python backend/tests/ui_a11y_audit.py
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ah_mock import install  # noqa: E402

URL = "http://localhost:3200/"
SPEC = os.path.join(HERE, "..", "data", "test_spectra", "synthetic_cesium137.n42")
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


NAMES_JS = r"""
() => {
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const textOf = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const nameOf = (el) => {
    const aria = el.getAttribute('aria-label'); if (aria && aria.trim()) return aria.trim();
    const by = el.getAttribute('aria-labelledby');
    if (by) { const t = by.split(/\s+/).map((id) => document.getElementById(id)).filter(Boolean).map(textOf).join(' ').trim(); if (t) return t; }
    if (el.labels && el.labels.length) { const t = [...el.labels].map(textOf).join(' ').trim(); if (t) return t; }
    if (el.closest('label')) { const t = textOf(el.closest('label')); if (t) return t; }
    const t = textOf(el); if (t) return t;
    const img = el.querySelector('img[alt]'); if (img && img.alt.trim()) return img.alt.trim();
    const title = el.getAttribute('title'); if (title && title.trim()) return title.trim();
    if (el.tagName === 'INPUT' && el.placeholder) return el.placeholder;
    return '';
  };
  const sel = 'button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], [role=switch], [tabindex]:not([tabindex="-1"])';
  const unnamed = [...document.querySelectorAll(sel)].filter(visible).filter((el) => !nameOf(el))
    .map((el) => el.id || (el.className && String(el.className).slice(0, 40)) || el.tagName);
  const noAlt = [...document.querySelectorAll('img:not([alt])')].map((i) => (i.getAttribute('src') || '').split('/').pop());
  const ids = {}; document.querySelectorAll('[id]').forEach((e) => { ids[e.id] = (ids[e.id] || 0) + 1; });
  const dupes = Object.entries(ids).filter(([, n]) => n > 1).map(([id]) => id);
  const unlabeled = [...document.querySelectorAll('input:not([type=hidden]):not([type=file]), select, textarea')].filter(visible)
    .filter((el) => !nameOf(el)).map((el) => el.id || el.name || el.tagName);
  const canvases = [...document.querySelectorAll('canvas')].filter(visible)
    .filter((c) => c.getAttribute('aria-hidden') !== 'true' && !(c.getAttribute('role') === 'img' && (c.getAttribute('aria-label') || '').trim())).map((c) => c.id || 'canvas');
  const modals = [...document.querySelectorAll('.modal')].map((m) => ({ id: m.id, role: m.getAttribute('role'), modal: m.getAttribute('aria-modal'),
      labelled: !!(m.getAttribute('aria-label') || m.getAttribute('aria-labelledby')) }));
  return { unnamed, noAlt, dupes, unlabeled, canvases, modals, lang: document.documentElement.lang, title: document.title,
           landmarks: { main: !!document.querySelector('main'), header: !!document.querySelector('header'), skip: !!document.querySelector('a.skip-link') } };
}
"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        install(page, burst=0)
        page.route("**/radiacode/status", lambda r, q: r.fulfill(status=200, content_type="application/json",
                   body=json.dumps({"connected": False, "available": True, "device_info": None, "last_error": None})))
        page.goto(URL, wait_until="networkidle")
        page.select_option("#port-select", "COM8")
        page.click("#btn-connect-device")
        page.wait_for_function("document.getElementById('device-conn-label').textContent === 'Connected'", timeout=8000)
        page.set_input_files("#file-input", SPEC)
        page.wait_for_selector("#dashboard", state="visible", timeout=20000)
        page.wait_for_timeout(2500)

        info = page.evaluate(NAMES_JS)
        check("page language and title are set", bool(info["lang"]) and bool(info["title"].strip()), f"{info['lang']!r} {info['title']!r}")
        check("landmarks: a header, a main region and a skip link", all(info["landmarks"].values()), str(info["landmarks"]))
        check("every visible control has an accessible name", not info["unnamed"], ", ".join(info["unnamed"][:12]))
        check("every image has an alt attribute (decorative ones alt=\"\")", not info["noAlt"], f"{len(info['noAlt'])}: " + ", ".join(sorted(set(info['noAlt']))[:8]))
        check("element ids are unique", not info["dupes"], ", ".join(info["dupes"][:10]))
        check("every visible form field has a label", not info["unlabeled"], ", ".join(info["unlabeled"][:10]))
        check("visible canvases are images with a text description", not info["canvases"], ", ".join(info["canvases"]))
        bad = [m["id"] for m in info["modals"] if m["role"] != "dialog" or m["modal"] != "true" or not m["labelled"]]
        check("every modal is a labelled aria-modal dialog", not bad, ", ".join(bad))

        # keyboard: the Settings dialog
        page.focus("#btn-settings")
        page.keyboard.press("Enter")
        page.wait_for_selector("#settings-modal", state="visible")
        try:
            page.wait_for_function("document.getElementById('settings-modal').contains(document.activeElement)", timeout=2000)
            inside = True
        except Exception:
            inside = False
        check("opening a dialog moves focus into it", inside)
        stay = True
        for _ in range(60):
            page.keyboard.press("Tab")
            if not page.evaluate("document.getElementById('settings-modal').contains(document.activeElement)"):
                stay = False
                break
        check("Tab stays inside the open dialog", stay)
        page.keyboard.press("Shift+Tab")
        check("Shift+Tab stays inside too", page.evaluate("document.getElementById('settings-modal').contains(document.activeElement)"))
        page.keyboard.press("Escape")
        page.wait_for_function("getComputedStyle(document.getElementById('settings-modal')).display === 'none'", timeout=3000)
        check("Esc closes the dialog", True)
        check("focus returns to the button that opened it", page.evaluate("document.activeElement && document.activeElement.id") == "btn-settings",
              str(page.evaluate("document.activeElement && (document.activeElement.id || document.activeElement.tagName)")))

        # keyboard focus is visible on every stop of the first screenful
        page.evaluate("window.scrollTo(0, 0); document.activeElement && document.activeElement.blur()")
        invisible = []
        for _ in range(25):
            page.keyboard.press("Tab")
            r = page.evaluate("""() => { const e = document.activeElement; if (!e || e === document.body) return null; const s = getComputedStyle(e);
                const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0; const shadow = s.boxShadow && s.boxShadow !== 'none';
                const hasBorderChange = false; return { id: e.id || e.className || e.tagName, ok: outline || shadow || hasBorderChange } }""")
            if r and not r["ok"]:
                invisible.append(str(r["id"])[:30])
        check("keyboard focus is visible on the first 25 tab stops", not invisible, ", ".join(invisible[:10]))

        # reduced motion
        ctx2 = browser.new_context(viewport={"width": 1400, "height": 1000}, reduced_motion="reduce")
        p2 = ctx2.new_page()
        install(p2, burst=0)
        p2.route("**/radiacode/status", lambda r, q: r.fulfill(status=200, content_type="application/json",
                 body=json.dumps({"connected": False, "available": True, "device_info": None, "last_error": None})))
        p2.goto(URL, wait_until="networkidle")
        anim = p2.evaluate("""() => [...document.querySelectorAll('body *')].filter((e) => { const s = getComputedStyle(e);
            return s.animationName !== 'none' && parseFloat(s.animationDuration) > 0.05 && s.animationIterationCount === 'infinite' && e.offsetParent !== null }).map((e) => e.id || e.className).slice(0, 8)""")
        check("with reduced motion requested no infinite animation runs", not anim, ", ".join(str(a) for a in anim))
        ctx2.close()

        check("no JS errors", not errs, "; ".join(errs[:3]))
        browser.close()

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(fails)}/{len(results)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
