"""Dose units (static/js/units.js) and alert logic (static/js/alerts.js) under Node.

The banner, beep and notification need a browser: the smoke test covers them. Skipped when Node is not installed."""
import json
import pathlib
import shutil
import subprocess

import pytest

JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(tmp_path, body):
    script = tmp_path / "t.mjs"
    script.write_text(
        f"import * as u from '{(JS / 'units.js').as_uri()}';\nimport * as a from '{(JS / 'alerts.js').as_uri()}';\n"
        "const out = {};\n"
        "const fake = (init = {}) => { const d = { ...init }; return { getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); }, d }; };\n"
        + body + "\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_dose_rate_formatting_in_both_units(tmp_path):
    out = run_js(tmp_path, """
        const f = (v, unit) => u.formatDoseRate(v, unit).text;
        out.sv = [0, 0.0004, 0.05, 0.12, 1.5, 12.34, 123.4, 999.9, 1000, 2500, 25000].map((v) => f(v, 'uSv'));
        out.rem = [0, 0.12, 0.64, 1, 25, 640, 2500, 100000].map((v) => f(v, 'uRem'));
        out.none = [f(null, 'uSv'), f(undefined, 'uRem'), f(NaN, 'uSv'), f(-3, 'uSv')];
        out.parts = u.formatDoseRate(0.61, 'uRem');
    """)
    assert out["sv"] == ["0.00 nSv/h", "0.40 nSv/h", "50.0 nSv/h", "0.12 µSv/h", "1.50 µSv/h", "12.3 µSv/h", "123 µSv/h",
                         "1.00 mSv/h", "1.00 mSv/h", "2.50 mSv/h", "25.00 mSv/h"]       # 999.9 rounds up into the next prefix
    assert out["rem"] == ["0.00 µRem/h", "12.0 µRem/h", "64.0 µRem/h", "100 µRem/h", "2.50 mRem/h", "64.00 mRem/h", "250.00 mRem/h", "10000.00 mRem/h"]
    assert out["none"] == ["-- µSv/h", "-- µRem/h", "-- µSv/h", "0.00 nSv/h"]
    assert out["parts"] == {"value": "61.0", "unit": "µRem/h", "text": "61.0 µRem/h"}


def test_dose_totals_and_conversions(tmp_path):
    out = run_js(tmp_path, """
        out.sv = [0.0005, 0.5, 1, 12.345, 1500, null].map((v) => u.formatDoseTotal(v, 'uSv'));
        out.rem = [0.05, 0.5, 8, 12.346, 20, 20000, null].map((v) => u.formatDoseTotal(v, 'uRem'));
        out.conv = [u.toUSv(2000, 'uRem'), u.toUSv(20, 'uSv'), u.fromUSv(20, 'uRem'), u.fromUSv(0.5, 'uSv')];
        out.resolve = [u.resolveUnit('auto', 'uRem'), u.resolveUnit('auto', 'uSv'), u.resolveUnit('uSv', 'uRem'), u.resolveUnit('uRem', 'uSv'),
                       u.resolveUnit('junk', 'uRem'), u.resolveUnit(undefined, 'weird')];
        out.labels = [u.unitLabel('uRem'), u.unitLabel('uSv'), u.unitLabel('x')];
    """)
    assert out["sv"] == ["0.5 nSv", "500.0 nSv", "1.00 µSv", "12.35 µSv", "1.500 mSv", "--"]
    assert out["rem"] == ["5.00 µRem", "50.0 µRem", "800 µRem", "1.235 mRem", "2.000 mRem", "2.000 Rem", "--"]
    assert out["conv"] == [20, 20, 2000, 0.5]
    assert out["resolve"] == ["uRem", "uSv", "uSv", "uRem", "uRem", "uSv"]
    assert out["labels"] == ["µRem/h", "µSv/h", "µSv/h"]


def test_unit_preference_is_stored_and_survives_blocked_storage(tmp_path):
    out = run_js(tmp_path, """
        const s = fake();
        out.dflt = u.getDosePref(s);
        out.set = [u.setDosePref('uRem', s), u.getDosePref(s), s.d.doseUnit];
        out.junk = [u.setDosePref('furlongs', s), u.getDosePref(s)];
        const broken = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
        out.blocked = [u.getDosePref(broken), u.setDosePref('uSv', broken), u.getDosePref(null)];
    """)
    assert out["dflt"] == "auto" and out["set"] == ["uRem", "uRem", "uRem"] and out["junk"] == ["auto", "auto"]
    assert out["blocked"] == ["auto", "uSv", "auto"]


def test_alert_start_and_end_with_hysteresis(tmp_path):
    out = run_js(tmp_path, """
        const st = new a.AlertState();
        const seq = (values, limit = 100) => values.map((v) => st.step(v, limit));
        out.hover = seq([90, 120, 90, 120, 90]);                // above the limit once at a time: never starts
        out.start = seq([120, 130]);                            // two in a row starts it
        out.stays = seq([95, 85, 81, 120]);                     // between 80 % and 100 % it stays active
        out.end = seq([79, 50]);                                // below 80 % ends it, once
        out.spike = seq([250]);                                 // over twice the limit starts at once
        out.after = [st.active, st.step(10, 100), st.active];
    """)
    assert out["hover"] == [None] * 5
    assert out["start"] == [None, "start"]
    assert out["stays"] == [None] * 4
    assert out["end"] == ["end", None]
    assert out["spike"] == ["start"]
    assert out["after"] == [True, "end", False]


def test_alert_state_edge_cases(tmp_path):
    out = run_js(tmp_path, """
        const st = new a.AlertState();
        out.off = [st.step(500, 100, false), st.active];
        out.nolimit = [st.step(500, 0), st.step(500, -4), st.step(500, NaN)];
        out.nan = [st.step(NaN, 100), st.step(null, 100), st.step(undefined, 100)];
        st.step(500, 100);
        out.disabledWhileActive = [st.active, st.step(500, 100, false), st.active];     // switching the alert off ends it
        st.step(500, 100);
        out.clear = [st.active, st.clear(), st.clear(), st.active];
        st.step(500, 100); st.step(500, 100);
        out.noValueEnds = [st.active, st.step(null, 100), st.active];                  // readings stop (device gone): the alert ends
    """)
    assert out["off"] == [None, False]
    assert out["nolimit"] == [None, None, None]
    assert out["nan"] == [None, None, None]
    assert out["disabledWhileActive"] == [True, "end", False]
    assert out["clear"] == [True, "end", None, False]
    assert out["noValueEnds"] == [True, "end", False]


def test_alert_settings_are_sanitized_and_stored(tmp_path):
    out = run_js(tmp_path, """
        out.dflt = a.sanitizeAlerts(null);
        out.defaults = a.DEFAULT_ALERTS;
        out.junk = a.sanitizeAlerts({ doseEnabled: 'yes', doseUSvH: -5, cps: 'abc', sound: 1, notify: true, extra: 1 });
        out.good = a.sanitizeAlerts({ doseEnabled: false, doseUSvH: '0.5', cpsEnabled: true, cps: 250, sound: true });
        const s = fake();
        out.empty = a.loadAlerts(s);
        a.saveAlerts({ doseUSvH: 3, notify: true, bogus: 1 }, s);
        out.saved = [a.loadAlerts(s), 'bogus' in JSON.parse(s.d.alertSettings)];
        out.corrupt = a.loadAlerts(fake({ alertSettings: '{not json' }));
        out.blocked = a.loadAlerts({ getItem() { throw new Error('x'); } });
        out.thr = [a.thresholdForUnit(20, 'uRem'), a.thresholdForUnit(0.123456, 'uSv'), a.CLEAR_FRACTION];
    """)
    assert out["dflt"] == out["defaults"] == {"doseEnabled": True, "doseUSvH": 20, "cpsEnabled": False, "cps": 1000, "sound": False, "notify": False}
    assert out["junk"] == {"doseEnabled": True, "doseUSvH": 20, "cpsEnabled": False, "cps": 1000, "sound": False, "notify": True}
    assert out["good"] == {"doseEnabled": False, "doseUSvH": 0.5, "cpsEnabled": True, "cps": 250, "sound": True, "notify": False}
    assert out["empty"] == out["defaults"]
    assert out["saved"][0]["doseUSvH"] == 3 and out["saved"][0]["notify"] is True and out["saved"][1] is False
    assert out["corrupt"] == out["defaults"] and out["blocked"] == out["defaults"]
    assert out["thr"][0] == {"value": 2000, "label": "µRem/h"} and out["thr"][1]["value"] == 0.1235 and out["thr"][2] == 0.8


def test_default_dose_limit_matches_the_old_fixed_banner():
    # The previous banner fired at 2000 uRem/h; the default limit (20 uSv/h) is the same dose rate.
    assert 20 * 100 == 2000


def test_safe_distance(tmp_path):
    out = run_js(tmp_path, """
        out.d = [a.safeDistanceM(80, 20), a.safeDistanceM(20, 20), a.safeDistanceM(10, 20), a.safeDistanceM(0, 20), a.safeDistanceM(50, 0),
                 a.safeDistanceM(500, 20, 50), a.safeDistanceM(NaN, 20)];
    """)
    assert out["d"] == [0.2, 0, 0, 0, 0, 2.5, 0]                  # 10 cm * sqrt(80/20) = 20 cm; inverse-square


def test_device_alarm_limits_rows(tmp_path):
    out = run_js(tmp_path, """
        const sv = { l1_dose_rate: 0.5, l2_dose_rate: 1.0, l1_count_rate: 100, l2_count_rate: 200.5, count_unit: 'cps',
                     l1_dose: 0.00001, l2_dose: 0.0001, dose_unit: 'Sv' };
        out.sv = u.formatAlarmLimits(sv, 'uSv');
        out.svRem = u.formatAlarmLimits(sv, 'uRem');
        const r = { l1_dose_rate: 50, l2_dose_rate: 100, l1_count_rate: 60, l2_count_rate: 120, count_unit: 'cpm', l1_dose: 0.001, l2_dose: null, dose_unit: 'R' };
        out.r = [u.formatAlarmLimits(r, 'uSv'), u.formatAlarmLimits(r, 'uRem')];
        out.partial = u.formatAlarmLimits({ l1_dose_rate: null, l2_dose_rate: 2, l1_count_rate: null, l2_count_rate: null, dose_unit: 'Sv' }, 'uSv');
        out.none = [u.formatAlarmLimits(null, 'uSv'), u.formatAlarmLimits({}, 'uSv'), u.formatAlarmLimits('x', 'uSv')];
    """)
    assert out["sv"] == [
        {"label": "Dose rate", "value": "0.50 µSv/h / 1.00 µSv/h"},
        {"label": "Count rate", "value": "100 cps / 200.5 cps"},
        {"label": "Accumulated dose", "value": "10.00 µSv / 100.00 µSv"},
    ]
    assert out["svRem"][0]["value"] == "50.0 µRem/h / 100 µRem/h"
    assert out["r"][0][0]["value"] == "0.50 µSv/h / 1.00 µSv/h"          # 50 uR/h = 0.5 uSv/h (about 100 uR per uSv)
    assert out["r"][1][0]["value"] == "50.0 µRem/h / 100 µRem/h"
    assert out["r"][0][1]["value"] == "60 cpm / 120 cpm"
    assert out["r"][0][2]["value"] == "10.00 µSv / --"                         # 0.001 R = 1000 uR = 10 uSv; a missing level shows "--"
    assert out["partial"] == [{"label": "Dose rate", "value": "-- / 2.00 µSv/h"}]      # missing registers shown as "--", empty rows dropped
    assert out["none"] == [[], [], []]
