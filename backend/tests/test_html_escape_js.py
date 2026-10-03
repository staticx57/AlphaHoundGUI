"""escapeHtml (static/js/html.js) under Node, plus a guard that untrusted text is not put into innerHTML raw.

Skipped when Node is not installed."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_escape_html_neutralises_markup_and_handles_non_strings(tmp_path):
    script = tmp_path / "t.mjs"
    script.write_text(
        f"import {{ escapeHtml as e }} from '{(JS / 'html.js').as_uri()}';\n"
        "console.log(JSON.stringify([e('<img src=x onerror=alert(1)>'), e(`a & \"b\" 'c'`), e(null), e(undefined), e(42)]));\n",
        encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert out[0] == "&lt;img src=x onerror=alert(1)&gt;"
    assert out[1] == "a &amp; &quot;b&quot; &#39;c&#39;"
    assert out[2:] == ["", "", "42"]


UNTRUSTED = re.compile(r"\$\{\s*(err\.message|error\.message|device\.name|device\.address|state\.error|message)\s*\}")


def test_untrusted_text_is_escaped_in_html_templates():
    """A template line that builds markup (a tag on the same line) must not interpolate these names raw."""
    offenders = []
    for path in sorted(JS.glob("*.js")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "<" in line and UNTRUSTED.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()[:90]}")
    assert not offenders, "wrap in escapeHtml():\n" + "\n".join(offenders)
