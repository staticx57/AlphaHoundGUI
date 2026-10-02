"""
Static check that JS only looks up element IDs that exist in index.html.

A lookup of a missing ID returns null, and an unguarded `.textContent`/`.style`
on it throws at runtime. This broke the AlphaHound live dose readout
(`dose-display`) and background loading (`bg-active-indicator`) without any
backend test noticing.

LEGACY_NULL_GUARDED lists IDs that are still looked up but no longer exist
(removed panels, old "-top" controls). Every use is behind an `if`/`?.` guard.
Do not add to it: add the element to index.html or remove the dead JS instead.
"""

import pathlib
import re

STATIC = pathlib.Path(__file__).resolve().parents[1] / "static"

LEGACY_NULL_GUARDED = {
    "btn-acquire-spectrum", "btn-acquire-top", "btn-advanced", "btn-calibrate",
    "btn-connect-top", "btn-disconnect-radiacode", "btn-disconnect-top",
    "btn-rc-clear", "btn-rc-get-spectrum", "btn-rc-reset-dose",
    "btn-refresh-ports-top", "btn-uranium-ratio", "doseRateChart",
    "isotopes-tbody", "port-select-top", "radiacode-connected",
    "rc-device-model", "server-acquisition-info",
}


def _missing_ids():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html_ids = set(re.findall(r'\bid="([^"]+)"', html))
    scripts = {p: p.read_text(encoding="utf-8") for p in (STATIC / "js").glob("*.js")}

    dynamic = set()
    for text in scripts.values():
        dynamic |= set(re.findall(r'\bid=[\\"\']+([A-Za-z0-9_-]+)', text))
        dynamic |= set(re.findall(r'\.id\s*=\s*[\'"]([^\'"]+)', text))

    missing = {}
    for path, text in scripts.items():
        for m in re.finditer(r'getElementById\(\s*[\'"]([^\'"]+)[\'"]\s*\)', text):
            element_id = m.group(1)
            if element_id not in html_ids and element_id not in dynamic:
                missing.setdefault(element_id, set()).add(path.name)
    return missing


def test_no_new_missing_element_ids():
    unexpected = {i: sorted(f) for i, f in _missing_ids().items() if i not in LEGACY_NULL_GUARDED}
    assert not unexpected, f"JS looks up IDs absent from index.html: {unexpected}"


def test_html_has_no_duplicate_ids():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', html)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"duplicate element IDs in index.html: {dupes}"
