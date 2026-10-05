"""Labels for the saved acquisitions in the History dialog (static/js/saved_runs.js), run under Node."""
import json
import pathlib
import shutil
import subprocess

import pytest

MODULE = pathlib.Path(__file__).resolve().parents[1] / "static" / "js" / "saved_runs.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def describe(tmp_path, run):
    script = tmp_path / "t.mjs"
    script.write_text(f"import {{ describeSavedRun }} from '{MODULE.as_uri()}';\n"
                      f"console.log(JSON.stringify(describeSavedRun({json.dumps(run)})));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("run,expected", [
    ({"name": "spectrum_2026-10-03_10-16-41.n42", "kind": "complete"},
     {"when": "2026-10-03 10:16:41", "whenLabel": "saved", "kind": "Complete", "detail": ""}),
    ({"name": "spectrum_2026-10-04_22-03-00_in_progress.n42", "kind": "in_progress"},
     {"when": "2026-10-04 22:03:00", "whenLabel": "started", "kind": "In progress", "detail": ""}),
    ({"name": "spectrum_2026-10-04_20-52-33_interrupted_3827s.n42", "kind": "interrupted"},
     {"when": "2026-10-04 20:52:33", "whenLabel": "started", "kind": "Interrupted", "detail": "3827s"}),
    ({"name": "spectrum_2026-10-04_20-52-33_interrupted_2.n42", "kind": "interrupted"},
     {"when": "2026-10-04 20:52:33", "whenLabel": "started", "kind": "Interrupted", "detail": "2"}),
    ({"name": "acquisition_in_progress.n42", "kind": "in_progress"},
     {"when": "acquisition_in_progress.n42", "whenLabel": "", "kind": "In progress", "detail": ""}),
])
def test_saved_run_labels(tmp_path, run, expected):
    assert describe(tmp_path, run) == expected
