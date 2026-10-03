"""Metadata card labels and values (static/js/metadata_cards.js) under Node.

Regression for "MEAN DOSE RATE USV H": raw keys were shown as KEY.toUpperCase() with underscores replaced, values unrounded.
Skipped when Node is not installed."""
import json
import pathlib
import shutil
import subprocess

import pytest

MODULE = pathlib.Path(__file__).resolve().parents[1] / "static" / "js" / "metadata_cards.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(tmp_path, body):
    script = tmp_path / "t.mjs"
    script.write_text(
        f"import * as m from '{MODULE.as_uri()}';\nconst out = {{}};\n" + body + "\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


# what the live acquisition sends (acquisition_manager.py), with the numbers that used to show up raw
LIVE = """{
  source: 'AlphaHound Device', channels: 1024, count_time_minutes: 5.0003, acquisition_time: 300.02, live_time: 300.02, real_time: 300.02,
  start_time: '2026-10-02T17:43:30.903564+00:00',
  mean_cps_gamma: 271.456789, mean_cps_beta: 150.5, mean_cps_alpha: 6.25, max_cps_total: 480,
  exposure_during_acquisition: '123.5 nSv (mean 1.483, max 3.250 \\u00b5Sv/h)', exposure_uSv: 0.123456, mean_dose_rate_uSv_h: 1.482912,
  max_dose_rate_uSv_h: 3.250001, exposure_covered_s: 299.7, exposure_method: 'integrated instrument dose rate',
  time_notes: 'Live time equals real time here.', device_duration_s: 298.4
}"""


def test_keys_become_readable_labels_with_units_in_the_value(tmp_path):
    out = run_js(tmp_path, """
        out.k = ['mean_dose_rate_uSv_h', 'exposure_uSv', 'exposure_covered_s', 'mean_cps_gamma', 'peak_temperature_c', 'sample_rate_hz', 'n42_version',
                 'channels', 'a', 'dose_rate_uRem_h', 'serial_number'].map(m.humanizeKey);
    """)
    assert out["k"][0] == {"label": "Mean dose rate", "unit": "\u00b5Sv/h"}           # the label the user saw as "MEAN DOSE RATE USV H"
    assert out["k"][1] == {"label": "Exposure", "unit": "\u00b5Sv"}
    assert out["k"][2] == {"label": "Exposure covered", "unit": "s"}
    assert out["k"][3] == {"label": "Mean CPS gamma", "unit": None}                   # "cps" stays an acronym; only trailing units move
    assert out["k"][4] == {"label": "Peak temperature", "unit": "\u00b0C"}
    assert out["k"][5] == {"label": "Sample rate", "unit": "Hz"}
    assert out["k"][6] == {"label": "N42 version", "unit": None}
    assert out["k"][7] == {"label": "Channels", "unit": None}
    assert out["k"][8] == {"label": "A", "unit": None}
    assert out["k"][9] == {"label": "Dose rate", "unit": "\u00b5Rem/h"}
    assert out["k"][10] == {"label": "Serial number", "unit": None}


def test_number_and_time_formats(tmp_path):
    out = run_js(tmp_path, """
        out.n = [5, 1234567, 1.482912, 271.456789, 0.00012346, 150.5, 99.99, -2.5, NaN].map(m.formatNumber);
        out.s = [12.34, 59.96, 60, 300, 3599, 3600, 3900, 86400].map(m.formatSeconds);
    """)
    assert out["n"] == ["5", "1,234,567", "1.483", "271.5", "0.0001235", "150.5", "99.99", "-2.5", "NaN"]
    assert out["s"] == ["12.3s", "60.0s", "1.0 min", "5.0 min", "60.0 min", "1h 0m", "1h 5m", "24h 0m"]


def test_live_capture_cards_are_clean(tmp_path):
    out = run_js(tmp_path, f"out.cards = m.describeMetadata({LIVE});")
    cards = {c["key"]: c for c in out["cards"]}
    labels = [c["label"] for c in out["cards"]]
    # no raw key leaks into a label
    assert all("_" not in label and "USV" not in label and not label.endswith(" S") for label in labels), labels
    assert cards["acquisition_time"]["label"] == "Acquisition time" and cards["acquisition_time"]["value"] == "5.0 min (300 s)"
    assert cards["start_time"]["value"] != "2026-10-02T17:43:30.903564+00:00" and "T17" not in cards["start_time"]["value"]
    assert cards["channels"]["value"] == "1024"
    assert cards["source"]["value"] == "AlphaHound Device"
    assert cards["device_duration_s"]["label"] == "Device duration" and cards["device_duration_s"]["value"] == "5.0 min"
    # six keys about one dose figure are one card, with the rates as rows
    assert cards["exposure"]["label"] == "Dose this acquisition" and cards["exposure"]["value"] == "123.5 nSv"
    assert cards["exposure"]["rows"] == [{"k": "Mean rate", "v": "1.48 \u00b5Sv/h"}, {"k": "Max rate", "v": "3.25 \u00b5Sv/h"}]
    assert "299.7" not in cards["exposure"]["value"] and "integrated instrument dose rate" in cards["exposure"]["title"]
    # four count-rate keys are one card
    assert cards["count_rates"]["rows"] == [{"k": "\u03b3 Gamma", "v": "271.5"}, {"k": "\u03b2 Beta", "v": "150.5"}, {"k": "\u03b1 Alpha", "v": "6.25"}]
    assert cards["count_rates"]["detail"] == "Peak total 480 cps"
    consumed = {"exposure_uSv", "mean_dose_rate_uSv_h", "max_dose_rate_uSv_h", "exposure_covered_s", "exposure_method", "exposure_during_acquisition",
                "mean_cps_gamma", "mean_cps_beta", "mean_cps_alpha", "max_cps_total", "time_notes", "live_time", "real_time", "count_time_minutes"}
    assert not consumed & set(cards)
    assert len(out["cards"]) == 7                                            # was 15 cards
    for c in out["cards"]:                                                   # no unrounded numbers anywhere
        text = " ".join([c["value"]] + [r["v"] for r in c.get("rows", [])] + [c.get("detail", "")])
        assert not any(len(tok.split(".")[-1]) >= 5 for tok in text.split() if tok.replace(".", "").isdigit() and "." in tok), text


def test_dose_values_follow_the_unit_preference(tmp_path):
    out = run_js(tmp_path, f"""
        const md = {LIVE};
        out.sv = m.describeMetadata(md, {{ doseUnit: 'uSv' }}).find((c) => c.key === 'exposure');
        out.rem = m.describeMetadata(md, {{ doseUnit: 'uRem' }}).find((c) => c.key === 'exposure');
    """)
    assert out["sv"]["value"] == "123.5 nSv" and out["rem"]["value"] == "12.3 \u00b5Rem"
    assert [r["v"] for r in out["rem"]["rows"]] == ["148 \u00b5Rem/h", "325 \u00b5Rem/h"]


def test_file_metadata_cards(tmp_path):
    out = run_js(tmp_path, """
        out.file = m.describeMetadata({ source: 'RadiaCode RadiaCode-110', start_time: '2026-10-02T17:43:30+00:00', channels: 1024, manufacturer: 'RadiaCode',
                                         model: 'RadiaCode-110', live_time: 1803, real_time: 1803, serial_number: 'UNKNOWN' }).map((c) => [c.key, c.label, c.value]);
        out.noTimes = m.describeMetadata({ live_time: 600, real_time: 600, source: 'X' }).map((c) => [c.key, c.label, c.value]);
        out.apart = m.describeMetadata({ live_time: 600, real_time: 580 }).map((c) => [c.key, c.label, c.value]);
        out.misc = m.describeMetadata({ calibration: { a0: 0, a1: 2.5 }, flag: true, empty: '', nothing: null, obj: { a: 1 }, note: 'hello', ratio_pct: 12.345,
                                         energy_calibration_slope: 2.9876, temperature_c: 29.5 }).map((c) => [c.label, c.value]);
        out.empty = [m.describeMetadata(null), m.describeMetadata({})];
    """)
    keys = [c[0] for c in out["file"]]
    assert "source" not in keys and "serial_number" not in keys                  # a repeat of manufacturer + model, and a placeholder
    assert dict((c[0], c[2]) for c in out["file"])["live_time"] == "30.1 min (1803 s)"
    assert out["noTimes"][0][1] == "Live = real time" and out["noTimes"][1][1] == "Source"
    assert [c[1] for c in out["apart"]] == ["Live time", "Real time"]            # different values stay two cards
    misc = dict((c[0], c[1]) for c in out["misc"])
    assert misc["Calibration"] == "2.50 keV/ch" and misc["Flag"] == "Yes" and misc["Empty"] == "\u2013" and misc["Nothing"] == "\u2013"
    assert misc["Obj"] == '{"a":1}' and misc["Note"] == "hello" and misc["Ratio"] == "12.35 %"
    assert misc["Calibration slope"] == "2.988" and misc["Temperature"] == "29.5 \u00b0C"
    assert out["empty"] == [[], []]


def test_a_dose_card_without_an_exposure_number_shows_the_summary_text(tmp_path):
    out = run_js(tmp_path, """
        out.a = m.describeMetadata({ exposure_during_acquisition: '10.0 nSv (mean 0.3, max 0.5 \\u00b5Sv/h)' });
        out.b = m.describeMetadata({ mean_dose_rate_uSv_h: 0.5 });
    """)
    assert out["a"][0]["value"] == "10.0 nSv (mean 0.3, max 0.5 \u00b5Sv/h)"
    assert out["b"][0]["value"] == "\u2013" and out["b"][0]["rows"] == [{"k": "Mean rate", "v": "0.50 \u00b5Sv/h"}]
