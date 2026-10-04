"""Message classification and routing (static/js/dialogs.js) and the device capability table (static/js/device_features.js) under Node."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

STATIC = pathlib.Path(__file__).resolve().parents[1] / "static"
JS = STATIC / "js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(tmp_path, body):
    script = tmp_path / "t.mjs"
    script.write_text(
        f"import * as d from '{(JS / 'dialogs.js').as_uri()}';\nimport * as f from '{(JS / 'device_features.js').as_uri()}';\nconst out = {{}};\n"
        + body + "\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_toast_type_is_read_from_the_wording(tmp_path):
    out = run_js(tmp_path, """
        out.t = ['Error exporting PDF: boom', 'Failed to save', 'Could not read this file', 'Calibration applied', 'Spectrum saved',
                 'Imported 3 isotopes', 'Background cleared', 'No spectrum data to export', 'Warning: CHN stores a quadratic', null, undefined].map(d.classify);""")
    assert out["t"] == ["error", "error", "error", "success", "success", "success", "success", "warning", "warning", "warning", "warning"]


def test_a_failure_wins_over_a_success_word_in_the_same_message(tmp_path):
    out = run_js(tmp_path, "out.t = ['Failed to save the file', 'Could not apply: nothing was updated'].map(d.classify);")
    assert out["t"] == ["error", "error"]


def test_notifications_go_to_the_registered_notifier_and_otherwise_to_the_console(tmp_path):
    out = run_js(tmp_path, """
        const seen = [];
        const original = { warn: console.warn, error: console.error };
        console.warn = (m) => seen.push(['warn', m]);
        console.error = (m) => seen.push(['error', m]);
        d.notify('no notifier yet', 'info');
        d.notify('and an error', 'error');
        d.setNotifier((message, type) => seen.push(['notifier', message, type]));
        d.notify('now routed', 'success');
        d.notifyAuto('Spectrum saved');
        d.notify(null);
        console.warn = original.warn; console.error = original.error;
        out.seen = seen;""")
    assert out["seen"] == [["warn", "no notifier yet"], ["error", "and an error"], ["notifier", "now routed", "success"],
                           ["notifier", "Spectrum saved", "success"], ["notifier", "", "info"]]


def test_every_feature_named_in_the_html_exists_for_some_device(tmp_path):
    """A typo in data-device-feature would hide that control forever, on both devices, without an error anywhere."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    used = set(re.findall(r'data-device-feature="([^"]+)"', html))
    assert len(used) >= 10
    out = run_js(tmp_path, "out.caps = f.DEVICE_CAPABILITIES;")
    known = set().union(*[set(c) for c in out["caps"].values()])
    assert not (used - known), f"features in the HTML that no device defines: {sorted(used - known)}"


def test_capabilities_say_what_each_device_can_do(tmp_path):
    out = run_js(tmp_path, """
        out.before = [f.isFeatureSupported('temperature'), f.isFeatureSupported('anything')];
        out.ah = f.getCapabilities('alphahound'); out.rc = f.getCapabilities('radiacode'); out.unknown = f.getCapabilities('nothing');""")
    assert out["before"] == [True, True]                       # no device active: everything is allowed
    assert out["ah"]["temperature"] is True and out["rc"]["temperature"] is False
    assert out["ah"]["doseReset"] is False and out["rc"]["doseReset"] is True
    assert out["ah"]["alphaDetails"] is True and out["unknown"] == {}
