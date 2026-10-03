/**
 * Radiation alerts: configurable thresholds for the dose rate and the AlphaHound count rate.
 *
 * Replaces one fixed 2000 µRem/h banner that only the AlphaHound fed. Both devices now feed the same monitor; the
 * limits, a beep and a desktop notification are settings. The logic (when an alert starts and ends) is pure and
 * tested; AlertCenter adds the banner, the beep and the notification.
 *
 * An alert starts after two readings in a row above the limit (a single reading above twice the limit starts it at
 * once) and ends only when the value falls below 80 % of the limit, so a value hovering at the threshold does not
 * flicker.
 */

import { fromUSv, formatDoseRate, resolveUnit, getDosePref, unitLabel, safeStorage } from './units.js';

export const DEFAULT_ALERTS = Object.freeze({
    doseEnabled: true,      // the old banner was always on, at 2000 uRem/h = 20 uSv/h
    doseUSvH: 20,
    cpsEnabled: false,
    cps: 1000,
    sound: false,
    notify: false,
});
export const CLEAR_FRACTION = 0.8;
const STORE_KEY = 'alertSettings';

/** Settings from untrusted storage: unknown keys dropped, bad values replaced by the defaults. */
export function sanitizeAlerts(raw) {
    const d = DEFAULT_ALERTS;
    const r = raw && typeof raw === 'object' ? raw : {};
    const num = (v, fallback) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : fallback);
    const bool = (v, fallback) => (typeof v === 'boolean' ? v : fallback);
    return {
        doseEnabled: bool(r.doseEnabled, d.doseEnabled),
        doseUSvH: num(r.doseUSvH, d.doseUSvH),
        cpsEnabled: bool(r.cpsEnabled, d.cpsEnabled),
        cps: num(r.cps, d.cps),
        sound: bool(r.sound, d.sound),
        notify: bool(r.notify, d.notify),
    };
}

export function loadAlerts(storage = safeStorage()) {
    try {
        return sanitizeAlerts(JSON.parse(storage?.getItem(STORE_KEY) || 'null'));
    } catch (e) {
        return sanitizeAlerts(null);
    }
}

export function saveAlerts(settings, storage = safeStorage()) {
    const clean = sanitizeAlerts(settings);
    try { storage?.setItem(STORE_KEY, JSON.stringify(clean)); } catch (e) { /* ignore */ }
    return clean;
}

/** Start / end logic with hysteresis for one quantity. step() returns 'start', 'end' or null. */
export class AlertState {
    constructor() {
        this.active = false;
        this._above = 0;
    }

    step(value, limit, enabled = true) {
        if (!enabled || !(limit > 0) || !Number.isFinite(value)) {
            return this.clear();
        }
        if (!this.active) {
            this._above = value > limit ? this._above + 1 : 0;
            if (value > 2 * limit || this._above >= 2) {
                this.active = true;
                this._above = 0;
                return 'start';
            }
            return null;
        }
        if (value < limit * CLEAR_FRACTION) {
            this.active = false;
            this._above = 0;
            return 'end';
        }
        return null;
    }

    /** Forget everything (device disconnected, alert switched off): 'end' if one was active. */
    clear() {
        const was = this.active;
        this.active = false;
        this._above = 0;
        return was ? 'end' : null;
    }
}

/** Distance (m) at which a point source's rate would fall to the limit, from a reading taken at `atCm` (inverse square). */
export function safeDistanceM(rate, limit, atCm = 10) {
    if (!(rate > 0) || !(limit > 0) || rate <= limit) return 0;
    return (atCm * Math.sqrt(rate / limit)) / 100;
}

/** The banner, beep and notification for the monitored quantities. */
export class AlertCenter {
    /** @param {(key: string, active: boolean) => void} [onChange] called when an alert starts or ends */
    constructor(doc = document, storage = safeStorage(), onChange = null) {
        this.doc = doc;
        this.storage = storage;
        this.onChange = onChange;
        this.settings = loadAlerts(storage);
        this.states = { dose: new AlertState(), cps: new AlertState() };
        this.values = { dose: null, cps: null };
        this.dismissed = false;
        this.banner = null;
        this.linesEl = null;
        this._sig = null;
        this.audio = null;
    }

    reload() {
        this.settings = loadAlerts(this.storage);
        this.updateDose(this.values.dose);
        this.updateCps(this.values.cps);
    }

    /** @param {number|null} uSvPerHour the live dose rate */
    updateDose(uSvPerHour) {
        this.values.dose = uSvPerHour ?? null;
        this._step('dose', uSvPerHour, this.settings.doseUSvH, this.settings.doseEnabled);
    }

    /** @param {number|null} totalCps gamma + beta + alpha counts per second */
    updateCps(totalCps) {
        this.values.cps = totalCps ?? null;
        this._step('cps', totalCps, this.settings.cps, this.settings.cpsEnabled);
    }

    /** Device gone: stop alerting about readings that no longer arrive (all quantities, or the named ones). */
    reset(keys = Object.keys(this.states)) {
        for (const key of keys) {
            this.values[key] = null;
            this._apply(key, this.states[key].clear());
        }
    }

    _step(key, value, limit, enabled) {
        this._apply(key, this.states[key].step(value, limit, enabled));
        if (this.states[key].active) this._render();
    }

