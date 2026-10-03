"""Result headline logic (static/js/summary.js) under Node: the verdict, AI agreement, peak labels and number formats.

Skipped when Node is not installed. The card itself is covered by the browser smoke test."""
import json
import pathlib
import shutil
import subprocess

import pytest

MODULE = pathlib.Path(__file__).resolve().parents[1] / "static" / "js" / "summary.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(tmp_path, body):
    script = tmp_path / "t.mjs"
    script.write_text(
        f"import * as m from '{MODULE.as_uri()}';\nconst out = {{}};\n" + body + "\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_confidence_bands_and_names(tmp_path):
    out = run_js(tmp_path, """
        out.bands = [100, 70.1, 70, 40.1, 40, 0, NaN].map(m.confidenceLabel);
        out.names = [m.normalizeName('Cs-137'), m.normalizeName(' cs 137 '), m.normalizeName(null), m.normalizeName('Ba-137m')];
    """)
    assert out["bands"] == ["HIGH", "HIGH", "MEDIUM", "MEDIUM", "LOW", "LOW", "LOW"]
    assert out["names"] == ["cs137", "cs137", "", "ba137m"]


def test_headline_identification(tmp_path):
    out = run_js(tmp_path, """
        const iso = [{ isotope: 'Cs-137', confidence: 95, confidence_label: 'MEDIUM' }, { isotope: 'K-40', confidence: 41 },
                     { isotope: 'Ra-226', confidence: 30 }, { isotope: 'Th-232', confidence: 20 }, { isotope: 'U-238', confidence: 10 }];
        out.found = m.summarizeIdentification({ isotopes: iso, isCalibrated: true });
        out.plain = m.summarizeIdentification({ isotopes: [{ isotope: 'K-40', confidence: 80 }] });
        out.none = m.summarizeIdentification({ isotopes: [] });
        out.missing = m.summarizeIdentification({});
        out.uncal = m.summarizeIdentification({ isotopes: iso, isCalibrated: false });
        out.junk = m.summarizeIdentification({ isotopes: [null, {}] });
    """)
    assert out["found"]["name"] == "Cs-137" and out["found"]["confidence"] == 95
    assert out["found"]["label"] == "MEDIUM"                                   # the server's own label wins
    assert [a["name"] for a in out["found"]["also"]] == ["K-40", "Ra-226", "Th-232"]       # at most three alternatives
    assert out["plain"]["label"] == "HIGH" and out["plain"]["also"] == []     # derived from the band when absent
    assert out["none"] == {"state": "none"} and out["missing"] == {"state": "none"} and out["junk"] == {"state": "none"}
    assert out["uncal"] == {"state": "uncalibrated"}                          # nothing is identified without a calibration


def test_ai_agreement(tmp_path):
    out = run_js(tmp_path, """
        const line = m.summarizeIdentification({ isotopes: [{ isotope: 'Cs-137', confidence: 90 }, { isotope: 'K-40', confidence: 45 }] });
        const ai = (...names) => names.map((n, i) => ({ isotope: n, confidence: 90 - i * 10 }));
        out.agree = m.compareIdentifications(line, ai('cs137', 'Ba-133')).state;
        out.partialAi = m.compareIdentifications(line, ai('K-40', 'Co-60')).state;           // the net's top is line matching's runner-up
        out.partialLine = m.compareIdentifications(line, ai('Co-60', 'Eu-152', 'Cs-137')).state;   // line matching's top is the net's third
        out.differ = m.compareIdentifications(line, ai('Co-60', 'Eu-152', 'Am-241')).state;
        out.suppressedIgnored = m.compareIdentifications(line, [{ isotope: 'Co-60', confidence: 99, suppressed: true }, { isotope: 'Cs-137', confidence: 80 }]).state;
        out.noAi = m.compareIdentifications(line, []).state;
        out.noLine = m.compareIdentifications({ state: 'none' }, ai('Cs-137')).state;
        out.nulls = [m.compareIdentifications(null, null).state, m.compareIdentifications(line, undefined).state];
    """)
    assert out["agree"] == "agree" and out["partialAi"] == "partial" and out["partialLine"] == "partial"
    assert out["differ"] == "differ"
    assert out["suppressedIgnored"] == "agree"                                # a suppressed prediction is not an answer
    assert out["noAi"] == "none" and out["noLine"] == "none" and out["nulls"] == ["none", "none"]


def test_peak_labels(tmp_path):
    out = run_js(tmp_path, """
        const peaks = [{ energy: 32.6 }, { energy: 665.35 }, { energy: 1460.8 }, { energy: 1461.9 }];
        const iso = [
            { isotope: 'Cs-137', confidence: 90, matched_peaks: [{ observed: 665.3 }] },
            { isotope: 'Ba-137m', confidence: 60, matched_peaks: [{ observed: 665.9 }] },
            { isotope: 'K-40', confidence: 70, matched_peaks: [{ observed: 1460.9 }] },
            { isotope: 'Broken', confidence: 99 },
        ];
        out.labels = m.peakMatches(peaks, iso);
        out.tight = m.peakMatches(peaks, iso, 0.2);
        out.empty = [m.peakMatches(null, iso), m.peakMatches(peaks, null)];
    """)
    assert out["labels"] == [[], ["Cs-137", "Ba-137m"], ["K-40"], ["K-40"]]   # best match first, tolerance 1.5 keV
    assert out["tight"][1] == ["Cs-137"] and out["tight"][3] == []
    assert out["empty"] == [[], [[], [], [], []]]


def test_number_formats(tmp_path):
    out = run_js(tmp_path, """
        out.count = [987, 12345, 4.2e6, 3.1e9, NaN, 0].map(m.formatCount);
        out.dur = [0, 45, 90, 750, 3 * 3600 + 5 * 60, -1, NaN].map(m.formatDuration);
        out.total = [m.totalCounts([1, 2, 3, 'x', null]), m.totalCounts(null)];
        out.live = [m.liveSeconds({ live_time: 600 }), m.liveSeconds({ live_time: 0, real_time: 120 }), m.liveSeconds({ count_time_minutes: 2 }), m.liveSeconds({}), m.liveSeconds(null)];
        out.facts = m.summaryFacts({ counts: [10, 20, 30], metadata: { live_time: 30 }, peaks: [{}, {}] });
        out.noTime = m.summaryFacts({ counts: [10], metadata: {}, peaks: null });
    """)
    assert out["count"] == ["987", "12,345", "4.20 M", "3.10 G", "--", "0"]
    assert out["dur"] == ["--", "45 s", "1.5 min", "13 min", "3 h 05 min", "--", "--"]
    assert out["total"] == [6, 0]
    assert out["live"] == [600, 120, 120, None, None]
    assert out["facts"] == {"peaks": 2, "total": 60, "live": 30, "rate": 2}
    assert out["noTime"] == {"peaks": 0, "total": 10, "live": None, "rate": None}


def test_spectrum_change(tmp_path):
    out = run_js(tmp_path, """
        const a = m.spectrumSignature([1, 2, 3]);
        out.sig = a;
        out.first = m.spectrumChange(null, a);
        out.same = m.spectrumChange(a, m.spectrumSignature([1, 2, 3]));
        out.grown = m.spectrumChange(a, m.spectrumSignature([2, 3, 4]));
        out.fewer = m.spectrumChange(a, m.spectrumSignature([1, 1, 1]));
        out.channels = m.spectrumChange(a, m.spectrumSignature([1, 2, 3, 4]));
        out.bad = m.spectrumSignature(null);
    """)
    assert out["sig"] == {"length": 3, "total": 6} and out["bad"] == {"length": 0, "total": 0}
    assert out["first"] == "new" and out["same"] == "same" and out["grown"] == "grown"
    assert out["fewer"] == "new" and out["channels"] == "new"


def test_chain_link_distinguishes_a_decay_step_from_a_branch(tmp_path):
    """Bi-212 -> Po-212 (64 %) ... Tl-208 is the OTHER product of Bi-212 (36 %), so no arrow from Po-212 to it."""
    out = run_js(tmp_path, """
        const seq = [
          {nuclide: 'Pb-212', branching_to_next: 1.0, is_branch: false, feeder: 'Po-216', branching_from_feeder: 1.0},
          {nuclide: 'Bi-212', branching_to_next: 0.6406, is_branch: false, feeder: 'Pb-212', branching_from_feeder: 1.0},
          {nuclide: 'Po-212', branching_to_next: null, is_branch: false, feeder: 'Bi-212', branching_from_feeder: 0.6406},
          {nuclide: 'Tl-208', branching_to_next: 1.0, is_branch: true, feeder: 'Bi-212', branching_from_feeder: 0.3594},
          {nuclide: 'Pb-208', branching_to_next: 1.0, is_branch: false, feeder: 'Tl-208', branching_from_feeder: 1.0},
        ];
        out.links = [0, 1, 2, 3, 4].map((i) => m.chainLink(seq, i));
        out.empty = [m.chainLink(null, 0), m.chainLink([], 0)];
    """)
    pb212, bi212, po212, tl208, pb208 = out["links"]
    assert pb212 == {"kind": "decay", "percent": None, "from": "Pb-212"}
    assert bi212["kind"] == "decay" and bi212["percent"] == pytest.approx(64.06)
    assert po212["kind"] == "branch" and po212["percent"] == pytest.approx(35.94) and po212["from"] == "Bi-212"
    assert tl208 == {"kind": "decay", "percent": None, "from": "Tl-208"}
    assert pb208["kind"] == "none"
    assert out["empty"] == [{"kind": "none", "percent": None, "from": None}] * 2
