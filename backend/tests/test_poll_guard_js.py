"""Timed polls in the UI never overlap: a tick that finds the previous request unanswered is skipped.

setInterval fires on schedule whether or not the last request came back. When the server slowed down (a 480 minute
acquisition, 2 s per status reply) the polls piled up behind Chrome's six connections per host and the page hung.
static/js/poll.js wraps a poll so it cannot run twice at once; main.js must use it for every timed server poll."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js"
MODULE = JS / "poll.js"
NODE = shutil.which("node")


def run_js(tmp_path, body):
    script = tmp_path / "t.mjs"
    script.write_text(
        f"import * as m from '{MODULE.as_uri()}';\n"
        "const out = {};\n"
        "const sleep = (ms) => new Promise((r) => setTimeout(r, ms));\n" + body +
        "\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_a_tick_is_skipped_while_the_previous_poll_is_pending(tmp_path):
    out = run_js(tmp_path, """
        let started = 0, release;
        const poll = m.nonOverlapping(() => { started++; return new Promise((r) => { release = r; }); });
        poll(); poll(); poll();                       // three ticks while the first request hangs
        out.whilePending = started;
        release(); await sleep(0);
        poll();                                       // the next tick after it answered runs again
        out.afterAnswer = started;
    """)
    assert out == {"whilePending": 1, "afterAnswer": 2}


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_a_failed_poll_does_not_stop_the_next_one(tmp_path):
    out = run_js(tmp_path, """
        let started = 0;
        const poll = m.nonOverlapping(async () => { started++; throw new Error('offline'); });
        await poll().catch(() => {});
        await poll().catch(() => {});
        out.started = started;
    """)
    assert out == {"started": 2}


def test_every_timed_server_poll_in_main_js_is_guarded():
    src = (JS / "main.js").read_text(encoding="utf-8")
    assert "from './poll.js'" in src
    assert "setInterval(async" not in src, "an inline async interval callback is not guarded"
    for name in ("pollRadiacodeDose", "refreshAlphaHoundDetails", "pollAcquisitionStatus"):
        assert re.search(rf"\bconst {name} = nonOverlapping\(", src), f"{name} is polled without the guard"