    _apply(key, change) {
        if (change && this.onChange) {
            try { this.onChange(key, change === 'start'); } catch (e) { /* a listener must not break monitoring */ }
        }
        if (change === 'start') {
            this.dismissed = false;
            this._render();
            this._signal(key);
        } else if (change === 'end') {
            this._render();
        }
    }

    _lines() {
        const lines = [];
        const pref = getDosePref(this.storage);
        if (this.states.dose.active) {
            const unit = resolveUnit(pref, 'uRem');
            const rate = formatDoseRate(this.values.dose, unit).text;
            const limit = formatDoseRate(this.settings.doseUSvH, unit).text;
            const dist = safeDistanceM(this.values.dose, this.settings.doseUSvH);
            lines.push({
                title: 'High dose rate',
                text: `${rate} (limit ${limit})`,
                extra: dist > 0 ? `Back to the limit at about ${dist.toFixed(1)} m (point source, from 10 cm)` : '',
            });
        }
        if (this.states.cps.active) {
            lines.push({
                title: 'High count rate',
                text: `${Math.round(this.values.cps).toLocaleString('en-US')} cps (limit ${Math.round(this.settings.cps).toLocaleString('en-US')} cps)`,
                extra: '',
            });
        }
        return lines;
    }

    _ensureBanner() {
        if (this.banner) return;
        this.banner = this.doc.createElement('div');
        this.banner.id = 'safety-alert';
        this.banner.className = 'safety-banner';
        this.banner.setAttribute('role', 'alert');
        this.banner.hidden = true;
        this.linesEl = this.doc.createElement('div');
        this.linesEl.className = 'safety-lines';
        const dismiss = this.doc.createElement('button');
        dismiss.type = 'button';
        dismiss.className = 'safety-dismiss';
        dismiss.textContent = 'Dismiss';
        dismiss.setAttribute('aria-label', 'Dismiss the warning (it returns if a new alert starts)');
        dismiss.addEventListener('click', () => {
            this.dismissed = true;
            this._sig = null;
            this.banner.hidden = true;
        });
        this.banner.append(this.linesEl, dismiss);
        this.doc.body.appendChild(this.banner);
    }

    /**
     * Shows the active alerts. The structure is rebuilt only when the set of alerts changes (so a screen reader hears
     * "High dose rate" once, and the Dismiss button keeps keyboard focus); the live values are updated in place.
     */
    _render() {
        const lines = this._lines();
        this._ensureBanner();
        const show = lines.length > 0 && !this.dismissed;
        this.banner.hidden = !show;
        if (!show) {
            this._sig = null;
            return;
        }
        const signature = lines.map((l) => l.title).join('|');
        if (signature !== this._sig) {
            this._sig = signature;
            this.linesEl.innerHTML = lines.map(() => `
                <div class="safety-line"><strong class="safety-title"></strong><span class="safety-value" aria-hidden="true"></span>
                    <small class="safety-extra" aria-hidden="true"></small><span class="sr-only"></span></div>`).join('');
            lines.forEach((l, i) => {
                const el = this.linesEl.children[i];
                el.querySelector('.safety-title').textContent = l.title;
                el.querySelector('.sr-only').textContent = `${l.title}: ${l.text}`;
            });
        }
        lines.forEach((l, i) => {
            const el = this.linesEl.children[i];
            el.querySelector('.safety-value').textContent = l.text;
            el.querySelector('.safety-extra').textContent = l.extra;
        });
    }

    _signal(key) {
        if (this.settings.sound) this._beep();
        if (this.settings.notify) this._notify(key);
    }

    _beep() {
        try {
            const Ctx = globalThis.AudioContext || globalThis.webkitAudioContext;
            if (!Ctx) return;
            this.audio = this.audio || new Ctx();
            const now = this.audio.currentTime;
            for (const offset of [0, 0.3]) {
                const osc = this.audio.createOscillator();
                const gain = this.audio.createGain();
                osc.frequency.value = 880;
                gain.gain.setValueAtTime(0.0001, now + offset);
                gain.gain.exponentialRampToValueAtTime(0.25, now + offset + 0.02);
                gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.22);
                osc.connect(gain).connect(this.audio.destination);
                osc.start(now + offset);
                osc.stop(now + offset + 0.25);
            }
        } catch (e) { /* no audio available */ }
    }

    _notify(key) {
        try {
            const N = globalThis.Notification;
            if (!N || N.permission !== 'granted' || !this.doc.hidden) return;   // only when the page is in the background
            const line = this._lines().find((l) => l.title === (key === 'dose' ? 'High dose rate' : 'High count rate'));
            if (line) new N(line.title, { body: line.text, tag: `radtrace-${key}` });
        } catch (e) { /* notifications unavailable */ }
    }

    /** For the Settings "Test" button: sound and notification as they would happen, without a real alert. */
    test() {
        if (this.settings.sound) this._beep();
        const N = globalThis.Notification;
        if (this.settings.notify && N && N.permission === 'granted') {
            try { new N('RadTrace test alert', { body: 'Alerts are working.', tag: 'radtrace-test' }); } catch (e) { /* ignore */ }
        }
    }
}

/** Human text for the threshold field: the limit converted to the unit on screen. */
export function thresholdForUnit(uSvPerHour, unit) {
    return { value: Number(fromUSv(uSvPerHour, unit).toPrecision(4)), label: unitLabel(unit) };
}
